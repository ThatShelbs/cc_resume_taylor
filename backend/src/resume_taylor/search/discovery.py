"""Find how to pull a company's postings straight from its careers page.

Per company, in order: (1) fingerprint a known careers URL, (2) probe the public board APIs
with slug variants of the name (accepted only when the board plainly belongs to that company),
(3) ask Claude, with web tools and the career-page-discovery skill, for the careers URL, the ATS
board and the company's own job-search URL of whatever is still unresolved.

A route is only accepted when it returns postings. A board that exists but lists nothing never ends
the search: the company's own site search and careers page are tried next, and only when everything
is empty is the company saved as "empty" (looked at again within a week) rather than "connected"."""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

from resume_taylor.config import CAREER_DISCOVERY_SKILL_PATH
from resume_taylor.pipeline.prompts import load_skill
from resume_taylor.pipeline.runtime import warn

from . import claude
from .connectors import connector_for
from .normalize import norm_company
from .routes import RouteBook

_LOCALE = r"(?:[a-z]{2}(?:-[A-Za-z]{2})?/)?"
_PATTERNS = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)", re.I)),
]
_WORKDAY = re.compile(rf"([A-Za-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/{_LOCALE}([A-Za-z0-9_-]+)", re.I)
_WORKDAY_SITE = re.compile(rf"(wd\d+)\.myworkdaysite\.com/{_LOCALE}recruiting/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+)", re.I)
_EIGHTFOLD = re.compile(r"([A-Za-z0-9-]+\.eightfold\.ai)", re.I)
_RESERVED = {"embed", "v1", "api", "jobs", "careers", "en", "wday", "recruiting", "job", "search"}

# ATS types whose list calls are real APIs: zero postings means "no openings", not "wrong route".
_API_ATS = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "workday", "eightfold")


def fingerprint(text: str) -> dict | None:
    """A route from any URL or HTML that mentions a known ATS, else None."""
    if not text:
        return None
    for m in _WORKDAY.finditer(text):  # keep looking past a locale or reserved first match
        tenant, wd, site = m.groups()
        if site.lower() not in _RESERVED:
            return {"ats": "workday", "host": f"{tenant}.{wd}.myworkdayjobs.com", "tenant": tenant, "site": site}
    for m in _WORKDAY_SITE.finditer(text):
        wd, tenant, site = m.groups()
        return {"ats": "workday", "host": f"{wd}.myworkdaysite.com", "tenant": tenant, "site": site, "recruiting": True}
    for ats, pat in _PATTERNS:
        for m in pat.finditer(text):
            token = m.group(1)
            if token.lower() not in _RESERVED:
                return {"ats": ats, "token": token}
    m = _EIGHTFOLD.search(text)
    if m:
        dom = parse_qs(urlsplit(text).query).get("domain") or re.findall(r"domain=([A-Za-z0-9.-]+)", text)
        if dom:
            return {"ats": "eightfold", "host": m.group(1), "domain": dom[0]}
    return None


_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|plc|gmbh|group|holdings|the)\b\.?", re.I)


def slug_variants(name: str) -> list[str]:
    base = _SUFFIX.sub(" ", name.lower())
    words = re.findall(r"[a-z0-9]+", base)
    if not words:
        return []
    out = ["".join(words), "-".join(words)]
    if len(words) > 1:
        out.append(words[0])
    seen, uniq = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def _name_matches(board_name: str, company: str, strict: bool = False) -> bool:
    a, b = norm_company(board_name), norm_company(company)
    if not (a and b):
        return False
    if a == b:
        return True
    return not strict and min(len(a), len(b)) >= 5 and (a in b or b in a)


def probe(client, company: str) -> tuple[dict, int] | None:
    """Try the public board APIs under slug variants. Returns (route, job_count) or None."""
    from .connectors import ashby, lever

    words = re.findall(r"[a-z0-9]+", _SUFFIX.sub(" ", company.lower()))
    full = ("".join(words), "-".join(words))
    for slug in slug_variants(company)[:3]:
        exact = slug in full
        strict = not exact  # the first word alone ("johnson") must be the whole name of the board
        info = client.get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}")
        if info and _name_matches(info.get("name", ""), company, strict):
            return {"ats": "greenhouse", "token": slug}, -1
        info = client.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
        if info and _name_matches(info.get("name", ""), company, strict):
            return {"ats": "workable", "token": slug}, -1
        sr = client.get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 1})
        if sr and sr.get("content") and _name_matches((sr["content"][0].get("company") or {}).get("name", ""), company, strict):
            return {"ats": "smartrecruiters", "token": slug}, -1
        if exact:  # these two APIs do not name the company, so only trust the unambiguous slug
            for mod, ats in ((lever, "lever"), (ashby, "ashby")):
                if client.get_json(mod.API.format(token=slug), params={"mode": "json"} if ats == "lever" else None):
                    return {"ats": ats, "token": slug}, -1
    return None


def validate(client, route: dict, company: str) -> int | None:
    """How many postings the route returns (0 is a real answer), or None if it cannot be read."""
    conn = connector_for(route)
    if not conn:
        return None
    queries = [""] if route["ats"] in ("workday", "eightfold", "site_search") else []
    try:
        return len(conn.list_jobs(client, route, company, queries))
    except (KeyError, ValueError, TypeError):
        return None


def _resolve_deterministic(client, company: str, careers_url: str) -> tuple[dict, str] | None:
    if careers_url:
        route = fingerprint(careers_url)
        if not route:
            html = client.get_text(careers_url, robots=True)
            route = fingerprint(html or "")
        if route:
            return route, "fingerprint"
    found = probe(client, company)
    if found:
        return found[0], "probe"
    return None


def _same_route(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def _candidates(client, hit: dict, careers_url: str) -> list[dict]:
    """Routes to try for one company, best first: its ATS board, then its own site search, then the
    careers page read page by page."""
    cands: list[dict] = []
    for src in (hit.get("ats_url", ""), careers_url):
        r = fingerprint(src)
        if r:
            cands.append(r)
    if not cands and careers_url:
        r = fingerprint(client.get_text(careers_url, robots=True) or "")
        if r:
            cands.append(r)
    search_url = (hit.get("search_url") or "").strip()
    if search_url.startswith("http"):
        cands.append({"ats": "site_search", "search_url": search_url, "careers_url": careers_url})
    if careers_url:
        cands.append({"ats": "careers_page", "careers_url": careers_url})
    uniq: list[dict] = []
    for r in cands:
        if not any(_same_route(r, u) for u in uniq):
            uniq.append(r)
    return uniq


def discover_routes(client, book: RouteBook, companies: list[dict], *, force: bool = False,
                    model: str | None = None, effort: str | None = None, progress=print) -> dict[str, dict]:
    """companies: [{name, careers_url?}]. Fills `book`; returns {name: route record}."""
    results: dict[str, dict] = {}
    todo = []
    for c in companies:
        existing = book.usable(c["name"])
        changed_url = bool(c.get("careers_url")) and (existing or {}).get("careers_url") != c["careers_url"]
        if existing and not force and not changed_url:
            results[c["name"]] = existing
        elif not force and not changed_url and (failed := book.recent_failure(c["name"])):
            results[c["name"]] = failed  # looked for recently and found nothing; retry in a few days
        else:
            todo.append(c)

    empty_found: dict[str, dict] = {}  # name -> a working board that lists nothing right now

    def work(c):
        found = _resolve_deterministic(client, c["name"], c.get("careers_url", ""))
        if not found:
            return c, None
        route, method = found
        return c, (route, method, validate(client, route, c["name"]))

    pending = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for c, found in pool.map(work, todo):
            if found and found[2]:
                route, method, count = found
                results[c["name"]] = book.set(c["name"], {**route, "careers_url": c.get("careers_url", "")}, method=method, job_count=count)
                progress(f"{c['name']}: {route['ats']}, {count} postings")
            else:
                if found and found[2] == 0 and found[0]["ats"] in _API_ATS:
                    empty_found[c["name"]] = {**found[0], "careers_url": c.get("careers_url", "")}
                pending.append(c)

    # Claude, with web tools, for what the deterministic steps could not place or found empty.
    if pending:
        rules = load_skill(CAREER_DISCOVERY_SKILL_PATH)
        for i in range(0, len(pending), 10):
            batch = pending[i:i + 10]
            listing = "\n".join(f"- {c['name']}" + (f" (careers page: {c['careers_url']})" if c.get("careers_url") else "") for c in batch)
            reply = claude.ask(
                rules + "\n\nTask: DISCOVER. Reply with JSON only: {\"companies\": [{\"name\": str, \"careers_url\": str, "
                "\"ats_url\": str, \"search_url\": str, \"notes\": str}]}.",
                f"Find the official careers page, applicant-tracking board and job-search URL for each company:\n{listing}",
                tools=claude.WEB_TOOLS, model=model, effort=effort, label="Career-page discovery",
            )
            by_name = {norm_company(x.get("name", "")): x for x in (reply or {}).get("companies", []) if isinstance(x, dict)}
            for c in batch:
                hit = by_name.get(norm_company(c["name"]), {})
                url = hit.get("careers_url") or c.get("careers_url") or ""
                search_url = (hit.get("search_url") or "").strip()
                extra = {"careers_url": url, "search_url": search_url if search_url.startswith("http") else ""}
                chosen = None
                for route in _candidates(client, hit, url):
                    if c["name"] in empty_found and _same_route({k: v for k, v in route.items() if k != "careers_url"},
                                                                 {k: v for k, v in empty_found[c["name"]].items() if k != "careers_url"}):
                        continue  # already known to list nothing
                    count = validate(client, route, c["name"])
                    if count:
                        chosen = (route, count)
                        break
                    if count == 0 and route["ats"] in _API_ATS and c["name"] not in empty_found:
                        empty_found[c["name"]] = route
                if chosen:
                    route, count = chosen
                    note = "Read from the page itself; fewer fields than an ATS feed." if route["ats"] == "careers_page" else ""
                    results[c["name"]] = book.set(c["name"], {**route, **extra, "ats": route["ats"]}, method="claude", job_count=count, note=note)
                    progress(f"{c['name']}: {route['ats'].replace('_', ' ')}, {count} postings")
                elif c["name"] in empty_found:
                    results[c["name"]] = book.set(c["name"], {**empty_found[c["name"]], **extra}, method="claude", job_count=0,
                                                  status="empty", note="Career site found, but it lists no openings right now.")
                    progress(f"{c['name']}: {empty_found[c['name']]['ats']}, no openings right now")
                else:
                    results[c["name"]] = book.set(c["name"], {"ats": "", **extra}, method="none", job_count=None,
                                                  status="failed", note=hit.get("notes") or "No careers page found.")
                    warn(f"No postings route found for {c['name']}.")
    book.save()
    return results

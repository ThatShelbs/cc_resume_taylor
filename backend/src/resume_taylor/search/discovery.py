"""Find how to pull a company's postings straight from its careers page.

Per company, in order: (1) fingerprint a known careers URL, (2) probe the public board APIs
with slug variants of the name (accepted only when the board plainly belongs to that company),
(3) ask Claude, with web tools and the career-page-discovery skill, for the careers URL and
ATS board of whatever is still unresolved. Every route is validated by pulling its job list."""

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

_PATTERNS = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)", re.I)),
]
_WORKDAY = re.compile(
    r"([A-Za-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}(?:-[A-Z]{2})?/)?([A-Za-z0-9_-]+)", re.I
)
_EIGHTFOLD = re.compile(r"([A-Za-z0-9-]+\.eightfold\.ai)", re.I)
_RESERVED = {"embed", "v1", "api", "jobs", "careers", "en", "wday"}


def fingerprint(text: str) -> dict | None:
    """A route from any URL or HTML that mentions a known ATS, else None."""
    if not text:
        return None
    m = _WORKDAY.search(text)
    if m and m.group(3).lower() not in _RESERVED:
        tenant, wd, site = m.groups()
        return {"ats": "workday", "host": f"{tenant}.{wd}.myworkdayjobs.com", "tenant": tenant, "site": site}
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


def _name_matches(board_name: str, company: str) -> bool:
    a, b = norm_company(board_name), norm_company(company)
    return bool(a and b and (a == b or a in b or b in a))


def probe(client, company: str) -> tuple[dict, int] | None:
    """Try the public board APIs under slug variants. Returns (route, job_count) or None."""
    from .connectors import ashby, lever

    for slug in slug_variants(company)[:3]:
        exact = slug in ("".join(re.findall(r"[a-z0-9]+", _SUFFIX.sub(" ", company.lower()))),)
        info = client.get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}")
        if info and _name_matches(info.get("name", ""), company):
            return {"ats": "greenhouse", "token": slug}, -1
        info = client.get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
        if info and _name_matches(info.get("name", ""), company):
            return {"ats": "workable", "token": slug}, -1
        sr = client.get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings", params={"limit": 1})
        if sr and sr.get("content") and _name_matches((sr["content"][0].get("company") or {}).get("name", ""), company):
            return {"ats": "smartrecruiters", "token": slug}, -1
        if exact:  # these two APIs do not name the company, so only trust the unambiguous slug
            for mod, ats in ((lever, "lever"), (ashby, "ashby")):
                if client.get_json(mod.API.format(token=slug), params={"mode": "json"} if ats == "lever" else None):
                    return {"ats": ats, "token": slug}, -1
    return None


def validate(client, route: dict, company: str) -> int | None:
    """Number of postings the route returns, or None if it returns nothing usable."""
    conn = connector_for(route)
    if not conn:
        return None
    try:
        jobs = conn.list_jobs(client, route, company, [""] if route["ats"] in ("workday", "eightfold") else [])
    except (KeyError, ValueError, TypeError):
        return None
    return len(jobs) if jobs or route["ats"] in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters") else None


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


def discover_routes(client, book: RouteBook, companies: list[dict], *, force: bool = False,
                    model: str | None = None, effort: str | None = None, progress=print) -> dict[str, dict]:
    """companies: [{name, careers_url?}]. Fills `book`; returns {name: route record}."""
    results: dict[str, dict] = {}
    todo = []
    for c in companies:
        existing = book.usable(c["name"])
        if existing and not force and not (c.get("careers_url") and existing.get("careers_url") != c["careers_url"]):
            results[c["name"]] = existing
        else:
            todo.append(c)

    def work(c):
        found = _resolve_deterministic(client, c["name"], c.get("careers_url", ""))
        if not found:
            return c, None
        route, method = found
        count = validate(client, route, c["name"])
        return c, (route, method, count)

    pending = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for c, found in pool.map(work, todo):
            if found and found[2] is not None:
                route, method, count = found
                results[c["name"]] = book.set(c["name"], {**route, "careers_url": c.get("careers_url", "")}, method=method, job_count=count)
                progress(f"{c['name']}: {route['ats']}, {count} postings")
            else:
                pending.append(c)

    # Claude, with web tools, for what the deterministic steps could not place.
    if pending:
        rules = load_skill(CAREER_DISCOVERY_SKILL_PATH)
        for i in range(0, len(pending), 10):
            batch = pending[i:i + 10]
            listing = "\n".join(f"- {c['name']}" + (f" (careers page: {c['careers_url']})" if c.get("careers_url") else "") for c in batch)
            reply = claude.ask(
                rules + "\n\nTask: DISCOVER. Reply with JSON only: {\"companies\": [{\"name\": str, \"careers_url\": str, \"ats_url\": str, \"notes\": str}]}.",
                f"Find the official careers page and applicant-tracking board for each company:\n{listing}",
                tools=claude.WEB_TOOLS, model=model, effort=effort, label="Career-page discovery",
            )
            by_name = {norm_company(x.get("name", "")): x for x in (reply or {}).get("companies", []) if isinstance(x, dict)}
            for c in batch:
                hit = by_name.get(norm_company(c["name"]), {})
                url = hit.get("careers_url") or c.get("careers_url") or ""
                route = fingerprint(hit.get("ats_url", "")) or fingerprint(url)
                method = "claude"
                if not route and url:
                    route = fingerprint(client.get_text(url, robots=True) or "")
                if route:
                    count = validate(client, route, c["name"])
                    if count is not None:
                        results[c["name"]] = book.set(c["name"], {**route, "careers_url": url}, method=method, job_count=count)
                        progress(f"{c['name']}: {route['ats']}, {count} postings")
                        continue
                if url:
                    route = {"ats": "careers_page", "careers_url": url}
                    count = validate(client, route, c["name"])
                    if count:
                        results[c["name"]] = book.set(c["name"], route, method="claude", job_count=count,
                                                      note="Read from the page itself; fewer fields than an ATS feed.")
                        progress(f"{c['name']}: careers page, {count} postings")
                        continue
                results[c["name"]] = book.set(c["name"], {"ats": "", "careers_url": url}, method="none", job_count=None,
                                              status="failed", note=hit.get("notes") or "No careers page found.")
                warn(f"No postings route found for {c['name']}.")
    book.save()
    return results

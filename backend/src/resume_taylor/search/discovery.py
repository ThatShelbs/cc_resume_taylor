"""Find how to pull a company's postings straight from its careers page.

Per company, in order: (1) fingerprint a known careers URL: its address, its HTML, the page behind
its "Search jobs" link, and for a page built by JavaScript one headless render of it; (2) probe the
public board APIs with slug variants of the name (accepted only when the board plainly belongs to
that company); (3) ask Claude, with web tools and the career-page-discovery skill, for the careers
URL, ATS board and search URL of whatever is still unresolved. Every route is validated by pulling
its job list.

Every route keeps the company's own careers page (`careers_url`) next to the ATS board
(`board_url`), so results can always link a person straight to the company. Routes found without a
careers page get one looked up once (`careers_url_checked`)."""

import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

from resume_taylor.config import CAREER_DISCOVERY_SKILL_PATH
from resume_taylor.pipeline.prompts import load_skill
from resume_taylor.pipeline.runtime import warn

from . import claude
from . import render as rendering
from .connectors import EMPTY_OK, connector_for
from .normalize import norm_company
from .routes import RouteBook, is_company_page

_PATTERNS = [
    ("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([A-Za-z0-9_-]+)", re.I)),
    ("greenhouse", re.compile(r"boards-api\.greenhouse\.io/v1/boards/([A-Za-z0-9_-]+)", re.I)),
    ("lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([A-Za-z0-9_-]+)", re.I)),
    ("ashby", re.compile(r"jobs\.ashbyhq\.com/([A-Za-z0-9_.%-]+)", re.I)),
    ("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([A-Za-z0-9_-]+)", re.I)),
    ("workable", re.compile(r"apply\.workable\.com/([A-Za-z0-9_-]+)", re.I)),
    ("recruitee", re.compile(r"([A-Za-z0-9-]+)\.recruitee\.com", re.I)),
    ("bamboohr", re.compile(r"([A-Za-z0-9-]+)\.bamboohr\.com/(?:careers|jobs)", re.I)),
    ("breezy", re.compile(r"([A-Za-z0-9-]+)\.breezy\.hr", re.I)),
    ("rippling", re.compile(r"ats\.rippling\.com/(?:api/v2/board/)?([A-Za-z0-9_-]+)", re.I)),
]
_TEAMTAILOR = re.compile(r"([A-Za-z0-9-]+\.teamtailor\.com)", re.I)
_WORKDAY = re.compile(
    r"([A-Za-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}(?:-[A-Z]{2})?/)?([A-Za-z0-9_-]+)", re.I
)
_EIGHTFOLD = re.compile(r"([A-Za-z0-9-]+\.eightfold\.ai)", re.I)
_RESERVED = {"embed", "v1", "api", "jobs", "careers", "en", "wday", "www", "app", "help", "assets", "cdn", "static"}


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
    m = _TEAMTAILOR.search(text)
    if m and m.group(1).split(".")[0].lower() not in _RESERVED:
        return {"ats": "teamtailor", "host": m.group(1).lower()}
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
        rc = client.get_json(f"https://{slug}.recruitee.com/api/offers/")
        if rc and rc.get("offers") and _name_matches(rc["offers"][0].get("company_name", ""), company):
            return {"ats": "recruitee", "token": slug}, -1
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
    return len(jobs) if jobs or route["ats"] in EMPTY_OK else None


def _fingerprint_page(url: str, html: str, links: list[str]) -> dict | None:
    route = fingerprint(html or "") or fingerprint(" ".join(links))
    if not route and "teamtailor-cdn" in (html or ""):  # a Teamtailor site on the company's own domain
        route = {"ats": "teamtailor", "host": urlsplit(url).netloc.lower()}
    return route


def fingerprint_careers_page(client, careers_url: str) -> dict | None:
    """The ATS behind a careers page: its URL, its HTML, the page its 'Search jobs' link opens, and,
    when the page is built by JavaScript, the same checks on one headless render."""
    route = fingerprint(careers_url)
    if route or not client.allowed_by_robots(careers_url):
        return route
    html = client.get_text(careers_url, robots=True) or ""
    anchors = rendering.static_anchors(html, careers_url)
    route = _fingerprint_page(careers_url, html, [h for h, _ in anchors])
    for link in ([] if route else rendering.job_search_links(anchors)):
        route = fingerprint(link) or (_fingerprint_page(link, client.get_text(link, robots=True) or "", [])
                                      if client.allowed_by_robots(link) else None)
        if route:
            return route
    if route:
        return route
    page = rendering.render(careers_url)
    if not page:
        return None
    route = _fingerprint_page(page.url, page.html, [h for h, _ in page.anchors] + page.frames)
    for link in ([] if route else rendering.job_search_links(page.anchors)):
        route = fingerprint(link)
        if not route and client.allowed_by_robots(link):
            inner = rendering.render(link)
            route = _fingerprint_page(link, inner.html, [h for h, _ in inner.anchors] + inner.frames) if inner else None
        if route:
            break
    return route


def _resolve_deterministic(client, company: str, careers_url: str) -> tuple[dict, str] | None:
    if careers_url:
        route = fingerprint_careers_page(client, careers_url)
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
    backfill: list[dict] = []
    for c in companies:
        existing = book.usable(c["name"])
        if existing and not force and not (c.get("careers_url") and existing.get("careers_url") != c["careers_url"]):
            results[c["name"]] = existing
            if not existing.get("careers_url") and not existing.get("careers_url_checked"):
                backfill.append(c)
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
                if not c.get("careers_url"):
                    backfill.append(c)
            else:
                pending.append(c)

    # Claude, with web tools, for what the deterministic steps could not place, plus the careers
    # page of companies whose job board was found without one.
    todo_claude = [(c, False) for c in pending] + [(c, True) for c in backfill]
    if todo_claude:
        rules = load_skill(CAREER_DISCOVERY_SKILL_PATH)
        for i in range(0, len(todo_claude), 10):
            batch = todo_claude[i:i + 10]
            listing = "\n".join(f"- {c['name']}" + (f" (careers page: {c['careers_url']})" if c.get("careers_url") else "")
                                + (f" (job board already known: {results[c['name']].get('board_url', '')})" if only else "")
                                for c, only in batch)
            reply = claude.ask(
                rules + "\n\nTask: DISCOVER. Reply with JSON only: {\"companies\": [{\"name\": str, \"careers_url\": str, "
                "\"ats_url\": str, \"search_url\": str, \"notes\": str}]}.",
                f"Find the official careers page and applicant-tracking board for each company:\n{listing}",
                tools=claude.WEB_TOOLS, model=model, effort=effort, label="Career-page discovery",
            )
            by_name = {norm_company(x.get("name", "")): x for x in (reply or {}).get("companies", []) if isinstance(x, dict)}
            for c, only in batch:
                hit = by_name.get(norm_company(c["name"]), {})
                found_url = str(hit.get("careers_url") or "").strip()
                found_url = found_url if is_company_page(found_url) else ""
                search = _search_template(str(hit.get("search_url") or ""), found_url or c.get("careers_url", ""))
                if only:  # the board is known; keep only the careers page (and its search link) Claude found
                    rec = results[c["name"]]
                    rec.update({"careers_url": found_url or rec.get("careers_url", ""), "careers_url_checked": True})
                    if search:
                        rec["search_url"] = search
                    continue
                url = c.get("careers_url") or found_url
                route = fingerprint(hit.get("ats_url", "")) or (fingerprint_careers_page(client, url) if url else None)
                method = "claude"
                if route:
                    count = validate(client, route, c["name"])
                    if count is not None:
                        extra = {"careers_url": url, **({"search_url": search} if search else {})}
                        results[c["name"]] = book.set(c["name"], {**route, **extra}, method=method, job_count=count)
                        progress(f"{c['name']}: {route['ats']}, {count} postings")
                        continue
                if url:
                    route = {"ats": "careers_page", "careers_url": url, **({"search_url": search} if search else {})}
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


def _search_template(template: str, careers_url: str) -> str:
    """A careers-site search URL with {q}, kept only when it is on the company's own site."""
    t = template.strip()
    if "{q}" not in t or not is_company_page(t) or not careers_url:
        return ""
    return t if rendering.site_of(t) == rendering.site_of(careers_url) else ""

"""A company's own careers-site search (careers.example.com/search?q=...), for companies whose ATS
board is empty, unknown or not a public API. The route stores `search_url` with `{q}` (and optionally
`{location}`) where the keywords go.

Reads schema.org JobPosting JSON-LD from each results page; with none, follows posting-looking links
on the same site and reads each posting page (JSON-LD first, then the page's own title and text).
Pages that need JavaScript to list jobs return nothing here and are left to the `careers_page` route."""

import re
from urllib.parse import quote_plus, urljoin, urlsplit

from ..normalize import html_to_text, new_posting
from .careers_page import jsonld_postings, posting_from_jsonld, same_site

NAME = "site_search"
MAX_LINKS = 40
MAX_QUERIES = 4

_HREF = re.compile(r"""href=["']([^"'#]+)["']""", re.I)
_JOB_PATH = re.compile(
    r"/(job|jobs|position|positions|opening|openings|requisition|req|posting|postings|vacancy|vacancies|role|roles)/"
    r"|/jobs?[-_]?\d|[?&](jobid|job_id|req|reqid|id)=\d",
    re.I,
)
_TITLE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_PAGE_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TITLE_SPLIT = re.compile(r"\s[|–—-]\s")


def search_page_url(route: dict, query: str) -> str:
    url = route.get("search_url") or route.get("careers_url", "")
    return url.replace("{q}", quote_plus(query)).replace("{location}", "")


def job_links(html: str, base_url: str) -> list[str]:
    """Links on the page that look like individual postings on the same site, in page order."""
    out: list[str] = []
    for href in _HREF.findall(html or ""):
        u = urljoin(base_url, href.strip())
        if urlsplit(u).scheme not in ("http", "https") or not same_site(base_url, u):
            continue
        if _JOB_PATH.search(u) and u not in out:
            out.append(u)
    return out


def _from_page(html: str, url: str, company: str) -> dict | None:
    """A posting built from the page itself when it carries no JSON-LD."""
    m = _TITLE.search(html) or _PAGE_TITLE.search(html)
    title = html_to_text(m.group(1)).strip() if m else ""
    title = _TITLE_SPLIT.split(title)[0].strip() if title else ""
    text = html_to_text(html)
    if not title or len(text) < 300:
        return None
    return new_posting(source=NAME, ats=NAME, company=company, title=title, external_id=url, url=url,
                       apply_url=url, description_text=text)


def _read_posting(client, url: str, company: str) -> dict | None:
    html = client.get_text(url, robots=True)
    if not html:
        return None
    ld = jsonld_postings(html)
    if ld:
        return posting_from_jsonld(ld[0], company, url)
    return _from_page(html, url, company)


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    if not (route.get("search_url") or route.get("careers_url")):
        return []
    templated = "{q}" in (route.get("search_url") or "")
    out: dict[str, dict] = {}
    links: list[str] = []
    for q in ((queries or [""])[:MAX_QUERIES] if templated else [""]):
        page_url = search_page_url(route, q)
        html = client.get_text(page_url, robots=True)
        if not html:
            continue
        for i, j in enumerate(jsonld_postings(html)):
            p = posting_from_jsonld(j, company, j.get("url") or page_url, external_id=j.get("url") or f"{page_url}#{i}")
            out.setdefault(p["id"], p)
        for u in job_links(html, page_url):
            if u not in links:
                links.append(u)
    for u in links[:MAX_LINKS]:
        if len(out) >= MAX_LINKS:
            break
        p = _read_posting(client, u, company)
        if p:
            out.setdefault(p["id"], p)
    return list(out.values())


def hydrate(client, route: dict, posting: dict) -> dict:
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    from . import careers_page

    return careers_page.verify(client, route, posting)

"""Import one posting from a URL: a career-page or ATS link (never Indeed or Glassdoor, which
are not fetched). Used by "Import from URL" so a posting never has to be pasted by hand."""

import re
from urllib.parse import urlsplit

from . import discovery
from .connectors import careers_page, connector_for
from .normalize import norm_company

NOT_FETCHED = ("indeed.", "glassdoor.", "ziprecruiter.", "linkedin.")


class ImportFailed(ValueError):
    pass


def _pretty(token: str) -> str:
    return re.sub(r"[-_]+", " ", token).strip().title()


def _company_from(route: dict, url: str) -> str:
    token = route.get("token") or route.get("tenant") or urlsplit(url).netloc.split(".")[0]
    return _pretty(token)


def import_url(client, url: str) -> dict:
    url = url.strip()
    host = urlsplit(url).netloc.lower()
    if not host or not url.lower().startswith(("http://", "https://")):
        raise ImportFailed("That does not look like a web address. Paste a full link that starts with https://.")
    if any(h in host for h in NOT_FETCHED):
        raise ImportFailed(
            "Resume Taylor does not read job-board pages. Open the posting, copy its text, and paste it on the New project page, "
            "or look for the same role on the company's own careers page."
        )
    route = discovery.fingerprint(url)
    if route and route["ats"] != "careers_page":
        conn = connector_for(route)
        company = _company_from(route, url)
        jobs = conn.list_jobs(client, route, company, [])
        key = norm_company(url)
        for p in jobs:
            ext = str(p.get("external_id", ""))
            if ext and (ext in url or url.rstrip("/") == p["url"].rstrip("/") or norm_company(p["url"]) == key):
                conn.hydrate(client, route, p)
                p["route"] = route
                p["origin"] = "imported"
                return p
        raise ImportFailed("That company's job board is reachable, but this posting was not on it. It may be closed.")
    html = client.get_text(url, robots=True)
    if not html:
        raise ImportFailed("Could not open that page (it may block automated reads). Paste the posting text instead.")
    found = careers_page.jsonld_postings(html)
    if not found:
        raise ImportFailed("Could not find a structured job posting on that page. Paste the posting text instead.")
    p = careers_page.posting_from_jsonld(found[0], "", url)
    if not p["company"]:
        p["company"] = _pretty(urlsplit(url).netloc.split(".")[-2] if "." in urlsplit(url).netloc else host)
    p["route"] = {"ats": "careers_page", "careers_url": url}
    p["origin"] = "imported"
    return p

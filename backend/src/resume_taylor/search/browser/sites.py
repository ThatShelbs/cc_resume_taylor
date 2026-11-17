"""Per-site URLs and page parsing for the signed-in job boards. Pure functions over page HTML or
text, so they are testable with saved fixtures.

Deterministic parsers come first. If a site changes its markup and one finds nothing, the driver
falls back to `claude_extract`, which asks Claude to read the page text and keeps only results whose
title and company appear verbatim in that text (nothing is invented)."""

import html as htmllib
import re
from urllib.parse import quote_plus

from ..claude import ask
from ..normalize import html_to_text, new_posting, with_pay

LOGIN = {
    "linkedin": "https://www.linkedin.com/login",
    "indeed": "https://secure.indeed.com/auth",
    "google": "https://accounts.google.com/",
}
# A signed-in page for each site: where the login window waits to see you are in.
HOME = {
    "linkedin": "https://www.linkedin.com/feed/",
    "indeed": "https://www.indeed.com/",
    "google": "https://www.google.com/",
}
SIGNED_IN_URL = {"linkedin": "linkedin.com/feed", "indeed": "indeed.com/", "google": "google.com/"}


def search_url(site: str, query: str, location: str, recency_days: int) -> str:
    q, loc = quote_plus(query), quote_plus(location)
    if site == "linkedin":
        return (f"https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}"
                f"&f_TPR=r{recency_days * 86400}&f_E=5%2C6&sortBy=DD")
    if site == "indeed":
        return f"https://www.indeed.com/jobs?q={q}&l={loc}&fromage={recency_days}&sort=date"
    return f"https://www.google.com/search?q={quote_plus(f'{query} jobs {location}')}&ibp=htl;jobs"


def _clean(raw: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", raw or "")).strip()


def _squash(raw: str) -> str:
    return re.sub(r"\s+", " ", _clean(raw))


def parse_linkedin(markup: str) -> list[dict]:
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="[^"]*?/jobs/view/(?:[^"/?]*?-)?(\d{6,})[^"]*"[^>]*>(.*?)</a>', markup or "", re.S):
        jid, title = m.group(1), _squash(m.group(2))
        if jid in seen or not title:
            continue
        tail = markup[m.end(): m.end() + 1500]
        company = _squash((re.search(r'(?:subtitle|primary-description|company-name)[^>]*>(.*?)</', tail, re.S) or [None, ""])[1])
        loc = _squash((re.search(r'(?:metadata-item|location)[^>]*>(.*?)</', tail, re.S) or [None, ""])[1])
        url = f"https://www.linkedin.com/jobs/view/{jid}"
        seen.add(jid)
        out.append(new_posting(source="linkedin", company=company, title=title, external_id=jid, locations=[loc] if loc else [],
                               url=url, apply_url=url, aggregator_only=True))
    return [p for p in out if p["company"]]


def parse_indeed(markup: str) -> list[dict]:
    out, seen = [], set()
    for m in re.finditer(r'data-jk="([0-9a-f]{8,})"', markup or ""):
        jk = m.group(1)
        if jk in seen:
            continue
        block = markup[m.start(): m.start() + 3500]
        title = _squash((re.search(r'jobTitle[^>]*>(.*?)</h2>', block, re.S) or [None, ""])[1])
        company = _squash((re.search(r'(?:company-name|companyName)[^>]*>(.*?)</', block, re.S) or [None, ""])[1])
        loc = _squash((re.search(r'(?:text-location|companyLocation)[^>]*>(.*?)</', block, re.S) or [None, ""])[1])
        if not (title and company):
            continue
        seen.add(jk)
        url = f"https://www.indeed.com/viewjob?jk={jk}"
        out.append(new_posting(source="indeed", company=company, title=title, external_id=jk, locations=[loc] if loc else [],
                               url=url, apply_url=url, aggregator_only=True))
    return out


def parse_detail(site: str, markup: str) -> str:
    patterns = {
        "linkedin": r'(?:show-more-less-html__markup|jobs-description__content|jobs-box__html-content)[^>]*>(.*?)</div>',
        "indeed": r'id="jobDescriptionText"[^>]*>(.*?)</div>\s*(?:</div>|<div)',
    }
    m = re.search(patterns.get(site, "$^"), markup or "", re.S)
    return html_to_text(m.group(1)) if m else ""


PARSERS = {"linkedin": parse_linkedin, "indeed": parse_indeed}

EXTRACT_SYSTEM = (
    "You read the visible text of a job-search results page. Return JSON only: "
    '{"jobs":[{"title":"","company":"","location":"","posted_hint":"","url":""}]}. '
    "Copy title and company exactly as written in the text. Use an empty string for anything not shown. "
    "Never invent a job or a link."
)


def claude_extract(site: str, page_text: str, links: list[str], source: str, model=None, effort=None) -> list[dict]:
    """Fallback reader. Every returned job must have its title and company present in the page text."""
    text = (page_text or "")[:14000]
    if not text.strip():
        return []
    reply = ask(EXTRACT_SYSTEM, f"Page text:\n{text}\n\nLinks on the page:\n" + "\n".join(links[:80]),
                model=model, effort=effort, label=f"{site} page read")
    low = text.lower()
    out = []
    for j in (reply or {}).get("jobs", []) if isinstance(reply, dict) else []:
        title, company = str(j.get("title", "")).strip(), str(j.get("company", "")).strip()
        if not title or not company or title.lower() not in low or company.lower() not in low:
            continue
        url = str(j.get("url", "")).strip()
        if url and url not in links:
            url = ""  # only links that were really on the page
        out.append(new_posting(source=source, company=company, title=title, external_id=url or f"{site}:{company}:{title}",
                               locations=[str(j.get("location", ""))], url=url, apply_url=url, aggregator_only=True))
    return out


def finish_detail(posting: dict, text: str) -> dict:
    if text:
        posting["description_text"] = text
        with_pay(posting, text)
    return posting

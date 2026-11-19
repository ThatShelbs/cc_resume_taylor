"""Opt-in structured job-board source: LinkedIn's public guest endpoints (strictly capped and
throttled; they are against LinkedIn's terms and rate-limit silently, so they are off unless the
user turns them on). It returns *hits*: aggregator postings that `crosswalk` tries to trace back
to the company's own careers page."""

import html as htmllib
import re

from ..normalize import html_to_text, new_posting, with_pay

LINKEDIN_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_VIEW = "https://www.linkedin.com/jobs/view/{id}"
LINKEDIN_MAX_PAGES = 4

_CARD = re.compile(r"<li>(.*?)</li>", re.S)


def _first(pattern: str, text: str) -> str:
    m = re.search(pattern, text, re.S)
    return htmllib.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip() if m else ""


def parse_linkedin_cards(markup: str) -> list[dict]:
    out = []
    for card in _CARD.findall(markup or ""):
        urn = re.search(r"jobPosting:(\d+)", card) or re.search(r"/jobs/view/[^\"?]*?-(\d+)\?", card)
        title = _first(r'base-search-card__title[^>]*>(.*?)</', card)
        if not urn or not title:
            continue
        dt = re.search(r'<time[^>]*datetime="([^"]+)"', card)
        out.append(new_posting(
            source="linkedin", ats="", company=_first(r'base-search-card__subtitle[^>]*>(.*?)</(?:h4|a)>', card),
            title=title, external_id=urn.group(1), locations=[_first(r'job-search-card__location[^>]*>(.*?)</', card)],
            posted_at=dt.group(1) if dt else None, posted_at_source="ats" if dt else "",
            url=LINKEDIN_VIEW.format(id=urn.group(1)), apply_url=LINKEDIN_VIEW.format(id=urn.group(1)),
            aggregator_only=True,
        ))
    return out


def linkedin_search(client, keywords: str, location: str, recency_days: int, senior: bool = True) -> list[dict]:
    """A few pages of one search. Stops at the first empty page (LinkedIn's silent rate limit)."""
    out = []
    for page in range(LINKEDIN_MAX_PAGES):
        params = {"keywords": keywords, "location": location, "f_TPR": f"r{recency_days * 86400}", "start": page * 25}
        if senior:
            params["f_E"] = "5,6"
        markup = client.get_text(LINKEDIN_SEARCH, params=params, cache=True)
        cards = parse_linkedin_cards(markup or "")
        if not cards:
            break
        out.extend(cards)
    return out


def linkedin_detail(client, posting: dict) -> dict:
    markup = client.get_text(posting["url"], robots=False)
    if not markup:
        return posting
    body = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', markup, re.S)
    if body:
        posting["description_text"] = html_to_text(body.group(1))
        with_pay(posting, posting["description_text"])
    return posting


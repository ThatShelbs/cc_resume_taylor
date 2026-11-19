"""Robert Half, the staffing agency: a free, public source of contract, contract-to-hire and permanent
roles, many listed nowhere else. Its search and posting pages are server-rendered and allowed by
robots.txt, so no sign-in and no browser are needed.

Postings are Robert Half's own requisitions. The client company is usually not named, so they are
marked with `agency` and never traced to a careers page. Search URLs have the form
/us/en/jobs/<city-st | all>/<keywords-slug>?postedwithin=<0|1|3|7|30>."""

import re

from ..normalize import html_to_text, new_posting, with_pay

NAME = "roberthalf"
AGENCY = "Robert Half"
COMPANY = "Robert Half (client not named)"
BASE = "https://www.roberthalf.com/us/en"
POSTED_WITHIN = (1, 3, 7, 30)  # the site's "date posted" choices; 0 means any time
MAX_QUERIES = 10

_CARD = re.compile(r"<rhcl-job-card\b[^>]*>(.*?)</rhcl-job-card>", re.S)
_HEADLINE = re.compile(r'<a[^>]+href="([^"]+/job/[^"]+)"[^>]*slot="headline"[^>]*>(.*?)</a>', re.S)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def place_slug(location: str) -> str:
    """'Denver, CO' -> 'denver-co'. Remote or unparseable places search everywhere ('all')."""
    loc = (location or "").strip()
    m = re.match(r"^([A-Za-z .'-]+),\s*([A-Za-z]{2})\b", loc)
    if not loc or "remote" in loc.lower() or not m:
        return "all"
    return _slug(f"{m.group(1)} {m.group(2)}")


def search_url(query: str, location: str, recency_days: int) -> str:
    within = next((d for d in POSTED_WITHIN if d >= recency_days), 0)
    return f"{BASE}/jobs/{place_slug(location)}/{_slug(query) or 'all'}?postedwithin={within}"


def _sub(slot: str, block: str) -> str:
    m = re.search(rf'data-subslot="{slot}"[^>]*>(.*?)</(?:li|span)>', block, re.S)
    return html_to_text(m.group(1)) if m else ""


def parse_cards(markup: str) -> list[dict]:
    out, seen = [], set()
    for block in _CARD.findall(markup or ""):
        head = _HEADLINE.search(block)
        if not head:
            continue
        url, title = head.group(1), html_to_text(head.group(2))
        job_id = url.rstrip("/").rsplit("/", 1)[-1]
        if not title or job_id in seen:
            continue
        seen.add(job_id)
        worksite = _sub("worksite", block).lower()
        lo, hi, period = _sub("salary-min", block), _sub("salary-max", block), _sub("salary-period", block)
        pay_text = f"${lo} - ${hi} per {period.lower().replace('hourly', 'hour').replace('annual', 'year')}" if lo and hi else ""
        kind = _sub("type", block)
        loc = _sub("location", block)
        p = new_posting(
            source=NAME, ats=NAME, company=COMPANY, title=title, external_id=job_id, req_id=job_id,
            locations=[loc] + (["Remote"] if worksite == "remote" else []),
            work_mode=worksite if worksite in ("remote", "hybrid", "onsite") else "unknown",
            posted_at=_sub("date", block) or None, posted_at_source="ats" if _sub("date", block) else "",
            url=url, apply_url=url, description_text=_sub("copy", block),
        )
        p["agency"], p["employment_type"], p["needs_detail"] = AGENCY, kind, True
        p["route"] = {"ats": NAME}
        out.append(with_pay(p, pay_text or p["description_text"]))
    return out


def search(client, query: str, location: str, recency_days: int) -> list[dict]:
    return parse_cards(client.get_text(search_url(query, location, recency_days), robots=True) or "")


def parse_detail(markup: str) -> str:
    parts = []
    for slot in ("description", "requirements"):
        m = re.search(rf'data-testid="job-details-{slot}"[^>]*>(.*?)</div>', markup or "", re.S)
        if m:
            parts.append(html_to_text(m.group(1)))
    return "\n\nRequirements:\n".join(p for p in parts if p)


# -- connector interface (hydrate and verify for shortlisted postings) -------------------------

def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    out: dict[str, dict] = {}
    for q in queries[:MAX_QUERIES]:
        for p in search(client, q, route.get("location", ""), int(route.get("recency_days", 14))):
            out.setdefault(p["id"], p)
    return list(out.values())


def hydrate(client, route: dict, posting: dict) -> dict:
    text = parse_detail(client.get_text(posting["url"], robots=True) or "")
    if text:
        posting["description_text"] = text
        with_pay(posting, text)
    posting["needs_detail"] = False
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    html = client.get_text(posting["url"], cache=False)
    if html is None:
        status = client.status(posting["url"])
        return False if status in (404, 410) else None
    if posting.get("external_id") and posting["external_id"] not in html:
        return False  # the posting page now redirects to a search page
    return not re.search(r"no longer (available|accepting)|position has been filled|job (is )?closed", html, re.I)

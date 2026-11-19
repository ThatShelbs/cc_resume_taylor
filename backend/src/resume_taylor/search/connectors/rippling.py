"""Rippling ATS: ats.rippling.com/api/v2/board/{token}/jobs (paged list). The posting page's Next.js
data holds the description, pay range and posting date, read in `hydrate`."""

import json
import re

from ..normalize import html_to_text, new_posting, with_pay

NAME = "rippling"
API = "https://ats.rippling.com/api/v2/board/{token}/jobs"
MAX_PAGES = 5
_NEXT = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    out = []
    for page in range(MAX_PAGES):
        data = client.get_json(API.format(token=route["token"]), params={"page": page, "pageSize": 100})
        items = (data or {}).get("items", []) if isinstance(data, dict) else []
        for j in items:
            locs = [x.get("name", "") for x in j.get("locations") or [] if x.get("name")]
            kinds = {str(x.get("workplaceType", "")).upper() for x in j.get("locations") or []}
            mode = "remote" if "REMOTE" in kinds else "hybrid" if "HYBRID" in kinds else "onsite" if "ON_SITE" in kinds else "unknown"
            p = new_posting(source=NAME, ats=NAME, company=company, title=j.get("name", ""), external_id=str(j.get("id", "")),
                            locations=locs, work_mode=mode, url=j.get("url", ""), apply_url=j.get("url", ""))
            p["needs_detail"] = True
            out.append(p)
        if not items or page + 1 >= int((data or {}).get("totalPages") or 1):
            break
    return out


def parse_job_page(html: str) -> dict:
    m = _NEXT.search(html or "")
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["apiData"]["jobPost"] if m else {}
    except (ValueError, KeyError, TypeError):
        return {}


def hydrate(client, route: dict, posting: dict) -> dict:
    job = parse_job_page(client.get_text(posting["url"]) or "")
    desc = job.get("description") or {}
    parts = desc.values() if isinstance(desc, dict) else [desc]
    text = "\n\n".join(html_to_text(str(x)) for x in parts if x)
    if text:
        posting["description_text"] = text
    if job.get("createdOn"):
        posting["posted_at"], posting["posted_at_source"] = job["createdOn"], "ats"
    for r in job.get("payRangeDetails") or []:
        if r.get("rangeEnd") and str(r.get("frequency", "")).upper() == "YEAR":
            posting.update(pay_min=round(r.get("rangeStart") or r["rangeEnd"]), pay_max=round(r["rangeEnd"]),
                           currency=r.get("currency") or "USD", pay_period="year")
            break
    with_pay(posting, text)
    posting["needs_detail"] = False
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    status = client.status(posting["url"]) if posting.get("url") else None
    if status in (404, 410):
        return False
    return True if status == 200 else None

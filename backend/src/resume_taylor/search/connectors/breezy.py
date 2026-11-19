"""Breezy HR: {token}.breezy.hr/json (public list; the posting page carries the description)."""

import re

from ..normalize import html_to_text, new_posting, with_pay
from .careers_page import jsonld_postings

NAME = "breezy"
API = "https://{token}.breezy.hr/json"


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    data = client.get_json(API.format(token=route["token"]))
    out = []
    for j in data if isinstance(data, list) else []:
        locs = [x.get("name", "") for x in j.get("locations") or [] if x.get("name")] or [(j.get("location") or {}).get("name", "")]
        remote = bool((j.get("location") or {}).get("is_remote"))
        p = new_posting(
            source=NAME, ats=NAME, company=company, title=j.get("name", ""), external_id=str(j.get("id", "")),
            locations=[x for x in locs if x] + (["Remote"] if remote else []), work_mode="remote" if remote else "unknown",
            posted_at=j.get("published_date"), posted_at_source="ats" if j.get("published_date") else "",
            url=j.get("url", ""), apply_url=j.get("url", ""), pay_text=str(j.get("salary") or ""),
        )
        p["needs_detail"] = True
        out.append(with_pay(p, p["pay_text"]))
    return out


def hydrate(client, route: dict, posting: dict) -> dict:
    html = client.get_text(posting["url"]) or ""
    ld = jsonld_postings(html)
    text = html_to_text(ld[0].get("description", "")) if ld else ""
    if not text:
        m = re.search(r'class="description"[^>]*>(.*?)</div>', html, re.S)
        text = html_to_text(m.group(1)) if m else ""
    if text:
        posting["description_text"] = text
        with_pay(posting, text)
    posting["needs_detail"] = False
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(API.format(token=route["token"]))
    if data is None:
        return None
    return any(str(j.get("id")) == posting["external_id"] for j in data)

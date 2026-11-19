"""SmartRecruiters public postings API: api.smartrecruiters.com/v1/companies/{id}/postings"""

from ..normalize import html_to_text, new_posting, with_pay

NAME = "smartrecruiters"
API = "https://api.smartrecruiters.com/v1/companies/{token}/postings"
PAGE = 100
MAX_PAGES = 5


def _loc(l: dict) -> str:
    parts = [l.get("city"), l.get("region") or l.get("country", "").upper()]
    return ", ".join(x for x in parts if x)


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    """The API searches server-side with `q`, so with role keywords only matching postings are listed."""
    out: list[dict] = []
    seen: set[str] = set()
    for q in (queries or [""])[:4]:
        _list_query(client, route, company, q, out, seen)
    return out


def _list_query(client, route: dict, company: str, q: str, out: list[dict], seen: set[str]) -> None:
    for page in range(MAX_PAGES):
        params = {"limit": PAGE, "offset": page * PAGE}
        if q:
            params["q"] = q
        data = client.get_json(API.format(token=route["token"]), params=params)
        items = (data or {}).get("content") or []
        for j in items:
            if str(j.get("id", "")) in seen:
                continue
            seen.add(str(j.get("id", "")))
            loc = j.get("location") or {}
            mode = "remote" if loc.get("remote") else "hybrid" if loc.get("hybrid") else "unknown"
            p = new_posting(
                source=NAME, ats=NAME, company=company, title=j.get("name", ""),
                req_id=str(j.get("refNumber") or ""), external_id=str(j.get("id", "")),
                locations=[_loc(loc)], work_mode=mode, posted_at=j.get("releasedDate"), posted_at_source="ats",
                url=f"https://jobs.smartrecruiters.com/{route['token']}/{j.get('id', '')}",
            )
            p["apply_url"] = p["url"]
            p["needs_detail"] = True
            out.append(p)
        if len(items) < PAGE:
            break


def hydrate(client, route: dict, posting: dict) -> dict:
    if not posting.get("needs_detail"):
        return posting
    data = client.get_json(f"{API.format(token=route['token'])}/{posting['external_id']}", cache=True)
    if not data:
        return posting
    sections = ((data.get("jobAd") or {}).get("sections")) or {}
    text = "\n\n".join(html_to_text((sections.get(k) or {}).get("text", ""))
                       for k in ("jobDescription", "qualifications", "additionalInformation"))
    posting["description_text"] = text.strip()
    posting["url"] = posting["apply_url"] = data.get("postingUrl") or posting["url"]
    posting["needs_detail"] = False
    return with_pay(posting, text)


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(f"{API.format(token=route['token'])}/{posting['external_id']}")
    if data is None:
        status = client.status(posting["url"])
        return False if status == 404 else None
    return str(data.get("active", True)).lower() != "false"

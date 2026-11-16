"""Greenhouse job boards: boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"""

from ..normalize import html_to_text, new_posting, with_pay

NAME = "greenhouse"
API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def _pay_from_ranges(job: dict) -> dict:
    for r in job.get("pay_input_ranges") or []:
        lo, hi = r.get("min_cents"), r.get("max_cents")
        if hi:
            return {
                "pay_min": round((lo or hi) / 100), "pay_max": round(hi / 100),
                "currency": r.get("currency_type") or "USD", "pay_period": "year",
                "pay_text": r.get("title") or "",
            }
    return {}


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    data = client.get_json(API.format(token=route["token"]), params={"content": "true", "pay_transparency": "true"})
    out = []
    for j in (data or {}).get("jobs", []):
        text = html_to_text(j.get("content", ""))
        p = new_posting(
            source=NAME, ats=NAME, company=company, title=j.get("title", ""),
            req_id=str(j.get("requisition_id") or ""), external_id=str(j.get("id", "")),
            locations=[(j.get("location") or {}).get("name", "")],
            posted_at=j.get("first_published") or j.get("updated_at"), posted_at_source="ats",
            url=j.get("absolute_url", ""), apply_url=j.get("absolute_url", ""),
            description_text=text, **_pay_from_ranges(j),
        )
        out.append(with_pay(p, text))
    return out


def hydrate(client, route: dict, posting: dict) -> dict:
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(f"{API.format(token=route['token'])}/{posting['external_id']}")
    if data is None:
        status = client.status(posting["url"]) if posting.get("url") else None
        return False if status == 404 else None
    return True

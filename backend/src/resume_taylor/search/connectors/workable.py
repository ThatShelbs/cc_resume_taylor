"""Workable: apply.workable.com/api/v1/widget/accounts/{slug}?details=true"""

from ..normalize import html_to_text, new_posting, with_pay

NAME = "workable"
API = "https://apply.workable.com/api/v1/widget/accounts/{token}"


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    data = client.get_json(API.format(token=route["token"]), params={"details": "true"})
    out = []
    for j in (data or {}).get("jobs", []):
        loc = ", ".join(x for x in (j.get("city"), j.get("state") or j.get("country")) if x)
        text = html_to_text(j.get("description", ""))
        p = new_posting(
            source=NAME, ats=NAME, company=company, title=j.get("title", ""), external_id=str(j.get("shortcode", "")),
            locations=[loc], work_mode="remote" if j.get("telecommuting") else "unknown",
            posted_at=j.get("published_on") or j.get("created_at"), posted_at_source="ats",
            url=j.get("url") or j.get("shortlink", ""), apply_url=j.get("application_url") or j.get("url", ""),
            description_text=text,
        )
        out.append(with_pay(p, text))
    return out


def hydrate(client, route: dict, posting: dict) -> dict:
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(API.format(token=route["token"]))
    if data is None:
        return None
    return any(str(j.get("shortcode")) == posting["external_id"] for j in data.get("jobs", []))

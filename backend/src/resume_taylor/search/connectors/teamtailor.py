"""Teamtailor: every career site publishes a JSON Feed at /jobs.json whose items carry a schema.org
JobPosting, so the fields come from the employer's own structured data."""

from ..normalize import html_to_text, with_pay
from .careers_page import posting_from_jsonld

NAME = "teamtailor"
FEED = "https://{host}/jobs.json"


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    data = client.get_json(FEED.format(host=route["host"]))
    out = []
    for item in (data or {}).get("items", []) if isinstance(data, dict) else []:
        ld = item.get("_jobposting") or {"title": item.get("title", ""), "description": item.get("content_html", ""),
                                         "datePosted": item.get("date_published")}
        p = posting_from_jsonld(ld, company, item.get("url", ""))
        p.update(source=NAME, ats=NAME, external_id=str(item.get("id", "")))
        if not p["description_text"]:
            p["description_text"] = html_to_text(item.get("content_html", ""))
        out.append(with_pay(p, p["description_text"]))
    return out


def hydrate(client, route: dict, posting: dict) -> dict:
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(FEED.format(host=route["host"]))
    if data is None:
        return None
    return any(str(i.get("id")) == posting["external_id"] for i in data.get("items", []))

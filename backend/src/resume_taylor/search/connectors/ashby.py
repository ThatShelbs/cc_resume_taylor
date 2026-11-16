"""Ashby: api.ashbyhq.com/posting-api/job-board/{name}?includeCompensation=true"""

from ..normalize import html_to_text, new_posting, with_pay

NAME = "ashby"
API = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def _comp(job: dict) -> dict:
    comp = job.get("compensation") or {}
    for tier in comp.get("compensationTiers") or []:
        for c in tier.get("components") or []:
            if str(c.get("compensationType", "")).lower() == "salary" and c.get("maxValue"):
                return {
                    "pay_min": round(c.get("minValue") or c["maxValue"]), "pay_max": round(c["maxValue"]),
                    "currency": c.get("currencyCode") or "USD", "pay_period": "year",
                    "pay_text": comp.get("compensationTierSummary") or "",
                }
    return {}


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    data = client.get_json(API.format(token=route["token"]), params={"includeCompensation": "true"})
    out = []
    for j in (data or {}).get("jobs", []):
        if j.get("isListed") is False:
            continue
        text = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", ""))
        locations = [j.get("location", "")] + [
            (s.get("location") if isinstance(s, dict) else s) for s in j.get("secondaryLocations") or []
        ]
        mode = {"remote": "remote", "hybrid": "hybrid", "onsite": "onsite"}.get(str(j.get("workplaceType", "")).lower(), "unknown")
        if j.get("isRemote") and mode == "unknown":
            mode = "remote"
        p = new_posting(
            source=NAME, ats=NAME, company=company, title=j.get("title", ""), external_id=str(j.get("id", "")),
            locations=[l for l in locations if l], work_mode=mode, posted_at=j.get("publishedAt"),
            posted_at_source="ats", url=j.get("jobUrl", ""), apply_url=j.get("applyUrl") or j.get("jobUrl", ""),
            description_text=text, **_comp(j),
        )
        out.append(with_pay(p, text))
    return out


def hydrate(client, route: dict, posting: dict) -> dict:
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(API.format(token=route["token"]))
    if data is None:
        return None
    return any(str(j.get("id")) == posting["external_id"] for j in data.get("jobs", []))

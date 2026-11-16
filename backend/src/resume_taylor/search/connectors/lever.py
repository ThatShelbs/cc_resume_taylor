"""Lever: api.lever.co/v0/postings/{company}?mode=json"""

from ..normalize import html_to_text, new_posting, with_pay

NAME = "lever"
API = "https://api.lever.co/v0/postings/{token}"


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    data = client.get_json(API.format(token=route["token"]), params={"mode": "json"})
    out = []
    for j in data if isinstance(data, list) else []:
        cats = j.get("categories") or {}
        locations = list(cats.get("allLocations") or ([cats["location"]] if cats.get("location") else []))
        text = j.get("descriptionPlain") or html_to_text(j.get("description", ""))
        for lst in j.get("lists") or []:
            text += f"\n\n{lst.get('text', '')}\n{html_to_text(lst.get('content', ''))}"
        text += "\n\n" + (j.get("additionalPlain") or html_to_text(j.get("additional", "")))
        sal = j.get("salaryRange") or {}
        pay = {}
        if sal.get("max"):
            pay = {
                "pay_min": round(sal.get("min") or sal["max"]), "pay_max": round(sal["max"]),
                "currency": sal.get("currency") or "USD",
                "pay_period": "year" if str(sal.get("interval", "")).lower().startswith("per-year") else "",
            }
        mode = {"remote": "remote", "hybrid": "hybrid", "on-site": "onsite"}.get(str(j.get("workplaceType", "")).lower(), "unknown")
        p = new_posting(
            source=NAME, ats=NAME, company=company, title=j.get("text", ""), external_id=str(j.get("id", "")),
            locations=locations, work_mode=mode, posted_at=j.get("createdAt"), posted_at_source="ats",
            url=j.get("hostedUrl", ""), apply_url=j.get("applyUrl") or j.get("hostedUrl", ""),
            description_text=text.strip(), **pay,
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

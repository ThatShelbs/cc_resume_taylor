"""Recruitee: {token}.recruitee.com/api/offers/ (public JSON, names the company)."""

from ..normalize import html_to_text, new_posting, with_pay

NAME = "recruitee"
API = "https://{token}.recruitee.com/api/offers/"


def _pay(sal: dict) -> dict:
    hi = (sal or {}).get("max")
    if not hi:
        return {}
    period = str(sal.get("period") or "").lower()
    mult = {"hour": 2080, "month": 12, "year": 1}.get(period, 1)
    return {"pay_min": round(float(sal.get("min") or hi) * mult), "pay_max": round(float(hi) * mult),
            "currency": sal.get("currency") or "", "pay_period": "hour" if period == "hour" else "year"}


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    data = client.get_json(API.format(token=route["token"]))
    out = []
    for j in (data or {}).get("offers", []) if isinstance(data, dict) else []:
        text = html_to_text(j.get("description", "")) + "\n\n" + html_to_text(j.get("requirements", ""))
        mode = "remote" if j.get("remote") else "hybrid" if j.get("hybrid") else "onsite" if j.get("on_site") else "unknown"
        loc = ", ".join(x for x in (j.get("city"), j.get("state_code") or j.get("country")) if x) or j.get("location", "")
        p = new_posting(
            source=NAME, ats=NAME, company=company, title=j.get("title", ""), external_id=str(j.get("id", "")),
            locations=[loc] if loc else [], work_mode=mode, posted_at=j.get("published_at") or j.get("created_at"),
            posted_at_source="ats", closes_at=j.get("close_at"), url=j.get("careers_url", ""),
            apply_url=j.get("careers_apply_url") or j.get("careers_url", ""), description_text=text.strip(),
            **_pay(j.get("salary") or {}),
        )
        out.append(with_pay(p, text))
    return out


def hydrate(client, route: dict, posting: dict) -> dict:
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(API.format(token=route["token"]))
    if data is None:
        return None
    return any(str(j.get("id")) == posting["external_id"] for j in data.get("offers", []))

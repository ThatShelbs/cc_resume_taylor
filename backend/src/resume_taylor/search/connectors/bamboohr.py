"""BambooHR: {token}.bamboohr.com/careers/list, with /careers/{id}/detail for the full text."""

from ..normalize import html_to_text, new_posting, with_pay

NAME = "bamboohr"
LIST = "https://{token}.bamboohr.com/careers/list"
DETAIL = "https://{token}.bamboohr.com/careers/{id}/detail"
PAGE = "https://{token}.bamboohr.com/careers/{id}"


def _place(loc: dict) -> str:
    loc = loc or {}
    return ", ".join(x for x in (loc.get("city"), loc.get("state") or loc.get("province") or loc.get("country")) if x)


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    data = client.get_json(LIST.format(token=route["token"]))
    out = []
    for j in (data or {}).get("result", []) if isinstance(data, dict) else []:
        jid = str(j.get("id", ""))
        loc = _place(j.get("location")) or _place(j.get("atsLocation"))
        url = PAGE.format(token=route["token"], id=jid)
        p = new_posting(
            source=NAME, ats=NAME, company=company, title=(j.get("jobOpeningName") or "").strip(), external_id=jid,
            locations=[x for x in (loc, "Remote" if j.get("isRemote") else "") if x],
            work_mode="remote" if j.get("isRemote") else "unknown", url=url, apply_url=url,
        )
        p["needs_detail"] = True
        out.append(p)
    return out


def hydrate(client, route: dict, posting: dict) -> dict:
    data = client.get_json(DETAIL.format(token=route["token"], id=posting["external_id"]))
    job = ((data or {}).get("result") or {}).get("jobOpening") or {}
    if job:
        text = html_to_text(job.get("description", ""))
        posting["description_text"] = text
        if job.get("datePosted"):
            posting["posted_at"], posting["posted_at_source"] = job["datePosted"], "ats"
        with_pay(posting, f"{job.get('compensation') or ''}\n{text}")
    posting["needs_detail"] = False
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(LIST.format(token=route["token"]))
    if data is None:
        return None
    return any(str(j.get("id")) == posting["external_id"] for j in data.get("result", []))

"""Eightfold career sites: https://{host}/api/apply/v2/jobs?domain={domain}"""

from ..normalize import html_to_text, new_posting, with_pay

NAME = "eightfold"
PAGE = 50
MAX_PAGES = 6


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    seen: dict[str, dict] = {}
    for q in (queries or [""])[:6]:
        for page in range(MAX_PAGES):
            data = client.get_json(
                f"https://{route['host']}/api/apply/v2/jobs",
                params={"domain": route["domain"], "start": page * PAGE, "num": PAGE, "query": q},
            )
            items = (data or {}).get("positions") or []
            for j in items:
                pid = str(j.get("id", ""))
                if not pid or pid in seen:
                    continue
                text = html_to_text(j.get("job_description", ""))
                locs = j.get("locations") or [j.get("location", "")]
                url = j.get("canonicalPositionUrl") or f"https://{route['host']}/careers/job/{pid}"
                p = new_posting(
                    source=NAME, ats=NAME, company=company, title=j.get("name", ""), req_id=str(j.get("display_job_id") or ""),
                    external_id=pid, locations=[l for l in locs if l], posted_at=j.get("t_create"),
                    posted_at_source="ats" if j.get("t_create") else "", url=url, apply_url=url, description_text=text,
                )
                seen[pid] = with_pay(p, text)
            if len(items) < PAGE:
                break
    return list(seen.values())


def hydrate(client, route: dict, posting: dict) -> dict:
    return posting


def verify(client, route: dict, posting: dict) -> bool | None:
    status = client.status(posting["url"])
    if status is None:
        return None
    return status != 404

"""Workday career sites: POST https://{host}/wday/cxs/{tenant}/{site}/jobs, then a detail GET.
Common in pharma and large enterprises. The list is light (title, place, 'Posted N Days Ago'),
so descriptions are fetched only for postings that survive the prefilter (`hydrate`)."""

from ..normalize import (
    days_ago_to_iso,
    html_to_text,
    new_posting,
    parse_iso,
    parse_posted_ago,
    with_pay,
)

NAME = "workday"
PAGE = 20
MAX_PAGES = 5


def _base(route: dict) -> str:
    return f"https://{route['host']}/wday/cxs/{route['tenant']}/{route['site']}"


def _public_url(route: dict, path: str) -> str:
    return f"https://{route['host']}/{route['site']}{path}"


def list_jobs(client, route: dict, company: str, queries: list[str]) -> list[dict]:
    seen: dict[str, dict] = {}
    for q in (queries or [""])[:8]:
        for page in range(MAX_PAGES):
            data = client.post_json(
                f"{_base(route)}/jobs",
                {"appliedFacets": {}, "limit": PAGE, "offset": page * PAGE, "searchText": q},
            )
            items = (data or {}).get("jobPostings") or []
            for j in items:
                path = j.get("externalPath", "")
                if not path or path in seen:
                    continue
                days = parse_posted_ago(j.get("postedOn", ""))
                bullets = j.get("bulletFields") or []
                seen[path] = new_posting(
                    source=NAME, ats=NAME, company=company, title=j.get("title", ""),
                    req_id=str(bullets[0]) if bullets else "", external_id=path,
                    locations=[j.get("locationsText", "")],
                    posted_at=days_ago_to_iso(days) if days is not None else None,
                    posted_at_source="parsed" if days is not None else "",
                    url=_public_url(route, path), apply_url=_public_url(route, path),
                )
                seen[path]["needs_detail"] = True
            if len(items) < PAGE:
                break
    return list(seen.values())


def hydrate(client, route: dict, posting: dict) -> dict:
    if not posting.get("needs_detail"):
        return posting
    data = client.get_json(f"{_base(route)}{posting['external_id']}", cache=True)
    info = (data or {}).get("jobPostingInfo")
    if not info:
        return posting
    text = html_to_text(info.get("jobDescription", ""))
    locs = [info.get("location", ""), *(info.get("additionalLocations") or [])]
    posting["locations"] = [l for l in locs if l] or posting["locations"]
    posting["description_text"] = text
    if info.get("jobReqId"):
        posting["req_id"] = info["jobReqId"]
    if info.get("startDate") and parse_iso(info["startDate"]):
        posting["posted_at"], posting["posted_at_source"] = info["startDate"], "ats"
    remote = str(info.get("remoteType", "")).lower()
    if "remote" in remote:
        posting["work_mode"] = "remote"
    elif "hybrid" in remote or "flexible" in remote:
        posting["work_mode"] = "hybrid"
    posting["needs_detail"] = False
    return with_pay(posting, text)


def verify(client, route: dict, posting: dict) -> bool | None:
    data = client.get_json(f"{_base(route)}{posting['external_id']}")
    if data is None:
        status = client.status(posting["url"])
        return False if status == 404 else None
    return bool((data.get("jobPostingInfo") or {}).get("canApply", True))

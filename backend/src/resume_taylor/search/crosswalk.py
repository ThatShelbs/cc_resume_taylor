"""Trace job-board leads back to the company's own careers page.

For each lead we find the company's route, pull its postings (once per company) and look for
the same role. A match makes the careers-page posting the record and notes where else it is
listed (more places usually means a bigger applicant pool). No match leaves an
"aggregator only" lead, shown with lower confidence."""

import re

from .discovery import fingerprint
from .normalize import norm_company, norm_title


def _tokens(title: str) -> set:
    return set(norm_title(title).split())


def title_match(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    jac = len(ta & tb) / len(ta | tb)
    return jac >= 0.8


def _location_compatible(hit: dict, cand: dict) -> bool:
    hit_text = " ".join(hit.get("locations", [])).lower()
    cand_locs = [l.lower() for l in cand.get("locations", [])]
    if not hit_text.strip() or not cand_locs:
        return True
    if "remote" in hit_text and cand.get("work_mode") == "remote":
        return True
    city = re.split(r"[,(]", hit_text)[0].strip()
    return any(city and city in l for l in cand_locs)


def find_match(hit: dict, pool: list[dict]) -> dict | None:
    req = re.search(r"\b(?:req|jr|r)[-_ ]?\d{3,}\b", f"{hit['url']} {hit.get('description_text', '')}", re.I)
    for cand in pool:
        if req and cand.get("req_id") and req.group(0).lower() in cand["req_id"].lower():
            return cand
    for cand in pool:
        if title_match(hit["title"], cand["title"]) and _location_compatible(hit, cand):
            return cand
    return None


def route_from_links(hit: dict) -> dict | None:
    """A Google Jobs hit often carries the employer's own apply link; its host can name the ATS."""
    for link in hit.get("apply_links", []) or [hit.get("apply_url", "")]:
        route = fingerprint(link)
        if route:
            return route
    return None


def crosswalk(hits: list[dict], pools: dict[str, list[dict]]) -> tuple[list[dict], list[dict]]:
    """pools: {norm_company: [careers-page postings]}. Returns (matched ATS postings with
    also_listed_on filled in, unmatched aggregator-only leads)."""
    matched: dict[str, dict] = {}
    leads: list[dict] = []
    for hit in hits:
        pool = pools.get(norm_company(hit["company"]))
        found = find_match(hit, pool) if pool else None
        if found is None:
            leads.append(hit)
            continue
        rec = matched.setdefault(found["id"], found)
        src = hit["source"]
        if src and src != "web" and src not in rec["also_listed_on"]:
            rec["also_listed_on"].append(src)
    return list(matched.values()), leads

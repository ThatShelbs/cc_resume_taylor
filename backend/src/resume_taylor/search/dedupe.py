"""Merge duplicate postings: the same role listed twice, in several cities, or reposted."""

import re

from .normalize import norm_company, norm_title

JACCARD_MERGE = 0.9


def _shingles(text: str, n: int = 5) -> set:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _merge(into: dict, other: dict) -> None:
    for loc in other.get("locations", []):
        if loc not in into["locations"]:
            into["locations"].append(loc)
    for src in other.get("also_listed_on", []):
        if src not in into["also_listed_on"]:
            into["also_listed_on"].append(src)
    for field in ("posted_at", "pay_max", "closes_at", "description_text"):
        if not into.get(field) and other.get(field):
            into[field] = other[field]
    if not into.get("pay_min") and other.get("pay_min"):
        into["pay_min"], into["currency"], into["pay_period"] = other["pay_min"], other["currency"], other["pay_period"]


def _rank(p: dict) -> tuple:
    """Prefer a careers-page record over an aggregator-only one, then the richer one."""
    return (0 if p.get("aggregator_only") else 1, len(p.get("description_text", "")))


def _similar_titles(a: str, b: str) -> bool:
    ta, tb = set(norm_title(a).split()), set(norm_title(b).split())
    return bool(ta and tb) and len(ta & tb) / len(ta | tb) >= 0.6


def dedupe(postings: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for p in sorted(postings, key=_rank, reverse=True):
        key = "|".join([norm_company(p["company"]), norm_title(p["title"]), p.get("req_id") or ""])
        if key in groups:
            _merge(groups[key], p)
            continue
        groups[key] = {**p, "locations": list(p["locations"]), "also_listed_on": list(p["also_listed_on"])}
    kept = list(groups.values())
    # Fallback: near-identical descriptions at the same company (a repost under a new title or id).
    result: list[dict] = []
    sigs: list[tuple[str, set]] = []
    for p in kept:
        sig = _shingles(p.get("description_text", ""))
        company = norm_company(p["company"])
        match = None
        if sig:
            for i, (c, s) in enumerate(sigs):
                if c == company and jaccard(sig, s) >= JACCARD_MERGE and _similar_titles(p["title"], result[i]["title"]):
                    match = result[i]
                    break
        if match is not None:
            _merge(match, p)
        else:
            result.append(p)
            sigs.append((company, sig))
    return result

"""How old a posting is, and what that means. A role open 14+ days may already be in panel
interviews, so recent postings rank higher; older ones stay visible but are flagged."""

from datetime import datetime, timezone

from .normalize import parse_iso

FRESH_MAX = 6
ACTIVE_MAX = 13
AGING_MAX = 20  # 21+ is "late"

BAND_NOTES = {
    "fresh": "Posted in the last week.",
    "active": "Open one to two weeks.",
    "aging": "Open 14+ days; interviews may already be under way.",
    "late": "Open 21+ days; panels may be well along. Still worth a quick, strong application.",
    "unknown": "Posting date not stated.",
}


def age_days(posting: dict, now: datetime | None = None) -> int | None:
    now = now or datetime.now(timezone.utc)
    dt = parse_iso(posting.get("posted_at")) or parse_iso(posting.get("first_seen"))
    if not dt:
        return None
    return max(0, (now - dt).days)


def band(age: int | None) -> str:
    if age is None:
        return "unknown"
    if age <= FRESH_MAX:
        return "fresh"
    if age <= ACTIVE_MAX:
        return "active"
    if age <= AGING_MAX:
        return "aging"
    return "late"


def points(age: int | None, max_points: int = 15) -> int:
    """Freshness share of the score. Decays through the bands; unknown is mid-low."""
    if age is None:
        return round(max_points * 0.33)
    if age <= 2:
        return max_points
    if age <= FRESH_MAX:
        return round(max_points * 0.87)
    if age <= ACTIVE_MAX:
        return round(max_points * 0.6)
    if age <= AGING_MAX:
        return round(max_points * 0.27)
    return round(max_points * 0.07)


def annotate(posting: dict, now: datetime | None = None) -> dict:
    age = age_days(posting, now)
    posting["age_days"] = age
    posting["freshness"] = band(age)
    posting["freshness_note"] = BAND_NOTES[posting["freshness"]]
    posting["date_estimated"] = posting.get("posted_at_source") in ("first_seen", "")
    return posting

"""Hard filters: level, recency, exclusions, pay floor and location. Unknown values pass but
are flagged, so a posting is only rejected on evidence. Run once on the raw pool (cheap
prefilter) and again after Claude has filled in work mode, pay and remote states."""

from dataclasses import dataclass, field
from datetime import datetime

from . import freshness, geo
from .normalize import level_rank, title_level
from .prefs import Preferences


@dataclass
class Verdict:
    ok: bool
    reason: str = ""  # level | stale | excluded | pay_below_floor | location | closed
    evidence: str = ""
    flags: list[str] = field(default_factory=list)  # things that passed on missing data


def check_level(p: dict, prefs: Preferences) -> Verdict | None:
    level = title_level(p["title"], prefs.equivalent_titles)
    p["level"] = level
    if level_rank(level) < level_rank(prefs.min_level):
        return Verdict(False, "level", f"'{p['title']}' reads as {level.replace('_', ' ')}; minimum is {prefs.min_level.replace('_', ' ')}.")
    return None


def check_exclusions(p: dict, prefs: Preferences) -> Verdict | None:
    hay = f"{p['title']}\n{p.get('description_text', '')}".lower()
    for phrase in prefs.exclusions:
        ph = phrase.strip().lower()
        if ph and ph in hay:
            return Verdict(False, "excluded", f"Mentions your exclusion '{phrase.strip()}'.")
    return None


def check_pay(p: dict, prefs: Preferences) -> tuple[Verdict | None, list[str]]:
    if not prefs.base_floor:
        return None, []
    hi = p.get("pay_max")
    if hi and (p.get("currency") or "USD") == "USD":
        if hi < prefs.base_floor:
            return Verdict(False, "pay_below_floor", f"Stated top of range ${hi:,} is below your ${prefs.base_floor:,} floor."), []
        return None, []
    return None, ["pay not stated"]


def _anchors(prefs: Preferences) -> list[tuple[float, float]]:
    out = []
    for place in [prefs.home_location, *prefs.anchor_cities]:
        c = geo.resolve(place) if place else None
        if c:
            out.append(c)
    return out


DEFAULT_NO_RELOCATE_RADIUS = 60


def check_location_no_relocation(p: dict, prefs: Preferences) -> tuple[Verdict | None, list[str]]:
    """Non-relocator: reject anything outside the home area (anchors within the radius, allowed
    cities) or outside the country, unless it is remote. Only truly unplaceable locations pass."""
    locs = p.get("parsed_locations") or geo.parse_locations(p.get("locations", []))
    p["parsed_locations"] = locs
    mode = p.get("work_mode", "unknown")
    country = prefs.remote_country
    if mode == "remote":
        states = {s.upper() for s in (p.get("remote_states") or [])} | {l["state"] for l in locs if l["state"]}
        foreign = [l for l in locs if l["country"] == "other"]
        if foreign and not any(l["country"] == "US" for l in locs):
            return Verdict(False, "location", f"Remote, but for {foreign[0]['raw']}; you only want remote roles open to {country}."), []
        if prefs.remote_states and states and not (states & set(prefs.remote_states)):
            return Verdict(False, "location", f"Remote, but only for {', '.join(sorted(states))}; you can work from {', '.join(prefs.remote_states)}."), []
        return None, [] if (states or any(l["country"] == "US" for l in locs)) else ["remote eligibility not stated"]
    radius = prefs.radius_miles or DEFAULT_NO_RELOCATE_RADIUS
    anchors = _anchors(prefs)
    area = [geo.parse_location(x) for x in [prefs.home_location, *prefs.anchor_cities, *prefs.allowed_cities] if x]
    area_states = {a["state"] for a in area if a["state"]}
    allowed = {(c.split(",")[0].strip().lower(), geo.to_state(c.split(",")[1]) if "," in c else None) for c in prefs.allowed_cities}
    if not anchors and not allowed:
        return None, ["no home area set"]
    if not locs:
        return None, ["location not stated"]
    unknown = False
    for l in locs:
        if l["country"] == "other":
            continue
        if l["remote"] and mode == "unknown":
            return None, []
        if l["city"] and any(l["city"].lower() == c and (not st or not l["state"] or st == l["state"]) for c, st in allowed):
            return None, []
        if l["lat"] is not None:
            if anchors and min(geo.miles((l["lat"], l["lon"]), a) for a in anchors) <= radius:
                return None, []
        elif l["state"]:
            if l["state"] in area_states:
                unknown = True
        else:
            unknown = True
    if unknown:
        return None, ["location could not be placed on a map"]
    where = "; ".join(l["raw"] for l in locs[:3])
    return Verdict(False, "location", f"{where} is outside your {radius}-mile area and you are not relocating."), []


def check_location(p: dict, prefs: Preferences) -> tuple[Verdict | None, list[str]]:
    if prefs.relocation == "no":
        return check_location_no_relocation(p, prefs)
    has_rule = bool(prefs.home_location or prefs.allowed_cities or prefs.remote_states)
    if not has_rule:
        return None, []
    locs = p.get("parsed_locations") or geo.parse_locations(p.get("locations", []))
    p["parsed_locations"] = locs
    mode = p.get("work_mode", "unknown")
    states = {s.upper() for s in (p.get("remote_states") or [])} | {l["state"] for l in locs if l["state"]}
    if mode == "remote":
        if prefs.remote_states and states and not (states & set(prefs.remote_states)):
            return Verdict(False, "location", f"Remote, but only for {', '.join(sorted(states))}; you can work from {', '.join(prefs.remote_states)}."), []
        return None, [] if states else ["remote eligibility not stated"]
    if not locs:
        return None, ["location not stated"]
    allowed = {c.split(",")[0].strip().lower() for c in prefs.allowed_cities}
    anchors = _anchors(prefs) if prefs.radius_miles else []
    unknown = False
    for l in locs:
        if l["remote"] and mode == "unknown":
            return None, []
        if l["city"] and l["city"].lower() in allowed:
            return None, []
        if l["lat"] is not None and anchors:
            if min(geo.miles((l["lat"], l["lon"]), a) for a in anchors) <= prefs.radius_miles:
                return None, []
        elif l["lat"] is None:
            unknown = True
    if unknown and anchors:
        return None, ["location could not be placed on a map"]
    if not anchors and not allowed:
        return None, []
    where = "; ".join(l["raw"] for l in locs[:3])
    return Verdict(False, "location", f"On-site or hybrid at {where}, outside your {prefs.radius_miles}-mile radius and allowed cities."), []


def apply_filters(p: dict, prefs: Preferences, now: datetime | None = None, window_days: int | None = None) -> Verdict:
    """Returns the first failing Verdict, else an ok Verdict carrying any flags."""
    for check in (check_level, check_exclusions):
        v = check(p, prefs)
        if v:
            return v
    age = freshness.age_days(p, now)
    window = window_days or prefs.recency_days
    if age is not None and age > window:
        return Verdict(False, "stale", f"Posted {age} days ago; window is {window} days.")
    if p.get("closes_at"):
        from .normalize import parse_iso
        closes = parse_iso(p["closes_at"])
        if closes and closes < (now or datetime.now(closes.tzinfo)):
            return Verdict(False, "closed", f"Closing date {p['closes_at'][:10]} has passed.")
    flags: list[str] = []
    v, f = check_pay(p, prefs)
    if v:
        return v
    flags += f
    v, f = check_location(p, prefs)
    if v:
        return v
    flags += f
    if age is None:
        flags.append("posting date not stated")
    return Verdict(True, flags=flags)

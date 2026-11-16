"""Search preferences: one model shared by the engine and the API."""

import json
from pathlib import Path

from pydantic import BaseModel, Field

LEVELS = ["ic", "manager", "senior_manager", "director", "senior_director", "vp", "executive"]
DEPTHS = ("quick", "standard", "deep")
COUNTS = (3, 5, 10, 20)
SOURCES = ("targets", "ideated", "boards", "linkedin", "google")


class Preferences(BaseModel):
    titles: list[str] = Field(default_factory=list)  # title variants to search
    equivalent_titles: list[str] = Field(default_factory=list)  # treated as at least director
    min_level: str = "director"
    skill_terms: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    admired_companies: list[str] = Field(default_factory=list)
    about_me: str = ""
    home_location: str = ""  # "Crystal Lake, IL"
    radius_miles: int = 0  # 0 = no distance rule
    anchor_cities: list[str] = Field(default_factory=list)
    allowed_cities: list[str] = Field(default_factory=list)
    remote_states: list[str] = Field(default_factory=list)  # remote roles must allow one of these
    base_floor: int = 0  # minimum base salary, 0 = off
    exclusions: list[str] = Field(default_factory=list)  # phrases that reject a posting
    recency_days: int = 14
    count: int = 5
    depth: str = "standard"
    sources: list[str] = Field(default_factory=lambda: ["targets", "ideated", "boards"])
    linkedin_direct: bool = False  # opt-in: LinkedIn guest endpoints

    def normalized(self) -> "Preferences":
        data = self.model_dump()
        data["min_level"] = data["min_level"] if data["min_level"] in LEVELS else "director"
        data["depth"] = data["depth"] if data["depth"] in DEPTHS else "standard"
        data["count"] = data["count"] if data["count"] in COUNTS else 5
        data["recency_days"] = max(1, min(90, int(data["recency_days"])))
        data["radius_miles"] = max(0, int(data["radius_miles"]))
        data["base_floor"] = max(0, int(data["base_floor"]))
        data["sources"] = [s for s in data["sources"] if s in SOURCES]
        data["remote_states"] = [s.strip().upper() for s in data["remote_states"] if s.strip()]
        return Preferences(**data)


def load_prefs(path) -> Preferences:
    p = Path(path) if path else None
    if p and p.exists():
        try:
            return Preferences(**json.loads(p.read_text(encoding="utf-8"))).normalized()
        except Exception:
            pass
    return Preferences().normalized()

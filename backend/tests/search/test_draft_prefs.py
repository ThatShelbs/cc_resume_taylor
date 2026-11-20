"""Starting search settings: drafted from the resume, never beyond what the documents support."""

from resume_taylor.search import draft_prefs
from resume_taylor.search.candidate import Candidate
from resume_taylor.search.prefs import Preferences, resolve_min_level


def candidate(**kw) -> Candidate:
    base = dict(tier="partial", titles=["Director, Medical Affairs", "Senior Manager, Medical Affairs"], skills=["Veeva CRM", "KOL engagement"],
                source_text="Led medical affairs. Veeva CRM and KOL engagement. Pharma launch planning.")
    base.update(kw)
    return Candidate(**base)


def test_unsupported_skills_are_dropped_and_levels_validated():
    reply = {"titles": ["Director, Medical Affairs", "Head of Medical Affairs"], "title_keywords": ["medical affairs"],
             "skill_terms": ["Veeva CRM", "Kubernetes"], "industries": ["Pharma"], "min_level": "wizard"}
    out = draft_prefs.sanitize(reply, candidate())
    assert out["skill_terms"] == ["Veeva CRM"]  # Kubernetes is nowhere in the resume
    assert out["min_level"] == "" and out["title_keywords"] == ["medical affairs"]


def test_draft_falls_back_to_the_parsed_resume_when_claude_is_unavailable(monkeypatch):
    monkeypatch.setattr(draft_prefs.claude, "ask", lambda *a, **k: None)
    out = draft_prefs.draft(candidate())
    assert out["titles"] == ["Director, Medical Affairs", "Senior Manager, Medical Affairs"]
    assert out["skill_terms"] == ["Veeva CRM", "KOL engagement"]
    assert out["min_level"] == "senior_manager"  # one below the most recent title (director)


def test_min_level_defaults_to_one_below_the_latest_title_and_respects_a_choice():
    assert resolve_min_level(Preferences(), ["Vice President, Strategy"]) == "senior_director"
    assert resolve_min_level(Preferences(titles=["Director, Data"])) == "senior_manager"
    assert resolve_min_level(Preferences(min_level="vp"), ["Analyst"]) == "vp"
    assert resolve_min_level(Preferences()) == "manager"
    assert Preferences().normalized().min_level == ""

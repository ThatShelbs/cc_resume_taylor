"""The interview preparation step: which skills to confirm, and tolerant question parsing."""

from resume_taylor.pipeline import interview


def test_skill_checks_list_hard_gaps_first_and_skip_covered_terms():
    reqs = [
        {"term": "Influence VPs", "tier": "competency", "status": "positionable", "kind": "soft", "ids": []},
        {"term": "Databricks", "tier": "tool", "status": "gap", "kind": "hard", "ids": []},
        {"term": "Python", "tier": "tool", "status": "covered", "kind": "hard", "ids": []},
    ]
    assert [c["name"] for c in interview.skill_checks(reqs)] == ["Databricks", "Influence VPs"]


def test_questions_parse_and_fall_back(monkeypatch):
    monkeypatch.setattr(interview, "find_claude_cli", lambda: "claude")
    replies = iter(['```json\n{"questions": [{"question": "Tell me about X — now?", "why": "Y"}]}\n```', "not json"])
    monkeypatch.setattr(interview, "invoke_claude", lambda *a, **k: next(replies))
    qs = interview.ask_questions("msg", None, None)
    assert qs == [{"question": "Tell me about X , now?", "why": "Y"}]
    assert interview.ask_questions("msg", None, None) == []
    assert interview._fallback_questions({"competencies": ["product ownership"]})[0]["question"].startswith("Tell me about")

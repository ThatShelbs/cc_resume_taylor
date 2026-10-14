"""Recency trimming, title guard, skill groups, and the voice-pass acceptance check."""

import docx

from resume_taylor.pipeline.guards_quality import limit_bullets_by_recency, warn_unsupported_title
from resume_taylor.pipeline.render.docx_builder import build_docx
from resume_taylor.pipeline.runtime import WARNINGS
from resume_taylor.pipeline.skills import build_skill_groups, consistent_skill_groups
from resume_taylor.pipeline.voice_pass import _acceptable


def _warned(fn, *args):
    before = len(WARNINGS)
    fn(*args)
    return WARNINGS[before:]


def test_recency_caps_old_roles_but_never_drops_an_employer():
    jobs = [
        {"company": "New", "dates": "2021 - Present"},
        {"company": "Old", "dates": "Jan 2005 - Dec 2010"},
        {"company": "Undated", "dates": ""},
    ]
    bullets = {c: [f"{c} bullet {i}." for i in range(6)] for c in ("New", "Old", "Undated")}
    trimmed = limit_bullets_by_recency(bullets, jobs, 2026)
    assert len(trimmed["New"]) == 5 and len(trimmed["Undated"]) == 5
    assert trimmed["Old"] == ["Old bullet 0.", "Old bullet 1."]


def test_title_warning_only_when_the_title_is_not_the_candidates_own():
    assert _warned(warn_unsupported_title, "Head of Analytics with 10 years.", "Head of Analytics", "Analyst at Acme")
    assert not _warned(
        warn_unsupported_title, "Head of Analytics with 10 years.", "Head of Analytics", "Head of Analytics, Acme"
    )


def test_skill_groups_follow_the_draft_and_fall_back_when_edited():
    draft = "**Tools:** Python | SQL\n**Leadership:** Team Leadership\n"
    skills = ["Python", "Team Leadership", "SQL", "Git"]
    groups = build_skill_groups(skills, draft)
    assert groups == [
        {"label": "Tools", "skills": ["Python", "SQL"]},
        {"label": "Leadership", "skills": ["Team Leadership"]},
        {"label": "Other", "skills": ["Git"]},
    ]
    assert consistent_skill_groups(groups, skills) == groups
    assert consistent_skill_groups(groups, [*skills, "Rust"]) is None, "an edited list renders flat"
    assert build_skill_groups(skills, "no categories here") is None


def test_grouped_skills_render_as_labeled_lines(tmp_path):
    out = tmp_path / "r.docx"
    data = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "phone": "",
        "location": "",
        "summary": "Analyst.",
        "skills": ["Python", "Team Leadership"],
        "skill_groups": [
            {"label": "Tools", "skills": ["Python"]},
            {"label": "Leadership", "skills": ["Team Leadership"]},
        ],
    }
    build_docx(data, out)
    texts = [p.text for p in docx.Document(str(out)).paragraphs]
    assert "Tools: Python" in texts and "Leadership: Team Leadership" in texts


def test_voice_pass_rewrites_must_keep_numbers_and_stay_short():
    original = "Spearheaded a seamless migration cutting costs 12%."
    assert _acceptable(original, "Led a migration that cut costs 12%.")
    assert not _acceptable(original, "Led a migration that cut costs 15%.")
    assert not _acceptable(original, "Led a robust migration that cut costs 12%.")
    assert not _acceptable(original, "Led a migration that cut costs 12% across every team and region we supported.")

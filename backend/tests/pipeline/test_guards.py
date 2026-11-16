"""The deterministic validation/correction guards."""

from resume_taylor.pipeline.guards import (
    find_deny_violations,
    fix_years_of_experience,
    load_deny_patterns,
    remove_em_dashes,
    strip_cross_employer_mentions,
)
from resume_taylor.pipeline.runtime import WARNINGS
from support import DENY_FIXTURE


def test_deny_list_blocks_identities_not_collaboration():
    patterns = load_deny_patterns(DENY_FIXTURE)
    ok = find_deny_violations("Partnered with software engineers.", {}, [], patterns)
    bad = find_deny_violations("Worked as a full-stack engineer.", {}, ["Figma"], patterns)
    assert ok == []
    assert len(bad) == 2


def test_fix_years_of_experience():
    src = "Data scientist with 10 years of experience."
    assert fix_years_of_experience("Leader with 15+ years of experience.", src) == (
        "Leader with 10+ years of experience."
    )
    assert fix_years_of_experience("Leader with 11 years of experience.", src).startswith("Leader with 11")


def test_fix_years_catches_loose_phrasing():
    src = "Data scientist with 10 years of experience."
    assert fix_years_of_experience("Over 15 years leading teams.", src) == "Over 10 years leading teams."
    assert fix_years_of_experience("Built 3 years of models.", src) == "Built 3 years of models."


def test_remove_em_dashes():
    assert remove_em_dashes("Built X — and Y") == "Built X, and Y"
    assert remove_em_dashes("Built X – and Y") == "Built X, and Y"
    assert remove_em_dashes("From 2019–2021") == "From 2019–2021"


def test_strip_cross_employer_mentions():
    out = strip_cross_employer_mentions(
        {"Allstate Insurance": ["Did X at Acme.", "Did Y."], "Acme Corp": ["Did Z."]}
    )
    assert out == {"Allstate Insurance": ["Did Y."], "Acme Corp": ["Did Z."]}
    assert len(WARNINGS) == 1


def test_drop_unverified_skills_removes_hard_skills_and_keeps_supported_and_soft_ones(capsys):
    from resume_taylor.pipeline.guards import drop_unverified_skills

    source = "Led a team of analysts. Built Python and SQL pipelines. Presented to executives."
    skills = ["Python", "Databricks", "PHP", "R", "Go", "Stakeholder Management", "SQL (Postgres)"]
    kept = drop_unverified_skills(skills, source, extra_evidence="Fact: owned the roadmap")
    assert kept == ["Python", "Stakeholder Management", "SQL (Postgres)"]
    out = capsys.readouterr().out
    assert "removed skill 'Databricks'" in out and "removed skill 'PHP'" in out


def test_drop_unverified_skills_drops_soft_skills_without_any_leadership_evidence():
    from resume_taylor.pipeline.guards import drop_unverified_skills

    assert drop_unverified_skills(["Executive Influence", "SQL"], "Wrote SQL reports.") == ["SQL"]

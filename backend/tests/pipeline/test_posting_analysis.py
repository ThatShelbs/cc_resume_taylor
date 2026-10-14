"""Posting analysis: the requirement map, acronym pairing, and the claim audit."""

from resume_taylor.pipeline.posting_analysis import (
    apply_acronym_pairs,
    audit_requirements,
    build_requirement_map,
    missing_supported_terms,
    priorities_block,
)

ANALYSIS = {
    "target_title": "Head of Analytics",
    "must_have": ["Marketing Mix Modeling", "Kubernetes", "Experiment Platforms"],
    "nice_to_have": ["Forecasting"],
    "tools": ["Python"],
    "acronym_pairs": [["MMM", "Marketing Mix Modeling"]],
}
FACTS = {
    "F001": {"id": "F001", "employer": "Acme", "text": "Built a marketing mix modeling program.", "tags": ["mmm"], "metrics": []},
    "F002": {"id": "F002", "employer": "unassigned", "text": "Forecasting for stores.", "tags": [], "metrics": []},
}
SOURCE = "Built a marketing mix modeling program. Ran experiments across teams. Python."
PROFILE = {"tools": ["Python"], "skills": []}


def test_requirement_map_classifies_covered_adjacent_and_gap():
    reqs = {r["term"]: r for r in build_requirement_map(ANALYSIS, SOURCE, FACTS, PROFILE)}
    assert reqs["Marketing Mix Modeling"]["status"] == "covered" and reqs["Marketing Mix Modeling"]["ids"] == ["F001"]
    assert reqs["Python"]["status"] == "covered" and reqs["Python"]["ids"] == []
    assert reqs["Experiment Platforms"]["status"] == "adjacent"
    assert reqs["Kubernetes"]["status"] == "gap"
    assert reqs["Forecasting"]["status"] == "gap", "an unassigned fact is not evidence"


def test_priorities_block_lists_gaps_as_off_limits():
    reqs = build_requirement_map(ANALYSIS, SOURCE, FACTS, PROFILE)
    block = priorities_block(ANALYSIS, reqs)
    assert "Target title: Head of Analytics" in block
    assert "- Marketing Mix Modeling (must) [F001]" in block
    assert "Do not claim, imply, or hint at these:\n- Kubernetes" in block
    assert "MMM = Marketing Mix Modeling" in block


def test_missing_supported_terms_only_counts_covered_requirements():
    reqs = build_requirement_map(ANALYSIS, SOURCE, FACTS, PROFILE)
    assert missing_supported_terms(reqs, "Led marketing mix modeling.") == ["Python"]
    assert missing_supported_terms(reqs, "marketing mix modeling in Python") == []


def test_acronym_pairs_keep_the_candidates_own_form_first():
    pairs = [["MMM", "Marketing Mix Modeling"]]
    job = "Experience with MMM (Marketing Mix Modeling)."
    assert apply_acronym_pairs(["MMM", "Marketing Mix Modeling", "Python"], pairs, job) == [
        "MMM (Marketing Mix Modeling)",
        "Marketing Mix Modeling (MMM)",
        "Python",
    ]
    assert apply_acronym_pairs(["MMM"], pairs, "Experience with MMM only.") == ["MMM"], "posting must use both forms"


def test_audit_reports_where_each_requirement_is_used():
    reqs = build_requirement_map(ANALYSIS, SOURCE, FACTS, PROFILE)
    experience = [{"company": "Acme", "bullets": [{"text": "Led marketing mix modeling."}]}]
    audit = {r["term"]: r for r in audit_requirements(reqs, "Led marketing mix modeling.", experience)}
    assert audit["Marketing Mix Modeling"]["roles"] == ["Acme"] and audit["Marketing Mix Modeling"]["in_output"]
    assert not audit["Kubernetes"]["in_output"] and audit["Kubernetes"]["roles"] == []

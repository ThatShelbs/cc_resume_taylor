from resume_taylor.search.insights import posting_insights_text

POSTING = {
    "fit": {"angle": "Led launch analytics at scale (F003).", "gaps": ["Pharma launches"],
            "subscores": {"skills": {"score": 20, "max": 25, "evidence": ["F003", "F011", "a resume line"]}}},
    "requirements": [
        {"term": "SQL", "status": "covered"}, {"term": "stakeholder influence", "status": "positionable"},
        {"term": "Spark", "status": "gap"},
    ],
}


def test_insights_are_labeled_hints_with_gaps_marked_do_not_claim():
    text = posting_insights_text(POSTING)
    assert text.startswith("JOB SEARCH HINTS") and "Emphasis only" in text
    assert "Facts the search matched to this role: F003, F011" in text and "a resume line" not in text
    assert "supports: SQL" in text and "related real work" in text
    assert "Gaps (do not claim these): Pharma launches; Spark" in text


def test_no_fit_and_no_requirements_means_no_hints():
    assert posting_insights_text({}) == ""
    assert posting_insights_text({"fit": {"gaps": [], "subscores": {}}, "requirements": []}) == ""

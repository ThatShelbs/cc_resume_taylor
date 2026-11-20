import json

import pytest

from resume_taylor.api.storage.job_search import JobSearchStore
from resume_taylor.search.dedupe import dedupe
from resume_taylor.search.normalize import new_posting, norm_company, same_company


@pytest.mark.parametrize("a,b", [
    ("Veeva", "Veeva Systems"),
    ("Veeva Systems, Inc.", "veeva"),
    ("J&J", "Johnson & Johnson"),
    ("J&J Innovative Medicine", "Johnson & Johnson"),
    ("Johnson & Johnson MedTech", "JNJ"),
    ("Eli Lilly and Company", "Lilly"),
    ("Teladoc Health", "Teladoc"),
])
def test_same_company_variants_share_a_key(a, b):
    assert norm_company(a) == norm_company(b)
    assert same_company(a, b)


@pytest.mark.parametrize("a,b", [
    ("Johnson Controls", "Johnson & Johnson"),
    ("Johnson Controls", "J&J"),
    ("Health Catalyst", "Teladoc Health"),
    ("Veeva", "Vera"),
])
def test_different_companies_stay_apart(a, b):
    assert not same_company(a, b)
    assert norm_company(a) != norm_company(b)


def test_postings_at_variant_company_names_merge():
    a = new_posting(source="x", ats="greenhouse", company="Veeva Systems", title="Director, Medical Affairs", req_id="R1")
    b = new_posting(source="y", ats="aggregator", company="Veeva", title="Director, Medical Affairs", req_id="R1", aggregator_only=True)
    assert len(dedupe([a, b])) == 1


def test_targets_are_merged_once_with_a_backup(tmp_path):
    store = JobSearchStore(tmp_path)
    (tmp_path / "targets.json").write_text(json.dumps([
        {"id": "veeva", "name": "Veeva", "notes": "mine"},
        {"id": "veevasystems", "name": "Veeva Systems", "careers_url": "https://careers.veeva.com"},
        {"id": "jj", "name": "J&J"},
        {"id": "jjmedicine", "name": "J&J Medicine"},
    ]), encoding="utf-8")
    targets = store.targets()
    assert [t["name"] for t in targets] == ["Veeva", "J&J"]
    assert targets[0]["careers_url"] == "https://careers.veeva.com"
    assert targets[0]["notes"] == "mine"
    assert list(tmp_path.glob("targets.*.bak.json"))
    result = store.add_targets([{"name": "Johnson & Johnson"}, {"name": "Veeva Inc"}, {"name": "Pfizer"}])
    assert result["added"] == ["Pfizer"] and len(result["skipped"]) == 2

"""Company briefs keep only what carries a real source link, and are cached for a week."""

from resume_taylor.search import claude as claude_mod
from resume_taylor.search import research

BRIEF = {"companies": [{
    "name": "Acme", "snapshot": "Acme makes industrial sensors.", "snapshot_url": "https://acme.com/about",
    "signals": [
        {"text": "Raised a Series C.", "date": "2026-09", "url": "https://news.example.com/acme-series-c"},
        {"text": "Rumored layoffs.", "date": "2026-10", "url": ""},
        {"text": "Great place to work.", "date": "", "url": "https://www.glassdoor.com/acme"},
    ],
    "needs": "A leader who can scale analytics for the launch team.",
}]}


def test_sanitize_drops_unsourced_and_job_board_claims():
    got = research.sanitize(BRIEF["companies"][0])
    assert got["snapshot"].startswith("Acme makes") and got["snapshot_url"] == "https://acme.com/about"
    assert [s["text"] for s in got["signals"]] == ["Raised a Series C."]
    assert got["needs"].startswith("A leader")


def test_a_snapshot_without_a_source_is_dropped_but_the_posting_read_stays():
    got = research.sanitize({"snapshot": "Big company.", "snapshot_url": "", "signals": [], "needs": "Own the roadmap."})
    assert got == {"snapshot": "", "snapshot_url": "", "signals": [], "needs": "Own the roadmap."}
    assert research.sanitize({"snapshot": "x", "snapshot_url": "", "signals": [], "needs": ""}) is None


def test_results_get_briefs_and_the_second_run_uses_the_cache(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: calls.append(1) or BRIEF)
    results = [{"company": "Acme", "title": "Director", "description_text": "Lead analytics."}]
    assert research.research_results(results, cache_dir=tmp_path, progress=lambda m: None) == 1
    assert results[0]["research"]["signals"][0]["url"].startswith("https://news.example.com")
    again = [{"company": "Acme Inc.", "title": "VP", "description_text": "x"}]
    assert research.research_results(again, cache_dir=tmp_path, progress=lambda m: None) == 1 and len(calls) == 1


def test_a_failed_call_leaves_results_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: None)
    results = [{"company": "Acme", "title": "Director", "description_text": "x"}]
    assert research.research_results(results, cache_dir=tmp_path, progress=lambda m: None) == 0 and "research" not in results[0]

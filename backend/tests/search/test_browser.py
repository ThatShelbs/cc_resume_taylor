"""Signed-in job board search: pacing, bot-check tripwire, parsers and the driver, all offline with
a fake page source (no Chrome, no network)."""

from datetime import datetime, timezone

from resume_taylor.search.browser import driver, sites
from resume_taylor.search.browser.session import Page
from resume_taylor.search.browser.state import RUN_BUDGET, AccountState, new_usage, tripped

T0 = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def make_state(tmp_path, clock=None):
    return AccountState(tmp_path / "accounts.json", now=clock or Clock())


LINKEDIN_HTML = """
<ul><li><div class="job-card"><a href="https://www.linkedin.com/jobs/view/director-of-ops-at-acme-3912345678?x=1">
Director of Operations</a><h4 class="base-search-card__subtitle">Acme Corp</h4>
<span class="job-search-card__location">Chicago, IL</span></div></li></ul>"""

ZIP_HTML = """<html><script type="application/ld+json">{"@context":"https://schema.org","@type":"ItemList","numberOfItems":2,
"itemListElement":[{"@type":"ListItem","position":"1","name":"Project Manager II",
"url":"https://www.ziprecruiter.com/c/Apex-Systems/Job/Project-Manager-II/-in-Greenwood-Village,CO?jid=d974590db25b640e"},
{"@type":"ListItem","position":"2","name":"Program Director",
"url":"https://www.ziprecruiter.com/c/Acme-Health/Job/Program-Director/-in-Denver,CO?jid=0123456789abcdef"}]}</script>
<script type="application/ld+json">{"@type":"FAQPage","mainEntity":[]}</script></html>"""

ZIP_DETAIL = """<div><h2 class="font-bold">Job description</h2><div class="flex flex-col">
<div class="text-primary whitespace-pre-line [overflow-wrap:anywhere]">Lead delivery of IT projects.<br>Salary: $110,000 - $130,000 per year</div>
</div></div><div>Similar Jobs</div>"""

INDEED_HTML = """
<div class="job_seen_beacon"><a data-jk="abcdef0123456789"><h2 class="jobTitle"><span>VP Operations</span></h2></a>
<span data-testid="company-name">Globex</span><div data-testid="text-location">Remote</div></div>"""


class FakeSession:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def fetch(self, url):
        self.calls.append(url)
        return self.pages.pop(0) if len(self.pages) > 1 else self.pages[0]


def page(html="", text="results", url="https://www.linkedin.com/jobs/search/"):
    return Page(url=url, html=html, text=text, links=[])


def test_parsers_read_fixtures():
    li = sites.parse_linkedin(LINKEDIN_HTML)
    assert [(p["title"], p["company"], p["external_id"]) for p in li] == [("Director of Operations", "Acme Corp", "3912345678")]
    assert li[0]["aggregator_only"] and li[0]["source"] == "linkedin"
    ind = sites.parse_indeed(INDEED_HTML)
    assert [(p["title"], p["company"]) for p in ind] == [("VP Operations", "Globex")]
    zr = sites.parse_ziprecruiter(ZIP_HTML)
    assert [(p["title"], p["company"], p["locations"], p["external_id"]) for p in zr] == [
        ("Project Manager II", "Apex Systems", ["Greenwood Village, CO"], "d974590db25b640e"),
        ("Program Director", "Acme Health", ["Denver, CO"], "0123456789abcdef"),
    ]
    assert zr[0]["source"] == "ziprecruiter" and zr[0]["aggregator_only"]
    assert sites.parse_detail("ziprecruiter", ZIP_DETAIL).startswith("Lead delivery of IT projects.")


def test_search_urls_cover_every_site_and_reject_unknown():
    import pytest

    assert "fromage=14" in sites.search_url("indeed", "vp ops", "Chicago, IL", 14)
    assert sites.search_url("ziprecruiter", "vp ops", "Chicago, IL", 7).endswith("&days=10")
    assert sites.search_url("ziprecruiter", "vp ops", "Chicago, IL", 60).endswith("&days=30")
    with pytest.raises(ValueError):
        sites.search_url("google", "vp ops", "Chicago, IL", 14)


def test_tripwire_flags_bot_checks_and_sign_out():
    assert tripped("https://www.linkedin.com/jobs/", "Please complete this security check")
    assert tripped("https://www.linkedin.com/authwall?x", "hello") == "signed out"
    assert tripped("https://www.linkedin.com/jobs/search/", "Director of Operations") == ""


def test_per_run_budget_and_no_daily_cap(tmp_path):
    st = make_state(tmp_path)
    st.mark_connected("indeed")
    qs = [{"q": f"director {i}", "location": "Chicago"} for i in range(RUN_BUDGET["search"] + 5)]
    for _run in range(3):  # several runs in one day: each gets the full budget
        s, used = FakeSession([page(INDEED_HTML, url="https://www.indeed.com/jobs")]), new_usage()
        hits, note = driver.search_site("indeed", s, st, qs, 14, usage=used, progress=lambda *_: None)
        assert len(s.calls) == RUN_BUDGET["search"] == used["search"] == 10
        assert "this run's 10 searches" in note
        st.record_run("indeed", used)
    assert st.can_use("indeed") and st.status("indeed")["last_run"]["search"] == 10


def test_detail_budget_is_per_run(tmp_path):
    st = make_state(tmp_path)
    st.mark_connected("linkedin")
    s, used = FakeSession([page('<div class="show-more-less-html__markup">Full text</div>')]), new_usage()
    posts = [{"url": f"https://www.linkedin.com/jobs/view/{i}"} for i in range(RUN_BUDGET["detail"] + 3)]
    opened = sum(driver.hydrate_detail("linkedin", s, st, p, used) for p in posts)
    assert opened == RUN_BUDGET["detail"] == used["detail"]


def test_not_connected_site_is_unusable_unless_login_optional(tmp_path):
    st = make_state(tmp_path)
    assert not st.can_use("linkedin")
    assert st.can_use("ziprecruiter") and st.status("ziprecruiter")["login_optional"]
    st.trip("ziprecruiter", "bot check (captcha)")
    assert not st.can_use("ziprecruiter")


def test_retired_google_state_is_forgotten(tmp_path):
    (tmp_path / "accounts.json").write_text('{"google": {"connected_at": "2026-11-01T00:00:00+00:00"}, "linkedin": {}}')
    st = make_state(tmp_path)
    assert st.forget_retired() == ["google"]
    assert "google" not in (tmp_path / "accounts.json").read_text() and st.forget_retired() == []


def test_login_wall_stops_the_site_without_retry(tmp_path):
    st = make_state(tmp_path)
    st.mark_connected("linkedin")
    s = FakeSession([page(url="https://www.linkedin.com/authwall?trk=x")])
    qs = [{"q": "director", "location": "Chicago"}, {"q": "vp", "location": "Chicago"}]
    hits, note = driver.search_site("linkedin", s, st, qs, 14, progress=lambda *_: None)
    assert hits == [] and "stopped for today" in note
    assert len(s.calls) == 1  # no second query, no retry
    assert not st.status("linkedin")["connected"] and st.status("linkedin")["cooldown_until"]


def test_search_returns_hits_and_counts_usage(tmp_path):
    st = make_state(tmp_path)
    st.mark_connected("linkedin")
    s = FakeSession([page(LINKEDIN_HTML)])
    hits, note = driver.search_site("linkedin", s, st, [{"q": "director", "location": "Chicago"}], 14, progress=lambda *_: None)
    assert note == "" and len(hits) == 1
    assert st.status("linkedin")["last_run"] is None  # written once at the end of a run, by run.py


def test_claude_fallback_keeps_only_text_backed_jobs(monkeypatch):
    reply = {"jobs": [
        {"title": "Director of Ops", "company": "Acme", "location": "IL", "url": "https://x.test/1"},
        {"title": "Invented Role", "company": "Nobody Inc", "location": "", "url": ""},
    ]}
    monkeypatch.setattr(sites, "ask", lambda *a, **k: reply)
    out = sites.claude_extract("ziprecruiter", "Director of Ops at Acme in IL", ["https://x.test/1"], "ziprecruiter")
    assert [p["title"] for p in out] == ["Director of Ops"]


def test_state_file_holds_no_secrets(tmp_path):
    st = make_state(tmp_path)
    st.mark_connected("indeed")
    st.trip("indeed", "bot check (captcha)")
    text = (tmp_path / "accounts.json").read_text()
    assert "password" not in text.lower() and "cookie" not in text.lower()


def test_run_search_uses_connected_account_and_skips_unconnected(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import httpx

    from resume_taylor.search import claude as claude_mod
    from resume_taylor.search import run
    from resume_taylor.search.http import Client

    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: None)
    st = AccountState(tmp_path / "accounts.json")
    st.mark_connected("linkedin")
    fake = FakeSession([page(LINKEDIN_HTML)])
    monkeypatch.setattr(run, "make_session", lambda site, d: fake)
    client = Client(cache_dir=None, transport=httpx.MockTransport(lambda r: httpx.Response(404)), sleep=lambda s: None)
    args = SimpleNamespace(prefs=None, targets=None, routes=None, store=None, cache_dir=None, profile=None, resume=None, fact_bank=None,
                           count=3, depth="quick", sources="linkedin_account,indeed_account", recency=14, model=None, effort=None,
                           accounts_dir=str(tmp_path))
    report = run.run_search(args, client=client, progress=lambda *_: None)
    assert report["source_counts"].get("linkedin") == 1
    assert any("Indeed" in n and "skipped" in n for n in report["notes"])
    assert fake.calls  # LinkedIn was searched; Indeed (not connected) never opened a browser
    last = AccountState(tmp_path / "accounts.json").status("linkedin")["last_run"]
    assert (last["search"], last["detail"]) == (1, 1) and len(fake.calls) == 2  # one search, one shortlisted detail

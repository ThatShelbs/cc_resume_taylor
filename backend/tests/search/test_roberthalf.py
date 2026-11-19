"""Robert Half: public, server-rendered staffing-agency postings. Offline, with markup in the shape the
site serves (rhcl-job-card web components)."""

from types import SimpleNamespace

import httpx

from resume_taylor.search import claude as claude_mod
from resume_taylor.search import run
from resume_taylor.search.connectors import roberthalf as rh
from resume_taylor.search.http import Client
from resume_taylor.search.score import source_points

CARD = """
<rhcl-job-card job-id="00630-0013542640-usen" variant="card">
    <a href="https://www.roberthalf.com/us/en/job/denver-co/director-of-operations/00630-0013542640-usen" slot="headline" target="_blank">
        Director of Operations
    </a>
    <ul slot="job-info">
        <li data-subslot="location">Denver, CO</li>
        <li data-subslot="worksite">remote</li>
        <li data-subslot="type">Permanent / Full Time</li>
        <li data-subslot="salary">
            <span data-subslot="salary-min">150000</span> - <span data-subslot="salary-max">180000</span>
            <span data-subslot="salary-currency">USD</span> / <span data-subslot="salary-period">Annual</span>
        </li>
        <li data-subslot="copy">We are looking for a Director of Operations.&lt;br&gt;&lt;br&gt;Responsibilities:&lt;br&gt;Lead the team.</li>
        <li data-subslot="date">2026-11-16T15:48:44Z</li>
    </ul>
</rhcl-job-card>"""

DETAIL = """<rhcl-job-card job-id="00630-0013542640-usen" variant="listing">
<a href="https://www.roberthalf.com/us/en/job/denver-co/director-of-operations/00630-0013542640-usen" slot="headline">Director of Operations</a>
<div slot="description" data-testid="job-details-description">
We are looking for a Director of Operations.&lt;br&gt;Lead a team of 40 across three sites.
</div>
<div slot="requirements" data-testid="job-details-requirements">
&lt;br&gt;10+ years of operations leadership.
</div></rhcl-job-card>"""


def test_search_url_slugs_place_keywords_and_window():
    assert rh.search_url("Director of Operations", "Denver, CO", 7) == \
        "https://www.roberthalf.com/us/en/jobs/denver-co/director-of-operations?postedwithin=7"
    assert rh.search_url("VP, Ops", "Remote (United States)", 14).endswith("/jobs/all/vp-ops?postedwithin=30")
    assert rh.search_url("VP Ops", "Crystal Lake, IL", 90).endswith("/jobs/crystal-lake-il/vp-ops?postedwithin=0")


def test_parse_cards_marks_agency_postings():
    [p] = rh.parse_cards(CARD + CARD)  # duplicates collapse
    assert (p["title"], p["company"], p["source"], p["agency"]) == \
        ("Director of Operations", "Robert Half (client not named)", "roberthalf", "Robert Half")
    assert p["locations"] == ["Denver, CO", "Remote"] and p["work_mode"] == "remote"
    assert (p["pay_min"], p["pay_max"]) == (150000, 180000) and p["posted_at"].startswith("2026-11-16")
    assert not p["aggregator_only"] and p["needs_detail"] and p["route"] == {"ats": "roberthalf"}
    assert "Lead the team." in p["description_text"]
    assert source_points(p) == 3  # a distinct listing, but not the employer's own


def test_hydrate_and_verify_use_the_posting_page():
    pages = {"/us/en/job/denver-co/director-of-operations/00630-0013542640-usen": DETAIL}
    client = Client(cache_dir=None, sleep=lambda s: None, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, text=pages.get(r.url.path, "")) if r.url.path != "/robots.txt" else httpx.Response(404)))
    [p] = rh.parse_cards(CARD)
    rh.hydrate(client, {}, p)
    assert "40 across three sites" in p["description_text"] and "10+ years" in p["description_text"]
    assert rh.verify(client, {}, p) is True
    pages.clear()  # the page now says nothing about this posting: it was taken down
    assert rh.verify(client, {}, p) is False


def test_run_search_adds_robert_half_without_crosswalk(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: None)

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(404)
        if req.url.path.startswith("/us/en/jobs/"):
            return httpx.Response(200, text=CARD)
        return httpx.Response(200, text=DETAIL)

    client = Client(cache_dir=None, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    args = SimpleNamespace(prefs=None, targets=None, routes=str(tmp_path / "routes.json"), store=None, cache_dir=None, profile=None,
                           resume=None, fact_bank=None, count=3, depth="quick", sources="roberthalf", recency=14, model=None,
                           effort=None, accounts_dir=None)
    report = run.run_search(args, client=client, progress=lambda *_: None)
    assert report["source_counts"]["roberthalf"] == 1
    assert report["source_counts"]["board_only_leads"] == 0  # agency postings never go through crosswalk
    assert report["postings_seen"] == 1

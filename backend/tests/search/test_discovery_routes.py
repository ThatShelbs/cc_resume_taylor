"""Career-site discovery that never settles for an empty board, plus the company's own site search."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from resume_taylor.search import claude as claude_mod
from resume_taylor.search import discovery, run
from resume_taylor.search.connectors import careers_page, workday
from resume_taylor.search.http import Client
from resume_taylor.search.prefs import Preferences
from resume_taylor.search.routes import RouteBook


def make_client(handler):
    return Client(transport=httpx.MockTransport(handler), sleep=lambda s: None)


def jsonld(title: str, url: str = "", ident: str = "") -> str:
    body = {"@type": "JobPosting", "title": title, "description": "<p>" + "Lead medical strategy. " * 30 + "</p>",
            "datePosted": "2026-11-10", "hiringOrganization": {"name": "Acme"}}
    if url:
        body["url"] = url
    if ident:
        body["identifier"] = {"value": ident}
    return f'<script type="application/ld+json">{json.dumps(body)}</script>'


SEARCH_PAGE = (
    "<html><body>"
    '<a href="/jobs/1001/director-medical-affairs">Director</a>'
    '<a href="https://careers.acme.com/job/1002">VP</a>'
    '<a href="https://tracker.evil.com/job/9">ad</a>'
    '<a href="/about">About</a></body></html>'
)


def acme_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "boards-api.greenhouse.io/v1/boards/acme" in url and "/jobs" in url:
        return httpx.Response(200, json={"jobs": []})
    if url.endswith("/v1/boards/acme"):
        return httpx.Response(200, json={"name": "Acme"})
    if "careers.acme.com/search" in url:
        return httpx.Response(200, text=SEARCH_PAGE)
    if "/jobs/1001/" in url:
        return httpx.Response(200, text="<html>" + jsonld("Director, Medical Affairs") + "</html>")
    if "/job/1002" in url:
        return httpx.Response(200, text="<html><head><title>VP Medical | Acme</title></head><h1>VP Medical</h1>"
                              + "<p>" + "Own the medical affairs strategy across regions. " * 20 + "</p></html>")
    return httpx.Response(404)


def test_empty_board_falls_through_to_the_companys_own_site_search(tmp_path, monkeypatch):
    def fake_ask(system, user, **kw):
        return {"companies": [{"name": "Acme", "careers_url": "https://careers.acme.com",
                               "search_url": "https://careers.acme.com/search?q={q}"}]}

    monkeypatch.setattr(claude_mod, "ask", fake_ask)
    book = RouteBook(tmp_path / "routes.json")
    out = discovery.discover_routes(make_client(acme_handler), book, [{"name": "Acme"}], progress=lambda m: None)
    rec = out["Acme"]
    assert rec["status"] == "resolved" and rec["ats"] == "careers_page"
    assert rec["job_count"] == 2 and rec["search_url"].endswith("{q}")


def test_a_board_that_lists_nothing_is_saved_as_empty_not_connected(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: {"companies": [{"name": "Acme", "notes": "no site found"}]})
    book = RouteBook(tmp_path / "routes.json")
    out = discovery.discover_routes(make_client(acme_handler), book, [{"name": "Acme"}], progress=lambda m: None)
    assert out["Acme"]["status"] == "empty" and out["Acme"]["ats"] == "greenhouse" and out["Acme"]["job_count"] == 0
    assert book.usable("Acme")  # trusted for a few days...
    book.routes["acme"]["verified_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec="seconds")
    assert book.usable("Acme") is None  # ...then looked at again


def test_recent_failures_are_not_researched_every_run(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: calls.append(1) or {"companies": []})
    book = RouteBook(tmp_path / "routes.json")
    book.set("Nowhere Co", {"ats": ""}, method="none", job_count=None, status="failed", note="nothing")
    out = discovery.discover_routes(make_client(lambda r: httpx.Response(404)), book, [{"name": "Nowhere Co"}], progress=lambda m: None)
    assert out["Nowhere Co"]["status"] == "failed" and not calls


@pytest.mark.parametrize("text,expect", [
    ("https://wd5.myworkdaysite.com/en-US/recruiting/acme/External", {"ats": "workday", "host": "wd5.myworkdaysite.com", "tenant": "acme", "site": "External"}),
    ("https://pfizer.wd1.myworkdayjobs.com/en-US/PfizerCareers", {"ats": "workday", "host": "pfizer.wd1.myworkdayjobs.com", "tenant": "pfizer", "site": "PfizerCareers"}),
])
def test_workday_fingerprints(text, expect):
    got = discovery.fingerprint(text)
    assert all(got[k] == v for k, v in expect.items())


def test_workday_fingerprint_skips_a_reserved_first_match():
    html = '<a href="https://acme.wd1.myworkdayjobs.com/wday/x">a</a> <a href="https://acme.wd1.myworkdayjobs.com/AcmeExternal">b</a>'
    assert discovery.fingerprint(html)["site"] == "AcmeExternal"


def test_myworkdaysite_postings_get_recruiting_urls():
    route = {"host": "wd5.myworkdaysite.com", "tenant": "acme", "site": "External", "recruiting": True}
    assert workday._public_url(route, "/job/1") == "https://wd5.myworkdaysite.com/recruiting/acme/External/job/1"


def test_first_word_slug_needs_the_whole_board_name(tmp_path):
    def handler(request):
        url = str(request.url)
        if url.endswith("/v1/boards/johnson"):
            return httpx.Response(200, json={"name": "Johnson Controls"})
        return httpx.Response(404)

    assert discovery.probe(make_client(handler), "Johnson & Johnson Vision") is None


def test_listing_page_postings_get_distinct_ids():
    html = "<html>" + jsonld("Director A", ident="R1") + jsonld("Director B", ident="R2") + "</html>"

    def handler(request):
        return httpx.Response(200, text=html)

    jobs = careers_page.list_jobs(make_client(handler), {"careers_url": "https://acme.com/careers"}, "Acme", [])
    assert len(jobs) == 2 and len({j["id"] for j in jobs}) == 2


def test_a_resolved_route_that_lists_nothing_is_marked_empty_after_a_run(tmp_path):
    book = RouteBook(tmp_path / "routes.json")
    book.set("Acme", {"ats": "greenhouse", "token": "acme"}, method="probe", job_count=5)
    book.record_run("Acme", 0)
    assert book.get("Acme")["status"] == "empty"
    book.record_run("Acme", 3)
    assert book.get("Acme")["status"] == "resolved"


def test_pull_company_drops_off_role_titles_and_counts_them():
    from resume_taylor.search.relevance import RoleFamily

    handler_jobs = {"jobs": [
        {"id": 1, "title": "Director, Medical Affairs", "absolute_url": "https://x/1", "location": {"name": "Remote"}, "content": ""},
        {"id": 2, "title": "Account Executive", "absolute_url": "https://x/2", "location": {"name": "Remote"}, "content": ""},
    ]}
    client = make_client(lambda r: httpx.Response(200, json=handler_jobs))
    family = RoleFamily.from_prefs(Preferences(titles=["Director, Medical Affairs"]))
    jobs, err, off = run.pull_company(client, {"ats": "greenhouse", "token": "acme"}, "Acme", family.search_terms(), "target", family=family)
    assert [j["title"] for j in jobs] == ["Director, Medical Affairs"] and off == 1 and err == ""

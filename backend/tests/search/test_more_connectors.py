"""Recruitee, BambooHR, Teamtailor, Breezy and Rippling: list, hydrate, verify and discovery, offline
against JSON in the shape each public endpoint returns."""

import json

import httpx

from resume_taylor.search import discovery
from resume_taylor.search.connectors import CONNECTORS
from resume_taylor.search.http import Client

RECRUITEE = {"offers": [{
    "id": 2832667, "title": "Director of Operations", "company_name": "Acme", "city": "Chicago", "state_code": "IL",
    "remote": False, "hybrid": True, "on_site": False, "published_at": "2026-11-18 16:23:32 UTC", "close_at": None,
    "careers_url": "https://careers.acme.test/o/director-ops", "careers_apply_url": "https://careers.acme.test/o/director-ops/c/new",
    "description": "<p>Lead operations.</p>", "requirements": "<p>10 years.</p>",
    "salary": {"min": "150000", "max": "180000", "period": "year", "currency": "USD"},
}]}
BAMBOO_LIST = {"meta": {"totalCount": 1}, "result": [{"id": "68", "jobOpeningName": "VP Operations ", "location": {"city": "Denver", "state": "Colorado"},
                                                       "atsLocation": {}, "isRemote": True}]}
BAMBOO_DETAIL = {"result": {"jobOpening": {"description": "<p>Own the plan. Salary $200,000 - $230,000 per year.</p>",
                                           "datePosted": "2026-11-10", "compensation": None}}}
TEAMTAILOR = {"items": [{"id": "b55", "title": "Head of Ops", "url": "https://acme.teamtailor.com/jobs/1-head-of-ops",
                         "date_published": "2026-11-11T17:34:36+01:00", "content_html": "<p>Lead.</p>",
                         "_jobposting": {"@type": "JobPosting", "title": "Head of Ops", "description": "<p>Lead the ops team.</p>",
                                         "datePosted": "2026-11-11", "jobLocation": {"address": {"addressLocality": "Austin", "addressRegion": "TX"}}}}]}
BREEZY = [{"id": "9bb", "name": "Operations Director", "url": "https://acme.breezy.hr/p/9bb-operations-director",
           "published_date": "2026-11-12T08:31:24.700Z", "location": {"name": "Lisbon, PT", "is_remote": False}, "salary": "", "locations": []}]
BREEZY_PAGE = ('<script type="application/ld+json">{"@type":"JobPosting","title":"Operations Director",'
               '"description":"<p>Run operations across EMEA.</p>"}</script>')
RIPPLING = {"items": [{"id": "84d", "name": "Business Operations Manager", "url": "https://ats.rippling.com/acme/jobs/84d",
                       "locations": [{"name": "New York, NY", "workplaceType": "ON_SITE"}]}], "page": 0, "totalPages": 1}
RIPPLING_PAGE = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {"apiData": {"jobPost": {
    "description": {"company": "<p>About Acme.</p>", "role": "<p>Run bizops.</p>"}, "createdOn": "2026-11-01T10:00:00-07:00",
    "payRangeDetails": [{"currency": "USD", "frequency": "YEAR", "rangeStart": 185000, "rangeEnd": 240000}]}}}}}) + "</script>"

ROUTES = {
    "acme.recruitee.com": {"/api/offers/": RECRUITEE},
    "acme.bamboohr.com": {"/careers/list": BAMBOO_LIST, "/careers/68/detail": BAMBOO_DETAIL},
    "acme.teamtailor.com": {"/jobs.json": TEAMTAILOR},
    "acme.breezy.hr": {"/json": BREEZY, "/p/9bb-operations-director": BREEZY_PAGE},
    "ats.rippling.com": {"/api/v2/board/acme/jobs": RIPPLING, "/acme/jobs/84d": RIPPLING_PAGE},
}


def make_client():
    def handler(req):
        body = ROUTES.get(req.url.host, {}).get(req.url.path)
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, text=body if isinstance(body, str) else json.dumps(body))
    return Client(cache_dir=None, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def one(route, company="Acme"):
    client = make_client()
    conn = CONNECTORS[route["ats"]]
    [p] = conn.list_jobs(client, route, company, [])
    if p.get("needs_detail"):
        conn.hydrate(client, route, p)
    return client, conn, p


def test_recruitee():
    client, conn, p = one({"ats": "recruitee", "token": "acme"})
    assert (p["title"], p["locations"], p["work_mode"]) == ("Director of Operations", ["Chicago, IL"], "hybrid")
    assert (p["pay_min"], p["pay_max"]) == (150000, 180000) and "10 years." in p["description_text"]
    assert p["url"] == "https://careers.acme.test/o/director-ops" and conn.verify(client, {"token": "acme"}, p) is True


def test_bamboohr_hydrates_from_detail():
    client, conn, p = one({"ats": "bamboohr", "token": "acme"})
    assert (p["title"], p["locations"], p["work_mode"]) == ("VP Operations", ["Denver, Colorado", "Remote"], "remote")
    assert "Own the plan." in p["description_text"] and p["posted_at"] == "2026-11-10" and p["pay_max"] == 230000
    assert not p["needs_detail"] and conn.verify(client, {"token": "acme"}, p) is True


def test_teamtailor_reads_the_jobposting():
    client, conn, p = one({"ats": "teamtailor", "host": "acme.teamtailor.com"})
    assert (p["title"], p["locations"], p["source"]) == ("Head of Ops", ["Austin, TX"], "teamtailor")
    assert "Lead the ops team." in p["description_text"] and conn.verify(client, {"host": "acme.teamtailor.com"}, p) is True


def test_breezy_hydrates_from_page_jsonld():
    client, conn, p = one({"ats": "breezy", "token": "acme"})
    assert (p["title"], p["locations"]) == ("Operations Director", ["Lisbon, PT"])
    assert p["description_text"] == "Run operations across EMEA." and conn.verify(client, {"token": "acme"}, p) is True


def test_rippling_hydrates_from_next_data():
    client, conn, p = one({"ats": "rippling", "token": "acme"})
    assert (p["title"], p["locations"], p["work_mode"]) == ("Business Operations Manager", ["New York, NY"], "onsite")
    assert "Run bizops." in p["description_text"] and (p["pay_min"], p["pay_max"]) == (185000, 240000)
    assert p["posted_at"].startswith("2026-11-01") and conn.verify(client, {}, p) is True


def test_fingerprints_and_probe_for_new_boards():
    assert discovery.fingerprint("https://acme.recruitee.com/o/x") == {"ats": "recruitee", "token": "acme"}
    assert discovery.fingerprint("https://acme.bamboohr.com/careers/68") == {"ats": "bamboohr", "token": "acme"}
    assert discovery.fingerprint("https://acme.breezy.hr/p/9bb") == {"ats": "breezy", "token": "acme"}
    assert discovery.fingerprint("https://ats.rippling.com/acme/jobs/1") == {"ats": "rippling", "token": "acme"}
    assert discovery.fingerprint("https://acme.teamtailor.com/jobs") == {"ats": "teamtailor", "host": "acme.teamtailor.com"}
    assert discovery.probe(make_client(), "Acme") == ({"ats": "recruitee", "token": "acme"}, -1)
    for route in ({"ats": "bamboohr", "token": "acme"}, {"ats": "teamtailor", "host": "acme.teamtailor.com"},
                  {"ats": "breezy", "token": "acme"}, {"ats": "rippling", "token": "acme"}):
        assert discovery.validate(make_client(), route, "Acme") == 1

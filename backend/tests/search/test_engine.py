"""The job search engine, offline: connectors against recorded-shape JSON through
httpx.MockTransport, and whole runs with Claude replaced by a stub."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from resume_taylor.search import claude as claude_mod
from resume_taylor.search import crosswalk, dedupe, discovery, filters, freshness, geo, normalize, run, score
from resume_taylor.search.connectors import ashby, careers_page, greenhouse, lever, workday
from resume_taylor.search.http import Client
from resume_taylor.search.prefs import Preferences
from resume_taylor.search.routes import RouteBook

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)


def iso(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def make_client(handler, tmp_path=None):
    return Client(cache_dir=tmp_path, transport=httpx.MockTransport(handler), sleep=lambda s: None)


# -- normalize ---------------------------------------------------------------------------------

@pytest.mark.parametrize("text,lo,hi", [
    ("Base $186.014,40 - $220.000,00 per year", 186014, 220000),
    ("range $194.600.00 to $230.000.00", 194600, 230000),
    ("$150k-$200k plus bonus", 150000, 200000),
    ("$225,000 - $265,000 USD", 225000, 265000),
])
def test_parse_pay_handles_odd_formats(text, lo, hi):
    got = normalize.parse_pay(text)
    assert (got["pay_min"], got["pay_max"]) == (lo, hi)


def test_parse_pay_hourly_and_none():
    assert normalize.parse_pay("$60 - $80 per hour")["pay_max"] == 166400
    assert normalize.parse_pay("competitive pay")["pay_max"] is None


@pytest.mark.parametrize("title,level", [
    ("Sr. Director, Data Science", "senior_director"), ("Head of AI", "director"),
    ("Senior Manager, Analytics", "senior_manager"), ("Data Scientist", "ic"),
    ("Vice President, Commercial", "vp"), ("Chief Data Officer", "executive"),
])
def test_title_level(title, level):
    assert normalize.title_level(title) == level


def test_equivalent_titles_count_as_director():
    assert normalize.title_level("Principal Scientist", ["principal"]) == "director"


def test_posted_ago():
    assert normalize.parse_posted_ago("Posted 3 Days Ago") == 3
    assert normalize.parse_posted_ago("Posted Today") == 0
    assert normalize.parse_posted_ago("2 weeks ago") == 14


# -- freshness, dedupe ---------------------------------------------------------------------------

def test_freshness_bands_and_points_decay():
    assert [freshness.band(a) for a in (0, 6, 7, 13, 14, 20, 21, None)] == [
        "fresh", "fresh", "active", "active", "aging", "aging", "late", "unknown"]
    pts = [freshness.points(a) for a in (1, 5, 10, 16, 30)]
    assert pts == sorted(pts, reverse=True) and pts[0] == 15


def test_dedupe_merges_locations_and_sources():
    a = normalize.new_posting(company="Acme Inc", title="Sr Director, AI", locations=["Chicago, IL"], req_id="R1",
                              description_text="x " * 50, url="u1")
    b = normalize.new_posting(company="Acme", title="Senior Director AI", locations=["Remote"], req_id="R1",
                              description_text="x " * 50, url="u2", also_listed_on=["linkedin"])
    out = dedupe.dedupe([a, b])
    assert len(out) == 1
    assert set(out[0]["locations"]) == {"Chicago, IL", "Remote"} and out[0]["also_listed_on"] == ["linkedin"]


# -- geo and filters -----------------------------------------------------------------------------

def test_parse_location_variants():
    assert geo.parse_location("Chicago, IL")["lat"] is not None
    assert geo.parse_location("North Chicago, Illinois, United States")["state"] == "IL"
    assert geo.parse_location("US-IL-Lake Forest")["city"] == "Lake Forest"
    r = geo.parse_location("Remote - US")
    assert r["remote"] and r["lat"] is None


def test_distance_crystal_lake_to_chicago_is_about_45_miles():
    d = geo.miles(geo.resolve("Crystal Lake, IL"), geo.resolve("Chicago, IL"))
    assert 40 < d < 55


def prefs(**kw):
    return Preferences(**{"min_level": "director", **kw}).normalized()


def posting(**kw):
    base = dict(company="Acme", title="Director, AI", locations=["Chicago, IL"], description_text="Lead the AI team." * 20,
                posted_at=iso(2), posted_at_source="ats", url="https://x/1", ats="greenhouse", external_id="1")
    base.update(kw)
    return normalize.new_posting(**base)


def test_filters_reject_on_evidence_and_pass_unknowns():
    pf = prefs(base_floor=225000, home_location="Crystal Lake, IL", radius_miles=60, remote_states=["IL"],
               exclusions=["MD required"])
    assert filters.apply_filters(posting(title="Data Scientist"), pf, NOW).reason == "level"
    assert filters.apply_filters(posting(pay_max=180000, currency="USD"), pf, NOW).reason == "pay_below_floor"
    assert filters.apply_filters(posting(description_text="MD required for this role"), pf, NOW).reason == "excluded"
    assert filters.apply_filters(posting(locations=["Houston, TX"]), pf, NOW).reason == "location"
    assert filters.apply_filters(posting(posted_at=iso(25)), pf, NOW).reason == "stale"
    ok = filters.apply_filters(posting(), pf, NOW)  # Chicago is inside 60 miles; pay unknown only flags
    assert ok.ok and "pay not stated" in ok.flags
    remote_tx = posting(locations=["Remote - Texas"], work_mode="remote")
    assert filters.apply_filters(remote_tx, pf, NOW).reason == "location"
    remote_us = posting(locations=["Remote - US"], work_mode="remote")
    assert filters.apply_filters(remote_us, pf, NOW).ok


def test_widened_window_keeps_older_postings():
    p = posting(posted_at=iso(25))
    assert not filters.apply_filters(p, prefs(), NOW, 14).ok
    assert filters.apply_filters(p, prefs(), NOW, 30).ok


# -- http ----------------------------------------------------------------------------------------

def test_http_caches_and_stops_after_rate_limit(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(200, text="hello") if "ok" in req.url.path else httpx.Response(429)

    c = make_client(handler, tmp_path)
    assert c.get_text("https://a.test/ok") == "hello" and c.get_text("https://a.test/ok") == "hello"
    assert len(calls) == 1  # second read came from the 24-hour cache
    assert c.get_text("https://b.test/limited") is None
    n = len(calls)
    assert c.get_text("https://b.test/other") is None and len(calls) == n  # host skipped for the run


def test_robots_txt_is_respected():
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private")
        return httpx.Response(200, text="page")

    c = make_client(handler)
    assert c.get_text("https://a.test/public", robots=True) == "page"
    assert c.get_text("https://a.test/private/x", robots=True) is None


# -- connectors ------------------------------------------------------------------------------------

def test_greenhouse_lever_ashby_parse():
    gh = {"jobs": [{"id": 7, "title": "Director, ML", "location": {"name": "Remote - US"}, "first_published": iso(3),
                    "absolute_url": "https://boards.greenhouse.io/acme/jobs/7",
                    "content": "&lt;p&gt;Pay range $200,000 - $250,000&lt;/p&gt;"}]}
    lv = [{"id": "L1", "text": "Head of Data", "categories": {"location": "Chicago, IL"}, "createdAt": int((NOW - timedelta(days=4)).timestamp() * 1000),
           "descriptionPlain": "Lead data.", "hostedUrl": "https://jobs.lever.co/acme/L1", "applyUrl": "https://jobs.lever.co/acme/L1/apply",
           "workplaceType": "hybrid", "salaryRange": {"min": 210000, "max": 260000, "currency": "USD", "interval": "per-year-salary"}}]
    ab = {"jobs": [{"id": "A1", "title": "VP AI", "location": "Boston, MA", "isRemote": False, "publishedAt": iso(1),
                    "jobUrl": "https://jobs.ashbyhq.com/acme/A1", "descriptionHtml": "<p>Own AI.</p>",
                    "compensation": {"compensationTiers": [{"components": [{"compensationType": "Salary", "minValue": 300000, "maxValue": 350000, "currencyCode": "USD"}]}]}}]}

    def handler(req):
        h = req.url.host
        return httpx.Response(200, json=gh if "greenhouse" in h else lv if "lever" in h else ab)

    c = make_client(handler)
    g = greenhouse.list_jobs(c, {"token": "acme"}, "Acme", [])[0]
    assert g["pay_max"] == 250000 and g["posted_at_source"] == "ats" and g["level"] == "director"
    le = lever.list_jobs(c, {"token": "acme"}, "Acme", [])[0]
    assert le["work_mode"] == "hybrid" and le["pay_min"] == 210000 and le["level"] == "director"
    a = ashby.list_jobs(c, {"token": "acme"}, "Acme", [])[0]
    assert a["pay_max"] == 350000 and a["level"] == "vp"


def test_workday_list_then_hydrate():
    def handler(req):
        if req.method == "POST":
            body = json.loads(req.content)
            jobs = [{"title": "Director, Analytics", "externalPath": "/job/Chicago/Director_R123", "locationsText": "Chicago, IL",
                     "postedOn": "Posted 3 Days Ago", "bulletFields": ["R123"]}] if body["offset"] == 0 else []
            return httpx.Response(200, json={"jobPostings": jobs, "total": len(jobs)})
        return httpx.Response(200, json={"jobPostingInfo": {"jobDescription": "<p>Lead analytics. $190,000 - $240,000</p>",
                                                           "location": "Chicago, IL", "jobReqId": "R123", "remoteType": "Hybrid"}})

    c = make_client(handler)
    route = {"host": "acme.wd5.myworkdayjobs.com", "tenant": "acme", "site": "Careers"}
    jobs = workday.list_jobs(c, route, "Acme", ["director"])
    assert len(jobs) == 1 and jobs[0]["needs_detail"] and normalize_age(jobs[0]) == 3
    workday.hydrate(c, route, jobs[0])
    assert jobs[0]["pay_max"] == 240000 and jobs[0]["work_mode"] == "hybrid" and not jobs[0]["needs_detail"]


def normalize_age(p):
    return freshness.age_days(p, datetime.now(timezone.utc))


def test_careers_page_reads_json_ld():
    html = '<script type="application/ld+json">{"@type":"JobPosting","title":"Director, Data","datePosted":"2026-11-10",' \
           '"description":"<p>Lead.</p>","jobLocation":{"address":{"addressLocality":"Lake Forest","addressRegion":"IL"}},' \
           '"validThrough":"2099-01-01","baseSalary":{"currency":"USD","value":{"minValue":200000,"maxValue":240000,"unitText":"YEAR"}}}</script>'
    c = make_client(lambda req: httpx.Response(200, text=html))
    out = careers_page.list_jobs(c, {"careers_url": "https://acme.test/careers"}, "Acme", [])
    assert out[0]["title"] == "Director, Data" and out[0]["locations"] == ["Lake Forest, IL"] and out[0]["pay_max"] == 240000


# -- discovery -------------------------------------------------------------------------------------

@pytest.mark.parametrize("url,expect", [
    ("https://boards.greenhouse.io/acme", {"ats": "greenhouse", "token": "acme"}),
    ("https://jobs.lever.co/acme/123", {"ats": "lever", "token": "acme"}),
    ("https://jobs.ashbyhq.com/acme", {"ats": "ashby", "token": "acme"}),
    ("https://abbvie.wd1.myworkdayjobs.com/en-US/AbbVie_Careers", {"ats": "workday", "host": "abbvie.wd1.myworkdayjobs.com", "tenant": "abbvie", "site": "AbbVie_Careers"}),
    ("https://careers.smartrecruiters.com/Acme", {"ats": "smartrecruiters", "token": "Acme"}),
])
def test_fingerprint(url, expect):
    assert discovery.fingerprint(url) == expect


def test_slug_variants_and_probe_requires_a_name_match():
    assert discovery.slug_variants("Acme Therapeutics, Inc.")[0] == "acmetherapeutics"

    def handler(req):
        if "greenhouse" in req.url.host:
            return httpx.Response(200, json={"name": "Totally Different Co"})
        return httpx.Response(404)

    assert discovery.probe(make_client(handler), "Acme Therapeutics") is None
    ok = discovery.probe(make_client(lambda r: httpx.Response(200, json={"name": "Acme Therapeutics"}) if "greenhouse" in r.url.host else httpx.Response(404)), "Acme Therapeutics")
    assert ok and ok[0]["ats"] == "greenhouse"


def test_route_book_roundtrip(tmp_path):
    book = RouteBook(tmp_path / "r.json")
    book.set("Acme Inc", {"ats": "lever", "token": "acme"}, method="probe", job_count=3)
    book.save()
    assert RouteBook(tmp_path / "r.json").usable("Acme")["ats"] == "lever"


# -- crosswalk -------------------------------------------------------------------------------------

def test_crosswalk_prefers_the_careers_page_record():
    careers = posting(title="Director, AI Platform", locations=["Chicago, IL"])
    hit = normalize.new_posting(source="linkedin", company="Acme", title="Director AI Platform", locations=["Chicago, Illinois"],
                                url="https://linkedin.com/jobs/view/1", aggregator_only=True)
    other = normalize.new_posting(source="indeed", company="Acme", title="Chief Cat Herder", locations=["Chicago, IL"],
                                  url="https://indeed.com/viewjob?jk=2", aggregator_only=True)
    matched, leads = crosswalk.crosswalk([hit, other], {"acme": [careers]})
    assert matched[0]["also_listed_on"] == ["linkedin"] and leads == [other]


# -- scoring -----------------------------------------------------------------------------------------

def cand_with_facts():
    return SimpleNamespace(
        tier="full", has_evidence=True, fact_bank={"F001": {"id": "F001", "text": "Led MMM"}}, source_text="Led marketing mix modeling.",
        profile_skills={"tools": [], "skills": []}, skills=["MMM"], tags=[], titles=[], employers=[],
        summary=lambda: "candidate")


def test_finalize_drops_invented_quotes_and_fact_ids_and_clamps():
    p = posting(description_text="We need deep marketing mix modeling experience and executive presence. " * 8)
    data = {"skills": {"score": 99, "quotes": ["deep marketing mix modeling experience", "made up quote that is not present"], "evidence": ["F001", "F999"]},
            "leadership": {"score": 10, "quotes": [], "evidence": []}, "domain": {"score": 5, "quotes": ["executive presence"], "evidence": []},
            "seniority_realism": {"score": 8, "quotes": ["executive presence"], "evidence": []}, "gaps": ["a", "b", "c", "d"]}
    out = score.finalize(p, data, cand_with_facts(), prefs(), [], NOW)
    subs = out["fit"]["subscores"]
    assert subs["skills"]["score"] == 25 and subs["skills"]["quotes"] == ["deep marketing mix modeling experience"]
    assert subs["skills"]["evidence"] == ["F001"]
    assert subs["leadership"]["score"] == 3  # no quote: treated as barely supported (15 // 4)
    assert len(out["fit"]["gaps"]) == 3 and out["fit"]["total"] <= 100


def test_fresh_outranks_late_at_equal_fit():
    c = cand_with_facts()
    a = score.finalize(posting(posted_at=iso(2)), {}, c, prefs(), [], NOW)
    b = score.finalize(posting(posted_at=iso(28)), {}, c, prefs(), [], NOW)
    assert a["fit"]["total"] > b["fit"]["total"]


def test_no_evidence_tier_is_a_preference_match():
    c = SimpleNamespace(tier="quick", has_evidence=False, fact_bank=None, source_text="", profile_skills={}, skills=[], tags=[],
                        titles=[], employers=[], summary=lambda: "prefs")
    p = score.finalize(posting(), {"skills": {"score": 20, "quotes": ["Lead the AI team."], "evidence": ["F001"]}}, c, prefs(), [], NOW)
    assert p["fit"]["kind"] == "preference_match" and p["fit"]["subscores"]["skills"]["evidence"] == []


# -- a whole run ------------------------------------------------------------------------------------

def stub_ask(system, user, **kw):
    if "Task: SCORE" in system:
        ids = [line.split("id=")[1].split(" ")[0] for line in user.splitlines() if line.startswith("=== POSTING")]
        return {"postings": [{"id": i, "skills": {"score": 20, "quotes": ["Lead the AI team."], "evidence": []},
                              "leadership": {"score": 10, "quotes": ["Lead the AI team."], "evidence": []},
                              "domain": {"score": 6, "quotes": ["Lead the AI team."], "evidence": []},
                              "seniority_realism": {"score": 10, "quotes": ["Lead the AI team."], "evidence": []},
                              "gaps": ["Pharma launch experience"], "angle": "", "verdict": "Reasonable match."} for i in ids]}
    if "Task: SWEEP" in system:
        return {"hits": [{"title": "Director, AI", "company": "Acme", "location": "Chicago, IL", "url": "https://www.linkedin.com/jobs/view/99",
                          "posted_hint": "2 days ago"}]}
    if "Task: DISCOVER" in system:
        return {"companies": []}
    return {"companies": [{"name": "Globex", "cluster": "industry", "rationale": "Same industry as your last employer."}]}


def test_full_run_never_returns_a_failing_posting_and_ranks_fresh_first(tmp_path, monkeypatch, workspace):
    monkeypatch.setattr(claude_mod, "ask", stub_ask)
    gh = {"jobs": [
        {"id": 1, "title": "Director, AI", "location": {"name": "Chicago, IL"}, "first_published": iso(2), "absolute_url": "https://b/1",
         "content": "Lead the AI team. " * 30},
        {"id": 2, "title": "Director, Data", "location": {"name": "Chicago, IL"}, "first_published": iso(12), "absolute_url": "https://b/2",
         "content": "Lead the AI team. " * 30},
        {"id": 3, "title": "Data Analyst", "location": {"name": "Chicago, IL"}, "first_published": iso(1), "absolute_url": "https://b/3",
         "content": "Analyze things. " * 30},
        {"id": 4, "title": "Director, Ops", "location": {"name": "Houston, TX"}, "first_published": iso(1), "absolute_url": "https://b/4",
         "content": "Lead the AI team. " * 30},
    ]}

    def handler(req):
        if "greenhouse" in req.url.host and req.url.path.endswith("/jobs"):
            return httpx.Response(200, json=gh)
        if "greenhouse" in req.url.host:
            return httpx.Response(200, json={"id": 1})
        return httpx.Response(404)

    routes = tmp_path / "routes.json"
    book = RouteBook(routes)
    book.set("Acme", {"ats": "greenhouse", "token": "acme"}, method="manual", job_count=4)
    book.save()
    (tmp_path / "targets.json").write_text(json.dumps([{"name": "Acme"}]), encoding="utf-8")
    (tmp_path / "prefs.json").write_text(json.dumps(
        {"titles": ["Director"], "home_location": "Chicago, IL", "radius_miles": 30, "sources": ["targets", "ideated", "boards"], "depth": "quick"}), encoding="utf-8")
    args = SimpleNamespace(prefs=str(tmp_path / "prefs.json"), targets=str(tmp_path / "targets.json"), routes=str(routes), store=None,
                           cache_dir=None, profile=str(workspace.latest("in_profile")), resume=str(workspace.latest("in_resume")),
                           fact_bank=str(workspace.fact_bank_path), count=3, depth="quick", sources=None, recency=14, model=None, effort=None)
    report = run.run_search(args, client=make_client(handler))

    titles = [p["title"] for p in report["results"]]
    assert "Data Analyst" not in titles and all("Houston" not in " ".join(p["locations"]) for p in report["results"])
    assert titles[0] == "Director, AI"  # fresher at equal fit
    assert {r["reason"] for r in report["rejected"]} >= {"level", "location"}
    assert report["tier"] == "full" and all(p["verified"] in ("live", "unconfirmed") for p in report["results"])
    assert any(c["company"] == "Acme" and c["status"] == "ok" for c in report["coverage"])
    li = [p for p in report["results"] + report["more"] if "linkedin" in p.get("also_listed_on", [])]
    assert li  # the LinkedIn lead was traced back to the careers-page posting


def test_non_relocator_keeps_home_area_and_remote_us_only():
    pf = prefs(relocation="no", home_location="Kenosha, WI", anchor_cities=["Milwaukee, WI", "Chicago, IL"], radius_miles=60)
    for city in ["Milwaukee, WI", "Kenosha, WI", "Racine, WI", "Evanston, IL", "Naperville, IL", "Waukesha, WI"]:
        assert filters.apply_filters(posting(locations=[city]), pf, NOW).ok, city
    for city in ["Austin, TX", "Toronto, Canada", "London, United Kingdom", "Madison, WI"]:
        assert filters.apply_filters(posting(locations=[city]), pf, NOW).reason == "location", city
    assert filters.apply_filters(posting(locations=["Remote - US"], work_mode="remote"), pf, NOW).ok
    assert filters.apply_filters(posting(locations=["Remote - Canada"], work_mode="remote"), pf, NOW).reason == "location"
    hybrid_tx = posting(locations=["Dallas, TX"], work_mode="hybrid")
    assert filters.apply_filters(hybrid_tx, pf, NOW).reason == "location"


def test_non_relocator_enforced_even_with_radius_zero_and_relocator_unchanged():
    far = posting(locations=["Houston, TX"])
    assert filters.apply_filters(far, prefs(relocation="no", home_location="Kenosha, WI"), NOW).reason == "location"
    assert filters.apply_filters(far, prefs(home_location="Kenosha, WI"), NOW).ok

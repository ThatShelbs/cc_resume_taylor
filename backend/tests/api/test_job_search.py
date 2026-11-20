"""Job search API: targets, suggestion and search jobs (fake engine scripts), the postings
lifecycle, tailoring from a posting, and the unified board."""

import textwrap
import time

import httpx
import pytest

from resume_taylor.api.routers import job_search as js_router
from resume_taylor.api.storage.paths import Paths
from resume_taylor.search.http import Client
from support import make_client

POSTING_ID = "abc123def456"
DESCRIPTION = "Lead the AI platform team and own the roadmap. " * 12

FAKE_SEARCH = textwrap.dedent("""\
    import json, sys, time
    from pathlib import Path
    args = sys.argv[1:]
    get = lambda flag: args[args.index(flag) + 1] if flag in args else None
    for s in ("ideating", "discovering", "sweeping", "scoring", "verifying", "ranking"):
        print(f"::stage {s}", flush=True)
    marker = Path(__file__).with_name("sleep.txt")
    time.sleep(float(marker.read_text()) if marker.exists() else 0)
    posting = lambda pid, title, total: {
        "id": pid, "title": title, "company": "Acme", "locations": ["Chicago, IL"], "work_mode": "hybrid",
        "url": "https://boards.greenhouse.io/acme/jobs/" + pid, "apply_url": "https://boards.greenhouse.io/acme/jobs/" + pid,
        "ats": "greenhouse", "external_id": pid, "route": {"ats": "greenhouse", "token": "acme"}, "pay_text": "$200,000 - $240,000",
        "posted_at": "2026-11-14T00:00:00+00:00", "also_listed_on": [], "aggregator_only": False, "verified": "live",
        "fit": {"total": total, "kind": "evidence", "subscores": {}, "gaps": ["Pharma launches"], "angle": "", "verdict": "ok"},
        "description_text": DESCRIPTION, "first_seen": "2026-11-15T00:00:00",
    }
    report = {"started": "x", "count": int(get("--count")), "depth": get("--depth"), "tier": "full", "results": [
        posting("abc123def456", "Director, AI", 88), posting("fedcba654321", "Head of Data", 71)],
        "more": [], "rejected": [{"id": "r1", "title": "Analyst", "company": "Acme", "reason": "level", "evidence": "x", "url": ""}],
        "coverage": [{"company": "Acme", "status": "ok", "count": 2}], "notes": [], "timings": {"total": 1.0}}
    Path(get("--out")).write_text(json.dumps(report))
    print("::stage done", flush=True)
    """).replace("DESCRIPTION", repr(DESCRIPTION))

FAKE_SUGGEST = textwrap.dedent("""\
    import json, sys
    from pathlib import Path
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1])
    skip = json.loads(Path(args[args.index("--exclude") + 1]).read_text())
    cos = [{"name": n, "cluster": "industry", "rationale": "Same industry.", "careers_url": ""} for n in ("Globex", "Initech", "Acme")]
    out.write_text(json.dumps({"tier": "full", "companies": [c for c in cos if c["name"] not in skip]}))
    """)


@pytest.fixture
def js(client, tmp_path, monkeypatch):
    search = tmp_path / "fake_search.py"
    search.write_text(FAKE_SEARCH, encoding="utf-8")
    suggest = tmp_path / "fake_suggest.py"
    suggest.write_text(FAKE_SUGGEST, encoding="utf-8")
    monkeypatch.setattr(Paths, "search_command", property(lambda self: [str(search)]))
    monkeypatch.setattr(Paths, "search_suggest_command", property(lambda self: [str(suggest)]))
    return client


def wait(client, job_id, timeout=20):
    end = time.time() + timeout
    while client.get(f"/api/jobs/{job_id}").json()["status"] not in ("succeeded", "failed", "cancelled") and time.time() < end:
        time.sleep(0.05)
    return client.get(f"/api/jobs/{job_id}").json()


def run_search(client, **body):
    job = client.post("/api/job-search/search", json={"count": 3, **body})
    assert job.status_code == 200, job.text
    done = wait(client, job.json()["id"])
    assert done["status"] == "succeeded", done
    return done


def mock_http(monkeypatch, handler=None):
    handler = handler or (lambda req: httpx.Response(200, json={"id": 1}))
    monkeypatch.setattr(js_router, "make_client", lambda: Client(transport=httpx.MockTransport(handler), sleep=lambda s: None))


def test_readiness_tiers(js, tmp_path):
    assert js.get("/api/job-search/readiness").json()["tier"] == "full"
    empty = make_client(Paths(tmp_path / "empty"))
    r = empty.get("/api/job-search/readiness").json()
    assert r["tier"] == "quick" and not r["has_resume"]


def test_targets_import_limit_and_duplicates(js):
    r = js.post("/api/job-search/targets/import", json={"text": "Acme Inc, https://boards.greenhouse.io/acme\nGlobex\nacme"}).json()
    assert r["added"] == ["Acme Inc", "Globex"] and r["skipped"] == ["acme"]
    many = "\n".join(f"Company {i}" for i in range(120))
    r = js.post("/api/job-search/targets/import", json={"text": many}).json()
    assert r["total"] == 100 and len(r["over_limit"]) == 22
    targets = js.get("/api/job-search/targets").json()["targets"]
    assert len(targets) == 100 and targets[0]["careers_url"].startswith("https://boards.greenhouse.io")
    assert js.post("/api/job-search/targets/suggest", json={"count": 10}).status_code == 409  # list is full


def test_suggest_then_accept(js):
    js.post("/api/job-search/targets/import", json={"text": "Acme"})
    job = js.post("/api/job-search/targets/suggest", json={"count": 5}).json()
    assert wait(js, job["id"])["status"] == "succeeded"
    latest = js.get("/api/job-search/targets/suggestions/latest").json()
    assert [c["name"] for c in latest["companies"]] == ["Globex", "Initech"]  # Acme was already a target
    r = js.post("/api/job-search/targets/suggestions/accept", json={"names": ["Globex"]}).json()
    assert r["added"] == ["Globex"]
    assert [c["name"] for c in js.get("/api/job-search/targets/suggestions/latest").json()["companies"]] == ["Initech"]


def test_search_job_merges_postings_and_keeps_user_choices(js):
    done = run_search(js)
    assert done["result"]["found"] == 2
    posts = js.get("/api/job-search/postings").json()
    assert [p["title"] for p in posts] == ["Director, AI", "Head of Data"] and posts[0]["is_new"] and posts[0]["freshness"]
    assert js.get(f"/api/job-search/postings/{POSTING_ID}").json()["description_text"].startswith("Lead the AI platform")
    js.patch(f"/api/job-search/postings/{POSTING_ID}", json={"stage": "interested"})
    run_search(js)  # the same posting is found again
    again = js.get(f"/api/job-search/postings/{POSTING_ID}").json()
    assert again["stage"] == "interested" and not again["is_new"]
    run = js.get(f"/api/job-search/runs/{done['result']['run_id']}").json()
    assert run["rejected"][0]["reason"] == "level" and "description_text" not in run["results"][0]
    assert js.get("/api/job-search/runs").json()[0]["found"] == 2


def test_bad_stage_and_unknown_posting(js):
    run_search(js)
    assert js.patch(f"/api/job-search/postings/{POSTING_ID}", json={"stage": "nonsense"}).status_code == 400
    assert js.get("/api/job-search/postings/ffffffffffff").status_code == 404


def test_search_validates_count_and_a_second_search_is_refused(js, tmp_path):
    assert js.post("/api/job-search/search", json={"count": 7}).status_code == 400
    (tmp_path / "sleep.txt").write_text("1.5")
    first = js.post("/api/job-search/search", json={"count": 3})
    assert first.status_code == 200
    second = js.post("/api/job-search/search", json={"count": 3})
    assert second.status_code == 409 and "already running" in second.json()["detail"]
    assert wait(js, first.json()["id"])["status"] == "succeeded"


def test_search_lane_does_not_block_generation(js, tmp_path):
    from support import JOB_TEXT
    (tmp_path / "sleep.txt").write_text("2")
    pid = js.post("/api/projects", json={"job_text": JOB_TEXT, "role": "Director"}).json()["project"]["id"]
    first = js.post("/api/job-search/search", json={"count": 3}).json()
    gen = js.post(f"/api/projects/{pid}/generate").json()
    assert wait(js, gen["id"])["status"] == "succeeded"
    assert js.get(f"/api/jobs/{first['id']}").json()["status"] in ("running", "queued")  # generation finished first
    assert wait(js, first["id"])["status"] == "succeeded"


def test_tailor_creates_a_linked_project_with_the_posting_text(js, monkeypatch):
    mock_http(monkeypatch)
    run_search(js)
    r = js.post(f"/api/job-search/postings/{POSTING_ID}/tailor", json={"generate": True})
    assert r.status_code == 200, r.text
    project = r.json()["project"]
    assert project["posting_id"] == POSTING_ID and project["role"] == "Director, AI" and project["url"].endswith(POSTING_ID)
    assert wait(js, r.json()["job"]["id"])["status"] == "succeeded"
    text = js.get(f"/api/projects/{project['id']}").json()["job_text"]
    assert "Lead the AI platform team" in text and "Acme" in text
    post = js.get(f"/api/job-search/postings/{POSTING_ID}").json()
    assert post["project_id"] == project["id"] and post["stage"] == "interested"
    assert js.post(f"/api/job-search/postings/{POSTING_ID}/tailor", json={}).status_code == 409  # already started


def test_tailor_refuses_a_closed_posting(js, monkeypatch):
    mock_http(monkeypatch, lambda req: httpx.Response(404))
    run_search(js)
    r = js.post(f"/api/job-search/postings/{POSTING_ID}/tailor", json={"generate": False})
    assert r.status_code == 409 and "no longer live" in r.json()["detail"]


def test_tailor_needs_a_resume_in_the_quick_tier(tmp_path, monkeypatch):
    empty = make_client(Paths(tmp_path / "empty"))
    store = js_router.JobSearchStore(empty.app.state.ctx.paths.job_search_dir)
    store.add_posting({"id": POSTING_ID, "title": "Director", "company": "Acme", "description_text": DESCRIPTION, "route": {}, "url": "u"})
    mock_http(monkeypatch)
    r = empty.post(f"/api/job-search/postings/{POSTING_ID}/tailor", json={})
    assert r.status_code == 409 and "profile" in r.json()["detail"].lower()


def test_board_merges_postings_and_projects(js, monkeypatch):
    mock_http(monkeypatch)
    run_search(js)
    js.patch("/api/job-search/postings/fedcba654321", json={"stage": "dismissed", "dismiss_reason": "pay"})
    r = js.post(f"/api/job-search/postings/{POSTING_ID}/tailor", json={"generate": False}).json()
    pid = r["project"]["id"]
    cols = {c["id"]: c["column"] for c in js.get("/api/job-search/pipeline").json()["cards"]}
    assert cols[pid] == "tailoring" and cols["fedcba654321"] == "closed" and POSTING_ID not in cols  # the project stands in for its posting
    js.patch(f"/api/projects/{pid}", json={"outcome_stage": 1})
    assert {c["id"]: c["column"] for c in js.get("/api/job-search/pipeline").json()["cards"]}[pid] == "applied"
    js.patch(f"/api/projects/{pid}", json={"outcome_stage": 3})
    card = next(c for c in js.get("/api/job-search/pipeline").json()["cards"] if c["id"] == pid)
    assert card["column"] == "interviewing" and card["fit"] == 88 and card["posting_id"] == POSTING_ID


def test_import_url_reads_json_ld_and_blocks_job_boards(js, monkeypatch):
    page = ('<script type="application/ld+json">{"@type":"JobPosting","title":"Director, Data","datePosted":"2026-11-10",'
            '"description":"<p>' + "Lead the data team. " * 10 + '</p>","hiringOrganization":{"name":"Initech"}}</script>')
    mock_http(monkeypatch, lambda req: httpx.Response(200, text=page))
    r = js.post("/api/job-search/postings/import-url", json={"url": "https://careers.initech.test/jobs/1"})
    assert r.status_code == 200 and r.json()["company"] == "Initech" and r.json()["stage"] == "interested"
    blocked = js.post("/api/job-search/postings/import-url", json={"url": "https://www.indeed.com/viewjob?jk=1"})
    assert blocked.status_code == 422 and "company's own careers page" in blocked.json()["detail"]


def test_preferences_roundtrip_normalizes(js):
    body = {"titles": ["Director"], "count": 9, "depth": "weird", "remote_states": ["il "], "base_floor": 225000}
    saved = js.put("/api/job-search/preferences", json=body).json()
    assert saved["count"] == 5 and saved["depth"] == "standard" and saved["remote_states"] == ["IL"]
    assert js.get("/api/job-search/preferences").json()["base_floor"] == 225000


def test_google_jobs_and_serpapi_are_gone(js):
    assert js.get("/api/settings/serpapi-key").status_code in (404, 405)
    ready = js.get("/api/job-search/readiness").json()
    assert "serpapi" not in ready
    assert not {"google", "google_account"} & set(ready["options"]["sources"])
    assert [a["site"] for a in ready["accounts"]] == ["linkedin", "indeed", "ziprecruiter"]
    assert {"roberthalf", "ziprecruiter_account"} <= set(ready["options"]["sources"])


def test_retired_google_profile_is_cleaned_up(js):
    jsdir = js.app.state.ctx.paths.job_search_dir
    (jsdir / "browser_profile" / "google").mkdir(parents=True)
    (jsdir / "accounts.json").write_text('{"google": {"connected_at": "2026-11-01T00:00:00+00:00"}}')
    accounts = js.get("/api/job-search/accounts").json()["accounts"]
    assert "google" not in {a["site"] for a in accounts}
    assert not (jsdir / "browser_profile" / "google").exists()
    assert "google" not in (jsdir / "accounts.json").read_text()


def test_search_timeout_grows_with_signed_in_sites(js, monkeypatch):
    from resume_taylor.api.routers import job_search as jsr

    seen = {}

    def fake_submit(ctx, kind, label, args, timeout, on_success=None):
        seen["timeout"] = timeout
        return {"id": "x"}

    monkeypatch.setattr(jsr, "_submit_search_job", fake_submit)
    r = js.post("/api/job-search/search", json={"count": 5, "depth": "quick", "sources": ["boards", "linkedin_account", "ziprecruiter_account"]})
    assert r.status_code == 200, r.text
    assert seen["timeout"] == jsr.DEPTH_TIMEOUT["quick"] + 2 * jsr.ACCOUNT_SITE_TIMEOUT


FAKE_DRAFT = textwrap.dedent("""\
    import json, sys
    from pathlib import Path
    args = sys.argv[1:]
    Path(args[args.index("--out") + 1]).write_text(json.dumps({
        "titles": ["Director, AI"], "title_keywords": ["machine learning"], "skill_terms": ["Python"],
        "industries": ["Pharma"], "min_level": "senior_manager"}))
    """)


def test_first_run_flag_and_draft_merge_into_empty_fields_only(js, tmp_path, monkeypatch):
    draft = tmp_path / "fake_draft.py"
    draft.write_text(FAKE_DRAFT, encoding="utf-8")
    monkeypatch.setattr(Paths, "search_draft_command", property(lambda self: [str(draft)]))
    assert js.get("/api/job-search/readiness").json()["first_run"] is True
    js.put("/api/job-search/preferences", json={"titles": ["Head of Data"]})
    done = wait(js, js.post("/api/job-search/preferences/draft").json()["id"])
    assert done["status"] == "succeeded", done
    prefs = js.get("/api/job-search/preferences").json()
    assert prefs["titles"] == ["Head of Data"]  # typed value kept
    assert prefs["title_keywords"] == ["machine learning"] and prefs["min_level"] == "senior_manager"
    assert js.get("/api/job-search/readiness").json()["first_run"] is False


def test_tailor_passes_the_search_insights_to_the_pipeline(js, monkeypatch):
    mock_http(monkeypatch)
    run_search(js)
    r = js.post(f"/api/job-search/postings/{POSTING_ID}/tailor", json={"generate": False})
    assert r.status_code == 200, r.text
    ctx = js.app.state.ctx
    hints = ctx.store.dir(r.json()["project"]["id"]) / "posting_insights.txt"
    assert hints.exists() and "Pharma launches" in hints.read_text(encoding="utf-8")
    from resume_taylor.api.services.pipeline_runner import pipeline_command
    cmd = pipeline_command(ctx.paths, job_text=hints, out_dir=hints.parent, result_json=hints.parent / "r.json", template="classic",
                           posting_insights=hints)
    assert "--posting-insights" in cmd

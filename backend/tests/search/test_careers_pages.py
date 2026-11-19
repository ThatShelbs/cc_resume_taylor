"""Company careers pages: finding the ATS behind them (plain HTML, a 'Search jobs' link, a JavaScript
page), reading postings from real on-page links, robots.txt, and keeping the careers-page link on
every route and posting. Offline: a mock HTTP transport and a fake headless renderer."""

import json

import httpx

from resume_taylor.search import claude as claude_mod
from resume_taylor.search import discovery
from resume_taylor.search import render as rendering
from resume_taylor.search.connectors import careers_page
from resume_taylor.search.http import Client
from resume_taylor.search.routes import RouteBook, board_url, careers_link, is_company_page

PFIZER = ('<html><a href="https://pfizer.wd1.myworkdayjobs.com/PfizerCareers/page/61cd8c398601100158e598894f100000">'
          'Join Our Talent Community</a><a href="https://www.linkedin.com/company/pfizer/jobs">LinkedIn</a></html>')
GREENHOUSE_BOARD = {"name": "Initech", "jobs": []}


def client_for(pages: dict, robots: str = ""):
    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=robots) if robots else httpx.Response(404)
        key = f"{req.url.host}{req.url.path}" + (f"?{req.url.query.decode()}" if req.url.query else "")
        body = pages.get(key, pages.get(f"{req.url.host}{req.url.path}"))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, text=body if isinstance(body, str) else json.dumps(body))
    return Client(cache_dir=None, transport=httpx.MockTransport(handler), sleep=lambda s: None)


def test_pfizer_style_careers_page_resolves_to_its_workday_board():
    c = client_for({"www.pfizer.com/about/careers": PFIZER})
    route = discovery.fingerprint_careers_page(c, "https://www.pfizer.com/about/careers")
    assert route == {"ats": "workday", "host": "pfizer.wd1.myworkdayjobs.com", "tenant": "pfizer", "site": "PfizerCareers"}
    assert board_url(route) == "https://pfizer.wd1.myworkdayjobs.com/PfizerCareers"


def test_search_jobs_link_is_followed_one_hop():
    c = client_for({
        "www.initech.test/careers": '<a href="https://jobs.initech.test/open-roles">Search jobs</a>',
        "jobs.initech.test/open-roles": '<iframe src="https://boards.greenhouse.io/embed/job_board?for=initech"></iframe>',
    })
    assert discovery.fingerprint_careers_page(c, "https://www.initech.test/careers") == {"ats": "greenhouse", "token": "initech"}


def test_javascript_careers_page_is_rendered_once(monkeypatch):
    calls = []

    def fake_render(url, timeout_ms=30000):
        calls.append(url)
        return rendering.Rendered(url=url, html="<div id=app></div>", text="Open roles",
                                  anchors=[("https://jobs.lever.co/initech/123", "Director, Ops")], frames=[])

    monkeypatch.setattr(rendering, "render", fake_render)
    c = client_for({"www.initech.test/careers": "<div id=app></div><script src=app.js></script>"})
    assert discovery.fingerprint_careers_page(c, "https://www.initech.test/careers") == {"ats": "lever", "token": "initech"}
    assert calls == ["https://www.initech.test/careers"]


def test_robots_txt_blocks_reading_a_careers_page(monkeypatch):
    monkeypatch.setattr(rendering, "render", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not render")))
    c = client_for({"www.initech.test/careers": PFIZER}, robots="User-agent: *\nDisallow: /careers")
    assert discovery.fingerprint_careers_page(c, "https://www.initech.test/careers") is None


SEARCH_PAGE = """<base href="https://careers.initech.test/applications/">
<a href="jobs/results/1234567-director-of-operations?q=director" aria-label="Learn more about Director of Operations"></a>
<a href="jobs/results/7654321-staff-accountant?q=director">Staff Accountant</a>
<a href="jobs/results?page=2">Next</a><a href="https://www.linkedin.com/jobs/view/999">LinkedIn</a>"""
POSTING_NO_LD = "<html><nav>Menu</nav><h2>Director of Operations</h2><p>Lead operations across three plants. $180,000 - $220,000 a year.</p></html>"
POSTING_LD = ('<script type="application/ld+json">{"@type":"JobPosting","title":"Staff Accountant","datePosted":"2026-11-10",'
              '"description":"<p>Close the books.</p>"}</script>')


def test_search_url_template_reads_postings_from_real_links():
    c = client_for({
        "careers.initech.test/applications/jobs/results?q=director": SEARCH_PAGE,
        "careers.initech.test/applications/jobs/results/1234567-director-of-operations": POSTING_NO_LD,
        "careers.initech.test/applications/jobs/results/7654321-staff-accountant": POSTING_LD,
    })
    route = {"ats": "careers_page", "careers_url": "https://careers.initech.test/applications/",
             "search_url": "https://careers.initech.test/applications/jobs/results?q={q}"}
    jobs = careers_page.list_jobs(c, route, "Initech", ["director"])
    by_title = {p["title"]: p for p in jobs}
    assert list(by_title) == ["Director of Operations", "Staff Accountant"]  # best title match first; no board links
    assert "three plants" in by_title["Director of Operations"]["description_text"]
    assert by_title["Director of Operations"]["pay_max"] == 220000 and not by_title["Director of Operations"]["read_by_claude"]
    assert by_title["Staff Accountant"]["posted_at"] == "2026-11-10"


def test_claude_fallback_keeps_robots_blocked_leads_without_fetching(monkeypatch):
    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: {"jobs": [
        {"url": "https://careers.initech.test/jobs/1234567-director-of-operations", "title": "Director of Operations", "location": "Austin, TX"},
        {"url": "https://www.indeed.com/viewjob?jk=1", "title": "Off-site board", "location": ""},
    ]})
    c = client_for({"careers.initech.test/start": "<p>Nothing here</p>"}, robots="User-agent: *\nDisallow: /jobs/")
    [p] = careers_page.list_jobs(c, {"ats": "careers_page", "careers_url": "https://careers.initech.test/start"}, "Initech", ["director"])
    assert (p["title"], p["locations"], p["read_by_claude"], p["needs_detail"]) == ("Director of Operations", ["Austin, TX"], True, False)
    assert not any("/jobs/1234567" in str(r) for r in c.errors)


def test_routes_keep_careers_page_and_board_link(tmp_path):
    book = RouteBook(tmp_path / "routes.json")
    rec = book.set("Initech", {"ats": "greenhouse", "token": "initech", "careers_url": ""}, method="probe", job_count=3)
    assert rec["board_url"] == "https://job-boards.greenhouse.io/initech" and careers_link(rec) == rec["board_url"]
    rec["careers_url"] = "https://www.initech.test/careers"
    assert careers_link(rec) == "https://www.initech.test/careers"
    assert not is_company_page("https://www.linkedin.com/company/initech/jobs") and is_company_page("https://initech.test/jobs")


def test_careers_page_backfill_asks_once_and_skips_job_boards(tmp_path, monkeypatch):
    asked = []

    def fake_ask(system, user, **k):
        asked.append(user)
        return {"companies": [{"name": "Initech", "careers_url": "https://www.initech.test/careers",
                               "search_url": "https://www.initech.test/careers/search?q={q}", "ats_url": ""},
                              {"name": "Globex", "careers_url": "https://www.linkedin.com/company/globex/jobs"}]}

    monkeypatch.setattr(discovery.claude, "ask", fake_ask)
    c = client_for({"boards-api.greenhouse.io/v1/boards/initech": GREENHOUSE_BOARD, "boards-api.greenhouse.io/v1/boards/initech/jobs": {"jobs": []},
                    "boards-api.greenhouse.io/v1/boards/globex": {"name": "Globex"}, "boards-api.greenhouse.io/v1/boards/globex/jobs": {"jobs": []}})
    book = RouteBook(tmp_path / "routes.json")
    out = discovery.discover_routes(c, book, [{"name": "Initech"}, {"name": "Globex"}], progress=lambda *_: None)
    assert out["Initech"]["careers_url"] == "https://www.initech.test/careers"
    assert out["Initech"]["search_url"] == "https://www.initech.test/careers/search?q={q}"
    assert out["Globex"]["careers_url"] == "" and out["Globex"]["careers_url_checked"]  # a LinkedIn page is never a careers page
    # an empty board is not an answer: the company is asked about once, then saved as "no openings right now"
    assert out["Initech"]["status"] == "empty" and out["Initech"]["ats"] == "greenhouse"
    first_run = len(asked)  # the batch lookup, plus one read of Initech's own careers page before settling for "empty"
    discovery.discover_routes(c, RouteBook(tmp_path / "routes.json"), [{"name": "Initech"}, {"name": "Globex"}], progress=lambda *_: None)
    assert len(asked) == first_run and first_run == 2  # then remembered


def test_search_run_links_every_posting_to_the_company_careers_page(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from resume_taylor.search import run

    monkeypatch.setattr(claude_mod, "ask", lambda *a, **k: None)
    job = {"id": 11, "title": "Director of Operations", "absolute_url": "https://job-boards.greenhouse.io/initech/jobs/11",
           "location": {"name": "Chicago, IL"}, "first_published": "2026-11-15T00:00:00Z", "content": "<p>Lead ops.</p>"}
    c = client_for({"www.initech.test/careers": '<a href="https://boards.greenhouse.io/initech">Jobs</a>',
                    "boards-api.greenhouse.io/v1/boards/initech/jobs": {"jobs": [job]},
                    "boards-api.greenhouse.io/v1/boards/initech/jobs/11": job})
    (tmp_path / "targets.json").write_text(json.dumps([{"name": "Initech", "careers_url": "https://www.initech.test/careers"}]))
    args = SimpleNamespace(prefs=None, targets=str(tmp_path / "targets.json"), routes=str(tmp_path / "routes.json"), store=None,
                           cache_dir=None, profile=None, resume=None, fact_bank=None, count=3, depth="quick", sources="targets",
                           recency=14, model=None, effort=None, accounts_dir=None)
    report = run.run_search(args, client=c, progress=lambda *_: None)
    [cov] = report["coverage"]
    assert cov["careers_url"] == "https://www.initech.test/careers" and cov["ats"] == "greenhouse"
    seen = json.loads((tmp_path / "routes.json").read_text())["initech"]
    assert seen["board_url"] == "https://job-boards.greenhouse.io/initech"
    [p] = [*report["results"], *report["more"]]
    assert p["company_careers_url"] == "https://www.initech.test/careers"


def test_tls_context_verifies_certificates_and_offers_no_alpn():
    """Cloudflare (in front of every Workday board) answers httpx's ALPN 'http/1.1' handshake with 429."""
    import ssl

    from resume_taylor.search.http import tls_context

    ctx = tls_context()
    ctx.set_alpn_protocols(["http/1.1"])  # what httpcore does on every connection: ignored
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname

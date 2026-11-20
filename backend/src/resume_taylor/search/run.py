"""`python -m resume_taylor.search`: one job search run.

target companies + ideated companies  ->  careers-page postings (ATS APIs)
job-board sweep (+ opt-in LinkedIn, your signed-in boards)  ->  leads traced back to careers pages
Robert Half (staffing agency, public pages)  ->  its own postings, marked as agency roles
dedupe -> freshness -> hard filters -> shortlist -> Claude fit scoring -> strict filters
-> live verification -> top N, with every rejection and per-company coverage reported."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from resume_taylor.pipeline.runtime import stage, warn

from . import freshness
from .browser.driver import hydrate_detail, search_site, site_of_source
from .browser.session import BrowserSession, BrowserUnavailable
from .browser.state import LABELS, RUN_BUDGET, SITES, AccountState, new_usage, profile_dir
from .candidate import build_candidate
from .connectors import board_hits, connector_for, roberthalf
from .connectors.careers_page import search_page
from .crosswalk import crosswalk, route_from_links
from .dedupe import dedupe
from .discovery import discover_routes
from .filters import apply_filters
from .http import Client
from .ideation import ideate
from .normalize import norm_company
from .prefs import COUNTS, DEPTHS, Preferences, load_prefs, resolve_min_level
from .relevance import RoleFamily
from .research import research_results
from .routes import RouteBook, careers_link
from .score import cheap_rank, finalize, score_postings
from .sweep import claude_sweep, expand_queries
from .verify import verify_posting

# ideated companies, crosswalk companies, shortlist multiplier
DEPTH = {
    "quick": {"ideated": 0, "cross": 10, "k": 2},
    "standard": {"ideated": 30, "cross": 25, "k": 3},
    "deep": {"ideated": 75, "cross": 50, "k": 4},
}
MAX_SHORTLIST = 80
WIDEN_TO_DAYS = 30


def make_session(site: str, accounts_dir):
    """An open signed-in browser for one site. Tests replace this with a fake."""
    return BrowserSession(profile_dir(accounts_dir, site)).__enter__()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) if path and Path(path).exists() else default
    except (OSError, ValueError):
        return default


def pull_company(client, route: dict, name: str, titles: list[str], origin: str, cluster: str = "",
                 family: RoleFamily | None = None) -> tuple[list[dict], str, int]:
    """(on-role postings, error, how many listed postings were not the wanted role)."""
    conn = connector_for(route)
    if not conn:
        return [], "no connector", 0
    try:
        jobs = conn.list_jobs(client, route, name, titles)
    except (KeyError, ValueError, TypeError) as exc:
        return [], f"{exc.__class__.__name__}: {exc}", 0
    off_role = 0
    if family is not None:
        jobs, off_role = family.split(jobs)
    for p in jobs:
        p["route"], p["origin"], p["ideated_cluster"] = route, origin, cluster
    return jobs, "", off_role


def _coverage_status(route: dict, jobs: list, off_role: int, err: str) -> str:
    """ok: postings found (or listings exist but none are your role); empty: the site works but lists
    nothing; failed: no usable route or an error."""
    if err or route.get("status") not in ("resolved", "empty"):
        return "failed"
    return "ok" if jobs or off_role else "empty"


def _links(route: dict, query: str, prefix: str = "") -> dict:
    """The company's careers page and, when its site has a search URL, that search run for `query`."""
    out = {f"{prefix}careers_url": careers_link(route or {})}
    if (route or {}).get("search_url"):
        out[f"{prefix}search_url"] = search_page(route["search_url"], query)
    return out


def _reject(p: dict, reason: str, evidence: str) -> dict:
    return {"id": p["id"], "title": p["title"], "company": p["company"], "url": p.get("url", ""),
            "reason": reason, "evidence": evidence}


def run_search(args, client: Client | None = None, progress=print) -> dict:
    t0 = time.time()
    prefs: Preferences = load_prefs(args.prefs)
    overrides = {k: v for k, v in (("count", args.count), ("depth", args.depth), ("recency_days", args.recency)) if v}
    if args.sources:
        overrides["sources"] = [s for s in args.sources.split(",") if s]
    prefs = Preferences(**{**prefs.model_dump(), **overrides}).normalized()
    cfg = DEPTH[prefs.depth]
    count = prefs.count
    cand = build_candidate(*(Path(p) if p else None for p in (args.profile, args.resume, args.fact_bank)), prefs)
    prefs = prefs.model_copy(update={"min_level": resolve_min_level(prefs, cand.titles)})
    client = client or Client(cache_dir=args.cache_dir)
    book = RouteBook(args.routes)
    known = _read_json(args.store, {})  # id -> stored posting (for first_seen)
    targets = _read_json(args.targets, []) if "targets" in prefs.sources else []
    titles = prefs.titles or cand.titles[:2] or ["director"]
    family = RoleFamily.from_prefs(prefs, cand)
    queries = family.search_terms() or titles  # short role keywords for servers that search
    off_role_total = 0
    timings: dict[str, float] = {}
    report: dict = {
        "started": _now().isoformat(timespec="seconds"), "count": count, "depth": prefs.depth, "sources": prefs.sources,
        "tier": cand.tier, "min_level": prefs.min_level, "coverage": [], "rejected": [], "ideated": [], "source_counts": {}, "notes": [],
    }

    # -- companies: your list plus ideated ones ------------------------------------------------
    stage("ideating")
    companies = [{"name": t["name"], "careers_url": t.get("careers_url", ""), "origin": "target", "cluster": t.get("cluster", "")}
                 for t in targets if t.get("name")]
    if "ideated" in prefs.sources and cfg["ideated"]:
        t = time.time()
        progress(f"Thinking of {cfg['ideated']} more companies to look at...")
        passed_on = [p["company"] for p in known.values() if p.get("stage") == "dismissed" and p.get("dismiss_reason") == "company"]
        ideas = ideate(cand, cfg["ideated"], exclude=[*(c["name"] for c in companies), *passed_on],
                       model=args.model, effort=args.effort)
        report["ideated"] = ideas
        companies += [{"name": i["name"], "careers_url": i.get("careers_url", ""), "origin": "ideated", "cluster": i["cluster"]} for i in ideas]
        timings["ideating"] = round(time.time() - t, 1)

    # -- careers pages -------------------------------------------------------------------------
    stage("discovering")
    t = time.time()
    routes = discover_routes(client, book, [{"name": c["name"], "careers_url": c["careers_url"]} for c in companies],
                             model=args.model, effort=args.effort, progress=progress) if companies else {}
    pool: list[dict] = []
    pools: dict[str, list[dict]] = {}

    def pull(c):
        route = routes.get(c["name"])
        if not route or route.get("status") not in ("resolved", "empty"):
            return c, [], (route or {}).get("note") or "no careers page found", 0
        jobs, err, off = pull_company(client, route, c["name"], queries, c["origin"], c["cluster"], family)
        return c, jobs, err, off

    with ThreadPoolExecutor(max_workers=6) as ex:
        for c, jobs, err, off in ex.map(pull, companies):
            route = routes.get(c["name"]) or {}
            off_role_total += off
            report["coverage"].append({
                "company": c["name"], "origin": c["origin"], "ats": route.get("ats", ""), "count": len(jobs),
                "off_role": off, "listed": len(jobs) + off,
                "status": _coverage_status(route, jobs, off, err),
                "note": err or (f"{off} listings, none match your role." if off and not jobs else ""),
                **_links(route, titles[0]),
            })
            pool.extend(jobs)
            pools.setdefault(norm_company(c["name"]), []).extend(jobs)
            if jobs:
                progress(f"{c['name']} ({route.get('ats', '')}): {len(jobs)} postings")
    for row in report["coverage"]:
        if not row["note"]:
            book.record_run(row["company"], row["listed"])  # a route that lists nothing is rechecked within a week
    book.save()
    report["source_counts"]["careers_pages"] = len(pool)
    report["source_counts"]["careers_pages_off_role"] = off_role_total
    timings["careers_pages"] = round(time.time() - t, 1)

    # -- job boards ----------------------------------------------------------------------------
    stage("sweeping")
    t = time.time()
    hits: list[dict] = []
    if "boards" in prefs.sources:
        hits += claude_sweep(expand_queries(prefs, cand, prefs.depth), prefs, model=args.model, effort=args.effort, progress=progress)
    if "linkedin" in prefs.sources and prefs.linkedin_direct:
        where = prefs.home_location or "United States"
        for q in expand_queries(prefs, cand, "quick")[:3]:
            got = board_hits.linkedin_search(client, q["q"], where, prefs.recency_days)
            hits += got
            progress(f"LinkedIn: '{q['q']}' gave {len(got)} leads")
    # Robert Half: public staffing-agency postings. They are its own requisitions (client unnamed), so
    # they join the pool directly instead of going through crosswalk.
    agency: list[dict] = []
    if "roberthalf" in prefs.sources:
        seen_rh: set[str] = set()
        for q in expand_queries(prefs, cand, "quick")[:roberthalf.MAX_QUERIES]:
            got = [p for p in roberthalf.search(client, q["q"], q["location"], prefs.recency_days) if p["id"] not in seen_rh]
            seen_rh.update(p["id"] for p in got)
            agency += got
            progress(f"Robert Half: '{q['q']}' in {q['location']} gave {len(got)} postings")
        if agency:
            report["source_counts"]["roberthalf"] = len(agency)
    # signed-in sites: your own accounts, slow and budgeted per run (see search/browser)
    accounts_dir = getattr(args, "accounts_dir", None)
    accounts = AccountState(Path(accounts_dir) / "accounts.json") if accounts_dir else None
    sessions: dict = {}
    usage: dict[str, dict] = {}
    for site in SITES:
        if f"{site}_account" not in prefs.sources:
            continue
        if not accounts or not accounts.can_use(site):
            report["notes"].append(f"{LABELS[site]} (your account) was skipped: not connected, or paused after a bot check.")
            continue
        usage[site] = new_usage()
        try:
            sessions[site] = make_session(site, accounts_dir)
            found, note = search_site(site, sessions[site], accounts, expand_queries(prefs, cand, "quick")[:RUN_BUDGET["search"]],
                                      prefs.recency_days, usage=usage[site], progress=progress, model=args.model, effort=args.effort)
        except BrowserUnavailable as exc:
            report["notes"].append(f"{LABELS[site]} (your account) was skipped: {exc}")
            sessions.pop(site, None)
            continue
        hits += found
        if note:
            report["notes"].append(note)
    hits, off_hits = family.split(hits)  # board leads face the same role gate as career-site postings
    off_role_total += off_hits
    for src in ("linkedin", "indeed", "glassdoor", "web", "ziprecruiter", "builtin"):
        n = sum(1 for h in hits if h["source"] == src)
        if n:
            report["source_counts"][src] = n
    timings["sweeping"] = round(time.time() - t, 1)

    # -- trace leads back to careers pages -----------------------------------------------------
    stage("crosswalking")
    t = time.time()
    matched: list[dict] = []
    leads = hits
    extra: dict[str, dict] = {}
    if hits:
        new_names, seen = [], {norm_company(c["name"]) for c in companies}
        for h in hits:
            key = norm_company(h["company"])
            if key and key not in seen and len(new_names) < cfg["cross"]:
                seen.add(key)
                new_names.append({"name": h["company"], "careers_url": ""})
        extra = discover_routes(client, book, new_names, model=args.model, effort=args.effort, progress=progress) if new_names else {}
        for name, route in extra.items():
            if route.get("status") in ("resolved", "empty"):
                jobs, err, off = pull_company(client, route, name, queries, "board", family=family)
                off_role_total += off
                pools.setdefault(norm_company(name), []).extend(jobs)
                report["coverage"].append({"company": name, "origin": "board", "ats": route.get("ats", ""), "count": len(jobs),
                                           "off_role": off, "listed": len(jobs) + off,
                                           "status": _coverage_status(route, jobs, off, err), "note": err,
                                           **_links(route, titles[0])})
        for h in hits:  # a board hit's apply link may reveal the employer's ATS directly
            key = norm_company(h["company"])
            if key not in pools and (r := route_from_links(h)):
                jobs, _, off = pull_company(client, r, h["company"], queries, "board", family=family)
                off_role_total += off
                pools[key] = jobs
        matched, leads = crosswalk(hits, pools)
        progress(f"Job boards: {len(hits)} leads, {len(matched)} matched to careers pages, {len(leads)} board-only")
        have = {p['id'] for p in pool}
        pool += [m for m in matched if m['id'] not in have]
    report["source_counts"]["board_leads_matched_to_careers_page"] = len(matched)
    report["source_counts"]["board_only_leads"] = len(leads)
    pool += leads + agency
    timings["crosswalking"] = round(time.time() - t, 1)

    # every posting links to its company's own careers page when we know it (board leads included)
    known_routes = {norm_company(n): r for n, r in {**routes, **extra}.items() if careers_link(r)}
    for p in pool:
        if p.get("agency"):
            continue
        route = known_routes.get(norm_company(p["company"])) or p.get("route") or {}
        p.update(_links(route, p["title"], prefix="company_"))

    # -- dedupe, dates, filters ----------------------------------------------------------------
    stage("filtering")
    now = _now()
    pool = dedupe(pool)
    report["postings_seen"] = len(pool)
    report["off_role"] = off_role_total
    report["listed"] = len(pool) + off_role_total
    for p in pool:
        prior = known.get(p["id"]) or {}
        p["first_seen"] = prior.get("first_seen") or now.isoformat(timespec="seconds")
        p["is_new"] = p["id"] not in known
        if not p.get("posted_at"):
            p["posted_at"], p["posted_at_source"] = p["first_seen"], "first_seen"
        freshness.annotate(p, now)
    windows = [prefs.recency_days] + ([WIDEN_TO_DAYS] if prefs.recency_days < WIDEN_TO_DAYS else [])
    results: list[dict] = []
    scored: dict[str, dict] = {}
    rejected: dict[str, dict] = {}
    window_used = windows[0]
    k = min(MAX_SHORTLIST, cfg["k"] * count)

    for window in windows:
        window_used = window
        stage("filtering")
        survivors: list[tuple[dict, list[str]]] = []
        for p in pool:
            if p["id"] in scored or p["id"] in rejected:
                continue
            v = apply_filters(p, prefs, now, window)
            if v.ok:
                survivors.append((p, v.flags))
            else:
                rejected[p["id"]] = _reject(p, v.reason, v.evidence)
        survivors.sort(key=lambda pf: cheap_rank(pf[0], cand, prefs, now), reverse=True)
        shortlist = survivors[:k]
        progress(f"{len(survivors)} postings pass your filters; reading the best {len(shortlist)} closely")

        # fetch full descriptions only for the shortlist, then re-check what descriptions reveal
        to_score: list[tuple[dict, list[str]]] = []
        for p, flags in shortlist:
            conn = connector_for(p.get("route") or {})
            if conn and p.get("needs_detail"):
                conn.hydrate(client, p["route"], p)
            elif p.get("aggregator_only") and not p.get("description_text") and (site := site_of_source(p["source"])) in sessions:
                hydrate_detail(site, sessions[site], accounts, p, usage.get(site))
            elif p.get("aggregator_only") and p["source"] == "linkedin" and prefs.linkedin_direct and not p.get("description_text"):
                board_hits.linkedin_detail(client, p)
            v = apply_filters(p, prefs, now, window)
            if v.ok:
                to_score.append((p, v.flags))
            else:
                rejected[p["id"]] = _reject(p, v.reason, v.evidence)

        stage("scoring")
        data = score_postings([p for p, _ in to_score], cand, model=args.model, effort=args.effort, progress=progress) if to_score else {}
        for p, flags in to_score:
            finalize(p, data.get(p["id"]), cand, prefs, flags, now)
            # Claude may have revealed work mode, remote states, pay or a closing date: strict re-check
            v = apply_filters(p, prefs, now, window)
            if v.ok:
                p["flags"] = list(dict.fromkeys([*p["flags"], *v.flags]))
                scored[p["id"]] = p
            else:
                rejected[p["id"]] = _reject(p, v.reason, v.evidence)

        stage("verifying")
        ranked = sorted((p for p in scored.values() if p["id"] not in {r["id"] for r in results}),
                        key=lambda p: (p["fit"]["total"], -(p.get("age_days") or 999)), reverse=True)
        for p in ranked:
            if len(results) >= count:
                break
            verify_posting(client, p)
            if p["verified"] == "closed":
                rejected[p["id"]] = _reject(p, "closed", "The posting is no longer live at its source.")
                scored.pop(p["id"], None)
                continue
            results.append(p)
            progress(f"Verified: {p['company']}: {p['title']}")
        if len(results) >= count:
            break
        if window != windows[-1]:
            report["notes"].append(f"Only {len(results)} of {count} found in {window} days, so the window was widened to {windows[-1]} days. Older postings carry an aging or late badge.")

    for s in sessions.values():
        if hasattr(s, "close"):
            s.close()
    for site, used in usage.items():
        accounts.record_run(site, used)

    # -- a sourced brief on the companies behind the results -------------------------------------
    if results and prefs.depth != "quick":
        stage("researching")
        t = time.time()
        briefs = research_results(results, cache_dir=Path(args.cache_dir) if args.cache_dir else None, model=args.model,
                                  effort=args.effort, progress=progress)
        report["source_counts"]["company_briefs"] = briefs
        timings["researching"] = round(time.time() - t, 1)

    # -- rank and report -----------------------------------------------------------------------
    stage("ranking")
    results.sort(key=lambda p: (p["fit"]["total"], -(p.get("age_days") or 999)), reverse=True)
    result_ids = {p["id"] for p in results}
    more = sorted((p for p in scored.values() if p["id"] not in result_ids), key=lambda p: p["fit"]["total"], reverse=True)[:30]
    if len(results) < count:
        report["notes"].append(f"Found {len(results)} postings that pass every filter and are live, short of the {count} you asked for. "
                               "Nothing was padded; try more companies, a wider radius or a longer window.")
    careers_only = sum(1 for p in results if not p.get("aggregator_only") and not p.get("agency") and not p.get("also_listed_on"))
    report.update({
        "finished": _now().isoformat(timespec="seconds"), "window_days": window_used,
        "results": results, "more": more, "rejected": list(rejected.values()),
        "careers_only_share": round(careers_only / len(results), 2) if results else 0,
        "timings": {**timings, "total": round(time.time() - t0, 1)}, "http_requests": client.requests,
        "http_errors": client.errors[:20],
    })
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run one job search.")
    ap.add_argument("--prefs")
    ap.add_argument("--targets")
    ap.add_argument("--routes")
    ap.add_argument("--store")
    ap.add_argument("--cache-dir")
    ap.add_argument("--profile")
    ap.add_argument("--resume")
    ap.add_argument("--fact-bank")
    ap.add_argument("--count", type=int, choices=COUNTS)
    ap.add_argument("--depth", choices=DEPTHS)
    ap.add_argument("--sources", help="comma list of: targets,ideated,boards,roberthalf,linkedin,linkedin_account,indeed_account,ziprecruiter_account")
    ap.add_argument("--accounts-dir", help="the job_search data folder holding accounts.json and browser profiles")
    ap.add_argument("--recency", type=int)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model")
    ap.add_argument("--effort")
    args = ap.parse_args(argv)
    stage("preparing")
    report = run_search(args)
    Path(args.out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    stage("done")
    print(f"Done: {len(report['results'])} postings, {len(report['rejected'])} rejected, {report['timings']['total']}s.")
    for note in report["notes"]:
        warn(note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

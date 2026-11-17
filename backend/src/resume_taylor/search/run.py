"""`python -m resume_taylor.search`: one job search run.

target companies + ideated companies  ->  careers-page postings (ATS APIs)
job-board sweep (+ opt-in LinkedIn / Google Jobs)  ->  leads traced back to careers pages
dedupe -> freshness -> hard filters -> shortlist -> Claude fit scoring -> strict filters
-> live verification -> top N, with every rejection and per-company coverage reported."""

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from resume_taylor.pipeline.runtime import stage, warn

from . import freshness
from .browser.driver import hydrate_detail, search_site, site_of_source
from .browser.session import BrowserSession, BrowserUnavailable
from .browser.state import DAILY_CAPS, LABELS, SITES, AccountState, profile_dir
from .candidate import build_candidate
from .connectors import board_hits, connector_for
from .crosswalk import crosswalk, route_from_links
from .dedupe import dedupe
from .discovery import discover_routes
from .filters import apply_filters
from .http import Client
from .ideation import ideate
from .normalize import norm_company
from .prefs import COUNTS, DEPTHS, Preferences, load_prefs
from .routes import RouteBook
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


def pull_company(client, route: dict, name: str, titles: list[str], origin: str, cluster: str = "") -> tuple[list[dict], str]:
    conn = connector_for(route)
    if not conn:
        return [], "no connector"
    try:
        jobs = conn.list_jobs(client, route, name, titles)
    except (KeyError, ValueError, TypeError) as exc:
        return [], f"{exc.__class__.__name__}: {exc}"
    for p in jobs:
        p["route"], p["origin"], p["ideated_cluster"] = route, origin, cluster
    return jobs, ""


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
    client = client or Client(cache_dir=args.cache_dir)
    book = RouteBook(args.routes)
    known = _read_json(args.store, {})  # id -> stored posting (for first_seen)
    targets = _read_json(args.targets, []) if "targets" in prefs.sources else []
    titles = prefs.titles or cand.titles[:2] or ["director"]
    timings: dict[str, float] = {}
    report: dict = {
        "started": _now().isoformat(timespec="seconds"), "count": count, "depth": prefs.depth, "sources": prefs.sources,
        "tier": cand.tier, "coverage": [], "rejected": [], "ideated": [], "source_counts": {}, "notes": [],
    }

    # -- companies: your list plus ideated ones ------------------------------------------------
    stage("ideating")
    companies = [{"name": t["name"], "careers_url": t.get("careers_url", ""), "origin": "target", "cluster": t.get("cluster", "")}
                 for t in targets if t.get("name")]
    if "ideated" in prefs.sources and cfg["ideated"]:
        t = time.time()
        progress(f"Thinking of {cfg['ideated']} more companies to look at...")
        ideas = ideate(cand, cfg["ideated"], exclude=[c["name"] for c in companies],
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
        if not route or route.get("status") != "resolved":
            return c, [], (route or {}).get("note") or "no careers page found"
        jobs, err = pull_company(client, route, c["name"], titles, c["origin"], c["cluster"])
        return c, jobs, err

    with ThreadPoolExecutor(max_workers=6) as ex:
        for c, jobs, err in ex.map(pull, companies):
            route = routes.get(c["name"]) or {}
            report["coverage"].append({
                "company": c["name"], "origin": c["origin"], "ats": route.get("ats", ""), "count": len(jobs),
                "status": "ok" if jobs or (route.get("status") == "resolved" and not err) else "failed", "note": err,
            })
            pool.extend(jobs)
            pools.setdefault(norm_company(c["name"]), []).extend(jobs)
            if jobs:
                progress(f"{c['name']} ({route.get('ats', '')}): {len(jobs)} postings")
    report["source_counts"]["careers_pages"] = len(pool)
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
    serp = os.environ.get("SERPAPI_KEY", "").strip()
    if "google" in prefs.sources:
        if serp:
            for q in expand_queries(prefs, cand, "quick")[:4]:
                hits += board_hits.serpapi_search(client, serp, q["q"], q["location"])
        else:
            report["notes"].append("Google Jobs was skipped because no SerpAPI key is set.")
    # signed-in sites: your own accounts, slow and capped (see search/browser)
    accounts_dir = getattr(args, "accounts_dir", None)
    accounts = AccountState(Path(accounts_dir) / "accounts.json") if accounts_dir else None
    sessions: dict = {}
    for site in SITES:
        if f"{site}_account" not in prefs.sources:
            continue
        if not accounts or not accounts.can_use(site, "search"):
            report["notes"].append(f"{LABELS[site]} (your account) was skipped: not connected, paused, or at today's limit.")
            continue
        try:
            sessions[site] = make_session(site, accounts_dir)
            found, note = search_site(site, sessions[site], accounts, expand_queries(prefs, cand, "quick")[:DAILY_CAPS[site]["search"]],
                                      prefs.recency_days, progress=progress, model=args.model, effort=args.effort)
        except BrowserUnavailable as exc:
            report["notes"].append(f"{LABELS[site]} (your account) was skipped: {exc}")
            sessions.pop(site, None)
            continue
        hits += found
        if note:
            report["notes"].append(note)
    for src in ("linkedin", "indeed", "glassdoor", "google_jobs", "web", "ziprecruiter", "builtin"):
        n = sum(1 for h in hits if h["source"] == src)
        if n:
            report["source_counts"][src] = n
    timings["sweeping"] = round(time.time() - t, 1)

    # -- trace leads back to careers pages -----------------------------------------------------
    stage("crosswalking")
    t = time.time()
    matched: list[dict] = []
    leads = hits
    if hits:
        new_names, seen = [], {norm_company(c["name"]) for c in companies}
        for h in hits:
            key = norm_company(h["company"])
            if key and key not in seen and len(new_names) < cfg["cross"]:
                seen.add(key)
                new_names.append({"name": h["company"], "careers_url": ""})
        extra = discover_routes(client, book, new_names, model=args.model, effort=args.effort, progress=progress) if new_names else {}
        for name, route in extra.items():
            if route.get("status") == "resolved":
                jobs, err = pull_company(client, route, name, titles, "board")
                pools.setdefault(norm_company(name), []).extend(jobs)
                report["coverage"].append({"company": name, "origin": "board", "ats": route.get("ats", ""), "count": len(jobs),
                                           "status": "ok" if jobs else "failed", "note": err})
        for h in hits:  # a Google Jobs apply link may reveal the ATS directly
            key = norm_company(h["company"])
            if key not in pools and (r := route_from_links(h)):
                jobs, _ = pull_company(client, r, h["company"], titles, "board")
                pools[key] = jobs
        matched, leads = crosswalk(hits, pools)
        progress(f"Job boards: {len(hits)} leads, {len(matched)} matched to careers pages, {len(leads)} board-only")
        have = {p['id'] for p in pool}
        pool += [m for m in matched if m['id'] not in have]
    report["source_counts"]["board_leads_matched_to_careers_page"] = len(matched)
    report["source_counts"]["board_only_leads"] = len(leads)
    pool += leads
    timings["crosswalking"] = round(time.time() - t, 1)

    # -- dedupe, dates, filters ----------------------------------------------------------------
    stage("filtering")
    now = _now()
    pool = dedupe(pool)
    report["postings_seen"] = len(pool)
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
                hydrate_detail(site, sessions[site], accounts, p)
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

    # -- rank and report -----------------------------------------------------------------------
    stage("ranking")
    results.sort(key=lambda p: (p["fit"]["total"], -(p.get("age_days") or 999)), reverse=True)
    result_ids = {p["id"] for p in results}
    more = sorted((p for p in scored.values() if p["id"] not in result_ids), key=lambda p: p["fit"]["total"], reverse=True)[:30]
    if len(results) < count:
        report["notes"].append(f"Found {len(results)} postings that pass every filter and are live, short of the {count} you asked for. "
                               "Nothing was padded; try more companies, a wider radius or a longer window.")
    careers_only = sum(1 for p in results if not p.get("aggregator_only") and not p.get("also_listed_on"))
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
    ap.add_argument("--sources", help="comma list of: targets,ideated,boards,linkedin,google,linkedin_account,indeed_account,google_account")
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

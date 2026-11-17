"""Job search: target companies, runs, found postings, and the pipeline board that ties the
whole lifecycle together. The engine itself (resume_taylor.search) runs as subprocess jobs on
their own lane, so a long search never blocks resume generation."""

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException

from resume_taylor.pipeline.parsing import parse_applicant_info, parse_prior_resume, parse_profile_skills
from resume_taylor.search import freshness
from resume_taylor.search.browser.state import LABELS, SITES, AccountState, profile_dir
from resume_taylor.search.candidate import readiness
from resume_taylor.search.http import Client
from resume_taylor.search.ideation import CLUSTERS
from resume_taylor.search.importer import ImportFailed, import_url
from resume_taylor.search.prefs import COUNTS, DEPTHS, SOURCES, Preferences
from resume_taylor.search.verify import verify_posting

from ..context import Ctx
from ..schemas import (
    AcceptSuggestionsBody,
    DiscoverBody,
    ImportUrlBody,
    PostingPatch,
    SearchBody,
    SuggestBody,
    TailorBody,
    TargetPatch,
    TargetsImportBody,
)
from ..services import pipeline_runner
from ..services.jobs import Job
from ..storage import credentials
from ..storage.fs import atomic_write_text, remove_tree
from ..storage.job_search import MAX_TARGETS, JobSearchError, JobSearchStore

router = APIRouter(prefix="/api/job-search", tags=["job-search"])

DEPTH_TIMEOUT = {"quick": 900, "standard": 1800, "deep": 3600}
COLUMNS = ["prospect", "interested", "tailoring", "resume_ready", "applied", "interviewing", "offer", "closed"]


def make_client() -> Client:
    """The HTTP client for in-process checks (verify, import). Tests replace this."""
    return Client()


def store_for(ctx: Ctx) -> JobSearchStore:
    return JobSearchStore(ctx.paths.job_search_dir)


def _bad(exc: Exception) -> HTTPException:
    return HTTPException(400, str(exc))


def _input_args(ctx) -> list[str]:
    args: list[str] = []
    pp, rp = ctx.profile_path(), ctx.resume_path()
    if pp:
        args += ["--profile", str(pp)]
    if rp:
        args += ["--resume", str(rp)]
    if ctx.paths.fact_bank_path.exists():
        args += ["--fact-bank", str(ctx.paths.fact_bank_path)]
    return args


def _tier(ctx) -> str:
    fb = ctx.paths.fact_bank_path
    return readiness(ctx.profile_path(), ctx.resume_path(), fb if fb.exists() else None)


# -- readiness and preferences -----------------------------------------------------------------

@router.get("/readiness")
def get_readiness(ctx: Ctx):
    store = store_for(ctx)
    pp, rp = ctx.profile_path(), ctx.resume_path()
    return {
        "tier": _tier(ctx),
        "has_profile": bool(pp), "has_resume": bool(rp), "has_fact_bank": ctx.paths.fact_bank_path.exists(),
        "targets": len(store.targets()), "max_targets": MAX_TARGETS,
        "new_strong": store.count_new_strong(), "serpapi": credentials.serp_status(ctx.paths.secrets_path),
        "accounts": [_accounts(ctx).status(s) for s in SITES],
        "options": {"counts": list(COUNTS), "depths": list(DEPTHS), "sources": list(SOURCES), "clusters": CLUSTERS},
    }


# -- connected accounts ------------------------------------------------------------------------
# You sign in yourself in a real Chrome window. Only that browser profile is kept (no passwords).

def _accounts(ctx) -> AccountState:
    return AccountState(ctx.paths.job_search_dir / "accounts.json")


@router.get("/accounts")
def get_accounts(ctx: Ctx):
    st = _accounts(ctx)
    return {"accounts": [st.status(s) for s in SITES]}


@router.post("/accounts/{site}/connect")
def connect_account(ctx: Ctx, site: str):
    if site not in SITES:
        raise HTTPException(404, "Unknown site.")
    args = [*ctx.paths.search_login_command, site, "--dir", str(ctx.paths.job_search_dir)]
    return _submit_search_job(ctx, "job_search_login", f"Sign in to {LABELS[site]} in the browser window", args, 720)


@router.post("/accounts/cancel-login")
def cancel_login(ctx: Ctx):
    """Stop a sign-in window that is still waiting (also closes its Chrome window)."""
    stopped = [j.id for j in ctx.jobs.active() if j.kind == "job_search_login" and ctx.jobs.cancel(j.id)]
    return {"cancelled": stopped}


@router.delete("/accounts/{site}")
def disconnect_account(ctx: Ctx, site: str):
    if site not in SITES:
        raise HTTPException(404, "Unknown site.")
    _accounts(ctx).disconnect(site)
    prof = profile_dir(ctx.paths.job_search_dir, site)
    if prof.exists():
        remove_tree(prof)
    return {"ok": True}


@router.get("/preferences")
def get_preferences(ctx: Ctx):
    return store_for(ctx).get_prefs()


@router.put("/preferences")
def put_preferences(ctx: Ctx, body: Preferences):
    return store_for(ctx).save_prefs(body)


@router.post("/preferences/suggest")
def suggest_preferences(ctx: Ctx):
    """Starting values drawn from the profile and resume. Nothing is saved; the form merges them."""
    out: dict = {"titles": [], "skill_terms": [], "home_location": ""}
    pp, rp = ctx.profile_path(), ctx.resume_path()
    try:
        if rp:
            jobs = parse_prior_resume(rp).get("jobs", [])
            out["titles"] = [jobs[0]["title"]] if jobs else []
        if pp:
            sk = parse_profile_skills(pp)
            out["skill_terms"] = [*sk.get("skills", []), *sk.get("tools", [])][:12]
            out["home_location"] = parse_applicant_info(pp).get("location", "") or ""
    except SystemExit:
        pass
    return out


# -- targets -----------------------------------------------------------------------------------

@router.get("/targets")
def get_targets(ctx: Ctx):
    store = store_for(ctx)
    return {"targets": store.targets_with_routes(), "max": MAX_TARGETS}


@router.post("/targets/import")
def import_targets(ctx: Ctx, body: TargetsImportBody):
    store = store_for(ctx)
    items = [t.model_dump() for t in body.items] if body.items else store.parse_import(body.text)
    if not items:
        raise HTTPException(400, "No companies found. Paste one per line, optionally followed by a comma and its careers page.")
    try:
        return store.add_targets(items)
    except JobSearchError as exc:
        raise _bad(exc) from None


@router.patch("/targets/{tid}")
def patch_target(ctx: Ctx, tid: str, body: TargetPatch):
    try:
        return store_for(ctx).update_target(tid, body.model_dump(exclude_unset=True))
    except JobSearchError as exc:
        raise HTTPException(404, str(exc)) from None


@router.delete("/targets/{tid}")
def delete_target(ctx: Ctx, tid: str):
    store_for(ctx).remove_target(tid)
    return {"ok": True}


def _submit_search_job(ctx, kind: str, label: str, args: list[str], timeout: int, on_success=None) -> dict:
    s = ctx.settings()
    try:
        job = ctx.jobs.submit(kind, label, args, timeout=timeout, env=pipeline_runner.job_env(ctx, s),
                              on_success=on_success, lane="search")
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None
    return job.summary()


@router.post("/targets/suggest")
def suggest_targets(ctx: Ctx, body: SuggestBody):
    store = store_for(ctx)
    room = MAX_TARGETS - len(store.targets())
    if room <= 0:
        raise HTTPException(409, f"Your list already has {MAX_TARGETS} companies. Remove some to make room.")
    s = ctx.settings()
    ctx.paths.scratch_dir.mkdir(parents=True, exist_ok=True)
    out = ctx.paths.scratch_dir / "job_search_suggest.json"
    exclude = ctx.paths.scratch_dir / "job_search_exclude.json"
    atomic_write_text(exclude, json.dumps([t["name"] for t in store.targets()]))
    args = [
        *ctx.paths.search_suggest_command, "--prefs", str(store.prefs_path), *_input_args(ctx),
        "--exclude", str(exclude), "--count", str(max(1, min(body.count, room, 100))), "--out", str(out),
        "--model", s.model, "--effort", s.effort,
    ]
    if body.clusters:
        args += ["--clusters", ",".join(c for c in body.clusters if c in CLUSTERS) or ",".join(CLUSTERS)]

    def on_success(job: Job) -> None:
        data = json.loads(out.read_text(encoding="utf-8"))
        out.unlink(missing_ok=True)
        store.save_suggestions(data)
        job.result = {"count": len(data.get("companies", [])), "tier": data.get("tier")}

    return _submit_search_job(ctx, "job_search_suggest", "Finding companies for you", args, s.timeout_seconds * 3 + 120, on_success)


@router.get("/targets/suggestions/latest")
def latest_suggestions(ctx: Ctx):
    store = store_for(ctx)
    data = store.latest_suggestions()
    if not data:
        return {"exists": False, "companies": []}
    have = {t["id"] for t in store.targets()}
    from resume_taylor.search.normalize import norm_company
    return {"exists": True, **data, "companies": [c for c in data.get("companies", []) if norm_company(c["name"]) not in have]}


@router.post("/targets/suggestions/accept")
def accept_suggestions(ctx: Ctx, body: AcceptSuggestionsBody):
    store = store_for(ctx)
    data = store.latest_suggestions() or {}
    wanted = {n.lower() for n in body.names}
    picked = [c for c in data.get("companies", []) if c["name"].lower() in wanted]
    return store.add_targets(picked, added_by="suggested") if picked else {"added": [], "skipped": [], "over_limit": [], "total": len(store.targets())}


@router.post("/targets/discover")
def discover_targets(ctx: Ctx, body: DiscoverBody):
    store = store_for(ctx)
    if not store.targets():
        raise HTTPException(409, "Add some companies first.")
    s = ctx.settings()
    args = [*ctx.paths.search_discover_command, "--targets", str(store.targets_path), "--routes", str(store.routes_path),
            "--cache-dir", str(store.cache_dir), "--model", s.model, "--effort", s.effort]
    if body.force:
        args.append("--force")
    return _submit_search_job(ctx, "job_search_discover", "Finding career pages", args, s.timeout_seconds * 6 + 300)


# -- searches ----------------------------------------------------------------------------------

@router.post("/search")
def start_search(ctx: Ctx, body: SearchBody):
    if body.count not in COUNTS:
        raise HTTPException(400, f"Count must be one of {', '.join(map(str, COUNTS))}.")
    store = store_for(ctx)
    prefs = store.get_prefs()
    depth = body.depth if body.depth in DEPTHS else prefs.depth
    sources = [x for x in (body.sources if body.sources is not None else prefs.sources) if x in SOURCES]
    if not sources:
        raise HTTPException(400, "Pick at least one source to search.")
    if "targets" in sources and not store.targets() and len(sources) == 1:
        raise HTTPException(409, "Add target companies first, or turn on ideated companies or the job board sweep.")
    s = ctx.settings()
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    ctx.paths.scratch_dir.mkdir(parents=True, exist_ok=True)
    out = ctx.paths.scratch_dir / f"job_search_{run_id}.json"
    args = [
        *ctx.paths.search_command, "--prefs", str(store.prefs_path), "--targets", str(store.targets_path),
        "--routes", str(store.routes_path), "--store", str(store.postings_path), "--cache-dir", str(store.cache_dir),
        *_input_args(ctx), "--count", str(body.count), "--depth", depth, "--sources", ",".join(sources),
        "--accounts-dir", str(ctx.paths.job_search_dir), "--out", str(out), "--model", s.model, "--effort", s.effort,
    ]
    if body.recency_days:
        args += ["--recency", str(body.recency_days)]

    def on_success(job: Job) -> None:
        report = json.loads(out.read_text(encoding="utf-8"))
        out.unlink(missing_ok=True)
        merged = store.merge_run(report, run_id)
        job.result = {"run_id": run_id, "found": len(report.get("results", [])), **merged}

    return _submit_search_job(ctx, "job_search", f"Searching for your top {body.count}", args, DEPTH_TIMEOUT[depth], on_success)


@router.get("/runs")
def list_runs(ctx: Ctx):
    return store_for(ctx).list_runs()


@router.get("/runs/{run_id}")
def get_run(ctx: Ctx, run_id: str):
    try:
        return store_for(ctx).get_run(run_id)
    except JobSearchError as exc:
        raise HTTPException(404, str(exc)) from None


# -- postings ----------------------------------------------------------------------------------

def _decorate(ctx, rec: dict) -> dict:
    """Refresh age and freshness (they change with the calendar, not only per run)."""
    out = {**rec}
    freshness.annotate(out)
    return out


@router.get("/postings")
def list_postings(ctx: Ctx, stage: str | None = None, only_new: bool = False, freshness_band: str | None = None, min_score: int = 0):
    store = store_for(ctx)
    return [_decorate(ctx, r) for r in store.list_postings(stage=stage, only_new=only_new, freshness=freshness_band, min_score=min_score)]


@router.post("/postings/import-url")
def import_posting(ctx: Ctx, body: ImportUrlBody):
    client = make_client()
    try:
        posting = import_url(client, body.url)
    except ImportFailed as exc:
        raise HTTPException(422, str(exc)) from None
    finally:
        client.close()
    posting["posted_at"] = posting.get("posted_at") or datetime.now().isoformat(timespec="seconds")
    freshness.annotate(posting)
    rec = store_for(ctx).add_posting(posting)
    return _decorate(ctx, rec)


@router.get("/postings/{pid}")
def get_posting(ctx: Ctx, pid: str):
    try:
        return _decorate(ctx, store_for(ctx).posting_with_text(pid))
    except JobSearchError as exc:
        raise HTTPException(404, str(exc)) from None


@router.patch("/postings/{pid}")
def patch_posting(ctx: Ctx, pid: str, body: PostingPatch):
    try:
        return _decorate(ctx, store_for(ctx).patch_posting(pid, body.model_dump(exclude_unset=True)))
    except JobSearchError as exc:
        raise _bad(exc) from None


@router.post("/postings/{pid}/verify")
def verify(ctx: Ctx, pid: str):
    store = store_for(ctx)
    try:
        rec = store.get_posting(pid)
    except JobSearchError as exc:
        raise HTTPException(404, str(exc)) from None
    client = make_client()
    try:
        checked = verify_posting(client, dict(rec))
    finally:
        client.close()
    rec = store.update_posting(pid, {"verified": checked["verified"], "last_verified_at": checked["last_verified_at"]})
    return _decorate(ctx, rec)


@router.post("/postings/{pid}/tailor")
def tailor(ctx: Ctx, pid: str, body: TailorBody):
    """Start a resume project from a found posting: no copy and paste."""
    store = store_for(ctx)
    try:
        rec = store.posting_with_text(pid)
    except JobSearchError as exc:
        raise HTTPException(404, str(exc)) from None
    if rec.get("project_id") and any(m.id == rec["project_id"] for m in ctx.store.all()):
        raise HTTPException(409, "This posting already has a resume project. Open it from the board.")
    ctx.require_inputs()
    if not body.skip_verify:
        client = make_client()
        try:
            checked = verify_posting(client, dict(rec))
        finally:
            client.close()
        store.update_posting(pid, {"verified": checked["verified"], "last_verified_at": checked["last_verified_at"]})
        if checked["verified"] == "closed":
            raise HTTPException(409, "This posting is no longer live at its source, so there is nothing to tailor for.")
    text = rec.get("description_text", "").strip()
    if len(text) < 40:
        raise HTTPException(422, "This posting has no description to tailor against. Open the link, copy the text, and use New project instead.")
    header = [rec["title"], rec["company"]]
    if rec.get("locations"):
        header.append("Location: " + "; ".join(rec["locations"]))
    if rec.get("pay_text"):
        header.append("Pay: " + rec["pay_text"])
    header.append("Apply: " + (rec.get("apply_url") or rec.get("url", "")))
    s = ctx.settings()
    meta = ctx.store.create(
        job_text="\n".join(header) + "\n\n" + text, company=rec["company"], role=rec["title"], url=rec.get("apply_url") or rec.get("url", ""),
        template=body.template or s.default_template,
        cover_letter=s.cover_letter_default if body.cover_letter is None else body.cover_letter,
    )
    ctx.store.touch(meta.id, posting_id=pid)
    updates = {"project_id": meta.id}
    if rec.get("stage") == "prospect":
        updates["stage"] = "interested"
    store.update_posting(pid, updates)
    job = pipeline_runner.start_pipeline(ctx, meta.id, render=False).summary() if body.generate else None
    return {"project": ctx.project_summary(ctx.store.get(meta.id), ctx.current_hashes()), "job": job}


# -- the board ---------------------------------------------------------------------------------

def project_column(summary: dict) -> str:
    status, stage = summary.get("status"), summary.get("outcome_stage", 0)
    if status in ("rejected", "archived"):
        return "closed"
    if status == "offer" or stage >= 4:
        return "offer"
    if status == "interviewing" or stage in (2, 3):
        return "interviewing"
    if status == "applied" or stage == 1:
        return "applied"
    return "resume_ready" if summary.get("has_result") else "tailoring"


@router.get("/pipeline")
def pipeline(ctx: Ctx):
    """One board for the whole lifecycle: postings before a project exists, then projects."""
    store = store_for(ctx)
    postings = store.list_postings()
    by_id = {p["id"]: p for p in postings}
    hashes = ctx.current_hashes()
    cards: list[dict] = []
    linked: set[str] = set()
    for meta in ctx.store.all():
        summary = ctx.project_summary(meta, hashes)
        post = by_id.get(summary.get("posting_id", ""))
        if post:
            linked.add(post["id"])
            post = _decorate(ctx, post)
        cards.append({
            "kind": "project", "id": meta.id, "column": project_column(summary), "title": meta.role or meta.name, "company": meta.company,
            "url": meta.url, "outcome_stage": meta.outcome_stage, "status": meta.status, "updated_at": meta.updated_at,
            "applied_on": meta.applied_on, "posting_id": meta.posting_id or None,
            "fit": (post or {}).get("fit", {}).get("total") if post else None,
            "freshness": (post or {}).get("freshness") if post else None, "age_days": (post or {}).get("age_days") if post else None,
            "active_job": bool(summary.get("active_job")),
        })
    for p in postings:
        if p["id"] in linked or p.get("project_id"):
            continue
        p = _decorate(ctx, p)
        if p.get("stage") not in ("prospect", "interested", "dismissed"):
            continue
        cards.append({
            "kind": "posting", "id": p["id"], "column": "closed" if p["stage"] == "dismissed" else p["stage"],
            "title": p["title"], "company": p["company"], "url": p.get("url", ""), "fit": (p.get("fit") or {}).get("total"),
            "freshness": p.get("freshness"), "age_days": p.get("age_days"), "is_new": p.get("is_new", False),
            "dismiss_reason": p.get("dismiss_reason", ""), "updated_at": p.get("last_seen", ""),
            "work_mode": p.get("work_mode"), "locations": p.get("locations", [])[:2],
        })
    return {"columns": COLUMNS, "cards": cards}


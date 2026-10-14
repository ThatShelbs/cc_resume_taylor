"""Starting the pipeline as a job: the command line, the environment, and what happens
when it finishes. The one place that knows how to run `python -m resume_taylor.pipeline`
for a project (and for the sample-data seeder)."""

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import HTTPException

from ..storage import credentials
from ..storage.fs import plain_path, remove_tree
from ..storage.paths import Paths
from ..storage.projects import ProjectError, file_hash, now, stamp
from ..storage.settings import Settings
from .jobs import Job

if TYPE_CHECKING:
    from ..context import AppContext


def input_hashes(paths: Paths) -> dict[str, str]:
    """Fingerprints of the files a generation reads, to tell later when they changed."""
    return {
        "profile": file_hash(paths.latest("in_profile")),
        "resume": file_hash(paths.latest("in_resume")),
        "fact_bank": file_hash(paths.fact_bank_path),
    }


def pipeline_command(
    paths: Paths, *, job_text: Path, out_dir: Path, result_json: Path, template: str,
    render_json: Path | None = None, model: str | None = None, effort: str | None = None,
    cover_letter: bool = False,
) -> list[str]:
    """Arguments (after the interpreter) for one pipeline run. With `render_json` the saved
    result is re-validated and rendered without calling Claude. Plain paths throughout
    (no extended-length prefix) because the pipeline hands them to Word."""
    args = [
        *paths.generator_command,
        "--profile", str(plain_path(paths.latest("in_profile"))),
        "--resume", str(plain_path(paths.latest("in_resume"))),
        "--job", str(plain_path(job_text)),
        "--fact-bank", str(plain_path(paths.fact_bank_path)),
        "--deny", str(plain_path(paths.deny_path)),
        "--template", template,
        "--out-dir", str(plain_path(out_dir)),
        "--result-json", str(plain_path(result_json)),
    ]
    if model:
        args += ["--model", model]
    if effort:
        args += ["--effort", effort]
    if render_json:
        args += ["--render-json", str(plain_path(render_json))]
    elif cover_letter:
        args.append("--cover-letter")
    return args


def job_env(ctx: "AppContext", s: Settings) -> dict:
    """Extra environment for a pipeline subprocess: the timeout, plus the
    API key when the user saved one in Settings (else .env or the CLI
    login decides)."""
    env = {"CLAUDE_TIMEOUT": str(s.timeout_seconds)}
    key = credentials.load_key(ctx.paths.secrets_path)
    if key:
        env["ANTHROPIC_API_KEY"] = key
    return env



def start_pipeline(ctx: "AppContext", pid: str, *, render: bool) -> Job:
    store, paths, jobs = ctx.store, ctx.paths, ctx.jobs
    meta = store.get(pid)
    s = ctx.settings()
    if render and not store.result_path(pid).exists():
        raise HTTPException(409, "Generate this resume first.")
    staging = store.dir(pid) / f".staging-{uuid.uuid4().hex[:8]}"
    staging.mkdir()
    ctx.require_inputs()
    d = store.dir(pid)
    args = pipeline_command(
        paths, job_text=d / "job.txt", out_dir=staging, result_json=staging / "result.json", template=meta.template,
        render_json=d / "result.json" if render else None, model=s.model, effort=s.effort, cover_letter=meta.cover_letter,
    )
    kind = "render" if render else "generate"
    started = now()

    def on_success(job: Job) -> None:
        hashes = {}
        if not render:
            hashes = store.snapshot_inputs(pid, {
                "profile": ctx.profile_path(), "resume": ctx.resume_path(), "fact_bank": paths.fact_bank_path,
            })
        store.promote(pid, staging, new_version=not render)
        done_at = stamp()
        fields = {"rendered_at": done_at, "result_saved_at": done_at}
        run = {"kind": kind, "when": started, "ok": True, "model": s.model, "effort": s.effort}
        if render:
            fields["last_render"] = run
        else:
            fields["last_generate"] = {**run, "input_hashes": hashes}
        store.touch(pid, **fields)

    def on_finish(job: Job) -> None:
        if job.outcome != "succeeded" and (staging / "result.json").exists():
            # The pipeline finished but installing its output failed: keep
            # the new files rather than throw away a finished draft.
            job.error = f"{job.error} Your new files were kept in {plain_path(staging)}."
        else:
            remove_tree(staging, quiet=True)
        if job.outcome != "succeeded":
            run = {"kind": kind, "when": started, "ok": False, "model": s.model, "effort": s.effort,
                   "error": job.error}
            try:
                store.touch(pid, **({"last_render": run} if render else {"last_generate": run}))
            except (ProjectError, OSError):
                pass

    label = "Re-rendering resume" if render else f"Tailoring resume for {meta.name}"
    try:
        return jobs.submit(
            kind, label, args,
            project_id=pid,
            timeout=(240 if render else s.timeout_seconds * 4 + 300),
            log_path=store.dir(pid) / "run.log",
            env=job_env(ctx, s),
            on_success=on_success,
            on_finish=on_finish,
        )
    except RuntimeError as exc:
        remove_tree(staging, quiet=True)
        raise HTTPException(409, str(exc)) from None



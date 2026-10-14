"""Liveness probe, the system status the setup screens read, and data-folder housekeeping
(backup, open in the file manager, shut down)."""

import os
import sys
import threading
import time
import zipfile
from datetime import datetime

from fastapi import APIRouter, HTTPException

from resume_taylor import __version__
from resume_taylor.pipeline.render.templates import TEMPLATES

from ..context import Ctx
from ..schemas import OpenFolderBody
from ..services import demo
from ..services.os_integration import open_path, word_available
from ..storage import credentials
from ..storage import facts as facts_mod
from ..storage.fs import plain_path
from ..storage.projects import STATUSES
from ..storage.settings import EFFORT_CHOICES, MODEL_CHOICES

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"app": "resume-taylor", "version": __version__}


@router.get("/system")
def system(ctx: Ctx):
    pp, rp = ctx.profile_path(), ctx.resume_path()
    fact_count = None
    if ctx.paths.fact_bank_path.exists():
        try:
            fact_count = len(facts_mod.read_facts(ctx.paths.fact_bank_path))
        except facts_mod.FactBankError:
            fact_count = 0
    deny_count = len([r for r in facts_mod.check_deny_text(facts_mod.read_deny_text(ctx.paths.deny_path)) if not r["error"]])
    return {
        "version": __version__,
        "claude": {**ctx.claude.info(), **ctx.claude.login()},
        "api_key": credentials.status(ctx.paths.secrets_path),
        "sample_loaded": demo.is_loaded(ctx.paths),
        "word": word_available(),
        "platform": sys.platform,
        "data_root": str(plain_path(ctx.paths.data_root)),
        "inputs": {
            "profile": pp.name if pp else None,
            "resume": rp.name if rp else None,
            "fact_bank": fact_count,
            "deny_patterns": deny_count,
        },
        "onboarding_needed": not (pp and rp),
        "templates": [
            {"key": t.key, "label": t.label, "description": t.description} for t in TEMPLATES.values()
        ],
        "statuses": STATUSES,
        "models": MODEL_CHOICES,
        "efforts": EFFORT_CHOICES,
        "active_jobs": [j.summary() for j in ctx.jobs.active()],
    }


@router.post("/system/backup")
def backup_data(ctx: Ctx):
    """Zip the user's inputs, projects and settings (never the API key)."""
    dest = plain_path(ctx.paths.data_root) / f"ResumeTaylor-backup-{datetime.now():%Y-%m-%d-%H-%M-%S}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for sub in (ctx.paths.input_dir, ctx.paths.projects_dir):
            for f in plain_path(sub).rglob("*"):
                if f.is_file() and "_trash" not in f.parts:
                    z.write(f, f.relative_to(plain_path(ctx.paths.data_root)))
        for f in (ctx.paths.deny_path, ctx.paths.settings_path):
            if f.exists():
                z.write(plain_path(f), f.name)
    open_path(dest.parent)
    return {"path": str(dest)}


@router.post("/system/open-folder")
def open_folder(ctx: Ctx, body: OpenFolderBody):
    targets = {"data": ctx.paths.data_root, "inputs": ctx.paths.input_dir, "projects": ctx.paths.projects_dir,
               "archive": ctx.paths.archive_dir}
    if body.target not in targets:
        raise HTTPException(400, "Unknown folder.")
    open_path(targets[body.target])
    return {"ok": True}


@router.post("/system/shutdown")
def shutdown():
    def _stop():
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=_stop, daemon=True).start()
    return {"ok": True}

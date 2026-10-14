"""The per-app state and helpers every route shares.

`create_app()` builds one AppContext and stores it on `app.state.ctx`; route
functions receive it through the `Ctx` dependency instead of closing over it.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from ..pipeline.factbank import snap_employer
from ..pipeline.guards import load_deny_patterns
from ..pipeline.parsing import parse_prior_resume
from ..pipeline.sources import read_docx_text
from .services.claude_status import ClaudeStatus
from .services.jobs import JobManager
from .services.pipeline_runner import input_hashes
from .storage import facts as facts_mod
from .storage.paths import Paths
from .storage.projects import ProjectStore, file_hash
from .storage.settings import Settings, load_settings


@dataclass
class AppContext:
    paths: Paths
    token: str
    store: ProjectStore
    jobs: JobManager
    allowed_hosts: set
    claude: ClaudeStatus = field(default_factory=ClaudeStatus)
    uploads: dict[str, dict] = field(default_factory=dict)  # upload_id -> {"path": Path}
    cache: dict = field(default_factory=dict)

    # -- settings and inputs -----------------------------------------------------

    def settings(self) -> Settings:
        return load_settings(self.paths.settings_path)

    def profile_path(self) -> Path | None:
        return self.paths.latest("in_profile")

    def resume_path(self) -> Path | None:
        return self.paths.latest("in_resume")

    def require_inputs(self) -> tuple[Path, Path]:
        pp, rp = self.profile_path(), self.resume_path()
        if not pp:
            raise HTTPException(409, "Add your profile first (Profile page).")
        if not rp:
            raise HTTPException(409, "Upload your base resume first (Base Resume page).")
        return pp, rp

    def companies(self) -> list[str]:
        rp = self.resume_path()
        if not rp:
            return []
        try:
            return [j["company"] for j in parse_prior_resume(rp)["jobs"]]
        except SystemExit:
            return []

    def current_hashes(self) -> dict[str, str]:
        return input_hashes(self.paths)

    def source_context(self) -> dict:
        """Profile+resume text, fact bank, and deny list for the live linter,
        cached until any of those files change."""
        cache, paths = self.cache, self.paths
        key = (tuple(self.current_hashes().values()), file_hash(paths.deny_path))
        if cache.get("ctx_key") != key:
            pp, rp = self.profile_path(), self.resume_path()
            text = ""
            try:
                if pp:
                    text += read_docx_text(pp)
                if rp:
                    text += "\n" + read_docx_text(rp)
            except SystemExit:
                pass
            bank = None
            if paths.fact_bank_path.exists():
                bank = {f.id: f.model_dump() for f in facts_mod.read_facts(paths.fact_bank_path)}
                comps = self.companies()
                for fact in bank.values():
                    fact["employer"] = snap_employer(fact["employer"], comps) or "unassigned"
            try:
                deny = load_deny_patterns(paths.deny_path)
            except SystemExit:
                deny = []
            cache["ctx_key"] = key
            cache["ctx"] = {"source_text": text, "fact_bank": bank, "deny": deny}
        return cache["ctx"]

    def invalidate_sources(self) -> None:
        """Call after any change to the profile, resume, fact bank or never-claim list."""
        self.cache.pop("ctx_key", None)

    # -- projects and pipeline runs ------------------------------------------------

    def project_summary(self, meta, hashes: dict) -> dict:
        store = self.store
        d = store.dir(meta.id)
        outputs = store.outputs(meta.id)
        last = meta.last_generate
        job = self.jobs.latest_for(meta.id)
        changed = []
        if last and last.ok and last.input_hashes:
            changed = [k for k, v in hashes.items() if last.input_hashes.get(k, "") != v]
        return {
            **meta.model_dump(),
            "has_result": (d / "result.json").exists(),
            "has_pdf": any(f["name"].endswith(".pdf") and f["name"].startswith("out_resume_") for f in outputs),
            "inputs_changed": changed,
            "outputs_stale": bool(meta.result_saved_at and meta.rendered_at and meta.result_saved_at > meta.rendered_at),
            "active_job": job.summary() if job and not job.done else None,
        }


def get_context(request: Request) -> AppContext:
    return request.app.state.ctx


Ctx = Annotated[AppContext, Depends(get_context)]

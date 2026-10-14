"""Job-application projects: content, generation, versions, files, trash."""

from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse

from resume_taylor.pipeline.render.templates import TEMPLATES
from resume_taylor.pipeline.sources import read_input_text

from ..context import Ctx
from ..schemas import NewProject, ProjectPatch, RenderBody, TextBody
from ..services import live_checks, pipeline_runner
from ..services.os_integration import open_path
from ..storage import facts as facts_mod
from ..storage.projects import guess_company_role
from ..uploads import read_upload, scratch_file

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
def list_projects(ctx: Ctx):
    hashes = ctx.current_hashes()
    return [ctx.project_summary(m, hashes) for m in ctx.store.all()]


@router.post("/guess")
def guess(body: TextBody):
    return guess_company_role(body.text)


@router.post("/extract-posting")
async def extract_posting(ctx: Ctx, file: UploadFile = File(...)):
    name, data = await read_upload(file, (".docx", ".pdf", ".txt", ".md"))
    with scratch_file(ctx.paths.scratch_dir, name, data) as tmp:
        try:
            text = read_input_text(tmp)
        except (Exception, SystemExit) as exc:
            raise HTTPException(400, f"Couldn't read text from that file ({exc}).") from None
    if not text.strip():
        raise HTTPException(400, "No text could be read from that file (a scanned PDF?). Paste the text instead.")
    return {"text": text, **guess_company_role(text)}


@router.post("")
def create_project(ctx: Ctx, body: NewProject):
    s = ctx.settings()
    meta = ctx.store.create(
        job_text=body.job_text,
        company=body.company,
        role=body.role,
        name=body.name,
        url=body.url,
        template=body.template or s.default_template,
        cover_letter=s.cover_letter_default if body.cover_letter is None else body.cover_letter,
    )
    job = pipeline_runner.start_pipeline(ctx, meta.id, render=False).summary() if body.generate else None
    return {"project": ctx.project_summary(ctx.store.get(meta.id), ctx.current_hashes()), "job": job}


@router.get("/{pid}")
def get_project(ctx: Ctx, pid: str):
    meta = ctx.store.get(pid)
    job = ctx.jobs.latest_for(pid)
    return {
        "project": ctx.project_summary(meta, ctx.current_hashes()),
        "job_text": ctx.store.get_job_text(pid),
        "result": ctx.store.get_result(pid),
        "outputs": ctx.store.outputs(pid),
        "job": job.summary() if job else None,
    }


@router.patch("/{pid}")
def patch_project(ctx: Ctx, pid: str, body: ProjectPatch):
    patch = body.model_dump(exclude_unset=True)
    meta = ctx.store.update(pid, patch)
    return ctx.project_summary(meta, ctx.current_hashes())


@router.put("/{pid}/job")
def put_job_text(ctx: Ctx, pid: str, body: TextBody):
    ctx.store.get(pid)
    ctx.store.set_job_text(pid, body.text)
    return ctx.project_summary(ctx.store.touch(pid), ctx.current_hashes())


@router.put("/{pid}/result")
def put_result(ctx: Ctx, pid: str, result: dict = Body(...)):
    meta = ctx.store.save_result(pid, result)
    return ctx.project_summary(meta, ctx.current_hashes())


@router.post("/{pid}/lint")
def lint_project(ctx: Ctx, pid: str, result: dict = Body(...)):
    ctx.store.get(pid)
    sources = ctx.source_context()
    return live_checks.lint_result(result, sources["source_text"], sources["fact_bank"], sources["deny"])


@router.get("/{pid}/facts")
def project_facts(ctx: Ctx, pid: str):
    """Fact text for citation hover cards."""
    ctx.store.get(pid)
    return {f.id: {"text": f.text, "employer": f.employer, "kind": f.kind}
            for f in facts_mod.read_facts(ctx.paths.fact_bank_path)}


@router.post("/{pid}/generate")
def generate(ctx: Ctx, pid: str):
    return pipeline_runner.start_pipeline(ctx, pid, render=False).summary()


@router.post("/{pid}/render")
def render(ctx: Ctx, pid: str, body: RenderBody | None = None):
    if body and body.template:
        ctx.store.update(pid, {"template": body.template})
    return pipeline_runner.start_pipeline(ctx, pid, render=True).summary()


@router.get("/{pid}/versions")
def versions(ctx: Ctx, pid: str):
    return ctx.store.versions(pid)


@router.get("/{pid}/versions/{vid}")
def version(ctx: Ctx, pid: str, vid: str):
    return ctx.store.version_result(pid, vid)


@router.post("/{pid}/versions/{vid}/restore")
def restore_version(ctx: Ctx, pid: str, vid: str):
    restored = ctx.store.version_result(pid, vid)
    ctx.store.rotate(pid)
    ctx.store.save_result(pid, restored)
    if restored.get("template") in TEMPLATES:
        ctx.store.update(pid, {"template": restored["template"]})
    return pipeline_runner.start_pipeline(ctx, pid, render=True).summary()


def file_response(path: Path, download: bool) -> FileResponse:
    media = {".pdf": "application/pdf", ".md": "text/markdown; charset=utf-8",
             ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
    return FileResponse(
        path,
        media_type=media.get(path.suffix.lower(), "application/octet-stream"),
        filename=path.name if download else None,
        content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{pid}/files/{name}")
def project_file(ctx: Ctx, pid: str, name: str, download: bool = False):
    return file_response(ctx.store.safe_file(pid, "outputs", name), download)


@router.get("/{pid}/versions/{vid}/files/{name}")
def version_file(ctx: Ctx, pid: str, vid: str, name: str, download: bool = True):
    return file_response(ctx.store.safe_file(pid, "versions", vid, name), download)


@router.get("/{pid}/report")
def report(ctx: Ctx, pid: str):
    for f in ctx.store.outputs(pid):
        if f["name"].startswith("out_resume_") and f["name"].endswith("_report.md"):
            return PlainTextResponse(ctx.store.safe_file(pid, "outputs", f["name"]).read_text(encoding="utf-8"))
    raise HTTPException(404, "No report yet.")


@router.get("/{pid}/log")
def run_log(ctx: Ctx, pid: str):
    p = ctx.store.dir(pid) / "run.log"
    return PlainTextResponse(p.read_text(encoding="utf-8") if p.exists() else "")


@router.post("/{pid}/duplicate")
def duplicate(ctx: Ctx, pid: str):
    return ctx.project_summary(ctx.store.duplicate(pid), ctx.current_hashes())


@router.delete("/{pid}")
def delete_project(ctx: Ctx, pid: str):
    job = ctx.jobs.latest_for(pid)
    if job and not job.done:
        raise HTTPException(409, "Wait for the running job to finish (or cancel it) before deleting.")
    return {"trash_id": ctx.store.trash_project(pid)}


@router.post("/{pid}/open-folder")
def open_project_folder(ctx: Ctx, pid: str):
    open_path(ctx.store.dir(pid))
    return {"ok": True}

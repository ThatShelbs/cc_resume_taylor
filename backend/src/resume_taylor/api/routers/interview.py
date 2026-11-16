"""The optional pre-generation interview: questions for one posting, then saving the answers
into the fact bank and profile so every later application can use them."""

import json
import re

from fastapi import APIRouter, HTTPException

from resume_taylor.pipeline.factbank import snap_employer
from resume_taylor.pipeline.guards import remove_em_dashes

from ..context import Ctx
from ..schemas import InterviewAnswers
from ..services import pipeline_runner
from ..services.jobs import Job
from ..storage import facts as facts_mod
from ..storage import profile_store
from ..storage.fs import atomic_write_text

router = APIRouter(prefix="/api/projects/{pid}/interview", tags=["interview"])

MAX_ANSWER_CHARS = 800
HARD_SKILL_SECTION = "Software/Tools"
SOFT_SKILL_SECTION = "Skills"


def _clean(text: str, limit: int = MAX_ANSWER_CHARS) -> str:
    return remove_em_dashes(re.sub(r"\s+", " ", text or "").strip())[:limit]


@router.get("")
def get_interview(ctx: Ctx, pid: str):
    """The cached questions for this project, if an interview was already prepared."""
    ctx.store.get(pid)
    path = ctx.store.dir(pid) / "interview.json"
    if not path.exists():
        return {"exists": False}
    return {"exists": True, **json.loads(path.read_text(encoding="utf-8"))}


@router.post("/questions")
def prepare_interview(ctx: Ctx, pid: str):
    ctx.store.get(pid)
    pp, rp = ctx.require_inputs()
    d = ctx.store.dir(pid)
    out = ctx.paths.scratch_dir / f"interview_{pid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    s = ctx.settings()

    def on_success(job: Job) -> None:
        data = json.loads(out.read_text(encoding="utf-8"))
        out.unlink(missing_ok=True)
        data["companies"] = ctx.companies()
        atomic_write_text(d / "interview.json", json.dumps(data, ensure_ascii=False, indent=2))
        job.result = {"exists": True, **data}

    args = [
        *ctx.paths.interview_command,
        "--profile", str(pp), "--resume", str(rp), "--job", str(d / "job.txt"),
        "--fact-bank", str(ctx.paths.fact_bank_path), "--out", str(out),
        "--model", s.model, "--effort", s.effort,
    ]
    try:
        job = ctx.jobs.submit(
            "interview", "Preparing your interview questions", args,
            project_id=pid,
            timeout=s.timeout_seconds * 2 + 120,
            env=pipeline_runner.job_env(ctx, s),
            on_success=on_success,
        )
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from None
    return job.summary()


def _add_to_section(profile: profile_store.Profile, title: str, item: str) -> bool:
    section = next((s for s in profile.sections if s.title.strip().lower() == title.lower()), None)
    if section is None:
        section = profile_store.Section(title=title)
        profile.sections.append(section)
    if any(i.strip().lower() == item.lower() for i in section.items):
        return False
    section.items.append(item)
    return True


@router.post("/answers")
def save_answers(ctx: Ctx, pid: str, body: InterviewAnswers):
    """Persist the interview: answers become fact-bank entries, confirmed skills go on the profile,
    and the whole transcript is saved for this project's next generation."""
    ctx.store.get(pid)
    companies = ctx.companies()
    bank_path = ctx.paths.fact_bank_path
    existing = facts_mod.read_facts(bank_path)
    known = {f.text.strip().lower() for f in existing}

    new_facts, notes = [], []
    for a in body.answers:
        text = _clean(a.text)
        if not text:
            continue
        notes.append(f"Q: {_clean(a.question, 300)}\nA: {text}")
        employer = snap_employer(a.employer, companies) or "general"
        if text.lower() in known:
            continue
        known.add(text.lower())
        new_facts.append(facts_mod.Fact(text=text, employer=employer, kind="accomplishment", tags=["interview"]))

    profile_changed = False
    profile = None
    pp = ctx.profile_path()
    if pp:
        profile = profile_store.read_profile(pp)

    confirmed = []
    for sk in body.skills:
        name = _clean(sk.name, 80)
        if sk.status != "have" or not name:
            continue
        confirmed.append(name)
        note = _clean(sk.note, 400)
        if sk.kind == "soft" and note:
            # A soft skill confirmed with a story becomes a citable fact, not just a list entry.
            if note.lower() not in known:
                known.add(note.lower())
                new_facts.append(
                    facts_mod.Fact(text=note, employer="general", kind="trait", tags=["interview", name.lower()])
                )
            notes.append(f"Confirmed skill: {name}. {note}")
        else:
            notes.append(f"Confirmed skill: {name}.")
        if profile is not None:
            title = SOFT_SKILL_SECTION if sk.kind == "soft" else HARD_SKILL_SECTION
            profile_changed = _add_to_section(profile, title, name) or profile_changed

    if new_facts:
        if bank_path.exists():
            profile_store.backup(bank_path, ctx.paths.archive_dir)
        facts_mod.write_facts(bank_path, [*existing, *new_facts])
    if profile is not None and profile_changed:
        profile_store.save_profile(profile, pp, ctx.paths.archive_dir)

    notes_path = ctx.store.dir(pid) / "interview_notes.txt"
    if notes:
        atomic_write_text(notes_path, "\n\n".join(notes))
    else:
        notes_path.unlink(missing_ok=True)
    ctx.invalidate_sources()
    return {"facts_added": len(new_facts), "skills_added": confirmed if profile_changed else [], "notes": bool(notes)}

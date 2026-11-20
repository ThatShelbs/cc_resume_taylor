"""`python -m resume_taylor.search.draft_prefs`: draft starting search settings from the resume.

One Claude call (no web) proposes titles, role keywords, skills, industries and a minimum level; Python
then keeps only what the person's own documents support (skills must appear in the source text) and falls
back to what the resume parser alone can say when Claude is unavailable. The app merges the result into
empty fields only, so nothing the person typed is overwritten."""

import argparse
import json
import re
from pathlib import Path

from resume_taylor.config import COMPANY_IDEATION_SKILL_PATH
from resume_taylor.pipeline.prompts import load_skill
from resume_taylor.pipeline.runtime import stage

from . import claude
from .candidate import Candidate, build_candidate
from .prefs import LEVELS, Preferences, load_prefs, resolve_min_level

CONTRACT = """

Task: DRAFT PREFERENCES. Reply with JSON only:
{"titles": [str], "title_keywords": [str], "skill_terms": [str], "industries": [str], "min_level": str}"""


def _strings(value, limit: int) -> list[str]:
    out: list[str] = []
    for v in value if isinstance(value, list) else []:
        s = re.sub(r"\s+", " ", str(v)).strip()
        if s and s.lower() not in {x.lower() for x in out}:
            out.append(s)
    return out[:limit]


def sanitize(reply, cand: Candidate) -> dict:
    """What the person's documents support. Skills must appear in their text; the level must be valid."""
    reply = reply if isinstance(reply, dict) else {}
    hay = (cand.source_text + "\n" + " ".join(cand.skills) + " " + " ".join(cand.tags)).lower()
    skills = [s for s in _strings(reply.get("skill_terms"), 12) if s.lower() in hay] if cand.has_evidence else []
    level = reply.get("min_level") if reply.get("min_level") in LEVELS else ""
    return {
        "titles": _strings(reply.get("titles"), 6),
        "title_keywords": _strings(reply.get("title_keywords"), 8),
        "skill_terms": skills,
        "industries": _strings(reply.get("industries"), 5),
        "min_level": level,
    }


def fallback(cand: Candidate) -> dict:
    """Deterministic starting values from the parsed resume and profile alone."""
    titles = list(dict.fromkeys(cand.titles[:2]))
    return {"titles": titles, "title_keywords": [], "skill_terms": cand.skills[:12], "industries": [], "min_level": ""}


def draft(cand: Candidate, model=None, effort=None) -> dict:
    reply = None
    if cand.has_evidence:
        reply = claude.ask(load_skill(COMPANY_IDEATION_SKILL_PATH) + CONTRACT, f"About the person:\n{cand.summary()}",
                           model=model, effort=effort, label="Drafting search settings")
    out = sanitize(reply, cand)
    base = fallback(cand)
    for key in ("titles", "skill_terms"):
        out[key] = out[key] or base[key]
    out["min_level"] = out["min_level"] or resolve_min_level(Preferences(titles=out["titles"]), cand.titles)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Draft search settings from the resume.")
    ap.add_argument("--prefs")
    ap.add_argument("--profile")
    ap.add_argument("--resume")
    ap.add_argument("--fact-bank")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model")
    ap.add_argument("--effort")
    args = ap.parse_args(argv)
    stage("preparing")
    cand = build_candidate(*(Path(p) if p else None for p in (args.profile, args.resume, args.fact_bank)), load_prefs(args.prefs))
    stage("profiling")
    print("Reading your resume to draft your search settings...")
    data = draft(cand, args.model, args.effort)
    Path(args.out).write_text(json.dumps(data, indent=2), encoding="utf-8")
    stage("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

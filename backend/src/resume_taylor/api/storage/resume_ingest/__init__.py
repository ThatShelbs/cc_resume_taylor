"""
Turn an uploaded resume (Word or PDF) into the structure the pipeline needs,
then write it back out as a normalized in_resume*.docx that
parse_prior_resume() reads exactly.

Order of preference, most deterministic first:
  1. A .docx already in the pipeline layout parses directly (docx_io.py).
  2. Otherwise the text is parsed heuristically (extract.py).
  3. Only if that finds no employers, one Claude CLI call extracts the
     structure verbatim (ai.py, run as a job via __main__.py).

Whichever path ran, every company, title, date, and bullet is checked against
the raw text (verify.py) and anything not found verbatim is flagged for the
review screen. Nothing is written until a person confirms the structure.
"""

import re
from pathlib import Path

from resume_taylor.pipeline.parsing import PHONE_RE
from resume_taylor.pipeline.sources import docx_paras, read_docx_text

from .docx_io import structure_from_paras, structure_to_paras, validate_structure, write_resume_docx
from .extract import SECTION_ALIASES, extract_text, heuristic_parse
from .models import Education, Flag, IngestError, Job, OtherSection, ResumeStructure
from .verify import verify

__all__ = [
    "Education", "Flag", "IngestError", "Job", "OtherSection", "ResumeStructure",
    "extract_text", "heuristic_parse", "ingest", "prefill_contact", "structure_from_paras",
    "structure_to_paras", "validate_structure", "verify", "write_resume_docx",
]


def ingest(path: Path) -> ResumeStructure:
    """Deterministic ingestion only. The caller checks `.jobs` and offers the
    Claude fallback when it's empty."""
    if path.suffix.lower() == ".docx":
        try:
            structure = structure_from_paras(docx_paras(path, strip=False))
            if structure.jobs:
                structure.raw_text = read_docx_text(path)
                structure.source_file = path.name
                return verify(structure, structure.raw_text)
        except SystemExit:
            pass
    text = extract_text(path)
    structure = heuristic_parse(text)
    structure.source_file = path.name
    return verify(structure, text)


def prefill_contact(structure: ResumeStructure) -> dict:
    """Best-effort contact details from the resume header, for onboarding."""
    lines = structure.contact_lines
    pieces = []
    for line in lines:
        pieces += [p.strip() for p in re.split(r"\s*[|•·]\s*|\t", line) if p.strip()]
    email = next((m.group(0) for p in pieces if (m := re.search(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", p))), "")
    phone = next((m.group(0) for p in pieces if (m := PHONE_RE.search(p))), "")
    linkedin = next((p for p in pieces if "linkedin.com" in p.lower()), "")
    name = next(
        (p for p in pieces if p not in (email, linkedin) and not PHONE_RE.search(p) and "@" not in p
         and 1 < len(p.split()) <= 4 and not any(ch.isdigit() for ch in p)),
        "",
    )
    if name.isupper():
        name = name.title()  # small-caps headers extract as ALL CAPS
    location = next(
        (p for p in pieces if p not in (name, email, linkedin) and not PHONE_RE.search(p)
         and re.search(r",\s*[A-Z]{2}\b|,\s*[A-Z][a-z]+", p)),
        "",
    )
    skills = []
    for section in structure.other_sections:
        if section.title.lower() in SECTION_ALIASES["skills"]:
            for line in section.lines:
                label, _, rest = line.partition(":")
                items = rest if rest.strip() and len(label) < 30 else line
                skills += [s.strip() for s in re.split(r"[,|•·;]", items) if 1 < len(s.strip()) <= 60]
    return {"name": name, "email": email, "phone": phone, "location": location, "linkedin": linkedin,
            "skills": list(dict.fromkeys(skills))}

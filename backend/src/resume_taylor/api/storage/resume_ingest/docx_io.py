"""The pipeline's resume layout (docx paragraphs) <-> ResumeStructure, and writing the
normalized in_resume*.docx that `parse_prior_resume()` reads exactly."""

import re
from pathlib import Path

import docx

from resume_taylor.pipeline.parsing import parse_prior_resume

from .models import Education, IngestError, Job, OtherSection, ResumeStructure

PIPELINE_SECTIONS = {"summary", "education", "experience", "skills", "projects", "awards"}


def structure_from_paras(paras: list) -> ResumeStructure:
    """Read a resume that's already in the pipeline layout (the canonical
    in_resume*.docx), keeping the summary and other sections too."""
    parsed = parse_prior_resume(paras)
    structure = ResumeStructure(source="docx")
    current = None
    other: dict = {}
    prev_was_header = False
    for i, (style, text) in enumerate(paras):
        key = text.strip().rstrip(":").strip().lower()
        title = text.strip().rstrip(":").strip()
        next_style = paras[i + 1][0] if i + 1 < len(paras) else None
        if (
            style == "Normal"
            and isinstance(current, tuple)
            and next_style == "List Paragraph"
            and len(title) <= 40
            and key not in PIPELINE_SECTIONS
        ):
            # A heading we wrote for an extra section (its lines are always
            # List Paragraph), not a Normal-style content line like "Python, SQL".
            other[title] = []
            current = ("other", title)
            continue
        if style == "Normal" and key in PIPELINE_SECTIONS:
            current = key
            if key not in ("summary", "education", "experience"):
                other[title] = []
                current = ("other", title)
            prev_was_header = False
            continue
        if style == "Normal" and current in ("education", "experience") and "|" not in text and not prev_was_header:
            # A heading the pipeline doesn't know (e.g. "Certifications"): the
            # parser ignores its content, but the editor keeps it.
            other[title] = []
            current = ("other", title)
            continue
        prev_was_header = style == "Normal" and "|" in text
        if current == "summary":
            structure.summary = f"{structure.summary} {text.strip()}".strip()
        elif isinstance(current, tuple):
            other[current[1]].append(text.strip())
    structure.education = [Education(**e) for e in parsed["education"]]
    structure.jobs = [
        Job(company=j["company"], location=j["location"], dates=j["dates"], title=j["title"], bullets=j["source_bullets"])
        for j in parsed["jobs"]
    ]
    structure.other_sections = [OtherSection(title=t, lines=l) for t, l in other.items() if l]
    return structure


def _field(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("|", "/")).strip()


def structure_to_paras(structure: ResumeStructure) -> list:
    paras = []
    if structure.summary.strip():
        paras += [("Normal", "Summary"), ("Normal", _field(structure.summary))]
    if structure.education:
        paras.append(("Normal", "Education"))
        for e in structure.education:
            paras.append(("Normal", f"{_field(e.institution)} | {_field(e.location)}\t{_field(e.dates)}"))
            paras.append(("Normal", _field(e.degree) or " "))
    paras.append(("Normal", "Experience"))
    for j in structure.jobs:
        paras.append(("Normal", f"{_field(j.company)} | {_field(j.location)}\t{_field(j.dates)}"))
        paras.append(("Normal", _field(j.title) or " "))
        paras += [("List Paragraph", _field(b)) for b in j.bullets if _field(b)]
    for section in structure.other_sections:
        lines = [_field(l) for l in section.lines if _field(l)]
        if not lines:
            continue
        title = _field(section.title) or "Additional"
        # Other headings are always followed by List Paragraph lines, so a
        # "|" can never turn one of them into a phantom employer.
        paras.append(("Normal", title))
        paras += [("List Paragraph", l) for l in lines]
    return paras


def validate_structure(structure: ResumeStructure) -> None:
    if not structure.jobs:
        raise IngestError("Add at least one employer before saving.")
    for i, j in enumerate(structure.jobs, 1):
        if not _field(j.company):
            raise IngestError(f"Employer #{i} needs a company name.")
        if not _field(j.title):
            raise IngestError(f"Employer #{i} ({j.company}) needs a job title.")
    names = [_field(j.company).lower() for j in structure.jobs]
    if len(set(names)) != len(names):
        raise IngestError(
            "Two employers share the same company name. Add a distinguishing detail (e.g. a division) "
            "so bullets can't be attributed to the wrong one."
        )
    try:
        parsed = parse_prior_resume(structure_to_paras(structure))
    except SystemExit as exc:
        raise IngestError(str(exc)) from None
    if len(parsed["jobs"]) != len(structure.jobs):
        raise IngestError("The resume structure did not round-trip; check for unusual characters in employer lines.")


def write_resume_docx(structure: ResumeStructure, path: Path) -> None:
    validate_structure(structure)
    d = docx.Document()
    for style, text in structure_to_paras(structure):
        d.add_paragraph(text, style=style)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp.docx")
    d.save(str(tmp))
    tmp.replace(path)

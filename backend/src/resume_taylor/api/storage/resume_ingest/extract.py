"""Resume file -> text -> structure, with no Claude involved: pull the text out of a
.pdf/.docx/.txt, then parse it heuristically (section headings, date-range entry
headers, bullet markers, wrapped-line joining)."""

import re
from pathlib import Path

from resume_taylor.pipeline.sources import open_docx

from .models import Education, IngestError, Job, OtherSection, ResumeStructure

BULLET_CHARS = "•●▪◦‣∙·■□➢➤►–-*"
BULLET_RE = re.compile(rf"^\s*[{re.escape(BULLET_CHARS)}]\s+|^\s*[•●▪◦]\s*")


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            pages = PdfReader(str(path)).pages
        except Exception as exc:  # pypdf raises many types on malformed files
            raise IngestError(f"Could not read that PDF ({exc}).") from None
        text = "\n".join((page.extract_text() or "") for page in pages).strip()
        if not text:
            raise IngestError("That PDF has no selectable text (it may be a scanned image). Upload the Word version instead.")
        return text
    if suffix == ".docx":
        d = open_docx(path)
        lines = []
        for p in d.paragraphs:
            if not p.text.strip():
                continue
            is_list = p.style.name.lower().startswith("list") or p._p.pPr is not None and p._p.pPr.numPr is not None
            lines.append(("• " if is_list and not BULLET_RE.match(p.text) else "") + p.text.rstrip())
        for table in d.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    lines.append("\t".join(dict.fromkeys(cells)))
        return "\n".join(lines)
    if suffix in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="replace")
    raise IngestError("Upload a .pdf or .docx resume.")


# ---------------------------------------------------------------------------
# Heuristic parser
# ---------------------------------------------------------------------------

SECTION_ALIASES = {
    "summary": {"summary", "professional summary", "profile", "professional profile", "about", "about me",
                "career summary", "executive summary", "objective", "overview"},
    "experience": {"experience", "professional experience", "work experience", "employment",
                   "employment history", "work history", "career history", "relevant experience"},
    "education": {"education", "education & training", "education and training", "academic background"},
    "skills": {"skills", "core competencies", "technical skills", "skills & tools", "skills and tools",
               "competencies", "key skills", "areas of expertise", "tools", "technologies"},
}
OTHER_SECTIONS = {"projects", "awards", "certifications", "publications", "volunteer", "volunteering",
                  "honors", "honors & awards", "awards & recognition", "languages", "interests",
                  "leadership", "patents", "presentations", "speaking", "affiliations", "training"}

MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_POINT = rf"(?:{MONTH}\s+)?(?:\d{{1,2}}/)?(?:19|20)\d{{2}}"
DATE_RANGE_RE = re.compile(
    rf"({DATE_POINT}\s*(?:-|–|—|to|through)\s*(?:{DATE_POINT}|present|current|now|today))",
    re.IGNORECASE,
)
SINGLE_DATE_RE = re.compile(rf"({DATE_POINT})\s*$", re.IGNORECASE)


def _heading_key(line: str) -> str | None:
    key = re.sub(r"[:#*_]+", "", line).strip().lower()
    key = re.sub(r"\s+", " ", key)
    if not key or len(key) > 40:
        return None
    for section, aliases in SECTION_ALIASES.items():
        if key in aliases:
            return section
    if key in OTHER_SECTIONS:
        return "other"
    return None


def _split_place(text: str) -> tuple:
    """'Company | City, ST' / 'Company, City, ST' / 'Company – City' -> (company, location)."""
    text = text.strip(" \t|,-–—")
    for sep in ("|", "\t", " – ", " — ", " - ", " · ", " • "):
        if sep in text:
            left, _, right = text.partition(sep)
            return left.strip(" \t|,"), right.strip(" \t|,")
    # "Company, City, ST" or "Company, City, State"
    match = re.match(r"^(.+?),\s*([^,]+,\s*(?:[A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?))$", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text, ""


def _is_bullet(line: str) -> bool:
    return bool(BULLET_RE.match(line))


def _strip_bullet(line: str) -> str:
    return BULLET_RE.sub("", line, count=1).strip()


def _join_wrapped(prev: str, nxt: str) -> str:
    if prev.endswith("-") and nxt[:1].islower():
        return prev[:-1] + nxt
    return f"{prev} {nxt}"


def _parse_entries(lines: list, kind: str) -> list:
    """Entries of {head, dates, detail, bullets} from one section's lines."""
    entries = []
    current = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if _is_bullet(line):
            if current is None:
                current = {"head": "", "dates": "", "detail": "", "bullets": []}
                entries.append(current)
            current["bullets"].append(_strip_bullet(line))
            current["marked"] = True
            continue
        match = DATE_RANGE_RE.search(line) or (SINGLE_DATE_RE.search(line) if kind == "education" else None)
        if match:
            head = (line[: match.start()] + " " + line[match.end():]).strip(" \t|,-–—()")
            if not head and current is not None and not current["bullets"] and not current["dates"]:
                current["dates"] = match.group(1).strip()  # dates on their own line under the header
                continue
            current = {"head": head, "dates": match.group(1).strip(), "detail": "", "bullets": []}
            entries.append(current)
            continue
        if current is None:
            current = {"head": line, "dates": "", "detail": "", "bullets": []}
            entries.append(current)
        elif current["bullets"] and (
            current.get("marked")
            or line[:1].islower()
            or not current["bullets"][-1].rstrip().endswith((".", "!", "?"))
        ):
            # A wrapped continuation of the previous bullet (PDF line breaks).
            # With bullet glyphs every unmarked line is one; without them, a
            # line only continues a bullet that hasn't finished its sentence.
            current["bullets"][-1] = _join_wrapped(current["bullets"][-1], line)
        elif not current["detail"]:
            current["detail"] = line
        elif not current["head"]:
            current["head"] = line
        else:
            # Past the title line, unmarked lines are bullets whose glyphs
            # didn't survive text extraction.
            current["bullets"].append(line)
    return [e for e in entries if e["head"] or e["bullets"]]


def _looks_like_place(text: str) -> bool:
    return bool(_split_place(text)[1])


def _orient(head: str, detail: str) -> tuple:
    """Return (place line, title line). Some layouts lead with the title and
    put "Company | City" underneath; swap those back."""
    if not _looks_like_place(head) and _looks_like_place(detail):
        return detail, head
    return head, detail


def heuristic_parse(text: str) -> ResumeStructure:
    sections: dict = {}
    order: list = []
    other_titles: dict = {}
    current = "_header"
    sections[current] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        key = _heading_key(line) if line.strip() and not _is_bullet(line) else None
        if key:
            current = key if key != "other" else f"other:{line.strip().rstrip(':').strip()}"
            if key == "other":
                other_titles[current] = line.strip().rstrip(":").strip().title()
            sections.setdefault(current, [])
            order.append(current)
            continue
        sections[current].append(line)

    structure = ResumeStructure(source="heuristic", raw_text=text)
    structure.contact_lines = [l.strip() for l in sections.get("_header", []) if l.strip()]
    structure.summary = " ".join(
        _strip_bullet(l) if _is_bullet(l) else l.strip() for l in sections.get("summary", []) if l.strip()
    )

    for e in _parse_entries(sections.get("experience", []), "experience"):
        place, title = _orient(e["head"], e["detail"])
        company, location = _split_place(place)
        structure.jobs.append(
            Job(company=company, location=location, dates=e["dates"], title=title, bullets=e["bullets"])
        )
    for e in _parse_entries(sections.get("education", []), "education"):
        institution, location = _split_place(e["head"])
        degree = e["detail"] or " ".join(e["bullets"])
        structure.education.append(
            Education(institution=institution, location=location, dates=e["dates"], degree=degree)
        )
    if sections.get("skills"):
        structure.other_sections.append(
            OtherSection(title="Skills", lines=[_strip_bullet(l) for l in sections["skills"] if l.strip()])
        )
    for key in order:
        if key.startswith("other:") and sections.get(key):
            structure.other_sections.append(
                OtherSection(title=other_titles[key], lines=[_strip_bullet(l) for l in sections[key] if l.strip()])
            )
    return structure

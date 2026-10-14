"""Post-render ATS checks: does the finished file read back the way a parser will see it?
Everything routes through warn() so it lands in the report; nothing here changes the file."""

import re
from pathlib import Path

import docx

from ..runtime import warn

# "Jan 2020", "January 2020", "01/2020", "2020", with an optional "- Present" style end.
_DATE_TOKEN = r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?\d{4}"
DATE_RANGE_RE = re.compile(
    rf"^{_DATE_TOKEN}(?:\s*(?:-|–|to)\s*(?:{_DATE_TOKEN}|Present|Current))?$", re.IGNORECASE
)
HEADINGS = ("Summary", "Experience", "Skills")


def lint_docx(path: Path, data: dict) -> None:
    """Structure checks on the .docx: no tables or images, real headings, parseable dates."""
    d = docx.Document(str(path))
    if d.tables:
        warn("the resume contains a table; many ATS parsers scramble table content.")
    if d.inline_shapes:
        warn("the resume contains an image; ATS parsers ignore images.")
    for section in d.sections:
        if any(p.text.strip() for p in section.header.paragraphs + section.footer.paragraphs):
            warn("the resume has header/footer text; some ATS parsers skip headers and footers.")

    headings = {p.text.strip() for p in d.paragraphs if p.style.name.startswith("Heading")}
    missing = [h for h in HEADINGS if h not in headings and _expects(h, data)]
    if missing:
        warn(f"section heading(s) {', '.join(missing)} are not real Word headings, so a parser may not find them.")

    for job in data.get("experience", []):
        dates = (job.get("dates") or "").strip()
        if not dates:
            warn(f"{job.get('company', 'a role')} has no dates; ATS tenure and recency scoring needs them.")
        elif not DATE_RANGE_RE.match(dates):
            warn(f"dates '{dates}' for {job.get('company', 'a role')} aren't in a standard 'Mon YYYY - Mon YYYY' form.")


def _expects(heading: str, data: dict) -> bool:
    key = {"Summary": "summary", "Experience": "experience", "Skills": "skills"}[heading]
    return bool(data.get(key))


def lint_pdf_text(path: Path, data: dict) -> None:
    """Round-trip the PDF through a text extractor, as an ATS would, and confirm the key
    fields survive and read in order (name before email before the first heading)."""
    try:
        from pypdf import PdfReader

        text = "\n".join((page.extract_text() or "") for page in PdfReader(str(path)).pages)
    except Exception as exc:
        warn(f"could not read text back from {path.name} ({exc}); verify it is not an image-only PDF.")
        return
    if len(text.strip()) < 200:
        warn(f"{path.name} has almost no extractable text; an ATS would see an empty resume.")
        return

    flat = re.sub(r"\s+", " ", text)
    name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
    for label, value in (("name", name), ("email", data.get("email", ""))):
        if value and value.lower() not in flat.lower():
            warn(f"the {label} '{value}' was not found in the PDF's extracted text.")
    for job in data.get("experience", []):
        company = job.get("company", "")
        if company and company.lower() not in flat.lower():
            warn(f"employer '{company}' was not found in the PDF's extracted text.")
    positions = [flat.lower().find(h.lower()) for h in ("summary", "experience")]
    if all(p >= 0 for p in positions) and positions != sorted(positions):
        warn("the PDF's text order is scrambled (Experience appears before Summary).")

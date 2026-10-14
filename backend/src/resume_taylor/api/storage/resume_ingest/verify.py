"""Check every parsed field against the uploaded file's text, so anything not found
verbatim is flagged for the review screen."""

import re

from .extract import BULLET_CHARS
from .models import Flag, ResumeStructure


def _norm(text: str) -> str:
    text = text.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(rf"[{re.escape(BULLET_CHARS)}]", " ", text)
    text = re.sub(r"-\s*\n\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> list:
    return re.findall(r"[a-z0-9$%+.']+", _norm(text))


def _found(needle: str, haystack_norm: str, haystack_words: set) -> bool:
    n = _norm(needle)
    if not n or n in haystack_norm:
        return True
    words = _words(needle)
    if not words:
        return True
    hits = sum(1 for w in words if w in haystack_words)
    return hits / len(words) >= 0.9


def verify(structure: ResumeStructure, raw_text: str) -> ResumeStructure:
    """Flag any field that doesn't appear in the uploaded file's text."""
    hay = _norm(raw_text)
    hay_words = set(_words(raw_text))
    flags = []
    for i, j in enumerate(structure.jobs):
        for field in ("company", "title", "dates", "location"):
            value = getattr(j, field)
            if value and not _found(value, hay, hay_words):
                flags.append(Flag(path=f"jobs.{i}.{field}", message=f"'{value}' was not found in the uploaded file."))
        for k, b in enumerate(j.bullets):
            if not _found(b, hay, hay_words):
                flags.append(Flag(path=f"jobs.{i}.bullets.{k}", message="This bullet doesn't match the uploaded file verbatim."))
        if not j.title:
            flags.append(Flag(path=f"jobs.{i}.title", message="No job title was detected. Please add it."))
        if not j.dates:
            flags.append(Flag(path=f"jobs.{i}.dates", message="No dates were detected. Please add them."))
    for i, e in enumerate(structure.education):
        for field in ("institution", "degree", "dates"):
            value = getattr(e, field)
            if value and not _found(value, hay, hay_words):
                flags.append(Flag(path=f"education.{i}.{field}", message=f"'{value}' was not found in the uploaded file."))
    structure.flags = flags
    return structure

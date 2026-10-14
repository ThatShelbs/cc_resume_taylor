"""Writing-quality guards: warn-level checks for the things a recruiter notices even when
every fact is true (generic buzzwords, uniform bullet shapes, weak or repeated openers,
overlong bullets). Unlike guards.py these never change facts; the only edit is
normalize_text(), which swaps typographic characters for plain ones."""

import re
from statistics import pstdev

from .runtime import warn

_ZERO_WIDTH_RE = re.compile("[​‌‍⁠﻿­]")
_QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " "})


def normalize_text(text: str) -> str:
    """Strip invisible characters and swap curly quotes / ellipsis for plain ones. Invisible
    characters can break ATS keyword matching; the rest are common LLM output artifacts."""
    text = _ZERO_WIDTH_RE.sub("", text)
    return text.translate(_QUOTE_MAP).replace("…", "...")


# Phrases that read as generic or machine-written. Matched as whole words, case-insensitive.
AI_TELL_PHRASES = [
    "spearheaded",
    "orchestrated",
    "delve",
    "tapestry",
    "seamless(?:ly)?",
    "robust",
    "cutting-edge",
    "state-of-the-art",
    "results-driven",
    "detail-oriented",
    "team player",
    "proven track record",
    "passionate about",
    "dynamic",
    "synergy|synergies",
    "adept at",
    "well-versed",
    "in today's",
    "fast-paced",
    "go-getter",
    "think outside the box",
    "best-in-class",
    "holistic",
    "transformative",
    "not just .{3,40} but",
]
AI_TELL_RE = re.compile(r"(?<!\w)(?:" + "|".join(AI_TELL_PHRASES) + r")(?!\w)", re.IGNORECASE)

WEAK_OPENER_RE = re.compile(
    r"^(responsible for|helped|assisted|worked on|worked with|tasked with|duties included|"
    r"involved in|participated in|was |were )",
    re.IGNORECASE,
)

MIN_BULLETS, MAX_BULLETS = 2, 6
MAX_BULLET_WORDS = 40
MIN_SUMMARY_SENTENCES, MAX_SUMMARY_SENTENCES = 2, 4


def _first_word(text: str) -> str:
    match = re.match(r"[A-Za-z][A-Za-z'-]*", text.strip())
    return match.group(0).lower() if match else ""


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def warn_ai_tells(summary: str, bullets_by_company: dict) -> None:
    """Flag generic buzzword phrasing in the summary and bullets."""
    sections = [("the summary", summary)]
    sections += [(f"a bullet under {c}", b) for c, bs in bullets_by_company.items() for b in bs]
    for label, text in sections:
        hits = sorted({m.group(0).lower() for m in AI_TELL_RE.finditer(text)})
        if hits:
            warn(f"{label} uses generic phrasing ({', '.join(hits)}); reword it plainly: {text[:80]}...")


def warn_bullet_quality(summary: str, bullets_by_company: dict) -> None:
    """Flag structure problems: weak/repeated openers, overlong bullets, bullet counts,
    summary length, and bullets that all share one rhythm."""
    sentences = _sentence_count(summary)
    if sentences and not MIN_SUMMARY_SENTENCES <= sentences <= MAX_SUMMARY_SENTENCES:
        warn(f"the summary has {sentences} sentence(s); aim for {MIN_SUMMARY_SENTENCES}-{MAX_SUMMARY_SENTENCES}.")

    all_bullets = []
    for company, bullets in bullets_by_company.items():
        if bullets and not MIN_BULLETS <= len(bullets) <= MAX_BULLETS:
            warn(f"{company} has {len(bullets)} bullet(s); 3-5 reads best (older roles can have fewer).")
        openers = [_first_word(b) for b in bullets]
        for verb in sorted({v for v in openers if v and openers.count(v) > 1}):
            warn(f"{company}: {openers.count(verb)} bullets start with '{verb}'; vary the opening verbs.")
        for bullet in bullets:
            if WEAK_OPENER_RE.match(bullet):
                warn(f"a bullet under {company} opens weakly; lead with what you did: {bullet[:80]}...")
            words = len(bullet.split())
            if words > MAX_BULLET_WORDS:
                warn(f"a bullet under {company} is {words} words; tighten it to two lines: {bullet[:80]}...")
        all_bullets.extend(bullets)

    if len(all_bullets) >= 6:
        lengths = [len(b.split()) for b in all_bullets]
        if pstdev(lengths) < 2.5:
            warn("every bullet is nearly the same length; mix short and longer bullets so it reads as written by a person.")
        ends_with_number = sum(bool(re.search(r"\d[%\w$+,.]*\W*$", b)) for b in all_bullets)
        if ends_with_number >= 0.8 * len(all_bullets):
            warn("nearly every bullet ends on a metric; let some end on the action or scope instead.")
        openers = [_first_word(b) for b in all_bullets]
        repeated = sorted({v for v in openers if v and openers.count(v) >= 3})
        if repeated:
            warn(f"the resume reuses the same opening verb(s) across roles: {', '.join(repeated)}.")


def find_tell_bullets(bullets_by_company: dict) -> list:
    """(company, bullet) pairs that trip the buzzword check, for the optional voice pass."""
    return [(c, b) for c, bs in bullets_by_company.items() for b in bs if AI_TELL_RE.search(b)]


def warn_unsupported_title(summary: str, target_title: str, source_text: str) -> None:
    """The summary may describe the candidate's work in the posting's terms, but must not
    adopt the posting's title if that title appears nowhere in the candidate's own material."""
    title = target_title.strip().lower()
    if len(title) >= 4 and title in summary.lower() and title not in source_text.lower():
        warn(f"the summary uses the posting's title '{target_title}', which isn't a title in your materials; confirm it describes you.")


OLD_ROLE_YEARS = 12
MAX_RECENT_BULLETS, MAX_OLD_BULLETS = 5, 2
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _end_year(dates: str, this_year: int) -> int | None:
    if re.search(r"present|current|now", dates, re.IGNORECASE):
        return this_year
    years = [int(y) for y in _YEAR_RE.findall(dates)]
    return max(years) if years else None


def limit_bullets_by_recency(bullets_by_company: dict, jobs: list, this_year: int) -> dict:
    """Cap bullets per role: recent roles keep up to 5, roles that ended 12+ years ago keep
    2. Bullets arrive ordered most relevant first, so trimming keeps the best. An employer
    is never dropped entirely."""
    dates = {job["company"]: job.get("dates", "") for job in jobs}
    trimmed = {}
    for company, bullets in bullets_by_company.items():
        end = _end_year(dates.get(company, ""), this_year)
        cap = MAX_OLD_BULLETS if end is not None and this_year - end >= OLD_ROLE_YEARS else MAX_RECENT_BULLETS
        if len(bullets) > cap:
            print(f"  Trimmed {company} from {len(bullets)} to {cap} bullets (recency weighting).")
        trimmed[company] = bullets[:cap]
    return trimmed

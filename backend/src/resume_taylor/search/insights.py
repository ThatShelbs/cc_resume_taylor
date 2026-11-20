"""What the job search learned about one posting, as hints for the resume tailoring call.

The search already judged fit, found gaps and mapped each posting requirement against the person's own
evidence. Tailoring used to start from scratch; this turns that result into a short labeled block
(`--posting-insights`). It is emphasis only: tailoring still cites fact ids and never adds a claim."""

MAX_IDS = 8
MAX_TERMS = 10


def _terms(requirements: list[dict], status: str) -> list[str]:
    return [r["term"] for r in requirements if r.get("status") == status and r.get("term")][:MAX_TERMS]


def posting_insights_text(posting: dict) -> str:
    fit = posting.get("fit") or {}
    reqs = posting.get("requirements") or []
    if not fit and not reqs:
        return ""
    ids: list[str] = []
    for sub in (fit.get("subscores") or {}).values():
        for ev in sub.get("evidence") or []:
            if ev not in ids and len(ids) < MAX_IDS and str(ev).startswith("F"):
                ids.append(str(ev))
    lines = [
        "JOB SEARCH HINTS (what the search found when it scored this posting. Emphasis only, not facts: "
        "cite fact-bank ids as usual, and never add a figure, tool or claim they do not support):"
    ]
    if fit.get("angle"):
        lines.append(f"Why this candidate fits: {fit['angle']}")
    if ids:
        lines.append("Facts the search matched to this role: " + ", ".join(ids))
    covered, positionable = _terms(reqs, "covered"), _terms(reqs, "positionable")
    if covered:
        lines.append("Requirements the candidate's evidence supports: " + ", ".join(covered))
    if positionable:
        lines.append("Requirements to position through related real work, not claim directly: " + ", ".join(positionable))
    gaps = [*(fit.get("gaps") or []), *_terms(reqs, "gap")]
    if gaps:
        lines.append("Gaps (do not claim these): " + "; ".join(dict.fromkeys(gaps)))
    return "\n".join(lines) if len(lines) > 1 else ""

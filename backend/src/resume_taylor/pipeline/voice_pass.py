"""Optional voice pass (--voice-pass): rewrite only the bullets that trip the generic-phrasing
check, in the candidate's own wording. The rewrite must keep every number and not grow, so
no fact can change; anything that fails those checks is discarded and the original kept."""

import json
import re

from ..claude_cli import find_claude_cli, invoke_claude
from .guards_quality import AI_TELL_RE
from .runtime import warn

VOICE_SYSTEM_PROMPT = """You are a line editor for resume bullets. You change wording only, \
never facts. For each numbered bullet, rewrite it in plain, concrete language that sounds \
like the candidate's own sample bullets. Keep every number, tool, employer-specific detail, \
and claim exactly as is; add nothing; do not make it longer. Replace words like \
"spearheaded", "leveraged", "orchestrated", "seamless", "robust" with plain verbs. Reply \
with exactly one JSON object and nothing else: {"rewrites": {"0": "rewritten bullet", ...}}. \
Omit a number if the bullet is already fine."""

_NUMBER_RE = re.compile(r"\d[\d,.]*")


def _numbers(text: str) -> list:
    return sorted(n.rstrip(".,") for n in _NUMBER_RE.findall(text))


def _acceptable(original: str, rewrite: str) -> bool:
    return (
        bool(rewrite.strip())
        and _numbers(original) == _numbers(rewrite)
        and len(rewrite.split()) <= len(original.split()) + 3
        and "—" not in rewrite
        and not AI_TELL_RE.search(rewrite)
    )


def apply_voice_pass(flagged: list, style_samples: list, model: str | None, effort: str | None) -> dict:
    """flagged: [(company, bullet)]. Returns {(company, original bullet): rewritten bullet}
    for the rewrites that passed the checks."""
    if not flagged:
        return {}
    samples = "\n".join(f"- {s}" for s in style_samples[:12]) or "(none)"
    numbered = "\n".join(f"{i}. {bullet}" for i, (_, bullet) in enumerate(flagged))
    try:
        raw = invoke_claude(
            find_claude_cli(),
            VOICE_SYSTEM_PROMPT,
            f"CANDIDATE'S OWN BULLETS (voice samples):\n{samples}\n\nBULLETS TO REWRITE:\n{numbered}",
            model,
            effort,
        )
    except SystemExit as exc:
        warn(f"voice pass skipped ({exc}); kept the original bullets.")
        return {}
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        rewrites = json.loads(match.group(0)).get("rewrites", {}) if match else {}
    except (json.JSONDecodeError, AttributeError):
        rewrites = {}
    out = {}
    for key, text in (rewrites if isinstance(rewrites, dict) else {}).items():
        try:
            company, original = flagged[int(key)]
        except (ValueError, IndexError):
            continue
        if isinstance(text, str) and _acceptable(original, text.strip()):
            out[(company, original)] = text.strip()
    print(f"  Voice pass rewrote {len(out)} of {len(flagged)} flagged bullet(s).")
    return out

"""Claude calls for the search engine. Wraps `invoke_claude` so a failed call returns None
instead of exiting the whole run, and parses JSON out of the reply."""

import json
import re

from resume_taylor.claude_cli import find_claude_cli, invoke_claude, strip_code_fence
from resume_taylor.pipeline.runtime import warn

WEB_TOOLS = ("WebSearch", "WebFetch")


def parse_json(text: str):
    """The first JSON object or array in a reply (code fences and chatter tolerated)."""
    if not text:
        return None
    text = strip_code_fence(text)
    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                continue
    return None


def ask(system: str, user: str, *, tools: tuple[str, ...] = (), model: str | None = None,
        effort: str | None = None, timeout: int | None = None, label: str = "Claude call"):
    """One Claude call, parsed as JSON. None on any failure (the failure is logged as a warning)."""
    try:
        raw = invoke_claude(find_claude_cli(), system, user, model=model, effort=effort, tools=tools, timeout=timeout)
    except SystemExit as exc:
        warn(f"{label} failed: {str(exc).splitlines()[0][:200] if str(exc) else 'unknown error'}")
        return None
    data = parse_json(raw)
    if data is None:
        warn(f"{label} returned something that was not JSON.")
    return data

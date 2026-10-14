"""The Claude fallback: one verbatim-extraction call, used only when the deterministic
parser finds no employers. Runs as a subprocess job (see __main__.py)."""

import json
import re

from resume_taylor.claude_cli import find_claude_cli, invoke_claude, strip_code_fence

from .models import IngestError, ResumeStructure

AI_SYSTEM_PROMPT = """You are a verbatim resume-structure extraction tool. You never \
rewrite, summarize, improve, merge, or invent anything. Copy every value character for \
character from the resume text you are given.

Return exactly this JSON shape, wrapped in <RESUME_STRUCTURE> and </RESUME_STRUCTURE> \
tags, with nothing else in your reply:
<RESUME_STRUCTURE>
{"summary": "summary paragraph or empty string",
 "education": [{"institution": "", "location": "", "dates": "", "degree": ""}],
 "jobs": [{"company": "", "location": "", "dates": "", "title": "", "bullets": ["..."]}],
 "other_sections": [{"title": "Skills", "lines": ["..."]}],
 "contact_lines": ["name", "email", "phone", "..."]}
</RESUME_STRUCTURE>

Rules: one "jobs" entry per employer and role, most recent first, in the order they \
appear. If a person held several titles at one employer, make one entry per title with \
the same company. Leave a field as "" when it is not in the text; never guess."""


def ai_parse(text: str) -> ResumeStructure:
    claude_bin = find_claude_cli()
    raw = ""
    for attempt in range(2):
        raw = invoke_claude(claude_bin, AI_SYSTEM_PROMPT, text)
        match = re.search(r"<RESUME_STRUCTURE>(.*?)</RESUME_STRUCTURE>", raw, re.DOTALL)
        try:
            data = json.loads(strip_code_fence(match.group(1) if match else raw))
            structure = ResumeStructure(**data)
            structure.source = "ai"
            return structure
        except (json.JSONDecodeError, ValueError, TypeError):
            print(f"  Attempt {attempt + 1} did not return a usable structure, retrying...")
    raise IngestError("Claude could not structure this resume. Try the Word version, or fill in the form by hand.")

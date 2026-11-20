"""A short, sourced brief on each company behind the final results: what it is, what changed there
recently, and what the posting says the team needs. One batched Claude call with web tools, cached per
company for a week. Python keeps only claims that carry a link to a real source (never a job board), so
the brief can be checked in one click and nothing in it is the model's unsupported say-so."""

import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

from resume_taylor.config import JOB_FIT_SKILL_PATH
from resume_taylor.pipeline.prompts import load_skill

from . import claude
from .normalize import norm_company

CACHE_DAYS = 7
MAX_SIGNALS = 2
BOARD_HOSTS = ("linkedin.", "indeed.", "glassdoor.", "ziprecruiter.", "monster.", "simplyhired.", "builtin.", "google.com/search")

CONTRACT = """

Task: RESEARCH. Reply with JSON only:
{"companies": [{"name": str, "snapshot": str, "snapshot_url": str,
 "signals": [{"text": str, "date": "YYYY-MM or empty", "url": str}], "needs": str}]}"""


def _good_url(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith(("http://", "https://")) and bool(urlsplit(u).netloc) and not any(h in u for h in BOARD_HOSTS)


def _clip(text, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def sanitize(entry: dict) -> dict | None:
    """The sourced parts of one company's brief; None when nothing in it can be traced to a link."""
    if not isinstance(entry, dict):
        return None
    snapshot_url = str(entry.get("snapshot_url") or "").strip()
    snapshot = _clip(entry.get("snapshot"), 320) if _good_url(snapshot_url) else ""
    signals = []
    for s in entry.get("signals") or []:
        if isinstance(s, dict) and _clip(s.get("text"), 220) and _good_url(str(s.get("url") or "")):
            signals.append({"text": _clip(s["text"], 220), "date": _clip(s.get("date"), 10), "url": str(s["url"]).strip()})
    needs = _clip(entry.get("needs"), 320)
    if not (snapshot or signals or needs):
        return None
    return {"snapshot": snapshot, "snapshot_url": snapshot_url if snapshot else "", "signals": signals[:MAX_SIGNALS], "needs": needs}


def _cache_path(cache_dir: Path | None, company: str) -> Path | None:
    return Path(cache_dir) / "research" / f"{norm_company(company) or 'company'}.json" if cache_dir else None


def _cached(path: Path | None) -> dict | None:
    try:
        if path and path.exists() and time.time() - path.stat().st_mtime < CACHE_DAYS * 86400:
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return None


def research_results(results: list[dict], *, cache_dir: Path | None = None, model: str | None = None,
                     effort: str | None = None, progress=print) -> int:
    """Attach `research` to each result that gets a sourced brief. Returns how many did."""
    wanted: dict[str, dict] = {}  # normalized company -> first posting there
    for p in results:
        if not p.get("agency"):
            wanted.setdefault(norm_company(p["company"]), p)
    fresh: dict[str, dict] = {}
    todo = []
    for key, p in wanted.items():
        hit = _cached(_cache_path(cache_dir, p["company"]))
        if hit is not None:
            fresh[key] = hit
        else:
            todo.append(p)
    if todo:
        listing = "\n\n".join(
            f"- {p['company']}\n  Role: {p['title']}\n  Posting excerpt: {_clip(p.get('description_text'), 700)}" for p in todo
        )
        progress(f"Researching {len(todo)} companies...")
        reply = claude.ask(
            load_skill(JOB_FIT_SKILL_PATH) + CONTRACT,
            "Research each company with web search. Cite a source URL for every fact; leave a field empty rather "
            "than guess. `needs` comes from the posting excerpt alone.\n\n" + listing,
            tools=claude.WEB_TOOLS, model=model, effort=effort, label="Company research",
        )
        by_name = {norm_company(str(x.get("name", ""))): x for x in ((reply or {}).get("companies") or []) if isinstance(x, dict)} if isinstance(reply, dict) else {}
        for p in todo:
            brief = sanitize(by_name.get(norm_company(p["company"]), {}))
            if brief:
                fresh[norm_company(p["company"])] = brief
                path = _cache_path(cache_dir, p["company"])
                if path:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(brief), encoding="utf-8")
    n = 0
    for p in results:
        brief = fresh.get(norm_company(p["company"]))
        if brief:
            p["research"] = brief
            n += 1
    return n

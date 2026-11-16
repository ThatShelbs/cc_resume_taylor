"""The job-board sweep: expand the user's titles, skills and places into queries, then let Claude
(with web search) run site-targeted searches across LinkedIn, Indeed, Glassdoor and the open
web. Results are *leads*; `crosswalk` traces them back to the company's own careers page.
Indeed and Glassdoor pages are never fetched by this code."""

from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from resume_taylor.config import CAREER_DISCOVERY_SKILL_PATH
from resume_taylor.pipeline.prompts import load_skill

from . import claude, geo
from .candidate import Candidate
from .normalize import days_ago_to_iso, new_posting, parse_posted_ago
from .prefs import Preferences

QUERY_CAP = {"quick": 10, "standard": 25, "deep": 60}
GROUP_SIZE = 5
WORKERS = 4

SWEEP_CONTRACT = """

Task: SWEEP. Reply with JSON only:
{"hits": [{"title": str, "company": str, "location": str, "url": str, "posted_hint": str}]}
Return at most 25 hits per call. Only roles at director level or equivalent unless told otherwise."""


def expand_queries(prefs: Preferences, cand: Candidate, depth: str) -> list[dict]:
    """titles x skills x places, most valuable first, trimmed to the depth's cap."""
    titles = prefs.titles or [t for t in cand.titles[:2]] or ["director"]
    skills = (prefs.skill_terms or cand.skills)[:6]
    places: list[str] = []
    home = geo.parse_location(prefs.home_location) if prefs.home_location else None
    if home and home["city"]:
        places.append(f"{home['city']}, {home['state']}")
    places += [c for c in prefs.allowed_cities if c not in places][:3]
    places.append("Remote (United States)")
    if prefs.remote_states:
        places.append("Remote " + " or ".join(prefs.remote_states[:3]))
    queries: list[dict] = []
    for t in titles:  # plain title in every place first
        for place in places:
            queries.append({"q": t, "location": place})
    for s in skills:
        for t in titles:
            for place in places[:2] + places[-1:]:
                queries.append({"q": f"{t} {s}", "location": place})
    seen, uniq = set(), []
    for q in queries:
        key = (q["q"].lower(), q["location"].lower())
        if key not in seen:
            seen.add(key)
            uniq.append(q)
    return uniq[:QUERY_CAP.get(depth, 25)]


def _source_of(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    for name in ("linkedin", "indeed", "glassdoor", "ziprecruiter", "builtin"):
        if name in host:
            return name
    return "web"


def hits_to_postings(hits: list[dict]) -> list[dict]:
    out = []
    for h in hits:
        if not isinstance(h, dict) or not h.get("title") or not h.get("company") or not h.get("url"):
            continue
        days = parse_posted_ago(str(h.get("posted_hint", "")))
        src = _source_of(str(h["url"]))
        out.append(new_posting(
            source=src, ats="", company=str(h["company"]).strip(), title=str(h["title"]).strip(),
            locations=[str(h.get("location", ""))], external_id=str(h["url"]), url=str(h["url"]), apply_url=str(h["url"]),
            posted_at=days_ago_to_iso(days) if days is not None else None, posted_at_source="parsed" if days is not None else "",
            aggregator_only=True,
        ))
    return out


def _run_group(group: list[dict], prefs: Preferences, model, effort) -> list[dict]:
    lines = "\n".join(f"- {q['q']} | {q['location']}" for q in group)
    user = (
        f"Search for roles posted in the last {prefs.recency_days} days. Queries (title | place):\n{lines}\n"
        "Use site-targeted searches on linkedin.com/jobs/view, indeed.com/viewjob and glassdoor.com/job-listing, "
        "and also search the open web for the employer's own posting."
    )
    reply = claude.ask(load_skill(CAREER_DISCOVERY_SKILL_PATH) + SWEEP_CONTRACT, user, tools=claude.WEB_TOOLS,
                       model=model, effort=effort, label="Job board sweep")
    return (reply or {}).get("hits", []) if isinstance(reply, dict) else []


def claude_sweep(queries: list[dict], prefs: Preferences, *, model=None, effort=None, progress=print) -> list[dict]:
    groups = [queries[i:i + GROUP_SIZE] for i in range(0, len(queries), GROUP_SIZE)]
    hits: list[dict] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, found in enumerate(pool.map(lambda g: _run_group(g, prefs, model, effort), groups), 1):
            hits.extend(found)
            progress(f"Board sweep: query group {n} of {len(groups)}, {len(found)} leads")
    return hits_to_postings(hits)

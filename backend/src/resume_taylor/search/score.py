"""Fit scoring. Claude extracts facts and judges four evidence-backed subscores in batches
(rules in the job-fit-scoring skill); Python validates everything it said (quotes must be
verbatim, fact ids must exist, numbers are clamped) and computes the rest of the 100 points.

  skills 25 + leadership 15 + domain 10 + seniority realism 15      Claude, with quotes
  freshness 15 + comp 10 + location 5 + direct-source edge 5        Python
"""

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from resume_taylor.config import JOB_FIT_SKILL_PATH
from resume_taylor.pipeline.coverage import contains_term
from resume_taylor.pipeline.posting_analysis import build_requirement_map
from resume_taylor.pipeline.prompts import load_skill

from . import claude, freshness
from .candidate import Candidate
from .normalize import norm_title, with_pay
from .prefs import Preferences

BATCH = 5
WORKERS = 3
DESC_LIMIT = 6000
THIN_DESCRIPTION = 300
CAPS = {"skills": 25, "leadership": 15, "domain": 10, "seniority_realism": 15}

CONTRACT = """

Task: SCORE. Reply with JSON only:
{"postings": [{"id": str, "work_mode": str, "days_onsite": int|null, "remote_states": [str],
 "years_required": int|null, "people_management": "yes|no|unknown", "team_size": str,
 "closes_at": str|null, "pay_min": number|null, "pay_max": number|null, "pay_evidence": str,
 "work_mode_evidence": str, "bonus_equity": str, "must_have": [str], "tools": [str],
 "competencies": [str], "seniority": str,
 "skills": {"score": int, "quotes": [str], "evidence": [str]},
 "leadership": {"score": int, "quotes": [str], "evidence": [str]},
 "domain": {"score": int, "quotes": [str], "evidence": [str]},
 "seniority_realism": {"score": int, "quotes": [str], "evidence": [str]},
 "gaps": [str], "angle": str, "verdict": str}]}"""


def _norm_space(s: str) -> str:
    s = (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def verbatim(quote: str, text: str) -> bool:
    q = _norm_space(quote)
    return len(q) >= 8 and q in _norm_space(text)


# -- cheap ranking ---------------------------------------------------------------------------

def cheap_rank(p: dict, cand: Candidate, prefs: Preferences, now: datetime | None = None) -> float:
    """Free ordering used to choose which postings are worth a Claude call."""
    score = float(freshness.points(freshness.age_days(p, now)))
    title_words = {w for t in (prefs.titles or cand.titles) for w in norm_title(t).split() if len(w) > 3}
    score += 4 * len(title_words & set(norm_title(p["title"]).split()))
    terms = {*(prefs.skill_terms or []), *cand.skills[:80], *cand.tags[:40]}
    desc = (p.get("description_text") or "").lower()
    score += 1.5 * min(20, sum(1 for t in terms if t and contains_term(t, desc)))
    if not p.get("aggregator_only"):
        score += 3
    return score


# -- Claude batches ---------------------------------------------------------------------------

def _posting_block(p: dict) -> str:
    return (
        f"=== POSTING id={p['id']} ===\nTitle: {p['title']}\nCompany: {p['company']}\n"
        f"Locations: {'; '.join(p.get('locations', [])) or 'not stated'}\nPay text: {p.get('pay_text') or 'not stated'}\n"
        f"Description:\n{(p.get('description_text') or '(no description available)')[:DESC_LIMIT]}\n"
    )


def _score_group(group: list[dict], cand: Candidate, model, effort) -> dict:
    user = f"CANDIDATE (tier: {cand.tier}):\n{cand.summary()}\n\n" + "\n".join(_posting_block(p) for p in group)
    reply = claude.ask(load_skill(JOB_FIT_SKILL_PATH) + CONTRACT, user, model=model, effort=effort,
                       label="Fit scoring")
    items = (reply or {}).get("postings", []) if isinstance(reply, dict) else []
    return {str(i.get("id")): i for i in items if isinstance(i, dict)}


def score_postings(postings: list[dict], cand: Candidate, *, model=None, effort=None, progress=print) -> dict:
    groups = [postings[i:i + BATCH] for i in range(0, len(postings), BATCH)]
    out: dict = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, got in enumerate(pool.map(lambda g: _score_group(g, cand, model, effort), groups), 1):
            out.update(got)
            progress(f"Scoring: {min(n * BATCH, len(postings))} of {len(postings)} postings read")
    return out


# -- validation and the Python-computed points --------------------------------------------------

def _clean_sub(raw, key: str, posting_text: str, cand: Candidate, thin: bool) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    try:
        score = int(round(float(raw.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(CAPS[key], score))
    quotes = [q for q in raw.get("quotes", []) if isinstance(q, str) and verbatim(q, posting_text)][:3]
    evidence: list[str] = []
    for e in raw.get("evidence", []) if cand.has_evidence else []:
        if not isinstance(e, str):
            continue
        ids = re.findall(r"\bF\d+\b", e.upper())
        if ids and cand.fact_bank:
            evidence += [i for i in ids if i in cand.fact_bank]
        elif cand.source_text and verbatim(e, cand.source_text):
            evidence.append(e)
    evidence = list(dict.fromkeys(evidence))[:4]
    if not quotes:
        score = min(score, CAPS[key] // 4)  # no quoted support: treated as barely supported
    if thin:
        score = score // 2
    return {"score": score, "quotes": quotes, "evidence": evidence}


def comp_points(p: dict, prefs: Preferences) -> int:
    hi = p.get("pay_max")
    if not hi:
        return 4
    if prefs.base_floor:
        return 10 if hi >= prefs.base_floor * 1.15 else 8 if hi >= prefs.base_floor else 0
    return 7


def location_points(p: dict, flags: list[str]) -> int:
    if any("location" in f or "eligibility" in f for f in flags):
        return 3
    return 5


def source_points(p: dict) -> int:
    if p.get("aggregator_only"):
        return 0
    boards = len(p.get("also_listed_on", []))
    return 5 if boards == 0 else 3 if boards == 1 else 2


def finalize(p: dict, data: dict | None, cand: Candidate, prefs: Preferences, flags: list[str],
             now: datetime | None = None) -> dict:
    """Merge Claude's validated extraction into the posting and compute its total score."""
    text = p.get("description_text", "")
    thin = len(text) < THIN_DESCRIPTION
    data = data or {}
    if data:
        mode = data.get("work_mode")
        if mode in ("remote", "hybrid", "onsite") and verbatim(data.get("work_mode_evidence", ""), text):
            p["work_mode"] = mode
            p["work_mode_evidence"] = data["work_mode_evidence"]
        states = [s.strip().upper() for s in data.get("remote_states", []) if isinstance(s, str) and len(s.strip()) == 2]
        if states:
            p["remote_states"] = states
        if not p.get("pay_max") and isinstance(data.get("pay_max"), (int, float)) and verbatim(data.get("pay_evidence", ""), text):
            hi, lo = float(data["pay_max"]), data.get("pay_min")
            p.update(pay_max=round(hi), pay_min=round(float(lo)) if isinstance(lo, (int, float)) else round(hi),
                     currency="USD", pay_period="year", pay_text=data["pay_evidence"])
        elif not p.get("pay_max"):
            with_pay(p, text)
        if isinstance(data.get("closes_at"), str) and re.match(r"\d{4}-\d{2}-\d{2}", data["closes_at"]):
            p["closes_at"] = p.get("closes_at") or data["closes_at"]
        for k in ("years_required", "people_management", "team_size", "bonus_equity", "days_onsite"):
            if data.get(k) not in (None, "", "unknown"):
                p[k] = data[k]
    subs = {k: _clean_sub((data or {}).get(k), k, text, cand, thin) for k in CAPS}
    if not data:
        subs = {k: {"score": 0, "quotes": [], "evidence": []} for k in CAPS}
    fresh = freshness.points(freshness.age_days(p, now))
    comp, loc, src = comp_points(p, prefs), location_points(p, flags), source_points(p)
    total = sum(s["score"] for s in subs.values()) + fresh + comp + loc + src
    p["fit"] = {
        "total": total,
        "kind": "evidence" if cand.has_evidence else "preference_match",
        "subscores": {**{k: {**v, "max": CAPS[k]} for k, v in subs.items()},
                      "freshness": {"score": fresh, "max": 15}, "comp": {"score": comp, "max": 10},
                      "location": {"score": loc, "max": 5}, "source": {"score": src, "max": 5}},
        "gaps": [g for g in data.get("gaps", []) if isinstance(g, str)][:3],
        "angle": data.get("angle", "") if cand.has_evidence and isinstance(data.get("angle"), str) else "",
        "verdict": data.get("verdict", "") if isinstance(data.get("verdict"), str) else "",
        "scored": bool(data),
        "thin_description": thin,
    }
    if data and cand.has_evidence:
        analysis = {k: [x for x in data.get(k, []) if isinstance(x, str)] for k in ("must_have", "tools", "competencies")}
        analysis["nice_to_have"] = []
        try:
            p["requirements"] = build_requirement_map(analysis, cand.source_text, cand.fact_bank, cand.profile_skills)
        except Exception:
            p["requirements"] = []
    p["flags"] = flags + (["no full description"] if thin else []) + ([] if data else ["could not be scored"])
    return p

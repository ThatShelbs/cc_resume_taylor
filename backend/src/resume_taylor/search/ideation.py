"""Ideate target companies from the candidate's own history (or, with no resume yet, their
stated preferences). The judgment rules live in the company-ideation skill."""

from resume_taylor.config import COMPANY_IDEATION_SKILL_PATH
from resume_taylor.pipeline.prompts import load_skill

from . import claude
from .candidate import Candidate
from .normalize import norm_company

CLUSTERS = {
    "past_peers": "Direct competitors and close peers of past employers",
    "industry": "Other leaders in the same industries or domains",
    "adjacent": "Adjacent industries where the same skills transfer",
    "growth": "Fast-growing or recently funded companies hiring for this function",
    "admired": "Companies the person named as admired",
}

CONTRACT = """

Reply with JSON only:
{"companies": [{"name": "Company Name", "cluster": "past_peers|industry|adjacent|growth|admired",
 "rationale": "one sentence tied to the person's real history or stated preferences",
 "careers_url": "official careers page if you confirmed it, else empty"}]}
"""


def ideate(cand: Candidate, count: int, *, clusters: list[str] | None = None, exclude: list[str] | None = None,
           model: str | None = None, effort: str | None = None, label: str = "Company ideation") -> list[dict]:
    """Up to `count` distinct companies, none in `exclude`. Empty list if Claude fails."""
    wanted = [c for c in (clusters or list(CLUSTERS)) if c in CLUSTERS] or list(CLUSTERS)
    skip = {norm_company(n) for n in (exclude or [])}
    out: list[dict] = []
    for attempt in range(2):  # a second ask tops up a short or duplicate-heavy first answer
        need = count - len(out)
        if need <= 0:
            break
        ask = max(need, 5)
        user = (
            f"About the person (tier: {cand.tier}):\n{cand.summary()}\n\n"
            f"Suggest {ask} companies for them to target. Clusters to draw from:\n"
            + "\n".join(f"- {k}: {CLUSTERS[k]}" for k in wanted)
            + "\n\nDo NOT suggest any of these (already chosen or already suggested): "
            + (", ".join(sorted({*(exclude or []), *(c['name'] for c in out)})) or "none")
        )
        reply = claude.ask(load_skill(COMPANY_IDEATION_SKILL_PATH) + CONTRACT, user, tools=claude.WEB_TOOLS,
                           model=model, effort=effort, label=label)
        items = (reply or {}).get("companies", []) if isinstance(reply, dict) else reply or []
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            key = norm_company(name)
            if not key or key in skip:
                continue
            skip.add(key)
            cluster = it.get("cluster") if it.get("cluster") in CLUSTERS else wanted[0]
            out.append({
                "name": name, "cluster": cluster, "rationale": str(it.get("rationale", "")).strip(),
                "careers_url": str(it.get("careers_url", "") or "").strip(),
            })
            if len(out) >= count:
                break
        if not items:
            break
    return out[:count]

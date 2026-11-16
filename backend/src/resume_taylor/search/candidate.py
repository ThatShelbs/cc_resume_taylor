"""What the search knows about the person, at whatever level of setup they have reached.

full     profile + resume + fact bank     evidence-based, cites fact ids
partial  a resume and/or a profile        evidence-based, quotes resume lines
quick    nothing yet                      stated preferences only; scores are "Preference match"
"""

from dataclasses import dataclass, field
from pathlib import Path

from resume_taylor.pipeline.factbank import format_fact_bank, load_fact_bank
from resume_taylor.pipeline.parsing import parse_prior_resume, parse_profile_skills
from resume_taylor.pipeline.sources import read_input_text

from .prefs import Preferences


@dataclass
class Candidate:
    tier: str = "quick"
    employers: list[str] = field(default_factory=list)
    titles: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    source_text: str = ""
    fact_bank: dict | None = None
    profile_skills: dict = field(default_factory=lambda: {"tools": [], "skills": []})
    prefs: Preferences = field(default_factory=Preferences)

    @property
    def has_evidence(self) -> bool:
        return self.tier in ("full", "partial")

    def summary(self, max_facts: int = 60) -> str:
        """The candidate as plain text for ideation and scoring prompts."""
        p = self.prefs
        lines: list[str] = []
        if self.has_evidence:
            if self.employers:
                lines.append("Employers (most recent first): " + "; ".join(self.employers[:8]))
            if self.titles:
                lines.append("Past titles: " + "; ".join(self.titles[:8]))
            if self.skills:
                lines.append("Skills and tools: " + ", ".join(self.skills[:60]))
            if self.fact_bank:
                lines.append("Fact bank (the only evidence you may cite, by id):\n" + "\n".join(format_fact_bank(self.fact_bank).splitlines()[:max_facts]))
            elif self.source_text:
                lines.append("Resume and profile text:\n" + self.source_text[:6000])
        else:
            lines.append("No resume or fact bank yet. Use only the stated preferences below; make no claims about experience.")
        if p.titles:
            lines.append("Titles wanted: " + "; ".join(p.titles))
        if p.skill_terms:
            lines.append("Skill terms: " + ", ".join(p.skill_terms))
        if p.industries:
            lines.append("Industries of interest: " + ", ".join(p.industries))
        if p.admired_companies:
            lines.append("Companies they admire: " + ", ".join(p.admired_companies))
        if p.about_me.strip():
            lines.append("In their words: " + p.about_me.strip()[:1200])
        if p.home_location:
            lines.append("Home location: " + p.home_location)
        return "\n".join(lines)


def _safe(fn, *args, default=None):
    try:
        return fn(*args)
    except SystemExit:
        return default
    except Exception:
        return default


def build_candidate(profile: Path | None, resume: Path | None, fact_bank: Path | None, prefs: Preferences) -> Candidate:
    cand = Candidate(prefs=prefs)
    profile = profile if profile and Path(profile).exists() else None
    resume = resume if resume and Path(resume).exists() else None
    jobs = []
    if resume:
        parsed = _safe(parse_prior_resume, resume, default=None)
        jobs = (parsed or {}).get("jobs", [])
        cand.employers = [j["company"] for j in jobs]
        cand.titles = [j["title"] for j in jobs]
    if profile:
        cand.profile_skills = _safe(parse_profile_skills, profile, default=None) or cand.profile_skills
        cand.skills = [*cand.profile_skills.get("tools", []), *cand.profile_skills.get("skills", [])]
    texts = [_safe(read_input_text, p, default="") for p in (profile, resume) if p]
    cand.source_text = "\n".join(t for t in texts if t)
    if fact_bank and Path(fact_bank).exists() and cand.employers:
        cand.fact_bank = _safe(load_fact_bank, cand.employers, Path(fact_bank), default=None)
        if cand.fact_bank:
            tags = {t for f in cand.fact_bank.values() for t in (f.get("tags") or [])}
            cand.tags = sorted(tags)
    if profile and resume and cand.fact_bank:
        cand.tier = "full"
    elif cand.source_text.strip():
        cand.tier = "partial"
    return cand


def readiness(profile: Path | None, resume: Path | None, fact_bank: Path | None) -> str:
    has_profile = bool(profile and Path(profile).exists())
    has_resume = bool(resume and Path(resume).exists())
    has_facts = bool(fact_bank and Path(fact_bank).exists())
    if has_profile and has_resume and has_facts:
        return "full"
    if has_profile or has_resume:
        return "partial"
    return "quick"

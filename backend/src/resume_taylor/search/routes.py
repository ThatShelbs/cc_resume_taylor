"""Company route registry: for each company, how to pull its postings (which ATS, which board).
One shared file, so target companies and ideated ones both benefit from earlier discovery."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .normalize import norm_company

STALE_AFTER_DAYS = 30  # a route that returned postings
EMPTY_RECHECK_DAYS = 7  # a site that works but listed nothing: look again sooner
FAILED_RETRY_DAYS = 3  # no route found: do not spend a web search on it every run

# Hosts that are job boards or aggregators, never a company's own careers page.
NOT_CAREERS_HOSTS = ("linkedin.", "indeed.", "glassdoor.", "ziprecruiter.", "monster.", "simplyhired.", "careerbuilder.",
                     "builtin.", "dice.com", "roberthalf.", "wellfound.", "jooble.", "talent.com", "lensa.")


def is_company_page(url: str) -> bool:
    """A plausible official careers URL: http(s), and not a job board, an aggregator or a Google search."""
    u = (url or "").strip().lower()
    return u.startswith(("http://", "https://")) and not any(h in u for h in NOT_CAREERS_HOSTS) and "google.com/search" not in u


def board_url(route: dict) -> str:
    """The page a person can open to browse this route's job board."""
    ats, tok, host = route.get("ats", ""), route.get("token", ""), route.get("host", "")
    return {
        "greenhouse": f"https://job-boards.greenhouse.io/{tok}",
        "lever": f"https://jobs.lever.co/{tok}",
        "ashby": f"https://jobs.ashbyhq.com/{tok}",
        "smartrecruiters": f"https://careers.smartrecruiters.com/{tok}",
        "workable": f"https://apply.workable.com/{tok}/",
        "recruitee": f"https://{tok}.recruitee.com/",
        "bamboohr": f"https://{tok}.bamboohr.com/careers",
        "breezy": f"https://{tok}.breezy.hr/",
        "rippling": f"https://ats.rippling.com/{tok}/jobs",
        "teamtailor": f"https://{host}/jobs" if host else "",
        "workday": f"https://{host}/{route.get('site', '')}" if host else "",
        "eightfold": f"https://{host}/careers?domain={route.get('domain', '')}" if host else "",
    }.get(ats, "") if (tok or host) else ""


def careers_link(route: dict) -> str:
    """Where to send a person for this company's jobs: its own careers page, else the ATS board."""
    return route.get("careers_url") or route.get("board_url") or board_url(route)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RouteBook:
    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self.routes: dict[str, dict] = {}
        if self.path and self.path.exists():
            try:
                self.routes = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self.routes = {}

    def get(self, company: str) -> dict | None:
        return self.routes.get(norm_company(company))

    @staticmethod
    def _age_days(r: dict) -> float | None:
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(r["verified_at"])).total_seconds() / 86400
        except (KeyError, ValueError):
            return None

    def usable(self, company: str) -> dict | None:
        """A resolved (or recently empty) route that is recent enough to trust without rediscovering."""
        r = self.get(company)
        age = self._age_days(r) if r else None
        if r is None or age is None:
            return None
        if r.get("status") == "resolved":
            return r if age <= STALE_AFTER_DAYS else None
        if r.get("status") == "empty":
            return r if age <= EMPTY_RECHECK_DAYS else None
        return None

    def recent_failure(self, company: str) -> dict | None:
        r = self.get(company)
        age = self._age_days(r) if r else None
        return r if r and r.get("status") == "failed" and age is not None and age <= FAILED_RETRY_DAYS else None

    def record_run(self, company: str, listed: int) -> None:
        """What a real run saw: a route that lists nothing is marked empty (looked at again within a
        week), and an empty one that lists postings again is resolved."""
        r = self.get(company)
        if not r:
            return
        if listed == 0 and r.get("status") == "resolved":
            r.update(status="empty", job_count=0, verified_at=_now(), note="No openings listed at the last search.")
        elif listed > 0 and r.get("status") == "empty":
            r.update(status="resolved", job_count=listed, verified_at=_now(), note="")

    def set(self, company: str, route: dict, *, method: str, job_count: int | None, status: str = "resolved",
            note: str = "") -> dict:
        rec = {**route, "company": company, "method": method, "job_count": job_count, "status": status,
               "verified_at": _now(), "note": note}
        if not rec.get("board_url"):
            rec["board_url"] = board_url(rec)
        self.routes[norm_company(company)] = rec
        return rec

    def forget(self, company: str) -> None:
        self.routes.pop(norm_company(company), None)

    def save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.routes, indent=2), encoding="utf-8")
        tmp.replace(self.path)

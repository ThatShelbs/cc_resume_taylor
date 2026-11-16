"""Company route registry: for each company, how to pull its postings (which ATS, which board).
One shared file, so target companies and ideated ones both benefit from earlier discovery."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .normalize import norm_company

STALE_AFTER_DAYS = 30


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

    def usable(self, company: str) -> dict | None:
        """A resolved route that is recent enough to trust without rediscovering."""
        r = self.get(company)
        if not r or r.get("status") != "resolved":
            return None
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(r["verified_at"])).days
        except (KeyError, ValueError):
            return None
        return r if age <= STALE_AFTER_DAYS else None

    def set(self, company: str, route: dict, *, method: str, job_count: int | None, status: str = "resolved",
            note: str = "") -> dict:
        rec = {**route, "company": company, "method": method, "job_count": job_count, "status": status,
               "verified_at": _now(), "note": note}
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

"""Per-site account state and pacing rules. State only, never a secret: whether you signed in,
when, what the last search run used, and whether a site is cooling down after a bot check.

Shared by the API (shows status) and the search subprocess (enforces the per-run budget), so it is stdlib only
and keeps everything in one small JSON file."""

import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SITES = ("linkedin", "indeed", "ziprecruiter")
LABELS = {"linkedin": "LinkedIn", "indeed": "Indeed", "ziprecruiter": "ZipRecruiter"}
SOURCE_FOR_SITE = {"linkedin": "linkedin", "indeed": "indeed", "ziprecruiter": "ziprecruiter"}
# Sites whose job search works in a normal browser without signing in. Signing in is still offered.
LOGIN_OPTIONAL = frozenset({"ziprecruiter"})
# Sites this app no longer supports; their state and browser profile are cleaned up on sight.
RETIRED_SITES = ("google",)

# Per search run, per site. There is no daily cap; the bot-check cooldown below is what protects the account.
RUN_BUDGET = {"search": 10, "detail": 20}
COOLDOWN_HOURS = 24
DELAY_RANGE = (3.0, 9.0)  # seconds between page actions

# Words that mean "we think you are a bot" or "sign in again". Any hit stops that site for the day.
TRIPWIRE_MARKERS = (
    "captcha", "unusual traffic", "unusual activity", "verify you are human", "verify you're human",
    "are you a robot", "security check", "checkpoint", "temporarily restricted", "too many requests",
    "access denied", "press and hold", "i'm not a robot",
)
LOGIN_URL_MARKERS = ("/login", "/uas/login", "/authwall", "/checkpoint", "secure.indeed.com/auth", "/signin")


def _utc() -> datetime:
    return datetime.now(timezone.utc)


def profile_dir(job_search_dir: Path, site: str) -> Path:
    return Path(job_search_dir) / "browser_profile" / site


def human_delay(sleep=time.sleep, rng=random) -> float:
    secs = rng.uniform(*DELAY_RANGE)
    sleep(secs)
    return secs


def tripped(url: str, text: str) -> str:
    """Why this page means 'stop', or '' when it looks normal."""
    low = (text or "").lower()[:6000]
    u = (url or "").lower()
    for m in TRIPWIRE_MARKERS:
        if m in low:
            return f"bot check ({m})"
    for m in LOGIN_URL_MARKERS:
        if m in u:
            return "signed out"
    return ""


class AccountState:
    def __init__(self, path, now=_utc):
        self.path = Path(path)
        self._now = now

    # -- storage
    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _site(self, data: dict, site: str) -> dict:
        return data.setdefault(site, {})

    # -- queries
    def status(self, site: str) -> dict:
        s = self._read().get(site, {})
        cooling = self.cooling_until(site)
        return {
            "site": site, "label": LABELS[site], "connected": bool(s.get("connected_at")),
            "login_optional": site in LOGIN_OPTIONAL, "ready": self.can_use(site),
            "connected_at": s.get("connected_at"), "last_used": s.get("last_used"),
            "cooldown_until": cooling.isoformat(timespec="minutes") if cooling else None,
            "cooldown_reason": s.get("cooldown_reason", "") if cooling else "",
            "budget": dict(RUN_BUDGET), "last_run": s.get("last_run"),
        }

    def cooling_until(self, site: str) -> datetime | None:
        raw = self._read().get(site, {}).get("cooldown_until")
        try:
            until = datetime.fromisoformat(raw) if raw else None
        except ValueError:
            return None
        return until if until and until > self._now() else None

    def can_use(self, site: str) -> bool:
        """Signed in (or a site that does not need it) and not cooling down after a bot check."""
        s = self._read().get(site, {})
        return (bool(s.get("connected_at")) or site in LOGIN_OPTIONAL) and not self.cooling_until(site)

    # -- changes
    def mark_connected(self, site: str) -> None:
        data = self._read()
        s = self._site(data, site)
        s["connected_at"] = self._now().isoformat(timespec="seconds")
        s.pop("cooldown_until", None)
        self._write(data)

    def disconnect(self, site: str) -> None:
        data = self._read()
        data.pop(site, None)
        self._write(data)

    def record_run(self, site: str, usage: dict) -> None:
        """What one search run used on this site, kept for display only."""
        data = self._read()
        s = self._site(data, site)
        now = self._now().isoformat(timespec="seconds")
        s["last_run"] = {"search": int(usage.get("search", 0)), "detail": int(usage.get("detail", 0)), "at": now}
        s["last_used"] = now
        self._write(data)

    def trip(self, site: str, reason: str) -> None:
        """A bot check or sign-out: stop this site for a day. Signed out also clears 'connected'."""
        data = self._read()
        s = self._site(data, site)
        s["cooldown_until"] = (self._now() + timedelta(hours=COOLDOWN_HOURS)).isoformat(timespec="seconds")
        s["cooldown_reason"] = reason
        if reason == "signed out":
            s.pop("connected_at", None)
        self._write(data)

    def forget_retired(self) -> list[str]:
        """Drop state for sites the app no longer supports. Returns the ones removed."""
        data = self._read()
        gone = [k for k in RETIRED_SITES if k in data]
        if gone:
            for k in gone:
                data.pop(k)
            self._write(data)
        return gone


def new_usage() -> dict:
    """A per-run counter for one site."""
    return {"search": 0, "detail": 0}

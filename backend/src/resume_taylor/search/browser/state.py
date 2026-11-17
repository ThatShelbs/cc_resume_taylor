"""Per-site account state and pacing rules. State only, never a secret: whether you signed in,
when, how much was used today, and whether a site is cooling down after a bot check.

Shared by the API (shows status) and the search subprocess (enforces caps), so it is stdlib only
and keeps everything in one small JSON file."""

import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

SITES = ("linkedin", "indeed", "google")
LABELS = {"linkedin": "LinkedIn", "indeed": "Indeed", "google": "Google Jobs"}
SOURCE_FOR_SITE = {"linkedin": "linkedin", "indeed": "indeed", "google": "google_jobs"}

# Deliberately small. A person doing a job hunt looks at a handful of searches a day.
DAILY_CAPS = {
    "linkedin": {"search": 3, "detail": 20},
    "indeed": {"search": 3, "detail": 20},
    "google": {"search": 3, "detail": 0},
}
COOLDOWN_HOURS = 24
DELAY_RANGE = (3.0, 9.0)  # seconds between page actions

# Words that mean "we think you are a bot" or "sign in again". Any hit stops that site for the day.
TRIPWIRE_MARKERS = (
    "captcha", "unusual traffic", "unusual activity", "verify you are human", "verify you're human",
    "are you a robot", "security check", "checkpoint", "temporarily restricted", "too many requests",
    "access denied", "press and hold", "i'm not a robot",
)
LOGIN_URL_MARKERS = ("/login", "/uas/login", "/authwall", "/checkpoint", "accounts.google.com", "secure.indeed.com/auth", "/signin")


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
        s = data.setdefault(site, {})
        today = self._now().date().isoformat()
        if s.get("day") != today:
            s["day"], s["search"], s["detail"] = today, 0, 0
        return s

    # -- queries
    def status(self, site: str) -> dict:
        data = self._read()
        s = self._site(data, site)
        cooling = self.cooling_until(site)
        return {
            "site": site, "label": LABELS[site], "connected": bool(s.get("connected_at")),
            "connected_at": s.get("connected_at"), "last_used": s.get("last_used"),
            "cooldown_until": cooling.isoformat(timespec="minutes") if cooling else None,
            "cooldown_reason": s.get("cooldown_reason", "") if cooling else "",
            "used_today": {"search": s.get("search", 0), "detail": s.get("detail", 0)}, "caps": DAILY_CAPS[site],
        }

    def cooling_until(self, site: str) -> datetime | None:
        raw = self._read().get(site, {}).get("cooldown_until")
        try:
            until = datetime.fromisoformat(raw) if raw else None
        except ValueError:
            return None
        return until if until and until > self._now() else None

    def can_use(self, site: str, kind: str) -> bool:
        """Connected, not cooling down, and under today's cap for this kind of action."""
        s = self._site(self._read(), site)
        return bool(s.get("connected_at")) and not self.cooling_until(site) and s.get(kind, 0) < DAILY_CAPS[site][kind]

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

    def record(self, site: str, kind: str) -> None:
        data = self._read()
        s = self._site(data, site)
        s[kind] = s.get(kind, 0) + 1
        s["last_used"] = self._now().isoformat(timespec="seconds")
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

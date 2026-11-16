"""A polite HTTP client: per-host rate limits, backoff, a 24-hour disk cache and robots.txt
checks for HTML. The transport and sleep function can be injected so tests never touch the
network or wait."""

import hashlib
import json
import threading
import time
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlsplit

import httpx

USER_AGENT = "ResumeTaylor/1.0 (personal job search; respects robots.txt)"
CACHE_TTL = 24 * 3600
DEFAULT_INTERVAL = 1.0
HOST_INTERVALS = {"www.linkedin.com": 4.0}
MAX_RETRIES = 2


class Client:
    def __init__(
        self,
        cache_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
        intervals: dict | None = None,
        timeout: float = 20.0,
    ):
        self._http = httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.5"},
        )
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._sleep = sleep
        self._intervals = {**HOST_INTERVALS, **(intervals or {})}
        self._lock = threading.Lock()
        self._next_slot: dict[str, float] = {}
        self._blocked: set[str] = set()
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self.requests = 0
        self.errors: list[str] = []

    # -- rate limiting -----------------------------------------------------------------

    def _wait_turn(self, host: str) -> None:
        interval = self._intervals.get(host, DEFAULT_INTERVAL)
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot.get(host, 0.0))
            self._next_slot[host] = slot + interval
        delay = slot - now
        if delay > 0:
            self._sleep(delay)

    def is_blocked(self, url_or_host: str) -> bool:
        host = urlsplit(url_or_host).netloc or url_or_host
        return host in self._blocked

    # -- cache -------------------------------------------------------------------------

    def _cache_path(self, key: str) -> Path | None:
        if not self._cache_dir:
            return None
        return self._cache_dir / (hashlib.sha1(key.encode("utf-8")).hexdigest() + ".txt")

    def _cache_get(self, key: str) -> str | None:
        path = self._cache_path(key)
        try:
            if path and path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
                return path.read_text(encoding="utf-8")
        except OSError:
            pass
        return None

    def _cache_put(self, key: str, text: str) -> None:
        path = self._cache_path(key)
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError:
            pass

    # -- robots ------------------------------------------------------------------------

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = robotparser.RobotFileParser()
            try:
                resp = self._request("GET", f"{origin}/robots.txt", retries=0)
                if resp is not None and resp.status_code == 200:
                    parser.parse(resp.text.splitlines())
                    self._robots[origin] = parser
                else:
                    self._robots[origin] = None  # no usable robots.txt: allowed
            except Exception:
                self._robots[origin] = None
        parser = self._robots[origin]
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    # -- requests ----------------------------------------------------------------------

    def _request(self, method: str, url: str, *, retries: int = MAX_RETRIES, **kw) -> httpx.Response | None:
        host = urlsplit(url).netloc
        if host in self._blocked:
            return None
        for attempt in range(retries + 1):
            self._wait_turn(host)
            self.requests += 1
            try:
                resp = self._http.request(method, url, **kw)
            except httpx.HTTPError as exc:
                self.errors.append(f"{host}: {exc.__class__.__name__}")
                return None
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < retries:
                    self._sleep(2 * (attempt + 1))
                    continue
                if resp.status_code == 429:
                    self._blocked.add(host)  # stop hammering this host for the rest of the run
                    self.errors.append(f"{host}: rate limited, skipped for this run")
                return None
            return resp
        return None

    def get_text(self, url: str, *, params: dict | None = None, headers: dict | None = None,
                 cache: bool = True, robots: bool = False) -> str | None:
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        if cache:
            hit = self._cache_get(key)
            if hit is not None:
                return hit
        if robots and not self.allowed_by_robots(url):
            self.errors.append(f"{urlsplit(url).netloc}: disallowed by robots.txt")
            return None
        resp = self._request("GET", url, params=params, headers=headers)
        if resp is None or resp.status_code != 200:
            return None
        text = resp.text
        if cache and text:
            self._cache_put(key, text)
        return text

    def get_json(self, url: str, *, params: dict | None = None, headers: dict | None = None,
                 cache: bool = False):
        text = self.get_text(url, params=params, headers=headers, cache=cache)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def post_json(self, url: str, payload: dict):
        resp = self._request("POST", url, json=payload)
        if resp is None or resp.status_code != 200:
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def status(self, url: str) -> int | None:
        """HTTP status of a GET (uncached), or None if unreachable. Used to verify postings."""
        resp = self._request("GET", url)
        return resp.status_code if resp is not None else None

    def close(self) -> None:
        self._http.close()

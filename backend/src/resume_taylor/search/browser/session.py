"""A real, visible Chrome window using a persistent profile that you signed in to yourself.

No stealth plugins and no fingerprint spoofing: it is ordinary Chrome with your own session, driven
slowly. Playwright is imported lazily so the rest of the engine (and the tests) never need it."""

from dataclasses import dataclass, field
from pathlib import Path

from .state import human_delay, tripped


# A cookie that only exists once you are signed in (LinkedIn can land on many pages after login).
SESSION_COOKIES = {"linkedin": "li_at", "google": "SID"}


@dataclass
class Page:
    url: str
    html: str
    text: str
    links: list[str] = field(default_factory=list)


class BrowserUnavailable(RuntimeError):
    pass


class BrowserSession:
    """Context manager. `fetch(url)` loads one page like a person would: wait, scroll, read."""

    def __init__(self, profile: Path, headless: bool = False, sleep=None):
        self.profile, self.headless, self._sleep = Path(profile), headless, sleep
        self._pw = self._ctx = self._page = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise BrowserUnavailable("Playwright is not installed. Run: pip install -e backend") from exc
        self.profile.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        try:
            self._ctx = self._pw.chromium.launch_persistent_context(str(self.profile), channel="chrome", headless=self.headless,
                                                                    viewport=None)
        except Exception as exc:  # pragma: no cover
            self._pw.stop()
            raise BrowserUnavailable("Could not open Google Chrome. Install Chrome, then try again.") from exc
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        return self

    def __exit__(self, *exc):
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    def close(self) -> None:
        self.__exit__()

    def goto(self, url: str) -> None:
        self._page.goto(url, wait_until="domcontentloaded", timeout=45000)

    @property
    def url(self) -> str:
        return self._page.url if self._page else ""

    def fetch(self, url: str) -> Page:
        self.goto(url)
        human_delay(*(([self._sleep]) if self._sleep else []))
        for _ in range(3):  # scroll a little, as a reader would
            self._page.mouse.wheel(0, 700)
            human_delay(*(([self._sleep]) if self._sleep else []))
        return Page(
            url=self._page.url, html=self._page.content(), text=self._page.inner_text("body"),
            links=self._page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"),
        )

    def wait_until_signed_in(self, site: str, signed_in_url: str, timeout_s: int = 600) -> bool:
        """Block while the user signs in by hand. True once they land on a normal page for the site."""
        import time
        end = time.time() + timeout_s
        cookie = SESSION_COOKIES.get(site)
        while time.time() < end:
            try:
                # Playwright's sync API only processes browser events while it is waiting on its own
                # clock; time.sleep() would leave page.url frozen at the login page forever.
                self._page.wait_for_timeout(2000)
                if cookie and any(c.get("name") == cookie for c in self._ctx.cookies()):
                    return True
                urls = [p.url for p in self._ctx.pages]
            except Exception:  # window closed
                return False
            if any(signed_in_url in u and not tripped(u, "") for u in urls):
                return True
        return False

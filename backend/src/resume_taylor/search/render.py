"""Reading careers pages the way a person sees them.

Many company careers pages build their job links with JavaScript, so the plain HTML has no ATS link,
no JSON-LD and no postings. `render()` opens such a page once in a headless, signed-out browser
(no profile, nothing kept) and returns the final HTML, the visible text and every link with its
text. Callers check robots.txt first and only render when the plain fetch found nothing.

`static_anchors()` reads the same link list from plain HTML, and `job_links()` picks the links that
look like individual postings, so the engine follows links that are really on the page instead of
asking a model to guess posting URLs."""

import html as htmllib
import os
import re
import threading
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

from .normalize import norm_title


@dataclass
class Rendered:
    url: str
    html: str
    text: str
    anchors: list[tuple[str, str]] = field(default_factory=list)  # (absolute href, link text or aria-label)
    frames: list[str] = field(default_factory=list)


_LOCK = threading.Lock()  # one headless browser at a time, even from the discovery thread pool
ENABLED = os.environ.get("TAYLOR_NO_RENDER", "") != "1"


def render(url: str, timeout_ms: int = 30000) -> Rendered | None:
    """The rendered page, or None when rendering is off, Playwright is missing or the page fails."""
    if not ENABLED or not url:
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - depends on the install
        return None
    with _LOCK:
        try:
            with sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(channel="chrome", headless=True)
                except Exception:  # pragma: no cover - no Chrome: Playwright's own Chromium, if installed
                    browser = pw.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    anchors = page.eval_on_selector_all(
                        "a[href]", "els => els.map(e => [e.href, (e.innerText || e.getAttribute('aria-label') || '').trim().slice(0, 200)])")
                    return Rendered(url=page.url, html=page.content(), text=page.inner_text("body"),
                                    anchors=[(str(h), str(t)) for h, t in anchors], frames=[f.url for f in page.frames])
                finally:
                    browser.close()
        except Exception:  # pragma: no cover - network or browser trouble: behave as if nothing was found
            return None


_A = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.S | re.I)
_HREF = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.I)
_ARIA = re.compile(r'aria-label\s*=\s*["\']([^"\']+)["\']', re.I)
_BASE = re.compile(r'<base\b[^>]*href\s*=\s*["\']([^"\']+)["\']', re.I)


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", raw or ""))).strip()


def static_anchors(markup: str, page_url: str) -> list[tuple[str, str]]:
    """(absolute href, text) for every link in plain HTML, honoring <base href>."""
    base = _BASE.search(markup or "")
    root = urljoin(page_url, base.group(1)) if base else page_url
    out = []
    for attrs, inner in _A.findall(markup or ""):
        href = _HREF.search(attrs)
        if not href or href.group(1).startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        aria = _ARIA.search(attrs)
        out.append((urljoin(root, htmllib.unescape(href.group(1))), _clean(inner) or (aria.group(1) if aria else "")))
    return out


def site_of(url: str) -> str:
    """The registrable part of a host, roughly: 'careers.pfizer.com' -> 'pfizer.com'."""
    host = urlsplit(url).netloc.lower().split(":")[0]
    parts = host.split(".")
    if len(parts) > 2 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "net", "ac", "gov"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


# A path that names one posting: a job-ish word followed somewhere by an id or a long slug.
_JOB_PATH = re.compile(
    r"/(?:jobs?|positions?|openings?|vacanc(?:y|ies)|requisitions?|careers?|roles?|opportunit(?:y|ies)|apply)/"
    r"(?:[^?#]*/)?(?:[^/?#]*\d{4,}[^/?#]*|[a-z0-9]+(?:-[a-z0-9]+){2,})/?$", re.I)
_NOT_POSTING = re.compile(r"/(?:search|results|category|categories|teams?|locations?|departments?|benefits|students?|"
                          r"life|culture|faq|blog|events?|talent-community|saved|login|signin)/?$", re.I)
_LEAD = re.compile(r"^(learn more about|view job|apply (?:now )?(?:for)?|see details for)\s*:?\s*", re.I)


def anchor_title(text: str) -> str:
    return _LEAD.sub("", _clean(text)).strip(" -|")


def job_links(anchors: list[tuple[str, str]], page_url: str, titles: list[str] | tuple = (), limit: int = 40) -> list[tuple[str, str]]:
    """Links on the page that look like single postings on the same site, best title matches first."""
    site, here = site_of(page_url), urlsplit(page_url).path.rstrip("/")
    words = {w for t in titles for w in norm_title(t).split() if len(w) > 2}
    seen, picked = set(), []
    for href, text in anchors:
        parts = urlsplit(href)
        if parts.scheme not in ("http", "https") or site_of(href) != site:
            continue
        path = parts.path.rstrip("/")
        if path == here or path in seen or not _JOB_PATH.search(path) or _NOT_POSTING.search(path):
            continue
        seen.add(path)
        title = anchor_title(text)
        overlap = len(words & set(norm_title(title or path.replace("-", " ")).split()))
        picked.append((overlap, len(picked), href, title))
    picked.sort(key=lambda x: (-x[0], x[1]))
    return [(h, t) for _, _, h, t in picked[:limit]]


_JOB_SEARCH_TEXT = re.compile(
    r"\b(search (all )?(jobs|openings|roles|positions)|view (all )?(jobs|openings|roles|positions)|(see|explore|browse|find) "
    r"(all )?(jobs|openings|roles|opportunities|positions)|(open|current) (positions|roles|openings|opportunities)|job (search|openings)|"
    r"all jobs|join (our|the) team)\b", re.I)


def job_search_links(anchors: list[tuple[str, str]], limit: int = 3) -> list[str]:
    """Links whose text reads like 'Search jobs' / 'View open positions': the way into the job list."""
    out = []
    for href, text in anchors:
        if href.startswith("http") and _JOB_SEARCH_TEXT.search(text or "") and href not in out:
            out.append(href)
    return out[:limit]


_DROP_TAGS = re.compile(r"(?is)<(script|style|noscript|svg|nav|header|footer|form)\b.*?</\1>")


def main_text(markup: str, title: str = "", limit: int = 12000) -> str:
    """Readable text of a posting page without navigation, starting at the title when it appears."""
    from .normalize import html_to_text

    text = html_to_text(_DROP_TAGS.sub(" ", markup or ""))
    at = text.lower().find(title.lower()) if title else -1
    return text[at if at >= 0 else 0:][:limit].strip()

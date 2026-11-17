"""Runs targeted searches on the signed-in sites, gently, and returns *hits* in the same shape as
`connectors/board_hits.py` so crosswalk, dedupe, filters and scoring work unchanged.

Rules: only connected sites; one pace for everything; a daily cap per kind of action; the first
bot check or sign-out stops that site for a day (no retry). `session_for(site)` returns anything with
`fetch(url) -> Page`, so tests pass a fake."""

from . import sites
from .state import LABELS, SITES, SOURCE_FOR_SITE, AccountState, tripped


def search_site(site: str, session, state: AccountState, queries: list[dict], recency_days: int, *,
                progress=print, model=None, effort=None) -> tuple[list[dict], str]:
    """Hits plus a note ('' when all went normally). Stops at the first trip or cap."""
    hits: list[dict] = []
    label = LABELS[site]
    for q in queries:
        if not state.can_use(site, "search"):
            if state.cooling_until(site):
                return hits, f"{label} is paused for today ({state.status(site)['cooldown_reason']})."
            return hits, f"{label}: reached today's search limit, so it stopped there."
        page = session.fetch(sites.search_url(site, q["q"], q["location"], recency_days))
        state.record(site, "search")
        why = tripped(page.url, page.text)
        if why:
            state.trip(site, why)
            return hits, f"{label} stopped for today ({why}). Nothing was retried."
        found = sites.PARSERS[site](page.html) if site in sites.PARSERS else []
        if not found:
            found = sites.claude_extract(site, page.text, page.links, SOURCE_FOR_SITE[site], model=model, effort=effort)
        progress(f"{label}: '{q['q']}' in {q['location']} gave {len(found)} leads")
        hits += found
    return hits, ""


def hydrate_detail(site: str, session, state: AccountState, posting: dict) -> bool:
    """Open one shortlisted posting for its full text. False when capped or stopped."""
    if site not in sites.PARSERS or not posting.get("url") or not state.can_use(site, "detail"):
        return False
    page = session.fetch(posting["url"])
    state.record(site, "detail")
    why = tripped(page.url, page.text)
    if why:
        state.trip(site, why)
        return False
    sites.finish_detail(posting, sites.parse_detail(site, page.html))
    return bool(posting.get("description_text"))


def site_of_source(source: str) -> str:
    return next((s for s in SITES if SOURCE_FOR_SITE[s] == source), "")

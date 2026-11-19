"""Runs targeted searches on the signed-in sites, gently, and returns *hits* in the same shape as
`connectors/board_hits.py` so crosswalk, dedupe, filters and scoring work unchanged.

Rules: only connected sites (or ones that work without signing in); one pace for everything; a
budget per search run for each kind of action (no daily cap); the first bot check or sign-out stops
that site for a day (no retry). `session_for(site)` returns anything with `fetch(url) -> Page`, so
tests pass a fake."""

from . import sites
from .state import LABELS, RUN_BUDGET, SITES, SOURCE_FOR_SITE, AccountState, new_usage, tripped


def search_site(site: str, session, state: AccountState, queries: list[dict], recency_days: int, *,
                usage: dict | None = None, progress=print, model=None, effort=None) -> tuple[list[dict], str]:
    """Hits plus a note ('' when all went normally). Stops at the first trip or at the run's budget."""
    usage = usage if usage is not None else new_usage()
    hits: list[dict] = []
    label = LABELS[site]
    for q in queries:
        if usage["search"] >= RUN_BUDGET["search"]:
            return hits, f"{label}: used this run's {RUN_BUDGET['search']} searches, so it stopped there."
        if not state.can_use(site):
            if state.cooling_until(site):
                return hits, f"{label} is paused for today ({state.status(site)['cooldown_reason']})."
            return hits, f"{label} is not connected."
        page = session.fetch(sites.search_url(site, q["q"], q["location"], recency_days))
        usage["search"] += 1
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


def hydrate_detail(site: str, session, state: AccountState, posting: dict, usage: dict | None = None) -> bool:
    """Open one shortlisted posting for its full text. False when over budget or stopped."""
    usage = usage if usage is not None else new_usage()
    if (site not in sites.PARSERS or not posting.get("url") or usage["detail"] >= RUN_BUDGET["detail"]
            or not state.can_use(site)):
        return False
    page = session.fetch(posting["url"])
    usage["detail"] += 1
    why = tripped(page.url, page.text)
    if why:
        state.trip(site, why)
        return False
    sites.finish_detail(posting, sites.parse_detail(site, page.html))
    return bool(posting.get("description_text"))


def site_of_source(source: str) -> str:
    return next((s for s in SITES if SOURCE_FOR_SITE[s] == source), "")

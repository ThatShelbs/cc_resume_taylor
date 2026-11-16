"""Re-check a finalist against its source right before it is reported."""

from datetime import datetime, timezone

from .connectors import connector_for


def verify_posting(client, posting: dict) -> dict:
    """Sets `verified` (live | unconfirmed | closed) and `last_verified_at`. Returns the posting."""
    route = posting.get("route") or {}
    conn = connector_for(route)
    live = None
    if conn and not posting.get("aggregator_only"):
        try:
            live = conn.verify(client, route, posting)
        except (KeyError, ValueError, TypeError):
            live = None
    elif posting.get("url"):
        status = client.status(posting["url"])
        live = False if status in (404, 410) else None
    posting["verified"] = "live" if live is True else "closed" if live is False else "unconfirmed"
    posting["last_verified_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return posting

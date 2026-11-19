"""The optional Anthropic API key, kept in <data folder>/secrets.json.

Deliberately separate from settings (which the API returns to the browser):
the key is only ever written here, handed to the pipeline subprocess through
its environment, and reported back as "set" plus the last four characters."""

import json
import os
import re
from pathlib import Path

from .fs import atomic_write_text

KEY_PATTERN = re.compile(r"^sk-ant-[A-Za-z0-9_\-]{20,}$")
REDACT_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}")


class BadKey(ValueError):
    pass


def clean_key(raw: str) -> str:
    key = (raw or "").strip().strip('"').strip("'")
    if not KEY_PATTERN.match(key):
        raise BadKey("That doesn't look like an Anthropic API key. It should start with sk-ant- and have no spaces.")
    return key


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> None:
    if not data:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    atomic_write_text(path, json.dumps(data))
    try:
        os.chmod(path, 0o600)  # best effort; a no-op for most Windows setups
    except OSError:
        pass


def load_key(path: Path) -> str | None:
    key = _read(path).get("anthropic_api_key", "")
    return key if isinstance(key, str) and KEY_PATTERN.match(key) else None


def save_key(path: Path, raw: str) -> None:
    _write(path, {**_read(path), "anthropic_api_key": clean_key(raw)})


def clear_key(path: Path) -> None:
    data = _read(path)
    data.pop("anthropic_api_key", None)
    _write(path, data)


def status(path: Path) -> dict:
    """What the UI may know: whether a key is set, where from, and its tail."""
    key = load_key(path)
    if key:
        return {"set": True, "source": "app", "last4": key[-4:]}
    env_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if env_key:
        return {"set": True, "source": "env", "last4": env_key[-4:]}
    return {"set": False, "source": None, "last4": None}


def redact(text: str) -> str:
    return REDACT_PATTERN.sub("sk-ant-***", text)

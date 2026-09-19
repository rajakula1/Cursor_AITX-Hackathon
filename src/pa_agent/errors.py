"""Safe error helpers — never persist raw provider payloads (may contain notes)."""

from __future__ import annotations


def sanitize_exc(exc: BaseException, *, limit: int = 80) -> str:
    """Type + short message only; strip long bodies that may echo prompts/PHI."""
    name = type(exc).__name__
    msg = str(exc).replace("\n", " ").strip()
    if len(msg) > limit:
        msg = msg[:limit] + "…"
    return f"{name}: {msg}" if msg else name

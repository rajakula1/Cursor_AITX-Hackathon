"""Shared criterion `met` definition (gate + score must agree — spec §2.4)."""

from __future__ import annotations

from typing import Optional

MET_CONFIDENCE_THRESHOLD = 0.70


def normalize_text(text: str) -> str:
    """Collapse whitespace + lowercase for quote span checks."""
    return " ".join((text or "").lower().split())


def quote_in_note(quote: Optional[str], note: str) -> bool:
    if not quote or not str(quote).strip():
        return False
    return normalize_text(quote) in normalize_text(note)


def is_criterion_met(
    *,
    value: Optional[str],
    quote_verified: bool,
    confidence: float,
    threshold: float = MET_CONFIDENCE_THRESHOLD,
) -> bool:
    """met iff non-empty value AND quote_verified AND confidence >= threshold."""
    if not value or not str(value).strip():
        return False
    if not quote_verified:
        return False
    return float(confidence) >= threshold

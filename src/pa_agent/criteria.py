"""Shared criterion `met` definition + approval likelihood (spec §2.4)."""

from __future__ import annotations

from typing import Any, Optional, Sequence

MET_CONFIDENCE_THRESHOLD = 0.70
ALTERNATIVE_LIKELIHOOD_THRESHOLD = 0.55


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


def compute_approval_likelihood(
    *,
    policy_criteria: Sequence[dict[str, Any]],
    extractions: Sequence[dict[str, Any]],
    historical_approval_rate: Optional[float] = None,
    blend_historical: bool = True,
) -> float:
    """likelihood = 0.70 * weighted_met_confidence + 0.30 * historical_rate.

    Uses shared `is_criterion_met`. If blend is off or rate missing, first term only.
    """
    by_id = {e.get("criterion_id"): e for e in extractions}
    total_w = 0.0
    weighted = 0.0
    for c in policy_criteria:
        w = float(c.get("weight") or 1.0)
        total_w += w
        ext = by_id.get(c["id"])
        if not ext:
            continue
        conf = float(ext.get("confidence") or 0.0)
        met = is_criterion_met(
            value=ext.get("value"),
            quote_verified=bool(ext.get("quote_verified")),
            confidence=conf,
        )
        if met:
            weighted += w * conf

    if total_w <= 0:
        met_ratio = 0.0
    else:
        met_ratio = weighted / total_w

    if blend_historical and historical_approval_rate is not None:
        hist = max(0.0, min(1.0, float(historical_approval_rate)))
        return round(0.70 * met_ratio + 0.30 * hist, 4)
    return round(met_ratio, 4)

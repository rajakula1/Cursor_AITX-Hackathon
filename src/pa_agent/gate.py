"""Confidence gate — shared `met` evaluation (spec §2.4 / Block 6)."""

from __future__ import annotations

from typing import Any

from pa_agent.criteria import is_criterion_met
from pa_agent.state import CriterionResult, PublicStatus


def evaluate_confidence_gate(
    *,
    policy_criteria: list[dict[str, Any]],
    extractions: list[CriterionResult],
    prior_notes: str | None = None,
) -> dict[str, Any]:
    """All required criteria met → auto_completed; else needs_review + missing ids."""
    by_id = {e.get("criterion_id"): e for e in extractions}
    missing: list[str] = []
    refreshed: list[CriterionResult] = []

    for c in policy_criteria:
        cid = c["id"]
        ext = by_id.get(cid)
        if not ext:
            missing.append(cid)
            continue
        row: CriterionResult = dict(ext)  # type: ignore[assignment]
        row["met"] = is_criterion_met(
            value=row.get("value"),
            quote_verified=bool(row.get("quote_verified")),
            confidence=float(row.get("confidence") or 0.0),
        )
        refreshed.append(row)
        if not row["met"]:
            missing.append(cid)

    seen = {r["criterion_id"] for r in refreshed}
    for ext in extractions:
        if ext.get("criterion_id") not in seen:
            refreshed.append(dict(ext))  # type: ignore[arg-type]

    status: PublicStatus
    notes: str | None
    if policy_criteria and not missing:
        status = "auto_completed"
        notes = None
    else:
        status = "needs_review"
        if missing:
            # Short escalation copy — fields, not the whole case
            labels = []
            for cid in missing:
                ext = by_id.get(cid)
                text = (ext or {}).get("criterion_text") or cid
                labels.append(f"{cid} ({text})" if text != cid else cid)
            notes = "Escalate fields: " + "; ".join(labels)
        else:
            notes = prior_notes or "No policy criteria evaluated."

    return {
        "extractions": refreshed,
        "missing_fields": missing,
        "status": status,
        "human_review_notes": notes or prior_notes,
    }

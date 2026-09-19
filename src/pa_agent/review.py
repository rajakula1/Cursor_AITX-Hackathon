"""Human review helpers: re-score without re-extracting verified fields."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pa_agent.criteria import (
    ALTERNATIVE_LIKELIHOOD_THRESHOLD,
    compute_approval_likelihood,
    is_criterion_met,
    quote_in_note,
)
from pa_agent.gate import evaluate_confidence_gate
from pa_agent.tools.draft import build_export_markdown, build_pa_form_deterministic
from pa_agent.tools.formulary import get_formulary_alternative
from pa_agent.tools.save_case import save_case


def apply_human_edits(
    state: dict[str, Any],
    edits: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Apply field-level edits. Quote must still span-check against the note."""
    note = state.get("clinical_note") or ""
    updated = []
    for raw in state.get("extractions") or []:
        ext = dict(raw)
        cid = ext.get("criterion_id")
        if cid and cid in edits:
            patch = edits[cid]
            if "value" in patch:
                ext["value"] = patch["value"] or None
            if "quote" in patch:
                ext["quote"] = patch["quote"] or None
            if "confidence" in patch and patch["confidence"] is not None:
                ext["confidence"] = float(patch["confidence"])
            prior = ext.get("critic_note") or ""
            ext["critic_note"] = (prior + " | human_edit").strip(" |")

        verified = quote_in_note(ext.get("quote"), note)
        ext["quote_verified"] = verified
        if not verified:
            ext["confidence"] = 0.0
        ext["met"] = is_criterion_met(
            value=ext.get("value"),
            quote_verified=verified,
            confidence=float(ext.get("confidence") or 0.0),
        )
        updated.append(ext)

    out = deepcopy(state)
    out["extractions"] = updated
    return out


def rescore_case(state: dict[str, Any]) -> dict[str, Any]:
    """Re-enter draft → likelihood → alternative → gate → finalize (no extract/critic)."""
    current = deepcopy(state)

    refreshed = []
    for raw in current.get("extractions") or []:
        ext = dict(raw)
        ext["met"] = is_criterion_met(
            value=ext.get("value"),
            quote_verified=bool(ext.get("quote_verified")),
            confidence=float(ext.get("confidence") or 0.0),
        )
        refreshed.append(ext)
    current["extractions"] = refreshed

    form = build_pa_form_deterministic(current)  # type: ignore[arg-type]
    current["draft_pa_form"] = form
    current["missing_fields"] = list(form.get("missing_fields") or [])

    score = compute_approval_likelihood(
        policy_criteria=list(current.get("policy_criteria") or []),
        extractions=list(current.get("extractions") or []),
        historical_approval_rate=current.get("historical_approval_rate"),
        blend_historical=True,
    )
    current["approval_likelihood"] = score

    if score < ALTERNATIVE_LIKELIHOOD_THRESHOLD:
        drug_class = current.get("drug_class")
        payer = current.get("payer_name")
        if drug_class and payer:
            alt = get_formulary_alternative(drug_class, payer)
            if alt:
                label = alt["alternative_drug"]
                if not alt.get("requires_pa"):
                    label = f"{label} (no PA required)"
                current["alternative_suggestion"] = label
            else:
                current["alternative_suggestion"] = (
                    "No same-class alternative found in formulary."
                )
    else:
        current["alternative_suggestion"] = None

    gated = evaluate_confidence_gate(
        policy_criteria=list(current.get("policy_criteria") or []),
        extractions=list(current.get("extractions") or []),  # type: ignore[arg-type]
        prior_notes=current.get("human_review_notes"),
    )
    current.update(gated)

    status = current.get("status") or "needs_review"
    draft = dict(current.get("draft_pa_form") or form)
    draft["missing_fields"] = list(current.get("missing_fields") or [])
    draft["export_markdown"] = build_export_markdown(
        draft,  # type: ignore[arg-type]
        status=status,
        case_id=current.get("case_id"),
        approval_likelihood=current.get("approval_likelihood"),
        alternative_suggestion=current.get("alternative_suggestion"),
        human_review_notes=current.get("human_review_notes"),
    )
    current["draft_pa_form"] = draft
    save_case(current)
    return current

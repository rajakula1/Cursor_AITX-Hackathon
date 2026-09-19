"""LangGraph nodes — extract + quote verify live; critic/draft/score still stubbed."""

from __future__ import annotations

import uuid
from typing import Any

from pa_agent.criteria import is_criterion_met, quote_in_note
from pa_agent.graph.helpers import append_error
from pa_agent.state import CriterionResult, PAState
from pa_agent.tools.extract import extract_all
from pa_agent.tools.formulary import get_formulary_alternative
from pa_agent.tools.policy import get_payer_policy
from pa_agent.tools.save_case import save_case


def intake_node(state: PAState) -> dict[str, Any]:
    """Validate inputs, generate case_id, normalize aliases, upsert case."""
    try:
        errors: list[str] = []
        drug = (state.get("drug_name") or "").strip()
        diagnosis = (state.get("diagnosis_code") or "").strip()
        payer = (state.get("payer_name") or "").strip()
        note = (state.get("clinical_note") or "").strip()

        if not drug:
            errors.append("drug_name is empty")
        if not diagnosis:
            errors.append("diagnosis_code is empty")
        if not payer:
            errors.append("payer_name is empty")
        if not note:
            errors.append("clinical_note is empty")

        case_id = (state.get("case_id") or "").strip() or str(uuid.uuid4())

        # Alias resolution (canonical names applied when resolvable)
        policy_preview = get_payer_policy(drug or "?", diagnosis or "?", payer or "?")
        canonical_drug = policy_preview.get("canonical_drug") or drug
        canonical_payer = policy_preview.get("canonical_payer") or payer
        drug_class = policy_preview.get("drug_class")

        updates: dict[str, Any] = {
            "case_id": case_id,
            "drug_name": canonical_drug,
            "diagnosis_code": diagnosis,
            "payer_name": canonical_payer,
            "clinical_note": note,
            "drug_class": drug_class,
            "error_log": list(state.get("error_log") or []),
        }

        if errors:
            reason = "Intake validation failed: " + "; ".join(errors)
            updates["status"] = "needs_review"
            updates["human_review_notes"] = reason
            updates["error_log"] = updates["error_log"] + [reason]
            save_case({**state, **updates})
            return updates

        # Unresolvable aliases → needs_review (coverage will also see not_found)
        if policy_preview["lookup"] == "not_found" and (
            "Unresolvable" in (policy_preview.get("reason") or "")
        ):
            reason = policy_preview["reason"] or "Unresolvable alias"
            updates["status"] = "needs_review"
            updates["human_review_notes"] = reason
            updates["policy_lookup"] = "not_found"

        save_case({**state, **updates})
        return updates
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "intake_node", exc)


def coverage_check_node(state: PAState) -> dict[str, Any]:
    """Lookup payer policy. Sets policy_lookup / pa_required / criteria."""
    try:
        # Skip re-work if intake already failed hard on empty inputs
        if state.get("human_review_notes") and "Intake validation failed" in (
            state.get("human_review_notes") or ""
        ):
            return {
                "policy_lookup": "error",
                "pa_required": None,
                "policy_criteria": [],
            }

        result = get_payer_policy(
            state["drug_name"], state["diagnosis_code"], state["payer_name"]
        )
        updates: dict[str, Any] = {
            "policy_lookup": result["lookup"],
            "pa_required": result["requires_pa"],
            "policy_criteria": list(result["criteria"] or []),
            "drug_class": result["drug_class"] or state.get("drug_class"),
            "historical_approval_rate": result["historical_approval_rate"],
        }
        if result.get("canonical_drug"):
            updates["drug_name"] = result["canonical_drug"]
        if result.get("canonical_payer"):
            updates["payer_name"] = result["canonical_payer"]

        if result["lookup"] != "found":
            reason = result.get("reason") or f"Policy lookup={result['lookup']}"
            updates["status"] = "needs_review"
            updates["human_review_notes"] = reason
            # Spec: never treat not_found as no_pa_required
            updates["pa_required"] = None
        elif result["requires_pa"] is False:
            updates["status"] = "no_pa_required"
            updates["human_review_notes"] = (
                "Policy found: prior authorization is not required for this "
                "drug / diagnosis / payer."
            )
        # pa_required True → leave status for gate/finalize after extraction path
        return updates
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "coverage_check_node", exc)


def justification_extraction_node(state: PAState) -> dict[str, Any]:
    """OpenRouter Haiku fan-out per criterion; cache by (note_hash, criterion_id)."""
    try:
        import asyncio

        criteria = list(state.get("policy_criteria") or [])
        note = state.get("clinical_note") or ""
        pairs = asyncio.run(extract_all(criteria, note))

        extractions: list[CriterionResult] = []
        for criterion, out in pairs:
            value = out.get("value")
            quote = out.get("quote")
            confidence = float(out.get("confidence") or 0.0)
            extractions.append(
                {
                    "criterion_id": str(criterion["id"]),
                    "criterion_text": str(criterion.get("text") or ""),
                    "value": value,
                    "quote": quote,
                    "quote_verified": False,  # set by quote_verify_node
                    "confidence": confidence,
                    "met": False,
                    "critic_note": "",
                }
            )
        return {"extractions": extractions}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "justification_extraction_node", exc)


def quote_verify_node(state: PAState) -> dict[str, Any]:
    """Deterministic: quote_verified = normalized(quote) in normalized(note).

    Failed span → confidence = 0; value kept; met cannot become true.
    """
    try:
        note = state.get("clinical_note") or ""
        updated: list[CriterionResult] = []
        for raw in state.get("extractions") or []:
            ext: CriterionResult = dict(raw)  # type: ignore[assignment]
            verified = quote_in_note(ext.get("quote"), note)
            ext["quote_verified"] = verified
            if not verified:
                ext["confidence"] = 0.0
            ext["met"] = is_criterion_met(
                value=ext.get("value"),
                quote_verified=ext["quote_verified"],
                confidence=float(ext.get("confidence") or 0.0),
            )
            updated.append(ext)
        return {"extractions": updated}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "quote_verify_node", exc)


def critic_node(state: PAState) -> dict[str, Any]:
    """One batched Sonnet critic over all extractions. May lower confidence only."""
    try:
        import asyncio

        from pa_agent.tools.critique import apply_critic_decisions, critique_all

        extractions = list(state.get("extractions") or [])
        if not extractions:
            return {"extractions": []}

        note = state.get("clinical_note") or ""
        decisions = asyncio.run(critique_all(extractions, note))  # type: ignore[arg-type]
        updated = apply_critic_decisions(extractions, decisions)  # type: ignore[arg-type]
        return {"extractions": updated}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "critic_node", exc)


def pa_draft_builder_node(state: PAState) -> dict[str, Any]:
    """Fill typed PAForm from critic-adjusted fields; narrative = verified quotes only."""
    try:
        import asyncio

        from pa_agent.tools.draft import build_pa_form

        form = asyncio.run(build_pa_form(state))
        return {"draft_pa_form": form, "missing_fields": list(form.get("missing_fields") or [])}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "pa_draft_builder_node", exc)


def approval_likelihood_node(state: PAState) -> dict[str, Any]:
    """Deterministic likelihood (spec §2.4); shares `met` with the gate."""
    try:
        from pa_agent.criteria import compute_approval_likelihood

        score = compute_approval_likelihood(
            policy_criteria=list(state.get("policy_criteria") or []),
            extractions=list(state.get("extractions") or []),
            historical_approval_rate=state.get("historical_approval_rate"),
            blend_historical=True,
        )
        return {"approval_likelihood": score}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "approval_likelihood_node", exc)


def alternative_suggestion_node(state: PAState) -> dict[str, Any]:
    """Formulary alternative when likelihood < 0.55; prefer requires_pa=false."""
    try:
        drug_class = state.get("drug_class")
        payer = state.get("payer_name")
        if not drug_class or not payer:
            return {
                "alternative_suggestion": "No same-class alternative found in formulary."
            }
        alt = get_formulary_alternative(drug_class, payer)
        if not alt:
            return {
                "alternative_suggestion": "No same-class alternative found in formulary."
            }
        label = alt["alternative_drug"]
        if not alt.get("requires_pa"):
            label = f"{label} (no PA required)"
        return {"alternative_suggestion": label}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "alternative_suggestion_node", exc)


def confidence_gate_node(state: PAState) -> dict[str, Any]:
    """Deterministic gate using shared `is_criterion_met` via evaluate_confidence_gate."""
    try:
        from pa_agent.gate import evaluate_confidence_gate

        return evaluate_confidence_gate(
            policy_criteria=list(state.get("policy_criteria") or []),
            extractions=list(state.get("extractions") or []),  # type: ignore[arg-type]
            prior_notes=state.get("human_review_notes"),
        )
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "confidence_gate_node", exc)


def finalize_node(state: PAState) -> dict[str, Any]:
    """Upsert pa_cases, emit paste-ready export_markdown, escalate fields not cases."""
    try:
        from pa_agent.tools.draft import build_export_markdown

        status = state.get("status") or "needs_review"
        if status not in ("no_pa_required", "auto_completed", "needs_review"):
            status = "needs_review"

        missing = list(state.get("missing_fields") or [])
        notes = state.get("human_review_notes")
        # Escalation copy for review path when gate didn't already write one
        if status == "needs_review" and missing and not notes:
            notes = "Escalate fields: " + ", ".join(missing)

        draft = state.get("draft_pa_form")
        if isinstance(draft, dict):
            draft_out = dict(draft)
        else:
            draft_out = {
                "drug_name": state.get("drug_name") or "",
                "diagnosis_code": state.get("diagnosis_code") or "",
                "payer_name": state.get("payer_name") or "",
                "clinical_justification": (
                    "Prior authorization is not required."
                    if status == "no_pa_required"
                    else ""
                ),
                "criteria_checklist": [],
                "quantity": None,
                "duration": None,
                "missing_fields": missing,
                "export_markdown": "",
            }

        draft_out["missing_fields"] = missing
        draft_out["export_markdown"] = build_export_markdown(
            draft_out,  # type: ignore[arg-type]
            status=status,
            case_id=state.get("case_id"),
            approval_likelihood=state.get("approval_likelihood"),
            alternative_suggestion=state.get("alternative_suggestion"),
            human_review_notes=notes,
        )

        updates: dict[str, Any] = {
            "status": status,
            "missing_fields": missing,
            "human_review_notes": notes,
            "draft_pa_form": draft_out,
        }
        # Full upsert of merged state
        save_case({**state, **updates})
        return updates
    except Exception as exc:  # noqa: BLE001
        fallback = append_error(state, "finalize_node", exc)
        try:
            save_case({**state, **fallback})
        except Exception:  # noqa: BLE001
            pass
        return fallback

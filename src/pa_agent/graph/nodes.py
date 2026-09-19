"""LangGraph nodes — Block 2: intake/coverage/finalize real; LLM path stubbed."""

from __future__ import annotations

import uuid
from typing import Any

from pa_agent.graph.helpers import append_error
from pa_agent.state import PAState
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
    """Stub (Block 2). Real Haiku fan-out in Block 3."""
    try:
        return {"extractions": list(state.get("extractions") or [])}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "justification_extraction_node", exc)


def quote_verify_node(state: PAState) -> dict[str, Any]:
    """Stub (Block 2). Deterministic span check in Block 3."""
    try:
        return {}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "quote_verify_node", exc)


def critic_node(state: PAState) -> dict[str, Any]:
    """Stub (Block 2). Batched Sonnet critic in Block 4."""
    try:
        return {}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "critic_node", exc)


def pa_draft_builder_node(state: PAState) -> dict[str, Any]:
    """Stub (Block 2). Typed PAForm draft in Block 5."""
    try:
        return {"draft_pa_form": state.get("draft_pa_form")}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "pa_draft_builder_node", exc)


def approval_likelihood_node(state: PAState) -> dict[str, Any]:
    """Stub (Block 2). Deterministic formula in Block 5."""
    try:
        # Leave None so alternative routing stays off until scoring exists
        return {"approval_likelihood": state.get("approval_likelihood")}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "approval_likelihood_node", exc)


def alternative_suggestion_node(state: PAState) -> dict[str, Any]:
    """Stub-capable: real formulary lookup when likelihood < 0.55."""
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
        return {"alternative_suggestion": alt["alternative_drug"]}
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "alternative_suggestion_node", exc)


def confidence_gate_node(state: PAState) -> dict[str, Any]:
    """Deterministic gate: all required criteria met → auto_completed."""
    try:
        criteria = state.get("policy_criteria") or []
        extractions = state.get("extractions") or []
        by_id = {e.get("criterion_id"): e for e in extractions}

        missing: list[str] = []
        for c in criteria:
            cid = c["id"]
            ext = by_id.get(cid)
            if not ext or not ext.get("met"):
                missing.append(cid)

        if criteria and not missing:
            status = "auto_completed"
            notes = None
        else:
            status = "needs_review"
            notes = (
                "Unmet criteria: " + ", ".join(missing)
                if missing
                else "No policy criteria evaluated."
            )

        return {
            "missing_fields": missing,
            "status": status,
            "human_review_notes": notes or state.get("human_review_notes"),
        }
    except Exception as exc:  # noqa: BLE001
        return append_error(state, "confidence_gate_node", exc)


def finalize_node(state: PAState) -> dict[str, Any]:
    """Upsert case, emit export_markdown, never throw to UI."""
    try:
        status = state.get("status") or "needs_review"
        # Public status is never "error"
        if status not in ("no_pa_required", "auto_completed", "needs_review"):
            status = "needs_review"

        draft = state.get("draft_pa_form")
        export = ""
        if draft and isinstance(draft, dict) and draft.get("export_markdown"):
            export = str(draft["export_markdown"])
        else:
            export = _build_export_markdown(state, status)

        draft_out = dict(draft) if isinstance(draft, dict) else {
            "drug_name": state.get("drug_name") or "",
            "diagnosis_code": state.get("diagnosis_code") or "",
            "payer_name": state.get("payer_name") or "",
            "clinical_justification": "",
            "criteria_checklist": [],
            "quantity": None,
            "duration": None,
            "missing_fields": list(state.get("missing_fields") or []),
            "export_markdown": export,
        }
        draft_out["export_markdown"] = export
        draft_out["missing_fields"] = list(state.get("missing_fields") or [])

        updates: dict[str, Any] = {
            "status": status,
            "draft_pa_form": draft_out,
        }
        save_case({**state, **updates})
        return updates
    except Exception as exc:  # noqa: BLE001
        # Last resort: still try to surface needs_review
        fallback = append_error(state, "finalize_node", exc)
        try:
            save_case({**state, **fallback})
        except Exception:  # noqa: BLE001
            pass
        return fallback


def _build_export_markdown(state: PAState, status: str) -> str:
    lines = [
        "# Prior Authorization Draft",
        "",
        "> Demo data — not real PHI.",
        "",
        f"- **Status:** {status}",
        f"- **Case ID:** {state.get('case_id') or ''}",
        f"- **Drug:** {state.get('drug_name') or ''}",
        f"- **Diagnosis:** {state.get('diagnosis_code') or ''}",
        f"- **Payer:** {state.get('payer_name') or ''}",
    ]
    if state.get("approval_likelihood") is not None:
        lines.append(f"- **Approval likelihood:** {state['approval_likelihood']:.2f}")
    if state.get("alternative_suggestion"):
        lines.append(f"- **Alternative:** {state['alternative_suggestion']}")
    if state.get("human_review_notes"):
        lines.extend(["", "## Review notes", state["human_review_notes"] or ""])
    missing = state.get("missing_fields") or []
    if missing:
        lines.extend(["", "## Fields needing review", ", ".join(missing)])
    lines.append("")
    return "\n".join(lines)

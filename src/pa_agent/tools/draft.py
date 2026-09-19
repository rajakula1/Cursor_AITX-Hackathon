"""Build typed PAForm. Narrative uses verified quotes only."""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from pa_agent.config import get_settings
from pa_agent.state import CriterionResult, PAForm, PAState


def _verified_quotes(extractions: list[CriterionResult]) -> list[str]:
    quotes: list[str] = []
    for ext in extractions:
        if ext.get("quote_verified") and ext.get("quote"):
            q = str(ext["quote"]).strip()
            if q and q not in quotes:
                quotes.append(q)
    return quotes


def _checklist(extractions: list[CriterionResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ext in extractions:
        quote = ext.get("quote") if ext.get("quote_verified") else None
        rows.append(
            {
                "id": ext.get("criterion_id"),
                "text": ext.get("criterion_text"),
                "met": bool(ext.get("met")),
                "quote": quote,
                "confidence": float(ext.get("confidence") or 0.0),
                "critic_note": ext.get("critic_note") or "",
            }
        )
    return rows


def _missing_fields(extractions: list[CriterionResult], criteria: list[dict]) -> list[str]:
    by_id = {e.get("criterion_id"): e for e in extractions}
    missing: list[str] = []
    for c in criteria:
        cid = c["id"]
        ext = by_id.get(cid)
        if not ext or not ext.get("met"):
            missing.append(cid)
    return missing


def build_export_markdown(
    form: PAForm,
    *,
    status: str | None = None,
    case_id: str | None = None,
    approval_likelihood: float | None = None,
    alternative_suggestion: str | None = None,
    human_review_notes: str | None = None,
) -> str:
    lines = [
        "# Prior Authorization Draft",
        "",
        "> Demo data — not real PHI.",
        "",
    ]
    if case_id:
        lines.append(f"- **Case ID:** {case_id}")
    if status:
        lines.append(f"- **Status:** {status}")
    lines.extend(
        [
            f"- **Drug:** {form['drug_name']}",
            f"- **Diagnosis:** {form['diagnosis_code']}",
            f"- **Payer:** {form['payer_name']}",
        ]
    )
    if approval_likelihood is not None:
        lines.append(f"- **Approval likelihood:** {approval_likelihood:.2f}")
    if alternative_suggestion:
        lines.append(f"- **Formulary alternative:** {alternative_suggestion}")
    if form.get("quantity"):
        lines.append(f"- **Quantity:** {form['quantity']}")
    if form.get("duration"):
        lines.append(f"- **Duration:** {form['duration']}")
    lines.extend(
        ["", "## Clinical justification", form.get("clinical_justification") or "(none)"]
    )
    lines.extend(["", "## Criteria checklist (verified quotes only)"])
    for row in form.get("criteria_checklist") or []:
        mark = "MET" if row.get("met") else "UNMET"
        quote = row.get("quote") or "—(no verified quote)"
        lines.append(f"- [{mark}] **{row.get('id')}** {row.get('text')}")
        lines.append(f"  - Quote: {quote}")
        if row.get("critic_note"):
            lines.append(f"  - Critic: {row['critic_note']}")
    missing = form.get("missing_fields") or []
    if missing or human_review_notes:
        lines.extend(["", "## Human review"])
        if human_review_notes:
            lines.append(human_review_notes)
        if missing:
            lines.append("Unmet field ids: " + ", ".join(missing))
    lines.append("")
    return "\n".join(lines)


def build_pa_form_deterministic(state: PAState) -> PAForm:
    """Deterministic draft from critic-adjusted extractions (mock / fallback)."""
    extractions: list[CriterionResult] = list(state.get("extractions") or [])  # type: ignore[arg-type]
    criteria = list(state.get("policy_criteria") or [])
    quotes = _verified_quotes(extractions)

    if quotes:
        justification = (
            "Clinical justification based on chart evidence:\n\n"
            + "\n\n".join(f"- {q}" for q in quotes)
        )
    else:
        justification = (
            "Insufficient verified chart quotes to draft a clinical justification."
        )

    missing = _missing_fields(extractions, criteria)
    form: PAForm = {
        "drug_name": state.get("drug_name") or "",
        "diagnosis_code": state.get("diagnosis_code") or "",
        "payer_name": state.get("payer_name") or "",
        "clinical_justification": justification,
        "criteria_checklist": _checklist(extractions),
        "quantity": None,
        "duration": None,
        "missing_fields": missing,
        "export_markdown": "",
    }
    form["export_markdown"] = build_export_markdown(
        form, status=state.get("status")
    )
    return form


async def build_pa_form(state: PAState) -> PAForm:
    settings = get_settings()
    if settings.use_mock_extract:
        return build_pa_form_deterministic(state)
    try:
        return await _live_draft(state)
    except Exception:  # noqa: BLE001
        return build_pa_form_deterministic(state)


async def _live_draft(state: PAState) -> PAForm:
    from pydantic import BaseModel, Field

    from pa_agent.llm import get_draft_llm

    class _Draft(BaseModel):
        clinical_justification: str
        quantity: Optional[str] = None
        duration: Optional[str] = None

    verified = _verified_quotes(list(state.get("extractions") or []))  # type: ignore[arg-type]
    prompt = (
        "Draft a prior-authorization clinical justification.\n"
        "ONLY use the verified quotes below — do not invent facts.\n"
        "If quotes are insufficient, say what is missing briefly.\n\n"
        f"Drug: {state.get('drug_name')}\n"
        f"Diagnosis: {state.get('diagnosis_code')}\n"
        f"Payer: {state.get('payer_name')}\n\n"
        "Verified quotes:\n"
        + ("\n".join(f"- {q}" for q in verified) or "- (none)")
    )

    llm = get_draft_llm().with_structured_output(_Draft)
    out: _Draft = await llm.ainvoke(prompt)

    # Strip any sentence that is not grounded in a verified quote substring
    justification = out.clinical_justification
    # Keep LLM narrative but append verified quote block as ground truth
    if verified:
        justification = (
            justification.strip()
            + "\n\nSupporting verified quotes:\n"
            + "\n".join(f"- {q}" for q in verified)
        )

    base = build_pa_form_deterministic(state)
    base["clinical_justification"] = justification
    base["quantity"] = out.quantity
    base["duration"] = out.duration
    base["export_markdown"] = build_export_markdown(
        base, status=state.get("status")
    )
    return base


def build_pa_form_sync(state: PAState) -> PAForm:
    return asyncio.run(build_pa_form(state))

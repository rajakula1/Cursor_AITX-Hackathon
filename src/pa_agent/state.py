"""Frozen PA graph state contracts (spec §2.1)."""

from __future__ import annotations

from typing import Literal, NotRequired, Optional, TypedDict


PolicyLookup = Literal["found", "not_found", "error"]
PublicStatus = Literal["no_pa_required", "auto_completed", "needs_review"]


class CriterionResult(TypedDict):
    criterion_id: str
    criterion_text: str
    value: Optional[str]
    quote: Optional[str]
    quote_verified: bool
    confidence: float  # 0.0–1.0, post-critic
    met: bool
    critic_note: str


class PAForm(TypedDict):
    drug_name: str
    diagnosis_code: str
    payer_name: str
    clinical_justification: str
    criteria_checklist: list[dict]  # id, text, met, quote
    quantity: Optional[str]
    duration: Optional[str]
    missing_fields: list[str]
    export_markdown: str


class PAState(TypedDict):
    case_id: str
    drug_name: str
    diagnosis_code: str
    payer_name: str
    clinical_note: str
    drug_class: Optional[str]

    policy_lookup: Optional[PolicyLookup]
    pa_required: Optional[bool]
    policy_criteria: list[dict]  # [{id, text, weight}]

    extractions: list[CriterionResult]
    draft_pa_form: Optional[PAForm]
    missing_fields: list[str]

    approval_likelihood: Optional[float]
    alternative_suggestion: Optional[str]

    status: PublicStatus
    human_review_notes: Optional[str]
    error_log: list[str]

    # Internal (not in public UI contract; used by likelihood blend)
    historical_approval_rate: NotRequired[Optional[float]]

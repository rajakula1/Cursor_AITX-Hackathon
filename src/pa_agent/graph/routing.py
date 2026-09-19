"""Conditional edge routers for the PA graph."""

from __future__ import annotations

from typing import Literal

from pa_agent.criteria import ALTERNATIVE_LIKELIHOOD_THRESHOLD
from pa_agent.state import PAState

AfterCoverage = Literal["finalize", "justification_extraction"]
AfterLikelihood = Literal["alternative_suggestion", "confidence_gate"]


def route_after_coverage(state: PAState) -> AfterCoverage:
    """Early-exit to finalize when policy missing or PA not required."""
    # Intake validation failure already set needs_review
    notes = state.get("human_review_notes") or ""
    if "Intake validation failed" in notes:
        return "finalize"

    lookup = state.get("policy_lookup")
    if lookup != "found":
        return "finalize"

    if state.get("pa_required") is False:
        return "finalize"

    if state.get("pa_required") is True:
        return "justification_extraction"

    # Ambiguous → review, do not invent no_pa_required
    return "finalize"


def route_after_likelihood(state: PAState) -> AfterLikelihood:
    likelihood = state.get("approval_likelihood")
    if likelihood is not None and likelihood < ALTERNATIVE_LIKELIHOOD_THRESHOLD:
        return "alternative_suggestion"
    return "confidence_gate"

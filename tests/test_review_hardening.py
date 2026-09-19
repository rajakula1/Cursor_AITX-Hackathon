"""Regression tests for code-review hardening patches."""

from __future__ import annotations

from pa_agent.criteria import MIN_QUOTE_CHARS, quote_in_note
from pa_agent.errors import sanitize_exc
from pa_agent.graph.helpers import append_error
from pa_agent.state import CriterionResult, PAState
from pa_agent.tools.critique import apply_critic_decisions
from pa_agent.tools.draft import build_pa_form_deterministic


def test_sanitize_exc_truncates_and_drops_newlines():
    huge = Exception("NOTE:\n" + ("patient secret " * 40))
    out = sanitize_exc(huge, limit=80)
    assert "Exception:" in out
    assert "\n" not in out
    assert len(out) <= 80 + len("Exception: ") + 1  # allow ellipsis


def test_append_error_uses_sanitized_message():
    state: PAState = {
        "case_id": "x",
        "drug_name": "a",
        "diagnosis_code": "b",
        "payer_name": "c",
        "clinical_note": "secret note content should not appear raw",
        "drug_class": None,
        "policy_lookup": None,
        "pa_required": None,
        "policy_criteria": [],
        "extractions": [],
        "draft_pa_form": None,
        "missing_fields": [],
        "approval_likelihood": None,
        "alternative_suggestion": None,
        "status": "needs_review",
        "human_review_notes": None,
        "error_log": [],
    }
    # Long payload that would otherwise persist in error_log
    exc = RuntimeError("prefix " + ("LEAKED_NOTE_FRAGMENT " * 30))
    out = append_error(state, "test_node", exc)
    assert out["status"] == "needs_review"
    logged = out["error_log"][-1]
    assert logged.startswith("test_node: RuntimeError:")
    assert "LEAKED_NOTE_FRAGMENT " * 5 not in logged
    assert len(logged) < 120


def test_short_quote_cannot_verify():
    note = "Patient has negative TB screening within past 12 months is on file today."
    assert not quote_in_note("negative", note)
    assert len("negative") < MIN_QUOTE_CHARS
    long_q = "negative TB screening within past 12 months is on file"
    assert quote_in_note(long_q, note)


def test_critic_reject_all_fail_closed_zeros_met():
    extractions: list[CriterionResult] = [
        {
            "criterion_id": "c1",
            "criterion_text": "RA",
            "value": "yes",
            "quote": "documented diagnosis of rheumatoid arthritis confirmed",
            "quote_verified": True,
            "confidence": 0.95,
            "met": True,
            "critic_note": "",
        }
    ]
    decisions = [
        {
            "criterion_id": "c1",
            "action": "reject",
            "confidence": 0.0,
            "reason": "Critic unavailable; fail closed → review.",
        }
    ]
    out = apply_critic_decisions(extractions, decisions)
    assert out[0]["confidence"] == 0.0
    assert out[0]["met"] is False


def test_deterministic_draft_only_uses_verified_quotes():
    state: PAState = {
        "case_id": "x",
        "drug_name": "adalimumab",
        "diagnosis_code": "M06.9",
        "payer_name": "UnitedHealthcare",
        "clinical_note": "note",
        "drug_class": "TNF inhibitor",
        "policy_lookup": "found",
        "pa_required": True,
        "policy_criteria": [{"id": "c1", "text": "RA", "weight": 1.0}],
        "extractions": [
            {
                "criterion_id": "c1",
                "criterion_text": "RA",
                "value": "RA",
                "quote": "Documented diagnosis of rheumatoid arthritis in chart.",
                "quote_verified": True,
                "confidence": 0.9,
                "met": True,
                "critic_note": "confirm: ok",
            },
            {
                "criterion_id": "c3",
                "criterion_text": "TB",
                "value": "neg",
                "quote": "Hallucinated QuantiFERON result not in note at all.",
                "quote_verified": False,
                "confidence": 0.0,
                "met": False,
                "critic_note": "reject: span",
            },
        ],
        "draft_pa_form": None,
        "missing_fields": ["c3"],
        "approval_likelihood": 0.4,
        "alternative_suggestion": None,
        "status": "needs_review",
        "human_review_notes": None,
        "error_log": [],
    }
    form = build_pa_form_deterministic(state)
    assert "Documented diagnosis of rheumatoid arthritis in chart." in form[
        "clinical_justification"
    ]
    assert "Hallucinated QuantiFERON" not in form["clinical_justification"]
    assert "Hallucinated QuantiFERON" not in form["export_markdown"]

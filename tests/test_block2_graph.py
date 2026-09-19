"""Block 2: graph skeleton — Fixture A + unknown policy routing."""

from __future__ import annotations

from pa_agent.data.seed_store import clear_cases
from pa_agent.fixtures import load_fixture
from pa_agent.graph import build_graph, run_case
from pa_agent.graph.routing import route_after_coverage, route_after_likelihood
from pa_agent.state import PAState


def setup_function():
    clear_cases()
    # Drop cached graph so node edits during hackathon reload cleanly in tests
    from pa_agent.graph import get_compiled_graph

    get_compiled_graph.cache_clear()


def test_fixture_a_no_pa_required_early_finalize():
    fx = load_fixture("fixture_a_no_pa")
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    assert result["status"] == "no_pa_required"
    assert result["policy_lookup"] == "found"
    assert result["pa_required"] is False
    assert result["extractions"] == []
    assert result["draft_pa_form"] is not None
    assert result["draft_pa_form"]["export_markdown"]
    assert result["case_id"]


def test_unknown_policy_needs_review_never_no_pa():
    result = run_case(
        drug_name="adalimumab",
        diagnosis_code="Z99.99",
        payer_name="UnitedHealthcare",
        clinical_note="Demo data — not real PHI. Short note for unknown DX.",
    )
    assert result["status"] == "needs_review"
    assert result["policy_lookup"] == "not_found"
    assert result["pa_required"] is None
    assert result["status"] != "no_pa_required"
    assert result["human_review_notes"]


def test_unresolvable_payer_needs_review():
    result = run_case(
        drug_name="Humira",
        diagnosis_code="M06.9",
        payer_name="TotallyFakePayer",
        clinical_note="Demo data — not real PHI. Alias miss.",
    )
    assert result["status"] == "needs_review"
    assert result["policy_lookup"] == "not_found"


def test_empty_note_needs_review_no_crash():
    result = run_case(
        drug_name="Ozempic",
        diagnosis_code="E11.9",
        payer_name="Aetna",
        clinical_note="",
    )
    assert result["status"] == "needs_review"
    assert "clinical_note is empty" in (result.get("human_review_notes") or "")


def test_pa_required_unsupported_note_needs_review():
    """PA-required with a note that supports no criteria → all fields missing."""
    result = run_case(
        drug_name="Humira",
        diagnosis_code="M06.9",
        payer_name="UHC",
        clinical_note=(
            "Demo data — not real PHI. Patient visited clinic for a medication "
            "refill discussion only. Labs deferred. No specialist notes on file."
        ),
    )
    assert result["policy_lookup"] == "found"
    assert result["pa_required"] is True
    assert result["status"] == "needs_review"
    assert set(result["missing_fields"]) == {"c1", "c2", "c3", "c4"}


def test_route_after_coverage_branches():
    base: PAState = {
        "case_id": "x",
        "drug_name": "adalimumab",
        "diagnosis_code": "M06.9",
        "payer_name": "UnitedHealthcare",
        "clinical_note": "n",
        "drug_class": "TNF inhibitor",
        "policy_lookup": "found",
        "pa_required": False,
        "policy_criteria": [],
        "extractions": [],
        "draft_pa_form": None,
        "missing_fields": [],
        "approval_likelihood": None,
        "alternative_suggestion": None,
        "status": "no_pa_required",
        "human_review_notes": None,
        "error_log": [],
    }
    assert route_after_coverage(base) == "finalize"

    base["pa_required"] = True
    assert route_after_coverage(base) == "justification_extraction"

    base["policy_lookup"] = "not_found"
    base["pa_required"] = None
    assert route_after_coverage(base) == "finalize"


def test_route_after_likelihood():
    state: PAState = {
        "case_id": "x",
        "drug_name": "a",
        "diagnosis_code": "b",
        "payer_name": "c",
        "clinical_note": "n",
        "drug_class": None,
        "policy_lookup": "found",
        "pa_required": True,
        "policy_criteria": [],
        "extractions": [],
        "draft_pa_form": None,
        "missing_fields": [],
        "approval_likelihood": 0.4,
        "alternative_suggestion": None,
        "status": "needs_review",
        "human_review_notes": None,
        "error_log": [],
    }
    assert route_after_likelihood(state) == "alternative_suggestion"
    state["approval_likelihood"] = 0.7
    assert route_after_likelihood(state) == "confidence_gate"
    state["approval_likelihood"] = None
    assert route_after_likelihood(state) == "confidence_gate"


def test_graph_has_ten_nodes():
    graph = build_graph()
    names = set(graph.get_graph().nodes)
    expected = {
        "intake",
        "coverage_check",
        "justification_extraction",
        "quote_verify",
        "critic",
        "pa_draft_builder",
        "approval_likelihood",
        "alternative_suggestion",
        "confidence_gate",
        "finalize",
        "__start__",
    }
    assert expected.issubset(names)

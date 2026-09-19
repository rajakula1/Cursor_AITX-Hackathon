"""Block 6: confidence gate + pa_cases upsert + export markdown."""

from __future__ import annotations

from pa_agent.data.seed_store import clear_cases
from pa_agent.fixtures import apply_fixture_mocks, list_fixtures, load_fixture
from pa_agent.gate import evaluate_confidence_gate
from pa_agent.graph import get_compiled_graph, run_case
from pa_agent.state import CriterionResult
from pa_agent.tools.critique import clear_mock_critic
from pa_agent.tools.extract import clear_extract_cache
from pa_agent.tools.save_case import get_saved_case, to_pa_case_row


def setup_function():
    clear_cases()
    clear_extract_cache()
    clear_mock_critic()
    get_compiled_graph.cache_clear()


def test_gate_all_met_auto_completed():
    criteria = [{"id": "c1", "text": "RA", "weight": 1.0}]
    extractions: list[CriterionResult] = [
        {
            "criterion_id": "c1",
            "criterion_text": "RA",
            "value": "yes",
            "quote": "documented RA",
            "quote_verified": True,
            "confidence": 0.9,
            "met": False,
            "critic_note": "confirm: ok",
        }
    ]
    out = evaluate_confidence_gate(
        policy_criteria=criteria, extractions=extractions
    )
    assert out["status"] == "auto_completed"
    assert out["missing_fields"] == []
    assert out["extractions"][0]["met"] is True


def test_gate_escalates_fields_not_cases():
    criteria = [
        {"id": "c3", "text": "Negative TB screening", "weight": 1.0},
        {"id": "c4", "text": "Rheumatologist", "weight": 0.8},
    ]
    extractions: list[CriterionResult] = [
        {
            "criterion_id": "c3",
            "criterion_text": "Negative TB screening",
            "value": "neg",
            "quote": "fake",
            "quote_verified": False,
            "confidence": 0.0,
            "met": False,
            "critic_note": "reject: span",
        }
    ]
    out = evaluate_confidence_gate(
        policy_criteria=criteria, extractions=extractions
    )
    assert out["status"] == "needs_review"
    assert out["missing_fields"] == ["c3", "c4"]
    assert out["human_review_notes"].startswith("Escalate fields:")
    assert "c3" in out["human_review_notes"]
    assert "c4" in out["human_review_notes"]


def test_upsert_roundtrip_fixture_b():
    fx = load_fixture("fixture_b_auto_completed")
    apply_fixture_mocks(fx)
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    case_id = result["case_id"]
    saved = get_saved_case(case_id)
    assert saved is not None
    assert saved["case_id"] == case_id
    assert saved["status"] == "auto_completed"
    assert saved["draft_pa_form"]["export_markdown"]
    assert "verified quotes only" in saved["draft_pa_form"]["export_markdown"].lower() or (
        "Criteria checklist" in saved["draft_pa_form"]["export_markdown"]
    )
    assert saved.get("created_at")
    assert saved.get("updated_at")
    # Upsert again updates timestamp contract
    row = to_pa_case_row({**saved, "human_review_notes": "recheck"})
    assert row["status"] == "auto_completed"


def test_finalize_export_includes_likelihood_and_alternative_on_c():
    fx = load_fixture("fixture_c_needs_review")
    apply_fixture_mocks(fx)
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    export = result["draft_pa_form"]["export_markdown"]
    assert "Approval likelihood:" in export
    assert "etanercept" in export.lower()
    assert "Escalate fields:" in (result.get("human_review_notes") or "")
    assert "Human review" in export
    saved = get_saved_case(result["case_id"])
    assert saved is not None
    assert saved["missing_fields"] == ["c3", "c4"]
    assert saved["alternative_suggestion"]
    assert saved["approval_likelihood"] is not None


def test_golden_fixtures_expected_status_and_persisted():
    """Run all three goldens; assert expected.status and DB row exists."""
    for path in list_fixtures():
        fx = load_fixture(path.name)
        apply_fixture_mocks(fx)
        inp = fx["input"]
        expected = fx["expected"]
        result = run_case(
            drug_name=inp["drug_name"],
            diagnosis_code=inp["diagnosis_code"],
            payer_name=inp["payer_name"],
            clinical_note=inp["clinical_note"],
        )
        assert result["status"] == expected["status"], path.name
        saved = get_saved_case(result["case_id"])
        assert saved is not None
        assert saved["status"] == expected["status"]
        assert saved["draft_pa_form"]["export_markdown"]
        clear_cases()
        clear_extract_cache()
        clear_mock_critic()

"""Block 4: batched critic — confirm|downgrade|reject; never raise failed quotes."""

from __future__ import annotations

from pa_agent.data.seed_store import clear_cases
from pa_agent.fixtures import apply_fixture_mocks, load_fixture
from pa_agent.graph import get_compiled_graph, run_case
from pa_agent.state import CriterionResult
from pa_agent.tools.critique import (
    apply_critic_decisions,
    clear_mock_critic,
    configure_mock_critic,
)
from pa_agent.tools.extract import clear_extract_cache


def setup_function():
    clear_cases()
    clear_extract_cache()
    clear_mock_critic()
    get_compiled_graph.cache_clear()


def test_apply_critic_cannot_raise_failed_quote_verify():
    extractions: list[CriterionResult] = [
        {
            "criterion_id": "c3",
            "criterion_text": "TB",
            "value": "negative",
            "quote": "hallucinated",
            "quote_verified": False,
            "confidence": 0.0,
            "met": False,
            "critic_note": "",
        }
    ]
    # Malicious/overconfident critic tries to confirm at 0.99
    decisions = [
        {
            "criterion_id": "c3",
            "action": "confirm",
            "confidence": 0.99,
            "reason": "Looks fine",
        }
    ]
    out = apply_critic_decisions(extractions, decisions)
    assert out[0]["confidence"] == 0.0
    assert out[0]["met"] is False
    assert out[0]["quote_verified"] is False
    assert "confirm" in out[0]["critic_note"]


def test_apply_critic_may_downgrade_below_threshold():
    extractions: list[CriterionResult] = [
        {
            "criterion_id": "c1",
            "criterion_text": "RA",
            "value": "RA",
            "quote": "documented RA",
            "quote_verified": True,
            "confidence": 0.92,
            "met": True,
            "critic_note": "",
        }
    ]
    decisions = [
        {
            "criterion_id": "c1",
            "action": "downgrade",
            "confidence": 0.55,
            "reason": "Quote is weak / indirect",
        }
    ]
    out = apply_critic_decisions(extractions, decisions)
    assert out[0]["confidence"] == 0.55
    assert out[0]["met"] is False
    assert out[0]["critic_note"].startswith("downgrade:")


def test_apply_critic_confirm_cannot_raise_confidence():
    extractions: list[CriterionResult] = [
        {
            "criterion_id": "c1",
            "criterion_text": "RA",
            "value": "RA",
            "quote": "documented RA",
            "quote_verified": True,
            "confidence": 0.80,
            "met": True,
            "critic_note": "",
        }
    ]
    decisions = [
        {
            "criterion_id": "c1",
            "action": "confirm",
            "confidence": 0.99,
            "reason": "Very sure",
        }
    ]
    out = apply_critic_decisions(extractions, decisions)
    assert out[0]["confidence"] == 0.80


def test_fixture_b_critic_notes_present_still_auto_completed():
    fx = load_fixture("fixture_b_auto_completed")
    apply_fixture_mocks(fx)
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    assert result["status"] == "auto_completed"
    for ext in result["extractions"]:
        assert ext["critic_note"]
        assert ext["critic_note"].startswith("confirm:")
        assert ext["met"] is True


def test_fixture_c_critic_rejects_failed_quote_and_missing():
    fx = load_fixture("fixture_c_needs_review")
    apply_fixture_mocks(fx)
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    assert result["status"] == "needs_review"
    by_id = {e["criterion_id"]: e for e in result["extractions"]}

    assert by_id["c1"]["critic_note"].startswith("confirm:")
    assert by_id["c2"]["critic_note"].startswith("confirm:")
    assert by_id["c3"]["critic_note"].startswith("reject:")
    assert by_id["c3"]["confidence"] == 0.0
    assert by_id["c3"]["met"] is False
    assert by_id["c4"]["critic_note"].startswith("reject:")
    assert set(result["missing_fields"]) == {"c3", "c4"}


def test_configured_mock_critic_downgrade_flips_fixture_b_to_review():
    """If critic downgrades one field below 0.70, gate escalates that field."""
    fx = load_fixture("fixture_b_auto_completed")
    apply_fixture_mocks(fx)
    configure_mock_critic(
        {
            "c2": {
                "criterion_id": "c2",
                "action": "downgrade",
                "confidence": 0.40,
                "reason": "Methotrexate duration ambiguous",
            }
        }
    )
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    assert result["status"] == "needs_review"
    assert "c2" in result["missing_fields"]
    by_id = {e["criterion_id"]: e for e in result["extractions"]}
    assert by_id["c2"]["confidence"] == 0.40
    assert by_id["c2"]["critic_note"].startswith("downgrade:")

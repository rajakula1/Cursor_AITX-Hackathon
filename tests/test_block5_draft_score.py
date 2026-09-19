"""Block 5: PA draft, likelihood score, formulary alternative."""

from __future__ import annotations

from pa_agent.criteria import compute_approval_likelihood, is_criterion_met
from pa_agent.data.seed_store import UHC_ADA_RA_CRITERIA, clear_cases
from pa_agent.fixtures import apply_fixture_mocks, load_fixture
from pa_agent.graph import get_compiled_graph, run_case
from pa_agent.tools.critique import clear_mock_critic
from pa_agent.tools.extract import clear_extract_cache


def setup_function():
    clear_cases()
    clear_extract_cache()
    clear_mock_critic()
    get_compiled_graph.cache_clear()


def test_likelihood_formula_blend():
    criteria = UHC_ADA_RA_CRITERIA
    extractions = [
        {
            "criterion_id": "c1",
            "value": "RA",
            "quote_verified": True,
            "confidence": 1.0,
        },
        {
            "criterion_id": "c2",
            "value": "MTX",
            "quote_verified": True,
            "confidence": 1.0,
        },
        {
            "criterion_id": "c3",
            "value": None,
            "quote_verified": False,
            "confidence": 0.0,
        },
        {
            "criterion_id": "c4",
            "value": None,
            "quote_verified": False,
            "confidence": 0.0,
        },
    ]
    # weights 1+1.2+1+0.8=4; met contrib 1+1.2=2.2 → ratio 0.55
    # blend: 0.70*0.55 + 0.30*0.40 = 0.385 + 0.12 = 0.505
    score = compute_approval_likelihood(
        policy_criteria=criteria,
        extractions=extractions,
        historical_approval_rate=0.40,
    )
    assert score == 0.505

    no_blend = compute_approval_likelihood(
        policy_criteria=criteria,
        extractions=extractions,
        historical_approval_rate=0.40,
        blend_historical=False,
    )
    assert no_blend == 0.55


def test_likelihood_shares_met_definition():
    assert not is_criterion_met(
        value="x", quote_verified=False, confidence=0.99
    )
    score = compute_approval_likelihood(
        policy_criteria=[{"id": "c1", "weight": 1.0}],
        extractions=[
            {
                "criterion_id": "c1",
                "value": "x",
                "quote_verified": False,
                "confidence": 0.99,
            }
        ],
        historical_approval_rate=None,
        blend_historical=False,
    )
    assert score == 0.0


def test_fixture_b_draft_and_likelihood():
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
    assert result["approval_likelihood"] is not None
    assert result["approval_likelihood"] >= 0.75
    assert result["alternative_suggestion"] is None

    draft = result["draft_pa_form"]
    assert draft is not None
    assert draft["export_markdown"]
    assert "Demo data" in draft["export_markdown"]
    assert draft["clinical_justification"]
    # Narrative grounded in verified quotes from the note
    for ext in result["extractions"]:
        if ext["quote_verified"]:
            assert ext["quote"] in draft["clinical_justification"]
    assert len(draft["criteria_checklist"]) == 4
    assert all(row["met"] for row in draft["criteria_checklist"])
    assert all(row.get("quote") for row in draft["criteria_checklist"])


def test_fixture_c_likelihood_alternative_and_partial_draft():
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
    assert set(result["missing_fields"]) == {"c3", "c4"}

    likelihood = result["approval_likelihood"]
    assert likelihood is not None
    assert 0.30 <= likelihood <= 0.50
    assert likelihood < 0.55
    assert result["alternative_suggestion"]
    assert "etanercept" in result["alternative_suggestion"]

    draft = result["draft_pa_form"]
    assert draft is not None
    assert draft["export_markdown"]
    # Only verified quotes in justification
    by_id = {e["criterion_id"]: e for e in result["extractions"]}
    assert by_id["c1"]["quote"] in draft["clinical_justification"]
    assert by_id["c2"]["quote"] in draft["clinical_justification"]
    # Hallucinated quote must not appear
    assert by_id["c3"]["quote"] not in draft["clinical_justification"]


def test_high_likelihood_skips_alternative_node():
    fx = load_fixture("fixture_b_auto_completed")
    apply_fixture_mocks(fx)
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    assert result["approval_likelihood"] >= 0.55
    assert result["alternative_suggestion"] is None

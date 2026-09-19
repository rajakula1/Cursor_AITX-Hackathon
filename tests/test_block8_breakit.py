"""Block 8 break-it: empty note, unknown drug, hallucinated quote — never crash."""

from __future__ import annotations

import pytest

from pa_agent.data.seed_store import clear_cases
from pa_agent.fixtures import apply_fixture_mocks, load_fixture
from pa_agent.graph import get_compiled_graph, run_case
from pa_agent.tools.critique import clear_mock_critic
from pa_agent.tools.extract import clear_extract_cache

PUBLIC = {"no_pa_required", "auto_completed", "needs_review"}


def setup_function():
    clear_cases()
    clear_extract_cache()
    clear_mock_critic()
    get_compiled_graph.cache_clear()


def _assert_safe(result: dict) -> None:
    assert result is not None
    assert result.get("status") in PUBLIC
    assert "error" not in (result.get("status") or "")
    assert result.get("case_id")
    draft = result.get("draft_pa_form")
    assert draft is not None
    assert isinstance(draft.get("export_markdown"), str)


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "drug_name": "Ozempic",
            "diagnosis_code": "E11.9",
            "payer_name": "Aetna",
            "clinical_note": "",
        },
        {
            "drug_name": "Ozempic",
            "diagnosis_code": "E11.9",
            "payer_name": "Aetna",
            "clinical_note": "   \n\t  ",
        },
        {
            "drug_name": "",
            "diagnosis_code": "E11.9",
            "payer_name": "Aetna",
            "clinical_note": "Demo data — not real PHI. Short note.",
        },
        {
            "drug_name": "Ozempic",
            "diagnosis_code": "",
            "payer_name": "Aetna",
            "clinical_note": "Demo data — not real PHI. Short note.",
        },
        {
            "drug_name": "Ozempic",
            "diagnosis_code": "E11.9",
            "payer_name": "",
            "clinical_note": "Demo data — not real PHI. Short note.",
        },
    ],
)
def test_empty_or_blank_inputs_needs_review_no_crash(kwargs):
    result = run_case(**kwargs)
    _assert_safe(result)
    assert result["status"] == "needs_review"


def test_unknown_drug_needs_review_no_crash():
    result = run_case(
        drug_name="NotARealDrugXYZ",
        diagnosis_code="M06.9",
        payer_name="UHC",
        clinical_note="Demo data — not real PHI. Patient follow-up only.",
    )
    _assert_safe(result)
    assert result["status"] == "needs_review"
    assert result["policy_lookup"] == "not_found"
    assert result["status"] != "no_pa_required"


def test_unknown_payer_needs_review_no_crash():
    result = run_case(
        drug_name="Humira",
        diagnosis_code="M06.9",
        payer_name="FakeInsuranceCo",
        clinical_note="Demo data — not real PHI. Patient follow-up only.",
    )
    _assert_safe(result)
    assert result["status"] == "needs_review"
    assert result["policy_lookup"] == "not_found"


def test_unknown_diagnosis_policy_not_found_never_no_pa():
    result = run_case(
        drug_name="adalimumab",
        diagnosis_code="Z99.99",
        payer_name="UnitedHealthcare",
        clinical_note="Demo data — not real PHI. Chart note without matching policy DX.",
    )
    _assert_safe(result)
    assert result["status"] == "needs_review"
    assert result["policy_lookup"] == "not_found"
    assert result["pa_required"] is None


def test_fixture_c_hallucinated_quote_zeroed_no_crash():
    """Fixture 3 / C: model invents a quote → span check zeros confidence."""
    fx = load_fixture("fixture_c_needs_review")
    apply_fixture_mocks(fx)
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    _assert_safe(result)
    assert result["status"] == "needs_review"
    assert len(result["missing_fields"]) == 2
    by_id = {e["criterion_id"]: e for e in result["extractions"]}
    c3 = by_id["c3"]
    assert c3["quote_verified"] is False
    assert c3["confidence"] == 0.0
    assert c3["quote"] not in inp["clinical_note"]
    assert result["alternative_suggestion"]
    assert 0.30 <= result["approval_likelihood"] <= 0.50


def test_public_status_never_error_even_on_garbage():
    result = run_case(
        drug_name="???",
        diagnosis_code="!!!",
        payer_name="###",
        clinical_note="x",
    )
    _assert_safe(result)
    assert result["status"] == "needs_review"


def test_all_breakit_cases_do_not_raise():
    """Smoke: every break-it input returns without exception."""
    cases = [
        ("", "E11.9", "Aetna", ""),
        ("NotARealDrugXYZ", "M06.9", "UHC", "note"),
        ("Humira", "M06.9", "NoSuchPayer", "note"),
        ("adalimumab", "Z99.99", "UnitedHealthcare", "Demo data — not real PHI."),
    ]
    for drug, dx, payer, note in cases:
        clear_cases()
        result = run_case(
            drug_name=drug,
            diagnosis_code=dx,
            payer_name=payer,
            clinical_note=note,
        )
        _assert_safe(result)

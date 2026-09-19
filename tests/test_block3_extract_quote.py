"""Block 3: Haiku fan-out (mocked), quote span verify, extraction cache."""

from __future__ import annotations

import asyncio

from pa_agent.criteria import is_criterion_met, normalize_text, quote_in_note
from pa_agent.data.seed_store import clear_cases
from pa_agent.fixtures import apply_fixture_mocks, load_fixture
from pa_agent.graph import get_compiled_graph, run_case
from pa_agent.tools.extract import (
    cache_size,
    clear_extract_cache,
    extract_all,
    extract_field,
    note_hash,
)


def setup_function():
    clear_cases()
    clear_extract_cache()
    get_compiled_graph.cache_clear()


def test_normalize_and_quote_span():
    note = "Negative TB screening within past 12 months is on file."
    assert quote_in_note(
        "negative TB screening within past 12 months is on file.", note
    )
    assert not quote_in_note(
        "QuantiFERON-TB Gold assay performed last month was negative.", note
    )
    assert normalize_text("  A  B\nC ") == "a b c"


def test_is_criterion_met_rules():
    assert is_criterion_met(value="x", quote_verified=True, confidence=0.70)
    assert not is_criterion_met(value="x", quote_verified=True, confidence=0.69)
    assert not is_criterion_met(value="x", quote_verified=False, confidence=0.99)
    assert not is_criterion_met(value="", quote_verified=True, confidence=0.99)
    assert not is_criterion_met(value=None, quote_verified=True, confidence=0.99)


def test_extract_cache_keyed_by_note_hash_and_criterion():
    fx = load_fixture("fixture_b_auto_completed")
    apply_fixture_mocks(fx)
    note = fx["input"]["clinical_note"]
    c1 = {"id": "c1", "text": "Documented diagnosis of rheumatoid arthritis"}

    assert cache_size() == 0
    first = asyncio.run(extract_field(c1, note))
    assert cache_size() == 1
    second = asyncio.run(extract_field(c1, note))
    assert first == second
    assert cache_size() == 1
    # Different criterion → new cache entry
    c2 = {"id": "c2", "text": "methotrexate"}
    asyncio.run(extract_field(c2, note))
    assert cache_size() == 2
    assert note_hash(note) == note_hash(note)


def test_extract_all_fan_out_parallel_mock():
    fx = load_fixture("fixture_b_auto_completed")
    apply_fixture_mocks(fx)
    note = fx["input"]["clinical_note"]
    criteria = [
        {"id": "c1", "text": "RA"},
        {"id": "c2", "text": "MTX"},
        {"id": "c3", "text": "TB"},
        {"id": "c4", "text": "Rheum"},
    ]
    pairs = asyncio.run(extract_all(criteria, note))
    assert len(pairs) == 4
    assert all(out["quote"] for _, out in pairs)


def test_fixture_b_all_quotes_verified_auto_completed():
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
    assert result["missing_fields"] == []
    assert len(result["extractions"]) == 4
    for ext in result["extractions"]:
        assert ext["quote_verified"] is True
        assert ext["met"] is True
        assert ext["confidence"] >= 0.70
        assert quote_in_note(ext["quote"], inp["clinical_note"])


def test_fixture_c_hallucinated_quote_zeroed_two_missing():
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

    by_id = {e["criterion_id"]: e for e in result["extractions"]}
    assert by_id["c1"]["met"] is True and by_id["c1"]["quote_verified"] is True
    assert by_id["c2"]["met"] is True and by_id["c2"]["quote_verified"] is True

    # Hallucinated quote: kept value path but span check zeros confidence
    c3 = by_id["c3"]
    assert c3["quote"]
    assert quote_in_note(c3["quote"], inp["clinical_note"]) is False
    assert c3["quote_verified"] is False
    assert c3["confidence"] == 0.0
    assert c3["value"]  # value kept
    assert c3["met"] is False

    c4 = by_id["c4"]
    assert c4["value"] is None
    assert c4["met"] is False


def test_fixture_a_still_skips_extraction():
    fx = load_fixture("fixture_a_no_pa")
    inp = fx["input"]
    result = run_case(
        drug_name=inp["drug_name"],
        diagnosis_code=inp["diagnosis_code"],
        payer_name=inp["payer_name"],
        clinical_note=inp["clinical_note"],
    )
    assert result["status"] == "no_pa_required"
    assert result["extractions"] == []

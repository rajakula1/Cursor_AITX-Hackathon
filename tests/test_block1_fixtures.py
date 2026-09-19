"""Block 1 smoke tests: seeds, policy tool, fixtures, mock extract + quote span."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from pa_agent.data.seed_store import UHC_ADA_RA_CRITERIA, resolve_drug, resolve_payer
from pa_agent.fixtures import apply_fixture_mocks, list_fixtures, load_fixture
from pa_agent.tools.extract import extract_field
from pa_agent.tools.formulary import get_formulary_alternative
from pa_agent.tools.policy import get_payer_policy


def _normalize(s: str) -> str:
    return " ".join(s.lower().split())


def test_three_golden_fixtures_present():
    names = {p.name for p in list_fixtures()}
    assert "fixture_a_no_pa.json" in names
    assert "fixture_b_auto_completed.json" in names
    assert "fixture_c_needs_review.json" in names


def test_fixture_a_policy_no_pa():
    fx = load_fixture("fixture_a_no_pa")
    inp = fx["input"]
    result = get_payer_policy(inp["drug_name"], inp["diagnosis_code"], inp["payer_name"])
    assert result["lookup"] == "found"
    assert result["requires_pa"] is False
    assert result["canonical_drug"] == "semaglutide"
    assert result["canonical_payer"] == "Aetna"


def test_fixture_b_policy_and_verbatim_quotes():
    fx = load_fixture("fixture_b_auto_completed")
    inp = fx["input"]
    note = inp["clinical_note"]
    result = get_payer_policy(inp["drug_name"], inp["diagnosis_code"], inp["payer_name"])
    assert result["lookup"] == "found"
    assert result["requires_pa"] is True
    assert len(result["criteria"]) == 4

    apply_fixture_mocks(fx)

    async def _run():
        outs = []
        for c in UHC_ADA_RA_CRITERIA:
            outs.append(await extract_field(c, note))
        return outs

    outs = asyncio.run(_run())
    for out in outs:
        assert out["quote"]
        assert _normalize(out["quote"]) in _normalize(note)
        assert out["confidence"] >= 0.70


def test_fixture_c_hallucinated_quote_not_in_note():
    fx = load_fixture("fixture_c_needs_review")
    inp = fx["input"]
    note = inp["clinical_note"]
    apply_fixture_mocks(fx)

    c3 = next(c for c in UHC_ADA_RA_CRITERIA if c["id"] == "c3")
    out = asyncio.run(extract_field(c3, note))
    assert out["quote"]
    assert _normalize(out["quote"]) not in _normalize(note)

    c4 = next(c for c in UHC_ADA_RA_CRITERIA if c["id"] == "c4")
    missing = asyncio.run(extract_field(c4, note))
    assert missing["value"] is None
    assert missing["quote"] is None


def test_alias_normalization():
    assert resolve_payer("UHC") == "UnitedHealthcare"
    assert resolve_drug("Humira")["canonical_drug"] == "adalimumab"


def test_formulary_alternative_prefers_no_pa():
    alt = get_formulary_alternative("TNF inhibitor", "UnitedHealthcare")
    assert alt is not None
    assert alt["alternative_drug"] == "etanercept"
    assert alt["requires_pa"] is False


def test_unknown_policy_is_not_found_not_no_pa():
    result = get_payer_policy("adalimumab", "Z99.99", "UnitedHealthcare")
    assert result["lookup"] == "not_found"
    assert result["requires_pa"] is None

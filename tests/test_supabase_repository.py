"""Unit tests for Supabase repository (mocked client; no live network)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from pa_agent.data import repository
from pa_agent.data.supabase_client import clear_client_cache, health_check, is_configured
from pa_agent.tools.policy import get_payer_policy
from pa_agent.tools.save_case import get_saved_case, save_case


def setup_function():
    clear_client_cache()
    repository.clear_reference_cache()
    from pa_agent.data.seed_store import clear_cases

    clear_cases()


def test_is_configured_false_under_pytest():
    assert is_configured() is False


def test_policy_falls_back_to_memory():
    result = get_payer_policy("Humira", "M06.9", "UHC")
    assert result["lookup"] == "found"
    assert result["canonical_payer"] == "UnitedHealthcare"
    assert result["canonical_drug"] == "adalimumab"
    assert result["requires_pa"] is True
    assert len(result["criteria"]) == 4


def test_warm_cache_loads_from_supabase_when_configured():
    mock_client = MagicMock()

    def _table(name: str):
        t = MagicMock()
        if name == "payer_aliases":
            t.select.return_value.execute.return_value = MagicMock(
                data=[{"alias": "uhc", "canonical_payer": "UnitedHealthcare"}]
            )
        elif name == "drug_aliases":
            t.select.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "alias": "humira",
                        "canonical_drug": "adalimumab",
                        "drug_class": "TNF inhibitor",
                    }
                ]
            )
        elif name == "payer_policies":
            t.select.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "payer_name": "UnitedHealthcare",
                        "drug_name": "adalimumab",
                        "drug_class": "TNF inhibitor",
                        "diagnosis_code": "M06.9",
                        "requires_pa": True,
                        "criteria": [{"id": "c1", "text": "RA", "weight": 1.0}],
                        "historical_approval_rate": "0.40",
                    }
                ]
            )
        else:
            t.select.return_value.execute.return_value = MagicMock(data=[])
        return t

    mock_client.table.side_effect = _table
    with (
        patch("pa_agent.data.repository.is_configured", return_value=True),
        patch("pa_agent.data.repository.get_client", return_value=mock_client),
    ):
        source = repository.warm_reference_cache(force=True)
        assert source == "supabase"
        assert repository.resolve_payer("uhc") == "UnitedHealthcare"
        row = repository.find_policy("adalimumab", "M06.9", "UnitedHealthcare")
    assert row is not None
    assert row["historical_approval_rate"] == 0.4


def test_save_case_upserts_supabase_when_configured():
    upserted: list[dict] = []

    def _upsert(row):
        upserted.append(row)

    with (
        patch("pa_agent.tools.save_case.is_configured", return_value=True),
        patch("pa_agent.tools.save_case.upsert_pa_case", side_effect=_upsert),
    ):
        saved = save_case(
            {
                "case_id": "11111111-1111-1111-1111-111111111111",
                "drug_name": "adalimumab",
                "status": "needs_review",
                "error_log": [],
            }
        )
    assert saved["case_id"] == "11111111-1111-1111-1111-111111111111"
    assert len(upserted) == 1
    assert upserted[0]["case_id"] == saved["case_id"]
    assert get_saved_case(saved["case_id"]) is not None


def test_save_case_remote_false_skips_supabase():
    with (
        patch("pa_agent.tools.save_case.is_configured", return_value=True),
        patch("pa_agent.tools.save_case.upsert_pa_case") as upsert,
    ):
        save_case(
            {
                "case_id": "33333333-3333-3333-3333-333333333333",
                "status": "needs_review",
                "error_log": [],
            },
            remote=False,
        )
    upsert.assert_not_called()


def test_save_case_soft_fails_supabase_error():
    with (
        patch("pa_agent.tools.save_case.is_configured", return_value=True),
        patch(
            "pa_agent.tools.save_case.upsert_pa_case",
            side_effect=RuntimeError("boom"),
        ),
    ):
        saved = save_case(
            {
                "case_id": "22222222-2222-2222-2222-222222222222",
                "status": "auto_completed",
                "error_log": [],
            }
        )
    assert saved["status"] == "auto_completed"
    assert any("supabase_upsert" in e for e in (saved.get("error_log") or []))


def test_health_check_not_configured():
    h = health_check()
    assert h["configured"] is False
    assert h["ok"] is False

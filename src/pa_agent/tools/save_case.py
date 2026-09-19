"""save_case — upsert pa_cases (in-memory; Supabase when configured)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pa_agent.config import get_settings
from pa_agent.data.seed_store import get_case as _get_mem
from pa_agent.data.seed_store import save_case as _save_mem

# Columns aligned with sql/schema.sql pa_cases
_PA_CASE_KEYS = (
    "case_id",
    "drug_name",
    "diagnosis_code",
    "payer_name",
    "drug_class",
    "clinical_note",
    "policy_lookup",
    "pa_required",
    "policy_criteria",
    "extractions",
    "draft_pa_form",
    "missing_fields",
    "approval_likelihood",
    "alternative_suggestion",
    "status",
    "human_review_notes",
    "error_log",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_pa_case_row(state: dict[str, Any]) -> dict[str, Any]:
    """Project graph state onto the pa_cases contract."""
    row = {k: state.get(k) for k in _PA_CASE_KEYS}
    row["case_id"] = state.get("case_id")
    row["updated_at"] = _now_iso()
    existing = _get_mem(str(row["case_id"])) if row.get("case_id") else None
    row["created_at"] = (existing or {}).get("created_at") or _now_iso()
    # Public status never error
    if row.get("status") not in ("no_pa_required", "auto_completed", "needs_review"):
        row["status"] = "needs_review"
    return row


def save_case(state: dict[str, Any]) -> dict[str, Any]:
    case_id = state.get("case_id")
    if not case_id:
        raise ValueError("save_case requires case_id")

    row = to_pa_case_row(state)
    # Always keep in-memory copy for tests / demo without Supabase
    saved = _save_mem(str(case_id), row)

    if _supabase_configured():
        try:
            _upsert_supabase(row)
        except Exception as exc:  # noqa: BLE001 — persistence soft-fail
            from pa_agent.errors import sanitize_exc

            log = list(saved.get("error_log") or [])
            log.append(f"supabase_upsert: {sanitize_exc(exc)}")
            saved = _save_mem(str(case_id), {**saved, "error_log": log})

    return saved


def get_saved_case(case_id: str) -> dict[str, Any] | None:
    return _get_mem(case_id)


def _supabase_configured() -> bool:
    settings = get_settings()
    url = (settings.supabase_url or "").strip()
    key = (settings.supabase_key or "").strip()
    if not url or not key:
        return False
    if "your-project" in url or key.startswith("your-"):
        return False
    return True


def _upsert_supabase(row: dict[str, Any]) -> None:
    from supabase import create_client

    settings = get_settings()
    assert settings.supabase_url and settings.supabase_key
    client = create_client(settings.supabase_url, settings.supabase_key)
    payload = {k: v for k, v in row.items() if k in _PA_CASE_KEYS or k in ("created_at", "updated_at")}
    client.table("pa_cases").upsert(payload, on_conflict="case_id").execute()

"""save_case — upsert pa_cases (in-memory for Block 1)."""

from __future__ import annotations

from typing import Any

from pa_agent.data.seed_store import save_case as _save


def save_case(state: dict[str, Any]) -> dict[str, Any]:
    case_id = state.get("case_id")
    if not case_id:
        raise ValueError("save_case requires case_id")
    return _save(str(case_id), dict(state))

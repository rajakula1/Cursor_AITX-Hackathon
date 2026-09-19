"""Node helpers shared across the graph."""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Coroutine, TypeVar

from pa_agent.errors import sanitize_exc
from pa_agent.state import PAState, PublicStatus

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine from sync LangGraph nodes.

    Always uses a fresh thread + event loop so sequential OpenRouter
    nodes (extract → critic → draft) do not hit 'Event loop is closed'.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def append_error(state: PAState, where: str, exc: BaseException) -> dict[str, Any]:
    log = list(state.get("error_log") or [])
    log.append(f"{where}: {sanitize_exc(exc)}")
    return {
        "error_log": log,
        "status": "needs_review",
        "human_review_notes": state.get("human_review_notes")
        or f"Error in {where}; routed to human review.",
    }


def empty_state_defaults() -> dict[str, Any]:
    return {
        "case_id": "",
        "drug_name": "",
        "diagnosis_code": "",
        "payer_name": "",
        "clinical_note": "",
        "drug_class": None,
        "policy_lookup": None,
        "pa_required": None,
        "policy_criteria": [],
        "extractions": [],
        "draft_pa_form": None,
        "missing_fields": [],
        "approval_likelihood": None,
        "alternative_suggestion": None,
        "status": "needs_review",
        "human_review_notes": None,
        "error_log": [],
        "historical_approval_rate": None,
    }


def make_initial_state(
    *,
    drug_name: str,
    diagnosis_code: str,
    payer_name: str,
    clinical_note: str,
    status: PublicStatus = "needs_review",
) -> PAState:
    base = empty_state_defaults()
    base.update(
        {
            "drug_name": drug_name,
            "diagnosis_code": diagnosis_code,
            "payer_name": payer_name,
            "clinical_note": clinical_note,
            "status": status,
        }
    )
    return base  # type: ignore[return-value]

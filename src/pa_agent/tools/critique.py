"""critique_all — one batched Sonnet call over fields that still need judgment."""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any, Literal, Optional, TypedDict

from pydantic import BaseModel, Field

from pa_agent.config import get_settings
from pa_agent.criteria import is_criterion_met
from pa_agent.state import CriterionResult

_log = logging.getLogger("pa_agent.critique")

CriticAction = Literal["confirm", "downgrade", "reject"]


class CriticDecision(TypedDict):
    criterion_id: str
    action: CriticAction
    confidence: float  # proposed post-critic confidence (0–1)
    reason: str


class _Item(BaseModel):
    criterion_id: str
    action: Literal["confirm", "downgrade", "reject"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class _Batch(BaseModel):
    decisions: list[_Item]


_MOCK_DECISIONS: dict[str, CriticDecision] = {}

_CRITIC_SYSTEM = (
    "Prior-auth extraction critic. For each field choose confirm|downgrade|reject, "
    "confidence 0-1, short reason. May lower confidence only; never invent evidence. "
    "Never raise confidence above the extractor. Quote span already verified in code — "
    "judge whether value is supported by the quote."
)


def configure_mock_critic(mapping: dict[str, CriticDecision]) -> None:
    _MOCK_DECISIONS.clear()
    _MOCK_DECISIONS.update(mapping)


def clear_mock_critic() -> None:
    _MOCK_DECISIONS.clear()


@lru_cache(maxsize=1)
def _critic_chain():
    from pa_agent.llm import get_critic_llm, structured

    return structured(get_critic_llm(), _Batch)


def _default_mock_decisions(
    extractions: list[CriterionResult],
) -> list[CriticDecision]:
    decisions: list[CriticDecision] = []
    for ext in extractions:
        cid = str(ext["criterion_id"])
        if cid in _MOCK_DECISIONS:
            decisions.append(dict(_MOCK_DECISIONS[cid]))  # type: ignore[arg-type]
            continue

        if not ext.get("quote_verified"):
            reason = (
                "Reject: quote failed deterministic span check."
                if ext.get("quote")
                else "Reject: no supporting quote extracted."
            )
            decisions.append(
                {
                    "criterion_id": cid,
                    "action": "reject",
                    "confidence": 0.0,
                    "reason": reason,
                }
            )
        elif not (ext.get("value") and str(ext["value"]).strip()):
            decisions.append(
                {
                    "criterion_id": cid,
                    "action": "reject",
                    "confidence": 0.0,
                    "reason": "Reject: empty value.",
                }
            )
        else:
            decisions.append(
                {
                    "criterion_id": cid,
                    "action": "confirm",
                    "confidence": float(ext.get("confidence") or 0.0),
                    "reason": "Confirm: value supported by verified quote.",
                }
            )
    return decisions


def _deterministic_reject(ext: CriterionResult) -> CriticDecision | None:
    """Fields the model must reject — skip Sonnet for these."""
    cid = str(ext["criterion_id"])
    if not ext.get("quote_verified"):
        reason = (
            "Reject: quote failed deterministic span check (pre-critic)."
            if ext.get("quote")
            else "Reject: no supporting quote extracted (pre-critic)."
        )
        return {
            "criterion_id": cid,
            "action": "reject",
            "confidence": 0.0,
            "reason": reason,
        }
    if not (ext.get("value") and str(ext["value"]).strip()):
        return {
            "criterion_id": cid,
            "action": "reject",
            "confidence": 0.0,
            "reason": "Reject: empty value (pre-critic).",
        }
    return None


def fields_needing_llm_critique(
    extractions: list[CriterionResult],
) -> list[CriterionResult]:
    """Only quote-verified fields with a value need a Sonnet judgment."""
    return [e for e in extractions if _deterministic_reject(e) is None]


def apply_critic_decisions(
    extractions: list[CriterionResult],
    decisions: list[CriticDecision],
) -> list[CriterionResult]:
    """Apply critic output. Never raise confidence; never revive failed quote-verify."""
    by_id = {d["criterion_id"]: d for d in decisions}
    updated: list[CriterionResult] = []
    for raw in extractions:
        ext: CriterionResult = dict(raw)  # type: ignore[assignment]
        cid = str(ext["criterion_id"])
        decision = by_id.get(cid)
        current = float(ext.get("confidence") or 0.0)

        if decision is None:
            ext["critic_note"] = "No critic decision returned for this field."
            ext["met"] = is_criterion_met(
                value=ext.get("value"),
                quote_verified=bool(ext.get("quote_verified")),
                confidence=current,
            )
            updated.append(ext)
            continue

        action = decision["action"]
        proposed = float(decision.get("confidence") or 0.0)
        reason = decision.get("reason") or action
        ext["critic_note"] = f"{action}: {reason}"

        if not ext.get("quote_verified"):
            ext["confidence"] = 0.0
        elif action == "reject":
            ext["confidence"] = 0.0
        elif action == "downgrade":
            ext["confidence"] = min(current, proposed)
        else:  # confirm — may lower slightly if model proposes lower; never raise
            ext["confidence"] = min(current, proposed if proposed > 0 else current)

        ext["met"] = is_criterion_met(
            value=ext.get("value"),
            quote_verified=bool(ext.get("quote_verified")),
            confidence=float(ext["confidence"]),
        )
        updated.append(ext)
    return updated


async def critique_all(
    extractions: list[CriterionResult], note: str
) -> list[CriticDecision]:
    """One call over fields that still need judgment. Mock when USE_MOCK_EXTRACT=1."""
    settings = get_settings()
    if settings.use_mock_llm:
        return _default_mock_decisions(extractions)
    return await _live_critique(extractions, note)


async def _live_critique(
    extractions: list[CriterionResult], note: str
) -> list[CriticDecision]:
    """Skip Sonnet for deterministic rejects; shrink prompt (no full note)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    from pa_agent.errors import sanitize_exc

    decisions: list[CriticDecision] = []
    needs_llm: list[CriterionResult] = []
    for ext in extractions:
        det = _deterministic_reject(ext)
        if det is not None:
            decisions.append(det)
        else:
            needs_llm.append(ext)

    if not needs_llm:
        _log.info("critic skipped LLM — all %d fields deterministic reject", len(decisions))
        return decisions

    payload = [
        {
            "criterion_id": e["criterion_id"],
            "criterion_text": e.get("criterion_text"),
            "value": e.get("value"),
            "quote": e.get("quote"),
            "confidence": e.get("confidence"),
        }
        for e in needs_llm
    ]
    # Quote already span-checked — sending full note again is mostly wasted tokens.
    messages = [
        SystemMessage(content=_CRITIC_SYSTEM),
        HumanMessage(
            content=(
                f"Critique {len(payload)} field(s). Return one decision each.\n"
                f"Fields JSON:\n{payload}"
            )
        ),
    ]

    last_exc: Optional[Exception] = None
    chain = _critic_chain()
    for _ in range(2):
        try:
            out: _Batch = await chain.ainvoke(messages)
            for d in out.decisions:
                decisions.append(
                    {
                        "criterion_id": d.criterion_id,
                        "action": d.action,
                        "confidence": float(d.confidence),
                        "reason": d.reason,
                    }
                )
            return decisions
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await asyncio.sleep(0.2)

    _log.warning(
        "live critic failed: %s", sanitize_exc(last_exc) if last_exc else "unknown"
    )
    # Fail closed for fields that still needed LLM
    for e in needs_llm:
        decisions.append(
            {
                "criterion_id": str(e["criterion_id"]),
                "action": "reject",
                "confidence": 0.0,
                "reason": "Critic unavailable (timeout/schema); fail closed → review.",
            }
        )
    return decisions


def critique_all_sync(
    extractions: list[CriterionResult], note: str
) -> list[CriticDecision]:
    return asyncio.run(critique_all(extractions, note))

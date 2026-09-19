"""critique_all — one batched Sonnet call over all extractions (spec §2.5)."""

from __future__ import annotations

import asyncio
from typing import Any, Literal, Optional, TypedDict

from pa_agent.config import get_settings
from pa_agent.criteria import is_criterion_met
from pa_agent.state import CriterionResult

CriticAction = Literal["confirm", "downgrade", "reject"]


class CriticDecision(TypedDict):
    criterion_id: str
    action: CriticAction
    confidence: float  # proposed post-critic confidence (0–1)
    reason: str


# Optional per-criterion mock overrides for tests/fixtures
_MOCK_DECISIONS: dict[str, CriticDecision] = {}


def configure_mock_critic(mapping: dict[str, CriticDecision]) -> None:
    _MOCK_DECISIONS.clear()
    _MOCK_DECISIONS.update(mapping)


def clear_mock_critic() -> None:
    _MOCK_DECISIONS.clear()


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
            # Soft miss: do not raise confidence
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
            # Hard rule: failed span check stays at 0; critic cannot raise
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
    """One call over all fields. Mock when USE_MOCK_EXTRACT=1."""
    settings = get_settings()
    if settings.use_mock_llm:
        return _default_mock_decisions(extractions)
    return await _live_critique(extractions, note)


async def _live_critique(
    extractions: list[CriterionResult], note: str
) -> list[CriticDecision]:
    from pydantic import BaseModel, Field

    from pa_agent.llm import get_critic_llm, structured

    class _Item(BaseModel):
        criterion_id: str
        action: Literal["confirm", "downgrade", "reject"]
        confidence: float = Field(ge=0.0, le=1.0)
        reason: str

    class _Batch(BaseModel):
        decisions: list[_Item]

    payload = [
        {
            "criterion_id": e["criterion_id"],
            "criterion_text": e.get("criterion_text"),
            "value": e.get("value"),
            "quote": e.get("quote"),
            "quote_verified": e.get("quote_verified"),
            "confidence": e.get("confidence"),
        }
        for e in extractions
    ]
    prompt = (
        "You are a prior-auth extraction critic. For EACH criterion, choose "
        "confirm | downgrade | reject and set a confidence 0-1 with a short reason.\n"
        "Rules:\n"
        "- If quote_verified is false, you MUST reject with confidence 0.\n"
        "- You may lower confidence; never invent evidence not in the note.\n"
        "- Never raise confidence above the extractor's value.\n"
        "- Return one decision per criterion_id.\n\n"
        f"Extractions JSON:\n{payload}\n\n"
        f"Clinical note:\n{note}"
    )

    last_exc: Optional[Exception] = None
    llm = structured(get_critic_llm(), _Batch)
    for _ in range(2):
        try:
            # Sync invoke — avoids event-loop conflicts after extract's asyncio.run
            out: _Batch = llm.invoke(prompt)
            return [
                {
                    "criterion_id": d.criterion_id,
                    "action": d.action,
                    "confidence": float(d.confidence),
                    "reason": d.reason,
                }
                for d in out.decisions
            ]
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await asyncio.sleep(0.35)

    import logging

    from pa_agent.errors import sanitize_exc

    logging.getLogger("pa_agent.critique").warning(
        "live critic failed: %s", sanitize_exc(last_exc) if last_exc else "unknown"
    )
    # Fail closed: reject all fields so gate escalates to needs_review
    return [
        {
            "criterion_id": str(e["criterion_id"]),
            "action": "reject",
            "confidence": 0.0,
            "reason": "Critic unavailable (timeout/schema); fail closed → review.",
        }
        for e in extractions
    ]


def critique_all_sync(
    extractions: list[CriterionResult], note: str
) -> list[CriticDecision]:
    return asyncio.run(critique_all(extractions, note))

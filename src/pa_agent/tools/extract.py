"""extract_field — OpenRouter Haiku fan-out + cache by (note_hash, criterion_id)."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, TypedDict

from pa_agent.config import get_settings


class ExtractionOut(TypedDict):
    value: str | None
    confidence: float
    quote: str | None


_CACHE: dict[tuple[str, str], ExtractionOut] = {}
_MOCK_BY_CRITERION: dict[str, ExtractionOut] = {}


def note_hash(note: str) -> str:
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def clear_extract_cache() -> None:
    _CACHE.clear()


def cache_size() -> int:
    return len(_CACHE)


def configure_mock_extractions(mapping: dict[str, ExtractionOut]) -> None:
    """Test/fixture hook: set mock outputs per criterion_id."""
    _MOCK_BY_CRITERION.clear()
    _MOCK_BY_CRITERION.update(mapping)


def _mock_extract(criterion: dict[str, Any], note: str) -> ExtractionOut:
    cid = criterion["id"]
    if cid in _MOCK_BY_CRITERION:
        return dict(_MOCK_BY_CRITERION[cid])  # type: ignore[return-value]

    text = criterion.get("text", "")
    tokens = [t.lower() for t in text.replace(",", " ").split() if len(t) > 4]
    for sentence in note.replace("\n", " ").split("."):
        s = sentence.strip()
        if not s:
            continue
        lower = s.lower()
        if any(tok in lower for tok in tokens[:3]):
            if s in note:
                return {
                    "value": s[:120],
                    "confidence": 0.85,
                    "quote": s,
                }
    return {"value": None, "confidence": 0.0, "quote": None}


async def extract_field(criterion: dict[str, Any], note: str) -> ExtractionOut:
    """Extract one criterion. Cached. Mock when USE_MOCK_EXTRACT=1."""
    key = (note_hash(note), str(criterion["id"]))
    if key in _CACHE:
        return dict(_CACHE[key])  # type: ignore[return-value]

    settings = get_settings()
    if settings.use_mock_extract:
        result = _mock_extract(criterion, note)
    else:
        result = await _live_extract(criterion, note)

    _CACHE[key] = result
    return dict(result)  # type: ignore[return-value]


async def extract_all(
    criteria: list[dict[str, Any]], note: str
) -> list[tuple[dict[str, Any], ExtractionOut]]:
    """Parallel fan-out — one wall-clock round-trip for N criteria."""
    if not criteria:
        return []

    async def _one(c: dict[str, Any]) -> tuple[dict[str, Any], ExtractionOut]:
        try:
            out = await extract_field(c, note)
        except Exception:  # noqa: BLE001 — field-level soft fail → needs_review
            out = {"value": None, "confidence": 0.0, "quote": None}
        return c, out

    return list(await asyncio.gather(*[_one(c) for c in criteria]))


async def _live_extract(criterion: dict[str, Any], note: str) -> ExtractionOut:
    """OpenRouter Haiku structured extract; one retry then soft-fail."""
    from pydantic import BaseModel, Field

    from pa_agent.llm import get_extract_llm

    class _Out(BaseModel):
        value: str | None = Field(default=None)
        confidence: float = Field(default=0.0, ge=0.0, le=1.0)
        quote: str | None = Field(default=None)

    prompt = (
        "Extract evidence for the prior-auth criterion from the clinical note.\n"
        "Return value (short answer), confidence 0-1, and a verbatim quote "
        "copied exactly from the note. If unsupported, value/quote null and "
        "confidence 0.\n\n"
        f"Criterion: {criterion.get('text')}\n\n"
        f"Note:\n{note}"
    )

    last_exc: Exception | None = None
    for _attempt in range(2):  # initial + one retry (spec §7)
        try:
            llm = get_extract_llm().with_structured_output(_Out)
            out: _Out = await llm.ainvoke(prompt)
            return {
                "value": out.value,
                "confidence": float(out.confidence),
                "quote": out.quote,
            }
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await asyncio.sleep(0.25)

    _ = last_exc
    return {"value": None, "confidence": 0.0, "quote": None}


def extract_field_sync(criterion: dict[str, Any], note: str) -> ExtractionOut:
    """Sync wrapper for tests / non-async callers."""
    return asyncio.run(extract_field(criterion, note))


def dump_cache_stats() -> str:
    return json.dumps({"cache_entries": len(_CACHE)}, indent=2)

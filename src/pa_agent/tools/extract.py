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
# Live-mode overrides (e.g. Fixture C hallucinated c3) applied after Haiku
_LIVE_OVERRIDES: dict[str, ExtractionOut] = {}


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


def set_live_overrides(mapping: dict[str, ExtractionOut]) -> None:
    """Force specific criterion outputs in live mode (demo hallucination)."""
    _LIVE_OVERRIDES.clear()
    _LIVE_OVERRIDES.update(mapping)


def clear_live_overrides() -> None:
    _LIVE_OVERRIDES.clear()


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

    cid = str(criterion["id"])
    # Demo inject wins even in live mode (Fixture C hallucinated quote)
    if cid in _LIVE_OVERRIDES:
        result = dict(_LIVE_OVERRIDES[cid])  # type: ignore[assignment]
        _CACHE[key] = result  # type: ignore[assignment]
        return dict(result)  # type: ignore[return-value]

    settings = get_settings()
    if settings.use_mock_llm:
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

    from pa_agent.llm import get_extract_llm, structured

    class _Out(BaseModel):
        value: str | None = Field(
            default=None,
            description="Short answer for the criterion, or null if unsupported",
        )
        confidence: float = Field(
            default=0.0, ge=0.0, le=1.0, description="Confidence 0-1"
        )
        quote: str | None = Field(
            default=None,
            description="Verbatim substring copied from the note, or null",
        )

    prompt = (
        "Extract evidence for the prior-auth criterion from the clinical note.\n"
        "Return value (short answer), confidence 0-1, and a verbatim quote "
        "copied exactly from the note. If unsupported, value/quote null and "
        "confidence 0.\n"
        "Never invent a quote that is not present in the note.\n\n"
        f"Criterion: {criterion.get('text')}\n\n"
        f"Note:\n{note}"
    )

    last_exc: Exception | None = None
    for _attempt in range(2):  # initial + one retry (spec §7)
        try:
            llm = structured(get_extract_llm(), _Out)
            # Prefer sync invoke inside the fan-out thread to avoid loop reuse bugs
            out: _Out = await asyncio.to_thread(llm.invoke, prompt)
            return {
                "value": out.value,
                "confidence": float(out.confidence),
                "quote": out.quote,
            }
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await asyncio.sleep(0.35)

    # Soft-fail → field not extracted → needs_review
    if last_exc:
        import logging

        from pa_agent.errors import sanitize_exc

        logging.getLogger("pa_agent.extract").warning(
            "live extract failed for %s: %s",
            criterion.get("id"),
            sanitize_exc(last_exc),
        )
    return {"value": None, "confidence": 0.0, "quote": None}


def extract_field_sync(criterion: dict[str, Any], note: str) -> ExtractionOut:
    """Sync wrapper for tests / non-async callers."""
    return asyncio.run(extract_field(criterion, note))


def dump_cache_stats() -> str:
    return json.dumps({"cache_entries": len(_CACHE)}, indent=2)

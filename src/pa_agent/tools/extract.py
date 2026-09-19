"""extract_field — OpenRouter Haiku (live) or fixture-aware mock (Block 1).

Cache key: (sha256(note), criterion_id).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, TypedDict

from pa_agent.config import get_settings


class ExtractionOut(TypedDict):
    value: str | None
    confidence: float
    quote: str | None


_CACHE: dict[tuple[str, str], ExtractionOut] = {}

# Fixture-driven mock responses keyed by criterion_id. Quotes must be
# substrings of the golden note for Fixture B; Fixture C intentionally
# returns a hallucinated quote for c3.
_MOCK_BY_CRITERION: dict[str, ExtractionOut] = {}


def note_hash(note: str) -> str:
    return hashlib.sha256(note.encode("utf-8")).hexdigest()


def clear_extract_cache() -> None:
    _CACHE.clear()


def configure_mock_extractions(mapping: dict[str, ExtractionOut]) -> None:
    """Test/fixture hook: set mock outputs per criterion_id."""
    _MOCK_BY_CRITERION.clear()
    _MOCK_BY_CRITERION.update(mapping)


def _mock_extract(criterion: dict[str, Any], note: str) -> ExtractionOut:
    cid = criterion["id"]
    if cid in _MOCK_BY_CRITERION:
        return dict(_MOCK_BY_CRITERION[cid])  # type: ignore[return-value]

    # Heuristic fallback: if criterion keywords appear in note, return a
    # short verbatim window; else empty (routes to needs_review).
    text = criterion.get("text", "")
    # Prefer longest sentence from note that shares a key token
    tokens = [t.lower() for t in text.replace(",", " ").split() if len(t) > 4]
    for sentence in note.replace("\n", " ").split("."):
        s = sentence.strip()
        if not s:
            continue
        lower = s.lower()
        if any(tok in lower for tok in tokens[:3]):
            quote = s if s.endswith(".") else s + "."
            # Only accept if quote is actually in note (normalized later)
            if quote.rstrip(".") in note or s in note:
                return {
                    "value": s[:120],
                    "confidence": 0.85,
                    "quote": s if s in note else None,
                }
    return {"value": None, "confidence": 0.0, "quote": None}


async def extract_field(criterion: dict[str, Any], note: str) -> ExtractionOut:
    """Extract one criterion. Cached. Mock until USE_MOCK_EXTRACT=0."""
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


async def _live_extract(criterion: dict[str, Any], note: str) -> ExtractionOut:
    """Live Haiku path — wired in Block 3; stubbed safely for Block 1."""
    # Deferred: structured OpenRouter call. Fail soft → needs_review.
    try:
        from pydantic import BaseModel, Field

        from pa_agent.llm import get_extract_llm

        class _Out(BaseModel):
            value: str | None = Field(default=None)
            confidence: float = Field(default=0.0, ge=0.0, le=1.0)
            quote: str | None = Field(default=None)

        llm = get_extract_llm().with_structured_output(_Out)
        prompt = (
            "Extract evidence for the prior-auth criterion from the clinical note.\n"
            "Return value (short answer), confidence 0-1, and a verbatim quote "
            "copied from the note. If unsupported, value/quote null and confidence 0.\n\n"
            f"Criterion: {criterion.get('text')}\n\n"
            f"Note:\n{note}"
        )
        out: _Out = await llm.ainvoke(prompt)
        return {
            "value": out.value,
            "confidence": float(out.confidence),
            "quote": out.quote,
        }
    except Exception:  # noqa: BLE001
        return {"value": None, "confidence": 0.0, "quote": None}


def extract_field_sync(criterion: dict[str, Any], note: str) -> ExtractionOut:
    """Sync wrapper for tests / non-async callers."""
    import asyncio

    return asyncio.run(extract_field(criterion, note))


def dump_cache_stats() -> str:
    return json.dumps({"cache_entries": len(_CACHE)}, indent=2)

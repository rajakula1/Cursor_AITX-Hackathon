"""Load golden fixtures and apply mock extraction maps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pa_agent.tools.extract import ExtractionOut, configure_mock_extractions, clear_extract_cache

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES_DIR / name
    if not path.suffix:
        path = FIXTURES_DIR / f"{name}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def list_fixtures() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("fixture_*.json"))


def apply_fixture_mocks(fixture: dict[str, Any]) -> None:
    """Install mock extract outputs for this fixture and clear LLM cache."""
    clear_extract_cache()
    raw = fixture.get("mock_extractions") or {}
    mapping: dict[str, ExtractionOut] = {}
    for cid, payload in raw.items():
        mapping[cid] = {
            "value": payload.get("value"),
            "confidence": float(payload.get("confidence") or 0.0),
            "quote": payload.get("quote"),
        }
    configure_mock_extractions(mapping)

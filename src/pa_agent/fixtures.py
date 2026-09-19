"""Load golden fixtures and apply mock extraction / critic maps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pa_agent.tools.critique import (
    CriticDecision,
    clear_mock_critic,
    configure_mock_critic,
)
from pa_agent.tools.extract import (
    ExtractionOut,
    clear_extract_cache,
    configure_mock_extractions,
)

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
    """Install mock extract (+ optional critic) outputs; clear LLM cache."""
    clear_extract_cache()
    clear_mock_critic()

    raw = fixture.get("mock_extractions") or {}
    mapping: dict[str, ExtractionOut] = {}
    for cid, payload in raw.items():
        mapping[cid] = {
            "value": payload.get("value"),
            "confidence": float(payload.get("confidence") or 0.0),
            "quote": payload.get("quote"),
        }
    configure_mock_extractions(mapping)

    critic_raw = fixture.get("mock_critic") or {}
    if critic_raw:
        decisions: dict[str, CriticDecision] = {}
        for cid, payload in critic_raw.items():
            decisions[cid] = {
                "criterion_id": cid,
                "action": payload["action"],
                "confidence": float(payload.get("confidence") or 0.0),
                "reason": str(payload.get("reason") or ""),
            }
        configure_mock_critic(decisions)

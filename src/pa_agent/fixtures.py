"""Load golden fixtures and apply mock extraction / critic maps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pa_agent.config import get_settings
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


def apply_fixture_mocks(fixture: dict[str, Any], *, force: bool = False) -> None:
    """Install mock extract (+ optional critic) outputs.

    In live mode (USE_MOCK_EXTRACT=0), skips full mocks unless force=True and
    does **not** clear the Haiku extract cache (re-runs stay fast).
    Fixture C still injects only the hallucinated c3 quote when
    INJECT_FIXTURE_C_HALLUCINATION=1 (default off) so talk-track #2 stays optional.
    """
    from pa_agent.tools.extract import clear_live_overrides, set_live_overrides

    clear_mock_critic()
    clear_live_overrides()
    settings = get_settings()

    if settings.use_mock_llm or force:
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
        return

    # Live mode: optional single-field hallucination inject for Fixture C
    if (
        settings.inject_fixture_c_hallucination
        and fixture.get("id") == "fixture_c_needs_review"
    ):
        raw = fixture.get("mock_extractions") or {}
        c3 = raw.get("c3")
        if c3:
            set_live_overrides(
                {
                    "c3": {
                        "value": c3.get("value"),
                        "confidence": float(c3.get("confidence") or 0.0),
                        "quote": c3.get("quote"),
                    }
                }
            )

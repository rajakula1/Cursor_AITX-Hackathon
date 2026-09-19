"""get_formulary_alternative — conditional when likelihood < 0.55."""

from __future__ import annotations

from typing import Any

from pa_agent.data.seed_store import find_formulary_alternative


def get_formulary_alternative(
    drug_class: str, payer: str
) -> dict[str, Any] | None:
    """Prefer alternatives with requires_pa=false."""
    return find_formulary_alternative(drug_class, payer, prefer_no_pa=True)

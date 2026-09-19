"""get_payer_policy — alias map + policy row lookup."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pa_agent.data.seed_store import find_policy, resolve_drug, resolve_payer


class PolicyResult(TypedDict):
    lookup: Literal["found", "not_found", "error"]
    requires_pa: bool | None
    criteria: list[dict[str, Any]]
    drug_class: str | None
    historical_approval_rate: float | None
    canonical_drug: str | None
    canonical_payer: str | None
    reason: str | None


def get_payer_policy(drug: str, diagnosis: str, payer: str) -> PolicyResult:
    """Resolve aliases and look up payer_policies.

    not_found never becomes no_pa_required — caller routes to needs_review.
    """
    try:
        canonical_payer = resolve_payer(payer)
        drug_row = resolve_drug(drug)
        if not canonical_payer:
            return PolicyResult(
                lookup="not_found",
                requires_pa=None,
                criteria=[],
                drug_class=None,
                historical_approval_rate=None,
                canonical_drug=None,
                canonical_payer=None,
                reason=f"Unresolvable payer alias: {payer!r}",
            )
        if not drug_row:
            return PolicyResult(
                lookup="not_found",
                requires_pa=None,
                criteria=[],
                drug_class=None,
                historical_approval_rate=None,
                canonical_drug=None,
                canonical_payer=canonical_payer,
                reason=f"Unresolvable drug alias: {drug!r}",
            )

        canonical_drug = drug_row["canonical_drug"]
        row = find_policy(canonical_drug, diagnosis.strip(), canonical_payer)
        if not row:
            return PolicyResult(
                lookup="not_found",
                requires_pa=None,
                criteria=[],
                drug_class=drug_row["drug_class"],
                historical_approval_rate=None,
                canonical_drug=canonical_drug,
                canonical_payer=canonical_payer,
                reason=(
                    f"No policy for {canonical_payer} / {canonical_drug} / {diagnosis}"
                ),
            )

        return PolicyResult(
            lookup="found",
            requires_pa=bool(row["requires_pa"]),
            criteria=list(row["criteria"]),
            drug_class=row["drug_class"],
            historical_approval_rate=float(row["historical_approval_rate"]),
            canonical_drug=canonical_drug,
            canonical_payer=canonical_payer,
            reason=None,
        )
    except Exception as exc:  # noqa: BLE001 — tool must degrade, not crash
        return PolicyResult(
            lookup="error",
            requires_pa=None,
            criteria=[],
            drug_class=None,
            historical_approval_rate=None,
            canonical_drug=None,
            canonical_payer=None,
            reason=str(exc),
        )

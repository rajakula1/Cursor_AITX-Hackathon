"""Data access: Supabase when configured, in-memory seed_store fallback."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pa_agent.data import seed_store
from pa_agent.data.supabase_client import get_client, is_configured


def resolve_payer(payer: str) -> str | None:
    key = seed_store.normalize_key(payer)
    if is_configured():
        try:
            res = (
                get_client()
                .table("payer_aliases")
                .select("canonical_payer")
                .eq("alias", key)
                .limit(1)
                .execute()
            )
            if res.data:
                return str(res.data[0]["canonical_payer"])
        except Exception:
            pass
    return seed_store.resolve_payer(payer)


def resolve_drug(drug: str) -> dict[str, str] | None:
    key = seed_store.normalize_key(drug)
    if is_configured():
        try:
            res = (
                get_client()
                .table("drug_aliases")
                .select("canonical_drug, drug_class")
                .eq("alias", key)
                .limit(1)
                .execute()
            )
            if res.data:
                row = res.data[0]
                return {
                    "canonical_drug": str(row["canonical_drug"]),
                    "drug_class": str(row["drug_class"]),
                }
        except Exception:
            pass
    return seed_store.resolve_drug(drug)


def find_policy(
    drug_name: str, diagnosis_code: str, payer_name: str
) -> dict[str, Any] | None:
    if is_configured():
        try:
            res = (
                get_client()
                .table("payer_policies")
                .select(
                    "payer_name, drug_name, drug_class, diagnosis_code, "
                    "requires_pa, criteria, historical_approval_rate"
                )
                .eq("payer_name", payer_name)
                .eq("drug_name", drug_name)
                .eq("diagnosis_code", diagnosis_code)
                .limit(1)
                .execute()
            )
            if res.data:
                row = dict(res.data[0])
                row["criteria"] = list(row.get("criteria") or [])
                row["historical_approval_rate"] = float(
                    row.get("historical_approval_rate") or 0.7
                )
                return row
        except Exception:
            pass
    return seed_store.find_policy(drug_name, diagnosis_code, payer_name)


def find_formulary_alternative(
    drug_class: str, payer_name: str, prefer_no_pa: bool = True
) -> dict[str, Any] | None:
    if is_configured():
        try:
            res = (
                get_client()
                .table("formulary_alternatives")
                .select(
                    "payer_name, drug_class, original_drug, "
                    "alternative_drug, requires_pa"
                )
                .eq("payer_name", payer_name)
                .eq("drug_class", drug_class)
                .execute()
            )
            matches = [dict(r) for r in (res.data or [])]
            if matches:
                if prefer_no_pa:
                    no_pa = [m for m in matches if not m.get("requires_pa")]
                    if no_pa:
                        return no_pa[0]
                return matches[0]
        except Exception:
            pass
    return seed_store.find_formulary_alternative(
        drug_class, payer_name, prefer_no_pa=prefer_no_pa
    )


def save_case_mem(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return seed_store.save_case(case_id, payload)


def get_case_mem(case_id: str) -> dict[str, Any] | None:
    return seed_store.get_case(case_id)


def get_case(case_id: str) -> dict[str, Any] | None:
    """Memory first (tests/demo), then Supabase pa_cases."""
    mem = seed_store.get_case(case_id)
    if mem is not None:
        return mem
    if not is_configured():
        return None
    try:
        res = (
            get_client()
            .table("pa_cases")
            .select("*")
            .eq("case_id", case_id)
            .limit(1)
            .execute()
        )
        if res.data:
            return deepcopy(dict(res.data[0]))
    except Exception:
        return None
    return None


def upsert_pa_case(row: dict[str, Any]) -> None:
    """Upsert one pa_cases row. Raises on failure (caller soft-fails)."""
    client = get_client()
    client.table("pa_cases").upsert(row, on_conflict="case_id").execute()


def seed_reference_data() -> dict[str, int]:
    """Upsert aliases / policies / formulary from in-memory seeds into Supabase."""
    client = get_client()
    counts: dict[str, int] = {}

    payer_rows = [
        {"alias": alias, "canonical_payer": canonical}
        for alias, canonical in seed_store.PAYER_ALIASES.items()
    ]
    client.table("payer_aliases").upsert(payer_rows, on_conflict="alias").execute()
    counts["payer_aliases"] = len(payer_rows)

    drug_rows = [
        {
            "alias": alias,
            "canonical_drug": meta["canonical_drug"],
            "drug_class": meta["drug_class"],
        }
        for alias, meta in seed_store.DRUG_ALIASES.items()
    ]
    client.table("drug_aliases").upsert(drug_rows, on_conflict="alias").execute()
    counts["drug_aliases"] = len(drug_rows)

    policy_rows = []
    for p in seed_store.PAYER_POLICIES:
        policy_rows.append(
            {
                "payer_name": p["payer_name"],
                "drug_name": p["drug_name"],
                "drug_class": p["drug_class"],
                "diagnosis_code": p["diagnosis_code"],
                "requires_pa": p["requires_pa"],
                "criteria": p["criteria"],
                "historical_approval_rate": p["historical_approval_rate"],
            }
        )
    client.table("payer_policies").upsert(
        policy_rows, on_conflict="payer_name,drug_name,diagnosis_code"
    ).execute()
    counts["payer_policies"] = len(policy_rows)

    alt_rows = [dict(a) for a in seed_store.FORMULARY_ALTERNATIVES]
    # No natural unique key in schema beyond id — delete+insert class matches is heavy;
    # upsert by scanning: insert only when empty, else leave existing.
    existing = (
        client.table("formulary_alternatives")
        .select("id", count="exact")
        .limit(1)
        .execute()
    )
    if int(existing.count or 0) == 0:
        client.table("formulary_alternatives").insert(alt_rows).execute()
        counts["formulary_alternatives"] = len(alt_rows)
    else:
        counts["formulary_alternatives"] = int(existing.count or 0)

    return counts

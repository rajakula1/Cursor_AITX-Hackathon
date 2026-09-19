"""Data access: warm-cached reference tables + Supabase pa_cases writes.

Reference reads (aliases / policies / formulary) are loaded once into process
memory (from Supabase when configured, else seed_store) so each case does not
pay 3–6 HTTP round-trips. Case persistence still upserts to Supabase.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pa_agent.data import seed_store
from pa_agent.data.supabase_client import get_client, is_configured

_WARM = False
_PAYER_ALIASES: dict[str, str] = {}
_DRUG_ALIASES: dict[str, dict[str, str]] = {}
_POLICIES: list[dict[str, Any]] = []
_FORMULARY: list[dict[str, Any]] = []


def clear_reference_cache() -> None:
    """Test / ping hook — force next lookup to re-warm."""
    global _WARM
    _WARM = False
    _PAYER_ALIASES.clear()
    _DRUG_ALIASES.clear()
    _POLICIES.clear()
    _FORMULARY.clear()


def _load_from_seed() -> None:
    _PAYER_ALIASES.update(seed_store.PAYER_ALIASES)
    _DRUG_ALIASES.update(
        {k: dict(v) for k, v in seed_store.DRUG_ALIASES.items()}
    )
    _POLICIES.extend(deepcopy(seed_store.PAYER_POLICIES))
    _FORMULARY.extend(deepcopy(seed_store.FORMULARY_ALTERNATIVES))


def _load_from_supabase() -> bool:
    client = get_client()
    payers = client.table("payer_aliases").select("alias, canonical_payer").execute()
    drugs = (
        client.table("drug_aliases")
        .select("alias, canonical_drug, drug_class")
        .execute()
    )
    policies = (
        client.table("payer_policies")
        .select(
            "payer_name, drug_name, drug_class, diagnosis_code, "
            "requires_pa, criteria, historical_approval_rate"
        )
        .execute()
    )
    alts = (
        client.table("formulary_alternatives")
        .select(
            "payer_name, drug_class, original_drug, alternative_drug, requires_pa"
        )
        .execute()
    )
    if not (payers.data and drugs.data and policies.data):
        return False

    for row in payers.data:
        _PAYER_ALIASES[str(row["alias"])] = str(row["canonical_payer"])
    for row in drugs.data:
        _DRUG_ALIASES[str(row["alias"])] = {
            "canonical_drug": str(row["canonical_drug"]),
            "drug_class": str(row["drug_class"]),
        }
    for row in policies.data:
        item = dict(row)
        item["criteria"] = list(item.get("criteria") or [])
        item["historical_approval_rate"] = float(
            item.get("historical_approval_rate") or 0.7
        )
        _POLICIES.append(item)
    for row in alts.data or []:
        _FORMULARY.append(dict(row))
    return True


def warm_reference_cache(*, force: bool = False) -> str:
    """Load reference tables once. Returns source: supabase | seed."""
    global _WARM
    if _WARM and not force:
        return "cached"
    clear_reference_cache()
    source = "seed"
    if is_configured():
        try:
            if _load_from_supabase():
                source = "supabase"
            else:
                _load_from_seed()
        except Exception:
            clear_reference_cache()
            _load_from_seed()
    else:
        _load_from_seed()
    _WARM = True
    return source


def _ensure_warm() -> None:
    if not _WARM:
        warm_reference_cache()


def resolve_payer(payer: str) -> str | None:
    _ensure_warm()
    key = seed_store.normalize_key(payer)
    return _PAYER_ALIASES.get(key) or seed_store.resolve_payer(payer)


def resolve_drug(drug: str) -> dict[str, str] | None:
    _ensure_warm()
    key = seed_store.normalize_key(drug)
    row = _DRUG_ALIASES.get(key)
    if row:
        return dict(row)
    return seed_store.resolve_drug(drug)


def find_policy(
    drug_name: str, diagnosis_code: str, payer_name: str
) -> dict[str, Any] | None:
    _ensure_warm()
    for row in _POLICIES:
        if (
            row["payer_name"] == payer_name
            and row["drug_name"] == drug_name
            and row["diagnosis_code"] == diagnosis_code
        ):
            return deepcopy(row)
    return seed_store.find_policy(drug_name, diagnosis_code, payer_name)


def find_formulary_alternative(
    drug_class: str, payer_name: str, prefer_no_pa: bool = True
) -> dict[str, Any] | None:
    _ensure_warm()
    matches = [
        deepcopy(r)
        for r in _FORMULARY
        if r["payer_name"] == payer_name and r["drug_class"] == drug_class
    ]
    if matches:
        if prefer_no_pa:
            no_pa = [m for m in matches if not m.get("requires_pa")]
            if no_pa:
                return no_pa[0]
        return matches[0]
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

    clear_reference_cache()
    return counts

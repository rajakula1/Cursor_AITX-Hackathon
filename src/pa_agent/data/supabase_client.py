"""Supabase client factory — service role, server-side only."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pa_agent.config import get_settings


def is_configured() -> bool:
    """True when URL + service role look real (not .env.example placeholders)."""
    settings = get_settings()
    url = (settings.supabase_url or "").strip()
    key = (settings.supabase_key or "").strip()
    if not url or not key:
        return False
    if "your-project" in url or key.startswith("your-"):
        return False
    return True


@lru_cache(maxsize=1)
def get_client() -> Any:
    """Cached PostgREST client. Raises if not configured."""
    if not is_configured():
        raise RuntimeError(
            "Supabase not configured — set SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY in .env"
        )
    from supabase import create_client

    settings = get_settings()
    assert settings.supabase_url and settings.supabase_key
    return create_client(settings.supabase_url, settings.supabase_key)


def clear_client_cache() -> None:
    get_client.cache_clear()


def health_check() -> dict[str, Any]:
    """Probe reference tables; used by UI + ping script."""
    if not is_configured():
        return {
            "ok": False,
            "configured": False,
            "message": "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set",
            "tables": {},
        }

    tables = (
        "payer_aliases",
        "drug_aliases",
        "payer_policies",
        "formulary_alternatives",
        "pa_cases",
    )
    counts: dict[str, int | str] = {}
    try:
        client = get_client()
        for name in tables:
            try:
                res = client.table(name).select("*", count="exact").limit(1).execute()
                counts[name] = int(res.count or 0)
            except Exception as exc:  # noqa: BLE001
                counts[name] = f"error: {exc}"
        missing = [t for t, v in counts.items() if isinstance(v, str)]
        empty_ref = [
            t
            for t in ("payer_aliases", "drug_aliases", "payer_policies")
            if counts.get(t) == 0
        ]
        if missing:
            missing_schema = any(
                "PGRST205" in str(counts[t]) or "schema cache" in str(counts[t]).lower()
                for t in missing
            )
            msg = (
                "Tables not created yet — paste sql/setup.sql (or sql/schema.sql) "
                "in the Supabase SQL editor, then: python scripts/ping_supabase.py --seed"
                if missing_schema
                else (
                    "Tables missing or inaccessible — run sql/schema.sql "
                    "in the Supabase SQL editor"
                )
            )
            return {
                "ok": False,
                "configured": True,
                "message": msg,
                "tables": counts,
            }
        if empty_ref:
            return {
                "ok": False,
                "configured": True,
                "message": (
                    "Reference tables empty — run sql/seed.sql "
                    "or: python scripts/ping_supabase.py --seed"
                ),
                "tables": counts,
            }
        return {
            "ok": True,
            "configured": True,
            "message": "connected",
            "tables": counts,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "configured": True,
            "message": str(exc),
            "tables": counts,
        }

#!/usr/bin/env python3
"""Ping Supabase and optionally seed reference tables.

Usage (prefer the project venv):
  .venv/bin/python scripts/ping_supabase.py
  .venv/bin/python scripts/ping_supabase.py --seed

Prerequisite: run sql/setup.sql once in the Supabase SQL editor.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"


def _reexec_in_venv_if_needed() -> None:
    """If .venv exists and we're not running it, re-exec so deps resolve.

    Do not Path.resolve() the venv interpreter — on macOS it is often a symlink
    to Homebrew Python; exec'ing the target skips the venv site-packages.
    """
    if not VENV_PYTHON.is_file():
        return
    if os.environ.get("_PA_PING_VENV") == "1":
        return
    # Already running this venv?
    venv_root = (ROOT / ".venv").resolve()
    try:
        if Path(sys.prefix).resolve() == venv_root:
            return
    except OSError:
        pass
    os.environ["_PA_PING_VENV"] = "1"
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


_reexec_in_venv_if_needed()

sys.path.insert(0, str(ROOT / "src"))

try:
    from pa_agent.data.supabase_client import (  # noqa: E402
        clear_client_cache,
        health_check,
        is_configured,
    )
except ModuleNotFoundError as exc:
    missing = getattr(exc, "name", None) or str(exc)
    print(
        f"FAIL: missing package ({missing}).\n"
        "Install into the project venv, then re-run:\n"
        "  python3 -m venv .venv\n"
        "  source .venv/bin/activate\n"
        "  pip install -r requirements.txt\n"
        "  .venv/bin/python scripts/ping_supabase.py"
    )
    raise SystemExit(1) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Ping / seed Supabase for PA Intake")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="Upsert aliases, policies, formulary from in-memory seeds",
    )
    args = parser.parse_args()

    clear_client_cache()
    if not is_configured():
        print("FAIL: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        return 1

    health = health_check()
    print(json.dumps(health, indent=2, default=str))

    if args.seed:
        from pa_agent.data.repository import seed_reference_data

        try:
            counts = seed_reference_data()
            print("seeded:", json.dumps(counts, indent=2))
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL seed: {exc}")
            print("Hint: run sql/setup.sql in the Supabase SQL editor first.")
            return 1
        health = health_check()
        print("after seed:", json.dumps(health, indent=2, default=str))
        return 0 if health.get("ok") else 1

    if not health.get("ok"):
        msg = str(health.get("message") or "")
        if "No module named" in msg or "supabase" in msg.lower():
            print(
                "\nFix: use the project venv (has the supabase package):\n"
                "  source .venv/bin/activate\n"
                "  python scripts/ping_supabase.py\n"
                "or:\n"
                "  .venv/bin/python scripts/ping_supabase.py"
            )
        else:
            print(
                "\nNext steps:\n"
                "  1. Supabase SQL editor → paste sql/setup.sql → Run\n"
                "  2. .venv/bin/python scripts/ping_supabase.py --seed"
            )
        return 1

    print("OK: Supabase ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

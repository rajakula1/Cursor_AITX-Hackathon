#!/usr/bin/env python3
"""Live OpenRouter smoke: ping + Fixture B end-to-end with USE_MOCK_EXTRACT=0.

Requires OPENROUTER_API_KEY in .env. Costs real OpenRouter credits.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Force live mode for this process (do not rely on .env alone)
os.environ["USE_MOCK_EXTRACT"] = "0"

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from pa_agent.config import get_settings, is_live_llm, require_openrouter_key  # noqa: E402
from pa_agent.data.seed_store import clear_cases  # noqa: E402
from pa_agent.fixtures import apply_fixture_mocks, load_fixture  # noqa: E402
from pa_agent.graph import get_compiled_graph, run_case  # noqa: E402
from pa_agent.tools.critique import clear_mock_critic  # noqa: E402
from pa_agent.tools.extract import clear_extract_cache, clear_live_overrides  # noqa: E402


def main() -> int:
    print("Live OpenRouter smoke")
    print(f"  USE_MOCK_EXTRACT={os.environ.get('USE_MOCK_EXTRACT')}")
    print(f"  is_live_llm={is_live_llm()}")
    settings = get_settings()
    print(f"  extract_model={settings.extract_model}")
    print(f"  critic_model={settings.critic_model}")

    try:
        require_openrouter_key()
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1

    # 1) Ping
    print("\n[1/2] Ping Haiku…")
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_app_title,
        },
    )
    try:
        resp = client.chat.completions.create(
            model=settings.extract_model,
            messages=[{"role": "user", "content": "Reply with exactly PONG"}],
            temperature=0,
            max_tokens=16,
            extra_body={"provider": {"require_parameters": True}},
        )
        text = (resp.choices[0].message.content or "").strip()
        print(f"  Response: {text!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL ping: {exc}")
        return 2

    # 2) Fixture B live graph
    print("\n[2/2] Fixture B live graph (Haiku fan-out + Sonnet critic/draft)…")
    clear_cases()
    clear_extract_cache()
    clear_mock_critic()
    clear_live_overrides()
    get_compiled_graph.cache_clear()

    fx = load_fixture("fixture_b_auto_completed")
    apply_fixture_mocks(fx)  # live: no full mocks
    inp = fx["input"]
    try:
        result = run_case(
            drug_name=inp["drug_name"],
            diagnosis_code=inp["diagnosis_code"],
            payer_name=inp["payer_name"],
            clinical_note=inp["clinical_note"],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL graph: {exc}")
        return 3

    print(f"  status={result.get('status')}")
    print(f"  likelihood={result.get('approval_likelihood')}")
    print(f"  missing={result.get('missing_fields')}")
    for ext in result.get("extractions") or []:
        print(
            f"  {ext['criterion_id']}: met={ext.get('met')} "
            f"verified={ext.get('quote_verified')} "
            f"conf={float(ext.get('confidence') or 0):.2f} "
            f"| {(ext.get('critic_note') or '')[:60]}"
        )
    export = (result.get("draft_pa_form") or {}).get("export_markdown") or ""
    print(f"  export_chars={len(export)}")

    if result.get("status") not in (
        "auto_completed",
        "needs_review",
        "no_pa_required",
    ):
        print("FAIL: invalid public status")
        return 4

    # Soft expectation: with a rich note, prefer auto_completed but allow review
    if result.get("status") == "auto_completed":
        print("PASS: live Fixture B auto_completed")
    else:
        print(
            "WARN: live Fixture B returned "
            f"{result.get('status')} (soft-fail/critique may have downgraded). "
            "Graph stayed crash-free."
        )
        print("PASS: live path completed without crash")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

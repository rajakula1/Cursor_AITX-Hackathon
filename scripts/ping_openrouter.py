#!/usr/bin/env python3
"""Confirm one OpenRouter ping before wiring graph nodes (Block 1 gate)."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `python scripts/ping_openrouter.py` without installing the package
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pa_agent.config import get_settings, require_openrouter_key  # noqa: E402


def main() -> int:
    settings = get_settings()
    try:
        require_openrouter_key()
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 1

    from openai import OpenAI

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_app_title,
        },
    )

    print(f"Pinging OpenRouter model={settings.extract_model} ...")
    try:
        resp = client.chat.completions.create(
            model=settings.extract_model,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with exactly the word PONG and nothing else.",
                }
            ],
            temperature=0,
            max_tokens=16,
            extra_body={"provider": {"require_parameters": True}},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: OpenRouter call error: {exc}")
        return 2

    text = (resp.choices[0].message.content or "").strip()
    print(f"Response: {text!r}")
    if "PONG" in text.upper():
        print("OK: OpenRouter reachable.")
        return 0
    print("WARN: Call succeeded but unexpected content (still usable).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

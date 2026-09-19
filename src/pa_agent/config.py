"""Environment / stack config. One required secret: OPENROUTER_API_KEY."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:8501"
    openrouter_app_title: str = "PA-Intake-Hackathon"
    extract_model: str = "anthropic/claude-haiku-4.5"
    critic_model: str = "anthropic/claude-sonnet-4.5"
    supabase_url: str | None = None
    supabase_key: str | None = None
    llm_timeout_s: float = 45.0
    llm_max_retries: int = 1
    use_mock_extract: bool = True  # Block 1 default until routing works


def get_settings() -> Settings:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    return Settings(
        openrouter_api_key=key,
        openrouter_http_referer=os.environ.get(
            "OPENROUTER_HTTP_REFERER", "http://localhost:8501"
        ),
        openrouter_app_title=os.environ.get(
            "OPENROUTER_APP_TITLE", "PA-Intake-Hackathon"
        ),
        supabase_url=os.environ.get("SUPABASE_URL") or None,
        supabase_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or None,
        use_mock_extract=os.environ.get("USE_MOCK_EXTRACT", "1") not in (
            "0",
            "false",
            "False",
        ),
    )


def require_openrouter_key() -> str:
    settings = get_settings()
    if not settings.openrouter_api_key or settings.openrouter_api_key.startswith(
        "sk-or-v1-your"
    ):
        raise RuntimeError(
            "Set OPENROUTER_API_KEY in .env (copy from .env.example). "
            "Cursor credits do not pay OpenRouter calls."
        )
    return settings.openrouter_api_key

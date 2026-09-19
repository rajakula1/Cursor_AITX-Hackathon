"""Environment / stack config. One required secret: OPENROUTER_API_KEY."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")

_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}


def _env_flag(name: str, *, default: bool) -> bool:
    """Parse boolean env; unknown/garbage values fall back to default (safer)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in _TRUTHY:
        return True
    if val in _FALSY:
        return False
    return default


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
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 1
    # When True: extract/critic/draft use fixtures/heuristic mocks (offline tests)
    use_mock_llm: bool = True
    # Demo-only: inject Fixture C hallucinated c3 (default OFF — enable for talk track)
    inject_fixture_c_hallucination: bool = False
    # Optional third Sonnet call for qty/duration (default OFF — saves ~1–3s)
    use_draft_meta_llm: bool = False
    # Log per-node wall times to stderr / Streamlit-friendly logger
    latency_log: bool = False


def get_settings() -> Settings:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    # Default mock ON so typos don't accidentally go live + spend + egress
    use_mock = _env_flag("USE_MOCK_EXTRACT", default=True)
    return Settings(
        openrouter_api_key=key,
        openrouter_http_referer=os.environ.get(
            "OPENROUTER_HTTP_REFERER", "http://localhost:8501"
        ),
        openrouter_app_title=os.environ.get(
            "OPENROUTER_APP_TITLE", "PA-Intake-Hackathon"
        ),
        extract_model=os.environ.get(
            "OPENROUTER_EXTRACT_MODEL", "anthropic/claude-haiku-4.5"
        ),
        critic_model=os.environ.get(
            "OPENROUTER_CRITIC_MODEL", "anthropic/claude-sonnet-4.5"
        ),
        supabase_url=os.environ.get("SUPABASE_URL") or None,
        supabase_key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or None,
        llm_timeout_s=float(os.environ.get("LLM_TIMEOUT_S", "60")),
        use_mock_llm=use_mock,
        inject_fixture_c_hallucination=_env_flag(
            "INJECT_FIXTURE_C_HALLUCINATION", default=False
        ),
        use_draft_meta_llm=_env_flag("USE_DRAFT_META_LLM", default=False),
        latency_log=_env_flag("LATENCY_LOG", default=False),
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


def is_live_llm() -> bool:
    return not get_settings().use_mock_llm

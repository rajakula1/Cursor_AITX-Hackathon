"""OpenRouter LLM clients (OpenAI-compatible). No Anthropic SDK."""

from __future__ import annotations

import logging

from langchain_openai import ChatOpenAI

from pa_agent.config import get_settings, require_openrouter_key

_log = logging.getLogger("pa_agent.llm")


def _base_kwargs(model: str) -> dict:
    settings = get_settings()
    require_openrouter_key()
    return {
        "model": model,
        "temperature": 0,
        "api_key": settings.openrouter_api_key,
        "base_url": settings.openrouter_base_url,
        "timeout": settings.llm_timeout_s,
        "max_retries": settings.llm_max_retries,
        "default_headers": {
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_app_title,
        },
        # Fail closed if a provider hop ignores json_schema (spec §2.6)
        "extra_body": {"provider": {"require_parameters": True}},
    }


def get_extract_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(**_base_kwargs(settings.extract_model))


def get_critic_llm() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(**_base_kwargs(settings.critic_model))


def get_draft_llm() -> ChatOpenAI:
    return get_critic_llm()


def structured(llm: ChatOpenAI, schema):
    """Prefer native json_schema; fall back only on method-not-supported errors."""
    try:
        return llm.with_structured_output(schema, method="json_schema")
    except (NotImplementedError, ValueError, TypeError) as exc:
        _log.warning("json_schema structured output unavailable (%s); falling back", type(exc).__name__)
        return llm.with_structured_output(schema)

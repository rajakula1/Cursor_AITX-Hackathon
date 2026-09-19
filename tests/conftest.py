"""Pytest defaults: always mock LLMs so CI/offline stays free and deterministic."""

from __future__ import annotations

import os

# Must run before pa_agent.config is imported by tests
os.environ["USE_MOCK_EXTRACT"] = "1"
os.environ.setdefault("INJECT_FIXTURE_C_HALLUCINATION", "1")

"""Compile the 10-node PA LangGraph."""

from __future__ import annotations

import logging
import time
from functools import lru_cache, wraps
from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from pa_agent.config import get_settings
from pa_agent.graph.helpers import make_initial_state
from pa_agent.graph.nodes import (
    alternative_suggestion_node,
    approval_likelihood_node,
    confidence_gate_node,
    coverage_check_node,
    critic_node,
    finalize_node,
    intake_node,
    justification_extraction_node,
    pa_draft_builder_node,
    quote_verify_node,
)
from pa_agent.graph.routing import route_after_coverage, route_after_likelihood
from pa_agent.state import PAState

_log = logging.getLogger("pa_agent.latency")


def _timed(name: str, fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    @wraps(fn)
    def _wrap(state: PAState) -> dict[str, Any]:
        if not get_settings().latency_log:
            return fn(state)
        t0 = time.perf_counter()
        out = fn(state)
        ms = (time.perf_counter() - t0) * 1000
        _log.info("node %-28s %7.0f ms", name, ms)
        return out

    return _wrap


def build_graph():
    g: StateGraph = StateGraph(PAState)

    g.add_node("intake", _timed("intake", intake_node))
    g.add_node("coverage_check", _timed("coverage_check", coverage_check_node))
    g.add_node(
        "justification_extraction",
        _timed("justification_extraction", justification_extraction_node),
    )
    g.add_node("quote_verify", _timed("quote_verify", quote_verify_node))
    g.add_node("critic", _timed("critic", critic_node))
    g.add_node("pa_draft_builder", _timed("pa_draft_builder", pa_draft_builder_node))
    g.add_node(
        "approval_likelihood", _timed("approval_likelihood", approval_likelihood_node)
    )
    g.add_node(
        "alternative_suggestion",
        _timed("alternative_suggestion", alternative_suggestion_node),
    )
    g.add_node("confidence_gate", _timed("confidence_gate", confidence_gate_node))
    g.add_node("finalize", _timed("finalize", finalize_node))

    g.add_edge(START, "intake")
    g.add_edge("intake", "coverage_check")
    g.add_conditional_edges(
        "coverage_check",
        route_after_coverage,
        {
            "finalize": "finalize",
            "justification_extraction": "justification_extraction",
        },
    )
    g.add_edge("justification_extraction", "quote_verify")
    g.add_edge("quote_verify", "critic")
    g.add_edge("critic", "pa_draft_builder")
    g.add_edge("pa_draft_builder", "approval_likelihood")
    g.add_conditional_edges(
        "approval_likelihood",
        route_after_likelihood,
        {
            "alternative_suggestion": "alternative_suggestion",
            "confidence_gate": "confidence_gate",
        },
    )
    g.add_edge("alternative_suggestion", "confidence_gate")
    g.add_edge("confidence_gate", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


@lru_cache(maxsize=1)
def get_compiled_graph():
    return build_graph()


def run_case(
    *,
    drug_name: str,
    diagnosis_code: str,
    payer_name: str,
    clinical_note: str,
) -> dict[str, Any]:
    """Invoke the full graph from raw intake fields."""
    graph = get_compiled_graph()
    initial = make_initial_state(
        drug_name=drug_name,
        diagnosis_code=diagnosis_code,
        payer_name=payer_name,
        clinical_note=clinical_note,
    )
    t0 = time.perf_counter()
    result = graph.invoke(initial)
    if get_settings().latency_log:
        _log.info("run_case total %7.0f ms", (time.perf_counter() - t0) * 1000)
    return result

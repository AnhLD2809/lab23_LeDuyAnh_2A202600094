"""Routing functions for conditional edges.

Each function maps graph state to the name of the next node. These are used as
conditional-edge functions by LangGraph's ``add_conditional_edges``.
"""

from __future__ import annotations

import logging

from .state import AgentState, Route

logger = logging.getLogger(__name__)

# Mapping from route values to target graph nodes
_CLASSIFY_MAP: dict[str, str] = {
    Route.SIMPLE.value: "answer",
    Route.TOOL.value: "tool",
    Route.MISSING_INFO.value: "clarify",
    Route.RISKY.value: "risky_action",
    Route.ERROR.value: "retry",
}


def route_after_classify(state: AgentState) -> str:
    """Map classified route to the next graph node.

    Falls back to ``answer`` for unknown routes so the graph always terminates.
    """
    route = state.get("route", Route.SIMPLE.value)
    target = _CLASSIFY_MAP.get(route, "answer")
    if route not in _CLASSIFY_MAP:
        logger.warning("Unknown route '%s' — defaulting to 'answer'", route)
    logger.debug("route_after_classify: route=%s → %s", route, target)
    return target


def route_after_retry(state: AgentState) -> str:
    """Decide whether to retry, fallback, or dead-letter.

    Bounded retry: if ``attempt >= max_attempts`` the request is sent to
    the dead-letter queue for manual review.
    """
    attempt = int(state.get("attempt", 0))
    max_attempts = int(state.get("max_attempts", 3))
    if attempt >= max_attempts:
        logger.info(
            "route_after_retry: attempt=%d >= max_attempts=%d → dead_letter",
            attempt,
            max_attempts,
        )
        return "dead_letter"
    logger.debug("route_after_retry: attempt=%d < max_attempts=%d → tool", attempt, max_attempts)
    return "tool"


def route_after_evaluate(state: AgentState) -> str:
    """Decide whether tool result is satisfactory or needs retry.

    This is the 'done?' check that enables retry loops — a key LangGraph
    advantage over LCEL chains.
    """
    result = state.get("evaluation_result", "success")
    if result == "needs_retry":
        logger.debug("route_after_evaluate: needs_retry → retry")
        return "retry"
    logger.debug("route_after_evaluate: success → answer")
    return "answer"


def route_after_approval(state: AgentState) -> str:
    """Continue only if approved, otherwise redirect to clarification.

    Supports approve → tool, reject → clarify outcomes.
    """
    approval = state.get("approval") or {}
    if approval.get("approved"):
        logger.debug("route_after_approval: approved → tool")
        return "tool"
    logger.info("route_after_approval: rejected → clarify")
    return "clarify"

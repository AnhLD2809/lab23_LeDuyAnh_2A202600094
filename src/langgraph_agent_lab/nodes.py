"""Node functions for the LangGraph workflow.

Each function should be small, testable, and return a partial state update. Avoid mutating the
input state in place.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid

from .state import AgentState, ApprovalDecision, Route, make_event


# ---------------------------------------------------------------------------
# PII patterns used by intake_node
# ---------------------------------------------------------------------------
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN]"),
    (re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "[CARD]"),
]


def _mask_pii(text: str) -> str:
    """Replace common PII patterns with safe placeholders."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def intake_node(state: AgentState) -> dict:
    """Normalize raw query into state fields.

    Performs whitespace normalization and PII masking before forwarding
    the sanitized query to the classifier.
    """
    raw_query = state.get("query", "")
    query = _mask_pii(raw_query.strip())
    return {
        "query": query,
        "messages": [f"intake:{query[:80]}"],
        "events": [make_event("intake", "completed", "query normalized and PII masked")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route.

    Routing policy priority: risky → tool → missing_info → error → simple.
    Uses keyword sets with explicit priority ordering so that a query
    containing both risky and tool keywords is routed to 'risky'.
    """
    query = state.get("query", "")
    query_lower = query.lower()
    tokens = re.findall(r"\b[\w']+\b", query_lower)

    risky_keywords = {
        "refund",
        "delete",
        "send",
        "cancel",
        "remove",
        "revoke",
        "terminate",
        "disable",
        "transfer",
        "transferring",
        "escalate",
        "suspend",
        "purge",
        "wipe",
    }
    tool_keywords = {"status", "order", "lookup", "check", "track", "find", "search", "return"}
    vague_keywords = {"it", "this", "that", "issue", "problem", "thing"}
    error_keywords = {"timeout", "fail", "failure", "error", "crash", "unavailable", "deadlock", "exception"}

    # Detect prompt-injection / system-spoofing patterns — always treat as risky
    injection_patterns = [
        "ignore previous instructions",
        "ignore all instructions",
        "you are now",
        "[system:",
        "system:",
    ]

    route = Route.SIMPLE
    risk_level = "low"

    # 1) Check for injection/spoofing → risky
    if any(pat in query_lower for pat in injection_patterns):
        route = Route.RISKY
        risk_level = "critical"
    # 2) Check risky keywords → risky
    elif any(token in risky_keywords for token in tokens):
        route = Route.RISKY
        risk_level = "high"
    # 3) Check error keywords → error (before tool, so "deadlock exception" isn't misrouted)
    elif any(token in error_keywords for token in tokens) or "cannot recover" in query_lower:
        route = Route.ERROR
    # 4) Check tool keywords → tool
    elif any(token in tool_keywords for token in tokens):
        route = Route.TOOL
    # 5) Check vague / missing info (short + vague pronouns)
    elif len(tokens) < 5 and any(token in vague_keywords for token in tokens):
        route = Route.MISSING_INFO

    return {
        "route": route.value,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route.value}, risk={risk_level}")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating.

    Generates a context-aware clarification question. If a risky action
    was rejected, asks for a safer alternative.
    """
    approval = state.get("approval") or {}
    if approval and not approval.get("approved", True):
        question = "The risky request was rejected. Please provide a safer alternative action."
    else:
        query = state.get("query", "")
        question = (
            f"Your request \"{query[:60]}\" lacks specific details. "
            "Can you provide the order ID, account reference, or additional context?"
        )
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "missing information requested")],
    }


def tool_node(state: AgentState) -> dict:
    """Call a mock tool with idempotency support.

    Simulates transient failures for error-route scenarios to demonstrate retry loops.
    Uses ``max_attempts`` from state (populated from the scenario) to decide how many
    times to return a simulated error before succeeding.
    """
    attempt = int(state.get("attempt", 0))
    max_attempts = int(state.get("max_attempts", 3))
    scenario_id = state.get("scenario_id", "unknown")

    # Idempotency key — deterministic per scenario + attempt
    idempotency_key = hashlib.sha256(f"{scenario_id}:{attempt}".encode()).hexdigest()[:12]

    if state.get("route") == Route.ERROR.value and attempt < max_attempts:
        result = (
            f"ERROR: transient failure attempt={attempt} "
            f"scenario={scenario_id} idempotency_key={idempotency_key}"
        )
    else:
        result = (
            f"mock-tool-result for scenario={scenario_id} "
            f"idempotency_key={idempotency_key}"
        )
    return {
        "tool_results": [result],
        "events": [
            make_event(
                "tool",
                "completed",
                f"tool executed attempt={attempt}",
                idempotency_key=idempotency_key,
            )
        ],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for approval.

    Extracts evidence from the query and tags the risk level so the
    approval node and human reviewer have full context.
    """
    query = state.get("query", "")
    risk_level = state.get("risk_level", "high")
    return {
        "proposed_action": f"Execute risky operation: \"{query[:100]}\". Risk level: {risk_level}. Approval required.",
        "events": [
            make_event(
                "risky_action",
                "pending_approval",
                f"approval required, risk_level={risk_level}",
            )
        ],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step with optional LangGraph interrupt().

    Set LANGGRAPH_INTERRUPT=true to use real interrupt() for HITL demos.
    Default uses mock decision so tests and CI run offline.
    Supports approve, reject, and edit decision outcomes.
    """
    import os

    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        value = interrupt(
            {
                "proposed_action": state.get("proposed_action"),
                "risk_level": state.get("risk_level"),
            }
        )
        if isinstance(value, dict):
            action = str(value.get("action", "")).lower()
            if action in {"approve", "approved", "continue"}:
                decision = ApprovalDecision(
                    approved=True,
                    reviewer=str(value.get("reviewer", "human-reviewer")),
                    comment=str(value.get("comment", "approved by human reviewer")),
                )
            elif action in {"reject", "rejected", "deny"}:
                decision = ApprovalDecision(
                    approved=False,
                    reviewer=str(value.get("reviewer", "human-reviewer")),
                    comment=str(value.get("comment", "rejected by human reviewer")),
                )
            else:
                decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval for lab")
    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt or fallback decision.

    Implements bounded retry with exponential-backoff metadata.
    If ``attempt >= max_attempts``, the routing function sends to dead_letter.
    """
    attempt = int(state.get("attempt", 0)) + 1
    max_attempts = int(state.get("max_attempts", 3))
    backoff_ms = min(1000 * (2 ** (attempt - 1)), 30_000)  # exponential cap at 30s
    errors = [f"transient failure attempt={attempt}/{max_attempts}"]
    return {
        "attempt": attempt,
        "errors": errors,
        "events": [
            make_event(
                "retry",
                "completed",
                f"retry attempt {attempt}/{max_attempts}, backoff={backoff_ms}ms",
                attempt=attempt,
                max_attempts=max_attempts,
                backoff_ms=backoff_ms,
            )
        ],
    }


def answer_node(state: AgentState) -> dict:
    """Produce a final response grounded in tool results and approval context."""
    parts: list[str] = []

    # Ground in tool results
    tool_results = state.get("tool_results", [])
    if tool_results:
        latest = tool_results[-1]
        parts.append(f"Based on tool execution: {latest}")

    # Ground in approval context
    approval = state.get("approval")
    if approval:
        if approval.get("approved"):
            parts.append(f"Action approved by {approval.get('reviewer', 'reviewer')}.")
        else:
            parts.append(f"Action was rejected: {approval.get('comment', 'no comment')}.")

    if not parts:
        route = state.get("route", "simple")
        query = state.get("query", "")
        parts.append(f"Processed '{route}' request: \"{query[:80]}\"")

    answer = " ".join(parts)
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated from grounded context")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the 'done?' check that enables retry loops.

    Checks the latest tool result for error indicators. This is the key
    advantage of LangGraph over LCEL — conditional loops with state.
    """
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    if "ERROR" in latest:
        return {
            "evaluation_result": "needs_retry",
            "events": [
                make_event(
                    "evaluate",
                    "completed",
                    f"tool result indicates failure, retry needed. result={latest[:100]}",
                )
            ],
        }
    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "completed", "tool result satisfactory")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Log unresolvable failures for manual review.

    Third layer of error strategy: retry → fallback → dead letter.
    Records severity, attempt count, and error history for the ops team.
    """
    attempt = state.get("attempt", 0)
    max_attempts = state.get("max_attempts", 3)
    errors = state.get("errors", [])
    scenario_id = state.get("scenario_id", "unknown")

    return {
        "final_answer": (
            f"Request could not be completed after {attempt}/{max_attempts} retry attempts. "
            f"Scenario '{scenario_id}' logged for manual review."
        ),
        "events": [
            make_event(
                "dead_letter",
                "completed",
                f"max retries exceeded, attempt={attempt}/{max_attempts}",
                severity="critical",
                scenario_id=scenario_id,
                error_count=len(errors),
            )
        ],
    }


def finalize_node(state: AgentState) -> dict:
    """Finalize the run and emit a final audit event with execution summary."""
    route = state.get("route", "unknown")
    attempt = state.get("attempt", 0)
    has_answer = bool(state.get("final_answer") or state.get("pending_question"))
    return {
        "events": [
            make_event(
                "finalize",
                "completed",
                f"workflow finished: route={route}, attempts={attempt}, resolved={has_answer}",
            )
        ],
    }

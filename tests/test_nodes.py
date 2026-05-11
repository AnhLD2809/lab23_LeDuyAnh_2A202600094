"""Unit tests for individual node functions."""

from langgraph_agent_lab.nodes import (
    _mask_pii,
    answer_node,
    dead_letter_node,
    evaluate_node,
    intake_node,
    retry_or_fallback_node,
    risky_action_node,
    tool_node,
)
from langgraph_agent_lab.state import Route


# ---------------------------------------------------------------------------
# PII masking
# ---------------------------------------------------------------------------


def test_mask_pii_email():
    assert "[EMAIL]" in _mask_pii("Contact me at john@example.com please")


def test_mask_pii_phone():
    assert "[PHONE]" in _mask_pii("Call me at 555-123-4567")


def test_mask_pii_ssn():
    assert "[SSN]" in _mask_pii("My SSN is 123-45-6789")


def test_mask_pii_card():
    assert "[CARD]" in _mask_pii("Card number 4111-1111-1111-1111")


def test_mask_pii_no_pii():
    text = "Hello world, nothing sensitive here"
    assert _mask_pii(text) == text


# ---------------------------------------------------------------------------
# intake_node
# ---------------------------------------------------------------------------


def test_intake_normalizes_whitespace():
    result = intake_node({"query": "  hello world  "})
    assert result["query"] == "hello world"


def test_intake_masks_pii():
    result = intake_node({"query": "Email me at test@example.com"})
    assert "[EMAIL]" in result["query"]


# ---------------------------------------------------------------------------
# tool_node
# ---------------------------------------------------------------------------


def test_tool_node_error_route_fails():
    """Error-route should produce ERROR result when attempt < max_attempts."""
    state = {"route": Route.ERROR.value, "attempt": 0, "max_attempts": 3, "scenario_id": "T1"}
    result = tool_node(state)
    assert "ERROR" in result["tool_results"][0]


def test_tool_node_error_route_succeeds_after_max():
    """Error-route should succeed once attempt >= max_attempts."""
    state = {"route": Route.ERROR.value, "attempt": 3, "max_attempts": 3, "scenario_id": "T1"}
    result = tool_node(state)
    assert "ERROR" not in result["tool_results"][0]
    assert "mock-tool-result" in result["tool_results"][0]


def test_tool_node_idempotency_key():
    """Tool results should include an idempotency key."""
    state = {"route": Route.TOOL.value, "attempt": 0, "max_attempts": 3, "scenario_id": "T1"}
    result = tool_node(state)
    assert "idempotency_key" in result["tool_results"][0]


def test_tool_node_non_error_route():
    state = {"route": Route.TOOL.value, "attempt": 0, "max_attempts": 3, "scenario_id": "T2"}
    result = tool_node(state)
    assert "mock-tool-result" in result["tool_results"][0]


# ---------------------------------------------------------------------------
# evaluate_node
# ---------------------------------------------------------------------------


def test_evaluate_success():
    state = {"tool_results": ["mock-tool-result for scenario=T1"]}
    result = evaluate_node(state)
    assert result["evaluation_result"] == "success"


def test_evaluate_needs_retry():
    state = {"tool_results": ["ERROR: transient failure"]}
    result = evaluate_node(state)
    assert result["evaluation_result"] == "needs_retry"


def test_evaluate_empty_results():
    result = evaluate_node({"tool_results": []})
    assert result["evaluation_result"] == "success"


# ---------------------------------------------------------------------------
# retry_or_fallback_node
# ---------------------------------------------------------------------------


def test_retry_increments_attempt():
    result = retry_or_fallback_node({"attempt": 0, "max_attempts": 3})
    assert result["attempt"] == 1


def test_retry_backoff_metadata():
    result = retry_or_fallback_node({"attempt": 2, "max_attempts": 3})
    event = result["events"][0]
    assert "backoff" in event["message"]


# ---------------------------------------------------------------------------
# answer_node
# ---------------------------------------------------------------------------


def test_answer_grounds_in_tool_results():
    state = {"tool_results": ["mock-tool-result for scenario=T1"]}
    result = answer_node(state)
    assert "mock-tool-result" in result["final_answer"]


def test_answer_grounds_in_approval():
    state = {"approval": {"approved": True, "reviewer": "test-reviewer"}}
    result = answer_node(state)
    assert "test-reviewer" in result["final_answer"]


def test_answer_default():
    result = answer_node({})
    assert result["final_answer"]


# ---------------------------------------------------------------------------
# risky_action_node
# ---------------------------------------------------------------------------


def test_risky_action_includes_query():
    result = risky_action_node({"query": "Refund customer", "risk_level": "high"})
    assert "Refund customer" in result["proposed_action"]
    assert "high" in result["proposed_action"]


# ---------------------------------------------------------------------------
# dead_letter_node
# ---------------------------------------------------------------------------


def test_dead_letter_includes_scenario_info():
    state = {"attempt": 3, "max_attempts": 3, "scenario_id": "DL1", "errors": ["e1", "e2"]}
    result = dead_letter_node(state)
    assert "DL1" in result["final_answer"]
    assert "3/3" in result["final_answer"]
    event = result["events"][0]
    assert event["metadata"]["severity"] == "critical"

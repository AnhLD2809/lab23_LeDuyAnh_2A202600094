"""Metrics tests — including latency and edge cases."""

from langgraph_agent_lab.metrics import metric_from_state, summarize_metrics
from langgraph_agent_lab.state import make_event


def test_metric_from_state_success():
    state = {
        "scenario_id": "S",
        "route": "simple",
        "final_answer": "ok",
        "events": [make_event("intake", "completed", "ok"), make_event("answer", "completed", "ok")],
        "errors": [],
    }
    metric = metric_from_state(state, expected_route="simple", approval_required=False)
    assert metric.success is True
    assert metric.nodes_visited == 2


def test_metric_from_state_with_latency():
    """Latency should be propagated from the caller."""
    state = {
        "scenario_id": "S",
        "route": "simple",
        "final_answer": "ok",
        "events": [],
        "errors": [],
    }
    metric = metric_from_state(state, expected_route="simple", approval_required=False, latency_ms=42)
    assert metric.latency_ms == 42


def test_metric_from_state_failure_route_mismatch():
    """When actual route doesn't match expected, success should be False."""
    state = {
        "scenario_id": "S",
        "route": "tool",
        "final_answer": "ok",
        "events": [],
        "errors": [],
    }
    metric = metric_from_state(state, expected_route="simple", approval_required=False)
    assert metric.success is False


def test_metric_from_state_approval_required_but_missing():
    """When approval is required but not observed, success should be False."""
    state = {
        "scenario_id": "S",
        "route": "risky",
        "final_answer": "ok",
        "events": [],
        "errors": [],
        "approval": None,
    }
    metric = metric_from_state(state, expected_route="risky", approval_required=True)
    assert metric.success is False
    assert metric.approval_observed is False


def test_metric_counts_retries_and_interrupts():
    state = {
        "scenario_id": "S",
        "route": "error",
        "final_answer": "ok",
        "events": [
            make_event("retry", "completed", "r1"),
            make_event("retry", "completed", "r2"),
            make_event("approval", "completed", "a1"),
        ],
        "errors": [],
    }
    metric = metric_from_state(state, expected_route="error", approval_required=False)
    assert metric.retry_count == 2
    assert metric.interrupt_count == 1


def test_summarize_metrics():
    m1 = metric_from_state(
        {"scenario_id": "1", "route": "simple", "final_answer": "ok", "events": [], "errors": []},
        "simple",
        False,
        latency_ms=10,
    )
    m2 = metric_from_state(
        {"scenario_id": "2", "route": "tool", "final_answer": None, "events": [], "errors": []},
        "tool",
        False,
        latency_ms=20,
    )
    report = summarize_metrics([m1, m2], resume_success=True)
    assert report.total_scenarios == 2
    assert 0 <= report.success_rate <= 1
    assert report.resume_success is True


def test_summarize_metrics_empty_raises():
    """Summarizing zero metrics should raise ValueError."""
    import pytest

    with pytest.raises(ValueError, match="No scenario metrics"):
        summarize_metrics([])

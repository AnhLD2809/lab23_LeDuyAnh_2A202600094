"""Report rendering tests."""

from langgraph_agent_lab.metrics import metric_from_state, summarize_metrics
from langgraph_agent_lab.report import render_report


def test_render_report_contains_required_sections():
    item = metric_from_state(
        {
            "scenario_id": "S01",
            "route": "simple",
            "final_answer": "ok",
            "events": [],
            "errors": [],
        },
        expected_route="simple",
        approval_required=False,
    )
    report = summarize_metrics([item], resume_success=True)
    text = render_report(report)
    assert "## 2. Kiến trúc hệ thống" in text
    assert "## 4. Kết quả chạy kịch bản" in text
    assert "S01" in text
    assert "thành công" in text  # resume_success note


def test_render_report_failure_analysis():
    """When a scenario fails, the failure analysis should mention it."""
    item = metric_from_state(
        {
            "scenario_id": "FAIL01",
            "route": "tool",
            "final_answer": "ok",
            "events": [],
            "errors": [],
        },
        expected_route="simple",  # mismatch → failure
        approval_required=False,
    )
    report = summarize_metrics([item], resume_success=False)
    text = render_report(report)
    assert "FAIL01" in text
    assert "failed" in text.lower() or "❌" in text


def test_render_report_latency_column():
    """Report should include the latency column."""
    item = metric_from_state(
        {
            "scenario_id": "S01",
            "route": "simple",
            "final_answer": "ok",
            "events": [],
            "errors": [],
        },
        expected_route="simple",
        approval_required=False,
        latency_ms=123,
    )
    report = summarize_metrics([item])
    text = render_report(report)
    assert "Latency" in text
    assert "123" in text

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
    assert "## 2. Architecture" in text
    assert "## 4. Scenario results" in text
    assert "S01" in text
    assert "Resume probe succeeded" in text

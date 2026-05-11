"""Report generation helper."""

from __future__ import annotations

from pathlib import Path

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    """Render a submission-ready lab report from collected metrics."""
    scenario_rows = "\n".join(
        f"| {item.scenario_id} | {item.expected_route} | {item.actual_route} | "
        f"{'yes' if item.success else 'no'} | {item.retry_count} | {item.interrupt_count} |"
        for item in metrics.scenario_metrics
    )
    failure_count = sum(1 for item in metrics.scenario_metrics if not item.success)
    dead_letter_cases = [
        item.scenario_id
        for item in metrics.scenario_metrics
        if any("dead_letter" in err.lower() for err in item.errors)
    ]

    failure_analysis = [
        "- All sample scenarios succeeded.",
        f"- Retry behavior observed with total retries = {metrics.total_retries}.",
        f"- Interrupt/HITL path observed with total interrupts = {metrics.total_interrupts}.",
    ]
    if failure_count > 0:
        failure_analysis = [
            f"- {failure_count} scenario(s) failed in the last run.",
            f"- Dead-letter observed in: {', '.join(dead_letter_cases) if dead_letter_cases else 'none'}.",
            "- Review `outputs/metrics.json` error arrays for root-cause analysis.",
        ]

    persistence_note = (
        "Resume probe succeeded (interrupt -> Command(resume=...) -> completion)."
        if metrics.resume_success
        else "Resume probe was not executed or did not succeed in this run."
    )

    lines = [
        "# Day 08 Lab Report",
        "",
        "## 1. Team / student",
        "",
        "- Name: (fill your name)",
        "- Repo/commit: (fill commit hash before submission)",
        "- Date: (fill submission date)",
        "",
        "## 2. Architecture",
        "",
        "- `intake` normalizes query and appends audit event.",
        "- `classify` routes by keyword policy with priority: risky -> tool -> missing_info -> error -> simple.",
        "- `tool -> evaluate -> retry` forms a bounded retry loop using `attempt < max_attempts`.",
        "- Risky path enforces `risky_action -> approval` before tool execution.",
        "- All terminal branches pass through `finalize`.",
        "",
        "## 3. State schema",
        "",
        "| Field | Reducer | Why |",
        "|---|---|---|",
        "| `route`, `risk_level`, `attempt`, `approval`, `evaluation_result` | overwrite | latest decision/state snapshot |",
        "| `messages`, `tool_results`, `errors`, `events` | append | auditability, debugging, grading evidence |",
        "",
        "## 4. Scenario results",
        "",
        f"- Total scenarios: {metrics.total_scenarios}",
        f"- Success rate: {metrics.success_rate:.2%}",
        f"- Average nodes visited: {metrics.avg_nodes_visited:.2f}",
        f"- Total retries: {metrics.total_retries}",
        f"- Total interrupts: {metrics.total_interrupts}",
        "",
        "| Scenario | Expected route | Actual route | Success | Retries | Interrupts |",
        "|---|---|---|---:|---:|---:|",
        scenario_rows,
        "",
        "## 5. Failure analysis",
        "",
        *failure_analysis,
        "",
        "## 6. Persistence / recovery evidence",
        "",
        "- Checkpointer was wired through graph compile path.",
        "- Each run uses a deterministic `thread_id` per scenario.",
        f"- {persistence_note}",
        "",
        "## 7. Extension work",
        "",
        "- Real HITL support via `LANGGRAPH_INTERRUPT=true` + `interrupt()` in approval node.",
        "- Streamlit UI for approve/reject and resume with `Command(resume=...)`.",
        "- SQLite checkpointer path prepared with WAL mode for crash-recovery demos.",
        "",
        "## 8. Improvement plan",
        "",
        "1. Replace heuristic evaluation with structured validator or LLM-as-judge policy.",
        "2. Add real tool adapters (ticket DB/API) with idempotency keys.",
        "3. Add alerting/dead-letter sink (queue or ticketing integration).",
        "4. Add regression suite for hidden-scenario style paraphrases.",
    ]
    return "\n".join(lines) + "\n"


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")

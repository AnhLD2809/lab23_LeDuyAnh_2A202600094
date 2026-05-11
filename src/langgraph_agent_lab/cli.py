"""CLI for the lab."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

import typer
import yaml

from .graph import build_graph
from .metrics import MetricsReport, metric_from_state, summarize_metrics, write_metrics
from .persistence import build_checkpointer
from .report import write_report
from .scenarios import load_scenarios
from .state import Route, Scenario, initial_state

app = typer.Typer(no_args_is_help=True)


def _probe_resume_success(graph, scenarios: list[Scenario]) -> bool:
    """Run a minimal HITL interrupt/resume probe to evidence persistence + recovery."""
    if getattr(graph, "checkpointer", None) in (None, False):
        return False
    risky = next((item for item in scenarios if item.requires_approval), None)
    if risky is None:
        risky = Scenario(
            id="RESUME_PROBE",
            query="Refund this customer account and send confirmation",
            expected_route=Route.RISKY,
            requires_approval=True,
        )

    previous_interrupt = os.getenv("LANGGRAPH_INTERRUPT")
    os.environ["LANGGRAPH_INTERRUPT"] = "true"
    try:
        from langgraph.types import Command

        state = initial_state(risky)
        state["thread_id"] = f"{state['thread_id']}-resume-probe"
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        interrupted_state = graph.invoke(state, config=run_config)
        if "__interrupt__" not in interrupted_state:
            return False
        resumed_state = graph.invoke(
            Command(
                resume={
                    "action": "approve",
                    "approved": True,
                    "reviewer": "resume-probe",
                    "comment": "automated resume probe",
                }
            ),
            config=run_config,
        )
        approval = resumed_state.get("approval") or {}
        return bool(approval.get("approved") and resumed_state.get("final_answer"))
    except Exception:
        return False
    finally:
        if previous_interrupt is None:
            os.environ.pop("LANGGRAPH_INTERRUPT", None)
        else:
            os.environ["LANGGRAPH_INTERRUPT"] = previous_interrupt


@app.command("run-scenarios")
def run_scenarios(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run all grading scenarios and write metrics JSON."""
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    scenarios = load_scenarios(cfg["scenarios_path"])
    checkpointer = build_checkpointer(cfg.get("checkpointer", "memory"), cfg.get("database_url"))
    graph = build_graph(checkpointer=checkpointer)
    metrics = []
    for scenario in scenarios:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        final_state = graph.invoke(state, config=run_config)
        metrics.append(metric_from_state(final_state, scenario.expected_route.value, scenario.requires_approval))
    resume_success = _probe_resume_success(graph, scenarios)
    report = summarize_metrics(metrics, resume_success=resume_success)
    write_metrics(report, output)
    if cfg.get("report_path"):
        write_report(report, cfg["report_path"])
    typer.echo(f"Wrote metrics to {output}")


@app.command("validate-metrics")
def validate_metrics(metrics: Annotated[Path, typer.Option("--metrics")]) -> None:
    """Validate metrics JSON schema for grading."""
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    report = MetricsReport.model_validate(payload)
    if report.total_scenarios < 6:
        raise typer.BadParameter("Expected at least 6 scenarios")
    typer.echo(f"Metrics valid. success_rate={report.success_rate:.2%}")


@app.command("export-graph")
def export_graph(
    output: Annotated[Path, typer.Option("--output")] = Path("outputs/graph.mmd"),
) -> None:
    """Export graph diagram as Mermaid text for report/demo evidence."""
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    mermaid = graph.get_graph().draw_mermaid()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(mermaid, encoding="utf-8")
    typer.echo(f"Wrote Mermaid graph to {output}")


if __name__ == "__main__":
    app()

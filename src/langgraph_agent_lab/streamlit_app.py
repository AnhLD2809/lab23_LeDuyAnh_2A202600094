"""Streamlit UI for running the Day 08 LangGraph lab with HITL approval."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import streamlit as st

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import Route, Scenario, initial_state


def _build_graph(checkpointer_kind: str, sqlite_path: str) -> Any:
    if checkpointer_kind == "sqlite":
        checkpointer = build_checkpointer("sqlite", sqlite_path)
    else:
        checkpointer = build_checkpointer("memory")
    return build_graph(checkpointer=checkpointer)


@st.cache_resource(show_spinner=False)
def _cached_graph(checkpointer_kind: str, sqlite_path: str) -> Any:
    """Cache graph + checkpointer to support HITL resume across reruns."""
    return _build_graph(checkpointer_kind, sqlite_path)


def _thread_config(thread_id: str) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": thread_id}}


def _scenario_from_query(query: str, thread_id: str) -> dict[str, Any]:
    scenario = Scenario(
        id=f"ui-{thread_id}",
        query=query.strip(),
        expected_route=Route.SIMPLE,
    )
    state = initial_state(scenario)
    state["thread_id"] = thread_id
    return state


def _read_interrupt_payload(result: dict[str, Any]) -> dict[str, Any] | None:
    interrupt_data = result.get("__interrupt__")
    if not interrupt_data:
        return None
    first_interrupt = interrupt_data[0]
    return getattr(first_interrupt, "value", {"message": "approval required"})


def _render_state(result: dict[str, Any]) -> None:
    st.subheader("Execution Summary")
    st.write(
        {
            "route": result.get("route"),
            "risk_level": result.get("risk_level"),
            "attempt": result.get("attempt", 0),
            "final_answer": result.get("final_answer"),
            "pending_question": result.get("pending_question"),
            "approval": result.get("approval"),
        }
    )
    events = result.get("events", [])
    if events:
        st.subheader("Events")
        st.dataframe(events, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="LangGraph Agent Lab HITL", page_icon="lab", layout="wide")
    st.title("Day 08 Lab - Streamlit UI with HITL")
    st.caption("Risky actions pause for human approval via LangGraph interrupt/resume.")

    with st.sidebar:
        st.header("Runtime")
        checkpointer_kind = st.selectbox("Checkpointer", ["memory", "sqlite"], index=0)
        sqlite_path = st.text_input("SQLite path", value="checkpoints.db")
        use_hitl = st.toggle("Enable real HITL interrupt", value=True)
        default_thread = f"ui-thread-{time.strftime('%Y%m%d')}"
        thread_id = st.text_input("Thread ID", value=st.session_state.get("thread_id", default_thread))
        if st.button("New thread"):
            thread_id = f"ui-thread-{uuid.uuid4().hex[:8]}"
            st.session_state["thread_id"] = thread_id
            st.session_state["result"] = None
            st.session_state["pending_interrupt"] = None
            st.rerun()

    st.session_state["thread_id"] = thread_id
    os.environ["LANGGRAPH_INTERRUPT"] = "true" if use_hitl else "false"

    graph = _cached_graph(checkpointer_kind, sqlite_path)
    config = _thread_config(thread_id)

    query = st.text_area(
        "User query",
        value="Refund this customer and send confirmation email",
        height=120,
    )

    col_run, col_resume = st.columns([1, 1])
    with col_run:
        run_clicked = st.button("Run query", use_container_width=True)
    with col_resume:
        resume_clicked = st.button("Continue existing thread", use_container_width=True)

    if run_clicked:
        if not query.strip():
            st.error("Query is required.")
        else:
            initial = _scenario_from_query(query, thread_id)
            result = graph.invoke(initial, config=config)
            st.session_state["result"] = result
            st.session_state["pending_interrupt"] = _read_interrupt_payload(result)

    if resume_clicked:
        try:
            snapshot = graph.get_state(config)
            next_nodes = snapshot.next or ()
            st.info(f"Next node(s): {', '.join(next_nodes) if next_nodes else 'none (thread completed or not found)'}")
            st.session_state["result"] = snapshot.values or {}

            # Read interrupt payload from snapshot.tasks (not from values)
            interrupt_payload = None
            if next_nodes and hasattr(snapshot, "tasks"):
                for task in snapshot.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        first = task.interrupts[0]
                        interrupt_payload = getattr(first, "value", {"message": "approval required"})
                        break
            st.session_state["pending_interrupt"] = interrupt_payload
        except Exception as exc:  # pragma: no cover - UI runtime path
            st.error(f"Could not load thread state: {exc}")

    pending_interrupt = st.session_state.get("pending_interrupt")
    if pending_interrupt:
        st.warning("Human approval required before executing risky action.")
        st.json(pending_interrupt)
        decision = st.radio("Decision", options=["approve", "reject"], horizontal=True)
        reviewer = st.text_input("Reviewer", value="streamlit-reviewer")
        comment = st.text_input("Comment", value="Reviewed in Streamlit HITL panel")
        if st.button("Submit approval decision"):
            from langgraph.types import Command

            resume_payload = {
                "action": decision,
                "approved": decision == "approve",
                "reviewer": reviewer,
                "comment": comment,
            }
            result = graph.invoke(Command(resume=resume_payload), config=config)
            st.session_state["result"] = result
            st.session_state["pending_interrupt"] = _read_interrupt_payload(result)
            st.success("Decision submitted.")

    if st.session_state.get("result"):
        _render_state(st.session_state["result"])


if __name__ == "__main__":
    main()

"""Checkpoint-backed persistence for the Streamlit workflow."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from utils.memory import get_checkpointer
from utils.state import ResearchState
from utils.session_runtime import SessionGraph


_UI_PHASE_KEY = "ui_phase"


def _persist_node(state: ResearchState) -> ResearchState:
    return state


def build_web_checkpoint_graph(checkpointer=None):
    """Build the small graph used to checkpoint Streamlit's UI-managed state."""
    if checkpointer is None:
        checkpointer = get_checkpointer()

    workflow = StateGraph(ResearchState)
    workflow.add_node("persist", _persist_node)
    workflow.set_entry_point("persist")
    workflow.add_edge("persist", END)
    return SessionGraph(workflow.compile(checkpointer=checkpointer))


def _config(session_id: str) -> dict[str, dict[str, str]]:
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("A non-empty session ID is required.")
    return {"configurable": {"thread_id": sid}}


def save_web_state(graph, session_id: str, state: dict[str, Any], ui_phase: str) -> None:
    """Persist the current UI state and the page phase in one checkpoint."""
    payload = dict(state or {})
    payload["session_id"] = session_id
    payload["workflow"] = "streamlit"
    payload[_UI_PHASE_KEY] = ui_phase
    # The Streamlit workflow does not use the CLI conversation transcript.
    # Avoid replaying its add_messages reducer on every UI rerun.
    payload.pop("messages", None)
    graph.invoke(payload, _config(session_id))


def load_web_state(graph, session_id: str) -> tuple[dict[str, Any], str]:
    """Load a saved state and return ``(state, ui_phase)``."""
    snapshot = graph.get_state(_config(session_id))
    values = dict(getattr(snapshot, "values", None) or {})
    if not values or _UI_PHASE_KEY not in values:
        raise ValueError(
            f"Session {session_id!r} was not found as a Streamlit UI session."
        )
    ui_phase = str(values.pop(_UI_PHASE_KEY, "input") or "input")
    return values, ui_phase

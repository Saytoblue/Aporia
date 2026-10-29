# Author: Saytoblue <Saytoblue@gmail.com>
# Copyright (c) 2026-05-06 Saytoblue


"""
Aporia — LangGraph Orchestrator
Scope: Phase 0–2 (from friction points to core algorithm code).

Phase 0  elicit          Socratic elicitation -> researcher profile
Phase 1  idea_discovery  assumption mining -> 3 candidate directions
Phase 2  idea_refine     select + refine direction
         assumption_breaking / problem_reframing
         story_arc / necessity_check / proposal
         generate_core_code  (core deliverable for an AI coding assistant)
"""

from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Literal

from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig

from utils.state import ResearchState
from utils.memory import get_checkpointer
from utils.operations import task_attempt
from utils.session_runtime import SessionGraph, migration_patch
from agents.dialogue_agent import elicit_node
from agents.idea_agent import idea_node, idea_refine_node, paper_expand_node
from agents.refine_agent import (
    assumption_breaking_node,
    problem_reframing_node,
    story_arc_node,
    necessity_check_node,
    proposal_node,
    proposal_revision_node,
)
from agents.method_agent import generate_core_code_node


def _pass(state):
    return state


def _tracked_node(name, fn):
    """Track task retries separately from legitimate dialogue/revision loops."""
    def run(state, config: RunnableConfig):
        previous = dict(state.get("node_runs") or {})
        count = int(previous.get(name, 0) or 0) + 1
        previous[name] = count
        with task_attempt(name, config) as attempt:
            result = fn(state)
        updated = {**migration_patch(state), **dict(result or state)}
        replayed = list(updated.get("replayed_nodes") or [])
        if attempt > 1 and name not in replayed:
            replayed.append(name)
        updated["node_runs"] = previous
        updated["last_node"] = name
        updated["last_node_status"] = "replayed" if attempt > 1 else "completed"
        updated["last_node_attempt"] = attempt
        updated["replayed_nodes"] = replayed
        updated["last_node_at"] = datetime.now(timezone.utc).isoformat()
        return updated
    return run

human_elicit_continue  = _pass
human_direction_select = _pass
human_proposal_review  = _pass


def route_elicit(state: ResearchState) -> str:
    if state.get("friction_points") and state.get("dialogue_turns", 0) >= 2:
        return "idea_discovery"
    return "human_elicit_continue"


def route_after_idea(state: ResearchState) -> str:
    if state.get("candidate_directions") and not state.get("selected_direction"):
        return "human_direction_select"
    return "idea_refine"


def route_after_proposal(state: ResearchState) -> str:
    approved = str(state.get("human_feedback", "") or "").strip().lower() in (
        "approved", "yes", "ok"
    )
    if state.get("research_proposal") and not approved:
        return "human_proposal_review"
    return "generate_core_code"


def route_after_proposal_review(state: ResearchState) -> str:
    """Approved proposals continue; requested changes return to revision."""
    approved = str(state.get("human_feedback", "") or "").strip().lower() in (
        "approved", "yes", "ok"
    )
    return "paper_expand_post_proposal" if approved else "proposal_revision"


def build_graph(checkpointer=None):
    if checkpointer is None:
        checkpointer = get_checkpointer()

    g = StateGraph(ResearchState)

    g.add_node("elicit",                 _tracked_node("elicit", elicit_node))
    g.add_node("human_elicit_continue",  _tracked_node("human_elicit_continue", human_elicit_continue))
    g.add_node("idea_discovery",         _tracked_node("idea_discovery", idea_node))
    g.add_node("human_direction_select", _tracked_node("human_direction_select", human_direction_select))
    g.add_node("paper_expand",           _tracked_node("paper_expand", paper_expand_node))
    g.add_node("paper_expand_post_proposal", _tracked_node("paper_expand_post_proposal", paper_expand_node))
    g.add_node("idea_refine",            _tracked_node("idea_refine", idea_refine_node))
    g.add_node("assumption_breaking",    _tracked_node("assumption_breaking", assumption_breaking_node))
    g.add_node("problem_reframing",      _tracked_node("problem_reframing", problem_reframing_node))
    g.add_node("story_arc",              _tracked_node("story_arc", story_arc_node))
    g.add_node("necessity_check",        _tracked_node("necessity_check", necessity_check_node))
    g.add_node("proposal",               _tracked_node("proposal", proposal_node))
    g.add_node("proposal_revision",      _tracked_node("proposal_revision", proposal_revision_node))
    g.add_node("human_proposal_review",  _tracked_node("human_proposal_review", human_proposal_review))
    g.add_node("generate_core_code",     _tracked_node("generate_core_code", generate_core_code_node))

    g.set_entry_point("elicit")
    g.add_conditional_edges("elicit", route_elicit)
    g.add_edge("human_elicit_continue",  "elicit")

    g.add_conditional_edges("idea_discovery", route_after_idea)
    g.add_edge("human_direction_select", "paper_expand")
    g.add_edge("paper_expand",           "idea_refine")

    g.add_edge("idea_refine",         "assumption_breaking")
    g.add_edge("assumption_breaking", "problem_reframing")
    g.add_edge("problem_reframing",   "story_arc")
    g.add_edge("story_arc",           "necessity_check")
    g.add_edge("necessity_check",     "proposal")

    g.add_conditional_edges("proposal", route_after_proposal)
    g.add_conditional_edges("human_proposal_review", route_after_proposal_review)
    g.add_edge("proposal_revision", "human_proposal_review")
    g.add_edge("paper_expand_post_proposal", "generate_core_code")
    g.add_edge("generate_core_code",    END)

    return SessionGraph(g.compile(
        checkpointer=checkpointer,
        interrupt_before=[
            "human_elicit_continue",
            "human_direction_select",
            "human_proposal_review",
        ],
    ))


def start_dialogue(
    topic: str,
    session_id: str | None = None,
    user_language: str | None = None,
    initial_feedback: str | None = None,
):
    """
    Start a session and return (graph, config, first_question).
    """
    graph = build_graph()
    sid = session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": sid}}

    initial: ResearchState = {
        "topic": topic,
        "phase": "eliciting",
        "dialogue_turns": 1 if initial_feedback else 0,
        "session_id": sid,
        "workflow": "orchestrator",
        "checkpoints": [],
        "metadata": {},
        "user_language": user_language or "Auto",
        "user_insight": initial_feedback or "",
        "ui_phase": "graph_running",
    }
    if initial_feedback:
        initial["human_feedback"] = initial_feedback
        initial["messages"] = [{"role": "user", "content": initial_feedback}]

    first_msg = ""
    with graph.session(config, expected_checkpoint=None):
        for event in graph.stream(initial, config, stream_mode="values"):
            for m in reversed(event.get("messages", [])):
                if isinstance(m, dict) and m.get("role") == "assistant":
                    first_msg = m.get("content", "")
                    break
                if getattr(m, "type", "") == "ai":
                    first_msg = getattr(m, "content", "") or ""
                    break

    return graph, config, first_msg


def resume_session(session_id: str):
    """Return a graph/config pair for an existing persisted session."""
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("A non-empty session ID is required.")
    graph = build_graph()
    config = {"configurable": {"thread_id": sid}}
    try:
        snapshot = graph.get_state(config)
    except Exception as exc:
        raise RuntimeError(f"Unable to load session {sid!r}.") from exc
    values = getattr(snapshot, "values", None) or {}
    if not values:
        raise ValueError(f"Session {sid!r} was not found in the checkpoint store.")
    return graph, config

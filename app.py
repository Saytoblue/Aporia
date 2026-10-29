# Author: Saytoblue <Saytoblue@gmail.com>
# Copyright (c) 2026-05-06 Saytoblue


"""
Aporia — Streamlit Web UI
Run: streamlit run app.py
"""

import streamlit as st
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(__file__))

try:
    from dotenv import load_dotenv

    if os.path.exists(os.path.join(os.path.dirname(__file__), ".env")):
        load_dotenv(os.path.join(os.path.dirname(__file__), ".env"), override=True)
    elif os.path.exists(".env"):
        load_dotenv(".env", override=True)
except Exception:
    pass

_page_icon_path = os.path.join(os.path.dirname(__file__), "assets", "avatar_geo.png")
_page_icon = "A"
if os.path.exists(_page_icon_path):
    try:
        from PIL import Image

        _page_icon = Image.open(_page_icon_path)
    except Exception:
        _page_icon = _page_icon_path


def _is_ascii(s: str) -> bool:
    try:
        s.encode("ascii")
        return True
    except Exception:
        return False


def _topic_to_search_queries(topic: str) -> list[str]:
    t = (topic or "").strip()
    if not t:
        return []
    if _is_ascii(t):
        return [t]
    try:
        import json, re
        from langchain_core.messages import HumanMessage, SystemMessage
        from utils.llm_client import get_llm

        llm = get_llm(temperature=0.2)
        resp = llm.invoke([
            SystemMessage(content=(
                "Rewrite the user's research topic into 2 concise English academic search queries.\n"
                "Rules:\n"
                "- Preserve the exact task and scope. Do not add new tasks.\n"
                "- Use common English terminology and abbreviations.\n"
                "Output a strict JSON array of strings only."
            )),
            HumanMessage(content=t),
        ])
        m = re.search(r"\[.*\]", resp.content, re.DOTALL)
        if m:
            arr = json.loads(m.group())
            out = []
            for x in arr:
                s = str(x or "").strip()
                if s and s not in out:
                    out.append(s)
            if out:
                return out[:2]
    except Exception:
        pass
    return [t]


def _build_profile_from_topic_and_insight(topic: str, insight: str) -> dict:
    t = (topic or "").strip()
    ins = (insight or "").strip()
    if not t:
        return {"friction_points": [], "motivation": "", "research_taste": ""}
    try:
        import json, re
        from langchain_core.messages import HumanMessage, SystemMessage
        from utils.llm_client import get_llm

        llm = get_llm(temperature=0.2)
        resp = llm.invoke([
            SystemMessage(content=(
                "You summarize a compact researcher profile from a topic and a user insight.\n"
                "Priority rule:\n"
                "- The Topic is the primary objective and must dominate.\n"
                "- The Insight is secondary: treat it as inspiration/constraints/mechanisms, never as a new standalone task.\n"
                "Hard constraints:\n"
                "- Do NOT introduce new domains/tasks/datasets not implied by the Topic.\n"
                "- Each friction point must explicitly relate to improving the Topic objective.\n"
                "Output strict JSON only (no extra text):\n"
                "{\n"
                '  "friction_points": ["...","..."],\n'
                '  "motivation": "one sentence",\n'
                '  "research_taste": "one sentence"\n'
                "}"
            )),
            HumanMessage(content=json.dumps({
                "topic": t,
                "insight": ins,
            }, ensure_ascii=False)),
        ])
        m = re.search(r"\{.*\}", resp.content, re.DOTALL)
        if m:
            profile = json.loads(m.group())
            fp = profile.get("friction_points", [])
            fp = [str(x).strip() for x in (fp or []) if str(x).strip()]
            return {
                "friction_points": fp[:6],
                "motivation": str(profile.get("motivation", "") or "").strip(),
                "research_taste": str(profile.get("research_taste", "") or "").strip(),
            }
    except Exception:
        pass
    return {"friction_points": [ins] if ins else [], "motivation": "", "research_taste": ""}


@st.cache_resource(show_spinner=False)
def _web_checkpoint_graph():
    from utils.web_session import build_web_checkpoint_graph

    return build_web_checkpoint_graph()


@st.cache_resource(show_spinner=False)
def _orchestrator_checkpoint_graph():
    from agents.orchestrator import build_graph

    return build_graph()


def _graph_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _graph_phase(graph, config) -> str:
    snapshot = graph.get_state(config)
    next_nodes = set(getattr(snapshot, "next", None) or ())
    if "human_elicit_continue" in next_nodes:
        return "graph_elicit"
    if "human_direction_select" in next_nodes:
        return "graph_direction"
    if "human_proposal_review" in next_nodes:
        return "graph_proposal"
    if not next_nodes and (snapshot.values or {}).get("core_modification"):
        return "graph_done"
    return "graph_running"


def _stream_graph_until_pause(graph, config):
    """Run the shared graph until its next human gate or completion."""
    for _ in graph.stream(None, config, stream_mode="values"):
        pass
    return _graph_phase(graph, config)


def _last_assistant_message(state: dict) -> str:
    """Return the latest assistant message from either dict or LangChain form."""
    for message in reversed(state.get("messages", []) or []):
        if isinstance(message, dict):
            if message.get("role") == "assistant":
                return str(message.get("content", "") or "")
            continue
        if getattr(message, "type", "") == "ai":
            return str(getattr(message, "content", "") or "")
    return ""


def _refresh_graph_state(graph, config, phase: str) -> dict:
    """Copy the checkpoint values into Streamlit and attach its UI phase."""
    from utils.session_runtime import checkpoint_id
    snapshot = graph.get_state(config)
    st.session_state["_checkpoint_id"] = checkpoint_id(snapshot)
    state = dict(snapshot.values or {})
    state["ui_phase"] = phase
    st.session_state.state = state
    st.session_state.phase = phase
    return state


def _query_session_id() -> str:
    try:
        value = st.query_params.get("session_id", "")
    except Exception:
        return ""
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").strip()


def _set_query_session_id(session_id: str) -> None:
    try:
        st.query_params["session_id"] = session_id
    except Exception:
        pass


def _load_web_session(session_id: str) -> tuple[dict, str]:
    graph = _orchestrator_checkpoint_graph()
    config = _graph_config(session_id)
    snapshot = graph.get_state(config)
    from utils.session_runtime import checkpoint_id
    values = dict(getattr(snapshot, "values", None) or {})
    if values.get("workflow") == "orchestrator":
        st.session_state["_checkpoint_id"] = checkpoint_id(snapshot)
        st.session_state["graph_mode"] = "orchestrator"
        saved_phase = str(values.get("ui_phase", "graph_running"))
        # A graph checkpoint can be newer than the last UI write if the
        # process stopped between graph.stream() and _persist_web_session().
        # Human-gate pages must therefore be derived from snapshot.next.
        if saved_phase in ("experiment", "writing"):
            phase = saved_phase
        else:
            phase = _graph_phase(graph, config)
        values["ui_phase"] = phase
        return values, phase

    from utils.web_session import load_web_state

    st.session_state["graph_mode"] = "legacy"
    legacy = _web_checkpoint_graph()
    result = load_web_state(legacy, session_id)
    st.session_state["_checkpoint_id"] = checkpoint_id(legacy.get_state(config))
    return result


def _persist_web_session() -> None:
    session_id = str(st.session_state.get("session_id", "") or "").strip()
    state = st.session_state.get("state") or {}
    phase = str(st.session_state.get("phase", "input") or "input")
    if not session_id or not state:
        return
    try:
        from utils.session_runtime import checkpoint_id
        if st.session_state.get("graph_mode") == "orchestrator":
            graph = _orchestrator_checkpoint_graph()
            payload = dict(state)
            payload.pop("messages", None)
            payload["ui_phase"] = phase
            config = _graph_config(session_id)
            with graph.session(config, st.session_state.get("_checkpoint_id")):
                current = graph.get_state(config).values
                if any(current.get(key) != value for key, value in payload.items()):
                    graph.update_state(config, payload)
                st.session_state["_checkpoint_id"] = checkpoint_id(graph.get_state(config))
                _save_web_outputs(state)
        else:
            from utils.web_session import save_web_state
            graph = _web_checkpoint_graph()
            config = _graph_config(session_id)
            with graph.session(config, st.session_state.get("_checkpoint_id")):
                current = graph.get_state(config).values
                payload = {**state, "session_id": session_id, "workflow": "streamlit", "ui_phase": phase}
                payload.pop("messages", None)
                if any(current.get(key) != value for key, value in payload.items()):
                    save_web_state(graph, session_id, state, phase)
                st.session_state["_checkpoint_id"] = checkpoint_id(graph.get_state(config))
                _save_web_outputs(state)
        st.session_state.pop("_persistence_error", None)
        return True
    except Exception as exc:
        st.session_state["_persistence_error"] = str(exc)
        return False


def _save_web_outputs(state):
    from utils.artifacts import save_artifacts, save_failure_message
    report = save_artifacts(state, st.session_state.session_id)
    st.session_state["_artifact_save_error"] = save_failure_message(report)
    return report


def _continue_graph(graph, config, changes=None):
    """Protect the human update and subsequent execution from other tabs."""
    with graph.session(config, st.session_state.get("_checkpoint_id")):
        if changes:
            graph.update_state(config, changes)
        try:
            phase = _stream_graph_until_pause(graph, config)
        finally:
            # Also refresh after a node fails so Retry resumes the newer checkpoint.
            _refresh_graph_state(graph, config, _graph_phase(graph, config))
            _save_web_outputs(st.session_state.state)
        _persist_web_session()
        return phase


def _render_evidence(state):
    with st.expander("Literature evidence and research hypotheses", expanded=False):
        from utils.evidence import evidence_appendix
        st.markdown(evidence_appendix(state))


def _run_ui_node(fn, state):
    """Apply the same session guard to optional experiment/writing nodes."""
    graph = (_orchestrator_checkpoint_graph() if st.session_state.get("graph_mode") == "orchestrator"
             else _web_checkpoint_graph())
    config = _graph_config(st.session_state.session_id)
    from utils.storage import SessionBusyError, StaleSessionError
    try:
        with graph.session(config, st.session_state.get("_checkpoint_id")):
            updated = fn(state)
            metadata = dict(updated.get("metadata") or {})
            completed = list(metadata.get("ui_completed_nodes") or [])
            if fn.__name__ not in completed:
                completed.append(fn.__name__)
            metadata["ui_completed_nodes"] = completed
            updated = {**updated, "metadata": metadata}
            st.session_state.state = updated
            if not _persist_web_session():
                raise RuntimeError("Checkpoint save failed: " + st.session_state["_persistence_error"])
            return updated
    except (SessionBusyError, StaleSessionError) as exc:
        st.error(str(exc))
        st.stop()


def _compose_draft(state):
    from langchain_core.messages import HumanMessage, SystemMessage
    from utils.llm_client import get_llm
    from utils.evidence import evidence_prompt
    llm = get_llm(temperature=0.6)
    sections = ["abstract", "introduction", "related_work", "method", "experiments", "conclusion"]
    drafts = {}
    progress = st.progress(0, text="Preparing to write...")
    for i, section in enumerate(sections):
        progress.progress(int((i + 1) / len(sections) * 100), text=f"Composing {section} section...")
        response = llm.invoke([
            SystemMessage(content=f"Write the {section} section in the user's language. Distinguish hypotheses from observed results."),
            HumanMessage(content=f"Outline: {state.get('paper_outline', '')[:600]}\nStory arc: {state.get('story_arc', '')[:400]}\n"
                         + evidence_prompt(state.get("evidence_catalog", []))),
        ])
        drafts[section] = response.content
    return {**state, "draft_sections": drafts,
            "full_draft": "\n\n".join(f"## {s.upper()}\n\n{drafts[s]}" for s in sections)}


def _legacy_profile_node(state):
    if state.get("friction_points"):
        return state
    profile = _build_profile_from_topic_and_insight(state.get("topic", ""), state.get("user_insight", ""))
    return {**state, "friction_points": profile.get("friction_points", []) or [],
            "motivation": state.get("motivation") or profile.get("motivation", ""),
            "research_taste": state.get("research_taste") or profile.get("research_taste", "")}


def _clear_session_widgets():
    for key in list(st.session_state):
        if key.startswith("graph_") and key != "graph_mode":
            st.session_state.pop(key, None)
    for key in ("_checkpoint_id", "_artifact_save_error", "_persistence_error", "_selected_dir_idx", "_start_validation_requested", "_research_started_notice"):
        st.session_state.pop(key, None)


def _initialise_web_session() -> None:
    if "session_id" in st.session_state:
        return

    requested_id = _query_session_id()
    if requested_id:
        try:
            state, phase = _load_web_session(requested_id)
            st.session_state.state = state
            st.session_state.phase = phase
            st.session_state.session_id = requested_id
            return
        except Exception as exc:
            st.session_state["_resume_error"] = str(exc)

    st.session_state.state = {}
    st.session_state.phase = "input"
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.graph_mode = "pending"
    _set_query_session_id(st.session_state.session_id)


# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────

st.set_page_config(
    page_title="Aporia",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

_initialise_web_session()

# ──────────────────────────────────────────────
# Global custom CSS — deep space blue theme
# ──────────────────────────────────────────────

st.markdown("""
<style>
    /* ── Override main background (belt-and-suspenders with config.toml) ── */
    .stApp {
        background-color: #0B111D;
    }
    .main .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 2rem !important;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] > div {
        background-color: #0D1524;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1rem !important;
    }

    /* ── Text area card style ── */
    div[data-testid="stTextArea"] textarea {
        background-color: #151E32 !important;
        border: 1px solid #1E2A45 !important;
        border-radius: 10px !important;
        color: #E0E6F0 !important;
        font-size: 0.95rem !important;
        transition: border-color 0.25s ease, box-shadow 0.25s ease !important;
    }
    div[data-testid="stTextArea"] textarea:focus {
        border-color: #3A86FF !important;
        box-shadow: 0 0 0 3px rgba(58, 134, 255, 0.15) !important;
        outline: none !important;
    }
    div[data-testid="stTextArea"] textarea::placeholder {
        color: #3A5A80 !important;
        opacity: 0.6 !important;
    }
    div[data-testid="stTextArea"] label {
        color: #7B8CA8 !important;
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        letter-spacing: 0.03em !important;
    }

    /* ── Primary buttons ── */
    button[kind="primary"] {
        background-color: #3A86FF !important;
        border-color: #3A86FF !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        transition: background-color 0.2s !important;
    }
    button[kind="primary"]:hover {
        background-color: #5A9FFF !important;
        border-color: #5A9FFF !important;
    }

    /* ── Secondary buttons ── */
    button[kind="secondary"] {
        border-color: #1E2A45 !important;
        color: #7B8CA8 !important;
        border-radius: 8px !important;
    }
    button[kind="secondary"]:hover {
        border-color: #3A86FF !important;
        color: #3A86FF !important;
    }

    /* ── Progress bars ── */
    .stProgress > div > div > div {
        background-color: #3A86FF !important;
    }
    .stProgress > div > div {
        background-color: #151E32 !important;
    }

    /* ── Expander ── */
    div[data-testid="stExpander"] {
        border: 1px solid #1E2A45 !important;
        border-radius: 8px !important;
        background-color: #151E32 !important;
    }

    /* ── Info / warning boxes ── */
    div[data-testid="stAlert"] {
        background-color: #151E32 !important;
        border: 1px solid #1E2A45 !important;
        border-radius: 8px !important;
    }

    /* ── Metrics ── */
    div[data-testid="stMetric"] {
        background-color: #151E32 !important;
        border: 1px solid #1E2A45 !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
    }
    div[data-testid="stMetric"] label {
        color: #7B8CA8 !important;
    }
    div[data-testid="stMetricValue"] {
        color: #3A86FF !important;
        font-weight: 700 !important;
    }

    /* ── Radio buttons ── */
    div[data-testid="stRadio"] label {
        color: #B0BEC5 !important;
    }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
        border-bottom: 1px solid #1E2A45 !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #7B8CA8 !important;
        background-color: transparent !important;
        border-radius: 6px 6px 0 0 !important;
        padding: 8px 16px !important;
        font-size: 0.85rem !important;
    }
    .stTabs [aria-selected="true"] {
        color: #3A86FF !important;
        background-color: #151E32 !important;
        border-bottom: 2px solid #3A86FF !important;
    }

    /* ── Subtitle ── */
    .aporia-subtitle {
        color: #5A6E8C;
        font-size: 0.88rem;
        margin-top: -0.5rem;
        margin-bottom: 0.25rem;
        font-weight: 400;
    }

    /* ── Hint text ── */
    .aporia-hint {
        color: #5A6E8C;
        font-size: 0.8rem;
        font-style: italic;
        border-left: 2px solid #1E2A45;
        padding-left: 12px;
        margin-top: 10px;
        line-height: 1.5;
    }

    /* ── Breadcrumb ── */
    .aporia-breadcrumb {
        color: #3A5A80;
        font-size: 0.78rem;
        letter-spacing: 0.04em;
        margin-bottom: 1rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid #151E32;
    }

    /* ── Step header ── */
    .aporia-step-label {
        color: #3A86FF;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.14em;
        font-weight: 600;
        margin-bottom: 0.2rem;
    }

    /* ── Direction cards ── */
    .aporia-card {
        background-color: #151E32;
        border: 1px solid #1E2A45;
        border-radius: 10px;
        padding: 16px 20px;
        margin-bottom: 10px;
        transition: border-color 0.2s ease;
        cursor: default;
    }
    .aporia-card:hover {
        border-color: #3A86FF;
    }
    .aporia-card-selected {
        border-color: #3A86FF !important;
        box-shadow: 0 0 0 2px rgba(58, 134, 255, 0.18);
    }
    .aporia-card-index {
        color: #3A86FF;
        font-weight: 700;
        font-size: 0.75rem;
        margin-bottom: 4px;
    }
    .aporia-card-title {
        color: #E0E6F0;
        font-weight: 600;
        font-size: 0.9rem;
        margin-bottom: 6px;
    }
    .aporia-card-assumption {
        color: #7B8CA8;
        font-size: 0.78rem;
        font-style: italic;
        margin-bottom: 2px;
    }
    .aporia-card-oneline {
        color: #B0BEC5;
        font-size: 0.82rem;
    }

    /* ── Divider ── */
    .aporia-vdivider {
        border-left: 1px solid #1E2A45;
        height: 100%;
        min-height: 120px;
    }

    /* ── Sidebar timeline ── */
    .tl-dot {
        display: inline-block;
        width: 9px;
        height: 9px;
        border-radius: 50%;
        margin-right: 10px;
        vertical-align: middle;
    }
    .tl-row {
        font-size: 0.95rem;
        padding: 6px 0 6px 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    /* ── Spinner ── */
    .stSpinner > div {
        border-top-color: #3A86FF !important;
    }

    /* ── Hide native running-man SVG, preserve Stop button ── */
    div[data-testid="stStatusWidget"] svg,
    div[data-testid="stStatusWidget"] img,
    div[data-testid="stStatusWidget"] [data-testid="stStatusWidgetSpinner"] {
        display: none !important;
    }

    /* ── Custom rotating spinner (blue arc with gap, gradient fade) ── */
    @keyframes aporia-spin {
        0%   { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    .aporia-spinner {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 2.5px solid transparent;
        border-top-color: #3A86FF;
        border-right-color: rgba(58, 134, 255, 0.25);
        border-bottom-color: transparent;
        border-left-color: transparent;
        border-radius: 50%;
        animation: aporia-spin 0.85s linear infinite;
        transform-origin: center center;
    }
    .aporia-spinner-fixed {
        display: inline-block;
        width: 20px;
        height: 20px;
        border: 2.5px solid transparent;
        border-top-color: #3A86FF;
        border-right-color: rgba(58, 134, 255, 0.25);
        border-bottom-color: transparent;
        border-left-color: transparent;
        border-radius: 50%;
        animation: aporia-spin 0.85s linear infinite;
        transform-origin: center center;
    }

    /* ── Status container styling ── */
    div[data-testid="stStatus"] {
        border: 1px solid #1E2A45 !important;
        border-radius: 8px !important;
        background-color: #151E32 !important;
    }

    /* ── Global fonts ── */
    h1, h2, h3, h4, h5, h6, p, div, label, input, textarea {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
    }
    /* Preserve Material Symbols for Streamlit icons */
    .material-symbols-outlined, [class*="material-symbols"] {
        font-family: "Material Symbols Outlined", "Material Icons", sans-serif !important;
    }
    h1 {
        color: #E0E6F0 !important;
        font-weight: 700 !important;
    }
    h2 {
        color: #CCD6E0 !important;
        font-weight: 600 !important;
    }
    h3 {
        color: #B0BEC5 !important;
        font-weight: 600 !important;
    }

    /* ── Divider lines ── */
    hr, .stDivider {
        border-color: #151E32 !important;
    }

    /* ── Warnings ── */
    div[data-testid="stAlert"] {
        border-radius: 8px !important;
    }
    div[data-testid="stAlert"][kind="warning"] {
        background-color: rgba(255, 170, 0, 0.08) !important;
        border: 1px solid rgba(255, 170, 0, 0.25) !important;
    }

    /* ── Select boxes ── */
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
        background-color: #151E32 !important;
        border-color: #1E2A45 !important;
    }
    div[data-testid="stSelectbox"] [data-baseweb="select"] * {
        color: #E0E6F0 !important;
    }
    div[data-testid="stSelectbox"] label {
        color: #7B8CA8 !important;
        font-size: 0.85rem !important;
    }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# Breadcrumb helper
# ──────────────────────────────────────────────

_BREADCRUMB_STEPS = [
    "Research Direction",
    "Idea Discovery",
    "Direction Selection",
    "Idea Refinement",
    "Experiments",
    "Writing",
]

_BREADCRUMB_IDX = {
    "input": 0,
    "running": 1,
    "graph_elicit": 1,
    "graph_running": 1,
    "graph_direction": 2,
    "idea_select": 2,
    "graph_proposal": 3,
    "graph_done": 4,
    "refining": 3,
    "experiment": 4,
    "writing": 5,
}


def _render_breadcrumb(phase: str):
    idx = _BREADCRUMB_IDX.get(phase, 0)
    parts = []
    for i, s in enumerate(_BREADCRUMB_STEPS):
        if i < idx:
            parts.append(
                f'<span style="color:#3A86FF; font-weight:500;">{s}</span>'
            )
        elif i == idx:
            parts.append(
                f'<span style="color:#E0E6F0; font-weight:700;">{s}</span>'
            )
        else:
            parts.append(
                f'<span style="color:#2A3F5F;">{s}</span>'
            )
    html = ' &nbsp;<span style="color:#1E2A45;">›</span>&nbsp; '.join(parts)
    st.markdown(
        f'<div class="aporia-breadcrumb">{html}</div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────
# Title area
# ──────────────────────────────────────────────

_current_phase = st.session_state.get("phase", "input")
_show_spinner = _current_phase not in ("input", "idea_select", None)

if _show_spinner:
    st.markdown("""
    <style>
        header[data-testid="stHeader"]::after {
            content: '';
            position: absolute;
            right: 175px;
            top: 0;
            bottom: 0;
            margin-top: auto;
            margin-bottom: auto;
            width: 20px;
            height: 20px;
            border: 2.5px solid transparent;
            border-top-color: #3A86FF;
            border-right-color: rgba(58, 134, 255, 0.25);
            border-bottom-color: transparent;
            border-left-color: transparent;
            border-radius: 50%;
            animation: aporia-spin 0.85s linear infinite;
            z-index: 999999;
        }
    </style>
    """, unsafe_allow_html=True)

st.title("Aporia")
st.markdown(
    '<p class="aporia-subtitle">'
    'An agentic assistant from initial intuition to structured paper drafts'
    '</p>',
    unsafe_allow_html=True,
)

# ──────────────────────────────────────────────
# Sidebar helpers: keep session tools secondary to model setup
# ──────────────────────────────────────────────

def _render_session_controls():
    st.caption("This ID is backed by the local checkpoint database.")
    st.code(st.session_state.session_id, language="text")
    resume_id = st.text_input(
        "Load another session",
        value="",
        placeholder="Paste a session ID",
        key="resume_session_input",
    )
    if st.button("Load session", use_container_width=True, disabled=not resume_id.strip()):
        try:
            _clear_session_widgets()
            loaded_state, loaded_phase = _load_web_session(resume_id.strip())
            st.session_state.state = loaded_state
            st.session_state.phase = loaded_phase
            st.session_state.session_id = resume_id.strip()
            st.session_state.pop("_resume_error", None)
            st.session_state.pop("_selected_dir_idx", None)
            _set_query_session_id(st.session_state.session_id)
            st.rerun()
        except Exception as exc:
            st.session_state["_resume_error"] = str(exc)
    if st.button("New session", use_container_width=True):
        _clear_session_widgets()
        st.session_state.state = {}
        st.session_state.phase = "input"
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.graph_mode = "pending"
        st.session_state.pop("_selected_dir_idx", None)
        st.session_state.pop("_resume_error", None)
        _set_query_session_id(st.session_state.session_id)
        st.rerun()
    if st.session_state.get("_resume_error"):
        st.warning(st.session_state["_resume_error"])
    if st.button("Reload current session", disabled=not bool(st.session_state.state)):
        try:
            sid = st.session_state.session_id
            _clear_session_widgets()
            state, phase = _load_web_session(sid)
            st.session_state.state, st.session_state.phase = state, phase
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    _render_session_history()


def _render_save_status():
    # Save failures must remain visible even when session tools are collapsed.
    if st.session_state.get("_persistence_error"):
        st.warning("Checkpoint save failed: " + st.session_state["_persistence_error"])
        if st.button("Retry checkpoint save"):
            _persist_web_session()
            st.rerun()
    if st.session_state.get("_artifact_save_error"):
        st.warning(st.session_state["_artifact_save_error"])
        if st.button("Retry saving outputs"):
            try:
                graph = (_orchestrator_checkpoint_graph() if st.session_state.get("graph_mode") == "orchestrator"
                         else _web_checkpoint_graph())
                config = _graph_config(st.session_state.session_id)
                with graph.session(config):
                    _save_web_outputs(graph.get_state(config).values)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _render_session_history():
    with st.expander("Session history and maintenance", expanded=False):
        from utils.sessions import list_sessions, rename_session, export_session, delete_session
        try:
            manager_graph = _orchestrator_checkpoint_graph()
            history = list_sessions(manager_graph)
            options = {item["session_id"]: item for item in history}
            if options:
                history_id = st.selectbox("Saved sessions", list(options),
                    format_func=lambda sid: f"{options[sid]['title']} · {sid}")
                if st.button("Open selected session"):
                    _clear_session_widgets()
                    state, phase = _load_web_session(history_id)
                    st.session_state.state, st.session_state.phase = state, phase
                    st.session_state.session_id = history_id
                    _set_query_session_id(history_id)
                    st.rerun()
                title = st.text_input("Session name", value=options[history_id]["title"], key="session_title_" + history_id)
                if st.button("Rename selected session"):
                    rename_session(manager_graph, history_id, title)
                    st.rerun()
                if st.button("Prepare session export"):
                    bundle = export_session(manager_graph, history_id)
                    st.download_button("Download session ZIP", bundle, file_name="aporia-session.zip", mime="application/zip")
                delete_confirmed = st.checkbox("Delete selected session (a recovery backup will be kept)", key="delete_confirm_" + history_id)
                if st.button("Delete selected session", disabled=not delete_confirmed):
                    recovery = delete_session(manager_graph, history_id)
                    if history_id == st.session_state.session_id:
                        _clear_session_widgets()
                        st.session_state.state = {}
                        st.session_state.phase = "input"
                        st.session_state.graph_mode = "pending"
                        st.session_state.session_id = str(uuid.uuid4())
                        _set_query_session_id(st.session_state.session_id)
                    st.session_state["_maintenance_message"] = f"Deleted session; recovery files: {recovery}"
                    st.rerun()
            else:
                st.caption("No saved sessions yet.")
            if st.button("Clean completed cache older than 30 days"):
                from utils.operations import clean_cache
                st.session_state["_maintenance_message"] = f"Removed {clean_cache(30)} cache records."
            if st.session_state.get("_maintenance_message"):
                st.info(st.session_state["_maintenance_message"])
        except Exception as exc:
            st.warning(f"Session maintenance unavailable: {exc}")


with st.sidebar:
    # Model setup is a prerequisite; show it before session IDs and recovery.
    st.markdown("### Configuration")
    st.caption("Choose a model provider first, then enter your research topic and intuition.")
    with st.expander("Model settings", expanded=True):
        provider_labels = {
            "deepseek": "DeepSeek",
            "gemini": "Gemini",
            "openai": "OpenAI",
            "anthropic": "Anthropic",
        }
        default_provider = (os.environ.get("RESEARCH_AGENT_LLM_PROVIDER") or os.environ.get("LLM_PROVIDER") or "deepseek").strip().lower()
        if default_provider not in ("gemini", "openai", "anthropic", "deepseek"):
            default_provider = "deepseek"
        provider_options = ["deepseek", "gemini", "openai", "anthropic"]
        provider = st.selectbox(
            "LLM Provider",
            options=provider_options,
            format_func=lambda value: provider_labels[value],
            index=provider_options.index(default_provider) if default_provider in provider_options else 0,
            key="settings_provider",
        )
        os.environ["RESEARCH_AGENT_LLM_PROVIDER"] = provider

        if provider == "gemini":
            api_key = st.text_input("Gemini API Key", type="password", value="", placeholder="Enter your Gemini API key", key="settings_gemini_api_key")
            model = st.text_input("Gemini Model", value="", placeholder="e.g. gemini-1.5-flash", key="settings_gemini_model")
            if api_key:
                os.environ["GEMINI_API_KEY"] = api_key
            if model:
                os.environ["GEMINI_MODEL"] = model
        elif provider == "anthropic":
            api_key = st.text_input("Anthropic API Key", type="password", value="", placeholder="Enter your Anthropic API key", key="settings_anthropic_api_key")
            model = st.text_input("Anthropic Model", value="", placeholder="e.g. claude-sonnet-4-6", key="settings_anthropic_model")
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key
            if model:
                os.environ["ANTHROPIC_MODEL"] = model
        elif provider == "deepseek":
            api_key = st.text_input("DeepSeek API Key", type="password", value="", placeholder="Enter your DeepSeek API key", key="settings_deepseek_api_key")
            model = st.text_input("DeepSeek Model", value="", placeholder="e.g. deepseek-v4-pro", key="settings_deepseek_model")
            base_url = st.text_input("DeepSeek Base URL", value="", placeholder="e.g. https://api.deepseek.com", key="settings_deepseek_base_url")
            if api_key:
                os.environ["DEEPSEEK_API_KEY"] = api_key
            if model:
                os.environ["DEEPSEEK_MODEL"] = model
            if base_url:
                os.environ["DEEPSEEK_BASE_URL"] = base_url
        else:
            api_key = st.text_input("OpenAI API Key", type="password", value="", placeholder="Enter your OpenAI API key", key="settings_openai_api_key")
            model = st.text_input("OpenAI Model", value="", placeholder="e.g. gpt-4o", key="settings_openai_model")
            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
            if model:
                os.environ["OPENAI_MODEL"] = model

        from utils.llm_client import _clean_key

        key_env = {
            "deepseek": "DEEPSEEK_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }[provider]
        # A blank widget must not silently opt in to using a configured secret.
        entered_api_key = _clean_key(api_key)
        configured_api_key = _clean_key(os.environ.get(key_env))
        use_configured_key = False
        if configured_api_key:
            use_configured_key = st.checkbox(
                f"Use configured {provider_labels[provider]} API key (.env / environment)",
                value=False,
                key=f"settings_use_configured_{provider}_key",
                help="Select this explicitly to use the existing key without entering it again. The secret is never displayed.",
            )
        api_key = entered_api_key or (configured_api_key if use_configured_key else None)
        provider_label = provider_labels[provider]
        key_source = "the sidebar" if entered_api_key else ".env / environment (explicitly selected)"
        if api_key:
            st.success(f"API key selected for {provider_label} from {key_source}.")
            st.caption("Key selected; credentials are checked when the model is called.")
        elif configured_api_key:
            st.warning(f"API key required: enter a {provider_label} key above, or explicitly select 'Use configured {provider_label} API key'. An existing key is available but has not been selected.")
        else:
            st.warning(f"API key required: enter a {provider_label} key above, or configure {key_env} in .env.")

        if provider == "gemini":
            st.caption(f"Effective: provider={provider_label} | model={os.environ.get('GEMINI_MODEL') or '(not set)'}")
        elif provider == "openai":
            st.caption(f"Effective: provider={provider_label} | model={os.environ.get('OPENAI_MODEL') or '(not set)'}")
        elif provider == "deepseek":
            st.caption(f"Effective: provider={provider_label} | model={os.environ.get('DEEPSEEK_MODEL') or '(not set)'} | base={os.environ.get('DEEPSEEK_BASE_URL') or '(not set)'}")
        else:
            st.caption(f"Effective: provider={provider_label} | model={os.environ.get('ANTHROPIC_MODEL') or '(not set)'}")
        st.caption(
            "paper_min="
            + str(os.environ.get("RESEARCH_AGENT_PAPER_MIN", ""))
            + " | paper_limit="
            + str(os.environ.get("RESEARCH_AGENT_PAPER_LIMIT", ""))
            + " | rerank_candidates="
            + str(os.environ.get("RESEARCH_AGENT_RERANK_CANDIDATES", ""))
        )

    st.divider()
    with st.expander("Sessions and recovery", expanded=False):
        _render_session_controls()
    _render_save_status()

    st.divider()

    # ── Progress timeline ──
    st.markdown(
        '<p style="color:#5A6E8C; font-size:0.82rem; text-transform:uppercase; '
        'letter-spacing:0.14em; margin-bottom:14px; font-weight:600;">Current Stage</p>',
        unsafe_allow_html=True,
    )

    _tl_phases = [
        ("input",         "Input"),
        ("idea_discovery","Idea Discovery"),
        ("idea_select",   "Idea Selection"),
        ("refining",      "Idea Refinement"),
        ("experiment",    "Experiment Support"),
        ("writing",       "Writing"),
        ("review",        "Review / Rebuttal"),
    ]

    current_phase = st.session_state.get("phase", "input")

    _sub_to_canonical = {
        "running":        "idea_discovery",
        "graph_elicit":   "idea_discovery",
        "graph_running":  "idea_discovery",
        "graph_direction":"idea_select",
        "graph_proposal": "refining",
        "graph_done":     "experiment",
        "idea_refine":    "refining",
        "done":           None,
    }
    _canonical_current = _sub_to_canonical.get(current_phase, current_phase)

    _past = True
    for _ph_key, _ph_label in _tl_phases:
        if _ph_key == _canonical_current:
            _past = False
            st.markdown(
                f'<div class="tl-row" style="color:#3A86FF; font-weight:700;">'
                f'<span class="tl-dot" style="background:#3A86FF; '
                f'box-shadow:0 0 6px rgba(58,134,255,0.45);"></span>'
                f'{_ph_label}'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif _past:
            st.markdown(
                f'<div class="tl-row" style="color:#4A5E7A;">'
                f'<span class="tl-dot" style="background:#2A3F5F;"></span>'
                f'{_ph_label}'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="tl-row" style="color:#1E2A45;">'
                f'<span class="tl-dot" style="background:#151E32;"></span>'
                f'{_ph_label}'
                f'</div>',
                unsafe_allow_html=True,
            )

# ──────────────────────────────────────────────
# Session state init
# ──────────────────────────────────────────────

if "state" not in st.session_state:
    st.session_state.state = {}
if "phase" not in st.session_state:
    st.session_state.phase = "input"

if st.session_state.pop("_research_started_notice", False):
    st.success("Research started successfully. The first analysis has finished; continue with the current step below.")

# ──────────────────────────────────────────────
# Phase: input
# ──────────────────────────────────────────────

if st.session_state.phase == "input":
    _render_breadcrumb("input")

    st.markdown(
        '<p class="aporia-step-label">Step 1</p>',
        unsafe_allow_html=True,
    )
    st.header("Tell me your research direction")

    col_left, col_div, col_right = st.columns([0.38, 0.02, 0.60])
    with col_left:
        topic = st.text_area(
            "Research direction",
            placeholder="e.g., medical image segmentation with diffusion models",
            height=130,
        )
    with col_div:
        st.markdown(
            '<div style="height:110px; border-left:1px solid #1E2A45; '
            'margin-top:28px;"></div>',
            unsafe_allow_html=True,
        )
    with col_right:
        user_insight = st.text_area(
            "Your intuition / experience",
            placeholder="e.g., prior work ignores anatomical priors; adding priors may help.\n\nIt can be vague; this is the most important input.",
            height=130,
        )

    st.markdown(
        '<p class="aporia-hint">Your intuition matters: '
        'literature-only synthesis often produces shallow combinations.</p>',
        unsafe_allow_html=True,
    )

    if api_key:
        st.caption(f"API Key source: {provider_label} · {key_source}. Validity is checked when the model is called.")
    else:
        st.caption(f"API Key required: enter a {provider_label} key in Configuration → Model settings, or explicitly select a configured key.")

    start_clicked = st.button("Start", type="primary")
    if start_clicked:
        st.session_state["_start_validation_requested"] = True
    if st.session_state.get("_start_validation_requested"):
        missing = []
        if not topic.strip():
            missing.append("Research direction: enter the topic you want to study in the left field.")
        if not user_insight.strip():
            missing.append("Your intuition / experience: add an observation, question, or initial hypothesis in the right field.")
        if not api_key:
            missing.append(f"API Key: open Configuration → Model settings at the top of the sidebar and enter a {provider_label} key, or explicitly select 'Use configured {provider_label} API key' after configuring {key_env} in .env.")
        if missing:
            st.error("Please complete the following before starting:\n\n" + "\n".join(f"- {item}" for item in missing))
        elif start_clicked:
            st.session_state.pop("_start_validation_requested", None)
            with st.status("Starting research — preparing the session...", expanded=True) as start_status:
                try:
                    from agents.orchestrator import start_dialogue

                    st.write(f"Inputs accepted. Using {provider} with the API key from {key_source}.")
                    st.write("Running the initial research analysis. Model responses may take some time; please keep this page open.")
                    start_status.update(label="Research is starting — waiting for the initial analysis...")
                    graph, config, _ = start_dialogue(
                        topic.strip(),
                        session_id=st.session_state.session_id,
                        user_language="Auto",
                        initial_feedback=user_insight.strip(),
                    )
                    start_status.update(label="Initial analysis finished — saving session...")
                    phase = _graph_phase(graph, config)
                    st.session_state.graph_mode = "orchestrator"
                    _refresh_graph_state(graph, config, phase)
                    _persist_web_session()
                    st.session_state["_research_started_notice"] = True
                    start_status.update(label="Research started successfully.", state="complete")
                except Exception as exc:
                    start_status.update(label="Research could not start. See the error below.", state="error")
                    st.error(f"Unable to start the research graph: {exc}")
                else:
                    st.rerun()

# ──────────────────────────────────────────────
# Phases: the shared LangGraph workflow
# ──────────────────────────────────────────────

elif st.session_state.phase == "graph_elicit":
    _render_breadcrumb("graph_elicit")
    state = st.session_state.state
    graph = _orchestrator_checkpoint_graph()
    config = _graph_config(st.session_state.session_id)

    st.markdown('<p class="aporia-step-label">Step 2</p>', unsafe_allow_html=True)
    st.header("Clarify the research friction")
    st.caption(f"Topic: {state.get('topic', '')}")
    question = _last_assistant_message(state)
    if question:
        st.info(question)

    answer = st.text_area(
        "Your answer",
        placeholder="Describe a concrete example, limitation, or constraint. A short answer is fine.",
        height=130,
        key="graph_elicit_answer",
    )
    if st.button("Continue analysis", type="primary", disabled=not answer.strip(),
                 key="elicit_submit_" + str(st.session_state.get("_checkpoint_id"))):
        try:
            changes = {
                "human_feedback": answer.strip(),
                "messages": [{"role": "user", "content": answer.strip()}],
            }
            with st.status("Continuing the research analysis...", expanded=True) as status:
                status.update(label="Running the shared research graph...")
                phase = _continue_graph(graph, config, changes)
                status.update(label="Checkpoint reached.", state="complete")
            st.rerun()
        except Exception as exc:
            st.error(f"Unable to continue the research graph: {exc}")

elif st.session_state.phase == "graph_running":
    _render_breadcrumb("graph_running")
    state = st.session_state.state
    graph = _orchestrator_checkpoint_graph()
    config = _graph_config(st.session_state.session_id)

    st.markdown('<p class="aporia-step-label">Step 2</p>', unsafe_allow_html=True)
    st.header(f"Analyzing: {state.get('topic', '')}")
    try:
        with st.status("Running the shared research graph...", expanded=True) as status:
            phase = _continue_graph(graph, config)
            status.update(label="Checkpoint reached.", state="complete")
        st.rerun()
    except Exception as exc:
        st.error(f"The research graph stopped unexpectedly: {exc}")

elif st.session_state.phase == "graph_direction":
    _render_breadcrumb("graph_direction")
    state = st.session_state.state
    graph = _orchestrator_checkpoint_graph()
    config = _graph_config(st.session_state.session_id)
    directions = [d for d in (state.get("candidate_directions") or []) if isinstance(d, dict)]

    st.markdown('<p class="aporia-step-label">Step 3</p>', unsafe_allow_html=True)
    st.header("Choose a research direction")
    st.caption("This selection is written into the graph state before refinement continues.")

    if directions:
        labels = [
            f"{i + 1}. {d.get('name', '')} — {d.get('one_line', '')}"
            for i, d in enumerate(directions)
        ]
        selected_idx = st.radio(
            "Candidate directions",
            options=list(range(len(directions))),
            format_func=lambda i: labels[i],
            key="graph_direction_idx",
        )
        selected = directions[selected_idx]
        st.markdown(f"**Broken assumption:** {selected.get('broken_assumption', '')}")
    else:
        st.warning("No candidate directions were found in this checkpoint.")
        selected_idx = 0
        selected = {}

    custom = st.text_area(
        "Optional custom direction",
        placeholder="Leave blank to use the selected candidate.",
        height=90,
        key="graph_custom_direction",
    )
    if custom.strip():
        selected = {
            "name": custom.strip(),
            "broken_assumption": custom.strip(),
            "one_line": custom.strip(),
            "rationale": "",
            "reframed_problem": "",
        }

    papers = [p for p in (state.get("raw_papers") or []) if isinstance(p, dict)]
    paper_by_label = {
        f"{i + 1}. {p.get('title', '')}": p.get("paper_id", "")
        for i, p in enumerate(papers[:12])
        if p.get("paper_id")
    }
    chosen_labels = st.multiselect(
        "Optional full-text papers",
        options=list(paper_by_label),
        key="graph_direction_papers",
        help="Only papers with an available PDF will be expanded by the graph.",
    )

    if st.button("Confirm direction", type="primary", disabled=not selected,
                 key="direction_submit_" + str(st.session_state.get("_checkpoint_id"))):
        try:
            changes = {
                "selected_direction": selected,
                "paper_fulltext_request": [paper_by_label[x] for x in chosen_labels],
                # Direction selection is not proposal approval. Keep this empty
                # so route_after_proposal still reaches its review checkpoint.
                "human_feedback": "",
            }
            with st.status("Refining the selected direction...", expanded=True) as status:
                phase = _continue_graph(graph, config, changes)
                status.update(label="Checkpoint reached.", state="complete")
            st.rerun()
        except Exception as exc:
            st.error(f"Unable to continue with this direction: {exc}")

elif st.session_state.phase == "graph_proposal":
    _render_breadcrumb("graph_proposal")
    state = st.session_state.state
    graph = _orchestrator_checkpoint_graph()
    config = _graph_config(st.session_state.session_id)

    st.markdown('<p class="aporia-step-label">Step 4</p>', unsafe_allow_html=True)
    st.header("Review the research proposal")
    if state.get("story_arc"):
        with st.expander("Story arc", expanded=False):
            st.markdown(state["story_arc"])
    st.markdown(state.get("research_proposal", ""))
    _render_evidence(state)
    revision_count = int(state.get("proposal_revision_count", 0) or 0)
    if revision_count:
        st.caption(f"Revision {revision_count} — review the complete revised proposal below.")

    papers = [p for p in (state.get("raw_papers") or []) if isinstance(p, dict)]
    paper_by_label = {
        f"{i + 1}. {p.get('title', '')}": p.get("paper_id", "")
        for i, p in enumerate(papers[:12])
        if p.get("paper_id")
    }
    chosen_labels = st.multiselect(
        "Optional full-text papers before code generation",
        options=list(paper_by_label),
        key="graph_proposal_papers",
    )
    feedback = st.text_area(
        "Your review",
        placeholder="Type approved, or describe what should be changed.",
        height=110,
        key="graph_proposal_feedback",
    )
    if st.button("Submit proposal review", type="primary", disabled=not feedback.strip(),
                 key="proposal_submit_" + str(st.session_state.get("_checkpoint_id"))):
        try:
            changes = {
                "human_feedback": feedback.strip(),
                "paper_fulltext_request": [paper_by_label[x] for x in chosen_labels],
            }
            approved = feedback.strip().lower() in ("approved", "yes", "ok")
            status_label = (
                "Generating the core algorithm guidance..."
                if approved else "Revising the proposal from your feedback..."
            )
            with st.status(status_label, expanded=True) as status:
                phase = _continue_graph(graph, config, changes)
                status.update(label="Checkpoint reached.", state="complete")
            st.rerun()
        except Exception as exc:
            st.error(f"Unable to generate the core code guidance: {exc}")

elif st.session_state.phase == "graph_done":
    _render_breadcrumb("graph_done")
    state = st.session_state.state
    st.markdown('<p class="aporia-step-label">Step 5</p>', unsafe_allow_html=True)
    st.header("Core algorithm guidance is ready")
    _render_evidence(state)
    if state.get("research_proposal"):
        with st.expander("Research proposal", expanded=False):
            st.markdown(state["research_proposal"])
    st.markdown(state.get("core_modification", ""))
    st.download_button(
        "Download core algorithm notes",
        data=state.get("core_modification", ""),
        file_name="core_algorithm.md",
        mime="text/markdown",
    )
    if st.button("Continue to experiments", type="primary"):
        st.session_state.phase = "experiment"
        _persist_web_session()
        st.rerun()

# ──────────────────────────────────────────────
# Phase: legacy running workflow
# ──────────────────────────────────────────────

elif st.session_state.phase == "running":
    _render_breadcrumb("running")

    state = st.session_state.state
    topic = state.get("topic", "")

    st.markdown(
        '<p class="aporia-step-label">Step 2</p>',
        unsafe_allow_html=True,
    )
    st.header(f"Analyzing: {topic}")

    with st.status("Initializing analysis pipeline...", expanded=True) as run_status:
        run_status.update(label="Deconstructing research landscape...")
        try:
            state = _run_ui_node(_legacy_profile_node, state)
            st.write("Research landscape mapped.")
            st.session_state.state = state
            _persist_web_session()
        except Exception as e:
            st.warning(f"Profile step had an issue: {e}. Continuing.")
            st.write("Research landscape mapped (with warnings).")

        run_status.update(label="Retrieving relevant literature...")
        try:
            from agents.idea_agent import paper_search_node
            state = _run_ui_node(paper_search_node, state)
            n = len(state.get("raw_papers", []) or [])
            st.write(f"Retrieved {n} papers.")
            st.session_state.state = state
            _persist_web_session()
        except Exception as e:
            st.warning(f"Paper search had an issue: {e}. Continuing with no papers.")
            st.write("Paper search completed (with warnings).")

        run_status.update(label="Synthesizing structural hypotheses...")
        try:
            from agents.idea_agent import direction_synthesis_node
            state = _run_ui_node(direction_synthesis_node, state)
            if "raw_ideas" not in state:
                dirs = state.get("candidate_directions", []) or []
                state["raw_ideas"] = [
                    (d.get("name") or d.get("one_line") or "").strip()
                    for d in dirs
                    if isinstance(d, dict)
                ] or []
            n_dirs = len(state.get("candidate_directions", []) or [])
            st.write(f"Synthesized {n_dirs} candidate directions.")
            run_status.update(label="Analysis complete.", state="complete")
            st.session_state.state = state
            st.session_state.phase = "idea_select"
            _persist_web_session()
            st.rerun()
        except Exception as e:
            run_status.update(label="Error during synthesis.", state="error")
            st.error(f"Error: {e}")
            st.code(str(e))

# ──────────────────────────────────────────────
# Phase: idea_select
# ──────────────────────────────────────────────

elif st.session_state.phase == "idea_select":
    _render_breadcrumb("idea_select")

    state = st.session_state.state

    st.markdown(
        '<p class="aporia-step-label">Step 3</p>',
        unsafe_allow_html=True,
    )
    st.header("Pick a direction to refine")

    papers = state.get("raw_papers", []) or []
    if papers:
        with st.expander(f"Related papers ({len(papers)})"):
            for p in papers[:12]:
                score = p.get("relevance_score", None)
                score_txt = f" - score {score}" if score is not None else ""
                st.markdown(f"**{p.get('title','')}** ({p.get('year','')}){score_txt}")
                reason = (p.get("relevance_reason", "") or "").strip()
                if reason:
                    st.caption(f"reason: {reason}")
                if p.get("abstract"):
                    st.caption((p.get("abstract") or "")[:220] + "...")

    if state.get("paper_summary"):
        with st.expander("Literature summary (AI generated)"):
            st.markdown(state["paper_summary"])

    ideas = state.get("raw_ideas", [])
    dirs = state.get("candidate_directions", []) or []

    if ideas:
        st.subheader("Generated candidates")

        # Card-style direction selection
        selected_idx = st.session_state.get("_selected_dir_idx", 0)

        for i, d in enumerate(dirs):
            if not isinstance(d, dict):
                continue
            is_sel = (i == selected_idx)
            border = "border-color:#3A86FF; box-shadow:0 0 0 2px rgba(58,134,255,0.18);" if is_sel else ""
            label = f"Selected: {d.get('name', '')}" if is_sel else "Select this direction"

            cols = st.columns([0.85, 0.15])
            with cols[0]:
                st.markdown(
                    f'<div class="aporia-card" style="{border}">'
                    f'<div class="aporia-card-index">DIRECTION {i + 1}</div>'
                    f'<div class="aporia-card-title">{d.get("name", "")}</div>'
                    f'<div class="aporia-card-assumption">Broken assumption: {d.get("broken_assumption", "")}</div>'
                    f'<div class="aporia-card-oneline">{d.get("one_line", "")}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown("<br>", unsafe_allow_html=True)
                if is_sel:
                    st.button("Selected", key=f"dir_btn_{i}", disabled=True, use_container_width=True)
                else:
                    if st.button("Select", key=f"dir_btn_{i}", type="primary", use_container_width=True):
                        st.session_state["_selected_dir_idx"] = i
                        st.rerun()

        final_selected_name = ideas[selected_idx] if selected_idx < len(ideas) else (ideas[0] if ideas else "")
        st.info(f"Currently selected: **{final_selected_name}**")

        custom = st.text_area("Or write your own (can be rough):", height=80)
        final_idea = custom.strip() if custom.strip() else final_selected_name

        if st.button("Confirm and refine", type="primary"):
            state["selected_idea"] = final_idea
            if selected_idx < len(dirs):
                state["selected_direction"] = dirs[selected_idx]
            st.session_state.state = state
            st.session_state.phase = "refining"
            _persist_web_session()
            st.rerun()

# ──────────────────────────────────────────────
# Phase: refining
# ──────────────────────────────────────────────

elif st.session_state.phase == "refining":
    _render_breadcrumb("refining")

    state = st.session_state.state

    st.markdown(
        '<p class="aporia-step-label">Step 4</p>',
        unsafe_allow_html=True,
    )
    st.header("Refine + build story arc")

    from agents.refine_agent import gap_analysis_node, story_arc_node, proposal_node

    if not (state.get("story_arc") and state.get("research_proposal")):
        with st.status("Assessing theoretical novelty...", expanded=True) as refine_status:
            state = _run_ui_node(gap_analysis_node, state)
            st.write("Assumptions identified and evaluated.")

            refine_status.update(label="Constructing narrative framework...")
            novelty = state.get("novelty_score", 0)
            feasibility = state.get("feasibility_score", 0)

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Novelty", f"{novelty:.0%}")
                st.progress(int(novelty * 100))
            with col2:
                st.metric("Feasibility", f"{feasibility:.0%}")
                st.progress(int(feasibility * 100))

            if novelty < 0.6:
                st.warning("Low novelty; consider adjusting the direction.")
            if feasibility < 0.5:
                st.warning("Low feasibility; consider simplifying the method.")

            state = _run_ui_node(story_arc_node, state)
            st.write("Story arc constructed.")

            refine_status.update(label="Drafting research proposal...")
            state = _run_ui_node(proposal_node, state)
            st.write("Proposal draft generated.")
            refine_status.update(label="Refinement complete.", state="complete")
    else:
        st.info("Restored the saved refinement and proposal results.")

    st.subheader("Story arc")
    st.markdown(state.get("story_arc", ""))

    st.subheader("Proposal draft")
    st.markdown(state.get("research_proposal", ""))

    st.session_state.state = state
    _persist_web_session()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Continue to experiments", type="primary"):
            st.session_state.phase = "experiment"
            _persist_web_session()
            st.rerun()
    with col2:
        if st.button("Back to selection", type="secondary"):
            st.session_state.phase = "idea_select"
            _persist_web_session()
            st.rerun()

# ──────────────────────────────────────────────
# Phase: experiment
# ──────────────────────────────────────────────

elif st.session_state.phase == "experiment":
    _render_breadcrumb("experiment")

    state = st.session_state.state

    st.markdown(
        '<p class="aporia-step-label">Step 5</p>',
        unsafe_allow_html=True,
    )
    st.header("Experiment support")

    from agents.experiment_agent import github_search_node, code_modify_node, experiment_node

    completed = (state.get("metadata") or {}).get("ui_completed_nodes", [])
    if not state.get("baseline_code") or "code_modify_node" not in completed:
        with st.status("Scanning open-source baselines...", expanded=True) as exp_status:
            if not state.get("baseline_code"):
                state = _run_ui_node(github_search_node, state)
            repos = state.get("github_repos", []) or []
            st.write(f"Found {len(repos)} candidate repositories.")

            exp_status.update(label="Formulating code adaptation strategy...")
            if "code_modify_node" not in completed:
                state = _run_ui_node(code_modify_node, state)
            st.write("Adaptation strategy generated.")
            exp_status.update(label="Processing complete.", state="complete")
    else:
        st.info("Restored the saved baseline and code-modification results.")

    st.subheader("Recommended baselines")
    st.markdown(state.get("baseline_code", ""))

    st.subheader("Core code modification guidance")
    st.markdown(state.get("core_modification", ""))

    st.divider()

    st.subheader("Paste your experiment results")
    results = st.text_area(
        "Paste results (tables or numbers):",
        placeholder="e.g.,\nOurs: 85.3 mAP on COCO\nBaseline: 82.1 mAP\n...",
        height=150,
    )

    if st.button("Analyze results", disabled=not results):
        state["experiment_results"] = results
        with st.status("Evaluating experimental evidence...", expanded=True) as eval_status:
            state = _run_ui_node(experiment_node, state)
            eval_status.update(label="Analysis complete.", state="complete")
        st.markdown(state.get("ablation_plan", ""))

    st.session_state.state = state
    _persist_web_session()

    if st.button("Continue to writing", type="primary"):
        st.session_state.phase = "writing"
        _persist_web_session()
        st.rerun()

# ──────────────────────────────────────────────
# Phase: writing
# ──────────────────────────────────────────────

elif st.session_state.phase == "writing":
    _render_breadcrumb("writing")

    state = st.session_state.state

    st.markdown(
        '<p class="aporia-step-label">Step 6</p>',
        unsafe_allow_html=True,
    )
    st.header("Writing")

    from agents.writing_agent import outline_node, draft_node, polish_node
    if not state.get("paper_outline"):
        with st.spinner("Structuring manuscript outline..."):
            state = _run_ui_node(outline_node, state)
    else:
        st.info("Restored the saved manuscript outline.")

    st.subheader("Outline")
    st.markdown(state.get("paper_outline", ""))
    st.session_state.state = state
    _persist_web_session()

    if st.button("Generate full draft", type="primary"):
        state = _run_ui_node(_compose_draft, state)
        drafts = state["draft_sections"]
        sections = list(drafts)
        st.session_state.state = state
        _persist_web_session()

        st.success("Draft complete!")
        st.download_button(
            "Download draft (Markdown)",
            data=state["full_draft"],
            file_name="paper_draft.md",
            mime="text/markdown",
            type="primary",
        )

        # Tab-based section display
        section_tabs = st.tabs([s.upper() for s in sections if s in drafts])
        for tab, section in zip(section_tabs, [s for s in sections if s in drafts]):
            with tab:
                st.markdown(drafts[section])

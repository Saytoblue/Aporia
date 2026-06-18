# Author: Saytoblue <Saytoblue@gmail.com>
# Copyright (c) 2026-05-06 Saytoblue


"""
Aporia — Streamlit Web UI
Run: streamlit run app.py
"""

import streamlit as st
import sys
import os

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


# ──────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────

st.set_page_config(
    page_title="Aporia",
    page_icon=_page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

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
    "idea_select": 2,
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
# Sidebar: collapsible config + progress timeline
# ──────────────────────────────────────────────

with st.sidebar:
    with st.expander("Configuration", expanded=False):
        default_provider = (os.environ.get("RESEARCH_AGENT_LLM_PROVIDER") or os.environ.get("LLM_PROVIDER") or "deepseek").strip().lower()
        if default_provider not in ("gemini", "openai", "anthropic", "deepseek"):
            default_provider = "deepseek"
        provider_options = ["deepseek", "gemini", "openai", "anthropic"]
        provider = st.selectbox(
            "LLM Provider",
            options=provider_options,
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

        if provider == "gemini":
            st.caption(f"Effective: provider=gemini | model={os.environ.get('GEMINI_MODEL') or '(not set)'}")
        elif provider == "openai":
            st.caption(f"Effective: provider=openai | model={os.environ.get('OPENAI_MODEL') or '(not set)'}")
        elif provider == "deepseek":
            st.caption(f"Effective: provider=deepseek | model={os.environ.get('DEEPSEEK_MODEL') or '(not set)'} | base={os.environ.get('DEEPSEEK_BASE_URL') or '(not set)'}")
        else:
            st.caption(f"Effective: provider=anthropic | model={os.environ.get('ANTHROPIC_MODEL') or '(not set)'}")
        st.caption(
            "paper_min="
            + str(os.environ.get("RESEARCH_AGENT_PAPER_MIN", ""))
            + " | paper_limit="
            + str(os.environ.get("RESEARCH_AGENT_PAPER_LIMIT", ""))
            + " | rerank_candidates="
            + str(os.environ.get("RESEARCH_AGENT_RERANK_CANDIDATES", ""))
        )

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

    if st.button("Start", type="primary", disabled=not (topic and user_insight and api_key)):
        if not api_key:
            st.error("Please provide an API key in the sidebar first.")
        else:
            st.session_state.state = {
                "topic": topic,
                "user_insight": user_insight,
                "phase": "idea_discovery",
                "user_language": "Auto",
            }
            st.session_state.phase = "running"
            st.rerun()

# ──────────────────────────────────────────────
# Phase: running
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
            profile = _build_profile_from_topic_and_insight(topic, state.get("user_insight", ""))
            if not state.get("friction_points"):
                state["friction_points"] = profile.get("friction_points", []) or []
            if not state.get("motivation"):
                state["motivation"] = profile.get("motivation", "") or ""
            if not state.get("research_taste"):
                state["research_taste"] = profile.get("research_taste", "") or ""
            st.write("Research landscape mapped.")
        except Exception as e:
            st.warning(f"Profile step had an issue: {e}. Continuing.")
            st.write("Research landscape mapped (with warnings).")

        run_status.update(label="Retrieving relevant literature...")
        try:
            from agents.idea_agent import paper_search_node
            state = paper_search_node(state)
            n = len(state.get("raw_papers", []) or [])
            st.write(f"Retrieved {n} papers.")
        except Exception as e:
            st.warning(f"Paper search had an issue: {e}. Continuing with no papers.")
            st.write("Paper search completed (with warnings).")

        run_status.update(label="Synthesizing structural hypotheses...")
        try:
            from agents.idea_agent import direction_synthesis_node
            state = direction_synthesis_node(state)
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

    with st.status("Assessing theoretical novelty...", expanded=True) as refine_status:
        state = gap_analysis_node(state)
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

        state = story_arc_node(state)
        st.write("Story arc constructed.")

        refine_status.update(label="Drafting research proposal...")
        state = proposal_node(state)
        st.write("Proposal draft generated.")
        refine_status.update(label="Refinement complete.", state="complete")

    st.subheader("Story arc")
    st.markdown(state.get("story_arc", ""))

    st.subheader("Proposal draft")
    st.markdown(state.get("research_proposal", ""))

    st.session_state.state = state

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Continue to experiments", type="primary"):
            st.session_state.phase = "experiment"
            st.rerun()
    with col2:
        if st.button("Back to selection", type="secondary"):
            st.session_state.phase = "idea_select"
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

    with st.status("Scanning open-source baselines...", expanded=True) as exp_status:
        state = github_search_node(state)
        repos = state.get("github_repos", []) or []
        st.write(f"Found {len(repos)} candidate repositories.")

        exp_status.update(label="Formulating code adaptation strategy...")
        state = code_modify_node(state)
        st.write("Adaptation strategy generated.")
        exp_status.update(label="Processing complete.", state="complete")

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
            state = experiment_node(state)
            eval_status.update(label="Analysis complete.", state="complete")
        st.markdown(state.get("ablation_plan", ""))

    st.session_state.state = state

    if st.button("Continue to writing", type="primary"):
        st.session_state.phase = "writing"
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

    with st.spinner("Structuring manuscript outline..."):
        from agents.writing_agent import outline_node, draft_node, polish_node
        state = outline_node(state)

    st.subheader("Outline")
    st.markdown(state.get("paper_outline", ""))

    if st.button("Generate full draft", type="primary"):
        write_progress = st.progress(0, text="Preparing to write...")
        sections = ["abstract", "introduction", "related_work", "method", "experiments", "conclusion"]
        drafts = {}

        from langchain_core.messages import HumanMessage, SystemMessage
        from utils.llm_client import get_llm
        llm = get_llm(temperature=0.6)

        for i, section in enumerate(sections):
            pct = int((i + 1) / len(sections) * 100)
            write_progress.progress(pct, text=f"Composing {section} section...")
            resp = llm.invoke([
                SystemMessage(content=f"You are a top-tier conference paper writing expert. Write the {section} section in the user's language (match the language used in the input)."),
                HumanMessage(content=f"Outline: {state.get('paper_outline','')[:600]}\nStory arc: {state.get('story_arc','')[:400]}\nWrite the {section} section."),
            ])
            drafts[section] = resp.content

        state["draft_sections"] = drafts
        state["full_draft"] = "\n\n".join(
            f"## {s.upper()}\n\n{drafts[s]}" for s in sections if s in drafts
        )
        write_progress.progress(100, text="Draft complete.")
        st.session_state.state = state

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

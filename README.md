<div align="center">
  <img src="assets/avatar_geo.png" width="140" alt="Aporia"/>

  # Aporia

  **An agentic assistant from initial intuition to structured paper drafts**

  From a vague research frustration to a breakable assumption, a falsifiable story arc, an annotated core algorithm, and a complete manuscript draft — all within a single multi-agent pipeline.

  [![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
  [![LangGraph](https://img.shields.io/badge/LangGraph-1.x-brightgreen.svg)](https://github.com/langchain-ai/langgraph)
  [![Streamlit](https://img.shields.io/badge/Streamlit-1.57-red.svg)](https://streamlit.io)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

  [Quick Start](#quick-start) · [Workflow](#workflow) · [Architecture](#architecture) · [Configuration](#configuration)

  English | [简体中文](README.zh.md)

</div>

<div align="center">
  <img src="assets/system.png" alt="Aporia system architecture" width="100%"/>
</div>

---

## Why Aporia?

Most AI research tools assume you already have a clear topic. Aporia works at the moment *before* that — when you only have a gut feeling that something is off. It surfaces implicit assumptions, breaks them, and builds a logically closed story arc that leads to a concrete, executable research plan.

## Workflow

Aporia is a **5-phase, LangGraph-driven multi-agent pipeline**:

| Phase | Agent | What it does |
|-------|-------|--------------|
| **1. Input** | — | Capture your research direction and intuition |
| **2. Idea Discovery** | `idea_agent` | Search papers (Semantic Scholar / arXiv), mine implicit assumptions, generate 3 candidate directions |
| **3. Idea Refinement** | `refine_agent` | Break assumptions, reframe problems, construct story arc, run necessity check, draft research proposal |
| **4. Experiment** | `experiment_agent` | Search GitHub / PapersWithCode baselines, generate code modification guidance, analyze results |
| **5. Writing** | `writing_agent` | Outline → section-by-section draft → simulated reviewer feedback |

Each phase preserves state via LangGraph's checkpoint system, allowing pause and resume at any point.

## Key Features

- **Friction-first, not topic-first** — start from what bothers you, not what you've already decided
- **Assumption breaking over gap filling** — directions that challenge a field's premises, not incremental add-ons
- **Story arc with necessity check** — every component must trace to a "because X, we must have Y"
- **Multi-provider LLM** — Gemini / OpenAI / Anthropic / DeepSeek, switchable in the sidebar
- **Card-based direction selection** — clickable cards with live highlight for candidate directions
- **Progress timeline** — sidebar shows current stage with completed / in-progress / pending states
- **Breadcrumb navigation** — always know where you are in the pipeline
- **Live status updates** — `st.status` containers show real-time step-by-step progress
- **Custom spinner** — blue arc indicator replaces native running-man animation
- **Deep space blue theme** — `#0B111D` background, `#3A86FF` accent, geometric avatar
- **Session checkpoints** — pause and resume any node with LangGraph persistence

## Quick Start

### Prerequisites

- Python 3.11+
- At least one LLM API key (DeepSeek, OpenAI, Gemini, or Anthropic)

### Web UI (recommended)

```bash
git clone https://github.com/Saytoblue/Aporia
cd Aporia
pip install -r requirements.txt

cp .env.example .env
# add your API key to .env

streamlit run app.py
```

Open http://localhost:8501. Expand **Configuration** in the sidebar, select your LLM provider, enter your API key, and start a session.

### CLI

```bash
python main.py
# or resume a session:
python main.py --resume SESSION_ID
```

The CLI opens with a single question. Answer naturally — there's no form to fill in. Any language works. A local SQLite checkpoint database is used by default, so the printed session ID can be resumed after restarting the process. The Streamlit UI shows the same kind of session ID in the sidebar, stores it in the URL, and can load another session from that sidebar.

The shared execution graph also journals task attempts and successful model
responses in `RESEARCH_AGENT_CACHE_DIR/operations.sqlite` (default:
`.research_agent_cache/operations.sqlite`). Resuming the same failed task can reuse
saved responses; new dialogue turns, new runs and other sessions get fresh model
calls. Normal dialogue/revision loops are not marked as retries. Literature
searches share a successful-result cache with a one-hour TTL; set
`RESEARCH_AGENT_SEARCH_CACHE_TTL=0` to disable that search cache. PDF downloads
are validated and atomically replaced before reuse.

Keep both the checkpoint database and the cache directory to retain this recovery
behavior. Responses are stored locally; API keys are not part of journal records.
This does not guarantee exactly-once remote calls: a crash before a response is
saved, or simultaneous workers running the same task, can still duplicate calls.
The journal is local even when a remote checkpoint database is configured.

For an opt-in real-model smoke evaluation of the problem-reframing node, configure
one LLM provider first and run:

```bash
python scripts/eval_llm_quality.py --output outputs/llm_eval.json
```

This makes real API calls. The report records provider/model, latency, raw
outputs, and basic lexical smoke checks; it is not a substitute for expert
assessment of scientific quality.

## Architecture

```
User Input (topic + intuition)
        │
        ▼
  agents/orchestrator.py   ← LangGraph state graph (14 nodes, 3 interrupt points)
        │
   ┌────┼────┬────┬────┬────┐
   ▼    ▼    ▼    ▼    ▼    ▼
dialogue  idea  refine  method  experiment  writing
        │
        ▼
  tools/literature_tools.py   +   tools/code_tools.py   ← external APIs
        │
        ▼
  utils/llm_client.py   ← unified LLM client (4 providers)
```

| Directory | Purpose |
|-----------|---------|
| `agents/` | 6 agents: elicitation → discovery → refinement → method → experiment → writing |
| `tools/` | External API calls: Semantic Scholar, arXiv, GitHub, PapersWithCode |
| `utils/` | Infrastructure: `ResearchState` (TypedDict), LLM client factory, checkpoint persistence |
| `prompts/` | Prompt templates for each agent |
| `assets/` | Static resources: avatar, workflow diagram |

## LLM Providers

Aporia supports 4 LLM backends, selectable in the sidebar:

| Provider | Model (configurable) | Notes |
|----------|---------------------|-------|
| **DeepSeek** | deepseek-v4-pro | OpenAI-compatible API; default provider |
| **Gemini** | gemini-1.5-flash | Google Generative AI |
| **OpenAI** | gpt-4o | GPT-4o / GPT-4 / custom base URL |
| **Anthropic** | Claude | Claude series via Anthropic API |

Built-in retry logic handles rate limiting, network errors, and Gemini model fallback.

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | — |
| `DEEPSEEK_MODEL` | DeepSeek model name | deepseek-v4-pro |
| `DEEPSEEK_BASE_URL` | DeepSeek API endpoint | https://api.deepseek.com |
| `GEMINI_API_KEY` | Gemini API key | — |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `ANTHROPIC_API_KEY` | Anthropic API key | — |
| `RESEARCH_AGENT_LLM_PROVIDER` | Default provider | deepseek |
| `RESEARCH_AGENT_PAPER_LIMIT` | Max papers per search | 60 |
| `RESEARCH_AGENT_RERANK_CANDIDATES` | Papers to re-rank | 30 |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar API key (optional) | — |
| `DATABASE_URL` | Checkpoint database URL | `sqlite:///.aporia/checkpoints.sqlite` |
| `APORIA_ALLOW_MEMORY_CHECKPOINTS` | Explicit development-only in-memory fallback | unset |

See `.env.example` for the full list.

## Session management and evidence

CLI and Web outputs are stored in `outputs/<session_id>/`, configurable with
`RESEARCH_AGENT_AUTOSAVE_DIR`. Failed file saves report paths and can be retried
from the checkpoint with the Web **Retry saving outputs** button or
`python main.py --retry-save SESSION_ID`, without model calls. Checkpoint failures
are reported separately, with retry and reload controls in the Web sidebar.

The sidebar includes history, rename, ZIP export, recoverable deletion and cache
maintenance. Equivalent CLI commands require no model API key:

- `python main.py --list-sessions`
- `python main.py --rename SESSION_ID "Study name"`
- `python main.py --export SESSION_ID --export-path study.zip`
- `python main.py --delete SESSION_ID`
- `python main.py --clean-cache --cache-days 30`

Deletion saves state, full checkpoint records and outputs under the cache's
`.trash/` directory first and reports the recovery path. Recovery currently
requires manual work; exported ZIP files are readable data bundles, not directly
importable checkpoint databases. Cache cleanup removes expired shared searches
and completed operations, skipping busy sessions and retaining failed-task retry
responses. It does not remove the paper library, PDFs or legacy untagged model results.

Local file locks serialize each session across CLI/Web processes sharing one
cache directory. Stale browser submissions are rejected and must be reloaded.
This is not a distributed lock across hosts, including when using PostgreSQL.
Legacy state is migrated in the read view and persisted on the next normal write,
preserving pending execution; future schema versions are rejected. PostgreSQL
connections now enter their context, run setup, and close at process exit.

New PDF extraction retains one-based PDF page positions and source text. Legacy
text with no page mapping remains explicitly unlocated. Proposal generation and
revision receive session-scoped evidence IDs, distinguish literature claims from
hypotheses, and report missing provenance or unknown citations. `evidence.json`
and the proposal appendix retain claim links, source locations and quotes.
Links establish traceability, not semantic verification or scientific validity;
coverage is limited by PDF extraction budgets and the catalog size cap.

## Scope

**Applicable:** empirical research involving code — CS (CV / NLP / ML / Systems), computational biology, data science, computational physics/chemistry.

**Not applicable:** pure mathematical proofs, humanities/social-science hermeneutics, clinical trials requiring ethical review.

## Roadmap

- [x] Multi-provider LLM (DeepSeek / Gemini / OpenAI / Anthropic)
- [x] Streamlit Web UI with deep space theme
- [x] Card-based direction selection
- [x] Progress timeline and breadcrumb navigation
- [ ] Evaluation benchmark for idea quality
- [ ] Local model support (Ollama / vLLM) for privacy-sensitive research
- [ ] Implementation decision assistant (backbone, optimizer, hyperparameters with story-arc justification)

## Contributing

One constraint: don't turn this into a form-filling pipeline. The value is in discovering the research question through dialogue. Any change that skips elicitation defeats the purpose.

Most welcome: real usage cases, new Socratic trigger archetypes, domain-specific prompt improvements, evaluation methodology for idea quality.

## License

MIT

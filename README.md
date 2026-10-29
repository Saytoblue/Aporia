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

  [English](#aporia) | [简体中文](#简体中文)

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

---

## 简体中文

[English](#aporia) | 简体中文

### 为什么需要 Aporia？

大多数 AI 科研工具假设你已经有一个明确的课题。Aporia 在你还没有想清楚课题的时候介入——当你只有一种“哪里不对劲”的直觉时。它帮你挖掘隐性假设，打破它们，并构建一个逻辑闭环的故事主线，最终产出可执行的研究计划。

### 工作流程

Aporia 是一个 **5 阶段、基于 LangGraph 的多 Agent 流水线**：

| 阶段 | Agent | 功能 |
|------|-------|------|
| **1. 输入** | — | 输入你的研究方向和直觉 |
| **2. 方向发现** | `idea_agent` | 论文搜索（Semantic Scholar / arXiv），挖掘隐性假设，生成 3 个候选方向 |
| **3. 方向精炼** | `refine_agent` | 打破假设，重构问题，构建故事线，必要性检查，撰写研究提案 |
| **4. 实验支持** | `experiment_agent` | 搜索 GitHub / PapersWithCode 基线仓库，生成代码修改指导，分析实验结果 |
| **5. 论文写作** | `writing_agent` | 大纲 → 逐节撰写 → 模拟审稿反馈 |

每个阶段的运行状态通过侧边栏进度时间线和主体区域的实时状态面板可视化呈现。所有状态通过 LangGraph 检查点系统持久化，支持暂停和恢复。

### 核心特性

- **摩擦优先而非课题优先**：从困扰你的事情出发，而不是已经决定的方向
- **打破假设而非填补空白**：挑战领域前提的方向，而非在现有方法上增量叠加
- **故事主线与必要性检查**：每个组件必须能追溯到“因为 X，所以必须有 Y”
- **多 Provider LLM**：Gemini / OpenAI / Anthropic / DeepSeek，侧边栏可切换
- **交互式方向选择**：通过候选方向卡片进行选择
- **进度时间线与面包屑导航**：查看当前阶段以及已完成、进行中和待处理的步骤
- **实时状态更新**：页面展示逐步处理进度
- **会话断点续传**：基于 LangGraph 检查点暂停和恢复研究会话
- **会话管理与证据追溯**：支持会话导出、备份删除，并为提案保留文献来源和页码

### 快速开始

#### 环境要求

- Python 3.11+
- 至少一个 LLM API Key（DeepSeek、OpenAI、Gemini 或 Anthropic）

#### Web 界面（推荐）

```bash
git clone https://github.com/Saytoblue/Aporia
cd Aporia
pip install -r requirements.txt

cp .env.example .env
# 在 .env 中填入你的 API Key

streamlit run app.py
```

打开 http://localhost:8501，在侧边栏配置 LLM Provider 和 API Key 后即可开始。

#### 命令行

```bash
python main.py
# 恢复之前的会话：
python main.py --resume SESSION_ID
```

会话从一个问题开始，自然地回答即可，无需填写表单，支持任意语言。默认使用本地 SQLite 保存检查点，重新启动程序后可以通过 session ID 恢复。Streamlit 网页也会在 URL 中保存 session ID，并允许从侧边栏加载其他会话。

共享执行图会把任务尝试记录和成功的模型响应保存到 `RESEARCH_AGENT_CACHE_DIR/operations.sqlite`（默认：`.research_agent_cache/operations.sqlite`）。恢复同一失败任务时可复用已保存响应；新对话轮次、新运行和其他会话仍会重新调用模型。文献搜索成功结果默认缓存一小时，可设置 `RESEARCH_AGENT_SEARCH_CACHE_TTL=0` 关闭。PDF 下载经过有效性检查后再原子替换缓存文件。

保留检查点数据库和缓存目录才能保留恢复能力。模型响应会存储在本地，日志不包含 API Key。这不能保证远端调用恰好一次：响应保存前崩溃或多个进程同时执行同一任务，仍可能造成重复调用。即使使用远端检查点数据库，操作日志仍保存在本地。

如需对真实模型执行可选的质量冒烟评测，先配置一个 LLM Provider，再运行：

```bash
python scripts/eval_llm_quality.py --output outputs/llm_eval.json
```

该命令会真实调用 API。报告记录 Provider/模型、耗时、原始输出和基础词汇检查；这些指标不能替代专家对科学质量的评审。

### 架构

```text
用户输入（课题 + 直觉）
        │
        ▼
  agents/orchestrator.py   ← LangGraph 状态图（14 节点，3 个人工交互点）
        │
   ┌────┼────┬────┬────┬────┐
   ▼    ▼    ▼    ▼    ▼    ▼
dialogue  idea  refine  method  experiment  writing
        │
        ▼
  tools/literature_tools.py + tools/code_tools.py   ← 外部 API
        │
        ▼
  utils/llm_client.py   ← 统一 LLM 客户端（4 个 Provider）
```

| 目录 | 用途 |
|------|------|
| `agents/` | 6 个 Agent：引导、发现、精炼、方法、实验和写作 |
| `tools/` | 外部 API：Semantic Scholar、arXiv、GitHub、PapersWithCode |
| `utils/` | 基础设施：ResearchState、LLM 客户端、检查点持久化 |
| `prompts/` | 各 Agent 的 Prompt 模板 |
| `assets/` | 静态资源：头像和流程图 |

### LLM Provider

| Provider | 模型（可配置） | 说明 |
|----------|--------------|------|
| **DeepSeek** | deepseek-v4-pro | OpenAI 兼容 API；默认 Provider |
| **Gemini** | gemini-1.5-flash | Google Generative AI |
| **OpenAI** | gpt-4o | 支持 GPT-4o / GPT-4 / 自定义 Base URL |
| **Anthropic** | Claude | 通过 Anthropic API 使用 Claude 系列 |

内置重试逻辑处理限流和网络错误，Gemini 支持模型自动回退。

### 配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — |
| `DEEPSEEK_MODEL` | DeepSeek 模型名称 | deepseek-v4-pro |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | https://api.deepseek.com |
| `GEMINI_API_KEY` | Gemini API 密钥 | — |
| `OPENAI_API_KEY` | OpenAI API 密钥 | — |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | — |
| `RESEARCH_AGENT_LLM_PROVIDER` | 默认 Provider | deepseek |
| `RESEARCH_AGENT_PAPER_LIMIT` | 每次搜索最大论文数 | 60 |
| `RESEARCH_AGENT_RERANK_CANDIDATES` | 重排序候选数 | 30 |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar API 密钥（可选） | — |
| `DATABASE_URL` | 检查点数据库 URL | `sqlite:///.aporia/checkpoints.sqlite` |
| `APORIA_ALLOW_MEMORY_CHECKPOINTS` | 仅开发环境使用的内存回退 | 未设置 |

完整列表见 `.env.example`。

### 会话管理与证据追溯

CLI 和网页的研究产物统一保存在 `outputs/<session_id>/`（可通过 `RESEARCH_AGENT_AUTOSAVE_DIR` 修改根目录）。保存失败会显示具体路径；网页可点击 **Retry saving outputs**，CLI 可运行 `python main.py --retry-save SESSION_ID`，从检查点重新导出而无需再次调用模型。检查点写入失败与产物写入失败会分别提示。

网页侧边栏提供历史会话、重命名、ZIP 导出、备份删除和缓存清理。CLI 对应命令如下，管理命令不需要模型 API Key：

- `python main.py --list-sessions`
- `python main.py --rename SESSION_ID "研究名称"`
- `python main.py --export SESSION_ID --export-path study.zip`
- `python main.py --delete SESSION_ID`
- `python main.py --clean-cache --cache-days 30`

删除前会在缓存目录 `.trash/` 中保存状态、完整检查点记录及产物；目前需要人工恢复。ZIP 导出是可阅读的数据包，不是可直接导入运行的检查点数据库。缓存清理只处理过期共享搜索结果和已完成任务，会跳过运行中的会话并保留失败任务的重试响应；不会清理论文库或 PDF，也会保留旧版未标记会话归属的模型缓存。

同一会话使用本机文件锁，防止 CLI、网页或多个标签页同时运行。过期页面提交会被拒绝并提示重新加载。该机制只适用于共享同一个本地缓存目录的进程，不提供跨主机分布式锁；使用 PostgreSQL 也不会改变这一点。旧版 State 会在读取时兼容迁移，并在下次正常写入时保存版本；更高的未知版本会被拒绝。PostgreSQL 连接会执行初始化并在进程退出时关闭。

新提取的 PDF 会保留从 1 开始的页码和原文片段；缺少页码的旧缓存会明确标为未定位。提案和修订使用会话级证据编号，区分文献主张与研究假设，并提示缺少来源或引用未知等情况。`evidence.json` 和提案附录保存主张、来源、页码和原文。可追溯来源不代表系统已验证来源在语义上支持该结论；覆盖范围也受 PDF 提取预算和证据数量上限影响。

### 适用范围

**适用：** 涉及代码实现的实证研究，例如计算机科学（CV / NLP / ML / 系统）、计算生物学、数据科学、计算物理和计算化学。

**不适用：** 纯数学证明、人文社科诠释学研究，以及需要伦理审查的临床试验。

### 路线图

- [x] 多 Provider LLM（DeepSeek / Gemini / OpenAI / Anthropic）
- [x] Streamlit Web UI
- [x] 候选方向选择与流程进度显示
- [ ] 想法质量评估基准
- [ ] 本地模型支持（Ollama / vLLM），用于隐私敏感研究
- [ ] 实现决策助手（主干网络、优化器、超参数建议及故事主线理由）

### 贡献指南

请不要把 Aporia 变成填表流水线。它的价值在于通过对话发现研究问题，任何跳过引导过程的改动都会削弱这一点。欢迎真实使用案例、新的苏格拉底式触发原型、领域 Prompt 改进和想法质量评估方法。

### 许可证

MIT

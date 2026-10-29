<div align="center">
  <img src="assets/avatar_geo.png" width="140" alt="Aporia"/>

  # Aporia

  **从模糊直觉到结构化论文草稿的智能助手**

  将研究者模糊的痛点，转化为可打破的假设、可证伪的故事主线、带注释的核心算法代码，以及完整的论文草稿——全程在一个多 Agent 流水线中完成。

  [![Python 3.10+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
  [![LangGraph](https://img.shields.io/badge/LangGraph-1.x-brightgreen.svg)](https://github.com/langchain-ai/langgraph)
  [![Streamlit](https://img.shields.io/badge/Streamlit-1.57-red.svg)](https://streamlit.io)
  [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

  [快速开始](#快速开始) · [工作流程](#工作流程) · [架构](#架构) · [配置](#配置)

  [English](README.md) | 简体中文

</div>

<div align="center">
  <img src="assets/system.png" alt="Aporia 系统架构图" width="100%"/>
</div>

---

## 为什么需要 Aporia？

大多数 AI 科研工具假设你已经有一个明确的课题。Aporia 在你还没有想清楚课题的时候介入——当你只有一种"哪里不对劲"的直觉时。它帮你挖掘隐性假设，打破它们，并构建一个逻辑闭环的故事主线，最终产出可执行的研究计划。

## 工作流程

Aporia 是一个 **5 阶段、基于 LangGraph 的多 Agent 流水线**：

| 阶段 | Agent | 功能 |
|------|-------|------|
| **1. 输入** | — | 输入你的研究方向和直觉 |
| **2. 方向发现** | `idea_agent` | 论文搜索（Semantic Scholar / arXiv），挖掘隐性假设，生成 3 个候选方向 |
| **3. 方向精炼** | `refine_agent` | 打破假设，重构问题，构建故事线，必要性检查，撰写研究提案 |
| **4. 实验支持** | `experiment_agent` | 搜索 GitHub / PapersWithCode 基线仓库，生成代码修改指导，分析实验结果 |
| **5. 论文写作** | `writing_agent` | 大纲 → 逐节撰写 → 模拟审稿反馈 |

每个阶段的运行状态通过侧边栏进度时间线和主体区域的实时状态面板可视化呈现。所有状态通过 LangGraph 检查点系统持久化，支持随时暂停和恢复。

## 核心特性

- **摩擦优先而非课题优先** — 从困扰你的事情出发，而不是已经决定的方向
- **打破假设而非填补空白** — 挑战领域前提的方向，而非在现有方法上增量叠加
- **故事主线与必要性检查** — 每个组件必须能追溯到"因为 X，所以必须有 Y"
- **多 Provider LLM** — Gemini / OpenAI / Anthropic / DeepSeek 四合一，侧边栏一键切换
- **卡片式方向选择** — 可点击卡片，选中时蓝色高亮
- **进度时间线** — 侧边栏可视化当前阶段，已完成/进行中/待进行三态区分
- **面包屑导航** — 始终知道自己在流水线中的位置
- **实时状态更新** — `st.status` 容器展示逐步处理进度
- **自定义旋转指示器** — 蓝色弧线替代原生运行中图标
- **深空静谧蓝主题** — `#0B111D` 背景，`#3A86FF` 强调色，几何风格头像
- **会话断点续传** — 基于 LangGraph 持久化，任意节点可暂停恢复

## 快速开始

### 环境要求

- Python 3.11+
- 至少一个 LLM API Key（DeepSeek、OpenAI、Gemini 或 Anthropic）

### Web 界面（推荐）

```bash
git clone https://github.com/Saytoblue/Aporia
cd Aporia
pip install -r requirements.txt

cp .env.example .env
# 在 .env 中填入你的 API Key

streamlit run app.py
```

打开 http://localhost:8501。在侧边栏展开 **Configuration**，选择 LLM provider，输入 API Key，即可开始。

### 命令行

```bash
python main.py
# 或恢复之前的会话：
python main.py --resume SESSION_ID
```

会话以单个问题开始。自然地回答即可——无需填写任何表单，支持任意语言。默认使用本地 SQLite 保存检查点，因此重新启动程序后可以使用终端显示的 session ID 恢复。Streamlit 网页侧边栏也会显示 session ID，并将其放入 URL；刷新网页或重新打开 URL 后可以恢复，也可以在侧边栏加载其他会话。

共享执行图还会把任务尝试次数和模型成功响应保存到
`RESEARCH_AGENT_CACHE_DIR/operations.sqlite`（默认是
`.research_agent_cache/operations.sqlite`）。同一失败任务恢复时可以复用已保存的响应；
新的对话轮次、新一轮运行及其他会话会重新调用模型。正常的对话或修改循环不会被标记为重试。
文献搜索会缓存成功结果，默认有效期一小时；设置
`RESEARCH_AGENT_SEARCH_CACHE_TTL=0` 可关闭搜索缓存。PDF 会经过有效性检查，再原子替换缓存文件。

保留检查点数据库和缓存目录，才能保留上述恢复能力。模型响应会存储在本地，日志记录不包含 API 密钥。
这不能保证远端调用恰好一次：响应尚未保存时发生崩溃，或多个进程同时执行同一任务，仍可能重复调用。
即使使用远端检查点数据库，这份操作日志仍是本地存储。

如需对真实模型执行可选的质量冒烟评测，先配置一个 LLM provider，再运行：

```bash
python scripts/eval_llm_quality.py --output outputs/llm_eval.json
```

该命令会真实调用 API。报告会记录 provider/model、耗时、原始输出和基础词汇检查；这些指标不能替代专家对科学正确性和研究价值的评审。

## 架构

```
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
  tools/literature_tools.py   +   tools/code_tools.py   ← 外部 API
        │
        ▼
  utils/llm_client.py   ← 统一 LLM 客户端（4 个 Provider）
```

| 目录 | 用途 |
|------|------|
| `agents/` | 6 个 Agent：引导 → 发现 → 精炼 → 方法 → 实验 → 写作 |
| `tools/` | 外部 API 调用：Semantic Scholar、arXiv、GitHub、PapersWithCode |
| `utils/` | 基础设施：ResearchState（TypedDict）、LLM 客户端工厂、检查点持久化 |
| `prompts/` | 各 Agent 的 Prompt 模板 |
| `assets/` | 静态资源：头像、流程图 |

## LLM Provider

Aporia 支持 4 种 LLM 后端，在侧边栏下拉切换：

| Provider | 模型（可配置） | 说明 |
|----------|--------------|------|
| **DeepSeek** | deepseek-v4-pro | OpenAI 兼容 API；默认 provider |
| **Gemini** | gemini-1.5-flash | Google Generative AI |
| **OpenAI** | gpt-4o | GPT-4o / GPT-4 / 自定义 base URL |
| **Anthropic** | Claude | Claude 系列，通过 Anthropic API |

内置自动重试逻辑处理限流、网络错误，Gemini 支持模型自动回落。

## 配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — |
| `DEEPSEEK_MODEL` | DeepSeek 模型名称 | deepseek-v4-pro |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | https://api.deepseek.com |
| `GEMINI_API_KEY` | Gemini API 密钥 | — |
| `OPENAI_API_KEY` | OpenAI API 密钥 | — |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥 | — |
| `RESEARCH_AGENT_LLM_PROVIDER` | 默认 provider | deepseek |
| `RESEARCH_AGENT_PAPER_LIMIT` | 每次搜索最大论文数 | 60 |
| `RESEARCH_AGENT_RERANK_CANDIDATES` | 重排序候选数 | 30 |
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar API 密钥（可选） | — |
| `DATABASE_URL` | 检查点数据库 URL | `sqlite:///.aporia/checkpoints.sqlite` |
| `APORIA_ALLOW_MEMORY_CHECKPOINTS` | 仅开发环境使用的内存回退 | 未设置 |

完整列表见 `.env.example`。

## 会话管理与证据追溯

CLI 和网页的研究产物统一保存在 `outputs/<session_id>/`（可通过
`RESEARCH_AGENT_AUTOSAVE_DIR` 改变根目录），包括状态、提案、核心代码及证据清单。
保存失败会显示具体路径；网页可点击 **Retry saving outputs**，CLI 可使用
`python main.py --retry-save SESSION_ID` 从检查点重新导出，无需再次调用模型。
检查点写入失败与产物写入失败分别提示；网页也提供检查点重试及重新加载按钮。

网页侧边栏提供历史会话、重命名、ZIP 导出、删除和过期缓存清理。CLI 对应命令：

- `python main.py --list-sessions`
- `python main.py --rename SESSION_ID "研究名称"`
- `python main.py --export SESSION_ID --export-path study.zip`
- `python main.py --delete SESSION_ID`
- `python main.py --clean-cache --cache-days 30`

管理命令不需要模型密钥。删除前先在缓存目录 `.trash/` 中保存状态、完整检查点记录及产物，
成功后显示备份路径；目前备份供人工恢复，尚无一键导入。ZIP 导出是可阅读的数据包，
不是可直接导入运行的检查点数据库。清理仅针对过期共享搜索结果和已完成任务，
会跳过运行中的会话并保留失败任务的重试响应；不会清理论文库或 PDF。
旧版未标记会话归属的模型缓存会保留。

同一会话采用本机文件锁，防止 CLI/网页或多个标签页同时运行。
过期页面提交会被拒绝并提示重新加载。该机制适用于共享同一个本地缓存目录的进程，
不提供跨主机的分布式锁；配置 PostgreSQL 也不会改变这一点。
旧 State 在读取时兼容迁移，在下次正常写入时保存版本，保留原有待执行节点；
遇到高于当前支持版本的状态会拒绝写入。PostgreSQL 连接会正确进入上下文、执行 setup 并在退出时关闭。

新读取的 PDF 保留从 1 开始的 PDF 页位置及原文片段，旧缓存缺页码时标为未定位。
提案与修订使用当前会话的证据编号，区分文献主张和研究假设；无证据、未知引用或缺少
结构化主张记录时会显示警告。`evidence.json` 和提案附录记录主张、来源、页码及原文。
引用关联只代表能定位来源，不代表已自动验证其语义支持或研究结论；覆盖范围还受 PDF 提取预算和证据条数上限影响。

## 适用范围

**适用：** 涉及代码实现的实证研究——计算机科学（CV / NLP / ML / 系统）、计算生物学、数据科学、计算物理/化学。

**不适用：** 纯数学证明、人文社科诠释学研究、需要伦理审查的临床试验。

## 路线图

- [x] 多 Provider LLM（DeepSeek / Gemini / OpenAI / Anthropic）
- [x] Streamlit Web UI（深空蓝主题）
- [x] 卡片式方向选择
- [x] 进度时间线和面包屑导航
- [ ] 想法质量评估基准
- [ ] 本地模型支持（Ollama / vLLM），用于隐私敏感研究
- [ ] 实现决策助手（主干网络、优化器、超参推荐，附故事主线理由）

## 贡献指南

唯一约束：不要将其变成一个填表流水线。设计的核心在于 AI 如何为人类思维插上翅膀。价值在于通过对话发现研究问题。任何跳过或简化引导过程的改动都违背了初衷。

最欢迎：真实使用案例、新的苏格拉底式触发原型、领域特定 Prompt 优化、想法质量的评估方法论。

## License

MIT

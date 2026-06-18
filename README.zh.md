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
git clone https://github.com/Paradoxtcal/Aporia
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

会话以单个问题开始。自然地回答即可——无需填写任何表单，支持任意语言。

## 架构

```
用户输入（课题 + 直觉）
        │
        ▼
  agents/orchestrator.py   ← LangGraph 状态图（7 节点，3 个人工交互点）
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
| `agents/` | 7 个 Agent：引导 → 发现 → 精炼 → 方法 → 实验 → 写作 |
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

完整列表见 `.env.example`。

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

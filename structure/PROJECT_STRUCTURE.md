# Aporia 项目结构详解

Aporia 是一个 **AI 驱动的学术研究助手**，覆盖从 idea 发现到论文写作的完整 Phase-0 流程。基于 LangGraph 多 Agent 编排，支持 CLI (`main.py`) 和 Web UI (`app.py`) 两种入口方式。

---

## 根目录文件

| 文件 | 用途 |
|---|---|
| **`main.py`** | **CLI 入口**，交互式命令行流程：苏格拉底式引导 → 想法发现 → 方向选择 → 论文精炼 → 核心代码生成。自动保存中间状态（`research_state.json`, `core_algorithm.py`, `research_proposal.md`），支持 `--resume` 断点续跑和 `--compress-pdfs` PDF 压缩 |
| **`app.py`** | **Streamlit Web UI 入口**，提供完整的图形化界面，5 步流程（输入 → 想法发现 → 选择 → 精炼 → 实验 → 写作），支持侧边栏配置 LLM provider 和 API Key |
| **`requirements.txt`** | Python 依赖清单：LangGraph/LangChain 系列、OpenAI/Google GenAI、PDF 处理（pikepdf/pypdf/Pillow）、Streamlit 等 |
| **`.env.example`** | 环境变量模板，配置 LLM provider、API Key、论文搜索参数等 |
| **`LICENSE`** | 许可证文件 |
| **`README.md`** / **`README.zh.md`** | 项目说明文档（英文/中文） |

---

## `agents/` — Agent 层（核心业务逻辑）

基于 LangGraph 的多 Agent 协作，由 `orchestrator.py` 编排为状态图。

| 文件 | 对应阶段 | 功能 |
|---|---|---|
| **`orchestrator.py`** | 全局编排 | 构建 LangGraph 状态图，定义节点顺序：`elicit` → `idea_discovery` → `idea_refine` → `assumption_breaking` → `problem_reframing` → `story_arc` → `necessity_check` → `proposal` → `generate_core_code`。在 3 个人工交互点设置 `interrupt_before` 等待用户输入 |
| **`dialogue_agent.py`** | Phase 0: Elicit | 苏格拉底式提问，1-3 轮对话将用户的模糊直觉转化为结构化的研究者画像（摩擦点、动机、约束、研究品味） |
| **`idea_agent.py`** | Phase 1: Idea Discovery | 论文搜索 + 方向合成。从 Semantic Scholar/arXiv 搜索论文，LLM 重排序相关性，挖掘隐式假设，生成 3 个打破不同假设的候选研究方向 |
| **`refine_agent.py`** | Phase 2: Idea Refinement | 方向精炼：隐式假设挖掘 → 问题重构 → 故事线构建 → 必要性检查（Necessity/Sufficiency/Counterexample 三测试） → 研究提案生成 |
| **`method_agent.py`** | Phase 2: Core Code | 生成核心算法代码（Python/PyTorch 风格），标注 `# WHY`（设计决策）和 `# DIFF`（与基线差异），输出可直接交给 Cursor/Claude Code 的集成指令 |
| **`experiment_agent.py`** | Phase 3: Experiment | GitHub/PapersWithCode 搜索基线仓库 → 推荐 top 3 + 修改策略 → 生成代码修改指导 → 实验结果分析（判断可发表性 A/B/C/D） |
| **`writing_agent.py`** | Phase 4: Writing | 论文大纲 → 分节撰写（abstract ~ conclusion） → 模拟 NeurIPS Area Chair 审稿，给出修改反馈 |

---

## `tools/` — 工具层（外部 API 调用）

| 文件 | 功能 |
|---|---|
| **`literature_tools.py`** | 文献搜索：Semantic Scholar API（关键词搜索） + arXiv API（最新论文），支持 PDF 下载/文本提取/全文缓存，论文库 JSON 持久化 |
| **`code_tools.py`** | 代码搜索：GitHub Search API（按 star 排序）+ Papers with Code API，查找带官方代码的论文仓库 |

---

## `utils/` — 工具层（基础设施）

| 文件 | 功能 |
|---|---|
| **`state.py`** | `ResearchState` TypedDict 定义，包含全部状态字段：topic、friction_points、raw_papers、candidate_directions、story_arc、core_modification、full_draft 等 |
| **`llm_client.py`** | LLM 客户端工厂，支持 Gemini / OpenAI / Anthropic / Ollama。包含自动重试（限流/网络错误）、Gemini 模型回落、无效 API Key 检测 |
| **`memory.py`** | Checkpointer 选择器：默认 MemorySaver，可选 SQLite/PostgreSQL 持久化 |

---

## `prompts/` — Prompt 模板

| 文件 | 功能 |
|---|---|
| **`idea_prompts.py`** | 所有核心 prompt 模板：文献综述、假设打破、问题重构、故事线、必要性检查、提案、写作系统 prompt、ChatGPT 文献分析模板 |
| **`refine_prompts.py`** | 重导出 `idea_prompts.py` 的 prompt（给 refine_agent 使用） |
| **`experiment_prompts.py`** | Phase 3 占位（实际复用 idea_prompts） |
| **`writing_prompts.py`** | 导出 `WRITING_SYSTEM_PROMPT`（给 writing_agent 使用） |

---

## `scripts/` — 脚本工具

| 文件 | 功能 |
|---|---|
| **`compress_pdfs.py`** | 批量 PDF 压缩打包：使用 pikepdf + Pillow 压缩图片/重采样/去元数据，输出 ZIP 供 ChatGPT 上传分析 |

---

## `assets/` — 静态资源

`avatar_geo.png` / `avatar_geo.svg` / `workflow.jpg` — App 图标和工作流程图

---

## 数据流总览

```
用户输入 (topic + insight)
    │
    ▼
dialogue_agent (苏格拉底提问 → 研究者画像)
    │
    ▼
idea_agent (论文搜索 + 假设挖掘 → 3 个候选方向)
    │
    ▼
[用户选择方向]
    │
    ▼
refine_agent (假设打破 → 故事线 → 提案)
    │
    ▼
method_agent (核心代码生成)
    │
    ▼
experiment_agent (基线搜索 + 代码修改指导)
    │
    ▼
writing_agent (大纲 → 草稿 → 审稿反馈)
```

# Aporia 技术栈

## 编排 & Agent 框架

- **LangGraph** — 核心框架，用有向状态图编排多 Agent 协作（`agents/orchestrator.py`），支持 `interrupt_before` 人工交互点
- **LangChain** — LLM 调用封装（`langchain-core`, `langchain-community`）

## LLM 接入

| Provider   | SDK                          | 说明                          |
|------------|------------------------------|-------------------------------|
| OpenAI     | langchain-openai             | GPT-4o / DeepSeek 等 OpenAI 兼容 API |
| Gemini     | langchain-google-genai       | Google Generative AI          |
| Anthropic  | langchain-anthropic          | Claude 系列                   |
| DeepSeek   | langchain-openai（兼容模式）    | 通过 ChatOpenAI + 自定义 base URL |
| Ollama     | langchain-community          | 本地模型                      |

自建 `_RetryingLLM` 重试层：限流/网络错误自动重试、Gemini 模型自动回落、无效 API Key 检测。

## UI

| 入口      | 技术        | 说明                                    |
|-----------|------------|----------------------------------------|
| Web UI    | Streamlit  | 侧边栏配置、多步骤流程、状态指示（`app.py`）    |
| CLI       | Python     | 交互式命令行，支持 `--resume` 断点续跑（`main.py`） |

## 状态管理

- **LangGraph Checkpointer** — `MemorySaver`（内存）/ `SqliteSaver` / `PostgresSaver` 持久化
- **TypedDict** — `ResearchState` 定义全流程 60+ 状态字段（`utils/state.py`）
- **Streamlit Session State** — Web 端临时保持

## 外部工具 & API

| API                     | 用途                  |
|-------------------------|---------------------|
| Semantic Scholar API    | 经典论文检索              |
| arXiv API               | 最新论文检索              |
| GitHub Search API       | 基线仓库搜索              |
| Papers with Code API    | 带官方代码的论文查找          |

## PDF & 数据处理

- **pypdf** — PDF 文本提取
- **pikepdf + Pillow** — PDF 批量压缩
- **requests / httpx** — HTTP 请求

## 其他依赖

- **python-dotenv** — 环境变量管理
- **pydantic** — 数据校验

---

> 纯 Python 生态，无前端构建工具，无数据库强依赖（可选的 SQLite/PostgreSQL 持久化）。

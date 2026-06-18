# Aporia 目录结构

```
Aporia/
│
├── main.py                     CLI 入口（交互式命令行，支持 --resume 断点续跑）
├── app.py                      Streamlit Web UI 入口（5 步流程可视化界面）
│
├── agents/                     Agent 层 — 核心业务逻辑
│   ├── orchestrator.py         全局编排器（LangGraph 状态图，7 节点 + 3 人工交互点）
│   ├── dialogue_agent.py       Phase 0: 苏格拉底式提问 → 研究者画像
│   ├── idea_agent.py           Phase 1: 论文搜索 + 方向合成 → 3 个候选方向
│   ├── refine_agent.py         Phase 2: 假设打破 → 故事线 → 必要性检查 → 提案
│   ├── method_agent.py         Phase 2: 生成核心算法代码（# WHY / # DIFF 标注）
│   ├── experiment_agent.py     Phase 3: GitHub 基线搜索 + 代码修改指导 + 结果分析
│   └── writing_agent.py        Phase 4: 大纲 → 分节撰写 → 模拟审稿反馈
│
├── tools/                      工具层 — 外部 API 调用
│   ├── literature_tools.py     Semantic Scholar / arXiv 论文搜索，PDF 下载/提取/缓存
│   └── code_tools.py           GitHub Search / Papers with Code 代码仓库搜索
│
├── utils/                      工具层 — 基础设施
│   ├── state.py                ResearchState TypedDict（60+ 字段，全流程状态）
│   ├── llm_client.py           LLM 工厂：Gemini / OpenAI / Anthropic / DeepSeek / Ollama
│   └── memory.py               Checkpointer：MemorySaver / SQLite / PostgreSQL
│
├── prompts/                    Prompt 模板
│   ├── idea_prompts.py         文献综述、假设打破、问题重构、故事线、提案 prompt
│   ├── refine_prompts.py       重导出（给 refine_agent）
│   ├── experiment_prompts.py   Phase 3 占位
│   └── writing_prompts.py      论文写作系统 prompt
│
├── scripts/                    脚本工具
│   └── compress_pdfs.py        PDF 批量压缩打包（pikepdf + Pillow）
│
├── assets/                     静态资源
│   ├── avatar_geo.png / .svg   项目头像（几何风格）
│   └── workflow.jpg            工作流程图
│
├── .env / .env.example         环境变量配置（API Key、Provider、搜索参数）
├── requirements.txt            Python 依赖清单
├── LICENSE                     MIT 许可证
├── README.md / README.zh.md   项目文档（英文 / 中文）
└── PROJECT_STRUCTURE.md        项目结构说明
```

## 分层架构

```
用户输入 (topic + insight)
        │
        ▼
  agents/orchestrator.py  ←  LangGraph 状态图编排
        │
   ┌────┼────┬────┬────┐
   ▼    ▼    ▼    ▼    ▼
dialogue idea refine method experiment writing  ← 各 Agent 节点
        │
        ▼
  tools/literature_tools.py  +  tools/code_tools.py  ← 外部 API
        │
        ▼
  utils/llm_client.py  ←  LLM 调用（多 Provider 统一接口）
```

## 各 Agent 职责

| Agent              | 阶段       | 输入                          | 输出                          |
|--------------------|-----------|------------------------------|------------------------------|
| dialogue_agent     | Phase 0   | 用户模糊直觉                     | 研究者画像（摩擦点、动机、品味）   |
| idea_agent         | Phase 1   | 研究者画像                      | 3 个候选研究方向                  |
| refine_agent       | Phase 2   | 选定方向 + 论文摘要               | 假设分析 + 故事线 + 研究提案       |
| method_agent       | Phase 2   | 研究提案                       | 核心算法代码（带 WHY/DIFF 标注）   |
| experiment_agent   | Phase 3   | 提案 + 核心代码                  | 基线推荐 + 修改指导 + 结果分析      |
| writing_agent      | Phase 4   | 提案 + 实验结果                  | 论文大纲 + 分节草稿 + 审稿反馈     |

## 数据流

```
Phase 0: Elicit           模糊直觉 → 结构化研究者画像
Phase 1: Idea Discovery   论文搜索 + 假设挖掘 → 3 个候选方向
        [用户选择方向]
Phase 2: Idea Refinement  假设打破 → 问题重构 → 故事线 → 必要性检查 → 提案
Phase 3: Experiment       基线搜索 + 代码修改指导 + 实验结果分析
Phase 4: Writing          大纲 → 分节撰写 → 模拟审稿反馈
```

# 20 · 开源科研 Agent 框架调研：浙大 SciToolAgent、西湖 DeepScientist 与可落地技术栈

> 版本：v0.1 · 日期：2026-10-23 · 性质：开源框架调研 + 工程反思  
> 目的：回答“现有开源科研 Agent 到底怎么搭、用了什么前后端、哪些能借、哪些不能借”，作为 [21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md) 的技术输入。  
> 证据纪律：仓库语言/目录/package.json 为 2026-10-23 通过 GitHub 公开 API 读取；论文与二手报道只用于定位，不把外部效果数字当作本项目结果。`SIM` 与“未实测”保持原标注。

---

## 0. 结论先行

1. **浙大最直接相关的开源科研 Agent 是 `SciToolAgent`（HICAI-ZJU，张强团队）**，不是 DeepScientist。它把 500+ 科学工具组织成 `SciToolKG`，用 Planner / Executor / Summarizer + 安全检查完成多工具编排；代码是 Python + FastAPI，偏 API/工具层，不是一个完整的论文写作前端。
2. **DeepScientist、CycleResearcher 是西湖大学张岳团队（WestlakeNLP）的工作**，常被误认为浙大；AiraXiv 是西湖/浙大等合作署名的 AI 开放获取平台，不是 Agent 框架。DeepScientist 的本地优先 daemon + React UI + `skills/` 目录，是现有开源里最接近我们目标形态的工程参考。
3. **现有开源框架的常见技术栈是**：Python 执行引擎（FastAPI / CLI / Gradio）+ Docker / 运行目录 + TypeScript/React 或简单 Web UI + 模型 API；有研究价值的往往是 **run harness、工具/技能目录、评测与记忆**，不是前端本身。
4. **它们普遍缺的不是“更多 Agent”，而是**：claim–证据闭合、变更后的维护、隐藏评测隔离、技能的供应链安全、人类签署的强制点。这正好是我们的空位。
5. **可落地栈**（详见 [21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md)）：Vite + React/TS 前端；FastAPI + Pydantic + Python worker；Postgres + Redis + 对象存储；Docker 沙箱；DeepSeek（OpenAI 兼容）+ LiteLLM/模型网关；SSE；Playwright/Pytest。不是 Next.js 全家桶，也不是 10 微服务。

---

## 1. 调研方法与证据等级

| 等级 | 含义 | 本文用法 |
| --- | --- | --- |
| `[仓库已核验]` | 通过 GitHub API 读取仓库存在、语言构成、顶层目录或 package.json | 用于技术栈判断 |
| `[论文/项目页]` | arXiv、Nature、官方项目页或官方文档 | 用于定位架构与声明 |
| `[二手报道]` | CSDN、Toutiao、榜单文章 | 只用于发现名字/线索，不引用效果数字 |
| `[分析]` | 本文判断 | 明确标注，不作为事实 |

**限制**：没有逐行阅读所有仓库，也没有运行任何外部系统；语言构成只能说明“主要实现语言”，不能说明架构质量。本调研不比较效果数字，不引用 star 数作为质量证据。

---

## 2. 先把“浙大”与“西湖”分清

### 2.1 浙大：SciToolAgent（HICAI-ZJU）

- **项目**：`SciToolAgent: A Knowledge Graph-Driven Scientific Agent for Multi-Tool Integration`
- **单位**：浙江大学 HICAI-ZJU / 张强团队；与昇思 MindSpore 生态合作。
- **论文**：Nature Computational Science（2025）；代码：[HICAI-ZJU/SciToolAgent](https://github.com/HICAI-ZJU/SciToolAgent)。
- **要解决的问题**：科学工具太多、接口/依赖/版本复杂；让 LLM 能选工具、排工具链、执行并总结。
- **架构要点**：
  1. **SciToolKG**：把工具的功能、输入输出、依赖、兼容性与安全属性组织成知识图谱；
  2. **Planner**：基于图谱检索增强，生成工具链；
  3. **Executor**：按序调用工具，失败时重试/调整；
  4. **Summarizer**：汇总多个工具输出，必要时让 Planner 重规划；
  5. **安全审查**：在工具执行前后做毒性/安全阈值检查；
  6. **记忆**：把结果写入上下文，供后续查询使用。
- **技术栈（仓库已核验）**：Python 为主（约 92 万字节 Python、5.5 万字节 Notebook、少量 Shell）；`FastAPI 0.115` + `uvicorn`；`langchain` / `llama-index` / `chroma` / `openai` / `paper-qa`；科学工具依赖包含 RDKit、pymatgen、ASE、BioPython、MDAnalysis 等；`app.py` 提供 `/chat` API。
- **前端形态**：仓库以 API 和工具层为主，没有一个产品级证据工作台；`app.py` 的 `ChatQuery` 直接接收 `api_key` / `api_base`。这是**原型便利**，不是生产安全设计——我们的实现必须把 key 留在服务端，不能让浏览器传 key。
- **能借的**：工具知识图谱/注册表、工具权限与安全属性、Planner → Executor → Summarizer 的职责分离、失败重试、工具级安全审查。
- **不能直接借的**：把 API key 放进请求体；把“工具调用成功”当成“结论正确”；没有 claim/EA/证据闭合与稿件维护。

> 参考：[SciToolAgent 仓库](https://github.com/HICAI-ZJU/SciToolAgent)、[Nature 论文](https://www.nature.com/articles/s43588-025-00849-y)、[MindSpore 项目介绍](https://www.mindspore.cn/news/zh/2026-1-12)。效果数字未复现。

### 2.2 浙大 CAD&CG：`learning_research` 是方法论，不是 Agent 框架

浙大 CAD&CG（彭思达/周晓巍组）公开的 `learning_research` 是很高质量的**科研方法论文档**：如何找问题、读论文、做实验、写论文、与导师沟通。它不是软件框架，也不提供 run harness、工具运行时或前端。

对我们的价值：**把方法论沉淀为 Skill 的流程模板与检查点**（例如 goal-driven、paper reading、experiment record、writing/rebuttal），而不是把它当成“可运行的科研智能体”。这也解释了为什么“浙大那些工作”里，真正可对照的软件框架是 SciToolAgent，而不是 CAD&CG 的视觉/方法论文档。

### 2.3 西湖：DeepScientist / CycleResearcher / AiraXiv

- **DeepScientist**：西湖大学张岳团队（WestlakeNLP），本地优先的自主研究工作室；论文 `DeepScientist: Advancing Frontier-Pushing Scientific Findings Progressively`（arXiv 2509.26603）；仓库 [ResearAI/DeepScientist](https://github.com/ResearAI/DeepScientist)。
- **CycleResearcher**：同团队的前序工作，用自动化评审做迭代训练/改进；仓库 [zhu-minjun/Researcher](https://github.com/zhu-minjun/Researcher)。
- **AiraXiv**：AI 驱动的开放获取/预印本平台，支持人类与 AI 科学家、MCP/API 交互；论文有浙大等合作署名，但它是**出版/评审平台**，不是我们要直接复刻的 Agent 框架。参考：[AiraXiv arXiv](https://arxiv.org/html/2605.21481v1)。

我们借 DeepScientist 的**工程形态**，不借它的“全自主/超越人类 SOTA”口径；借 AiraXiv 的**MCP/API 与评审接口**思路，不做自动投稿或假评审。

---

## 3. 开源科研 Agent 框架地图

| 项目 | 单位/性质 | 主要范围 | 架构/技术栈（公开信息） | 前端/交互 | 可借 | 不借/风险 |
| --- | --- | --- | --- | --- | --- | --- |
| **SciToolAgent** | 浙大 HICAI-ZJU；开源 | 科学工具编排（生物/化学/材料） | Python、FastAPI、LangChain/Chroma、OpenAI、500+ 工具、SciToolKG；Planner/Executor/Summarizer + safety | API-first；无产品级证据工作台 | 工具注册表、安全属性、工具链规划 | 请求体传 API key；工具成功 ≠ 结论正确；无 claim/EA/维护 |
| **DeepScientist** | 西湖大学；开源 | 本地优先自主研究工作室 | Python 引擎 + TypeScript UI；Vite、React、Tailwind、Radix、TanStack Query、Zustand/Jotai、@xyflow/react、Monaco、Tiptap、Recharts、Playwright；daemon + `skills/`；可选 Claude Code/Codex/OpenCode | 较完整的本地 Web/TUI 工作台 | 本地 daemon、运行目录、技能目录、React UI 栈 | 全自主/SOTA 口径；分阶段开源与安全风险；不宜直接照搬自主性 |
| **The Agentic Scientist / AI-Scientist-v3** | Sakana AI；开源 | 编码 Agent 驱动的计算科学研究 | Python + Docker + 编码 Agent harness；`task.md` → 想法/实验/rubric/基线/消融/最终评测/论文；每阶段一个 run 目录 | CLI/任务目录为主 | Docker 隔离、run 目录、rubric/自验证、论文产物组织 | 全自动/“AI Scientist”叙事；许可证/效果数字需逐项核 |
| **AI-Researcher** | 港大 HKUDS；开源 | idea → 文献 → 实现 → 论文 | Python + Gradio + Docker + LiteLLM；多 Agent 流水线；benchmark | Gradio 单页 Demo | 双进程、Docker、端到端任务 | Gradio 不适合作证据工作台；端到端口径过宽 |
| **GPT Researcher** | 开源 | 深度研究报告（web/local） | Python 后端 + TypeScript 前端；LangGraph、Docker、`frontend/`、`skills/` | Next.js/React 前端 | 前后端分离、报告与引用 | chat/report-first，不是证据维护 |
| **InternAgent** | 上海 AI Lab；开源 | 长时程自主科学发现 | Python 为主；MCTS 可视化、`sci_tasks`、任务/记忆/评测 | 轻量 Web/可视化 | 任务 harness、长时程状态、评测 | 前端与证据层不是重点 |
| **Biomni** | Stanford；开源 | 生物医学通用 Agent | Python 库 + notebooks + 工具/数据湖；无独立前端 | Notebook/库 | 领域工具注册、数据/工具编排 | 领域窄；无证据闭合 |
| **AutoSOTA** | 清华/中关村学院；项目 | 自动发现 SOTA 模型 | Python 多 Agent + 资源准备/实验/评估/构思 | 研究项目页/代码 | 固定评测、实验循环、成本意识 | “刷 SOTA”口径；不可作为我们的效果承诺 |
| **Agent Laboratory** | 开源 | 端到端研究/报告 | Python，多 Agent 工作流 | 轻量 UI/CLI | 角色分工、报告产物 | 缺少证据级维护与签署 |
| **Open Deep Research** | LangChain；开源 | 可配置深度研究 | LangGraph + Studio；Python | Studio/开发 UI | 事件/状态图、可配置研究 | Studio 是调试工具，不是产品前端 |
| **AiraXiv** | 西湖/浙大合作署名；平台论文 | AI 开放获取与评审平台 | 平台 + MCP/API + 多智能体评审 | Web 平台 | MCP/API、评审/反馈接口 | 不是 Agent 框架；不做自动投稿/假评审 |

> 说明：表中“开源”指公开仓库/代码入口；许可证、完整性与可运行性未逐项审计。DeepScientist/CycleResearcher 属于西湖大学，不是浙大；SciToolAgent 是浙大直接相关的开源框架。

**已下载仓库的许可证核对（2026-10-23，以仓库 LICENSE 为准）**：

| 仓库 | 本地形态 | 许可证 | 对我们的约束 |
| --- | --- | --- | --- |
| `HICAI-ZJU/SciToolAgent` | 完整 git clone（含历史） | MIT | 可读、可对照；再分发保留版权与许可声明 |
| `ResearAI/DeepScientist` | 完整 git clone（含历史） | Apache-2.0 | 可读、可对照；派生/再分发保留 NOTICE/变更说明 |
| `SakanaAI/AI-Scientist-v3` | 完整 git clone（含历史） | Apache-2.0 | 同上 |
| `zhu-minjun/Researcher`（CycleResearcher） | 完整 git clone（含历史） | CycleResearcher License（研究专用，非 OSI） | **不复用代码/模型/权重，不打包，不再分发**；仅本地只读对照 |
| `assafelovic/gpt-researcher` | 完整工作树快照（无 `.git`） | Apache-2.0 | 可读、可对照；保留 NOTICE |
| `aiming-lab/AutoResearchClaw` | 完整工作树快照（无 `.git`） | MIT | 可读、可对照 |
| `wanshuiyin/Auto-claude-code-research-in-sleep`（ARIS） | 完整工作树快照（无 `.git`） | MIT | 可读、可对照 |
| `EvoMap/AutoResearch`、`Gen-Verse/RSI-Anything`、`OpenRSI-Foundation/OpenRSI-Index` | 完整工作树快照（无 `.git`） | Apache-2.0 | 可读、可对照；保留 NOTICE |
| `DAIR-AutoResearch/AutoSci`、`SamuelSchmidgall/AgentLaboratory` | 完整工作树快照（无 `.git`） | MIT | 可读、可对照 |
| `InternScience/InternAgent` | 完整工作树快照（无 `.git`；子模块未拉） | Apache-2.0 | 可读主树；benchmark 子模块待补 |
| `snap-stanford/Biomni` | 完整工作树快照（无 `.git`） | Apache-2.0 | 可读、可对照 |
| `HKUDS/AI-Researcher` | 待补（工作树 901 MB；examples GIF/数据集占大头） | 仓库页未声明 | 未完成前不复制代码 |

> 其余框架只看了公开 README/目录，许可证与完整性**未审计**；不得把“公开仓库”当成“可直接复用”。完整清单与中断记录见 [`oss/full/CLONES.md`](oss/full/CLONES.md)。

---

## 4. 深读：三种可参考的工程形态

### 4.1 SciToolAgent：工具知识图谱 + API-first

**值得学的不是“500 个工具”这个数字，而是工具被组织成可查询、可约束的对象**：

- 工具有输入/输出、依赖、兼容性、安全等级；Planner 不是凭 prompt 猜，而是从 `SciToolKG` 检索；
- Executor 只负责按计划调用，不负责发明结论；
- Summarizer 负责汇总，并可触发重规划；
- 安全检查是工具执行的一部分，不是事后说明。

**对我们的映射**：

| SciToolAgent | 我们的对应物 |
| --- | --- |
| SciToolKG | Tool Registry + Skill Registry（能力、权限、证据契约、兼容性） |
| Planner | Workflow 的任务编译/阶段规划（不是自由 agent） |
| Executor | Execution worker + Docker 沙箱 |
| Summarizer | Evidence/Manuscript 的受约束汇总；不能创建 claim |
| Safety check | 工具权限、网络 allowlist、沙箱、人工审批、导出硬门 |

**关键反思**：SciToolAgent 是“把工具调用做对”，我们是“把工具调用产生的证据变成可签署的 claim/稿件”。它解决 `tool use`，我们解决 `evidence closure`；两者互补，不应该把 500 个工具直接搬进我们的核心。

### 4.2 DeepScientist：本地优先 + 技能目录 + 完整 React 工作台

公开 `src/ui/package.json` 显示它使用（2026-10-23）：

- Vite 5、React 18、TypeScript、Tailwind 3；
- Radix UI、TanStack Query、Zustand/Jotai；
- `@xyflow/react`（图谱）、Monaco（编辑器）、Tiptap（富文本/稿件）、Recharts；
- `socket.io-client`、react-resizable-panels、Playwright e2e；
- Python 引擎 + TypeScript daemon/UI + `src/skills/` 目录（intake-audit、scout、idea、baseline、experiment、analysis-campaign、decision、write、figure-polish、paper-outline、paper-plot、references、review、finalize、rebuttal、nature-* 等）。

这几乎验证了我们上一轮推荐的“React/TS + Vite + Radix + xyflow + Monaco”的组合不是拍脑袋，而是一个已经产品化的科研 Agent 在做同样选择。

**能借的**：

- **本地优先**：daemon + 本地文件/运行目录，而不是把一切放到云端；
- **技能目录**：把论文流程拆成可加载的技能，而不是一个巨大的 prompt；
- **工作台**：图谱、编辑器、稿件、diff、终端都在一个界面；
- **技能命名**：`intake-audit / scout / idea / baseline / experiment / analysis / write / figure / references / review / finalize / rebuttal` 可以作为我们的预置技能清单的起点。

**不能直接借的**：

- 它的“全自主发现/超越 SOTA”口径与我们的 A3 边界不一致；
- 按公开目录看，它的技能更多是流程包；我们需要的 `EvidenceContract + Lease + 撤销传播 + 隐藏评测` 仍需按本文规范补齐（不把“有 skills 目录”当成合格技能运行时）；
- 它的运行证据/评测可见性需要按 [19](19-RSI出题规范对照-自进化运行纪律反思.md) 的固定实例、隐藏 verifier、step 账本重新设计。

### 4.3 AI-Scientist-v3：run 目录 + Docker + rubric

公开 README 的核心形态是：

- 输入一个 `task.md`；
- 编码 Agent 提想法、跑实验、按 rubric 评估、迭代；
- 基线/消融/最终密封评测/事后分析/论文写作；
- 所有阶段产物留在同一个 run 目录；
- 推荐每个 agent phase 在 Docker 内运行；README 明确警告编码 Agent 有完整工具权限、可继承 API key、任务文件会驱动行为。

**对我们的映射**：

- 采用 **run directory + artifact envelope + Docker sandbox + rubric/评测**；
- 不采用“所有阶段自动跑完、人只看结果”的默认；
- 把“final sealed evaluation”改造成我们 [19](19-RSI出题规范对照-自进化运行纪律反思.md) 的公开/隐藏分离与冻结验收；
- 把编码 Agent 的权限压到最小，不把 API key/宿主目录直接暴露给它。

---

## 5. 技术栈的共性结论

| 层 | 现有框架的常见选择 | 结论 |
| --- | --- | --- |
| 执行引擎 | Python（FastAPI/CLI/Gradio） | 我们的科学工具、PDF、Docker、统计都在 Python，后端选 Python 合理 |
| 前端 | Gradio/Streamlit 原型；DeepScientist/GPT Researcher 用 React/TS | 证据工作台要 React/TS；Gradio 只做内部原型 |
| 编排 | 自定义流水线、LangGraph、编码 Agent harness | 不能把 LangGraph 当证据事实源；自定义 workflow + 类型化 agent 步骤 |
| 沙箱 | Docker / 运行目录 / 受限工具 | 必须；代码执行不能跑在 API 进程或浏览器 |
| 存储 | 本地文件 + SQLite/Postgres + 对象存储 | 生产用 Postgres + 对象存储；本地单人可用 SQLite 起步 |
| 技能 | 目录式 `skills/` + SKILL.md；工具注册表 | 需要升级为 manifest + 权限 + 证据契约 + 租约 + 撤销 |
| 事件/UI | SSE/WebSocket、Studio、socket.io | 运行事件用 SSE；审批走 REST；WebSocket 只在协作/终端 |
| 评测 | rubric/基准/自动评审 | 要有公开/隐藏分离、固定实例、step 账本；不能只看自报 |
| 人机边界 | 部分系统有人审/安全门 | 我们的核心：人签署、导出硬门、A3 |

**最重要的工程结论**：这些系统真正难的不是“把 LLM 接上”，而是 **run harness、工具/技能运行时、证据对象、评测隔离**。前端是展示层；我们的差异化在证据与维护。

---

## 6. 反模式与必须避开的坑

1. **把 API key 放进前端/请求体**：SciToolAgent 的 `app.py` 接收 `api_key`/`api_base`，适合原型但不适合产品；我们的 key 只在服务端/密钥库。
2. **把工具调用成功当结论正确**：工具返回 200 不代表 claim 被支持；必须有 span/EA/裁定。
3. **把 Gradio/Streamlit 当最终工作台**：做演示很快，但 diff、图谱、签署、变更回放、细粒度权限做不动。
4. **把 Agent 框架当领域模型**：LangGraph/编码 Agent 是执行手段；claim、EA、run、slot、closure 必须由我们自己的领域模块拥有。
5. **自动下载并执行任意 Skill**：供应链/提示注入/许可证/宿主权限风险；必须走允许清单、校验、沙箱、dry-run、人工批准。
6. **公开评测与隐藏验收混在一起**：会污染准入；必须固定实例、公开/隐藏分离、冻结后独立验收（见 [19](19-RSI出题规范对照-自进化运行纪律反思.md)）。
7. **用效果数字当架构证明**：AI Scientist/DeepScientist 的 SOTA 数字是它们自己的口径；我们不能复用为我们的结果。
8. **10 个微服务先于一个纵切**：外部产品也没有这么做；先模块化单体 + 一个 worker。
9. **“全自动”作为默认**：与 A3 冲突；默认人在环，自动只用于低风险检查和草稿。

---

## 7. 我们借什么、不借什么

| 借 | 具体落点 |
| --- | --- |
| SciToolAgent 的工具图谱/安全属性 | Tool Registry + Skill Registry 的 `inputs/outputs/permissions/safety` |
| SciToolAgent 的 Planner/Executor/Summarizer | 阶段内的规划/执行/汇总分离，但 Evidence 独立创建 claim |
| DeepScientist 的本地 daemon + React UI | 本地优先、run workspace、图谱/编辑器/稿件工作台 |
| DeepScientist 的技能目录 | `skills/builtin` 的 intake/scout/idea/baseline/experiment/write/figure/review/finalize 分类 |
| AI-Scientist-v3 的 run 目录/Docker/rubric | 每次 run 的不可变目录、沙箱、评测清单 |
| GPT Researcher 的前后端分离 | Python API + TS/React 前端，避免 Gradio 单页 |
| [19](19-RSI出题规范对照-自进化运行纪律反思.md) 的固定实例/隐藏评测/step 账本 | Skill/协议自进化的运行底座 |

| 不借 | 原因 |
| --- | --- |
| 全自动“AI Scientist”叙事 | 与 A3 冲突；没有人类签署不能对外 |
| 外部系统的 SOTA/效果数字 | 不是我们的实验；不可复用 |
| 请求体传 API key | 安全边界错误 |
| 任意互联网 Skill 自动安装 | 供应链/许可/注入风险 |
| LangGraph Studio 当产品 UI | 调试工具，不是证据工作台 |
| 10 个微服务/K8s/Kafka | 对毕设过重；先模块化单体 + worker |
| 自动投稿/自动评审模拟 | 合规红线；评审模拟只能作内部自检 |

---

## 8. 对“最终能写出论文”的判断

现有开源已经证明：**论文级的文本、图表、LaTeX/PDF 可以自动生成**；真正没有解决的是：

- 每个事实句是否有可定位来源；
- 每个 claim 是否有 run/EA 支持；
- 数据/依赖/稿件变更后，旧结论是否 stale、能否重闭合；
- 人类是否在正确的门上签署；
- Skill/协议是否真的在固定实例上改进了下一轮，而不是“又跑了一次”。

所以我们的目标不应是“再做一个 AI Scientist”，而是：**一个能生成可签署论文草稿、并在变更后维护证据闭合的运行时**。这决定了技术栈的选择：Python 执行 + React 证据工作台 + 类型化 API/SSE + Postgres 证据账本 + Docker + DeepSeek。具体落地见 [21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md)。

---

## 9. 来源与证据等级

| 来源 | 用途 | 等级 |
| --- | --- | --- |
| [HICAI-ZJU/SciToolAgent](https://github.com/HICAI-ZJU/SciToolAgent) | 浙大工具 Agent 的代码/语言/入口 | 仓库已核验（语言/顶层目录） |
| [SciToolAgent, Nature Computational Science](https://www.nature.com/articles/s43588-025-00849-y) | 论文/架构声明 | 论文页（未逐段精读） |
| [MindSpore 项目介绍](https://www.mindspore.cn/news/zh/2026-1-12) | 团队与 Planner/Executor/Summarizer/SciToolKG | 项目页 |
| [ResearAI/DeepScientist](https://github.com/ResearAI/DeepScientist) | 本地优先、skills、UI package.json | 仓库已核验（package.json/顶层目录） |
| [DeepScientist arXiv 2509.26603](https://arxiv.org/abs/2509.26603) | 系统定位 | 论文摘要/HTML |
| [zhu-minjun/Researcher](https://github.com/zhu-minjun/Researcher) | CycleResearcher | 仓库入口 |
| [SakanaAI/AI-Scientist-v3](https://github.com/SakanaAI/AI-Scientist-v3) | 编码 Agent、Docker、run 目录、rubric | 仓库 README（已核验 README 片段） |
| [HKUDS/AI-Researcher](https://github.com/HKUDS/AI-Researcher) | Gradio/Docker/LiteLLM 形态 | 仓库已核验（语言/顶层/入口） |
| [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | Python + TypeScript 前后端 | 仓库已核验（语言/顶层） |
| [InternScience/InternAgent](https://github.com/InternScience/InternAgent) | 长时程科学 Agent | 仓库已核验（语言/顶层） |
| [snap-stanford/Biomni](https://github.com/snap-stanford/Biomni) | 生物医学 Agent/工具库 | 仓库已核验（语言/顶层） |
| [AutoSOTA arXiv 2604.05550](https://arxiv.org/abs/2604.05550) | 自动 SOTA 研究系统 | 论文入口（未精读） |
| [AiraXiv arXiv 2605.21481](https://arxiv.org/html/2605.21481v1) | 开放获取/评审平台 | 论文 HTML（未精读） |
| [DeepSeek API 文档](https://api-docs.deepseek.com/zh-cn/index.html) | OpenAI/Anthropic 兼容、模型与工具能力 | 官方文档（2026-10-23 查看） |
| [DeepSeek Change Log](https://api-docs.deepseek.com/updates/) | 模型名迁移/JSON/Function Calling | 官方文档 |
| [AG-UI 1.0 规范报道](https://www.sitepoint.com/ag-ui-1-0-stable-spec-agent-user-interaction) | Agent–UI 事件/审批 | 公开规范报道 |
| [K-Dense scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | 技能库/许可证 | 仓库入口（未逐项审计） |
| 本地 `oss/` 快照与 00–19 文档 | 现有设计输入 | 本地材料 |

**未核验/不可引用为结论**：所有外部系统的效果数字、star 数、SOTA 提升、接受率；它们的许可证与完整开源状态；DeepScientist/AI Scientist 的实际可运行性。本文只把仓库结构和技术形态作为工程参考。

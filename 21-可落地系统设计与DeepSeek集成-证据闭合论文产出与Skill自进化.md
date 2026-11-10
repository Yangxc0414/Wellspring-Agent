# 21 · 可落地系统设计与 DeepSeek 集成：证据闭合、论文产出与 Skill 自进化

> 版本：v0.1 · 日期：2026-10-23 · 性质：实现设计稿（未实现/未实测）  
> 工作名：**ClaimWeave（拟）**；仓库/站点当前仍叫 Research Agent，完整改名以单独变更为准。  
> 上游输入：[04](04-自动化研究与写作流水线.md)、[07](07-复现级验证与执行Harness设计.md)、[09](09-系统架构与流程编排设计.md)、[11](11-自进化循环设计-准入理由、跨循环继承、迁移与能力增益.md)、[13](13-创新点评审与主张收敛-需求对齐、开源对照与验证顺序.md)、[14](14-产品差异化与Demo反思-从证据链写作到证据运营工作台.md)、[16](16-科研Skill生态调研与动态流程编排.md)、[17](17-基于Skill契约的上层微服务架构.md)、[18](18-GitHub%20Pages部署与多智能体Skill设计.md)、[19](19-RSI出题规范对照-自进化运行纪律反思.md)、[20](20-开源科研Agent框架调研-浙大SciToolAgent与主流技术栈.md)  
> 边界：本文设计的是**可签署草稿的生产与维护运行时**，不是全自主科学家，不做自动投稿、假同行评审、未披露 ghostwriting、伪造数据/引用或 AIGC 检测规避。所有未运行的目标都标为“待验证”。

---

## 0. 一页结论

### 0.1 要建什么

一个**本地优先 / API 优先**的科研证据运行时：

1. **接入**：本地文件夹、公开仓库元数据、论文/数据/代码材料；只读扫描，不执行未授权代码。
2. **闭合**：从文献/实验/运行到 claim、EA、稿件句、图、闭包报告与导出，所有事实句可追溯。
3. **维护**：数据、依赖、claim、模型或稿件变更后，沿证据图定位 stale/孤儿，分派重跑/重写/复核，重新闭合。
4. **人签**：在 G0/G2/G3/G4/G5 等门由人做科学判断、授权与最终责任；机器只起草。
5. **论文产出**：从固定任务生成可编辑的 Markdown/LaTeX/DOCX/PDF 草稿、图表、证据包与 AI 使用声明；不自动投稿。
6. **Skill**：预置技能 + 受控下载 + dry-run/pilot/lease；自进化只产生候选，经固定实例、隐藏评测与人工签署后准入。

### 0.2 技术栈决定（一句话）

**React + TypeScript + Vite** 证据工作台；**FastAPI + Pydantic v2 + Python worker**；**Postgres + Redis + 对象存储**；**Docker 沙箱**；**DeepSeek（OpenAI 兼容）通过 ModelGateway**；**SSE** 运行事件；**Playwright/Pytest**。公共站点继续静态部署 GitHub Pages；产品运行时本地/边缘部署，不混在一起。

### 0.3 最重要的三个判断

- **先一个纵切，不做平台全景**：接入 → 一个 claim/EA → 一次运行/判定 → 变更重闭合 → 人签/导出。没有这个，其他都是演示。
- **后端以 S0–S16 为 canonical，P0–P8 只作 UI 叙事压缩**；demo 的 X0/G1/... 是演示标签，不得写成正式门禁。
- **DeepSeek 是模型网关的一个 provider，不是架构中心**；JSON/tool 输出必须经 Pydantic 校验，key 只在服务端，模型/参数/成本必须可审计。

> 如何把工程架构写成论文可接受的系统贡献、以及扩展性/不变量如何验证，见 [22](22-可扩展工程架构与论文创新点-从Demo到可维护证据运行时.md)。

---

## 1. 范围、目标与非目标

### 1.1 目标（可验收）

| 编号 | 目标 | 验收 |
| --- | --- | --- |
| G1 | 一个真实纵切 | 一个开放论文/仓库，完成 intake → claim/span/EA → 一次运行/判定 → 稿件句/图 → Q1/G5 → 人签/导出（或阻断） |
| G2 | 可维护 | 修改一个数字/claim/依赖，系统定位受影响的 claim/句/图，生成 ChangeSet 与处置，重新闭合 |
| G3 | 可追溯 | 每个事实句有 slot；每个 claim 有来源或 EA；每个数字有 run；每个引用可核 |
| G4 | 可签署 | 人工在正确门签署，签名/理由/证据哈希进入 append-only 审计；机器不能代签 |
| G5 | 可评测 | 在固定实例、固定预算、固定基线上报告结构闭合、语义支持、复现、维护与人工时间 |
| G6 | Skill 可控 | 预置 + 受控下载 + dry-run + lease + revoke；自进化候选不能自动 active |

### 1.2 非目标（首版明确不做）

- 全自主科学发现、自动提出并验证任意领域新理论；
- 湿实验执行、自动操作仪器、绕过实验安全审查；
- 自动投稿、自动回复审稿、伪造同行评审；
- 未披露 ghostwriting、伪造数据/参考文献、规避 AIGC 检测；
- 未授权抓取知网/万方/维普或付费全文；
- 一开始上 10 个微服务、K8s、Kafka、区块链、多租户 SaaS；
- 承诺“任意主题一键出可发表论文”或复用外部系统的 SOTA 数字。

### 1.3 A3 边界矩阵

| 环节 | 机器负责 | 人保留 |
| --- | --- | --- |
| 选题/问题 | 生成候选、整理证据、指出风险 | 选择问题、判断科学价值 |
| 文献 | 检索、去重、定位 span、覆盖回执 | 处理争议、决定是否采信 |
| 假设 | 生成可证伪候选、反例 | 选择主假设、设定门槛 |
| 设计 | 起草协议、对照、停止规则 | 冻结协议、批准高风险变更 |
| 执行 | 沙箱运行、记录日志、复现 | 实验安全、资源与合规授权 |
| 判定 | 评分、EA、失败归因 | 异常处理、最终判断 |
| 写作 | 受 claim/EA 约束起草、图表 | 论证取舍、署名、投稿 |
| 导出 | 硬门检查、封包 | 终审、签署、最终责任 |

---

## 2. 设计原则

1. **Evidence 是唯一 claim writer**：技能、执行、Writer 只能提交 artifact，不能直接写 claim。
2. **决定性工作流 + 受约束 Agent**：阶段与门由代码状态机控制；Agent 只做阶段内提议/执行/检查。
3. **结构闭合不等于语义为真**：claim–span/EA 对齐是必要条件；另设 `SemanticAudit` 抽样和人工复核。
4. **变更即新版本**：冻结产物不原地改；Run 钉模板/镜像/协议版本；变更生成新 revision 与影响闭包。
5. **人签是硬门**：G0/G2/G3/G4/G5 不能由 Agent 代签；导出只由 Closure 执行。
6. **本地优先、API 优先**：浏览器只与 BFF 通信；LLM/沙箱/密钥/数据库都在服务端；公共 Pages 只做展示。
7. **Skill 是过程包，不是 Agent**：有 manifest、权限、证据契约、测试、租约、撤销；可下载但不可自动执行/自动晋升。
8. **自进化是受控实验，不是宣传语**：固定实例、统一预算、公开/隐藏分离、step 账本、冻结验收、人工准入。
9. **所有未运行的目标保持“待验证”**：C1–C4/E7/E8 在真实跑完前不写成结果。
10. **许可证与合规先于能力**：外部 Skill/代码先看 license、来源、权限与可撤销性；不把 CC BY-NC 内容直接商品化。

---

## 3. 总体架构

### 3.1 两条轨道

```
轨道 A：公共站点（GitHub Pages，静态）
  site/  →  品牌 / 真实 OpenAlex 检索 / 只读 intake / SIM demo
  没有服务端执行、没有 LLM key、没有用户代码执行

轨道 B：产品运行时（本地或边缘）
  React SPA  ──REST/SSE──▶  FastAPI BFF/API
                                │
                    ┌───────────┼────────────┐
                    ▼           ▼            ▼
              Workflow     Evidence      Manuscript
              Knowledge    Execution     Impact/Closure
              Skills       Audit         ModelGateway
                    │
        Postgres（事实源）/ Redis（队列/租约）/ 对象存储（artifact）
                    │
                Python worker → Docker sandbox / retrieval / judges / skills
```

### 3.2 三个 deployable（首版）

| 单元 | 职责 | 不做什么 |
| --- | --- | --- |
| `apps/web` | React SPA：运行台、证据工作台、稿件、变更、审批、技能、审计 | 不直接访问 DB/LLM/沙箱；不持有 API key |
| `apps/api` | FastAPI BFF：鉴权、项目/运行命令、查询聚合、SSE、审批、导出 | 不长任务阻塞；不执行不可信代码 |
| `apps/worker` | 检索、解析、沙箱运行、Judge、Skill 执行、传播计算 | 不持有浏览器会话；不直接改 claim |

`site/` 只作为静态站点，单独部署 Pages。**不要**把产品 SPA 塞进 site 的 iframe；iframe 只是 demo 嵌入，不是产品架构。

### 3.3 模块（模块化单体，不是 10 个容器）

| 模块 | 拥有的对象 | 主要命令/事件 |
| --- | --- | --- |
| Project/Intake | Project、intake profile、materials | 创建项目、只读扫描、导入 |
| Workflow | WorkflowTemplate、RunInstance、StageExecution、Checkpoint | 编译、启动/暂停/恢复、跳过可选阶段 |
| Knowledge | Source、Document、Span、QuerySpec、CoverageReceipt、ConflictEdge | 检索、解析、去重、定位、覆盖 |
| Execution | TaskSpec、Protocol、RunCapsule、Attempt、Verdict、EA、FailureRecord、CostRecord | 沙箱运行、Judge、重跑、失败归因 |
| Evidence | Claim、EvidenceLink、EvidenceDebt、SemanticAudit | 创建/绑定/失效/审计 |
| Manuscript | Manuscript、Sentence、Slot、Figure、Binding | 版本、槽位、图、diff |
| Impact | ChangeSet、ImpactClosure、Disposition | 影响闭包、重跑/重写/复核 |
| Closure | ClosureReport、Signature、ExportManifest、ExportBundle | Q1/G5、签署、导出/阻断 |
| Skills | SkillManifest、SkillLease、SkillRun、SkillArtifact | 发现、安装、dry-run、激活、撤销 |
| Memory/Evolution | ProcessProtocol、EvolutionCandidate、AdmissionRecord、ScopePassport、CapabilityDelta | PF、EV0–EV4、租约、能力归因 |
| Audit | AuditEvent、AIUsage、PolicyVersion | append-only、审计查询 |
| ModelGateway | ModelProfile、ModelCall | provider 路由、成本、重试、脱敏 |

> 边界原则：按**证据对象**拆模块，不按阶段/Agent/Skill 拆；模块之间通过 typed API/事件通信。MVP 一个 API 进程 + 一个 worker；只有独立扩缩容/安全隔离/发布节奏需要时才拆服务。

---

## 4. 技术栈：最终选择与理由

### 4.1 推荐版本（以稳定为先）

| 层 | 选择 | 说明 |
| --- | --- | --- |
| 前端框架 | React 18/19 + TypeScript + Vite | 本地面板、长任务、无 SEO 需求；Vite 简单、启动快；与 DeepScientist 的 UI 形态一致 |
| 样式/组件 | Tailwind + Radix UI + 自有 design tokens（可套 shadcn/ui） | 细粒度证据工作台需要可控组件，不用重型 UI 套件 |
| 服务状态 | TanStack Query v5 + OpenAPI 生成的 TS 类型 | 服务端是事实源；避免手写重复 DTO |
| UI 状态 | Zustand（或 useReducer） | 只存选中对象、抽屉、focus、分页；不复制 workflow 状态 |
| 事件 | SSE（`text/event-stream`）+ REST 命令 | 单向运行事件/日志天然适合 SSE；审批/命令用 REST；WebSocket 暂不需要 |
| 图/编辑/稿件 | `@xyflow/react` + Monaco/CodeMirror + Tiptap/Markdown + Recharts | claim–EA 图、LaTeX/JSON diff、稿件编辑、指标图 |
| 后端 | Python 3.12 + FastAPI + Pydantic v2 | 科学计算、Docker、PDF、统计、工具生态都在 Python；Pydantic 适配证据契约 |
| ORM/迁移 | SQLAlchemy 2 + Alembic | 显式事务、版本迁移；不把业务逻辑放进 ORM 回调 |
| 数据库 | Postgres 16 + pgvector（可选） | 事实账本、状态、门禁、审计；向量只是派生索引 |
| 队列 | Redis 7 + Arq（或 Dramatiq） | 长任务/重试/租约；Arq 轻量异步；Celery 在团队更熟时可用 |
| 对象存储 | 本地内容寻址目录 / MinIO / S3 | PDF、日志、图、导出包；不可变、哈希寻址 |
| 沙箱 | Docker（独立 worker） | 运行复现代码；只读项目挂载、网络默认关、资源/时间限制 |
| 模型 | DeepSeek API（OpenAI 兼容）+ ModelGateway；LiteLLM 可选 | 多 provider/本地模型可替换；key 服务端；结构化输出校验 |
| Agent 框架 | 自定义 workflow 状态机 + Pydantic AI；LangGraph 可选 | 证据/门禁由我们拥有；Pydantic AI 负责类型化 agent 步骤；LangGraph 只用于复杂子图 |
| 可观测性 | OpenTelemetry + 结构化日志；Langfuse/Phoenix 可选 | run/stage/model/tool 追踪；审计事件单独 append-only |
| 测试 | Pytest + Vitest + Playwright + 契约测试 | API、UI、端到端；证据对象/gate 的 golden tests |
| 部署 | Docker Compose：web/api/worker/postgres/redis/minio；Pages 静态站点 | 一个人能跑；不上 K8s |
| 包管理 | pnpm（前端）+ uv（Python） | 锁定版本；一条命令启动 |

### 4.2 为什么不是别的

| 备选 | 不选/慎选原因 |
| --- | --- |
| Next.js 作为主应用 | 产品是本地/边缘、长任务、鉴权应用，无 SEO；Next 需要额外 Node 运行时，SSR 不解决问题。若团队更熟 Next，可做 React 壳，但仍需 Python 执行层。 |
| Streamlit / Gradio | 适合算法原型，不适合证据图谱、diff、双栏检查、签署、变更回放；AI-Researcher 用 Gradio 是研究 demo 的合理选择，不是产品前端。 |
| Vue/Nuxt / SvelteKit | 都可做；但现有 agent UI 生态（Radix/shadcn、xyflow、Monaco/Tiptap）和团队可复用性更偏 React。不要为“轻”重写一套。 |
| CopilotKit / assistant-ui 作为壳 | 它们解决对话/copilot/generative UI，不是证据工作台；可用于右侧解释/审批助手。 |
| LangGraph 作为事实源 | 证据对象、claim、门禁必须由 Postgres 领域模型拥有；LangGraph 可以是阶段内的执行图，不能替代证据账本。 |
| 10 个微服务/K8s/Kafka | 对毕设过重；先模块化单体 + worker，等有独立扩缩容/隔离证据再拆。 |
| Temporal | 长任务可靠，但运维复杂度高；首版 Arq + DB 状态 + checkpoint 足够。 |

### 4.3 本地优先与托管

- **本地单用户**：SQLite 也可以起步，但为了审计/并发/迁移，推荐 Postgres（Docker Compose）；对象存储用本地目录；worker 同机。
- **团队/边缘**：Postgres + MinIO + Redis；API/worker 分开；反向代理；密钥放 Secret/环境变量。
- **公共站点**：GitHub Pages 只放静态 site + demo；不连接本地运行时；真实 OpenAlex 检索可在浏览器直连公开 API，但不接触用户私有材料。
- **不要**为了演示在 Pages 上运行 LLM、Docker 或数据库。

---

## 5. 领域模型与硬不变量

### 5.1 对象清单

| 聚合 | 对象 | 关键字段 |
| --- | --- | --- |
| 项目 | `Project`、`IntakeProfile`、`Material`、`GenreProfile`、`Budget` | id、目标、体裁、预算、权限 |
| 来源 | `SourceRecord`、`Document`、`Span`、`QuerySpec`、`CoverageReceipt`、`ConflictEdge` | 来源、版本、许可证、页-段-句锚点、覆盖、冲突 |
| 证据 | `Claim`（literature/result/manuscript）、`EvidenceLink`、`EvidenceDebt`、`SemanticAudit` | 条件、方向、状态、span/EA、债务、审计 |
| 设计/执行 | `TaskSpec`、`Protocol`、`RunPlan`、`RunCapsule`、`Attempt`、`Verdict`、`EA`、`FailureRecord`、`CostRecord` | 冻结版本、镜像/seed、日志、评分、证据产物 |
| 稿件 | `Manuscript`、`Section`、`Sentence`、`Slot`、`Figure`、`Binding` | 版本、六类槽、图源、绑定 |
| 治理 | `ChangeSet`、`ImpactClosure`、`Disposition`、`ClosureReport`、`Signature`、`ExportManifest`、`ExportBundle` | 变更、影响、处置、签署、导出 |
| 技能 | `SkillManifest`、`SkillLease`、`SkillRun`、`SkillArtifact` | 权限、证据契约、测试、租约、产物 |
| 自进化 | `ProcessProtocol`、`EvolutionCandidate`、`AdmissionRecord`、`ScopePassport`、`CapabilityDelta` | 阶段、候选、理由、租约、迁移、增益 |
| 审计 | `AuditEvent`、`AIUsage`、`PolicyVersion` | append-only、模型/参数、策略版本 |

### 5.2 Artifact 信封（沿用 [04](04-自动化研究与写作流水线.md) / [17](17-基于Skill契约的上层微服务架构.md)）

```json
{
  "artifact_id": "ART-...",
  "artifact_type": "span|run|verdict|ea|claim|sentence|figure|closure",
  "project_id": "PRJ-...",
  "run_id": "RUN-...",
  "producer": "knowledge|execution|skill|manuscript|...",
  "version": 3,
  "status": "draft|frozen|superseded|invalid|stale",
  "content_hash": "sha256:...",
  "inputs": ["ART-..."],
  "created_at": "2026-10-23T..."
}
```

**没有上游 artifact 不得产出；冻结只出新版本；`content_hash` 不可变；下游引用必须在变更时重新计算。**

### 5.3 四条硬不变量（不可由 Agent 改写）

1. **claim 只由 Evidence 创建**：`result_claim` 必须引用 `scored` verdict + `EA(source=rerun)`；技能/执行不能直接写 claim。
2. **导出只由 Closure 执行**：未解析槽位、stale、冲突、无 EA → `ExportBlocked`；没有旁路。
3. **Run 钉住模板/协议版本**：`run.workflow_id@version` 不可变；运行中改模板必须人工签核并创建新 revision。
4. **技能租约可撤销**：`SkillRevoked` 必须触发依赖 artifact 的复核；不能只在技能库里删一行。

### 5.4 状态机（节选）

| 对象 | 状态 |
| --- | --- |
| Claim | draft / supported / refuted / inconclusive / stale / superseded / retracted |
| Run | planned / running / paused / judging / completed / failed / timed_out / cancelled |
| Submission | created / snapshot_ok / judging / scored / candidate_invalid / verifier_error / infrastructure_error |
| Slot | empty / bound / conflicted / stale / orphan / blocked |
| Gate | requested / approved / rejected / expired / overridden |
| Skill | registered / validated / pilot / active / deprecated / revoked |
| EvidenceDebt | open / assigned / resolved / accepted_risk |

---

## 6. 工作流：S0–S16 canonical，P0–P8 只作 UI 叙事

### 6.1 Canonical S0–S16（实现/工程口径）

| 阶段 | 主要产物 | 门 | 人/自动 | 失败去向 |
| --- | --- | --- | --- | --- |
| S0 接入 | 问题卡、项目配置、材料 | G0 | 人 | 补材料 |
| S1 文献调研 | 文献快照、span、claim 卡、争议矩阵、gap | Q0 | 自动 + 抽样人审 | 回检索/抽取 |
| S2 Idea 发散 | 候选全集 | — | Agent | 补发散 |
| S3 Idea 收敛 | 短名单、否证条件 | G1 | 人 | 回 S2/S3 |
| S4 实验设计 | DesignCard、Protocol、TaskSpec | G2 | 人冻结 | 改设计 |
| S5e 探索 | 探索记录（不进 Judge） | — | Agent/worker | 重试/停止 |
| S5c 确证 | RunCapsule、Verdict、EA、FailureRecord | G2′ | 自动；高风险转人 | 按失败路由 |
| S6 图表 | 候选图包 / 图计划 / 定稿图 | G3 约束 | Agent + 人 | 修数据/重绘 |
| S7 论证骨架 | 论证图 | — | Agent | 重规划 |
| S8 体裁大纲 | 大纲 + 图计划 | G3 | 人 | 重规划 |
| S9 证据卡 | manuscript_claim、槽位、证据卡 | — | Evidence/Curator | 补证据 |
| S10 逐节生成 | 草稿、句槽 | — | Writer（只绑定不新建） | 回 S9/S10 |
| S11 批判 | 问题清单（内部自检，不是同行评审） | — | Agent | 回 S10 |
| S12 修订 | 修订稿 | — | Agent | 回 S11 |
| S13 全稿核验 | 核验报告 | Q1 | 自动 + 独立复核 | 回 S12 |
| S14 评审模拟 | 内部模拟报告（仅自检） | — | Agent | 按回退矩阵 |
| S15 终审 | 终稿、AI 使用声明、限制 | G4 | 人 | 退回 |
| S16 导出 | ClosureReport、ExportBundle | G5 | 自动 + 人签 | 阻断/修复 |

### 6.2 UI 的九幕映射（P0–P8）

| UI 阶段 | 对应 S / 真实门 | 说明 |
| --- | --- | --- |
| P0 任务编译 | S0/S4 · G0/G2/G2′ | UI 压缩叙事 |
| P1 检索与阅读 | S1 · Q0 | 不写 G1 |
| P2 假设裁决 | S2/S3 · G1 | |
| P3 设计冻结 | S4 · G2/G2′ | |
| P4 复现执行 | S5e/S5c · X0–X7 | |
| P5 判定与 Claim | S5c/S9 · verdict+EA | |
| P6 写作与图表 | S6–S10 · G3/Q1 | |
| P7 核验与导出 | S12–S16 · Q1/G4/G5 | |
| P8 记忆准入 | 跨轮 EV1–EV4/PF · M1 | M1 是里程碑，不是门 |

> demo 里的 X0/G1/G2/G4/C2/C3/G3/G5/M1 是**演示标签**，不是 canonical gates；后端/论文一律使用 S0–S16 与 G0/Q0/G1/G2/G2′/G3/Q1/G4/G5。这个映射要在 UI 契约条和论文中保持一致，避免“两套门”。

### 6.3 门禁决策权

| 门 | 类型 | 谁签 | 机器能做什么 | 不能做什么 |
| --- | --- | --- | --- | --- |
| G0 | 人 | 研究者 | 整理问题/材料/风险 | 代签 |
| Q0 | 自动 + 抽样人审 | 检索/阅读负责人 | 覆盖/身份/span/冲突检查 | 把摘要当全文 |
| G1 | 人 | 研究者/导师 | 候选排序、查新 | 替人决定科学价值 |
| G2 | 人 | 研究者 | 设计、预算、风险清单 | 自动冻结高风险协议 |
| G2′ | 自动；高风险转人 | 执行负责人 | TaskSpec/rubric/oracle 检查 | 运行中改模板 |
| G3 | 人 | 作者/导师 | 大纲/图计划草稿 | 代签 |
| Q1 | 自动 + 独立复核 | 核验者 | 引用/数字/图/槽位检查 | 掩盖冲突 |
| G4 | 人 | PI/作者 | 终稿与限制说明 | 代签 |
| G5 | 自动 + 人签 | PI/授权人 | 硬门检查、封包 | 绕过 Closure |

---

## 7. API 与事件契约

### 7.1 原则

- **REST 命令 + SSE 事件**：命令有幂等键；长任务只返回 run_id；事件流单向。
- **OpenAPI 为唯一契约**：后端 Pydantic → OpenAPI → `openapi-typescript` → 前端类型；禁止手写两份 DTO。
- **所有写操作有 actor / project / policy_version / idempotency_key / audit_event_id**。
- **不把 API key、模型内部 prompt、原始 CoT 暴露给前端**；前端只看结构化状态与可公开依据。
- **错误是对象**：`{code, message, retryable, details, trace_id}`；不要只返回 500 文本。

### 7.2 端点（首版）

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/v1/projects` | 创建项目（问题、体裁、预算） |
| POST | `/api/v1/projects/{id}/intake/local` | 注册本地文件夹（只读元数据；不上传内容） |
| POST | `/api/v1/projects/{id}/intake/url` | 读取公开仓库元数据 |
| GET | `/api/v1/projects/{id}` | 项目快照 |
| POST | `/api/v1/projects/{id}/runs` | 编译并创建 run（template/version） |
| POST | `/api/v1/runs/{run_id}/start` · `/pause` · `/resume` | 运行控制 |
| GET | `/api/v1/runs/{run_id}` | run 状态 + 当前 stage/artifact |
| GET | `/api/v1/runs/{run_id}/events` | SSE 事件流（支持 Last-Event-ID） |
| GET | `/api/v1/runs/{run_id}/artifacts` | artifact 列表/过滤 |
| GET | `/api/v1/artifacts/{id}` | artifact 详情 + hash + 来源 |
| GET/POST | `/api/v1/claims` · `/claims/{id}/evidence` | claim 查询/绑定 |
| POST | `/api/v1/runs/{run_id}/gates/{gate}/decisions` | 人签/拒绝（signer、reason、hash） |
| POST | `/api/v1/projects/{id}/changes` | 变更集 |
| GET | `/api/v1/changes/{id}/impact` | 影响闭包 |
| POST | `/api/v1/changes/{id}/dispositions` | 重跑/重写/复核 |
| POST | `/api/v1/exports` | 请求导出（Closure） |
| GET | `/api/v1/skills` · POST `/skills/install` | 技能列表/安装 |
| POST | `/api/v1/skills/{id}/validate` · `/dry-run` · `/activate` · `/revoke` | 生命周期 |
| GET | `/api/v1/audit` | 审计查询 |
| GET/POST | `/api/v1/settings/models` | 模型 profile（key 仅服务端/加密） |

### 7.3 SSE 事件信封

```json
{
  "id": "evt_01J...",
  "seq": 42,
  "run_id": "RUN-0311-02",
  "type": "artifact.created",
  "schema_version": "1.0",
  "occurred_at": "2026-10-23T10:31:22Z",
  "data": {
    "artifact_id": "ART-...",
    "artifact_type": "span",
    "producer": "knowledge",
    "content_hash": "sha256:..."
  }
}
```

事件类型（至少）：

```text
run.started / run.paused / run.resumed / run.completed / run.failed
stage.started / stage.completed
artifact.created / artifact.frozen / artifact.stale
tool.started / tool.completed / tool.failed
gate.requested / gate.decided
claim.created / claim.stale / claim.blocked
change.detected / impact.computed / disposition.required
approval.required / approval.recorded
export.blocked / export.released
skill.loaded / skill.activated / skill.revoked
```

- `seq` 单调递增；断线按 `Last-Event-ID` 重连；服务端保留至少 24h 事件。
- `gate.requested` 触发前端审批抽屉；`approval.recorded` 写入 Audit。
- 事件数据只放可展示的 artifact/状态；prompt/CoT/key 不进 SSE。

### 7.4 审批回执（示例）

```json
POST /api/v1/runs/RUN-0311-02/gates/G4/decisions
{
  "decision": "approved",
  "signer": "PI-...",
  "role": "principal_investigator",
  "reason": "结论边界与限制已核对；AI 使用声明已披露",
  "evidence_hash": "sha256:...",
  "policy_version": "POL-2026-10-01",
  "idempotency_key": "..."
}
```

- 审批是 REST 命令；返回 `audit_event_id`。
- 首版签名可用“账号+角色+理由+证据哈希”；不要伪造密码学签名；若需要电子签名，后续接 WebAuthn/组织 SSO。
- 拒绝必须带理由；拒绝不会删除 artifact，只改变状态/路由。

---

## 8. DeepSeek 与 ModelGateway

### 8.1 现状（官方文档，2026-10-23）

DeepSeek API 与 OpenAI/Anthropic 兼容：

- OpenAI base：`https://api.deepseek.com`（部分 SDK 需 `/v1`，用 SDK 统一处理）；
- Anthropic base：`https://api.deepseek.com/anthropic`；
- 官方当前模型标识为 `deepseek-flash` 与 `deepseek-v4-pro`；旧的 `deepseek-chat` / `deepseek-reasoner` 已宣布在 2026-07-24 停用（以实施时官方文档为准）；
- 支持 tool calling、JSON output、streaming、上下文缓存等（具体能力按官方文档与实测）。

> 不要在代码里硬编码旧模型名；用 `DEEPSEEK_MODEL_FAST` / `DEEPSEEK_MODEL_REASON` 配置，并在启动时做一次 capability probe。

### 8.2 配置

```dotenv
# 仅服务端；不要提交 .env
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_MODEL_FAST=deepseek-flash
DEEPSEEK_MODEL_REASON=deepseek-v4-pro
MODEL_PROVIDER=deepseek
MODEL_MAX_RETRIES=3
MODEL_TIMEOUT_SECONDS=120
RUN_TOKEN_BUDGET=400000
RUN_COST_BUDGET_CNY=20
```

（模型名/价格以官方文档与账户实际可用列表为准；不要在本设计里承诺具体价格。）

### 8.3 角色路由

| 角色 | 默认模型 | 参数 | 约束 |
| --- | --- | --- | --- |
| 抽取/格式化/翻译 | fast | temperature 0–0.2，JSON | Pydantic 校验；不写 claim |
| 文献摘要/span 候选 | fast/reason | 低温度 | 只提交 artifact，必须可定位 |
| 规划/假设/协议草稿 | reason | 低温度、明确结构 | 人类选择/冻结 |
| Judge/评审自检 | reason | 低温度、rubric | 独立上下文；不写 claim |
| 稿件句草稿 | reason | 中等温度 | 只能绑定现有 claim；不许新增事实 |
| 变更归因 | reason | 低温度 | 只提议处置，不自动签 |

### 8.4 结构化输出与工具调用

- 统一 `ModelGateway.complete(task, schema, tools, budget)`；不允许业务代码直接拼 HTTP。
- JSON：`response_format={"type":"json_object"}` + prompt 明确 schema；DeepSeek JSON 模式不保证绝对 schema，必须 Pydantic 校验 → 失败重试/修复 → 再失败转人工。
- 工具：tool schema 由 Pydantic 生成；最多 N 个工具；工具调用必须先过权限/沙箱；不存在“模型随意跑 shell”。
- 流式：SSE 只转发摘要/状态与最终结构化结果；token 级草稿可在编辑器显示，但不落库为最终证据。
- 重试：429/5xx/超时指数退避；JSON/schema 失败有限重试；不能因为重试而改变 evidence。
- 模型审计：记录 `provider/model/version/params/prompt_hash/input_hash/output_hash/tokens/cost`；不记录 key；不默认持久化原始 reasoning_content（若 provider 返回，作为临时内容处理，只保留简短理由码/结论）。

### 8.5 Key 与隐私

- `.env`/Secret Manager；单用户可用本地 `.env`，团队用密钥库。
- 若做 BYOK：服务端加密保存、解密只在调用时、永不回传前端；key 不进日志/事件/导出。
- 项目材料可能包含未发表数据：默认只发送必要的片段给模型；提供“本地模型/自托管”配置；发送前做敏感信息扫描。
- 任何外部 API 调用都记录用途与数据范围；没有用户授权不把私有稿件发给第三方。

### 8.6 小测与 fallback

- 启动时做 capability probe：JSON、tool call、长上下文、流式、超时。
- 若 DeepSeek 的 JSON/tool 在某任务不稳定：改用宽松解析 + 校验 + 人工复核，或切换 provider；不能静默降低证据要求。
- provider 切换必须记录在 run 的 model audit；不同模型的结果不能混为同一 evidence。
- 不把“使用 DeepSeek”当作效果承诺；最终质量由任务、证据、评审与人类编辑共同决定。

---

## 9. Skill 系统：预置、受控下载与自进化

### 9.1 Skill 是什么

Skill 是**过程包**，不是 Agent、不是 claim writer。它声明：

- 能做什么（capability）；
- 需要什么输入、产出什么 artifact；
- 允许调用哪些工具/网络/文件；
- 证据契约（产物如何被 Evidence 接受）；
- 验证方式（静态检查、golden cases、dry-run）；
- 版本、来源、许可证、签名、兼容性、租约与撤销。

### 9.2 包格式

```text
my-skill/
├── skill.yaml          # manifest（机器读）
├── SKILL.md            # 给 Agent/人读的程序性说明
├── scripts/            # 可执行步骤（沙箱内）
├── tests/              # 单元 + golden
├── examples/           # 输入/输出样例
└── LICENSE
```

### 9.3 Manifest（示例）

```yaml
id: knowledge.openalex-search
version: 0.3.0
kind: retrieval
license: MIT
source:
  type: github
  repo: example/openalex-skill
  commit: 8f2c1d
  sha256: "..."
  signature: "..."        # 可选，首版至少 sha256 + 人工复核
compatibility: ">=0.1 <1.0"
permissions:
  network: ["api.openalex.org"]
  fs: ["project:read"]
  model: ["embedding"]
allowed_tools: ["http.get", "json.parse"]
inputs:
  query: QuerySpec
outputs:
  hits: SourceHit[]
  coverage: CoverageReceipt
evidence_contract:
  produces: ["SourceHit", "Span", "CoverageReceipt"]
  requires: ["project_id", "query"]
  forbidden: ["claim.write", "export.write"]
verification:
  static: ["no_host_write", "no_secret_read", "license_present"]
  golden: ["tests/golden/*.json"]
  dry_run: true
lease:
  ttl_days: 90
  scope: project
```

### 9.4 生命周期（硬门）

```text
register → validate → dry-run → pilot → active → deprecated → revoked
```

| 状态 | 条件 | 能做什么 |
| --- | --- | --- |
| registered | manifest/来源/许可存在 | 只能查看 |
| validated | schema/权限/静态扫描通过 | 可 dry-run |
| pilot | dry-run + golden 通过；人批准 | 只在 shadow/项目范围运行 |
| active | 人签 + 租约生效 | 可用于确证运行 |
| deprecated | 新版本/维护问题 | 不再新用；已有依赖复核 |
| revoked | 人撤/复评失败/安全事件 | 依赖 artifact 进入复核；阻断导出 |

- 没有自动 `active`；Agent 不能给自己发租约。
- 租约含 scope、版本、依赖快照、生效/到期、复评触发、回滚指针。
- 撤销沿 `SkillRun → SkillArtifact → Claim/EA → Manuscript Sentence/Figure` 传播；未处置即阻断 G5。

### 9.5 预置技能目录（建议）

| 类别 | Skill | 产物 | 证据约束 |
| --- | --- | --- | --- |
| 接入 | `intake-audit` | IntakeProfile、gaps | 只读元数据；不执行 |
| 文献 | `openalex-search` | SourceHit、CoverageReceipt | 不写 claim；不把摘要当全文 |
| 文献 | `pdf-parse-spans` | Span | 页-段-句锚点；无全文不读 |
| 文献 | `citation-verify` | CitationCheck | DOI/Crossref；不生成假引用 |
| 构思 | `gap-card` / `hypothesis-generate` | GapCard、HypothesisCard | 记录否证条件；自评只作 ranking |
| 设计 | `protocol-freeze` | Protocol、RunPlan | 指标/停止/预算；人工冻结 |
| 执行 | `docker-repro` | RunCapsule、Attempt、FailureRecord | 镜像/seed/日志；失败不记 0 |
| 判定 | `judge-score` / `counterfactual` | Verdict、EA、CF 记录 | 独立 Judge；来源=rerun |
| 证据 | `claim-compose` | Claim、EvidenceLink | 只能 Evidence 创建 |
| 证据 | `semantic-support-audit` | SemanticAudit | 结构≠语义；抽样人工 |
| 写作 | `outline` / `section-write` | 大纲、Sentence、Slot | 只绑定 claim；不新增事实 |
| 图表 | `figure-build` / `figure-audit` | Figure、FIG-AUDIT | 数据=run；图注一致 |
| 核验 | `q1-check` / `closure-export` | Q1Report、ExportBundle | 硬门；阻断不绕过 |
| 维护 | `impact-closure` / `change-repair` | ImpactClosure、ChangeSet | 变更重闭合 |
| 自进化 | `skill-dry-run` / `ev-evaluate` | DryRunReceipt、AdmissionRecord | 固定实例、隐藏评测 |

（`review-internal` 只能做内部自检，不生成或冒充同行评审。）

### 9.6 下载/安装：允许“自行下载”，但不允许“自行执行”

**允许的来源**：

1. 产品内置 `skills/builtin`（随版本发布、受测试）；
2. 官方/团队维护的 Skill Registry（签名或哈希 + 版本）；
3. 用户显式提供的一个 URL/GitHub release，**必须人工确认**；下载包进入隔离区。

**安装流水线**：

```text
resolve → fetch (HTTPS/pinned commit) → verify sha256/signature
→ license check → manifest validate → static scan (no host write/secret read)
→ sandbox dry-run → golden tests → human review → pilot lease
```

**禁止**：

- 自动从任意网页下载代码并在宿主执行；
- 自动 `active`、自动读取环境密钥、自动访问任意网络；
- 把下载的 SKILL.md 当作系统指令直接覆盖系统策略（prompt injection）；
- 无许可证/无法追溯 commit 的包进入导出依赖；
- 自动把外部效果数字写进我们的评测。

### 9.7 自进化：候选，不是自动升级

> 现有框架的 RSI/A-Evolve/ARIS/AutoResearch/DeepScientist 机制对照，见 [23](23-开源自改进机制对照-从A-Evolve-RSI-Anything到我们的Lease-Gated-Runtime.md)。

自进化只在**技能/过程协议**层发生，不自动改研究问题、门槛、判据或 claim。

**运行底座（来自 [19](19-RSI出题规范对照-自进化运行纪律反思.md) 的四个缺口）**：

1. **固定实例 + 统一预算**：同一个可执行 artifact/问题/基线/指标/预算跨轮不变；否则 EV4 只能审理由。
2. **租约控制器**：lease 是 P0 前硬门；回滚恢复 artifact 快照；撤销阻断下一次确证运行。
3. **公开/隐藏分离**：开发只可见 public/validation；最终冻结后独立 hidden verifier，成绩不回灌。
4. **step 账本**：父版本、patch、公开评测收据、对照/消融、成本、负结果、子实验/完整 step 区分。

**候选流水线**：

```text
failure trace / observed gap
→ candidate hypothesis (why it failed, what to change)
→ patch or new skill (no claim/gate changes)
→ static + permission check
→ sandbox dry-run
→ public golden evaluation
→ shadow/pilot
→ EV0 prediction (ranking only)
→ EV1 reason chain
→ EV2 retention + lease
→ EV3 transfer (near/far domain)
→ EV4 capability delta on held-out
→ human admission
→ active lease or rejected/revoked
```

**EV0–EV4**：

- EV0 只排序/预算，不进入 because；
- EV1 记录“为何被接受”的理由链，不是单一分数；
- EV2 租约/版本/谱系/到期/复评/回滚；
- EV3 适用域护照；相似度不是迁移证据；
- EV4 留出任务、效应区间、成本、判定者、周期；没有对照不写增益。

**ProcessProtocol（PF-P0–P8）**：

- 只改变同阶段的检查顺序、模板、预检、失败路由和复跑策略；
- 不改变研究问题、假设、显著性门槛、判据、署名与责任；
- 状态：active / pilot / rejected / revoked；
- 记录 last_run、counterfactual、gates、lease、next_run、boundary；
- 所有数值/状态仍是 SIM，直到真实固定实例实验完成。

**“自行下载 skill + 自进化”的安全版本**：

- Agent 可以**发现/推荐** registry 中的 skill，生成安装候选；
- 下载/安装需要人工批准；执行在沙箱；网络与文件权限最小化；
- Agent 可以**生成** skill/patch 候选；不能自动 active；不能绕过 EV/human；
- 所有候选写入 step 账本；拒绝也保留理由与反例。

### 9.8 许可证纪律

| 来源 | 许可证 | 我们的用法 |
| --- | --- | --- |
| K-Dense `scientific-agent-skills` | MIT（以仓库为准） | 可参考/适配，保留 attribution/license |
| `AI-Research-SKILLs` | MIT（以仓库为准） | 可参考/适配，保留 license |
| `Academic Research Skills` | CC BY-NC 4.0（以仓库为准） | 只读/对照；不直接打包进商业交付 |
| 其他网络 Skill | 逐包核验 | 无许可证/无法追溯 → 不安装、不进依赖 |

> 许可证会变化；实施时以仓库 LICENSE 为准，并在 skill manifest 记录 SPDX 标识和来源 commit。

### 9.9 现状判断：self-improvement-ready，还不是 self-improving

先把结论说清：

- **机制层已经体现**：9.7 有 `Observation → Candidate → DryRun → Public/Hidden → EV0–EV4 → human → Lease → revoke`；[23](23-开源自改进机制对照-从A-Evolve-RSI-Anything到我们的Lease-Gated-Runtime.md) 有 retained/incumbent、2×2、step ledger；[22](22-可扩展工程架构与论文创新点-从Demo到可维护证据运行时.md) 把 claim/export/run/lease 四条不变量写进代码边界；demo 有 EV/租约的 SIM 镜头。
- **阶段层还没有闭环**：S1 / S2–S3 / S4–S5 / S6 / S8–S12 / S13–S16 没有各自的固定实例、incumbent baseline、主指标、隐藏集和租约范围。EV4 目前是“通用四问”，不是“这一阶段到底有没有变好”。
- **工程层没有证据**：没有真实的 SkillRun 归因、do-nothing 对照、跨阶段干扰测试；E7/E8 未跑。因此现在只能称 **self-improvement-ready runtime**，不能称“系统会自我进化/越跑越强”。

这不是推翻 9.7，而是给“准入层”补上“阶段测量层”。否则自改进只剩状态机。

### 9.10 分阶段自改进矩阵

原则：**每个阶段只改执行技能/过程协议，不改研究问题、claim、门槛、判据、署名**。每条候选都要有固定实例、对照、成本、负结果与租约。

| 阶段 | 可变对象（只能改这些） | 观测与触发 | 固定实例（建议规模，待跑） | 主指标 / 隐藏与租约 |
| --- | --- | --- | --- | --- |
| **S1 文献** | 检索式扩展、源路由、筛选顺序、抽取 schema/prompt | coverage gap、无 span 支撑、引文错误、单条成本 | 冻结语料快照 + 20–30 个问题 + 200–300 个 gold spans；检索预算固定 | gold-span recall @ budget、citation precision、CoverageReceipt 完整度、cost/query；隐藏 1/3 问题；租约绑 domain+corpus version，索引/语料变更即撤销 |
| **S2–S3 Idea** | 发散 lens、prior-work 检索策略、短名单流程、idea 卡模板；**评分 rubric 与权重固定** | 重复、缺少否证条件、人审拒绝、不可行 | 12–20 个 problem cards + 冻结证据包 + 固定 rubric；2 名评审 | 否证条件完整率、与本地证据重复率、human novelty/feasibility、cost/idea；隐藏 4–6 卡；租约绑问题族，证据更新即撤销 |
| **S4 设计** | DesignCard 模板、检查清单、preflight、失败路由；**指标/阈值固定** | G2 退回理由、缺负对照、预算超限 | problem + baseline + metric contract + budget；人工冻结 | G2 一次通过率、设计完整度（指标/停止/对照/预算）；隐藏 problem cards；租约绑模板范围，协议变更即撤销 |
| **S5 执行** | 环境修复、preflight、harness 配置、重试/日志策略；**Judge 与指标固定** | 失败类别、重跑方差、低 evidence yield、成本 | Docker image + task + baseline + 3 seeds + 预算；模板/协议版本 pin | valid run rate、evidence yield/GPU-hour、方差、恢复时间；隐藏 task/seed；租约绑 template version，模板/基线变更使旧 run 失效 |
| **S6 图表** | 绘图模板、polish 轮、布局/图注检查 | 渲染失败、图-数不一致、图注漂移 | 冻结 run data + FigureSpec + 目标体裁 | data-figure mismatch rate（目标 0）、render success、可读性 rubric；隐藏数据/图 spec；租约绑模板/领域，数据版本变更即撤销 |
| **S8–S12 写作** | 体裁大纲、章节 prompt、润色、图-文同步；**claim/槽位规则固定** | 无支撑句、缺槽位、引文错误、人工改动大 | evidence ledger + outline + 体裁 + 12 节；同一 Writer 模型/预算 | unsupported sentence rate、claim-slot coverage、citation precision、human edit distance；隐藏 evidence pack/章节；租约绑 genre/venue，claim/证据版本变更即撤销 |
| **S13–S16 核验** | 审计清单、交叉核对 prompt、缺陷路由、导出 preflight；**门禁判据固定** | 漏检、误阻断、Closure 缺口、导出失败 | manuscript + artifacts + 20–30 个 seeded defects | defect recall、false block rate、Closure 完整度、导出可复现；隐藏 8–10 个缺陷；租约绑审计范围，新缺陷类触发复评 |

> 这张表的作用不是“保证提升”，而是把每个阶段的 **candidate / incumbent / do-nothing** 放到同一张可比表上。没有这张表，EV4 只能写“看起来更好”。

### 9.11 什么叫“有效”：固定实例、对照与判定

**判定单位**不是“整个 Agent”，而是 `StageLease` 范围内的一次 skill/process 变更。`StageLease` 是 9.7 的 `Lease` 在阶段上的子类型，scope 至少含 `{stage, domain, genre, template_version}`；过期、越界或依赖变更都必须撤销：

```text
Δ = metric(candidate) - metric(incumbent)
同模型 / 同语料 / 同预算 / 同任务族
随机过程至少 3 seeds；报告均值、区间、成本
```

**接受规则（建议，写进 pre-registration）**：

1. 主指标达到预注册的 MDE，且 95% CI 下界 > 0；或“非劣 + 成本显著更低”；
2. **硬不变量零违反**：claim 只能由 Evidence 创建、export 只能由 Closure、Run 绑模板/协议、lease 可撤销并传播；
3. 隐藏集不回归超过预注册容差；隐藏结果冻结后才可见，不能回写候选选择；
4. 成本不超预算；负结果必须入库；
5. 人工准入签字；没有签字只能 `pilot`，不能 `active`。

**必须有的三个对照**：

- `do nothing`：不改变任何 skill/process；防止“改了很多，其实只是模型波动”；
- `incumbent`：当前 active 版本；严格优于才替换，允许“不劣 + 更便宜”；
- `2×2 crossing`：旧/新 skill × 旧/新任务；至少一个近域迁移 + 一个远域拒绝案例。

**跨阶段干扰**：S1 的检索策略变化会改变 S3 的输入，S5 的修复策略会改变 S8 的证据量。候选必须在一条完整 S0–S16 固定实例上跑一次 end-to-end，报告下游是否退化；不能只在单阶段离线集上“赢了”就 active。

**判定结果只有四种**：`admit` / `pilot-only` / `reject` / `no-decision`。`no-decision` 表示实例或预算不足，不允许写成“有效”。

### 9.12 可借的 Skill 清单（本地路径 / 许可 / 借什么）

路径简写：

- `DS` = `oss/full/ResearAI__DeepScientist/src/skills`（Apache-2.0）
- `AS` = `oss/AutoSci-main/.claude/skills`（MIT）
- `AR` = `oss/Auto-claude-code-research-in-sleep-main/skills`（MIT）
- `KD` = `oss/Scientific-Agent-Skills-curated/skills`（MIT）
- `AI` = `oss/AI-Research-SKILLs-curated`（MIT）
- `AC` = `oss/AutoResearchClaw-main/.claude/skills`（MIT）

| 阶段 | 可借 Skill | 借什么 | 我们必须自写 |
| --- | --- | --- | --- |
| S1 | `DS/scout/SKILL.md`、`KD/literature-review/SKILL.md`、`AS/ingest/SKILL.md` | 最小未知量 framing、coverage/records vs studies/局限、paper→wiki 图边 | 授权中文库检索日志、中文源规范化、句级 span 抽取 |
| S2–S3 | `AS/ideate/SKILL.md`、`AS/novelty/SKILL.md`、`DS/idea/SKILL.md` | 五阶段发散、把被淘汰 idea 的失败原因作为 anti-repetition memory、客观契约/board packet | 本地证据 novelty、重复/负迁移惩罚、固定 rubric 的评分卡 |
| S4–S5 | `DS/baseline/SKILL.md`、`DS/experiment/SKILL.md`、`AS/exp-design/SKILL.md`、`AR/experiment-audit/SKILL.md`、`KD/statistical-analysis/SKILL.md` | comparator identity/metric contract、PLAN/CHECKLIST、非线性 ablation、假 GT/归一化作弊审计、检验/效应量/功效 | 模板版本 pin、失败归因、evidence yield/GPU-hour、隐藏 task/seed |
| S6 | `DS/paper-plot/SKILL.md`、`DS/figure-polish/SKILL.md`、`AR/figure-spec/SKILL.md` | render→inspect→revise、成品图打磨、确定性 JSON→SVG | 图-数据哈希/版本联动、中文核刊图规范 |
| S8–S12 | `DS/paper-outline/SKILL.md`、`DS/write/SKILL.md`、`AS/paper-plan/SKILL.md`、`AS/paper-draft/SKILL.md`、`AS/paper-compile/SKILL.md`、`AI/20-ml-paper-writing/ml-paper-writing/SKILL.md` | 证据→大纲、按章节 job 写作、venue 格式/编译、顶会结构 | 中文核刊格式、句级 claim slot、AI 使用声明（不做 AIGC 规避） |
| S13–S16 | `AR/citation-audit/SKILL.md`、`AR/paper-claim-audit/SKILL.md`、`AR/integrity-forensics/SKILL.md`、`DS/finalize/SKILL.md` | 零上下文引文核验、论文数字对 raw results、span-anchored 诚信审计、收口 | ClosureReport/导出 manifest/哈希/AI 使用记录、撤销闭包 |
| 自改进 | `AC/a-evolve/SKILL.md`、`AR/meta-optimize/SKILL.md`、`AR/meta-apply/SKILL.md` | Solve→Observe→Evolve→Gate→Reload；proposer 只读、applier 特权落地、jury-at-landing、人工触发 | EV0–EV4、固定实例、hidden eval、StageLease、依赖撤销 |

> `AR/meta-apply` 最值得学的是**权限边界**：proposer 只能 stage，不能写；唯一能落地的是人工触发的特权 applier，而且 jury 在落地时重新跑，不信任 producer 写的 verdict。我们的差异是再加固定实例、hidden eval、lease 与证据闭合撤销。
>
> `oss/Academic-Research-Skills-curated` 是 **CC BY-NC 4.0**：只读/对照，不进入产品交付；CycleResearcher 是研究专用许可，不复用/不打包/不再分发。

### 9.13 推荐实现顺序：先 S5，再 S1，再写作

**第 0 步（不做自修改）**：先加 `StageInstance` 注册表、`SkillRun` 归因、`do-nothing` 基线。没有这三样，后面所有 delta 都不可信。

**第 1 步：S5 执行/复现（最优先）**。理由：结果客观、可用 Docker pin、容易被独立 Judge 复核。固定 8–12 个任务、每个 3 seeds、隐藏 3–4 个；候选只做“preflight/环境修复/失败路由”一个 patch；主指标 `valid run rate` + `evidence yield/GPU-hour`。这是毕设最可能拿到的硬证据。

**第 2 步：S1 文献**。冻结语料 + 20–30 问题 + 200–300 gold spans，隐藏 1/3；候选只改检索式/筛选顺序/抽取 schema；主指标 `gold-span recall @ budget` + `citation precision`。这一步能直接支撑中文核刊的“证据覆盖”叙事。

**第 3 步：S8–S12 写作**。固定 8–12 个 evidence pack + 3 种体裁，隐藏 3–4 个；候选只改章节/体裁 skill；主指标 `unsupported sentence rate` + `claim-slot coverage` + `human edit distance`。不要用“文风像不像人”当主指标。

**第 4 步：跨阶段与论文声明**。做 S1→S3、S5→S8 的干扰测试、2×2 crossing、近域/远域迁移；只有 E7/E8 真正跑完，才写“自改进有效”。论文创新点建议写成四条可测贡献：阶段条件化的 skill 演化、StageLease/撤销闭包、evidence-yield 指标、do-nothing/incumbent/hidden 的判定协议；不要写成“通用科研智能体自我进化”。

### 9.14 并发多智能体：哪些阶段并行、怎么合并、怎么防失控

> 不另造角色体系：沿用 [09](09-系统架构与流程编排设计.md) §4.3 的 13 个角色与 [18](18-GitHub Pages部署与多智能体Skill设计.md) 的 Conductor / Scout / Builder / Executor / Judge / Auditor。这里补的是**并发编排、合并策略、权限隔离与团队策略自改进**。

#### 9.14.1 先判断“该不该多智能体”

多智能体不是能力，是**用 token/时延换覆盖与独立视角**。只有同时满足以下条件才拆：

1. 子任务可并行，彼此低耦合；
2. 不需要共享可写状态（或能切成独立 workspace）；
3. 需要独立视角/冗余覆盖（检索、候选、批判、审计），而不是强顺序推理；
4. 固定实例上，多智能体相对单 Agent 的质量/成本/时延有可测优势。

强顺序阶段（S4 设计冻结、S8 大纲、S12 合并修订、S15 终审、S16 导出）**默认单写者**；多智能体只做旁路可行性探测，不并发写同一产物。

#### 9.14.2 五种编排模式与阶段映射

| 模式 | 做什么 | 适用阶段 | 默认上限 | 合并方式 |
| --- | --- | --- | --- | --- |
| **P0 单写者** | 一个角色写，其他只读 | S0/S4/S7/S8/S12/S15/S16 | 1 | 无合并；人工门 |
| **P1 fan-out / fan-in** | 并行生产，统一收口 | S1/S2/S6/S9/S10 | 见下表 | `union_dedup` / `rank_select` / `single_writer` |
| **P2 有界辩论/集成** | 独立 critic/reviewer 多轮 | S3/S11/S14 | 3 轮；2–4 角色 | 问题清单 + 冲突卡；**不按多数票定性** |
| **P3 并行执行** | 独立沙箱/run 同时跑 | S5e/S5c | 2 run | 各自 RunCapsule；Judge 独占 |
| **P4 独立审计** | 规则 + 独立复核并行 | Q0/Q1/S13 | 2–3 审计者 | 问题清单；不直接改稿 |

#### 9.14.3 逐阶段编排

| 阶段 | 谁并行 | 默认上限 | 单写者/合并 | 硬禁止 |
| --- | --- | --- | --- | --- |
| **S1 文献** | Scout 按来源轴（arXiv/OpenAlex/中文库/引文链）并行；Reader 按论文簇并行 | 3–5 Scout；检索 8、解析 4、抽取 4 | Claim Curator 收口；`union_dedup` + coverage | 摘要当全文；无 span 建 claim；并发写同一来源记录；中文库仅走授权 API/机构订阅 |
| **S2 Idea** | Ideator 按 lens 并行（in-domain / cross-domain / failure-driven / cost-aware） | 3–5 Agent；20–50 候选 | 聚类 + 去重 + `rank_select` | 共享聊天室互相污染；把数量当质量 |
| **S3 收敛** | Critic + 独立 novelty checker 并行 | 3 轮；2–3 Critic | 规则排序 + 冲突卡；人 G1 | 多数票产生“真理”；LLM 自评替代人审 |
| **S4 设计** | 只并行 feasibility probe（算力/成本/伦理） | 1 个设计写者 | Architect 单写；人冻结 | 并发写同一 Protocol；Agent 改阈值 |
| **S5e 探索** | 沙箱并行试跑 | 2 run；不进 Judge | 各自记录；不合并成 claim | 共享 workspace；探索结果冒充确证 |
| **S5c 确证** | 2 个 run 并行；Judge 独占 | 2 run | 每 run 独立 RunCapsule；Judge 串行判定 | Work 与 Judge 争 GPU；同一 workspace 双写 |
| **S6 图表** | 每图独立 Figure Builder | 最多 4 图 | 图包单写者；数据 hash pin | 一图多写者；图数据不回链 run |
| **S8 大纲** | 无 | 1 | Architect/Writer 单写；G3 | 并行改大纲 |
| **S9 证据卡** | 按节并行组装证据卡 | 每节独立 | Claim Composer 单写 claim；Curator 准入 | Writer 创建 claim；跨节抢同一槽位 |
| **S10 写作** | 按节并行生成 | 最多 3 节 | 单合并 Editor；槽位只绑定 | 并行改同一节；无证据补写 |
| **S11 批判** | 4 类 Critic 并行（逻辑/证据/新颖性/表达） | 4 个独立上下文 | 问题清单 union；冲突卡 | Critic 直接改稿；Critic 与 Writer 共享上下文 |
| **S12 修订** | 无 | 1 | Writer/Editor 单写；最多 2 轮 | 多 Agent 并发改同一段 |
| **S13 核验** | 规则检查 + 独立 Verifier | 2–3 | 问题清单；Q1 汇总 | 审计者改稿；用生成者自评替代 |
| **S14 评审模拟** | 2–3 个 reviewer 角色 | 2–3 轮 | 模拟报告；仅自检 | 冒充真实同行评审；自动投稿 |
| **S15/S16** | 无 | 1 | 人签 + Export Auditor | 并发导出；绕过 G4/G5 |

> 这些上限与 [09](09-系统架构与流程编排设计.md) §5.12 一致；如果任务需要突破上限，必须新建 `StageRun` 并重新申请预算，不允许子 Agent 自行扩编。

#### 9.14.4 共享状态：artifact store 是黑板，不是聊天室

- Agent 之间**只传引用，不传长对话**；下游从 artifact store 读 `Span / Claim / EA / RunCapsule / Draft`，不读上一轮完整上下文。
- **一对象一写者**：Scout 不写 claim，Writer 不写 EA，Critic 不改稿，Judge 不写 Work 工作区；合并是一个显式的 `merge` 任务，不是隐式覆盖。
- **合并策略必须声明**：
  - `union_dedup`：来源/候选/问题清单，按稳定 key 去重，保留 provenance 与冲突项；
  - `rank_select`：按**冻结 rubric** 排序取 top-k，记录落选者与理由；
  - `single_writer`：设计/大纲/稿件/导出，只能一个写者，其他提交 patch 建议；
  - `conflict_card`：分歧不平均、不投票，保留双方证据与主张，交 G1/G4 或人工裁决；
  - `quarantine`：失败/未验证分支不进入合并，只保留记录。
- **合并回执** `MergeReceipt`：输入 artifact 哈希、策略、输出、冲突、丢弃项、成本；没有回执的合并不能进入下游。
- **幂等**：`AgentTask` 带 `idempotency_key`；重试返回同一 artifact，不重复建 claim/run。

#### 9.14.5 并发安全与预算

- **只有 Conductor 能派生子任务**；默认只派一层 `AgentTask`，AgentTask 只能调用工具、不能再派生 Agent；如未来需要二层，`max_depth=2` 且必须单独申请 lease；递归委派默认关闭。
- **预算预留**：每个 `AgentTask` 调用前预留 token/GPU/时长，结束后结算；并发不能超卖同一预算；超预算停止新任务并输出未完成清单。
- **取消树**：取消 `StageRun` 必须级联取消子任务与沙箱；已产生 artifact 保留但标 `cancelled`。
- **Judge 隔离**：独立队列、独立 workspace、独立上下文、隐藏 rubric；Judge 运行时不与 Work 争 GPU；Work 不能读 Judge 的隐藏答案。
- **权限 token**：每个 AgentTask 只带本角色的最小权限（读哪些 artifact、写哪个 workspace、能否调用 shell/网络）；Skill 权限按角色收窄，不按 skill 自放大。
- **失败隔离**：一个分支失败不污染其他分支；只合并 `admitted/verified` 的 artifact；失败原因进 FailureRecord。

#### 9.14.6 多智能体策略本身怎么自改进

把“团队怎么组”也当成候选对象，而不是写死在代码里：

```text
TeamPolicyCandidate {
  stage, pattern, role_set, fanout_width,
  decomposition_rule, merge_policy, critic_set,
  model_mix, handoff_schema, adaptive_trigger
}
```

**可以改**：角色组合、fan-out 宽度、任务分解、合并策略、critic 组合、模型档位、交接 schema、何时从单 Agent 扩成多 Agent。
**不能改**：claim/EA、gate/rubric、判据、署名、导出规则。

**评测**：同一批固定实例，比较 `single-agent baseline`、`incumbent team`、`candidate team`；主指标沿用 §9.10 的阶段指标，另加协调成本：

| 协调指标 | 含义 | 目标 |
| --- | --- | --- |
| duplicate work rate | 重复检索/重复候选/重复实验占比 | 越低越好 |
| merge loss rate | 合并时丢失的有效证据/候选占比 | 越低越好 |
| conflict rate / resolution time | 冲突数与人工解决时间 | 有记录，不强行归零 |
| judge disagreement | 独立 Judge 与规则/复核分歧 | 作为风险信号，不作真理投票 |
| cost per admitted artifact | 每个被准入产物的 token/GPU/时延 | 不高于 incumbent |
| isolation violations | Work 读 Judge/越权写 | **必须为 0** |

**接受规则**：团队候选必须在阶段主指标上不劣于 single-agent，且成本/时延在预算内；只有“质量更好且成本可接受”才允许默认多 Agent。否则默认单 Agent，多 Agent 只在触发条件下临时展开。

**自适应 fan-out（建议作为论文创新点之一）**：

```text
默认 single-agent
→ 触发：coverage 不足 / 候选多样性低 / 连续同类失败 / 评分接近 / 高风险 claim
→ 有界 fan-out（不超过阶段上限）
→ 合并 + 独立 Judge
→ 触发消失后收回单 Agent
```

这比“固定 5 个 Agent 一起上”更可辩护：它把多智能体当成**可测量的预算分配策略**，而不是能力叙事。

**租约**：`TeamPolicyLease` scope 至少含 `{stage, pattern, max_width, model_mix, prompt_version}`；模型/角色 prompt/交接 schema 任一变化都触发复评；撤销时沿 `AgentTask → Artifact → Claim/EA → Manuscript` 传播。

#### 9.14.7 API、事件与 demo

- 数据对象：`StageRun {stage, pattern, max_parallel, merge_policy, budget, lease_id}`；`AgentTask {task_id, stage_run_id, role, skill_ref, input_refs, workspace_id, idempotency_key, budget, stop_condition}`；`MergeReceipt`。
- SSE 新增：`stage.fanout`、`agent.started/completed/failed`、`artifact.created`、`conflict.detected`、`merge.completed`、`judge.started/completed`、`team_policy.lease.activated/revoked`。
- Demo 不画“聊天泡泡”，画**并行泳道 + artifact 引用 + 合并节点 + 封存的 Judge + 成本表 + 冲突卡**；取消按钮必须能级联取消子任务。所有数字仍标 SIM，直到真实运行。

#### 9.14.8 不能做

- 不把多 Agent 自由对话当共享状态；不并发写同一 artifact；不让多数票生成 claim/verdict；
- 不让子 Agent 无限派生、绕过预算、读 Judge 隐藏答案；
- 不为“看起来高级”在 S4/S8/S12/S16 强行并行；
- 不把 Agent 数量、辩论轮数、token 消耗当作能力提升证据。

### 9.15 论文与实验同时进行：双轨编排与同步屏障

“边跑实验边写论文”可以做，但必须区分**可提前写的文本**与**必须等证据的结果性内容**。否则就会出现“先写结论、再补实验”的倒置，直接破坏 claim/EA 闭合。

#### 9.15.1 两条轨道，不改变 canonical 门

```text
实验主轨：S4 设计冻结 → S5e 探索 → S5c 确证 → EA/Verdict → S6 图
论文辅轨：S1 证据 → S8-pre 预大纲 → S10-pre 非结果章节 →（等待 EA）→ 结果章节
```

- `S8-pre` / `S10-pre` 是**预写作产物**，不是 canonical 的 G3 大纲或终稿；G3/G4/G5 仍然按 S0–S16 执行。
- 论文辅轨可以在 G2 冻结后启动，但只能使用 `PaperContract` 中标记为 `allowed_pre_evidence` 的章节与槽位。
- 实验主轨的 `RunCapsule / EA / FailureRecord` 是唯一能填结果槽的证据；论文辅轨不能写 claim、不能改判据。

#### 9.15.2 什么能提前写，什么不能

| 可以提前写（`allowed_pre_evidence`） | 必须等 EA/Claim 才能写（`evidence_required`） |
| --- | --- |
| 引言的问题背景、研究问题、贡献的“待验证”表述 | 摘要中的结果数字、性能结论 |
| 相关工作、领域背景、方法动机 | 结果节的数值、显著性、对比结论 |
| 方法/协议/实验设置（来自已冻结的 G2） | “优于/达到/首次”等比较性 claim |
| 限制、风险、伦理、AI 使用声明骨架 | 结论、贡献的最终措辞 |
| 图表模板、坐标轴、caption 骨架 | 带最终数据的图、表、误差棒 |
| 引用占位（必须已核验 DOI/元数据） | 任何未核验的参考文献 |

**硬规则**：结果性内容在证据到达前只能用 `Slot(status=pending_evidence)` 占位，例如 `[PENDING: RUN-0311 / EA-...]`，不能写成自然语言结论，也不能用“预计/大约/可能”绕过。

#### 9.15.3 同步屏障与时间线

```text
B0  G2 冻结：Protocol + TaskSpec + PaperContract v0（provisional）
     ├─ 实验线：S5e/S5c 运行（2 run 上限；Judge 独占）
     └─ 论文线：S10-pre 写引言/相关工作/方法/限制；结果槽只占位

B1  EA 到达：Claim 准入（Evidence/Curator）→ 结果槽可绑定
     ├─ 实验线：S6 图（数据 hash 绑定 run）
     └─ 论文线：写结果/摘要数字/结论；图注与正文同步

B2  G3：最终大纲 + 图计划冻结 → S10 证据性章节定稿
B3  Q1/G4：全稿核验 + 人签
B4  G5：Closure + Export；任何 stale slot/claim 阻断导出
```

- `B1` 之前允许论文线先写“方法与协议”，因为它们的证据是 G2 冻结件，不是运行结果；
- `B1` 之后才允许填结果；如果实验失败，论文线只能降级/删除 claim，或把失败写进限制，不能“绕开失败写成功”；
- `B2` 之前的大纲是 provisional，不能把预写作当成 G3 已通过。

#### 9.15.4 状态模型：槽位比段落更可靠

```text
PaperContract.status: provisional → frozen_at_G3 → exported
Slot.status:         empty → reserved → pending_evidence → bound → stale
ClaimProposal.status: proposed → promoted/rejected
Claim.status:        admitted → stale   # Claim 只能由 Evidence 创建
Figure.status:       template → data_pending → final → stale
```

> 预写作阶段只能有 `ClaimProposal`，不能有 `Claim`；`Claim` 只能由 Evidence/Curator 在 EA 到达后创建。

- Writer 只能填 `bound` 槽；`pending_evidence` 槽在 UI/导出中显示为待证据，不得渲染成正文；
- 每个 `bound` 槽必须带 `evidence_ref`（EA/Claim/Span）与 `run_ref`（如适用）；
- 结果/图/claim 任一版本变化，`impact-closure` 把受影响的 `Slot` 标 `stale`，并阻断 G4/G5；
- 论文线与实验线共享 `EvidenceBoard` 的只读视图；Writer 不能改 `Claim/EA/Run`。

#### 9.15.5 调度、预算与隔离

- **队列分离**：实验线走 `sandbox_cpu/sandbox_gpu + judge`；论文线走 `llm`。两者可同时进行，但 Judge 仍独占，不能与 Work 争 GPU。
- **预算分轨**：项目预算下分 `experiment_budget` / `paper_budget`；预写作优先用 fast 模型，结果性章节与核验用 reason 模型；不能挪用 Judge 预算。
- **写者隔离**：实验线只写 `RunCapsule/EA/FailureRecord`；论文线只写 `Draft/Sentence/SlotProposal`；Claim 由 Evidence/Curator 准入。
- **取消/失败**：取消实验线不删除已有草稿，但所有依赖该 run 的槽变 `stale`；实验失败不得自动把槽标 `bound`。
- **并发上限**：实验线 2 run；论文线最多 3 节并行；预写作不得同时改同一节；最终合并单写者。

#### 9.15.6 这套“重叠策略”本身怎么自改进

把重叠程度也作为 `OverlapPolicyCandidate`：

```text
OverlapPolicyCandidate {
  allowed_pre_evidence_sections,
  max_pending_slots,
  pre_draft_depth,
  sync_cadence,
  budget_split,
  figure_policy
}
```

**可改**：预写作章节集合、最大 pending 槽数、同步频率、预算分配、图模板提前量。  
**不可改**：claim/EA、G3/G4/G5、结果槽的 evidence_required 属性、导出阻断规则。

**评测**（同一批固定实例，对比 sequential 与 overlap）：

| 指标 | 作用 |
| --- | --- |
| lead time to signed draft | 主要效率指标 |
| stale sentence rate / rework rate | 结果变化导致的返工 |
| unsupported sentence rate | 质量硬指标，不能因 overlap 上升 |
| GPU idle time / token cost | 资源效率 |
| human edit distance | 人工修订成本 |
| evidence violations | 必须为 0（结果槽无 EA、导出绕过 Closure 等） |

**接受规则**：lead time 有显著改善，且 unsupported/stale 指标不劣化、evidence violations 为 0，才允许把 overlap 设为默认；否则回到 sequential。隐藏集与独立 Judge 照常适用。

**自适应重叠**：实验方差大/失败率高时降低 pre-draft 深度；证据稳定、方法已冻结时提高重叠。这个阈值由 `OverlapPolicyLease` 管理，scope 至少含 `{stage_pair, genre, max_pending_slots, sync_cadence}`；协议/证据 schema 变化即撤销。

#### 9.15.7 Demo 怎么表现

运行台同时显示两条泳道：

- **实验泳道**：S5e/S5c、GPU/沙箱、RunCapsule、Judge（封存）；
- **论文泳道**：S10-pre 草稿、pending 槽、引用占位；
- **同步节点**：EA 到达 → claim 准入 → 槽位从 `pending_evidence` 变 `bound`；
- **变更节点**：run 结果变化 → 受影响句子变 `stale` → G4/G5 阻断；
- **成本表**：实验 GPU/时延 vs 论文 token，分轨显示。

演示里不要把 pending 槽渲染成确定结论；`stale` 必须有可见的“需复核”标记，不能静默通过。

### 9.16 实验证据的采集、成形与入稿

> 对象与不变量沿用 [07](07-复现级验证与执行Harness设计.md) §5：`EA`、`Verdict`、`Claim`、`Slot`。这里补的是**从运行产物到论文可引用证据**的采集协议、证据卡、聚合规则与入稿检查。

#### 9.16.1 一条硬链：不是“日志”，而是“可重跑的证据”

只有下面这条链上的数字/图/结论才能进论文：

```text
RunCapsule / EA(source=rerun) → Verdict=scored → Claim=supported → Slot=bound → Export
```

- Agent 自己写的 summary、截图、聊天记录、手抄表格**都不是证据**；
- 探索 run（S5e）不进入 claim 图（I7）；确证必须来自冻结 protocol 的干净重跑；
- 每个进入正文的数字、表、图都必须有 `EA/Claim/Slot` 引用；没有引用就阻断，不靠“作者记得”。

#### 9.16.2 采集：Run Recorder 自动抓，Agent 不参与原始证据

采集器是确定性服务，不是 LLM。它订阅 run 事件，自动写入不可变 `EA`：

| 类别 | 必采字段 |
| --- | --- |
| 身份 | task/protocol 版本、image digest、code commit、data revision、dependency lock、seed、硬件 |
| 执行 | 完整命令、stdout/stderr、exit code、开始/结束时间、重试、成本 |
| 指标 | metrics.json/csv（含单位、方向、n、每 seed 值、均值/方差/CI） |
| 产物 | predictions、checkpoints、日志、表格、图数据（不是只有 PNG）、环境快照 |
| 失败 | failure category、attribution、是否可重试、对应日志 |
| 完整性 | 每个 artifact 的 SHA-256、产生者、run_id、captured_at、immutable |

规则：

- **不允许 Agent 自报结果作为 EA**；Agent 可以写解释，但解释必须引用 EA。
- 一个 artifact 一个 EA；EA 只读、内容寻址；路径可换，哈希不能换。
- 多 run 用 `run_family_id` 聚合；每个 run 独立捕获，禁止把不同 run 的 seed/指标拼成一条“漂亮结果”。
- 采集失败（缺日志/缺指标/缺环境）本身就是 `EvidenceDebt`，不能静默补零。

#### 9.16.3 成形：EvidenceCard 是稿件侧的聚合视图

`EvidenceCard` 不替代 07 的 `R/EA/Claim`，只做“这一条证据能不能支持这一句话”的稿件侧视图；字段只放引用，不复制原始数据。

```json
{
  "card_id": "EC-014",
  "question": "RQ-02",
  "claim_candidate": "在数据集 D、协议 P 下，方法 M 的指标 Y 高于 baseline B",
  "scope": "D / split S / metric Y / 3 seeds / 预算 C",
  "protocol_ref": "PROT-003@v2",
  "run_family": ["RUN-0311", "RUN-0312"],
  "metric_records": ["M-ACC-01"],
  "baseline_ref": "RUN-0301",
  "stats": {"mean": 84.7, "std": 0.5, "n": 3, "ci95": [84.0, 85.4], "test": "paired bootstrap"},
  "validity_threats": ["单机单卡", "数据截断"],
  "negative_results": ["seed=2 未显著"],
  "artifact_refs": ["EA-021", "EA-022"],
  "figure_refs": ["F-003"],
  "reproduction": {"command": "bash repro.sh", "image_digest": "sha256:...", "seed": 0},
  "status": "draft | admitted | rejected | stale"
}
```

成形规则：

- **每个数字/统计量必须来自 MetricRecord；每个 MetricRecord 必须来自 EA；每个 EA 必须来自 run。**
- EvidenceCurator 可以写卡片叙事、归纳 validity threat，但不能发明数值、不能改单位/方向/n。
- 缺 baseline、缺 seed 分布、缺 CI、缺环境、缺复现命令 → 卡片 `EvidenceDebt`，不得 `admitted`。
- 卡片必须写 scope/conditions；没有 scope 的“M 更好”不是 claim，是口号。

#### 9.16.4 聚合：报分布，不报“最好 seed”

- 使用**所有预注册 run/seed**；报告 mean/median、std/CI、n、每 seed 值；附录给 per-run 表。
- 预注册排除规则；排除必须写理由与原始记录；不能看到结果后再删 seed。
- 比较类实验用配对检验/效应量；baseline 必须同数据、同 split、同 metric、同调参预算。
- 方差大：加 seed 或降级 claim；不能只报最好一次。
- 失败 run 保留在 run family 中；不能只留成功 run。
- `best-of-N` 只用于候选选择，不能用于证据聚合；证据要的是分布，不是冠军。

#### 9.16.5 入稿：数字/表/图由渲染器填，Writer 只选 claim 与模板

| 稿件元素 | 来源 | Writer 能做什么 | 不能做什么 |
| --- | --- | --- | --- |
| 结果数字 | MetricRecord → Claim → Slot | 选 claim、选模板、写解释 | 手打数字、改单位、改 n |
| 结果表 | MetricRecord / EA | 选列、选格式 | 手抄、删失败 run |
| 图 | Figure data + plot code hash | 选图型、写 caption claim | 用截图、改数据点 |
| 摘要/结论数字 | admitted Claim | 引用已准入 claim | 新造数字、扩大 scope |
| 方法/协议 | G2 冻结件 | 解释、组织 | 改协议、改判据 |

- 结果段模板：`在 [D/split] 上，[M] 的 [Y] 为 [mean±std, n]；相对 [B] 的 [delta]，95% CI [..]，检验 [..]；见表/图 [..]。` 所有方括号都必须绑定。
- 摘要/结论只能引用 `supported` claim；不能出现新数字或“首次/最优”等未准入措辞。
- Q1 核验：数字→MetricRecord→EA→run；图→data hash→run；claim→EA；任一断链或 `stale` 阻断导出。
- 证据不足：降级 claim（缩小 scope/写 inconclusive）或回实验；不能“写得保守一点但数字不变”。

#### 9.16.6 最小证据包检查表

在 S9 建 claim 前逐项打勾；缺一项就写 `EvidenceDebt`，不得入稿：

- [ ] G2 冻结的 protocol / TaskSpec 版本
- [ ] image digest、code commit、data revision、dependency lock
- [ ] 完整命令、seed、硬件、预算
- [ ] stdout/stderr、exit code、重试记录
- [ ] metrics（单位、方向、n、每 seed 值、均值/方差/CI）
- [ ] baseline 同数据/split/metric/调参预算
- [ ] 统计检验/效应量（比较类实验）
- [ ] 失败 run 与负结果
- [ ] 每个 artifact 的 SHA-256 与 EA 引用
- [ ] 图数据 + 绘图代码 hash（不是只有图片）
- [ ] Verdict / EA / Claim 引用
- [ ] 一条可复现命令或复现包

#### 9.16.7 失败、负结果与矛盾证据

- 失败是证据：保留 `FailureRecord`，写进限制/失败分析；不能“只报成功”。
- 负结果：保留并标注；可支持“边界/不适用”claim；不能从 run family 中删除。
- 矛盾结果：生成 `ConflictCard`，保留双方 run/EA；不平均、不投票；claim 收窄或标 inconclusive，交人判断。
- 协议变更：新 protocol 版本、新 G2；旧 run 不混入新 claim。

#### 9.16.8 采集策略本身怎么自改进

`EvidenceCapturePolicy` 可以作为候选，但只改“采什么/怎么规范化/怎么聚合”，不改 I1–I8：

- 可改：必采字段、指标 schema 校验、缺失字段检测、聚合方式、证据卡模板、采集失败重试。
- 不可改：`source=rerun`、claim 准入、Q1/Closure 判据、导出阻断。
- 固定实例：归档 run + 隐藏 run；比较 `capture completeness`、`traceability rate`、`time-to-card`、`rework rate`、`unsupported sentence rate`；候选不能让任何一条 evidence violation 上升。
- 多智能体：每个 run 独立采集，单一 EvidenceCurator/Claim Curator 收口；并行 Agent 不能合并彼此的原始数据，冲突走 ConflictCard。

#### 9.16.9 不能做

- 不用 Agent 自报 summary/截图当证据；不用“最好 seed”当结果；不手打论文数字；
- 不把探索 run 混入确证；不跨 protocol 版本拼 run；不删除失败/负结果；
- 不让 Writer 创建 claim、改 EA、改图数据；不在缺证据时用模糊措辞蒙混；
- 不在有 `stale` 槽/未准入 claim 时导出。

### 9.17 写作任务识别与 Skill 适配：中文期刊 / 英文会议 / 学位论文 / 基金

写作不能只加载一个通用 `write` skill。正确顺序是：**先识别任务画像（WritingProfile），再路由到最小 skill bundle**；语言、venue、体裁、引用风格、交付格式任一不同，加载的 skill 与检查表都应不同。

#### 9.17.1 WritingProfile：先回答“写什么、写给谁、按什么规范”

```json
{
  "profile_id": "WP-014",
  "output_language": "zh-CN | en | bilingual",
  "venue_type": "zh_core_journal | zh_thesis | en_journal | en_conference | grant_zh | grant_en | report",
  "venue_name": "…",
  "discipline": "…",
  "genre": "research_article | review | thesis | proposal | report",
  "citation_style": "GB/T 7714-2015 | APA 7 | IEEE | Nature | venue-specific",
  "section_schema": "IMRAD | Chinese-core-journal | thesis-chapters | NSFC-modules",
  "deliverable": "docx | latex | markdown",
  "length_limit": "…",
  "anonymity": "none | double-blind | 活页匿名",
  "template_ref": "…",
  "confidence": 0.0,
  "evidence": ["用户明确说中文核心", "模板为 ctex", "期刊投稿指南"],
  "overrides": []
}
```

**识别信号（按优先级）**：

1. 用户显式目标：`中文核心/CSSCI/北大核心`、`SCI/EI`、`NeurIPS/ICLR/ACL`、`学位论文`、`国自然/国社科`；
2. 模板/格式：`ctex`/`xelatex`、`GB/T 7714`、`IEEEtran`、`neurips.sty`、`.docx` 校模板；
3. 目标期刊/会议的投稿指南、页数、匿名要求；
4. 示例论文/已有草稿的 section 结构与引用风格；
5. 文本语言比例只能作辅助信号，**不能只凭界面语言或作者母语判断**。

**硬规则**：

- `output_language` 与 `venue_type` 分开判断：中文作者写英文会议，仍走 `en_conference`；
- 置信度低或信号冲突（如“中文期刊”但给的是 IEEEtran 模板）→ 不静默选择，向人确认 top-2 候选与证据；
- 画像版本化；用户可 override，override 写入 Audit；
- 中途换 venue → 生成 `WritingMigration` change set，重新审计受影响章节，不悄悄换风格。

#### 9.17.2 路由：base + locale + venue + deliverable

不要把所有写作 skill 一次性加载。按四层组合最小 bundle：

| 层 | 作用 | 候选 |
| --- | --- | --- |
| **base** | 证据绑定、claim/slot、引文核验、图-文一致 | `claim-compose`、`citation-audit`、`paper-claim-audit`、`figure-audit` |
| **locale** | 中/英文写作习惯与语言检查 | 中文：`zLanqing/research-writing-skill`、`JingYangYuan/paper-write-4ss`；英文：`Master-cai/research-paper-writing`、`SNL-UCSB/paper-writing` |
| **venue** | 期刊/会议/基金模板与硬性格式 | `qinyan/venue-templates`（英文 venue/NSF）、`qinyan/nsfc-proposal`/`nssfc-proposal`（中文基金）、中文期刊/校模板由我们维护 |
| **deliverable** | Word / LaTeX / Markdown 产出 | `zLanqing/office-academic-skill`（DOCX/PPTX）、LaTeX 模板与编译检查 |

**典型路由表**：

| 画像 | 主 bundle | 关键检查 | 不能混用 |
| --- | --- | --- | --- |
| **中文核心期刊** | zLanqing `research-writing-skill` + JingYangYuan `paper-write-4ss` + 我们的中文期刊模板 + `citation-audit` + `figure-audit` | GB/T 7714、中文摘要/关键词、基金标注、图题双语、单位/量纲、栏目字数 | 不套 NeurIPS/IEEE 模板；不直接机翻英文摘要 |
| **英文会议** | Master-cai `research-paper-writing` + SNL-UCSB `paper-writing` + AI-Research `ml-paper-writing` + DeepScientist `paper-outline`/`write` + `citation-audit` | venue 模板、页限、匿名、related work 定位、supplementary | 不套中文期刊格式；不把中文长句直译 |
| **英文期刊** | Master-cai + SNL-UCSB + qinyan `scientific-writing`/`venue-templates` + `citation-audit` | 期刊 citation style、structured abstract、reporting guideline（CONSORT/STROBE/PRISMA 如适用） | 不混会议 page limit；不伪造 reporting checklist |
| **中文学位论文** | Tianyuai `scut-thesis-writing` + zLanqing `office-academic-skill` + 学校模板 | 章节编号、Word 样式、图表/公式编号、页码、参考文献、盲审格式 | 不套期刊短文结构；不绕过学校模板 |
| **中文基金（NSFC/NSSFC）** | qinyan `nsfc-proposal` / `nssfc-proposal` / `research-proposal` + 我们的基金模板 | 2026 NSFC 三模块/页限、NSSFC 活页匿名、AI 辅助声明、5 篇代表作 | 不把论文摘要当立项依据；不自动生成科学观点 |
| **英文基金** | qinyan `research-proposal` + `venue-templates`（NSF/NIH/DOE） | 资助机构模板、page limit、broader impacts、data management plan | 不混中文基金口径 |
| **人文/交叉** | lishix520 `academic-paper-strategist` + `academic-paper-composer`；中文社科用 JingYangYuan | 论证结构、平台/期刊规范、引文风格 | 不套 ML 论文的“实验优先”结构 |

> 这些仓库都已完整克隆到 `oss/writing-skills/`（见 §9.17.6）；`Academic Research Skills` 是 **CC BY-NC 4.0**，只读对照、不进产品。

#### 9.17.3 语言与 venue 的具体检查

**中文期刊/学位论文**：

- 引用：GB/T 7714（或学校/期刊指定版本）；中英文文献条目格式分别检查；
- 结构：摘要（目的/方法/结果/结论）、关键词、引言、方法、结果、讨论、结论、参考文献；
- 语言：中文标点、全半角、术语一致、避免“显著/先进/有效”无证据修饰；
- 基金/作者信息/单位/通信作者/利益冲突/AI 使用声明；
- 图表：图题/表题、双语标题（如期刊要求）、单位、显著性标记、数据来源；
- 字数/页数/栏目限制。

**英文会议/期刊**：

- venue 模板、页限、匿名、字体/边距、reference style、appendix/supplementary；
- section 逻辑、related work 定位、contribution 与 evidence 对应；
- 语言：时态、主动/被动、术语、数字/单位、统计报告；
- 审稿人视角：novelty、baseline、ablation、limitation、reproducibility。

**基金**：

- NSFC：立项依据/研究内容/研究基础三模块、页限、AI 辅助声明；科学观点必须由申请人提供；
- NSSFC：选题说明 300 字、活页匿名、学科评审差异；
- 英文基金：机构模板、broader impacts、data management plan。

**双语摘要**：作为两个独立 slot，claim/数字必须同源；禁止中文写“显著提升”、英文写“slightly improves”这类不一致。

#### 9.17.4 Skill manifest 增加写作维度

写作类 skill 的 manifest 除现有权限/证据契约外，至少增加：

```yaml
locale: zh-CN | en | multilingual
venue_types: [zh_core_journal, en_conference, grant_zh, thesis]
genres: [research_article, review, thesis, proposal]
citation_styles: [GB/T 7714-2015, APA7, IEEE]
deliverables: [docx, latex, markdown]
language_policy: monolingual | bilingual-abstract
```

加载器只加载与 `WritingProfile` 匹配的 bundle；不匹配的 skill 不进入上下文。许可证与来源 commit 仍按 9.8 记录。

#### 9.17.5 多智能体写作：同一画像、同一风格、单一合并

- 所有并行章节 Writer 共享**同一个 WritingProfile/style guide**；禁止每节各自选风格；
- 最多 3 节并行；最终单 Editor 合并；
- 设一个 `venue/language auditor`（可独立模型/上下文），检查引用风格、术语、摘要/正文一致、匿名/页限；
- 双语摘要由两个 Writer 分别写，但 claim/数字引用同一 Claim；单一 auditor 对比；
- 画像中途变更 → 所有受影响句子标 `stale`，重新走 style/venue audit。

#### 9.17.6 识别与路由本身怎么评测、怎么自改进

固定任务集建议覆盖：`zh_core_journal`、`zh_thesis`、`en_conference`、`en_journal`、`grant_zh`、`humanities` 六类，每类 3–5 个任务，中英文各半。

指标：

- routing accuracy / wrong-bundle rate；
- citation style violations（GB/T 7714 等）；
- format compliance（页限、匿名、模板）；
- unsupported sentence rate；
- human edit distance；
- cost / time-to-draft。

比较 `rule-only router`、`LLM-assisted router`、`incumbent router`；隐藏任务集；错误路由必须由人确认，不能自动切换。`WritingProfileLease` scope 含 `{venue_type, locale, template_version}`；模板/期刊指南变更即复评。

#### 9.17.7 已完整拉取的写作 skill 仓库

`oss/writing-skills/`（全部为 full git clone，含 `.git`；逐仓 commit/许可证见 `oss/writing-skills/CLONES.md`）：

| 仓库 | 语言/用途 | 许可 | 关键 skill |
| --- | --- | --- | --- |
| `zLanqing/codex-claude-academic-skills` | 中文优先；论文写作/Word/PPT | MIT | `research-writing-skill`、`office-academic-skill`、`scientific-toolkit-skill` |
| `Master-cai/Research-Paper-Writing-Skills` | 英文 ML/CV/NLP | MIT | `research-paper-writing` |
| `SNL-UCSB/paper-writing-skill` | 英文 systems/ML 修辞与 red team | MIT | `paper-writing` |
| `lishix520/academic-paper-skills` | 英文人文/交叉 | MIT | `academic-paper-strategist`、`academic-paper-composer` |
| `LeonChaoX/qinyan-academic-skills` | 中英/基金/venue | MIT | `scientific-writing`、`venue-templates`、`nsfc-proposal`、`nssfc-proposal`、`qinyan-paper-polish` |
| `JingYangYuan/paper-write-4ss` | 中文社科 | MIT | `paper-write-4ss` |
| `Tianyuai/SCUT-Thesis-Writing-Skills` | 中文学位论文/Word | MIT | `scut-thesis-writing` |
| `Orchestra-Research/AI-Research-SKILLs` | 英文科研/写作/评测 | MIT | `ml-paper-writing` 等 98 个 skill |
| `Imbad0202/academic-research-skills` | 英文 12-agent 论文流水线 | **CC BY-NC 4.0（只读）** | 只对照，不打包进产品 |

> 未纳入：`academic-humanizer`、`AIGC-Detector-Rewriter`、`humanize-mba-text` 等以规避 AIGC 检测为目的的仓库；写作链路不做检测规避。

---

## 10. 论文产出：从任务到可签署草稿

### 10.1 两种入口

1. **新论文/复现—扩展**：给定问题 + 代码/数据 + 目标体裁；走 S0–S16。
2. **存量稿件体检/修复**：导入 PDF/LaTeX + 代码/数据；抽取 claim/槽位，找无证据/过期/冲突，生成 ChangeSet 与修复计划。

首版建议先做 **入口 1 的一个固定任务**（一篇开放论文/仓库），再做入口 2；否则范围失控。

### 10.2 产物

| 产物 | 说明 |
| --- | --- |
| `Manuscript` | Markdown/LaTeX 版本；章节/句/槽 |
| `Figure[]` | SVG/PDF/PNG + 数据来源 + 图注 |
| `Claim[]` + `EA[]` | 结果/文献 claim 与证据链接 |
| `RunCapsule[]` | 运行快照、日志、镜像/seed |
| `ClosureReport` | Q1/G5 检查、未决项、风险 |
| `ExportBundle` | 稿件 + 图表 + 证据包 + AI 使用声明 + 复现清单 |
| `AIUsage` | 模型、用途、参数、成本、人工修改记录 |

### 10.3 质量检查（硬门 + 软门）

| 检查 | 类型 | 失败处理 |
| --- | --- | --- |
| 每个事实句有 slot | 硬（G3/Q1） | 阻断/退回写作 |
| 每个 claim 有来源/EA | 硬 | 不建 claim/退回 S9 |
| 每个数字有 run | 硬 | 阻断导出 |
| 引用 DOI/元数据可核 | 硬 | 删/换/标记未核验 |
| 图与 run/claim 一致 | 硬 | 重绘/阻断 |
| 跨节数字/术语一致 | 硬（Q1） | 回 S12 |
| 语义支持抽样 | 软/人审 | 标注 supported/weak/unsupported |
| 限制与 AI 使用声明 | 硬（G4） | 退回 |
| 人工终审/签署 | 硬（G5） | 不导出 |

### 10.4 “最好效果”怎么写才诚实

- 目标是**在固定任务/体裁/预算下，产出证据闭合、可维护、可签署的草稿**；不是“保证发表”。
- 质量由：检索覆盖、claim–span/EA 绑定、语义审计、复现、Q1/G5、人工编辑共同决定。
- 用固定实例 + 基线 + 人评；报告限制、失败、成本；不引用外部 SOTA 数字。
- 可以追求“比 LLM-only 草稿更少无证据句、更少假引用、更容易复核”，但必须用实验证明。
- 自动生成的是**草稿**；署名、投稿、科学判断与最终责任在人。

---

## 11. 前端信息架构

### 11.1 路由/视图

| 路由 | 视图 | 关键交互 |
| --- | --- | --- |
| `/intake` | 接入/体检 | 文件夹/URL/示例；只读扫描；候选方向 |
| `/runs/:id` | 运行台 | 阶段/对象流/指令流/契约/SSE；暂停/单步/聚焦 |
| `/runs/:id/evidence` | 证据工作台 | claim/span/EA/债务/语义审计/图 |
| `/runs/:id/manuscript` | 稿件 | 句/槽/图/claim 绑定；diff |
| `/runs/:id/changes` | 变更 | ChangeSet/影响闭包/处置/重闭合 |
| `/runs/:id/closure` | 签署/导出 | Q1/G5/证据包/人签/阻断 |
| `/skills` | 技能注册表 | manifest/来源/权限/测试/租约/撤销 |
| `/audit` | 审计 | run/AI usage/签署/成本/事件 |
| `/settings` | 模型/密钥 | provider/profile/budget；key 不回显 |

### 11.2 关键 UI 约束

- **证据对象优先**：点击 claim/EA/span/run 打开 inspector，显示 owner、版本、hash、状态、来源、失效影响；不是只显示聊天。
- **运行事件流**：SSE 驱动阶段、对象流、指令、门禁；断线重连；事件可展开为 artifact。
- **人签抽屉**：`gate.requested` 时暂停/弹出证据包、风险、未决项；签署必须写理由并记录 hash；不能一键代签。
- **REAL / SIM / DESIGN** 徽章：所有数字/状态有来源；公共站点 `LIVE · OPENALEX` 只表示公开检索，不表示运行实测。
- **Focus 模式**：一屏显示对象流 → 卡组 → 当前指令 → 反馈；日志/侧栏可折叠；详情抽屉按需展开。
- **不用 iframe 作为产品架构**：demo 可以嵌入；产品是独立 SPA + BFF。
- **可访问性**：键盘、焦点、对比度、错误提示；表格/图/编辑器可用；移动端只保证可操作，不做主演示。
- **复用 demo 设计 token**：宋体标题、等宽标签、淡蓝底、细线、紧凑卡片；把 demo 当设计规格，不当生产代码。

### 11.3 前端技术细化

- `@tanstack/react-query` 管理快照查询/缓存；SSE reducer 更新 run 事件与失效。
- Zustand 只存 UI：当前 run/stage、选中的 artifact、抽屉、focus、deck 页。
- `@xyflow/react` 画 claim–EA–run–sentence 图；节点点击打开 inspector。
- Monaco/CodeMirror 用于 JSON/LaTeX/diff；Tiptap 或 Markdown 编辑器用于稿件；只用一种编辑内核，避免双源。
- Playwright 覆盖：接入→运行→审批→导出→变更→撤销；SSE 断线；键盘；移动端基本操作。
- 错误/空态/加载态与 demo 一样精致；不做“无脑 spinner”。

---

## 12. 数据、存储、安全与合规

### 12.1 存储

- Postgres：对象、状态、门禁、claim/EA、审计、成本；JSONB 存契约快照；递归 CTE 做传播闭包；pgvector 只做派生索引。
- 对象存储：PDF、日志、图、导出包；内容寻址；不可变桶/目录；生命周期。
- Redis：队列、租约、缓存、限流；非权威。
- 审计：append-only；事件 + AIUsage + Signature + PolicyVersion；与业务同事务 outbox。
- 备份/恢复：Postgres 每日；对象存储版本；run 目录快照；导出包哈希。

### 12.2 安全

- key 在服务端 Secret/加密 BYOK；永不回传前端；日志脱敏。
- API 鉴权：本地单用户 token；团队 OIDC；角色（研究者/核验者/PI/管理员）。
- 沙箱：Docker、非 root、只读挂载、网络默认关、CPU/内存/时间限制、无宿主 socket；执行前人工授权。
- SSRF/路径穿越：URL allowlist、内网拒绝、文件路径规范化。
- 提示注入：论文/网页/工具输出是不可信数据，不是系统指令；工具调用需 policy 允许；引用来源与权限。
- 供应链：Skill 签名/哈希/许可证/静态扫描/沙箱/人工批准；禁止自动执行。
- 数据合规：只使用授权来源；不抓知网/万方/维普；不上传未授权全文；AI 使用可披露。
- A3：人签、导出硬门、实验安全、署名与最终责任在人。

### 12.3 红线

- 不生成 ghostwriting 交付、不伪造数据/引用、不规避 AIGC 检测、不自动投稿、不伪造同行评审、不未经授权抓取文献。
- 评审模拟仅为内部自检，不能冒充真实同行评审。
- 不把外部系统效果数字/star 数当作我们的结果或质量证明。
- 不把 SIM 指标写成实测；C1–C4/E7/E8 未运行前保持“待验证”。

---

## 13. 评测计划：证明什么、不证明什么

### 13.1 研究问题（建议）

| 编号 | 问题 | 主要指标 |
| --- | --- | --- |
| C1 | claim–span/EA 绑定能否降低无证据/假引用？ | 无证据句比例、引用可核率、人工支持率 |
| C2 | 独立重跑/判定能否提升结果可信度？ | 复现通过率、Verdict/EA 一致性 |
| C3 | 变更后能否定位 stale/孤儿并重闭合？ | 发现率、修复时间、导出阻断正确率 |
| C4 | 人签/闭包门是否可接受？ | 人工时间、漏检、误报、可用性 |
| E7 | 技能/过程协议能否跨轮保留？ | 固定实例、隐藏评测、回滚/保留 |
| E8 | 是否能迁移/带来能力增益？ | 留出任务、效应区间、成本 |

> 这些是设计中的评测问题，**不是已得结果**；C1–C4/E7/E8 仍待运行。

### 13.2 固定实例与基线

- 选 1 篇开放论文/1 个仓库 + 1 个固定任务；冻结数据、代码、指标、预算。
- 基线：LLM-only 写作/人工写作/简单 RAG；同一任务、同一模型预算。
- 隐藏集：最终 artifact 冻结后才跑；成绩不反馈；防止选择偏差。
- 人评：2–3 名领域评审；盲评；报告一致性；记录 AI 使用。

### 13.3 指标与验收（目标，不是承诺）

| 维度 | 指标 | 目标（立项时写死，跑后报告） |
| --- | --- | --- |
| 结构 | 事实句 slot 绑定率 | ≥ 99% |
| 引用 | 伪造引用 / 不可核引用 | 0 / 0 |
| 语义 | 抽样支持率（人评） | 待标定，目标 ≥ 90% |
| 复现 | 独立重跑通过 | 依任务定义 |
| 维护 | 变更后 stale 发现率/修复时间 | 100% 发现 / 时间待测 |
| 导出 | 未解析槽/无 EA 阻断 | 100% |
| 成本 | token/人民币/人工分钟 | 按 run 记账 |
| 自进化 | 固定实例隐藏评测 | 未运行，禁止宣称增益 |

**不证明**：通用科学发现能力、跨领域 SOTA、自动发表、替代同行评审、底层模型智力提升。

---

## 14. 仓库布局与实施路线

### 14.1 建议布局

```text
毕业设计/
├── apps/
│   ├── web/                 # React + TS + Vite SPA
│   ├── api/                 # FastAPI BFF + modules
│   └── worker/              # Python worker + Docker sandbox
├── packages/
│   ├── contracts/           # OpenAPI 生成的 TS 类型
│   └── ui/                  # 可选：design tokens/组件
├── skills/
│   ├── builtin/             # 预置技能
│   └── registry/            # 本地 registry index（不含未审代码）
├── site/                    # 现有静态站点（不改造成产品）
├── demo/                    # 现有 demo（设计规格）
├── docs/                    # 00–21
├── deploy/
│   ├── compose.yml
│   └── .env.example
├── scripts/
└── tests/
```

- `pnpm` + `uv`；`ruff`/`mypy`/`pytest`；ESLint/Prettier；Playwright。
- `compose`：api、worker、web、postgres、redis、minio；DeepSeek 外网 API。
- 首版不引入 Nginx 复杂配置；web 可用静态文件服务器。

### 14.2 分阶段（单人/毕设）

| 阶段 | 周期（估） | 交付 | 退出条件 |
| --- | --- | --- | --- |
| P0 对齐/冻结 | 1 周 | 本文档、论文 spine、数据模型、UI spec | 选定 1 个任务；确定 DeepSeek profile |
| P1 纵切 | 3–4 周 | 接入→claim/EA→run→closure→人签→导出；SSE；3 个视图 | 真实跑通一次；无 key 泄漏；审计完整 |
| P2 论文 | 3–4 周 | 大纲/写作/图/Q1/G5；Markdown/LaTeX/DOCX | 一篇固定任务的草稿 + 证据包；人评 |
| P3 技能 | 2–3 周 | builtin skills、registry、install/verify/dry-run/pilot/lease/revoke | 受控安装 + 撤销传播；无自动执行 |
| P4 自进化 | 2–3 周 | 固定实例、隐藏评测、step 账本、EV/PF | 只在固定实例上报告；不宣称通用增益 |
| P5 展示 | 1–2 周 | 静态站点/demo 更新、演示脚本 | 不把 SIM 说成结果 |

> 若团队更大，可并行 P2/P3；但 P1 纵切必须先完成。不要先做“全流程 UI”，再做后端。

### 14.3 第一条纵切的验收清单

- [ ] 读取一个真实项目/论文（本地或公开），生成 intake profile；
- [ ] 检索/读取产生可定位 span；未读全文不建 claim；
- [ ] 一个真实/沙箱运行产出 RunCapsule、Verdict、EA；
- [ ] Evidence 创建 claim；Manuscript 句绑定 claim；图绑定 run；
- [ ] G5 检查通过/阻断；人工签署/拒绝写入审计；
- [ ] 修改一个数字/依赖，产生 ChangeSet、stale 传播、重闭合；
- [ ] API key 不在浏览器/日志；SSE 断线可恢复；
- [ ] 测试覆盖 happy path + 至少 2 条失败路径。

---

## 15. 风险与开放问题

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 范围过大 | 做不完/只做 UI | P1 纵切；非目标清单；每周验收 |
| DeepSeek JSON/tool 不稳定 | 结构化输出失败 | 校验/修复/重试；人工兜底；provider fallback |
| 模型/价格变化 | 设计失效 | ModelGateway + env；capability probe；不硬编码 |
| 沙箱逃逸/供应链 | 安全事件 | Docker 隔离、权限最小化、Skill 审核、无宿主 key |
| 语义支持不足 | 结构闭合但意思错 | SemanticAudit + 人评；不宣称 truth |
| 评测泄漏 | 自进化结论无效 | 固定实例、公开/隐藏分离、隐藏 verifier |
| 许可证 | 不能交付 | manifest SPDX；CC BY-NC 只读；逐包核验 |
| 人类瓶颈 | 速度慢 | 人签只在关键门；界面给证据包；记录时间 |
| 论文质量不达发表 | 目标落空 | 固定任务/体裁；人评；不承诺；逐步提升 |
| 数据合规 | 法律/伦理风险 | 授权来源；不抓库；AI 披露；A3 |

**开放问题**：

1. 首发任务选哪篇开放论文/仓库？体裁是中文核刊、英文 IMRaD 还是国自然？
2. Postgres 还是 SQLite 起步？是否要团队/远程？
3. DeepSeek 预算与模型 profile；是否需要本地模型兜底？
4. Pydantic AI 还是 LangGraph？是否已有团队经验？
5. 人评专家从哪来、如何盲评、如何记录 AI 使用？
6. 是否把技能市场/自进化放入毕设主线，还是作为 extension？
7. 产品名最终用 ClaimWeave 还是更保守的学术名？

---

## 16. 与现有文档的关系

| 文档 | 本文如何承接 |
| --- | --- |
| [02](02-需求书-科研自动化与写作平台.md) | 产品目标/团队/验收 → 本文的 G1–G6 与路线图 |
| [04](04-自动化研究与写作流水线.md) | S 阶段、artifact 信封、质量门 → §5–§6 |
| [07](07-复现级验证与执行Harness设计.md) | RunCapsule/EA/失败记录 → §5、§9、§10 |
| [09](09-系统架构与流程编排设计.md) | 五层/角色/门禁 → §3、§6 |
| [11](11-自进化循环设计-准入理由、跨循环继承、迁移与能力增益.md) | EV1–EV4/租约/PF → §9 |
| [14](14-产品差异化与Demo反思-从证据链写作到证据运营工作台.md) | RWMT/六个对象/三幕 → §10、§11 |
| [16](16-科研Skill生态调研与动态流程编排.md) | 技能目录/渐进加载 → §9 |
| [17](17-基于Skill契约的上层微服务架构.md) | 模块/端口/四不变量/三 deployable → §3 |
| [18](18-GitHub%20Pages部署与多智能体Skill设计.md) | Pages 静态/本地运行时 → §3、§12 |
| [19](19-RSI出题规范对照-自进化运行纪律反思.md) | 固定实例/租约控制器/隐藏评测/step 账本 → §9.7 |
| [20](20-开源科研Agent框架调研-浙大SciToolAgent与主流技术栈.md) | 框架/技术栈证据 → §4、§9 |
| [22](22-可扩展工程架构与论文创新点-从Demo到可维护证据运行时.md) | 模块/端口/扩展点/架构测试与“系统贡献”表述 → §3、§4、§14、§8 |
| [23](23-开源自改进机制对照-从A-Evolve-RSI-Anything到我们的Lease-Gated-Runtime.md) | RSI/A-Evolve/ARIS/AutoResearch/DeepScientist 的自改进机制与 Lease-Gated Runtime → §9.7、§14 |

---

## 17. 参考（与证据等级）

| 来源 | 用途 | 等级 |
| --- | --- | --- |
| [DeepSeek API 文档](https://api-docs.deepseek.com/zh-cn/index.html) | 兼容格式、模型、工具/JSON/流式 | 官方文档（实施时复核） |
| [DeepSeek Change Log](https://api-docs.deepseek.com/updates/) | 模型名迁移与能力变更 | 官方文档 |
| [HICAI-ZJU/SciToolAgent](https://github.com/HICAI-ZJU/SciToolAgent) | 工具图谱/Planner/Executor/Summarizer | 仓库已核验 |
| [DeepScientist](https://github.com/ResearAI/DeepScientist) | 本地 daemon、UI 栈、skills 目录 | 仓库已核验 |
| [AI-Scientist-v3](https://github.com/SakanaAI/AI-Scientist-v3) | Docker/run 目录/rubric | 仓库 README |
| [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | Python + TS 前端形态 | 仓库已核验 |
| [AG-UI 1.0](https://www.sitepoint.com/ag-ui-1-0-stable-spec-agent-user-interaction) | Agent–UI 事件/审批 | 公开规范报道 |
| [K-Dense scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | 技能包/许可证 | 仓库入口 |
| 本地 `oss/`、`demo/`、`site/`、00–20 | 现有设计与演示 | 本地材料 |

> 外部效果数字、star 数、SOTA 提升均不作为本文结论；未运行的目标全部保持“待验证”。本文是设计稿，不是实现证明。

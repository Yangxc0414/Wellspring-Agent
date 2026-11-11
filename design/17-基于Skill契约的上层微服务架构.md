# 基于 Skill 契约的上层微服务架构：从工作台到证据运营平台

> 版本：v0.2 · 日期：2026-10-23 · 性质：上层架构调整设计，不新增实验结果
> v0.2 增量：补充“服务 ≠ 模块 ≠ 插件”的三种粒度、服务内六边形分层、五个可插拔端口（Retriever/Judge/Writer/Exporter/SkillRuntime）、插件 manifest 与生命周期、各服务内部模块，以及“目标态微服务、毕设先三个 deployable”的拆分标准。
> 上游依据：[09-系统架构与流程编排设计](09-系统架构与流程编排设计.md)、[11-自进化循环](11-自进化循环设计-准入理由、跨循环继承、迁移与能力增益.md)、[14-产品差异化](14-产品差异化与Demo反思-从证据链写作到证据运营工作台.md)、[15-调研补充](15-2026年9-10月调研补充与证据工作台实现.md)、[16-科研 Skill 生态调研](16-科研Skill生态调研与动态流程编排.md)、[04-流水线](04-自动化研究与写作流水线.md)、[07-复现级验证](07-复现级验证与执行Harness设计.md)
> 证据纪律：本文是架构设计，不是已部署系统；服务边界、事件、SLA 与容量均为 `[设计]`；没有运行微服务、没有做性能/一致性实验
> 适用边界：面向“证据运营工作台”的上层；不改变 A3 边界，不替代人工签署与最终责任

---

## 0. 一页结论

微服务适合这个系统，但拆分依据必须是**证据对象与责任边界**，不是阶段数、Agent 数或 skill 数。

建议采用：

```text
                    ┌─────────────────────────────┐
                    │  Workbench / Gateway (BFF)  │
                    └──────────────┬──────────────┘
                                   │ commands / queries
                    ┌──────────────▼──────────────┐
                    │  Workflow / Orchestrator    │
                    │  模板 · 能力图 · Run 状态    │
                    │  检查点 · 版本钉住           │
                    └───┬───────┬───────┬─────────┘
        ┌───────────────┘       │       └───────────────┐
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│ Knowledge     │       │ Execution     │       │ Skills        │
│ 检索 · span   │       │ Work/Judge    │       │ manifest      │
│ 覆盖 · 冲突   │       │ RunCapsule/EA │       │ sandbox/lease │
└───────┬───────┘       └───────┬───────┘       └───────┬───────┘
        │                       │                       │
        └───────────────┬───────┴───────────────┬───────┘
                        ▼                       ▼
                ┌───────────────┐       ┌───────────────┐
                │ Evidence      │◄──────│ Manuscript    │
                │ claim/EA/债务 │       │ 句/槽/图/版本 │
                └───────┬───────┘       └───────┬───────┘
                        │                       │
                        └───────────┬───────────┘
                                    ▼
                            ┌───────────────┐
                            │ Impact        │
                            │ ChangeSet     │
                            │ 影响闭包/处置 │
                            └───────┬───────┘
                                    ▼
                            ┌───────────────┐
                            │ Closure/Export│
                            │ 报告/签核/门禁│
                            └───────┬───────┘
                                    ▼
                            ┌───────────────┐
                            │ Audit / Eval  │
                            │ 事件/AI 使用  │
                            └───────────────┘
```

一句话：**工作流决定“这次做哪些能力”，Evidence 决定“什么能成为 claim”，Closure 决定“什么能导出”，Skills 只负责“怎么做”，Audit 记录“谁在何时做了什么”。**

v0.2 补充：目标态仍是微服务，但**可插拔点下沉到插件/端口层**——服务内用六边形分层隔离领域与基础设施，五个端口（Retriever、Judge、Writer、Exporter、SkillRuntime）承担算法/数据源/模型替换；毕设只交付 `web-bff`、`core`、`worker` 三个可部署单元，不把每个模块都拆成服务。

---

## 1. 为什么现在适合微服务

- **Skill 运行时天然是独立部署单元**：技能需要沙箱、权限、资源限制、独立升级与撤销；不应该和 UI/工作流进程混在一起。
- **执行服务需要独立扩缩容**：Work/Judge、Docker、GPU/CPU 任务与 Web 工作台的负载特征不同；执行失败不应拖垮工作台。
- **证据账本与导出需要强边界**：claim 的创建、失效传播与导出阻断不能被任意服务绕过；独立服务 + 私有数据 + 事件契约比“共享数据库 + 约定”更可控。
- **审计需要 append-only**：AI 使用、人工签核、技能租约与撤销必须独立于业务库，不能被业务更新覆盖。

但微服务不是目的。若按“P0–P8 各一个服务、13 个 Agent 各一个服务、177 个 skill 各一个服务”拆，会得到：

- 大量跨服务同步调用与分布式事务；
- 每个服务都要重复项目、权限、版本、错误处理；
- 一个本地 demo 需要几十个容器；
- 证据链的因果顺序难以保证。

因此先定边界，再定部署。

---

## 2. 服务边界（按证据对象拆，不按阶段拆）

| 服务 | 拥有的对象 | 主要命令 | 主要事件 | 为什么独立 |
| --- | --- | --- | --- | --- |
| **Gateway / BFF** | 项目会话、视图聚合 | 创建项目、打开工作台、提交命令 | — | UI 只与 BFF 通信；不直接访问领域库 |
| **Workflow / Orchestrator** | `WorkflowTemplate`、`RunInstance`、`Checkpoint` | 编译任务、启动/暂停/恢复、跳过可选阶段 | `RunStarted`、`StageSkipped`、`CheckpointRequired`、`RunCompleted` | 唯一掌握“这次做哪些能力、当前在哪、版本钉在哪”的服务 |
| **Knowledge** | `Source`、`Span`、`Query`、`CoverageReceipt`、`ConflictEdge` | 检索、去重、筛选、定位 span、生成覆盖回执 | `SpanAdded`、`SourceConflict`、`CoverageUpdated` | 检索/解析/冲突是独立负载，且需要来源版本与覆盖证据 |
| **Execution** | `RunCapsule`、`Attempt`、`Verdict`、`EA`、`Cost` | 启动 Work、独立 Judge、重跑、失败归因 | `RunScored`、`EACreated`、`RunFailed`、`CostRecorded` | 沙箱/算力/成本独立；执行失败不能拖垮工作台 |
| **Skills** | `SkillManifest`、`SkillLease`、`SkillRun`、`SkillArtifact` | 加载、dry-run、激活、运行、撤销 | `SkillLoaded`、`SkillActivated`、`SkillRevoked` | 技能是内容包，不是领域服务；统一运行时做权限/沙箱/租约 |
| **Evidence** | `Claim`（literature/result/manuscript）、`EvidenceLink`、`EvidenceDebt`、`SemanticAudit` | 创建 claim、绑定 EA/span、计算债务、登记冲突 | `ClaimCreated`、`ClaimStale`、`DebtChanged`、`ClaimBlocked` | 唯一能创建 claim 的服务；技能与执行只能提交 artifact |
| **Manuscript** | `Manuscript`、`Sentence`、`Slot`、`Figure`、`Binding` | 创建版本、绑定句/图、解析槽位、生成 diff | `SentenceBound`、`SlotUnresolved`、`ManuscriptVersioned` | 稿件是交付物，不是 claim 的附庸；版本与句级槽位独立演化 |
| **Impact** | `ChangeSet`、`ImpactClosure`、`Disposition` | 接收变更、计算影响、分派重跑/重写/复核 | `ChangeDetected`、`ImpactComputed`、`DispositionRequired` | 变更影响是跨证据/稿件/图的投影，独立于任何单个阶段 |
| **Closure / Export** | `ClosureReport`、`Signature`、`ExportManifest` | 重新闭合、检查硬门、签署、导出/阻断 | `ClosureFailed`、`ExportBlocked`、`ExportReleased` | 只有它能决定“能否出门”；不能被技能或工作流绕过 |
| **Audit** | `AuditEvent`、`AIUsage`、`PolicyVersion` | 追加事件、查询轨迹、导出审计包 | 订阅所有事件 | append-only；人工签核与 AI 使用必须可追溯 |
| **Evaluation**（可选） | `BenchmarkTask`、`EvalRun`、`Metric` | 跑 C1–C4、生成报告 | `EvalCompleted` | 评测与生产隔离，避免用评测数据反哺生产 |

> 不建议把 `Knowledge` 和 `Evidence` 合成一个“大证据服务”：检索是高频外部 I/O，claim 是强一致的核心账本，二者的扩缩容与失败模式不同。也不建议把 `Manuscript` 塞进 `Closure`：稿件版本与导出报告的生命周期不同。

### 2.1 三种粒度：服务 ≠ 模块 ≠ 插件

| 粒度 | 例子 | 变化频率 | 是否独立部署 |
| --- | --- | --- | --- |
| **服务** | Workflow、Evidence、Execution、Skills、Closure | 低；按 bounded context 演化 | 是 |
| **模块** | `TemplateRegistry`、`DebtCalculator`、`GateEvaluator` | 中；按用例/领域拆分 | 否，随服务部署 |
| **插件** | Retriever、Judge、Writer、Exporter、Skill | 高；按算法/数据源/模型替换 | 可选，由运行时加载 |

**关键判断**：可插拔改进主要发生在“插件”层，不是“服务”层。把每个插件都拆成微服务，会把一次替换变成一次分布式发布；把每个模块都当服务，会得到分布式单体。

### 2.2 服务内部采用六边形架构

每个服务内部固定五层：

```text
API / Event Handler      REST、gRPC、消息订阅
        ↓
Application / Use Case   命令、查询、Saga 步骤、幂等
        ↓
Domain                   实体、值对象、状态机、不变量
        ↓
Ports                    领域需要的接口（不依赖框架）
        ↓
Adapters                 Postgres、对象存储、事件总线、模型、沙箱、外部源
```

- Domain 不 import 任何 ORM、HTTP、消息队列或厂商 SDK；
- Port 由 Domain/Application 定义，Adapter 实现；
- 替换模型、检索源、Judge、导出格式，只替换 Adapter，不改 Domain；
- 每个服务只拥有自己的数据库 schema，不跨库 JOIN。

### 2.3 五个可插拔端口

只把高变化、可替换的能力做成端口；不要把每个函数都插件化。

| 端口 | 归属服务 | 输入 → 输出 | 不能做什么 |
| --- | --- | --- | --- |
| `RetrieverPort` | Knowledge | `QuerySpec` → `SourceHit[] / Span[] / CoverageReceipt` | 不能写 claim；不能把摘要当全文证据 |
| `JudgePort` | Execution | `RunCapsule + Rubric` → `Verdict + EA` | 不能被 Work 修改；不能跳过干净重跑 |
| `WriterPort` | Manuscript | `Claim[] + Slot[]` → `Draft` | 不能创建 claim；不能新增未被 claim 支持的事实 |
| `ExporterPort` | Closure | `ExportManifest` → `Artifact` | 不能跳过 GateEvaluator；不能改 claim 状态 |
| `SkillRuntimePort` | Skills | `SkillManifest` → `Lease + SkillArtifact` | 不能写领域库；不能绕过权限/沙箱/撤销 |

基础设施适配器（`ModelProvider`、`ObjectStore`、`EventBus`、`Sandbox`）也走端口，但它们是**技术适配**，不算科研插件，不应该出现在论文贡献里。

### 2.4 插件契约与生命周期

```ts
interface PluginManifest {
  id: string;
  version: string;                 // semver
  capability: "retriever" | "judge" | "writer" | "exporter" | "skill";
  inputs: JsonSchema;
  outputs: JsonSchema;
  permissions: string[];           // read:project / net:academic / exec:docker ...
  evidenceContract: string;        // 产物必须绑定什么
  verificationScope: string;       // 本插件不验证什么
  compatibility: string;           // 宿主/运行时版本
  tests: string[];                 // dry-run / golden cases
  license: string;
  signature: string;
  owner: string;
}
```

生命周期：

```text
register → validate(manifest/signature) → dry-run(golden cases)
→ shadow/pilot(lease, 小流量) → active(scope)
→ deprecated → revoked(依赖传播)
```

- 插件只能写自己的 artifact/返回值，不能直接写 Evidence/Manuscript/Closure 的库；
- 版本 pin + 兼容矩阵；破坏性变更升 major；
- 每个插件至少有一个 golden case 与一个失败样例；
- 合同测试（consumer-driven contract test）在 CI 中跑，不靠人工记忆；
- 插件撤销触发 `PluginRevoked`，Impact 重新计算依赖闭包。

### 2.5 各服务的内部模块

| 服务 | 内部模块（先做粗粒度） | 可插拔点 |
| --- | --- | --- |
| Workflow | `TemplateRegistry`、`TaskCompiler`、`CapabilityGraph`、`RunStateMachine`、`CheckpointManager`、`SchedulerPort` | 模板/配方；调度器适配 |
| Knowledge | `QueryPlanner`、`SourceAdapters`、`Deduper`、`Screener`、`SpanExtractor`、`CoverageCalculator`、`ConflictDetector` | 检索源、解析器、去重/筛选策略 |
| Execution | `RunOrchestrator`、`SandboxAdapter`、`JudgePort`、`VerdictScorer`、`EABuilder`、`CostMeter`、`FailureClassifier` | Judge、沙箱、评分 rubric |
| Skills | `ManifestValidator`、`PermissionEvaluator`、`DryRunRunner`、`SandboxPool`、`LeaseManager`、`ArtifactPublisher`、`RevocationPropagator` | 技能包本身；执行器适配 |
| Evidence | `ClaimFactory`、`EvidenceLinker`、`DebtCalculator`、`SemanticAuditPort`、`StalenessProjector`、`ClaimStateMachine` | 语义审计策略；债务权重 |
| Manuscript | `DocumentModel`、`SentenceSegmenter`、`SlotBinder`、`FigureRegistry`、`VersionDiff` | 体裁模板、分段/锚点策略 |
| Impact | `ChangeNormalizer`、`DependencyProjection`、`ImpactClosure`、`DispositionPlanner`、`RecomputeQueue` | 传播规则、处置策略 |
| Closure | `GateEvaluator`、`ReportBuilder`、`SignatureService`、`ManifestBuilder`、`ExportAdapter` | 导出格式、报告模板、签核策略 |
| Audit | `EventStore`、`AIUsageLedger`、`PolicyRegistry` | 存储后端；保留策略 |

### 2.6 当前模块的反思

- **9 阶段 / 13 Agent / 18 个 S 阶段是逻辑视图，不是模块边界。** 不要把它们一一映射为服务；服务边界按证据对象与责任拆。
- **Evidence 是 claim 的唯一写者。** Manuscript 只拥有句/槽/图；Closure 只读 claim 与 EA；Skills/Execution 只交 artifact。
- **Impact 与 Audit 是横切投影，不是阶段。** 它们订阅事件，不应该被塞进某个 P 阶段。
- **BFF 只做读模型聚合与命令转发**，不能包含“什么算闭合”的业务规则。
- **Skills 不是 Workflow 的一部分**：Workflow 只声明需要一个能力，Skills 负责加载/租约/沙箱；替换技能不改变 Workflow 代码。
- **不要为每个模块建数据库**：模块共享服务内的 schema；数据库边界跟服务走，不跟模块走。

### 2.7 架构选择：目标态微服务，毕设先三个可部署单元

目标态是 8–10 个 bounded-context 服务；但毕设不需要一开始就上十个容器。建议：

| 阶段 | 可部署单元 | 包含模块 | 什么时候拆 |
| --- | --- | --- | --- |
| **MVP** | `web-bff`、`core`、`worker` | BFF；Workflow/Evidence/Manuscript/Closure；Execution/Skills/Impact/Audit | 先证明纵切 |
| **Phase 1** | 拆出 `execution`、`skills` | 沙箱/算力/技能安全独立 | 执行/技能负载或安全需求出现 |
| **Phase 2** | 拆出 `impact`、`audit` | 事件驱动投影、append-only | 变更场景或审计需求增长 |
| **Phase 3** | 拆出 `knowledge`、`manuscript` | 检索/解析、句槽/版本 | 数据量/多人协作出现 |

**判断标准**：只有出现“独立扩缩容、独立安全边界、独立发布节奏、独立故障域”之一，才拆服务；否则留在同一 deployable 的模块里。

---

## 3. 核心流程（Saga，不是分布式事务）

### 3.1 新建一轮研究

```text
BFF → Workflow.CreateRun(template@version)
Workflow → 校验模板/权限 → RunStarted
Workflow → Knowledge.Prepare / Execution.Prepare / Skills.Preload
Workflow → 进入 P0 checkpoint（人工确认 TaskSpec）
```

### 3.2 检索到 claim

```text
Knowledge.Search → Source/Span/CoverageReceipt
Knowledge → SpanAdded
Evidence.CreateLiteratureClaim(span_id) → ClaimCreated
Manuscript.Bind(sentence, claim) → SentenceBound
```

### 3.3 执行到结果 claim

```text
Execution.Run → RunCapsule
Execution.Judge → Verdict(scored) + EA
Evidence.CreateResultClaim(run_id, ea_id) → ClaimCreated
Manuscript.Bind(sentence, claim, slot)
```

### 3.4 变更后的维护

```text
Impact.ChangeDetected(change_set)
Impact → 读取依赖投影 → ImpactComputed
Impact → DispositionRequired(rerun/rewrite/recheck)
Execution / Manuscript 执行处置
Closure.Reclose → ClosureReport
Closure.Sign(actor, scope) → ExportReleased | ExportBlocked
```

### 3.5 技能加载/撤销

```text
Skills.Load(manifest) → verify signature/permissions → dry-run → SkillLoaded(pilot)
Skills.Run → sandbox worker → SkillArtifact(artifact_id)
Skills.Revoke → SkillRevoked → Impact recompute dependent artifacts → Manuscript/Closure review
```

**关键**：技能只产生 `SkillArtifact`；Evidence 才创建 claim；Closure 才导出。任何服务都不能直接改别人的表。

---

## 4. 契约与不变量

### 4.1 Artifact 信封

沿用 `04-` §2.14：

```json
{
  "artifact_id": "ART-...",
  "artifact_type": "span|run|verdict|ea|claim|sentence|figure|closure",
  "project_id": "PRJ-...",
  "run_id": "RUN-...",
  "producer": "knowledge|execution|skill|manuscript|...",
  "version": 3,
  "status": "draft|confirmed|stale|blocked",
  "content_hash": "sha256:...",
  "inputs": ["ART-..."],
  "created_at": "..."
}
```

### 4.2 四条硬不变量

1. **claim 只由 Evidence 创建**：`result_claim` 必须引用 `scored` verdict + `EA(source=rerun)`；技能/执行不能直接写 claim。
2. **导出只由 Closure 执行**：未解析槽位、stale、冲突、无 EA → `ExportBlocked`；没有任何旁路。
3. **Run 钉住模板版本**：`run.workflow_id@version` 不可变；运行中改模板必须人工签核并创建新 revision。
4. **技能租约可撤销**：`SkillRevoked` 必须触发依赖 artifact 的复核；不能只在技能库里删一行。

### 4.3 事件契约

每个事件至少带：

```json
{
  "event_id": "EVT-...",
  "event_type": "ClaimStale",
  "schema_version": 1,
  "project_id": "PRJ-...",
  "correlation_id": "RUN-...",
  "causation_id": "EVT-...",
  "producer": "evidence",
  "occurred_at": "...",
  "payload": {}
}
```

- 消费者必须幂等（`event_id` 去重）；
- 生产者在同一事务写 outbox，再由 relay 发布；
- 失败进入 DLQ，不静默丢事件；
- 事件 schema 版本化，不破坏旧消费者。

---

## 5. 一致性与可靠性

- **不要分布式事务**：使用 Saga + outbox + 补偿；Evidence/Manuscript/Closure 的最终状态由事件驱动。
- **读模型**：工作台需要跨服务聚合时，由 BFF 或专用 read model 组装；不要跨库 JOIN。
- **最终一致**：`ImpactComputed` 到达前，工作台显示“影响计算中”；不能假装已经闭合。
- **失败关闭**：Closure 无法确认证据状态时，默认 `ExportBlocked`，而不是放行。
- **重试**：命令带 `Idempotency-Key`；执行失败有 attempts、失败分类与人工队列。
- **超时/熔断**：同步调用全部有 timeout；长任务异步化；技能/执行 worker 不阻塞 BFF。

---

## 6. 安全与权限

- **技能沙箱**：容器/gVisor/Firecracker 隔离；默认无网络；按 manifest 授予 `read:project`、`net:academic`、`exec:docker` 等 capability。
- **签名与版本**：技能 manifest 签名/哈希；只允许 allowlist + 版本 pin；撤销立即生效。
- **最小权限**：Knowledge 只读来源；Execution 只写 run/EA；Skills 只写 artifact；Evidence 只写 claim；Closure 只写 report/export。
- **人工签核**：作者/PI 的 Signature 由 Closure/Audit 记录；AI 使用、未解决项与限制随包导出。
- **审计**：所有跨服务命令与事件进 Audit；trace 带 `project_id/run_id/claim_id/skill_id`。

---

## 7. 毕设可落地的分阶段路径

不要一开始就上 10 个微服务。按“模块化单体 → 抽取高风险 worker → 再拆事件服务”推进：

### Phase 0（2–3 周）：模块化单体（可先一个进程）

一个进程/一个仓库，内部模块：

```text
web/ (BFF + Workbench)
workflow/  knowledge/  evidence/  execution/  manuscript/  closure/  audit/
```

- 模块间只通过接口/事件（进程内 event bus）通信；
- 每个模块独立 schema/namespace；
- 先跑通“一份稿件 + 一个 ChangeSet + 一次重跑 + 一次签署导出”。
- 如果要提前展示微服务边界，可拆成 `web-bff` + `core` + `worker` 三个 deployable，但事件契约与模块边界不变；不要为了“像微服务”把每个模块单独部署。

### Phase 1（2–3 周）：抽 Execution + Skills

- Execution 独立 worker（Docker sandbox）；
- Skills 独立 runtime（manifest/dry-run/lease/sandbox）；
- 通过 NATS/Redis Streams 或 HTTP 命令连接；
- 这是最需要隔离、最容易出安全事故的两块。

### Phase 2（2–3 周）：抽 Impact + Audit

- Impact 订阅 `ChangeDetected`、`ClaimCreated`、`SentenceBound`，维护依赖投影；
- Audit 订阅全部事件，append-only；
- 工作台通过 BFF 读 read model。

### Phase 3（可选）：抽 Knowledge + Manuscript

- Knowledge 独立检索/解析/覆盖回执；
- Manuscript 独立版本/句槽/图；
- 只有在检索量、稿件量或多用户需求真实出现时再做。

**毕设最小可交付**：Phase 0 + Phase 1 的 Skills/Execution；足以证明“技能加载/运行/撤销 + 证据门禁 + 变更维护”的纵切，不需要 10 个容器。

---

## 8. 数据与部署建议

| 组件 | 建议 | 备注 |
| --- | --- | --- |
| 数据库 | Postgres，每服务独立 schema/DB | 不共享表；claim/closure 强约束用事务 |
| 对象存储 | MinIO/S3，内容寻址 | artifact 不可变；按 hash 去重 |
| 事件总线 | NATS JetStream 或 Redis Streams（毕设）；Kafka（规模化） | 先 outbox，后接总线 |
| 图谱 | Postgres 邻接表 + 递归 CTE | 不急着上 Neo4j；先证明查询/传播需求 |
| 搜索 | Postgres FTS/OpenSearch | 检索与 claim 查询分开 |
| 部署 | Docker Compose（毕设）→ K8s（产品） | 先单机多容器，后编排 |
| 可观测性 | OpenTelemetry + 结构化日志 | trace 贯穿 run/claim/skill |
| 密钥 | Secrets/环境变量，不进镜像 | 技能不得读取未授权 secret |

---

## 9. 不该做的事

- **一个阶段一个服务**：P0–P8 是能力，不是部署单元；
- **一个 Agent 一个服务**：Agent 是角色，不是 bounded context；
- **一个 skill 一个服务**：技能是内容包，统一由 Skills 运行时加载；
- **共享数据库**：会让边界退化成“分布式单体”；
- **同步长链**：BFF 同步等待执行/技能/闭包会放大故障；
- **为了微服务上图数据库/Kafka/K8s**：毕设阶段先证明流程与证据，不证明基础设施规模；
- **技能直接写 claim 或导出**：绕过证据门禁，直接破坏系统可信性。

---

## 10. 与现有文档的关系

- `09-` 的五层组件、Agent 角色、9 个门禁仍是逻辑架构；本文把它们映射为服务边界，不改变门禁语义。
- `16-` 的“能力图 + 任务编译 + 技能运行时 + 证据权限”是本文的上层原则；本文补的是部署/通信/一致性。
- `18-` 把本文的服务边界落到“哪些能公开、哪些必须留在运行时”：GitHub Pages 只承载展示/公开检索/案例回放，Actions 做定时预计算，LLM/沙箱/密钥进入本地或边缘运行时；不改变本文的服务边界与硬不变量。
- `14-` 的 RWMT 三幕是产品主线；本文的 Impact/Closure 服务对应“变更—修复—签署”。
- `04-`/`07-` 的 artifact/EA/run capsule 是本文的领域对象；本文不重新定义它们。

---

## 11. 不可宣称

- 本文是架构设计，不是已部署微服务；没有性能、可用性、一致性或成本实验；
- 不写“微服务提升科研可信度”；可信度来自证据契约与导出硬门，不是部署形态；
- 不把服务数量当工作量或创新点；
- 不把外部 skill 仓库的机制当作本项目实现；
- 所有 demo 仍为 SIM，C1–C4/E7/E8 未运行。

---

## 附录：服务事件一览

| 事件 | 生产者 | 主要消费者 | 用途 |
| --- | --- | --- | --- |
| `RunStarted` | Workflow | Audit, BFF | 工作台进入运行态 |
| `SpanAdded` | Knowledge | Evidence, Manuscript | 文献 claim/句绑定 |
| `RunScored` | Execution | Evidence, Audit | 创建结果 claim 的前置 |
| `EACreated` | Execution | Evidence | 结果 claim 绑定 EA |
| `ClaimCreated` | Evidence | Manuscript, Audit | 句/图绑定 |
| `SentenceBound` | Manuscript | Closure, Impact | 闭合检查 |
| `ChangeDetected` | Impact | Workflow, Skills | 触发影响闭包 |
| `ImpactComputed` | Impact | Manuscript, Closure | 更新失效句/图 |
| `SkillLoaded` | Skills | Audit, BFF | 技能进入 pilot |
| `SkillRevoked` | Skills | Impact, Manuscript, Closure | 依赖产物复核 |
| `ClosureFailed` | Closure | Workflow, BFF | 阻断导出并回退 |
| `ExportReleased` | Closure | Audit, BFF | 生成可审计导出包 |

---

*本文为上层微服务架构设计，不替代 09-/04-/07- 的领域契约；所有服务边界、事件与部署均为设计，未运行、未做性能实验。*

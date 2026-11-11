# 22 · 可扩展工程架构与论文创新点：从 Demo 到可维护的证据运行时

> 版本：v0.1 · 日期：2026-10-23 · 性质：工程架构设计 + 论文表述建议  
> 输入：[17](17-基于Skill契约的上层微服务架构.md)、[19](19-RSI出题规范对照-自进化运行纪律反思.md)、[20](20-开源科研Agent框架调研-浙大SciToolAgent与主流技术栈.md)、[21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md)  
> 结论先行：**代码架构值得写进论文，但只能作为“系统/工程贡献”，不能把“用了分层/微服务/设计模式”本身说成研究创新。** 创新点必须是“架构机制让某个性质可被强制、可被度量、可被扩展”，并有实现与验证。

---

## 0. 判断

当前仓库有一份很好的**演示原型**，但没有可维护的产品代码：

- `demo/index.html` 约 480KB，CSS/JS 内联，状态是全局变量 + 直接 DOM 操作；
- `site/assets/app.js` 约 82KB，页面逻辑、检索、技能、案例等混在一个 IIFE；
- 没有类型化 API、没有后端、没有数据库、没有测试门禁；
- 它适合做导师演示和 Pages 展示，**不适合在它上面继续堆产品功能**。

所以第一件事不是“重构 demo”，而是**冻结 demo 作为设计规格**，另建一个从一开始就有边界、类型和测试的应用。否则后面接 DeepSeek、接 skill、接自进化，一定会变成屎山。

---

## 1. 先把“架构创新”说清楚

### 1.1 不能这样写

- ❌ “本文采用微服务架构，因此具有创新性。”
- ❌ “本文使用整洁架构/DDD/六边形架构，所以先进。”
- ❌ “本文代码分层清晰、可扩展，因此达到创新。”
- ❌ “本文用了 React/FastAPI/Postgres，所以工程创新。”

这些是**工程手段**，不是研究贡献；审稿人/答辩老师会问“所以呢？证明了什么？”

### 1.2 可以这样写

把架构写成一条**可验证的机制**：

> 面向证据闭合的科研 Agent 运行时，把 claim/EA/closure 的所有权固化为模块不变量；通过端口与 Skill 运行时隔离模型、检索、执行、导出等易变实现，使新增能力不需要修改证据核心，且不能绕过导出硬门。

它有四个可测点：

1. **不变量被强制**：尝试从 Skill/Writer 直接创建 claim、从 Manuscript 直接导出、运行中改模板、撤销后继续使用技能，都必须失败。
2. **扩展面有界**：新增检索源/模型 provider/Skill/体裁模板，只改 adapter/config/skill 包，不改 Evidence/Closure 核心。
3. **运行可复算**：固定实例、统一预算、step 账本、checkpoint/restore、隐藏评测；自进化不是面板状态。
4. **人签可追溯**：G0/G2/G3/G4/G5 的签署、理由、证据哈希进入 append-only 审计。

这四点可以写成**系统贡献**，并与主研究贡献（RWMT/证据闭合）绑定；它们不是“代码风格”，而是“让证据闭合在工程上不可绕过”的机制。

---

## 2. 目标架构：模块化单体 + 六边形 + 端口

### 2.1 一张图

```
┌────────────────────────────────────────────────────────────┐
│ apps/web  React/TS SPA                                     │
│  app shell / features / components / generated API client  │
└───────────────────────────┬────────────────────────────────┘
                            │ REST commands + SSE events
┌───────────────────────────▼────────────────────────────────┐
│ apps/api  FastAPI BFF + application modules                │
│                                                            │
│  api/          routes, auth, SSE, DTO validation           │
│  application/  use cases, ports, transaction boundaries    │
│  domain/       entities, value objects, invariants         │
│  adapters/     postgres, model, storage, event bus         │
│                                                            │
│  modules: project / workflow / knowledge / execution /     │
│           evidence / manuscript / impact / closure /       │
│           skills / audit / model_gateway                   │
└───────────────┬───────────────────────────┬────────────────┘
                │ outbox/events             │ jobs
┌───────────────▼─────────────┐   ┌─────────▼────────────────┐
│ Postgres（事实源）          │   │ apps/worker              │
│ Redis（队列/租约）          │   │ retrieval / sandbox /    │
│ Object Store（artifact）    │   │ judge / skills / hidden  │
└─────────────────────────────┘   └──────────────────────────┘
```

### 2.2 模块与公共接口

每个模块只有两类对外面：

- **Application API**：其他模块可调用的用例（例如 `Evidence.create_claim()`、`Closure.evaluate()`）；
- **Domain Events**：`claim.created`、`artifact.frozen`、`skill.revoked` 等，通过 outbox 发布。

**禁止**：

- 跨模块直接读/写对方表；
- 从 route 直接调用 ORM/LLM/Docker；
- 在 domain 里 import FastAPI/SQLAlchemy/OpenAI；
- 通过“共享 utils”隐藏跨模块依赖；
- 用一个 `services/` 大文件承载全部逻辑。

### 2.3 核心端口（只做 7 个，不要每件事都插件化）

| 端口 | 归属 | 输入 → 输出 | 不能做什么 |
| --- | --- | --- | --- |
| `ModelPort` | ModelGateway | prompt/messages/schema/tools → structured output | 不能写 claim；不能绕过预算/审计 |
| `RetrieverPort` | Knowledge | QuerySpec → SourceHit/Span/CoverageReceipt | 不能写 claim；不能把摘要当全文 |
| `ParserPort` | Knowledge | Document → Span/结构 | 不能改来源元数据 |
| `JudgePort` | Execution | RunCapsule + rubric → Verdict + EA | 不能被 Work 修改；不能跳过重跑 |
| `SandboxPort` | Execution | TaskSpec/镜像/seed → RunCapsule | 不能访问宿主密钥；不能写 evidence |
| `WriterPort` | Manuscript | Claim[] + Slot[] → Draft | 不能创建 claim；不能新增未支持事实 |
| `ExporterPort` | Closure | ExportManifest → Artifact | 不能跳过 GateEvaluator；不能改 claim |
| `SkillRuntimePort` | Skills | SkillManifest → Lease + SkillArtifact | 不能写领域库；不能绕过权限/租约 |

（`ArtifactStorePort`、`EventBusPort`、`ClockPort` 属于基础设施端口，可内部使用，不写成“科研插件”。）

### 2.4 领域不变量在代码里怎么强制

| 不变量 | 代码机制 | 测试 |
| --- | --- | --- |
| claim 只由 Evidence 创建 | `Claim` 无 public setter；只有 `Evidence.create_claim()` 能构造；其他模块只有 read port | 架构测试：非 Evidence 模块不得 import claim 写接口 |
| 导出只由 Closure 执行 | Export 命令只存在于 Closure；ExporterPort 只能由 Closure 调用 | 调用其他模块导出接口必须 403/不存在 |
| Run 钉模板版本 | `RunPlan` 冻结后不可变；`RunCapsule` 引用 hash；改模板生成新 revision | 改模板后旧 run 哈希不变；无 revision 的变更被拒 |
| 技能租约可撤销 | `SkillLease` 校验在 SkillRuntimePort；`SkillRevoked` 触发依赖闭包复核 | 撤销后调用返回 `LEASE_REVOKED`；依赖 artifact `stale` |
| 数字必须来自 run | Manuscript 编译时校验 numeric slot → EA → run | 手填数字/无 EA 数字在 G5 阻断 |
| 人签不可代签 | GateDecision 需要 actor role + reason + evidence hash | Agent token 调审批接口返回 403 |

> 这些测试是论文“工程贡献”的证据，不是附赠的单元测试。

---

## 3. 代码布局：让“新东西”有固定落点

```text
apps/
├── api/
│  └── src/
│     ├── api/                 # FastAPI routes、SSE、auth、DTO
│     ├── application/         # use cases、ports、unit-of-work
│     ├── domain/              # 纯领域对象/不变量，无框架
│     ├── adapters/            # postgres、openalex、deepseek、minio、bus
│     └── modules/
│        ├── project/
│        ├── workflow/
│        ├── knowledge/
│        ├── execution/
│        ├── evidence/
│        ├── manuscript/
│        ├── impact/
│        ├── closure/
│        ├── skills/
│        ├── audit/
│        └── model_gateway/
├── worker/
│  └── src/
│     ├── jobs/                # 队列 handler
│     ├── runtime/             # run harness、checkpoint、hidden eval
│     ├── sandbox/             # Docker adapter
│     └── skills/              # skill runtime
└── web/
   └── src/
      ├── app/                 # shell/routes/providers
      ├── features/            # runs / evidence / manuscript / changes / skills / audit
      ├── components/          # 可复用 UI
      ├── lib/                 # api client、SSE、query keys
      └── styles/              # tokens
packages/
├── contracts/                 # OpenAPI → TS 类型（生成，不手写）
└── ui/                        # 可选：跨 app 组件
skills/
├── builtin/                   # 预置技能
└── registry/                  # registry index（不含未审代码）
deploy/
├── compose.yml
└── .env.example
tests/
├── e2e/                       # Playwright
├── architecture/              # import-linter/依赖规则
└── fixtures/                  # golden evidence cases
```

### 3.1 依赖规则

```text
api → application → domain
        ↑
    adapters（实现 ports）
worker → application/ports（不反向依赖 api）
web → packages/contracts（只通过 HTTP/SSE）
```

- `domain` 不依赖任何外部框架；
- `application` 只依赖 domain + ports；
- `adapters` 实现 ports；
- `api` 只做协议转换/鉴权/SSE；
- `worker` 通过 application/ports 执行任务；
- 前端不 import 后端代码，只 import 生成的契约类型。

用 `import-linter` 或自定义脚本在 CI 中强制；违反即失败。

### 3.2 每条“新能力”的落点

| 要新增 | 只应改 | 不应改 |
| --- | --- | --- |
| 新检索源（Crossref/PubMed） | 新 `RetrieverPort` adapter + config + contract test | Evidence/Closure/Manuscript |
| 新模型 provider（DeepSeek/本地 vLLM） | 新 `ModelPort` adapter + profile + capability probe | workflow/evidence 核心 |
| 新 Skill | `skills/` 包 + manifest + tests + registry + lease | 领域表/claim/export 代码 |
| 新体裁模板 | `genre/` 配置 + Q1/G5 规则 + golden | 领域对象 |
| 新图类型 | `Figure` 子类型 + figure builder + audit 规则 | Closure 导出主流程 |
| 新存储/队列 | 新 adapter + compose 配置 | domain/application |
| 新 UI 视图 | `features/` + route + generated client | 后端 domain |

---

## 4. Run Harness：把“自进化”变成可复算的运行

[19](19-RSI出题规范对照-自进化运行纪律反思.md) 指出四个缺口；代码上对应四件东西：

### 4.1 固定实例

```text
Instance = {
  task_id, problem, input_data, code_base, baseline,
  metrics, constraints, budget, hidden_test_ref
}
```

- 实例冻结后不可改；跨轮必须引用同一个 hash。
- 目标/门槛/预算写进 `TaskSpec` 与 `RunPlan`；不能运行中改。

### 4.2 租约控制器

```text
LeaseController.assert_active(skill_or_protocol, run)
  → 校验 scope / version / expiry / revocation / dependencies
```

- P0 前硬门：没有 active lease，不能用该技能/协议进入确证运行。
- 撤销：写 `SkillRevoked` → 计算依赖闭包 → 标记 artifact stale → 阻断导出。
- 回滚：恢复 checkpoint/artifact snapshot；不是只改状态字段。

### 4.3 公开/隐藏分离

- 开发只读 `split=public|validation`；
- final artifact 冻结后，独立 worker 跑 `split=hidden`；
- 隐藏成绩不回灌到候选选择；选择偏差写进限制。
- 事件/日志不泄露 hidden 内容。

### 4.4 Step 账本

```json
{
  "candidate_id": "C-014",
  "parent": "C-013",
  "kind": "subexperiment|full_step|qualified_version",
  "artifact_hash": "sha256:...",
  "public_eval": {"metric": "...", "value": 0.82, "receipt": "RCPT-..."},
  "comparisons": [{"baseline": "...", "delta": 0.03, "ci": "..."}],
  "cost": {"tokens": 102400, "cny": 6.8, "minutes": 42},
  "negative_results": ["..."],
  "decision": "keep|rollback|reject",
  "reason": "..."
}
```

- 子实验 vs 完整 step 必须分开；不能把一次 prompt 改动算成“多轮进化”。
- 拒绝也写账；负结果保留。
- 最终准入看 hidden eval + 人工签，不看面板曲线。

---

## 5. 前端代码架构：不要把业务规则写进 React

### 5.1 结构

```text
web/src/
├── app/            # shell, router, providers, error boundary
├── features/
│  ├── runs/        # 运行台、SSE、focus
│  ├── evidence/    # claim/EA/span/债务 inspector
│  ├── manuscript/  # 句/槽/图/diff
│  ├── changes/     # ChangeSet/Impact/Disposition
│  ├── closure/     # Q1/G5/审批/导出
│  ├── skills/      # manifest/安装/租约/撤销
│  └── audit/
├── components/     # Badge/Table/Graph/Code/Diff 等
├── lib/
│  ├── api/         # generated client + error mapping
│  ├── events/      # SSE manager、reconnect、event reducer
│  └── query/       # query keys/cache policies
└── styles/         # tokens + layout
```

### 5.2 规则

- 服务端状态用 TanStack Query；UI 状态用 Zustand；**不复制后端 workflow 状态机**。
- SSE 只更新事件缓存与失效标记；页面重新查询快照。
- 所有 API 类型来自 `packages/contracts`；不在前端手写 DTO。
- 业务不变量不在 React 里“再实现一遍”；前端只展示后端拒绝/门禁。
- 每个 feature 有自己的测试；共享组件有 Storybook 或可视化快照。
- 不做“全局大 store”；不做“一个页面文件 2000 行”；不做 iframe 产品架构。
- 真实/SIM/设计态 badge 由数据字段驱动，不由页面写死。

---

## 6. 测试与质量门禁：让架构可执行

### 6.1 分层测试

| 层 | 工具 | 测什么 |
| --- | --- | --- |
| Domain unit | Pytest | 不变量、状态转换、哈希/版本 |
| Application | Pytest + fakes at ports | 用例/事务/事件/失败路由 |
| Adapter contract | Pytest | DeepSeek/Postgres/Docker/OpenAlex 接口契约 |
| Integration | Testcontainers | Postgres/Redis/对象存储/MinIO |
| API contract | Schemathesis/OpenAPI | 请求/响应/错误/幂等 |
| E2E | Playwright | 接入→运行→审批→导出→变更→撤销 |
| Architecture | import-linter | 依赖方向/模块边界/禁止跨表 |
| Safety | Pytest | 绕过 claim/export/lease 必须失败 |

### 6.2 CI 顺序

```text
ruff + mypy + eslint + tsc
→ domain/unit
→ architecture
→ adapter contract
→ API contract
→ Playwright smoke
→ docker compose build & smoke
```

- 架构测试失败 = 阻断合并；不靠 code review 记忆。
- 关键路径（claim/closure/lease）要求分支覆盖与变异测试（可选）；不要用总覆盖率当质量证明。
- 任何 schema 变更必须版本化 + 生成前端类型 + 迁移脚本。

---

## 7. 扩展性评估：把“好架构”变成论文证据

### 7.1 研究问题

> 端口/技能运行时是否能让新能力以有界变更接入，同时保持四条硬不变量和导出硬门不被绕过？

### 7.2 扩展任务（案例系列）

| 任务 | 预期改动 | 验证 |
| --- | --- | --- |
| A. 新增 Crossref 检索源 | 新 `RetrieverPort` adapter + config + tests | Evidence/Closure 无改动；Q0 通过 |
| B. 新增本地 vLLM provider | 新 `ModelPort` adapter + profile | 模型审计；fallback；无 domain 改动 |
| C. 新增“图表一致性审计” Skill | skill 包 + manifest + tests + registry | dry-run→pilot→active→revoke；依赖闭包 |
| D. 新增中文核刊体裁模板 | config + Q1/G5 rules + golden | 不影响其他体裁 |
| E. 新增 Figure 类型 | schema + builder + audit | export manifest 兼容；旧版本可重建 |

### 7.3 指标

| 指标 | 说明 |
| --- | --- |
| 变更面 | files/modules/LOC；是否触碰 Evidence/Closure 核心 |
| 架构违规 | import-linter 违规数（目标 0） |
| 不变量回归 | 四条硬不变量测试通过率（目标 100%） |
| 扩展时间 | 从任务开始到 pilot 通过的小时数 |
| 测试完整性 | 新路径的契约/E2E 覆盖 |
| 开发者理解成本 | 2–3 名同学按文档完成扩展的时间/错误（可选小样本） |
| 回归 | 原有 golden cases 全过 |

> 这是**系统/工程贡献的评估**，不是科学效果评估；它回答“架构是否真的降低了扩展风险”，不回答“论文质量是否更高”。后者要靠证据闭合实验。

### 7.4 失败/绕过测试（必须有）

- Skill 尝试直接创建 claim → 拒绝；
- Manuscript 尝试直接导出 → 拒绝；
- 运行中修改模板版本 → 新 revision/拒绝；
- 撤销技能后继续调用 → `LEASE_REVOKED`；
- 手填数字无 EA → G5 阻断；
- Agent token 调人工审批 → 403；
- 隐藏测试内容出现在前端/SSE → 测试失败。

这些 negative tests 是论文里很有说服力的“架构有效性”证据。

---

## 8. 论文怎么放：创新点分层与表述

### 8.1 贡献分层

| 层级 | 贡献 | 证据 |
| --- | --- | --- |
| 主贡献（研究） | RWMT/证据闭合：claim–EA–run–slot–closure 的对象模型与维护机制 | 真实纵切 + 结构/语义/维护评估 |
| 支撑贡献（系统） | 可插拔证据运行时：端口/Skill 运行时隔离易变实现，四条硬不变量由架构强制 | 架构测试 + 扩展任务 + 绕过测试 |
| 扩展贡献（待验证） | 租约门控的过程/技能自进化：固定实例、隐藏评测、step 账本 | E7/E8；未跑前只写设计 |
| 治理贡献 | 人签/导出硬门与 AI 使用审计 | 审批/导出失败路径 + 人评 |

### 8.2 论文中的“创新点”可以这样写

1. **提出并实现一种面向证据闭合的科研 Agent 运行时**：把 claim/EA/closure 的所有权固化为领域不变量，导出只经 Closure，数字必须回溯到 run/EA。
2. **设计可插拔的扩展架构**：以 7 个核心端口隔离模型、检索、解析、判定、写作、沙箱、导出与 Skill 运行时；新增 provider/Skill 不修改证据核心，架构测试保证依赖方向。
3. **把自进化放进可复算的运行底座**：固定实例、统一预算、公开/隐藏评测分离、租约控制器与 step 账本；候选不能自动 active，撤销沿依赖闭包传播。
4. **以人签和硬门约束责任边界**：机器起草，人在 G0/G2/G3/G4/G5 做科学判断与最终签署；审计可追溯。

**注意**：第 2 条是“系统/工程贡献”，不要单独说“本文创新性地使用了六边形架构”。它的创新性在于**与证据闭合不变量结合，并被扩展性/绕过测试验证**；离开这个语境就只是普通工程实践。

### 8.3 建议的章节结构

```text
第 3 章 需求与总体设计
  3.x 证据闭合运行时；模块边界；端口；部署

第 4 章 关键机制
  4.x claim/EA/closure 不变量
  4.x 端口与 Skill 运行时
  4.x run harness / lease / hidden eval

第 5 章 实现
  5.x 技术栈；API/SSE；前端；数据/审计

第 6 章 评估
  6.x 证据闭合/维护实验（主）
  6.x 架构一致性与扩展任务（支撑）
  6.x 绕过测试/失效场景
  6.x 限制与效度威胁

第 7 章 结论
```

### 8.4 不能写的句子

- “本文首次提出可插拔科研 Agent 架构”（没有充分检索，且不是首个）。
- “微服务架构提升了科研质量”（没有因果证据）。
- “代码分层清晰，因此系统更可靠”（需要测试/故障数据）。
- “架构支持任意 Skill，因此可以自动进化”（自动下载/执行有安全边界）。
- “用了 DeepSeek，所以效果最好”（模型不是效果保证）。

### 8.5 可以写的句子

- “本文将 claim/EA/closure 的所有权固化为模块不变量，并用架构测试与绕过测试验证其不可绕过性。”
- “在 5 个扩展任务中，新增检索源/模型/Skill/体裁/图类型均不需要修改 Evidence/Closure 核心，四条硬不变量测试保持通过。”
- “与单体原型相比，扩展变更面从 X 个模块降至 Y 个 adapter/skill 包（若完成对照）。”
- “该架构是主贡献的使能条件：它让证据闭合与维护在工程上可执行、可审计、可扩展。”

---

## 9. 迁移策略：不要重构 demo，另建产品

1. **冻结 demo**：`demo/`、`site/` 保持现状；只作为设计规格和展示；不再加业务功能。
2. **抽取资产**：design tokens、组件结构、fixture 数据、事件/契约条内容；不复制 480KB 单文件逻辑。
3. **新建应用**：`apps/web` + `apps/api` + `apps/worker`；从第一行就按模块/端口建。
4. **先纵切**：接入→claim/EA→run→closure→人签→导出；只实现需要的模块；其他模块保持空接口。
5. **再加扩展**：新 provider/Skill/体裁按固定落点接入；每加一个，跑架构/不变量/golden 测试。
6. **最后做 UI 丰富度**：不要把 demo 的每个视觉细节都搬过来；先保证证据工作台可用。

---

## 10. 反屎山清单（Code Review 必看）

- [ ] domain 是否 import 了 FastAPI/SQLAlchemy/OpenAI/Docker？
- [ ] route 是否直接写 SQL/调 LLM/算业务？
- [ ] 是否跨模块直接读对方表？
- [ ] 是否新增了 `utils.py` 大杂烩/循环依赖？
- [ ] 是否绕过了 `Evidence.create_claim`/`Closure.export`？
- [ ] 是否在 React 里复制了 workflow 状态机/业务不变量？
- [ ] 是否手写 DTO 而不是生成契约？
- [ ] 是否把 API key/CoT/hidden test 写进前端/SSE/日志？
- [ ] 是否新增了未测试的 Skill 自动执行路径？
- [ ] 是否把一次 prompt 改动算成“自进化”？
- [ ] 是否为了抽象而抽象（无第二个实现的 port/策略）？
- [ ] 是否更新了架构测试/ADR/迁移脚本？

---

## 11. 风险与取舍

| 风险 | 表现 | 缓解 |
| --- | --- | --- |
| 过度设计 | 每个类都接口化；开发变慢 | 只保留 7 个核心端口；无第二实现不抽象 |
| 微服务化过早 | 部署/调试成本爆炸 | 模块化单体 + 1 worker；按证据再拆 |
| 事件泛滥 | 事件版本失控、调试困难 | 只发领域事件；schema 版本；outbox；测试 |
| 前端复制业务 | 规则两套、难维护 | 前端只渲染后端状态；契约生成 |
| 架构测试形同虚设 | 违规靠 review 记忆 | import-linter + CI 阻断 |
| 扩展性评估造假 | 只加简单 adapter | 选择真实扩展任务；记录变更面/时间/回归 |
| 论文过度宣称 | “首个/先进架构” | 用“本文实现/在本文范围内”；给出证据 |

---

## 12. 与现有文档的关系

| 文档 | 关系 |
| --- | --- |
| [17](17-基于Skill契约的上层微服务架构.md) | 服务/模块/插件边界、端口、硬不变量；本文把它落成代码布局与测试门禁 |
| [19](19-RSI出题规范对照-自进化运行纪律反思.md) | 固定实例/租约控制器/hidden eval/step 账本；本文落成 worker/run harness |
| [20](20-开源科研Agent框架调研-浙大SciToolAgent与主流技术栈.md) | DeepScientist UI/daemon/skills、SciToolAgent 工具图谱/安全、AI Scientist v3 run 目录等工程参考 |
| [21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md) | 技术栈、API/SSE、DeepSeek、Skill 生命周期、论文产出与评测 |
| [23](23-开源自改进机制对照-从A-Evolve-RSI-Anything到我们的Lease-Gated-Runtime.md) | 自改进机制、固定实例、隐藏评测、step 账本与租约 |
| [13](13-创新点评审与主张收敛-需求对齐、开源对照与验证顺序.md) | 主/支撑/扩展/工程贡献分层；本文把“工程架构”收敛为系统贡献而不是主创新 |

---

## 13. 结论

**可以把这个设计写进毕业设计的创新点，但要写成“可验证的系统机制”，而不是“代码写得好”。**

最稳妥的表述是：

> 本文实现了一个面向证据闭合的科研 Agent 运行时。它用领域不变量保证 claim/EA/closure 的所有权，用端口与 Skill 运行时隔离易变实现，用 run harness/租约/隐藏评测约束自进化。该架构使新增模型、检索源、Skill 与体裁模板不需要修改证据核心，并通过架构一致性测试、扩展任务与绕过测试验证其可扩展性与不可绕过性。

这段话里，“架构”服务于“证据闭合/维护”的主贡献；工程贡献有测试和扩展任务支撑；不宣称“首个”“最好”“自动进化”。这比单独说“我用了微服务/分层架构”更像一篇毕业设计，也更经得起答辩追问。

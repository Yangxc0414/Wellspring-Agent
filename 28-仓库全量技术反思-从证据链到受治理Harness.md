---
title: 仓库全量技术反思：从证据链到受治理 Harness
date: 2026-10-24
status: audit-note
scope: research_agent/ + site/ + modules/ + docs 00–27
evidence: tests, CLI runs, code reading, browser checks; no external benchmark
related: [21, 22, 23, 25, 26, 27]
---

# 仓库全量技术反思：从证据链到受治理 Harness

> 这份文档不是功能清单，而是一次“把系统拆开看”的审计：**哪些流程真的跑通、哪些只是结构、哪些主张现在不能写、下一步先修什么。**
> 与本轮百篇调研配套阅读：[`30-自进化与RSI百篇调研-机制证据与治理.md`](30-自进化与RSI百篇调研-机制证据与治理.md)。
> 外部效果数字均不是本仓库结果；本仓库的结果只到本地 fixture / CC-BY / ChemLab 协议验证。

---

## 0. 先给判断

### 0.1 系统现在是什么

一句话：

> **一个本地可运行的科研证据链原型 + 一个受治理的 harness 改进控制面；不是 autonomous RSI，也不是可投稿的自动科研系统。**

拆开说：

- **证据链**：S1 文献 → S2–S3 假设 → S4 设计 → S5 本地 run → S6 图 → S8–S12 论文契约/基金骨架；产物以 JSON 落盘，人工签 claim 后才允许进入结果槽；closure 做结构闭合，sign 生成本地 manifest。
- **控制面**：候选（skill/process/prompt/knowledge）→ dry-run → public/hidden/near-OOD/regression → 人签 lease → runtime 消费 → sealed confirmation → trace。默认 `pending_human`，没有 approve/claim/sign API。
- **前端**：四套。`research_agent/web/` 是模块工作台（静态任务快照），`site/` 是单屏产品壳/演示，`site/live/` 是真实 runtime 控制台，`site/models/` 是本地模型网关配置/探测页。
- **边界**：不训练权重、不联网（默认）、不自动写 claim、不自动导出、不做同行评审。

### 0.2 现在能跑通什么

本轮实际跑过（临时目录，不污染仓库）：

1. `pipeline run --run-dataset chemlab` → S1 fixture + S5 真实 ChemLab run + schematic figure + paper contract；
2. `run claim` → 人签 claim（scope 绑定 EA）；
3. `protocol freeze` → ProtocolCard（design/capsule 哈希）；
4. `bibliography verify` → DataCite 快照；
5. `pipeline run --run-dir --claim-file --protocol-file --bibliography-file` → 五个结果槽全部绑定；
6. `closure check` → 11/11 pass；`closure sign` → signature + export manifest（`submission=false`）。

这条链证明的是：**对象接线、哈希绑定、人工门与导出阻断是成立的**。它不证明：研究假设成立、结果可泛化、论文可投稿、系统会自进化。

### 0.3 现在不能宣称什么

- 不能宣称“已实现 RSI / self-improving / 越跑越强”；
- 不能宣称“hidden/near-OOD/regression 已证明泛化/抗遗忘”；
- 不能宣称“closure 11/11 = 同行评审通过 / 可投稿”；
- 不能宣称“ChemLab R² = 科研发现 / SOTA”；
- 不能宣称“LLM proposer 可靠”；
- 不能把 fixture 数字、静态快照、演示动画写成实验结果。

---

## 1. 程序到底怎么跑：对象、命令、门

### 1.1 一条纵切的真实调用链

```text
CLI: python -m research_agent pipeline run
  └─ cli.py:_cmd_pipeline_run
      └─ PipelineRunner.run (pipeline.py)
          ├─ LiteratureAgent.run        → QueryPlan / SourceHit / Span / CoverageReceipt / Gap
          ├─ IdeaAgent.run              → IdeaCard / IdeaShortlist（候选假设）
          ├─ ExperimentDesignAgent.run  → design draft（G2 前）
          ├─ RunAgent.execute           → RunCapsule / EvidenceArtifact（可选）
          ├─ FigureAgent.run            → scene / SVG / manifest（示意图）
          ├─ PaperAgent.run             → PaperContract + slots（结果槽 pending）
          └─ GrantAgent.run             → 基金骨架（可选）
      └─ write_pipeline_artifacts       → demo.json / figure.svg / paper.json / specs.json
```

**关键事实**：

- `PipelineRunner` 默认用 `FixtureRetriever + SimpleParser`；`--real-corpus` 才切到冻结 CC-BY 语料；`--use-lease` 才按 active S1 lease 切 retriever/budget。
- S5 只有在 `--run-dataset` 或 `--run-dir` 时才有 `modules.run`；否则 `stage_skip`，结果槽保持 pending。
- `paper.json` 不是论文正文，是**论文契约 + 槽位**；`PaperAgent` 明确不写结果数字、不生成 claim。
- `demo.json` 是合并视图，不是单一证据对象；它把不同臂（S1 fixture、S5 real run、S6 schematic、S8 slots）放在同一个文件里。**这正是前端必须显示“臂”的原因**。

### 1.2 人工门与闭合链

```text
run execute → run-capsule.json + ea.json + metrics.json
run claim   → claim.json（status=supported，必须 human_reason，scope 必须等于 EA scope）
protocol freeze → protocol-card.json（design/capsule 哈希 + limitation + human_reason）
bibliography verify → bibliography-card.json（DataCite snapshot + card_sha256）
pipeline run --run-dir --claim-file --protocol-file --bibliography-file
  → paper slots: method.protocol=bound_protocol, result.primary=bound_claim,
    result.figure=bound_figure, limitation=bound_scope, citation.related=bound_bibliography
closure check → closure-report.json（11 checks）
closure sign  → signature.json + export-manifest.json（submission=false）
```

**这道链的真正不变量**：

- 没有 EA 不能 claim；没有 claim 不能绑 `result.primary`；
- 没有 ProtocolCard 不能绑方法/限制；没有 DataCite 卡不能绑引用；
- 没有数据图 provenance 不能绑 `result.figure`；
- 槽位未 bound，closure 不能 ready；
- closure 未 ready，sign 拒绝导出。

**这道链没有证明的**：

- claim 的文字是否真的支持 statement（只检查 status/refs）；
- 人是谁（没有身份/密码学签名）；
- 结果是否可泛化（只有单 run/单数据集）；
- 论文是否可读/可投稿（只有 contract）。

### 1.3 RSI 控制面怎么跑

```text
rsi propose   → StepRecord(pending_human) + dry_run_ref
rsi evaluate  → public_eval / hidden_eval / near_ood_eval / regression_eval
rsi admit     → public+hidden passed + dry-run + human_reason + scope → Lease(active)
run execute --use-lease / pipeline --use-lease / --use-s5-lease
              → 解析 active lease，实际改 seeds / retriever+budget
rsi real-confirm / s5-confirm
              → sealed confirmation（used_for_admission=false）
rsi trace     → 校验 lease→capsule→confirmation 链接（只读，不改 ledger）
rsi status    → MetaTracker report（episodes/leases/confirmations/warnings/calibration）
```

**关键事实**：

- `rsi` 的 `lease` 是 JSON 账本，不是密码学令牌；`active` 只是状态字段。
- `run execute --use-lease` 只解析 `experiment.run.seeds`；`pipeline --use-lease` 只解析 `literature.retrieval.budget`。
- `process/prompt/knowledge` 候选可以进 ledger，但**没有运行时 loader 会加载它们**。这是“半 inert”的自进化链。
- `rsi trace` 对 S5 seed lease 会校验 seeds/dataset；对 S1 harness lease 只校验 capsule completed + 无 capability claim，**不校验 retriever/budget 是否真的被 pipeline 使用**。

### 1.4 Runtime 与前端

```text
FastAPI (127.0.0.1:8787)
  POST /api/runs           → JobManager.submit → PipelineRunner.run
  GET  /api/runs/{id}      → status/result summary
  GET  /api/runs/{id}/events/stream → SSE 增量事件
  GET  /api/runs/{id}/artifacts     → 只读产物列表/下载
  GET  /api/rsi/status|trace|ledgers → 只读审计
  （没有 approve/claim/sign 端点）
```

- `JobManager` 的 `result` summary 只包含模块 **status**，不包含模块对象；`site/live` 需要再取 `demo.json` 才能渲染臂级信息（本轮已在前端补这个 detail fetch）。
- 三套前端没有共享 view model：`research_agent/web/app.js`、`site/live/live.js`、`site/assets/app.js` 各自实现状态/格式化。**这是重复逻辑与不一致的根源**。

---

## 2. 已验证与未验证

### 2.1 已验证（本轮或近期）

| 项 | 证据 | 结论 |
|---|---|---|
| 单元/契约测试 | `python -m unittest discover -s tests -v` | **71 tests OK**（58 基线 + 10 模型网关/能力 + 2 runtime 模型端点 + 1 CLI 参数测试） |
| 模型网关 | `tests/test_models.py` 本地假 HTTP server | OpenAI `reasoning_effort`、Anthropic `thinking.budget_tokens`、密钥脱敏/不落盘、URL 策略、runtime binding 通过；未调用外部 API |
| fixture 纵切 | `pipeline run` | S1→S3→S4→S6→S8 可跑；S5 可选 |
| 真实文本 S1 | `pipeline run --real-corpus` | 4 篇 CC-BY 正文、2,287 spans；仍无 claims |
| S5 ChemLab | `pipeline run --run-dataset chemlab` | RunCapsule/EA/claim draft/result figure |
| 人签 claim | `run claim` | scope 必须匹配 EA（本轮修复） |
| ProtocolCard | `protocol freeze` | design/capsule 哈希 + limitation + human reason |
| DataCite 快照 | `bibliography verify` | 4 条元数据 + card hash |
| paper 槽位 | `pipeline --run-dir --claim-file --protocol-file --bibliography-file` | 5/5 bound |
| closure | `closure check` | 11/11 pass（临时 E2E） |
| sign | `closure sign` | signature + manifest，`submission=false` |
| runtime | FastAPI + SSE + artifacts | 本地 job 可执行；无 approve/claim/sign |
| 前端 | Playwright 1440/390 | 无 console error；无页面级横向溢出；臂/任务提示可见 |

### 2.2 未验证

| 项 | 缺口 | 影响 |
|---|---|---|
| 真 held-out | S5 的 hidden/near-OOD/regression 只是不同 `test_size`；ChemLab 共用同一 test CSV | 不能写泛化/抗遗忘 |
| sealed hidden | hidden 任务在 repo 可见；无 commitment/独立进程 | 自选/过拟合风险 |
| 多轮改进 | 只有 1 个 approved + 1 个 confirmation | 不能写“越跑越强” |
| no-op 对照 | 没有 | 无法区分改进与噪声 |
| 统计不确定性 | 没有 CI/anytime-valid gate | 单点差值不可靠 |
| peer-review benchmark | 未接 PaperBench/RE-Bench/MLGym 等 | 不能写科研能力 |
| skill runtime | 只有静态 manifest/文档 | 技能供应链风险未防 |
| memory 治理 | 没有 provenance/taint/撤销 | 记忆毒化风险 |
| ChangeSet/stale | 设计有，代码无 | RWMT 主线未落地 |
| 身份/签名 | 本地 JSON，不是密码学签名 | 不能写不可抵赖 |
| 成本账本 | 没有统一 token/GPU/人工成本 | 不能写“更高效” |
| 真实研究 | ChemLab/iris 是协议验证 | 不能写科学发现 |

---

## 3. 代码级审计：P0/P1/P2

> 这一节只列“会影响证据可信度/可复现性”的问题，不列风格问题。所有行号以当前工作区为准。

### P0-1 S5 的四个 split 不是真隔离

**位置**：`research_agent/s5_eval.py:13`（`TASKS`）、`:76`（`_evaluate`）、`:232-234`（hidden/near/regression）；`research_agent/modules/run.py:166`（ChemLab）。

**事实**：

- `TASKS` 的 public/hidden/near_ood/regression 只是 `test_size` 不同（0.2/0.3、0.25/0.35、0.15/0.4、0.1/0.45）。
- `_evaluate` 对每个 split 调 `RunAgent.execute`，数据集不变；ChemLab 的 `_execute_chemlab` 始终读同一组 `*_test_Morgan_fingerprints.csv`。
- iris/breast_cancer 的 `train_test_split` 用不同 `test_size`，test 集会有大量重叠；hidden 不等于 held-out。

**后果**：`hidden`/`near-OOD`/`regression` 的名字会误导读者；门禁实际上测的是“不同验证比例/不同训练子集”，不是分布外/旧任务遗忘。

**修法**：按文档/反应/任务做 disjoint split；每个 split 记录 n 与样本 hash；加测试证明交集为空。

### P0-2 hidden 任务没有 sealed

**位置**：`research_agent/rsi_fixtures/real_tasks.json`；`research_agent/rsi.py:626`（`trace_research`）。

**事实**：hidden 问题、gold texts、任务分布都在 repo 中；候选/agent 可读；没有运行前 commitment 或独立 evaluator 进程。

**后果**：与 [2607.24300](https://arxiv.org/abs/2607.24300) 的 verifier–deployment gap 同类；候选可以针对 hidden 过拟合。

**修法**：hidden 放独立目录/独立用户；运行前记录 Merkle/hash commitment；agent 只能拿到 accept/reject 与聚合指标；trace 校验 commitment。

### P0-3 只有一次完整循环

**位置**：`research_agent/web/data/rsi-chemlab-v2/ledger.json`（3 episodes，1 approved，1 confirmed）。

**事实**：没有两次完整 `propose→…→confirm` 重跑；没有 no-op composite；没有跨轮继承。

**后果**：无法区分“改进”与“一次采样波动”；与 [2610.27610](https://arxiv.org/abs/2610.27610) 的 22% 门槛相比证据不足。

**修法**：至少 2 次 full-loop rerun；第二次用未参与选择的任务；no-op 对照；报告差值+CI+成本。

### P0-4 candidate 只检查 target 子串，不检查 patch 语义

**位置**：`research_agent/rsi.py:30`（`IMMUTABLE_SURFACES`）、`:139-155`（`GovernancePolicy.check`）。

**事实**：

```python
target = candidate.target.lower()
for surface in IMMUTABLE_SURFACES:
    if surface in target:
        raise RSIPolicyError(...)
```

只检查 `target` 是否包含 `claim/evidence/gate/rubric/export/signature/authorship`；`patch` 是自由文本，完全不检查。

**后果**：一个 target 为 `process.foo` 的候选，可以在 patch/rationale 里写“把 gate 改成自动通过”或“claim 直接 supported”；治理只防君子不防小人。

**修法**：结构化 patch schema（字段/类型/范围）；对 patch 的写操作做语义校验；dry-run 在隔离环境执行；禁止任何 immutable surface 的写字段。

### P0-5 只有两个 target 被运行时消费

**位置**：`research_agent/real_eval.py:56`（只接受 `literature.retrieval.budget`）；`research_agent/s5_eval.py:42`（只接受 `experiment.run.seeds`）。

**事实**：`process/prompt/knowledge` 候选可以进 ledger、拿 lease，但没有 loader 会把它们加载到 pipeline/run。

**后果**：自进化链是“半 inert”；UI 上的 9 步 loop 对多数 kind 只是状态机，不是执行链。

**修法**：`HarnessVersion` registry + loader；lease 选择 version；trace 校验实际加载 version。

### P0-6 `trace_research` 只验证 seed budget

**位置**：`research_agent/rsi.py:667`。

**事实**：只有 target 为 `experiment.run.seeds` 时才校验 `seed_budget_applied`；S1 harness lease 没有“retriever/budget 实际应用”的检查。

**后果**：`rsi trace` 可能对一个“没有真正加载”的 S1 lease 返回 ok（只要 capsule completed + 无 capability claim）。

**修法**：trace 接收 pipeline `demo.json`/run config；校验 retriever kind、budget、prompt/process version 与 lease 一致。

### P0-7 `admit`/`_claimable` 不要求四 split 齐全

**位置**：`research_agent/rsi.py:364`（`admit`）、`:605`（`_claimable`）。

**事实**：`admit` 只强制 `public_eval` 与 `hidden_eval` 都 passed；near-OOD/regression 可选。`_claimable` 只要求“present evals 都 claim_eligible”，不要求四项都存在。

**后果**：`capability_claims` 可能在没有 cross-domain/regression 证据时出现；MetaTracker 只给 warning，不阻断。

**修法**：如果目标是 capability claim，四 split 全部存在且 passed；否则显式标记 `harness_only` 并禁止 capability claim。

### P0-8 closure 是结构检查，不是身份/签名验证

**位置**：`research_agent/closure.py:46`（claim_supported 只查 status）、`:98-102`（all_slots_bound 只查 pending）、`:125`（sign）。

**事实**：

- `claim_supported` 只看 `claim.status == "supported"`；
- `all_slots_bound` 只看没有 `pending_evidence`，不检查每个槽的**期望绑定类型**；
- `sign` 只要求 `human_reason` 非空，写本地 JSON；没有签名者身份、不能验证签名、没有吊销。

**后果**：手工编辑 JSON 可以把 `method.protocol` 改成 `bound_claim` 而 closure 仍 pass；不能写“不可抵赖”。

**修法**：逐槽期望状态；claim/EA/capsule 的 hash 链；签名者身份与时间戳；可选真实签名（Sigstore/GPG）；closure 重算所有 hash。

### P0-9 `paper.status` 永远 `needs_evidence`，pipeline 永远 `needs_human`

**位置**：`research_agent/modules/paper.py:107`（`status="needs_evidence"`）；`research_agent/pipeline.py:430`。

**事实**：即使五个槽全部 bound、closure ready，`paper.status` 仍是 `needs_evidence`；`pipeline` 的条件 `paper.status != "ready"` 永远为真，所以状态永远 `needs_human`。

**后果**：状态语义不准确；用户无法从 pipeline 状态判断“结构闭合已完成，只差签署”。

**修法**：增加 `paper.status = contract_bound`/`ready_for_closure`；pipeline 状态区分 `needs_evidence`/`needs_signature`/`closure_ready`/`exported`。

### P1-1 `StepLedger.record_actuals` 可变历史

**位置**：`research_agent/rsi.py:330` 附近（`record_actuals`）。

**事实**：`record_actuals` 直接覆盖 `record.actuals`，没有 append-only 事件；ledger 不是不可变的。

**后果**：预测/实际校准可以被重写；审计价值下降。

**修法**：`actuals` 记录为 append-only events，保留上一条与 hash；或写 separate audit log。

### P1-2 `CandidateArchive.select_parents` 对指标取算术平均

**位置**：`research_agent/rsi.py:777`。

**事实**：

```python
values = [float(v) for v in metrics.values()]
return sum(values) / len(values)
```

如果 hidden metrics 同时有 `mean_r2`、`min_r2`、`cost`、`failed_runs`，平均没有意义（单位不同、方向不同）；成本越低越好，质量越高越好。

**后果**：父代选择可能偏向“成本高但质量高”或“成本低但质量低”的混合，而不是 Pareto 前沿。

**修法**：显式 fitness 配置（quality/cost/coverage/regression）+ Pareto/lexicographic；不要把不同单位平均。

### P1-3 `Lease` scope 是自由字符串，没有绑定 harness version

**位置**：`research_agent/rsi.py:111-136`；`research_agent/real_eval.py:56`；`research_agent/s5_eval.py:42`。

**事实**：lease 只带 `scope` 字符串与 TTL；没有 `harness_version`、config hash、evaluator version。执行器按 target + patch 解析，不校验“这个 lease 对应的 harness 版本是否就是实际运行的版本”。

**后果**：scope 相同但 config 不同的两次运行可能被误认为同一 lease；撤销/复评的传播对象不明确。

**修法**：`Lease` 增加 `harness_id/version/config_sha256/evaluator_version`；执行器只加载精确版本；trace 校验。

### P1-4 静态快照没有 as-of 与来源链

**位置**：`research_agent/web/data/*.json`、`tasks.json`、`rsi.json`；`scripts/build-task-index.py`、`scripts/export-rsi-view.py`。

**事实**：`tasks.json` 记录 `created_at`，但页面没有统一显示“数据截至何时”；`rsi.json` 有 source，但 KPI 没有 as-of；`site/live` 的 ledger 列表也没有时间。

**后果**：读者无法判断数字是何时、哪次 run、哪个臂。

**修法**：统一 `data_as_of`、`run_id`、`scope`、`source_file`；页面顶部/每个卡片显示；过期数据降级。

### P1-5 runtime summary 丢失模块详情

**位置**：`research_agent/runtime/jobs.py:241`。

**事实**：`job.result.modules` 只保留每个模块的 `status`，不保留 `literature.coverage`、`run.capsule`、`paper.slots`。前端必须再取 `demo.json`。

**后果**：API 消费方容易把 status 当完整结果；live 首屏只能显示粗略事实。

**修法**：summary 增加 `arms`/`run`/`claim` 摘要，或明确 `detail_url`；文档写清 summary 是 projection。

### P1-6 三套前端重复实现状态/格式化

**位置**：`research_agent/web/app.js`、`site/live/live.js`、`site/assets/app.js`。

**事实**：`MIXED ARMS`、`claim`、`scope`、`metric` 格式化逻辑各写一份；本轮只同步了前两套。

**后果**：同一数据在不同页面显示不同；修一个漏一个。

**修法**：抽 `shared/view-model.js`（纯函数：`evidenceArms`、`claimStatus`、`formatMetric`、`scopeMatch`），三套前端共用；或由 runtime 返回 view model。

### P2-1 模块接口仍是具体类，不是统一端口

**位置**：`research_agent/pipeline.py:141` 起；`research_agent/ports.py` 只有 Retriever/Parser。

**事实**：`PipelineRunner` 直接实例化 `LiteratureAgent`、`IdeaAgent`、`ExperimentDesignAgent`、`RunAgent`、`FigureAgent`、`PaperAgent`、`GrantAgent`；只有 retriever/parser 是端口。

**后果**：替换模型/技能/模块需要改 pipeline；与设计文档的“七个端口/六边形”不一致。

**修法**：为 `JudgePort`/`WriterPort`/`ExporterPort`/`SkillRuntimePort` 做最小接口；先抽 `RunPort`/`PaperPort`，不要一次性重构。

### P2-2 文档与代码的计数/状态漂移

**事实**：README 仍以 27 份文档、9/10 模块的口径描述；`modules/*/SPEC.md` 多数 `status: draft`；`AGENTS.md` 的模块表与代码新增不完全同步；`18-`/`21-` 中的前端/架构描述早于当前代码。

**后果**：评审/新同学会拿旧口径理解系统；文档之间的“当前实现”互相矛盾。

**修法**：建一个 `STATUS.md`（单一当前状态矩阵：模块/版本/测试/已验证/未验证/入口）；README 只链接它；旧文档保留为历史设计，不再改“当前实现”。

### P2-3 测试覆盖“契约”多于“语义”

**事实**：测试对 schema/status/boundary 很强；对“证据是否真的支持 claim”“split 是否真的 disjoint”“UI 是否真的显示正确臂”缺少测试。

**修法**：加 property/golden tests：split 交集为空、claim scope 链、closure 槽位类型、前端 view-model 快照。

---

## 4. 架构反思：模块化单体是对的，但“证据运行时”还没成形

### 4.1 做对的地方

1. **SPEC 作为源**：每个模块有 `SPEC.md`，CLI 可读/最小更新/定点 patch；版本与 changelog 可追踪。
2. **artifact 中介**：模块只交换 JSON/dataclass，不共享聊天记录；适合审计。
3. **三权分离的雏形**：proposal（agent）≠ evaluation（fixture/real/s5）≠ admission（human）；runtime 只读 RSI。
4. **硬门**：没有 EA 不 claim，没有 claim 不绑结果槽，没有 closure 不导出；这些是真正的结构不变量。
5. **本地可复现**：数据/代码/环境哈希；不联网；测试覆盖边界。

### 4.2 没做对/没做完的地方

1. **“证据运行时”缺对象**：没有 `ChangeSet`、`StaleMark`、`ClosureTask`、`CostLedger`、`SignatureIdentity`；`closure` 是一次性检查，不是持续维护。
2. **“自进化”缺执行对象**：没有 `HarnessVersion`、`SkillArtifact`、`MemoryRecord` 的运行时；lease 只覆盖两个参数。
3. **“研究”缺问题对象**：`IdeaAgent` 只从 spans 生成候选，没有 novelty check、没有 falsification 执行、没有真实研究任务；`PaperAgent` 只产契约。
4. **“评审”缺独立对象**：没有 Judge/Reviewer 的独立上下文与校准；`closure` 不是评审。
5. **“身份”缺**：所有签名都是本地 JSON + 人写理由；没有 signer identity、权限、审计日志。
6. **“成本”缺**：没有 token/GPU/人工成本账本；`cost` 只是检索条数/seed 数，不能支撑“更高效”。

### 4.3 建议的边界重画

不要把“阶段”当服务边界，也不要把“Agent”当服务边界。按**证据对象**拆：

```text
Source/Span ──> ClaimProposal ──> EvidenceArtifact ──> BoundClaim ──> ClosureReport ──> ExportManifest
      │                │                  │                  │
      └─ Coverage ─────┘                  └─ RunCapsule ─────┘
```

- `Source/Span`：S1；
- `ClaimProposal`：S2–S3/S9；
- `EvidenceArtifact`：S5；
- `BoundClaim`：S9/S13；
- `ClosureReport`：S13–S16；
- `ExportManifest`：S16；
- 横切：`StepLedger`/`Lease`/`Audit`/`Cost`。

这与 `17-` 的 bounded context 方向一致，但**毕设阶段不需要十个容器**；一个模块化单体 + 三个 deployable（web-bff/core/worker）足够。不要为了“微服务”拆服务。

---

## 5. 前端反思：三套界面，三种真相

### 5.1 三套界面的定位

| 界面 | 数据源 | 用途 | 风险 |
|---|---|---|---|
| `research_agent/web/` | 静态 `data/tasks/*/demo.json` + `rsi.json` | 模块工作台/答辩演示 | 快照过期；跨任务/跨臂混读 |
| `site/` | 静态 `site/data/*` + iframe demo | 公开产品壳/导师演示 | 演示数字易被当结果；文档副本未渲染 |
| `site/live/` | 本地 FastAPI + SSE | 真实运行控制台 | 本地 HTTP/CORS；summary 信息不足 |
| `site/models/` | 本地 FastAPI `/api/models*` | 模型网关配置/探测 | 密钥只在 runtime 内存或 env；Probe 会产生 API 费用 |

### 5.2 本轮已做的细粒度修正

**工作台（`research_agent/web/`）**

- 新增 `EVIDENCE ARMS` 卡：S1 / S5 / S8 三臂分别显示模式、数值、claim 状态；`MIXED ARMS` 红标；明确“不要把两臂读成一个结果”。
- 顶部状态 badge 从单一 `FIXTURE` 改为 `MIXED ARMS`（当 S1 fixture + S5 real 同时存在）；tooltip 说明不可合并。
- 自进化面板新增 `LEDGER / SCOPE / THIS TASK / MATCH` 上下文条；跨任务台账用红色 banner 明确“不是本任务证据”。
- `claim_eligible` 不再硬编码 false；按 evidence 的 `claim_eligible` + `simulation` 计算。
- `capability_claims` 不再硬编码 0；按 report 实际数量显示，并给 red/green 语义。
- lease 状态按 TTL 计算 effective status（active/expired），不直接信 JSON 的 `status`。
- S5 卡的 `CLAIM` 状态按 `claim_draft`/`paper.claims` 实际值显示；`STATUS` 按 completed 给 ok/bad。
- 论文卡的 `CLAIMS` 数量按 `paper.claims` 实际值显示。
- 移动端 390px：臂卡单列；无页面级横向溢出；console 无错误。

**Live（`site/live/`）**

- `RESULT` 从 5 个事实扩展到 8 个：`S1 ARM`、`S5 ARM`、`CLAIM`、`MODE`（MIXED ARMS）。
- `MIXED ARMS` 红色 note：S1 hit/span 与 S5 指标来自不同臂；EA 只覆盖本地协议 run。
- S5 指标格式化为 3 位小数，避免 `0.16473279439342386` 撑破网格。
- 运行完成后自动取 `demo.json` 补全臂级信息（summary 只有 status，不够）。
- 移动端 390px：无横向溢出；无 console error。

### 5.3 还需要改的 UX

1. **统一 as-of**：每个卡片显示 `data_as_of` / `run_id` / `scope`；顶部显示“数据截至”。
2. **状态语义**：区分 `needs_evidence` / `needs_signature` / `closure_ready` / `exported`；不要让 `needs_human` 包打天下。
3. **“为什么 blocked”下钻**：gate/closure 失败时，点开显示具体缺哪个槽、哪个 hash、哪条 warning；不要只给一个红点。
4. **证据链可视化**：claim → EA → capsule → figure → closure 的可点击链路；当前是分散在多个 tab。
5. **表格可读性**：Live result grid 8 项在窄屏会拥挤；建议 2 列/折叠。
6. **错误态/空态**：runtime 离线、CORS、无 ledger、无 artifacts 的错误提示已经不错；再加“一键复制启动命令”。
7. **可访问性**：颜色不是唯一语义（红/绿同时配文字/图标）；`prefers-reduced-motion` 已有，但演示动画仍多；键盘 focus 顺序需审查。
8. **去重复逻辑**：三套前端共享 view model；否则下次修一个漏两个。
9. **不要假精确**：`0.144 R2` 这种三位小数在 n=3 时没有统计意义；建议显示 `0.14` + `n=3` + “协议验证”。
10. **演示模式与真实模式分离**：`site/` 的 SIM 动画不能与 `site/live/` 的真实结果混在同一视觉语言里；用不同的 badge/底色。

### 5.4 前端改动验证记录

- 1440×900：工作台总览/自进化、Live 运行完成；无 console error；无页面级横向溢出。
- 390×844：工作台臂卡单列、Live 表单/结果可读；无页面级横向溢出。
- 真实浏览器操作：连接 runtime → 提交 ChemLab run → 等 SSE 完成 → 查看 artifacts/preview；通过。
- 未做：Safari/Firefox、屏幕阅读器、200% zoom、慢网/断网恢复。

---

## 6. 研究/产品叙事：把“自进化”放回正确的位置

### 6.1 三条主张，不要混

| 主张 | 现在能不能写 | 应该怎么写 |
|---|---|---|
| 证据运营/RWMT | 可以写“原型/设计/样例验证” | 变更→影响闭包→重跑/重写/复核→重新闭合→签署；不要写“已证明” |
| 受治理 harness 改进 | 可以写“控制面 + 本地证据链 + 负结果” | 候选→dry-run→public/hidden→人签 lease→consume→sealed；不要写“RSI” |
| 科研能力/自动发现 | 不能写 | 只有协议验证；接 PaperBench/RE-Bench 后再谈 |

### 6.2 最值得做的下一件事

不是再加一个模块，也不是再做一个动画，而是：

> **把 S5 的四个 split 做成真隔离，并跑两次完整循环 + no-op 对照。**

理由：

- 这是 [2610.27610](https://arxiv.org/abs/2610.27610) 直接指出的证据缺口；
- 这是 [2606.28374](https://arxiv.org/abs/2606.28374) 的 held-out selection 的最小实现；
- 这是 [2607.24300](https://arxiv.org/abs/2607.24300) 的 sealed audit 的最小实现；
- 做完之后，“控制面”才有资格谈“改进”，否则只是状态机。

### 6.3 论文/毕设的诚实贡献表述

建议把贡献收成三句话：

1. **问题**：科研 agent 的改进缺少“可审计的准入 + 可复现的证据链”，现有工作多在单 benchmark 上报告增益。
2. **方法**：一个受治理的 harness 改进控制面（候选/dry-run/public-hidden/lease/revoke/trace），以及一条 RunCapsule→EA→人签 Claim→paper slot→closure 的证据链。
3. **验证**：本地真实数据（ChemLab/CC-BY）上的协议验证与负结果；明确不外推为科研能力或通用 RSI。

不要写“首个/唯一/空白”；用“交集/一体化/仍较少见”。不要写“已证明/SOTA”；用“设计/原型/样例验证”。

---

## 7. 路线图：P0/P1/P2 与验收

### P0（1–2 周，先补证据）

| 任务 | 交付 | 验收 |
|---|---|---|
| 真 held-out split | `s5_eval` 四 split 使用不同数据/任务；`real_eval` 文档级 split | 测试证明 split 交集为空；报告 n |
| sealed evaluator | hidden 独立目录/进程 + commitment | agent 环境不可读 hidden；trace 校验 commitment |
| 两次完整循环 | 2 个 full-loop episode + no-op 对照 | ledger 有 ≥2 个 approved/confirm；报告差值+CI+成本 |
| structured patch | `Candidate.patch_schema` + 语义校验 | 改 gate 的 patch 被拒；测试锁定 |
| closure 槽位类型 | 逐槽 expected status + hash 链 | 错槽 JSON fail |
| pipeline 状态 | `needs_evidence/needs_signature/closure_ready/exported` | 全槽 bound 后不再显示 needs_evidence |
| 前端 as-of/arm | 统一 view model + 时间/来源 | 三套前端一致 |

### P1（2–4 周，形成可复现实验）

- `HarnessVersion` registry + loader；lease 选择 version；trace 校验实际加载。
- Archive 选择改 Pareto + edit budget + critic/pruner。
- CostLedger（token/GPU/人工/检索）；报告“单位成本的质量变化”。
- ChangeSet/Stale 传播：claim→sentence→figure；重跑/重写/复核。
- Memory/skill provenance/taint/撤销；skill manifest 加 tests/permissions/signature。

### P2（4–8 周，外部效度）

- 接一个外部 benchmark（优先 PaperBench 或 RE-Bench；不要全接）。
- 多轮 AIDE² 式循环（至少 2 轮，不追求 8 天）。
- anytime-valid gate / drift 监控（SAHOO/SEA）。
- 6–8 篇 held-out 论文语料 + 文档级迁移。

---

## 8. 本轮实际改动清单

### 8.1 代码

- `research_agent/modules/run.py`
  - 新增 `_dataset_scope`：按 dataset_id 推导 EA scope（修复 breast_cancer 被写成 iris）。
  - `run claim` 强制 `claim.scope == EA.scope`；claim warning 改为实际 scope。
  - SPEC `modules/run/SPEC.md` v0.2.1，Contract 增加 scope 一致性。
- `research_agent/pipeline.py`
  - fixture 检索 + S5 local run 时，warning 改为“fixture retrieval; S5 local run is a separate evidence arm; no API/claims”，不再误写“no experiment”。
- `tests/test_run.py` / `tests/test_pipeline.py`
  - 新增 breast_cancer scope 测试、错 scope 拒绝测试、warning 不含 iris 断言；S5 pipeline 断言 warning 含 “separate evidence arm” 且不含 “no experiment”。

### 8.2 前端

- `research_agent/web/index.html`：新增 `#arm-ledger` 容器。
- `research_agent/web/app.js`：
  - `currentScope` / `evidenceArms` / `rsiScopeInfo` / `leaseStatus`；
  - `MIXED ARMS` badge；`EVIDENCE ARMS` 卡；RSI ledger/scope banner；
  - dynamic `claim_eligible` / `capability_claims` / claim status / paper claims / lease effective status。
- `research_agent/web/styles.css`：arm ledger / mixed badge / evo context 样式，移动端单列。
- `site/live/index.html`：`#arm-note`。
- `site/live/live.js`：8 项 result facts、MIXED ARMS note、metric 格式化、demo detail fetch。
- `site/live/live.css`：arm note 样式。

### 8.3 文档/调研

- `30-自进化与RSI百篇调研-机制证据与治理.md`：100 篇调研综合、16 篇深读、对照与路线。
- `28-仓库全量技术反思-从证据链到受治理Harness.md`：本文。
- `research/self-evolution-100/bibliography.json`：100 篇元数据 + 摘要哈希 + 读点。
- `research/self-evolution-100/catalog.md`：100 篇 Markdown 目录。

### 8.4 回归

```bash
python -m unittest discover -s tests -v
# 实测：Ran 71 tests in ~30s · OK
```

---

## 9. 不可宣称（再次强调）

- 不写“已实现 RSI / self-improving / 越跑越强”；
- 不写“能力提升 / 通用迁移 / SOTA”；
- 不写“hidden/near-OOD/regression 已证明泛化/抗遗忘”；
- 不写“closure 11/11 = 同行评审 / 可投稿”；
- 不写“ChemLab R² = 科研发现”；
- 不写“LLM proposer 可靠”；
- 不把 fixture/静态快照/演示动画写成实验结果；
- 不把外部论文的作者口径写成我们的结果。

> **本仓库当前最诚实的定位：受治理的科研证据链与 harness 改进控制面原型。**
> 下一个里程碑不是“更多模块”，而是“真 held-out + 两次完整循环 + sealed evaluator”。

*审计时间：2026-10-24。代码与数据以工作区为准；外部论文以 arXiv 元数据与摘要为准。*

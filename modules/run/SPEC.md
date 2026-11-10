---
id: run
name: S5 执行与证据
stage: S5
version: 0.7.0
status: draft
owner: research-agent
inputs:
  - RunRequest
  - Protocol
  - protocol_sha256
outputs:
  - RunCapsule
  - EvidenceArtifact
  - ClaimRecord
  - ProtocolBinding
tools:
  - run.execute
  - run.claim
  - experiment.approve
  - experiment.run
  - experiment.ingest
  - experiment.claim
gates:
  - G2
invariants:
  - 没有冻结 protocol 不执行（strict pipeline 强制；直接调用 RunAgent 时由调用方负责）
  - 不伪造指标；每次 run 固定 seed 并可复算
  - RunCapsule 与 EA 不可原地修改
  - 不自动创建 Claim；必须有人签理由
  - iris/breast_cancer/chemlab 仅用于协议验证，不是论文科学证据
  - 传入 protocol_sha256 时必须写入 RunCapsule，并与冻结协议 design_sha256 一致
  - ProtocolBinding 只能由 completed capsule + EA 生成，不能修改已冻结 ProtocolCard
  - 生成实验包只能在本地 CLI 经 approve + --allow-execute 后执行；MCP/HTTP 不执行训练
  - 执行前必须校验 approval/data/spec/code 哈希；环境只允许白名单变量，不自动安装依赖
  - execution receipt/experiment-evidence 不是 RunCapsule/EA/Claim；Claim 只能由 CLI 人签并绑定 evidence hash
---

# S5 执行与证据

## Purpose

在本地用固定协议、固定 seeds 执行一个可复算的基线实验，产出不可变的 `RunCapsule` 与 `EvidenceArtifact`；只有在人工签署后才允许把 EA 绑定成 `ClaimRecord`。它验证“run → EA → claim”的证据闭包，不证明研究假设。

## Contract

- 输入：`RunRequest`（protocol_id、protocol_sha256、dataset、model、seeds、test_size、metric）；`protocol_sha256` 为 frozen ProtocolCard 的 design_sha256 时，RunCapsule 记录该哈希；
- 输出：`RunCapsule`（数据/代码哈希、环境、seeds、逐 seed 指标、均值/方差、artifact 路径）、`EvidenceArtifact`（metrics 文件的 sha256、run_id、source=run、immutable=true、scope 由 dataset/split 推导）、`ClaimRecord`；
- 支持 `iris` / `breast_cancer` 分类（logistic/accuracy）与 `chemlab` 反应转化回归（Ridge/R²+MAE，含 mean baseline 与 delta_r2）；chemlab 数据为 MIT 许可的本地冻结 fixture；
- `chemlab` 的 `test_size` 表示内部验证比例：每次 run 在 `(1-test_size)` 的随机训练子集上拟合，默认 0.3；不同 `test_size` 必须产生不同训练子集，禁止所有 split 复用同一子集；
- `split=demo|holdout` 仅用于 chemlab：`demo` 使用 418/22 原始划分，`holdout` 使用由训练池确定性派生的 376/42 划分；holdout 与 demo test 不重叠，只允许在租约后 confirmation 使用，禁止进入准入或候选选择；
- 失败：数据/模型不可用或指标缺失 → `status=failed`，不写指标为 0，不生成 EA；
- `run claim` 必须提供非空 `human_reason`，只能绑定已有 EA；claim 的 scope 必须与 EA 的 scope 完全一致，不能自动生成 Claim；
- `ClaimRecord` 可带 `ClaimAssertion[]`：每条包含 metric / comparator / value / tolerance / observed / status / condition；`run claim` 在写入前从 metrics artifact 重算数值，任一 assertion 失败即拒绝签署；无 assertion 的 legacy claim 保留但显式警告“未重算”；
- `run execute --use-lease` 必须解析 active S5 seed lease；无 lease/冲突时 fail closed，输出记录 `active_harness`；
- `run-contract-check` 必须从 capsule 的逐 seed 指标计算 paired baseline delta（`delta_<metric>` 或 `baseline_<metric>`）；有预注册 `min_delta` 时必须与其比较，未达标为 blocker；无 baseline 时标 `not_verifiable`，不得写成通过；
- 数据/代码哈希与 seeds 必须可由第三方复算；不得联网。


## Current Implementation

- `research_agent/experiment_runner.py`：生成实验包的 `approve → run → ingest → claim` 本地生命周期；run 使用子进程、timeout、环境 allowlist、stdout/stderr 和 artifact SHA；ingest 校验 execution/receipt/metrics/artifact 哈希并写 `experiment-evidence.json`；claim 必须 verified evidence + 人签理由，可带数值 assertion；MCP 不暴露执行/签核；

- `research_agent/modules/run.py`：`RunAgent.execute` / `RunAgent.claim` / `verify_claim_assertions`；claim 支持结构化数值断言并从 metrics 重算；
- 分类：本地 sklearn iris/breast_cancer + `StandardScaler + LogisticRegression`；
- 回归：`modules/run/fixtures/chemlab` 的 MIT 数据（B/C 512-bit Morgan fingerprints → LCAP conversion），`Ridge(alpha=1.0)`，固定 test CSV、按 seed 与 `test_size` 变化训练子集，记录 R²/MAE；`holdout` 使用 42 条派生反应，NOTICE 记录派生规则与 SHA-256；
- 每个 seed 写一条 metric；EA 绑定 `metrics.json` 的 sha256；RunCapsule 记录 dataset_id/哈希；
- CLI：`python -m research_agent run execute` / `run claim`；`run claim --assertion "metric=accuracy,value=0.95,comparator=>=,tolerance=0.01"` 可重复传入结构化数值断言；`run execute --use-lease` 从 `s5_eval.resolve_s5_seed_policy` 读取 active seed lease，实际覆盖 seeds，并输出 `active_harness`；
- `research_agent/run_contract.py` 从 `capsule.metrics_by_seed` 计算 paired delta：优先 `delta_<metric>`，否则 `metric - baseline_<metric>`；预注册 `min_delta>0` 时未达标为 blocker；无 baseline 时 `min_delta=not_verifiable` 仅警告，不伪造通过；
- 三个数据集都是**协议验证数据**，不是本课题的科学发现或论文证据；
- strict pipeline 只在存在匹配当前 design_sha256 的 frozen ProtocolCard 时执行 S5，并在 run 完成后写 `protocol-binding.json`。


## Boundaries

- 生成实验包的显式本地执行已实现；自动启动/多配置探索仍未实现；MCP/HTTP 永远不执行训练；
- `experiment-evidence.json` 是本地证据回执，不是 EA；`experiment claim` 是 CLI 人签，不是 MCP 工具；
- `experiment closure/lineage` 是本地实验专用 profile，不复用 RunCapsule/EA closure；

- 通用实验执行/自动启动/探索尚未实现；S4 codegen 只生成项目内实验包，S5 仍只执行内置 iris/breast_cancer/ChemLab 协议验证；
- 生成包的本地执行必须由用户在批准环境显式启动；agent/MCP 不执行训练，也不把本地 receipt 当 RunCapsule/EA/Claim；

- 不执行用户任意代码，不联网，不访问密钥；
- 不创建 Verdict/Closure/Export；不做同行评审；
- 不把 iris 结果写成论文结果或 SOTA；
- Claim 仅覆盖 demo scope，且必须人工签署；没有 EA 不能 claim。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `research_agent/modules/run.py` 与 `tests/test_run.py`；
4. 跑 `python -m unittest discover -s tests -v`。

## Changelog

- 2026-10-30 · v0.7.0 · status=draft · 0.7.0（2026-10-30）：把闭环最后一公里从"人凭空写断言"变成"人确认一个可审计的提议"。实测严格模式跑到 G5 时，run/claim-draft.json 只给出 statement（"mean accuracy is 0.956 over seeds [17,18,19]"）与证据引用，assertions 为空——人签之前必须自己编 metric/comparator/value/tolerance，没有任何依据可抄。现在 draft 增加 assertion_proposal：取每种子指标的最差值作为下限（无需任何分布假设），附 basis(mean/min/max/seeds)、可复制的 assertion_argument（实测 metric=accuracy,value=0.9111,comparator=>=,tolerance=0.0）与边界声明"提议是给人的草稿，不是 claim，不可签核"。metric 从 capsule.metric_name 取（chemlab 取 delta_r2），没有逐种子值时返回 status=unavailable 而不是猜一个数。人仍要自己敲最终 --assertion，所以没有任何东西被自动变成可签署内容。tests.test_pipeline 22 项 OK（新增 AssertionProposalTest 两项：最差种子成下限且边界声明存在、无值时报 unavailable 不猜）。契约变化：claim 草稿新增一个只读字段。
- 2026-10-28 · v0.6.2 · status=draft · run-contract 的 min_delta 不再恒为未评估：从 paired seed metrics 计算 `delta_<metric>`/`baseline_<metric>`；预注册阈值未达标为 blocker；无 baseline 标 `not_verifiable` 警告；不改变 EA/claim/人工门。
- 2026-10-27 · v0.6.1 · status=draft · 补充本地实验 closure/lineage profile 边界：独立于 EA/RunCapsule，不替代同行评审；证据与签名仍可哈希复验。
- 2026-10-27 · v0.6.0 · status=draft · 新增生成实验包的本地生命周期：approve→run（显式 --allow-execute、环境 allowlist、timeout、stdout/stderr、artifact SHA）→ingest（哈希校验、experiment-evidence）→claim（CLI 人签、assertion）；MCP/HTTP 不执行训练；自动探索仍 roadmap。
- 2026-10-27 · v0.5.0 · status=draft · 明确边界：S4 只生成实验代码包；通用实验执行/自动启动/探索仍是 roadmap；S5 继续只跑内置协议；本地 receipt 不是 EA/Claim。
- 2026-10-26 · v0.4.1 · status=pilot · 新增 run-contract/check：绑定 protocol/dataset/seeds/metric 与 artifact allowlist，核验 capsule/EA/evidence hash 与必需产物；min_delta 因缺 baseline 明确标为未评估，不伪造通过。
- 2026-10-25 · v0.4.0 · status=draft · RunRequest 支持传入 frozen ProtocolCard 的 protocol_sha256；RunCapsule 记录该哈希；pipeline strict 模式在无匹配冻结协议时拒绝执行 S5。
- 2026-10-25 · v0.3.0 · status=draft · 契约升级：ClaimRecord 支持结构化数值 assertion（metric/comparator/value/tolerance/observed/status）；run claim 在签署前从 metrics 重算，失败直接拒绝；closure 支持重算 claim assertion。
- 2026-10-24 · v0.2.2 · status=draft · 文档不变式同步：协议验证边界覆盖 iris/breast_cancer/chemlab，不再只写 iris
- 2026-10-24 · v0.2.1 · status=draft · 最小修复：EA scope 按 dataset_id 推导（breast_cancer 不再写成 iris）；run claim 强制 claim scope 与 EA scope 一致；claim warning 改为数据集/scope 实际值；新增 breast_cancer 与错 scope 拒绝测试
- 2026-10-24 · v0.2.0 · status=draft · 最小改进：RunRequest 增加 split=demo|holdout；ChemLab 增加 42 条由训练池确定性派生的 held-out 反应集（与 22 测试集不重叠），仅用于租约后 sealed confirmation；不进入准入选择
- 2026-10-24 · v0.1.5 · status=draft · 最小改进：ChemLab 使用 test_size 作为内部验证比例，Ridge 在 (1-test_size) 训练子集上拟合；修复 S5 各 split 复用同一 80% 子集导致门禁失效的问题
- 2026-10-24 · v0.1.4 · status=draft · 最小改进：ChemLab 增加 mean baseline（DummyRegressor），逐 seed 记录 baseline_r2/delta_r2；实测 Ridge R² 0.193 vs baseline −0.048，ΔR²≈0.242；仍是 baseline 协议验证
- 2026-10-24 · v0.1.3 · status=draft · 最小改进：增加 ChemLab 真实化学反应转化数据（MIT，418 train/22 test，Morgan 512-bit，Ridge/R²）；只做协议验证，不宣称新发现
- 2026-10-24 · v0.1.2 · status=draft · 最小改进：支持 breast_cancer 本地数据集；dataset_id/哈希随数据集变化；仍只做 iris/breast_cancer 协议验证，不联网
- 2026-10-24 · v0.1.1 · status=draft · 最小改进：CLI run execute --use-lease 解析 S5 seed lease；无 lease fail closed；输出记录 active_harness，不静默回退
- 2026-10-24 · v0.1.0 · 初始 S5 执行：本地 iris 协议验证、RunCapsule、EA、人签 Claim；不自动创建 Claim。

---
id: experiment
name: 实验设计
stage: S4
version: 0.9.0
status: pilot
owner: research-agent
inputs:
  - question
  - hypothesis
  - baseline
  - primary_metric
  - controls
  - seeds
  - budget
  - evidence
  - language
  - idea_id
outputs:
  - DesignCard
  - ProtocolDraft
  - PreRegistrationChecklist
  - ProtocolCard
  - ProtocolBinding
  - ExperimentPackage
  - ExperimentExecution
  - ExperimentEvidence
  - ExperimentClosure
  - ExperimentFigure
  - DataAudit
  - ExperimentSweepEvidence
  - SupportPanelCheck
tools:
  - design.validate
  - model.experiment_designer
  - experiment.codegen
  - experiment.approve
  - experiment.run
  - experiment.ingest
  - experiment.claim
  - experiment.closure
  - experiment.sign
  - experiment.lineage
  - experiment.figure
  - experiment.consistency-registry
  - experiment.sweep-approve
  - experiment.sweep-run
  - experiment.sweep-ingest
  - experiment.sweep-status
  - experiment.local-init
  - experiment.local-approve
  - experiment.local-run
  - experiment.local-ingest
gates:
  - G2
invariants:
  - 不执行 run
  - 不创建 Claim
  - 主指标与停止条件需人工冻结
  - 模型不得覆盖调用方已提供的字段
  - 模型补全任何字段后 status 必须保持 needs_human
  - 模型不得生成结果、指标数值、证据引用或 ProtocolCard
  - 预注册必须先冻结 design，再执行 run；不得要求 completed capsule 才能冻结
  - ProtocolCard 必须绑定当前 design_sha256；run 后再单独写 ProtocolBinding
  - experiment codegen 只生成项目内自包含实验包；不执行、不安装依赖、不联网、不创建 EA/Claim/gate
  - 生成包必须带 data/spec/code SHA-256 与 README 边界；target 不得出现在 features；执行必须由用户在本地显式完成
  - 执行前必须有 approve 记录与 `--allow-execute`；MCP/HTTP 不执行训练，不自动安装依赖
  - local-exec（类 Codex 本地命令）仅 CLI：local-init 登记 argv/env_prefix/cwd/expected_outputs/timeout；local-approve 人签并绑定 spec 哈希；local-run 需 approve+--allow-execute、不用 shell、spec 批准后变更即拒绝
  - local-exec 记录 command/env_prefix/git commit/platform/stdout/stderr/产物哈希；local-ingest 校验哈希产 local-evidence（claim_eligible=false），失败/超时/缺产物保留为 incomplete；MCP/HTTP 不暴露 local-run
  - ingest 必须校验 execution/receipt/metrics/artifact 哈希；evidence 不是 EA/Claim
  - claim 只能由 CLI 人签，绑定 evidence hash；MCP 不暴露签核
  - 结果图只能从 verified evidence 生成，schematic 必须为 false；manifest 必须绑定 spec/execution/evidence/claim 哈希，缺 matplotlib 时跳过而不是安装依赖
  - 实证稿有结果图时必须在正文引用图 1；图号无 manifest 对应则阻断；图表不得替代 claim 或 closure
  - sweep 生命周期：sweep-approve 人签 → sweep-run 显式 `--allow-execute` → sweep-ingest 校验哈希 → `verified_exploratory` evidence；它不是 EA/Claim，不能作为确认结果
  - 确认 run 可用 `--ridge-alpha` 绑定 sweep best_alpha；approve/run/ingest 必须一致，evidence 记录 alpha；确认结果仍需人签 claim
  - 若同一 run 存在 support-panel.json，local experiment closure 的 `support_panel.ready` 只允许 ready/not_applicable；needs_human/blocked/partial 或不可读均阻断
  - 传入手稿时 `support_panel.manuscript` 必须匹配 panel 的 draft_sha256，旧 panel 不能给新稿背书；panel 文件进入 artifact_refs 与 lineage
  - 无 span 级 evidence 时不调用模型 designer：待人工补全占位保持不变并记录 warning
---

# 实验设计子智能体（S4）

## Purpose

把假设收敛成一个可冻结的 pre-registration 草稿：问题、baseline、主指标、对照、seed、预算、停止条件。它不跑实验、不产生结果、不替代 G2。

## Contract

- 输入：question / hypothesis / baseline / primary_metric / controls / seeds / budget / evidence / language / idea_id；
- 输出：`DesignCard` + 预注册检查项；
- 缺少 hypothesis/baseline/metric/budget/control → `needs_human`；
- 完整 → `ready_for_g2`，仍必须人工签 G2；
- 设计必须记录 `idea_id`（来自 G1 选择）；没有 selected idea 时只能标记 provisional；
- 可选 `designer`：只补全缺失的 hypothesis/baseline/primary_metric/controls/budget；不得覆盖调用方已给字段，不得返回结果、指标数值、evidence_refs 或 stopping_rule；
- 只要有一个字段来自模型，status 必须保持 `needs_human`，直到人工确认；
- test 模式下无 designer、无 key、模型失败或输出非法时保留确定性占位并写 warning；production 模式下绑定缺失、调用失败或 JSON 不可解析直接抛 `ModelRequiredError`；
- 不执行 run，不产生 Claim，不自动 freeze。

## Current Implementation

- `research_agent/experiment_runner.py`：`experiment approve/run/ingest/claim` 本地生命周期；run 使用白名单环境、timeout、stdout/stderr；ingest 生成 `experiment-evidence.json`；claim 是 CLI 人签；
- `research_agent/local_exec.py`：类 Codex 的受治理本地命令实验（`experiment local-init/local-approve/local-run/local-ingest`）。local-init 登记人指定的 command（解析为 argv，不用 shell）+ env_prefix（conda/uv/docker 前缀）+ cwd + expected_outputs + timeout；local-approve 人签绑定 spec 哈希；local-run 需 approve+--allow-execute，记录 command/env_prefix/git commit/platform/stdout/stderr/产物哈希；local-ingest 校验哈希产 `local-evidence.json`（claim_eligible=false）。仅 CLI，MCP/HTTP 不暴露；不安装依赖；失败/超时/缺产物保留为 incomplete；
- 生成包执行记录写 `execution.json`，receipt/metrics/artifact 均可哈希复验；自动启动/探索仍未实现；
- `research_agent/experiment_figures.py`：verified evidence → matplotlib mean/std 结果图 + 证据绑定 manifest（`kind=data_result_plot`、`renderer=matplotlib`、`astradraw=false`、`schematic=false`）；AstraDraw 只用于方法/框架示意图，不用于结果图；
- `research_agent/experiment_closure.py`：本地实验 closure/lineage profile；校验 data/spec/code/approval/execution/metrics/evidence/claim 哈希与 assertion，输出 closure report；`experiment sign` 为 CLI 人签；不是 RunCapsule/EA closure；report/status 标 `closure_profile=local_experiment`；

- `research_agent/experiment_codegen.py`：从 run 的 `experiment.json` + 项目内 CSV 生成 `experiments/<EXP-ID>/`：`experiment-spec.json`、`run_experiment.py`、`requirements.txt`、`README.md`、`code-manifest.json`；支持 tabular regression/classification、dummy+Ridge/Logistic/RandomForest/GradientBoosting、固定 seeds/split、dry-run；只生成代码，不执行；
- CLI `experiment scaffold`；MCP `research_experiment_codegen`；生成包写 `metrics/predictions/run-receipt/artifact-manifest`，但 run-receipt 不是 RunCapsule/EA/Claim；

- `research_agent/design_audit.py`：S4 设计/统计清单（必需字段、seeds、controls、effect size/power/randomization/多重比较/CI/缺失数据/敏感性）；输出 `design-audit.json`，只作 G2 人工审阅清单，不改变 design.status 或自动冻结；
- `research_agent/modules/experiment.py`；
- 纯校验与草稿；默认不联网、不执行代码；
- 可选 `research_agent/adapters/research_models.py::gateway_experiment_designer`：按设置中的 `experiment` 模型绑定解析；test 模式无 key/绑定缺失时返回 `(None, note)`，保留确定性草稿；production 模式 strict 直接失败；
- 模型只补全缺失字段，字段长度/controls 数量受限；任何模型补全都记 warning 并强制 `needs_human`；
- 统一停止规则由确定性代码给出：主指标/样本量/停止条件冻结后不得事后修改；
- `freeze_design`：ready_for_g2 design + 非空 limitation/人签理由 → 先写 ProtocolCard（design_sha256，capsule_sha256 为空）；不要求 run 已完成；
- `freeze`（legacy）：仍保留“completed RunCapsule + 人签”路径，用于兼容旧流程；strict pipeline 不再使用它；
- run 完成后由 pipeline 写 `ProtocolBinding`（protocol_id / design_sha256 / capsule_sha256 / EA id / run_id），不修改已冻结 ProtocolCard；不自动创建 Claim。


## Boundaries

- 不提供“自动实验”能力；
- 不把缺失字段自动编造为默认值；
- 不修改 rubric、阈值、判据。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `ExperimentDesignAgent` 与测试；
4. 不碰 run/judge 模块。

## Changelog

- 2026-11-10 · v0.9.0 · status=pilot · 模块(3)实验执行从"仅生成包"升级为可执行用户指定本地命令（类 Codex）：新增 `research_agent/local_exec.py` 与 CLI `experiment local-init/local-approve/local-run/local-ingest`，落实 ARCHITECTURE §4 目标契约（command argv + env_prefix + cwd + expected_outputs + timeout）。治理不变：仅 CLI、需 approve+--allow-execute、不用 shell（argv 直跑，防注入）、env allowlist、不装依赖；approve 绑定 spec 哈希，批准后改 spec 即拒绝；记录 command/env_prefix/git commit/platform/stdout/stderr/产物哈希；local-ingest 校验哈希产 local-evidence（claim_eligible=false，需人签才成结果），失败/超时/缺产物保留 incomplete。MCP/HTTP 不暴露 local-run。新增 tests/test_local_exec.py。
- 2026-11-01 · v0.8.2 · status=pilot · empirical 预检不再只回一句按顺序解决：每条 blocker 生成确切 CLI（literature run 取 run-context 的 goal、synthesize、innovation review、scaffold、ingest、claim），输出新增 blocker_actions 与 ordering；实验包不存在时记为 blocker 而不是抛异常。新增 tests/test_empirical_commands.py 2 项。
- 2026-10-30 · v0.8.1 · status=pilot · 0.8.1（2026-10-30）：freeze_design/freeze 不再假设 seeds 是 int。pipeline 在部分路径把 seeds 写成实际种子列表，导致按文档命令 protocol freeze-design --design <run>/experiment.json 直接 TypeError 崩溃（严格模式的门后路径因此完全走不通）。改为统一调用 contracts.seed_count()：列表取长度、数字原样、字符串数字可接受、布尔与其它形状给出清晰错误。tests.test_pipeline 20 项 OK。
- 2026-10-29 · v0.8.0 · status=pilot · 0.8.0（2026-10-29）：S4 设计草案遵循 span-only——request.evidence 为空时跳过模型 designer 并写 warning，避免让模型在无证据情况下'补全'预注册字段；契约变化：新增该不变量与 needs_human 行为。
- 2026-10-28 · v0.7.15 · status=pilot · 新增 `experiment consistency-registry`：从 verified experiment-evidence 的 aggregate metrics 派生外部 `check_consistency.py` 所需的 schema-1.0 registry；record claim 状态与 spec/evidence/claim hash；sample_size 仅表示 dataset rows，不是 evaluation N；不创建/修改证据、claim、closure 或签名。

- 2026-10-28 · v0.7.14 · status=pilot · `experiment sign` 接受 `--manuscript` 并在重校验时使用同一手稿；修复带手稿 closure 无法签署的问题；offline 全链路测试覆盖 claim→manuscript→closure→signed→capsule S13 done。

- 2026-10-27 · v0.7.13 · status=pilot · local experiment closure 接入 support-panel：`support_panel.ready` 只允许 ready/not_applicable，手稿需匹配 panel draft_sha256；panel 进入 artifact_refs 与 lineage。与 canonical closure 使用同一治理语义，但不共享产物。
- 2026-10-27 · v0.7.12 · status=pilot · experiment status 增加 preflight 阶段（missing/passed/failed），批准前可检查 dry-run 是否通过。
- 2026-10-27 · v0.7.11 · status=pilot · 新增 `experiment preflight`：校验 data/spec/code hash 后运行 `run_experiment.py --dry-run`，只验证 schema/依赖，不训练、不写 execution/evidence、不需要 approve。
- 2026-10-27 · v0.7.10 · status=pilot · 数据审计增加 `target.copy`：任一特征与 target 完全一致即警告（分类/回归都检查），捕获直接标签泄漏。
- 2026-10-27 · v0.7.9 · status=pilot · paired comparison 增加 deterministic bootstrap 95% CI 与 exact sign-test p；状态摘要暴露这些字段，明确未做多重比较校正、仍属探索性统计。
- 2026-10-27 · v0.7.8 · status=pilot · 修正数据审计 ID-like 误报：连续数值特征高唯一率不再判 ID；保留列名匹配与低数值比例判据。新增真实乳腺癌子集的分类型 CV/RF/GB 回归测试。
- 2026-10-27 · v0.7.7 · status=pilot · sweep runner 遵循 `cv_folds`：分类 StratifiedKFold、回归 KFold，按 seed+fold 聚合；sweep evidence 记录 cv_folds，探索与确认实验使用同一 CV 设计。
- 2026-10-27 · v0.7.6 · status=pilot · lineage 增加 verified results table 节点，closure/lineage 现在覆盖 alpha/CV/结果表；新增 sweep→confirm→CV→图/表→写作→closure→lineage 集成测试。
- 2026-10-27 · v0.7.5 · status=pilot · claim 记录 ridge_alpha/cv_folds/results_table hash；closure 校验 alpha、CV、结果表存在与 hash，篡改结果表即 blocked。
- 2026-10-27 · v0.7.4 · status=pilot · 生成包 README 写入 Data audit 与 warnings；实验状态在 evidence 缺失时显示计划中的 cv_folds，便于 Qoder 在批准前检查设计。
- 2026-10-27 · v0.7.3 · status=pilot · codegen 增加表格数据审计：缺失、重复、常量列、ID-like 列、类别不平衡、近完美 feature-target 相关；写入 spec/data_audit 与 warnings，只警告不替代 G2/人工。
- 2026-10-27 · v0.7.2 · status=pilot · 实验包支持可选 k-fold CV（`cv_folds`，分类用 StratifiedKFold）；每 fold 作为 seed/fold 行，paired comparison 按 seed+fold 配对；receipt/evidence 记录 cv_folds。
- 2026-10-27 · v0.7.1 · status=pilot · 生成 runner 输出 `results-table.csv/.md`（按方法 mean/std/95% CI/n），纳入 artifact manifest；ingest evidence 记录表路径与 hash。
- 2026-10-27 · v0.7.0 · status=pilot · 生成 runner 增加 paired seed comparison：primary vs baseline 的 mean_diff、normal-approx 95% CI、wins；写入 metrics/receipt/evidence；明确不构成显著性声明。
- 2026-10-27 · v0.6.9 · status=pilot · 打通 sweep→确认实验：`experiment approve/run --ridge-alpha` 绑定 best_alpha，approve/run/ingest 哈希与值一致校验，evidence 记录 `ridge_alpha`；确认结果仍走单配置 run + 人签 claim。
- 2026-10-27 · v0.6.8 · status=pilot · 完成本地 sweep 生命周期：sweep-approve/sweep-run/sweep-ingest/sweep-status；ingest 校验 execution/receipt/artifact 哈希并写 `verified_exploratory` evidence；sweep 仍不是 EA/Claim，确认结果必须走单配置 run + 人签 claim。
- 2026-10-27 · v0.6.7 · status=pilot · 生成 runner 增加 random_forest 与 gradient_boosting（表格回归/分类），用于更强的本地实证基线；仍只生成、不执行、不创建 EA/Claim。
- 2026-10-27 · v0.6.6 · status=pilot · experiment closure 记录可选 AstraDraw 方法示意图 manifest/SVG（schematic 警告级校验）并纳入 artifact_refs；不把示意图当证据，缺失不阻断。
- 2026-10-27 · v0.6.5 · status=pilot · 结果图 manifest 增加 `kind=data_result_plot`/`renderer=matplotlib`/`astradraw=false`；明确 AstraDraw 只用于示意图，避免结果图被误认为 AstraDraw 产物。
- 2026-10-27 · v0.6.4 · status=pilot · HPO 最小切片：`experiment scaffold --alpha-grid` / MCP `alpha_grid` 生成 ridge alpha 固定网格计划与自包含 `run_sweep.py`；只规划与生成代码，执行未接入 approve/run/ingest，sweep 结果不能成为 evidence/claim。
- 2026-10-27 · v0.6.3 · status=pilot · 新增数据结果图 profile：`experiment figure` 从 verified evidence 生成 mean/std 柱状图与 manifest（绑定 spec/execution/evidence/claim 哈希，schematic=false）；closure 校验 figure.binding/not_schematic 并纳入 artifact_refs；status 增加 figure freshness；lineage 增加 figure 节点；缺 matplotlib 只跳过，不安装依赖。
- 2026-10-27 · v0.6.2 · status=pilot · 生成实验包把 design.idea_id 写入 experiment-spec；same-run empirical loop 校验 hypothesis/methods/metric/seeds，并在存在 innovation review 时校验 idea_id 属于候选方向；缺 idea_id 只警告，不伪造关联。
- 2026-10-27 · v0.6.1 · status=pilot · closure report、export manifest、signature 与 experiment status 统一标注 `closure_profile=local_experiment`；profile 词汇来自共享 `closure_profiles.py`，不把本地实验 profile 升格为 RunCapsule/EA closure。
- 2026-10-27 · v0.6.0 · status=pilot · 新增本地实验 closure/lineage profile：closure 校验哈希与 claim assertion，sign 为 CLI 人签，lineage 支持 fresh/stale；不复用 EA/RunCapsule，不替代同行评审。
- 2026-10-27 · v0.5.0 · status=pilot · 新增生成实验包的闭环后半段：CLI approve/run/ingest/claim；执行需显式 allow、环境 allowlist、timeout；ingest 校验哈希并生成 evidence；claim 人签并绑定 evidence；MCP 不执行训练；自动探索仍 roadmap。
- 2026-10-27 · v0.4.0 · status=pilot · 新增实验代码生成：S4 设计 + 项目内 CSV → 自包含实验包（spec/runner/requirements/README/manifest）；固定 seeds/split、dummy+Ridge/Logistic、dry-run；不执行、不装依赖、不创建 EA/Claim；自动启动/探索执行仍为 roadmap。
- 2026-10-26 · v0.3.1 · status=pilot · 新增 deterministic design audit：pipeline/task 写 `design-audit.json`，检查必需设计字段、seeds/controls 与统计计划关键词；只警告/阻断清单，不替代 G2。
- 2026-10-25 · v0.3.0 · status=pilot · 预注册顺序修正：新增 freeze_design（不要求 RunCapsule，先冻结 design）；ExperimentRequest/DesignCard 增加 idea_id；run 完成后再写 protocol-binding，不再用跑后 capsule 反向冻结协议。
- 2026-10-25 · v0.2.1 · status=pilot · 生产模式 strict：experiment 绑定缺失、模型调用失败或输出不可解析时直接抛 ModelRequiredError；test 模式保留确定性草稿回退。
- 2026-10-25 · v0.2.0 · status=pilot · 可选模型 designer：只补全缺失的设计草稿字段，不覆盖人工输入、不生成结果/指标数值/Claim、不冻结协议；模型补全后仍为 needs_human，禁止直接 G2。
- 2026-10-24 · v0.1.1 · status=pilot · 最小改进：增加 freeze：ready_for_g2 design + completed capsule + 人签理由 + limitation → ProtocolCard；校验 design/capsule 哈希
- 2026-10-23 · v0.1.0 · 初始 DesignCard 校验；仅草稿，不执行。

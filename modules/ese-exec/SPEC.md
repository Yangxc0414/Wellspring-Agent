---
id: ese-exec
name: ESE 研究执行器
stage: S5
version: 0.4.1
status: pilot
owner: research-agent
inputs:
  - protocol
  - corpus_dir
  - pipeline_dir
outputs:
  - ese-study-result
  - evidence-table
  - ese-exploration-note
tools:
  - ese_exec.run_study
  - ese_explore.run_exploration
gates: []
invariants:
  - 只读分析；不创建 Claim/EA/Verdict/Signature，不做门禁决定
  - 协议必须先于数据冻结；记录 protocol sha256 与每个仓库的 HEAD
  - 只挖掘本地 clone；联网 clone 是显式独立步骤
  - 标签只来自预注册的路径/提交消息规则，结果标为 exploratory
---

# ESE 研究执行器（ese-exec）

## Purpose

把一份预注册的 repository-mining 协议真的执行成结果制品：抽样框、时间窗、去重策略、标签来源、统计计划都来自协议文件，执行器只做提取与统计，不改协议、不写 Claim。

## Contract

输入：

- protocol JSON（schema `ese-study-protocol-0.1`）：study_id / method（目前只支持 repository-mining）/ research_questions / sampling_frame.repos / time_window / dedup_policy / label_source / analysis（metric、unit、ci_level、permutation.n、permutation.seed）；
- 本地仓库 clone 目录（按协议里的 repo name 解析）。

行为：

- 用 `git log --no-merges --name-only` 提取提交与文件列表；
- 单位 = 触碰至少一个 `.py` 文件的提交；outcome = 同提交触碰 `tests/`、`test_*.py`、`*_test.py`；bug-fix 标签 = 提交标题匹配 fix/bug/issue/regression/hotfix/patch；
- 计算每个仓库与合并的 co-change 率、Wilson 95% 区间、bug-fix 与非 bug-fix 的差及其两侧置换检验 p 值（固定种子，可复跑）。

输出：

- `result.json`（schema `ese-study-result-0.1`，含 protocol sha256、每库 HEAD）、`result.md`；
- 边界声明固定写入结果：exploratory、启发式标签、无 Claim/EA/签名。

## Exploration loop（0.2.0 新增）

`research_agent/ese_explore.py` + `scripts/ese_explore.py` 把已有部件串成一次 agent 驱动的 ESE 探索：

- 输入一个 SE 研究问题 + 可选的 SE 语料目录 + 本地仓库 clone；
- 第 1 步：调用 pipeline 跑 S1-S4（真实 SE 语料、`--ese-method repository-mining`）；
- 第 2 步：从 idea/experiment 产物起草八字段齐全的 repository-mining 协议（冻结）；
- 第 3 步：用 `ese_exec.run_study` 执行，得到区间与置换检验；
- 第 4 步：写 `note.md`：文献依据、候选 idea、设计草稿、协议完整性、真实结果、反思与下一问。

探索循环同样只读：不创建 Claim/EA/Verdict/Signature，不替代 G2/S5b。

## 分层分析（0.3.0 新增）

执行器按项目、提交文件数桶（1-2 / 3-5 / >5）、是否同时改生产文件分层，计算每层 bug-fix 与非 bug-fix 的 co-change 差，并用 Mantel-Haenszel 风险差权重给出调整后的差值；只用两组都非空的层。作者身份与更细的日历时间桶仍未实现。

## S5 运行制品（0.4.0 新增）

`ese_exec.emit_run_artifacts` 把一次研究结果写成与 run-contract 同族的制品：run-capsule.json（protocol sha256、仓库 HEADs 的 dataset sha256、执行器代码 sha256、metric/mean/std、warnings）、ea.json（对 evidence.json 的哈希）、metrics.json、run-contract.json 与 run-contract-check.json。契约校验复用 `run_contract.verify_run_contract`；它只写文件，不创建 Claim、不调用签名。`scripts/run_ese_study.py --emit-run-artifacts` 触发。

## S5 运行制品（0.4.0 新增）

`ese_exec.emit_run_artifacts` 把一次研究结果写成与 run-contract 同族的制品：run-capsule.json（protocol sha256、仓库 HEADs 的 dataset sha256、执行器代码 sha256、metric/mean/std、warnings）、ea.json（对 metrics.json 的哈希）、metrics.json、run-contract.json 与 run-contract-check.json。契约校验复用 run_contract.verify_run_contract；它只写文件，不创建 Claim、不调用签名。`scripts/run_ese_study.py --emit-run-artifacts` 触发。

## Current Implementation

`research_agent/ese_exec.py` + `scripts/run_ese_study.py`；测试 `tests/test_ese_exec.py`（提取/过滤、区间、置换、协议校验、结果文件）。

## Boundaries

- 不执行 experiment runner，也不替代 S5 的 RunCapsule/EA/Claim 链；
- 不做因果推断；标签启发式会引入误分类，结果只能作为探索性证据；
- 不自动 clone 仓库（网络动作留给显式命令）；
- 不修改协议；需要改协议时新建 study_id 并重新冻结。

## Minimal Change Workflow

1. 新方法（如 benchmark-evaluation）先扩 SPEC Contract 与协议 schema，再加实现与测试；
2. 协议字段修改 = 新 study_id，不复用旧结果；
3. 结果字段变化先改本 SPEC 的 Contract，再改代码与测试。

## Changelog

- 2026-11-18 · v0.4.1 · status=pilot · metrics 增加 pooled 标识行（test_cochange_rate/bugfix_difference/adjusted_difference/time_split_difference），capsule metric_name 改为标识符，claim 数值断言可被 verify_claim_assertions 重算
- 0.4.0（2026-11-18）：新增 S5 运行制品输出（run-capsule.json / ea.json / metrics.json / run-contract.json + check），把探索性结果封成 run-contract 可校验的一族；签名仍是人签 CLI 步骤。

- 2026-11-18 · v0.3.1 · status=pilot · 分层分析标注并剔除退化层（两组均为 0%/100%），调整差不再被退化层稀释；note 的 design-protocol gap 同步说明已实现与未实现的控制
- 2026-11-18 · v0.2.1 · status=pilot · 探索循环增加问题-候选对齐检查与设计-协议缺口记录（controls/selected idea/unsigned 选择），note 增加 2b/3b 两节
- 0.1.0（2026-11-18）：首版；repository-mining 协议执行、Wilson 区间、置换检验、结果制品与测试。
- 0.2.0（2026-11-18）：新增 agent 驱动的探索循环（pipeline S1-S4 → 协议起草 → 执行 → note.md），输入增加 pipeline_dir，输出增加 ese-exploration-note。
- 0.3.0（2026-11-18）：执行结果增加分层分析（project / commit_size_bucket / production_cochange 的 Mantel-Haenszel 调整差），把 S4 控制变量真正映射进分析；结果 schema 增加 stratified 字段。
- 0.4.0（2026-11-18）：新增 S5 运行制品输出（run-capsule.json / ea.json / metrics.json / run-contract.json + check），把探索性结果封成 run-contract 可校验的一族；签名仍是人签 CLI 步骤。

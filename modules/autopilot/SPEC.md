---
id: autopilot
name: 策略自动驾驶
stage: S2–S16
version: 0.2.3
status: draft
owner: research-agent
inputs:
  - AutopilotPolicy
  - RunDirectory
  - ClaimDraft
  - RunCapsule
  - EvidenceArtifact
outputs:
  - G1Decision
  - ProtocolCard
  - BibliographyCard
  - ClaimRecord
  - ClosureSignature
  - ExportManifest
  - EvidenceBundle
  - LineageManifest
  - AutopilotReport
  - AutopilotLedger
tools:
  - autopilot.policy.init
  - autopilot.run
  - autopilot.research
  - autopilot.status
gates:
  - G1
  - G2
  - S5b
  - G5
invariants:
  - 策略只能由人创建；自动流程不得创建、修改或放宽策略
  - 策略哈希与授权人写进每一步的 reason；签名标记 delegated，不冒充人签
  - 越过 scope / 数据集 / 最低种子数 / 有效期 / max_runs 一律停止，不得降级继续
  - 断言必须是胶囊里最差种子的下限（comparator >=, tolerance 0）；草稿弱于下限即拒绝
  - 已存在 claim 的 run 不再签署；bundle 目标已存在时不覆盖
  - 只在 CLI 暴露；MCP/HTTP/runtime 不提供 autopilot 工具
  - submission_ready 恒为 false；不投稿、不生成评审意见
---

# 策略自动驾驶（autopilot）

## Purpose

把 G1 选题、G2 冻结、S5b 签署、G5 闭合这四个原本逐次等人敲的门，变成**人一次性授权、机器在边界内执行**。解决的是"每一步都要人在场"的运维问题，不解决"谁负责"的问题：责任仍记在策略的 `authorized_by` 上，签名明确标为 delegated。

明确不解决：策略本身的合法性、真实实验、外部效度、期刊投稿。也不替代模型：无模型时 G1 的可推进性仍受 `idea` 模块的确定性候选限制（见 `57-` §3.19）。

## Contract

- 输入：`autopilot-policy.json`（schema `autopilot-policy-0.1`，必须含 `policy_sha256` 且与内容一致）、项目目录、run 目录（含 `demo.json`、`run/run-capsule.json`、`run/ea.json`、`run/claim-draft.json`）、本地 signer store。
- 策略字段：`policy_id`、`authorized_by`、`authorized_at`、`expires_at`、`scope`、`datasets`、`min_seeds`、`max_runs`、`endpoint`（bundle|lineage）、`signer_id`、`require_worst_seed_assertion`、`auto_g1`、`auto_g2.limitation`、`bibliography_source`、`statement=draft_verbatim`、`boundary`。
- 输出：G1 decision、frozen ProtocolCard、verified BibliographyCard、signed ClaimRecord、closure signature + export manifest（submission=false）、sealed evidence bundle、lineage manifest/verify、`autopilot-report.json`、append-only `autopilot/ledger.json`。
- `autopilot research`：从 topic 一步到证据包。先跑确定性 pipeline（不调用 planner/writer/idea/experiment 模型；可用 `--corpus-dir` 读本地全文），再执行同一策略下的完整委托链。要求策略 `allow_revise_idea`（确定性候选只能到 revise），否则在消耗 run 之前拒绝。
- `autopilot_snapshot`：给 HTTP/工作台的只读投影，剥掉全部绝对路径，只保留 policy/status/steps/claim/signature/bundle 相对路径/lineage/delegation 与最近 5 条历史。
- 停止：任何策略越界、claim 已存在、closable 前置缺失、closure 非 ready、bundle 已存在、lineage verify 非 clean，都以 `status=stopped` 写报告并返回非零；不得继续签署。
- 证据边界：autopilot 只调用既有模块的公开入口（`RunAgent.claim`、`ExperimentDesignAgent.freeze`、`BibliographyAgent.verify`、`ClosureAgent.sign/publish`、`LineageAgent.build/verify`、`PipelineRunner`），不复制它们的判定逻辑，也不写 Claim/EA 之外的证据。

## Current Implementation

- `research_agent/autopilot.py`：`build_policy` / `load_policy` / `policy_fingerprint` / `inspect_run` / `parse_assertion` / `worst_seed_floor` / `run_autopilot` / `autopilot_status`；
- `research_agent/cli_autopilot.py`：`autopilot policy init|run|status`，由 `cli.py` 单向 import；
- 流程：策略检查 → G1（取 `shortlist.ranked[0]`，可配置是否接受 revise）→ G2（design 无 blockers 时 `freeze` 绑定胶囊）→ bibliography verify → `RunAgent.claim`（断言=最差种子）→ 用 `run_dir` 重放 pipeline（strict + claim_file + **复用原 idea/design**，避免重新检索改变 design_sha256 而在 G2 被拦）→ closure check → `ClosureAgent.sign`（HMAC，本地 signer）→ `publish` 到 `bundles/<RUN-ID>` → `verify_bundle` → `LineageAgent.build/verify` → 重写 loop-capsule；
- 每次运行写 `autopilot/<RUN-ID>/autopilot-report.json` 与 `claim-delegation.json`，并追加 `autopilot/ledger.json`；`max_runs` 只统计真正签过 claim 的记录；
- 不联网；fixture 运行必须在报告里保持 fixture 警告；不修改 MCP 工具面；
- bind 重放时从原 `paper.json` 读取 language/venue，并用 `_replay_writer` 只回放 `model_draft` 章节，避免把宿主写好的稿重写成确定性模板；回放文本仍走原有引用/数字/长度校验。

## Boundaries

- 策略文件不是签名：它记录的是授权范围与授权人，`closure signature` 仍用本地 HMAC signer，且 `human_reason` 以 `[delegated:autopilot]` 开头；
- 策略的“人写”是**流程约束，不是密码学证明**：能运行 CLI 的本地进程同样能读 signer store，也能写一份自称授权的策略。真正的隔离要求授权人持有 agent 读不到的密钥（例如口令保护的离线签名），当前未实现；因此报告只能说“按策略 X 代签”，不能说“人已逐次批准”；
- 无模型时 G1 只能选 `revise` 候选，策略必须显式 `allow_revise_idea`；这不是质量证明；
- 不保证 run 一定 closable：缺 protocol/bibliography/result-figure 时在对应步骤停止；
- 不提供 MCP/HTTP 端点；宿主 Agent 只能通过 CLI/Shell 触发，且必须先有策略；
- 不覆盖已有 claim、bundle、export manifest。

## Minimal Change Workflow

1. 先改本文件的 `Contract` 或 `Current Implementation`；
2. 升 `version`，在 Changelog 追加说明；
3. 改代码 + `tests/test_autopilot.py`；
4. `python -m unittest tests.test_autopilot`；涉及命令面时跑 `workspace export`。

## Changelog

- 2026-10-30 · v0.2.3 · status=draft · 不让策略越过 G2：inspect_run 读取 demo.modules.study_design.audit，若研究设计披露为 incomplete 则拒绝签署，理由为 study design audit is incomplete; G2 is blocked。实测 ccfa-gate-probe（模板设计）autopilot 返回 stopped/policy 且未创建 claim；v7（披露完整）不受影响。tests.test_autopilot 14 项 OK。只收紧不放松，升 patch。
- 2026-10-30 · v0.2.2 · status=draft · autopilot research 支持 --study-design-file：先把 study-design.json 复制进新 run，首跑与 bind 都带上它，避免全自动路径丢失研究设计；run 已有 demo.modules.study_design 但目录里没有文件时，bind 会从 demo 恢复并写入 run/study-design.json。实测 v7 全自动后论文 setup 段仍是研究设计，严格审计只剩 fixture。tests.test_autopilot 13 项 OK。新增可选输入，升 patch。
- 2026-10-30 · v0.2.1 · status=draft · 绑定 claim 不再毁掉宿主写好的稿：Qoder 实测发现，autopilot 重放 pipeline 绑定时 1) 固定用 en/en_conference，中文稿被整篇重写成英文；2) 没有 section_writer，Qoder 的五段 model_draft 被确定性模板覆盖。现在 bind 从原 paper.json 读取 language/venue，并用 _replay_writer 只回放状态为 model_draft 的章节，其他章节仍走确定性生成；模型文本仍通过原有引用/数字/长度校验。实测 runtime_data/qoder-effect-v4：五段 Qoder 中文内容在 autopilot 完成后原样保留，结果段绑定 iris claim；同稿 strict writing audit 只剩 fixture 边界。tests.test_autopilot 13 项 OK（FullChain 新增 MODEL MARKER 断言）。bind 行为修复，升 patch。
- 2026-10-30 · v0.2.0 · status=draft · 一步到包：新增 `autopilot research --project --topic --policy`，确定性跑完 S1→S5 后接同一策略的委托链；要求策略显式允许 revise 候选，否则在消耗 run 前拒绝。bind 阶段改为复用 run 已有的 idea.json/experiment.json——实测发现重新检索会让 design_sha256 变化，strict 在 G2 直接 blocked（`expected fa6ebb… got aa507b…`），复用后通过。新增 `autopilot_snapshot`（路径剥离）与 runtime `/api/autopilot-status` 只读端点；工作台 CLOSURE PROFILES 下新增 AUTOPILOT 条带（policy/status/steps/claim/sig/bundle/委托声明）。实测 runtime_data/autopilot-research：一条命令从 topic 到 bundles/RUN-AUTO-…（9 文件，clean，lineage clean）；真实 DOM 显示 `COMPLETED · AUTO-f275d62f45 · bundles/RUN-AUTO-E2E · verified 9 files`；tests.test_autopilot 12 项、test_runtime_api 4 项 OK。策略仍不可覆盖（去掉 --force），输出契约新增命令与只读端点，升 minor。
- 2026-10-30 · v0.1.0 · status=draft · 首版：策略边界（scope/数据集/最低种子/有效期/次数/终点）+ G1→G2→bibliography→S5b→G5→publish→lineage 的委托链；断言必须等于最差种子下限，delegation 写进每个 reason；已签 claim 与已有 bundle 不覆盖；只在 CLI 暴露。

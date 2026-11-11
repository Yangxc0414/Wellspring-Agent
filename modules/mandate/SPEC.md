---
id: mandate
name: 持续委托投影
stage: META
version: 0.2.0
status: draft
owner: research-agent
inputs:
  - Project
  - RunCapsule
  - AutopilotPolicy
outputs:
  - MandateStatus
tools:
  - mandate.status
gates: []
invariants:
  - 只读投影：不创建 Claim/EA/Verdict，不签名、不批准、不执行、不写项目状态
  - 触发来自已有 loop-capsule 的 blockers/next_actions，不重新计算门禁；capsule 快照与判定总线冲突时以总线为准并留 stale_snapshot_suppressed 审计行
  - 缺失 artifact 不是 pass；过期或撤销的委托必须停止
  - 委托授权只能由人写入；agent 不得创建、放宽或续期
  - 状态只能是 empty/active/partial/needs_human/stopped
---

# 持续委托投影

## Purpose

把“一次 run 是否有效”的验收单位，扩展为“一项委托在一段时间内是否被妥善处理”。
本模块只读取项目、run capsule 和 autopilot policy，输出触发、上下文、方案、授权状态、
核验规则和未完成事项；它不产生任何新权限，也不替代 G1/G2/S5b/G5。

## Contract

- 输入：项目目录（含 `project.json`、`runs/*/loop-capsule.json`、可选
  `autopilot/policy.json`）。
- 输出：`research-mandate-0.1` JSON，含：
  - `stages.trigger`：来自 capsule 的 blockers 与 policy 过期事件；
  - `stages.context`：每个 run 的 capsule 路径/SHA-256、route/status、blocker 数；
  - `stages.plan`：capsule 的 next_actions（owner/gate/command），按 run 聚合；
  - `stages.approval`：policy 状态（missing/active/expired/exhausted/invalid）、
    `runs_used/remaining_runs` 与 human gates；签名/发布仍为 human-only；
  - `stages.verification`：触发被清除的判定规则与仍需人执行的命令；
  - `stages.obligations`：跨 run 的未完成 blocker；
  - `stages.acceptance`：状态与验收规则。
- 失败：项目不存在或不可读时抛 `ProjectError`；单个 capsule 损坏时记为
  `invalid_capsule` 触发，不静默跳过。
- 证据边界：本模块输出不是证据、不是 Claim、不是 gate 决定；缺失节点不是 pass。

## Current Implementation

- `build_mandate_status(project, now=None, max_runs=20)`：纯读投影；
- CLI：`python -m research_agent mandate status --project <dir> [--max-runs N] [--output file]`；
- 无 MCP 工具、无 runtime 端点、无后台 daemon；
- 状态：无 run 为 `empty`；有 blocker/next_action 为 `needs_human`；policy 过期或
  ledger 计数达到 `max_runs` 为 `stopped`；窗口被 `--max-runs` 截断且窗口内无阻碍为
  `partial`（窗口外的 run 是没看过，不是干净）；无阻碍且未截断为 `active`。

## Boundaries

- 不判断科学质量，不重算 CCF-A/venue 审计，不生成方案内容；
- 不把 `next_actions` 自动执行；命令只作为人可复制的建议；
- 不读取或修改 `claim.json`/`closure` 的签名字段；
- 不新增委托，不延长有效期，不扩大 scope；policy 只能由人创建；
- 预算耗尽按 `autopilot/ledger.json` 中同一 policy_id 的 runs 计数判定；ledger 不可读时
  不把它当作“已用 0”，而是把 policy 标为 invalid 并给出 trigger，避免误报 active。

## Minimal Change Workflow

1. 先改本文件的 `Contract` 或本节；
2. 升 `version`，在 Changelog 追加说明；
3. 改 `research_agent/mandate.py` + CLI + 测试；
4. `python -m unittest discover -s tests -v`。

## Changelog

- 2026-11-11 · v0.2.0 · status=draft · capsule 触发消费迁移到判定总线（verdict-ledger 0.2.0 roadmap 项）：capsule 是签署前快照，autopilot 代签后其 CLOSURE_UNSIGNED 变 stale——mandate 现在对每个 run 先查判定总线（closure_profiles 单点判定，非重算门禁：总线消费的是已记录判定），冲突时以总线为准：抑制 stale blocker、过滤 stale 重签 plan、追加 `stale_snapshot_suppressed` 审计触发（authority=verdict-ledger、recomputed、source_sha256 绑定，fail-visible 不静默）。不变量「不重新计算门禁」修订为「不重算门禁；capsule 快照与判定总线冲突时以总线为准并留审计行」。实测 E2E RUN-E2E-02：suppression 触发行 + plan 零 stale 重签 + RUN-E2E-01 诚实 blocker 保留；tests/test_mandate 新增迁移测试。输出新增触发种类，升 minor。
- 2026-11-01 · v0.1.3 · status=draft · 修掉自己模块里的乐观偏差：--max-runs 截断窗口时不再报 active，新增 partial 状态与 MANDATE_SCOPE_TRUNCATED 触发；窗口内已有 blocker 时仍为 needs_human。实测两 run（A 干净、B 未签 claim）max_runs=1 由 active 变 partial。新增 2 项测试，共 10 项。
- 2026-10-31 · v0.1.2 · 预算耗尽纳入投影：按 `autopilot/ledger.json` 中同一 policy_id 的
  runs 计数对比 `max_runs`，达到上限即 `stopped`；ledger 不可读标为 invalid 而不是已用 0。
- 2026-10-31 · v0.1.1 · 明确 0.1.x 只按 expires_at 停止，未累计 ledger 的 max_runs；
  预算耗尽仍由 autopilot 执行层拦截，避免把“投影状态”误当“预算执行器”。
- 2026-10-31 · v0.1.0 · 首版：只读聚合 run capsule 的 blockers/next_actions 与
  autopilot policy，输出持续委托的触发/上下文/方案/授权/核验/未完成事项；不新增权限。

---
id: lineage
name: 证据沿袭与变更影响
stage: S13–S16
version: 0.2.0
status: pilot
owner: research-agent
inputs:
  - demo.json
  - claim.json
  - run-capsule.json
  - ea.json
  - protocol-card.json
  - bibliography-card.json
  - result-figure.manifest.json
  - result-figure.svg
  - paper.json
  - closure-report.json
  - signature.json
  - export-manifest.json
outputs:
  - LineageManifest
  - ChangeImpact
tools:
  - lineage.build
  - lineage.verify
  - lineage.impact
gates:
  - G5
invariants:
  - 不创建 Claim/EA/Verdict，不自动重跑或重签
  - 节点哈希来自文件或 capsule 内容哈希；不能凭空生成支持关系
  - 上游节点变化必须沿依赖边传播为 stale
  - signature 失效时 export_allowed=false
  - S1 span 到 claim 的边在现有契约中尚不存在；不得伪造成已连通的语义链
  - 处置分类由 stale 节点 kind 推导，不代表自动修复已经执行
---

# 证据沿袭与变更影响（S13–S16）

## Purpose

在已经闭合的科研产物上回答一个现有生成式 Agent 很少系统处理的问题：**证据、数据或代码变了以后，哪些 Claim、图、稿件槽位、closure 与 signature 不再成立？** 它把产物做成内容寻址的依赖图，并在变更时传播 stale 状态，作为重跑、重绑、重新闭合与重新签署的入口。

## Contract

- 输入是一个本地 bundle，包含 RunCapsule、EA、Claim、ProtocolCard、BibliographyCard、结果图 manifest/SVG、PaperContract、ClosureReport、Signature 和 ExportManifest 中实际存在的文件；
- 构建 `LineageManifest`：每个节点含 `node_id/kind/label/sha256/dependencies/path/metadata`；边由字段中的 ID 与状态推导；
- 当前节点覆盖：dataset/code（来自 capsule 内容哈希）→ run → protocol/EA → figure/claim → paper slots → paper → closure → signature → export manifest；bibliography 作为独立上游；
- `lineage verify --manifest ... --bundle ...` 重新计算当前节点的哈希；任何变化返回 `stale`；
- `lineage impact` 传播变化到所有下游节点，输出 `stale_claims/stale_slots/stale_figures/requires_reclosure/requires_resign/export_allowed`，并把每个 stale 节点归入 `rerun/rewrite/recheck` 三类处置，给出 `action_counts` 与有序 `next_steps`；
- `--fail-on-stale` 以非零退出码作为 CI/签署前门禁；没有发生变化时必须返回 `clean`；
- 不修改输入，不写 Claim/EA，不自动重跑或重签；处置只是计划，执行仍需人或下一层运行器；

## Current Implementation

- `research_agent/lineage.py`：`LineageAgent.build/verify/impact`；
- CLI：`python -m research_agent lineage build|verify|impact`；
- bundle 已生成真实 ChemLab 闭合快照：11 项 closure 通过、人签 signature；
- 对 dataset 哈希做模拟变更后，传播到 run/protocol/EA/figure/claim/4 个 slots/paper/closure/signature/export，`export_allowed=false`；impact 同时生成 `dispositions`（run/evidence→rerun，figure/paper→rewrite，其余→recheck）、`action_counts` 与 `next_steps`；
- 当前只覆盖 S5 结果臂与 paper/closure；S1 SourceHit/Span 还没有进入 Claim 的显式边（contracts 里 Claim 只引用 EA），这是下一步而不是已完成能力；
- 不判断 claim 是否在语义上被 span 支持；沿袭只保证“哪些产物需要复查”。

## Boundaries

- 不是 peer review，不是事实核查；
- 不把 stale 自动修复为 fresh；
- 不把“文件哈希一致”解释成“结论正确”；
- 不替代 `closure check`、人工 claim 签署或最终导出门。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `research_agent/lineage.py`、`research_agent/cli.py` 与 `tests/test_lineage.py`；
4. 跑 `python -m unittest discover -s tests -v`；
5. 重新生成 bundle 的 lineage 与 impact，确认 clean/stale 两条路径。

## Changelog

- 2026-10-25 · v0.2.0 · status=pilot · impact 增加维护处置：stale 节点映射为 rerun/rewrite/recheck，输出 action_counts 与有序 next_steps；处置只计划，不自动重跑/重签
- 2026-10-24 · v0.1.0 · 初始实现：17 节点内容寻址图、dataset 变更传播、verify/impact CLI、4 个测试；覆盖闭合后的 S5 证据臂，明确 S1→claim 边尚未实现。

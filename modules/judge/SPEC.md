---
id: judge
name: 证据支持审稿
stage: S5b–S13
version: 0.1.2
status: pilot
owner: research-agent
inputs:
  - PaperContract
  - ClaimRecord
  - Span
  - SupportJudge
outputs:
  - SupportAuditReport
tools:
  - judge.support
  - model.support_judge
gates: []
invariants:
  - 只产 advisory 支持判定，不创建/修改 Claim、EA、paper slot、gate、signature 或 export
  - 状态只能是 supported / partial / contradicted / insufficient
  - 模型只能基于给定句子与证据片段判断，不能新增引用或证据
  - 无模型时只能输出明确标注的 lexical heuristic，不能伪装成语义判断
  - production 的 strict 审计要求 judge 模型绑定；test 模式允许 heuristic 回退
  - 句子出现显式 [span] / [source] 时只使用该引用；section refs 只能作为无显式引用时的 fallback
  - production strict 下 contradicted verdict 必须阻断 job；partial/insufficient 只作 advisory
  - judge 与 paper/idea/experiment/literature 共用同一 profile 时，runtime readiness 必须显式提示独立性受限；只警告，不阻断
---

# 证据支持审稿（S5b–S13）

## Purpose

在已签 claim 之后，对论文草稿的句子与章节证据引用做独立支持审稿，帮助人发现“引用存在但并不支持这句话”的情况。它是 advisory 审计，不是新门禁，也不替代作者判断。

## Contract

- 输入：`PaperContract`（draft sections + evidence_refs）、已签 `ClaimRecord`、`Span[]`、可选 `SupportJudge`；
- 输出：`SupportAuditReport`：
  - `items[]`：section、sentence、citation_mode、evidence_refs、status、rationale、method；`citation_mode` 为 explicit_span / explicit_source / section_fallback / unresolved_explicit；
  - `citation_modes`：按对齐方式计数，提示 section fallback 的覆盖比例；
  - `counts`：supported / partial / contradicted / insufficient；
  - `method`：`model_judge` 或 `lexical_overlap_heuristic`；
  - `status`：`ready` / `partial` / `attention` / `not_applicable`；
  - `boundary` 与 warnings。
- 模型输出必须按 item id 对齐；未知 id、非法状态、越界 evidence_refs 一律丢弃；
- 模型不能新增证据引用、Claim、数字或改变 paper/gate；
- strict 模式下模型缺失、调用失败或输出不可解析直接抛 `ModelRequiredError`；非 strict 模式回退 heuristic 并明确标注。

## Current Implementation

- `research_agent/support_audit.py`：按句切分 draft section；显式 `[span]` / `[source]` 优先，section evidence_refs 仅作 fallback；模型 verdict 校验后汇总；无模型时 lexical overlap heuristic，绝不返回 supported；production strict 下 contradicted 抛 `SupportAuditError`；
- `research_agent/adapters/support_judge.py`：通过设置中的 `judge` 模型绑定调用网关；
- `research_agent/postprocess.py`：在已签 claim 的 postprocess 中写 `support-audit.json`，并写入 `postprocess.json`；
- runtime/CLI 都可注入 judge；production readiness 要求 judge 绑定与 key；
- `ModelService.readiness()` 在 judge 与写作/假设/实验/文献共用同一 profile 时返回 `warnings[]`，提示同一基座模型的独立性受限；不改变 bound/key 的硬性 readiness 判定；
- 该报告不进入 closure checks，不改变 G1/G2/G3/G5。

## Boundaries

- 不是语义蕴含的证明；`partial` 仍可能是错的；
- 不是新 gate，不自动拒绝/接受 publication；
- 不覆盖数值 claim 的确定性重算（那仍由 claim assertions / Closure 负责）；
- 人签 claim、Closure、导出仍只能由人工完成。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `support_audit.py`、`support_judge.py` 与测试；
4. 跑 `python -m unittest discover -s tests -v`，并导出工作区快照。

## Changelog

- 2026-10-26 · v0.1.2 · status=pilot · 独立性提示：judge 与 paper/idea/experiment/literature 共用同一 profile 时，runtime readiness 显式 warning；不阻断生产模式，不改变 gate/claim。
- 2026-10-26 · v0.1.1 · status=pilot · per-citation 对齐：显式 [span]/[source] 优先，section refs 仅作 fallback；新增 citation_mode；production strict 下 contradicted verdict 直接阻断 job。
- 2026-10-26 · v0.1.0 · status=pilot · 初始独立支持审稿：句子级 advisory verdict、模型 judge、lexical heuristic 回退、postprocess `support-audit.json`；不改变 claim/gate/export。

---
id: bibliography
name: 参考文献核验
stage: S13
version: 0.1.0
status: draft
owner: research-agent
inputs:
  - frozen_metadata_snapshot
outputs:
  - BibliographyCard
tools:
  - bibliography.verify
gates:
  - G5
invariants:
  - 必须有 DOI/唯一标识与元数据快照哈希
  - 只做元数据核验，不做同行评审
  - 不伪造条目或引用
---

# 参考文献核验

## Purpose

对冻结的 DOI 元数据快照做结构核验，产出可绑定的 BibliographyCard；它证明条目存在且元数据一致，不证明论文结论正确，也不替代同行评审。

## Contract

- 输入：`bibliography.json`（`verification_source=datacite_api_snapshot`，逐条 DOI/title/authors/year/url/response_sha256）；
- 校验：DOI 唯一且以 `10.48550/` 开头、标题/作者/年份/URL 非空、response 哈希 64 位、至少 2 条；
- 输出：`BibliographyCard`（status=verified_datacite_snapshot、entry_count、card_sha256、verified_at、warnings）；
- 失败：缺字段/重复 DOI/哈希非法 → 拒绝，不生成 card；
- 不联网：只读冻结快照；快照时间与来源必须写入。

## Current Implementation

- `research_agent/bibliography.py`：`BibliographyAgent.verify`；
- 冻结 `modules/literature/fixtures/bibliography.json`：4 篇 CC-BY arXiv 论文的 DataCite 元数据快照；
- 仅元数据核验，不是 peer review；不允许把 card 写成“论文已通过评审”。

## Boundaries

- 不抓取知网/万方/维普；
- 不核验正文引用上下文；
- 不自动投稿；
- 不覆盖数据/图表/claim 的证据边界。

## Changelog

- 2026-10-24 · v0.1.0 · 初始 DataCite 快照核验与 BibliographyCard。

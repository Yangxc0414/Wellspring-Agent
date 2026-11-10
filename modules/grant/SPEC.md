---
id: grant
name: 基金申报
stage: S8–S12（基金轨）
version: 0.2.1
status: pilot
owner: research-agent
inputs:
  - topic
  - scheme
  - evidence_refs
outputs:
  - GrantPlan
  - ComplianceChecklist
  - EvidenceMap
tools:
  - grant.scheme
  - grant.template
  - research_grant_template
gates:
  - G4
invariants:
  - 不生成科学观点
  - 不写预算数字
  - 不自动提交
  - 官方模板优先
---

# 基金申报子智能体（NSFC/NSSFC 轨）

## Purpose

为 NSFC/NSSFC/通用研究计划生成申报骨架与合规检查清单，把证据映射到模块，不替代申请人的科学判断与最终责任。

## Contract

- 输入：topic / scheme / evidence_refs；
- 输出：`GrantPlan`（模块、合规项、evidence_refs、status=draft_needs_human）；
- NSFC：立项依据 / 研究内容 / 研究基础 / 创新点 / 预算说明；
- NSSFC：选题说明 / 选题依据 / 研究内容 / 创新之处 / 研究基础 / 经费概算 / 活页匿名；
- 不写科学观点、预算数字；不自动提交；官方模板优先。

## Current Implementation

- `research_agent/modules/grant.py`；
- 仅骨架与合规提示；不联网、不读官方模板文件；
- 页限/字数只写“以当年模板为准”，不伪造具体政策。

## Boundaries

- 不是 ghostwriting；科学问题、创新点、预算由申请人/负责人提供；
- 不替代伦理/利益冲突/AI 使用声明的人工核对；
- 不自动提交、不伪造同行评审。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `GrantAgent` 与测试；
4. 不碰 paper/figure 模块。

## Changelog

- 2026-10-31 · v0.2.1 · status=pilot · 新增 MCP 工具 research_grant_template：在项目内写空白 grant-draft-0.1，申请人填写后用 research_venue_audit(kind=grant) 检查；路径限制在项目内，无签名/提交入口。新增 3 项测试。
- 2026-10-31 · v0.2.0 · status=pilot · 基金轨只有 GrantPlan 骨架和独立 venue audit，没有给申请人一个可填写的起始文件。新增 grant template --scheme nsfc|nssfc|generic --output：写出空白 sections（模块名来自 SCHEMES）、evidence_refs、compliance、NSSFC 默认匿名标记；申请人填写后用 venue audit --kind grant 检查。空白模板会被审计 blocked，这是预期。新增 4 项测试。契约新增 CLI 与 grant-draft-0.1，升 minor。
- 2026-10-23 · v0.1.0 · 初始 NSFC/NSSFC 骨架与合规清单。

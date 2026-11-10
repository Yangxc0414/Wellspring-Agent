---
id: venue-audit
name: 中文期刊与基金申请检查
stage: S8–S12（写作/基金轨）
version: 0.3.0
status: draft
owner: research-agent
inputs:
  - Manuscript
  - GrantSections
outputs:
  - VenueAudit
tools:
  - research_venue_audit
  - venue.audit
gates: []
invariants:
  - 只做结构与合规检查，不生成科学观点、不写预算数字、不签名、不提交
  - 中文期刊检查基于工作 profile，不是官方模板；官方模板与当年征集通知优先
  - 基金检查只验收模块骨架与合规确认，不替代申请人的判断
  - 状态只能是 ready_for_human / needs_revision / blocked，submission_ready 恒为 false
---

# 中文期刊与基金申请检查

## Purpose

CCF-A 设计审计（`ccfa-audit`）只覆盖英文 ML 会议，中文期刊与 NSFC/NSSFC 申报没有对应的
确定性检查：通用写作审计看不到中文摘要/关键词、GB/T 7714 参考文献、基金标注、活页匿名等
约束；基金模块只生成骨架，不检查申请人交回的稿件是否完整。本模块补这两个缺口。

## Contract

- `audit_chinese_journal(manuscript, profile="zh_core_journal")`：
  - 输入为 `manuscript.py` 产出的稿件 JSON（abstract / keywords / sections / references）；
  - 检查中文摘要（≥50 字，工作目标 ≥150）、关键词 3–8、profile 要求的中文/英文节标题、
    参考文献数量（≥5，工作目标 ≥8）、中文文献存在性、元数据核验状态、基金/资助标注、
    创新/贡献陈述、数据/代码可用性；
  - 输出 `venue-audit-0.1`：checks / blockers / warnings / status。
- `audit_grant(sections, scheme, evidence_refs, anonymous, identity_removed, ai_statement)`：
  - 按 NSFC/NSSFC/generic 的模块清单检查必备章节、章节长度、创新点、证据引用、
    NSSFC 活页匿名确认与 AI 使用声明；
  - 输出同 schema；`status` 为 `ready_for_human` / `needs_revision` / `blocked`。
- 两者都 `submission_ready: false`；不读取官方模板、不联网、不生成申报正文。
- `manuscript_from_draft(document, references)` 把 DraftDocument + pack 参考适配为稿件视图；`writing_audit` 在中文期刊 profile 下调用本模块，结果作为 advisory 并入 warnings，不改变 writing audit 的 status。


## Current Implementation

- `research_agent/venue_audit.py`：`audit_chinese_journal` / `audit_grant` / `manuscript_from_draft`；MCP 工具 `research_venue_audit` 与 CLI `venue audit` 共用这两个检查；无签名/提交路径；
- 中文期刊 profile 复用 `revision_templates.get_venue_profile`（工作 profile，非官方模板）；
- 基金模块清单复用 `modules.grant.SCHEMES`，避免两处政策漂移；
- 检查是确定性的关键词/结构检查；它不是同行评审，也不能证明创新性。

## Boundaries

- 中文期刊检查只覆盖“有没有、够不够、标没标”，不评价学术质量与创新性；
- 基金检查不写科学问题、创新点、预算数字，不替代伦理/利益冲突/匿名核对；
- 不自动提交、不生成签名、不把“检查通过”写成“可投稿”；
- 目标期刊/基金委当年官方模板与页限永远是最终依据。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `venue_audit.py` 与 `tests/test_venue_audit.py`；
4. 需要 CLI 时另开 `venue audit`，并同步 workspace/plugin 导出。

## Changelog

- 2026-11-01 · v0.3.0 · status=draft · pack 附件逻辑抽成 research_agent/pack_audit.py 的 attach_pack_rubric + manuscript_pack_text，CLI 与 MCP 共用同一实现（此前 CLI 有 --skill-pack-root/--venue/--skill-stage/--skill-profile/--skill-max-items，而宿主工具面一个都没有，两面结论不可比）。attach 时同时产出 coverage.pack_scope 与截断说明，并把 scope_like 计数升级为一条 warning。CLI 侧净减 69 行重复代码。
- 2026-11-01 · v0.2.9 · status=draft · --skill-profile 增加 design（idea+design），用于把研究设计 artifact 与稿件审计分开；阶段/profile 过滤现在发生在 max-items 窗口之前，skill_pack 与 coverage.pack_scope 一并带出 checklist_items / checklist_total / limit_applied / truncated / warnings，窗口不完整时 boundary 追加 partial rubric。分母不完整的 advisory 评分必须自己说明自己是部分的。
- 2026-11-01 · v0.2.8 · status=draft · venue audit 新增 --skill-profile draft/submission/revision；与 --skill-stage 互斥；coverage 输出 profile 与 stages；仍为 advisory。
- 2026-10-31 · v0.2.7 · status=draft · venue audit 的 skill pack 摘要新增 actionable_counts；coverage 默认跳过叙述性条目并报告 context_skipped，仍只作咨询。
- 2026-10-31 · v0.2.6 · status=draft · 接入 skill pack 时暴露 route_confidence；低置信度路由写入 warnings，仍只作咨询，不改变任何判定。
- 2026-10-31 · v0.2.5 · status=draft · venue audit 的 --skill-pack/--skill-pack-root 现在除 route/checklist 外还输出 coverage（covered/missing/unmatched），可用 --skill-stage 过滤；仍是 advisory，不改变 status、不把词项覆盖当合规。新增覆盖断言。
- 2026-10-31 · v0.2.4 · status=draft · venue audit 支持 --skill-pack-root + --venue：从 shared venue-index.tsv 自动路由 pack，并把 route/pack checklist 作为 advisory 附在结果中；不改变 status，不把路由或清单当 pass/fail。新增 1 项集成测试。
- 2026-10-31 · v0.2.3 · status=draft · venue audit 之前只有硬编码中文期刊检查；新增可选 --skill-pack，把本地 SKILL pack 的 license/provenance/阶段 checklist 作为 advisory 附在结果中，不改变 status、不把 skill 清单当 pass/fail。新增 1 项测试。
- 2026-10-31 · v0.2.2 · status=draft · 中文期刊/基金检查只有 MCP 工具，没有人类/脚本可直接调用的 CLI。新增 venue audit --file --kind zh_journal|grant（--profile/--scheme/--anonymous/--identity-removed/--ai-statement），输出 venue-audit-0.1；只读、不签名、不提交。新增 2 项 CLI 测试，venue-audit 11 项通过。契约新增 CLI，升 patch。
- 2026-10-31 · v0.2.1 · status=draft · 新增 manuscript_from_draft(DraftDocument, references)，把解析后的草稿适配为稿件视图；writing_audit 在中文期刊 profile 下接入本模块，结果作为 advisory 并入 warnings，不改变 writing audit status。新增 1 项 adapter 测试。
- 2026-10-31 · v0.2.0 · status=draft · 新增只读 MCP 工具 research_venue_audit（kind=zh_journal|grant），由 ResearchMCPService.venue_audit 读取项目内 JSON 并调用两个纯函数；路径受 project_file 限制。新增 4 项 MCP 测试，覆盖中文稿件、NSSFC 匿名与路径越界。工具无签名/提交入口。
- 2026-10-31 · v0.1.0 · 首版：中文期刊稿件检查（摘要/关键词/章节/参考文献/基金/创新/数据）
  与 NSFC/NSSFC 基金骨架检查（模块/长度/创新/证据/匿名/AI 声明）；纯函数，无签名与提交路径。

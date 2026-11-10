---
id: paper
name: 论文写作
stage: S8–S12
version: 0.6.0
status: pilot
owner: research-agent
inputs:
  - topic
  - language
  - venue_type
  - evidence_refs
  - figure_refs
  - spans
  - literature_brief
  - idea_candidates
  - design
  - claim_statements
  - claim_assertions
outputs:
  - PaperContract
  - DraftSection
  - SectionSlots
  - DraftScaffold
  - paper.md
tools:
  - writing.profile
  - claim.slot
  - model.paper_writer
gates:
  - G3
  - Q1
invariants:
  - 不创建 Claim
  - 结果槽必须 pending_evidence 直到 EA/Claim/Figure
  - 示意图不能绑定为结果图；数据图必须引用 manifest
  - 模型不能写 Results，不能引入未给出的引用或数字
  - 无 key 时确定性草稿必须仍然可读、可运行
---

# 论文写作子智能体（S8–S12）

## Purpose

按语言/venue 生成论文契约与章节骨架，明确哪些槽位需要证据，绝不提前写结果数字或结论。它让“论文—实验”可以并行：方法与骨架可先写，结果槽保持 `pending_evidence`。

## Contract

PaperRequest 输入 topic/language/venue_type/spans/literature_brief/idea_candidates/design/claim_statements(+assertions)/可选 synthesis（literature-synthesis-deterministic-0.1 或 -0.1 矩阵）；输出 PaperContract/SectionSlots/DraftScaffold/paper.md。synthesis 存在且有 ≥2 来源主题时，相关工作章节追加跨来源主题块，引用只允许当前 run 已有 span id；结果槽仍只在 EA/人签 Claim 后绑定；citation.related 仍要求 verified bibliography。模型不能写 Results、不能新增引用或数字。


## Current Implementation

- `research_agent/modules/paper.py`：按 profile 生成槽位与证据约束的 DraftSection；无 claim 时结果段不写数字；有 claim_refs/claim_statements 时只引用人签陈述；存在 claim_assertions 时只渲染 status=pass 的已验证 metric/comparator/value/observed；
- 可选 `section_writer`（`research_agent/adapters/paper_writer.py`）：仅允许写 abstract/introduction/related_work/discussion/conclusion；引用必须是已给 span/source，数字必须在给定证据/设计上下文中出现，否则拒收并回退确定性草稿；Results/Method/槽位/门禁永不由模型写入；
- `render_paper_markdown()` 输出 `paper.md`；pipeline 还输出 `report.md`（覆盖、来源、gap、候选、设计、run、门禁与下一步）；
- 默认 `writer=auto`：无 paper binding 或无 key 时不联网，直接使用确定性草稿。


## Boundaries

- 不替代 Writer 的证据绑定；
- 不把 schematic figure 绑定到 result.figure；
- 不把模型草稿当证据；模型不能写 Results；
- 不绕过 Q1/G4/G5。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `PaperAgent` 与测试；
4. 不碰 figure/experiment/claim。

## Changelog

- 2026-10-30 · v0.6.0 · status=pilot · 论文的实验设计段现在可以来自真正的 pre-registered study design，而不是本地 run 设计：PaperRequest 新增 study_design/study_design_audit，_study_design_text 渲染问题/假设/claims-evidence/数据切分与泄漏/基线调参与算力/单变量消融/稳健性/计算/统计与功效/负结果/局限，status 随 CCF-A 审计；study design 存在时不再加“本地协议验证设计”前缀（本地 run 仍只在结果段标注协议验证）。实测 Qoder v7：setup 段是研究设计，正文无 StandardScaler，严格写作审计只剩 fixture。tests.test_pipeline 27 项 OK。输出契约新增两个可选输入，按规则升 minor。
- 2026-10-30 · v0.5.2 · status=pilot · 论文不再把本地协议验证冒充研究设计：当 PaperRequest 带 run_summary 时，实验设计段前置“本地协议验证设计（不是本研究的科学设计）”说明，结果段前置“claim 来自本地协议验证 run，不是本研究科学结论”。原因是 Qoder 宿主评测里，一篇钙钛矿稿的实验设计段直接出现 iris 的 logistic regression/accuracy，结果段绑定 iris claim，读者会把它误读为研究结论。文字边界由 pipeline 的 run 模块显式传入，不改变槽位与哈希。tests.test_pipeline 25 项 OK（新增一项断言两段前缀）。只改输出文案，升 patch。
- 2026-10-30 · v0.5.1 · status=pilot · 0.5.1（2026-10-30）：确定性草稿不再假设 design.seeds 是 int。设计工件在部分路径带的是种子列表，而草稿用 %d 格式化，导致 G2 之后直接 TypeError（复用冻结设计跑严格模式时必现）。改为调用 contracts.seed_count()，与 experiment/evidence_packages 共用同一实现。tests.test_pipeline 20 项 OK。
- 2026-10-30 · v0.5.0 · status=pilot · 0.5.0（2026-10-30）：写作护栏两处修正，都由今天一次真实端到端跑暴露（Qoder 作为模型连答三轮，最后停在 paper needs_evidence）。(1) 数字守卫误杀：_validate_writer_sections 在含引用的原文上扫 NUMBER_RE，而 span id 本身带数字（ARXIV-2609.19526-S01-03），于是宿主写出的 5 个章节里 4 个被判 ungrounded_number 拒绝，只有不含引用的那节通过——即"引用得越多越像编造数字"。修法是先 CITATION_RE.sub 去掉方括号引用再扫数字；真实编造的数字仍被拒（新增测试用 35 percent 验证）。(2) 引用白名单过宽：payload 的 allowed_refs 与校验集都用全部 request.spans（实测 1329 条），而提示词只展示前 40 条 evidence，等于允许模型引用它从未见过的文本。新增 citable_refs(request, language) 作为唯一来源：可引用集 = 展示给模型的 span 切片 ∪ 展示的来源卡 ref，payload 与校验共用同一函数；上限常量 MAX_WRITER_EVIDENCE_SPANS=40。方向是收紧（只减少可引用面），不改人工门与导出门。(3) 该守卫此前**没有任何行为测试**（只有一条静态源码断言），这也是误杀能活到今天的直接原因；新增 tests/test_paper_writer_guard.py 4 项覆盖三个方向：带引用被接受、编造数字被拒、未展示 span 被拒、可引用集等于展示集。实测：同一命令重跑后 section writer produced 5 section(s)，results/method 仍为确定性章节。契约变化：可引用集定义改变。
- 2026-10-28 · v0.4.0 · status=pilot · PaperRequest 新增可选 synthesis 输入：相关工作章节在确定性草稿中追加跨来源主题块（仅引用当前 run 已有 span id，不新增数字/引用来源）；无 synthesis 或主题为空时输出不变
- 2026-10-27 · v0.3.2 · status=pilot · 新增 software_journal/computer_journal WritingProfile；writer payload 携带外部 Skill 投影的 journal_style brief，模型写非结果章节时遵循目标期刊规范；仍不写结果数字、不签核。
- 2026-10-26 · v0.3.1 · status=pilot · 中文摘要改为目的/方法/结果/结论结构；writer prompt 增加中文摘要结构、反套话与段落引用要求；投稿级格式与审计交给 manuscript 模块，不改变本模块的证据契约。
- 2026-10-25 · v0.3.0 · status=pilot · 契约扩展：PaperRequest 接收 claim_assertions；结果段在人签 claim 下渲染已验证的 metric/comparator/value/observed，仍不自行重算 EA。
- 2026-10-25 · v0.2.0 · status=pilot · 契约升级：论文模块新增证据约束的 DraftSection 正文草稿与 writer_mode；结果/方法承诺仍由确定性代码控制，模型只能写非结果章节且引用/数字需通过校验；新增 paper.md 渲染。
- 2026-10-24 · v0.1.5 · status=pilot · 最小改进：支持 bibliography_refs；citation.related 标 bound_bibliography（DataCite 元数据快照，非同行评审）
- 2026-10-24 · v0.1.4 · status=pilot · 最小改进：支持 protocol_refs；method.protocol 标 bound_protocol、limitation 标 bound_scope；writer 不复核 ProtocolCard
- 2026-10-24 · v0.1.3 · status=pilot · 修正 invariant：result.figure 可由数据图 manifest 绑定，示意图仍不能冒充结果图
- 2026-10-24 · v0.1.2 · status=pilot · 最小改进：支持 result_figure_refs；有数据图 manifest 时 result.figure 标 bound_figure，writer 不复核数据
- 2026-10-24 · v0.1.1 · status=pilot · 最小改进：支持传入人签 claim_refs；仅有 claim 时 result.primary 标为 bound_claim，不写数字，writer 不复核 EA
- 2026-10-23 · v0.1.0 · 初始 PaperContract 与语言/venue 路由；结果槽 pending。

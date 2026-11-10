---
id: manuscript
name: 中文投稿工作稿与审计
stage: S8–S12
version: 0.9.4
status: pilot
owner: research-agent
inputs:
  - PaperContract
  - LiteratureResult
  - BibliographyCard
  - ClaimRecord
outputs:
  - Manuscript
  - ManuscriptAudit
  - ArgumentLedger
  - ClaimRegistry
tools:
  - manuscript.assemble
  - manuscript.audit
  - manuscript.claim_registry
gates: []
invariants:
  - 不创造证据、数字、Claim 或实验结果；只重排与校验已有内容
  - 引用编号必须映射到来源元数据；无法映射时保留 `[待补文献:token]` 并阻断
  - 参考文献使用 GB/T 7714 风格草稿；缺字段不臆造
  - 每个候选 claim 必须记录 claim×ref×anchor 的 evidence row；span anchor 必须带 quote 与 SHA-256
  - 语言候选检测只做词法覆盖；semantic completeness 必须标为 unknown
  - submission_ready 只有在 structure/reference/citation/numeric/claim/fixture 等硬检查全部通过，且 context 明确提供已签 claim 与真实 run/experiment 上下文时才为 true；否则最多为 attention，不得冒充可投稿
  - context 的 claim_signed/run_summary 由调用方提供；本模块只做一致性与边界检查，不自行验证签名
  - 审计不是同行评审，不保证期刊录用
---

# 中文投稿工作稿与审计（S8–S12）

## Purpose

把内部 `paper.md`（证据工作稿）整理成更接近中文期刊投稿形式的工作稿：结构化摘要、关键词、编号引用、GB/T 7714 风格参考文献、论证台账和确定性审计。它不生成新的科学内容，也不替代真实实验、人工写作或同行评审。

## Contract

输入：

- `PaperContract`：title、profile、draft、slots、claims、fixture_mode；
- `LiteratureResult`：hits / spans / brief，用于来源与 span 映射；
- 可选 `BibliographyCard.entries`：已验证的 DOI/作者/年份等元数据；
- 可选上下文：claim statements/assertions、design、run summary、figure refs。

输出：

- `manuscript.json`：title、language、venue、abstract、keywords、sections、numbered references、citation map、unresolved citations；
- `manuscript.md`：标题、摘要、关键词、章节、参考文献；
- `manuscript-audit.json`：status（pass/attention/blocked）、submission_ready、blockers、warnings、checks；
- `argument-ledger.json`：按句记录 section / sentence / refs / numbers / supported / needs_evidence；
- `claim-registry.json`：每个候选 claim 的 claim_id、sentence SHA-256、candidate_kinds、claim×ref×anchor evidence rows、coverage report；`semantic_completeness=unknown`。

关键检查：

- 标题不得保留“工作稿：”前缀；从主题派生的标题只警告，要求人工润色；
- 必需章节（摘要/引言/相关工作/方法/实验设计/结果/讨论/结论）；
- 中文摘要结构（目的/方法/结果/结论）与长度（zh_core_journal 目标 200–600 字）；
- 关键词 3–5（中文）/ 3–6（英文）；
- 参考文献存在、已核验、无孤立条目；zh_core_journal 目标 ≥8 条；
- 显式引用全部可解析；无未解析 `[待补文献:...]`；
- 结果段数字必须来自 span / claim / design / run summary；
- claim registry 覆盖：引用句/定量句/结果句必须有已解析证据；source-level 引用无精确锚点只警告，未登记定量/结果/范围声明阻断；语义完整性始终标为 unknown；
- 无 TODO/待补/DATA_NEEDED；
- fixture 不可提交；
- `result.primary` 未绑定人签 claim 时阻断；
- context 未提供 `claim_signed=true` 或真实 `run_summary.run_id` 时，`submission.claim_signed` / `submission.run_context` 只警告，`submission_ready=false`；
- 过度声明与中文套话只警告；
- 图表未在正文引用时警告。

## Current Implementation

- `research_agent/manuscript.py`：citation conversion、GB/T 7714-style formatter、argument ledger、audit；
- `research_agent/pipeline.py`：在 paper 阶段后构建 manuscript bundle，并把五个文件写入 artifacts；
- `claim-registry.json` 与 `argument-ledger.json` 都由 `manuscript.py` 生成；span anchor 的 quote/SHA-256 直接来自 LiteratureResult.spans；
- `write_pipeline_artifacts` 输出 `manuscript.json` / `manuscript.md` / `manuscript-audit.json` / `argument-ledger.json`；
- report 增加“中文投稿工作稿”一节，显示审计状态与 blockers；
- `demo.json` 增加 `manuscript_uri` 与 `manuscript_audit_uri`；
- 确定性摘要使用目的/方法/结果/结论结构；模型 writer 的 system prompt 增加中文摘要结构与反套话规则。

## Boundaries

- 不是期刊模板引擎；不保证字号、行距、图表排版、作者信息、基金格式；
- GB/T 7714 只覆盖常见期刊/电子资源的基础字段；缺卷期页码不臆造；
- 引用映射依赖来源元数据或 bibliography；未核验来源会阻断；
- 审计是结构性/证据性检查，不是同行评审，也不能证明论文“质量不错”；
- 没有真实实验、全文和已签 claim 时，`submission_ready` 必须为 false；结构通过不等于可投稿。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `research_agent/manuscript.py`，补 `tests/test_manuscript.py`；
4. 跑 `python -m unittest discover -s tests -v`，并检查一次真实 pipeline 的 `manuscript-audit.json`。

## Changelog

- 2026-11-02 · v0.9.4 · status=pilot · v0.9.4 renders the keyword label separator in the paper's own language: an English-language draft now reads **Keywords:** while the Chinese draft keeps **关键词：**. The colon was the one constant left in a statement that already switched its label and its list separator by language, so English drafts carried full-width CJK punctuation. The first cut of this change dropped the closing bold markers and every generated draft lost its bold on that line; the manuscript test caught it, which is the same lesson as the session's other print-the-real-output rules. Detection lists were deliberately left alone: DESIGN_STATEMENT_MARKERS keeps both ASCII and full-width variants on purpose, because a Chinese-only list once let an English boundary sentence pass as an unsupported claim.
- 2026-11-01 · v0.9.3 · status=pilot · Provenance adds the third sourcing outcome: a draft decimal rendered with MORE decimals than the artifact stores is reported in decimals_over_precision with a warning, because the paper then implies precision the evidence does not carry. Found on the metric-validity draft: the breast_cancer AUC interval lower bound is written as -0.033070 while study-design-metric-validity.json stores -0.03307. Sign is strict and matches inside the draft folder are rejected, so rounding never becomes self-citation.
- 2026-11-01 · v0.9.2 · status=pilot · Provenance adds a rounding tier: a draft value whose literal differs from the artifact by rendering precision is reported as decimals_rounded_match with both forms, the source file and the digit counts, provided the match lies outside the draft own folder. Without it, -0.033070 in the metric-validity draft was flagged as existing only inside the paper folder, when study-design-metric-validity.json actually stores -0.03307 at five decimals. Sign is kept strict, self-copies are rejected as matches, and the warning still says the rendering precision is a human call.
- 2026-11-01 · v0.9.1 · status=pilot · Two honesty fixes in the number checks. numeric.fidelity no longer says unsupported numbers: the allowed set comes from signed claim statements and assertions plus span and design fields, so an unsigned claim rejects every result number, and the old wording read like a fabrication accusation when the block is policy. The detail now states that and points at manuscript provenance for the sourcing question. Provenance now excludes the draft file itself from the corpus and reports decimals whose only hits are inside the draft own directory as decimals_only_in_draft_folder with a warning, because an audit card echoing the draft is not a source. Re-scoring the metric-validity draft showed 31 of 32 decimals have a source outside the paper folder and one (-0.033070) exists only inside it.
- 2026-11-01 · v0.9.0 · status=pilot · New read-only subcommand manuscript provenance: it traces every decimal in a draft to a byte-identical value in an on-disk artifact corpus and deliberately certifies no integer count by string presence, because small integers match by accident and only re-running the recorded command establishes a count. The scanned file budget is part of the reported denominator. Motivated by auditing the metric-validity draft, where 32 of 32 decimals traced but an earlier hand-written check had reported 17 unsourced values purely because its token regex split six-decimal numbers.
- 2026-10-31 · v0.8.1 · status=pilot · 全流程实跑发现 manuscript-audit.json 走 manuscript.py 的 _audit，不经过 writing_audit，因此新的中文期刊检查没有进入 pipeline 产物。现在 _audit 对 zh_core_journal/software_journal/computer_journal 附加 venue_audit（nested advisory，不改变整体 status/submission_ready），新增 1 项测试；workspace 导出待重跑。
- 2026-10-31 · v0.7.3 · status=pilot · 生成稿关键词把英文疑问词与功能动词当成关键词：主题 How do self-improving coding agents use archives? 渲染出 Keywords: How, self-improving, coding, agents, use，出现在真实稿的摘要下方。KEYWORD_STOP 只有中文停用词和 study/review/research 等少量英文词，没有 how/use/does/the 等。现在补齐英文疑问词、助动词、介词与常见功能动词；关键词仍只从主题/标题抽取，不引入来源标题或新事实。实测该主题得到 self-improving, coding, agents, archives 四个内容词；新增回归测试。升 patch。
- 2026-10-30 · v0.7.2 · status=pilot · 生成稿能通过严格写作审计的两处硬伤：摘要原先渲染成粗体段“**摘要：**”，strict writing audit 按 section heading 找摘要，导致每份生成稿都报 structure.abstract；现在渲染为二级标题。另把 claim 断言里的 value/observed/tolerance 连同 4/6 位小数形式加入 allowed numbers，否则论文自己渲染的 observed=0.955556 会被 numeric.fidelity 判成未支持数字。实测 runtime_data/qoder-effect-v4：重渲染后 strict audit 只剩 fixture 一个 blocker（fixture sources cannot be submitted），structure.abstract 与 results.numbers_traceable 均通过。tests.test_manuscript 16 项 OK（新增一项四舍五入值放行）。升 patch。
- 2026-10-30 · v0.7.1 · status=pilot · 0.7.1（2026-10-30）：参考文献核验不再被变音符号绊倒。实测同一条真实语料 pipeline 挂 --bibliography-file（已验证卡片，4 条）后仍剩 1 条未验证：卡片写 "Darwin Godel Machine"，语料写 "Darwin Gödel Machine"，而 _norm_title 是把非 [0-9a-z\u4e00-\u9fff] 字符直接删掉——ö 被删除而不是折叠成 o，于是 "godel" 与 "gdel" 成为两个不同的键。改为 NFKD 规范化后再剔除组合记号，标题只差变音符号时仍算同一篇。效果：同一配置下预审 blocker 从 2 项降到 **1 项**，四条参考文献全部 verified=True，只剩 results.signed_claim（人签）。tests.test_manuscript 15 项 OK（新增 ReferenceTitleMatchTest 两项：变音符号折叠、变体标题仍能对上卡片并带回作者与年份）。契约未变，升 patch。
- 2026-10-30 · v0.7.0 · status=pilot · 0.7.0（2026-10-30）：claim 登记器两处精确性修正，都由实跑照出。(1) 元语句标记表只有中文（证据边界/人工门/待补…），而确定性模板是中英双语，于是同一句话的中文版被跳过后英文版仍被当作"无证据的主张"——实测同一条真实语料 pipeline 因这一条多出两个 blocker（claims.evidence_ledger、claims.registry_coverage）。补上英文对应词后，同一命令的 blockers 从 4 项降到 2 项（references.verified、results.signed_claim），候选数 11→9、supported 9/9、needs_evidence 0。(2) 假设与设计字段（Hypothesis (draft): / 研究假设（草案）：/ baseline: / primary metric: / seeds: 等）不再被当作需要引用的主张——假设是研究要检验的对象，不是无依据的断言；新增 DESIGN_STATEMENT_MARKERS 在句子级跳过。另外修掉一处"空集制造的绿色"：候选数为 0 时 coverage_rate 原本返回 1.0，现在返回 null 并给 coverage_note 说明"未定义"（前端已有 ?? "unknown" 兜底）。tests.test_manuscript 13 项 OK（新增 ClaimRegistryMarkerTest 三项：中英元语句都被跳过、假设不算主张、空候选集报未定义）。契约变化：coverage_rate 可为 null。
- 2026-10-28 · v0.1.3 · status=pilot · submission_ready 不再等同于结构审计通过：新增 `submission.claim_signed` 与 `submission.run_context` 检查；缺少已签 claim 或真实 run/experiment 上下文时降为 attention，submission_ready=false；管线从 claim 文件的 human_reason 传入 claim_signed。
- 2026-10-26 · v0.1.2 · status=pilot · 新增 claim registry：claim×ref×anchor evidence rows、quote/SHA-256、词法候选覆盖率和 semantic_completeness=unknown；source-level 引用无精确锚点只警告，未登记定量/结果/范围声明阻断。
- 2026-10-26 · v0.1.1 · status=pilot · 阈值细化：中文核心期刊摘要目标 200–600 字、关键词 3–5、参考文献目标 ≥8；仍只警告不阻断，硬阻断保持引用/claim/fixture/numeric/placeholder。
- 2026-10-26 · v0.1.0 · status=pilot · 首个中文投稿工作稿层：结构化摘要、关键词、编号引用、GB/T 7714 风格参考文献、论证台账与确定性 submission readiness 审计；fixture/缺 claim/未核验引用会阻断。

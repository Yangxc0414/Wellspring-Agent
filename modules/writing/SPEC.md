---
id: writing
name: 写作包与手稿预审
stage: S8–S12
version: 0.9.0
status: draft
owner: research-agent
inputs:
  - ResearchRun
  - LiteratureLedger
  - LiteratureSpans
  - ExperimentDesign
  - RunCapsule
  - ClaimStatus
  - ManuscriptDraft
  - ExperimentEvidence
  - ExperimentClaim
outputs:
  - WritingPack
  - ReferenceCards
  - EvidenceMap
  - WritingContract
  - WritingAudit
  - ManuscriptDraft
  - ManuscriptReview
  - SupportLedger
  - SupportPanel
  - SupportAdjudication
  - SupportGold
  - SupportGoldAnnotations
  - SupportGoldTemplate
  - ClaimPlan
  - SupportSectionSummary
  - ManuscriptSectionEdit
  - JournalStyleAudit
  - PackBinding
  - EmpiricalPaperLoop
tools:
  - writing.pack
  - writing.audit
  - writing.external-lint
  - writing.external-claim-audit
  - writing.external-consistency
  - writing.draft
  - writing.review
  - writing.support-panel
  - writing.support-gold
  - writing.support-gold-template
  - writing.support-items
  - writing.support-verdicts
  - writing.section-edit
  - empirical.check
  - empirical.paper
gates:
  - S5b
  - G5
invariants:
  - WritingPack 是单个 run 的只读投影；不创建 Claim、EA、Gate、Signature 或 Closure
  - 只允许引用 pack 中登记的 reference_id；不得编造标题、作者、DOI 或 URL
  - claim 未签核时 allowed_result_numbers 必须为空；结果段出现数值即阻断
  - 实验包写作必须计算 `experiment-evidence.json` 的 SHA-256，并要求签名 claim 的 `evidence_sha256` 一致、evidence.status=verified、human_reason 非空；任一不满足则 claim 不得标 signed，写作包必须警告
  - support 审计必须在模型 judge 前做确定性数值预检：句中的小数/百分比必须出现在引用 span 或已签 claim 的 allowed numbers 中，否则该项直接 `insufficient`，method=`deterministic_evidence_precheck`；不能把“数字有引用”当成证据
  - 实验包 EA 描述必须携带真实 evidence 路径、SHA-256、scope、claim 绑定状态；不得再返回空对象冒充 EA
  - 已签核时结果数值只能来自 claim assertions 或 RunCapsule mean/std
  - 来源为 fixture 时不得声称可投稿；preprint/peer_reviewed=unknown 必须显式警告
  - 摘要-only 来源只能作为线索，不生成 span，也不能当全文证据
  - 审计只检查引用键、结果数值、章节结构、占位符与来源边界；不做语义蕴含判断，也不替代同行评审
  - submission_ready 始终为 false；最多输出 ready_for_human_review
  - 模型初稿只能使用 pack 中 REF；审计阻断时必须修复一次，仍阻断则返回 blocked，不把初稿当完成
  - `--offline-draft` 只用于无 key 测试：仅使用 pack refs 与 signed claim allowed numbers 生成确定性工作稿，标记 `writer_mode=deterministic_offline_test_only`；仍走同一引用/数值/结构审计与 closure 预检，不得声称模型质量或可投稿
  - 模型修订只有在确定性审计不变差、引用/数值/长度检查通过时才接受；否则保留上一版并记录拒绝原因
  - MCP 只写 `<project>/runs/<RUN-ID>/writing-pack.json|md` 与 `writing-audit.json`；draft 必须位于项目内
  - support panel 只接受与当前 pack_id/pack_sha256 绑定的草稿；未绑定直接失败，不做“先审后补”
  - support panel 的每个 judge profile 是独立调用，但 profile id/family 由调用方提供，不能证明 provider/model 真正独立
  - `--require-families` / `require_families` 必须要求每个 judge 声明 family 且至少两个不同 family；记录 judge_families/independence，但仍是声明值，不是密码学证明
  - `--require-providers` / `require_providers` 必须要求每个 judge 有 provider id 且至少两个不同 provider；记录 judge_providers/judge_models/independence=distinct_providers，但 provider 配置仍不等于输出独立、语义独立或人工金标准
  - 句级分歧必须进入 needs_human；strict 下未裁决的分歧阻断；contradicted 或未解析引用始终阻断
  - 人工裁决必须给出 status 与 human_reason；面板不自动裁决、不把多数票冒充人工确认
  - pairwise kappa 只覆盖被审计子集，不是 human gold，也不是语义蕴含证明
  - support panel 不创建 Claim/EA/gate/signature，不改变稿件，不授权投稿
  - 若 run 目录存在 support-panel.json，writing audit 必须返回其 status/pending_human/fingerprint；panel 未 ready 或与当前稿 draft_sha256 不一致时，审计 blocked，不能给旧 panel 背书
  - support ledger 必须报告 item_limit/total_cited_sentences/audited_cited_sentences/truncated；达到上限时不能静默假装全审
  - audit 必须检测未带引用的第三方式事实句（研究表明/已有研究/文献报告/studies show 等）；默认 warning，strict_support 下 blocker
  - 未引用事实检测排除“本文/我们/本研究/本实验”等自指句，避免把作者自己的实验或立场误判为外部事实
  - 该检测只是词法线索，不能判断句子真假；它不能替代支持账本、语义判断或同行评审
  - audit 必须报告 multi_ref_sentence_count/samples：同一句含多个 REF 时给出 warning，提示拆成单 REF 句
  - writer prompt 要求每句最多一个 REF；support-patch 拒绝含多个 REF 的改写句，防止把多来源支持拼成综述性断言
  - 写作包必须生成 claim_plan：每个 claim 绑定一个 ref_id 与一个 span_id，并携带该 span 的 quote；无 span 的 REF 进入 unusable_refs
  - claim_plan 是写作辅助，不是 Claim/EA/证据或语义蕴含证明；writer 只能从 claim_plan 选择主张，每句对应一个 claim/REF
  - support judge 必须按批调用（默认每批 8 句，最多 20），避免长稿一次 payload 导致输出截断/非 JSON；每批校验后再合并
  - 项目内部 ID（TH/CP/SUP/CLM/EXP/PROT/BIB/SPAN 等）不得被当作结果数字；结果数值检查必须先剥离这些标识符
  - Qoder-native 支持评审必须先返回只读 items，再由 Qoder 提供 verdict；verdict 必须覆盖所有 judgeable item（strict 默认 true），id/status/evidence_refs 必须来自当前 pack
  - Qoder verdict 复用只允许同一 `judge_model` 且 sentence+evidence 内容键完全一致；变更句必须重新判定；复用项在 ledger 标记 `reused=true`，并记录 `provided_count`/`reused_count`/`reuse_source`
  - Qoder verdict ledger 标记 `judge_model=qoder:<id>`、`verdict_source=qoder`；它是 Qoder 自评审记录，不是外部独立评审或 human gold
  - support verdict 写新 ledger 前，若新稿 draft hash 与旧 ledger 不同，旧 ledger 必须归档到 `<run>/support-ledger-history/support-ledger-<旧sha前16>.json`；归档只证明存在性与身份，不是正确性证明
  - human gold 可直接从 Qoder support-ledger 构造 panel-like wrapper（`final_status=status`），用 `--ledger` 生成空白模板或与人工多数标签比较；Qoder ledger 是单 judge 自评审，不是 panel 或 human gold
  - writing audit 必须读取同 run、同 draft hash 的已有 support-ledger；strict 下 blocked ledger 阻断，partial 只 warning
  - support ledger 必须包含 section_summary：按 section 汇总 counts 与 weak_items，并按 weak 数量降序给出 weak_sections；它只用于定位优先修订章节，不是事实判断
  - Qoder section edit 支持 `##` 与 `###` 标题；只替换一个匹配章节；其他章节与 pack marker 原样保留；不得新增 REF/数字，不得覆盖源稿；expected_section_sha256 不匹配即拒绝
  - section edit 不调用模型、不创建 Claim/EA/gate/signature；修改后必须重新走 support-items/verdicts/audit
  - 已有草稿只能通过 bind 附加当前 pack marker，正文不得改变；已绑定/不同 pack/output=source/无可用 REF 必须拒绝；unresolved REF 返回但不得当证据；MCP `research_manuscript_bind` 与 CLI `writing bind` 共用 `bind_text_to_pack`
  - 含 `[REF-xx]` 的句子不得被长度阈值静默丢弃；低于 8 字的 cited 句子计入 `skipped_short_cited` 并告警，不生成 support item
  - 外部期刊 Skill 只以 MIT 许可的写作规范投影接入：software_journal/computer_journal profile 记录 skill/pack/license/copyright；不是官方模板
  - `writing external-lint` 只执行调用方指定的外部白名单 `scientific-writing/scripts/lint_manuscript.py`，使用当前解释器、只读、不安装依赖、不改稿；外部 issues 不是本仓库证据或签名
  - `empirical paper --external-lint` 把外部 lint 结果写入 final audit；外部 error/unavailable 使 loop 进入 needs_more_work，capsule S8 必须反映该 blocked 状态
  - `writing external-claim-audit` 只从本地 claim-registry 的 verified_anchor evidence rows 生成临时 claim CSV/source manifest，再运行外部 audit_claims.py；无 evidence 或未验证 anchor 必须被外部拒绝；临时包不改变本地 claim/closure
  - `writing external-consistency` 只执行调用方指定的外部白名单 `scientific-writing/scripts/check_consistency.py`，读取项目内 JSON registry（数值事实/方法/结果映射），使用当前解释器、只读、不安装依赖；外部 error 阻断，warning 为 attention；registry 与外部 issues 都不是本仓库证据、Claim 或签名
  - journal_style audit 检查摘要四要素、关键词、中图分类号、英文摘要、GB/T 7714 类型标记、图表题注、威胁有效性与引言弧线；结果作为 warning/journal_style，不替代同行评审
  - writer prompt 必须注入目标期刊规范 brief；venue 不得被来源 venue 覆盖
  - 非 strict 下截断把 ready 降为 partial 并给出 warning；strict 下截断直接 blocked；默认上限 80，可显式提高到 200
  - human gold 至少需要两个独立 annotator，item id 集合必须一致，status 必须在支持状态集内；缺失/重复/非法标签直接失败
  - human gold 只计算双人 observed agreement 与 pairwise Cohen's kappa，以及 panel 与 gold majority 的 accuracy/confusion；kappa 是标注一致性，不是事实正确性
  - human gold 是参照集，不是 closure gate；gold draft_sha256 与当前稿不一致时 writing audit 只警告，不阻断
  - panel 与 gold 只有在双方 draft_sha256 一致时才能对照；不一致直接拒绝，不能用旧 panel 对 new gold
  - panel 也必须传播 judge ledger 的截断：truncated 时非 strict 至少 partial，strict 直接 blocked；不能只审前 N 句就报 ready
  - human gold 不创建 Claim/EA/gate/signature，不授权投稿；submission_ready 始终 false
  - gold 模板只包含句子/refs/evidence 与空 status/note；必须省略 panel verdict/rationale，避免把模型判断锚定给标注者
  - 模板不是 gold；空白 status 必须被 support-gold 拒绝，直到标注者独立填写
  - empirical loop 必须验证 experiment.run_id 与 run 相同、evidence=verified、claim 已人签；缺一项即 blocked
  - empirical loop 只草拟/评审/复审 closure，不执行实验、不签 claim、不签 closure、不投稿；最终仍停在 ready_for_human_review
  - 写作包只在 figure manifest 校验 clean 且 `kind=data_result_plot` 时携带结果图；AstraDraw 示意图不得冒充结果图；实证稿必须引用图 1，引用无 manifest 的图号或未引用已验证结果图都会阻断
  - 写作契约的 length_target 是提示词与审计的唯一长度来源；低于目标必须报告（strict 时阻断）
  - 可用 REF 少于 5 时多样性检查记为 not_assessable，不得静默跳过
---

# 写作包与手稿预审（S8–S12）

## Purpose

把一次研究运行压缩成 Qoder/Claude Code 等外部写作 Agent 可直接使用的小型证据包，并在成稿后做确定性预审。写作包负责“能写什么、引用什么、数字能不能用”；预审负责“有没有越权引用、越权报数、缺章节或占位符”。它不替作者写作，也不替人签核。

## Contract

输入：

- `WritingPackRequest`：`project_dir`、`run_id`、`language`（zh/en）、`venue`（zh_core_journal/software_journal/computer_journal/en_conference）、`max_sources`、`max_spans_per_source`；
- 运行产物：`literature-ledger.json`、`literature.json`、`idea.json`、`experiment.json`、`run/run-capsule.json`、`run/ea.json`、`run/metrics.json`、`run/claim-draft.json`、可选 `claim/claim.json`；
- `ManuscriptDraft`：`.md` / `.txt` / `.tex` / `.docx`，位于项目目录内；
- `SupportPanelRequest`：`.md` / `.txt` / `.tex` 草稿，必须带匹配当前 pack 的 marker；DOCX 暂不做 marker 绑定，因此不进入 panel。

输出：

- `<run>/writing-pack.json`：任务与停止点、来源卡（标题/作者/年份/arXiv id/URL/abstract/license/full_text/peer_reviewed）、选中 span、来源简报、idea、实验设计、run capsule/EA、claim 状态、写作契约、warnings、token 估算；
- `<run>/writing-pack.md`：一页人类可读摘要；
- `<run>/writing-audit.json`：`status=ready_for_human_review|blocked`、`submission_ready=false`、引用计数、章节检查（含 `structure.merged_headings`）、结果数值检查、占位符、fixture 检查、blockers/warnings、draft SHA-256；中文期刊 profile 下另含 `venue_audit`（advisory，venue 的 blockers 只并入 warnings，不改变整体 status）；若存在 support-panel，还包含其 status/pending_human/fingerprint/draft_matches，未裁决或 stale panel 阻断；
- `<run>/support-panel.json`：多 judge 的逐句 verdicts、多数结果、分歧项、pending_human、pairwise observed agreement/kappa、panel_fingerprint 与 `status=ready|partial|needs_human|blocked|not_applicable`；`<run>/support-adjudication-template.json` 为分歧项的人工裁决模板；
- `<run>/support-gold.json|md`：双人（或多人）标注的逐句 labels、majority、observed agreement、pairwise Cohen's kappa、annotator 列表，以及可选 panel-vs-gold accuracy/confusion/disagreements；`status=complete|incomplete`；
- `<run>/support-gold-annotations-<annotator>.json` + `support-gold-template.json|md`：由 panel 生成的空白标注模板，含句子/refs/evidence 与空 status/note；不包含 panel 的 verdict/rationale，避免锚定；
- `claim_plan`：写作包内每个候选主张绑定一个 `ref_id`/`span_id`/`quote`，并列出无可用 span 的 `unusable_refs`；writer 优先从中取句，每句一个 REF。
- 评审环进展谓词（v0.9.0，借鉴 CCFA continuity）：`review_progress(prev, cur)` 纯函数显式定义「什么不算进展」——同一非空 `must_fix` 集合被重新打分（即使 overall 微涨）判 `no_progress_same_concerns` 并停止；no-op 修订（候选文本与现稿相同）拒收 `no_op_revision`。谓词置于阈值/分数单调检查之后，不改变过阈值即停的既有行为。`manuscript-review.json` 增 `stop_reason`（`threshold_reached/score_plateau/no_progress_same_concerns/rounds_exhausted/revision_rejected/support_no_candidate`），review 迭代增 `progress` 字段；停止原因只读披露，不创建 Claim/EA/gate。

写作契约：

- `article_type`：存在 RunCapsule 时为 `reproduction`，否则为 `review`；
- `citation_style`：草稿使用 `[REF-01]`，导出时再映射为 GB/T 7714 数字引用；
- `allowed_result_numbers`：未签核为空；已签核时来自 claim assertions、capsule mean/std 与 verified per-method mean/std；
- `allowed_design_numbers`：已签核实证稿可提及的已验证设计常量（seeds/test split/rows）；结果数字按容差匹配，设计常量必须精确匹配，防止用 0.9999 冒充设计常量 1；
- 实证稿除了“结果”节，还会检查摘要/讨论/结论中的小数与百分比，防止把编造数值放在非结果章节绕过审计；已签核但结果节没有任何数字时记 warning，不伪装成实证结果；
- `rules`：只引用已登记来源；未签核不报结果数字；文献主张指向 span 或来源卡；不得使用 fixture；不得留下 TODO/待补。
- 章节检查按标题子串匹配，**一个标题可同时满足多个必需章节**（如"实验与结果"同时满足 experiment 与 result）；合并章节是期刊/会议常见写法，因此**不阻断**，但面板不得把合并读成"9 个独立章节都存在"：`structure.merged_headings` 以 warning 级列出被同一标题满足的章节组，标题与章节一一对应时为 pass。


## Current Implementation

- `research_agent/support_audit.py`：pack-aware `audit_pack_support()` 把每个 `[REF-xx]` 句解析到 selected spans，输出 supported/partial/contradicted/insufficient 账本；模型 judge 前先做确定性数值预检（小数/百分比必须出现在引用 span 或 signed claim allowed numbers），失败直接 insufficient 并标 `deterministic_evidence_precheck`；无 judge 只做词法启发式；strict 需要模型
- `research_agent/support_panel.py`：同一绑定稿由多个 judge profile 独立审计，逐句记录 verdicts、多数结果、分歧与 pending_human；支持人工裁决文件（status + human_reason），输出 pairwise kappa 与 panel_fingerprint；strict 下未裁决分歧阻断
- `research_agent/support_gold.py`：读取多个 annotator JSON（至少两人、同一 item 集），计算 majority、observed agreement 与 pairwise Cohen's kappa；可选读取 support-panel 对照 gold majority，输出 accuracy/confusion/disagreements；`build_gold_templates()` 从 panel 生成不含 verdict/rationale 的空白双人模板；不是自动 judge，也不签核
- 写作包带 `pack_id`/`pack_sha256`，writer/review 自动附加 pack marker；`writing audit --semantic --strict-support --strict-pack-binding` 同时检查语义支持与稿-包绑定
- `research_agent/empirical_loop.py`：同一个 run 的 literature/synthesis/innovation-review + 本地实验 evidence + 人签 claim → 写作包 → 初稿 → 可选多轮评审 → 带手稿的 experiment closure；输出 `runs/<RUN>/empirical-paper-loop.json|md`，`submission_ready=false`，停在人工审阅/签名前；`check` 同时校验 experiment 的 hypothesis/methods/metric/seeds 与 idea_id 是否能回到 innovation 候选；启用 review 且分数低于阈值时，loop status 为 `needs_more_work`，不会报 `ready_for_human_review`，并把最新一轮 weaknesses/must_fix 写入 loop 报告；
- `manuscript_writer.py` 按 `article_type` 分支：review 写综述/立场，reproduction 写实证论文，只允许报告已签 claim/verified evidence 中的结果数字；写作包把 `experiment_design` 与 `experiment_package` 分开，已签核时把各方法 mean/std 纳入 `allowed_result_numbers`；
- `manuscript_review.py` 的评审/修订提示同样区分两类文章；修订若删除全部已报告结果数字则拒绝；
- `research_agent/manuscript_writer.py`：写作包+创新评审 → 中文综述/立场初稿 → 确定性审计 → 一次定向修复；
- `research_agent/manuscript_review.py`：5 维 rubric 评审（evidence/contribution/method/clarity/venue_fit）→ 修订 → 再评审；候选修订需通过引用/数值/章节审计且 blockers 不变差；输出 `manuscript-review.json`、`manuscript-review-iterations.jsonl`、`final.md`、`final-audit.json`；
- CLI `manuscript draft|review`；MCP `research_manuscript_draft|research_manuscript_review`；
- 评分是模型辅助的稿件预审，不是同行评审；不签 Claim、不声称 submission_ready。

- `research_agent/writing_pack.py`：`build_writing_pack()` / `render_writing_pack()`；PDF 句级 span 经过换行归一、代码/指令/玩具算术/致谢/图表题过滤与相关性排序；来源卡合并 arXiv 元数据、摘要、作者与 provenance；新增 `_build_claim_plan()`，将每个候选主张绑定到一个 ref/span/quote，并标记无 span 的 unusable_refs；实验包路径生成真实 `ea` 描述并校验 `claim.evidence_sha256 == sha256(experiment-evidence.json)`、evidence.status=verified、human_reason；不匹配的 claim 标 invalidated 并阻止结果数字；
- `research_agent/writing_audit.py`：`audit_manuscript()` / `write_audit()`；检查 `[REF-xx]`/数字引用、九个中文章节、结果数值策略、占位符、fixture 来源、预印本警告；
- MCP `research_writing_pack` / `research_manuscript_audit`；CLI 暂无独立命令，复用 MCP/HTTP/Python 契约；
- 2026-10-26 真实运行：4 篇 arXiv 全文、4 个来源卡、16 处引用、中文综述稿审计 `ready_for_human_review`（claim missing，review 类型）；
- 审计不判断句子是否真的支持结论；真正的语义审计仍由 `manuscript.py` 的 claim registry、`support_audit.py` 与人工审稿负责。

已知边界：不做参考文献格式的最终 GB/T 7714 排版；不做 DOI/Crossref 在线核验；不自动改写草稿；不判断领域新颖性。

## Boundaries

- 写作包不等于论文，不包含未经审计的结论；
- span 是证据锚点，不是语义蕴含证明；
- 审计通过只表示“没有发现结构性越权”，不表示可投稿或可发表；
- 不替用户签署 Claim、Protocol、Closure 或 export approval；
- 不联网；arXiv 元数据来自已下载的 `inputs/arxiv-sources.json`；
- 不把 fixture、模板图或示例数字写入正式稿。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 `version` + Changelog；
3. 改 `writing_pack.py` / `writing_audit.py` / `support_panel.py`，保持输出 schema 兼容；
4. 补 `tests/test_writing_pack.py`、`tests/test_writing_audit.py`、`tests/test_support_panel.py` 与 MCP 测试；
5. 跑全量测试与至少一个真实 run 的写作包/审计。

## Changelog

- 2026-11-11 · v0.9.0 · status=draft · 评审环进展谓词（借鉴 CCFA continuity，71-§4.2 设计输入 6）：review_progress 纯函数显式定义「什么不算进展」——同一 must_fix 集合被重新打分（即使分数微涨）= 空转，停止并记 stop_reason=no_progress_same_concerns；no-op 修订（文本不变）拒收 reason=no_op_revision。result 增 stop_reason（threshold_reached/score_plateau/no_progress_same_concerns/rounds_exhausted/revision_rejected/support_no_candidate），review 迭代增 progress 字段。谓词置于阈值/单调检查之后，现有过阈值多轮测试不受影响。tests/test_review_loops 增 3 项。
- 2026-11-02 · v0.8.2 · status=draft · 新增 script.punctuation 审计：按写作包声明的语言检查文字/标点脚本泄漏（en 稿出现全角标点或汉字即报警，zh 稿只检查夹在两个汉字之间的半角标点），两个方向都输出分母计数；语言缺失时记为 not_assessable 并写入 warnings，不再静默全绿。
- 2026-11-01 · v0.8.1 · status=draft · Reproduction map keeps the pack claim status verbatim (signed / draft_needs_human / missing) instead of collapsing it to unsigned: a projection must not be vaguer than the field it reports.
- 2026-11-01 · v0.8.0 · status=draft · Writing pack now carries a reproduction_map: the claim status, a re-run command rebuilt from the parameters the RunCapsule recorded, the dataset/code/protocol hashes and the named artifacts. The capsule stores no invocation, so the command is reconstructed rather than replayed, it is withheld when the dataset or seed list does not name a runnable surface, and the renderer states that nothing here re-ran the experiment. Adds the reviewer-facing claim-to-command-to-artifact table the reproducibility checklist asks for.
- 2026-10-31 · v0.7.0 · status=draft · 中文期刊/基金检查此前只是独立模块，没有进入写作审计链：writing audit 现在对 zh_core_journal/software_journal/computer_journal 从 DraftDocument + pack refs 适配稿件视图并调用 venue_audit；venue 的 blockers/warnings 只并入 warnings，不改变整体 status（advisory）。新增 manuscript_from_draft 与 2 项测试。契约新增输出字段，升 minor。
- 2026-10-31 · v0.6.3 · status=draft · 写作包的证据选择原先完全不看研究问题：_span_score 只看页码/章节/长度/正面措辞，导致 How do self-improving coding agents use archives? 这个 run 的语料里 49 条含 archive 的证据句一条都没进 top-3，选中的是泛泛引言句；Qoder 的 evidence 评审据此指出“给定证据没有出现 archive”。现在从 query_plan.question 提取词项（去停用词/常见动词、复数归一），按全部候选 span 计算词项文档频率；对稀有词项（df≤20%）为每篇来源保留证据覆盖位：优先选该词项下质量最高的 span，再按原质量分填满 top-k，并把 topic_hits 写入 pack 便于审计。实测该 run：REF-01/02/04 的 top-3 各含 1 条 archive 句，REF-03 语料没有 archive 句故不伪造覆盖。回归测试覆盖“主题句击败同分引言句”。原有质量门槛与同源去重不变。升 patch。
- 2026-10-31 · v0.6.2 · status=draft · 手稿评审也能走宿主模型：manuscript review 原先硬编码 DeepSeek（无 key 直接失败、余额不足 HTTPError），现在先解析 paper 阶段的 gateway binding（host-agent 免 key），没有才回退 DeepSeek；ModelTurnPending 被 CLI 捕获并打印 turn id，不再抛 traceback；同时把 demo.topic 注入 writing pack 的空 task.goal，避免提示词出现空的“研究目标:”。实测 qoder-design-turn：Qoder 评审 turn 返回 evidence 3 / contribution 4 / method 5 / clarity 5 / venue_fit 2，status needs_more_work；must_fix 指出 iris 结果与钙钛矿主题不一致、fixture 证据与长度不足。review 状态没有被改写成通过。tests 相关 21 项与全量后续复跑。升 patch。
- 2026-10-31 · v0.6.1 · status=draft · strict support 不再强制外部 judge：已有 same-draft 的 Qoder support-ledger 时，CLI 不解析 judge profile，audit 直接消费 ledger；strict 下 ledger 的 insufficient/unresolved 会作为 blocker（status=blocked + support_ledger 原因），不再抛 support judge call failed。实测 qoder-design-turn：Qoder ledger 为 partial（6 supported/2 partial/1 insufficient），--strict-support 返回 blocked 且 blocker 含 support_ledger；非 strict 只报 fixture。tests.test_writing_audit 32 项与 test_writing_pack 9 项 OK。修复异常路径，升 patch。
- 2026-10-31 · v0.6.0 · status=draft · 写作包与 Qoder 支持面板在中文/数字引用稿上真的可用：1) 之前用英文字符长度 60 过滤 span，所有短中文 fixture 句（含‘该数值仅用于测试流程’这类边界句）被静默丢弃；现在按有效长度（CJK 计双）>=36、CJK 句 >=16 字符选择，边界句进入证据。2) 生成稿用 [1][2] 数字引用，support 审计只认 [REF-xx]，导致 0 个 item；现在从草稿参考文献表按标题映射数字引用到 pack REF，bind 也接受数字引用。3) 实测 Qoder 对 9 条可判 item 给出 6 supported / 2 partial / 1 insufficient（摘要-only 政策句引用了不支持它的 REF-01），support 状态 partial，audit 在非 strict 下只报 fixture；这是真实的支持缺口，不是机器漏判。tests.test_writing_pack 9 项 OK。契约新增数字引用映射，升 minor。
- 2026-10-30 · v0.5.1 · status=draft · 写作包的 allowed_result_numbers 补齐断言口径：signed claim 的 value/observed/tolerance 同时登记原值与 4/6 位小数形式。严格 writing audit 之前只放行 observed 原始长浮点，导致论文渲染的 accuracy >= 0.9111 与 observed=0.955556 都被判为 untraceable；现在两者可追溯。实测 v4 稿的数字检查通过，只剩 fixture 边界。升 patch。
- 2026-10-30 · v0.5.0 · status=draft · 0.5.0（2026-10-30）：章节面板不再把合并标题读成独立章节（测量暴露的过度记分）。先把指标饱和审查做成数：对磁盘上 133 份 writing-audit.json 逐检查项统计状态分布，21 项里 **15 项在真实产物中从未出现非默认值**；其中 127/133 来自 fixture 模式运行（fixture 检查恒为 blocker 级 fail），真正跑过真实语料的审计只有 6 份——所以"面板全绿"首先是样本构成，不是质量证据。据此定位到一个真实缺陷：REQUIRED_SECTIONS 用标题子串匹配，一个标题可同时满足多个必需章节；实测 6 个标题的手稿（引言与相关工作 / 实验与结果 / 讨论与结论）报 **structure.* 9/9 pass、status=ready_for_human_review、blockers=[]**，即一篇没有独立引言、独立结果、独立结论的稿子拿到满屏绿。修法不改判定语义（合并章节是期刊/会议常见写法，阻断是错的）：新增 structure.merged_headings，severity=warning、永不进 blockers，detail 逐个列出被同一标题满足的章节组（"实验与结果" -> experiment+result）；标题与章节一一对应时为 pass。同时补上此前**没有失败分支测试**的那条路径（structure.* 的 fail 分支在 tests 里 0 引用；另有一条名为 "still needs sections" 的测试其实只断言了 claim.signed，已按实际断言改名）。实测：同一份合并标题稿新增项 fail+warning、其余不变；删除摘要后 structure.abstract=fail 且进 blockers。tests.test_writing_audit 22 项 OK（新增 2 项）。契约变化：审计输出新增一个 warning 级检查项；阻断集合与人工门未移动。
- 2026-10-29 · v0.4.0 · status=draft · 0.4.0（2026-10-29）：实测发现写作契约里"目标6000-8500汉字"只写在提示词常量里、审计完全不检查，4913 字的稿子直接 ready_for_human_review；多样性检查在 4 篇语料下静默"skipped"。现在 LENGTH_TARGETS 成为 writer 提示词与 audit 的共同来源，pack.writing_contract 新增 length_target，audit 输出 han_character_count 与 length.chinese_characters（默认告警级，contract 标 strict 时阻断）；sources.diversity 改为显式 not_assessable 并写进 warnings。契约变化：新增两项不变量与产物字段。
- 2026-10-29 · v0.3.50 · status=draft · 0.3.50（2026-10-29）：修复 results.numbers_without_claim 误报。SECTION_REF_RE 原要求数字必须带小数段，导致「第 3 节」这类整数章节交叉引用被当作未签署结果数字，把「本节不报告结果数字」的诚实段落整体阻断并触发一次完整重写。现补两类结构引用（前缀+整数+章节名词、§/section+编号），仍拦截真实量值（0.87、12%、15 例、30 个）；两个方向各有回归测试。
- 2026-10-28 · v0.3.49 · status=draft · `empirical paper` 增加 `--external-consistency-auto`：从 verified experiment-evidence 自动派生 schema-1.0 registry，再运行白名单 `check_consistency.py`；claim 未签时按 exploratory 投影；仍不创建/修改证据、claim、closure 或签名。

- 2026-10-28 · v0.3.48 · status=draft · `empirical paper` 增加可选的 `--external-consistency/--external-consistency-registry`：在写作审计后运行白名单 `check_consistency.py`；外部 error/unavailable 把 final audit 置 blocked、loop 置 needs_more_work；registry 与外部 issues 不是本仓库证据或签名。

- 2026-10-28 · v0.3.47 · status=draft · support panel 增加 provider 级独立性证据：`judge_providers`/`judge_models`/`require_providers`，CLI 从 model profile 推导 provider 并支持 `--require-providers`；panel 记录 distinct_providers 与声明边界；MCP 同步可选 `judge_providers`/`require_providers`；不声称输出独立或人工金标准。

- 2026-10-28 · v0.3.46 · status=draft · 新增 `writing external-consistency`：对项目内 JSON registry 运行白名单 `scientific-writing/check_consistency.py`，检查数值事实/方法/结果映射；只读、不装依赖、不改 registry；外部 error 阻断、warning 为 attention；新增 adapter 与真实外部脚本测试。

- 2026-10-28 · v0.3.45 · status=draft · 新增 `writing external-claim-audit`：把本地 claim-registry verified_anchor rows 映射为临时 source manifest/claim CSV，运行白名单 `scientific-writing/audit_claims.py`；无证据/未验证 anchor 由外部 Skill 拒绝；只读、不改本地 claim/closure；新增 adapter 与真实外部脚本测试。

- 2026-10-28 · v0.3.44 · status=draft · 外部 lint 接入 empirical loop：`--external-lint/--external-skill-root` 在写作审计后运行白名单 Skill；外部 error/unavailable 把 final audit 置 blocked、loop 置 needs_more_work，capsule S8 随之阻断；新增集成测试。

- 2026-10-28 · v0.3.43 · status=draft · 新增外部 Skill 可执行 gate：`writing external-lint` 运行白名单 `scientific-writing/lint_manuscript.py`（MIT，调用方 skill root），只读、不装依赖、不改稿；CLI 记录 external-writing-gate；外部 issues 仍非本仓库证据或签名；新增 adapter 测试。
- 2026-10-28 · v0.3.42 · status=draft · 新增显式 `--offline-draft` 测试模式：从 pack 的 REF/选中 span/claim allowed numbers 生成确定性实证工作稿，经过同一 audit→experiment closure 预检；writer_mode 明示 test-only，不替代模型写作或投稿判断；新增 offline full-loop 测试。

- 2026-10-28 · v0.3.41 · status=draft · support panel 增加声明的模型家族：`judge_families` + `require_families`；要求每个 judge 有 family 且至少两个不同 family，记录 judge_families/independence/pair families；CLI `--judge-family`/`--require-families` 与 MCP 同步；家族仍是调用方声明，不是 provider 证明。

- 2026-10-28 · v0.3.40 · status=draft · support 审计增加确定性数值预检：小数/百分比未出现在引用 span 或 signed claim allowed numbers 时直接 insufficient，避免模型 judge 把“有引用”误判为支持；ledger 增加 precheck_failed 与逐项 precheck_missing。

- 2026-10-28 · v0.3.39 · status=draft · 实验包写作不再返回空 EA：生成 experiment-evidence 的路径/SHA/scope/claim 绑定描述；claim 必须 status=supported、evidence.status=verified、human_reason 非空且 evidence_sha256 与当前文件一致，否则标 invalidated 并清空结果数字；新增 stale claim 测试。
- 2026-10-28 · v0.3.38 · status=draft · 抽出共享 `bind_text_to_pack`；MCP `research_manuscript_bind` 与 CLI `writing bind` 使用同一实现；CLI 新增 `writing bind --draft --output`，不改正文、不签核。
- 2026-10-28 · v0.3.37 · status=draft · 新增已有草稿 bind 契约（只附加 pack marker、正文不变、拒绝已绑定/无可用 REF）；support audit 对含 REF 的短句不再 20 字静默丢弃，<8 字计入 `skipped_short_cited` 并告警。
- 2026-10-28 · v0.3.36 · status=draft · human gold 支持从 Qoder support-ledger 构造 panel-like wrapper；`writing support-gold-template --ledger` 可生成空白 A/B 模板，`writing support-gold --ledger` 可比较人工多数标签与 Qoder 自评审；不签核。
- 2026-10-28 · v0.3.35 · status=draft · support-verdicts 写新稿 ledger 前自动归档旧稿 ledger 到 `support-ledger-history/support-ledger-<旧sha前16>.json`，返回 `archived_ledger`；归档是存在性/身份记录，不是正确性证明。
- 2026-10-28 · v0.3.34 · status=draft · Qoder-native support verdict 支持 `reuse=true`：按 sentence+evidence 内容键复用同一 judge id 的旧 verdict，只重判变更句；ledger 记录 `provided_count`/`reused_count`/`reuse_source` 与逐项 `reused`，不同 judge id 不复用。
- 2026-10-27 · v0.3.33 · status=draft · 期刊 Skill profile 改为数据化 `fixtures/journal_skill_profiles.json`，每项记录 source/license/SHA-256 与 brief；新增 `skill journal-verify` 校验外部源漂移。当前 8 个源文件验证 fresh。
- 2026-10-27 · v0.3.32 · status=draft · 接入 Awesome-Journal-Skills 的 JOS/CJC 写作规范投影：writer brief + journal_style audit（摘要/关键词/TP/GB7714/图表/威胁有效性/引言弧线），保留 MIT 来源；修复写作包 venue 被参考文献 venue 覆盖的 bug。
- 2026-10-27 · v0.3.31 · status=draft · section edit 扩展到 `###` 子章节；Qoder 用其重写“与现有工作的关系”，真实复审 supported 从 10 提升到 17、partial 从 18 降到 14。仍不是可投稿。
- 2026-10-27 · v0.3.30 · status=draft · 新增 Qoder section edit：把 Qoder 写的单一章节安全应用到绑定稿，保留其他章节/marker，拒绝新增 REF/数字与陈旧写；不调用模型、不签核。
- 2026-10-27 · v0.3.29 · status=draft · support ledger 增加 section_summary（按章节 counts/weak_items/weak_sections）；Qoder-native ledger 已用于定位最弱章节（引言 5/5、相关工作 4/4 等）。只用于优先修订，不是事实判断。
- 2026-10-27 · v0.3.28 · status=draft · 新增 Qoder-native 支持评审：`support-items` 只读返回句级项，`support-verdicts` 接收 Qoder verdict 并写 support-ledger（`judge_model=qoder:<id>`）；审计读取已有 ledger。不调用外部模型、不签核。
- 2026-10-27 · v0.3.27 · status=draft · support judge 分批调用（默认 8/批，最多 20），修复长 claim-plan 稿一次 payload 返回非 JSON；结果数值检查剥离 TH/CP/SUP/CLM/EXP/PROT/BIB/SPAN 等内部 ID。真实 DeepSeek 对照：原稿 0/12 supported，claim-plan 稿 4/18 supported、11 partial，审计 ready_for_human_review。
- 2026-10-27 · v0.3.26 · status=draft · 写作包新增 Claim plan：每个候选主张绑定一个 ref/span/quote，列出 unusable_refs；writer prompt 要求每句对应一个 claim/REF。用于回应真实 DeepSeek 闭环中 11/12 partial 的问题：先把主张限制到单一 span 能直接陈述的范围。
- 2026-10-27 · v0.3.25 · status=draft · 新增 multi_ref_sentence_count/samples 与 warning；writer prompt 要求每句最多一个 REF；support-patch 拒绝多 REF 改写句并放宽拆句长度。真实 DeepSeek 闭环显示原稿 11/12 partial，拆句修订仍未翻成 supported，说明证据 span 本身不足以支撑综述性合并。
- 2026-10-27 · v0.3.24 · status=draft · audit 新增未引用事实句检测：研究表明/已有研究/文献报告等无引用句默认 warning，strict_support 下 blocker；排除自指句。输出 uncited_factual_count/samples。修复“事实句不带引用即可绕过支持账本”的漏洞。
- 2026-10-27 · v0.3.23 · status=draft · support ledger 显式报告截断（item_limit/total/audited/truncated）；非 strict 将 ready 降为 partial，strict 阻断；默认上限 80、可到 200。panel 同步传播截断。修复“只审前 40 句却显示 ready”的假覆盖。
- 2026-10-27 · v0.3.22 · status=draft · 新增 `writing support-gold-template`：从 support-panel 生成双人空白标注模板，包含句子/refs/evidence，但刻意省略 panel verdict/rationale 以避免锚定；模板不是 gold，空白 status 不能通过 support-gold。
- 2026-10-27 · v0.3.21 · status=draft · 新增 `writing support-gold`：双人标注 JSON → majority/observed agreement/pairwise Cohen's kappa，可选与 support-panel 对照 accuracy/confusion/disagreements；writing audit 返回 `support_gold` 摘要，但 gold 不是 closure gate。解决“只有内部 curated 校准、没有人类 gold”的缺口。
- 2026-10-27 · v0.3.20 · status=draft · writing audit 读取同 run 的 support-panel：panel 未 ready 或 draft_sha256 与审计稿不一致时 blocked；审计结果新增 support_panel 摘要。这样 Qoder 的 audit 不再在存在未裁决分歧时显示 ready。
- 2026-10-27 · v0.3.19 · status=draft · 新增多评审支持面板 `writing support-panel`：同一绑定稿由多个 judge profile 独立审计，输出逐句分歧、pending_human、pairwise kappa 与人工裁决模板；strict 下未裁决分歧阻断；profile id 不等于 provider 独立性证明。
- 2026-10-27 · v0.3.18 · status=draft · same-run empirical paper loop 接入 A/B 接受门（`--ab-check`/`--ab-section`）；盲评偏好原文时拒绝该轮修订。
- 2026-10-27 · v0.3.17 · status=draft · `writing audit`/`manuscript review`/`empirical paper` 支持 `--judge-profile`，用独立 model profile 做支持判断；同 provider 默认仍记录在 report。
- 2026-10-27 · v0.3.16 · status=draft · support ledger 缓存支持按 draft hash 的 cache_dir；manuscript review 与 empirical paper 复用同一候选的 verdict，减少重复 judge 调用和结果漂移。
- 2026-10-27 · v0.3.15 · status=draft · 新增可选 A/B 接受门：候选修订在确定性/支持检查通过后，再做匿名 A/B；若盲评偏好原文则拒绝。不是同行评审，同 provider 时仍有限。
- 2026-10-27 · v0.3.14 · status=draft · 实验写作包携带 data_audit warnings；数据泄漏/重复/不平衡警告进入写作包，提醒作者不要过度外推。
- 2026-10-27 · v0.3.13 · status=draft · 实验写作包与 writer prompt 携带 `cv_folds`；实证稿必须写清 holdout 还是 k-fold CV。
- 2026-10-27 · v0.3.12 · status=draft · 写作包携带 verified results table（表 1）；实证 writer 在结果节引用表 1；审计对“有表不引用/引用无表”给 warning。
- 2026-10-27 · v0.3.11 · status=draft · 实验写作包携带 paired comparison（mean_diff/CI95/wins），已签核实证稿的 allowed_result_numbers 包含这些值；writer 只能报告 normal-approx CI，不得声称显著性。
- 2026-10-27 · v0.3.10 · status=draft · 新增 support judge 校准集与 `writing support-eval`：12 个 curated 句-证据用例，输出 accuracy/precision/recall/confusion；按校准结果修订 judge prompt（方向支持但全称/范围不支持判 partial，仅相反方向判 contradicted），并提升 cache version。
- 2026-10-27 · v0.3.9 · status=draft · 新增 support-patch 修订模式：按 partial/insufficient/contradicted 问题句返回 find/rewrite JSON，只替换问题句；参考文献列表从支持审计排除；support ledger 增加 draft+pack+judge+votes 缓存，保证同一稿重复审计可复现。
- 2026-10-27 · v0.3.8 · status=draft · 新增 section 修订模式：按审稿 section_actions 与支持失败定位目标章节，只替换章节正文并保留其余章节；接受前要求 supported 引用不显著下降，解决长稿 full rewrite 截断/丢章节问题。
- 2026-10-27 · v0.3.7 · status=draft · 支持账本增加 claim-mode（proposal/method 行 not_required）、1–5 票多数与票型记录；writer prompt 增加“引用-证据对照”，要求每个 REF 只支持其 span 能直接蕴含的句子。
- 2026-10-27 · v0.3.6 · status=draft · support-aware manuscript review：每轮把句级支持失败喂给 review/revision；strict 下拒绝引入 contradicted/unresolved/insufficient 的修订；结果节忽略 Markdown/章节编号（如 4.2/4.3）避免误判结果数字。
- 2026-10-27 · v0.3.5 · status=draft · 新增稿-包绑定与句级支持账本：pack_id/marker、审计优先加载持久化 pack、[REF-xx]→selected spans 的 tri-state 语义支持；partial 警告，contradicted/unresolved/insufficient 在 strict 下阻断；MCP audit 增加 semantic/strict_support/strict_pack_binding。
- 2026-10-27 · v0.3.4 · status=draft · 写作包携带可选 AstraDraw 方法示意图（图 2，schematic=true）；writer 在方法节引用图 2；审计阻断“示意图写进结果节”，未引用时只 warning。
- 2026-10-27 · v0.3.3 · status=draft · 写作包只接受 `kind=data_result_plot` 的结果图 manifest；AstraDraw 示意图不得冒充实证结果图。
- 2026-10-27 · v0.3.2 · status=draft · 结果图绑定：写作包携带 clean 的 figure manifest/图注/路径；实证 writer 按图注写作并引用图 1；审计校验 figure.bound/referenced；experiment closure 同步校验 figure.binding。
- 2026-10-27 · v0.3.1 · status=draft · 修复实证文章写作缺陷：writer/review 按 article_type 分支，reproduction 稿可报告已签 claim 与 per-method mean/std，不再被提示为“综述且不放实验数值”；写作包拆分 experiment_design/experiment_package，新增 allowed_design_numbers、摘要/讨论数值审计、experiment-idea 关联校验，并拒绝删除全部或改动已报告结果数字的修订。
- 2026-10-27 · v0.3.0 · status=draft · 新增 same-run empirical paper loop：校验实验与 run 同源、evidence verified、claim 人签后，生成写作包/初稿/多轮评审，并把手稿审计绑定到 experiment closure；不执行实验、不签核、不投稿。
- 2026-10-26 · v0.2.0 · status=draft · 新增模型初稿与多轮评审闭环：写作包+创新评审→初稿→审计→修复；5 维 rubric→修订→再评审；修订必须不恶化确定性审计；仍不替代同行评审，submission_ready=false。
- 2026-10-26 · v0.1.0 · status=draft · 初始实现：单 run 写作包、真实来源卡、span 过滤、结果数值策略、中文手稿预审与 MCP 写入；不签核、不替代同行评审。

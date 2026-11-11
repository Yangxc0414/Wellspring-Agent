---
id: idea
name: 假设收敛
stage: S2–S3
version: 0.26.0
status: pilot
owner: research-agent
inputs:
  - topic
  - spans
  - language
outputs:
  - IdeaCard
  - IdeaBrief
  - IdeaShortlist
  - InnovationReview
  - GapMap
  - CriticSupplyPanel
tools:
  - idea.frame
  - model.idea_proposer
  - idea.innovation_review
  - model.innovation_critic
  - model.profile_binding
gates:
  - G1
invariants:
  - 候选不是 Claim
  - 必须带否证条件
  - 不能自动通过 G1
  - 聚类只生成候选框架，不评 novelty、不自动收敛短名单
  - 低证据支持、无跨来源候选、lens 单一必须进入 IdeaBrief.gaps / warning
  - 模型只能基于输入 span 提候选；evidence_refs 必须解析到输入 span
  - 模型候选仍需 G1；模型不能生成 Claim/结果/指标数值
  - innovation review 的 novelty/evidence/feasibility 评分只是模型辅助 critique，不是 novelty 证明；不得自动通过 G1
  - innovation review 只能引用写作包中存在的 REF；缺口/想法/实验计划缺字段或引用未知时必须拒绝或修复
  - innovation review 不运行实验、不写 Claim/EA/gate；落盘只写 run 目录
  - prior_art_scope 只能是 live_search/live_abstract/s1_corpus/none；live 结果只是 prior-art 线索，不是新颖性结论，也不得进入候选 evidence_refs 或当作写作包 REF
  - prior art 必须来自候选证据之外的来源；同 source/同 span 的 live 命中必须过滤，不得把候选自身证据伪装成 prior art；S1 回退同样排除候选来源
  - rule candidate 的代表 span 与 evidence_refs 先按 topic 词重叠排序，再按长度；不得只用最长 span
  - rule candidate 的 lens 跟随 section：limitation/discussion→boundary，evaluation/benchmark/result→measurement，method→mechanism；未知 section 才回退轮换
  - 跨来源 contrast 必须是不同 source 且与 topic 有词重叠；不能仅因 section 是 limitation 就拉入无关对照；contrast 不是 evidence，用于 A/B 假设框架与 shortlist 排序
  - prior_art_report 记录每个候选的 query、scope、hits 与 error；live 搜索失败时必须回退 s1_corpus/none 并记 warning，不得静默伪造命中
  - 任何候选都保持 novelty_status=unverified；仍需人工 G1 与独立 prior-art/新颖性判断
  - IdeaShortlist 只按 prior-art scope、证据数、跨来源、kill criteria 做 advisory 对比；不得给 novelty 分数、不得自动选短名单，selection 固定为 human_g1
  - 实验计划必须绑定 executable 注册表中的 profile，且 dataset/metric 属于该 profile；不可执行的直接拒绝
  - innovation-review 必须输出 independence 区块；同一模型回答全部批评角色时 single_author_review=true 且 admission_eligible=false
  - 每个批评角色必须由可解析的独立供给回答（provider+model 指纹不同），且提案模型不得兼任批评角色；只有全部条件满足才允许 admission_eligible=true
  - admission_eligible 只是供给层面板校验，不证明输出独立、不证明 novelty、不构成 G1/G2 通过；供给指纹来自配置，可被伪造，仍属 advisory
  - 阶段产物的文字由请求语言决定：prompt 内的硬编码语言指令不得覆盖 language 参数，未知语言在执行前拒绝
---

# 假设收敛子智能体（S2–S3）

## Purpose

把 S1 的 span 转成可讨论、可证伪的候选方向，供人做 G1 收敛。它不评“新颖性”、不自动选短名单、不创建 Claim。

## Contract

- 评审方独立检索（反证先验文献）：`innovation review --prior-art-corpus <真实语料> [--prior-art-limit N]`
  让 novelty 审稿人在想法生成**之后**，用每个想法自己的 mechanism/novelty_claim 措辞另起检索，
  拿到与生成方证据集**分离**的候选先验文献，逐条带 `overlap`（词法重叠）与
  `also_in_generator_set`（是否本来就在生成方集合里，独立不得默认成立）。
  novelty 提示词强制要求对每一条命中**点名接受或显式否定**，不得忽略；判定输出里带
  `review["prior_art"] = {available, queries, sources, with_overlap, reviewer_retrieved, boundary}`。
  未给语料时不静默：`available=false` 且 `reason` 写明"新颖性只用生成方自选证据判定"。
  边界：词法重叠是给人/模型看的指针，不是"已被做过"的证明；检索只用离线语料端口
  （`RetrieverPort.search`），不联网、不创建 Claim/EA/Verdict、不影响签核。

- 输入：`topic`、`Span[]`、`max_candidates`；可选 `prior_art_searcher(query, limit)`；
- 可选输入 `gap_pack`（`gaps` / `brief_gaps` / `facets` / `themes`，全部来自 S1 与 S1b 已有回执，不新增来源或数值）：S2 用它把候选绑定到**可验证的跨来源主题**，不得凭空贴标签；
- 输出：`IdeaCard` 带 `gap_ref` 与 `relation_type`。`gap_ref` 仅在候选 `evidence_refs` 命中 S1b 跨来源主题（`source_count>=2` 且 `stances[].evidence` 能解析到输入 span）时取 `theme:<theme_id>`；否则为 `unbound`（有缺口但无法验证绑定）或 `none`（未提供 gap_pack）。禁止按 index 轮转分配或编造关联；
- `relation_type` ∈ `single_source` / `contrast` / `theme_co_occurrence` / `unclassified`。离线确定性路径的 S1b `agreement` / `tension` 恒为空、`stance` 恒 `mixed`，因此**不得**据此输出 `tension` / `agreement`；`theme_co_occurrence` 只表示词法共现，不是语义综合；
- 输出：`IdeaResult.warnings` 必带 `synthesis_breadth=...`（gap_pack 是否提供、跨来源主题数、绑定候选数、relation 分布、离线未判定张力的声明）；`IdeaBrief.gaps` 在 gap_pack 缺失时写 `gap_pack_absent`、S1 无结构化科学缺口时写 `no_scientific_gap_in_s1`、有主题却零绑定时写 `no_gap_grounded`；
- 本改动只补输入契约与 `IdeaCard` 末尾两处带默认值的可选字段，不改候选生成、不改门禁、不写 Claim/EA/gate、不宣称创新点质量提升；
- 规则路径在同一 run 内**不得复用同一个对照 span**：`_contrast_for_group` 接受已用 span 集合，使多个候选尽量引用不同的对照来源。实测改动前 30 篇真实语料下 3 个候选共用 1 个对照 span，等于只用上 4 篇文献；
- 候选的 representative / title 必须优先取**可定位证据句**：疑似题名、作者名、地名、版权 / arXiv 行等无句末标点的短行排在实质句子之后，不得让论文题名充当候选标题。该判断只做排序降权，**不删改 S1 产物**；
- 输出：`IdeaResult.warnings` 必带 `idea_structure=...`：不同对照来源数、唯一否证条件数 / 候选数、唯一终止条件数 / 候选数、`needs_metric` 数，并显式声明「模板帧不含变量、预期方向或预注册指标，不是研究假设」。该回执只做结构计数，不构成质量判定；
- 本轮不改模板文案、不改候选数、不改门禁、不写 Claim/EA/gate、不宣称创新点质量提升；S1 的 span 抽取噪音过滤属 `literature` 模块，本轮未做；
- 输出：`IdeaCard` 带 `prediction`（可证伪预测十槽位 `variable / direction / condition / profile / dataset / metric / controls / seeds / stopping_rule / criterion`）、`prediction_status`（`testable` / `cannot_test` / `not_testable_here`）与 `open_slots`；
- 判定为纯函数：无 `prediction` → `not_testable_here` 且 `open_slots` 列全部十槽位；槽位未填齐、或 `validate_plan` 拒绝（`executable.py` 的可执行档位是唯一权威）→ `cannot_test`；填齐且 `validate_plan.ok` → `testable`。**不得**用语料主题词或词法启发式猜测研究对象归属；
- 规则路径**只标状态、不编造变量**：`prediction=None`、`prediction_status=not_testable_here`、`open_slots` 全列；模型 proposer 路径必须把供给给出的十槽位原样保留进 `prediction`（此前 `_model_cards` 静默丢弃，实测 10/10 供给 → 0/10 保留），不得丢失或改写；
- `IdeaResult.warnings` 的 `idea_structure=` 回执须报 `prediction_status` 分布；`testability` 是旧词法字段，权威状态以 `prediction_status` 为准；
- 本改动不改候选数、不改 hypothesis / falsification 模板、不改门禁、不写 Claim/EA/gate、不宣称创新点质量提升；G1 是否拒收 `not_testable_here` 属门禁语义变化，本轮未做；
- 输出：`IdeaCard[]`（标题、假设、否证条件、evidence_refs、status=candidate；lens / evidence_count / source_count / novelty_status / testability；prior_art_refs / prior_art_scope / prior_art_delta / kill_criteria；contrast_refs / contrast_note）；
- 输出：`IdeaBrief`（候选数、来源数、≥2 证据候选数、跨来源候选数、lens 分布、gaps、summary）；
- 输出：`IdeaShortlist`（ranked: rank/evidence/source/prior_art_scope/novelty_status/testability/has_kill_criteria；selection=human_g1；criteria/boundary）；只作对比，不自动选；
- 输出：`prior_art_report`（每个候选的 query/scope/hits/error）；live 命中只作 prior-art 线索，不进入 evidence_refs；
- 输出：`IdeaResult.warnings` 必带 `source_mode=...`：按输入 Span 的 `fixture` 标记统计，含 fixture 时显式声明「演练来源，候选不是研究证据或 claim」，全部非 fixture 时声明 `real` 但仍需 Q0 / Claim Curator；无 span 时声明无可定位证据。S1 的 `fixture_mode` 必须经此向 S2 传递，不得在 S1→S2 衔接处丢失；
- 候选按同 section/同来源/低 token 重叠聚成簇；每簇最多引用 4 个 span；
- 规则路径必须把 `_contrast_for_group` 选中的**异源对照 span** 纳入 `evidence_refs`（簇内最多 3 条 + 对照 1 条，总数 ≤4），并在 `contrast_refs` / `contrast_note` 保留其对照角色；`source_count` 按 `evidence_refs` 实际覆盖的独立来源数统计，不得再按聚簇来源数统计。这样 `IdeaBrief.multi_source_candidates` / `no_multi_source_candidate` / `idea_review` 的 `source_diversity` 才能反映真实跨来源情况。对照 span 必须来自输入 `Span[]`，不得新增或编造内容；找不到异源 span 时保持原行为；
- 输出：`IdeaResult.warnings` 必带 `candidate_breadth=...`：输入独立来源数、候选数、`evidence_refs` 覆盖 ≥2 独立来源的候选数，并显式声明「无 novelty 证明、无独立留出集与人工评分、G1 仍是人工签核」。该回执是披露，不改变候选生成或门禁、不写 Claim/EA/gate；
- 每个候选必须带否证条件；lens 轮换为 mechanism / boundary / measurement；
- status 为 `candidates_need_human` 或 `needs_evidence`；
- 明确 `novelty_status=unverified`；低证据支持 / 无跨来源候选 / lens 单一 / 无 prior art 写入 gaps；
- 可选 `proposer`：输入 `topic/spans/language/max_candidates`，返回候选 JSON；每个候选必须含 `title/hypothesis/falsification/lens/evidence_refs`，`evidence_refs` 必须是输入 span 的子集且至少一条；
- test 模式下无 proposer、无 key、模型失败或输出非法时回退规则模板；production 模式下绑定缺失、调用失败或 JSON 不可解析直接抛 `ModelRequiredError`，不回退；
- 模型候选与规则候选共享同一证据边界和 G1；
- 可选 `critic_models`（`role -> ModelPort`，role ∈ novelty/evidence/feasibility）与 `panel`（`model_catalog.critic_panel()` 输出）：把每个角色绑定到独立供给；未绑定的角色回落到提案模型，并被 independence 记为 single_author；
- `independence` 输出 `supplies`（role→provider/model/kind/host_label 指纹）、`distinct_supplies`、`distinct_providers`、`proposer_is_critic`、`reasons`、`kind` 与 `admission_eligible`；每条评审记录带 `supply`，事后可核对分数由谁给出；
- 禁止：自动 novelty 结论、自动 G1、把候选写成结果 claim。
- 可选输入 `generation_constraints`（v0.25.0 起；v0.26.0 类型化）：每行 `loop_id/subject/constraint_kind/payload/constraint/source_path/source_sha256`。S2 按 `constraint_kind` 分派——`require_lens_diversity` 在候选 lens 会塌缩时强制轮换出第二个 lens；`demote_candidate` 在 shortlist 对 `payload.title` 同名候选降权（ranked 带 `feedback_demoted`）；`carry_falsification` 把 `payload.falsification` 追加进候选 falsification；`carry_forward` / `require_falsification_binding` 不改候选，只记 provenance（`no_change_needed` / `not_applicable_to_generation`）。`constraint` 文本仅供人读；无 `constraint_kind` 的旧输入回退文本推断一次；未知 kind 不消费、不猜测。无约束时行为与升级前逐字节一致；约束不改门禁、不写 Claim/EA/gate、不自动 G1。
- 输出：`IdeaResult.feedback_constraints_applied`（v0.25.0 起；v0.26.0 增 `constraint_kind`）：每条被消费约束的 `loop_id/constraint_kind/subject/source_path/source_sha256/constraint/effect`，使 idea.json 可追溯「哪条判定塑造了这批候选」；未消费时为空列表。模型 proposer payload 增 `generation_constraints` 键（含 kind/payload，仅当非空）。


## Current Implementation

- `research_agent/innovation_review.py`：从 S1 run 构建缺口与候选想法，调用 novelty/evidence/feasibility 三个审稿角色，按 must_fix 修订后再次评审；每轮记录分数、评审和证据；输出 `innovation-review.json`、`innovation-iterations.jsonl`、`innovation-report.md`；
- `research_agent/independence.py`（v0.12.0）：供给指纹与面板校验；`model_catalog.py::critic_panel()` 给出可达成的角色面板与缺失项；CLI `innovation review --independent/--critic role=profile`；
- CLI `innovation review`；MCP `research_innovation_review`；需要真实模型 key（默认 DeepSeek），未签核 Claim 不参与；
- 所有 evidence_refs 必须解析到写作包 REF；缺少否证/实验计划字段会被拒绝并要求修复；模型输出不直接进入 Claim 或 G1。

- `research_agent/modules/idea.py`（v0.9.0）；rule candidate 从不同 source 选 topic 相关的 contrast span，形成 A/B 假设框架；contrast 不进入 evidence_refs，shortlist 记录 `has_contrast`；
- `research_agent/modules/idea.py`（v0.8.2）；rule candidate 的 lens 跟随 section，避免 Results 被当成 boundary、Limitations 被当成 mechanism；
- `research_agent/modules/idea.py`（v0.8.1）；rule candidate 代表 span/evidence_refs 按 topic 重叠排序；live/S1 prior-art 排除候选同 source/同 span，避免自证式 prior art；
- `research_agent/modules/idea.py`（v0.8.0）；生成 `IdeaShortlist`：按 prior-art scope/证据数/跨来源/kill criteria 排序，`selection=human_g1`，不评 novelty、不自动选短名单；
- `research_agent/modules/idea.py`（v0.7.0）；支持可选 `prior_art_searcher`：优先做 source-scoped live prior-art 搜索，写 `prior_art_scope=live_search|live_abstract` 与 `prior_art_report`；失败/无命中回退 S1 最近证据（`s1_corpus`/`none`）；live 结果不进入 evidence_refs，novelty 仍未核验；
- `research_agent/task_agent.py` 与 `pipeline.py` 已注入 prior-art searcher（复用 S1 literature/corpus）；`orchestrator.py` 仍使用 S1 最近证据回退，未接 live 搜索；
- `research_agent/modules/idea.py`（v0.3.0）；
- 对 span 做证据聚类，生成带 lens、支持跨度、来源数与否证条件的候选框架；机制与指标仍留 `需人工补全`；
- `language` 控制候选标题、假设、否证条件与 brief 摘要的生成语言（zh/en），默认 zh；不改变聚类与证据边界；
- `IdeaBrief` 汇总候选轴与收敛缺口，不自动 G1；
- 可选 `research_agent/adapters/research_models.py::gateway_idea_proposer`：按设置中的 `idea` 模型绑定解析；test 模式无 key/绑定缺失时返回 `(None, note)`，不阻断规则模板；production 模式 strict 直接失败；
- 模型输出逐候选校验：evidence_refs 必须解析到输入 span，缺否证条件/标题/假设的候选拒收；全部拒收时回退规则聚类并写 warning；
- 模型调用不是证据来源，不产生 Span/Claim，也不改变 novelty_unverified 与 G1。
- `research_agent/modules/idea.py`（v0.25.0）：消费 `generation_constraints`（feedback 0.4.0 消费侧的新鲜约束）；lens 多样性强制 / shortlist 降权 / 否证条件携带三种确定性 effect；`IdeaResult.feedback_constraints_applied` 写 provenance；pipeline（integration 0.50.0）负责把项目反馈账本接进 IdeaRequest。

## Boundaries

- 候选不是科学结论；
- 必须由人补全机制/指标并通过 G1；
- 不得把 truncation 后的 span 当作完整证据。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `IdeaAgent` 与测试；
4. 只动 idea 模块，不碰 literature/figure。

## Changelog

- 2026-11-11 · v0.26.0 · status=pilot · 消费侧改 kind-first：require_lens_diversity/demote_candidate/carry_falsification/carry_forward/require_falsification_binding 按类型分派，文本解析仅作旧输入回退；feedback_constraints_applied provenance 增 constraint_kind；未知 kind 不消费、不猜测。tests/test_idea 2 项。
- 2026-11-11 · v0.25.0 · status=pilot · 反馈环回指消费：IdeaRequest.generation_constraints 消费 feedback 0.4.0 新鲜约束（homogeneity 强制 lens 多样性、belief_revision 对 revise-or-drop 候选 shortlist 降权、t6b 携带已执行否证条件进 falsification）；IdeaResult.feedback_constraints_applied 写 provenance（loop_id/subject/source sha256/effect），idea.json 可追溯哪条判定塑造了候选；无约束时逐字节不变；G1/Claim 边界不变。tests/test_idea 增消费侧断言。
- 2026-11-07 · v0.24.1 · status=pilot · 模型/宿主供给面同步（patch）：0.24.0 让 IdeaCard 承载 prediction，但 IDEA_SYSTEM 仍要求模型只输出 5 个字段并禁止指标，导致真实 run 永远拿不到十槽位；且该提示词要求的是嵌套 prediction 对象，而 0.24.0 的 _model_cards 只读顶层扁平字段，二者不一致（上一轮测试用扁平 proposer 未暴露，本轮端到端测试抓到）。本 patch：IDEA_SYSTEM 声明十槽位、仅当研究对象确属已注册可执行档位时才填、不确定或不在册必须省略且禁止编造；_model_cards 优先读嵌套 prediction 并兼容旧扁平答案；新增 tests/test_idea_model_contract.py 4 例钉住提示词、gateway→IdeaCard→testable、宿主不给预测时 not_testable_here、档位外 cannot_test。host_model._validate 只检查 require_keys 不拒绝额外字段，故十槽位可穿过 WorkBuddy host-model 交接面。不改契约、不改门禁、不宣称质量提升。
- 2026-11-06 · v0.24.0 · status=pilot · 结构化预测贯通（修复契约丢字段，不编造研究内容）：只读原型实测注入 proposer 给出 10/10 预测槽位（variable/direction/condition/profile/dataset/metric/controls/seeds/stopping_rule/criterion）后，_model_cards 只保留 title/hypothesis/falsification/evidence_refs/lens，IdeaCard 保留 0/10，testability 被硬编码 needs_metric；同时 30 篇真实语料下按 12 条判据只有 4/12 满足。根因收敛为 IdeaCard 契约不承载结构化预测，而非语料或提示词。Contract 新增：IdeaCard 带 prediction/prediction_status(testable|cannot_test|not_testable_here)/open_slots；判定为纯函数，以 executable.py 的 validate_plan 为唯一权威；规则路径只标 not_testable_here + 全列 open_slots、绝不编造变量；模型 proposer 路径原样保留十槽位；idea_structure 回执报状态分布。已存在的 ExperimentDesign 字段可承接下游。未改候选数、模板文案、门禁、Claim/EA/gate；G1 拒收 not_testable_here 属门禁语义变化，需人裁，本轮未做。新增 tests/test_idea.py 用例钉住不编造、不丢弃、档位外 cannot_test 与向后兼容。
- 2026-11-06 · v0.23.0 · status=pilot · 候选内容质量的结构性修补（只改证据选择与披露，不动模板文案与门禁）：实测 30 篇真实 arXiv PDF + gap_pack 下，3 个候选共用同一个对照 span（LOCAL-ae40748989-S01-06）与同一篇对照来源，等于 30 篇语料只用上 4 篇；三个候选的 falsification / kill_criteria 唯一文本各 1/3（完全相同的万能模板句），testability 全 needs_metric、novelty 全 unverified；候选标题直接是论文题名或首页句子截断；S1 有 134/240 span 疑似题名/作者/地名等噪音，其中 2 条被当作证据引用。Contract 新增三条：同 run 内对照 span 不复用（最大化不同对照来源）、representative 优先可定位证据句（无句末标点的短行降权，不删改 S1 产物）、warnings 必带 idea_structure 结构回执（不同对照来源数、唯一否证/终止条件数、needs_metric 数，并声明模板帧不是研究假设）。明确结论：结构可追溯不等于内容是研究假设，hypothesis 仍缺变量/方向/可执行指标，需 L2 档位校验与 L4 留出集人工评分，本轮未做。新增 tests/test_idea.py 用例钉住对照去重、题名降权与回执。不改模板文案、候选数、门禁、Claim/EA/gate，不宣称质量提升。
- 2026-11-06 · v0.22.0 · status=pilot · L0 科学缺口贯通（只补输入契约与可选字段，不动门禁）：诊断探针实测 IdeaRequest 只有 topic/spans/max_candidates/run_id/language/prior_art_searcher，pipeline 已算出的 S1b synthesis_matrix 只写进 modules 未传 S2，IdeaCard 无 gap_ref/relation_type；且 30 篇真实语料下 S1 coverage.gaps 为空、S1b 确定性主题的 agreement/tension 恒空、stance 恒 mixed——即系统里没有科学缺口这个一等对象，S2 只能从原始句子做词法聚簇。Contract 新增：可选 gap_pack 输入（gaps/brief_gaps/facets/themes 全来自 S1/S1b 已有回执）、IdeaCard 末尾带默认值的 gap_ref 与 relation_type、gap_ref 只在 evidence_refs 命中跨来源主题 stances[].evidence 时才绑定（实测 54 条 evidence 全部能对上 span_id）、relation_type 枚举不含 tension/agreement（离线路径不得谎报语义综合）、warnings 必带 synthesis_breadth 与三种新 gaps。pipeline 构造并传入 gap_pack。不改候选生成/门禁/Claim/EA/gate，不宣称质量提升；L2 档位校验、L3 漏斗、L4 留出集仍未做。新增 tests/test_idea.py 用例钉住真绑定、向后兼容与不谎报 tension。
- 2026-11-06 · v0.21.0 · status=pilot · 规则路径跨来源证据贯通（只改证据归属，不动门禁）：实测用项目内 30 篇真实 arXiv PDF 走本地语料检索，S1 得 30 独立来源 / 240 span / coverage 1.0 / saturated / review_grade=yes / fixture_mode=false，但 S2 规则路径产出的 3 个候选各自 4 条 evidence_refs 全部来自同一篇论文，跨来源候选 0 个，max_candidates 调到 8 仍是 0 个；系统已挑出异源 contrast_refs 且 falsification 已按对照证据生成，却未把它计入 evidence_refs，导致 IdeaBrief.multi_source_candidates 恒 0、idea_review 恒判 single_source。Contract 新增两条：规则候选把异源对照 span 纳入 evidence_refs（簇内 3 + 对照 1，≤4）并让 source_count 按实际来源数统计；warnings 必带 candidate_breadth 回执（输入来源数 / 候选数 / 跨来源候选数 / 无 novelty 证明声明）。不改候选数、不改 G1、不写 Claim/EA/gate、不宣称创新点质量提升——项目无独立留出集与人工评分，研究质量不在已证范围。新增 tests/test_idea.py 用例钉住多来源输入下跨来源候选数与回执。
- 2026-11-06 · v0.20.0 · status=pilot · S1 到 S2 的证据来源贯通：实测发现 IdeaResult 没有任何 fixture 标记，S1 明确标注的 fixture_mode 在 S1→S2 衔接处丢失，下游读 idea.json 无法区分候选来自合成语料还是真实证据。Contract 新增一条：IdeaResult.warnings 必带 source_mode，按输入 Span 的 fixture 标记统计并显式声明演练/真实来源，无 span 时声明无可定位证据。只改披露，不改候选生成、不改门禁、不写 Claim/EA/gate。新增 tests/test_idea.py 两条用例钉住 fixture 与非 fixture 两种输入。
- 2026-11-03 · v0.19.0 · status=pilot · 出题与修订两处提示词现在都附上注册表里每个因子的合法水平与格子数上限（plan_levels_block，由 search_lab.SEARCH_FACTORS 与 MAX_DESIGN_CELLS 现场渲染，与预检同源，不手写清单）。动因是宿主作答的实跑：提示词只列出因子名而不列水平，模型于是发明了 archive "on"、archive_window "top2"、parent_selection "diversity_biased"，被 #77 的预检在执行之前拒掉——预检是对的，但提示词在教模型犯错。数值因子如实写成"任意数值（示意 0.005, 0.02, 0.05）"，因为执行侧对 min_delta 不做水平成员检查，提示不能比执行更严。未改动 executable.py（它在代码指纹三文件内），只在 idea 阶段拼接，因此既有研究包的 derivable/match 不受影响。新增 2 例守住：模型曾发明的水平名不得出现在提示词内、boolean 因子显示 on|off、数值因子显示为任意数值、上限 12 在列。
- 2026-11-03 · v0.18.0 · status=pilot · 想法预检现在也校验声明的实验设计本身：在 validate_plan（只查 profile/dataset/metric）之后，用执行侧同一个 normalize_design 校验因子名、每个因子的水平与格子数，并把结果并入 idea.executable（新增 cells）；不合格的想法在进入候选集之前就被拒并把原因写进 warnings，而不是等一整轮设计+跑数之后由 runner 拒。依据是实跑测出来的：宿主作答的 innovation-review.json 里 5 个想法有 3 个声明了未注册水平（archive on、archive_window top2、parent_selection diversity_biased）、1 个 16 格超上限，而 validate_plan 当时对它们全部返回 ok=True。约束：水平归一必须复用 normalize_design 的同一规则（boolean 写 on/off 合法、数值型 min_delta 不做水平成员检查），以免把可执行的设计误拒；判定仍属预检信息，不改变分数、不创建证据或门禁。新增 tests/test_design_preflight.py 5 例。
- 2026-11-03 · v0.17.0 · status=pilot · 想法评审在建模型端口时把本次 run 作为轮次绑定传下去：_default_model(project, run_id) 组出 {project_dir, run_id} 交给 default_model_for 的 binding 参数。此前账本已保存 prompt 原文与 messages_sha256，但每条轮次的 binding 都是空字典，导致"随包发布精确 prompt"无法按 run 归属；现在新跑的研究可在包内投影自己的 prompt。无 project/run 时传 None，不编造归属。用例 3 个：转发到网关端口、阶段填对 project+run、无上下文即不绑定。
- 2026-11-02 · v0.16.0 · status=pilot · 想法生成与多角色评审新增 language 参数（CLI innovation review --language zh|en、MCP research_innovation_review 同名可选参数，默认 zh 保持既有行为）：它决定返回字段（title、problem、mechanism、novelty_claim、falsification、risks 以及 experiment_plan 内的字符串）用哪种文字书写，prompt 本身仍是中文指令，不再由 prompt 内的硬编码规则替调用方决定产物语言。动因是实测——用 ACL 的 idea 档 rubric 打我们真实的 innovation-review.json 得 covered=0、artifact=zh、coverage_confidence=degraded，全库 11 个想法产物中纯 ASCII 的为 0；根因是 innovation_review.py:351 在 prompt 里硬编码第 8 条"使用中文"，而同一模块在 :236/:378/:418/:510 已经是 language-aware，声明参数被硬编码指令覆盖。同时 run_innovation_review 不再把写作包语言写死为 zh；未知语言在任何执行之前直接拒绝。新增 tests/test_innovation_language.py 三条用例：en 替换掉中文规则、默认仍要求中文、非法语言在 run 之前被拒。
- 2026-11-02 · v0.15.0 · status=pilot · v0.15.0 gives the novelty critic its own retrieval: innovation review --prior-art-corpus with --prior-art-limit searches a real CC-BY corpus using each idea's own mechanism wording after generation, and lists every hit with its source id, lexical overlap, and whether it was already in the generator's set. Before this change novelty was judged only against the sources the generator itself had chosen, which is the same self-answering structure recorded for the guideline memory A/B, and it is fixed without needing a second model provider or any key. Absent a corpus the review records prior_art.available=false with the reason rather than implying independence, and a retrieval failure degrades to the same explicit absence. The critic prompt now refuses to let a high score stand while ignoring the hits, and each line carries the id so the instruction to name the source is actually followable: the first version rendered only titles and overlaps, which one of the new cases caught. Reviewer-side overlap is a pointer for the critic, never a proof of non-novelty, and nothing here creates a claim, a verdict or a gate. Eight new cases in tests/test_innovation_prior_art.
- 2026-10-31 · v0.14.1 · status=pilot · design 水平被错误地字符串化：_normalise_ideas 用 str(level) 复制 design，gate/memory 的 true/false 变成 "True"/"False"，runner 的注册表只接受布尔水平，显式 design 仍可能被判不可执行。现在抽出 _normalise_design 并保留 JSON 标量类型（布尔、数字、字符串），新增回归测试。0.14.0 的 design 字段契约不变，升 patch。
- 2026-10-31 · v0.14.0 · status=pilot · 创新点的实验计划缺一个可执行的因子声明：experiment_plan 只有 profile/dataset/baseline/metric/stopping_rule，normalizer 会丢掉任何 design 键，于是文本写 archive_window=all|recent 的计划到了 study from-idea 只剩默认 memory×gate。现在 proposer 的输出 schema 与 normalizer 都保留 experiment_plan.design（{因子: [水平...]}），要求 9 明确 runner 不从句子里推断因子；缺 design 且文本提到注册因子时由 search-study runner 拒绝。计划 schema 增可选字段，属于契约变化，升 minor。
- 2026-10-31 · v0.13.2 · status=pilot · 创新评审不再对着空主题提案：run_innovation_review 在未显式传 topic 时从 run/demo.json 读取 topic，并在 writing pack 的 task.goal 为空时写入它。之前 pipeline run 的 pack.task.goal 为 null，提示词写成“研究主题: 未提供”，Qoder 只能凭空提案。实测 qoder-design-turn：新 turn 的提示含真实主题，Qoder 产出 3 个 gaps + 3 个 ideas（可执行 profile=protocol_run/iris/accuracy），novelty/evidence/feasibility 三位 Qoder critic 分别给 4-6 分，总评 needs_more_work；独立面板如实判定 single_author（proposer 与 critic 同为 Qoder，1 个 supply），不冒充独立评审。tests.test_innovation_review 1 项 OK。契约不变，升 patch。
- 2026-10-30 · v0.13.1 · status=pilot · 0.13.1（2026-10-30）：把"只能单来源"的结论改成可执行指引，并撤回一处无效改动。上一版把确定性聚类器也改成轮转顺序输入，实测预审仍是 0 advance / 3 revise——因为该聚类器按 section 分组、且同来源相似度被强制为 1.0，单来源簇是它的构造结果，换输入顺序无用；**为翻转判定而硬拼一条弱相关的外部来源属于作弊**，所以这处改动已回退（保留只对模型提示词生效的轮转取样，那里是实测有效且诚实：宿主的候选确实引用了 4 个来源中的 2 个）。同时把预审理由从 candidate relies on a single source 扩成带下一步的句子：ground it in a second source, or let a model propose cross-source candidates（并说明确定性聚类器自身做不到）。tests.test_idea 16 项 + tests.test_idea_review 全绿。无行为变化，升 patch。
- 2026-10-30 · v0.13.0 · status=pilot · 0.13.0（2026-10-30）：修掉"想法永远只能引用一篇论文"的结构性缺陷。实测：宿主写出的 3 个候选全部被判 revise，原因都是 relies on a single source——而这不是宿主偷懒：_proposer_payload 取的是 request.spans[:24]，而 span 按来源成组排列，前 24 条几乎全来自同一篇，任何忠于证据的候选都不可能满足"至少两个来源"。改为 _spread_spans：按 source_id 轮转取样（各来源各取一条，循环到上限）。实测同一批候选在修复后预审从 0 advance / 3 revise 变成 **3 advance / 0 revise**，即"推进"这个结论第一次真的可达。顺带修 load_idea_result：--idea-file 原先只接受系统自己的 idea.json，宿主直接交的原始答案（candidates 无 idea_id）会以 TypeError 失败；现在按顺序补 IDEA-01…、缺 title/hypothesis 的候选给出明确错误。tests.test_idea 16 项 OK（新增 EvidenceSpreadTest 五项：轮转遍历全部来源、前缀只覆盖一个来源、上限生效、无 id 的原始答案可复用、空候选被拒而非猜）。契约变化：想法提示词的证据取样规则 + --idea-file 接受无 id 的候选。
- 2026-10-29 · v0.12.0 · status=pilot · 0.12.0（2026-10-29）：单作者评审从披露变为可解除。新增 research_agent/independence.py 供给指纹（provider+model）与 evaluate_panel：每个批评角色可绑定独立供给，提案模型兼任审稿或全部角色由同一宿主回答时拒绝承认独立。innovation review 新增 critic_models 入参，每条评审记录带 supply；manuscript_writer 的写作提示按 admission_eligible 分两档措辞。实测（runtime_data/independence-demo/out/innovation-review.json）：三个 host profile 配置上互不相同→single_author_review=false，但账本把三次批评都归因到同一宿主（Qoder Desktop）→admission_eligible=false，kind=model_only。契约变化：新增入参与产物字段。
- 2026-10-29 · v0.11.0 · status=pilot · 0.11.0（2026-10-29）：评审独立性披露。实测显示 novelty/evidence/feasibility 三个角色在 Host-as-Model 下由同一宿主模型顺序回答，且仅调阈值就把结论从 needs_more_work 翻成 reviewed——"三方评审"表象没有独立支撑。result 新增 independence（critic_calls / distinct_model_ids / single_author_review / admission_eligible），写作提示词注入该事实并明确禁止把三角色写成三位独立审稿人或用其分数支撑"已通过评审"。契约变化：新增产物字段与不变量。
- 2026-10-29 · v0.10.0 · status=pilot · 0.10.0（2026-10-29）：可行性闸门。实测发现 S2/S3 生成的搜索类假设在本运行时完全不可执行（S5 只做一次固定拟合），实验计划字段因此被填成口径混淆内容（把文献语料写进 dataset）。现在 experiment_plan 必需新增 profile 字段，并与 research_agent/executable.py 的注册表校验（dataset/metric 必须属于所选档位）；不可执行的想法在校验阶段被拒绝而非带着空计划通过。生成提示词同步注入可执行档位与各档位 cannot_test。契约变化：新增必需字段与不变量。
- 2026-10-28 · v0.9.0 · status=pilot · rule candidate 增加跨来源 topic-driven contrast（不同 source + topic 词重叠），用于 A/B 假设与 falsification；contrast 不是 evidence，短名单记录 has_contrast；无相关对照时保持单边候选。
- 2026-10-28 · v0.8.2 · status=pilot · rule candidate lens 跟随 section（limitation→boundary、evaluation/result→measurement、method→mechanism），未知 section 才轮换；不改变证据/novelty 边界。
- 2026-10-28 · v0.8.1 · status=pilot · 修复 prior-art 自证与 topic 偏差：live/S1 prior-art 排除候选同 source/同 span；rule candidate 代表与 evidence_refs 按 topic 词重叠排序；真实语料 probe 从“同源 live_search”变为“独立来源 s1_corpus/none”。
- 2026-10-28 · v0.8.0 · status=pilot · 新增 `IdeaShortlist` advisory 对比：按 prior-art scope/证据数/跨来源/kill criteria 排序，`selection=human_g1`；不评 novelty、不自动选短名单。
- 2026-10-28 · v0.7.0 · status=pilot · 接入可选 live prior-art 搜索：TaskAgent/pipeline 复用 S1 literature 按候选查询，写 `prior_art_scope=live_search|live_abstract` 与 `prior_art_report`；失败回退 S1 最近证据；live 结果不进入 evidence_refs，`novelty_status=unverified`，不自动 G1；orchestrator 仍用 S1 回退。
- 2026-10-28 · v0.6.0 · status=pilot · IdeaCard 增加 S1 内最近 prior-art 上下文（`prior_art_refs/scope/delta/kill_criteria`）；无匹配记 `no_prior_art`；仍不是实时 prior-art 检索，`novelty_status=unverified`，不自动 G1。
- 2026-10-26 · v0.5.0 · status=pilot · 新增证据约束的创新评审闭环：缺口→候选→novelty/evidence/feasibility 三评审→修订→再评审；模型评分只是 advisory，不通过 G1、不写 Claim；引用/字段/否证条件做确定性校验。
- 2026-10-26 · v0.4.2 · status=pilot · 新增 deterministic idea review：检查证据 grounding、来源多样性、否证条件、可测指标、lens 与是否复述证据；输出 advance/revise/reject，明确词法预审不是文献新颖性，G1 仍人工。
- 2026-10-25 · v0.4.1 · status=pilot · 生产模式 strict：idea 绑定缺失、模型调用失败或输出不可解析时直接抛 ModelRequiredError，不再回退规则模板；test 模式保留规则回退。
- 2026-10-25 · v0.4.0 · status=pilot · 可选模型 proposer：只能基于给定 span 生成候选，引用必须解析到输入 span；输出非法或引用越界即拒收回退规则模板；模型候选仍受 G1、novelty_unverified 与 no-Claim 边界约束。
- 2026-10-25 · v0.3.1 · status=pilot · 最小改进：候选代表片段改为组内最长 span（上限 90 字符），减少截断片段进入假设标题。
- 2026-10-25 · v0.3.0 · status=pilot · 契约扩展：IdeaRequest 新增 language（zh/en），候选标题、假设、否证条件与 brief 摘要按语言生成；默认 zh，不改变证据边界与 G1 人工门。
- 2026-10-24 · v0.2.0 · status=pilot · 假设收敛升级：span 聚类而非逐句候选；IdeaCard 记录 lens/evidence_count/source_count/novelty_status/testability；IdeaBrief 汇总候选轴、多证据/跨来源数量与 low_evidence_support / no_multi_source_candidate / novelty_unverified 缺口；仍不自动 G1，不评 novelty。
- 2026-10-23 · v0.1.0 · 初始候选框架：span → 可证伪方向；不自动 G1。

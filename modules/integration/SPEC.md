---
id: integration
name: 通用 MCP 与项目目录
stage: META
version: 0.51.0
status: pilot
owner: research-agent
inputs:
  - MCPToolCall
  - ResearchProject
  - TaskRequest
outputs:
  - ProjectManifest
  - RunDirectory
  - TaskExecution
  - MCPToolResult
  - ExternalSkillAdvisory
  - SkillDistillCandidate
  - ManuscriptRevision
  - WritingPack
  - WritingAudit
  - SupportPanel
  - SupportAdjudication
  - ConferenceCorpus
  - SynthesisMatrix
  - InnovationReview
  - ManuscriptDraft
  - ManuscriptReview
  - ExperimentPackage
  - ModelProfileCatalog
  - AgentCapabilityManifest
  - LoopCapsule
tools:
  - research_project_init
  - research_bootstrap
  - research_plan
  - research_run
  - research_status
  - research_model_profiles
  - research_model_turns
  - research_model_respond
  - research_list_artifacts
  - research_read_artifact
  - research_next_actions
  - research_skill_list
  - research_skill_instructions
  - research_skill_invoke
  - research_skill_distill
  - research_manuscript_revise
  - research_figure_templates
  - research_figure_render
  - research_literature_fetch
  - research_literature_synthesis
  - research_conference_fetch
  - research_writing_pack
  - research_manuscript_audit
  - research_venue_audit
  - research_grant_template
  - research_innovation_review
  - research_manuscript_draft
  - research_manuscript_review
  - research_experiment_codegen
  - research_experiment_status
  - research_empirical_status
  - research_closure_status
  - research_evolution_status
  - research_lineage_status
  - research_support_panel
  - research_support_items
  - research_support_verdicts
  - research_manuscript_section_edit
  - research_manuscript_bind
  - research_manuscript_ab_review
  - research_model_void
  - research_host_contract
  - research_skill_packs
  - research_mandate_status
  - research_number_provenance
  - research_study_baseline
gates:
  - Q0
  - G1
  - G2
  - S5b
  - G5
invariants:
  - MCP 只暴露计划/执行/读取/下一步，不暴露 sign、approve、freeze、publish 或 export 工具
  - 所有项目写入必须位于 --root 或 RESEARCH_AGENT_MCP_ROOT 内；拒绝 ..、绝对越界路径与 symlink 逃逸
  - 每次运行写入 <project>/runs/<RUN-ID>/，并带 run-context.json 记录客户端与请求摘要
  - 每次 pipeline/task 运行写入只读 `loop-capsule.json`：S1→S2–S3→S4→S5→S6→S8–S12→S13→META 节点、blockers 与 bounded next_actions；缺失节点不得写成 pass，capsule 不创建证据/claim/gate/signature/closure
  - loop-capsule 由 run 产物派生；若同 run 存在 `experiments/<id>`，S5/S13 必须反映该实验包的 claim/closure/signature 阶段；S8–S12 必须读取 `manuscript-audit.json`/`writing-audit.json`，无写作审计时标 `WRITING_NOT_STARTED`；runtime 完成后可补 observation_id/active_policy_id，但不得改写其他节点的状态来源
  - loop-capsule 的 G5/S13 必须读取 `closure-signature/signature.json`：closure report ready 但未签名只能标 `CLOSURE_UNSIGNED` 与 S13=ready，不得写成 pass/done；签名后才把 G5 置 pass、S13 置 done、claim_status 置 signed，并在 reason 里区分 delegated 与 human
  - build fingerprint 必须固定为进程启动时导入的代码；每次请求重读磁盘会让长期运行的 stdio server 报出“当前文件”的哈希，掩盖它仍在执行旧模块
  - stdout 只输出 JSON-RPC/NDJSON；库与调试日志走 stderr，不能污染协议
  - production 模式缺 model binding/key 时必须失败，不得静默回退规则模板
  - fixture 仅用于流程验证；摘要-only 不生成 span，不产生 claim
  - MCP 的 external Skill 只以 instruction-only advisory 调用；不执行 scripts/tools/network；输出不进入 Claim/EA/gate
  - research_bootstrap 只初始化/计划/列目录；`run_now=true` 时才调用本地 TaskAgent `research_run`，仍不执行外部 Skill 脚本、不签核
  - research_skill_instructions 只返回 enabled Skill 的文本，不返回本地路径、不执行脚本；Qoder 自执行时仍不得把 Skill 指令当证据或门禁
  - MCP 蒸馏只产出 project notes 下的 disabled 候选；不自动启用；MCP 不提供 trusted script 执行
  - trusted script 全权限只在本地 CLI 显式 opt-in，且不是 sandbox
  - MCP revision 只写 `<project>/revisions/`；无 profile 时 copy mode；不改写成功不得声称改写
  - MCP figure render 只渲染项目 scene 或本地 vendored 模板；不执行 vendor 脚本、不联网、不修改原 AstraDraw 文件夹
  - figure 模板只提供视觉先验；manifest 必须标 schematic=true，不能把模板中的机制/数字当本文结论
  - revision 的 submission_ready 始终 false；DOCX/TeX 是工作模板，不是官方期刊模板
  - writing pack 是 run 的只读投影；未签核 claim 不得发布结果数值；不允许编造引用
  - 主 run 的事件流是权威状态：`research_agent/run_events.py` 以 append-only 哈希链记录 `seq/at/kind/phase/payload/prev_hash/entry_hash`，`demo.json` 与 `job.json` 只是派生投影，不得就地改写门禁结论；`verify_events()` 只报告链断裂，绝不静默修复
  - 阶段边界只有在**全部**门禁为 `pass`/`skipped` 时才由 `commit_boundary()` 写 `boundary_committed`；任一门禁 `blocked`/`needs_human`/`failed` 写 `gate_rejected` 且边界不提交。`replay_boundaries()` 只读重放，不自动续跑、不自动跨人工门
  - G3/G5 的 `status` 与 `reason` 只能由 `pipeline.evaluate_g3_g5()` 这一个纯函数决定；`pipeline.run()` 与 `write_pipeline_artifacts()` 都必须调用它，禁止在产物后处理里就地 mutate 门禁 dict
  - 全量判定记录（`scripts/record_test_verdict.py`）必须把运行器 `FAILED (errors=N, failures=M)` 里的两个数解析进结构化 `errors`/`failures` 字段；`summary_line` 保留运行器原文，二者不得互相矛盾
  - 允许一条**不跨人工门**的自动回路：S1 覆盖判定（`saturation` / `coverage_score` / `gaps` / `evidence_breadth`）可驱动下一轮 `max_sources`，由 `research_cycle.decide_next_cycle()` 纯函数决策、`run_literature_cycle()` 执行；每轮的观测与决策写进 append-only 事件链，预算有界（`max_cycles` / `budget_cap`），饱和或预算耗尽必须停下，耗尽时显式写「需人补语料」而不是假装已收敛
  - 该回路**只改变检索预算**：不改 Q0/G1/G2/G3/G5 判定、不写 Claim/EA/gate/signature、不置真 `submission_ready`、不自动续跑整个 pipeline、不新增语料（不编造文献）。`PipelineRequest.adaptive_retrieval` 默认 False，关闭时行为与上一版逐字一致
  - writing audit 的 submission_ready 始终 false；fixture 来源、未知引用、未签核结果数值必须阻断
  - MCP 只把 writing-pack.json/md 与 writing-audit.json 写入对应 run；draft 必须位于项目内
  - 模型 key 只来自用户/系统环境变量；Windows 启动器仅按名称从 HKCU\Environment 回读，不写项目、不写 MCP 配置、不记录值
  - conference fetch 仅下载 arXiv 公开 PDF；venue 来自 arXiv comment，未独立核验；不是完整 proceedings 抓取
  - innovation review 必须通过 REF 存在性/字段/可证伪性校验；模型输出不得创建 Claim/EA/gate
  - manuscript review 只在确定性审计不变差时接受修订；不改写未知引用；submission_ready 始终 false
  - writing pack 的 experiment_id 只读取 verified experiment-evidence 与人签 claim；evidence 不是 EA
  - MCP 不提供 experiment run/approve/claim；生成实验包的执行与签核只能在本地 CLI
  - MCP、HTTP JSON、Python SDK 共用同一套工具名/JSON Schema/边界；适配器不得各自复制业务逻辑
  - research_status 只读盘点 canonical_run/local_experiment closure 产物；不重跑、不签核、不改变 closure 状态
  - runtime `/api/autopilot-status` 只读且剥离绝对路径；不提供任何触发 autopilot 的端点
  - research_closure_status 一次只读一个 profile；canonical_run 与 local_experiment 的 closure 词汇不互换；只返回下一条人工命令
  - research_evolution_status 只读一个 RSI 台账的生命周期读数（episodes/decided/rejection_rate/gate_verdict/gate_stops/timeline）；零拒绝判为 gate_uninformative 而非成功；不 propose、不 admit、不 reject、不 revoke、不 activate
  - research_lineage_status 只重算项目内节点的 SHA-256 并判 fresh/stale；不重建 workspace、不读取项目外文件、不把 fresh 当作实验或 closure 有效
  - research_support_panel 只接受与 pack_id/pack_sha256 绑定的稿件；judge profile 由调用方提供，不能证明 provider/model 独立；分歧必须 pending_human 或 strict 阻断
  - research_support_panel 的 kappa 只覆盖被审计子集，不是 human gold；人工裁决必须带 status 与 human_reason；不创建 Claim/EA/gate/signature
  - research_support_items/verdicts 是 Qoder 自评审通道：items 只读、verdicts 只记录 Qoder 提供的判断；不调用外部模型、不冒充独立评审
  - verdicts 必须覆盖所有 judgeable item（strict 默认 true），id/status/evidence_refs 必须来自当前 pack；缺项直接拒绝
  - section edit 只替换一个匹配章节，其他章节与 marker 原样保留；不得新增 REF 或数字，不得覆盖源稿；expected_section_sha256 不匹配即拒绝
  - research_model_profiles 只返回 profile/provider/model/是否有 key；不得返回 API key、masked key、base URL 或本地路径；不发起网络调用
  - diverse_judge_pairs 只是可用性建议，不证明两个 profile 的 provider 真正独立或模型质量
  - HTTP adapter 默认只允许 loopback；非 loopback 必须配置 `RESEARCH_AGENT_API_TOKEN`，不得裸奔
  - capabilities 只暴露工具 schema、start-research/review-draft/review-idea prompt、边界/人类门，不暴露 secrets、绝对本地路径或内部 prompt
---

# 通用 MCP 与项目目录（META）

## Purpose

让 Qoder、Claude Code、Zcode 等外部 Agent 通过标准 MCP 调用本项目已有的科研流水线，并把全部产物落在用户指定的项目文件夹中。集成层只负责协议、项目边界和工具路由，不复制或绕过 S1–S16 的证据逻辑。

## Contract

输入：

- MCP stdio（newline-delimited JSON；兼容 LSP Content-Length）JSON-RPC 请求；
- `project_dir`：相对 `--root` 或位于其内的绝对路径；默认 `research-project`；
- `research_run`：`goal`、`source`（必填）、`task_type`、`max_sources`、`language`、`venue_type`、`flow_mode`、`run_dataset`、`run_seeds`、`deliverable`；
- 可选人工产物：`g1_decision_file`、`protocol_file`、`claim_file`、`bibliography_file`、`run_dir`，均相对项目根且必须已存在。

输出：

- `research_project_init`：`project.json` + `inputs/ runs/ protocols/ claims/ closure/ notes/`；
- `research_bootstrap`：初始化项目、生成任务计划、返回 enabled external Skill 清单与 journal Skill profile 清单；`run_now=true` 时在同一调用中执行本地 TaskAgent `research_run`；不执行外部 Skill 脚本、不签核；
- `research_run`：`runs/<RUN-ID>/` 下的 `run-context.json`、TaskAgent 全部产物；失败时额外写 `failure.json` 或 `startup-error.json`；
- `research_status`：最近 run 的状态、route、stopped_at、failure，以及可选的 `governance` 摘要（support_panel status/pending_human、support_gold status/κ/panel accuracy、writing_audit status）；对每个 run 额外读取 support-ledger/writing-audit/support-gold，返回 `support`（status/counts/judge_model/draft/weak_sections）、`manuscript`（status/submission_ready/draft）、`experiments`（experiment_id/package/stages/next_action）与 `idea`（candidate_count/candidates/shortlist_selection/shortlist_ranked/boundary）；未在 run index 中的任务目录也会补入；无 task.json 的 Qoder-native run 标记 `qoder_native=true` 且 status 为 `manuscript:<ledger status>`；只读；
- `research_list_artifacts` / `research_read_artifact`：仅限 run 目录内的文本产物；
- `research_next_actions`：G1/G2/S5b/G5 的人工 CLI 命令与 resume 参数；若同 run 的 support-ledger 为 partial/blocked/needs_human 或存在 weak_sections，额外返回 `support_review` 动作（draft、weak_sections、next_tools），提示用 `research_support_verdicts(reuse=true)` 只重判变更句；若 ledger 已 ready 但 human gold 缺失或 draft hash 不匹配，返回 `human_gold` 动作与生成/评估模板的 CLI；若同 run 的本地实验包尚未 approve，返回 `experiment_approval` 动作与 `experiment approve` CLI；G1 动作附带 `idea` 摘要与 `idea_ids`（候选/短名单/prior-art scope），供 Qoder 展示选择；若 `support-gold.json` 已存在且 draft hash 匹配，返回 `human_gold_ready` 动作（accuracy/disagreements），提示进入人工审阅而不是签名；不签核；
- `research_skill_list`：enabled/license/has_scripts/risk_flags 目录投影，不返回 instructions 或本地 origin；
- `research_skill_instructions`：只读返回一个已启用外部 Skill 的 instructions/description/license/hash 与 has_scripts；供 Qoder 自己执行，不调用模型、不执行脚本、不返回本地路径；
- `research_skill_invoke`：advisory；可选 `distill_on_success`，要求 `project_dir` 与 `human_reason`；
- `research_skill_distill`：写入 `<project>/notes/skill-library/` 的 disabled `local-*` 候选与 `<project>/notes/skill-distillations/` 回执，要求 license 与 human_reason；
- `research_manuscript_revise`：读取项目内 draft/data/spec，写入 `<project>/revisions/<REV-ID>/`；输出修订稿、diff、指标、图、审计与 MD/TeX/DOCX/PDF；有 profile 才模型改写，无 profile 为 copy mode；
- `research_figure_templates`：列出 vendored AstraDraw scene 模板（id/component/style/尺寸/对象数），不含外部素材；
- `research_figure_render`：把项目内 `.scene.json` 或模板渲染为 `<project>/figures/<FIG-ID>/` 下的 SVG/PNG/audit/manifest；
- `research_literature_fetch`：显式 `allow_network=true` 搜索 arXiv 并下载公开 PDF 到 `<project>/inputs/`，写 provenance/SHA256；不绕过付费墙；
- `research_literature_synthesis`：多篇来源 → 主题×来源矩阵（≥2 篇/主题、一致点、张力、未使用来源）；写作包/创新评审共享；
- `research_conference_fetch`：按 venue/year 抓取 arXiv 公开 PDF；只保留 arXiv comment 明确写主会接收、标题含 agent/研究自动化信号的论文；不是完整 proceedings 抓取，接受状态未独立核验；
- `research_writing_pack`：把一个 run 压成 `<run>/writing-pack.json|md`（真实来源卡、span、claim_plan：每个主张一个 ref/span/quote、idea/design/run/claim 状态与写作契约）；不签核；
- `research_manuscript_audit`：检查项目内草稿的引用键、结果数值、章节与占位符，写 `<run>/writing-audit.json`；若同 run 有 support-panel，返回其状态并阻断未裁决/stale panel；若同 run 有 support-gold，返回 annotator 数/mean kappa/panel accuracy 摘要（gold 不是 gate）；`support_max_items` 默认 80、最大 200，截断时 strict 阻断、非 strict 至少 partial；返回 `uncited_factual_count/samples`、`multi_ref_sentence_count/samples` 与目标期刊的 `journal_style`（外部 MIT Skill 投影，warning 级），strict_support 下未引用事实句阻断；最多 `ready_for_human_review`；
- `research_innovation_review`：基于全文 span 做 proposal→三评审→修订→再评审，输出 `<run>/innovation-review.json`、迭代记录与报告；不运行实验、不创建 Claim；
- `research_manuscript_draft`：用写作包+创新评审生成中文综述/立场初稿，并立刻跑确定性审计；不伪造实验、不签核；
- `research_manuscript_review`：rubric 评审→修订→再评审，候选修订必须通过引用/数值审计且不让 blockers 变差；`submission_ready=false`；
- `research_experiment_codegen`：从 run 的 S4 设计和项目内 CSV 生成自包含实验包（spec/runner/requirements/README/manifest）；**不执行**、不装依赖、不创建 EA/Claim、不通过 G2；
- `research_experiment_status`：只读返回实验包 lifecycle（spec/data/code/preflight/approval/execution/evidence/claim/support_panel/closure/signature/lineage）与 next_action；若同一 run 有 support-panel 且未 ready，next_action 指向人工裁决；不执行、不签核；
- 本地实验执行/ingest/claim/closure/lineage 仅走 CLI（approve→run→ingest→claim→closure→sign→lineage），MCP 不暴露执行或签核。
- `research_closure_status`：只读判断 canonical_run 或 local_experiment 的 closure 状态、check 结果、blockers、下一条人工命令，以及 presence/SHA-256 证据链（存在性与身份，不是正确性证明）；两种 profile 若存在 `support-panel.json`，链中记录其 status/fingerprint，blocked/needs_human 时 next_action 指向人工裁决；`closure check`/`experiment closure` 的 `support_panel_ready` 硬门只允许 ready/not_applicable；单次只查一个 profile，不重跑、不签核、不改产物；
- `research_evolution_status`：只读把一个 RSI 台账投影成工具面能看到的自改进读数——回合数、已被人工判定数、批准/拒绝数、拒绝率、未通过的关卡分布（gate_stops）与关卡判定（gate_verdict：no_episodes / awaiting_decisions / gate_uninformative / informative）。拒绝率与 gate_verdict 是对**门禁与任务集**的读数，不是提案质量的分数：一次都没拒过判为 gate_uninformative，永不写成成功。`ledger` 参数必填，多余参数（例如 approve）直接拒；不 propose、不 admit、不 reject、不 revoke、不 activate，门权限仍只在 CLI 且需要人工理由；
- `research_lineage_status`：只读重算 local experiment lineage 中各节点的 SHA-256，返回 fresh/stale、stale 原因与下一条 CLI 命令；项目外路径判 stale；不重建 lineage、不签核、不执行；
- `research_support_panel`：对绑定当前写作包的稿件运行多 judge 句级支持面板，写 `<run>/support-panel.json` 与人工裁决模板；返回逐句分歧、pending_human、pairwise kappa、fingerprint 与截断信息；`max_items` 默认 80、最大 200，截断时 non-strict 至少 partial、strict blocked；不签核、不改稿、不授权投稿；
- `research_model_profiles`：只读列出 model gateway 的 profile_id/label/provider/model/has_key、模块绑定与可用的跨 provider judge 对；不返回密钥、masked key、base URL 或路径，不联网；
- `research_support_items`：只读返回绑定稿的句级支持项（id/sentence/refs/evidence），不调用模型、不给 verdict；供 Qoder 用自己的额度做评审；
- `research_support_verdicts`：接收 Qoder 的句级 verdicts，校验 id/status/evidence_refs，写 `<run>/support-ledger.json`，标记 `judge_model=qoder:<id>`，并返回 section_summary/weak_sections；`reuse=true` 时对未改句（sentence+evidence 不变）复用同一 judge id 的旧 verdict，只要求变更项的新 verdict，返回 provided/reused 计数与逐项 `reused` 标记；不同 judge id 不复用；写新稿 ledger 前将不同 draft hash 的旧 ledger 归档到 `support-ledger-history/` 并返回 `archived_ledger`；不调用外部模型、不签核；
- `research_manuscript_section_edit`：把 Qoder 写的单一 section body 应用到绑定稿，支持 `##`/`###` 标题，保留其他章节与 pack marker；拒绝新增 REF/数字；支持 expected_section_sha256 防陈旧写；不调用模型、不签核；
- `research_manuscript_bind`：给已有草稿只附加当前 writing pack marker，正文原样保留；拒绝已绑定/不同 pack/output=source；要求至少一个能解析的 `[REF-xx]`，返回 resolved/unresolved refs；不造证据、不调用模型、不签核；
- MCP prompt `start-research`：一键入口文本，要求客户端调用 `research_bootstrap(run_now=true)` 走本地 TaskAgent，再按 writing pack → support items/verdicts（修订后 reuse=true）→ audit 的顺序执行；prompt 只描述流程，不执行工具、不签核；
- MCP prompt `review-idea`：读取 run 的 idea 摘要与短名单，逐个展示 prior-art scope/contrast/novelty_status/kill criteria，给出 advisory 对比；由人选择 idea_id 后在 CLI 运行 `flow g1`，prompt 不写 g1-decision、不签核；
- MCP prompt `review-draft`：已有草稿入口文本，要求先 `research_manuscript_bind`（未解析 REF 不当证据），再 support items/verdicts、section edit（reuse=true）与 audit，ledger ready 后生成 human gold 模板并停止；prompt 只描述流程、不执行工具、不签核；
- `GET /api/research/capabilities`：稳定能力清单（35 tools、JSON Schema、OpenAI function schema、人类门边界）；
- `POST /api/research/tools/{tool_name}`：框架无关的 JSON 工具调用入口；可选 Bearer token；
- `research_agent.framework_api.ResearchAgentAPI` / `research_agent.client.ResearchAgentClient`：本地 Python 与 HTTP client；
- `integrations/frameworks/`：LangGraph/CrewAI/AutoGen/自定义 HTTP 接入说明。

MCP 协议：

- `initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`、`resources/list`、`prompts/list`、`prompts/get`；
- 工具错误返回 `isError=true` 的 tool result；协议错误返回 JSON-RPC error。

## Current Implementation

- `research_agent/project.py`：项目 manifest、固定目录、run 目录、run index、越界校验、产物列表/读取；
- `research_agent/mcp_server.py`：stdio transport、工具表、参数校验、TaskAgent 调用、模型工具解析、next actions；
- v0.50.0 闭环接线：`pipeline.py` idea 阶段经 `loop_capsule.project_root_for_run` 定位项目，读 `feedback.generation_constraints`（新鲜约束进 `IdeaRequest.generation_constraints`；stale 默认拒绝入 warnings；emit `feedback_constraints` 事件），并消费 `waitpoints.pending_delegation_events`（emit `delegation_events` + warnings + `mark_delegation_acted`，图③ 06 回指）；`research_next_actions` 增 `kind=delegation_event`（含 task-less 分支）。不跨人工门、不写 Claim/EA/gate/signature。
- v0.51.0 快照消费者读时重算：`mcp_server._loop_capsule_summary`（research_status / next_actions 的 capsule 摘要）不再信任 `loop-capsule.json` 的 blockers/next_actions/nodes 判定字段，改为 `build_loop_capsule(target)` 读时重算（artifact 为准）；快照只保留历史与 runtime META（observation_id/active_policy_id 回填节点）；输出增 `recompute` 只读回执（snapshot_blockers vs recomputed_blockers）；`CLOSURE_UNSIGNED` 被移除时给 `verdict_override`（source=read-time-recompute、总线 sha256 绑定；无总线行时 recomputed=unknown，不冒充 signed）。
- `scripts/research_mcp_server.py`：固定 cwd/import path 到本仓库的 stdio 启动器，避免客户端从自己的安装目录启动时导入旧代码；
- `research_agent/framework_api.py`：框架无关 capabilities + `dispatch_tool`；MCP/HTTP/Python 共用；
- `research_agent/client.py`：`ResearchAgentClient`（HTTP）与 `LocalResearchAgent`（进程内）；
- `research_agent/runtime/app.py`：`/api/research/capabilities|health|tools/{tool}`；loopback 默认，token 保护远程；
- `research_agent/runtime/app.py` 的项目级实验链只读面：`GET /api/projects` 与 `GET /api/project-experiments?project_dir=...`，复用 `list_projects`/`list_project_experiments`；只返回 stages/next_action/evidence summary 与相对路径，拒绝越界项目；`research_status` 也返回同一 `experiment_inventory`；
- `research_agent/cli.py`：`project init|status`、`writing pack|audit`；
- `research_agent/loop_capsule.py`：从 run 目录产物生成只读 `loop-capsule.json`（S1→META 节点、blockers、next_actions、artifact_refs、boundary）；扫描同 run 的 `experiments/<id>`，把 experiment evidence/claim/closure/signature 阶段投影到 S5/S13；`write_pipeline_artifacts` 与 TaskAgent 统一写入，runtime 完成后补 observation/active policy；
- `research_agent/doc_interfaces.py`：文档接口只读审计（60 号文档 D6）；枚举 `AGENTS.md` 与 `modules/*/SPEC.md` 中全部 `*.json` 引用，按 exists / generated（必须带生成命令与缺失理由）/ template / relative_artifact / artifact_name / not_a_path / unexplained 七类分类，纯文件名在 `AGENTS.md` 里也严格检查；守卫是报告加测试棘轮，不创建文件、不改门禁；`tests/test_doc_interfaces.py` 断言未解释集合为空、改名注入必红、理由清单不腐烂，并断言新投影自身满足 `projections.py` 的七槽契约；
- `.mcp.json`（本机绝对路径，已忽略）、`.mcp.json.example`（占位符模板）、`.qoder/skills/`、`.claude/skills/`、`.zcode/skills/`：平台接入面；本地许可证与第三方边界见根目录 `LICENSING.md`/`SECURITY.md`/`THIRD_PARTY_NOTICES.md`，发布面由 `scripts/release_check.py` 自检；
- `scripts/research_mcp_demo.py`：真实 stdio 客户端演示（含 skill list → distill → list → manuscript revise）；
- `scripts/framework_bridge_demo.py`：真实 HTTP JSON 桥接演示（capabilities → project → plan → run → read）；
- `integrations/FRAMEWORKS.md`：LangGraph/CrewAI/AutoGen/OpenAI function calling 接入说明；
- `scripts/sync_integration_skills.py`：保持三端技能一致；
- 模型工具按 `RESEARCH_AGENT_MODE` 与 `RESEARCH_AGENT_MODEL_STORE` 解析；production 缺 key 直接失败；
- `source=local` 默认读取 `<project>/inputs/`，无 PDF/TXT/MD 时在创建 run 前拒绝。


## Boundaries

- HTTP adapter 是本地 JSON 工具桥，不是公网 SaaS；默认 loopback；远程必须 token + TLS/反代 + 额外鉴权/配额；
- HTTP 没有多租户隔离、配额、OAuth 或审计流水；生产化需另行设计；
- figure render 不在 MCP 中执行上游 Node/presentations 导出；可编辑 PPTX 仍由本地 AstraDraw 环境完成；
- arXiv fetch 只在 `allow_network=true` 时联网；只下载 arXiv 公开 PDF，不绕过付费墙；下载不是证据，必须再走 local PDF 解析得到 span；
- 不共享 runtime 浏览器会话里的 session key；MCP 进程只读自己的环境变量与 model store；
- 不创建、签署或发布 Claim/Closure/Signature；
- `source=fixture` 输出不可引用；`openalex` 只作线索；
- MCP 不执行带 scripts 的 external skill；`--trusted-scripts` 仅本地 CLI，且以用户 OS 权限运行、不是 sandbox；
- MCP revision 只修订已有稿件，不重新发明研究；生成稿的 `submission_ready=false`，官方模板/作者信息/投稿动作仍需人工；
- 蒸馏候选始终 disabled；MCP 不提供 enable/activate，也不把候选写入 Claim/EA/gate；
- 长任务同步执行；暂不发送 MCP progress notification；
- HTTP adapter 不做多租户鉴权/配额；远程部署必须另行加 TLS、token、反代与审计；
- HTTP 工具调用与 MCP 一样没有 sign/approve/freeze/publish；人类门仍走 CLI；
- Zcode/Claude Code 的配置路径随客户端版本可能变化，以 `integrations/README.md` 为准。

## Minimal Change Workflow

1. 先改本文件 Contract/工具表；
2. 升 version + Changelog；
3. 改 `project.py` / `mcp_server.py`，补 `tests/test_mcp.py` 或 `tests/test_integration_files.py`；
4. 跑 `python -m unittest discover -s tests -v`；
5. 若工具名或参数变化，同步更新三端 `SKILL.md` 与 `integrations/README.md`。

## Changelog
- 2026-11-11 · v0.51.0 · status=pilot · 快照消费者读时重算：research_status/_loop_capsule_summary 不再信任 loop-capsule.json 的 blockers/next_actions/nodes 判定字段，改为 build_loop_capsule(target) 读时重算（artifact 为准）；快照只保留历史与 runtime META（observation_id/active_policy_id 覆盖回节点）；增只读 recompute 回执（snapshot_blockers vs recomputed_blockers）；CLOSURE_UNSIGNED 被移除时仍给 verdict_override（source=read-time-recompute、总线 sha256 绑定，无总线行时不冒充 signed）。tests/test_verdict_ledger ConsumerMigrationTest 与 tests/test_next_actions_fallback 改为钉读时重算语义（快照命令不再被当权威回显；无 artifact 的 run 由新鲜重算给出动作）。
- 2026-11-11 · v0.50.2 · status=pilot · loop-capsule 增只读 feedback 投影（constraints_applied/loops/effects），从 idea.json 的 feedback_constraints_applied 派生——闭环是否消费了上一轮判定对宿主/工作台可见；additive，不改门禁/blockers/next_actions 语义。tests/test_loop_capsule 增断言。
- 2026-11-11 · v0.50.1 · status=pilot · doc_interfaces 分类修复：lineage 纳入 RELATIVE_PREFIXES——lineage/lineage.json 是 run 相对产物目录（与 run/claim/closure 同类），feedback SPEC 的该引用在 HEAD 即未分类（存量红灯，非本轮引入）；tests/test_doc_interfaces 增 relative_artifact 断言。
- 2026-11-11 · v0.50.0 · status=pilot · 闭环接线：pipeline idea 阶段经 project_root_for_run 读 feedback.generation_constraints（新鲜约束进 IdeaRequest，stale 默认拒绝入 warnings，emit feedback_constraints 事件）；消费 pending_delegation_events（emit delegation_events + warnings + mark_acted，图③ 06）；research_next_actions 增 kind=delegation_event（含 task-less 分支）。idea 0.25.0 / feedback 0.4.0 / waitpoints 0.2.0 同轮。
- 2026-11-11 · v0.49.0 · status=pilot · research_next_actions 读判定总线（71-§5 步 3 第二半）：`_next_actions` 追加 `_verdict_actions`（feedback.verdict_action_table 过本 run subject，kind=verdict_action、绑来源 sha256）；同函数两处 stale 快照判定改新鲜检查——G5 的「closure-signature/signature.json not in artifacts」与 S5b 的「claim/claim.json not in artifacts」用的都是 task.json 写入时刻的 artifacts 快照，autopilot 代签后会对已签闭包/已签 claim 重复给签署建议（与 verdict-ledger 抓到的 CLOSURE_UNSIGNED 同类漂移），改为读盘上的 signature 文件与 claim status；E2E RUN-E2E-02 实测 research_next_actions 从 stale 重签建议翻转为 verify_bundle/closure_check（runtime_data/m1-feedback/e2e-next-actions.json，behavior_changed=True）。输出新增 verdict_action 种类，升 minor。
- 2026-11-07 · v0.48.0 · status=pilot · 判定第一次改变下一次行为（有界、不跨人工门）：上一轮整体反思的结论是系统为单向投影架构，四种判定（资格/完成/失效/供给）的下游全是只读文字，唯一回路靠人在 CLI 显式重跑。本轮落地最小一条真回路：S1 覆盖判定驱动下一轮检索预算。新增 research_agent/research_cycle.py（observe 只读提取覆盖信号、decide_next_cycle 纯函数决策、run_literature_cycle 多轮执行并把每轮观测与决策写进 append-only 事件链，饱和或预算耗尽即停，耗尽显式标需人补语料）；PipelineRequest 末尾加默认 False 的 adaptive_retrieval，开启时 pipeline 的 S1 走回路并把 adaptive_cycle 投影与一行回执写进产物；CLI pipeline run 加 --adaptive-retrieval。实测基线（7 篇本地 CC-BY 全文）：预算 3 → 3 来源 / 24 span / coverage 0.675 / partial，下一轮预算 6 → 6 来源 / 48 span / 1.000 / saturated 并收敛。边界：只改检索预算，不改 Q0/G1/G2/G3/G5、不写 Claim/EA/gate/signature、不置真 submission_ready、不编造语料；默认关闭时既有行为逐字不变。新增 tests/test_research_cycle.py 与 pipeline 集成用例钉住预算有界、饱和即停、判定确实改变下一轮参数、默认关闭无回归。
- 2026-11-07 · v0.47.0 · status=pilot · 闭环状态可核对（只补骨架与单一权威，不改门禁语义）：对照 SciForge 的事件溯源与边界提交后复核，本系统仍有三处可定位缺口——pipeline.py:1098-1099 的 G3/G5 是硬编码字符串，write_pipeline_artifacts():1622-1637 又在产物后处理里就地 mutate 同一批 gate dict，存在两个互相覆盖的判定来源；主 run 只有 event_sink 内存回调与 job.json 整文件重写，没有 append-only 事件流、没有哈希链、没有「门禁未全过就不提交边界」的原子判定；scripts/record_test_verdict.py 调用 verdict_record 时未传 failures/errors，导致上一轮真实红灯 FAILED (errors=58) 的判定 JSON 里 errors=0 而 summary_line 写 58（D9 残余）。本轮：新增 research_agent/run_events.py（append_event/verify_events/commit_boundary/replay_boundaries/write_events/read_events，SHA-256 链 + append-only 落盘）；PipelineResult 末尾加默认空 events 字段，PipelineRunner._emit 同时写事件链；新增纯函数 evaluate_g3_g5 作为 G3/G5 唯一权威，run() 与 write_pipeline_artifacts() 都调用它并删除就地改写；产物写 events.ndjson 并在门禁未全过时写 gate_rejected；verdicts.parse_unittest_output 解析 failures/errors 且 record_test_verdict 传参。边界不变：不自动续跑、不自动跨人工门、不把 submission_ready 置真、不改 G1/G2/Q0 判定、不写 Claim/EA/gate/signature、events.ndjson 与 commit_boundary 都是可核对状态而非放行开关。新增 tests/test_run_events.py 与 tests/test_verdict_record.py 用例钉住链断裂可报、门禁失败不提交、G3/G5 单一来源、失败数解析。
- 2026-11-05 · v0.46.0 · status=pilot · 文档路径守卫合并，并记下一次**并发写入事故**。合并：删掉本模块 v0.45.0（下下条）新增的 `docs_paths.py` 与其测试，保留 `research_agent/doc_interfaces.py`（tests/test_doc_interfaces.py 19 例通过）——它把 AGENTS.md 与 modules/*/SPEC.md 一起枚举，多出 `relative_artifact` / `artifact_name` / `not_a_path` 三类，正好覆盖我那版被误判成 broken 的形状（`flow/idea.json` 其实由 pipeline 的 idea 阶段产出）。分类能力对比（同一文档，同口径不可比就并排列）：我那版 exists 12 / template 4 / generated 11 / broken 2；它这版 exists 15 / generated 19 / template 22 / relative_artifact 15 / artifact_name 86 / not_a_path 5 / unexplained 0。同一工件不留两个守卫，保留强的那个。共同盲点（两边都不报）：reason 只要求"文档里出现过那条命令"，而**命令存在不等于它会写出那个路径**——`pipeline-chemlab/run/run-capsule.json` 的现存产物在 `closed-loop/run/run/run-capsule.json`，多一层；修法是把解释变成可执行断言（跑一次命令，比对其产物路径与文档一致），归入 #93 的"可照抄入口"。并发事故：本轮 recorder 跑完全量得到 1227 例 OK 并记录指纹 `df22e107b5354c0a`，随后 `--show` 报 `stale`（当前 `c16f12f3cd6086c9`）——期间本文件与 `research_agent/doc_interfaces.py` 被另一个写入者改动（后者落盘 14:35，正在我的跑测窗口内）；我把 frontmatter 升到 0.46.0 时，对方也已写入一条同号 v0.45.0 记录，于是这份 SPEC 一度出现**两个 v0.45.0 描述两件事**。这不抹掉、只记录：它证明 #49 的"产物所有权要由 harness 强制"不是抽象主张，且**任何跨会话并发编辑都会使全量判定不可归属**；`--show` 报 stale 是正确行为，但结论是"多智能体同仓写侧必须先有所有权约定，否则判定与 SPEC 版本都会互相覆盖"。
- 2026-11-05 · v0.45.0 · status=pilot · 60 号文档 D6 落地：新增 research_agent/doc_interfaces.py 与 tests/test_doc_interfaces.py（19 例）。实测（枚举口径，不是抽样）：AGENTS.md 共 30 个 json 引用，12 个在当前检出存在、18 个不存在；18 个里 2 个是含占位符的模板，其余 16 个逐条登记生成命令与缺失原因。连同 29 份 SPEC 的接口正文共 162 个引用，0 个未解释，分类为 15 exists / 19 generated / 22 template / 15 relative_artifact / 86 artifact_name / 5 not_a_path；另有 29 个 SPEC Changelog 节共 93 个历史引用按 test_docs_freshness 的同一约定排除，并在报告里显式计数而不是静默丢弃。GENERATED_BY 每条必须同时写生成命令与缺失理由，沉默不算理由；改名注入（把 rsi-compare-ledger.json 换成 docs/renamed-away.json）立即报 unexplained。**落地过程中守卫把自己判负过一次**：第一版扫描把规格 Changelog 里作为回归示例写下的路径读成未解释引用，于是按接口正文/历史记录切分，并补了跳过量守恒与历史节排除用例——这条失败记录保留，不改成绿灯叙事。守卫只读：不创建文件、不改门禁/判定/签名，不验证命令真的跑得通；60-D6 的另一半（可照抄最短链入口）仍未落地，不得写成已支持。新增投影自身带齐 projections.py 七槽并经 projection_inventory 判 complete。无新增 CLI 命令或 MCP 工具，判定语义未动。
- 2026-11-05 · v0.45.0 · status=pilot · 新增 research_agent/docs_paths.py：文档里的路径引用变成可检查对象（60 号文档 D6，#93 的守卫那一半）。动因是实测：AGENTS.md 里有 29 个 `*.json` 路径、17 个当时不存在，读者无法区分"这是上一条命令的输出"与"这条引用是死的"，而 #81 的验收正是被后者卡住。规则不是"路径必须存在"（多数确实是产物），而是**缺席必须指名产出它的命令，且那条命令串必须能在同一份文档里找到**——找不到命令串的解释不算解释，只是换了说法的沉默（沿用 REVERSE_REASONS 的规矩）。四态：exists / template（裸文件名或含 "..." 的示例）/ generated（缺席但有可核的产出命令）/ broken（无）。broken 集合被测试钉成棘轮：新增一条死引用即红，修好一条必须显式改清单。实测 12 exists / 4 template / 11 generated / **2 broken**，两条 broken 都是真缺陷而非噪音：`flow/idea.json` 被 `flow g1 --idea-file` 读取却没有任何文档化命令写它；`pipeline-chemlab/run/run-capsule.json` 比流水线真正写出的位置少一层（仓库里现存产物是 `closed-loop/run/run/run-capsule.json`，即 `<output-dir>/run/run/run-capsule.json`），说明 AGENTS.md 自己的引用是错的——**这一点是守卫第一次运行就抓出来的，此前无人发现**。AGENTS.md 未擅自改动：要确认正确深度得真跑一次 pipeline，那是又一次验证，不在本轮里猜。测试 tests/test_docs_paths.py 7 例，含两条"必须能失败"的用例：复制文档改坏一个路径 → 守卫必须报 broken；替换未命中时测试自己先红（我第一版就是用了一个文档里不存在的替换目标，被这条断言挡住，等于测试自己骗了自己）。生成侧同时补了演示数据：`rsi fixture` 与 `rsi real-trial`（本地 BM25 + 冻结 CC-BY 语料，`simulation:false`）已在 AGENTS.md 指定路径落盘。
- 2026-11-05 · v0.44.0 · status=pilot · `research_evolution_status` 升 mcp-evolution-status-0.2，把 CLI 面的投影来源一起带过来。动因是第一次用真实数据跨面读回：`rsi real-trial` 在本地 BM25 + 冻结 CC-BY 语料上跑出的 `rsi-real-ledger.json` 带 `simulation: false`（4 个 episode、4 个已判定、4 个被拒、rejection_rate 1.0、gate_verdict=informative），经 Qoder 的 MCP 面调用读回后对比同面的 CLI story，发现 **story 携带 generated_at / source_fingerprint / base / read_only / provenance / summary.simulation_episodes，而工具一个都不带**——也就是宿主在 Qoder 里既看不出这份台账是演练还是真实，也看不出数字出自哪一代代码。§244 刚在 CLI 侧补的 simulation 披露，在 MCP 侧等于没补：来源在一个面存活、在另一个面被丢掉，就不是来源。工具现在原样透传 story 的这些槽（另加 story_schema_version 与 warnings），不自己重算时间、不重新发明格式。新增两条面 parity 用例：`test_the_mcp_face_carries_the_same_provenance_as_the_cli_face`（逐槽与 ledger_story 对比；generated_at 因两边各自取时、只比到日，避免造一个竞态断言）与 `test_a_simulated_ledger_announces_itself_through_the_mcp_face`（在临时台账上断言 simulation_episodes=1 且警告文字经 MCP 面仍可见）。35 例通过（本文件 + test_mcp + rsi_self_improvement）。判定语义未动：门、租约、签核仍只在 CLI。
- 2026-11-05 · v0.43.0 · status=pilot · 新增 research_agent/verdicts.py 与 scripts/record_test_verdict.py（60 号文档 D9，#94 闭合）。动因是本会话三次被同一件事咬到：后台套件被中断（退出码 1073807364，日志没有 Ran 行）、在套件飞行中改被测源码使判定作废（§221 规矩）、以及最险的一次——完成通知报 "completed (exit code 0)" 而套件实际打印的是 FAILED (failures=1)，因为命令链尾是 grep，**链的退出码是最后一个命令的退出码，不是套件的**。MCP 面早已解决同形问题（每条报错自报 served build，陈旧是一次比较而非猜测，见 #76），判定侧缺的就是这个。设计：`parse_unittest_output` 只读运行器自己写的汇总行，绝不从 shell 退出码推断；`verdict_record` 把 {source_fingerprint, tests_run, seconds, ok, truncated, finished_at, produced_by, summary_line, base} 落盘；`verdict_status` 回答四态 current / stale / failed / truncated / absent，其中 truncated 与 unreadable **一律 covers_current_source=False**（缺失与不可读不许被读成成功）。`scripts/record_test_verdict.py` 跑套件并写记录，返回码由解析出的判定行决定；`--show` 只读地报告"最近一份判定覆盖哪份代码"，不一致返回 1。实测（不是设计说明而是跑出来的）：--show 报 `stale | tests 1216 | current ae06a46d84bf7b80 | the newest verdict covers 9b753d1f6fb9246c ...`，rc=1。**实现中我自己写的解析器就是这条规矩的反面教材**：按空格切片取了 parts[3]（那是单词 "in"），float() 抛错被 except 静默吞掉，于是记录里 seconds=0.0 而判定照写不误——正是"默认值把失败吞成成功"。已改为正则 `^Ran (\\d+) tests? in ([0-9.]+)s`，且**匹配不上时 found=False 并说明 unreadable**，不再填零。新增 tests/test_verdict_record.py 11 例，其中两条钉住这次修正：不可读的汇总行不许变成 green-zero、单数形式 "Ran 1 test in 0.123s" 必须仍能解析。另附一份 live 演示：一份真实记录着失败运行的 test-verdict.json（ok=false）留在 runtime_data 里，说明失败与中断同样要被记录。
- 2026-11-05 · v0.42.0 · status=pilot · 新增 research_agent/projections.py：投影契约与枚举审计（60 号文档 D1）。动因是实测的系统性缺口——本仓库的主要产出是只读投影，而每个投影各自决定要不要带年份、生成它的代码指纹、fixture/simulation 标记、以及自己比率的分母；AST 扫描 157 个模块得到 171 个 schema id（229 个 dict 字面量声明），其中只有 11 个在字面量里带 generated_at、2 个带规范 source_fingerprint、3 个带 read_only。本会话追过的每一类"陈旧读数"（#76 旧构建、0/14 与 8/14 之争、无年份的 web 快照、#95 无 generated_at 的 MANIFEST、§244 汇总层丢掉 simulation、#54 全部包 stale）都是这一个缺口的实例。契约槽位定为 schema_version / generated_at / source_fingerprint / read_only / base / provenance / boundary；`projection_inventory()` 用 AST 枚举全部投影并报告每个槽位的状态，**四态而非两态**：in_literal、aliased（同一信息在别的键下，例如 host-contract 的 build 就是指纹——把它报成"缺指纹"会逼人复制字段）、elsewhere_in_file（静态扫描看不出来）、absent。它是报告不是门：171 个投影不可能一次补完，一个对全部投影都失败的守卫只会被删掉；真正被强制的是棘轮——签核/审计链上的投影在 tests/test_projection_contract.py 里被断言完整。实现过程中抓到我自己两个会让报告"好看"的错：(1) 汇总时只升级已见过的槽位，导致没人声明的槽位整条从 row 里消失、absent_slots 恒为空——一个列不出缺口的报告比没有报告更糟，因为它看起来像合规；(2) 任何带 schema_version 键的 dict 都被当成投影，于是本模块自己的 SLOT_MEANING 文档表被当成一个"完整"的投影，因此加了 schema id 形状过滤。另有 140 个字面量通过调用或格式化字符串声明版本，静态无法解析，计入 dynamic_schema_versions 而不是静默丢弃。测试 tests/test_projection_contract.py 共 11 例（InventoryShape 6 + AdoptionRatchet 2 + RuntimeSlot 3），含"四态对每个槽位必须守恒到 schema 总数"（这条正是能抓住 (1) 的断言）与"已知不完整的 closure-signature-0.2 必须列出缺口"。
- 2026-11-04 · v0.41.0 · status=pilot · 参数卫生从"每个 handler 自己记得"上移到共享 dispatch。实测：46 个工具里 42 个 handler 自带 `_reject_unknown`，`research_host_contract` 没有，另有 2 个 schema（venue_audit、grant_template）连 `additionalProperties: false` 都没声明。MCP 面看起来安全只是因为客户端按 schema 校验；HTTP 面与进程内调用直达 dispatch_tool，于是宿主发 `{"declared": [...]}`（而不是 `{"capabilities": [...]}`）会拿到一份"按零个已声明能力算出来"的契约、状态 200、无任何报错——本轮我自己就这么调过一次，被客户端 schema 挡住才发现两个面的校验位置不同。改法与 v0.40.0 的写守卫同构：新增纯函数 `unknown_argument_problem(name, arguments)` 与 `TOOL_SCHEMAS`，在 `dispatch_tool` 入口处按工具自己的 schema 拒收未声明键，一处规则覆盖所有面与所有未来工具；handler 里的 `_reject_unknown` 保留为冗余保险，不再是唯一防线。同时给 venue_audit 与 grant_template 的 schema 补上 `additionalProperties: false`（两者 handler 本来就有 `_reject_unknown`，属于 schema 漏写），于是"未约束的工具"从 2 降到 0，测试里不需要豁免清单。dispatch_tool 的 docstring 原先写"one validated tool call"，那是假设不是事实，现在它真的校验。测试：tests/test_dispatch_arg_hygiene.py 共 7 例（SchemaConstraint 2 + DispatchRefuses 5），其中 `test_an_unknown_argument_is_refused_for_every_tool_without_running_it` 用一个 Tripwire 替身枚举**全部 46 个工具**并断言拒收发生在 handler 之前（替身被触碰即失败），因此新增工具自动被覆盖；另有"拒收文案必须列出该工具真正声明的参数""声明过的参数不得被误拒""载荷类型错误留给 handler""未知工具不得被报成未知参数"。实测 55 例通过（含 preflight/face/integration_files/workspace/docs_freshness）。
- 2026-11-04 · v0.40.0 · status=pilot · HTTP 面写路由改为默认拒绝，并给前端补上它一直缺的凭证通道。动因是实测而非推测：`_require_research_api` 只被手工放进 4 个路由处理函数（3 个 /api/research/* GET 与通用工具 POST），而 59 条路由里 18 个 POST 中最敏感的 4 条——写模型密钥 /api/models/providers/{id}/key、改绑定 /api/models/bindings、代答 host-model 轮次 /api/host-model/respond、作废轮次 /api/host-model/void——完全无凭证；配合 `--allow-remote`（启动时只校验 host 是否 loopback，不校验有没有 token）就是"远程可达且无鉴权的写"。设计逻辑：逐路由手工加守卫不可能随路由数扩张，因此把规则收敛成纯函数 `credential_problem(client_host, token, authorization)`，由一个 http 中间件对所有 POST/PUT/PATCH/DELETE 生效（默认拒绝，新增路由无需有人记得加守卫）；GET 仍开放（本地 UI 轮询需要），/api/research/* 三个 GET 保留原 per-route 守卫，既有语义与测试不动。中间件里不抛 HTTPException——用户中间件位于 ExceptionMiddleware 之外，抛出会变成 500——改为直接返回 JSONResponse，并带 method/route/boundary 三个字段说明拒绝来自哪条规则。启动侧抽出纯函数 `remote_bind_problem(host, allow_remote, token)`：`--allow-remote` 而无 RESEARCH_AGENT_API_TOKEN 直接拒绝启动，理由写明"off-loopback 时每条写路由都会无凭证可达，而这些路由写模型密钥、绑定与 host-model 答案"。客户端侧：apps/web 的三个适配器（runtimeApi / hostModelApi / modelRuntime，共 4 个 fetch 点）此前**完全没有** Authorization 处理，服务端一收紧，设了 token 的用户 UI 写入就会 401 且无法自救；新增 `apps/web/src/adapters/runtimeAuth.ts`：内存态 token（不落 localStorage/cookie/文件，与"密钥只进 env 或运行时内存"的既有规则一致）、`authHeaders()`、`describeAuthRefusal()`（保留服务端 boundary 原文并附补救命令），并以 `window.researchRuntimeAuth.setToken` 作为一次会话内的粘贴入口。测试：tests/test_runtime_write_guard.py 12 例（纯函数 8：CredentialRule 4 + RemoteBindRule 4；HTTP 4），其中一条**枚举活路由表**断言每条 mutating 路由都返回 401——这条才是"默认拒绝"与"逐路由记忆"的区别所在；apps/web/tests/runtimeAuth.test.ts 5 例（含"无 token 时绝不发送空 Bearer 头"）。实测：前端 tsc --noEmit 通过、node --test 7 例通过；python 侧 test_runtime_write_guard + test_runtime_api + test_runtime_host_model_api 共 21 例通过。边界未变：没有任何路由能 sign/approve/freeze/publish/export，通用派发口 /api/research/tools/{tool_name} 只能打到 TOOL_NAMES（46 个），由 framework_api.call_tool 的 unknown tool 拒收保证。
- 2026-11-03 · v0.39.0 · status=pilot · 新增只读 MCP 工具 research_evolution_status：把一个 RSI 台账的生命周期读数（episodes/decided/approved/rejected/rejection_rate/gate_verdict/gate_stops/timeline）递给工具面。动因是实测事实：9 条 rsi/evolution/autopilot HTTP 路由没有一条被任何 MCP 能力指向，接入 Qoder 的 Agent 看不见自己所处的自改进回路，只能被人转述。工具带 readOnlyHint、ledger 必填、多余参数（如 approve）一律拒，不新增任何门权限；propose/admit/reject/revoke 仍只在 CLI。登记表同步：research_evolution_status -> cli rsi story + http /api/rsi/story。新增测试文件 tests/test_mcp_evolution_status.py 共 5 例。
- 2026-11-03 · v0.38.0 · status=pilot · 反向登记表两处仪表缺陷修正（都是我自己上一轮写出来的）：1) cli_command_paths 原先把 42 个"命名空间"（skill、empirical、study、task、closure 这类还有子命令的父节点）也算成命令，未到达表面数被虚增；现在只数叶子，faces.cli_commands 由 241 降为真实可执行命令数。2) unexplained_sample 是按字母排序的前 40 条，我却拿它口算了家族分布，得出 closure/agent/autopilot 为主的错误结论；改为输出 unexplained_families（对全部 unexplained 行统计）并显式标注 examples 是字母前缀、不得据其推分布。用例 3 条新增（家族计数必须等于 unexplained 总数、父节点不得出现在表面清单、截断仍显式报告）。
- 2026-11-03 · v0.37.0 · status=pilot · face_coverage 反向登记表（#80）：新增 reverse_coverage 与 REVERSE_REASONS，以 CLI 命令路径与 HTTP 路由为键，把 MCP 面未到达的表面分为 human_gate_by_design / reasoned / unexplained 三类，理由没写下来就是 unexplained——沉默不再被读成"没有缺口"。实测 241 条 CLI 里 37 条被 MCP 声明到达、59 条路由里 8 条到达，未到达 255 条中 unexplained 241、human_gate 11、reasoned 3。修掉自己刚写出的一个真 bug：分类循环把已到达的表面也算进缺口清单（surfaces 报 300 而不是 255），是靠与 §206 独立数过的 204/51 对不上才发现的；守恒断言 surfaces==sum(summary) 对这个 bug 无效，因为它两种情况下都成立。截断按 #28 的规矩显式报告。
- 2026-11-03 · v0.36.1 · status=pilot · face_coverage 登记表核实：research_run/manuscript_revise/study_baseline/support_panel 四个 unaudited 能力按 handler 实现（不是名字）登记为 CLI task run / revision run / study baseline / writing support-panel；research_run 与 CLI research run 同名不同能，按名配对会声明错目标。MATRIX_BOUNDARY 的验证子句改为随 http_targets_verified 切换，未枚举路由表时明确写 NOT verified。矩阵 schema face-matrix-0.2，declared 41 / unaudited 4 / problems 0。
- 2026-11-03 · v0.36.0 · status=pilot · 新增 research_agent/face_coverage.py：以能力为键显式登记 MCP/CLI/HTTP 三面由谁服务，并且每条声明都要经得起核验——cli 必须存在于程序化遍历 argparse 得到的 241 条命令路径里，http 必须存在于 create_app().routes 的 59 条路由里，写错或凭空造名会被 face_matrix().declaration_problems 报出并被用例判失败。动因是实测：按名字匹配只能配到 45 个工具里的 24 个，正则扫源码只能扫到 59 条路由中的 52 条，因此"某面缺失"与"某面改名"过去无法区分（#55/#40 的部分论断即由此而来）。未核验的能力不再猜，直接计入 unaudited（当前 8 个）并出现在输出里，矩阵自带空洞计数。人类门仍只允许 CLI：用例断言 approve/sign/freeze/publish 不出现在 MCP 工具名中。用例 5 个（含故意写错一条声明应被抓到）。待办：把矩阵经 framework_api.capabilities()/handoff contract 暴露给宿主一次读取，属 #79 剩余步骤。
- 2026-11-03 · v0.35.0 · status=pilot · MCP 工具错误载荷新增 served_build（导入期固定的代码指纹、源文件数、以及与 handoff contract 对照的确切命令）。动因是实测定位过程本身：一个常驻 stdio 服务进程跑的是启动时导入的旧构建，返回了当前代码里根本不存在的报错文本，我把这条误判成两处面的代码缺陷并立了工单，直到 grep 全仓找不到该字符串、重启连接器后同一请求返回与 CLI 完全一致的 0.2 结果才纠正。错误现在自带"是哪个构建产出的"，宿主可立刻判断是代码问题还是进程过期，而不用先怀疑实现。成功载荷不变。新增 tests/test_mcp_stale_build.py：错误载荷指纹与 build_fingerprint 恒等、目录整包经 MCP 面与库面逐项同数、data_files 与 skipped_unsupported_suffix 在两面一致。
- 2026-11-03 · v0.34.0 · status=pilot · adapters.research_models.default_model_for 新增可选 binding 参数并原样转给 _gateway_port（此前参数已存在于 _gateway_port 与 HostModelPort，只是没有任何调用方传值，实测 runtime_data/hm-eval/turns.json 12 条轮次 binding 全空）。契约变化只影响新建轮次的记录内容：host-model 账本不在哈希链上，既有 100+ 研究包的 derivable/match 不受影响。
- 2026-11-03 · v0.33.0 · status=pilot · 整包打分的 bundle 元数据新增 data_files（路径/字节/行数）：.csv/.tsv/.jsonl 这类已发布输出既不进入被打分文本（对上万个数字做词法匹配会把任何条目判为已满足），也不再被计入 skipped_unsupported_suffix 而无声丢弃——ACL/NeurIPS 的"随包发布模型输出"问的正是它们存在与否。实测 digits 完整链包：data_files=[reader/outputs-per-seed.csv, 11751 bytes, 81 lines]，skipped 归零，头部 19/38、制品侧 17/28（0.607）。两面共用同一函数，故 CLI 与 MCP 同步生效（parity 用例通过）。
- 2026-11-02 · v0.32.1 · status=pilot · 整包打分的两处度量自身缺陷被真实数据照出并修好。一、选件顺序：`coverage_input` 原来按路径排序取文件，实测 RUN-REAL-LIT 的 run 目录里 demo.json 有 709 KB，一个内部状态 dump 就把 20 万字符上限吃满，bundle 只剩 3 个文件，manuscript.md / paper.md / innovation-report.md 这些真正给人读的东西**根本没进打分**。现在 prose 类（.md/.tex/.txt）先占预算、JSON 其后，且**单文件上限 40000 字**；bundle 里新增 `order` 与 `max_file_chars` 把这个选择规则写进输出。修好后同一目录 16 个文件 / 106462 字。二、分母只报了打分条目：design 档 19 条扫描条目里有 13 条被 actionability 过滤掉，输出只显示 `items: 6`，于是 "covered 6 of 6" 看起来像满分，而真实情况是 19 条要求里只评了 6 条。coverage 返回体新增 `items_scanned`（实测 covered 6 / scored 6 / scanned 19）。同一目录修前后：writing 11/11 → 9/11（那 2 条本来是大 dump 贡献的），submission 14/23 → 13/23，design 6/6 不变（6 of 19 的真实分数）。动因写进 58- §182。受影响回归 57 条 OK（test_skill_packs / mcp 面同形 / writing_pack / venue_audit），release+workspace+docs 一致性 18 条 OK。只改投影与度量输出，不改判定与签核，升 patch。
- 2026-11-02 · v0.32.0 · status=pilot · research_skill_packs 的 coverage 与 CLI `skill coverage` 现在接受**整个包目录**作为打分单位：新增 `pack_audit.coverage_input(path)`，两面共用；目录输入按扩展名（.md/.json/.txt/.tex）拼接，并在返回体里带 `bundle`（每个文件相对路径与字数、file_count、considered、`excluded_numeric_artifacts`、skipped_unsupported_suffix、max_files/max_chars、truncated、boundary）。三件数值产物 study.json / study-evidence.json / closure-report.json **按名字排除并如实列出**：它们是测量本身而不是关于测量的陈述，逐格浮点与节点清单会主导词面命中却不回答任何 rubric 问题，而同样内容已由我们自己的代码投影进 README 与简报。上限 16 文件 / 200000 字，超限报 truncated 而不是静默少读。
  动因是 §179 的实测：审稿人读的是包，单文件打分系统性低估自己——预注册单独 design 0/6，bundle 3/6（另 1 条 near-miss）；README 单独 submission 命中 1（同档打分条目 23 条），bundle 命中 **8/23**；writing 4/11；reproducibility 2/4 并被 §0.31.0 的薄分母警告如实标出。第一次实现还把 study-evidence.json 收了进来，20 万字符上限被一个数字块吃满（chars 200009、truncated=True、只装了 10/11 个文件），于是分数虽然涨了、打分单位却成了一堆浮点——这正是排除名单要打印出来的理由。
  用例：`BundleInputTest` 3 条（目录打分与拼接清单与排除名单与跳过计数、单文件输入仍不产生 bundle 字段、超长目录如实报截断且不越上限）。三面同源由 `tests.test_mcp_skill_packs_parity` 继续钉住；输入形状与输出字段属契约变化，升 minor。advisory 只读，不执行脚本、不联网、不签核。
- 2026-11-02 · v0.31.0 · status=pilot · research_skill_packs 的 coverage 现在自带分母质量：返回体新增 `thin_denominator` 与 `items_required_for_verdict`，并在薄分母时写入 warning。动因是拿真实 pack 做阶段矩阵实测：同一个 ACL-Skills 根，idea 档只产出 **1** 条可打分条目，而 design 19、writing 21、submission 43、review 58、reproducibility 10；跨 venue 比，idea 档密度是 EACL 7 / NeurIPS 4 / AAAI 3 / ACL 1 / NAACL 1（7 倍差）。于是『S2 想法产物对 ACL 想法 rubric 覆盖 0/1』这种读数**不是对阶段的判定，而是 pack 路由的产物**——把 0/1 当缺陷写进论文或写进改进计划都是自伤。空清单本来就已经是 unusable，但 1–4 条这种薄分母过去会以 conf=ok 呈现；现在 conf 仍是 ok（分数照给），同时必须带一条明写『这不是对阶段的判定，先跨 venue 扫同一阶段再引用比率』的警告。用例：ThinDenominatorTest 3 条（5 条不打薄分母警告、1 条打且措辞含 only 1 actionable item、空清单仍是 unusable 而非 thin）；tests.test_skill_packs + mcp parity + writing_pack + venue_audit 共 54 条全绿。同一份用例还修正了一条旧断言：原来要求同脚本零覆盖时 warnings 必须为空，现在断言不得出现脚本/语言类警告即可，薄分母警告与该用例的主张无关。advisory 只读，门禁与签核面未移动。

- 2026-11-02 · v0.30.0 · status=pilot · v0.30.0 aligns the research_skill_packs input schema with what its handler now does: max_items default 200 as on the CLI, pack_dir documented as optional when pack_root plus venue route a pack, and pack_root plus venue documented for scan and coverage rather than for route only. A parameter that exists in the schema but is ignored by the action is not discoverable, so the description now states which actions read which argument.
- 2026-11-02 · v0.29.3 · status=pilot · The faces block moved into the shared preflight builder so CLI and HTTP return the same shape, and the HTTP count is now measured by the serving process instead of copied from the MCP list: the CLI reports http_tools=null with a note saying it did not measure that face. Counting a face by inference is the proxy-signal failure this module exists to catch, and I introduced it in 0.29.2.
- 2026-11-02 · v0.29.2 · status=pilot · Runtime adds GET /api/research/preflight so the governance chain state is visible to the web app as well as the CLI and MCP faces; it returns the three face counts (MCP tools, HTTP tools, CLI commands) and the same bookkeeping-only boundary. A test asserts the HTTP and MCP tool counts are equal, which is the first machine-checked cross-face size guard, and that the boundary states the UI cannot execute anything through it. The web app gains a read-only GovernancePanel in the context column that renders SPEC-to-changelog coverage, registry freshness, tool-surface agreement and blockers, with an explicit unavailable card when no runtime is reachable.
- 2026-11-02 · v0.29.1 · status=pilot · MCP face gains research_study_baseline so the budget-matched tuned reference is reachable from a host agent as well as the CLI: 45 tools with TOOLS/TOOL_NAMES parity, the study budget still caps the fold count server-side, and unknown arguments are rejected rather than dropped.
- 2026-11-01 · v0.29.0 · status=pilot · New CLI-only governance preflight (workspace preflight) answers in seconds which link of the SPEC/export/tool chain is stale: SPECs whose frontmatter version has no Changelog entry, an exported agent registry behind the live SPEC projection, and MCP TOOLS vs TOOL_NAMES vs the integration SPEC tools list. It exists because a killed command chain once left a version bump unwritten and the only detector was the full suite minutes later. It reports bookkeeping and says so: fresh does not mean behaviour is correct, and it never mutates anything.
- 2026-11-01 · v0.28.5 · status=pilot · Provenance warns when no draft directory was excluded, because the default corpus otherwise lets a value trace back to the draft own copies; both faces go through provenance_for_draft, which excludes the draft file.
- 2026-11-01 · v0.28.4 · status=pilot · MCP face gains research_number_provenance so the number trace is isomorphic with the CLI: same library, same fields, 44 tools with TOOLS/TOOL_NAMES parity, unknown arguments rejected rather than dropped, and the draft file excluded from its own corpus.
- 2026-11-01 · v0.28.3 · status=pilot · MCP research_writing_pack description now states that the returned pack includes the reproduction map with the rebuilt re-run command.
- 2026-11-01 · v0.28.2 · status=pilot · MCP research_skill_packs artifact description now states that the coverage input may be a JSON artifact or a Markdown/TeX/plain-text draft, matching the shared reader.
- 2026-11-01 · v0.28.1 · status=pilot · MCP tools/list for research_venue_audit now names the optional skill-pack rubric arguments in its description; before this the six pack parameters existed in the schema but the description still promised only the structural audit, so a host reading tools/list had no reason to try them. No behaviour change.
- 2026-11-01 · v0.28.0 · status=pilot · research_venue_audit 的 inputSchema 与 allowlist 补齐 skill_pack / skill_pack_root / venue / skill_stage / skill_profile / skill_max_items，宿主面与 CLI 面首次同构；pack 路径相对服务器根解析，仍不执行脚本、不联网、advisory。tests.test_mcp 新增同构断言（MCP 调 venue_audit 带 pack 时必须返回 skill_pack.coverage.pack_scope，且 checklist_total 与 skill_pack.checklist_total 一致，schema 必须声明这五个参数）。契约变化升 minor。
- 2026-11-01 · v0.27.0 · status=pilot · MCP 面新增两个只读工具：research_skill_packs（action=scan｜route｜coverage，把外部期刊 skill pack 的扫描、venue 路由与 rubric 覆盖度交给宿主 agent；coverage 永远带 pack_scope 的分母，截断时 boundary 自报 partial rubric；不执行脚本、不联网、advisory）与 research_mandate_status（项目级持续委托投影，7 个阶段字段 + MANDATE_SCOPE_TRUNCATED 的诚实视野）。工具数 41→43，README/QUICKSTART/ARCHITECTURE/integrations 计数由 test_docs_freshness 强制同步。契约新增两个工具与其边界，升 minor。门禁不变：仍然没有签核、批准、冻结、闭包签署、发布或导出端点。
- 2026-11-01 · v0.26.3 · status=pilot · 发行目录改为构建产物：新增 scripts/build_release.py（sync / --check / --prune），Wellspring-Agent 由仓库根生成，MANIFEST.txt 逐条记录 relpath+sha256+bytes；被拒路径含包内运行数据 research_agent/web/data、第三方本地态 vendor/astradraw/.local 与 output/docs、以点开头的文件。实测把发行体积从 236 MB 降到 14.7 MB，并阻止本地实验数据随开源包外发。新增 tests/test_release_integrity.py 三项：MANIFEST 与磁盘逐项一致、渲染器在包内且不含运行数据、发行目录与仓库根零漂移。
- 2026-11-01 · v0.26.2 · status=pilot · runtime 的 artifact 列举改为容忍 TOCTOU：JobManager.artifacts 里 is_file() 与 stat() 之间条目消失（清理、扫描器或并发写）此前会把列举变成 500，现在 size 读取包住 OSError 并跳过该条目——列一份产物清单不该因为其中一个文件正在消失而整体失败。补 tests.test_runtime 的 racy stat 回归测试（第一次 stat 通过、第二次 ENOENT）。内部健壮性，契约字段与人工门边界不变。
- 2026-11-01 · v0.26.1 · status=pilot · next_actions 在缺 task.json 但存在 loop-capsule 的 run 上，改为返回 capsule 里的人门命令，不再只回一句去读目录；无 capsule 或 capsule 无命令时仍回落 inspect。实测 claim-draft-ui/RUN-UI-CLAIM 由 1 条 inspect 变 4 条可执行命令（G1/S5b/G5/S8-S12）。新增 tests/test_next_actions_fallback.py 2 项。
- 2026-10-31 · v0.29.7 · status=pilot · 基金模板只有 CLI，Qoder/MCP 不能在项目内生成可填写的 grant 骨架。新增只写 scaffold 的 research_grant_template（project_dir/scheme/output），复用 grant.template 的 grant-draft-0.1；不生成科学观点/预算/签名/提交，输出路径受 project_output_path 限制。新增 3 项 MCP 测试；工具数 41。
- 2026-10-31 · v0.29.6 · status=pilot · Qoder/MCP 需要中文期刊与基金申请检查：新增只读工具 research_venue_audit（kind=zh_journal|grant），中文期刊检查摘要/关键词/章节/参考文献/基金/创新/数据，基金检查 NSFC/NSSFC 模块、创新点、证据、活页匿名与 AI 声明。工具不写稿、不签名、不提交；无 approve/sign/freeze/export 入口。新增 tests/test_venue_audit_mcp.py 4 项。
- 2026-10-31 · v0.29.5 · status=pilot · 工作台看不到 CCF-A 设计级别：capsule 的 S4 只读 demo.modules.study_design，而真实 run 的设计审计落在 run 目录的 study-design.json/study-design-audit.json，导致 ContextPanel 的 status/ccfa_level 为空。现在 demo 缺失时回退读取 run 级两份文件；实测 RUN-REAL-LIT 的 S4 显示 study_design_status=attention、ccfa_level=evidence_ready。新增 1 项回归测试。只读投影，不改审计。升 patch。
- 2026-10-31 · v0.29.4 · status=pilot · 工作台只显示第一个可判定 study 的人工门：capsule 在追加 S5b 后 break，IDEA-01 之后 IDEA-03 的更强 claim 不可见；去掉 break 后又把 STUDY-IDEA-03-iris 复现包当成独立 claim。现在为每个 idea 的**基础包**（STUDY-<idea>）各追加一个 S5b；STUDY-<idea>-<dataset> 复现包只作证据、不追加。实测 RUN-REAL-LIT 显示 IDEA-01 与 IDEA-03 两个 S5b，iris 复现包不出现。只读投影，不创建 claim。升 patch。
- 2026-10-31 · v0.29.3 · status=pilot · 工作台的 next_actions 只显示 run 级门，idea→study 的人工 S5b 只存在于 CLI loop status：capsule 不读 studies/*/closure-report.json，所以同一份证据在 CLI 显示“draft and sign the claim”，在工作台看不到。现在 build_loop_capsule 扫 <project>/studies，若某包的 has_decidable_comparison=pass 且 claim.present=fail，追加一个 owner=human、gate=S5b、命令为 study claim 的 next_action；非结果包不追加。新增回归测试。只读投影，不创建 claim。升 patch。
- 2026-10-30 · v0.29.2 · status=pilot · 研究设计披露成为 G2 条件：pipeline 在 study-design-file 审计结果为 incomplete 时把 G2 标 blocked、整体 status 降为 needs_human；loop-capsule 的 S4 节点带 study_design_status/ccfa_level/前 5 条 blockers，并新增 STUDY_DESIGN_INCOMPLETE blocker 与 G2 next action（重跑 design audit --strict）。实测 ccfa-gate-probe（模板设计）：G2 blocked、S4 blocked、胶囊 blockers 含 STUDY_DESIGN_INCOMPLETE；v7（Qoder 设计）为 ready_for_g2/disclosure_complete，不阻断。tests.test_loop_capsule 6 项、test_pipeline 27 项 OK。门禁语义变化：新增一个阻断条件，升 minor。
- 2026-10-30 · v0.29.1 · status=pilot · pipeline 新增 --study-design-file：读取 study-design.json，跑 CCF-A 披露审计，把 design+audit 放进 demo.modules.study_design，并传给论文 setup 段；--resume-dir 会从 run 目录拾取 study-design.json。本地 run 设计仍是 experiment.json，两者不再混用。实测 v7：study_design audit 写入 warnings，论文 setup 段为研究设计。tests.test_pipeline 27 项、test_cli 通过。新增输入，升 patch（兼容旧调用）。
- 2026-10-30 · v0.29.0 · status=pilot · 工作台能看见全自动：runtime 新增只读 GET /api/autopilot-status?project_dir=...，返回 autopilot_snapshot（schema autopilot-snapshot-0.1）：policy id/hash/authorized_by/expires、status/stopped_at/reasons、逐步 steps、claim id/断言、signature id/report、bundle 相对路径与 verified、lineage、delegation 与最近 5 条历史；所有绝对路径剥离，端点不提供任何触发能力。实测 runtime_data/autopilot-e2e 返回 completed / AUTO-f275d62f45 / bundles/RUN-AUTO-E2E / verified=True；真实 DOM 在 CLOSURE PROFILES 下渲染 AUTOPILOT 条带；tests.test_runtime_api 4 项 OK。新增只读端点，升 minor。
- 2026-10-30 · v0.28.5 · status=pilot · 闭环状态不再自相矛盾：loop_capsule 改为同时读取 closure/closure-report.json 与 closure-signature/signature.json，closure ready 但未签名时新增 CLOSURE_UNSIGNED 并给出 closure sign 命令，G5 只有签名后才 pass（delegated 与 human 分开写 reason），S13 只有签名后才 done，S5 的 claim_status 会报 signed。autopilot 在封装完成后重写胶囊，避免流水线在签名前写下的旧状态残留。另修一个会掩盖旧代码的缺陷：build fingerprint 原先每次调用都重读磁盘文件，长期运行的 MCP 进程会报告“当前文件”的哈希却仍在执行旧模块；现在固定为进程启动时导入的代码，MCP 服务初始化即定值。实测 runtime_data/autopilot-e2e：胶囊 blockers 只剩 WRITING_AUDIT_BLOCKED 与 FIXTURE_ONLY，G5=pass(delegated)，S13=done，claim_status=signed；真实 DOM 显示 claim=signed · sig=delegated；tests 中 loop_capsule 5 项、autopilot 9 项、closure_profiles 16 项 OK。升 minor（新增 blocker 名称与节点状态取值）。
- 2026-10-30 · v0.28.4 · status=pilot · 宿主拿到的下一步命令不再比它读过的草稿弱：loop_capsule 在 CLAIM_UNSIGNED 的 S5b next_action 里填入草稿真实的 scope，并在 assertion_proposal 存在时追加 --assertion（原先 scope 是占位符、断言完全缺失，宿主照抄就会签一个没有数字口径的 claim）。statement 与 human-reason 仍是占位符。实测 runtime_data/claim-draft-ui 的 research_status 返回 --scope S5/demo/iris --assertion metric=accuracy,value=0.9111...；tests.test_loop_capsule 4 项 OK（新增一项）。仍是人类执行的命令，不签核，升 patch。
- 2026-10-30 · v0.28.3 · status=pilot · 插件说明书补上它能执行的那一步：plugin_bundle 生成的 SKILL.md 第 5 步不再只说“展示 CLI 命令”，而是指明具体 run 的逐字命令来自 research_status 的 closure_profiles.canonical_run[].claim_draft.command（项目相对路径，已带建议 --assertion，签署后消失）。原因是宿主没有别的途径知道命令在哪，原来那句话等于让它猜。plugin export 重新生成 6 个文件，plugin verify 报 in_sync=true；tests.test_plugin_bundle 新增一条断言，防止说明书退回空话。仅生成文本变化，契约不变，升 patch。
- 2026-10-30 · v0.28.2 · status=pilot · 0.28.2（2026-10-30）：开始还工程债——把宿主面向的两个命令族从 5000 行的 cli.py 里切出去。新增 research_agent/cli_host.py（print_json + handoff/plugin 处理器 + add_host_parsers），cli.py 只保留 import 与一次 add_host_parsers(sub) 调用；import 图保持单向（cli_host 不 import cli）。等价性用派生清单做逐字节校验：切分前后 CommandRegistry().snapshot()["commands"] 完全相同（173 条），因为清单本来就是从 argparse 树派的——这正是上一轮把清单改成派生换来的能力。实测 handoff contract（blocked=[]）、plugin verify（in_sync=true）、spec list/show --body 均正常，tests.test_cli/test_specs/test_workspace/test_handoff/test_plugin_bundle 46 项 OK。过程中的一次自我失误：按行号区间删除时把同区间内的 spec 四个处理器一并删掉（CLI 启动即 NameError），已按 parser 的参数与 SpecStore API 重建并跑测试确认。契约未变，升 patch。
- 2026-10-30 · v0.28.1 · status=pilot · 0.28.1（2026-10-30）：续跑不能改变结论。实测 --resume-dir 只拾取 g1/协议/claim/run 与（本轮新增的）idea/design，**漏掉了已验证的 bibliography 卡片**：同一个 run 续跑后预审从 1 项 blocker 退回 2 项（references.verified 又出现），看上去像"新跑一遍发现了问题"，实际是续跑丢了一个输入。修复：_resume_pipeline_inputs 增加 bibliography.json / inputs/bibliography.json 的拾取；实测续跑后的 manuscript-audit blockers 与原 run **逐项相同**（同为 results.signed_claim），human_gates 也一致（G1 pass / G2 pass / G5 blocked）。tests.test_pipeline 24 项 OK（新增 ResumeInputsTest 两项：卡片存在时必须被拾取、不存在时不得凭空造一个）。契约变化：续跑输入集合增加一项。
- 2026-10-30 · v0.28.0 · status=pilot · 0.28.0（2026-10-30）：把"平台宿主免 API key、CLI 客户端要配 key"写进插件包本身。manifest 新增 model_supply 三段：host_supplied_no_api_key（平台宿主自己当模型，生成阶段返回 pending ModelTurn，宿主用 research_model_respond 或 handoff 作答后重跑，api_key_required=false）、client_configured_key（没有能作答的 agent 的纯 CLI 客户端，绑定一次带 key 的 profile）、if_neither（既不供模型也没 key 时以 blocked=model_stages_suspend_without_a_host_model 停住，而不是悄悄产出更弱的草稿）；每段都带 detect 命令。SKILL.md 第 4 步同步改写：在 Qoder 这类平台上"你（宿主）就是模型，不需要任何 API key"；纯 CLI 则绑一次 keyed profile。实测两种声明下的协商结果：can_call_tools+can_serve_model → blocked=[]（免 key、无阻塞）；只声明 can_call_tools 或 can_call_tools+can_write_files → blocked=[model_stages_suspend_without_a_host_model]（因为没有可作答的宿主模型）。契约变化：插件清单新增只读字段与 SKILL 指引，运行期判定未动。
- 2026-10-30 · v0.27.0 · status=pilot · 0.27.0（2026-10-30）：门后继续真的能继续了。为了让 G1/G2 在后续 run 里仍然成立，新增两个复用输入 --idea-file 与 --design-file（--resume-dir 也会自动从 run 目录拾取 idea.json / experiment.json）：G1 决策绑定的想法集合与 G2 冻结协议绑定的设计都不再重新生成，报告里会写明"reused from <file>，本 run 不重新生成"。同时修三处真缺陷：(1) protocol freeze-design 对 seeds 为列表的设计直接崩（TypeError），现在统一走 contracts.seed_count()，列表取长度、数字原样、其余干净报错；同一个崩溃在 paper 的确定性草稿（%d 格式化）与 evidence_packages（int()）各有一份，一并收敛到同一助手，避免"同一个形状在不同消费者处各写一遍"。(2) G1 通过后 idea.json 仍写着 candidates_need_human，导致 loop-capsule 同时出现 G1 pass 与 G1_IDEA_SELECTION_REQUIRED 两个互相矛盾的结论；现在通过 G1 时把 idea 状态置为 selected 并标出选中卡片。(3) --idea-file/--design-file 一开始只加到了 task 的共享 parser，pipeline run 用的是自己的 parser，实测报 unrecognized arguments，已补齐。实测严格模式全链路：flow g1 → protocol freeze-design → pipeline --flow-mode strict（复用 idea/design）跑到 exit 0，human_gates 为 G1 pass / G2 pass / G5 blocked（EA exists but no Claim/Closure），blockers 恰好是 CLAIM_UNSIGNED / CLOSURE_NOT_RUN / WRITING_AUDIT_BLOCKED 三项人工步骤，产物 20 个含 g1-decision.json 与 manuscript。tests.test_pipeline 20 项 OK（新增 G1ResumeTest 用合成 idea 工件验证 selected 状态与胶囊不再要求 G1）。契约变化：新增两个输入与一个状态取值。
- 2026-10-30 · v0.26.2 · status=pilot · 0.26.2（2026-10-30）：实跑照出一处"两个设计被读成一个"的缺口并修掉。用空模型库跑完整 pipeline（runtime_data/loop-check/run，24 个产物）时，S4 草案被 design-audit 判为 incomplete（缺基线/主指标/预算、无对照条件），但研究臂仍按自己声明的 factorial 设计执行并产出三条比较——报告里没有任何一句话说明"执行的不是那份草案"，读者很容易把执行出的数字当成对草案的验证。改为在 pipeline 的研究臂执行后追加 warning，明说执行的是该臂在 dataset 上声明的设计、而非 S4 草案、且草案仍有 N 条 blocker、因此该研究不构成对草案的证据。只加说明，不改任何判定与门禁；tests.test_pipeline 19 项 OK（新增一条断言）。另记录两条我先前的误判：把 literature.json 的 sources 键当作存在而报"0 来源"（真实是 hits=4、spans=1329），以及把 claim-registry 的 10 条候选误当已签 claim（实测 signed=0）——两次都是先核实再下结论才没写错。
- 2026-10-30 · v0.26.1 · status=pilot · 0.26.1（2026-10-30）：规格的工具清单补上 research_host_contract（38 → 39），并把 tests.test_integration_files 里写死的 len(TOOL_NAMES)==38 换成"规格声明的工具集合与实装工具集合相等"。写死数字的断言与本仓库反复批评的手抄清单是同一类毛病：加工具的人必须记得改测试，忘了就得到一个只会提醒自己的假绿；改为以规格为准后，忘记更新 SPEC 会直接失败，这才是"规格是源"的可执行形式。
- 2026-10-30 · v0.26.0 · status=pilot · 0.26.0（2026-10-30）：宿主协商升级为 MCP 工具 research_host_contract（第 39 个工具）。上一轮插件包 SKILL.md 写的是"先协商"，但协商只有 CLI 一条路——不能调用工具的宿主拿不到它，等于说明书里的一句空话（我当时写的是"或 MCP 上的等价物"，那时它并不存在）。现在它真的存在：mcp_tools.TOOLS 新增只读条目（readOnlyHint=true，参数 capabilities 数组 + 可选 outbox_dir 探针路径），ResearchMCPService.host_contract 调用同一个 host_contract() 函数，dispatch 走既有单点。实测通过真实 stdio 服务：tools/list 返回 39 个工具且含 research_host_contract；调用后返回 schema=host-contract-0.1、blocked=[model_stages_suspend_without_a_host_model]、5 个阶段等待宿主作答、6 项人工门、build=7514ed2b8eb1d862。过程记录：第一次插入把 schema 放到了列表头部而名字加在尾部，导致 [t[name] for t in TOOLS] == TOOL_NAMES 不再对齐（该不变量正是清单派生那轮加强的），移到尾部并修掉一处多余逗号后恢复对齐；服务方法第一版的 summary 里硬编码了 0 个 blocker 并且重复计算了一次 contract，改为算一次并如实报告"几种传输可用 / 几个阶段挂起 / 几个 blocker"。tests.test_mcp + test_framework_api + test_plugin_bundle + test_handoff 39 项 OK；插件包重导出后 manifest tools=39 且 tool_names 含新工具。契约变化：MCP 工具面新增一个只读工具（不含任何门禁能力）。
- 2026-10-30 · v0.25.0 · status=pilot · 0.25.0（2026-10-30）：插件包改为**生成物**，不再手写。新增 research_agent/plugin_bundle.py 与 CLI plugin export|verify：manifest.json（入口、38 个 MCP 工具名与计数、CLI 命令计数、prompts、轮次 TTL、六项人工门、边界）、mcp.qoder.json 与 mcp.zcode.json（stdio 片段）、mcp.codex.toml（Codex 用 TOML 的 [mcp_servers.*]，不是 JSON）、SKILL.md（先协商 handoff contract → 选传输 → 答轮次 → 停在人工门）、README.md（各家安装法）。根路径默认写成占位符 <RESEARCH_AGENT_ROOT>，plugin export --root <path> 才落地成绝对路径，因此仓库里提交的是可移植形态。verify 重新派生并逐文件比较，missing/stale/unexpected 三类差异都会报，退出码非 0——把"插件说明书过期"变成测试失败而不是用户踩坑。实测：plugin export 生成 6 个文件、verify in_sync=true；manifest 入口里不含 sign/approve/freeze/publish，human_only 与 host_contract.GATE_VERBS 逐项相等；CLI 命令计数随新命令自动从 171 增至 173（上一轮把清单改为派生的即时回报）。新增 tests/test_plugin_bundle.py 5 项（提交物与派生一致、--root 物化、无门禁权限、SKILL 指引、手工改一个片段会被判 stale 且多出文件判 unexpected）。过程中我自己又踩了一次 Python 3.8 不支持 write_text(newline=) 的坑（生产代码与测试各一次），改为共用 _write 助手。契约变化：新增 plugin 命令组与 plugin/ 产物目录。
- 2026-10-30 · v0.24.1 · status=pilot · 0.24.1（2026-10-30）：把"平台与插件效果一样"从说法变成断言。新增 tests/test_adapter_equivalence.py 三项：(1) 同一串 research_project_init/research_plan/research_run 分别经**进程内 API**（平台路径）与**真实 stdio MCP 服务**（Qoder/Codex/Zcode 插件路径）执行，逐文件比较项目内全部 JSON 产物，只允许剥离实例身份（run/project/task/experiment id、UUID、时间戳、绝对路径），其余必须相同；(2) 反向防呆：两侧文献账本都必须非空，防止"两个空结果相等"这种假通过；(3) 第三种传输（file-drop handoff）与 MCP 对同一请求哈希的回答，落库后 text_sha256 与 text 必须相同，只有 host_label 不同（归属差异，不是内容差异）。实测首轮就抓到三处"差异"，逐字段核对后确认全部是实例身份（临时目录绝对路径与 TASK- id），不是研究内容分歧——于是把剥离规则补全而不是放宽比较。三项 OK，单文件耗时约 3.4 秒。无行为改动，升 patch；这一条是"即插即用"的可执行定义。
- 2026-10-30 · v0.24.0 · status=pilot · 0.24.0（2026-10-30）：更正——上一条目的版本号被误写成 0.16.0（低于既有 0.23.0，等于版本倒退），正文内容不变，此处以正确版本号重记：能力清单从手抄改为派生，并加防漂移测试。workspace.cli_command_surface() 遍历 build_parser() 子命令树产出叶子命令，CommandRegistry.snapshot() = 人工条目(curated=true，保留人写描述与安全分级) + 派生条目(curated=false，safety=catalog_only 自标"未经人工分类、不携带安全承诺")。实测漂移规模：真实 CLI 170 条命令路径 / 37 组，而手抄清单只有 48 条，study / memory / handoff / host-model / benchmark / empirical / project / bibliography / signer / action / research / web 共 12 组对宿主完全不可见——刚交付的复现护栏、留出验证、file-drop 接入插件宿主根本无从发现，而 test_workspace 一直绿（它比的是同一份手抄清单）。前端 safety 联合类型加 catalog_only、SAFETY_LABEL 加"未分类"，tsc --noEmit 通过。新增 CommandCatalogDriftTest 四项（每条命令必须在清单内、曾不可见的组现在必须在、派生条目自标未分类、人工描述不被覆盖）。清单 48 → 170，重导出后 tests.test_workspace 10 项 OK。契约变化：清单产物新增字段与新的 safety 取值。
- 2026-10-30 · v0.24.0 · status=pilot · 0.24.0（2026-10-30）：能力清单从手抄改为派生，并加了一条防漂移测试。实测发现：workspace 导出的 command-catalog 是手工维护的 48 条，而真实 CLI 有 170 条命令路径、37 个命令组——**study / memory / handoff / host-model / benchmark / empirical / project / bibliography / signer / action / research / web 共 12 个组对宿主完全不可见**，也就是说刚交付的复现护栏、留出验证、file-drop 接入这些能力，插件宿主根本无从发现；而 tests.test_workspace 一直是绿的，因为它比对的是同一份手抄清单（恒绿不等于有信息，这是本仓库第三次撞到同一类问题）。改法：新增 workspace.cli_command_surface()，直接遍历 build_parser() 的子命令树产出叶子命令（id/group/label/syntax/description），CommandRegistry.snapshot() 输出 = 人工条目（curated=true，保留人写的描述与安全分级）+ 派生条目（curated=false，safety=catalog_only 明确声明"未经人工分类，不携带任何安全承诺"），并新增 curated/derived 计数。前端 CommandRecord.safety 联合类型加 catalog_only、SAFETY_LABEL 加"未分类"，tsc --noEmit 通过。新增 tests.test_workspace.CommandCatalogDriftTest 四项：每条 CLI 命令都必须出现在清单里、曾经不可见的组现在必须在、派生条目必须自标未分类、人工条目的描述不得被派生覆盖。实测清单 48 → 170 条，重导出后 tests.test_workspace 10 项 OK。契约变化：清单产物新增字段与新的 safety 取值。
- 2026-10-30 · v0.23.0 · status=pilot · 2026-10-30 · v0.23.0 · status=pilot · 接入点自证版本：paths.build_fingerprint() 对包内全部 .py 取哈希（本机 184 个文件 → 7c100540fda2c4fa），经 framework_api.capabilities()["build"] 与 mcp_server 的 research_status 结果载荷同时暴露，含 source_files 与 boundary。动机是实测事故：宿主侧长驻 stdio 服务无法区分"功能没做"与"服务载的是旧码"——本轮 Qoder 的 research_status 已返回 replication/overturned/power_ladders（新字段）却不含 build，而同一服务的 innovation_review 仍报 DeepSeek HTTPError，两个证据互相矛盾、只能靠猜。现在宿主一次比较指纹即可判定。新增测试 test_build_fingerprint_reaches_every_entry_point（tests.test_framework_api + tests.test_mcp 共 21 项 OK）。契约变化：capabilities 与 status 多一个只读字段。
- 2026-10-30 · v0.22.0 · status=pilot · 2026-10-29 · v0.22.0 · status=pilot · 项目目录契约补全：PROJECT_DIRS 加入 studies 与 memory。此前 S5 研究包与 guideline 记忆都写进未声明目录（实测 cp 因缺 studies/ 失败、memory/ 由模块自行 mkdir），等于子系统绕过项目契约落地。project init 现在产出 8 个目录（实测 runtime_data/contract-check：claims closure inputs memory notes project.json protocols runs studies），paths 字段随之声明二者，closure 盘点与 memory 读写的越界校验继续只认项目根。tests.test_cli/tests.test_workspace/test_study_replication/test_guideline_memory 共 40 项通过，全量套件 679+ 项 OK。
- 2026-10-29 · v0.21.0 · status=pilot · 0.21.0（2026-10-29）：research_next_actions 接入研究三态。_next_actions 在任务分支与无 task.json 的原生 run 分支都并入 pending_study_actions 的输出（study_execution 带可直接执行的 from-idea 命令；跑过但区间全跨零 → study_no_finding 明确写出'这是非结果，加种子或收窄主张，不要重跑到绿灯'；有可判定比较 → human_gate S5b 指向 study claim）。执行仍在 CLI，人工门不变，工具数量不变（38）。实测：只含 innovation-review 的 project 连读两次 research_next_actions，中间原样执行 IDEA-01 的命令 → IDEA-01 由 study_execution 变为 study_no_finding，IDEA-02 动作保留。
- 2026-10-29 · v0.20.0 · status=pilot · 0.20.0（2026-10-29）：工作台显示研究结论三态。GET /api/project-closures 的 search_study 行返回 verdict 投影，CLOSURE PROFILES 区块逐项渲染 positive/negative/undecidable/unavailable 与区间，并对跨零区间的正点估计显式写出'不算提升，只是还没判定'；本机对已签名的 iris 研究（2 可判定 / 2 不可判定）核验过 HTTP 响应不含绝对路径。工具数量不变（38），仍是只读投影扩展。
- 2026-10-29 · v0.19.0 · status=pilot · 0.19.0（2026-10-29）：独立评审接入宿主 Agent 入口。research_innovation_review 新增 critic_profiles（role→profile id，未知角色/未知 profile 直接 ProjectError，不再谎报 deterministic template 回退）与 independent（按 critic_panel 排席，供给不足即失败并报缺几个）；_gateway_critic_model 用 strict 解析，把 ModelRequiredError 转成工具错误。同时修正两处过时描述：research_innovation_review 与 research_manuscript_draft 不再写 Requires a model/DeepSeek key —— keyless host_agent 供给同样满足。工具数量不变（38），仍是入参与文案变化。实测：同一 run 走 CLI 与走真实 stdio MCP 产出的 innovation-review.json 逐字节相同（sha 1120fa8e331cad36）。
- 2026-10-29 · v0.18.0 · status=pilot · 0.18.0（2026-10-29）：只读闭包盘点上线。runtime 新增 GET /api/project-closures?project_dir=，返回 detect_project_profiles()（canonical_run / local_experiment / search_study 与 present_profiles），供工作台显示三套 closure profile 的真实状态与下一步人工动作；search_study 条目的 study_dir 改为项目内相对路径，避免把用户绝对路径带上 HTTP。仍是只读：没有 sign/approve/freeze/export 端点，人工门继续在 CLI。工具数量不变（38）。
- 2026-10-29 · v0.17.0 · status=pilot · 0.17.0（2026-10-29）：批评面板与挂起退出码。profile_catalog 现在遵守 RESEARCH_AGENT_MODEL_STORE（此前读内建默认，与 CLI 看到的配置不一致）并内嵌 critic_panel；research_model_profiles 随之返回可成席的角色→profile 建议与缺失供给数；runtime 新增只读 GET /api/host-model/panel；CLI 新增 innovation review --critic role=profile 与 --independent，并把 ModelTurnPending 统一成 exit 3 的交接提示而非 traceback。工具数量不变（38），仍是响应结构扩展；无签核/执行入口。
- 2026-10-29 · v0.16.2 · status=pilot · 0.16.2（2026-10-29）：新增 research_model_void（38 工具）。实测发现答案按请求哈希重放 + 一次性消费会让'JSON 合法但不符合模块深层契约'的答案永久粘住，宿主除了手删文件没有恢复路径；void 只重开请求、不授予任何能力，需写原因并保留原答案哈希。
- 2026-10-29 · v0.16.1 · status=pilot · 0.16.1（2026-10-29）：research_model_profiles 目录增加 keyless/supply 字段与 host_agent_profiles/host_agent_bound_modules；keyless 宿主供给不再计入 diverse_judge_pairs 与 available_profiles（两个宿主 profile 不是两个独立 provider）。只读目录，不返回密钥。
- 2026-10-29 · v0.16.0 · status=pilot · 0.16.0 修正：恢复被 --tool 替换覆盖的 tools 清单，完整登记 37 个工具（含 research_model_turns / research_model_respond）。注意：spec update 的列表字段是整体替换语义，不是追加。
- 2026-10-29 · v0.16.0 · status=pilot · 0.16.0 追加：tools 清单登记 research_model_turns / research_model_respond（37 工具）；均为能力通道，非人工门。
- 2026-10-29 · v0.16.0 · status=pilot · 0.16.0（2026-10-29）：MCP/HTTP/SDK 增加 research_model_turns（只读宿主模型队列）与 research_model_respond（提交宿主生成结果，按请求哈希绑定、形状校验、一次性消费）；共 37 工具。两个工具都不是人工门：不 approve/claim/sign/freeze/publish/export，提交内容仍受写作审计、引用白名单与结果数值上限约束。契约变化：keyless host_agent profile 让生成步骤可以完全不调用外部 API。
- 2026-10-28 · v0.15.71 · status=pilot · pipeline run 新增 --resume-dir：从既有 run 输出目录拾取 g1-decision/protocol/claim/run 产物续跑（显式 flag 优先，resume_sources 回显拾取结果）；不改变任何门禁语义，签核仍在 CLI/人工
- 2026-10-28 · v0.15.70 · status=pilot · `research_status` 的工具说明显式声明只读 `experiment_inventory`，便于外部 Agent 发现项目级 experiment 清单；行为与工具数不变。

- 2026-10-28 · v0.15.69 · status=pilot · `research_status` 新增只读 `experiment_inventory`（项目内所有 experiment 的 stages/next_action/evidence summary）；与 Web `/api/project-experiments` 共用 `list_project_experiments`；不执行、不签核；工具数不变。

- 2026-10-28 · v0.15.68 · status=pilot · 新增只读 runtime 项目级实验链：`GET /api/projects` 与 `GET /api/project-experiments?project_dir=...`，返回真实 stages/next_action/evidence summary，拒绝越界路径；Web EVIDENCE 页显示多 experiment 清单；不执行、不签核、不暴露绝对路径；MCP 工具数不变。

- 2026-10-28 · v0.15.67 · status=pilot · `research_support_panel` 增加可选 `judge_providers`/`require_providers`：记录 provider id 与 distinct_providers，要求至少两个不同 provider；仍是调用方声明配置，不证明输出独立；工具数不变。

- 2026-10-28 · v0.15.66 · status=pilot · 新增 `scripts/setup_mcp.py`：由当前 checkout 生成 `.mcp.json`（拒绝覆盖、支持 `--print`/`--force`），降低 `.mcp.json` 改为忽略后的接入成本；Qoder/Claude 文档改用该入口；工具契约不变。

- 2026-10-28 · v0.15.65 · status=pilot · 开源交付面：`.mcp.json` 改为本机配置并忽略，新增 `.mcp.json.example`；`oss/` 研究快照、Anthropic 参考、`claude-code-main`、`template_refs` 加入忽略；新增 `scripts/release_check.py` 检查交付文档/忽略规则/密钥/本地路径，并补 SECURITY/CONTRIBUTING/THIRD_PARTY_NOTICES/LICENSING；工具契约不变。

- 2026-10-28 · v0.15.64 · status=pilot · `research_support_panel` 增加可选 `judge_families`/`require_families`，把 family 声明与 independence 写入 panel；strict 面板可要求至少两个不同家族；仍不证明 provider 独立、不签核。

- 2026-10-28 · v0.15.63 · status=pilot · loop-capsule 的 S8–S12 读取 manuscript-audit/writing-audit，blocked 进入 WRITING_AUDIT_BLOCKED；无写作审计且已有 paper/实验包时标 WRITING_NOT_STARTED；前端显示真实 audit/submission_ready/blockers。

- 2026-10-28 · v0.15.62 · status=pilot · loop-capsule 扫描同 run 的 `experiments/<id>`，把 evidence/claim/closure/signature 阶段投影到 S5/S13；`research_status`/`research_next_actions` 返回 capsule；TaskAgent 的 S1-only/失败路径也写 capsule。

- 2026-10-28 · v0.15.61 · status=pilot · 新增只读 `loop-capsule.json`：从真实 run 产物派生 S1→S2–S3→S4→S5→S6→S8–S12→S13→META 节点、blockers 与 next_actions；runtime 补 observation/active policy；缺失节点不写成 pass，不创建证据/claim/gate/signature/closure。
- 2026-10-28 · v0.15.60 · status=pilot · `start-research` prompt 增加 hypothesis_design 分支：读取 G1 的 idea/idea_ids，使用 review-idea 展示候选，停在人工 flow g1 前；不代选、不签核。
- 2026-10-28 · v0.15.59 · status=pilot · 新增 `review-idea` MCP prompt：展示 idea 候选/短名单/prior-art/contrast，给出 advisory 对比，停在人工 `flow g1` 前；不写 g1-decision、不签核。
- 2026-10-28 · v0.15.58 · status=pilot · `research_next_actions` 的 G1 动作附带 `idea` 摘要与 `idea_ids`（候选/短名单/prior-art scope），供 Qoder 直接展示选择；不签核。
- 2026-10-28 · v0.15.57 · status=pilot · `research_run` rule idea 增加跨来源 topic-driven contrast（不同 source + topic 词重叠）与 A/B 假设框架；contrast 不进入 evidence_refs，status 候选/短名单记录 has_contrast。
- 2026-10-28 · v0.15.56 · status=pilot · `research_run` rule idea 的 lens 跟随 section（limitation→boundary、evaluation/result→measurement、method→mechanism），未知 section 才轮换。
- 2026-10-28 · v0.15.55 · status=pilot · `research_run` idea 修复 prior-art 自证：live/S1 命中排除候选同 source/同 span；rule candidate 代表/evidence_refs 按 topic 重叠排序；`novelty_status=unverified` 不变。
- 2026-10-28 · v0.15.54 · status=pilot · `research_status` 为每个 run 增加 `idea` 摘要（candidate_count/candidates/prior_art_scope/shortlist_selection/shortlist_ranked/boundary），让 G1 候选在 Qoder 状态面可见；只读。
- 2026-10-28 · v0.15.53 · status=pilot · `research_run` 的 S1 默认开启 `followup_plan`：首轮后按未覆盖面向在剩余 max_sources 内补检索，记录 followup_queries/sources/spans/budget；证据边界不变。
- 2026-10-28 · v0.15.52 · status=pilot · `research_run` 的 idea 产物增加 `IdeaShortlist` advisory 对比（prior-art scope/证据数/跨来源/kill criteria；selection=human_g1）；不评 novelty、不自动选短名单。
- 2026-10-28 · v0.15.51 · status=pilot · `research_run` 的 idea 产物增加 prior-art 上下文与 `prior_art_report`；TaskAgent/pipeline 按候选复用 S1 literature 做 source-scoped live prior-art 搜索，失败回退 S1 最近证据；live 结果不进入 evidence_refs，novelty 仍未核验。
- 2026-10-28 · v0.15.50 · status=pilot · `research_next_actions` 在 human gold 已存在且 draft hash 匹配时返回 `human_gold_ready` 动作（accuracy/disagreements），提示进入人工审阅；不是 peer review 或签名。
- 2026-10-28 · v0.15.49 · status=pilot · `research_status` 为每个 run 增加 `experiments` 摘要（experiment_id/package/stages/next_action），与 `research_next_actions` 的 `experiment_approval` 一致；只读、不 approve/run。
- 2026-10-28 · v0.15.48 · status=pilot · `research_next_actions` 扫描同 run 的本地实验包；未 approve 时返回 `experiment_approval` 动作（experiment_id/package/CLI），MCP 不 approve/run；不签核。
- 2026-10-28 · v0.15.47 · status=pilot · 新增 `review-draft` MCP prompt：已有草稿先 bind，再走 support items/verdicts/section edit（reuse=true）/audit，ledger ready 后生成 human gold 模板并停止；prompt 不执行工具、不签核。
- 2026-10-28 · v0.15.46 · status=pilot · MCP 扩到 35 工具：新增 `research_manuscript_bind`，给已有草稿只附加当前 writing pack marker，正文不变，返回 resolved/unresolved REF；同时 support ledger 不再用 20 字阈值静默丢弃含 REF 的短句（<8 字计入 `skipped_short_cited` 并告警）；不签核。
- 2026-10-28 · v0.15.45 · status=pilot · `research_status` 为每个 run 增加 `support`/`manuscript`/`support_gold` 摘要，并补入未索引的 RUN-* 目录；无 task.json 的 Qoder-native run 标记 `qoder_native=true`、status=`manuscript:<ledger status>`；只读、不签核。
- 2026-10-28 · v0.15.44 · status=pilot · `research_next_actions` 在 support-ledger ready 且 human gold 缺失/过期时返回 `human_gold` 动作：模板未生成则给出 `support-gold-template --ledger`，模板已生成则给出 `support-gold --ledger`；Qoder 不得代填 gold；不签核。
- 2026-10-28 · v0.15.43 · status=pilot · `research_support_verdicts` 写新稿 ledger 前自动归档旧稿 ledger 到 `support-ledger-history/support-ledger-<旧sha前16>.json`，返回 `archived_ledger`；归档只证明存在性与身份，不签核。
- 2026-10-28 · v0.15.42 · status=pilot · `research_next_actions` 感知同 run 的 `support-ledger.json`：partial/blocked/needs_human 或存在 weak_sections 时返回 `support_review` 动作（draft/weak_sections/next_tools，提示 reuse=true）；Qoder-native run 即使缺 task.json 也优先返回该动作；不签核。
- 2026-10-28 · v0.15.41 · status=pilot · MCP 新增 `start-research` prompt（`prompts/list`/`prompts/get`）与 prompts capability：一键文本要求客户端用 `research_bootstrap(run_now=true)` 执行本地 TaskAgent，再走 writing pack → support items/verdicts（reuse=true）→ audit；prompt 不执行工具、不签核。
- 2026-10-28 · v0.15.40 · status=pilot · `research_support_verdicts` 增加 `reuse=true`：按 sentence+evidence 内容键复用同一 `judge_model` 的旧 verdict，只提交变更句，返回 `provided_count`/`reused_count`/`reuse_source` 与逐项 `reused` 标记；不同 judge id 不复用；不签核。
- 2026-10-27 · v0.15.39 · status=pilot · `research_plan`/`research_run`/`research_bootstrap` 支持 `venue_type=software_journal|computer_journal`；TaskAgent 写作 profile 使用外部期刊 Skill brief；不签核。
- 2026-10-27 · v0.15.38 · status=pilot · `research_bootstrap` 增加 `run_now`，在同一调用中通过本地 TaskAgent 执行 bounded `research_run`；不执行外部 Skill 脚本、不签核。
- 2026-10-27 · v0.15.37 · status=pilot · MCP 扩到 34 工具：新增 `research_bootstrap`，一次调用完成初始化、计划、启用 Skill 与期刊 profile 清单；不运行长任务、不调用模型、不执行脚本、不签核。
- 2026-10-27 · v0.15.36 · status=pilot · MCP 扩到 33 工具：新增只读 `research_skill_instructions`，让 Qoder 自己消费已启用外部 Skill 指令，不调用模型/不执行脚本；不签核。
- 2026-10-27 · v0.15.35 · status=pilot · `research_manuscript_audit` 对 software_journal/computer_journal 返回 journal_style 检查（MIT Skill 投影）；只读、不签核。
- 2026-10-27 · v0.15.34 · status=pilot · section edit 支持 `###` 子章节；Qoder-native 二次修订后 supported 从 10 升至 17；不调用模型、不签核。
- 2026-10-27 · v0.15.33 · status=pilot · MCP 扩到 32 工具：新增 `research_manuscript_section_edit`，把 Qoder 写的单一章节安全落盘，拒绝新增 REF/数字与陈旧写；不调用模型、不签核。
- 2026-10-27 · v0.15.32 · status=pilot · support ledger/audit 增加 section_summary 与 weak_sections，供 Qoder 定向修订；只读优先化，不签核。
- 2026-10-27 · v0.15.31 · status=pilot · MCP 扩到 31 工具：新增 Qoder-native 支持评审通道 `research_support_items`（只读项）与 `research_support_verdicts`（记录 Qoder verdicts，不调用外部模型）；审计读取已有 support-ledger；不签核。
- 2026-10-27 · v0.15.30 · status=pilot · support judge 分批调用（默认 8/批，最多 20），长稿审计不再因一次 payload 截断而失败；结果数值检查剥离内部 ID；不签核。
- 2026-10-27 · v0.15.29 · status=pilot · `research_writing_pack` 增加 claim_plan（每个主张一个 ref/span/quote 与 unusable_refs）；只读投影，不签核。
- 2026-10-27 · v0.15.28 · status=pilot · `research_manuscript_audit` 返回多 REF 同句计数/样例与 warning；不改变 ready/blocked，只提示拆句；不签核。
- 2026-10-27 · v0.15.27 · status=pilot · `research_manuscript_audit` 返回未引用事实句计数/样例；默认 warning，`strict_support` 下阻断；排除自指句；不签核。
- 2026-10-27 · v0.15.26 · status=pilot · support ledger 截断显式化：`research_manuscript_audit` 增加 `support_max_items`（默认 80，最大 200），`research_support_panel` 同步；截断时 strict 阻断、非 strict 至少 partial；不签核。
- 2026-10-27 · v0.15.25 · status=pilot · `research_status` 的每个 run 增加可选 `governance` 摘要（panel/gold/writing audit）；只读，不执行、不签核。
- 2026-10-27 · v0.15.24 · status=pilot · MCP 扩到 29 工具：新增只读 `research_model_profiles`，让 Qoder 发现可用 judge profile 与跨 provider 候选对；只返回 profile/model/provider/has_key，不返回密钥、base URL 或路径，不联网。
- 2026-10-27 · v0.15.23 · status=pilot · `research_manuscript_audit` 返回同 run 的 support-gold 摘要（annotators/mean kappa/panel accuracy）；human gold 是 CLI 生成的参照集，不是 closure gate，不改稿、不签核。
- 2026-10-27 · v0.15.22 · status=pilot · `research_manuscript_audit` 感知同 run 的 support-panel：未 ready 或 draft hash 不一致即 blocked，并返回 support_panel 摘要；`research_next_actions` 在 panel blocked/needs_human 时置顶 `support adjudication (human only)` 与 CLI；不签核、不改稿。
- 2026-10-27 · v0.15.21 · status=pilot · MCP 扩到 28 工具：新增 `research_support_panel`，多 judge 审计绑定稿并写分歧账本与人工裁决模板；strict 下未裁决分歧阻断；`research_closure_status` 与 `research_experiment_status` 识别 panel 状态；若 panel 存在，`closure check`/`experiment closure` 要求 ready/not_applicable，手稿须匹配 panel draft hash；不签核、不改稿。
- 2026-10-27 · v0.15.20 · status=pilot · MCP 扩到 27 工具：新增只读 `research_lineage_status`，重算 local experiment lineage 的节点哈希并返回 fresh/stale；不重建、不执行、不签核。同步修正 canonical closure 的 claim 查找（`run/claim/claim.json` 优先）与 next_action：未签 claim 时不再提示 closure sign。
- 2026-10-27 · v0.15.19 · status=pilot · `research_closure_status` 增加只读 presence/SHA-256 证据链与 `chain_fingerprint`；只证明文件存在与身份，不证明正确性、语义蕴含或可投稿。
- 2026-10-27 · v0.15.18 · status=pilot · MCP 扩到 26 工具：新增只读 `research_closure_status`，统一返回 canonical_run/local_experiment 的 closure 状态与下一条人工命令；不执行、不签核。
- 2026-10-27 · v0.15.17 · status=pilot · `research_experiment_status` 增加只读 preflight 阶段；不执行训练。
- 2026-10-27 · v0.15.16 · status=pilot · `research_manuscript_audit`/`research_manuscript_review` 增加 `judge_profile`，用 model gateway profile 做独立支持判断；不签核。
- 2026-10-27 · v0.15.15 · status=pilot · `research_manuscript_review` 增加可选 `ab_check`/`ab_sections`；盲 A/B 偏好原文时拒绝修订；不签核。
- 2026-10-27 · v0.15.14 · status=pilot · MCP 扩到 25 工具：新增只读 `research_empirical_status`，检查 same-run literature/synthesis/innovation/experiment/evidence/claim 前置条件；不执行、不签核。
- 2026-10-27 · v0.15.13 · status=pilot · `research_experiment_status.evidence_summary` 在 evidence 缺失时回退到 spec 计划中的 cv_folds；便于批准前检查。
- 2026-10-27 · v0.15.12 · status=pilot · `research_experiment_status` 增加只读 `evidence_summary`（mean/std、CV、alpha、comparison、results table、data audit）；不执行/不签核。
- 2026-10-27 · v0.15.11 · status=pilot · `research_experiment_codegen` 增加可选 `cv_folds`（0 或 2–10）；只生成代码。
- 2026-10-27 · v0.15.10 · status=pilot · `research_experiment_status` 增加只读 sweep stages/best_alpha；不执行 sweep、不创建 evidence/claim。
- 2026-10-27 · v0.15.9 · status=pilot · `research_experiment_codegen` 的 methods 枚举增加 `random_forest`/`gradient_boosting`；仍只生成代码。
- 2026-10-27 · v0.15.8 · status=pilot · `research_manuscript_audit` 增加 `refresh_support` 缓存刷新；`research_manuscript_review` 的 `revision_mode` 增加 `support` 问题句补丁；不执行、不签核。
- 2026-10-27 · v0.15.7 · status=pilot · `research_manuscript_review` 增加 `revision_mode=full|section|auto`；section 只改目标章节，避免长稿截断；仍不签核。
- 2026-10-27 · v0.15.6 · status=pilot · `research_manuscript_audit`/`research_manuscript_review` 增加 `support_votes`（1–5，多票多数）；仍不执行、不签核。
- 2026-10-27 · v0.15.5 · status=pilot · `research_manuscript_review` 增加 optional `semantic_support`/`strict_support`，把句级支持失败输入评审/修订；不签核、不执行实验。
- 2026-10-27 · v0.15.4 · status=pilot · `research_manuscript_audit` 增加 optional `semantic`/`strict_support`/`strict_pack_binding`，只读检查句级支持与稿-包绑定；模型 key 仅在 semantic 时使用，不执行、不签核。
- 2026-10-27 · v0.15.3 · status=pilot · `research_experiment_codegen` 增加可选 `alpha_grid`（2–8 个正数），只生成 sweep 计划与 `run_sweep.py`；MCP 不执行 sweep、不 ingest、不创建证据。
- 2026-10-27 · v0.15.2 · status=pilot · 只读 `research_experiment_status` 增加 figure freshness；不新增工具、不执行、不签核。
- 2026-10-27 · v0.15.1 · status=pilot · `research_status` 新增只读 `closure_profiles` 盘点（canonical RunCapsule/EA 与本地实验包分别归属不同 profile），并提示对应的人签入口；不新增 MCP 工具，不执行/签核。
- 2026-10-27 · v0.15.0 · status=pilot · MCP 扩到 24 工具：新增 `research_manuscript_ab_review`，对项目内原文/改写稿做匿名 A/B rubric 盲评并落盘；`research_manuscript_revise` 新增 `goal`/`review_file`/`plan_file`/`auto_plan`，支持 section-level plan 与评审驱动改写。
- 2026-10-27 · v0.14.0 · status=pilot · MCP 扩到 23 工具：新增只读 `research_experiment_status`，一次返回实验 spec/data/code/approval/execution/evidence/claim/closure/signature/lineage freshness 与 next action；不执行、不签核。
- 2026-10-27 · v0.13.1 · status=pilot · `research_manuscript_revise` 新增 `goal`/`review_file`：把改写目标和评审 must_fix 送入逐段修订；修复双层 JSON、整节输出与 Figure/Table 中英互译的误判。
- 2026-10-27 · v0.13.0 · status=pilot · 本地实验闭环接入：writing pack/audit 支持 `experiment_id`，读取 verified evidence 与人签 claim；实验 approve/run/ingest/claim/closure/sign/lineage 仅本地 CLI；MCP 仍只做 codegen，不执行训练、不签核。
- 2026-10-27 · v0.12.1 · status=pilot · 写作包/手稿审计支持 `experiment_id`：读取 verified experiment-evidence 与人签 claim，未签核时阻断结果数值；MCP 仍不执行训练、不签核；实验执行/approve/claim 仅本地 CLI。
- 2026-10-27 · v0.12.0 · status=pilot · MCP 扩到 22 工具：新增 `research_experiment_codegen`，从 S4 设计和项目内 CSV 生成自包含实验包（spec、确定性 runner、requirements、README、code manifest）；只生成代码，不执行、不装依赖、不创建 EA/Claim；自动启动/探索执行仍是 roadmap。
- 2026-10-26 · v0.10.1 · status=pilot · 启动器增加 Windows 用户环境变量回读：Qoder/Zcode 子进程即使未继承 shell key，也能从 HKCU\Environment 读取 `DEEPSEEK_API_KEY` 等名称；key 不写入项目、MCP 配置或日志。
- 2026-10-27 · v0.11.0 · status=pilot · MCP 扩到 21 工具：新增 `research_literature_synthesis`，把多篇全文归并为主题×来源矩阵（每主题至少 2 篇、未使用来源显式记录）；写作包、创新评审与中文初稿共享该矩阵；手稿审计新增正文来源多样性检查（≥5 个不同 REF、单一来源 ≤60%）；
- 2026-10-26 · v0.10.0 · status=pilot · MCP 扩到 20 工具：新增 `research_conference_fetch`（按 venue/year 抓取 arXiv 公开 PDF，过滤 workshop/preprint/非 agent 标题）、`research_innovation_review`（提案→novelty/evidence/feasibility 评审→修订→再评审）、`research_manuscript_draft`（证据包+创新评审→中文综述/立场初稿→确定性审计）、`research_manuscript_review`（rubric 评审→修订→再评审，审计不变差才接受）；都不创建 Claim/EA/gate，conference venue 来自 arXiv comment 且未独立核验。
- 2026-10-26 · v0.8.1 · status=pilot · 新增 `scripts/research_mcp_server.py` 固定启动器：把 cwd 与 import path 钉在本仓库，Qoder 等客户端即使从自己的安装目录启动也不会导入旧 `research_agent`；`.mcp.json`、Qoder/Zcode 示例与注册记录改用启动器，并加 `PYTHONIOENCODING=utf-8`；工具契约不变。
- 2026-10-26 · v0.8.0 · status=pilot · MCP 扩到 16 工具：新增 `research_writing_pack` / `research_manuscript_audit`，把 run 压成带真实来源卡、span 与写作契约的写作包，并在成稿后审计引用键/结果数值/章节/占位符/fixture；未签核 claim 不发布结果数值；`submission_ready` 始终 false；修复本文件 frontmatter 的 YAML 缩进。
- 2026-10-26 · v0.7.0 · status=pilot · MCP 扩到 14 工具：新增 `research_literature_fetch`，显式 allow_network 搜索/下载 arXiv 公开 PDF 到项目 inputs；下载后仍走 local PDF 解析与 Q0，不把摘要当全文。
- 2026-10-26 · v0.6.0 · status=pilot · MCP 扩到 13 工具：新增 `research_figure_templates`/`research_figure_render`，从项目 scene 或 vendored AstraDraw 模板生成 SVG/PNG/audit/manifest；模板仅视觉先验，不改原 AstraDraw 文件夹；Qoder 可直接调用。
- 2026-10-26 · v0.5.0 · status=pilot · 新增框架无关能力层：`ResearchAgentAPI`/`ResearchAgentClient`、`/api/research/capabilities`、`/api/research/tools/{tool}`、OpenAI function schema 与框架接入示例；MCP/HTTP/Python 共用工具契约；HTTP 非 loopback 需 token；人类门边界不变。
- 2026-10-26 · v0.4.0 · status=pilot · MCP 扩到 11 工具：新增 `research_manuscript_revise`，项目内已有手稿 + 数据 → 修订/指标/图/审计/MD/TeX/DOCX/PDF；无 profile 为 copy mode，submission_ready 始终 false。
- 2026-10-26 · v0.3.0 · status=pilot · MCP 扩到 10 工具：新增 `research_skill_list` 与 `research_skill_distill`，`research_skill_invoke` 支持成功调用后蒸馏为 project notes 下的 disabled 候选；MCP 仍不执行外部 scripts、不自动启用；演示覆盖 list→distill→list。
- 2026-10-26 · v0.2.0 · status=pilot · 新增 MCP 工具 `research_skill_invoke`：调用已启用、无 scripts 的外部 SKILL.md，输出不可信 advisory；不执行脚本/工具/网络，不写 Claim/EA/gate；可选把 advisory 写入项目 `notes/skill-invocations/`。
- 2026-10-26 · v0.1.0 · status=pilot · 首个通用 MCP stdio 集成：项目目录、7 个安全工具、Qoder/Claude Code/Zcode 技能与配置、真实 stdio 演示；无 sign/approve 工具。

---
title: Research Skill 调研精读：9 个仓库的机制对照与本项目落地
date: 2026-10-26
status: implemented subset + roadmap
scope: S0–S16, SkillLab, MCP, manuscript/source ledgers
related: [34, 40, 45, 46]
---

# Research Skill 调研精读

> 本文是调研与阶段性落地记录；当前工具数、扩展边界和已验证能力以 [`ARCHITECTURE.md`](ARCHITECTURE.md) 与 [`组会汇报-科研智能体进展与下一步.md`](组会汇报-科研智能体进展与下一步.md) 为准。文中的“下一步”不代表当前已支持。

对 `D:\Users\20691\Downloads\Research Skill调研` 下 9 个仓库（21,705 个文件）做了分层精读：README / SKILL.md / 契约 / 核心脚本 / 测试与评估。不是照搬提示词，而是抽取可被 Python 代码强制执行的状态机、账本和门禁。

## 1. 九个仓库各自在解决什么

| 仓库 | 核心贡献 | 最值得借鉴的机制 |
| --- | --- | --- |
| `CCFA-Skills-main` | 17 个 CCF-A 论文流水线技能 + 40+ venue LaTeX 模板 | artifact ownership、idea rubric、experiment discipline、integrity/submission checker、revision ledger |
| `academic-research-skills-main` | 5 个技能、8 阶段论文流水线、~150 个验证脚本 | claim registry、evidence row 协议、citation resolver、held-out eval、block-anchored revision |
| `Auto-claude-code-research-in-sleep-main` | 87 个自主科研技能、10 个 MCP bridge | run state/resume-forward、evidence_check、forensics obligations、bounded fan-out、auto-review loop |
| `scientific-agent-skills-main` | 177 个科学技能、518 个脚本 | claim/evidence marker、citation ledger、statistics reproducibility、skill repo contract linter |
| `ECC-main` | 311 个 canonical skills、跨宿主投影、hooks/schemas | 单一 canonical skill + 自动投影、agent IR、hash-chained capsule、adversarial review |
| `deer-flow-main` | super-agent harness、deep research、systematic review | subagent capacity/turn budget、immutable context snapshot、report receipt contract、artifact handles |
| `last30days-skill-main` | 30+ 社媒源的近 30 天检索 | 明确时间窗、date_confidence、过期证据降权、freshness 重取 |
| `reverse-skill-main` | 网络安全/逆向路由 | 授权 scope gate、Evidence→Finding→Path 证据图、只读 case audit |
| `claude-skills-main` | 398 skills、research pack、markdown/doc 工具 | deep-research source cards、litreview 预算/计数、确定性 classifier、md→AST→HTML 渲染 |

星数对照（GitHub API，2026-10-26）：scientific-agent-skills ≈54.6k、nature-skills ≈50.6k、Auto-claude-code-research-in-sleep ≈18.1k、AI-Research-SKILLs ≈14k。星数不是质量证明，但能反映这些机制的社区验证度。

## 2. 关键原始机制（精读摘录）

### 2.1 Artifact ownership / gate contract（CCFA）

`CCFA-Skills-main/ccf-common/references/artifact-contracts.md`：

- 一个 purpose 只允许一个 canonical artifact；普通迭代原位更新，不生成 `v2`/`final-final`；
- 先写临时 sibling，再原子替换；失败构建不得截断上一版；
- 每类 artifact 有明确 owner；review 只给建议，不能直接改 manuscript；
- gate 不是“工具跑完”，而是有 required evidence、pass condition、blocker、owner。

对我们是直接约束：`pipeline.py` 已用原子 JSON 写、canonical 文件；但 gate 仍只有 status/reason，没有 evidence hash/owner。下一阶段应补 gate ledger。

### 2.2 Claim registry + evidence rows（ARS / scientific-agent-skills）

- `academic-research-skills-main/shared/references/evidence_row_protocol.md`：每个 `(claim_id, ref_slug, anchor)` 一行；quote 必须能在持有的 source text 中精确重放；excerpt 有字节 span 与 SHA-256；错误状态必须显式，不能把 placeholder 当 excerpt。
- `academic-research-skills-main/scripts/claim_registry_coverage.py`：只做词法候选检测（引用句/定量句），覆盖率与 semantic completeness 分开；partial registration 仍是 unresolved。
- `scientific-agent-skills-main/skills/scientific-writing/scripts/audit_claims.py`：`[claim:C001]`、`[evidence:E001]`、claim_text_sha256、evidence manifest；`supported` 无 evidence ID 直接无效。

本轮已落地到 `research_agent/manuscript.py`：

- 每个引用句/定量句/结果句生成 `CLM-...`，记录 sentence SHA-256、candidate_kinds；
- 每个 citation token 生成 claim×ref×anchor row；span anchor 带 `quote` + `span_sha256`；
- source-level 引用无精确 anchor 只标 `source_only`，不冒充已验证；
- 词法覆盖率与 `semantic_completeness=unknown` 分开，避免把“检测到的句子”说成“全部语义 claim”。

### 2.3 Source cards / screening / recency（claude deep-research, deer-flow, last30days）

- `claude-skills-main/research/deep-research/skills/deep-research/SKILL.md`：每个来源一个文件，至少 3 个不同类型来源，必须有 adversarial pass。
- `deer-flow-main/.../report_contract.py`：`[rN]` receipt citations、可验证 handle、显式失败。
- `last30days-skill-main/skills/last30days/scripts/lib/dates.py`、`fusion.py`：明确时间窗、`date_confidence`、窗口外证据严格降权。
- `academic-research-skills-main/sr-screener/SKILL.md`：筛选计数、排除原因、kappa/PABAK、每个数字可回溯到文件。

本轮已落地 `research_agent/literature_ledger.py`：

- 来源卡：标题/年份/venue/DOI/URL/license/full_text/fixture、source_type（preprint/venue_indexed/unknown）、peer_reviewed=unknown；
- 筛选计数：found / included_full_text / abstract_only / duplicates / metadata_incomplete / with_locatable_span；
- 元数据覆盖、DOI 覆盖、近五年分布、source type 分布；
- 不把 metadata/venue 当作 claim support；peer_reviewed 始终 unknown。

### 2.4 Run state / resume-forward / bounded fan-out（ARIS）

- `Auto-claude-code-research-in-sleep-main/tools/run_state.py`：phase 状态 pending/running/done/failed/skipped/accepted/provisional；resume 跳到第一个非 terminal phase；`accept()` 要求 verdict id 与实际 reviewer。
- `.../tools/forensics_gate.py`：obligations 只追加，flags 可计算，acquittal 不能自动发生。
- `.../skills/shared-references/fan-out-pattern.md`：硬 cap（8 shards/4 concurrent/8 turns）、coverage receipt、no recursion。
- `.../tools/iteration_log.py`：连续无新发现 → 结构 pivot；更久 → 人工。

我们的 `next_actions`/`run_dir` 已能续跑，但没有正式 run-state ledger、stall ledger、bounded fan-out receipt。下一阶段优先级较高。

### 2.5 Review/eval（ARS/CCFA/ECC）

- ARS：最多 1 轮 re-revise；未解决 P0 不允许 early stop；DA CRITICAL 阻断 Accept。
- CCFA：idea reviewer 权重 20/25/20/20/10/5，`not assessed ≠ 0`；但无轮次上限，这是反例。
- ECC `workflows/orch-review.workflow.js`：并行 reviewer、按证据去重、adversarial verifier 默认 refuted、fail-closed。
- ARS held-out：B1–B8 schema、I1–I15 invariants、human-expert panel record；`check_ranking_lift.py` 阻止未确认回退。

本轮没有引入自动审稿 panel，因为无 API key 时只能得到伪评审；已有 support audit 仍是 advisory。正式评测仍是缺口。

### 2.6 Skill 治理（scientific-agent-skills/ECC）

- `scientific-agent-skills-main/tests/_contract/structure.py`：closed frontmatter、500 行上限、禁止 eval/exec/os.system/popen、相对链接校验；
- `scientific-agent-skills-main/tests/_meta/test_repo_contract.py`：每个带脚本的 skill 必须有测试与依赖声明；
- ECC：311 canonical skills → 自动投影到多宿主；禁止手写多个副本。

我们的 SkillLab 已有 usage/eval/version；manifest linter（frontmatter/脚本安全/三端投影一致性）已落地。通用可执行 SkillRuntime 仍未实现。

## 3. 对 S0–S16 的逐阶段映射

| 阶段 | 现有能力 | 调研后差距 | 本轮处理 / 下一步 |
| --- | --- | --- | --- |
| S0 任务路由 | RouteDecision 信号/置信度/needs_input；strict routing | classifier 的 2-signal/ask 策略 | 已落地确定性 signal router + decision log；进一步语义路由待做 |
| S1 文献 | SourceHit/Span/coverage/gap | 来源卡、筛选计数、时效、peer-review 状态 | **已落地 literature-ledger.json** |
| S2–S3 假设 | 证据 refs + falsification + lens | CCFA idea rubric、小规模 novelty check | 已落地词法 idea-review；独立 reviewer/新颖性检索待做 |
| S4 设计 | baseline/metric/controls/seeds/stopping | 统计功效、效应量、随机化/多重比较 | 已落地 design-audit；设计→S5 语义绑定仍待做 |
| S5 运行 | RunCapsule/EA、protocol hash、seeds | frozen contract runner、artifact allowlist、min_delta | 已落地 run contract/allowlist hash；min_delta 未评估；任意本地实验 runner 待做 |
| S5b Claim | ClaimAssertion/数值重算/人签 | evidence_check/preflight、cross-family provenance | 部分：claim draft/closure；下一步 provenance |
| S6 图 | schematic SVG + manifest | 数据图规范、图表审计 | 已有 SVG audit；下一步统计图检查 |
| S8–S12 写作 | paper + manuscript + audit | claim registry、引用核验、期刊模板 | **已落地 claim-registry + manuscript audit + 已有手稿 revision** |
| S13–S16 闭包 | closure/lineage/signer/bundle | obligations、hash chain、artifact handles | 已落地 append-only obligations、lineage/signature |
| META Skill | usage/eval/version | manifest linter、跨宿主投影 | 已落地 lint + external advisory + trusted script + distill candidate |
| MCP/集成 | 14 工具、项目目录、无签核 | receipt/subagent contracts | 已有 artifacts/project/skill；下一步 gate ledger |

## 4. 本轮实际改动

1. `research_agent/literature_ledger.py`：S1 来源卡、筛选计数、DOI/年份/近五年、peer-review unknown、source-level warnings；
2. `research_agent/manuscript.py`：claim registry、claim×ref×anchor evidence rows、quote/SHA-256、词法覆盖率、semantic completeness unknown；
3. `pipeline.py`：新增 `literature-ledger.json`、`claim-registry.json`、`design-audit.json`，demo URI 与 report 摘要；
4. `manuscript-audit.json`：新增 `claims.registry_coverage`；未登记定量/结果/范围声明阻断，source-only 只警告；
5. `research_agent/design_audit.py`：S4 必需字段/seeds/controls 与统计计划清单（effect size/power/randomization/多重比较/CI/缺失数据/敏感性）；只作 G2 审阅清单；
6. `research_agent/obligations.py`：closure append-only obligations；open → resolved → reopened，历史不删除，resolution 绑定报告 SHA-256；
7. `research_agent/skill_lint.py` + `skill lint`：frontmatter/name/description/body 行数、重复名称、越界链接、scripts 危险调用检查；不执行脚本；
8. `research_agent/external_skills.py` + `skill invoke`：无脚本 Skill 做 instruction-only advisory；带脚本 Skill 只有本地 CLI 显式 `--trusted-scripts` 才以用户 OS 权限运行（继承环境、超时与输出上限，**不是 sandbox**）；两者都写 usage，不写 Claim/EA/gate；
9. `research_agent/skill_distill.py` + `skill distill` + MCP `research_skill_distill`：enabled + license + human_reason 才可把外部 SKILL.md 与完整 scripts/references/assets 复制为 disabled `local-*` 候选，记录 provenance 与逐文件 SHA-256；不执行、不自动启用；`--distill-on-success` 只在成功调用后沉淀；
10. `task_agent.py` 的 RouteDecision：信号/置信度/needs_input；strict-routing 下模糊任务要求指定 task_type；
11. `idea_review.py`：S2–S3 证据 grounding/来源多样性/否证/可测性/lens/复述检测，输出 advance/revise/reject；
12. `run_contract.py`：S5 protocol/dataset/seeds/metric 绑定 + artifact allowlist + capsule/EA/evidence hash 核验；min_delta 缺 baseline 时明确未评估；
13. RSI 闭环加固（见 48-）：strict admission、证据不可替换、active-lease capability claims、默认拒绝 policy、哈希链事件日志；
14. MCP 从 8 工具扩到 13：新增 `research_skill_list`/`research_skill_distill`/`research_manuscript_revise`/`research_figure_templates`/`research_figure_render`；MCP 不执行外部 scripts，AstraDraw 模板只作视觉先验；
15. `scripts/external_skill_demo.py`：无 key 演示扫描→启用→带参脚本调用→完整资源蒸馏；产物在 `runtime_data/integrations/external-skill-demo/`，候选保持 disabled；
16. revision 纵切：`revision.py` + `revision_io.py` + `revision_figures.py`，读取已有 MD/DOCX/TEX，重算数据指标、生成 bar/line 图、逐段模型改写、引用/数字防篡改、审计与 MD/TeX/DOCX/PDF 导出；无 profile 为 copy mode；
17. `scripts/manuscript_revision_demo.py`：无 key 演示已有手稿 + 数据 → 修订包；输出在 `runtime_data/revision-demo-output/`；
19. 新增 `research_literature_fetch`：显式 allow_network 搜索/下载 arXiv 公开 PDF 到项目 inputs，再走 local PDF 解析；
20. AstraDraw 图工作流：`figure_workflow.py` + CLI `figure templates|render` + MCP `research_figure_templates|research_figure_render`；从 vendored scene/模板输出 SVG/PNG/audit/manifest；模板仅视觉先验，schematic=true；
21. 框架无关接入：`framework_api.py` + `client.py` + `/api/research/capabilities` + `/api/research/tools/{tool}`；MCP/HTTP/Python 共用 34 工具契约；`scripts/framework_bridge_demo.py` 用真实 runtime 完成 capabilities→project→plan→run→read；
22. 写作包与中文稿预审：`writing_pack.py` + `writing_audit.py` + CLI `writing pack|audit` + MCP `research_writing_pack|research_manuscript_audit`；写作包带真实来源卡/span/写作契约，未签核 Claim 不发布结果数值；中文稿审计检查引用/数值/章节/占位符/fixture，最多 `ready_for_human_review`；
23. PDF/文本句级解析改进：合并硬换行、跨空行续行与连字符断词，合并缩写/小数/标签造成的伪断句；真实 arXiv 全文 span 从“版面碎片”变为可读的完整句；
24. 顶会开放语料 + 创新评审 + 手稿迭代：`conference_fetcher.py` 按 venue/year 下载 arXiv 公开 PDF 并过滤 workshop/symposium/preprint/非 agent 标题；`innovation_review.py` 做缺口→候选→三评审→修订→再评审；`manuscript_writer.py` 从写作包+创新评审生成中文初稿并审计；`manuscript_review.py` 做 rubric→修订→再评审，审计不变差才接受；CLI/MCP 共 34 工具；
25. 真实顶会文章：22 篇 2024–2026 顶会 arXiv 语料、22 篇全文、16 篇写作包、6 个缺口、3 个创新方向；中文立场综述 59 处引用、0 结果数值、审计 `ready_for_human_review`，导出 DOCX/PDF；模型评审 6.0→6.2（未达 7.0）；
26. 实验闭环：`experiment_codegen.py` 从 S4 设计和项目内 CSV 生成自包含实验包；`experiment_runner.py` 提供 CLI approve→run（显式 allow、环境 allowlist、timeout）→ingest（哈希校验、experiment-evidence）→claim（人签、assertion）；breast cancer demo 已跑通 dummy 0.6082 / logistic 0.8918±0.0149，evidence verified、Claim 未签；MCP 只生成代码，不执行/签核；
27. 多篇综合与研究主循环：`literature_synthesis.py` 把 16 篇来源归并为 6 个跨来源主题（每主题 ≥2 篇，0 未使用），写作包/创新评审共享；`loop_ledger.py` 把 S0–S16 阶段、Q0/G1/G2/S5b/G5 门禁、创新/手稿迭代次数和下一步落成 `research-loop.json`；审计新增正文来源多样性检查（≥5 个不同 REF，单一来源 ≤60%）；
28. 测试：来源账本、claim coverage、S4 设计审计、S5 run contract、S0 route decision、S2 idea review、closure obligations、Skill linter、external advisory/trusted script、Skill distillation、manuscript revision、writing pack/audit、conference fetch、literature synthesis、innovation review、manuscript review、loop ledger、framework API/HTTP bridge、RSI governance、section-level revision plan/A-B review、closure profiles、same-run empirical paper loop、experiment result figure/evidence binding、sweep plan codegen、AstraDraw 方法示意图槽位、稿-包绑定、句级支持账本、claim-mode、多票 judge、support-aware review、section/support-patch 修订、支持账本缓存与 judge 校准、RF/GB 实验基线与 sweep 生命周期、confirm alpha、CV、数据审计、paired CI、结果表与 evidence summary；全量 479 tests；
29. 修复 `runtime/app.py` 中 EvolutionObservationStore/ActivePolicyStore 初始化晚于 JobManager 的导入错误。

## 5. 明确不照搬

- 不引入 87/177/311 个 skill 的全量目录；只保留最小、可测试的 Python 机制；
- 不把 LLM-as-judge、WebSearch、模拟 5 人 panel 当作独立证据；
- 不做无上限 review loop；建议最多 2 轮，未解决项进入 limitations；
- 不复制多个 skill 副本；使用单一 canonical + 生成投影；
- 不把 metadata/venue 当作 claim support；
- 不把 fixture、自评分 CSV 或内部 audit pass 当作期刊质量证明。

## 6. 下一步优先级

1. **Gate ledger**：每个 gate 记录 required evidence、evidence hashes、owner、verdict、human sign；直接落 CCFA/ARS 的 gate record。
2. **Run state/resume-forward + stall ledger**：把 `next_actions` 从建议升级为正式状态机；S5 run contract/allowlist 已有，仍缺 baseline min_delta 与 run-state。
3. **Citation resolver cache + freshness**：DOI/Crossref/OpenAlex 快照，显式 MATCHED/UNMATCHED/UNREACHABLE。
4. **Skill 跨宿主投影**：已有 canonical + sync 脚本 + 一致性测试；仍需按宿主版本生成投影与 lint。
5. **外部 held-out / human blind eval**：没有这一步，不能声称“论文质量不错”。
6. **S5 运行账本**：min_delta 自动判定、run-state/stall ledger；外部脚本当前是“显式信任 + 全权限”，不是 OS sandbox，若要做不可信技能市场再单独设计隔离执行。

## 7. 参考路径

- `CCFA-Skills-main/ccf-common/references/artifact-contracts.md`
- `CCFA-Skills-main/ccf-idea-reviewer/references/rubric.md`
- `academic-research-skills-main/shared/references/evidence_row_protocol.md`
- `academic-research-skills-main/scripts/claim_registry_coverage.py`
- `academic-research-skills-main/evals/heldout/MEASUREMENT_CONTRACT.md`
- `Auto-claude-code-research-in-sleep-main/tools/run_state.py`
- `Auto-claude-code-research-in-sleep-main/tools/forensics_gate.py`
- `scientific-agent-skills-main/skills/scientific-writing/scripts/audit_claims.py`
- `scientific-agent-skills-main/tests/_contract/structure.py`
- `claude-skills-main/research/deep-research/skills/deep-research/SKILL.md`
- `deer-flow-main/backend/packages/harness/deerflow/subagents/report_contract.py`
- `last30days-skill-main/skills/last30days/scripts/lib/dates.py`

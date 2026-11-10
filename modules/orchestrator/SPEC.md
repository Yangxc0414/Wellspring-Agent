---
id: orchestrator
name: 多智能体编排
stage: S1–S3
version: 0.2.3
status: pilot
owner: research-agent
inputs:
  - topic
  - max_sources
  - source
  - literature_memory
  - custom_agents
  - evolution_policy
outputs:
  - CollaborationPlan
  - ScoutTask
  - ScoutReport
  - MergedEvidenceView
  - IdeaCard
  - CustomAgent
  - AdvisoryNote
  - SkillCandidate
  - EvolutionPolicy
tools:
  - literature.facet_subset
  - literature.memory.advise
  - idea.cluster
  - rsi.propose
gates:
  - Q0
  - G1
invariants:
  - 只并行相互独立的检索面向；人工门之间保持串行
  - 每个 scout 只能读自己获得授权的 facet_subset，不能重写问题或越过预算
  - fan-in 只合并 SourceHit/Span/Coverage/Brief，按 source_id/span_id 去重
  - 不创建 Claim/EA，不代替人工通过 G1/G2/S5b/G5
  - 文献记忆只记录覆盖/产出/缺口等过程量，不保存摘要、span 文本或 claim 文本
  - 记忆只能调整下一轮面向顺序与预算；不能把记忆内容当证据
  - 由记忆派生的 SkillCandidate 永远 pending_human；必须走 dry-run、public/hidden/regression 与人工准入
  - 自定义子智能体只能是 advisory：只能选择白名单 checks，不写 Claim/EA、不通过门禁、不执行任意代码
  - 自进化策略关闭时忽略记忆调序并抑制新的候选；已有 lease/confirmation 不被追溯撤销
  - 自进化策略只允许切换 literature.memory_order / literature.query_planner / orchestrator.facet_budget；Claim/EA/gate/rubric/held-out/closure/signature/export 不可切换
  - fixture 输出必须透传 fixture_mode；不得把模拟覆盖写成真实结果
---

# 多智能体编排子智能体（S1–S3）

## Purpose

把“一个 Agent 从头做到尾”改成有边界的协作：独立的文献面向并行侦察，覆盖审计做 fan-in，假设收敛在合并证据视图上只跑一次；进入 G1 之后的阶段仍由人工门控制。编排器本身不生产 Claim，也不替人做准入判断。

## Contract

输入：

- `topic`: 研究问题（2–500 字符）；
- `max_sources`: 总来源预算（1–50）；由记忆与固定分组分配到各 scout；
- `source`: `fixture` / `real`；OpenAlex 实时 fan-out 不在本模块默认启用；
- `literature_memory`: 可选的 `literature-memory-0.1` 过程记忆，用来重排面向与预算；
- `custom_agents`: 用户手动注册的子智能体；只能绑定白名单 checks（coverage/citation/hypothesis/protocol/evidence/figure/closure），输出 advisory note；
- `evolution_policy`: `evolution-policy-0.1`，master switch + 三个安全 scope；关闭时忽略 memory_order 并抑制新候选，不触碰已有 lease。

输出：

- `CollaborationPlan`: topology、roles、lanes、typed handoffs、human gates、budget、stop point；只描述计划，不执行；
- `ScoutTask`: `{question, facet_subset, budget, source_scope}`；
- `ScoutReport`: `{hits, spans, coverage, brief}`，每个 scout 只能报告其 facet_subset；
- `MergedEvidenceView`: 去重后的 hits/spans、facet coverage、合并 gap 与 saturation；
- `IdeaCard[]` / `IdeaBrief`: 在合并视图上生成候选帧，status 仍为候选，G1 未通过；
- `CustomAgent`: 用户注册的 advisory role；`stages`、`checks`、`tools`、`outputs` 均由白名单派生；
- `AdvisoryNote[]`: 对 coverage/citation/hypothesis 的确定性检查结果；protocol/evidence/figure/closure 在当前 stop point 返回 deferred；
- `EvolutionPolicy`: master switch 与安全 scope 状态；不可变面以 locked 列表返回；
- `SkillCandidate`: 记忆派生的 query-planner 或 budget 改进候选，`status=pending_human`，受 policy 抑制。

协作规则：

- `fan-out`：默认三组 `core+survey` / `method+evaluation` / `limitation+recent`；线程数不超过组数；每组独立 retriever，避免共享限流状态；
- `fan-in`：按 `source_id` 合并来源，按 `span_id` 合并 span；facet 覆盖取并集；任一 scout 的 cap/缺口进入合并 gap；
- `sequential`：idea facilitator 只在 fan-in 完成后运行一次；随后停在 G1 前；
- `custom-advisory`：启用的自定义子智能体作为独立 advisory 车道；只运行与当前 stop point 兼容的确定性 checks；其余 checks 明确 deferred；
- `evolution policy`：master off 时使用 balanced facet groups、忽略记忆调序、抑制候选；单 scope off 时只抑制对应候选。
- `gate`：G1/G2/S5b/G5 需要人工；`protocol-designer`、`runner`、`evidence-curator`、`figure-builder`、`writer`、`closure-auditor` 在计划中可见但不会被本模块执行；
- `independent`：`rsi-governor` 可以评估/提议，但不能由编排器自动准入或撤销。

失败/状态：

- 任一 scout 抛错：整次编排显式失败，错误包含 scout role；不静默返回部分覆盖；
- 没有 span：`merged.status` 为 `insufficient`，IdeaAgent 输出 `needs_evidence`；
- 预算小于面向数：只调度优先级最高的面向，其余进入 `deferred_facets`，不伪造覆盖。

## Current Implementation

- `research_agent/orchestrator.py`：稳定 facade，保留 `run_orchestration`、`public_snapshot`、`write_orchestration_artifacts` 与兼容导出；fan-in 后的 IdeaAgent 现在注入 source-scoped live prior-art searcher（复用 literature retriever），候选带 `prior_art_scope/report` 与 advisory `IdeaShortlist`；
- `research_agent/orchestration/plan.py`：roles/handoffs/gates、`collaboration_plan`、`topology_snapshot`、policy summary；
- `research_agent/orchestration/advisories.py`：自定义 advisory role 派生与 coverage/citation/hypothesis 检查；
- `research_agent/orchestration/merge.py`：scout report 去重、facet 覆盖、gap 与合并指标；
- `research_agent/orchestration/common.py` / `errors.py`：时间、run id、fingerprint 与 `OrchestrationError`；
- `research_agent/paths.py` / `storage.py`：默认状态路径与原子 JSON 读写的单一实现；CLI/runtime 不再依赖 CWD 或各自复制写盘代码；
- `research_agent/custom_agents.py`：`CustomAgentStore`（add/update/delete/list），checks 白名单与 stage/tool/output 派生，advisory-only 边界；snapshot 提供 checks 元数据，前端不再维护第二份白名单；
- `research_agent/evolution_policy.py`：`EvolutionPolicyStore`，master switch + 三个安全 scope + locked 列表；关闭时抑制新候选并忽略 memory_order；
- `research_agent/literature_memory.py`：`LiteratureMemoryStore.record/record_result/advise/snapshot`，按 topic/mode/facet 记录 attempts、covered_runs、queries、sources、spans、gaps、saturation；
- S1 fan-out 调用 `LiteratureAgent`，通过 `facet_subset` 限制面向；每个 scout 使用独立 `FixtureRetriever` 或 `RealCorpusRetriever`；
- fan-in 在编排器内完成，不新增 Claim 或 EvidenceArtifact；IdeaAgent 只接收合并后的 span；
- 记忆更新在 fan-in 之后一次写入，记录的是过程量与计数；`advise` 输出下一轮 facet 优先级、预算、scout 分组与候选技能；
- `public_snapshot` 只导出计数、facet 覆盖、候选帧与记忆摘要，不导出摘要/span 文本，供静态工作台展示；
- CLI：`orchestrate plan|run`、`literature memory show|advise`、`agent list|add|toggle|delete|export`、`rsi policy show|set`；
- Runtime：只读 `/api/orchestrator/topology`、`/api/orchestrator/plan`、`/api/literature/memory`；自定义子智能体与 policy 的本地管理端点不提供 approve/claim/sign。

## Boundaries

- 不做 S4 设计冻结、S5 运行、Claim 签署、闭包签名或导出；
- 不把 scout 的局部结论拼成新结论；fan-in 只做证据视图合并；
- 不用文献记忆替代检索，不用记忆中的覆盖计数作为引用证据；
- 不在 runtime 中执行 fan-out 写操作；执行留在 CLI/受控 job；
- 不自动把 SkillCandidate 写入 RSI 账本；准入仍由 `rsi propose → dry-run → evals → human` 流程完成。
- 自定义子智能体不接收任意 prompt、不执行代码、不调用外部工具；只能运行白名单确定性 checks，输出 advisory note。
- 自进化策略关闭不修改历史 ledger/lease/confirmation；它只阻止新的自动候选与记忆调序。

## Minimal Change Workflow

1. 先改本文件 `Contract` 或 `Current Implementation`；
2. 升 `version`，在 `## Changelog` 追加说明；
3. 最小化改 `research_agent/orchestrator.py` 或 `literature_memory.py`；
4. 加/改 `tests/test_orchestrator.py`、`tests/test_literature_memory.py` 与 runtime 测试；
5. 跑 `python -m unittest discover -s tests -v`，并重新导出工作区快照。

## Changelog

- 2026-10-28 · v0.2.3 · status=pilot · 明确编排 scouts 保持 `followup_plan=false`：follow-up 会改变 scout 的 query 计数、gap/saturation，进而改变 memory/skill candidate（实测从 query_planner 变为 facet_budget）；gap follow-up 只在 TaskAgent/pipeline 开启；idea live prior-art 与 IdeaShortlist 不变。
- 2026-10-28 · v0.2.2 · status=pilot · fan-in 后的 idea 阶段接入 live prior-art searcher（复用 literature retriever，source-scoped）；候选带 prior_art_scope/report 与 advisory IdeaShortlist；仍不自动 G1、不评 novelty。
- 2026-10-25 · v0.2.1 · status=pilot · 内部结构收敛：`orchestrator.py` 拆为稳定 facade + `orchestration/{plan,advisories,merge,common,errors}.py`，roles/plan、advisory checks、merge 与 runner 分离；新增 `paths.py`（repo-root 绝对默认路径）与 `storage.py`（原子 JSON 读写），CLI/runtime/四个 store 共用，消除 CWD 漂移与重复写盘；`custom-agents.json` snapshot 增加 tool/output 元数据，前端表单单读后端 schema。契约、门禁与证据边界不变。
- 2026-10-24 · v0.2.0 · status=pilot · 新增手动子智能体与自进化策略：`CustomAgentStore` 只允许白名单 advisory checks，fan-in 后执行 coverage/citation/hypothesis 确定性检查，后阶段 checks 明确 deferred；`EvolutionPolicyStore` 提供 master switch 与 literature.memory_order / literature.query_planner / orchestrator.facet_budget 三个安全 scope，关闭时忽略记忆调序并抑制候选，Claim/EA/gate/rubric/held-out/closure/signature/export 保持 locked；新增 CLI/runtime 管理面与静态快照。
- 2026-10-24 · v0.1.0 · status=pilot · 初始实现：S1 三 scout facet fan-out、fan-in 去重、IdeaAgent 单次 fan-in；文献过程记忆与待人工准入的 query-planner SkillCandidate；CLI 与只读 runtime 端点；不创建 Claim，不自动过 G1。

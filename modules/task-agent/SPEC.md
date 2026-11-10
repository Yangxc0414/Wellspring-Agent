---
id: task-agent
name: 任务路由与执行
stage: S0–S12
version: 0.7.0
status: draft
owner: research-agent
inputs:
  - TaskRequest
  - success_criteria
  - source_scope
  - run_dataset
  - run_dir
  - g1_decision_file
  - protocol_file
  - claim_file
  - bibliography_file
outputs:
  - TaskPlan
  - TaskExecution
  - TaskReport
  - LoopCapsule
tools:
  - literature.run
  - idea.frame
  - experiment.design
  - pipeline.run
gates:
  - Q0
  - G1
  - G2
  - S5b
  - G3
invariants:
  - 只路由到已有模块，不创造新的证据对象
  - 不创建 Claim/EA，不替人签署或通过门禁
  - 任务类型不明确时必须请求补充，不能静默跑全套流程
  - 文献综述只跑 S1；实验验证必须有 run_dataset 或可复用的 run_dir
  - 报告必须区分完成、需证据、需人工和失败
  - 执行异常必须写结构化 FailureRecord（`failure.json`）：含 error_type/retryable/suggested_action；它只用于诊断，不改变 claim、门禁或签名
  - fixture 与摘要-only 必须显式标注
  - 每次 task 完成/失败都写只读 loop-capsule.json；缺失节点不是通过，capsule 不创建证据/claim/gate/signature/closure
  - next_actions 只指向可执行命令，不代替人执行、不代替人签核
  - 包查找必须认多环境命名：想法执行后的包可能是 STUDY-<idea>-<dataset>（--datasets all），ledger 只能按前缀识别并以想法声明的环境为优先，不得把已执行的想法报成从未执行
---

# 任务路由与执行（S0–S12）

## Purpose

把“用户给一个任务”变成可执行、可检查、可停止的任务计划。任务层只负责识别交付物、选择最小必要阶段、调用已有科研模块、记录检查点并生成任务报告；它不替代任何模块，也不改变证据边界。

## Contract

- 签核向导必须把它递出的命令的**后果**一起递出去（`loop_ledger.pending_study_actions`）：
  对已执行的研究，`study claim` 命令在满足条件时自带 `--baseline-file <路径>`——包内已绑定，
  或在该包与其父目录里找到 `tuned-baseline*.json` 且**数据集相同、种子有交集**（找不到就不写这个
  参数，并在 message 里说明"只会与研究内部参照格比较，先跑 study baseline"）；
  向导只报它验证过的路径，绝不写一个凭猜测填的路径。
  同一动作还必须先说两件事，否则等于把撞门禁的命令当"下一步"递给人：
  包内 `code_fingerprint` 与当前代码不一致时明写 closure 会在 `code.unchanged` 失败，
  并给出 `study closure --verify-repro` 出路；预注册没有 `baseline` 槽时明写
  closure 会警告"对手是跑完之后才定的"。
  非结果（无可判定比较）不得出现任何对手相关语句——没有可签的主张，就没有可绑的对手。
  动作对象仍带结构化字段 `tuned_baseline = {bound, candidate, declared, bound_in_command}` 与
  `code_stale`，供程序判断而不是只给人读文本。边界不变：只读投影，不执行、不签核、不创建证据。

输入：

- `goal`: 研究任务目标（2–500 字符）；
- `task_type`: `auto` / `literature_review` / `hypothesis_design` / `experiment_validation` / `full_research`；
- `deliverable`: 可选交付物名称；
- `source`: `fixture` / `real` / `openalex` / `local`；
- `max_sources`、`run_dataset`、`run_dir`、`run_seeds`；
- `constraints`、`success_criteria`；
- 可选模型边界：`query_planner`、`section_writer`、`idea_proposer`、`experiment_designer`；均只通过模块构造函数注入；
- `strict_models=true`（production）时，任一 required 模型缺失、调用失败或输出不可解析都会让任务失败，不回退规则模板；
- `flow_mode=review|strict`：review 生成完整待审包（演示/回归）；strict 把 Q0/G1/G2 当控制流，分别在证据不足、未选 idea、未冻结协议时停止；
- strict 续跑入口：`g1_decision_file`（selected_idea_id + human_reason）、`protocol_file`（frozen ProtocolCard，design_sha256 必须匹配当前 design）、`claim_file`（已签 ClaimRecord）、`bibliography_file`（verified DataCite snapshot）、`run_dir`（复用已完成 RunCapsule/EA，禁止为已签 claim 重跑 S5）；签署仍只能由 CLI/人工完成。

路由：

- `literature_review`：只跑 S1，产出 `literature.json` 与任务报告；
- `hypothesis_design`：跑 S1 → S2/S3 → S4，产出候选、设计草案与任务报告；
- `experiment_validation`：必须有 `run_dataset` 或 `run_dir`，走完整 pipeline 的 S1–S5（run_dir 时复用已有 capsule/EA），产出 RunCapsule/EA/claim draft；
- `full_research`：走完整 pipeline，产出报告与工作稿；
- 自动路由按关键词/数据集推断；无法判断时进入 `full_research`，但会在报告中标注；
- `task_type=auto` 且 `source=openalex` 时，若推断结果为 `hypothesis_design` / `full_research`，降级为 `literature_review`：摘要-only 不能生成 span，不能支撑候选/工作稿；显式指定的 `task_type` 不降级，由证据检查如实失败或要求补充全文。

输出：

- `TaskPlan`：route、steps、human gates、success criteria、budget、blocking issues；
- `TaskExecution`：每一步状态、质量检查、warnings、artifacts、started/finished、`evidence_packages`（S1–S13 每个证据包的状态/细节/边界）、`error` 与 `failure`（失败时的结构化 FailureRecord）；
- `TaskReport`：人类可读的任务完成报告与下一步人工动作。

失败/状态：

- `needs_input`：缺少必要输入（如实验验证缺 run_dataset）；
- `needs_evidence`：没有来源或 span；
- `needs_human`：已产出证据/工作稿，但 claim/G2/closure 仍需人工；
- `failed`：执行异常，写 `task-error.txt` 与 `failure.json`，不伪造成功。`failure.json` schema 为 `task-failure-0.1`，含 `error_type`、`error`、`retryable`、`suggested_action`、`warnings` 与边界；它只做诊断，不自动重试、不改变输入或门禁。

## Current Implementation

- `research_agent/task_agent.py`：`TaskRouter` + `TaskAgent.plan/run`；
- `literature_review` 直接复用 `LiteratureAgent`；
- `hypothesis_design` 复用 `LiteratureAgent` + `IdeaAgent` + `ExperimentDesignAgent`；
- `experiment_validation` / `full_research` 复用 `PipelineRunner` + `write_pipeline_artifacts`；
- CLI：`python -m research_agent task plan|run`；
- strict 续跑支持复用 `run_dir` 的 RunCapsule/EA，支持 `bibliography_file` 绑定 citation.related；已签 claim 的续跑会执行 closure/lineage postprocess，并把 closure ready 回写到证据包与 G3/G5；
- 任务产物：`task-plan.json`、`task.json`、`task-report.md`，以及对应阶段产物；`task.json` 含 `evidence_packages`，报告含“证据包状态”一节；失败时额外写 `failure.json`；
- `failure.json` 的 retryable 只按已知瞬时错误（429/超时/连接失败/5xx）推断，其余按不可重试处理；`suggested_action` 面向人工修复（配置 key、切换 source、检查引用），不会自动执行；
- `flow_mode=strict` 时，任务报告必须显示 `stopped_at` 与下一步人工动作（G1 decision / freeze-design / run / sign claim）；
- strict 在 Q0/G1/G2 提前停止时，仍必须保留已计算的 `idea-review.json` / `design-audit.json` / run-contract 等阶段审计产物，不得因为 early return 丢失；
- 提供已签 `claim_file` 时，主链在写出 `demo.json` 后自动运行 `closure check` 与 `lineage build/verify`，写 `postprocess.json`；closure 状态回写证据包，但不会签核或提交；
- 可选模型边界与 pipeline 共用绑定：`query_planner` 规划检索，`idea_proposer` 提候选，`experiment_designer` 补设计草稿，`section_writer` 写非结果章节；模型不能改路由、证据、Claim、门禁或结果数字；
- 默认不联网；`source=openalex` 时只取摘要线索，不生成 span。

## Boundaries

- 不是通用 ReAct/任意工具智能体；只处理科研任务路由；
- 不创建 Claim、EA、Verdict，不自动冻结协议或签署 closure；
- 不把任务报告当论文结论；
- 没有真实全文时只能返回 `needs_evidence`，不能补写证据；
- 后续若接入动态规划/LLM planner，必须保留相同的 blockers 与 human gates。

## Minimal Change Workflow

1. 先改本文件 Contract 或 Current Implementation；
2. 升 version 并在 Changelog 追加；
3. 改 `research_agent/task_agent.py` 与 `tests/test_task_agent.py`；
4. `python -m unittest discover -s tests -v`。

## Changelog

- 2026-11-02 · v0.7.0 · status=draft · v0.7.0 makes the guidance own the consequences of the command it hands over. pending_study_actions now appends --baseline-file when a tuned baseline is bound inside the package or a matching report sits beside it (same dataset, overlapping seeds, verified before the path is printed), and when none exists it says so and points at study baseline instead of inventing an argument. The same action now states two things that were previously hidden until closure refused them: a stale code fingerprint means closure will block at code.unchanged and gives the verify-repro route, and a pre-registration without a baseline slot means closure will warn that the opponent was chosen after the run. Non-result actions carry no opponent language at all, because a claim that cannot be signed has no opponent to bind, and the first version of this change leaked an empty phrase, opponent available at colon, into exactly that branch. Actions carry tuned_baseline = bound/candidate/declared/bound_in_command and code_stale so a caller can branch on structure rather than reading prose. Still a read-only projection: it executes nothing and signs nothing. Five new cases in tests/test_loop_ledger.StudyGuidanceBaselineTest, 18 in the file.
- 2026-10-30 · v0.6.3 · status=draft · 2026-10-29 · v0.6.3 · status=pilot · 修掉今天自己引入的一个闭环 bug：loop_ledger 只找 STUDY-<idea>，而 --datasets all 写的是 STUDY-<idea>-<dataset>，于是四环境都跑完的 IDEA-01 被报成 study_execution（让宿主 Agent 把四份研究重跑一遍）。新增 _idea_package(project, idea_id, declared_dataset)：精确名优先，否则按 STUDY-<idea>- 前缀收集已有包、优先返回想法声明的那个环境，都没有才返回 None。实测 runtime_data/idea-replication（4 个环境包）修复前 [(study_execution,IDEA-01),(study_execution,IDEA-02)]，修复后 [(human_gate,IDEA-01 → STUDY-IDEA-01-iris, signable=[memory_on_gate_off]),(study_execution,IDEA-02)]——已执行的进入签核门，未执行的才给重跑命令。新增回归测试。同时暴露一条真实限制（记入 55- §8）：overturn 判定只看同一个 studies/ 目录，因此这里被推荐签署的 memory_on_gate_off（iris@32 positive）在另一个项目里已被 iris@64 判为未判定——跨项目的证据目前互相看不见。
- 2026-10-29 · v0.6.2 · status=draft · 2026-10-29 · v0.6.2 · status=pilot · study_replication 动作改为优先给出**带溯源**的复现命令：_replication_action 读取包的 study-origin.json，若绑了 idea_id+run_id 就产出 study from-idea --datasets <未试环境列表>（复现同时保留想法溯源），否则退回 study search --dataset <单个未试> 的因子式命令；study_execution 动作新增 replication_option="--datasets all" 与 replication_note，让宿主 Agent 第一次执行时就看到多环境选项。动作仍只是建议，执行与签核都在 CLI/人。
- 2026-10-29 · v0.6.1 · status=draft · 2026-10-29 · v0.6.1 · status=pilot · next_actions 不再建议签署被更高功效推翻的比较：新增 loop_ledger._overturned_comparisons(project, package)，按 design_key + dataset + **decided_at.directory 归属**过滤，pending_study_actions 把命中的比较从 decidable_comparisons 剔除并记入 overturned_comparisons，剔空后动作由 human_gate S5b（去签）降级为 study_no_finding，消息点名"这条判定不作为可签署依据"。第一版只按 design+dataset 过滤，导致 64 种子包被自己的证据判成"已推翻"，由新增测试抓到并修（推翻者保留自己的结论）。实测真实包：STUDY-IRIS-16 → [memory_on_gate_off]、STUDY-IRIS-64 → []。契约变化：动作多一个字段、少一类错误建议。
- 2026-10-29 · v0.6.0 · status=draft · 2026-10-29 · v0.6.0 · status=pilot · next_actions 新增 study_replication：loop_ledger._replication_action 在研究包已执行且该设计只存在于一个数据集时追加一条动作，给出 datasets_present/datasets_untried、可执行命令（study search --dataset <未试数据集> --seeds <沿用> --budget <沿用> 仅多水平 --factors && study replicate）与理由（区间在一个数据集训定不能说明泛化）；一旦同设计出现第二个数据集，该设计进入 replicated 组，动作自行消失，不长期 nag；无 study-spec.json 设计声明的包不产建议（不凭空猜关系）。实测 runtime_data/from-idea-check RUN-QODER-HOST：三数据集齐备后 pending_study_actions 只剩 2 条 human_gate，study_replication 为 0 条；单数据集夹具中 1 条且命令含 --dataset breast_cancer。契约变化：新增一种 action kind。
- 2026-10-28 · v0.5.2 · status=draft · TaskAgent 每次运行写 `loop-capsule.json`（S1→META 节点/blockers/next_actions），包括文献综述只跑 S1 和失败路径；通过 MCP `research_status`/`research_next_actions` 可读；不创建证据/claim/gate/signature/closure。

- 2026-10-26 · v0.5.1 · status=draft · 修复 strict early-return 丢失阶段审计产物：G1/G2 停止时仍写出 `idea-review.json`、`design-audit.json` 与 run-contract；补 strict G1→G2 续跑测试。
- 2026-10-26 · v0.5.0 · status=draft · 新增 RouteDecision：记录 route/confidence/signals/needs_input/candidates；`RESEARCH_AGENT_STRICT_ROUTING=1` 时模糊任务要求指定 task_type，否则保留 fallback 并写入 warning；TaskPlan 增加 route_decision。
- 2026-10-26 · v0.4.0 · status=draft · auto 路由遇到 `source=openalex` 时，将 hypothesis_design/full_research 降级为 literature_review：摘要-only 无法生成 span；显式 task_type 不降级，保持证据检查如实失败。
- 2026-10-26 · v0.3.0 · status=draft · 新增结构化 FailureRecord：失败时写 `failure.json`（error_type/retryable/suggested_action/warnings）并在 `TaskExecution` 返回 `error`/`failure`；只用于诊断，不自动重试、不改 claim/gate/signature。
- 2026-10-26 · v0.2.2 · status=draft · 严格流程续跑支持 run_dir 复用已有 RunCapsule/EA 与 bibliography_file；主链可在已签 claim 上产出 closure/lineage，并把 closure ready 回写到 G3/G5。
- 2026-10-25 · v0.2.1 · status=draft · 提供已签 claim_file 时，主链在写出 demo 后自动执行 closure check 与 lineage build/verify，产出 postprocess.json；仍不签核、不提交，closure 状态回写到证据包。
- 2026-10-25 · v0.2.0 · status=draft · 新增 strict_flow/review 流程模式：strict 下 Q0/G1/G2 是控制流而非报告；支持 g1_decision/protocol_file/claim_file 续跑入口；review 仍可生成完整待审包。
- 2026-10-25 · v0.1.2 · status=draft · TaskExecution 增加 evidence_packages：按 S1–S13 汇总每个证据包的状态、细节与边界；runtime job 与任务报告同步返回，前端 EVIDENCE 页可直接展示。
- 2026-10-25 · v0.1.1 · status=draft · 任务执行层支持注入 section_writer / idea_proposer / experiment_designer，与 pipeline 使用同一模型绑定；production 下 strict_models 让模型失败直接失败，不静默回退；模型仍只能提出候选或草稿，不创建 Claim/EA，不改变路由与人工门。
- 2026-10-25 · v0.1.0 · 初始任务层：四种路由、检查点、质量检查、任务报告、CLI；不创建 Claim/EA。

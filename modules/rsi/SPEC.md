---
id: rsi
name: 受治理的递归改进
stage: META
version: 0.12.0
status: pilot
owner: research-agent
inputs:
  - Observation
  - Candidate
  - PublicEval
  - HiddenEval
  - HumanDecision
  - EvolutionPolicy
  - Harness2Run
outputs:
  - StepLedger
  - AdmissionRecord
  - Lease
  - RSIReport
  - ConfirmationRecord
  - RSIStory
  - EvolutionPolicyState
  - EvolutionObservation
  - ActivePolicyState
  - Harness2Story
  - GenerationLedger
  - EvolutionLineage
tools:
  - rsi.ledger
  - rsi.policy
  - rsi.trace
  - rsi.observations
  - rsi.active
  - rsi.harness2
gates:
  - H0
  - H1
invariants:
  - 候选不能修改 claim/evidence/gate/rubric/export/signature
  - 没有 dry-run 不能准入
  - 没有 public+hidden 不能准入
  - 没有人签不能 active
  - 撤销必须保留并传播
  - 过期 lease 不得生效；不同预算的 active lease 冲突必须拒绝执行
  - 预测与实际写入 ledger；数值预测只用于过程校准，不得当作能力证据；coverage gap 不能作为降低预算的理由
  - 候选按 public 排序，最多两个 finalist 依次 gate；hidden 不参与排序或提案
  - harness-only 或 simulated 证据不得写入 capability claim
  - lease scope 必须与执行器 scope 匹配；跨 benchmark 不得自动生效
  - 同一 benchmark 的 target+patch 不得重复 propose；拒绝项无新证据不得重试
  - 候选集必须预注册；hidden 不用于扩展候选或选择 retriever
  - active real harness lease 必须由 pipeline run --use-lease 消费；无 lease 或冲突时 fail closed
  - runtime job 完成时必须写入 observation（非 fixture/非证据）；观测只用于候选建议，不得进入 Claim/EA/Closure
  - observation suggestion 只读且 advisory；activation 必须走 CLI 人理由，MCP/runtime 不提供激活或签核入口
  - active literature budget 必须由下一次 runtime job 消费并在事件流记录；S5 seed lease 必须覆盖 runtime 的 run_seeds，否则视为未闭环
  - strict admission 必须同时具备 public/hidden/near_ood/regression、非 simulation 证据、evaluator、artifact_sha256 与 task_pack_sha256；缺一项不得准入
  - 已 evaluate 的证据不得在 admit 时被替换；准入必须记录 approved_by 与 evidence_digest
  - capability_claims 只能来自 active lease；revoked/expired 必须自动收回
  - 每次 propose/evaluate/admit/reject/revoke/confirmation 必须追加哈希链事件；事件链断裂时审计失败
  - 模型提案是不可信输入；schema 归一化不得绕过 scope/gate，且必须保留提案 id/rationale
  - proposal batch 审计必须保留逐条拒绝原因，不能只报接受率
  - schema-repair 只允许回灌格式/策略错误并重试；不得跳过 gate，不得把修复次数当能力增益
  - real sealed confirmation 只复核、不回流准入；回归由人处理
  - sealed confirmation 必须使用未参与选择/准入的 held-out task pack
  - S5 evaluator 只改 run seed budget；iris/breast_cancer/chemlab 指标不是论文证据
  - ChemLab seed-budget confirmation 必须使用与 admission 测试集不重叠的 42 条派生 held-out 反应；不得复用固定 22 化合物测试集冒充复核
  - active S5 seed lease 必须由 run execute --use-lease 消费；无 lease 时 fail closed
  - S5 sealed confirmation 必须使用 held-out protocol instances；used_for_admission=false
  - S5 选择是 dataset-specific；不得当作通用 harness 结论
  - rsi trace 必须 fail closed：lease 未生效、capsule seeds/dataset 不匹配、存在 capability claim 或 confirmation 回流准入时不得报 traceable
  - confirmation 记录只作审计，不得回流准入或生成 capability claim；regressed 必须保留并交人处理；重复同一 artifact 不得重复记账
  - confirmation/trace 必须 fail closed：status/passed 不一致、scope 不匹配、delta 非有限数值、confirmation 与 ledger hash 不一致时不得通过
  - 自进化策略只控制新候选与记忆调序：master off 时不得新增 propose/自动研究循环候选；不得追溯撤销已有 lease/confirmation
  - 策略只允许切换 literature.memory_order / literature.query_planner / orchestrator.facet_budget；claim/evidence/gate/rubric/held-out/closure/signature/export 不在可切换集合内
  - 确认不可动作于升级，但 regressed 确认必须可动作于降级：自动撤销该候选的 active 租约；升级仍需人工签署
  - 每个 episode 记录 platform_fingerprint（平台代码指纹）与 candidate.version（自进化候选版本），供自进化版本管理与平台自我迭代的关联/回滚；平台只记账与提供接缝，不实现自进化算法
  - EvalEvidence 自动绑定 code_fingerprint（产生该证据的平台代码指纹），verdict 不得跨构建静默复用；ProposerPort/EvaluatorPort 为候选/评测供给接缝（内部简单自改进、外部 Agent、同学细粒度自进化均可实现），平台只校验证据形状与哈希、不伪造指标
---

# 受治理的递归改进（RSI 控制面）

## Purpose

这不是“让 Agent 自己改自己”的开关，而是 RSI 的**准入与账本控制面**：观察研究运行，记录候选改进（skill/process/prompt/knowledge），要求 dry-run、public/hidden 评测、人签、租约与撤销。它追踪的是“改进过程本身”，不是宣称系统已经越跑越强。

## Contract

- 输入：`Observation`、`Candidate`、`PublicEval`、`HiddenEval`、`HumanDecision`、`EvolutionPolicy`；
- 输出：`StepLedger`、`AdmissionRecord`、`Lease`、`RSIReport`、`EvolutionPolicyState`；
- Candidate 只能改 skill/process/prompt/knowledge；
- 禁止修改 claim/evidence/gate/rubric/export/signature/authorship；
- 准入前必须有 dry-run、public、hidden、人签与 scope；
- 候选可包含 retriever+budget 组合；候选集必须预注册，hidden 不用于扩展候选或选择 retriever；
- 候选按 public 指标排序；最多两个 finalist 按该预注册顺序依次过 hidden/near-OOD/regression gate；hidden 不参与排序或提案；
- 模型提案是不可信输入：只允许经 schema 归一化与 GovernancePolicy；提案 id/rationale 必须写入 ledger，不能绕过 scope/gate；可选 schema-repair 最多回灌一次错误并重试，仍走同一 evaluator；
- proposal batch 审计必须保留逐条 gate 结果；接受率本身不是能力证据；
- S5 evaluator 只允许 run seed-budget 变更；支持 iris/breast_cancer（accuracy）与 chemlab（R²）；结果仅协议验证，`claim_eligible=false`，不是论文证据；ChemLab 的 split 必须使用不同训练子集，confirmation 使用 42 条派生 held-out 反应，且不得回流准入；
- real sealed confirmation 使用独立新问题，`used_for_admission=false`；回归不自动撤销，交人处理；
- active lease 必须能解析为执行器参数并由研究运行消费；未准入策略不得生效；
- active real harness lease 由 `pipeline run --use-lease` 消费；无 lease 或冲突时必须 fail closed，且运行输出记录 `active_harness`；
- active lease 到期即失效；多个不同预算的 active lease 视为冲突，必须 fail closed；
- lease scope 必须与执行器 scope 匹配；fixture runner/confirm 只消费 `S1/fixture`，真实 probe lease 不跨 benchmark 生效；
- fixture/模拟证据必须标记 `simulation: true`；真实语料 harness 评估必须标记 `claim_eligible: false`；两者都不得写入 capability claim；
- 租约后的 sealed confirmation 只做复核，不回流候选选择/准入，也不产生 capability claim；
- 预算降低只能由 retrieval_cost 观测触发；coverage gap 是 guard，候选不得增加 gap；
- 预测与实际必须写入 ledger，供 MetaTracker 审计；候选可选记录数值 `predicted_metrics`，MetaTracker 汇总 MAE/bias/direction/coverage；未记录时显式标 `uncalibrated`/`partial`，不得用自由文本冒充校准；
- `rsi trace` 只读校验 active lease → research capsule（seeds/dataset）→ 无 capability claim → 可选 sealed confirmation（不回流准入）；任一核心链接不匹配即 `ok=false`，不修改 ledger；
- sealed confirmation 结果写入 `StepLedger.confirmations`（status/passed/split/delta/artifact hash），只作审计；写入时强制 `sealed=true`、`used_for_admission=false`、`status/passed` 一致、scope 匹配 lease、delta 为有限数值，`regressed` 只告警并交人处理；
- 同一 benchmark 的 target+patch 已存在时不得重复 propose；拒绝项无新证据不得重试；
- 拒绝/撤销保留负结果与理由；不能静默重试；
- 没有真实 evaluator 时，只能记录 `pending_human`，不能写 capability gain。
- 自进化的**执行**不在本模块重写：递归改进（Propose–Probe–Compose、c1..c8 组件面、平行/顺序两种模式）由外部 Harness² 引擎承担，本模块只消费其产物；
- 接缝契约 `harness2-run-0.1`：必须带 `schema`、`harness2.method_version`、`run.{adapter,k,modes,exit_code}`、`budget.{R,expected_R,P,expected_P}`、`tasks[].{task_id,status}`、`surface.components`（≥6）、`adopted[]`、`classification.{simulation,claim_eligible}` 与 64 位 `task_pack_sha256`；任一缺失即拒绝入库，不得部分接受；
- 预算恒等式 `R=4k`、`P=3k` 必须成立；任务状态非 `ok`、阶段回退或桥进程非零退出时，产物只能作为失败记录，不能映射为候选；
- 产物必须显式声明便携性补丁（如 `fcntl.flock→msvcrt`、`tree.read_tree` POSIX 路径）；补丁缺声明等同于来源不可信；
- 确定性执行器/提案者产出的证据一律 `simulation=true`、`claim_eligible=false`，不得因"跑了完整递归"而升格为能力证据；
- 采纳改动按 `(组件路径, diff)` 去重为一条 `Candidate`；同一改动在多个任务/模式被采纳，只写进 rationale 的观察点，不刷多条 episode；
- 组件路径命中 `claim/evidence/gate/rubric/export/signature/authorship/closure/heldout` 时拒绝映射，并保留 blocked 理由；
- 新 scope `harness2.harness` 只登记可编辑面；`record` 只写 `pending_human`，`admit` 仍要求 dry-run + public + hidden + 具名人，Harness² 自身不持有任何签核入口；
- 留出检查（held-out）由平台侧执行：提案者不得见过该任务；没有留出集时 hidden 证据为空，准入必须失败而不是降级。
- 自进化本身必须可版本化，且分两条轨道记账：`agent`（被采纳的 harness 树 SHA-256 + episode + 证据摘要）与 `platform`（平台代码指纹 + 提交/备注）；`compare` 只能同轨比较，跨轨拒绝；
- 平台指纹定义为 `research_agent/**/*.py` 的内容哈希 + Python 版本（16 hex）。它**不覆盖** SPEC、测试、脚本与前端，因此只改文档不会移动指纹——这一点必须写进边界，不能被读成"整仓版本号"；
- 世代台账 append-only + 哈希链事件；`open` 只接受 `proposed|adopted`，`close` 只接受 `adopted|reverted|superseded`；标记 `superseded` 必须已存在更新的 adopted 世代（否则拒绝）；
- adopted 的 agent 世代必须带 tree sha；同一棵树在新平台复验时，旧记录自动 `superseded`（复验不是新改进，不能显示成两个"当前版本"）；
- adopted 的 platform 世代必须带 commit 或 note，否则 `verify` 告警：版本无法重建；
- 跨轨耦合：adopted agent 世代的 `platform_fingerprint` 与当前不一致时，`verify` 报 `stale_agents` 并提示复验；**不自动撤销租约、不自动改 claim**（降级/复验是人的动作）；
- 平台代码在最后一次 platform 世代之后又变化时，`verify` 提示"记录一个新的 platform 世代"，不得静默通过；
- 世代台账不 apply patch、不签名、不撤销 lease：`propose` 只记录补丁与 `git apply --check` 的结果，是否采纳由人决定；
- 世代引用必须用仓库相对路径；对外投影（页面）剥离 `artifact_ref`，不发布本机绝对路径。


## Current Implementation

- `research_agent/evolution_policy.py`：`EvolutionPolicyStore`（master switch + 三个安全 scope + locked 列表）；CLI `rsi policy show|set`、runtime `/api/evolution/policy`；关闭时 `rsi propose`/`propose-model`/`research-cycle` 拒绝新增候选，orchestrator 忽略 memory_order 并抑制候选；已有 lease 不撤销；
- `research_agent/rsi.py`：`Candidate / EvalEvidence / StepRecord / Lease / StepLedger / GovernancePolicy / RSIController / MetaTracker / trace_research`；
- 无模型训练、无外部 API；本地模型只做推理；
- `MetaTracker` 输出 episode 数、pending/approved/rejected、active/expired/revoked lease、lineage、warnings、next questions、逐 episode 的 predicted/actual，以及数值预测校准（status/coverage/MAE/bias/direction）；
- `ledger_story(ledger)` 把真实 episode、dry-run、public/hidden/near-OOD/regression、人签、租约、消费与 sealed confirmation 归一为只读 `RSIStory`；保留被拒绝候选与缺失门禁，不把确认后的 harness 变化升格为 capability claim；runtime `/api/rsi/story` 与 CLI `rsi story` 只读输出；
- `Lease.effective_status` 按 TTL 计算过期；expired lease 不参与执行、不能作为父代；`record_actuals` 把预测-实际写入 ledger；
- 默认 `propose` 只写 pending；`admit` 需要 public/hidden passed + dry-run + reason + scope；`revoke` 保留记录；
- `admit(strict=True)`（真实 retrieval/S5 trial 默认启用）要求四类 sealed 证据、非 simulation、evaluator、artifact/task-pack SHA-256、approver；证据一旦 evaluate 不得在 admit 替换；记录 `admission_mode`/`approved_by`/`evidence_digest`；
- `StepLedger` 追加 `*.events.jsonl` 哈希链（seq/prev_hash/entry_hash），`MetaTracker.report()["event_log"]` 只读校验；primary JSON 仍是当前快照；
- `EvolutionPolicyStore.allows_candidate` 改为默认拒绝：只允许三个已登记 safe scope 与 `skill:` 候选；closure/heldout 加入不可变面；
- `MetaTracker._claimable` 绑定 active lease；revoked/expired lease 的 episode 自动从 capability_claims 移除；父代打分不再把 cost/gap 当作越高越好；
- `rsi_fixture.py`：public 预筛后最多两个 finalist 按 public cost 顺序逐个过 hidden/near_ood/regression；指标含 gold recall、cost、coverage_gaps；coverage_gaps 不得增加；同一 benchmark 的 target+patch+scope 已存在时跳过；所有 fixture 证据标记 `simulation: true`；
- `real_eval.py` + `RealCorpusRetriever` / `MiniLMRetriever`：冻结 CC-BY 正文；`--retriever bm25|minilm|compare`；compare 预注册候选集选中 `minilm+budget3`；`resolve_active_harness` + `pipeline run --use-lease` 实际应用 lease；证据 `simulation=false`、`claim_eligible=false`；
- `real_eval.run_real_confirmation` / `rsi real-confirm`：在独立新问题上 sealed 复核 active real harness；`used_for_admission=false`；
- `s5_eval.py` + `rsi s5-trial`：本地 iris 真跑 5-seed incumbent vs 4/3/2；public 预筛后最终候选过 hidden/near/regression；实测 seeds3 通过，cost 10→6、mean −0.0025、min 不变；人签后发 S5 lease；claims 为空；
- `modules/run` + `run execute|claim`：RunCapsule/EA/人签 Claim；`pipeline run --claim-file` 把 claim 引到 paper.result.primary 标 `bound_claim`，不写数字；
- `adapters/local_hf_model.py` + `rsi propose-model` + `rsi real-trial --candidate-file`：本地 frozen Qwen2.5-0.5B-Instruct 生成候选；schema 归一化后仍走 GovernancePolicy/gate；
- `model_batch.py` + `rsi model-batch`：3 条公开 observation 中 1 条 eligible、2 条 near-OOD 拒绝；
- `research_runner.py`：fixture research queue 与 S1 budget 消费；真实 research runner 仍为 fixture。
- `evolution_observations.py` + runtime `JobManager._record_observation`：每个 runtime job 完成后写入 observation（topic/route/status/stopped_at/max_sources/q0_status/packages/warnings/fixture）；观测不是证据；CLI `rsi observations show|suggest` 只读生成候选建议；
- `evolution_active.py` + CLI `rsi active show|activate|deactivate`：activation 复用 active lease + 四类 passed 证据 + 人理由，只走 CLI；runtime 只读 `/api/evolution/active` 并在下一次 job 消费 `literature.retrieval.budget`；
- runtime 对非空 `run_dataset` 解析 `S5/demo/<dataset>` active seed lease，覆盖 `run_seeds` 并在事件流记录；无 lease/冲突时沿用请求值并明确记录，不静默伪造生效；
- 观测→建议→real-trial/s5-trial→admit→active→下一轮 job 的收益回写仍只记录过程指标，不是 capability claim。
- `research_agent/rsi_harness2.py`：接缝层——`probe`（定位 Harness² 与 3.12/3.13 解释器，失败只报状态不抛）、`run_bridge`（调用 3.12 桥）、`validate_artifact`（冻结契约）、`conformance`（预算/任务/回退/分类/补丁自检）、`to_candidates`（去重 + 不可变面拦截）、`to_evidence`（public + 可选 hidden，强制 simulation）、`record_episode`（只写 pending）；平台侧仍是 Python 3.8，不导入 Harness²；
- `scripts/harness2_run.py`：唯一导入 Harness² 的 3.12 桥；进程内安装两个便携性补丁（`fcntl.flock`、`tree.read_tree` POSIX 路径），跑 `schedule.run_domain`，产出 `harness2-run-0.1`；内置 `demo`（上游确定性 demo）与 `science`（claim↔span 绑定任务包，含留出任务）两个适配器；
- CLI `rsi harness2 probe|run|status|record`；`run` 在自检不全时以非零退出；`record` 写 pending episodes 并输出台账摘要；runtime `GET /api/rsi/harness2` 只读返回产物投影与探针状态，`?record=true` 仅列出"将会写入什么"；
- 站点 `site/rsi/` 读 `site/data/harness2.json`（由 `build-site.mjs` 从 `runtime_data/harness2/story.json` 同步）；没有产物时页面显式留空，不填默认数字；
- 已实跑：`k=2`、`agg+seq`、3 个任务，`R=48/48`、`P=36/36`、6 次采纳（去重后 1 条候选）、留出 1/1（基线 0/1）；全部标记 `simulation=true`、`claim_eligible=false`；台账 episode 停在 `pending_human`，`near_ood/regression/dry-run/lease` 缺失点名可见。
- `research_agent/evolution_generations.py`：`Generation` / `GenerationStore`（append-only + 哈希链）提供 `open/close/list/compare/verify/story`；`agent_generation_from_run` 把一次 Harness² 运行记成 agent 世代（树 SHA + episode + 证据摘要，同树换平台自动 supersede）；`platform_snapshot` / `propose_platform_patch` 记平台世代与补丁提议；`summarize_lineage` 生成页面投影并剥离 `artifact_ref`；
- `Harness2` 产物新增 `platform_fingerprint`，`summarize` 带到 story；`rsi harness2 record --generation LABEL` 在一次调用里同时写 episode 与 agent 世代；
- CLI `rsi gen list|verify|snapshot|propose|close|agent|compare|export`；runtime `GET /api/rsi/generations` 只读返回双轨 lineage 与 warnings；
- 站点 `/rsi/` 新增 `02 / GENERATIONS`：左右两轨世代链、当前指纹、复验告警；数据来自 `site/data/evolution.json`（由 `build-site.mjs` 从 `runtime_data/evolution/story.json` 同步）；
- 已实跑世代链：平台 P1（f692c16, 8640c59332cc379a）→ P2（5a3468317b2bf3df）→ P3（d9d851a50bd7ba58, adopted）；agent G0（树 5110f019…, 跑在 P2）→ G1（同树, 跑在 P3, adopted，G0 自动 superseded）；`rsi gen verify` 输出 `ok=true`、0 error、0 warning、8 条事件。


## Boundaries

- 不是 RSI 本身；只是 RSI 的治理与记账层；
- 没有真实研究执行器/EA 时，不能填 capability claim；
- 不自动生成科学假设、不自动改 claim/门槛/判据；
- 没有人类签字不能 active；没有 hidden eval 不能宣称泛化；
- 负结果和撤销记录不能删除。
- 不是代码托管：世代台账只存指纹、提交与备注，不存全量源码；没有 commit 时只能靠 note 重建，`verify` 会点名；
- 平台指纹只覆盖 `research_agent/**/*.py`：SPEC、测试、脚本、前端改动不会移动它，所以"指纹没变"不等于"什么都没变"；
- 世代台账不判断"这次进化好不好"：它记的是版本、证据与耦合；好/坏仍由 public/hidden/留出与人签回答。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 只改 `research_agent/rsi.py` 与 `tests/test_rsi.py`；
4. 不碰 literature/figure/paper 的证据边界；
5. 跑 `python -m unittest discover -s tests -v`。

## Changelog

- 2026-11-10 · v0.12.0 · status=pilot · 解耦接缝与证据代码指纹：ports.py 新增 `ProposerPort`/`EvaluatorPort` 协议（候选/评测供给契约），内部简单自改进、外部 Agent（Claude Code/Codex/Qoder/Zcode）与同学后续细粒度自进化引擎均可实现，平台只校验证据形状与哈希、不伪造指标；`EvalEvidence` 新增 `code_fingerprint` 并在 `__post_init__` 自动绑定产生该证据的平台代码指纹（D9 verdict 绑定，verdict 不得跨构建静默复用）。与 v0.9–0.11 的版本接缝/世代/harness² 互补：执行与供给可替换，判据与台账不搬家。新增 tests/test_rsi_ports.py（外部 fake proposer/evaluator 走通 propose→evaluate、证据自动绑指纹）。
- 2026-11-10 · v0.11.0 · status=pilot · 自进化本身做双轨版本管理：agent 轨道记采纳树 SHA-256 + episode + 证据摘要，platform 轨道记 research_agent/**/*.py 的代码指纹 + 提交/备注；两条轨道由 platform_fingerprint 关联。新增 Generation/GenerationStore（append-only + 哈希链，open/close/compare/verify/story）、agent_generation_from_run（同树换平台自动 supersede 旧记录）、platform_snapshot、propose_platform_patch（只记 git apply --check 结果，不应用）；CLI rsi gen 七个子命令、runtime /api/rsi/generations、/rsi/ 世代区块与 site/data/evolution.json。跨轨耦合：adopted agent 世代的平台指纹与当前不一致时 verify 报 stale_agents 并要求复验，但不自动撤销租约、不改 claim。实跑 P1→P2→P3 + G0→G1 五条记录、8 条事件，verify ok、0 warning。新增 tests/test_evolution_generations.py 19 例。
- 2026-11-10 · v0.10.0 · status=pilot · 自进化执行下沉到外部 Harness²，平台只保留接缝。新增 harness2-run-0.1 冻结契约（预算恒等式 R=4k/P=3k、任务状态、采纳树、经验证据、classification 与 task_pack_sha256）、conformance 自检（10 项）、Candidate 去重与不可变面拦截、public/hidden 证据映射（强制 simulation=true、claim_eligible=false）、held-out 由平台侧执行；新 scope harness2.harness 只登记可编辑面，record 只写 pending_human。动机：会议设定要求「剥离自迭代、调用 RSI 基础设施」，而上一版平台自带最小控制面，容易被误读为重复造轮子；接缝让执行侧可替换、判据侧不搬家。新增 tests/test_rsi_harness2.py；实跑 k=2 双模式 R=48/48、P=36/36、留出 1/1（基线 0/1）。
- 2026-11-10 · v0.9.0 · status=pilot · 平台与自进化互补的版本接缝：`Candidate.version`（自进化候选版本，由进化核心/同学填写）与 `StepRecord.platform_fingerprint`（propose 时自动取 `paths.build_fingerprint()`）写入 ledger 与 propose 事件。动机：同学的自进化基础设施要对"自进化本身"做版本管理、并对平台代码做自我迭代；平台侧必须把"哪一版平台代码产生了哪一版候选/episode"记下来，才能关联、复现与回滚，而不必平台自己实现进化算法。契约新增字段（向后兼容，默认空/自动指纹），不改变 claim/EA/gate 不变量。新增 tests/test_rsi_version_hook.py。

- 2026-11-08 · v0.8.0 · status=pilot · 新增 `rsi actuals --episode ID --metric KEY=VALUE [--note]`，闭合人工提案的校准环（#96 的另一半）。v0.6.0 让 `rsi propose --predicted-metric` 能写预测，但 `actuals` 此前只在 `rsi_fixture`/`s5_eval` 内部写，人工提案的同一 episode 没有文档化命令记实测，校准环对人工候选仍不闭合。现在 `rsi actuals` 调 `RSIController.record_actuals`，复用 `_predicted_metrics` 的数值解析（拒收非数值/inf/nan）。行为用例钉住：预测+实测共享一个度量 ⇒ tracking.status="tracked"、compared_episodes≥1；只有实测无预测 ⇒ 仍 "uncalibrated"（不假报 tracked）。命令面用例断言 `rsi propose --help` 含 `--predicted-metric`、`rsi actuals --help` 含 `--metric/--episode`。33 例通过。这是"审计层读的每个字段都要有文档化命令能写"这条守卫的第一个完整闭环实例。
- 2026-11-05 · v0.7.0 · status=pilot · rsi story 升 rsi-story-0.4，采纳投影契约（60 号文档 D1，实现见 modules/integration v0.42.0）：返回体新增 `source_fingerprint`（生成它的代码指纹，取自 paths.build_info，于是"宿主读到的是不是当前代码"一次比较即可判定，与 #76 的 served build 同一机制）、`base`（"一个台账：N 个 episode；下面每个计数只描述这个台账，不描述项目也不描述 harness"）、`provenance`（simulation_episodes / episodes / source）。动机是实测：AST 枚举 171 个投影后发现 story 只带 generated_at 与 read_only，缺指纹与基，因此一份被转贴的 story 无法回答"这是对哪份代码、哪个台账说的"。判定语义、计数、gate_verdict 四态与警告文字一律未动；有一条用例专门断言 story 的 base 里带 episode 数、fingerprint 与 build_info 一致、provenance.simulation_episodes 与台账一致。
- 2026-11-05 · v0.6.0 · status=pilot · 自改进回路补上两个"结构上不可能"的缺口。(1) 数值预测无法从命令面进入回路：`Candidate.predicted_metrics` 早在数据模型里、早有 numeric/finite 校验、tracking 会读它、story 也会序列化它，但**没有任何文档化命令能填它**——`rsi propose` 只有 `--predicted`（散文）。实测后果：`rsi propose` 造出的 episode 一律 `predicted_metrics={}`，`rsi fixture` 造的 4 个 episode 也全是 `{}`，于是 story 恒报 `calibration: uncalibrated` 与警告 "actuals recorded without numeric predictions"，跑多少次试验都一样。一个不能被校准的回路只能积累拒绝，无法改进自己的判定规则。现在 `rsi propose --predicted-metric KEY=VALUE`（可重复；纯函数 `_predicted_metrics` 解析，拒收缺等号、空键、非数值、inf/nan，并在报错里带上 offending 原文）。(2) 模拟来源在汇总层被丢掉：episode 自带 `simulation`，tracking 甚至算过一个 all-simulated 标志（rsi.py:826），但 story 的 summary 两者都没带，读 headline 计数的人分不清"演练过的回路"与"改进过的回路"。现在 `rsi-story-0.3` 的 summary 带 `simulation_episodes`（**按 episode 计数，不是全有全无**——混合台账正是全有全无会读成"真实"的地方），并在 >0 时追加警告：这条 story 重建的是被演练的回路、不是被改进的回路，其计数不构成真实能力增益的证据。实测三态：fixture 台账 4/4 simulated、`rsi propose` 台账 0、混合台账 1/2。这与 #60（from-idea 不接受预注册 ⇒ 121 个包里 origin 与 prereg 零共存）、#86（primary_metric 写死 ⇒ 达标主张签不了）是同一形状：**数据模型支持正确做法、校验也在、读取端也在，但命令面表达不出来，于是该证据在生产路径上恒为空**；已记为 #96，建议加一条枚举式守卫——审计/校准层读的每个字段，至少要有一条文档化命令能写它。测试 tests/test_rsi_self_improvement.py 共 9 例（解析 4 + 往返 2 + 模拟披露 3），与既有 test_rsi / test_mcp_evolution_status 合计 32 例通过。
- 2026-11-03 · v0.5.1 · status=pilot · gate_stops 分类修正（实测出来的自己的错）：lease:active 与 human:approved 原本被当成"未通过的关卡"计入 stops，等于把门禁的成功写成失败；revoked 仍留在 stops 里，因为自动降级是要被看见的信号。新增用例直接钉住这条断言。
- 2026-11-03 · v0.5.0 · status=pilot · rsi story 升 rsi-story-0.2：summary 新增 decided / rejection_rate / gate_verdict / gate_stops 与判定边界文字。gate_verdict 四态 no_episodes / awaiting_decisions / gate_uninformative / informative，其中"本轮一次都没拒过"判为 gate_uninformative 而不是好消息——这与检索探针饱和是同一失效（#45），拒绝率是对门禁与任务集的读数，不是提案质量的分数。gate_stops 按 gate:state 计未通过的关卡，让从没开火的关卡点名可见（实测本地唯一台账：episodes 1、decided 0、public/hidden/near_ood/regression/lease 全 missing）。5 个新用例分别钉住四个状态与 gate_stops 的正反面。
- 2026-10-29 · v0.4.0 · status=pilot · 0.4.0（2026-10-29）：闭合返回边。(1) record_confirmation 遇 regressed 自动撤销对应 active 租约（只降级、不升级）；(2) ActivePolicyStore 每次 resolve/snapshot 都重读源租约，撤销立即生效而不再等到 TTL，账本缺失/不可读时 fail-closed；(3) literature.retrieval.budget 与 experiment.run.seeds 注册进 SAFE_SCOPES，activate 必须过 scope 门，门禁第一次真正管到运行时消费的目标；(4) 激活记录保存 ledger_path，snapshot 对外隐藏该路径并暴露 lease_state。契约变化：确认不再是纯审计记录，降级可自动。
- 2026-10-28 · v0.3.1 · status=pilot · 接通生产自进化闭环：runtime job 完成写 observation；新增 `rsi observations show|suggest` 与 `rsi active show|activate|deactivate`（仅 CLI 人理由）；runtime 消费 active literature budget 与 S5 seed lease，并在事件流记录；观测/建议不进入 Claim/EA/Closure。
- 2026-10-26 · v0.3.0 · status=pilot · 自进化闭环加硬：strict admission（四类 sealed 证据 + evaluator/artifact/task-pack hash + approver）、证据不可替换、capability_claims 只认 active lease、默认拒绝的 policy、append-only 哈希链事件日志；真实 retrieval/S5 trial 走 strict。
- 2026-10-24 · v0.2.1 · status=pilot · 新增 EvolutionPolicy：master switch + literature.memory_order / literature.query_planner / orchestrator.facet_budget 三个安全 scope；关闭时阻止新的 propose/model/research-cycle 候选并让 orchestrator 忽略记忆调序，已有 lease/confirmation 不追溯撤销；Claim/EA/gate/rubric/held-out/closure/signature/export 保持 locked；新增 CLI `rsi policy` 与 runtime 本地管理端点。
- 2026-10-24 · v0.2.0 · status=pilot · 只读故事重建：新增 ledger_story/RSIStory，把 episode、dry-run、public/hidden/near-OOD/regression、人签、租约、消费与 sealed confirmation 归一为审计时间线；新增 runtime /api/rsi/story 与 CLI rsi story；不改变准入、claim 或能力边界。
- 2026-10-24 · v0.1.28 · status=pilot · 静态加固：confirmation 写入严格校验 sealed 布尔、status/passed 一致、scope 与 lease 匹配、delta 有限数值；trace 校验 confirmation 文件与 ledger artifact hash 链接、dataset 前缀精确匹配；修正 _evidence 单行定义
- 2026-10-24 · v0.1.27 · status=pilot · 最小改进：StepLedger 增加 confirmations 审计记录；S5 sealed confirmation 自动记为 confirmed/regressed/unsupported，强制 sealed 且 used_for_admission=false；MetaTracker 汇总并告警未确认 active lease；ChemLab lease 记录 confirmed，claims 仍为空
- 2026-10-24 · v0.1.26 · status=pilot · 最小改进：FrozenModelProposer 增加 schema-repair 重试（冻结模型、错误回灌、仍过同一 public/hidden gate）；3 条固定观察实测 0 次修复、1/3 eligible、2 条被 near-OOD 拒绝，说明当前瓶颈是 gate 而非 JSON schema
- 2026-10-24 · v0.1.25 · status=pilot · 最小改进：增加 rsi trace 只读审计，校验 active lease -> capsule seeds/dataset -> 无 capability claim -> sealed confirmation 的 linkage；ChemLab 实跑 7/7 检查通过
- 2026-10-24 · v0.1.24 · status=pilot · 最小改进：ChemLab sealed confirmation 改用 42 条 held-out 反应；已签 seeds2 复核 confirmed（mean R2 +0.00566、min +0.00966、cost 20->8、failed 0），used_for_admission=false；仍 claim_eligible=false
- 2026-10-24 · v0.1.23 · status=pilot · 最小改进：S5 增加 ChemLab R2 基准（seeds2 通过，cost 10->4，mean -0.0095，min +0.0402；数值预测 cost 精确、mean 偏差 0.0095）；ChemLab confirm 无新 held-out 反应集时返回 unsupported；修复 test_size 未生效导致的 split 复用
- 2026-10-24 · v0.1.22 · status=pilot · 最小改进：Candidate 支持数值 predicted_metrics；MetaTracker 增加预测-实际校准（MAE/bias/direction/coverage），无数值预测时显式标 uncalibrated/partial；校准仅描述过程，不改变 capability claim 边界
- 2026-10-24 · v0.1.21 · status=pilot · 最小改进：pipeline run --use-s5-lease 消费 S5 seed lease 并执行真实 run，产出 EA + claim draft；paper.result.primary 在 claim draft 阶段保持 pending，只有人签 claim 后才 bound_claim
- 2026-10-24 · v0.1.20 · status=pilot · 最小改进：S5 支持 breast_cancer；iris 选 seeds3，breast_cancer 选 seeds2（cost 10→4、mean −0.0055），两者均通过 sealed 复核；结论按数据集分别报告，不宣称通用
- 2026-10-24 · v0.1.19 · status=pilot · 最小改进：增加 S5 sealed confirmation（4 个新 test_size）；已签 seeds3 复核通过，mean −0.001、min 不变、cost 20→12，used_for_admission=false
- 2026-10-24 · v0.1.18 · status=pilot · 最小改进：run execute --use-lease 解析 S5 seed lease，实际以 3 seeds 运行并记录 active_harness；无 lease 显式失败
- 2026-10-24 · v0.1.17 · status=pilot · 最小改进：S5 seed-budget evaluator；5 seeds incumbent vs 4/3/2，seeds3 通过 hidden/near/regression，cost 10→6、mean −0.0025、min 不变；人签后发 S5 lease，claims 为空
- 2026-10-24 · v0.1.16 · status=pilot · 最小改进：增加 3 篇未参与设计的 CC-BY 论文 held-out transfer corpus（6 问）；已签 minilm+budget3 复核 recall/gap 不变，cost 因语料仅 3 篇而持平；不宣称通用迁移
- 2026-10-24 · v0.1.15 · status=pilot · 最小改进：增加 real-confirm sealed 复核（4 个新问题、独立 tasks pack）；已签 MiniLM+budget3 lease 复核通过，cost 28→24、recall/gap 不变，used_for_admission=false
- 2026-10-24 · v0.1.14 · status=pilot · 最小改进：增加 model-batch prompt 稳定性审计；3 条公开观察下 1 条 eligible、2 条被 near-OOD 拒绝，逐条保留 gate 结果
- 2026-10-24 · v0.1.13 · status=pilot · 最小改进：接入本地 frozen Qwen2.5-0.5B-Instruct proposer、候选 JSON 与 candidate-file 评测；模型提案保留 id/rationale，仍走 public/hidden gate 与人签
- 2026-10-24 · v0.1.12 · status=pilot · 最小改进：pipeline run --use-lease 解析 active real harness lease 并实际切换到所选 retriever+budget；无 lease 或冲突时显式失败，不静默回退
- 2026-10-24 · v0.1.11 · status=pilot · 最小改进：候选可包含 retriever+budget 组合（bm25/minilm），候选集预注册；compare 模式下 governor 以 near-OOD gate 选中 minilm+budget3，bm25+budget2 作为负结果保留
- 2026-10-24 · v0.1.10 · status=pilot · 最小改进：real-trial 支持 --retriever bm25|minilm；MiniLM 是人工指定的独立 frozen-retriever probe（abstract 级），不是 RSI 自动提出的候选；结果仍 claim_eligible=false
- 2026-10-24 · v0.1.9 · status=pilot · 最小改进：同一 benchmark 的 target+patch 去重；重复 real-trial 只返回 skipped 候选，不新增 episode 或 lease
- 2026-10-24 · v0.1.8 · status=pilot · 最小改进：active lease 解析增加 expected_scope；fixture research/confirm 只消费 S1/fixture，真实 probe 的 lease 不会跨 benchmark 生效
- 2026-10-24 · v0.1.7 · status=pilot · 最小改进：增加 CC-BY 真实论文语料与 S1 real-trial；public 排序后最多两个 finalist 依次过 hidden gate；真实语料标记 claim_eligible=false，人签后 capability_claims 仍为空
- 2026-10-24 · v0.1.6 · status=pilot · 最小改进：lease TTL 与冲突 fail-closed；prediction actual 写入 ledger 并由 MetaTracker 汇总；预算提案改由 retrieval_cost 触发，coverage gap 只作 guard 且不得增加
- 2026-10-24 · v0.1.5 · status=pilot · 最小改进：增加租约后 sealed confirmation（独立 tasks_confirm.json），只做复核，不回流选择/准入；无 active lease 时显式返回 no_active_lease
- 2026-10-24 · v0.1.4 · status=pilot · 最小改进：hidden 只用于 public 预筛后的最终候选；fixture 证据标记 simulation；active lease 绑定到 ResearchRunner 的 S1 预算并产生租约后研究批次
- 2026-10-24 · v0.1.3 · 增加 ModelPort、FrozenModelProposer 与可选 DeepSeek adapter；离线测试只用 fake model，未发起网络调用。
- 2026-10-24 · v0.1.2 · 增加 fixture research queue 与 research→observation→TF-RSI cycle；观测仍为合成任务。
- 2026-10-24 · v0.1.1 · 增加 CandidateArchive/父代选择、OOD/regression split、fixture TF-RSI 回路；仍无真实论文/实验评测。
- 2026-10-23 · v0.1.0 · 初始控制面：候选策略、step ledger、人签准入、lease、revoke、MetaTracker；无真实评测。

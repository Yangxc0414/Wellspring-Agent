---
id: feedback
name: 反馈端口
stage: S5–S16
version: 0.6.0
status: pilot
owner: research-agent
inputs:
  - ProjectDirectory
  - LineageManifest
  - VerdictLedger
outputs:
  - FeedbackLedger
tools:
  - feedback.list
  - feedback.run
gates:
  - G5
invariants:
  - 默认关闭：未显式启用任何环时，本模块不写任何文件、任何投影输出与不存在本模块时逐字节一致
  - 每条环 observe → propose → gate → apply → record；gate 对会改动任何受门禁产物（claim/EA/closure/signature/export）的 proposal 一律默认拒绝
  - v1 只允许只读 effect（重验 + 记录回执）；任何自动改写都是 roadmap 且必须先注册 SAFE_SCOPES 式准入
  - 账本行确定性：不含墙钟字段；同一批产物跑两次环，行内容逐字节一致（来源 sha256 绑定）
  - 反思不是环：只产出文本而不改变下一步动作的机制不进入本注册表（71-图① 底注口径）
---

# 反馈端口（FeedbackPort）

## Purpose

把「判定改变下一步行动」做成可插拔的一等接缝：每条反馈环 = observe（读判定/产物）→ propose（确定性建议）→ gate（默认拒绝）→ apply（只在允许范围内）→ record（确定性账本）。服务于 71-图① 的四条反馈环（T6b 证伪/反事实、信念修订、溯源/失效传播、同质化监测）与 M1 五类反馈对照实验——环与环之间可单独开关、单独测量。明确不解决：不产生新判定（判定来自 verdict-ledger 单点与各产物）；不替代人工门；不做常驻进程。

## Contract

- 输入：项目目录；`loops` 显式启用清单（默认空 = 全关）。
- 输出：`feedback-ledger-0.1`——`rows`（每行 `loop_id/subject/observation/proposal/gate_decision/effect`，来源产物绑 sha256）、`loops`、`boundary`；仅当至少一条环启用并产生行时写 `feedback-ledger.json`（原子写）。
- 消费侧（v0.4.0，v0.6.0 类型化）：`generation_constraints(project)` 读 `feedback-ledger.json`，提取 `proposal.kind=generation_constraint` 且 gate 为 auto_allowed 的行；输出 `generation-constraints-0.2`：每行带 `constraint_kind`（`carry_falsification` / `require_falsification_binding` / `demote_candidate` / `carry_forward` / `require_lens_diversity`）+ `payload`，`constraint` 文本仅供人读；生成端按 kind 消费，不解析散文。**只有 `require_lens_diversity` / `demote_candidate` / `carry_falsification` 三种真正改变生成的 kind 越过消费边界**；`carry_forward` / `require_falsification_binding` 留作账本回执（审计/人工），不进生成 provenance。逐条重算 `observation.source_path` 的 sha256——不匹配或缺失 → 默认拒绝，入 `stale`；行带辅助绑定（`idea_source_path/idea_source_sha256`）时同时校验，任一变化即 stale。旧文本账本在消费边缘一次性推断 kind/payload 并标 `legacy_inferred=true`；未知 kind 不猜测。确定性排序，只读不写盘；账本缺失/不可读 → 空 constraints（fail-closed）。
- 失败：未知环 id → 拒绝并列出已注册环；观察对象不可验（如 lineage manifest 损坏）→ 该行 `state=verify_failed`，不中断其余环。
- 证据边界：不创建 Claim / EA / gate / signature；v1 的 apply 只执行只读重验并把回执记入账本；消费侧只把新鲜约束交给生成端，stale 约束可见地拒绝。


## Current Implementation

- `research_agent/feedback.py`：注册表 `_LOOPS` + `run_feedback(project, loops=None, limit)`；`loops=None`（默认）→ 返回 `status=disabled` 且**不落盘任何文件**。
- 已注册环（v0.1.0）：`lineage_reverify`——溯源/失效传播环的回指侧：observe = 对每个含 `lineage/lineage.json` 的 run 重跑 `LineageAgent().verify`（只读），state = impact 的 `status/changed/stale/requires_reclosure/requires_resign/export_allowed`；propose = 记录回执 + stale 时给出人工下一步文案；gate = 只读自动放行、改动类一律拒绝；apply = 账本记录。
- v0.2.0：确定性决策表 `verdict_action_table(rows)` + `t6b_falsification` 环；v0.3.0：`belief_revision` / `homogeneity` 环（记录化）。
- v0.4.0 消费侧：`generation_constraints(project)`——generation_constraint 行的只读消费端，来源 sha256 新鲜度校验（stale 默认拒绝）。idea 模块 0.25.0 消费它（lens 多样性强制、shortlist 降权、否证条件携带）并把 `feedback_constraints_applied` provenance 写入 idea.json；pipeline（integration 0.50.0）接线。图① 后三环由此从「记录化」变为「判定 → 下一步动作」。
- CLI：`python -m research_agent feedback list` / `feedback run --project P [--loops lineage_reverify] [--limit N]`；MCP/HTTP 暂不暴露（roadmap）。
- 是否联网：否。fixture：测试用临时目录伪造最小 run（run-capsule + claim），lineage manifest 由 `LineageAgent().build` 真实生成。


## Boundaries

- M1 五类反馈对照（真实/打乱/过时/含噪/矛盾）已跑在本端口上（scripts/m1_feedback_sensitivity.py，verdict=supported）；多 run 统计测量脚本 scripts/m1_multi_run.py 已就绪、按指示延后执行。
- T6b/信念修订/同质化的回指侧 v0.4.0 落地为生成约束消费（idea 0.25.0）：约束只影响候选生成（lens 多样性、shortlist 降权、否证条件携带），不改写任何受门禁产物；自动改写仍是 roadmap，须先注册 SAFE_SCOPES 式准入。
- `mandate.py`（读快照不重算）与前端 ContextPanel 的判定消费迁移属 verdict-ledger SPEC roadmap，不在本模块。
- lineage 尚未把 feedback-ledger / idea.json 的约束 provenance 纳入节点：生成侧失效目前由消费时 sha256 重算保证（stale 默认拒绝）；把「claim → idea → 约束 → 判定」整链纳入 lineage 图登记为 roadmap，不在本轮扩契约。


## Minimal Change Workflow

1. 新增环：先在本 SPEC Contract 增行 → 注册表加 observe/propose/gate/apply 四函数 → tests/test_feedback 加「禁用时零写入 + 确定性」断言 → version 升 minor。
2. 只改某环的观察/建议文案：patch。
3. 让某环获得自动改写权：**停下**——需要先在 rsi 的 SAFE_SCOPES 注册 scope 并过 71-§4.0 默认拒绝纪律，SPEC 升 minor 且要求人工确认。

## Changelog

- 2026-11-11 · v0.6.0 · status=pilot · 类型化约束协议：三环 proposal 增 constraint_kind（carry_falsification/require_falsification_binding/demote_candidate/carry_forward/require_lens_diversity）+ payload；generation_constraints 输出 generation-constraints-0.2 透传 kind/payload，旧文本账本在消费边缘一次性推断并标 legacy_inferred=True——生成端不再依赖英文散文匹配；未知 kind 不猜测、不消费。tests/test_feedback 2 项。
- 2026-11-11 · v0.5.0 · status=pilot · 证据链加固：belief_revision 观察改绑主来源 idea-review.json（判定侧）+ 辅助绑定 idea.json（标题侧）；generation_constraints 同时校验主/辅 sha256，任一变化即 stale 默认拒绝——评审改了而约束不失效的洞被堵上。tests/test_feedback 增 review 变更失效断言。
- 2026-11-11 · v0.4.0 · status=pilot · 消费侧落地：generation_constraints(project) 读 feedback-ledger 的 generation_constraint 行，逐条重算来源 sha256——不匹配即默认拒绝入 stale 清单（上游变更→失效→回指复验在生成消费侧的落点）；只读、不写盘；idea 模块消费并写 provenance（见 idea 0.25.0）。图① 后三环从「记录化」升级为「判定→下一步动作」。tests/test_feedback 增消费侧断言。
- 2026-11-11 · v0.3.0 · status=pilot · 注册三环中的后两环：`belief_revision`（图① 反馈环 C 记录化第一步——idea.json candidates × idea-review.json reviews 的 recommendation/reasons，revise/needs_more_work → 「revise or drop」约束，approve → 「carry forward」，自动信念修订机制仍是 roadmap）；`homogeneity`（图① 自环记录化——lens 分布 + single-source 占比的确定性计数，total<3 诚实报 insufficient_data、dominant_share≥0.67 报 homogeneous 并给多样性约束，diverse 零 proposal）。真实 E2E 数据实证：belief_revision 4 行（全 revise）、homogeneity insufficient_data（2 候选不足 3，无 proposal 入账——账本记行动建议，不记观察日志）。tests/test_feedback 增 3 项，升 minor。
- 2026-11-11 · v0.2.0 · status=pilot · 新增确定性决策表 `verdict_action_table(rows)`（71-§4.2 设计输入 3 的落点：verdict 行 → 每 subject 一个建议动作；同 subject 判定矛盾或不变量违例——closure signed 而 claim 未签——升级 `escalate_conflict` 交人工，不猜赢家；`snapshot_drift` → `verdict_bus_authoritative`）；`scripts/m1_feedback_sensitivity.py` 五类反馈（real/stale/shuffled/noisy/contradictory）判别力 harness，预注册判据下实测 E2E 项目 verdict=supported（real 1.0 / 退化均值 0.333 / 矛盾 5/5 升级）；**M1 第二半**：决策表接入 `research_next_actions`（kind=verdict_action，只带本 run 的 subject，绑 source sha256），端到端实测 RUN-E2E-02 `behavior_changed=True`（baseline=stale capsule 重签建议 → wired=verify_bundle/closure_check）；注册第二环 `t6b_falsification`（图① T6b 审计项 → 记录化 proposal：读 study-origin.json 的否证条件 × study claim 状态，stale/缺失都给出约束文本，自动注入生成提示词仍是 roadmap）。tests/test_feedback 16 项 + tests/test_verdict_ledger 13 项。升 minor。
- 2026-11-11 · v0.1.0 · status=draft · 初始实现：注册表 + `lineage_reverify` 环（71-§5 步 2 的第一条环，图① 反馈环 B 的回指侧）；验收测试钉「关闭全部环 = 与今日行为逐字节一致」（默认零写入，投影不受模块存在影响）+ 环运行的确定性 + gate 对改动类 proposal 默认拒绝；tests/test_feedback 6 项。

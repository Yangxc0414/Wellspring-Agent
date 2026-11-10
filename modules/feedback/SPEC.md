---
id: feedback
name: 反馈端口
stage: S5–S16
version: 0.1.0
status: draft
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
- 失败：未知环 id → 拒绝并列出已注册环；观察对象不可验（如 lineage manifest 损坏）→ 该行 `state=verify_failed`，不中断其余环。
- 证据边界：不创建 Claim / EA / gate / signature；v1 的 apply 只执行只读重验并把回执记入账本。

## Current Implementation

- `research_agent/feedback.py`：注册表 `_LOOPS` + `run_feedback(project, loops=None, limit)`；`loops=None`（默认）→ 返回 `status=disabled` 且**不落盘任何文件**。
- 已注册环（v0.1.0）：`lineage_reverify`——溯源/失效传播环的回指侧：observe = 对每个含 `lineage/lineage.json` 的 run 重跑 `LineageAgent().verify`（只读），state = impact 的 `status/changed/stale/requires_reclosure/requires_resign/export_allowed`；propose = 记录回执 + stale 时给出人工下一步文案；gate = 只读自动放行、改动类一律拒绝；apply = 账本记录。
- CLI：`python -m research_agent feedback list` / `feedback run --project P [--loops lineage_reverify] [--limit N]`；MCP/HTTP 暂不暴露（roadmap）。
- 是否联网：否。fixture：测试用临时目录伪造最小 run（run-capsule + claim），lineage manifest 由 `LineageAgent().build` 真实生成。

## Boundaries

- M1 五类反馈对照（真实/打乱/过时/含噪/矛盾）跑在本端口上是下一步：当前环只有 `lineage_reverify`，反馈注入源与对照 harness 登记为 roadmap。
- T6b 自动回指、信念修订、同质化监测未实现（71-§2 图① 对照）；实现它们时各自注册为独立环，不得共用一个"反思"大环。
- `mandate.py`（读快照不重算）与前端 ContextPanel 的判定消费迁移属 verdict-ledger SPEC roadmap，不在本模块。

## Minimal Change Workflow

1. 新增环：先在本 SPEC Contract 增行 → 注册表加 observe/propose/gate/apply 四函数 → tests/test_feedback 加「禁用时零写入 + 确定性」断言 → version 升 minor。
2. 只改某环的观察/建议文案：patch。
3. 让某环获得自动改写权：**停下**——需要先在 rsi 的 SAFE_SCOPES 注册 scope 并过 71-§4.0 默认拒绝纪律，SPEC 升 minor 且要求人工确认。

## Changelog

- 2026-11-11 · v0.1.0 · status=draft · 初始实现：注册表 + `lineage_reverify` 环（71-§5 步 2 的第一条环，图① 反馈环 B 的回指侧）；验收测试钉「关闭全部环 = 与今日行为逐字节一致」（默认零写入，投影不受模块存在影响）+ 环运行的确定性 + gate 对改动类 proposal 默认拒绝；tests/test_feedback 6 项。

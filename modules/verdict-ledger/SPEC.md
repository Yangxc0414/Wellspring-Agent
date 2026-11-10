---
id: verdict-ledger
name: 判定总线
stage: S5–S16
version: 0.2.0
status: pilot
owner: research-agent
inputs:
  - ProjectDirectory
  - ClosureProfilesInventory
  - LoopCapsuleSnapshot
outputs:
  - VerdictLedger
tools:
  - verdicts.collect
  - verdicts.show
gates: []
invariants:
  - 只读投影：不产生新判定，不写 Claim / EA / gate / signature / evidence
  - 每行绑定其来源产物的 sha256；来源不可读时该行 fail-visible（status=unreadable），不静默
  - 确定性：同一批产物收集两次，输出逐字节相同（无墙钟字段）；审计靠重放不靠信任
  - snapshot_drift 只报告「重算 vs 快照」的差异，绝不改写快照本身
  - 输出不含绝对路径（可经 HTTP / MCP 只读面发布）
---

# 判定总线（Verdict Ledger）

## Purpose

把一个研究项目里**已经存在的判定**收敛成一份确定性只读投影，让消费者（next_actions、反馈环、autopilot、宿主 Agent）读总线而不是各自读快照。解决的具体缺陷：`loop-capsule.json` 的 blockers 是签署前快照——autopilot 在快照之后代签了 closure，快照仍然写 `CLOSURE_UNSIGNED`，跟着 next_actions 走的宿主会对一个已签署的闭包再喊一次 `closure sign`。明确不解决：不产生新判定（判定仍在各单点：closure_profiles / study_claims / study_replication / rsi 账本）；不做跨项目扫描；不承担导出或签署。

## Contract

- 输入：项目目录（`runs/RUN-*`、`experiments/EXP-*`、`studies/<dir>` 的产物）；`--limit` 控制 per-profile 扫描上限（与 closure_profiles 同参）。
- 输出：`verdict-ledger-0.1` JSON——`rows`（每行 `kind/subject/status/verdict_source/source_path/source_sha256/detail`）、`sources`（去重后的来源文件 + sha256）、`counts`、`present_profiles`、`boundary`。
- 行的 kind（v0.1.0）：`closure`（canonical_run，含 delegated 标记）、`claim`（signed/draft/absent）、`experiment`（local_experiment closure）、`study`（search_study closure，含 underpowered）、`snapshot_drift`（重算 = signed 而快照 blockers 仍含 CLOSURE_UNSIGNED；反向差异 v1 不报，登记在 Boundaries）。
- 失败：capsule 不可解析 → 该 run 的 snapshot 行 `status=unreadable` 并写 detail，不抛异常中断整份账本；项目目录不存在 → 抛错。
- 复算语义：判定全部来自 `closure_profiles.detect_project_profiles`（唯一判定来源）；本模块只做行映射、来源绑定与快照对照。

## Current Implementation

- `research_agent/verdict_ledger.py`：`collect(project, limit)` 纯函数 + `write_ledger(path, ledger)`（storage.write_json_atomic 原子落盘）。
- 快照对照读取 `runs/<id>/loop-capsule.json` 的 blockers；capsule 的其他字段一律不读。
- CLI：`python -m research_agent verdicts collect --project P --output <path>` / `verdicts show --ledger <path>`；MCP/HTTP 暂不暴露（roadmap：并入 `research_status` 载荷）。
- 是否联网：否。fixture：无（投影不依赖 fixture 数据；测试用临时目录伪造最小产物）。

## Boundaries

- v1 不读 rsi 账本（租约撤销 / regressed 事件的判定入账放到下一版；其账本位置不在项目目录内）。
- v1 的 snapshot_drift 只覆盖 closure 方向的「已签但快照仍说未签」；反向（快照没报、实际未签）与 claim/experiment/study 方向的漂移登记为 roadmap。
- 消费者迁移（v0.2.0 完成）：`mcp_server._loop_capsule_summary`（research_status / next_actions 的 capsule 摘要）在读到 CLOSURE_UNSIGNED 时先经判定总线重算，已签则**移除该 stale blocker、过滤 stale 的 closure sign 建议并附 `verdict_override`**；快照与重算一致时输出与迁移前逐字节语义一致（`verdict_override=null`）。`loop_ledger` 经查已从产物重算（G5 直接查 signature 文件），无需迁移；`mandate.py`（SPEC 规定"不重新计算门禁"）与前端 ContextPanel 的迁移登记为 roadmap。

## Minimal Change Workflow

1. 新增行 kind：先在本 SPEC Contract 增条目 → verdict_ledger 行映射函数加分支 → tests/test_verdict_ledger 加确定性断言 → version 升 minor。
2. 改动判定来源（closure_profiles 输出字段变化）：只改映射，不改判定；version 升 patch。
3. 暴露给 MCP/HTTP：先在 integration SPEC 记录只读工具条目，再动 mcp_server；verdict-ledger SPEC 只记 roadmap。

## Changelog

- 2026-11-11 · v0.2.0 · status=pilot · 消费者迁移第一步：`mcp_server._loop_capsule_summary`（research_status 与 research_next_actions 的 capsule 摘要）在快照含 CLOSURE_UNSIGNED 时经判定总线重算 closure 判定——已签则移除 stale blocker、过滤 stale 的 closure sign 建议、附 `verdict_override`（含来源 sha256）；快照一致时 `verdict_override=null`、输出语义与迁移前一致。`loop_ledger` 审计结果：已从产物重算（G5 直接查 signature 文件），无需迁移；mandate（SPEC 规定不重算）与前端登记 roadmap。实测 E2E RUN-E2E-02：迁移前摘要 status=blocked + 建议重签；迁移后 blockers 无 CLOSURE_UNSIGNED + override.recomputed=signed。tests/test_verdict_ledger 新增 ConsumerMigrationTest 3 项（覆盖 override、一致快照不动、缺 capsule），升 minor。
- 2026-11-11 · v0.1.0 · status=draft · 初始实现：closure/claim/experiment/study 四类判定行 + snapshot_drift（E2E 实测发现：autopilot 代签后 loop-capsule 仍报 CLOSURE_UNSIGNED，next_actions 指向对已签闭包的重复签署）；判定全部复用 closure_profiles.detect_project_profiles 单点，本模块零新判定；tests/test_verdict_ledger 钉确定性（两次收集逐字节一致）、来源 sha256 绑定、drift 行为。

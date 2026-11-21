# 文献台账上屏：EVIDENCE 面板对齐 modules/literature 契约

> 状态基线：2026-11-21。承接 141（人工门对话化与模块契约对齐，其 §5 把"文献台账"列为下一增量）、137（逐会话就绪度）、138（面板与会话同频）。
> 本文只改前端工作台（`apps/web`）；不改后端、不改 seed 转录文本、不新增任何实验读数。

---

## 0. 一句话结论

文献调研模块的后端深度（query plan / span 规则 / 来源构成 / 六面向覆盖 / gap 登记）此前只活在转录文本与 CLI 产物里，前端 EVIDENCE 面板只有一个 coverage 四格计数。本轮在 EVIDENCE 面板新增 **S1 文献台账**（LITERATURE LEDGER）：来源构成、六面向覆盖逐项核对、gap 登记列表、检索计划——全部从任务已有状态**只读派生**，面向注记逐字转录自会话产物声明，不发明任何数字。

## 1. 对齐映射：面板段 ↔ literature 模块产物

| literature 模块产物（CLI） | 台账段 | 数据来源（派生，不新增） |
|---|---|---|
| `query_plan{subqueries, source_scope, filters}` | 检索计划（可折叠） | 转录中已有的 plan 卡（`planFromMessages`）；ESE 的 RQ 挖掘计划不适用 |
| `counts{found, included_full_text, abstract_only, ...}` | 来源构成五行 | `task.coverage`（total / fullText = sources − abstractOnly / abstractOnly / spans / gaps）；两组 seed 转录原文（"3 条全文，1 条摘要-only"、"2 篇来源、1 篇有全文"）验证了该派生式 |
| 六面向覆盖审计（literature-brief 技能：core/survey/method/evaluation/limitation/recent） | 六面向逐项核对格 | `task.literature.facets` 注记，逐字转录：e2e 来自其 S1 覆盖声明（"只覆盖了 2/6（核心问题、综述），缺方法、评测、局限、近期进展"）；教学版与其 plan 卡三个子查询的面向归属一致（演示数据，按 demo 标签渲染） |
| `coverage.gaps[]` 逐条登记 | gap 登记列表 | `task.evidence` 中 kind=gap 的行（GAP-001 等）；coverage 计数与逐条行数不一致时显式说明差异来源 |

**未登记 ≠ 未覆盖**：没有面向注记的任务（示例任务）六格全部显示"— 未登记"，并注明面向核对由 literature-brief 技能按此六项执行——面板不猜。

## 2. 两个边界判断（本轮实测逼出来的）

1. **ESE（仓库挖掘）被排除**：它有 plan 卡，但那是 RQ 挖掘计划（repos/commits），不是文献检索计划；把它的"3 仓库"渲染成"全文 3"会冒名。`hasLiteratureLayer` 的规则定为：`spans > 0`，或"无 run capsule 且有 plan"（尚未执行的纯检索计划）。该规则有单测钉住（ESE 形状 → false）。
2. **coverage gap 计数 ≠ 逐条 gap 行**：e2e 的 coverage 登记 4 个 gap 但证据层没有逐条行（其 4 个 gap 就是四个未覆盖面向）。台账空态不再说"没有登记的 gap"造成自相矛盾，而是区分两态并指向 CLI 产物 `literature.json`。

**数据层注记 + run-once 迁移**：`task.literature` 与 `replay.basis` 同一纪律（design/137 的数据层标注），并加了 `ensureSeedLiteratureLedger` 迁移——旧 localStorage 快照里的两条 seed 会话自动回填注记，用户自建任务不动。

## 3. 已实测

- `npm run typecheck` 通过；`test:unit` 36/36（新增 `tests/literatureLedger.test.ts` 4 例：全文拆分派生式与两组转录原文一致 + 负数钳制、面向合并规则（已声明/未声明/部分声明）、gap 行提取与 plan 卡提取、hasLiteratureLayer 三态（含 ESE 形状排除））。
- 浏览器实测：教学任务（六面向已登记 3/6、plan 卡 3 子查询、GAP-001 行）、e2e（已登记 2/6 与其 S1 声明逐字一致、coverage-aware gap 空态）、ESE（台账不渲染）；旧快照迁移自动生效。
- `build` + `build:site` + `build-site.mjs` 刷新 `site/app` 镜像；`docs_audit` / `repo_hygiene` / `check_task_readiness.mjs` 全过。

## 4. 设计主张（可证伪）

1. 台账的正确数据策略是"派生 + 逐字转录"，不是"面板再算一遍"：全文拆分、面向归属都有单测或注释钉住出处，任何数字都能指回会话产物；
2. 文献层与运行层的边界必须显式（ESE 排除），否则台账会在仓库挖掘任务上冒名；
3. 面向注记放在数据层（task.literature）而不是面板硬编码，使未来 runtime 接入时同一面板可直接消费真实 literature-ledger.json 的同构数据。

## 5. 边界与剩余差距

- 面向注记目前只有两条 seed 会话登记；runtime 模式接入后应由后端在任务投影里带上 literature-ledger 的同构字段，而不是前端推断；
- 台账未展示 hits/duplicates/metadata（doi_coverage/year_range/recent_5y）等 ledger 字段——seed 会话没有这些数字，等真实 runtime 数据接入再扩段；
- design/141 §5 的其余增量不变：G1/G2 导入已签产物路径、verdict-ledger / feedback 端口投影。

## 6. Changelog

- `apps/web`：新增 `domain/literatureLedger.ts`（只读派生：来源构成、六面向合并、gap 提取、plan 卡提取、文献层判定）；`types.ts` 增 `LiteratureFacet/LiteratureAnnotation` 与 `ResearchTask.literature`；`seed.ts` 增 `SEED_LITERATURE_ANNOTATIONS`（两条会话逐字转录）并复用到 seed 与迁移；`workspaceStore.ts` 增 `ensureSeedLiteratureLedger` run-once 迁移；`ContextPanel` EVIDENCE 面板新增 LITERATURE LEDGER 段；样式（components.css）。
- 测试：`tests/literatureLedger.test.ts`（4 例）并入 `test:unit`。

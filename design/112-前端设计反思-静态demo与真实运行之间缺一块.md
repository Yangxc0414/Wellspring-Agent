# 112-前端设计反思：静态 demo 与真实运行之间缺一块

> 状态基线：2026-11-18。触发：111 号真实 API 全链运行完成后，发现 demo 页面**看不到这次运行**；用户也要求反思前端设计。
> 边界：本文是设计反思 + 一个小实现（真实运行面板）；不重写前端。

---

## 1. 现状盘点

| 前端 | 内容 | 数据来源 | 真实执行 |
| --- | --- | --- | --- |
| `site/`（GitHub Pages 静态站） | 12 个页面：home / app / demo / innovation / rsi / models / live / qoder / agent / docs | 构建时写死的 JSON/HTML | **不显示**（页面自称 static mirror） |
| `apps/web`（React/TS 工作台） | 45 个 tsx + 36 个 ts：domain/state/adapters/features | static adapter + runtime adapter | static 模式是 SIM；真实执行需本地 runtime |
| `runtime/` FastAPI | pipeline job / SSE / artifacts / 模型网关只读状态 | 本地 | 有，但页面无法从 Pages 访问 |

问题不是"缺页面"，而是**三段之间没有一条诚实的数据管道**：

- 真实运行发生在本地 CLI（本轮 pipeline/innovation/manuscript）；
- 它的产物在 `runtime_data/`；
- 静态站全靠手写与设计文档，读者无法在页面上核对"到底跑了什么"。

---

## 2. 具体问题（按影响排序）

1. **静态站与真实运行脱节**：111 号运行有 6 个阶段状态、5 个门禁、6198 span，页面上一句都没有；读者只能读文档。
2. **手写数字会过期**：模块数 33→34、测试 1300+→1500+、"缺--memory-pack"都踩过；根源是页面引用字面量而不是生成数据。
3. **没有产物溯源视图**：页面说"37.5%"、"run-capsule"，但不给 artifact 路径/哈希/生成命令，读者无法按图索骥。
4. **图与断言没有证据元数据**：四张策略图/双循环图的 caption 只有文字边界，没有"这张图对应哪个 artifact/哪条命令"。
5. **两套 UI 重复**：`site/` 与 `apps/web` 各自渲染同一批状态，字段名与状态口径容易漂移（例如 gate 命名）。
6. **真实执行只在本地**：这是安全边界（正确），但页面缺少"如何在本地复现"的一键命令块与预期输出。

---

## 3. 本轮实现的第一个修复：真实运行面板（生成式）

新增 `scripts/build_ese_run_panel.py`：

- 读 `runtime_data/ese-fullrun-20261118/demo.json`；
- 生成 `site/data/ese-run-summary.json`（run_id、fixture_mode、阶段状态、门禁状态、边界）；
- 在 `site/index.html` 的 `<!-- ESE-RUN-PANEL:START/END -->` 标记之间注入表格；
- 重跑脚本即可随新 run 更新，**不再手写状态**。

现状：面板显示 literature=ok(3 warnings)、synthesis=synthesized、idea=candidates_need_human、experiment=needs_human、figure=schematic_ready、paper=needs_evidence；gates: Q0=pass · G1/G2=needs_human · G3/G5=blocked；标注"本地真实 API 执行、门按设计停住、面板由脚本生成"。

测试：`tests/test_ese_run_panel.py` 3 例（状态保留、面板渲染含边界与 gate、缺 demo 报错）。

---

## 4. 后续前端设计建议（按优先级）

| 优先级 | 改动 | 说明 |
| --- | --- | --- |
| P0 | **统计与断言生成化** | 模块数/工具数/测试数/能力指标由 registry 与 fact-baseline 生成 JSON，页面引用；禁止再手写数字 |
| P0 | **运行索引页** | `runs/` 页列出最近 N 次真实运行（run_id/时间/阶段状态/门禁/产物哈希），由构建脚本生成 |
| P1 | **产物溯源卡** | 每个数字/结论旁给 artifact 路径 + sha256 + 生成命令；点击可复制 |
| P1 | **图注 evidence 元数据** | 每张图带 data-artifact/data-command，caption 由数据生成 |
| P2 | **统一状态口径** | site 与 apps/web 共用一份 `status.json`（gate 命名、阶段命名、颜色） |
| P2 | **本地复现块** | 每页给"在本地跑出这张图/这个数字"的命令与预期输出 |

---

## 5. 一句话

静态 demo 的问题不是"不够炫"，而是**它没有一条从真实运行到页面的生成管道**。本轮先补上最小的那块：把一次真实 ESE 全链运行的状态**生成**到页面上；下一步是把所有数字与图注都接到产物，而不是靠人记得更新。

## 3b. 补记：面板已覆盖到成稿审计

面板新增 `--project-run-dir/--review-dir`，读取 `manuscript-review.json` 与 `final-audit.json`，展示 review 状态/轮次/accepted 与 final audit 的引用数、汉字数、submission_ready；测试 5 例（含缺失下游的安全返回）。

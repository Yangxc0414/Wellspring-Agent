# Demo 展示面对照反思——从静态镜像到可证伪的后续路线

> 状态基线：2026-11-11（71 号文档落地后的第一轮展示面对照）。本文件记录对 demo 展示面（`site/`、`demo/`）的全量盘点结果与当轮修改。定位口径不变：**research-agent 仓库 = 早期 demo / 静态展示项目；智能体产品 = Wellspring-Agent（打开前端即工作台 + CLI + MCP）**；逐项实测读数以 `docs/fact-baseline.md` 为准。

## 1. 盘点方法

逐页对照 ground truth：46 个 MCP 工具（`tools/list` 为准）、1379 个 `def test_`（`tests/` 实测 grep）、28 个模块 SPEC（`modules/` 实测）、S0–S16 主链 + G1/G2/S5b/G5 四人工门 + Q0 自动门、1110 组会策略口径（四策略 × 三方向 × Q1–Q4 × M0–M3 × 四不做）、71 号解耦设计（判定总线 + 四端口）。

## 2. 三类发现

### (A) 过期数字与口径

| 位置 | 原文 | 问题 | 处置 |
| --- | --- | --- | --- |
| `site/index.html` hero | `6 模块 SPEC` | 实际 28 个 | 改 28 |
| 同上 | `9 门禁` | 无口径出处（gate-map 只列 4 人工 + 自动门） | 改「4 人工门 · G1/G2/S5b/G5」 |
| 同上 | `4 反馈环` | 四环中仅一条自动闭环，作为统计有夸大嫌疑 | 改「1/4 反馈环已自动闭环」——这一条同时是路线图的动机 |
| 同上 | `1300+ 自动测试` | 模糊 | 保留 1300+（grep 实测 1379 个 `def test_`，口径随版本变化已注记） |
| `site/index.html` #demos / #strategy | `9 阶段对象流` / `18 阶段全链` | 与 canonical S0–S16 双口径并存 | 统一为「9 幕叙事压缩（门禁对齐 S0–S16 canonical）」/「S0–S16 全链」 |
| `demo/index.html` meta / map-foot / aria / 注释 | `18 阶段主链` 等 4 处 | 同上 | 统一为 S0–S16 措辞；demo 内部 9 阶段叙事压缩保留（其 spec-note 已自我解释） |
| `site/innovation/index.html` + `app.js` | `THE 90-SECOND WALKTHROUGH` / `六个可看见的状态` / 注释 `Six acts…90 秒` | 页面按钮已是 105 秒、ACTS=7，文案是六幕旧版残留 | 统一 105 秒 / 七幕 |

### (B) 定位声明全站缺失

- 主页 hero 自称「本页是产品介绍」，footer 自称「静态产品演示页」；**全站 0 处**出现「research-agent = 早期 demo，智能体产品 = Wellspring-Agent」的定位与外链（仅 `site/app/index.html` 出现产品名）。
- 处置：hero lede 改写并加产品外链；#demos 的 app 卡标注「构建产物预览 · 真实执行需本地 runtime」；#boundary 补一句两产品关系；footer 改为「demo 展示镜像 · 智能体产品：Wellspring-Agent」；`site/README.md` 顶部加定位声明。

### (C) 「后续需要做的」零命中

- 判定总线 / FeedbackPort / MemoryWritePort / ExecPort / waitpoints 委托骨架 / SKILL.md fingerprint 全站 grep 零命中；Q1–Q4 未清单化；已实测亮点（search-study 三态判定、复现计数 + 功效阶梯、护栏开火率 8.1%、Host-as-Model 零 key、46 工具零签名）未上主页。
- 处置：主页 #strategy 区新增「接下来做什么 · 一个总线 + 四个端口」卡片组（六步 + 已实测基线 + 四个问题 + 出处链接 71 号文档）；`site/docs/` 增补 71 号文档（`build-site.mjs` 复制清单 + 索引卡片）。

## 3. 诚实度结论

SIM 标记整体诚实，无需重写：demo 129 处 SIM + meta 明示「不调用模型、不产生真实 claim」；rsi 页明示 `simulation=true`、`claim_eligible=false` 与「下一步未实现」；innovation 明写「数字来自 fixture，不冒充实验结果」；live/models/qoder 明示需本地 runtime。本轮改进属于**补定位、补路线、校数字**，不是重写叙事。

## 4. 当轮修改清单

- `site/index.html`：hero 定位 + 外链、统计五项校正、app/demo 卡注记、#strategy 增「接下来做什么」卡片组（含 Q1–Q4 与已实测基线）、#boundary 补两产品关系、footer 更新、lede/footer 链接样式。
- `demo/index.html`：meta description、map-foot、pipeline-svg aria、注释共 4 处 18 阶段 → S0–S16 措辞。
- `site/innovation/index.html` + `app.js`：90 秒/六幕 → 105 秒/七幕。
- `site/README.md`：顶部定位声明。
- `site/docs/index.html` + `scripts/build-site.mjs`：71 号文档入 docs 索引与复制清单（`node scripts/build-site.mjs` 已本地跑通，`site/docs/71-四图对照与解耦设计.md` 落盘）。

## 5. 验证

`node scripts/build-site.mjs` + `node scripts/check-site.mjs` 全绿（static mode confirmed）；`build_release.py --check` 零漂移后同步发行树，`test_release_integrity`（6）+ `test_release_surface`（5）全绿。两仓 workflow 期望全绿：research-agent Pages（demo 发布）与 Wellspring-Agent CI（release-surface + 核心离线套件硬门 + 前端 check）。

## 6. 原则

- demo 页不新增未经测试锚定的声称；路线图内容全部出自 71 号文档与 `docs/fact-baseline.md`，标注「待验证的计划，不是已实现的功能」（与主页策略口径同款措辞）。
- demo 内部叙事模型（9 幕、4 场景、SIM）保留其自我解释；只统一与 canonical（S0–S16 / 门禁）的引用措辞，不改 SIM 数据。

---

*本文件是 demo 展示面第一轮对照反思的沉淀；后续展示面改动对照此清单增量记录。产品定位以 Wellspring-Agent README 为准，研究口径以 `docs/fact-baseline.md` 为准。*

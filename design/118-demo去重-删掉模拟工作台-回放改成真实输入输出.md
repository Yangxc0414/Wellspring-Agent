# 118-demo 去重：删掉模拟工作台，回放改成真实运行输入→产物

> 状态基线：2026-11-18。触发：用户指出 demo 里存在与真实工作台重复、但不一致的页面，要求去掉或换方式，并用现有跑通流程的输入/输出设计 demo。
> 本轮删掉两个"像工作台但不是工作台"的页面，改成：**一个真实工作台入口（/app/）+ 一个生成式真实运行回放（/demo/）**。

---

## 1. 删掉了什么

| 页面 | 原状 | 问题 | 处理 |
| --- | --- | --- | --- |
| site/agent/ | agent.js 110 KB + agent.css 47 KB 的模拟工作台（SIM 数据） | 与 apps/web 真实工作台两套 UI，口径必然漂移 | 删除 js/css/README，保留一个说明页：**工作台已统一到 /app/**，附跳转 |
| root demo/index.html（→ site/demo/） | 505 KB 自包含 SIM 控制台（9 幕、对象流、指令流） | 看起来像工作台，实际是模拟回放；与真实运行无对应 | 由 `scripts/build_demo_run_page.py` 生成 **真实运行的输入→产物回放** |

现在 demo 里只有一个工作台入口：`/app/`（apps/web 构建产物）。

---

## 2. 新 demo 页怎么来

`scripts/build_demo_run_page.py` 读取一次真实运行：

- pipeline run 的 `demo.json / literature.json / idea.json / experiment.json / paper.json`；
- 项目 run 的 `manuscript-review.json` 与 `final-audit.json`。

生成单页 HTML（约 8 KB，非 500 KB），内容：

1. **输入**：研究问题、8 篇全文来源、6198 个 span；
2. **阶段 → 产物**：S1/S1b/S2-S3/S4/S6/S8 状态、warning 数、门禁（Q0 pass、G1/G2 needs_human、G3/G5 blocked）；
3. **候选**：3 条 idea（title/lens/refs）；
4. **S4 设计**：状态、metric、warning 数；
5. **S8 输出**：稿件 writer_mode/sections、手稿评审 rounds/accepted、成稿审计 citations/汉字/submission_ready；
6. **边界**：门禁仍人签、无 Claim/EA/签名、accepted≠通过、ready≠可投稿。

页面带 `data-demo-run`（run id）与 `data-dl-page="demo"`，沿用共享 legibility 层；索引页卡片文案改为"真实运行回放 · 输入 → 产物"，CTA 改为"真实运行回放"。

---

## 3. 为什么保留 /demo/ 而不是直接删

- 它现在回答一个 /app/ 不回答的问题："**这一次真实运行到底输入了什么、每个阶段产出了什么、门禁停在哪**"；
- 数据来自真实产物、由脚本生成，不是手写宣传页；
- 与 /app/ 的分工清晰：/app/ 是可交互工作台（构建产物），/demo/ 是只读回放。

---

## 4. 验收

| 项 | 结果 |
| --- | --- |
| site/agent/ | 说明页 + 跳转 /app/；agent.js/agent.css 已删除 |
| demo/index.html | 由脚本生成；site/demo 与源文件逐字节一致 |
| check-site | ok（8 demo pages legible；legibility 属性齐全） |
| 测试 | tests.test_demo_page 3 项 OK（生成页标记、源/副本一致、旧工作台重定向且资源删除） |
| 发布 | build_release --prune 清理旧 agent 资源；drift 0 |

---

## 5. 下一步

1. 新 demo 页目前固定读一次 full-run 的产物；可把 run id 作为 `--run-dir` 参数在构建时切换（frontier 24 篇/6 候选也可生成第二页）；
2. /app/ 内部还有 "SIM/LIVE" 状态标签，需要与真实运行面板（ESE 运行 tab）对齐口径；
3. 根目录 `demo/.研络 ResearchWeave.qoder.site` 等历史文件未处理，下一轮清理。

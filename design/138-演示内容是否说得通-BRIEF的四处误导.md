# 演示内容是否说得通——一次以“观众读到的那句话”为单位的核查

- 状态基线：2026-11-20；对象为 BRIEF / RUN / EVIDENCE / EVAL 的实际文案与读数
- 与 137 的分工：137 查“能不能打开、结构是否自洽”；本文查**内容本身是否成立**——数字算不算得出、下一步建不建议得对、缩写背后是不是同一个事实
- 结论：结构已经能走通，但**内容有 4 条误导性建议、3 处阶段夸大、1 处把委托签读成人签**。均已修

---

## 1. 方法

两件事分开做：

1. **数字可复算**：把种子里每个派生数拿去和产物/公式核对，而不是“看起来像真的”。
2. **文案可代入**：把每条任务的 BRIEF 当作“演示者现场会念的那一屏”，逐句问“这句话对这条任务成立吗”。

第 2 步抓到的问题比第 1 步多——因为数字都是真的，**错的是把真数字放进了错误的句式**。

## 2. 数字核对：全部可复算

ESE：

| 读数 | 种子 | 复算 |
|---|---|---|
| 合并比例 | 0.3749 | 1924/5132 = 0.3749 ✓ |
| 缺陷修复 | 0.4136 | 352/851 = 0.4136 ✓ |
| 其它提交 | 0.3672 | 1572/4281 = 0.3672 ✓ |
| 差值 | +0.0464 | 0.4136 − 0.3672 = 0.0464 ✓ |
| 仓库加权 | — | 按 commits 加权三个仓库率 = 0.3749 ✓ |

`p=0.015`（合并）与 `p=0.001`（时间切分）都能在 `runtime_data/ese-ms-20261118-03/result.json` 找到；`16 项 closure 检查`、`2 sources / 1 full text / 2 spans / 4 blockers`、`advance=0/revise=2/reject=0`、`accuracy 0.956` 也都能在 `report.md` 与 `closure-report.json` 里对上。

**这一层没有问题**，也说明前几轮“读数必须来自产物”的纪律守住了。

## 3. 内容问题：真数字 + 错句式

### 3.1 BRIEF 的 NEXT 是“只认文献任务”的状态机（4/7 条错）

原实现只看 `claim.status` 和 `coverage.spans`，于是：

| 任务 | 原 NEXT | 为什么不成立 |
|---|---|---|
| ESE | 先跑文献调研，至少拿到可定位的 span | 已跑完 5132 提交、EA 已封；它缺的是 claim 人签 |
| E2E | claim 已签；下一步运行 closure | 盘上是委托签，不是人签；说“已签”就是替 autopilot 冒充作者 |
| 写作 | 先跑文献调研…再进入假设收敛 | 它在 S8–S12，缺的是已签 claim，不是文献 |
| 钙钛矿 | 下一步是 G1 收敛与 claim 人工签署 | G1 还没收敛就谈 claim 签署，跳了两步 |

改成**按状态排序**的判断：人签/CLI 签 → closure；委托签 → 明确说“不是人签”；有 run → `run claim`；写作模式 → 先拿已签 claim；G1 未过 → 收敛候选；最后才落到“先检索”。

### 3.2 BRIEF 的 STAGE 声称未到达的阶段（3/7）

`briefStage` 直接用 `task.stage`，而阻塞任务的 `stage` 指向“本来要去的地方”。E2E 与完整闭环因此显示 **自进化提案**，可它们的 G5 还 blocked；ESE 显示 **结果图**，但它并没有产出图。

改为：阻塞时取 `completedStages` 里最后一个**真正通过**的阶段。现在 E2E / 完整闭环显示「闭包检查」，ESE 显示「证据判定」——都是它们实际走到的地方。

### 3.3 CLAIM 指标把委托签印成 signed

BRIEF 的 KPI 用的是 `claim.status` 原值，E2E 因此显示 `signed`；而 BRIEF 下方正文、EVIDENCE、RUN 卡都写“委托签署（非人签）”。**同一屏，指标和正文互相打脸。**

修法延续“单一判定源”：给 `ClaimSignatureLabel` 加 `kpi`（none / unsigned / signed / delegated / demo），BRIEF 与导出的 Markdown 都用它。现在 E2E 的 KPI 是 `delegated`。

### 3.4 BRIEF 看不见 run contract 阻塞

BRIEF 的 BLOCKERS 只统计门禁；E2E 的 `run contract blocked（min_delta 不可验证）` 不是门，于是被漏掉——而那恰恰是“不能宣称超过基线”的原因。

新增 `briefBlockers()`：门禁 + 非门禁的 run contract，两处（界面与复制出的 Markdown）共用。E2E 现在显示 2 个 blocker：G5 与 RUN CONTRACT。

### 3.5 G2 被说成“演示推进”，哪怕它是真冻结

BRIEF 的 G2 行只区分 `task.runtime` 与否则，非 runtime 一律写“演示推进；真实 G2 由 CLI 冻结”。ESE 是真实回放，run-capsule 绑定了 protocol sha256，这句话**低估**了它。

改为读 `replay.basis`：real/fixture 显示「已冻结；run-capsule 绑定 protocol sha256（真实产物）」，demo 才说“演示推进”。

### 3.6 EVAL 一排破折号没有解释

`PAPER — / REPRODUCED — / Δ REPRO —` 看起来像页面坏了。加了一句按状态切换的说明：没有登记基线时直接说“所以这三个数是空的，改进必须先复现基线”。

## 4. 一个“第一印象”问题

默认 tab 是「演示流程」（通用教学模板），且切任务时不变。于是选中 ESE 后，右侧第一屏仍是**别的项目**的教学重演——虽然上一轮加了“通用模板（非当前任务）”的提示，但观众先看到的是提示，不是这条任务。

改为：切任务时，若当前停在「演示流程」且新任务不是「完整闭环」，自动落到该任务的 **BRIEF**；手动选过的 tab（EVIDENCE / RUN…）保持不变。

实测：打开应用（完整闭环）→ 演示流程；切 ESE → BRIEF；先点 EVIDENCE 再切 E2E → 仍是 EVIDENCE。

## 5. 修后逐任务 BRIEF

| 任务 | STAGE | CLAIM | NEXT |
|---|---|---|---|
| 钙钛矿 | 假设收敛 | none | 已有候选方向；下一步 G1 人工收敛 |
| archive | 文献检索 | none | 还没有 span；先检索再收敛到 G1 |
| ESE | 证据判定 | unsigned | RunCapsule 与 EA 已就位；下一步 `run claim` |
| E2E | 闭包检查 | delegated | 委托签不是人签；由作者在 CLI 签核 |
| 完整闭环 | 闭包检查 | none | RunCapsule 与 EA 已就位；下一步 `run claim` |
| 写作 | 写作槽位 | none | 槽位 locked；先拿已签 claim |
| 命题 | 文献检索 | none | 还没有 span；先检索再收敛到 G1 |

## 6. 仍然不合理的部分（不改，写清）

1. **EVAL 仍是 SIM**：即使点了「提交独立评估」，得到的也是控制面演示，不是真实隔离评估。面板已标「隔离 · 演示数据」，但组会上不应把它当实验读数。
2. **PROJECTS 永久为空**：静态构建没有项目实验链，只有一句说明。它是诚实的空态，但对演示没有加分。
3. **ESE 的 `SPANS 0`** 容易被误读成“没证据”。它其实走的是 run-capsule 路线（链上标 RUN-CAPSULE），但 BRIEF 的 SPANS 格没有解释。若要彻底解决，应给 BRIEF 增加一个“证据类型”字段，而不是继续用 span 数当唯一指标。
4. **完整闭环仍是教学演示**，不是真实语料研究；它的 NEXT 说 `run claim`，对真实系统成立，对这个 demo 只是“该走的路”。

## 7. 下一步

1. 把 BRIEF 的 SPANS 格换成“证据基础”（SPAN / RUN-CAPSULE / 无），与 EVIDENCE 的角标同源。
2. PROJECTS 若能读到真实的 project-experiments 清单，给一条最小示例；否则考虑在静态构建里默认收起该 tab。
3. `replay.basis` 再往 BRIEF 其他行推广，彻底消除“非 runtime = 演示”的隐含假设。

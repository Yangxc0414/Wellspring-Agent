# 136-把真实闭环放进演示前端：委托签与 fixture 的两条防线

日期：2026-11-20
触发：要求把系统**真实跑通**的完整闭环做成演示前端里的历史会话，供组会展示具体结果。
素材：`runtime_data/e2e-closed-loop`（PIPE-20261110T163849Z-e2bd4a，RUN-E2E-01/02）
边界：只把**已存在**的真实产物搬进前端并如实标注；不伪造运行、不把 fixture 当科学结论。

## 0. 为什么不能直接照抄产物

搬之前先核了三件事，每件都足以让演示变成造假：

| 事实（来自产物） | 如果不标注的后果 |
| --- | --- |
| `demo.json`: `fixture_mode: true`、`"no API, no real experiment"` | 观众会把 fixture 读数当真实实验 |
| `signature.json`: `human_reason: [delegated:autopilot] …`、`submission: false`、`signed_at: 空` | 观众会把委托签当人签 |
| `export_manifest` 含本机绝对路径 | 泄露本机路径，且违反发布面纪律 |

## 1. 加了什么

新增种子任务 `seedE2EClosedLoop()`（`e2e-closed-loop`），12 条消息完整走 S1→G5：
S1 覆盖 → S2–S3 候选与独立预审 → G1 → S4 协议冻结 → S5a 运行 → S5b → S8–S12 写作槽位 → S13–S16 中文稿审计 → G5 闭合与签署。

**全部读数来自报告原文**，没有一个是编的：

- S1：2 sources / 1 full text / **2 spans / 4 gaps**，覆盖 2/6 面向，饱和度 partial
- 候选：IDEA-01 机制 / IDEA-02 测量，独立预审 **advance=0 / revise=2 / reject=0**
- S4：baseline `majority class`，metric `accuracy`，seeds 3，设计审计 blockers=0/warnings=1
- S5a：`RUN-20261110T163848Z-f84f16`，`sklearn:iris:150x4`，seeds [17,18,19]，**accuracy 0.956**，EA `EA-bf9f4eeca1d7`
- Run contract：**blocked**（`min_delta` 不可验证，无配对基线读数）
- 中文稿审计：**blocked**，4 个真阻断（引用元数据 / 2 句缺证据 / 候选只登记 1/3 / fixture 不可引用）
- 门禁：Q0/G1/G2/G3/S5 pass，**G5 needs_human**

## 2. 两条防线（本轮真正的改动）

### 2.1 委托签必须有自己的状态，不能落进"已人工签署"

排查发现一个会直接造假的缺口：`claimSignatureLabel()` 的兜底分支是 `signed-cli` → 文案「已人工签署（证据来自 CLI）」。只要 claim `status="signed"` 且不带 `origin`，**autopilot 委托签就会被显示成人签**。

修法是新增一个数据层状态，而不是改文案糊过去：

- `types.ts`：`origin?: "cli" | "cli-import" | "demo" | "delegated"`
- `claimSignature.ts`：新增 `signed-delegated`，badge「委托签 · 非人签」，detail 明确「不是作者人签；人工门在治理语义上仍未通过」
- 分支顺序放在兜底之前（有测试钉死顺序）

连带修正两处消费点：

- **SIGNED CLAIMS 计数**只认 `signed-cli` / `signed-import` → 实测 **0**（委托签不计入）
- **ClaimGateDialog** 非静态分支原先把 `status==="signed"` 当"无需再签"，现在 `delegated` 仍视为待签

### 2.2 fixture 边界写在界面上，不只写在文档里

- 首条 system 声明同时说清三件事：机制真实跑过、语料是 fixture、G5 是委托签
- S1 消息直接写「覆盖只有 partial」并列出缺哪四个面向
- 结尾 system 总结："三件事必须一起讲，少一件就是夸大"

### 2.3 顺手修掉的第三处不一致

实测发现右栏 RESEARCH FLOW 的产物写死「4 sources · 12 spans · 2 gaps」，而这条任务真实是 **2 sources / 2 spans / 4 gaps**——同屏两个数字打架。FlowDemo 是通用教学组件，不该冒充当前任务读数：

- banner 补一句"每步写的产物数字是教学示例，不是当前任务的真实读数"
- 字段标签从「产物」改为「产物（示例）」

## 3. 实测结果

| 检查项 | 结果 |
| --- | --- |
| 侧栏标签 | `闭环·待签`（不再出现"委托签 · 待签"重复） |
| 任务头 | `EXPERIMENT · 人签门待人签` / `回放 8/9 stages` / `HUMAN GATE` |
| EVIDENCE 覆盖 | 2 SPANS / 4 GAPS / 1 ABSTRACT-ONLY / **SIGNED CLAIMS 0** |
| chain 断言节点 | **委托签署（非人签）**；闭合 = locked |
| BRIEF | "盘上是 autopilot 委托签，不是人签" |
| 页面错误 | 无 404、无 JS 异常 |

7 项新测试 + 102 项相关测试全过。

## 4. 反思

1. **"有产物"不等于"能展示"**。这条闭环的产物完整、机制真实，但三处边界（fixture / 委托签 / 本机路径）任何一处不标注，摆到组会上就是把限制说成能力。
2. **兜底分支最容易造假**。`claimSignatureLabel` 的最后一个 `return` 把"没写来源的 signed"一律当人签——这是先写的代码没预料到 autopilot 代签。凡是"默认当成功"的兜底，都该被当成风险点排查一遍。
3. **同一屏的两个数字必须同源**。左侧 2 sources、右侧 4 sources 这种冲突，比单个数字错更伤可信度，因为它让观众怀疑所有数字。
4. **展示"机制闭环"和"科学结论"是两件事**，这条任务只能演示前者；后者需要真实语料 + 真人签，目前盘上没有，不能假装有。

## 5. 组会怎么用这条任务

推荐讲法：先点开「E2E 闭环：Iris 协议验证」，从 S1 一路往下滚，每到一个人工门停一下说"这里卡住了"；到最后 G5 指出"closure 16 项 ready，但盘上那份签名是委托签，不是人签——所以门仍然关着"。

这一条能把"门禁真的会卡"讲得比任何 PPT 都清楚；同时**必须**跟着说语料是 fixture，否则越界。

## 6. 下一步

1. 若要在组会上展示"真实语料的完整闭环"，需要一次 `--real-corpus` 的端到端运行 + 真人 sign；当前盘上没有这样的产物，不能拿 fixture 顶。
2. 把 `origin` 的 delegated 状态接到真实 autopilot 产物解析（现在是在种子任务里标注，尚未从 signature.json 反解）。
3. 排查其他可能有"兜底当成功"的判定函数（本轮只修了 claim 签名一处）。

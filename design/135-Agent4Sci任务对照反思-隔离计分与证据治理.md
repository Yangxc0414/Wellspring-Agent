# 135-Agent4Sci 任务对照反思：隔离计分与证据治理

日期：2026-11-20
参考仓库：项目根目录下的 `agent4sci-main/`（NeurIPS 2026 D&B，arXiv 2610.28763）
承接：`design/08`（曾把 AGENT4SCI 的评估隔离映射到工作台）
边界：本文是**任务设计的对照反思**，不改代码、不改门禁语义；区分「机制可迁移」与「定位不同不宜照搬」。

## 0. 先纠正一个容易犯的错

拿两套系统比"谁的任务设计更完整"会错位。它们根本不是一类东西：

| | Agent4Sci | 我们（Wellspring） |
| --- | --- | --- |
| 本质 | **评测基准 + 运行器**（README:20 明说 "This repository is the runner"） | **证据治理工作台** |
| 研究问题 | 给定论文/代码/数据/指标，前沿 agent 在固定算力下能比已发表最优改进多少（README:24-26） | 一个结论如何变得可追溯、可复核、可准入 |
| 任务驱动 | 20 benchmark / 25 任务，容器镜像封装（registry.yaml:1-90） | S1–S16 阶段 + Q0/G1/G2/S5b/G5 人工门 |
| 成功定义 | 在 held-out 上刷出更优指标 | 证据闭合、判定可重算、人签可审计 |

Agent4Sci 自己说 "It is a discovery-based testbed, not a leaderboard"（README:28）——它要的是**可信地计分**；我们要的是**可信地放行**。上图两条流程的强项正好互补。

## 1. Agent4Sci 的任务体系（事实）

### 1.1 两层任务，不是 S1-S16
- **benchmark task**：21 个镜像条目、25 个科学 ML 任务，11 个领域（`agent4sci/registry.yaml:1-90`、`README.md:20`）。每条只有 `image/domain/task` 三个字段。
- **run stages**：严格线性两段——`hillclimb`=[hillclimb, wrapup]、`evaluate`=[eval, audit]（`pipeline.py:54-89, 108-111`）。**无跨阶段回环**。

### 1.2 门是 sentinel 文件 + 数据分期，不是人工审批
- 完成门：`sentinel="METHODOLOGY.md" / "EVAL_RESULTS.md" / "AUDIT_RESULTS.md"`（`pipeline.py:67,79,85`），`_monitor` 检测文件出现即判步骤完成（`backends/local.py:132-144`）。
- 数据门：`MODE=hillclimb` 只挂 `train/val/`，**test 数据物理缺席**；`MODE=evaluate` 才挂 test + 评测脚本（`docs/image-contract.md:14-20`）。

### 1.3 判定者与被判者强解耦
- evaluator 固定强模型 `claude-opus-4.8`，evaluate 阶段**不挂载研究 skills**（`pipeline.py:28,74`）。
- 评测必须用统一的 `eval_test.py`，**禁止用被评者自己写的脚本**（`docs/protocol.md:28-30`）。
- audit 是独立 agent，判词要带 Log position / Action / Reasoning / **Code evidence（路径+行号+片段）** / Severity（`prompts.yaml:79-93`），终判 CLEAN / COMPROMISED。

### 1.4 反增量的任务模板
- 明令"不要重实现 baseline、不要重跑多种子调参 baseline"（experiment SKILL.md:12-20），把这类操作列为 invalid experiment。
- Tier1/Tier2 分级 + 实验登记（Category/Hypothesis/Rationale/Metrics/Runtime）+ 失败分诊 Fix/Pivot/Abandon（research/experiment SKILL.md）。
- 失败被写进 METHODOLOGY/SUMMARY 供审计，但**不是结构化 score 字段**。

## 2. 我们的任务体系（事实）

### 2.1 两套阶段声明没有机器映射
- 代码执行的是 `actions.py:34-107` 的 9 个阶段（S1 / S2–S3 / S4 / S5a / S5b / S6 / S8–S12 / S13–S16 / META），带 `id/label/owner/gates/human_gate/outputs`。
- 设计口径 S0–S16 在 `design/21:246-283`，文档自己声明 demo 的 X0/G1 是演示标签而非 canonical gates。
- 35 个 `modules/*/SPEC.md` 的 frontmatter 有 `inputs/outputs/tools/gates/invariants`（`specs.py:21-26`），**但与 9 阶段无机器对齐**。这是真缺口：`design/125` 修过文档重号，但两套阶段体系仍未统一到一处。

### 2.2 人工门 4 个，不是 G0-G5 六个
`framework_api.py:79` 对外清单 `["Q0","G1","G2","S5b","G5"]`；`mcp_tools.py:185-188` 声明 `research_run` 从不签 claim、冻协议、签 closure、批导出。但 `autopilot.py` 可**受控代签**，留 `[delegated:autopilot]` 与策略哈希、`submission=false`（`:32-39,337`）。这是治理优先于刷分，不是漏洞。

### 2.3 判定比它强：读时重算 + 单一事实源
`verdict_ledger.py` 每行 `verdict_source:"recomputed"` + `source_path/source_sha256`，同一产物集两次收集字节一致（`:1-32,153-277`）；`closure.py:168-336` 重验 claim_supported、EA sha256、capsule completed、assertions 重算、protocol binding；负结果是结构化的（`failures/atlas.json` 每条含 failure_id/kind/scope/observed/diagnosis/retry_condition/evidence）。

**这一块我们比 Agent4Sci 强**：它的审计是 LLM 判词 + 字符串匹配读 CLEAN/COMPROMISED（`pipeline.py:113-117`），作者自己承认审计 "a verdict, not a proof"（protocol.md:48-49）；我们的判定是哈希绑定的确定性重算。

## 3. 四个可迁移的机制（真正该学的）

1. **测试集物理隔离**：他们的 test 在 hill-climb 容器里根本不存在（`image-contract.md:19-20`），把多数 gaming 从"违规"变成"不可能"。我们目前 S5 split 多是同数据集不同 test_size，README:511 自列"S5 split 非真 held-out、hidden 未 sealed"——**这是可落地的升级**：eval 任务 containers 化，或在数据层做物理不可达。
2. **评测脚本冻结且禁止被评者自写**（protocol.md:28-30）。我们的 heldout_eval 是确定性读产物，已有 `source_fingerprint`，但缺"服务端冻结的评测器跑真实 held-out"这一环。
3. **判定者换容器/换模型/不带研究 skills**（pipeline.py:28,74）。我们在 `independence.py:56-118` 做到 provider+model 指纹级（检测 proposer 兼 critic），未到进程/数据隔离。可做的最小一步：evaluator 固定 profile + 独立 receipt，已有雏形（s5_eval.py:184-188、real_eval.py:220-229）。
4. **sentinel 作为机器可读完成门**（run_spec.py:19 + local.py:138）。我们用 verdict-ledger 做判定更强，但**编排层**仍靠 stage 状态机与人工看板；可借鉴 sentinel 让长任务的每一步有明确"产出即完成"信号。

## 4. 三个不该照搬的

- **字符串匹配读判词**（pipeline.py:115-117）：脆弱。我们的 verdict-ledger 已规避。
- **时间到点/进程退出当作成功**（local.py:132-144）：奖励"耗满时长"。我们 autopilot 虽可代签但 policy 哈希 + `submission=false` + 失败即停（autopilot.py:543），纪律更严。
- **研究/评估/审计完全无回环**（pipeline.py:108-111）：若目标是科研发现而非公平计分，缺把审计与负结果反馈进下一轮假设的机制。我们的 `feedback.py` 有 observe→propose→gate→apply→record 且默认拒绝、`research_cycle.py` 只改下一个检索预算一参数、不跨人工门——**这个"限权反馈"反而是更成熟的设计**，不该退回他们的无回环。

## 5. 对我们任务设计的反思结论

**我们的定位不是"补成另一个 Agent4Sci"。** 补数据隔离与冻结评测器，是为了让我们的"可复核判定"不建立在未隔离的读数上；而不是为了去刷 benchmark。三条具体落点：

1. **统一阶段声明**：把 `actions.py` 9 阶段与 35 个 SPEC.md 的 inputs/outputs/gates 映射到一台机器可读注册表，消除"设计说 S0–S16、代码跑 9 阶段、SPEC 写 35 模块"的三头分裂。
2. **把 held-out 从"同数据集切分"升级为"物理不可达 + 冻结评测器"**，并把现有 verdict-ledger 的 source_fingerprint 机制接上——这才是我们相对 Agent4Sci 真正能领先的地方：**既隔离，又让判定可重算**。
3. **给 EVAL 控制面接后端**：前端 EVAL 与 guidance queue 目前是 SIM（design/38:140-155 承认，后端零命中）。接上服务端 evaluator 后，才谈得上"评估任务"与"研究任务"在同一治理链上分权。

## 6. 一句话总结（可用于组会）

> "Agent4Sci 的任务设计是'为可信计分服务的隔离流水线'，值得学的是数据物理隔离、冻结评测脚本、判定者解耦三件事；我们的强项在证据链与读时重算判定，不该退回它的无回环或字符串判词。下一步是把 held-out 从切分升级为物理隔离，并统一阶段声明——让我们已有的可复核判定建立在真正隔离的读数上。"

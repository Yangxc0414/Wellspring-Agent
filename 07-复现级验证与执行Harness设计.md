# 复现级验证与执行 Harness 设计

> 工作名：**Research Agent** · 验证层代号 **RWVH**（沿用既有缩写；Research Agent Verification Harness）
> 版本：v0.1（首版设计，新增 Work/Judge、复现任务包、RWJT 与 FR-18–FR-24） · 日期：2026-10-19
> 上游依据：[01-组会纪要-核心判断与优先方向.md](01-组会纪要-核心判断与优先方向.md) 的判断 2「结果/过程/证据链三层可验证」与方向 B「从实验运行到论文陈述」
> 需求落点：[02-需求书-科研自动化与写作平台.md](02-需求书-科研自动化与写作平台.md) §4.2.5–§4.2.6、FR-18–FR-24
> 配套流水线：[04-自动化研究与写作流水线.md](04-自动化研究与写作流水线.md) S4–S6、S9–S13
> 系统架构入口：[09-系统架构与流程编排设计.md](09-系统架构与流程编排设计.md)（五层组件、编排/调度、E/C 车道与 X0–X7 的组合方式）
> 对照对象：[`oss/OpenRSI-Index-main/`](oss/OpenRSI-Index-main/)（本地快照）与 PaperBenchX（外部项目，仅项目口径）
> 证据等级：OpenRSI 元数据 `[已核验]`（2026-10-19 GitHub REST API）；机制 `[工程参考]`（读 README、任务包、Harness 文档与检查脚本，**未运行**）；PaperBenchX 全部数字 `[项目口径，未独立核验]`；本文人周 `[估算]`（±20%）。

---

## 0. 结论先行

### 0.1 五条结论

1. **OpenRSI-Index 和 PaperBenchX 解决的不是「怎么写」，而是「怎么证明一个 agent 真的做出来了」。** 前者给的是持久 Work + 干净 Judge + 快照 + 私有测试 + oracle + best-of-N 的长程执行底座；后者给的是原生科学环境 + 独立重跑 + 证据固定 + 三阶段 rubric 的复现评测方法。两者都不写中文长文，也都不把运行证据接到稿件句子上。
2. **我们当前设计缺的正是这一层。** `02-` 已有 FR-4 沙箱、结果卡、探索/确证隔离与产物信封，但没有独立 Judge、没有干净重跑、没有私有 rubric、没有 oracle/nop、没有失败状态机。于是「过程可信」仍是一句文档承诺，而不是可测属性。
3. **补法不是再做一个 OpenRSI，也不是做一个 93 任务的 PaperBenchX。** 我们做**最小可验收的复现判定层**：4 个任务、CPU/单卡、单次 Judge ≤ 30 分钟；它服务于我们的评测与产品确证，不追求公开排行榜。
4. **我们的独有增量是「复现—写作联合任务」（RWJT）。** OpenRSI 停在运行产物，PaperBenchX 停在 rubric 分；RWJT 要求 agent 先复现一个结果，再把这个结果写成中文核刊段落，且每个数字、图、结论都挂到重跑产物上。判定同时看 **R（复现分）** 与 **W（写作证据分）**，任一造假直接判 invalid。
5. **代价是工作量与人数。** 新增验证层 P0 约 **25 人周**（H1–H5），全量约 **39 人周**（含 P1 的 H6–H8）。8+1 的 196 人周装不下 215 人周；推荐改为 **9+1（220 人周，215 人周占 98%）**，若要保持 ≥5 人周缓冲则把 FR-12（9 人周）后置到答辩后（206 人周，94%）。

### 0.2 一句话定位

> **在「能写」与「可信」之间，补一台只认重跑证据的判定机；它不替人做科学判断，但让每一个进入稿件的数字都有一次可复核的运行。**

### 0.3 设计边界（先说不做什么）

| 不做 | 原因 |
| --- | --- |
| 不做「General AI Scientist」或「RSI」叙事 | 两个参照系统的目标、规模与证据都不支持我们这样宣称；我们做的是可审计的科研写作与轻量实验闭环 |
| 不做 93 任务、10 个原生科学环境的公开 benchmark | 超出 8 个月与现有算力；v1 只做 4 个任务，P1 扩到 6–8 个 |
| 不直接复用 OpenRSI 的 8×H100 / 13 小时 Judge 任务 | 与我们的成本约束不符；只借生命周期与契约，不借任务负载 |
| 不把 PaperBenchX / OpenRSI 的效果数字当作我们的结果 | 均为外部口径，未在本地复现 |
| 不做 AIGC 检测规避 | canary 只用于 benchmark 污染控制，不用于规避检测 |
| 不做自动投稿、伪造评审、代写代投 | 产品边界见 `02-` §1.4；导出不等于投稿 |
| 不做湿实验自动化 | 本期只做干实验；湿实验协议生成放 P2 |
| 不让 Judge 读 Work 的凭据或可写状态 | 三权分离：Work 执行、Judge 判定、人做科学决策 |

---

## 1. 两个参照系统到底解决了什么

### 1.1 OpenRSI-Index / RSI-Harness

**可核对事实**（本地快照 `oss/OpenRSI-Index-main/`，commit `c80c190`，2026-10-17，248 stars，Apache-2.0，1,560 个文件 / 约 135 MB）：

| 维度 | 事实 | 证据入口 | 等级 |
| --- | --- | --- | --- |
| 目标 | 评估 AI agent 能否在从单节点到数千 GPU 的规模上推进真实科研，而不只是复现、扫参或玩具任务 | `README.md` §Why OpenRSI Index | `[工程参考]` |
| 任务 | 16 个：3 个 signature（Qwen-122B-RL、marin-optimizer、gpic-text-to-image）+ 13 个 public；GPU 从 1×H100 到 256×H100 | `README.md` 任务表 | `[工程参考]` |
| 任务格式 | `task.toml` + `instruction.md` + `environment/` + `tests/test.sh` + `solution/solve.sh` | `rsi-tasks/*/` | `[工程参考]` |
| 运行模型 | 持久 Work 容器；`rsi-submit` 暂停 Work 并快照文件系统；每轮从干净镜像起一个全新 Judge，只读挂载 Work 的 WORKDIR，注入私有测试，跑 `/tests/test.sh`，记录 reward 后销毁 | `RSI-Harness/README.md` §How it works | `[工程参考]` |
| 反馈循环 | Work 恢复，Judge 反馈回给 Agent；直到提交次数或超时；有效提交中按主 reward 选最佳 | 同上 | `[工程参考]` |
| 隔离 | 默认 hidden tests；public Judge 只读挂载 `/tests` 并做 digest 校验；`clean_image` 默认 true；Judge 可读 `/logs/agent` 轨迹 | `RSI-Harness/docs/harbor-task-authoring/task-toml.md` | `[工程参考]` |
| oracle | `--agent oracle` 在真实路径跑 `solution/solve.sh` 并提交一次或 N 次，用于验证 Judge 能给出基线分；退出码是基础设施门，不是科学结论 | `RSI-Harness/README.md` §Validate a task's Judge with the oracle | `[工程参考]` |
| 运行产物 | `final_result.json`、`submissions/agent-N/report.json`、`test_output.txt`、`feedback/agent-N.log`、`verifier/agent-N/reward.json`、`agent_output.txt`、`engine_error.json`、`run-plan.json` | `RSI-Harness/README.md` §Run artifacts | `[工程参考]` |
| 状态 | run：`completed / no_valid_submission / failed / cancelled`；submission：`completed / verifier_error / verifier_timeout / infrastructure_error / submission_error` | 同上 | `[工程参考]` |
| 静态检查 | `checks/` 下 20+ 个脚本：task 字段、绝对路径、超时、网络策略、测试文件引用、canary、GPU 类型、Dockerfile、pip 固定、verifier 工具预置、AI 检测、发布/密钥扫描等 | `checks/` | `[工程参考]` |
| 贡献流水线 | RSI-Anything：proposal-agent 九门 PASS/REJECT → 自动建私有任务仓库 → GPU 上验证/运行 → 上传轨迹 → 独立复核科学合理性、严谨性、新颖性 | `CONTRIBUTING.md`、`.agents/skills/proposal-agent/SKILL.md` | `[工程参考]` |

**一个具体任务包长什么样**（`rsi-tasks/depth-width-allocation/`）：

- Work：1×GPU、64 CPU、512 GiB RAM、300 GiB storage、`no-network`，Agent 超时 154,800 秒（43 小时）。
- Judge：8×GPU、`no-network`、46,800 秒（13 小时），`environment_mode = "shared"`。
- 唯一计分产物：`/workspace/architecture.json`；`notes/` 不读、不执行、不计分。
- Judge 不接受候选的 checkpoint/代码/日志，而是从固定 source commit 重建并**重新训练 19,080 updates**；reward 是 100 个 loss 聚合值的负均值。
- `tests/evaluate.py` 做严格 JSON、workspace scope、regular file/no symlink、大小上限、source receipt/tree SHA256、固定配置、预算上限、训练子进程超时、100 个期望 metric、独占写 `reward.json`；候选校验失败/超时/基础设施失败均为 unscored。
- `solution/solve.sh` 只写 baseline manifest，用于 oracle 验证。

**它证明了三件事**：

1. 长程科研任务可以用「持久 Work + 一次性干净 Judge」的方式评测，而不必让评测器和 agent 共享可写状态。
2. 评测的可信度来自**接口与证据固定**：唯一产物、固定 source、receipt、预算上限、隐藏轨迹、独占 reward。
3. 「最佳提交」必须从有效提交中选；无效、超时、基础设施失败不能被当成 0 分或成功。

**它没有解决的三件事**：

1. 不写论文，也不判断论文陈述是否被运行证据支持；reward 是任务自定义的数值。
2. 不做中文核刊/申报书，不处理中文版面、GB/T 7714、证据槽。
3. 任务重、成本高：8×H100、13 小时 Judge；不适合作为我们日常迭代的默认评测。

### 1.2 PaperBenchX

> 以下全部为项目口径 `[项目口径，未独立核验]`，来自用户提供的文章；不进入我们的指标，也不作为「首创」依据。

| 维度 | 项目口径 |
| --- | --- |
| 定位 | 首个多学科、端到端论文结果复现 benchmark；「迈向 General AI Scientist 的第一步」 |
| 规模 | 93 篇论文 → 93 个复现任务；12 个研究方向；10 个原生科学环境；3,168 条专家核验 rubric；>1,000 专家小时 |
| 三类能力 | 实验重建（从正文/公式/图恢复模型、条件、参数与领域判断）；专业执行（原生科学软件、算力设置、诊断、收敛）；科学验证（模型设置/过程/后处理/证据支持结论/可独立再生） |
| 原生环境 | Ansys HFSS、Ansys Lumerical、Meep、PySCF/GPU4PySCF、ABACUS 等 |
| 长程性 | 任务有资源预算；agent 需安排算力、检查中间结果、诊断失败、决定调整或重跑 |
| 独立重跑 | 在隔离、无网络环境中重跑；删除生成输出与临时状态；只有重跑产生的产物算证据；日志/原始数据/轨迹/收敛记录/派生指标只读固定；每个判断可追到产物 |
| 评分 | 程序化检查数值一致性、单位、文件结构、容差；模型化科学评分做领域解释，使用私有 rubric/参考证据 |
| 构造 | 9 步：选论文/claim/范围 → 软件/许可/算力/时间可行性 → 原生环境 → 公开 instruction → 参考流程 + 初始运行 → 细粒度 rubric（模型/参数/执行/收敛/后处理/结论）→ 干净重跑 → 用成功/部分/无效流程校准 → 两位独立领域专家复核 |
| 结果 | 10 个前沿模型/agent 配置；最佳 GPT-6-Astra（Codex）加权均分 59.08%，完全复现率 13.98%（13/93）；70 个任务无任何配置完全复现；无配置在所有方向领先 |
| 阶段分 | Modeling 62.70%、Execution 61.84%、Validation 42.80%——验证最弱 |
| 交互 | 更多轮次不等于更好：Fable 5.1/5 约 113 轮、58.17%/57.96%；DeepSeek-V4.1-Flash 372.6 轮、45.47% |
| 时间 | 工具记录时间的 51.8%–63.3% 花在原生软件执行上；早期科学判断影响后续算力的价值 |
| 数据划分 | 12 个开放测试任务、81 个封闭测试任务；9 个完全开源环境、3 个需商业许可 |
| 包结构 | `instruction.md`、`task.toml`、`environment/`、`tests/rubric.json` 等；测试与 agent 可见材料分离 |

**它证明了三件事**：

1. 「复现」可以被拆成可评分的三阶段：建模、执行、验证；验证最弱，说明它是最值得补的环节。
2. 独立重跑与「只认重跑产物」是抵御伪造结果的关键；仅看 agent 自己生成的日志不够。
3. 原生科学环境与专家 rubric 是复现评测的门槛；这也解释了为什么多数端到端系统停在 ML/代码域。

**它没有解决的三件事**：

1. 不评写作：rubric 判断复现是否成立，不判断论文段落是否把结果写对、写得符合体裁。
2. 不做中文核刊；原生环境也以英文科学软件为主。
3. 93 任务、10 环境的规模不是 8 个月团队能复制的；我们只能做小而精的 v1。

### 1.3 共同点与我们的空位

| 维度 | OpenRSI | PaperBenchX | Research Agent要补的 |
| --- | --- | --- | --- |
| 核心对象 | 一个可执行任务 + 一个 reward | 一篇论文 + 一组 rubric | **一个 claim–run–artifact 三角** |
| 判定者 | 私有测试脚本 | 私有 rubric + 模型/程序检查 | 私有 rubric + 重跑证据 + 写作审计 |
| 隔离 | Work/Judge、快照、干净镜像 | 独立无网重跑、删除生成物 | 两者都借，但面向私有用户数据做私有 Judge |
| 输出 | reward、轨迹、final_result | 三阶段分、复现率 | R + W + J，且接到稿件槽与导出 |
| 写作 | 无 | 无 | **RWJT：复现后写中文核刊段落** |
| 中文 | 无 | 无 | 中文核刊/申报书体裁、GB/T 7714、页—段—句锚点 |
| 失效 | 无 | 无 | 运行/claim/句子跨版本传播 |

**空位一句话**：两个系统都在回答「做出来没有」，没有人回答「写进去的那句话，是否正好等于做出来的那个结果」。这正是 `01-` 方向 B 的落点，也是 `02-` D1/D2 的验收场景。

---

## 2. 问题定义：为什么现有设计还不够

### 2.1 四个失败模式

| 失败模式 | 典型表现 | 现有 FR-4 是否能挡住 | 需要的机制 |
| --- | --- | --- | --- |
| F1 伪造数字 | 正文写「提升 12.3%」，但没有对应运行；或从旧版本复制 | 部分：有结果卡，但没有独立重跑与数字—产物绑定 | 数字槽必须绑 `EA-` 证据产物；Judge 重跑；导出硬门 |
| F2 结果过期 | 改了数据/代码，正文仍是旧结果 | 部分：有产物信封，但没有运行级失效传播 | run → result claim → manuscript claim → sentence 的传播 |
| F3 孤儿 claim | 句子有引用，但引用不支持该句；或结论没有结果卡 | 部分：有证据图谱，但没有「结果 claim 必须来自确证运行」 | claim 准入规则；孤儿/悬空检测；导出阻断 |
| F4 基础设施失败被当成科学失败 | 环境装不上、Judge 超时，系统记 0 分或静默重试 | 否 | 失败分类；`verifier_error / infrastructure_error` 不记 0；重试与人工路由 |

### 2.2 现有 FR-4 与验证层的差距

| 能力 | FR-4 现状 | RWVH 补充 |
| --- | --- | --- |
| 执行 | 代码沙箱、运行 provenance、结果卡 | 持久 Work + 一次性 Judge + 快照 + 干净镜像 |
| 判定 | 独立 Evaluator 按 G2 判据给 verdict | 私有 rubric、三阶段评分、证据产物、失败归因 |
| 复现 | 同协议复跑基线 | 独立无网重跑；只认重跑产物；oracle/nop |
| 隔离 | 探索/确证目录隔离 | Work/Judge 进程与文件系统隔离；Judge 不可被 Work 修改 |
| 写作衔接 | 结果卡 → claim → 槽位 | run/artifact 级槽位；失效传播；导出硬门 |
| 评测 | 20 个可执行任务复现率 100% | 固定任务包、专家校准、开放/封闭集、可复现指标 |

### 2.3 设计目标

1. **只认重跑**：进入稿件的 `result_claim` 必须来自一次确证运行，且该运行可在干净环境中重放。
2. **判定独立**：Judge 不读 Work 的可写状态，不接受 Work 安装的评测工具，不被 Work 的 prompt 影响。
3. **证据可固定**：每个计分产物有路径、SHA-256、产生者、运行 ID、捕获时间；日志/原始数据/派生指标只读。
4. **失败可归因**：候选错误、评测错误、基础设施错误、科学结论错误分开记；不把 infra 失败变成 0 分。
5. **写作可审计**：中文核刊段落中的每个数字、图、结果 claim 都能追到运行；未解析槽位阻止导出。
6. **成本可控**：v1 单任务 Judge ≤ 30 分钟、CPU 或 1 卡；日常迭代不被 8 卡任务拖死。
7. **可校准**：oracle、nop、gold/partial/invalid、两位专家、κ 门槛；rubric 不是拍脑袋。

---

## 3. 定位与两条执行车道

### 3.1 产品边界仍是 A3

RWVH 不提高自动化等级，只提高**可验证性**。机器可以：建任务、跑 Work、提交、重跑、按 rubric 打分、把证据接到稿件；人仍然：定研究问题、批准确证协议、判断科学新颖性与伦理、终审署名。

### 3.2 两条车道

| 车道 | 目的 | 是否进 Judge | 是否可进 claim | 成本 | 对应状态 |
| --- | --- | --- | --- | --- | --- |
| **E 探索车道** | 试跑、调参、看中间结果、找方向 | 否 | 否 | 低 | S5e |
| **C 确证车道** | 产生要写进稿件的结论 | 是 | 是（仅 `scored` verdict → `confirmed` claim） | 中 | S5c / X0–X7 |

规则：

- 探索车道的 run 只能写 `exploratory_run`，不得生成 `result_claim`，不得被图表/正文引用；违反则 Q1 直接失败。
- 确证车道必须先有冻结的设计卡/protocol（G2 签署），运行前登记假设、主指标、停止规则、分析计划与预算。
- 确证运行失败时，允许修改代码/环境后重跑，但**不得修改主指标/停止规则**；修改即新协议、新版本、重新 G2。
- 一个用户项目不必所有实验都走 C 车道；只有要写进稿件的结论才走。

### 3.3 两种使用模式

| 模式 | 谁用 | 任务来源 | Judge 数据 | 输出 |
| --- | --- | --- | --- | --- |
| **基准模式** | 我们团队 / 评测 | 固定任务包（T1–T4） | 公开或授权数据 | R/W/J、baseline 对照、负结果报告 |
| **产品模式** | 用户项目 | 用户自己的设计卡 + protocol | 用户私有数据，私有部署内只读挂载 | 结果 claim 的 `confirmed` 证据包；不对外发布 |

产品模式的 Judge 必须满足：私有部署、无外网、数据不落第三方、Judge 容器用完即删、证据包只回用户项目库。基准模式才允许公开日志与 canary。

---

## 4. 总体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│ 写作平面（S7–S16）                                                   │
│ 论证图 · 体裁大纲 · 证据卡 · 逐节生成 · 批判修订 · 全稿核验 · 导出    │
└───────────────────────────────▲─────────────────────────────────────┘
                                │ 只接受 confirmed result_claim + EA
┌───────────────────────────────┴─────────────────────────────────────┐
│ 证据平面                                                             │
│ claim 图（LC/RC/MC）· 产物账本（EA）· 运行账本（RUN）· 失效传播       │
│ 规则：无重跑不 result_claim；无 result_claim 不写数字；stale 不出门   │
└───────────────────────────────▲─────────────────────────────────────┘
                                │ Verdict + Evidence Bundle
┌───────────────────────────────┴─────────────────────────────────────┐
│ 执行平面（RWVH）                                                     │
│ Task Package → Run Plan → Work → Submit/Snapshot → Judge → Verdict   │
│ Work：持久、可写、跑 agent；Judge：一次性、干净、只读、私有测试       │
└───────────────────────────────▲─────────────────────────────────────┘
                                │ 冻结协议 / 预算 / rubric
┌───────────────────────────────┴─────────────────────────────────────┐
│ 控制平面                                                             │
│ 设计卡 G2 · 任务编译与静态检查 · 资源/网络策略 · 提交上限 · 成本账本   │
└─────────────────────────────────────────────────────────────────────┘
```

**四个平面的职责边界**：

- 控制平面不执行用户代码；只做任务编译、策略、预算与门禁。
- 执行平面不写稿件；只产出 run、submission、verdict、evidence。
- 证据平面不生成文本；只做 claim 准入、边、版本与失效传播。
- 写作平面不直接调用运行环境；只能消费 `confirmed` 的 result claim 与证据产物。

---

## 5. 对象模型与契约

### 5.1 对象清单

| 对象 | ID 前缀 | 作用 | 关键字段 |
| --- | --- | --- | --- |
| TaskSpec | `T-` | 一个可执行任务的不可变定义 | task_type、source、environment、workdir、resources、network、timeouts、rubric_digest |
| RunPlan | `RP-` | 一次运行的编译结果 | task_id、image_digest、tests_digest、agent、gpu_pool、network、timeouts、budget、seed |
| Run | `RUN-` | 一次 Work/Judge 生命周期 | run_plan_id、state、started_at、ended_at、cost、submission_ids |
| Submission | `SUB-` | 一次提交的快照 | round、snapshot_hash、changed_paths、manifest_hash、status |
| Verdict | `V-` | Judge 的判定 | submission_id、status、R/W/J、subscores、rubric_items、evidence_refs、failure_records |
| RubricItem | `RI-` | 一条可判定 rubric | dimension、weight、selector、pass_condition、partial_credit、hard_gate |
| EvidenceArtifact | `EA-` | 一个只读证据产物 | kind、path、sha256、produced_by、run_id、captured_at、immutable |
| FailureRecord | `FR-` | 一次失败归因 | stage、category、code、message、attributable、retryable、evidence_refs |
| Claim | `CL-` | 三类 claim 共用 ID | claim_kind（literature/result/manuscript）、text、conditions、status、evidence_refs |
| Figure | `F-` | 图包 | data_refs、code_hash、render_hash、caption_claim |
| ExportBundle | `EB-` | 可审计导出包 | manuscript、claim_graph、run_ledger、verdicts、ai_usage、manifest |

> 与 `04-` §2.14 的既有 ID 对齐：`CL` 继续做统一 claim 前缀，用 `claim_kind` 区分三类；`R` 结果卡保留，`RUN`/`EA`/`V` 是新增对象，不替代结果卡。

### 5.2 核心 JSON 契约（节选）

**TaskSpec**

```json
{
  "schema_version": "rwvh-1.0",
  "task_id": "T-RWJT-001",
  "task_type": "repro | write | repro_and_write",
  "title": "…",
  "source": {
    "paper_doi": "…",
    "paper_arxiv": "…",
    "code_repo": "…",
    "code_commit": "…",
    "data_revision": "…",
    "license": "…"
  },
  "environment": {
    "image": "…@sha256:…",
    "workdir": "/workspace",
    "cpus": 8,
    "memory_mb": 32768,
    "gpus": 0,
    "network_mode": "no-network"
  },
  "resources": {
    "agent_timeout_sec": 7200,
    "verifier_timeout_sec": 1800,
    "max_submissions": 5,
    "judge_budget_note": "CPU-only; one clean rerun"
  },
  "deliverables": ["result.json", "manuscript_section.md"],
  "rubric_digest": "sha256:…",
  "canary": "rwvh-canary GUID …",
  "closed_set": true
}
```

**Verdict**

```json
{
  "schema_version": "rwvh-1.0",
  "verdict_id": "V-0007",
  "submission_id": "SUB-0003",
  "status": "scored | candidate_invalid | incomplete | verifier_error | verifier_timeout | infrastructure_error",
  "scores": {
    "reproduction": {"modeling": 0.72, "execution": 0.81, "validation": 0.55, "R": 0.69},
    "writing": {"claim_coverage": 0.90, "number_traceability": 1.0, "figure_traceability": 0.83, "citation_validity": 1.0, "genre_compliance": 0.88, "W": 0.91},
    "joint": {"J": 0.79}
  },
  "rubric_items": [{"item_id": "RI-014", "pass": "partial", "evidence_refs": ["EA-021"]}],
  "failure_records": [{"stage": "validation", "category": "post_processing", "code": "unit_mismatch", "attributable": "candidate"}],
  "evidence_refs": ["EA-018", "EA-019", "EA-021"],
  "judge_version": "rwvh-judge-0.3.1",
  "judged_at": "2026-10-19T12:00:00Z"
}
```

**EvidenceArtifact**

```json
{
  "artifact_id": "EA-021",
  "kind": "metric | log | table | figure | receipt | raw_data",
  "path": "runs/RUN-0004/artifacts/metrics.json",
  "sha256": "…",
  "produced_by": {"run_id": "RUN-0004", "stage": "judge_rerun", "command": "python3 evaluate.py"},
  "captured_at": "2026-10-19T11:58:00Z",
  "immutable": true,
  "source": "rerun",
  "notes": "Only rerun-produced artifacts count as evidence."
}
```

### 5.3 不变量

| 编号 | 不变量 | 违反时 |
| --- | --- | --- |
| I1 | 没有 `source = rerun` 的 `EA`，不得创建 `result_claim` | claim 准入失败；写作只能标「待证」 |
| I2 | 没有 `result_claim`，稿件不得出现具体数字/「本文实验表明」类断言 | 槽位保持 `blocked`；导出阻断 |
| I3 | 没有冻结 protocol 与 G2 签署，不得开确证运行 | 运行请求被拒绝 |
| I4 | Judge 的文件系统、测试、rubric 不能被 Work 修改 | 运行判 `infrastructure_error`；不记候选分 |
| I5 | `candidate_invalid / verifier_error / verifier_timeout / infrastructure_error` 不等于 0 分 | 状态原样记录；按策略重试/人工 |
| I6 | 每条 verdict 必须能追到 rubric item 与 evidence artifact | verdict 不完整；不得作为 claim 准入依据 |
| I7 | 探索车道的 run 不得进入 claim 图 | Q1 失败；相关句子标 stale |
| I8 | 导出包必须含稿件、claim 图、运行账本、verdict、AI 使用记录与 manifest | 导出阻断 |

> 运行产物如何自动采集、形成 `EvidenceCard`、聚合成可入稿证据，以及最小证据包检查表，见 [21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md) §9.16；本节只定义对象与不变量，不重复采集协议。

### 5.4 状态机

**Run**：`planned → running → paused → judging → running → … → completed | no_valid_submission | failed | cancelled | timed_out`

**Submission**：`created → snapshot_ok → judging → scored | candidate_invalid | incomplete | verifier_error | verifier_timeout | infrastructure_error | submission_error`

**Claim**：`draft → supported | refuted | inconclusive → stale → superseded | retracted`

**Slot**：`empty → bound → conflicted → stale → orphan → blocked`

状态转换规则：

- `candidate_invalid` 是候选可归因的失败（schema 错、预算超限、训练发散、非法文件），不写 reward，但保留反馈。
- `verifier_error` 是测试脚本/评测器错误；本轮不计分，修好后重跑，不改变候选的有效性。
- `infrastructure_error` 是镜像/GPU/网络/调度失败；不计分，按预算重试。
- `verifier_timeout` 先判断是否候选导致；候选导致记 `candidate_invalid`，否则记基础设施。
- 只有 `scored` 且无 hard-gate 失败的 submission 才能成为 best-of-N 候选。

---

## 6. 运行生命周期

### 6.1 X0–X7

| 子状态 | 做什么 | 产物 | 失败去向 |
| --- | --- | --- | --- |
| X0 任务编译 | 解析 `task.toml`、校验字段/路径/网络/超时/测试引用/canary；构建或拉取镜像；记录 digest | `RP-`、`run-plan.json` | 编译失败，任务不可运行 |
| X1 Work 启动 | 从任务镜像起持久 Work；挂载工作区；注入 agent CLI 与 `submit` 客户端；设置预算与网络 | Work 容器 | 启动失败，infrastructure |
| X2 研究循环 | Agent 读 instruction、改工作区、跑本地检查、记录假设 | 工作区变更、`agent_output.txt` | Agent 超时/退出 |
| X3 提交 | `rsi-submit` 式控制请求；暂停 Work；快照 WORKDIR；算 `snapshot_hash`；传 manifest | `SUB-` | 提交非法，candidate_invalid |
| X4 Judge | 从干净镜像起一次性 Judge；只读挂载快照；注入私有 tests/rubric；无网重跑；捕获日志与产物 | Judge 容器、原始输出 | verifier/infrastructure |
| X5 判定 | 按 rubric 打分；固定证据；分类失败；写 verdict | `V-`、`EA-`、`FR-` | 判定不完整，不得准入 |
| X6 恢复/迭代 | 恢复 Work；回传聚合反馈（不泄露私有 rubric/测试）；下一轮 | feedback log | 达到提交上限/超时 |
| X7 收尾 | 从有效提交中按主分选最佳；生成最终结果与证据包；销毁 Work | `final_result.json`、`EB-` | 无有效提交，`no_valid_submission` |

### 6.2 Work 与 Judge 的边界

| 项目 | Work | Judge |
| --- | --- | --- |
| 生命周期 | 持久，跨提交 | 一次性，每轮新建 |
| 文件系统 | 可写工作区 | 干净镜像 + 只读快照 |
| 私有测试 | 不可见（hidden） | 注入 `/tests` |
| rubric | 不可见 | 私有；只回聚合反馈 |
| 网络 | 按任务策略 | 默认 no-network；只允许 pinned 模型端点（如需要） |
| 可修改评测工具 | 否 | 否；Judge 工具从镜像/平台只读挂载 |
| 轨迹 | 产生 | 只读 `/logs/agent` |
| 产物 | 工作区文件 | 只读证据包 + verdict |

### 6.3 oracle 与 nop

- **oracle**：`solution/solve.sh` 在 Work 中运行并提交；期望 R ≥ 0.90、W ≥ 0.90（T3/T4），且无 hard-gate 失败。oracle 失败 → 任务不得发布，先修环境/评测/参考解。
- **nop**：空提交/最小提交必须 R ≤ 0.10、W ≤ 0.20；如果 nop 得分高，说明任务泄漏、rubric 太松或测试可被绕过。
- **partial**：只完成建模/只完成执行/只完成写作的参考流程，用于验证分阶段评分能区分。
- **invalid**：故意伪造数字/引用、越界写文件、篡改测试的流程，必须被判 `candidate_invalid` 或 hard-gate 失败。
- oracle 的退出码只说明「参考解是否跑通」，不是科学结论；oracle 通过也不证明任务有区分度，仍需 baseline 分布。

### 6.4 best-of-N

- 只从 `scored` 且无 hard-gate 的提交中选。
- 主分相同：先比证据完整率，再比 Judge/Agent 成本，最后比更早轮次（鼓励少而准的迭代）。
- 不选「分数高但证据不完整」的提交；不选 `candidate_invalid`。
- 最终结果同时报：主分、各阶段分、有效提交数、无效提交数、总轮次、成本、是否超时。

### 6.5 时间、资源与成本

v1 约束：

| 项 | 上限 | 理由 |
| --- | --- | --- |
| Work GPU | 0 或 1 | CPU/单卡可覆盖 v1 任务 |
| Judge GPU | 0 或 1 | 与 Work 不同时占用；可用 release-all 模式 |
| Agent 超时 | 2 小时/任务 | 与 4 个任务的日迭代匹配 |
| Judge 超时 | 30 分钟/提交 | 避免 13 小时级任务 |
| 提交上限 | 5 次/任务 | 够迭代，不鼓励盲试 |
| 单任务总成本 | ≤ 50 元（LLM + 算力） | 与 `02-` 单篇 ≤ 30 元目标一致；基准任务可略高 |
| 并发 | 2 个任务 | 单机 Docker 可承受 |

> OpenRSI 的 8×H100 / 43 小时 Agent / 13 小时 Judge 是长程 RSI 任务的合理配置；我们的目标是「可日常运行的复现判定」，不是复刻其规模。

### 6.6 与 S0–S16 的映射

| 现有阶段 | RWVH 子状态 | 说明 |
| --- | --- | --- |
| S4 实验设计 | X0 前置 | G2 冻结 design card/protocol，编译为 TaskSpec |
| S5e/S5c 执行分析 | X0–X7 | 探索走 S5e；确证走 S5c（X0–X7） |
| S6 图表 | X5/X7 | 只接受 `EA` 中的 figure/table 产物 |
| S7–S8 论证/大纲 | — | 读取 `confirmed result_claim`，不直接读 run |
| S9 证据卡 | I1/I2 | 结果 claim 必须来自确证运行 |
| S10 逐节生成 | 槽位 | `R/X/N/F` 槽绑定 claim/run/artifact/figure |
| S13 全稿核验 | Q1 + verdict | 数字、引用、stale、孤儿、hard gate |
| S16 导出 | I8 | 导出包含 verdict 与运行账本 |

---

## 7. 隔离、安全与防作弊

### 7.1 隔离清单

| 层 | 机制 | 借自 | 我们的约束 |
| --- | --- | --- | --- |
| 进程/文件系统 | Work 与 Judge 分离；Judge 从干净镜像起；只读快照 | OpenRSI | 本地 Docker 优先 |
| 测试 | hidden tests；Judge 注入；Work 不可见 | OpenRSI | public rubric 仅用于 T3 的公开评分说明 |
| rubric | 私有 `rubric.json`；只回聚合反馈与受限诊断 | PaperBenchX | 反馈不泄露具体 rubric 阈值 |
| 网络 | Judge 默认 no-network；只允许 pinned 模型端点 | OpenRSI | 产品模式完全内网 |
| 代码执行 | 候选代码在 Judge 内以隔离身份运行；限制路径/网络/环境 | OpenRSI `rsi-isolate` | v1 可先用 Docker 非 root + 只读挂载 |
| 数据 | 产品模式数据只读挂载；不落第三方 | 本设计 | 私有部署；证据包回项目库 |
| 产物 | SHA-256、只读、来源标记（rerun/candidate） | PaperBenchX | 只认 rerun |
| 污染 | canary GUID；开放/封闭集；发布前扫描 | OpenRSI + PaperBenchX | canary 不用于规避 AIGC 检测 |
| 密钥 | 不进任务目录；日志脱敏；发布前扫描 | OpenRSI | 与 `03-` §2.2 一致 |
| 提交 | 单产物/闭包校验；symlink/特殊文件拒绝；路径白名单 | OpenRSI | 见 §7.2 |

### 7.2 防作弊检查

| 作弊路径 | 检查 | 失败后果 |
| --- | --- | --- |
| 直接写死期望结果 | 私有 rubric + 重跑 + 随机种子/数据切片 | hard-gate 失败 / 低分 |
| 篡改测试/评测器 | Judge 从干净镜像起；tests 只读；digest 校验 | infrastructure_error，本轮不计分 |
| 越界写文件/符号链接 | workspace scope、regular file、no symlink、路径白名单 | candidate_invalid |
| 用旧结果冒充新结果 | `snapshot_hash` + `EA` 来源 + run_id 绑定 | 数字槽 stale；导出阻断 |
| 只改文字不改数字 | 数字—产物一致性检查 | Q1 失败 |
| 伪造引用 | 引用存在性/字段/上下文支持核验 | hard-gate；引用真实率必须 100% |
| 用 agent 轨迹中的私有 rubric 反推 | 轨迹只读但 rubric 不进 Work；反馈只给聚合 | 设计上不泄露 |
| 训练/评测数据泄漏 | 开放/封闭集；canary；数据 revision 固定 | 任务重做 |
| 资源滥用 | 预算、超时、进程/显存上限 | candidate_invalid / infrastructure |
| 自动投稿/代投 | 导出包不含投稿接口；人工终审 | 产品边界拒绝 |

### 7.3 反馈边界

Judge 回给 Work 的反馈只包含：

- 聚合分与阶段分；
- 通过/未通过的 rubric 维度（不披露具体阈值与私有测试）；
- 有界的错误诊断（例如「metric 文件缺失」「单位不一致」）；
- 资源使用与是否超时；
- 下一轮建议的检查项（不泄露答案）。

不回传：私有 rubric 全文、隐藏测试、参考解、其他候选的提交、Judge 内部日志、模型凭据。

### 7.4 伦理与合规

- 产品模式默认私有部署；用户数据不进入第三方训练。
- AI 使用记录（模型、版本、提示词哈希、证据、人工修改）随导出包提供，可披露。
- 评审模拟只是自检，不生成真实审稿意见，不冒充期刊/基金评审。
- 不提供 AIGC 检测规避；canary 是 benchmark 污染控制。
- 不提供自动投稿、代写代投、伪造数据/引用。
- 湿实验只生成协议，由人执行（P2）。

---

## 8. 评分：三阶段复现 + 写作证据

### 8.1 复现分 R

借用 PaperBenchX 的三阶段拆分，但权重与判据由我们定义：

| 阶段 | 权重 | 判据 | 典型证据 |
| --- | ---: | --- | --- |
| Modeling 建模 | 0.30 | 模型/假设/变量/参数/边界是否与论文一致；是否遗漏关键条件 | 配置文件、模型定义、单位、参数表 |
| Execution 执行 | 0.30 | 环境、数据、种子、预算、收敛/诊断是否正确；是否完成重跑 | 运行日志、收敛曲线、资源记录、退出码 |
| Validation 验证 | 0.40 | 后处理、统计、单位、容差、结论是否由产物支持；是否可独立再生 | metric 文件、图表、对照表、重跑回执 |

`R = 0.30 M + 0.30 E + 0.40 V`

Validation 权重最高，因为 PaperBenchX 的项目口径显示它最弱，也因为我们的产品最容易被「结果是真的，但解释/后处理错了」击穿。

### 8.2 写作证据分 W

| 维度 | 权重 | 判据 | 硬门 |
| --- | ---: | --- | --- |
| Claim coverage | 0.30 | 结果节的事实句是否都有 `result_claim`；关键结论是否覆盖 | 核心 claim 覆盖率 ≥ 90% |
| Number traceability | 0.25 | 每个数字是否绑 `EA` + `RUN`；单位/精度/统计量是否一致 | 计分数字追溯率 = 100% |
| Figure/table traceability | 0.15 | 图/表是否由 `EA` 生成；caption 与正文数字一致 | 图/表溯源率 = 100% |
| Citation validity | 0.15 | 引用真实、字段正确、上下文支持 | 伪造引用 = 0；真实率 = 100% |
| Genre compliance | 0.15 | 中文核刊章节义务、结构、字数、GB/T 7714、版面锚点 | 结构完整率 = 100% |

`W = 0.30 C + 0.25 N + 0.15 F + 0.15 Cite + 0.15 G`

### 8.3 联合分 J 与一票否决

`J = 0.55 R + 0.45 W`（仅 T3/T4；T1/T2 只报 R，T3 只报 W）

一票否决（直接 `candidate_invalid` 或 `hard_gate_failed`）：

- 任何计分数字无法追到重跑产物；
- 任何引用被判定为伪造/错字段/不支持且未标「存疑」；
- 任何核心结果 claim 来自探索运行或未冻结协议；
- 任何导出句子含未解析槽位；
- 任何试图修改 Judge/测试/rubric 的行为。

否决不是 0 分，而是「不计分 + 明确原因」；只有 `scored` 的提交进入 best-of-N。

### 8.4 Rubric item 契约

```json
{
  "item_id": "RI-014",
  "dimension": "validation.post_processing",
  "weight": 0.08,
  "description": "Reported metric uses the same aggregation and unit as the reference protocol.",
  "selector": {"artifact": "metrics.json", "path": "$.aggregate.mean", "expected_unit": "nats"},
  "pass_condition": "abs(reported - reference) <= tolerance and unit matches",
  "partial_credit": {"0.5": "unit matches but aggregation differs"},
  "hard_gate": false,
  "evidence": ["EA-021"]
}
```

要求：

- 每个 item 必须可定位到 artifact/路径/条件；不能只写「质量好」。
- hard_gate item 只用于造假、越界、引用伪造、未解析槽等不可妥协项。
- partial credit 必须有明确档位，不能凭感觉给 0.6。
- rubric 的 digest 写入 TaskSpec 与 RunPlan；运行中不可改。

### 8.5 校准

| 步骤 | 做法 | 通过标准 |
| --- | --- | --- |
| Oracle | 参考解跑真实路径 | R ≥ 0.90；W ≥ 0.90；无 hard gate |
| Nop | 空/最小提交 | R ≤ 0.10；W ≤ 0.20 |
| Gold/Partial/Invalid | 三种参考流程 | 分数单调：gold > partial > nop；invalid 被判无效 |
| 双专家 | 2 位领域专家独立评 20% 样本 | Cohen's κ ≥ 0.60 |
| 分歧裁决 | 第三位专家或全体讨论 | 分歧项记录理由 |
| 低一致项 | κ < 0.40 的 item | 改写或删除 |
| 区分度 | 至少 1 个基线落在 oracle 与 nop 之间 | 否则任务太易/太难 |

### 8.6 失败分类

| 类别 | 归属 | 是否计分 | 处理 |
| --- | --- | --- | --- |
| `candidate_invalid` | 候选 | 否 | 回传具体校验错误；可重交 |
| `incomplete` | 候选 | 否 | 缺产物/缺字段；可重交 |
| `diverged` | 候选 | 否 | 训练发散/NaN/OOM；可改代码后重交 |
| `verifier_error` | 评测 | 否 | 修测试/环境后重跑；不惩罚候选 |
| `verifier_timeout` | 视原因 | 否 | 候选导致则 candidate_invalid；否则 infra |
| `infrastructure_error` | 基础设施 | 否 | 重试；记录预算 |
| `submission_error` | 提交 | 否 | 修提交后重交 |
| `scored` | — | 是 | 进入 best-of-N |

科学失败（低分但仍 `scored`）再细分：

- `modeling`：模型/假设/参数错；
- `execution`：环境/收敛/预算错；
- `validation`：后处理/单位/统计/结论错；
- `writing`：数字/claim/引用/体裁错；
- `genre`：结构/版面/字数错。

每条失败写 `FailureRecord`，带 stage、code、attributable、retryable、evidence_refs；用于后续修复路由与负结果记忆。

### 8.7 报告方式

最终报告必须同时给出：

- R、W、J 与各子分；
- 有效/无效提交数、轮次、成本、是否超时；
- hard-gate 是否触发；
- 失败分类分布；
- 与 oracle/nop/baseline 的对照；
- 不确定性与限制（样本量、专家数、κ、任务数）。

不允许只报一个总分，也不允许把自动评审分当作质量结论。

---

## 9. 任务包规范与构建流程

### 9.1 目录结构

```text
task/
├── task.toml                 # 任务定义与资源/网络/超时
├── instruction.md            # agent 可见说明；不含私有 rubric
├── environment/
│   ├── Dockerfile
│   ├── docker-compose.yaml   # 可选
│   ├── requirements.lock
│   └── prepare.py            # 数据/环境准备，固定 revision
├── tests/
│   ├── test.sh               # 入口；只输出允许的反馈
│   ├── evaluate.py           # 评分与证据固定
│   ├── rubric.json           # 私有 rubric
│   └── assets/               # 参考证据/容差/单位表
├── solution/
│   └── solve.sh              # oracle；不得读 /tests
├── artifacts/                # 可选：公开数据/冻结结果
├── README.md                 # 任务来源、协议、限制
└── LICENSE                   # 代码/数据许可证
```

### 9.2 `task.toml` 示例（RWJT）

```toml
schema_version = "1.4"

[task]
name = "researchweave/rwjt-001"
version = "1.0.0"
description = "Reproduce a fixed-seed result and write a Chinese core-journal Results section with evidence slots."

[metadata]
author_name = "Research Agent"
difficulty = "medium"
category = "RWJT"
tags = ["reproduction", "writing", "chinese-core-journal"]
source_paper = "…"
source_code_commit = "…"
expert_time_estimate_hours = 6

[environment]
os = "linux"
cpus = 8
memory_mb = 32768
storage_mb = 51200
build_timeout_sec = 3600
workdir = "/workspace"
gpus = 0
network_mode = "no-network"

[agent]
timeout_sec = 7200
network_mode = "public"   # 仅模型端点；由平台 pin

[verifier]
timeout_sec = 1800
network_mode = "no-network"
environment_mode = "shared"

[metadata.rwvh]
task_type = "repro_and_write"
primary_metric = "J"
score_direction = "maximize"
rubric_digest = "sha256:…"
writing_genre = "chinese_core_journal_results"
closed_set = true
canary = "rwvh-canary GUID …"
```

> 与 OpenRSI 的 `[metadata.rsi_harness.verifier]` 对齐：`gpus`、`visibility`、`clean_image` 可作为兼容字段；RWVH 自己的字段放 `[metadata.rwvh]`，避免污染 Harbor 语义。

### 9.3 `instruction.md` 必须回答

1. 研究问题与要复现的 claim/表/图是什么；
2. 工作区、起始状态、可改文件、禁止动作；
3. 固定协议：数据 revision、代码 commit、环境、种子、预算、指标、容差；
4. 交付物：结果文件 + 中文段落 + 证据槽格式；
5. 反馈边界：会看到什么、不会看到什么；
6. 提交检查清单：文件类型、大小、无 symlink、无额外进程；
7. 体裁要求：章节、字数、GB/T 7714、图表/公式规范；
8. 明确「不得伪造数字/引用；不得读 `/tests`；不得修改评测器」。

### 9.4 `rubric.json` 示例

```json
{
  "schema_version": "rwvh-rubric-1.0",
  "task_id": "T-RWJT-001",
  "dimensions": {
    "reproduction": {"weight": 0.55, "items": ["RI-001", "RI-002", "RI-003"]},
    "writing": {"weight": 0.45, "items": ["RI-010", "RI-011", "RI-012"]}
  },
  "items": [
    {
      "item_id": "RI-001",
      "dimension": "reproduction.modeling",
      "weight": 0.15,
      "selector": {"artifact": "result.json", "path": "$.model"},
      "pass_condition": "model matches reference within declared tolerance",
      "hard_gate": false
    },
    {
      "item_id": "RI-010",
      "dimension": "writing.number_traceability",
      "weight": 0.20,
      "selector": {"manuscript": "section.md", "pattern": "\\[\\[N:EA-[0-9]+\\]\\]"},
      "pass_condition": "every numeric token has a resolvable EA with source=rerun",
      "hard_gate": true
    }
  ],
  "hard_gates": ["fabricated_number", "fabricated_reference", "unresolved_slot", "judge_tamper"]
}
```

### 9.5 九步构建流程

| 步 | 做什么 | 产物 | 失败条件 |
| ---: | --- | --- | --- |
| 1 | 选论文/claim/范围；确认许可证、代码/数据可得 | 任务卡 | 代码/数据不可得；许可不允许 |
| 2 | 可行性：软件、算力、时间、成本、确定性 | 可行性报告 | 单次 Judge > 30 分钟；依赖商业软件 |
| 3 | 原生/固定环境：pin commit、镜像 digest、数据 revision、seed | Dockerfile、lock | 版本漂移；构建不可复现 |
| 4 | 公开 instruction：目标、工作区、可改/不可改、交付物、反馈边界 | `instruction.md` | 含私有 rubric/答案 |
| 5 | 参考流程 + 初始运行：`solution/solve.sh`、gold artifacts | 参考解 | oracle 跑不通 |
| 6 | 细粒度 rubric：建模/执行/验证/写作；权重、硬门、容差 | `rubric.json` | item 不可定位；无 partial credit |
| 7 | 干净重跑：同接口、无网、删除生成物、只认重跑产物 | 重跑回执 | 重跑结果不一致且无法解释 |
| 8 | 校准：oracle/nop/gold/partial/invalid + 双专家 + κ | 校准报告 | oracle < 0.9；nop > 0.1；κ < 0.6 |
| 9 | 复核与冻结：两位专家、canary、开放/封闭划分、digest | 发布包 | 任一专家拒绝；泄漏/污染 |

### 9.6 v1 任务集（4 个）

| 编号 | 类型 | 内容 | 判定 | 预算 | 状态 |
| --- | --- | --- | --- | --- | --- |
| T1 | `repro` | 小规模 ML/优化结果复现：固定数据切片、固定种子、CPU 可跑；候选只交配置/结果，Judge 重跑 | R（M/E/V） | ≤ 10 分钟 | 候选池待 M1 预检 |
| T2 | `repro` | 计算科学结果复现：从 PySCF/Meep/ABACUS 等开源求解器选 1 个轻量任务；不选商业许可环境 | R | ≤ 30 分钟 | 候选池待 M1 预检 |
| T3 | `write` | 给定冻结运行包与论文，写中文核刊「结果与分析」节；不执行 | W | ≤ 5 分钟 | 可与 T1 共用 artifacts |
| T4 | `repro_and_write` | 复现 1 个表/图，并写对应的中文核刊段落；数字/图必须挂重跑产物 | J = 0.55R + 0.45W | ≤ 30 分钟 | 旗舰任务 |

**候选池准入**（T1/T2）：公开代码 + 公开数据（或可再分发切片）+ 许可证允许 + 单次运行 ≤ 30 分钟 + 结果对种子/环境不敏感（或有明确容差）+ 有可核对的参考值。M1 结束前必须完成 3 选 1 的预检，未通过则缩为 3 个任务（T1+T3+T4）。

### 9.7 发布检查清单

- [ ] oracle / nop / partial / invalid 全部跑通；
- [ ] 双专家签字，κ ≥ 0.60；
- [ ] 无 `/tests` 泄漏到 Work；
- [ ] canary 覆盖 `instruction.md`、`task.toml`、`environment/`、`tests/`、`solution/`；
- [ ] 密钥扫描通过；
- [ ] 镜像/数据/代码 digest 固定；
- [ ] 单次 Judge ≤ 30 分钟；
- [ ] 任务来源、许可证、限制写入 README；
- [ ] 开放/封闭划分记录；
- [ ] rubric digest 与 TaskSpec/RunPlan 一致。

---

## 10. 与写作链路的衔接

### 10.1 三类 claim 与两种证据等级

| claim 类型 | 来源 | 证据 | 可进入的位置 |
| --- | --- | --- | --- |
| `literature_claim` | S1 文献阅读 | span + 来源 + 版本 | 引言/相关工作/讨论的文献陈述 |
| `result_claim` | S5c 确证运行 | `EA` + `RUN` + protocol | 结果/摘要/结论中的「本文实验」 |
| `manuscript_claim` | S10 生成 | 上述两类 claim + 论证关系 | 稿件句子 |

证据等级：

- `confirmed`：来自确证运行，可用于结果/摘要/结论；
- `exploratory`：来自探索运行，只能用于内部笔记，不得进入稿件；
- `literature`：来自文献，只能支持文献陈述，不能支持「本文实验」；
- `inferred`：推理/外推，必须显式标注，不得写成确定事实。

### 10.2 槽位语法扩展

在既有 `E/N/F/C` 四类槽上新增两类：

| 槽 | 绑定对象 | 示例 | 导出要求 |
| --- | --- | --- | --- |
| `E` | 文献 claim | `[[E:CL-0042]]` | claim 存在、span 可定位、未 stale |
| `R` | 结果 claim | `[[R:CL-0107]]` | claim 为 `confirmed`，绑 `RUN`/`EA` |
| `N` | 数字/证据产物 | `[[N:EA-021]]` | 产物存在、来源 rerun、单位/精度一致 |
| `F` | 图/表 | `[[F:F-003]]` | 图包存在、数据/代码 hash 完整 |
| `X` | 运行 | `[[X:RUN-0004]]` | run 为 `scored`，protocol 冻结 |
| `C` | 交叉引用 | `[[C:sec-3.2]]` | 目标存在、编号一致 |

示例句子：

```text
在相同数据与预算下，本文方法的平均误差为 0.317[[N:EA-021]]，
较基线降低 12.4%[[R:CL-0107]][[X:RUN-0004]]，见图 3[[F:F-003]]。
```

导出时：

- `EA-021` 必须存在且 `source=rerun`；
- `CL-0107` 必须为 `confirmed`，其证据包含 `RUN-0004`；
- `F-003` 的数据必须来自 `RUN-0004`；
- 三者任一 stale，句子标 `blocked`，导出阻断。

### 10.3 claim 准入规则

1. `result_claim` 只能由 S5c 的确证 verdict 创建；探索 run 不能创建。
2. `result_claim` 必须带：claim 文本、数值/方向、条件（数据/指标/设置）、`RUN`、`EA`、置信/不确定性、反证条件。
3. `manuscript_claim` 必须至少绑定 1 个 `result_claim` 或 1 个 `literature_claim`；不得凭空创建。
4. 文献 claim 不能支持「本文实验表明」；结果 claim 不能支持「已有工作普遍认为」。
5. 冲突证据标 `unresolved`；核心结论冲突升级人工裁决。
6. 任何 claim 进入 `stale`，其下游句子与图表自动标 `stale`，导出阻断。

### 10.4 失效传播

新增边：

| 边 | 方向 | 语义 |
| --- | --- | --- |
| `reproduced_by` | result claim → run | 该 claim 由该确证运行产生 |
| `measured_by` | result claim → EA | 该 claim 的数值来自该产物 |
| `derived_from_run` | figure/table → run | 图/表由该运行生成 |
| `invalidated_by_run` | result claim → run | 新运行推翻/削弱旧 claim |
| `supersedes` | claim → claim | 新版本替代旧版本 |

传播规则：

- run 变为 `invalid/superseded` → 所有 `reproduced_by` 的 result claim 变 `stale`；
- result claim 变 `stale` → 所有绑定它的 manuscript claim、句子、图、表变 `stale`；
- protocol 变更 → 旧 run 不删，标 `superseded`；新 run 产生新 claim 版本；
- 数字变化 → 触发 Q1 数字核对与摘要/结果节重写；
- 引用撤稿 → literature claim 降级 → 相关句子标 `blocked`。

### 10.5 导出硬门

导出前必须全部通过：

1. 所有 `R/X/N/F` 槽可解析；
2. 所有计分数字 `source=rerun`；
3. 所有引用真实率 100%，或显式标「存疑」并人工确认；
4. 无 `stale`/`orphan`/`blocked` 句子；
5. 图/表数据来自 `confirmed` run；
6. 结构完整率 100%，GB/T 7714 通过；
7. 证据包含 claim 图、run 账本、verdict、AI 使用记录、manifest；
8. 人工终审签署。

任一条不满足：导出阻断，列出受影响句子与修复建议；不允许「先导出后补」。

---

## 11. 需求增量 FR-18–FR-24

### 11.1 总表

| 编号 | 名称 | 优先级 | 人周 | 依赖 | 主要验收 |
| --- | --- | --- | ---: | --- | --- |
| FR-18 | 复现执行底座（Work/Judge/快照/提交/状态） | P0 | 8 | B0 | oracle 跑通；快照隔离；状态机完整 |
| FR-19 | 任务包、私有 rubric 与静态检查 | P0 | 4 | FR-18 | 4 个任务包通过发布检查；无泄漏 |
| FR-20 | 独立重跑与证据固定 | P0 | 4 | FR-18/19 | 只认重跑产物；EA 100% 可追 |
| FR-21 | 分阶段评分与失败归因 | P0 | 3 | FR-20 | R/W/J 可复跑；失败分类 100% |
| FR-22 | RWJT 联合任务与中文写作审计 | P0 | 6 | FR-19/20/21 | 数字追溯 100%；核心 claim 覆盖 ≥90% |
| FR-23 | 任务构建、校准与开放/封闭集 | P1 | 6 | FR-19/22 | oracle≥0.9；nop≤0.1；κ≥0.6 |
| FR-24 | 原生科学环境与集群/GPU 调度 | P1/P2 | 8 | FR-18/23 | 1 个原生环境任务；1 卡/多节点可调度 |

> H1–H5 的人周拆分见 §12.1：8+4+4+3+6 = 25，分别对应 FR-18、FR-19、FR-20、FR-21、FR-22；与总表是同一组数字，不重复计算。

### 11.2 FR-18 复现执行底座（P0）

- Work 持久、可写；Judge 一次性、干净镜像；快照只读；提交触发暂停。
- 状态机、日志、`final_result.json`、`report.json`、`run-plan.json`。
- oracle 路径；best-of-N；提交上限；超时；失败恢复。
- **验收**：4 个任务 oracle 全部跑通；Work 修改 `/tests` 不影响 Judge；快照外文件不进 Judge；状态与产物字段完整率 100%。

### 11.3 FR-19 任务包、私有 rubric 与静态检查（P0）

- `task.toml`、`instruction.md`、`environment/`、`tests/`、`solution/` 规范。
- 静态检查：字段、路径、超时、网络、测试引用、canary、密钥、symlink、镜像 digest、rubric digest。
- 私有 rubric；反馈边界。
- **验收**：4 个任务包 100% 通过静态检查；`/tests` 不出现在 Work；反馈不泄露 rubric 阈值。

### 11.4 FR-20 独立重跑与证据固定（P0）

- Judge 在无网/隔离环境重跑；删除候选生成物；只读固定日志/原始数据/派生指标。
- `EA` 的 path/sha256/source/run_id；`source=rerun` 才可准入。
- 重跑一致性检查与容差。
- **验收**：每个计分数字 100% 绑 `EA`；候选生成物 0 个被当证据；重跑不一致 100% 有 `FailureRecord`。

### 11.5 FR-21 分阶段评分与失败归因（P0）

- M/E/V 三阶段 + W 五维；权重/硬门/partial credit。
- 失败分类：candidate/verifier/infrastructure/timeout；科学失败五类。
- 报告：R/W/J、有效/无效、成本、轮次、失败分布。
- **验收**：与人工复核一致率 ≥ 90%；infra 失败 0 个被记 0 分；失败分类覆盖率 100%。

### 11.6 FR-22 RWJT 联合任务与中文写作审计（P0）

- 复现 1 个表/图 + 写中文核刊「结果与分析」节。
- 数字/图/claim 槽；GB/T 7714；结构/字数/版面锚点。
- 导出硬门；失效传播。
- **验收**：计分数字追溯率 100%；核心 result claim 覆盖率 ≥ 90%；伪造数字/引用 0 个通过；结构完整率 100%。

### 11.7 FR-23 任务构建、校准与开放/封闭集（P1）

- 6–8 个任务；开放/封闭划分；双专家；κ；oracle/nop/gold/partial/invalid。
- 负结果报告；任务退役机制。
- **验收**：oracle ≥ 0.90；nop ≤ 0.10；至少 1 个基线在中间；κ ≥ 0.60；任务泄漏 0。

### 11.8 FR-24 原生科学环境与集群/GPU 调度（P1/P2）

- 1 个原生科学环境（PySCF/Meep/ABACUS 选 1）；1 卡/多节点调度；GPU 释放模式。
- 许可证与镜像分发；数据/软件 revision 固定。
- **验收**：原生任务可重跑；1 卡任务与 CPU 任务可并行；集群失败可归因。

---

## 12. 工作量、团队与里程碑

### 12.1 新增工作包

| 工作包 | 内容 | 人周 | 里程碑 |
| --- | --- | ---: | --- |
| H1 复现执行底座 | Work/Judge、快照、提交、状态机、oracle、best-of-N、本地 Docker | 8 | M1–M2 |
| H2 任务包与静态检查 | TaskSpec、`task.toml`、instruction、rubric schema、检查脚本、canary/密钥 | 4 | M1–M2 |
| H3 独立重跑与证据固定 | 无网重跑、产物账本、EA、重跑一致性、证据包 | 4 | M2–M3 |
| H4 分阶段评分与失败归因 | M/E/V + W、rubric 引擎、失败分类、报告 | 3 | M3 |
| H5 RWJT 与中文写作审计 | 4 个任务、中文段落、槽位、导出硬门、失效传播接口 | 6 | M3–M5 |
| **P0 合计** | | **25** | |
| H6 任务扩展与校准 | 6–8 任务、开放/封闭、双专家、κ、负结果 | 6 | M6 |
| H7 原生科学环境 | PySCF/Meep/ABACUS 选 1、许可证、镜像、重跑 | 4 | M6 |
| H8 集群/GPU 调度 | 1 卡/多节点、release-all、失败归因 | 4 | M6–M7 |
| **全量合计** | | **39** | |

> 25 人周是 P0；39 人周含 P1。与 `02-` §4.2.4 的 190 人周基线相加：**215 / 229 人周**。H1–H8 与 FR-18–FR-24 对应，表中不重复加总。

### 12.2 产能对账

| 配置 | FTE | 8 个月产能 | P0 215 | 全量 229 | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| 8 名学生 + 1 顾问 | 5.7 | ≈196 人周 | 110% | 117% | **装不下**；必须砍功能或加人 |
| **9 名学生 + 1 顾问（推荐）** | 6.4 | ≈220 人周 | **98%**（缓冲 5） | 104% | P0 可做；全量需 10+1 |
| 10 名学生 + 1 顾问 | 7.1 | ≈244 人周 | 88% | **94%**（缓冲 15） | 全量可行 |
| 5 名学生 + 1 顾问 | 3.5 | ≈120 人周 | 179% | 191% | 不可行；只能做压缩版 |

**推荐方案**：

- **9+1，P0 215 人周，98%**：适合「必须交付复现判定层」的版本；缓冲只有 5 人周，M1 后必须按实际 FTE 复估。
- **9+1，稳妥 206 人周，94%**：把 FR-12 评审模拟（9 人周）后置到答辩后；核心 P0 + FR-10 + 复现层保留。
- **10+1，全量 229 人周，94%**：增加 6–8 任务、原生环境、集群；适合要冲系统/评测论文的版本。
- **5 人最小版**：只做「核刊单体裁 + 证据层 + 1 个 RWJT 任务」，不做 T1/T2、不做评审模拟、不做失效传播全量；约 115 人周，120 人周产能的 96%。

### 12.3 里程碑映射

| 里程碑 | 新增交付 | 验收 |
| --- | --- | --- |
| M0 招募与定题 | 9 个题目、复现层范围冻结 | 每人一个可独立交付模块 |
| M1 底座 + 任务包 | H1 最小版、H2、T1 预检 | Work/Judge 跑通；1 个任务 oracle 通过 |
| M2 评分 + T1/T3 | H3、H4、T1/T3 | R/W 可复跑；nop ≤ 0.1 |
| M3 RWJT | H5、T2/T4 | J 可复跑；数字追溯 100% |
| M4 图表 + 全稿 | 与 G4/G5 集成 | 图/表证据链完整 |
| M5 申报书 + 评审 | 第二体裁、FR-12（可选） | 结构/证据门通过 |
| M6 失效 + 校准 | FR-10、H6/H7、双专家 | 失效召回 ≥85%；κ ≥0.6 |
| M7 整合 + 成文 | H8（可选）、论文/答辩 | 系统演示 + 投稿初稿 |

### 12.4 风险

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| 任务选不到「30 分钟可复现」的论文 | v1 任务不足 | M1 前 3 选 1；不满足则缩为 T1/T3/T4 三任务 |
| 重跑不确定 | 同一提交分数漂移 | 固定种子/数据切片；容差；重复 2 次取中位数（仅不确定任务） |
| 专家时间不足 | rubric 校准拖延 | 顾问 0.2 FTE + 2 位外部专家按小时计费；先校准 20% 样本 |
| LLM Judge 偏差 | 分数不可信 | 程序检查优先；LLM 只做领域解释；双专家校准；κ 门槛 |
| 私有数据合规 | 产品模式不能外送 | 私有部署；Judge 内网；数据只读挂载；证据包不出项目库 |
| 原生软件许可 | 不能分发镜像 | 选开源求解器；商业软件任务放 P2 且不公开镜像 |
| 与主流水线耦合过深 | 进度互相拖累 | RWVH 作为独立服务，通过 TaskSpec/Verdict/EA 接口接入；先跑通 T1 再接 S5c |
| 过度宣称 | 被质疑「又一个 benchmark」 | 只报本地 4 任务结果；不称「首个」；外部数字不进我们的结果 |

---

## 13. 验收指标

### 13.1 Harness 自身

| 指标 | 目标 |
| --- | --- |
| oracle 通过率 | 100%（4/4） |
| nop 得分 | R ≤ 0.10；W ≤ 0.20 |
| Work→Judge 泄漏 | 0（`/tests`、rubric、参考解均不可见） |
| 快照隔离 | 100%（快照外文件 0 个进入 Judge） |
| 证据产物可追 | 100%（path + sha256 + run_id） |
| 失败分类覆盖 | 100% |
| infra 失败误记 0 分 | 0 |
| 单次 Judge 超时 | ≤ 30 分钟（v1 全部任务） |
| 重跑一致性 | 确定任务 100%；不确定任务有容差与重复策略 |
| 导出硬门 | 未解析槽位 0 个导出 |
| 成本 | 单任务 ≤ 50 元；单篇全流程 ≤ 30 元（不含基准任务算力） |

### 13.2 基准与联合任务

| 指标 | 目标 |
| --- | --- |
| 任务数 | P0 4 个；P1 6–8 个 |
| rubric item 数 | 每任务 ≥ 20 条，覆盖 M/E/V/W |
| 双专家 κ | ≥ 0.60 |
| oracle R / W | ≥ 0.90 / ≥ 0.90 |
| 基线区分度 | 至少 1 个基线在 oracle 与 nop 之间 |
| 数字追溯率 | 100% |
| 核心 result claim 覆盖 | ≥ 90% |
| 伪造数字/引用通过 | 0 |
| 结构完整率 | 100% |
| 失效传播召回（与 FR-10 一致） | ≥ 85%，误报 ≤ 20% |
| 人工复核一致率 | ≥ 90% |

### 13.3 发布门槛

- 4 个任务全部通过 §9.7 清单；
- oracle/nop/partial/invalid 四类流程可复跑；
- 双专家签字；
- 至少 1 篇内部负结果报告（哪些任务不可复现、为什么）；
- 不把外部 benchmark 数字写进我们的结果表。

---

## 14. 不可宣称与残余风险

### 14.1 不可宣称

- 不称「General AI Scientist」「RSI」「首个复现 benchmark」「首个中文科研 benchmark」。
- 不称「开源都没做」；OpenRSI 已有 Work/Judge、快照、私有测试、oracle；PaperBenchX 已有三阶段复现评分、原生环境、独立重跑。我们只称「把复现判定接到中文写作证据链」。
- 不把 PaperBenchX 的 59.08%、13.98%、62.70/61.84/42.80 当作我们的结果或目标；这些是外部项目口径，未独立核验。
- 不把 OpenRSI 的任务数、GPU 规模、日志当作我们的能力证明。
- 不称「全自动」；A3 仍是人机协同。
- 不称「评审模拟能替代真实审稿」；它只是自检。
- 不称「通过本系统就能投稿」；导出不等于投稿，署名与责任在人。

### 14.2 残余风险

| 风险 | 说明 | 缓解 |
| --- | --- | --- |
| 任务泄漏 | 公开任务可能被模型记忆 | 封闭集；canary；私有 rubric；M6 复核 |
| 过拟合 rubric | Agent 可能针对评分模式优化 | 隐藏部分 item；轮换任务；人工抽查 |
| LLM Judge 偏差 | 领域解释可能不稳 | 程序检查优先；双专家；κ |
| 重跑不确定 | 随机性/硬件差异 | 固定种子；容差；重复；记录环境 |
| 原生软件许可 | 不能公开镜像 | 开源优先；商业软件不公开；P2 |
| 私有数据合规 | 产品模式数据敏感 | 私有部署；内网 Judge；最小化数据 |
| 成本 | 多次重跑 + LLM | 预算；缓存；只对确证运行开 Judge |
| 团队产能 | 9+1 仍紧 | M1 复估；FR-12 后置；任务缩为 3 个 |

---

## 15. 参考与复现命令

### 15.1 本地证据入口

| 内容 | 路径 |
| --- | --- |
| OpenRSI 总览与 16 任务表 | `oss/OpenRSI-Index-main/README.md` |
| Harness 生命周期、oracle、运行产物 | `oss/OpenRSI-Index-main/RSI-Harness/README.md` |
| `task.toml` 全字段、Judge 隔离、public/hidden、model_access | `oss/OpenRSI-Index-main/RSI-Harness/docs/harbor-task-authoring/task-toml.md` |
| 示例任务包 | `oss/OpenRSI-Index-main/rsi-tasks/depth-width-allocation/` |
| 示例 Judge | `.../tests/evaluate.py`、`tests/test.sh` |
| 示例参考解 | `.../solution/solve.sh` |
| 静态检查 | `oss/OpenRSI-Index-main/checks/` |
| 贡献流水线 | `oss/OpenRSI-Index-main/CONTRIBUTING.md`、`.agents/skills/proposal-agent/SKILL.md` |
| PaperBenchX | 用户提供的文章；仅 `[项目口径，未独立核验]` |

### 15.2 可复现命令

```bash
# 1) 任务包结构
find oss/OpenRSI-Index-main/rsi-tasks/depth-width-allocation -maxdepth 2 -type f

# 2) Work/Judge/快照/私有测试的生命周期
grep -n "persistent, isolated Work\|fresh, isolated Judge\|snapshot of Work\|private tests" \
  oss/OpenRSI-Index-main/RSI-Harness/README.md

# 3) task.toml 的 Judge/资源/网络字段
grep -n "\[metadata.rsi_harness.verifier\]\|visibility\|clean_image\|model_access\|rsi-isolate" \
  oss/OpenRSI-Index-main/RSI-Harness/docs/harbor-task-authoring/task-toml.md

# 4) oracle
grep -n "agent oracle\|solution/solve.sh\|rsi-oracle" \
  oss/OpenRSI-Index-main/RSI-Harness/README.md

# 5) 示例评测的预算/重跑/独占 reward
grep -n "PARAM_LIMIT\|TRAIN_LIMIT\|subprocess.run\|reward.json\|source_tree_sha256" \
  oss/OpenRSI-Index-main/rsi-tasks/depth-width-allocation/tests/evaluate.py

# 6) canary 与静态检查
grep -n "CANARY_STRING\|FAIL" oss/OpenRSI-Index-main/checks/check-canary.sh
ls oss/OpenRSI-Index-main/checks/check-*.sh | wc -l
```

> 这些命令只证明「机制/文本存在」，不证明端到端可运行；运行验证仍列在 `03-` §4 待补清单。

---

## 附录 A：一个 RWJT 的完整走法（示例）

**任务**：复现某小规模 ML 论文的表 2（固定数据切片、固定种子），并写中文核刊「结果与分析」一节。

1. **X0**：TaskSpec 固定代码 commit、数据 revision、seed、CPU 8 核、Judge 30 分钟；rubric digest 冻结。
2. **X1**：Work 启动；agent 看到 `instruction.md`，看不到 `/tests`。
3. **X2**：agent 读论文、写配置、跑本地检查；探索性试跑只写 `notes/`，不进 claim。
4. **X3**：agent 交 `result.json` + `section.md`；Work 暂停；快照。
5. **X4**：Judge 从干净镜像起，只读挂载快照；删除候选生成的 `result.json`/图；用固定 source 重跑；产出 `EA-021`（metric）、`EA-022`（图数据）、`EA-023`（日志）。
6. **X5**：Judge 按 rubric 打分：
   - M：模型/参数/单位是否一致；
   - E：数据/种子/预算/收敛；
   - V：后处理/容差/结论；
   - W：`section.md` 的每个数字是否绑 `EA`、图是否绑 `F`、引用是否真实、结构是否符合核刊。
7. **X6**：若 W 的数字追溯失败，反馈「第 2 段数字 `12.4%` 无对应 EA」；agent 修正后重交。
8. **X7**：从有效提交中选 J 最高者；导出 `EB`：稿件、claim 图、run 账本、verdict、AI 使用记录、manifest。
9. **人工终审**：人确认结论强度、限制、署名；导出，不自动投稿。

**预期 verdict**：R = 0.69（M 0.72 / E 0.81 / V 0.55），W = 0.91，J = 0.79；V 低是因为后处理单位不一致，触发 `FailureRecord(validation.post_processing.unit_mismatch)`；W 高是因为数字/图/引用全部可追。这个例子说明：**复现分低不等于写作分低，写作分高也不能掩盖验证失败**——两者必须分开报。

---

*本文是设计稿，不是已实现声明。所有「将/目标/验收」均为计划；所有外部系统数字均为其项目口径，未在本地复现。*

# RSI-Anything 深读反思：执行契约、保留层与领域不对称

> 版本：v0.1 · 日期：2026-10-19 · 性质：对本地代码快照的逐文件深读与设计修订
> 上游依据：[10](10-RSI与自进化反思-科研改进的准入与证据闭合.md) §1.9、[11](11-自进化循环设计-准入理由、跨循环继承、迁移与能力增益.md) §1.2/§3.0/§3.4、[07](07-复现级验证与执行Harness设计.md) 的 RWVH、[09](09-系统架构与流程编排设计.md) 的 Q1 与门禁
> 快照：`oss/RSI-Anything-main/`，commit `8ba44cd73ec6f57b151ec06e2f71a0726adfb687`，573 文件 / 18,229,117 bytes，Apache-2.0
> 证据纪律：代码机制标 `[代码]`；作者数字标 `[作者口径]`，本轮**未复现**；对“五域”的判断以**公开代码是否可运行**为准，不以 README 宣传为准
> 用途：回答“上一轮我们借对了什么、漏了什么、下一版设计要改哪里”；不是给 RSI-Anything 写评测，也不是把它的数字搬进本项目

---

## 0. 一页结论

上一轮我们把 RSI-Anything 概括为“预测—选择—保留的任务运行时”，并借了三个点：EV0 预测预筛、incumbent guard、判定封存 + cohort 隔离。**这个概括只说对了一半。**

深读代码后，更准确的判断是：RSI-Anything 是一台**三层机器**：

1. **任务层**：四候选 + incumbent 的 propose → predict → select → execute → feedback；预测只用于排序/选择，真实反馈才进入下一轮。
2. **运行层**：recipe → plan → stage → run record；有 run identity、source identity、stage receipt、输出哈希、resume、attempts 归档、文件锁、进程组清理、失败摘要。**这一层比我们的文档设计更成熟。**
3. **保留层**：代码修复是四段 checkpoint 继承链；GUI 是两代 world/policy pair + 2×2 交叉测试；实验室规划是 pair 级 retain；反应优化其实**冻结不学**；免疫科学标 **Coming soon**。

因此，本轮反思的结论是：

| # | 结论 | 对设计的影响 |
| --- | --- | --- |
| R1 | 我们上一轮只借了“三个点”，漏了“两个面”：**执行契约**与**交叉/条件确认** | 新增 E 层（执行契约）与 A 层（独立审计）；EV4 增加 2×2 交叉与 conditional confirmation |
| R2 | RSI-Anything 的任务级准入并不弱；弱的是**保留对象**与**证据闭合** | 差异必须收窄到 claim 级租约、护照、撤销传播、稿件槽与导出硬门，不能说“它没有准入” |
| R3 | 它的“五域”不是五条同等可运行的 RSI 回路 | 我们的能力矩阵必须区分“全链路可运行 / 冻结推理 / 未发布”，不能按 README 域数计分 |
| R4 | 它的 seal 是**进程内不变量**，不是外部时间戳或密码学证明 | 我们若要更强，需加外部锚定；不能把 `all_decisions_sealed_before_hidden_judge=True` 当绝对证明 |
| R5 | 它的 runner 对**源码**身份很强，对**外部资产**身份是任务自己补的 | 我们的 E 层必须把检索快照、prompt、模板、期刊规则、图表规格都纳入 identity，不能只哈希代码 |
| R6 | 我们目前的“可复现、可审计”仍停在文档与 SIM 演示 | 在 E1–E4 + A1–A3 跑通前，不继续扩写 EV 机制，也不再加新的演示图表 |
| R7 | 机制差异成立，效果差异未证明 | 可以说“我们做 claim 级准入与证据闭合的设计”；不能说“我们比它更强/更有效” |

一句话：**RSI-Anything 把“任务级改进如何被干净地接受”做得很实；我们要做的不是再喊一次“准入”，而是把准入接到 claim、句、图与导出，并且先把自己的运行契约补到同一水平。**

---

## 1. 深读范围与证据等级

### 1.1 读了什么

| 层 | 文件 | 本轮读到的内容 | 证据 |
| --- | --- | --- | --- |
| 总览 | `README.md`、`docs/workflow.md` | 六阶段循环、五域、命令、stage plans、run records、resume 规则 | `[文档]` |
| 运行器 | `src/rsi_anything/workflow/runner.py`、`config.py`、`types.py` | run identity、锁、receipts、attempts、source identity、plan dry-run | `[代码]` |
| 适配器 | `src/rsi_anything/tasks/code_repair.py`、`tasks/gui.py` | 四段 checkpoint 链、GUI 六阶段、expected artifacts | `[代码]` |
| 代码修复 | `tasks/code_repair/src/development.py`、`evaluation.py`、`incumbent.py` | dev 选择、5 候选 choose、public seal、hidden judge、Brier | `[代码]` |
| GUI | `tasks/gui/src/rsi_anything_gui/protocol.py`、`rsi.py`、`audit.py`、`experiment.py` | 11 个互斥 cohort、两代 pair、2×2 交叉、promotion gate、独立审计、事务式 episode | `[代码]` |
| 其他域 | `tasks/laboratory_planning/README.md`、`tasks/reaction_optimization/README.md`、`tasks/immune_science_v2/README.md` | pair retain 的文档描述、冻结推理、未发布 | `[文档]` |
| 测试 | `tests/test_workflow.py` | 17 个运行器契约测试 | `[代码]` |
| 资产 | `docs/ASSET_CARD.md`、`docs/benchmarks.md` | 资产内容、provenance、许可证、benchmark 口径 | `[文档]` |

### 1.2 证据等级

- **代码可核对**：机制存在、入口存在、测试存在；本轮**未执行**其训练/评测，因为需要 GPU、模型与大数据资产。
- **文档可核对**：stage plan、域说明、限制声明。
- **作者口径**：CodeContests 31.2%、APPS 46.37%、LiveCodeBench 33.05%、MiniWoB++ 99%、OSWorld +18.4%、LabHorizon 46.01%、Suzuki 96.15%。**全部未复现，不得当成本项目结果。**
- **不可核对**：免疫科学只有 “Coming soon”，没有实现可读。

### 1.3 一个必须先说清的纠正

上一轮 §1.9 写“它没有证明什么”时，列了“保留对象是 checkpoint、判定停在任务层、预测不是证据、没有中文长文、数字未复现”。这些仍然成立。但**不能由此推出“它的工程严谨性弱”**。相反：

- 它的 runner 有 17 个契约测试，覆盖 resume、输出篡改、失败停止、重试归档、缺失产物、覆盖保护、recipe 变更、文件锁、外部目录保护、GUI 命名空间、checkpoint 链、venv symlink、无 ML 依赖的 plan、checkpoint 内容变更、浏览器资产身份、非法 recipe、源码目录保护。
- 它的 GUI audit 是一套**独立实现**，从 raw transitions 重新计算动作合法性、episode 链、训练谱系、校准、冻结时间、成本与 promotion gate，而不是相信 summary。
- 它的 protocol 明确写 `limits`：one DOM task template、controls one seed、two proposals、one training seed、confirmation pilot-sized not power guarantee。

这三件事说明：**它对自己能主张的边界，比我们上一版的转述更克制。** 我们的反思首先要承认这一点。

---

## 2. RSI-Anything 的三层机器

### 2.1 任务层：预测只排序，反馈才学习

代码修复的每一轮是：

```text
当前程序 + 公共测试反馈
  → 策略生成 4 个候选
  → 世界模型给 5 个对象打分（4 候选 + keep_current）
  → choose() 选 utility 最高者；若不超过 incumbent，保留当前
  → 执行公共测试，得到真实反馈
  → 进入下一轮（最多 3 轮）
```

对应代码：

- `tasks/code_repair/src/evaluation.py:27-34`：`choose()` 要求 5 个预测，`best` 只在 4 个候选中选，且必须严格大于 incumbent 的第 5 个 utility，否则返回 `4`（keep current）。
- `tasks/code_repair/src/evaluation.py:44-57`：`Predictor.predict()` 只把 public observations 给模型，预测 utility、full-suite pass probability、predicted pass fraction。
- `tasks/code_repair/src/evaluation.py:93-122`：每步生成候选、预测、选择、真实执行，写入 `trace`；`optimizer_steps=0`、`hidden_tests_accessed=False`。
- `tasks/code_repair/src/evaluation.py:133-161`：`seal_public()` 逐条重放 trace，校验候选数、incumbent、选择索引与最终代码，写 `public_seal.json`。
- `tasks/code_repair/src/evaluation.py:164-210`：`judge()` 在 seal 之后才读 hidden tests，最后重新校验 public 文件哈希，并写 `all_decisions_sealed_before_hidden_judge=True`。

**关键点**：预测不是证据。预测只决定“先评估谁/选谁”；真正的成功与否由执行反馈和 hidden judge 决定。这一点我们上一版写对了，但只停在原则层，没有把**校准**写进 EV0。

### 2.2 运行层：run identity 是“可恢复”的前提

`src/rsi_anything/workflow/runner.py` 的核心契约：

| 契约 | 代码位置 | 做什么 | 为什么重要 |
| --- | --- | --- | --- |
| Run identity | `runner.py:86-90` | `digest(config + source_identity + plan.stages + plan.files)` | 换配置、换源码、换 stage 计划都不能悄悄 resume |
| 排他锁 | `runner.py:92-96` | `fcntl.flock(LOCK_EX \| LOCK_NB)` | 两个 runner 不能同时拥有同一个 run |
| Resume 校验 | `runner.py:97-108` | 比较 state.identity、config.json、渲染后的 task config | 防止“旧 run + 新配置”拼接 |
| Completed receipts | `runner.py:121-127` | 重算每个 completed stage 的 output hash | 产物被篡改后拒绝 resume |
| 失败重试归档 | `runner.py:144-151` | 把不完整输出移到 `attempts/<stage>/<attempt-1>` | 保留失败证据，不覆盖 |
| Expected artifacts | `runner.py:161-166` | 每个 stage 必须产生声明的文件/目录，目录递归哈希 | “进程退出 0”不等于“产物完整” |
| 失败摘要 | `runner.py:173-182` | 写 `state.json`、`summary.json` 的 failed/interrupted 状态与错误 | 失败可查询，不靠日志猜 |
| 进程组清理 | `runner.py:45-59`、`62-75` | SIGTERM → 等待 → SIGKILL，`start_new_session=True` | 子进程不会变成孤儿 |

`config.py:76-92` 的 `source_identity()` 还做了一件容易被忽略的事：它不仅哈希 `src/`，还哈希 backend 的 `src/vendor/config/configs`，并明确把浏览器 HTML、脚本、样式和媒体算进去。注释写得很清楚：`# Browser HTML, scripts, styles and media also define task behavior.`

**但有一个边界**：`source_identity()` 不哈希 `options.assets` 指向的外部资产。外部资产的完整性由任务自己补：代码修复在 `protocol.json` 里记录 `asset_manifest_sha256`（`evaluation.py:295-298`），GUI 在 `base_manifest.json` 里哈希基座模型（`protocol.py:52-64`）。这说明：**通用 runner 的 identity 是“源码强、外部资产任务自补”**。我们的 E 层不能照抄这个边界，因为我们的外部输入更多（检索快照、prompt、模板、期刊规则、图表规格），必须在通用层就纳入。

### 2.3 保留层：不是一种 retain，而是四种

这是本轮最重要的发现。README 用“五域”叙事，但代码里的“retain”并不对称：

| 域 | 公开代码里 retain 什么 | 是否有完整更新回路 | 证据等级 | 不能怎么读 |
| --- | --- | --- | --- | --- |
| 代码修复 | 四段 world checkpoint：`initial → semantic → expanded → incumbent`；每段用上一段作 parent | 是：`tasks/code_repair.py:31-42` 串行训练，最后 evaluate | `[代码]` | 不是 claim 级技能保留；不是跨任务迁移 |
| GUI | 两代 `world+policy+controller` pair；promotion gate 后成为下一代 incumbent | 是：`rsi.py:15-60` 两代更新，`61-72` 冻结后 2×2 交叉测试 | `[代码]` | 不是通用 GUI 能力；只覆盖一个 DOM task template |
| 实验室规划 | 文档说“accepted pair becomes starting point for next round” | **公开代码只给冻结推理**：`infer.py world/select`；学习回路未随快照发布 | `[文档]` | 不能把文档里的五步学习当成可运行实现 |
| 反应优化 | 冻结的 ReactionT5–JEPA 先验；测量反馈只改下一次推荐 | **没有模型更新**；README 明确 “Predictions stay frozen during this loop” | `[文档]` | 这是 Bayesian optimization / active learning，不是 RSI |
| 免疫科学 | 无 | 无；README 只有 “Coming soon” | `[文档]` | 不能计入“已实现域” |

**判断**：RSI-Anything 的“五域”是**论文/项目叙事层**的覆盖，不是五条同等成熟的可运行 RSI 回路。真正有完整更新回路的是代码修复与 GUI；实验室规划是“文档描述 + 冻结推理”；反应优化是“冻结先验 + 顺序推荐”；免疫科学未发布。

这对我们有两层含义：

1. **不要用域数做能力对比。** 我们的矩阵应按“可运行/可复现/仅设计”分级，而不是按“覆盖几个领域”打勾。
2. **我们自己的“全链路”也必须这样标注。** 目前 P0–P8、EV1–EV4、租约/护照/撤销传播大多是设计 + SIM；不能因为 demo 里有界面，就当成已实现。

### 2.4 判定层：任务级判定做得很干净

GUI 的判定设计比代码修复更完整，值得单独拆开：

| 机制 | 代码位置 | 做法 | 对我们的意义 |
| --- | --- | --- | --- |
| 互斥 cohort | `protocol.py:6-13` | probe / initial / update / terminal_calibration / dev / diagnostic / test / confirmation / rsi_test / rsi_update1 / rsi_update2，seed 全部不相交 | C 层 cohort registry 的直接模板 |
| 先冻结再开测 | `protocol.py:38`、`rsi.py:57-60` | 两代 proposal 都训练/选择/冻结后，才写 `all_versions_frozen_before_test=True` | EV4 的 freeze-before-test 必须是硬门，不是口头约定 |
| 2×2 交叉 | `rsi.py:61-72` | old_old / old_new / new_old / new_new × selected/pure，再加 policy-only 测试 | 把 world 贡献与 policy 贡献分开；我们的 EV4 目前只有 with/without asset |
| Promotion gate | `rsi.py:53` | dev gain ≥ 0.04 且 effective_seconds ≤ 1.2× incumbent | 增益与相对成本必须同时过；阈值是任务配置，不是普适常数 |
| Conditional confirmation | `protocol.py:36`、`audit.py:262-266` | pilot mean gain ≥ 0.05 才跑 630-instance confirmation；否则不宣称 | 小 pilot 不能直接写 capability gain；需要预声明确认门槛 |
| 独立审计 | `audit.py:178-269` | 从 raw transitions 重算动作、链、谱系、校准、冻结时间、成本、promotion | 我们也需要“第二套实现”，不能只信 summary |
| Limits | `protocol.py:43` | one DOM task template、controls one seed、two proposals、one training seed、confirmation pilot-sized not power guarantee | 每个 capability card 都应有 `limits` 字段 |

**注意**：`all_decisions_sealed_before_hidden_judge=True` 是代码自己写进 summary 的布尔值，不是外部可信时间戳。它证明“在这个进程里，seal 先于 judge”，不证明“没有人可以在文件系统层篡改”。若要更强，需要外部锚定（见 §6.3）。

---

## 3. 它比我们强的地方

这一节只写“我们目前确实没有做到”的，不写“它做得一般”的。

### 3.1 执行契约：我们只有原则，它有测试

我们的 `04-` §2.14 有产物信封、ID、版本、失效传播；`07-` 有 RWVH、X0–X7、R/W/J；`09-` 有门禁与调度。但**没有一个可执行的 runner 契约**，也没有对应的测试。具体缺口：

| 我们需要但当前文档没有钉死的 | RSI-Anything 的做法 | 我们的后果 |
| --- | --- | --- |
| run identity 包含什么 | config + source + plan + rendered files | 换 prompt/模板/规则后可能误 resume |
| completed stage 如何验证 | 重算输出文件/目录哈希 | 产物被改后仍可能继续跑 |
| 失败重试如何保留证据 | `attempts/<stage>/<attempt-1>` | 失败输出被覆盖，无法复盘 |
| 外部资产如何纳入身份 | 任务自补 manifest；runner 不通用 | 检索快照/期刊规则变化可能不被发现 |
| plan 是否产生副作用 | `plan` 不建 run 目录、不 import ML | 评审无法先看计划再批准 |
| 锁与进程清理 | `flock` + 进程组 SIGTERM/SIGKILL | 并发 run 可能互相污染 |

这不是“工程细节”，而是 **EV1–EV4 的前提**：如果 run 本身不可恢复、不可验证，准入记录就没有可复核的底座。

### 3.2 保留的对象是“配对 incumbent”，不是单个技巧

GUI 的 promotion 不是“新 world 比旧 world 好就留下”，而是：

```text
old_world + old_policy + old_controller
  vs
new_world + new_policy + new_controller
```

`rsi.py:53` 用 dev 上的 success rate 与 effective_seconds 同时比较；`rsi.py:61-72` 再用 2×2 交叉把 world 与 policy 的贡献拆开。这比我们 EV2 目前的“资产相对 incumbent 有增益”更细：

- 我们的资产是 claim 级技能/工作流/策略；它可能依赖一个模型、一个检索器、一个模板。**只测资产整体，不拆组件，就无法知道增益来自哪一部分。**
- 我们的 EV4 目前是 with/without asset；这会把“资产 + 上下文 + 执行者”混在一起。RSI-Anything 的 2×2 是一个可借的归因模板。

### 3.3 判定卫生：cohort、校准、确认、拒绝报告

RSI-Anything 在 GUI 上做了四件我们文档里有、但没有钉成执行物的事：

1. **校准 cohort 独立**：`terminal_calibration` 50 个 seed，专门拟合 temperature/bias；`audit.py:166-176` 重算 Brier，并检查选中的校准就是预声明网格的最优。我们的 EV0 只写“记录校准”，没有写“校准集独立、指标、选择规则”。
2. **conditional confirmation**：pilot gain ≥ 0.05 才开 630-instance confirmation；`audit.py:262-266` 检查这个决定。我们的 EV4 没有两级确认，容易在小 pilot 上过度宣称。
3. **拒绝也报告**：`rsi.py:72` 写 `raw_rejected_candidates_reported=True`；controller gate 也保留 fallback。我们的候选账本有 `rejected`，但没有强制“所有被拒候选都进入报告”。
4. **no-update path**：GUI policy 训练在没有正样本时写 `not_updated.json`；`audit.py:246-261` 允许“没有更新”并检查它被记录。我们的 EV2 没有明确“本轮无准入”也是一等结果。

### 3.4 审计是第二套实现

`tasks/gui/src/rsi_anything_gui/audit.py` 不是“再跑一遍 summary”，而是从 raw transitions 重新计算：

- 动作是否合法、状态转移是否正确、budget 是否递减（`audit.py:21-38`）；
- expert continuation 链是否连续、return target 是否正确（`audit.py:40-48`）；
- episode 的 initial/final/termination 链是否一致（`audit.py:50-102`）；
- online counterfactual 是否在 acting rollout 完成后才收集、是否覆盖所有合法分支（`audit.py:114-129`）；
- world checkpoint 是否真的变了、训练数据是否来自允许的 cohort（`audit.py:143-164`）；
- calibration 是否用了独立 cohort、是否选了预声明最优（`audit.py:166-176`）；
- test 是否在 freeze 之后才开始（`audit.py:209-210`）；
- promotion gate 是否按 protocol 计算（`audit.py:226-228`、`241-244`）。

这给我们的直接启示：**我们的 Q1/核验层不能只做“覆盖率检查”，还要有一个独立的 raw-data auditor。** 否则 claim 与 summary 之间没有可验证的桥。

### 3.5 资产与许可证的 provenance

`docs/ASSET_CARD.md` 记录了：

- 资产内容：fixed public candidate/execution records、200 CodeContests judging tasks、reference decisions、four trained world-model checkpoints、development records、training transitions；
- 模型与 revision：Qwen2.5-Coder-3B-Instruct `488639f...`、ReasonFlux-Coder-7B `6860a2f...`；
- 数据来源与许可证：CodeContests、CC BY 4.0、Qwen Research License、Apache-2.0；
- 哈希与 `original_sha256` 的保留规则。

我们的资产卡还停在“来源 + 日期 + 核验等级”，没有到“每个可保留资产的 manifest + 许可证 + 输入哈希 + 适用范围”。这是 EV2 租约要用的底层材料。

### 3.6 可复现性的“最小完整”

`tests/test_workflow.py` 的 17 个测试里，有几条特别值得我们照抄成验收：

- `test_resume_detects_changed_stage_output`：改一个 completed 输出，resume 必须失败。
- `test_retry_archives_partial_output_and_preserves_completed_stage`：失败重试要把旧输出归档，且不能重跑已完成阶段。
- `test_success_exit_requires_expected_artifact`：进程退出 0 但缺产物，必须失败。
- `test_plan_runs_without_ml_imports_or_run_directory`：plan 不能建 run 目录、不能 import ML。
- `test_source_identity_includes_browser_assets`：改一个 HTML，source identity 必须变。
- `test_source_directory_cannot_be_run_root`：源码目录不能当 run root。
- `test_run_lock_refuses_second_owner`：同一 run 不能被两个 runner 拥有。
- `test_relative_settings_and_venv_symlink_preserved`：venv 的 symlink 不能被 resolve 掉。

这些测试的共同点：**它们测的是“失败的边界”，不是“成功的路径”。** 我们的验收也应该这样写。

---

## 4. 它没有解决、我们也不能假装它解决了的地方

### 4.1 保留对象仍是 checkpoint/pair，不是 claim 级资产

RSI-Anything 的 retain 单位是：

- 代码修复：`checkpoints/world/<stage>/joint_checkpoint`；
- GUI：`world + policy + controller` pair；
- 实验室规划：policy–world pair；
- 反应优化：没有 retain（冻结先验）。

它没有：

- `AdmissionRecord`：为什么接受、反事实、独立判定、异议；
- `InheritanceLease`：版本、谱系、范围哈希、依赖快照、有效期、复评周期、回滚指针；
- `ScopePassport`：任务族、数据条件、指标定义、前置条件、已知失败、迁移历史、安全边界；
- 撤销传播：asset revoked → runs → claims → sentences/figures → export fail-closed；
- 句子级证据槽：claim 绑定到具体句/图，而不是任务分数。

所以正确的说法是：**它把“任务级准入”做得很好；它没有把“准入后的科学记录”做成对象。** 这两句话必须同时说。

### 4.2 没有租约、到期、复评与回滚

RSI-Anything 的“回滚”是隐式的：如果新 pair 没有过 promotion gate，就继续用 incumbent。它没有：

- 到期时间；
- 复评触发（依赖变化、范围漂移、冲突证据）；
- `probation` 状态；
- 显式回滚到某个 stable 版本；
- 撤销后的下游影响闭包。

我们的 `11-` 设计了这些，但**仍是设计**。深读之后更要克制：不能因为对方没有，就说我们的设计已经成立；只能说“这是一个没有被对方覆盖的对象，值得做，也必须用 E/C/A 层去验证”。

### 4.3 没有依赖图与失效传播

RSI-Anything 的 checkpoint 有 parent 链（`--parent`），但那是**训练谱系**，不是**证据依赖图**。它不能回答：

- 这个资产被哪些 run 使用？
- 哪些 claim 依赖它？
- 哪些句子/图引用了这些 claim？
- 撤销后哪些内容必须重跑/重写/阻断导出？

我们的 `11-` 设计了 `used_by_runs → result claims → sentences/figures → stale/rerun/rewrite → export fail-closed`，但 demo 里的撤销只是 SIM 状态变化，不是真实图谱传播。**深读后的判断：这条差异仍然成立，但必须用 V5 端到端验证，否则只是概念图。**

### 4.4 没有稿件证据闭合

RSI-Anything 的最终产物是任务结果、checkpoint、benchmark summary。它没有：

- claim 类型（事实/数字/因果/比较/方法）；
- claim–evidence–span 三角；
- 句/图槽位；
- 引用与数字的重跑绑定；
- 中文核刊体裁、GB/T 7714、AI 使用披露；
- 导出硬门。

这是我们的主战场，但也意味着：**我们不能用 RSI-Anything 的 hidden judge 来类比我们的稿件判定。** 它的 judge 判任务成功；我们的 Q1 判“这句话能不能带着证据出门”。两者的对象、误差、责任都不同。

### 4.5 没有人类签核

RSI-Anything 的 promotion 是自动的：dev gate 过了就替换 incumbent。它没有“人类批准”这一步。

我们的 A3 边界要求：机器负责检索、收敛、设计草稿、起草、图表、核验、修订；人类保留科学决策、实验安全、署名与最终责任。因此：

- 我们不能照抄“自动 promotion”；
- 租约的授予、远域迁移、撤销后的对外处置，必须有人类签核；
- 人类签核本身也要有记录（谁、何时、看了什么、附了什么异议）。

### 4.6 领域不对称：五域不是五条同等回路

见 §2.3。这里只补一句：**RSI-Anything 自己的 README 用“五域”讲框架，但公开代码只让两域完整可跑。** 这不是指责；这是提醒我们：

- 我们的能力矩阵也要区分“代码可运行 / 文档描述 / 设计目标 / SIM 演示”；
- 我们的“全流程”不能因为画了 P0–P8，就当成八段都已实现；
- 我们的论文/需求书里，凡是没有跑过的，都要标 `[设计]` 或 `[SIM]`。

### 4.7 证据窄：一个 DOM 模板、100 个实例、一个训练 seed

`protocol.py:43` 自己写了 limits：

- one DOM task template；
- controls one seed；
- RSI two proposals from incumbent, one training seed；
- conditional confirmation pilot-sized, not power guarantee。

`docs/benchmarks.md:34` 也写明 MiniWoB++ 是同一个 `click-checkboxes` 模板、100 个测试实例、120 秒/8 动作上限。所以：

- 99% 是这个模板上的结果，不是“通用 GUI 能力”；
- 39.4% 动作减少是相对初始 controller，不是相对人类；
- OSWorld 的 +18.4% 是相对初始 Agent 的相对增益，不是绝对成功率。

我们引用时只能引用“作者报告了什么”，不能引用“它证明了什么”。

### 4.8 seal 是进程内不变量，不是外部证明

`evaluation.py:160` 写 `public_seal.json`，`evaluation.py:207` 写 `all_decisions_sealed_before_hidden_judge=True`，`evaluation.py:196-197` 在 judge 后重新校验 public 文件哈希。这能防止**同一进程内的代码路径**在 judge 后改 public 文件，但不能防止：

- 有人在 seal 之前就看过 hidden tests；
- 有人在文件系统层替换 `public_seal.json`；
- 有人在另一个进程里改 public 文件后重算哈希。

所以它是“工程不变量”，不是“密码学证明”。我们若要更强，需要：

- 外部时间戳/不可变存储；
- 或者把 `seal_hash` 写进一个人类签核的记录，并在导出时重新校验；
- 或者用 append-only 事件日志 + 定期锚定。

### 4.9 没有假接受/假拒绝审计

RSI-Anything 有 promotion gate，但没有：

- 假接受率 / 假拒绝率的抽样审计；
- 被拒候选的后续追踪（后来是否被证明更好）；
- 探索配额（防止只选保守候选）；
- 人类-系统判定一致性（κ）。

这些是我们在 `11-` 里提到的 anti-Goodhart 机制，但还没有实现。深读后要承认：**对方没有，不等于我们有；我们只是设计上有。**

---

## 5. 对上一版设计的反思：哪里写弱了

### 5.1 只借“点”，没借“面”

上一版 §1.2 借了三件事：EV0、incumbent guard、seal + cohort。这三件都对，但都是**任务层的点**。我们漏了：

- **执行契约这个面**：没有它，EV0–EV4 的记录不可恢复、不可验证；
- **交叉/条件确认这个面**：没有它，EV4 的“能力增益”无法归因，也无法防止小 pilot 过度宣称。

所以 v0.2 的“三件事”应升级为 **“三机制 + 两平面”**：

| 层 | 借什么 | 落到哪里 |
| --- | --- | --- |
| 机制 | EV0 预测预筛 | `11-` §3.0；新增校准与 fallback |
| 机制 | incumbent guard | `11-` §3.2.6；扩展为 pair/asset 双 guard |
| 机制 | seal + cohort | `11-` §3.4.6；扩展为 freeze-before-test + 独立审计 |
| 平面 | 执行契约 | 新增 E1–E8；接 `07-` RWVH 与 `09-` 调度 |
| 平面 | 交叉/条件确认 | 新增 EV4 的 2×2 与 conditional confirmation |

### 5.2 EV0 太抽象：没有校准、没有 fallback、没有 trace schema

上一版 EV0 写“预测只排序，不作证据”，这是对的，但不够。缺：

- 校准集：用哪个 cohort？多少样本？指标是 Brier、ECE 还是 log loss？
- fallback：预测不可用时，是否回退到 incumbent / 规则 / 人类？
- trace：每次预测的输入哈希、模型版本、预测值、真实值、选择结果、是否被 guard 拦截；
- 校准失败的处理：如果 Brier 比基线差，EV0 还能不能用？
- 预测与真实的偏差如何进入下一轮（不是当证据，而是当“预测器是否可信”的信号）。

RSI-Anything 的做法：

- `development.py:36-37` 计算 `full_suite_probability_brier`；
- `incumbent.py:27-33` 用预测 utility 做 per-decision guard；
- GUI `protocol.py:29-30` 在独立 `terminal_calibration` cohort 上选 temperature/bias；
- `audit.py:166-176` 重算 Brier 并检查选中校准是最优。

我们应把 EV0 写成：

```text
EV0 输入：候选 + 当前 incumbent + 预测器版本 + 校准集版本
EV0 输出：排序、预测值、置信区间/校准参数、fallback 决策
EV0 证据：只进入 PredictionTrace，不进入 because[]
EV0 失败：Brier/ECE 不达标 → 降级为 heuristic；不得用于预算分配之外的任何决策
```

### 5.3 EV2 只讲租约，没讲“配对 incumbent”和“no-update”

上一版 EV2 的租约设计是完整的（版本、谱系、范围、依赖、有效期、复评、回滚），但缺三块：

1. **配对 incumbent**：资产不是孤立对象。它可能依赖一个模型、一个检索器、一个模板。只测资产整体，无法知道增益来自哪里。应借 GUI 的 2×2：旧/新资产 × 旧/新上下文（或旧/新模型）。
2. **no-update path**：如果本轮没有候选过门，必须记录“本轮无准入”，保留 incumbent。不能为了“有产出”而降低门槛。
3. **成本条款**：租约不仅要写“有效期”，还要写“相对 incumbent 的成本上限”。RSI-Anything 用 `effective_seconds ≤ 1.2× incumbent`；我们的成本应包括 token、检索、人工审阅、复评成本。

### 5.4 EV4 只讲留出集，没讲 freeze-before-test、2×2、conditional confirmation

上一版 EV4 有“冻结留出集、with/without、独立 judge、成本调整、区间/等价检验”，方向对，但缺执行细节：

- **freeze-before-test**：候选、判据、排序、预算、校准参数都要在开测前冻结；记录 `seal_hash` 与时间；
- **2×2 交叉**：旧/新资产 × 旧/新上下文，分离主效应与交互；
- **conditional confirmation**：pilot 过小阈值后，用预声明的 confirmation cohort 复核；只有 confirmation 过，才写 capability gain；
- **rejected report**：所有被拒候选都要报告，包括“后来看起来更好”的；
- **cost gate**：增益必须相对 incumbent 成本；不能让“多花 4 倍成本”的资产过门；
- **no hidden world/policy**：如果 fallback 到 policy，必须证明没有偷偷用 world（`audit.py:97` 的做法）。

### 5.5 我们的“可复现”停在文档层

`04-` 有产物信封，`07-` 有 RWVH，`09-` 有门禁，但：

- 没有 run identity 的字段定义；
- 没有 stage receipt 的 schema；
- 没有 attempts 归档规则；
- 没有 source identity 的“外部输入”清单；
- 没有 plan dry-run；
- 没有跨平台锁（RSI-Anything 用 `fcntl`，Windows 不适用）；
- 没有“进程退出 0 但缺产物”的失败规则。

这些不是“实现细节”，而是 **EV 记录的物理基础**。没有它们，`AdmissionRecord` 只是一个 JSON，无法证明它对应的 run 没有被改过。

### 5.6 我们之前把“五域”当成了同等证据

上一版 §1.9 写“领域覆盖代码修复、GUI、实验室规划、反应优化与免疫科学”，这是 README 口径。深读后应改为：

| 域 | 公开代码状态 | 我们能怎么用 |
| --- | --- | --- |
| 代码修复 | 完整训练 + 评测 | 借四段 checkpoint 链、5 候选 choose、seal |
| GUI | 完整训练 + 评测 | 借 cohort、2×2、conditional confirmation、audit |
| 实验室规划 | 冻结推理 | 只借“pair retain”的文档思路，不当已实现 |
| 反应优化 | 冻结先验 + 顺序推荐 | 借“测量反馈改变下一次推荐”，不叫 RSI |
| 免疫科学 | 未发布 | 不引用为工程证据 |

这也是我们对自己文档的要求：**能力矩阵要按证据等级，不按域数。**

### 5.7 我们的差异表述需要收窄

上一版说“RSI-Anything 停在任务层，我们做 claim 级准入”。这句话本身对，但容易被误读为“它没有准入/没有审计”。正确的表述是：

> RSI-Anything 已经把**任务级准入**做得相当扎实：prediction-guided selection、incumbent guard、public seal、cohort 隔离、promotion gate、独立 audit。它没有做的是**把准入结果变成 claim 级、可租约、可撤销、可写进稿件的资产**。我们的增量在后者，不在“再加一个 evaluator”。

---

## 6. 设计修订：E 层、C 层、A 层

这一节是本文的可执行部分。原则：**不新增一条线性主链，只给现有 P0–P8 / EV1–EV4 加三个支撑层。**

### 6.1 E 层：执行契约（E1–E8）

| ID | 契约 | 最小字段 | 验收 |
| --- | --- | --- | --- |
| E1 | Run identity | `run_id`, `recipe_hash`, `source_hash`, `plan_hash`, `external_inputs_hash` | 改任一输入，resume 必须失败 |
| E2 | Source identity | code + prompts + templates + retrieval snapshots + journal rules + figure specs | 改一个 prompt/规则，identity 必须变 |
| E3 | Stage receipt | `stage`, `attempt`, `status`, `started_at`, `finished_at`, `expected[]`, `outputs{path:hash}`, `log` | 缺产物或哈希不符，stage 失败 |
| E4 | Resume / attempts | completed 跳过前重算哈希；不完整输出移到 `attempts/<stage>/<n>`；foreign dir 拒绝 | 篡改输出/覆盖 run/并发 run 都必须失败 |
| E5 | Transactional commit | 每个 claim/sentence/figure 原子写；`identity_hash`；断点续跑按 item 跳过 | 中断后不重复、不丢条目 |
| E6 | Plan dry-run | 打印 stages、命令、cwd、env、resolved paths；不建 run、不 import ML | `plan` 无副作用 |
| E7 | Cost ledger | `policy_tokens`, `retrieval_calls`, `world_calls`, `human_minutes`, `effective_cost` | 成本可归因到 stage/asset |
| E8 | No-update path | `no_candidate`, `no_positive`, `guard_blocked`, `cost_blocked` | 无准入时保留 incumbent，记录原因 |

**E 层的最小实现范围**：只覆盖“要进入证据图谱”的 P3–P8 运行，不覆盖所有探索性草稿。探索性运行可以轻量，但不能冒充证据运行。

**跨平台注意**：RSI-Anything 的 `fcntl.flock` 是 POSIX；如果我们的开发/演示环境有 Windows，需要 `msvcrt`/`portalocker` 或统一在 WSL/Linux 跑。不要把“Linux 能跑”当成“跨平台”。

### 6.2 C 层：cohort registry（C1–C7）

| ID | Cohort | 用途 | 是否可进入证据 |
| --- | --- | --- | --- |
| C1 | probe | 环境/工具/浏览器/API 预检 | 否，排除 |
| C2 | update | 产生候选、训练/更新资产 | 否，只用于学习 |
| C3 | calibration | 预测器/判定器的校准 | 否，只用于校准 |
| C4 | development / admission | 候选比较、pilot、EV1–EV2 | 可进入准入记录，不可进入最终 test |
| C5 | confirmation | pilot 过门后的放大确认 | 可进入能力结论，但需预声明 |
| C6 | test / held-out | 冻结后一次性开测 | 可进入最终结论 |
| C7 | transfer | 近域/远域/对抗迁移 | 可进入护照，不可回流训练 |

规则：

- 所有 cohort 的实例/seed 必须互斥；C1 永远排除。
- C6 只在 freeze-before-test 之后打开；打开时间写入 receipt。
- C5 的阈值、样本量、指标必须在 pilot 之前声明。
- 任何 cohort 的复用都要写 `reuse_reason`，否则 audit 失败。

RSI-Anything 的 11 个 cohort 是直接模板（`protocol.py:6-13`）。我们不需要 11 个，但至少要有 C1–C7 这七类。

### 6.3 A 层：独立审计（A1–A6）

| ID | 审计 | 输入 | 失败意味着 |
| --- | --- | --- | --- |
| A1 | Raw-data recomputation | run records、transitions、claims、sentences | summary 与 raw 不一致，claim 不可导出 |
| A2 | Seal / freeze verification | seal_hash、freeze_time、test_start_time | 先看结果后冻结，结论作废 |
| A3 | Cohort overlap check | cohort registry、实际使用的 seed/实例 | 数据泄漏，结论作废 |
| A4 | Lineage check | asset → run → claim → sentence/figure | 依赖不明，claim 不可导出 |
| A5 | Cost check | cost ledger、fallback 记录 | 成本超门或偷偷用模型，capability gain 不成立 |
| A6 | Rejected / no-update report | candidate ledger、no-update records | 幸存者偏差，候选账本不完整 |

**A 层必须是第二套实现**，不能复用生成 claim 的同一段代码。RSI-Anything 的 `audit.py` 就是独立实现；我们可以用 Python 单独写一个 `audit/` 包，只读 raw JSON/JSONL，不 import 生成器。

**外部锚定**：如果我们要把 seal 说得比 RSI-Anything 更强，至少要做一件事：

- 把 `seal_hash` 写入一个 append-only 的事件日志；
- 在导出时重新计算并比对；
- 或者把 `seal_hash` 放进人类签核记录（谁、何时、看了哪个版本）。

否则不要用“不可篡改”这个词。

### 6.4 EV0 修订：预测器是“排序器”，不是“证据源”

新增 `PredictionTrace` 字段：

```json
{
  "trace_id": "PT-0007",
  "candidate_id": "CAND-0014",
  "predictor_version": "wm-2026-10-19",
  "calibration_id": "CAL-03",
  "inputs_hash": "...",
  "predicted_utility": 0.72,
  "predicted_interval": [0.61, 0.81],
  "incumbent_utility": 0.66,
  "guard": "passed",
  "selected": true,
  "observed_utility": 0.69,
  "brier": 0.031,
  "used_as": "ranking_only"
}
```

规则：

- `used_as` 只能是 `ranking_only` / `budget_allocation`；不能是 `admission_evidence`。
- 校准集独立（C3）；Brier/ECE 不达标 → 降级为 heuristic，不参与预算分配之外的决策。
- 预测器版本变化要写新 trace，不能覆盖旧 trace。
- 预测高但真实失败，要写 `prediction_miss`，进入下一轮校准，不进入 `because[]`。

### 6.5 EV2 修订：租约 + pair incumbent + no-update

在 `InheritanceLease` 增加：

- `incumbent_pair`: 资产 + 依赖的模型/检索器/模板版本；
- `cost_ratio_limit`: 相对 incumbent 的成本上限；
- `no_update_reason`: 无候选/无正样本/guard 拦截/成本拦截；
- `revalidation_trigger`: 依赖变化、范围漂移、冲突证据、到期；
- `rollback_pointer`: 上一个 stable 版本 + 回滚后的复评要求。

规则：

- 没有过门 → `no_update`，保留 incumbent，不写“本轮成功”。
- 过门但成本超限 → `cost_blocked`，不授予租约。
- 过门但只在一个近域 cohort 有效 → 租约 scope 只能是近域，不能写“通用”。

### 6.6 EV3 修订：护照要有 cohort 矩阵，不只是文字

`ScopePassport` 增加一张矩阵：

| 维度 | 近域 | 远域 | 对抗/边界 |
| --- | --- | --- | --- |
| 任务族 | C7-near | C7-far | C7-adv |
| 数据条件 | ... | ... | ... |
| 指标定义 | ... | ... | ... |
| 依赖版本 | ... | ... | ... |
| 结果 | 直接复用 / 先 pilot / 拒绝 | ... | ... |

规则：

- 护照不是“适用领域”一句话，而是**每个维度的证据等级 + 失败记录**。
- 负迁移必须写回护照；不能只写成功案例。
- 进入新任务时，三档判定（直接复用 / 先 pilot / 拒绝）要有理由码；理由码引用具体 cohort 结果。

### 6.7 EV4 修订：freeze-before-test + 2×2 + conditional confirmation

EV4 的执行顺序改为：

```text
1. 候选、判据、排序、预算、校准参数冻结 → seal_hash
2. pilot（C4）→ 过门？
3. 若 pilot gain ≥ 预声明阈值 → confirmation（C5）；否则不宣称
4. confirmation 过 → 打开 test（C6），记录 test_start_time
5. 2×2 交叉：旧/新资产 × 旧/新上下文（或旧/新模型）
6. 成本门：gain ≥ 阈值 且 effective_cost ≤ 1.0×/1.2× incumbent（按 scope 配置）
7. rejected report：所有候选（含被拒）都报告
8. audit A1–A6 通过 → 写 CapabilityDelta
```

规则：

- test 打开后不能再改候选/判据/排序；否则 audit A2 失败。
- 2×2 的交互项显著大于主效应 → 不能把增益归因给资产；只能写“在特定上下文组合下有效”。
- confirmation 未过 → 只能写“pilot 观察到候选增益”，不能写“能力提升”。
- 成本超门 → 不能写“更优”，只能写“在更高成本下有效”。

### 6.8 不照抄的清单

| 不照抄 | 原因 | 我们怎么做 |
| --- | --- | --- |
| 自动 promotion | A3 边界要求人类签核 | 机器提议，人类签核；签核记录入账 |
| checkpoint/pair 级 retain | 我们要 claim 级资产 | 保留 asset，不保留“模型即记忆” |
| 固定阈值 0.04 / 1.2× / 0.05 / 630 | 任务特定 | 写成按 scope 配置的模板，记录来源与生效日期 |
| 作者数字 | 未复现 | 只引用“作者报告了什么”，不当本项目结果 |
| “五域”等权 | 公开代码不对称 | 按“可运行/冻结推理/未发布”分级 |
| seal = 不可篡改 | 进程内不变量 | 加外部锚定或人类签核；否则不说“不可篡改” |
| 单 DOM 模板 = 通用 GUI | 证据窄 | 在 capability card 写 limits |
| 反应优化 = RSI | 模型冻结 | 叫“顺序实验设计/贝叶斯优化”，不叫 RSI |

---

## 7. 对现有文档与 demo 的改动清单

| 文档/模块 | 改什么 | 优先级 | 备注 |
| --- | --- | --- | --- |
| `12-`（本文） | 新增深读反思、E/C/A 层、V1–V7 | P0 | 已完成 |
| `10-` §1.9 | 加“v0.3 深读补正”：执行契约、四种 retain、五域不对称 | P0 | 指向本文 |
| `11-` §1.2 | 把“借三件事”升级为“三机制 + 两平面” | P0 | 指向本文 §6 |
| `11-` §3.0 | EV0 增加校准集、Brier/ECE、fallback、trace schema | P1 | 不改变“预测不作证据” |
| `11-` §3.2 | EV2 增加 pair incumbent、no-update、cost ratio | P1 | 租约字段扩展 |
| `11-` §3.4 | EV4 增加 freeze-before-test、2×2、conditional confirmation、rejected report | P1 | 与 `07-` RWVH 对接 |
| `04-` §2.14 | 产物信封增加 `run_id`、`stage_receipt`、`external_inputs_hash` | P1 | 不新增阶段 |
| `07-` RWVH | 增加 E1–E8 与 A1–A6 的验收项 | P1 | 与 X0–X7 合并 |
| `09-` 架构 | 增加 E/C/A 三个支撑层，不新增主链 | P2 | 放在“执行/审计”层 |
| `02-` §4.2.5–§4.2.6 | 增加本轮增量人周与优先级 | P2 | 见 §8 |
| `oss/README.md` | 补充执行契约、2×2、conditional confirmation、领域不对称 | P1 | 见 §9 |
| `demo/` | **暂不新增图表**；等 E1–E4 有真实 receipt 后，再把 SIM 的 prediction/seal 替换为真实记录 | P2 | 先补契约，再加 UI |

**关于 demo 的原则**：当前 demo 的资产租约控制台是“接口演示”，不是“实现证明”。在 E 层没有真实 run receipt 之前，继续加动画会放大“看起来像实现了”的风险。下一步如果要动 demo，应该加的是：

- 一个真实的 `run_id` / `stage_receipt` 面板（读本地 JSON，不造假数据）；
- 一个真实的 `calibration` 小面板（Brier/ECE + fallback）；
- 一个真实的 `freeze` 时间线（seal → confirmation → test）。

而不是再加一条模拟能力曲线。

---

## 8. 工作量与优先级

以下为**估算**（±30%），用于排序，不是报价；与 `07-` RWVH、`09-` Q1 有重叠。

| 工作包 | 内容 | 现有覆盖 | 增量人周 | 优先级 | 验收 |
| --- | --- | --- | ---: | --- | --- |
| E1–E4 runner | run identity、source identity、stage receipt、resume、attempts、lock | `07-` X0–X7 部分 | 4 | P0 | 移植/改写 8–10 个失败边界测试 |
| E5–E8 | 事务式提交、plan dry-run、cost ledger、no-update | `09-` 调度部分 | 2 | P1 | 断点续跑、成本归因、无准入记录 |
| C1–C7 | cohort registry、互斥检查、freeze 时间 | `09-` 门禁部分 | 2 | P1 | 7 类 cohort、无重叠、C6 冻结后开测 |
| A1–A6 | 独立 auditor、raw-data 重算、seal/cohort/lineage/cost/rejected 检查 | `09-` Q1 部分 | 4 | P0 | auditor 与生成器分离；篡改/泄漏/先看后冻必须失败 |
| EV0 校准 | 独立校准集、Brier/ECE、fallback、trace schema | `11-` §3.0 | 1.5 | P1 | 校准不达标自动降级 |
| EV2/EV4 归因 | pair incumbent、2×2、conditional confirmation、cost gate | `11-` §3.2/§3.4 | 2.5 | P1 | 2×2 可分离主效应/交互；confirmation 未过不宣称 |
| provenance / limits | 资产卡、许可证、输入哈希、limits 字段 | `03-`/`oss-` 部分 | 1 | P2 | 每个可保留资产有 manifest + limits |
| **合计** |  |  | **17** |  | 其中约 8 人周与既有 RWVH/Q1 重叠，**净新增约 9 人周** |

**建议顺序**：

1. **P0（4–5 人周）**：E1–E4 + A1–A3。先把“run 可恢复、产物不可篡改、cohort 不泄漏、test 不先看”跑通。
2. **P1（4–5 人周）**：C1–C7 + EV0 校准 + EV4 freeze/2×2/confirmation。没有这些，EV4 的“能力增益”不能写。
3. **P2（2–3 人周）**：EV2 pair/cost/no-update、EV3 护照矩阵、provenance/limits。
4. **P3**：再接中文稿件槽、撤销传播与导出硬门；这些是主贡献，但必须站在 E/C/A 层上。

**不改变总盘口径**：`02-` §4.2.6 的 215/229 人周仍是原估算；本轮 17 人周是**新增执行层**的单列估算。若按净新增 9 人周计入，总盘约 **224/238** 人周；若 17 人周全部另立、不与 RWVH/Q1 合并，则约 **232/246** 人周。建议先做 P0，再决定是否扩到 P1/P2。

---

## 9. 可证伪的验证计划（V1–V7）

| ID | 验证 | 通过标准 | 失败意味着什么 |
| --- | --- | --- | --- |
| V1 | Runner 契约 | 改 completed 输出 → resume 失败；改 prompt/模板 → identity 变；并发 run → 第二个被锁；失败重试 → 旧输出归档；plan → 不建 run | E 层不成立；“可复现执行”不能宣称 |
| V2 | 预测校准 | 独立 C3 上 Brier/ECE 优于未校准基线；不达标时自动降级；预测 trace 可追溯到真实结果 | EV0 不能用于预算分配之外；只能当 heuristic |
| V3 | 2×2 归因 | 资产主效应可分离；交互项不吞掉主效应；成本门可计算 | EV4 不能把增益归因给资产；只能写“组合有效” |
| V4 | Freeze-before-test | test 在 freeze 前打开 → audit 失败；seal 后改候选/判据 → audit 失败 | 判定封存是装饰；EV4 结论作废 |
| V5 | 撤销传播 | 撤销 asset → 所有 used_by_runs/claims/sentences/figures 标 stale；导出阻断；回滚不自动清除 stale | 证据闭合不成立；“可撤销资产”不能宣称 |
| V6 | No-update path | 无候选过门 → 记录 no_update + 保留 incumbent；不得自动 promotion | 反 Goodhart 失败；“保守准入”不能宣称 |
| V7 | Rejected report | 所有候选（含被拒）进入报告；审计可查拒绝理由与后续结果 | 幸存者偏差；候选账本不完整 |

**V1 可以最先跑**：它不需要模型、不需要 GPU，只需要一个最小的 runner + 临时目录。RSI-Anything 的 17 个测试是现成的模板；我们可以用自己的 stage 语义重写，不必复制代码。

**V2–V4 需要一个小型任务**：建议用 `07-` 的 RWJT 小样本或一个合成任务，不要一上来就跑中文核刊全稿。**V5 需要证据图谱**：可以先用手工构造的 claim/sentence/figure 图，再逐步接自动生成。**V6/V7 只需要候选账本**，可以在任何 pilot 上跑。

---

## 10. 一句话总结

> **RSI-Anything 真正值得我们学的，不是“预测—选择—保留”这句口号，而是它把“运行可恢复、判定先冻结、候选都报告、审计可重算”做成了代码；我们真正要做的，不是再借一个机制，而是把这些工程契约接到 claim、句、图与导出，让“准入”成为科学记录的一部分。**

---

## 附录 A：E 层最小 schema

### A.1 `RunIdentity`

```json
{
  "run_id": "RUN-2026-10-19-001",
  "recipe_hash": "sha256:...",
  "source_hash": "sha256:...",
  "plan_hash": "sha256:...",
  "external_inputs_hash": "sha256:...",
  "created_at": "2026-10-19T10:00:00+08:00"
}
```

### A.2 `StageReceipt`

```json
{
  "run_id": "RUN-2026-10-19-001",
  "stage": "P6-verify",
  "attempt": 1,
  "status": "completed",
  "started_at": "...",
  "finished_at": "...",
  "expected": ["claims.jsonl", "audit.json"],
  "outputs": {
    "claims.jsonl": "sha256:...",
    "audit.json": "sha256:..."
  },
  "log": "logs/P6-verify.1.log"
}
```

### A.3 `CohortRegistry`

```json
{
  "registry_id": "COH-01",
  "cohorts": {
    "probe": {"ids": ["..."], "purpose": "environment", "evidence": false},
    "calibration": {"ids": ["..."], "purpose": "predictor_calibration", "evidence": false},
    "dev": {"ids": ["..."], "purpose": "admission", "evidence": true},
    "confirmation": {"ids": ["..."], "purpose": "capability_confirmation", "evidence": true},
    "test": {"ids": ["..."], "purpose": "heldout", "evidence": true}
  },
  "overlap_check": "pass",
  "frozen_at": "..."
}
```

### A.4 `AuditReport`

```json
{
  "audit_id": "AUD-0007",
  "run_id": "RUN-2026-10-19-001",
  "checks": {
    "raw_recomputation": "pass",
    "seal_freeze": "pass",
    "cohort_overlap": "pass",
    "lineage": "pass",
    "cost": "pass",
    "rejected_report": "pass"
  },
  "errors": [],
  "auditor_version": "audit-0.1",
  "created_at": "..."
}
```

---

## 附录 B：RSI-Anything 代码入口 → 我们的设计映射

| RSI-Anything | 行号/位置 | 我们借什么 | 落到哪里 |
| --- | --- | --- | --- |
| `runner.py` run identity | 86–90 | E1 | §6.1 |
| `runner.py` lock | 92–96 | E4 | §6.1 |
| `runner.py` receipts | 121–127、161–166 | E3 | §6.1 |
| `runner.py` attempts | 144–151 | E4 | §6.1 |
| `config.py` source identity | 76–92 | E2 | §6.1 |
| `evaluation.py` choose | 27–34 | incumbent guard | §6.4/§6.5 |
| `evaluation.py` seal | 133–161、196–207 | freeze-before-test | §6.7 |
| `development.py` Brier | 36–37 | EV0 calibration | §6.4 |
| `rsi.py` promotion gate | 53 | cost/gain gate | §6.7 |
| `rsi.py` 2×2 | 61–72 | crossed attribution | §6.7 |
| `protocol.py` cohorts | 6–13 | C1–C7 | §6.2 |
| `protocol.py` limits | 43 | limits card | §6.8 |
| `audit.py` raw audit | 178–269 | A1–A6 | §6.3 |
| `experiment.py` transactional | 82–106 | E5 | §6.1 |
| `tests/test_workflow.py` | 38–190 | V1 | §9 |

---

## 附录 C：宣称边界

**可以说**：

- “我们设计了一个 claim 级资产准入层：租约、护照、撤销传播与导出硬门。”
- “我们借用了 RSI-Anything 的任务级执行契约与交叉/条件确认思路，并把它扩展到科研证据链。”
- “RSI-Anything 的公开代码在代码修复与 GUI 上有完整更新回路；实验室规划与反应优化在快照中是冻结推理；免疫科学未发布。”
- “我们尚未运行 E1–E8 / C1–C7 / A1–A6；目前只有设计与 SIM。”

**不能说**：

- “RSI-Anything 没有准入/没有审计。”——它有任务级准入和独立审计。
- “我们的系统已经会自进化。”——没有跑过 E7/E8，demo 是 SIM。
- “我们的方法比 RSI-Anything 更强/更有效。”——没有同协议对比，也没有复现。
- “五域都验证了。”——公开代码不对称，不能按 README 域数计分。
- “seal 不可篡改。”——进程内不变量，不是密码学证明。
- “CodeContests 31.2% / APPS 46.37% 等是我们的结果。”——作者口径，未复现。

**需要补证据才能说**：

- “我们的 E 层可复现”：需要 V1 通过。
- “我们的 EV0 校准有效”：需要 V2 通过。
- “我们的资产有可归因增益”：需要 V3 + V4 通过。
- “我们的撤销传播成立”：需要 V5 通过。
- “我们的准入能防 Goodhart”：需要 V6 + V7 通过。

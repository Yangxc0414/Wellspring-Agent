# 81-ESE研究智能体设计：从 MathRSI 的三层架构到经验软件工程的证据循环

> 状态基线：2026-11-18。定位：**设计提案 + 可运行原型**（`prototypes/ese/`，未注册），不是生产实现。
> 参照：`math-rsi-main/`（MathRSI v6）、本仓 `research-agent`、发行仓 `Wellspring-Agent/`。
> 边界：本文不修改 00–80 号设计文档，不新增生产模块，不改门禁/Claim/签名；演示中的效应量、区间与样本数均为示意，不是实证结果。
> 配套：`design/82-` 回答 demo 叙事与图如何与本文一致（内层证据闭合 / 外层方法演化）；原型见 `prototypes/ese/`（52 测试）。

---

## 0. 结论先行

1. **MathRSI 真正可迁移的不是"五阶段"或"三层"这些名词，而是四个机制**：义务驱动、局部返回点、能力边界声明、失败即资产；外加一个独立的、由真实研究证据驱动的 `meta-evolve`。没有这四件事，三层架构只是目录结构。
2. **ESE 不能照搬"证明检查"作为终审。** 数学的终审是证明检查器/证书/Lean；ESE 的终审是**设计有效性 + 统计不确定性 + 独立复现 + 适用域**四件事，不存在单一 PASS。把 ESE 塞进"证明通过/不通过"的二元语义，会制造虚假的确定性。
3. **建议的内核是一句话**：一条断言 × 三条轴 × 五阶段 × 五类威胁 × 两类失败 × 二维插件。它只定义语义，不新增门禁、不创建 Claim、不签名。
4. **现有仓库最强的 ESE 资产是 `study` 的预注册/区间门/复现计数；最弱的是实验 claim 的点证据、无失败图谱、无插件、无方法指纹、RSI 只优化检索代理。** 不要重写统计引擎，要"收束 + 补语义"。
5. **元演化必须独立、慢、可回滚。** 没有 held-out 研究任务与人工理由的"版本号"不是 RSI，只是改名。

一句话概括本设计：**把 MathRSI 的研究判断力，接到本仓已有的证据闭合与人工门上；用 ESE 的三轴、威胁与失败分类替换数学的证明/反例语义。**

---

## 1. 任务边界：ESE 研究智能体是什么、不是什么

### 1.1 是什么

面向**经验软件工程（Empirical Software Engineering）**的研究智能体，帮助研究者完成四件事：

1. **把模糊的 SE 问题变成可检验断言**：构念、操作化、population、comparison、metric、threshold、scope、五类效度威胁。
2. **在大实验之前杀死坏研究**：用最便宜、最可能致命的威胁探针，决定"继续/改设计/改规格/停止"。
3. **让结论可复现、可复用**：区间与效应量、独立复现、适用域、失效条件；把 durable 失败沉淀为下一次研究的输入。
4. **让框架随问题演进**：从真实失败中提炼方法/插件/检查项，经 held-out 任务与人工理由后才进入下一版。

### 1.2 不是什么

- 不是"自动写论文"：写作是证据的投影，不是证据本身。
- 不是"LLM 自评自签"：LLM 可以提议、可以当审稿人，但不能当统计判定器，也不能签名。
- 不是"把 GitHub 项目跑一遍就叫实证"：没有设计、没有威胁分析、没有区间与复现，只是运行日志。
- 不是"加更多门禁"：门禁解决"谁有权说完成"，不解决"这个结论是否有效"。
- 不是"把数学证明流程改个名字"：ESE 的证据是概率性的、情境依赖的、可被新数据推翻的。

### 1.3 三类用户价值

| 用户痛点 | 智能体应提供的价值 | 失败样子 |
| --- | --- | --- |
| 不知道这个 SE 问题能不能做 | 规格化 + 最难关口探针 + 功效/数据可行性 | 直接开跑，三个月后才发现数据不够 |
| 跑完不知道结论能不能信 | 三轴状态 + 区间门 + 效度威胁清单 | 用一个点估计写"显著提升" |
| 做完不知道下次怎么复用 | 失败图谱 + 数据集坑 + 协议卡 + 查询包 | 每次都从零踩同一个坑 |

---

## 2. MathRSI 拆解：名词之下的机制

### 2.1 三层各自解决什么

| 层 | 内容 | 解决的问题 | 在本仓的对应物 |
| --- | --- | --- | --- |
| **Base** | 五个子工作流：prepare → route-loop → prove → verify → handoff | 研究怎么推进、何时回流、何时停止 | `pipeline.py` 的 S0–S16 + 各模块 |
| **Domain Plugins** | 领域知识、归约、检查器、失败图谱、精确条件 | 领域方法从哪来、核验到什么范围 | 基本没有（modules 是阶段，不是领域插件） |
| **Workspace** | 单题 `FORMAL_SPEC` / `NEXT_SESSION` / wiki / proof / verification | 长程研究怎么恢复、怎么不重做 | `project/` + run artifacts（但无失败图谱） |

MathRSI 的关键不在"分了三层"，而在**每层的产物被下一层实际消费**：插件返回原调用点，workspace 的 wiki 在派发前被读、在结果回收后被写，Base 的阶段调度者只有一个。

### 2.2 五阶段不是流水线

`mathrsi-research` 的入口不是"从头跑五个阶段"，而是按已有产物选择起点：

- 已有规格/调查 → 直接 route-loop；
- 在途证明 → 直接 prove；
- 完整候选 → 直接 verify；
- 只缺交付 → 直接 handoff。

更关键的是**局部返回点**：

- verify 发现实质数学缺口 → 回 prove；
- prove 发现路线假设被击穿 → 回 route-loop；
- route-loop/prove 缺文献进口 → 回 survey，拿到原文条件后回**同一义务**；
- 插件只执行当前 scope，返回调用者，不自己启动下一阶段。

这使流程是**图**而不是**链**：每次返回都带着具体证据和新条件，而不是"重跑一遍"。

### 2.3 四个可迁移机制

| 机制 | MathRSI 的做法 | 为什么有效 | ESE 的对应物 |
| --- | --- | --- | --- |
| **义务驱动** | 每个行动写清"当前缺什么、输入是什么、产物怎样改变整体证明" | 进度用"闭合了什么义务"衡量，不用文件数/阶段名 | 每条 claim 的未闭义务：威胁未缓解、功效不足、复现未做、范围未定 |
| **局部返回点** | verify→prove→route-loop→survey，回到原义务 | 失败不是终止，是带证据的转向 | 分析发现效度问题 → 回设计；执行发现数据不可用 → 回设计；构念错配 → 回规格 |
| **能力边界声明** | 每个插件必须写 `cannot_support` | 结构性防止过度宣称，而不是靠提示词 | 每个方法/任务插件声明"不能支持什么"（因果、跨生态、实时预测……） |
| **失败即资产** | 失败图谱 + 重试条件 + 适用范围；anti-self-poisoning 区分环境失败与数学失败 | 失败可复用，但不会把一次限流写成"此路不通" | durable/operational 分类；失败图谱永不裁剪；重试条件与 scope |

### 2.4 `meta-evolve` 的真实含义

MathRSI 的 `mathrsi-meta-evolve` 不是"第六个解题阶段"，而是**独立的外层维护工作流**：

1. 从真实研究交接包/失败/用户反馈中取证；
2. 判断经验属于 base、领域插件、单题状态，还是**暂不采用**；
3. 原位修改现有版本，接实际 caller 与消费方；
4. 做针对性跨模型讨论；
5. 协调者**自己实际使用**修改后的内容；
6. 记录版本、采用/暂缓、未测范围，固定 tag 保留历史快照。

这解释了为什么 MathRSI 能讲 v0→v6 而不显得空洞：每一版都有**具体研究来源、具体改动、实际使用范围**，并且明确"没有由新版重做就不写成新版解题率"。

### 2.5 MathRSI 自己也不能照搬的地方

- **它有证明/证书作为最终真值来源**（至少是部分义务）。ESE 没有这种 oracle。
- **它的插件按数学分支切分**，方法与对象强耦合。ESE 的方法与任务可分离：同一个"缺陷预测"可以用挖掘、基准评测、受控实验研究。
- **它的失败多是数学失败**（反例、证明漏洞），边界相对清楚。ESE 的失败常是"设计 flaw / 功效不足 / 污染 / 真零效应"的混合，必须先分类。
- **它的记忆是单题 wiki**，不是跨项目的经验库。ESE 需要跨项目的失败模式、数据集坑、基准漂移。
- **它的 meta-evolve 由有领域判断的维护者执行**。把它自动化成"agent 自己改自己"，会迅速退化成 benchmark 过拟合。
- **它的 prose 很重、机器可检性弱**。产品化需要薄内核 + 可测试的契约，而不是把所有判断写进提示词。

---

## 3. 八个不对称：为什么 ESE 需要不同的内核

| 维度 | 数学 | 经验软件工程 | 设计后果 |
| --- | --- | --- | --- |
| **真值来源** | 证明检查、证书、Lean、反例 | 统计设计 + 独立复现 + 适用域 | 不能有单一 `verified=true`；必须是三轴 |
| **证据形态** | 演绎、全称、可机检 | 概率、抽样、情境依赖、可被新数据推翻 | 必须带区间、效应量、scope、失效条件 |
| **失败语义** | 反例/漏洞，边界清楚 | 设计 flaw / underpowered / 污染 / 泄漏 / 真零效应 | 先分类；operational 不得进图谱 |
| **"最难"在哪** | 最难余域/关键引理 | 最可能杀死断言的效度威胁/数据获取 | 最难关口探针，而不是最难引理 |
| **记忆单元** | 定理、引理、证明、反例 | 协议、数据集坑、失败模式、复现结果 | 单题 workspace + 跨项目 pattern |
| **方法与领域** | 强耦合（分支即方法） | 可分离（方法 × 任务） | 二维插件，而不是一维分支插件 |
| **复现** | 重放证明/重建 Lean | 独立数据/实现/分析者/时间窗 | 复现是独立轴，不是"再跑一次" |
| **人的角色** | 选路线、验收证明 | 设计、签核、伦理/隐私、解释 | 人门更多，但不能用门禁代替效度 |

一个直接推论：**MathRSI 的"五阶段"可以借，但"证明/验证"这一段的语义必须整体替换。** 在 ESE 里，`verify` 不是"检查证明对不对"，而是"检查设计是否支持这个结论、区间是否排除零、复现是否独立、范围是否被写清"。

---

## 4. 总体设计：Wellspring-ESE

![Wellspring-ESE 架构](../figures/ese/ese-architecture.png)

### 4.1 四层

| 层 | 名字 | 职责 | 不做什么 |
| --- | --- | --- | --- |
| **L1** | ESE Base | 五阶段研究闭环、最难关口探针、三轴判定、全局重评 | 不创建 Claim、不签名、不改门禁 |
| **L2** | Domain Plugins | 方法 × 任务 × 数据集卡；威胁立场、失败模式、核验器、报告规范 | 不签核、不改判据、不越权写 Claim |
| **L3** | Workspace Memory | 单题 claim/protocol/failure/dataset/decision/next-session；QueryPack | 不把摘要当证据、不裁剪失败 |
| **L4** | Meta-evolve | 从 durable 失败到框架版本；held-out 评估、人工采纳、回滚 | 不自动改 claim/evidence/gate/rubric/signature |

### 4.2 一条内核不变量

内核不认识"软件工程"或"数学"这些词。它只认：

```text
ClaimSpec × EvidenceAxis × ReproAxis × Scope
× Stage × ThreatKind × FailureKind × PluginManifest
```

领域语义全部由插件注入：数学插件提供归约/证书检查器；ESE 插件提供方法规范/统计核验/数据集卡。这样同一个 harness 可以挂不同领域，而不用改内核。

### 4.3 一条产品边界

- **LLM 提议**：生成 claim 草案、设计草案、分析脚本、审稿意见。
- **artifact 决定**：所有数值来自可复算的产物；LLM 不能写数值结论。
- **人签核**：claim、协议冻结、例外豁免、元演化采纳。
- **内核只读**：计算 blockers、状态、QueryPack、冲突报告；不写任何受门禁保护的产物。

---

## 5. ESE Base：五阶段与返回点

### 5.1 阶段表

| 阶段 | 输入 | 退出条件 | 产物 | 失败时回到 |
| --- | --- | --- | --- | --- |
| **Specify** | 研究问题、文献、数据线索 | 五类威胁齐全；scope 具体；threshold 有限；metric 可操作 | `ClaimSpec` + `DatasetCard` 草案 | 问题本身不清 → 人 |
| **Design** | ClaimSpec、数据/工具可行性 | 预注册四件套（采样/功效/分析/停止）非空；设计冻结；**最难关口探针通过** | `ProtocolCard` + probe 记录 | 探针失败 → Specify/Design |
| **Execute** | 冻结协议、环境 | run_id、数据/代码/环境指纹、原始输出齐全 | `StudyCapsule` + 原始 artifact | 操作失败 → Design |
| **Verify** | capsule、分析计划 | 证据轴已定；复现轴不是 not_attempted（或显式豁免）；范围/失效条件写清 | 分析报告 + 复现记录 + `VERIFICATION.md` | 效度问题 → Design；构念问题 → Specify |
| **Deposit** | 已签 claim、失败记录、数据集卡 | claim 三轴 + scope + 失效条件； durable 失败入图谱；NEXT_SESSION 更新 | Claim card + failure atlas + dataset card | 新 gap → 下一轮 Specify/Recon |

### 5.2 三轴：不得合并

| 轴 | 取值 | 回答的问题 | 常见误读 |
| --- | --- | --- | --- |
| **证据轴** | `supported` / `not_supported` / `undecidable` | 数据与统计是否支持断言原样（含幅度） | 把"点估计为正"读成 supported |
| **复现轴** | `reproduced` / `partial` / `failed` / `not_attempted` | 独立复现是否得到同向结果 | 把"再跑一次同一实验"读成复现 |
| **适用域轴** | 具体文本 | population × 语言 × 任务族 × 时间窗 × 工具版本 | 把"Java 开源项目"外推到"所有软件" |

一条断言可以是：**supported 且未复现、仅适用于 Java 开源项目、2015–2023**。这三个事实必须同时可见。把它们压成一个 `status`，就会在论文、评审、复现三个环节各丢一次信息。

未缓解威胁不是自动拒绝：它是必须被人写明的**残余风险**。签署前必须写清残余风险是什么、结论因此只能声称什么；空白不等于已缓解。

### 5.3 最难关口探针（hardest-threat probe）

MathRSI v6 的"最难余域预检"解决的是：易分支都通过了，但最难的核心没动，团队误以为在推进。ESE 的对应问题是：**主实验跑得很顺，但最可能杀死结论的那个威胁从未被测试。**

设计冻结前，必须至少跑一个探针，并记录：

- `threat`：它针对五类威胁中的哪一类；
- `question`：它要回答的具体问题；
- `cheapest_test`：为什么它比主实验便宜；
- `result`：passed / failed / inconclusive；
- `evidence`：实际读数/观察；
- `cost`：时间、数据、算力。

示例：

| 威胁 | 探针 | 失败后的动作 |
| --- | --- | --- |
| Construct | 指标与人工标签/真实缺陷的一致性抽查 | 回 Specify 换操作化 |
| Internal | 泄漏探针：重复样本、时间切分、特征可用性、隐藏 fix diff | 回 Design 改数据/提示/切分 |
| External | 3 个项目/2 个语言的小型外部样本 | 回 Design 收窄 scope 或改抽样 |
| Conclusion | 功效计算 + 最小可检测效应 | 回 Design 加样本/改设计/降主张 |
| Reproducibility | 干净环境重建 + 哈希核对 | 回 Design 修环境/记录 |

规则是 fail-closed：

- 没有探针 → 不允许冻结设计；
- 任一 failed → 不允许，回到 Specify/Design；
- 任一 inconclusive → 停止扩批，先解决不确定性；
- 全部 passed → 允许，但仍要记录探针覆盖范围。

### 5.4 断言 vs 反例的协同演化

MathRSI v6 的 primal–dual coevolution 把"构造下界"与"寻找上界反例"分开，用残差导引搜索。ESE 的对应物是：

- **正向臂**：寻找支持断言的证据（更多项目、更强基线、更细分析）。
- **对抗臂**：寻找杀死断言的反例（泄漏、混杂、平凡基线、负对照、替代度量、时间漂移）。
- **四个通道轮换**：effect（效应）、threat（威胁）、novelty（新情境）、condition（边界条件）。
- **停止准则**：当表观增益小于测量噪声/区间宽度时停止，而不是继续"调参到显著"。

这不是把统计检验自动化，而是把**研究注意力**从"找更多支持"转向"找最可能推翻它的证据"。

### 5.5 全局重评

触发条件（与 MathRSI 对齐）：

- 同一瓶颈连续两批没有决策增量；
- 局部成果很多，但原 claim 的关键义务没有减少；
- 准备做一次未经评估的昂贵扩批；
- 到达预注册的检查点；
- 关键依据（数据版本、基线、模型）变化。

动作：由**非当前作者**的两位只读评审分别检查"claim 连接/效度"与"总成本/替代路线"；当前调度者读原始意见后，实际执行一个有界后继（继续/改设计/换路线/收束/停止）。不能用"模型同意"代替证据，也不能用"文件数"代替进展。

### 5.6 返回点与唯一调度者

- Verify → Design：效度威胁未缓解、区间太宽、复现失败。
- Execute → Design：数据不可用、环境失败、工具 bug（operational）。
- Verify → Specify：构念错配、操作化不成立。
- Deposit → Specify/Recon：新 gap、新数据集、新基线。
- 插件 → 原调用点：插件只做当前 scope，不自己启动下一阶段。

**唯一调度者**：同一时刻只有一个 agent 决定下一阶段；子 agent 返回产物与剩余，不自行启动同级阶段。否则会出现两个 agent 同时改设计/同时跑实验的重复与冲突。

---

## 6. Domain Plugins：方法 × 任务 + 数据集卡

### 6.1 为什么是二维，而不是按分支

数学插件按分支切分，是因为"对象—方法—检查器"强耦合。ESE 不是：

- 同一个任务（缺陷预测）可以用 repository mining、benchmark evaluation、controlled experiment 三种方法研究；
- 同一种方法（case study）可以用于很多任务（代码评审、flaky test、重构）；
- 不同方法对同一威胁的立场不同（例如 external validity：mining 可能"接受并声明"，case study 可能"要求 redesign"）。

所以插件必须拆成 **METHOD** 与 **TASK** 两类，并允许组合。组合时如果对同一威胁给出相反立场，必须报 `Conflict`，不能静默取一。

### 6.2 插件契约

每个插件至少包含：

| 字段 | 含义 | 硬约束 |
| --- | --- | --- |
| `plugin_id` / `kind` | 标识与类型（METHOD/TASK） | 必填；类型必须匹配 |
| `hooks` | 可接入的阶段 | 必须是合法阶段 |
| `provides` | 提供什么（模板、检查器、失败模式、报告规范） | 必填 |
| `supports` | 能支持什么结论 | 必填、具体 |
| `cannot_support` | 不能支持什么 | **非空**，否则拒绝 |
| `returns_to` | 处理完回到哪个阶段 | 必须是合法阶段 |
| `writes` | 允许写哪些目录 | 不得写 claim/gate/signature |
| `forbidden` | 禁止的动作 | 必须包含 create_claim / sign / change_gate |
| `threat_stances` | 对五类威胁的立场（severity + advice） | METHOD 至少 3 类 |
| `failure_patterns` | 该任务/方法常见失败 | TASK 必须非空 |
| `verifier` | 可执行的核验/分析入口 | 只读或产出候选 artifact |

### 6.3 冲突处理

冲突不是错误，是信息：

- `ACCEPT` vs `REDESIGN` → 阻塞，必须由人/设计变更解决；
- `ACCEPT` vs `MITIGATE` 且 severity 差 ≥1 → 报告；
- severity 差 ≥2 → 报告。

报告必须写清：哪个威胁、方法插件主张什么、任务插件主张什么、为什么冲突、需要什么证据才能解决。不能"取平均"或"让 LLM 仲裁"。

### 6.4 数据集卡（Dataset Cards）

ESE 的重复踩坑很多来自数据，不是方法。每张卡至少：

- `name` / `source` / `license` / `version` / `access`；
- `sampling`（probability/stratified/convenience/purposive/census/unknown）；
- `subject_kind`（human/code/llm/mixed）；
- `known_biases`（如 Java only、temporal drift、bug-fix attribution、mutants ≠ faults）；
- `time_split`（按版本/时间切分，禁止随机 commit 切分）；
- `contamination_note`（LLM 数据集必填：训练截止、重叠检测、私有留出集）；
- `invalidation_conditions`（版本/许可/模型/时间窗变化时结论失效）。

### 6.5 方法特定检查项（ESE 不能只靠五类威胁）

五类威胁是共同语言，但每个方法还有自己的"必查项"。这些检查项应放进方法插件的 `checklist`，而不是让 agent 每次即兴发挥：

| 方法 | 必查项 |
| --- | --- |
| **Repository mining** | 抽样框与项目选择标准；时间切分（按版本/提交时间，禁止随机 commit）；重复仓库/镜像；commit 归属与 bug-fix 识别；license 与再分发；API 限流/快照时间 |
| **Controlled experiment** | IRB/知情同意（有人类参与者时）；随机化与任务顺序；学习/疲劳效应；需求特征；仪器与计时；退出/缺失；预注册分析 |
| **Benchmark evaluation** | 训练/测试污染；基准饱和（headroom）；prompt/预算/算力对齐；多基准与多重比较；选择偏差（只报好基准）；版本与时间切分 |
| **Case study** | 研究协议与链式证据；三角验证（访谈/文档/制品）；成员核查；研究者立场；可迁移性而非统计泛化；隐私/匿名 |
| **SLR** | 协议与 RQ；纳入/排除标准；数据库与检索式；质量评估；双人筛选与一致性（kappa）；PRISMA/可复现检索日期 |
| **Causal/quasi** | 识别策略（DiD/RDD/IV/matching）；混杂与平行趋势；安慰剂/负对照；敏感性分析；外推边界 |

这张表也是"任务插件"和"方法插件"的分工线：方法插件拥有检查项与报告规范，任务插件拥有该任务族的基线、失败模式与构念争议。

### 6.6 示例插件

| 类型 | 插件 | supports（示例） | cannot_support（示例） |
| --- | --- | --- | --- |
| METHOD | repository mining | 样本与抽样框范围内的相关性/趋势 | 因果机制、跨生态泛化 |
| METHOD | controlled experiment | 在操控变量上的效应量 | 大规模工业外推、长期效应 |
| METHOD | benchmark evaluation | 固定基准/预算下的相对表现 | 真实开发效率、未污染的能力 |
| METHOD | case study | 机制解释、情境化证据 | 统计 generalization |
| METHOD | survey/SLR | 文献覆盖与证据地图 | 新系统的效应 |
| TASK | defect prediction | 该基准上的排序/分类 | 跨项目迁移的因果解释、实时预测 |
| TASK | LLM4Code | 固定模型/提示/基准上的表现 | 跨模型泛化、真实生产力 |
| TASK | code review | 评审意见质量/有用性 | 团队长期文化变化 |
| TASK | flaky test | 检测/复现/修复效果 | 所有 CI 环境的稳定性 |
| TASK | refactoring | 可维护性代理指标上的变化 | 开发者认知负荷 |

### 6.7 插件不是什么

- 不是一段提示词；
- 不是一个审稿人角色（`custom_agents` 的 coverage/citation check 是审稿，不是领域方法）；
- 不是一个流水线阶段；
- 不是 claim 的签署者；
- 不是"只要加载就自动提升"的能力。

---

## 7. Workspace Memory：长程研究的真正底座

### 7.1 单题目录

```text
my-ese-problem/
  CLAIM.md / claim.json          # 断言 + 三轴 + 阶段 + scope
  PROTOCOL.md / protocol.json    # 预注册 + 冻结 + 分析计划 + 停止规则
  DATASETS.md                    # 数据集卡与坑
  FAILURES.md                    # durable 失败图谱（只增不减）
  REPLICATIONS.md                # 独立复现记录
  DECISIONS.md                   # 为什么改路线/改设计
  NEXT_SESSION.md                # 当前事实、未闭义务、下一动作
  research-wiki/                 # papers/ideas/experiments/claims
  work/                          # 脚本、原始输出、日志
```

目录按需要出现，不要求每个任务都生成全部文件。短任务可以只有 `CLAIM.md` + `work/`。

### 7.2 失败图谱

| 类别 | 类型 | 去哪 | 例子 |
| --- | --- | --- | --- |
| operational | environment / data_unavailable / transient / rate_limit | 运行日志 | API 429、磁盘满、依赖装不上 |
| durable | design_flaw / construct_mismatch / underpowered / contamination / leakage / population_drift / true_null | 失败图谱 | 时间切分泄漏、基准污染、n 不足、指标不测构念 |

每条 durable 失败至少记录：

- `failure_id` / `kind` / `observed` / `diagnosis`；
- `context`（可复核的键值：n、dataset、overlap_check、construct/operationalization…）；
- `retry_condition`（什么条件下值得重试；不可重试写 `none` 并说明）；
- `scope`（这个失败适用于哪些 population/任务/时间窗）；
- 证据链接（run id、artifact hash、日志）。

规则：

- **失败图谱永不裁剪**：它是最高反重复价值的信息；
- **operational 不进图谱**：把限流写成"方法无效"会让系统永久避开一条可行路线；
- **未知类型 fail-closed**：不静默归类；
- **重试条件必须具体**：不能写"以后再试"。

### 7.3 QueryPack：有预算的只读投影

派发前，用 `QueryPack` 把相关记忆压进一个硬预算：

- 优先级：`failures > scope > datasets > papers > ideas`；
- `failures` 永不裁剪；其他节按预算裁剪；
- 确定性生成，不做开放式 LLM 摘要；
- 读取后必须改变下一动作：复用哪条失败、避开哪个数据集、补哪个条件；
- 写入后读回实际实体，确认没有被模板覆盖。

### 7.4 记忆写入准入

| 可以写入 | 不可以写入 |
| --- | --- |
| 人签 claim、独立复现结果、durable 失败、数据集卡、协议卡 | LLM 摘要、operational 失败、无来源断言、fixture 结果 |
| 有 artifact hash 的证据 | "模型觉得对"的判断 |
| 明确 scope 与失效条件 | 跨 scope 的过度泛化 |

跨项目记忆只共享**可复用模式**（失败类型、数据集坑、方法边界），不共享单题参数与未签结论。

---

## 8. Meta-evolve：框架如何随问题演进

### 8.1 为什么必须独立

研究循环中改规则，会让"当前证据"与"当前判据"同时变化，无法归因。MathRSI 把 `meta-evolve` 放在解题循环之外，本仓的 `rsi` 也把候选/准入/租约与人签分开。ESE 必须沿用这个分离：

- 研究循环只读当前版本；
- 元演化只改下一版；
- 在途研究不被静默换版；
- 每次改动有版本、证据、回滚点。

### 8.2 触发与证据

| 触发 | 证据 | 可能的改动层 |
| --- | --- | --- |
| 同一 durable 失败在两个以上研究复现 | 失败图谱 + 两次 run 的 scope/条件 | method plugin / base |
| 某插件 `cannot_support` 被实际违反 | claim 草案 + 审稿意见 | task plugin / base |
| 某方法持续 underpowered | 多次功效计算 + 成本 | method plugin / dataset card |
| 复现成功但原 claim 未覆盖 | 复现记录 + 原 scope | base（返回点/范围） |
| 成本异常（探针太贵/执行太慢） | 时间/算力账本 | base / method plugin |

### 8.3 分层判断

| 归属 | 判断依据 | 例子 |
| --- | --- | --- |
| Base | 跨方法/跨任务都需要的研究行为 | "分析发现泄漏必须回设计" |
| Method plugin | 某一研究范式的规范/检查器 | "benchmark evaluation 必须先做去重探针" |
| Task plugin | 某一任务族的失败模式/基线 | "缺陷预测要注意时间切分与 class imbalance" |
| Dataset card | 某一数据集的坑/许可/污染 | "Defects4J 2.0 不支持随机 commit 切分" |
| Workspace-local | 单题参数/预算/一次 UNKNOWN | "本次 30 对项目、n=30" |
| Defer | 证据不足/收益不明 | "某模型在某任务上的提示技巧" |

### 8.4 候选与 shadow eval

候选必须写清：

- `target`（哪个文件/插件/字段）；
- `change`（最小 diff）；
- `rationale`（来自哪条 durable 失败）；
- `predicted_effect`（预期改善什么、代价是什么）；
- `source_failures`（必须引用 durable 失败）；
- `human_reason`（采纳理由）。

评估：

1. **不可变面检查**：触碰 claim/evidence/gate/rubric/signature/export/heldout → reject；
2. **held-out 任务**：至少 2 个未参与候选设计的 ESE 任务；
3. **无回归**：任一 held-out 任务退化 → reject；
4. **public 不为正** → reject；
5. **成本**：超过阈值且无人接受 → reject；
6. **人的理由**：缺失 → defer；
7. 全过 → adopt（仍由人执行）。

### 8.5 版本管理

- 版本号 + changelog + 证据 + 回滚点；
- **方法指纹**：不能只哈希 `research_agent/**/*.py`；还要覆盖插件 manifest、提示词、检查清单、分析脚本、数据集卡。否则"平台指纹没变"会掩盖研究方法变化；
- 固定 tag/commit；在途研究记录采用的 revision；
- 没有 held-out 证据的版本号不叫 RSI。

### 8.6 RSI 的失败模式

| 失败模式 | 表现 | 防线 |
| --- | --- | --- |
| 代理优化 | public 分数涨，真实研究质量不涨 | held-out + 人工理由 |
| Benchmark 过拟合 | 候选只对固定任务有效 | 轮换任务、留出任务、时间切分 |
| 规则膨胀 | 每失败加一条规则，系统越来越重 | 一次一层、最小 diff、删除无效规则 |
| 虚假因果 | 把相关当因果 | 预注册 + 对照 + 独立复现 |
| 自证循环 | 用同一模型评审自己的改动 | 跨供给评审 + 人签 |
| 隐藏人工 | 自动化把成本转嫁给签核者 | 记录 human_minutes，成本审计 |

---

## 9. 与现有仓库的接线

### 9.1 可以直接复用

| 现有资产 | 用途 | 备注 |
| --- | --- | --- |
| `study_preregistration.py` | 协议卡：question/hypothesis/analysis/decision_rule + baseline + TODO 占位拒绝 | 最接近 ESE 预注册的现成实现 |
| `search_lab._paired_diff_interval` | 配对均值差 + t 95% CI；n<MIN 截断 | 区间门的现成实现 |
| `study_claims.comparison_verdicts` | positive/negative/undecidable 单点 | 三态的唯一来源 |
| `study_replication.py` | 按设计分组、跨数据集复现计数 | 复现轴的现成实现 |
| `experiment local-init/approve/run/ingest` | 任意本地命令（argv、无 shell、approve、hash） | ESE 执行面的最佳接缝 |
| `run_contract.py` / `RunCapsule` | 过程记录、artifact allowlist、哈希 | 可扩展为 StudyCapsule |
| `verdict_ledger.py` | 判定总线、读时重算、source sha256 | 单一判定来源 |
| `closure.py` / `lineage.py` | 闭合、失效传播、导出锁 | 需增加数据集/时间/基准失效键 |
| `feedback.py` | observe→propose→gate→apply→record | 返回点的现成骨架 |
| `rsi.py` / Harness² / `evolution_generations.py` | 候选/证据/租约/世代/回滚 | 对象要从"检索/技能"扩展到"方法/插件" |
| `writing_pack.py` / `writing_audit.py` | 从已签 claim 投影论文 | 不让写作反推证据 |

### 9.2 需要最小扩展

1. **ClaimSpec 扩展**：在现有 claim/design 上增加只读字段——五类威胁、scope、`invalidation_conditions`、`repro` 轴、`evidence_kind=interval|point`。不得改写已签名字段。
2. **experiment claim 的区间口径**：ESE scope 下禁止只给点估计 ±tolerance；要求 CI/效应量，或显式标 `evidence_kind=point` 并降级为探索性。
3. **study 的数据集注册表**：从 iris/wine/breast_cancer/digits 扩到 ESE 数据集卡；不是把 Defects4J 塞进 `DATASETS`，而是新增 `dataset_card` 只读注册表。
4. **lineage 失效键**：除代码/产物 hash 外，增加 dataset version、time window、benchmark contamination、model/prompt hash。
5. **rsi 的方法指纹**：覆盖插件 manifest、提示词、检查清单、分析脚本、数据集卡；新增 `method_plugin` / `task_plugin` 候选 scope。
6. **UI 投影**：claim 三轴、威胁矩阵、失败图谱、QueryPack、元演化账本；只读，不提供签核按钮。

### 9.3 不要做

- 不要新增 10 个 ESE 模块；35 个模块对单人维护已经偏多（设计 75 §5 第 2 条）；
- 不要重写统计引擎；复用 `study` 的区间/功效/复现；
- 不要把 ESE 评测塞进 runtime/MCP；签核仍在 CLI/人工流程；
- 不要让 LLM 直接写 claim 数值或签核；
- 不要让元演化自动改 gate/claim/evidence；
- 不要把"跑通一个 benchmark"当成"验证了 ESE 能力"。

### 9.4 晋升路径

| 阶段 | 做什么 | 验收 |
| --- | --- | --- |
| **P0（现在）** | 原型：语义内核 + demo + 52 测试 | 测试绿；演示能说"不" |
| **P1（2–4 周）** | 一个真实 ESE 研究走完：协议卡 + 最难关口探针 + 执行 + 区间 + 失败图谱 | 一条人签 claim 或一条诚实的 undecidable |
| **P2（4–6 周）** | 3 个方法插件 + 3 个任务插件 + 数据集卡注册表；UI 只读投影 | 插件冲突可复现；QueryPack 被实际消费 |
| **P3（6–8 周）** | 元演化：2 条 durable 失败 → 候选 → 2 个 held-out 任务 → 人采纳/拒绝 | 有回滚点；无回归；方法指纹 |

### 9.5 与设计 80 的关系

设计 80 的结论是"ESE 评测不进系统代码，留在研究层（协议人写、独立脚本分析、报告进论文）"。本文**不推翻**这个结论：

- 统计评测仍然不进 runtime/gate；
- 本文新增的是**研究循环语义**（claim spec、三轴、威胁、失败图谱、插件契约），不是新的统计引擎；
- 它可以先活在 `prototypes/ese/` 与 `thesis-eval/`，只读消费系统产物；
- 只有 P1 产出真实人签 claim 后，才讨论是否晋升为 `modules/ese-core`（且只读、不签核）。

---

## 10. 对现有设计的反思：十二个不足

先说得公平：本仓在"过程可信"上做得比大多数科研智能体深——span-only、fixture 隔离、哈希链、门禁、lineage、closure、写作审计、判定总线，都是真机制，不是口号。问题不在这些机制错，而在**它们主要回答"过程有没有被记录/被授权"，不回答"经验结论是否有效"**。

### 10.1 十二个不足（按严重度）

| # | 不足 | 证据 | 后果 |
| --- | --- | --- | --- |
| 1 | **静态流水线，缺分析→设计回流** | `pipeline.py` 固定 S1→paper；`feedback` 只有 lineage/t6b/belief/homogeneity 四环，且 t6b 当前只有审计项 | 分析发现泄漏/混杂时，只能写 warning，不能把设计打回 |
| 2 | **ESE 语义缺失** | 无 ClaimSpec、五类威胁、DatasetCard、FailureRecord；`experiment` 只有 design card | 一条 ESE 断言无法被完整规格化，评审只能看散文 |
| 3 | **experiment claim 是点证据** | `_parse_assertion` 是 metric ± tolerance，不是区间门 | 点估计可被签成"提升"，与 `study` 的区间门不一致 |
| 4 | **study 很强但很窄** | 数据集仅 iris/breast_cancer/wine/digits；设计是搜索配置 2×2 | 最好的统计资产无法用于仓库挖掘/基准评测/案例研究 |
| 5 | **没有领域插件层** | modules 是阶段；`custom_agents` 是 coverage/citation 审稿角色 | 加一个 ESE 任务要改代码，不能靠知识/契约扩展 |
| 6 | **没有跨项目失败/数据集记忆** | 每项目独立 runs/artifacts；literature memory 是检索记忆 | 同一个坑反复踩；失败不可复用 |
| 7 | **没有最难关口探针** | 设计审计是清单，不是"先跑能杀死断言的测试" | 昂贵实验在效度未验证前就开跑 |
| 8 | **人签质量无仪器** | 设计 75 §3.1：系统不测量签核者是否真的看了预评估；单人签核循环 | 自动模式跑多后，人签退化为橡皮图章 |
| 9 | **独立性名不副实** | 设计 75 §3.4：同宿主验证者与提出者共享模型；`independence.py` 只做供给指纹披露 | "独立评审"可能只是同模型换会话 |
| 10 | **RSI 优化的是检索代理** | `rsi` 候选是 retriever/budget/skill；评估是 retrieval recall/S5 seed budget | 不能回答"研究方法是否变好"；容易把代理提升写成能力提升 |
| 11 | **模块数/维护成本** | 35 个模块；1487 测试；设计 75 §5 第 2 条自认偏多 | 单人维护已吃力；再加 ESE 模块会恶化 |
| 12 | **测量缺口** | 设计 75 §3.3：四个反馈环有效果语义、无效果测量；M1 flip_rate=1.0 但 n=1；M2 n=3 underpowered；35% run 无 verdict 动作 | 系统无法证明"闭环让研究更好" |

### 10.2 每条不足的具体表现

#### 1）静态流水线

现有 `pipeline run` 的顺序是 S1 文献 → S2/S3 想法 → S4 设计 → S5 执行 → S5b claim → S8 写作。它没有"分析阶段发现威胁 → 回到设计"的路径。`feedback.py` 的四个环是事后约束（lineage 失效、证伪、信念修订、同质化），不是**研究设计内的回流**。这导致：

- 效度威胁只能在 `design_audit` 里作为清单提示；
- 执行后发现泄漏，只能在报告里写"局限"，不能强制重跑；
- 评审看到的是一条"已完成"的链，而不是"曾经被打回"的链。

MathRSI 的 `verify→prove` 返回点之所以有效，是因为它**改变下一动作**，不是只写一条 review comment。ESE 需要同构的 `verify→design`。

#### 2）ESE 语义缺失

一条典型的 ESE 断言是：

> 在 Defects4J 2.0 的 30 个项目版本上，LLM 生成的测试比预算匹配的 EvoSuite 有更高的 mutation score（Δ≥0.05）。

这句话包含：构念（test effectiveness）、操作化（mutation score）、population（30 个项目版本）、comparison（预算匹配）、metric、threshold、scope、五类威胁。现有 `experiment` 的 design card 没有这些字段；`claim.statement` 是自由文本；`scope` 是 dataset 级字符串。结果是：**机器无法判断这句话是否被证据覆盖，人也只能靠散文审。**

#### 3）点证据 vs 区间

`experiment_runner._parse_assertion` 用 `metric / comparator / value / tolerance`。这适合"最差种子下限"这种协议验证，不适合 ESE 的效应量断言：

- 点估计没有不确定性；
- `tolerance` 不是置信区间；
- 多项目、多度量的多重比较没有记账；
- underpowered 无法在 claim 层表达。

`study` 已经做对了：只有 95% 区间不跨零的比较才能成为可签断言；n<4 不解释方向。这个口径应该推广到 ESE claim，而不是只留在 search-study。

#### 4）study 很强但很窄

`study` 的预注册、区间、功效、复现计数是全仓最接近 ESE 的部分。但它被锁在"搜索配置 2×2"上：

- 数据集是 toy ML；
- 设计是 `memory × gate`；
- 指标是 `improvement_per_evaluation`；
- 外部效度边界明确写"analogue=true，不构成对任何已发表系统的复现"。

这不是缺陷，是边界。但如果我们声称"面向 ESE"，就必须承认：**目前没有一个模块能研究仓库挖掘、基准评测、代码评审、flaky test。**

#### 5）没有插件层

`modules/` 是阶段模块（literature/idea/experiment/run/...），不是领域知识插件。`custom_agents.py` 可以加"覆盖与引用审稿人"，但它只做 `coverage`/`citation` 检查，不是方法/任务知识。

MathRSI 的插件能提供：领域对象定义、定理条件、归约、检查器、失败输入、重试条件、返回点。ESE 插件应提供：方法规范、威胁立场、基线、失败模式、分析脚本、报告清单。当前没有这个扩展点，所以每个新 ESE 任务都要改 `experiment_codegen` 或写一次性脚本。

#### 6）没有跨项目记忆

现有 `project/` 保存单项目 runs/artifacts；`literature_memory` 保存检索记忆；`guideline_memory` 保存写作/评审准则。没有"失败图谱"和"数据集坑"的跨项目记忆。结果是：

- 同一个泄漏坑在不同项目重复；
- 同一个数据集的 license/时间切分问题重复；
- 一次 underpowered 的教训不会进入下一次设计；
- 失败 run 虽然保留，但不会被下一次研究读取。

#### 7）没有最难关口探针

`design_audit` 有"seeds/controls/effect size/power/randomization/multiplicity/CI/missing data/sensitivity"清单，但它是**事后审阅清单**，不是"先跑一个便宜探针"。清单可以打勾，探针必须产生读数。

ESE 最常见的失败不是"清单没写"，而是"写了但没测"：写了时间切分，实际随机切；写了预算匹配，实际没匹配；写了去重，实际没去。探针是让这些"写了"变成"测了"的唯一方式。

#### 8）人签质量无仪器

设计 75 已经指出：四道门的语义强度全部锚在"人签"，但系统不测量签核质量。ESE 更严重，因为研究者常常就是开发者：

- 自己设计、自己跑、自己签；
- 知道预期结果，容易选择性解释；
- 单人签核的"独立性"只是不同时间点的同一个判断者。

需要：签署前检查点（必须确认数值边界/scope/失效条件）、查看路径记录、第二签核者、签核一致性读数。这些不是新门禁，是**门的质量测量**。

#### 9）独立性名不副实

`independence.py` 给每个批评角色算 `(provider_id, model_name)` 供给指纹，这是正确的第一步。但：

- 同宿主多会话仍共享模型偏差；
- `host_label` 可能都归因到同一个宿主；
- `admission_eligible` 已经在实测中拒绝"改了配置就算独立"。

ESE 的高风险 claim（例如"某方法在工业界有效"）需要跨供给复现，不能只靠同模型换会话。设计上应记录 `supply_independence`，并在 claim 的 scope 里写明"独立复现的供给"。

#### 10）RSI 优化的是检索代理

`rsi` 的候选是 retriever/budget/skill；评估是 gold recall/cost/coverage/S5 seed budget。它是**治理控制面**，不是研究质量引擎。Harness² 是 harness 进化，也不是科学假设评估。

问题不在"做了错事"，而在**命名与预期**：如果对外说"RSI/自进化"，读者会以为系统在学习"怎样做更好的研究"；实际它主要在学"怎样更省地检索/怎样改 harness"。这两件事的评估任务、证据、风险完全不同。

#### 11）模块数/维护成本

设计 75 §5 第 2 条已经承认："35 个模块对单人维护偏多；closure/lineage/maintenance 的边界在现场多次需要来回查证。" 1487 个测试是资产，也是负担。再为 ESE 加 10 个模块，会重复同样的错误。

正确做法：**一个薄内核 + 插件 + 复用现有资产**。内核不超过 5 个文件；插件是数据/脚本，不是新阶段。

#### 12）测量缺口

设计 75 §3.3 指出：四个反馈环有效果语义、无效果测量。M1 的 `flip_rate=1.0` 只有 n=1；M2 的 n=3 underpowered；M1 的 `verdict_action_coverage=0.645` 有 35% 未解释。这些是真实的测量缺口，不是文档没写。

ESE 设计不能重复这个错误：**每个机制都要有可失败的验收**。例如"失败图谱让下一次研究少踩坑"必须用"复用率/避免率"测量，而不是"我们建了图谱"。

### 10.3 Wellspring-Agent 专项反思

Wellspring-Agent 是本仓的产品/发行定位，强在：

- 打开前端即工作台，任务线程 + 运行上下文；
- 46 个 MCP 工具，零签名入口；
- 四类判定（资格/完成/失效/供给）；
- Harness² 双轨世代（agent tree SHA + platform fingerprint）；
- autopilot 人写策略、越界即停；
- 1487 测试 / 发布完整性。

但从 ESE 研究智能体的角度看，有五个具体缺口：

1. **"四类判定"是证据闭合判定，不是经验有效性判定。** 资格（span-only）、完成（capsule→EA→closure）、失效（lineage）、供给（模型草稿）都回答"这条链是否可审计"，不回答"这个效应是否真实"。
2. **Harness² 的 platform fingerprint 只覆盖 `research_agent/**/*.py`。** SPEC、测试、脚本、前端、插件 manifest、提示词、分析脚本都不移动指纹。对研究方法而言，这是**假阴性**：方法变了，指纹没变，旧证据被当成同一版本。
3. **RSI 的评估任务是检索 recall / S5 seed budget，不是 ESE 研究结果。** 这能证明"候选在代理指标上有效"，不能证明"候选让研究结论更可信"。
4. **autopilot 可以代签 G1/G2/S5b/G5。** 对协议验证可以；对 ESE 的设计批准（G2）和结果签署（S5b），这正是效度判断最需要人的地方。建议 ESE scope 下 autopilot 只代跑执行/ingest，不代签设计/claim。
5. **claim 的失效条件不够结构化。** 现在是代码/产物 hash + dataset scope；ESE 还需要 dataset version、time window、benchmark contamination、model/prompt hash。否则"代码没变"会被误读成"结论仍有效"。

产品层不应该为这些缺口加 10 个模块。应该：

- 用 `thesis-eval/` 承载 ESE 协议与分析脚本；
- 用 `prototypes/ese/` 验证语义；
- 只给产品加 2–3 个只读投影（claim 三轴、失败图谱、方法指纹）；
- 把 RSI 的候选 scope 从"检索"扩到"方法/插件"，但评估任务必须是 held-out ESE 任务。

### 10.4 如果只能改三件事

1. **加 ClaimSpec + 三轴 + 失败图谱**（语义层，不改统计引擎）。
2. **把 study 的预注册/区间/复现推广到 ESE claim**，用 `experiment local-*` 做执行面。
3. **把 RSI 从"检索代理"改成"方法/插件的 held-out 评估"**，并加方法指纹。

---

## 11. 一个完整案例：LLM 生成测试 vs EvoSuite

> 以下数值全部是**教学示意**，不是实证结果。案例的目的是展示流程与判据，不是主张任何效应。

### 11.1 ClaimSpec

| 字段 | 内容 |
| --- | --- |
| construct | test effectiveness |
| operationalization | mutation score = killed mutants / non-equivalent mutants，固定 operator set |
| population | Defects4J 2.0，Java 11，初版计划 30 个项目版本对（探针后改为 64 对，重新预注册） |
| comparison | LLM-generated tests vs EvoSuite，预算匹配、去重 |
| metric | delta_mutation_score |
| threshold | +0.05 |
| scope | Java 11 开源项目；Defects4J 2.0；固定 prompt/model cutoff；不外推到工业/ Python |
| threats | construct：mutation score ≠ fault detection，人工抽查 10%；internal：预算/ flakiness/泄漏；external：Java only；conclusion：配对设计、单次预注册比较、bootstrap CI；reproducibility：容器/提示词/种子/数据 hash |
| invalidation | Defects4J 版本变化、operator set 变化、模型/提示词变化、population 移出 Java 11 开源 |

### 11.2 最难关口探针

| 探针 | 问题 | 便宜测试 | 示意结果 | 动作 |
| --- | --- | --- | --- | --- |
| P-LEAK | 生成的测试是否复制了现有测试/修复 diff？ | 3 个项目去重 + diff overlap | 38% 重复（示意） | **redesign**：去重 + 隐藏 fix diff |
| P-POWER | 30 对是否够检测 0.05？ | 用 pilot 方差做功效 | 30 对只够检测 0.08，0.05 不够（示意） | **redesign**：加到 64 对并重新预注册；不得带着不足功效开跑 |
| P-CONSTRUCT | mutation score 是否追踪真实缺陷？ | 50 个 mutant 人工 replay | rank corr 0.71（示意） | pass，但 scope 写"代理指标" |
| P-ENV | 干净环境能否重建？ | 容器重建 + hash | pass | 记录环境指纹 |

### 11.3 Design

- 预注册采样、功效、分析计划、停止规则；
- 修订后 64 对，按项目大小/ mutant 数分层；这是看到**探针**后、看到**结果**前的新预注册；
- 预算匹配：EvoSuite 与 LLM 生成使用相同 token/时间预算；
- 分析：配对 bootstrap 95% CI；一个主比较；不做亚组钓鱼；
- 停止规则：区间跨零即报 undecidable；不"加到显著"。

### 11.4 Execute

- 用 `experiment local-init` 登记命令（argv、env、cwd、expected outputs、timeout）；
- `local-approve` 人签；`local-run --allow-execute`；
- `local-ingest` 校验 execution/receipt/metrics/artifact hash；
- 产出 `StudyCapsule`（数据/代码/环境/种子/命令/原始输出）。

### 11.5 Analyze

示意结果：CI [-0.02, +0.09] 跨零 → `undecidable`。

- 不能签；
- 记录 `underpowered` durable failure：n=64，但实际方差高于 pilot，按观测方差需要约 120 对；
- 不把"点估计 +0.03"写成"提升"；
- 不重跑到显著。

### 11.6 Replicate/Scope

- 原始 64 对 claim 保持 undecidable；
- 新开一条**窄化 claim**（12 个 mutant-rich 项目版本），预注册后再跑；
- 独立数据/独立实现/独立分析者；
- 示意结果：supported + reproduced；
- 签核，scope 写"仅这 12 对；不外推"；残余风险写明"mutation score 是代理指标、样本仅 Java"。
- **关键**：窄化 claim 不是"把原 claim 改到显著"；它是新 claim，原 claim 仍在图谱里。

### 11.7 Deposit

- 签核 claim card（三轴 + scope + 失效条件）；
- 失败图谱：`leakage`（去重/隐藏 diff）、`underpowered`（n/required_n）；
- 数据集卡：Defects4J 2.0 的 license/time split/contamination；
- NEXT_SESSION：下一步是"跨语言（Python）复现"或"工业案例"。

### 11.8 RSI

两条同类 `leakage` 失败 → 候选：给 benchmark-evaluation 插件加"强制去重探针"。

- public：+0.09（示意）；
- held-out：+0.06（示意，2 个任务，无回归）；
- 成本：+0.02（示意）；
- 人写理由 → adopt v0.2；回滚点 v0.1；
- 另一个候选"降低 gate 阈值"触碰不可变面 → reject；
- 另一个候选只有 public 提升、无 held-out → defer。

### 11.9 谁做什么

| 步骤 | agent | 人 |
| --- | --- | --- |
| 规格草案 | 生成候选、查文献、列威胁 | 确认构念/操作化/scope |
| 探针 | 写探针脚本、跑、报读数 | 判断是否足够、是否改设计 |
| 设计冻结 | 生成 protocol 草案、检查完整性 | **签 G2** |
| 执行 | 登记命令、跑、ingest | approve/授权环境 |
| 分析 | 复算区间、列威胁、写 verification | 核对数值边界/scope |
| 复现 | 找独立数据/实现、跑 | 判断独立性 |
| 签核 | 不签 | **签 S5b** |
| 元演化 | 提议、shadow eval | **采纳/拒绝** |

---

## 12. 路线图与验收指标

### 12.1 路线图

| 阶段 | 时间 | 交付 | 验收（可失败） |
| --- | --- | --- | --- |
| **P0** | 现在 | 原型 + demo + 52 测试 + 设计文档 | 测试绿；demo 能拒绝签署/拒绝采纳 |
| **P1** | 2–4 周 | 一个真实 ESE 研究：协议 + 探针 + 执行 + 区间 + 失败图谱 | 一条人签 claim，或一条诚实的 undecidable；失败图谱被下一次读取 |
| **P2** | 4–6 周 | 3 方法插件 + 3 任务插件 + 数据集卡；只读 UI | 插件冲突可复现；QueryPack 使用率 > 0；无回归 |
| **P3** | 6–8 周 | 元演化：2 条 durable 失败 → 候选 → 2 held-out → 人采纳/拒绝 | 有回滚点；held-out 无回归；方法指纹 |
| **P4** | 后续 | 跨项目记忆、复现库、论文投影 | 复现率/失败复用率可测 |

### 12.2 指标

| 指标 | 定义 | 目标（初始） |
| --- | --- | --- |
| `time_to_first_credible_claim` | 从立项到第一条可签 claim 的天数 | ≤ 30 天 |
| `protocol_coverage` | 有冻结协议的 claim / 全部 claim | 100% |
| `interval_gate_coverage` | 有 CI/效应量的 claim / 已签 claim | 100% |
| `replication_rate` | reproduced/partial / attempted | ≥ 50% |
| `failure_reuse_rate` | 引用了相关 durable 失败的新研究 / 有相关失败的新研究 | ≥ 60% |
| `threat_coverage` | 有具体缓解/证据的威胁 / 5 | 5/5 |
| `human_minutes_per_claim` | 人签+审阅+处理的分钟数 | 可接受且下降 |
| `rsi_yield` | 采纳且 held-out 改善的候选 / 提议候选 | ≥ 30% |
| `regression_rate` | 采纳后 held-out 退化的比例 | 0 |
| `claim_survival_6m` | 6 个月后仍未被失效的 claim / 已签 claim | 可测 |

### 12.3 Kill criteria

- P1 6 周内产不出任何可签 claim 或诚实的 undecidable → 停止加功能，先修循环；
- 失败复用率 < 30% → 图谱没有被消费，重做检索/QueryPack；
- 元演化候选在 held-out 上不超过 baseline → 停止称 RSI；
- 人签分钟数持续上升 → 流程太重，删步骤而不是加门；
- 任何"点估计 + 显著性"绕过区间门 → 视为回归。

---

## 13. 风险与反模式

| 反模式 | 表现 | 防线 |
| --- | --- | --- |
| **Rigor theater** | 门很多、哈希很多，但没有效度探针 | 最难关口探针 + 三轴 + 失败图谱 |
| **Gate inflation** | 每遇到问题加一道门 | 一次只改一层；门只加在"必须人判断"的地方 |
| **Dashboard science** | 指标好看，但不改变下一步 | 每个指标必须绑定一个动作 |
| **LLM 审稿当 oracle** | 同模型多会话，互评"通过" | 供给指纹 + 跨供给 + 人签 |
| **Benchmark 过拟合** | 候选只对固定任务有效 | held-out + 时间切分 + 轮换任务 |
| **Memory poisoning** | operational 失败/LLM 摘要进图谱 | 分类准入 + 只写 durable + 读回 |
| **Modularity theater** | 35+ 模块，单人维护不动 | 薄内核 + 插件 + 复用 |
| **RSI theater** | 版本号 + 自评，没有 held-out | 方法指纹 + shadow eval + 回滚 |
| **Automation of signature** | autopilot 代签设计/claim | ESE scope 下只代跑执行/ingest |
| **Ignoring human subjects** | 不做伦理/隐私/同意 | 任务插件必须声明 IRB/隐私边界 |

---

## 14. 结论

MathRSI 给我们的最深教训不是"要有五阶段"，而是三句话：

1. **进度的单位是闭合的义务，不是阶段名。**
2. **记忆的单位是可复用的失败，不是摘要。**
3. **演化的单位是有证据的改动，不是版本号。**

对 ESE，这三句话要换成：

1. **证据的单位是带 scope 与区间的 claim，不是点估计。**
2. **信任的单位是协议 + 独立复现，不是模型同意。**
3. **改进的单位是改变插件/方法的 durable 失败，不是 public 分数。**

所以，第一步不是再写一个模块，而是**让一条真实的 ESE 断言走完这条循环**：

- 写清五类威胁；
- 跑一个能杀死它的探针；
- 冻结协议；
- 执行并记录；
- 用区间而不是点估计判定；
- 独立复现；
- 把失败写进图谱；
- 让人签一个"可撤销、有范围"的 claim。

如果这条循环跑不通，加再多模块、再多门禁、再多"RSI"，都只是把不确定性藏得更深。

---

## 附录 A：数据契约（原型）

见 `prototypes/ese/models.py`、`loop.py`、`evolution.py`。核心对象：

- `ClaimSpec`：claim_id / construct / operationalization / population / comparison / metric / threshold / scope / threats
- `ValidityThreat`：kind / status / note（五类齐全）
- `DesignFreeze`：sampling_plan / power_analysis / analysis_plan / frozen
- `DatasetCard`：name / source / license / sampling / subject_kind / known_biases / time_split / contamination_note
- `FailureRecord`：failure_id / kind / context / observed / diagnosis / retry_condition / scope
- `ClaimState`：spec / stage / design / evidence / repro / run_id / env_fingerprint / human_reason / residual_risk_reason / invalidation_conditions
- `ThreatProbe` / `ProbeGate`：最难关口
- `EvolutionCandidate` / `ShadowTask` / `EvolutionDecision`：元演化准入

## 附录 B：ESE 效度威胁检查清单

### Construct

- 指标真的测了所声称的构念吗？
- 操作化与人工判断/真实缺陷的一致性如何？
- 有没有"指标可被优化但不代表构念"的捷径？

### Internal

- 观测到的差异是否由所声称的因子导致？
- 时间切分/重复样本/特征可用性/提示泄漏？
- 预算、环境、工具版本是否匹配？
- 有没有选择偏差/幸存者偏差？

### External

- population 是什么？抽样框是什么？
- 语言、生态、项目规模、团队规模、时间窗？
- 能否外推到工业/闭源/其他语言？

### Conclusion

- 样本量与功效？
- 效应量与 CI？
- 多重比较/亚组分析？
- 缺失数据/异常值/稳健性？

### Reproducibility

- 数据/代码/环境/种子/提示词 hash？
- 分析脚本是否可复算？
- 是否独立复现（数据/实现/分析者）？
- 基准污染/训练截止？

## 附录 C：MathRSI ↔ ESE 映射

| MathRSI | ESE | 备注 |
| --- | --- | --- |
| FORMAL_SPEC | ClaimSpec + Protocol | 断言不是定理，必须带 threshold/scope |
| ROUTE_REPORT | Design + probe report | 路线 = 方法选择 + 威胁缓解 |
| PROOF_DRAFT | StudyCapsule + analysis | 证据不是证明，是统计与复现 |
| VERIFICATION | 三轴 + replication | 无单一 PASS |
| HANDOFF | Claim card + failure atlas | 可签、可撤销、可复用 |
| failure map | FailureRecord（durable only） | operational 不进图谱 |
| plugin cannot_support | 方法/任务插件边界 | 结构性防过度宣称 |
| meta-evolve | 方法/插件元演化 | held-out + 人签 + 回滚 |
| NEXT_SESSION | 同名单题恢复页 | 当前事实、未闭义务、下一动作 |

## 附录 D：参考

- MathRSI：`math-rsi-main/README.zh-CN.md`、`docs/WORKSPACE.md`、`docs/PLUGIN_CONTRACT.md`、`docs/V6_CHANGES.md`、`base/skills/mathrsi-research/SKILL.md`、`base/skills/mathrsi-route-loop/SKILL.md`、`base/skills/mathrsi-verify/SKILL.md`、`base/skills/mathrsi-meta-evolve/SKILL.md`
- 本仓：`design/75-系统设计反思与机制合理性评估.md`、`design/78-导师方法论对照与任务书实施设计.md`、`design/80-ESE测评层设计.md`
- 代码：`research_agent/study_preregistration.py`、`research_agent/study_claims.py`、`research_agent/search_lab.py`、`research_agent/study_replication.py`、`research_agent/experiment_runner.py`、`research_agent/verdict_ledger.py`、`research_agent/feedback.py`
- 产品：`Wellspring-Agent/README.md`、`modules/rsi/SPEC.md`、`research_agent/evolution_generations.py`
- 方法学：Wohlin et al. `Experimentation in Software Engineering`；Runeson & Höst `Guidelines for Conducting and Reporting Case Study Research`；Kitchenham & Charters `Guidelines for Performing Systematic Literature Reviews`；Easterbrook et al. `Selecting Empirical Methods for Software Engineering Research`

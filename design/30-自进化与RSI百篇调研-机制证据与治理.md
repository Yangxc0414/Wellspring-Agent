---
title: 自进化 / RSI 百篇调研：机制、证据与治理
date: 2026-10-24
status: research-note
scope: 100 papers (2022–2026), arXiv snapshot 2026-10-24
evidence: metadata verified via arXiv id_list; abstracts read; no paper reproduced
related: [10, 11, 12, 23, 25, 26, 27, 28, 29]
---

# 自进化 / RSI 百篇调研：机制、证据与治理

> 这份文档回答三个问题：**过去四年自进化/RSI 到底在改什么；哪些证据真的支持“越跑越强”；我们的仓库应该借什么、拒绝什么。**
> 完整 100 篇目录见 [`research/self-evolution-100/catalog.md`](research/self-evolution-100/catalog.md)；机器可读书目见 [`research/self-evolution-100/bibliography.json`](research/self-evolution-100/bibliography.json)。
> 所有外部效果数字均为作者/机构口径，**本仓库没有复现任何一篇论文**。

---

## 0. 一页结论

1. **“自进化”不是一个东西。** 2026 年的综述已经把 bounded self-refinement（有界自我修正）与 open-ended RSI（开放式递归自我改进）分开；前者可评估、可工业落地，后者在 grounding、collapse、compute 三个方向上仍受约束（[2607.07663](https://arxiv.org/abs/2607.07663)，1,250 篇综述）。
2. **2022–2024 的主线是“让模型改自己的输出/提示/权重”；2025–2026 的主线是“让系统改自己的 harness、记忆、技能、数据准备器与研究流程”。** 权重冻结 + harness 进化成为更可复现的路线；训练型方法（SEAL、AgentEvolver、SkillRL）只作为对照。
3. **自评不可信是当前最硬的负结果之一。** 当 agent 同时控制“被优化的对象”和“验证它的测试”时，自评分数可以接近满分而真实部署退化；需要 agent 不可见、不可 author 的固定审计（[2607.24300](https://arxiv.org/abs/2607.24300)）。
4. **RSI 证据的整体质量仍然很弱。** 对 114 项研究的全文编码显示：只有约 **22%** 审计了完整循环的 **≥2 次重跑**；在人工编码样本中只有 **14%**；约 **60%** 在未参与选择的任务上评估（人工样本 **45%**）（[2610.27610](https://arxiv.org/abs/2610.27610)）。
5. **“public/hidden/near-OOD/regression”四个名字不等于四种真隔离。** 如果它们只是同一测试集的不同 `test_size`、或同一批文档的不同问题，那么 hidden 不是 hidden，near-OOD 也不是 OOD。这是本仓库当前最需要修的评测问题（详见 §5、§6）。
6. **没有 universal artifact。** 在四个 benchmark、六个 faithful baseline 上，没有任何一种自然语言 artifact（reflection / workflow / playbook / prompt）普遍获胜；必须在 disjoint held-out 上做 strict keep-better（[2606.28374](https://arxiv.org/abs/2606.28374)）。
7. **治理面正在从“lease”扩展成“分层可变性 + 供应链 + 记忆毒化 + 搜索污染”。** 只锁 claim/gate 不够：技能库、记忆、工具、检索都可能成为持久化攻击面（[2608.03509](https://arxiv.org/abs/2608.03509)、[2610.00093](https://arxiv.org/abs/2610.00093)、[2606.05241](https://arxiv.org/abs/2606.05241)）。
8. **我们的仓库不是严格 RSI。** 改进机制在系统外（人 + gate），评价标准外生（frozen public/hidden tasks + 人签）；更准确的定位是 **受治理的 harness 改进控制面**（governed harness improvement），属于 bounded self-refinement 的科研实例（GAI 的两个维度见 [2609.13406](https://arxiv.org/abs/2609.13406)）。
9. **科研自动化的外部基准已经存在。** PaperBench、RE-Bench、MLGym、MLE-bench、ScienceAgentBench、CORE-Bench 覆盖复现、ML 工程、数据驱动发现；我们的 ChemLab/iris 只是协议验证，不能替代这些基准，更不能写成“科研能力”。
10. **下一步不是再加一个模块，而是补三个证据条件：** 真 held-out + sealed evaluator、完整循环 ≥2 次重跑 + no-op 对照、成本/回归/撤销的可审计账本。否则“自进化”只能停留在控制面原型。

---

## 1. 方法：100 篇是怎么筛出来的

- **检索**：2026-10-24 通过 `export.arxiv.org` API 做 36 组主题检索（self-evolving、self-improving、RSI、Gödel/Darwin、agent memory、skills、research agent、benchmark、safety 等），得到 **1,207** 条候选。
- **筛选**：按“是否真的改变系统/策略/记忆/技能/流程”而非“是否用了 LLM”筛；保留经典机制、2025–2026 的关键增量、以及直接冲击我们设计的评测/安全论文；最终 **100 篇**。
- **核验**：100 篇全部通过 arXiv `id_list` 重新拉取元数据（标题、作者、日期、摘要哈希），不是凭记忆写 ID；书目中保留 `abstract_sha256`。
- **阅读深度**：100 篇做摘要级通读；约 20 篇做机制/证据/边界的二次核对；**没有下载 PDF 全文、没有复现、没有运行作者代码**。因此本文的“有效/无效”判断只到“作者报告了什么、证据形态是什么”，不到“我复现了”。
- **证据等级**：本文用三种标记：
  - `[原文]`：arXiv 摘要/正文明确写出；
  - `[作者口径]`：作者报告的增益，未复现；
  - `[我们的判断]`：基于机制与代码的推断，不是实验结果。

**筛选偏差**：arXiv 快照偏向英文、CS/ML 社区；2026 年论文占比较高，其中不少尚未经过同行评审；以“self-evolving/RSI”自描述的论文并不等于严格 RSI。我们在正文中会区分“作者自称”与“机制上成立”。

---

## 2. 五簇地图：100 篇分别在改什么

| 簇 | 篇数 | 主要改进对象 | 主要反馈/证据 | 代表工作 | 对我们的意义 |
|---|---:|---|---|---|---|
| A 基础机制 | 22 | 输出、prompt、代码、权重、记忆 | 自评、执行器、任务分数 | STaR、Self-Refine、SPIN、Absolute Zero、SEAL、GEPA、ACE | 提供“改进算子”；多数缺少治理与外部 grounding |
| B 自改与进化 | 20 | agent 代码、harness、技能库、数据准备器 | benchmark、archive、held-out | DGM、HGM、SIFT、RRSI、RSEA、SkillOS、R² Flow | 最接近我们的 harness 改进；关键在 archive/held-out/编辑预算 |
| C 科研自动化 | 21 | idea、实验、论文、研究工程 | 自动评审、专家、复现/竞赛 | AI Scientist v2、Agent Laboratory、Kosmos、Robin、PaperBench、RE-Bench | 证明“端到端”可行，但执行与证据仍是瓶颈；基准可外部化 |
| D 记忆/技能/上下文 | 14 | 记忆、技能、上下文 | 检索/任务效用/规模条件 | MemGPT、Mem0、A-MEM、HippoRAG、Dynamic Cheatsheet、SoK Skills | 经验一旦持久化就成为攻击面；需要 provenance/taint/撤销 |
| E RSI 治理/评测 | 23 | RSI 证据、安全、形式保证 | 审计、证书、攻击/防御 | RRSI、RSI-Anything、Dream-RSI、Auditing the Product、SAVER、SEVerA | 直接定义我们该补的证据与边界 |

### 2.1 一个重要的术语修正

很多工作把下面四件事都叫“self-improvement”：

1. **self-refinement**：同一轮内改输出（Self-Refine、Reflexion）；
2. **self-training**：用自生成数据改权重（STaR、SEAL、Absolute Zero）；
3. **self-modification**：改 agent 的代码/harness（SICA、DGM、Gödel Agent）；
4. **self-evolution**：改记忆/技能/上下文/流程，并跨任务保留（Voyager、AWM、ACE、ReasoningBank）。

这四类的**证据要求完全不同**：1 只需要任务反馈；2 需要训练/验证分离；3 需要代码沙箱与回归；4 需要持久化状态的可撤销与毒化防护。把它们混成一个“RSI”会掩盖真正的风险。

**我们的仓库落在 3+4 的交集**：改的是检索预算/seed budget（harness 参数），保留的是 ledger/lease/archive；但只消费两个 target，且没有版本化 harness registry。详见 §5。

---

## 3. 时间线：从“自评”到“受治理的 harness 进化”

| 阶段 | 代表工作 | 主要机制 | 主要问题 |
|---|---|---|---|
| 2022–2023 | STaR、Self-Refine、Reflexion、Constitutional AI、PromptBreeder、OPRO、Voyager | 自生成 rationale、自反馈、prompt 进化、技能库 | 自评偏差；无持久治理；单任务 |
| 2024 | SPIN、Self-Rewarding、TextGrad、DSPy、AWM、ExpeL、Gödel Agent、ADAS、AI Scientist、Agent Laboratory | 偏好自博弈、文本梯度、workflow 记忆、agent 搜索、端到端科研 | 训练/评测泄漏；研究自动化缺少执行验证 |
| 2025 | DGM、SICA、Absolute Zero、R-Zero、SEAL、GEPA、ACE、ReasoningBank、AI Scientist v2、PaperBench、RE-Bench、MLGym、MLE-bench | archive + 自改代码、zero-data RL、prompt/context 进化、研究基准 | 过拟合 benchmark；计算成本；hidden 不 sealed |
| 2026 | RRSI、RSI-Anything、Dream-RSI、RSIAgent、RSEA、SIFT、HGM、AIDE²、RSIBench-Data、RSIGym、Auditing the Product、SAVER、SkillJack、SEVerA、SAHOO | 正则化 harness 编辑、world model/replay、held-out selection、judge 预筛、RSI 基础设施、证据审计、安全/形式保证 | 证据仍弱：rerun 少、任务复用、缺少跨域迁移；技能/记忆攻击面 |

**趋势判断 `[我们的判断]`：**

- 研究重心从“模型能不能改自己”转向“**改什么、用什么信号接受、如何证明没有退化**”。
- 2026 年最值得借的不是某个新 agent，而是 **evaluation protocol**：held-out selection、sealed audit、anytime-valid certificate、edit budget、cost accounting。
- 最值得警惕的不是“模型太强”，而是 **评测太弱**：自评、公开 benchmark 污染、任务复用、hidden 泄漏，都会把“改进”变成“过拟合”。

---

## 4. 深读：16 篇直接改变我们设计的论文

### 4.1 DGM：archive 是必要的，但不是充分的

**Darwin Gödel Machine**（[2505.22954](https://arxiv.org/abs/2505.22954)）`[原文]`

- **机制**：agent 修改自身代码，archive 保留多样父代，在沙箱中跑 benchmark；开放-ended 搜索。
- **证据**：作者报告 coding benchmark 提升；有安全沙箱与人工检查。
- **边界**：单域、单类 benchmark；archive 的选择分数仍是任务分数；没有形式保证；计算成本高。
- **可借**：`CandidateArchive`、lineage、负结果保留、父代多样性。
- **不可借**：把 archive 平均分当“改进能力”；我们的 `select_parents` 目前对 hidden metrics 取算术平均，见 §5.3。

### 4.2 HGM：区分“当前分数”与“改进能力”

**Huxley–Gödel Machine**（[2510.21614](https://arxiv.org/abs/2510.21614)）`[原文]`

- **机制**：用树搜索近似“最优自改进机器”，强调 metaproductivity（改进生产率），而不是单点 benchmark 分数。
- **证据**：作者报告 human-level coding agent development；计算昂贵。
- **边界**：需要大量 rollout；metaproductivity 的度量依赖任务分布。
- **可借**：在 `MetaTracker` 里记录“每轮改进带来的后续改进率”，而不只是 mean score。
- **不可借**：把一次 seed-budget 成本下降写成 metaproductivity 提升。

### 4.3 SICA：自改代码的最小闭环

**A Self-Improving Coding Agent**（[2504.15228](https://arxiv.org/abs/2504.15228)）`[原文]`

- **机制**：coding agent 直接编辑自身代码，保留有效修改；单域闭环。
- **证据**：作者报告 benchmark 增益；没有跨域治理。
- **边界**：代码可执行、反馈可计算；科研写作/证据判断没有这么干净的 evaluator。
- **可借**：最小自改闭环、版本化代码、失败回滚。
- **不可借**：把“代码跑分提升”迁移成“科研能力提升”。

### 4.4 SIFT：用 judge 降低候选评估成本

**Self Improvement via Fast Tree-search**（[2609.19526](https://arxiv.org/abs/2609.19526)）`[原文]`

- **机制**：LLM pairwise judge + 正则 Bradley–Terry + 轻量树搜索；昂贵下游评测只留给最有希望的节点。
- **证据**：作者报告在严格预算下提升 coding 性能、样本效率高。
- **边界**：judge 偏差会直接进入搜索；需要 sealed 任务校准； pairwise 偏好不保证绝对正确。
- **可借**：在 public 预筛前加 judge 预筛，降低真实 run 成本；但 judge 不能替代 hidden gate。
- **对我们的直接启示**：我们目前只用 public 指标排序，没有 judge；候选多时成本会线性上升。

### 4.5 RRSI：harness RSI 会过拟合，必须正则化

**RRSI**（[2609.24972](https://arxiv.org/abs/2609.24972)）`[原文]`

- **机制**：限制候选一次能 bundle 的编辑数（temporally annealed budget）；鼓励未探索轨迹；critic 过滤 benchmark-specific 提案；pruner 删除太小/太贵/不再有用的改动。
- **证据**：作者报告缓解 in-distribution 增益在 OOD 上消失的问题。
- **边界**：critic/pruner 仍由模型/规则实现；需要外部验证。
- **可借**：**编辑预算 + critic + pruner**。我们的 candidate patch 目前是自由文本，可以一次改很多；这是 P0 级治理缺口。

### 4.6 RSI-Anything：world model 与 retained pair

**RSI-Anything**（[2610.13912](https://arxiv.org/abs/2610.13912)）`[原文]`

- **机制**：用 predictive world model 指导 action/learning-data selection；observed feedback 驱动 policy 或 workflow 改进，并条件性更新 world model；组件/兼容性检查决定是否保留 policy–model pair。
- **证据**：作者报告 code repair、GUI、lab planning、reaction optimization 的提升；数字为作者口径。
- **边界**：world model 可能随 policy 演化而不可靠；需要 conditional confirmation；跨域迁移未独立验证。
- **可借**：`retained pair` 与 `conditional confirmation` 的对象设计；我们的 ledger 只有 candidate/lease，没有“harness + evaluator + world model”的组合版本。
- **不可借**：把作者报告的 31.2% / 46.01% / 96.15% 当作我们的结果。

### 4.7 Dream-RSI：用历史 discovery tree 做 replay

**Dream-RSI**（[2609.14858](https://arxiv.org/abs/2609.14858)）`[原文]`

- **机制**：把累积的 discovery history 当作 replay simulator，在历史搜索树上低成本评估探索策略，再部署到在线搜索。
- **证据**：作者报告 exploration policy 的改进；仍是作者口径。
- **边界**：simulator 只覆盖已实现的搜索空间；新领域需要新树。
- **可借**：我们的每次 S5 trial 都留下 capsule/metrics；可以构建 **offline replay** 先筛候选，减少真实 run 次数。
- **注意**：replay 不能替代 held-out；它只能降低搜索成本。

### 4.8 RSEA：没有 universal artifact，必须 held-out keep-better

**Recursive Self-Evolving Agents via Held-Out Selection**（[2606.28374](https://arxiv.org/abs/2606.28374)）`[原文]`

- **机制**：维护 imperative strategy / reusable skills / procedural playbook 三层自然语言状态；每代从自身轨迹重写，只有在 disjoint held-out 不回归时才提交（strict keep-better）。
- **证据**：四个 benchmark、六个 faithful baseline（ReAct、Reflexion、GEPA、AWM、ACE、Dynamic Cheatsheet）同 backbone 对比；作者报告 **没有 artifact 普遍获胜**。
- **边界**：held-out 仍来自同一分布；跨域迁移未证明。
- **可借**：**disjoint held-out + strict keep-better**；这比“public 排序后最多两个 finalist”更强。
- **对我们的直接启示**：我们现在的 hidden 任务与 public 任务来自同一批论文/同一数据集，且 hidden 在 repo 里可见；需要真隔离。

### 4.9 自评不可信：SEAL 的外生审计

**Self-Authored Verification Is Unreliable in Heuristic Self-Improving Agents**（[2607.24300](https://arxiv.org/abs/2607.24300)）`[原文]`

- **机制**：指出 agent 同时控制“被优化对象”和“验证器”时，自评分可以虚高；提出 Sealed Exogenous Acceptance Loop（SEAL）：agent 保留自写测试，但接受/拒绝由固定的 harness-side audit 决定，agent 不可见、不可 author；回归时保留整个 incumbent。
- **证据**：作者用实验展示 verifier–deployment gap，以及少量外生信任即可阻止真实回归。
- **边界**：外生审计的覆盖范围有限；审计本身也可能被攻击。
- **可借**：**sealed exogenous acceptance** 应该成为我们 hidden gate 的设计原则，而不是“把 hidden 文件放在 repo 里”。
- **命名冲突**：此 SEAL 与“Self-Adapting Language Models”（[2506.10943](https://arxiv.org/abs/2506.10943)）不是同一个东西；文中需区分。

### 4.10 SEA：anytime-valid certificate

**Self-Evolving Agents with Anytime-Valid Certificates**（[2607.00871](https://arxiv.org/abs/2607.00871)）`[原文]`

- **机制**：把自修改限制在小 steering adapter + 版本化 harness；每次修改通过 anytime-valid gate，输出可审计证书；冻结 base model；用 best-of-N、micro-step search、self-authored reproduction oracle 等提供密集信号。
- **证据**：在 52 个 SWE-bench Verified 子集、四个 base model 上，作者报告 no-op composite 对照下的 +4/+5（GLM 5.2 24→28；GPT 29→34）。
- **边界**：仍是 coding 域；证书只对固定误差预算与任务分布有效；base capability 是主导因素。
- **可借**：**证书格式 + 固定误差预算 + no-op 对照**；我们目前是确定性 pass/fail，没有统计不确定性。
- **对我们的直接启示**：如果要做“能力增益”主张，至少要有 no-op 对照与置信区间；否则只是“某次跑分更高”。

### 4.11 GEPA：反思式 prompt 进化

**GEPA**（[2507.19457](https://arxiv.org/abs/2507.19457)）`[原文]`

- **机制**：用自然语言反思驱动 prompt/程序进化，Pareto 选择；少量 rollout 可超过 RL。
- **证据**：作者报告在多个任务上优于 RL/ prompt 优化基线。
- **边界**：单任务优化；Pareto 选择仍依赖任务分数；没有治理。
- **可借**：Pareto 多目标（质量/成本/覆盖）而不是单一平均分；我们的 archive 选择应改为 Pareto。

### 4.12 ACE：context 也会“自进化”，但会 collapse

**Agentic Context Engineering**（[2510.04618](https://arxiv.org/abs/2510.04618)）`[原文]`

- **机制**：把 context 当作可 grow-and-refine 的 playbook；用增量 delta 避免 brevity bias 与 context collapse；不训练权重。
- **证据**：作者报告在 agent/domain 任务上提升；context 可复用。
- **边界**：playbook 由模型自编辑，错误会累积；需要外部验证与版本回滚。
- **可借**：我们的 `knowledge`/`process` 候选可以做成版本化 playbook；但必须有 provenance、去重、失效条件。
- **注意**：ACE 的“context collapse”与“model collapse”不是同一概念；前者是上下文退化，后者是训练分布崩溃。

### 4.13 ReasoningBank / AWM / ExpeL：经验记忆的三条路线

- **ReasoningBank**（[2509.25140](https://arxiv.org/abs/2509.25140)）`[原文]`：把成功/失败推理写成可检索 memory；质量决定上限。
- **AWM**（[2409.07429](https://arxiv.org/abs/2409.07429)）`[原文]`：从轨迹归纳可复用 workflow；web agent 场景。
- **ExpeL**（[2308.10144](https://arxiv.org/abs/2308.10144)）`[原文]`：跨任务提取 insight，推理时检索；不改权重。
- **共同问题**：记忆是“经验”不是“证据”；没有 provenance 的记忆会把一次偶然成功放大成通用规则。
- **对我们的启示**：`knowledge` 候选必须区分“经验/协议/证据”，并带 scope、失效条件、撤销路径。

### 4.14 AI Scientist v2 / Agent Laboratory：端到端科研自动化的真实边界

- **AI Scientist v2**（[2504.08066](https://arxiv.org/abs/2504.08066)）`[原文]`：agentic tree search，workshop-level 自动发现；仍有大量人工与算力。
- **Agent Laboratory**（[2501.04227](https://arxiv.org/abs/2501.04227)）`[原文]`：多角色研究助手，人在环；偏 assistant。
- **PaperBench**（[2504.01848](https://arxiv.org/abs/2504.01848)）`[原文]`：论文复现 benchmark，rubric + 专家评分；任务重。
- **RE-Bench**（[2411.15114](https://arxiv.org/abs/2411.15114)）`[原文]`：8 个 ML 研究工程任务，对比人类专家；考察长程执行。
- **对我们的启示**：我们的 S1→paper 是**结构纵切**，不是“自动科研”；ChemLab 是**协议验证**，不是 research benchmark。要证明科研能力，必须接外部基准或做真实研究任务。

### 4.15 Auditing the Product：RSI 证据的“体检报告”

**Auditing the Product, Not the Recursion**（[2610.27610](https://arxiv.org/abs/2610.27610)）`[原文]`

- **机制**：对 114 项 eligible 研究做全文编码（其中 90 项自称 RSI），把“产品主张”与“过程主张”分开；编码 claim 与 evaluation design。
- **关键数字**：90 项 RSI 研究中，**22%** 审计了完整循环 ≥2 次重跑；**60%** 在未参与选择的任务上评估；人工编码随机样本中分别为 **14%** 与 **45%**。
- **对我们的直接命中**：我们目前只有 **1 次** seed-budget trial + 1 次 sealed confirmation；没有两次完整循环重跑；hidden 任务参与设计且可见。
- **可借**：把“过程证据”做成一张固定表：候选数、finalist 数、public/hidden 分离、选择是否用 hidden、重跑次数、成本、回归、人工签核。
- **不可借**：把“结构闭合”当“过程证据”；closure 11/11 只证明对象接线，不证明改进。

### 4.16 安全：从单次失败到“演化安全”

- **Safety in Self-Evolving Agents: A Survey**（[2610.00093](https://arxiv.org/abs/2610.00093)）`[原文]`：提出 SAVER（Substrate / Adaptation / Violation / Exposure / Response），核心是“经验变成可复用状态后，安全属性能否跨积累/复用保持”。
- **Evolutionary Safety of RSI**（[2609.31186](https://arxiv.org/abs/2609.31186)）`[原文]`：六类演化风险、五域分类；风险会跨更新累积、传播到后继系统。
- **SkillJack**（[2608.03509](https://arxiv.org/abs/2608.03509)）`[原文]`：中毒经验可被 agent 自己转成持久技能，绕过上下文清洗；技能库是新的攻击面。
- **Layered Mutability**（[2604.14717](https://arxiv.org/abs/2604.14717)）`[原文]`：预训练/对齐/自我叙事/记忆/权重五层；治理难度随速度、耦合、不可逆性、可观测性变化。
- **对我们的启示**：我们的 immutable surfaces 只覆盖 claim/evidence/gate/rubric/export/signature/authorship；**没有覆盖 memory/skill/tool 的持久化与供应链**。如果未来接真实 skill runtime，必须先做 provenance、签名、测试、撤销与毒化扫描。

---

## 5. 对照我们的仓库：哪些是“真”，哪些是“结构”

### 5.1 准确定位

用 GAI 的两个维度（[2609.13406](https://arxiv.org/abs/2609.13406)）看：

| 维度 | 我们的现状 | 结论 |
|---|---|---|
| 改进机制是否属于 agent | 候选由人/规则/本地 frozen proposer 提出，**人签准入** | 改进机制在系统外，不是自治 RSI |
| 评价标准是否外生 | public/hidden 任务 + 人签 + closure gate；但 hidden 在 repo 可见 | 评价标准部分外生，**隔离不足** |

因此更准确的说法是：

> **一个受治理的科研 harness 改进控制面：在冻结模型与外部证据下，让“改检索预算/执行预算/流程协议”的候选经过 dry-run、public/hidden 评测、人签租约与 sealed 复核；它不是 autonomous RSI，也不产生能力主张。**

这一定位与 [2607.07663](https://arxiv.org/abs/2607.07663) 的 bounded self-refinement 更接近；与 [2610.13912](https://arxiv.org/abs/2610.13912)、[2609.24972](https://arxiv.org/abs/2609.24972) 的 harness RSI 是同一问题域，但证据强度低得多。

### 5.2 现有机制（代码事实）

- `research_agent/rsi.py`：`Candidate`（kind/target/patch/rationale/predicted）、`EvalEvidence` 四 split、`StepLedger`、`Lease`、`MetaTracker`、`CandidateArchive`、`trace_research`。
- `research_agent/rsi_fixture.py`：fixture 评测、public 排序后最多两个 finalist、TTL/scope、去重、默认 pending。
- `research_agent/real_eval.py`：4 篇 CC-BY 正文的 BM25/MiniLM 检索评测；`resolve_active_harness` 只解析 `literature.retrieval.budget`。
- `research_agent/s5_eval.py`：seed-budget 5/4/3/2；`resolve_s5_seed_policy`；`run_s5_trial`。
- `research_agent/modules/run.py`：iris/breast_cancer/ChemLab run → RunCapsule/EA → 人签 claim。
- `research_agent/pipeline.py`：S1→S3→S4→S5(optional)→S6→S8–S12；`--use-lease` 消费 S1 budget；`--use-s5-lease` 消费 S5 seeds。
- `research_agent/runtime/`：FastAPI + SSE + artifacts + 只读 RSI；无 approve/claim/sign 端点。
- 前端三套：`research_agent/web/`（模块工作台）、`site/`（单屏产品壳）、`site/live/`（真实 runtime）。

### 5.3 关键缺口（按严重度）

| 级别 | 缺口 | 代码/证据 | 为什么严重 |
|---|---|---|---|
| P0 | S5 的 hidden/near-OOD/regression 不是真 held-out | `s5_eval.py` 的 `TASKS` 只是不同 `test_size`；ChemLab 所有 split 都在同一固定 test CSV 上评估（`run.py` 的 `_execute_chemlab`）；iris/breast_cancer 的不同 `test_size` 还会造成 test 集重叠 | 四道门看起来齐全，实际是在同一分布/同一测试集上重复测量；hidden 泄漏会系统性高估 |
| P0 | hidden 任务没有 sealed | `research_agent/rsi_fixtures/real_tasks.json` 在 repo 中可见；候选/agent 可读；没有 hash commitment 或独立进程 | 自评/自选会过拟合；与 [2607.24300](https://arxiv.org/abs/2607.24300) 的 verifier–deployment gap 同类 |
| P0 | 只有 1 次完整循环 | `rsi-chemlab-v2/ledger.json` 有 1 个 approved + 1 个 confirmation；没有 2 次 full-loop rerun |  [2610.27610](https://arxiv.org/abs/2610.27610) 的 22% 门槛都未达到；无法区分噪声与改进 |
| P0 | candidate 只检查 target 子串，不检查 patch 语义 | `rsi.py` `GovernancePolicy.check` 只对 `target` 做 `surface in target`；patch 是自由文本 | 可以把“改 claim/gate”的内容藏进 patch/rationale；不可变 surface 不是形式保证 |
| P0 | 只消费 2 个 target | `real_eval.resolve_active_harness` 只接受 `literature.retrieval.budget`；`s5_eval.resolve_s5_seed_policy` 只接受 `experiment.run.seeds` | `process/prompt/knowledge` 候选即使有 lease 也不会被运行时加载；自进化链是“半 inert” |
| P0 | `trace_research` 只验证 seed budget | `rsi.py` 的 `checks["seed_budget_applied"]` 只在 target 为 `experiment.run.seeds` 时执行；S1 harness lease 没有“retriever/budget 实际应用”校验 | 无法证明 lease 真的进入了研究执行 |
| P1 | `admit` 只强制 public+hidden；near-OOD/regression 可选 | `rsi.py` `admit` 签名；`_claimable` 只要求 present evals 都 claim_eligible | 可选门会被跳过；`capability_claims` 可能在没有 cross-domain/regression 时出现 |
| P1 | `closure.check` 是结构检查，不是身份/签名验证 | `closure.py` 只查 status/refs/hash；`all_slots_bound` 只查是否 pending | 手工编辑 JSON 可通过；没有签名者身份、时间戳、吊销状态 |
| P1 | `paper.status` 永远 `needs_evidence`，pipeline 永远 `needs_human` | `modules/paper.py`；`pipeline.py:430` | 即使所有槽位 bound、closure ready，pipeline 仍显示 needs_human；状态语义不准确 |
| P1 | 前端曾把跨任务 RSI 台账与跨臂指标并排展示 | `web/app.js` 的 KPI/面板；`site/live` 的 MODE | 读者会把 ChemLab 的 0.144 当作当前任务结果；已在本轮修复（arm ledger + scope banner） |
| P1 | 静态快照没有“as-of”时间 | `web/data/*.json`、`tasks.json` | 数据可能过期；读者无法判断是哪次 run |
| P1 | 没有 cost ledger / stale 传播 / ChangeSet | 设计文档有，代码无 | 无法证明“更低成本”与“失效后重闭合”；RWMT 主线未落地 |
| P2 | 没有 peer-review / research benchmark | 只有 4 篇 CC-BY、ChemLab/iris | 不能声称科研能力；只能声称协议验证 |
| P2 | 没有 skill runtime 的供应链防护 | skill 相关只有静态 manifest/文档 | 与 [2608.03509](https://arxiv.org/abs/2608.03509) 的攻击面相比几乎裸奔 |

> 说明：本轮已修复 `run` 模块的 EA scope 推导与 claim scope 一致性（`run.py:_dataset_scope` / `claim`，SPEC v0.2.1），并修复前端跨臂/跨任务展示；其余缺口保留为反思与路线，不在本轮扩大改动。

### 5.4 这对论文主张意味着什么

**可以写：**

- 一个受治理的 harness 改进控制面：候选、dry-run、public/hidden、人签 lease、撤销、sealed 复核、trace；
- 一个可复现的本地证据链：RunCapsule → EA → 人签 Claim → paper slot → ProtocolCard/DataCite → closure 11/11 → signed manifest；
- 一个诚实的负结果：BM25 budget2/3 被 near-OOD 拒绝；ChemLab seeds3 因 public 损失被拒；模型提案对 prompt 敏感；
- 一个工程差异：SPEC/artifact/gate、scope 绑定、只读 runtime、臂级 UI。

**不能写：**

- “已实现 RSI / self-improving / 越跑越强”；
- “能力提升 / 通用迁移 / SOTA”；
- “11/11 closure = 同行评审通过 / 可投稿”；
- “ChemLab R² = 科研发现”；
- “hidden/near-OOD/regression 已证明泛化/抗遗忘”；
- “LLM proposer 可靠”；它只是不可信输入，3-prompt 审计只有 1/3 eligible。

---

## 6. 改进路线：从“控制面原型”到“可审计的 harness 改进”

### P0（下一轮必须做，否则不要对外说“自进化”）

1. **真 held-out 协议**
   - S1：文档级 split（public/hidden 用不同论文），near-OOD 用不同主题/不同会议，regression 用旧任务；不要同一批 4 篇论文换问题。
   - S5：ChemLab 的 public/hidden/near-OOD/regression 必须用不同反应/不同 scaffold/不同数据切片；不能所有 split 共用同一 test CSV。
   - iris/breast_cancer：用不同数据子集/不同 seed 划分，保证 test 不重叠；或者明确降级为“sample-size robustness”而不是 hidden/OOD。
   - 验收：一个测试能证明四个 split 的测试样本交集为空；报告每个 split 的 n 与置信区间。

2. **sealed evaluator**
   - hidden 任务不放在 agent 可读的 repo 路径；用 hash commitment + 独立进程/独立用户；候选只能拿到 accept/reject 与聚合指标。
   - 验收：agent 运行环境中 `real_tasks.json` 不可读；hidden artifact 的 hash 在运行前已承诺；运行后不可改。

3. **两次完整循环重跑 + no-op 对照**
   - 同一 candidate 走两次完整 `propose→dry-run→public→hidden→admit→consume→confirm`；第二次使用未参与选择的任务。
   - 加 no-op composite 对照（只重跑 incumbent，不改 harness），报告差值、CI、成本。
   - 验收：`rsi` ledger 有 ≥2 个 full-loop episode；报告有 no-op 基线；不是只报“最好一次”。

4. **结构化 candidate/patch**
   - `Candidate` 增加 `patch_schema`（允许字段、类型、范围）；禁止在 patch 中出现 `claim/evidence/gate/rubric/export/signature` 的写操作；dry-run 校验语义，不只校验 target 子串。
   - 验收：构造一个 target 合法但 patch 试图改 gate 的候选，必须被拒绝；测试锁定。

5. **closure 的槽位类型校验**
   - `all_slots_bound` 改为逐槽期望状态：method.protocol=bound_protocol、result.primary=bound_claim、result.figure=bound_figure、limitation=bound_scope、citation.related=bound_bibliography；缺一不可。
   - 验收：把 method.protocol 改成 bound_claim 的 JSON 必须 fail。

6. **前端臂级/任务级语义**
   - 已完成：workbench 的 `EVIDENCE ARMS`、`MIXED ARMS`、RSI scope banner；live 的 `MIXED ARMS` + 8 项结果事实。
   - 下一步：加 `as-of` 时间、数据来源文件、claim/EA scope 的 tooltip。

### P1（形成可复现实验）

7. **Harness registry / loader**
   - 把 retriever、parser、prompt、process、预算做成 `HarnessVersion`（id、version、config、sha256、scope）；lease 选择 version；pipeline/run 从 registry 加载，而不是 if/else。
   - 验收：`trace_research` 能验证“实际加载的 harness version == lease 的 version”，不只验证 seeds。

8. **Archive 选择改为 Pareto + 编辑预算**
   - 不再对 hidden metrics 取算术平均；按质量/成本/覆盖/回归四个目标做 Pareto；加 `max_edits`、`critic`、`pruner`（借 RRSI）。
   - 验收：构造两个候选，一个质量高但成本高、一个质量略低但成本低，archive 能保留两者而不是被平均值吞掉。

9. **Memory/skill 治理**
   - provenance、taint、trust level、签名、测试、撤销传播；技能包要有 `tests/dry_run` 与 `permissions`。
   - 验收：一个“中毒经验”进入 skill 候选时，dry-run/测试能阻断；撤销后依赖 artifact 进入 stale。

10. **Stale/ChangeSet**
    - claim → sentence → figure 的失效传播；变更后重跑/重写/复核；closure 重新打开。
    - 验收：改一个 EA/claim 后，相关 result.figure 与 sentence 进入 stale，导出 blocked。

### P2（外部效度）

11. **接外部 benchmark**：PaperBench（复现）、RE-Bench（AI R&D）、MLGym/MLE-bench（研究工程）、ScienceAgentBench/CORE-Bench（数据/复现）。先做一个，不要全接。
12. **多轮 AIDE² 式循环**：8 天/7 次改进是作者口径；我们至少做 2 轮，记录成本与回归；不要追求“轮数”。
13. **统计证书/漂移监控**：anytime-valid gate、GDI/回归风险（SAHOO）、sealed confirmation；报告 CI 而不是单点。
14. **经济学**：记录 token/GPU/人工时长；报告“每减少 1 单位成本带来的质量变化”；不要把成本下降写成能力提升。

---

## 7. 100 篇中最值得先读的 20 篇

| # | 论文 | 为什么先读 |
|---|---|---|
| 1 | DGM（2505.22954） | archive + 自改代码的基准；理解“开放-ended”的代价 |
| 2 | HGM（2510.21614） | 区分当前分数与 metaproductivity |
| 3 | SICA（2504.15228） | 最小自改闭环 |
| 4 | SIFT（2609.19526） | judge + 树搜索降低评估成本 |
| 5 | RRSI（2609.24972） | 编辑预算/critic/pruner，直接可借 |
| 6 | RSI-Anything（2610.13912） | retained pair / world model / conditional confirmation |
| 7 | Dream-RSI（2609.14858） | replay simulator，降低真实 run 成本 |
| 8 | RSEA（2606.28374） | 没有 universal artifact；held-out keep-better |
| 9 | Self-Authored Verification（2607.24300） | 自评不可信；sealed 外生审计 |
| 10 | SEA（2607.00871） | anytime-valid certificate + no-op 对照 |
| 11 | GEPA（2507.19457） | 反思式 prompt 进化 + Pareto |
| 12 | ACE（2510.04618） | context/playbook 自进化与 collapse |
| 13 | ReasoningBank（2509.25140） | 经验记忆的质量瓶颈 |
| 14 | AI Scientist v2（2504.08066） | 端到端科研的真实边界 |
| 15 | Agent Laboratory（2501.04227） | 人在环研究助手 |
| 16 | PaperBench（2504.01848） | 复现 benchmark 的设计 |
| 17 | RE-Bench（2411.15114） | AI R&D 与人类专家对比 |
| 18 | AIDE²（2609.26457） | 8 天/7 次改进的多轮闭环 |
| 19 | Auditing the Product（2610.27610） | 114 项研究的证据体检；我们的镜子 |
| 20 | Safety in Self-Evolving Agents（2610.00093） | 经验持久化后的安全框架 |

> 完整 100 篇（含每篇的优化对象、反馈信号、读点、与本仓库关系）见 [`research/self-evolution-100/catalog.md`](research/self-evolution-100/catalog.md)。

---

## 8. 不可宣称与待补证据

- **未复现**：100 篇均为摘要/公开材料级阅读；所有效果数字是作者口径。不能把 RSI-Anything 的 31.2%、SEA 的 +4/+5、AIDE² 的 7 次改进写成我们的结果。
- **未做 peer-review benchmark**：PaperBench/RE-Bench/MLGym 等只是“应该接”的外部基准，我们尚未运行。
- **未做两次完整循环**：当前只有 1 个 approved episode + 1 个 sealed confirmation；不能写“越跑越强”。
- **未做真 held-out**：hidden/near-OOD/regression 的语义与隔离不足；不能写“泛化/抗遗忘”。
- **未做身份/签名**：closure sign 是本地 JSON 记录，不是密码学签名；不能写“不可抵赖”。
- **未做真实科研发现**：ChemLab 是 baseline 协议验证；4 篇 CC-BY 是检索 probe；不能写“科研能力”。

---

## 9. 关键来源

- 百篇书目：[`research/self-evolution-100/bibliography.json`](research/self-evolution-100/bibliography.json)
- 百篇目录：[`research/self-evolution-100/catalog.md`](research/self-evolution-100/catalog.md)
- 本仓库全量技术反思：[`28-仓库全量技术反思-从证据链到受治理Harness.md`](28-仓库全量技术反思-从证据链到受治理Harness.md)
- 既有设计文档：`10-`（RSI 反思）、`11-`（自进化循环）、`12-`（RSI-Anything 深读）、`23-`（开源对照）、`25-`（受治理 RSI）、`26-`（免训练 RSI）。

*本文档只做调研与设计判断，不是实验结果，也不构成对外能力声明。*

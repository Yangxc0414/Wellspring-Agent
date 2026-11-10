# 科学智能体（Scientific Agents / AI Scientist）Literature Review
## 组会汇报版 · 2026-10-17

> 配套文件：
> - 逐篇论文卡片：[`papers/01`](papers/01-T1-文献检索与关系推理.md)、[`02`](papers/02-T2-假设生成与探索.md)、[`03`](papers/03-T3-实验执行与仪器.md)、[`04`](papers/04-T4数据分析-T5评审-T6复现.md)、[`05`](papers/05-T7端到端与L2系统组织.md)、[`06`](papers/06-L3基础设施与工程生态.md)
> - 文献树：[`trees/01-literature-tree.md`](trees/01-literature-tree.md)
> - 挑战—洞察树：[`trees/02-challenge-insight-tree.md`](trees/02-challenge-insight-tree.md)
> - 配图与预览：[`figures/preview.html`](figures/preview.html)（图 1 研究框架、图 2 CALM 方法；PPTX 可编辑）
>
> 证据标记：`[已核验]` 元数据经 arXiv/期刊核对；`[部分核验]` 会议/数字未独立核对；`[公司报告]` 未同行评审；`[未验证]`/`[未找到]` 本轮未定位；`[推测]` 本文判断。

---

![图 1 · 科学智能体研究框架](figures/fig1-survey-framework.png)

> **图 1 · 科学智能体研究框架**：四段式领域地图——I 为 T1–T7 任务能力（代表系统，非首篇、非穷举）；II 为 L2 系统组织与 L3 基础设施，分两行全宽排布并与 III 的左栏对齐；III 为文献能力、系统组织、验证闭环三条演化主线，判断验证线最缺（→ D1 · D2 · D6）；IV 为 D1–D6 优先方向，CALM 以 `τ → 候选 → 阶梯 → z → 答 / 弃` 定位在 D2「失败归因」，只归因不修复。层间箭头只表示“组织为 L2 · 依赖 L3”，演化链表示代表性演进而非旧形态消失，均不表示逐卡映射；D 的编号顺序不等于优先级，优先级见图内排序行（D1 ≈ D2 > D3 > D4 > D6 > D5）。可编辑源文件：[PPTX](figures/fig1-survey-framework.pptx) · [SVG](figures/fig1-survey-framework.svg) · [PDF](figures/fig1-survey-framework.pdf)。图幅 16:9，PPTX 内最小辅助字为 6 pt，A4 打印偏小，建议 A3 或屏幕使用。

---

## 0. 一页结论（先看这 8 条）

1. **领域已经越过“能不能端到端”的门槛。** 2024–2026 年出现了 AI Scientist（Nature 2026）、AI Scientist-v2、Co-Scientist（Nature 2026）、Virtual Lab（Nature 2025）、Robin（Nature 2026）、Kosmos、Denario、AutoResearchClaw 等完整系统；“想法→实验→论文”不再是空白。`[已核验/部分核验]`
2. **但“端到端”不等于“科学正确”。** PaperBench 上最强系统复现完成度仅约两成；Denario 自报约 17% 生成内容数学错误或编造、仅约 10% 产出被判断为“有趣”；AI idea 的个体新颖性可以高于人类，但群体多样性显著更低。**验证层是当前真正的瓶颈。** `[原文]`
3. **研究重心正在从“生成”转向“验证与记忆”。** 2025–2026 的新工作集中在：复现评测（PaperBench/REPRO-Bench）、过程评测（MLR-Bench）、证据核验（AutoResearchClaw 四层引文核验）、自进化验证（ScienceClaw 三重门槛）、世界模型记忆（Kosmos）、工具生态（ToolUniverse）。`[已核验]`
4. **三条技术演化主线已经清晰**：① agentic RAG → 自反馈引用校验；② 线性流水线 → 实验树搜索 → 结构化世界模型；③ 单 agent → 多角色组织 → 集体科研平台。`[已核验/推测]`
5. **大部分论文属于 4 类 novelty（给已有 pipeline 加模块）**；1 类（新 milestone task）集中在评测与基础设施，2 类（新 pipeline）集中在端到端系统。**如果我们的工作只是“再加一个 agent/模块”，很难跳出 4 类。**
6. **最大的六个空白**：证伪优先的科研 agent、想法多样性作为优化目标、失败归因与负面结果复用、跨系统证据账本（provenance）、科研专用自治刻度 + 验证义务、湿实验 sim2real 基准。`[推测，基于本轮语料]`
7. **最适合作为组内第一个方向的是 D1（证据账本）与 D2（失败归因）**：它们不依赖昂贵湿实验，能直接复用现有 benchmark，且天然是 1 类/2 类 novelty。**D3（多样性约束构思）最容易做出第一篇论文**。`[推测]`
8. **不建议再做的事**：再做一个端到端论文生成 pipeline、再做一个多 agent 角色扮演系统、再做一个通用工具调用 agent、再做一个没有新任务的 RAG/综述 benchmark。这些已经有强基线，且审稿人会按 4 类看待。`[推测]`

---

## 1. 范围、方法与证据等级

### 1.1 收集范围
- 组内初稿列出的约 60 条论文/系统 + 9 个 GitHub 项目。
- 补充检索：arXiv API、Nature/ICML/ICLR/NeurIPS/ACL/EMNLP 页面、项目主页。
- 主题范围：科学智能体的任务能力（检索、构思、实验、分析、评审、复现、写作）、系统组织（端到端、多 agent、自治、编排）、基础设施（评测、记忆、自进化、安全、工具/环境）。

### 1.2 阅读深度
按 `paper-reading` skill 的分层：
- **Careful（精读）**：约 30 篇核心论文——读摘要、引言、方法、主实验、局限；提取五字段（全名/作者/出处/年份、动机、挑战、技术贡献、讨论）。
- **Skim（泛读）**：约 20 篇——读摘要、图表、结论，用于树定位。
- **未进入精读**：无法核验的条目，单列“未验证分支”，不进入主树。

### 1.3 证据等级与限制（必须说明）
- 本报告**没有复现任何一篇论文**；所有“有效/无效”判断基于论文自报结果、摘要与领域常识。
- “首篇/最早”是**本次已核验语料内**的判断，不是历史绝对第一；已在树中标注前驱与争议。
- 部分 2026 年条目非常新（SwarmRSI、ScienceClaw、EinsteinArena），未经同行评审；Kosmos 只有公司报告。
- 组内初稿的若干元数据有误，已在 §10 单列修正；**汇报时请以修正后的为准**。

---

## 2. 领域全景：数字与结构

### 2.1 语料统计（近似）
| 维度 | 数量 | 说明 |
|---|---|---|
| 进入主树的论文/系统 | 约 45 | 去重后；含 1 个公司报告、少量预印本 |
| 已核验元数据 | 约 40 | 37 篇 arXiv 原始元数据 + 4 篇期刊-only（SciToolAgent、X-ray、Virtual Lab、Robin） |
| 部分核验 | 4 | 会议/数字未独立核对 |
| 未验证/未找到 | 20+ | 组内初稿条目，单列 |
| 工程生态项目 | 9 | GitHub，非论文 |
| 1 类 novelty（新 task） | 约 25 个贡献点 | 评测与任务定义为主 |
| 2 类 novelty（新 pipeline/representation） | 约 30 个贡献点 | 端到端、RAG、多 agent、记忆 |
| 3 类 novelty（新 module） | 约 20 个贡献点 | 引用校验、Elo、树搜索、世界模型等 |
| 4 类 novelty（加模块改进） | 约 15 个贡献点 | 大量工程系统属此类 |

> 注：一篇论文常跨类；上表按“贡献点”归类，不做精确加总，也不等于论文数。

### 2.2 三条演化主线
1. **文献能力线**：单轮 RAG → agentic RAG（PaperQA2）→ 开放模型+自反馈（OpenScholar）→ 关系感知评测（SciNet）→ 开放众评（SciArena）。
2. **系统组织线**：线性四阶段（AI Scientist）→ 实验树搜索（v2）→ 结构化世界模型（Kosmos）→ 跨 run 记忆 + 自愈（AutoResearchClaw）；单 agent → AI PI 组会（Virtual Lab）→ 辩论/Elo（Co-Scientist）→ 专用 agent 分工（Robin）→ 集体平台（EinsteinArena）。
3. **验证线**：终态 rubric（PaperBench）→ 任务级执行+成本（ScienceAgentBench）→ 过程评测（MLR-Bench）→ 统一 harness（AstaBench）→ 验证驱动沉淀（ScienceClaw）。

**读法**：第一条线解决“知道什么”，第二条线解决“怎么组织长程工作”，第三条线解决“凭什么相信”。当前第一条和第二条已相对拥挤，第三条最缺。

---

## 3. Literature Tree（摘要）

> 完整树见 [`trees/01-literature-tree.md`](trees/01-literature-tree.md)。这里只给组会要讲的骨架。

### 3.1 1 类 novelty：已经被定义出来的 milestone task
- **文献**：关系感知检索评测（SciNet）、高精度文献综合（PaperQA2）、开放式科研众评（SciArena）。
- **构思**：文献接地的研究构思（ResearchAgent）、想法新颖性/多样性评测（Si et al.）、长时程假设搜索（AutoDiscovery，未验证）。
- **执行**：闭环基因扰动（BioDiscoveryAgent）、多工具编排（SciToolAgent）、真实仪器自主实验（AI X-ray Scientist）、自主化学实验（AutoLabs）。
- **分析**：ML 工程评测（MLE-bench）、数据科学 agent（DS-Agent）、多步发现评测（DiscoveryBench）、科研级代码（SciCode）。
- **评审/复现/写作**：评审过程仿真（AgentReview）、拟人评审（DeepReview）、从零复现（PaperBench）、社科可复现（REPRO-Bench）、端到端 AI 研究（AI Scientist）。
- **系统/基础设施**：多 agent 人机协同（Virtual Lab）、研究环境（MLGym）、集体平台（EinsteinArena）、任务级评测（ScienceAgentBench）、开放式过程评测（MLR-Bench）、工具生态（ToolUniverse）、自进化评测（ScienceClaw）、科研安全（SafeScientist）。

**关键判断**：真正被反复研究的 milestone 只有四个——**文献综合、端到端研究、复现、评测**。其余任务大多只有 1–3 篇论文，属于“定义出来了但还没形成社区”。

### 3.2 2 类 novelty：代表性 pipeline/representation
- **Agentic RAG**（PaperQA2）→ 开放模型+自反馈（OpenScholar）。
- **线性四阶段**（AI Scientist）→ 树搜索（v2）→ 世界模型（Kosmos）→ 自愈+跨 run 记忆（AutoResearchClaw）。
- **多角色组织**：AI PI+组会（Virtual Lab）、生成/反思/Elo（Co-Scientist）、五专用 agent（Robin）。
- **工具/环境**：工具 KG+安全审查（SciToolAgent）、工具 schema 生态（ToolUniverse）、Gym 接口（MLGym）。
- **评测**：rubric+复现（PaperBench）、统一 harness（AstaBench）、过程评测（MLR-Bench）。
- **记忆/技能**：技能树（SkillFoundry）、论文→agent（Paper2Agent）、三重验证沉淀（ScienceClaw）、集体记忆（EinsteinArena）。

### 3.3 3 类与 4 类的分界
- **3 类**：模块本身可插拔、且论文核心贡献是模块——如 Elo 假设锦标赛、VLM 图表审阅、结构化世界模型、四层引文核验、技能树维护、三重验证门槛。
- **4 类**：给已有 pipeline 加模块——如 OpenScholar 给 agentic RAG 加自反馈、Denario 把 AI Scientist 模块化、AutoResearchClaw 给线性流水线加自愈/记忆/核验、ScholarPeer 给 DeepReview 加上下文与多 agent。

**组会提醒**：4 类工作并非“低价值”，但**审稿人会问“去掉你的模块，基线还成立吗？”**；必须有强消融或新评测支撑，否则容易被归为增量工程。

---

## 4. Challenge → Insight Tree（摘要）

> 完整树见 [`trees/02-challenge-insight-tree.md`](trees/02-challenge-insight-tree.md)。

### 4.1 五个“元 insight”
本轮语料里真正可复用的解决思路只有五类：
1. **外部记忆/世界模型**：把“当前相信什么、还缺什么”从上下文里拿出来（Kosmos、Chain of Ideas、AutoSci）。
2. **证据绑定**：每个 claim 绑定到文献段落/工具结果/代码执行（PaperQA2、OpenScholar、AutoResearchClaw）。
3. **验证门槛**：只有通过复现/跨任务/科学约束验证的产物才允许沉淀（ScienceClaw）。
4. **环境接口**：用统一 schema/Gym/MCP 把工具与环境变成可组合对象（ToolUniverse、MLGym）。
5. **人机权限**：用自治等级、审批、置信度暂停控制风险（Feng et al.、AutoResearchClaw）。

其余 insight（Elo、辩论、arena、虚拟装置、技能树）多是任务专用技巧，迁移性有限。

### 4.2 最尖锐的三个未解矛盾
- **C2 失败不可归因**：现有“自愈”多是把代码跑通，不是把科学错误找出来；没有失败归因 benchmark。
- **C4 想法趋同**：系统优化单条 idea 的 novelty，却没有优化整个 idea 组合的 coverage；共享/辩论还可能加速趋同。
- **C6 证据不可审计**：每个系统各记各的日志；没有跨系统的 provenance 本体，导致复现、归因、责任划分都做不到。

---

## 5. 什么问题别人已经做过了（不要重复）

| 已被做过的方向 | 代表工作 | 为什么不要再做 | 还能怎么差异化 |
|---|---|---|---|
| 端到端“idea→实验→论文” | AI Scientist/v2、Denario、Agent Laboratory、AutoResearchClaw | 已有强基线，且 Nature 级系统在前 | 做验证层/失败层/审计层，而不是更长 pipeline |
| 多 agent 角色分工 | Virtual Lab、Co-Scientist、Robin、AgenticSciML | 角色设计已饱和，缺的是“协作是否真的更科学”的证据 | 做协作协议的对照实验与理论分析 |
| 工具调用/工具 KG | ToolUniverse、SciToolAgent、MLGym | 生态与标准已有人做 | 做工具质量认证、跨域协议、工具级 provenance |
| Agentic RAG/引用校验 | PaperQA2、OpenScholar、AutoResearchClaw | 引用存在性校验已较成熟 | 做证据可靠性、断章取义检测、图表/数据核验 |
| 复现 benchmark | PaperBench、REPRO-Bench、ScienceAgentBench | 任务级复现已有人做 | 做过程级、长周期、失败恢复评测 |
| 评审 agent/仿真 | AgentReview、DeepReview、ScholarPeer | 评审生成已多 | 做评审校准、跨论文一致性、治理 |
| 假设排序（Elo/辩论） | Co-Scientist | 相对排序已有人做 | 做多样性约束、可证伪性排序 |
| 通用自治五级 | Feng et al.、CSA | 概念已提出 | 做科研专用刻度 + 验证义务 |
| 技能库/自进化 | SkillFoundry、ScienceClaw、AutoResearchClaw | 2026 年已密集出现 | 做统一记忆本体、负迁移、安全边界 |
| 集体科研平台 | EinsteinArena | 平台形态已出现 | 做防趋同、失败传播、跨域 verifier |

---

## 6. 什么问题没被做（机会清单）

> 按“空白程度 × 可做性 × 影响力”排序。前四项是我认为最值得在组会上提出的。

| 排名 | 空白 | 为什么是空白 | 现有最接近 | 可做性 |
|---|---|---|---|---|
| 1 | **跨系统证据账本（Evidence Ledger）** | Kosmos 只做单系统逐句溯源；AutoResearchClaw 只做引文核验；没有统一 provenance 本体 | Kosmos、AutoResearchClaw VerifiedRegistry | 高（纯软件，可复用现有 benchmark） |
| 2 | **失败归因与负面结果复用** | 自愈执行器只修代码；没有“科学失败”归因 benchmark；失败经验不跨任务传播 | AutoResearchClaw self-healing、EvoMap 负结果保留 | 高（可用现有失败日志） |
| 3 | **想法多样性/覆盖度作为目标** | 现有系统优化单条 idea；Si et al. 只测量未解决；共享平台可能加剧趋同 | Si et al.、Co-Scientist、EinsteinArena | 中高（可用专家小规模评测） |
| 4 | **科研专用自治刻度 + 验证义务** | 通用五级不区分读文献/跑代码/湿实验/投稿；无“自治度↑则验证义务↑”的规范 | Feng et al.、AutoResearchClaw HITL | 高（概念+实证可做） |
| 5 | **湿实验 sim2real 基准** | 只有单装置虚拟光束线；没有标准仿真环境与迁移协议 | AI X-ray Scientist、BioDiscoveryAgent 模拟器 | 低（需要实验室/装置合作） |
| 6 | **过程级/月级长周期评测** | 现有 benchmark 多为小时级、终态评分 | MLR-Bench、AstaBench、ScienceAgentBench | 中（标注成本高） |
| 7 | **证伪优先的科研 agent** | 没有把可证伪性作为一等约束的公开论文 | PaperBench/REPRO-Bench 只做复现 | 中高（可定义新 task） |
| 8 | **AI 贡献归因与投稿政策技术方案** | 只有政策讨论，无技术系统 | 无 | 中（跨学科，需治理合作） |
| 9 | **科研记忆/技能统一本体** | 文献链、世界模型、信念分布、技能库四类记忆互不兼容 | Kosmos、SkillFoundry、ScienceClaw | 高但工程量大 |
| 10 | **跨仪器协议语义 / 资源市场调度** | 实验室中间件碎片化；算力/机时调度空白 | AutoLabs、ToolUniverse | 低（需要基础设施） |

---

## 7. 推荐方向（组会讨论用）

> 每个方向给：问题 → 为什么现在做 → 最小实验 → 评估 → 风险 → novelty 类型。
> 我的排序：**D1 ≈ D2 > D3 > D4 > D6 > D5**。

### D1 科研证据账本（Research Evidence Ledger）

- **问题**：科研 agent 的每个结论都应有可审计的证据链——哪篇论文的哪一段、哪次工具调用、哪段代码、哪个数据版本、哪次实验运行。当前系统各记各的日志，无法跨系统审计，也无法定位“错误从哪一步进入”。
- **为什么现在做**：Kosmos 证明了逐句溯源的可行性但只限单系统；AutoResearchClaw 的四层引文核验只覆盖引用；PaperBench/REPRO-Bench 说明复现失败的根因难定位。三者合起来指向同一个缺失：**统一的 evidence ledger**。
- **核心洞察**：把 claim 作为一等对象，建立 `claim → evidence edge` 的有向图；证据类型包括 paper-span、tool-call、code-commit、dataset-version、experiment-run；每个节点带置信度与时间戳；ledger 可 replay。
- **最小实验**：
  1. 选 20 个 PaperBench 任务 + 10 篇 AI Scientist 生成论文；
  2. 给 2 个现有系统（如 PaperQA2 + 一个数据分析 agent）加 ledger 输出；
  3. 让审计员（人或 LLM）只靠 ledger 判断 claim 是否成立；
  4. 对比“原始日志”基线，测审计时间、根因定位准确率、复现成功率。
- **评估**：claim-evidence coverage、审计 precision/recall、time-to-root-cause、replay success、跨系统互操作。
- **风险**：工程量大；schema 设计容易过度；需要说服系统作者接入。
- **Novelty**：**1 类（新的“证据审计”task）+ 2 类（ledger 表示）**。
- **适合 venue**：NeurIPS D&B / ICLR / ACL（资源与评测 track）。

### D2 失败归因与负面结果复用（Failure Attribution & Negative Memory）

- **问题**：现有 agent 失败后只会重试/停止；没有把失败拆成“数据错、代码错、假设错、仪器错、评测错”，也没有跨任务复用失败经验。
- **为什么现在做**：AutoResearchClaw 的 self-healing、AutoLabs 的自纠正、ScienceClaw 的验证沉淀都证明“失败处理”是系统瓶颈；但没有 benchmark 测“失败归因正确率”。组内初稿提到的 SAGE（多假设失败归因）本轮未找到，说明这个位置即使有人做也尚未形成公开基线。`[未找到]`
- **核心洞察**：失败归因 = 在多个候选原因上做**反事实重放**：如果改 X 后失败消失，则 X 是原因；把归因结果写入按上下文索引的失败记忆，后续任务先检索“相似失败”。

![图 2 · CALM 方法框架](figures/fig2-calm-method.png)

> **图 2 · CALM（D2 的方法实例）**：失败轨迹 τ → 双源候选 → 证据阶梯（T0/T0.5/T1，按需 T2）→ 终态 z → 回答 / 弃权。T2 条件执行且受预算约束；验证翻转记忆为可选写路径；CALM 只做失败归因，不做轨迹修复。可编辑源文件：[PPTX](figures/fig2-calm-method.pptx) · [SVG](figures/fig2-calm-method.svg) · [PDF](figures/fig2-calm-method.pdf)。

- **最小实验**：
  1. 从 PaperBench/MLGym/ScienceAgentBench 收集 200 条失败轨迹；
  2. 人工标注 root cause（5 类）；
  3. 构建多假设归因 agent + 反事实重放；
  4. 测 top-1/top-3 归因准确率、修复后成功率、跨任务负迁移。
- **评估**：归因准确率、恢复率、修复成本、负迁移率。
- **风险**：标注昂贵；根因可能不唯一；模拟器失败与真实失败分布不同。
- **Novelty**：**1 类（失败归因 task）+ 2 类（失败记忆）**。
- **适合 venue**：ICLR / NeurIPS D&B / ACL。

### D3 多样性约束的科研构思（Diversity-Constrained Ideation）

- **问题**：AI 生成 idea 的个体 novelty 可以很高，但群体多样性低、强化主流方向；现有系统（Co-Scientist 的 Elo、ResearchAgent 的评审）都在优化单条 idea，没有优化**想法组合的覆盖度**。
- **为什么现在做**：Si et al.（ICLR 2025）给出了“novelty 高、diversity 低”的经典证据；组内初稿提到的 *AI Research Agents Narrow Scientific Exploration*（2026-07，未验证）若属实，会进一步放大这个问题的重要性。`[原文/未验证]`
- **核心洞察**：把构思从“生成-筛选”改为**组合优化**：生成大量候选 → 按机制/概念聚类 → 以 coverage + novelty + feasibility 为目标选一组 → 显式惩罚与已有主流方向的相似度。
- **最小实验**：
  1. 用 Si et al. 的 100+ 主题或 ResearchAgent 数据；
  2. 对比 naive sampling、Elo 筛选、coverage 选择三组；
  3. 指标：语义多样性（聚类数/熵）、专家 novelty、可行性、成本；
  4. 请 5–10 位领域研究者盲评。
- **评估**：diversity（机制簇覆盖）、novelty、feasibility、expert preference。
- **风险**：多样性指标效度；为多样性牺牲质量；专家评测成本。
- **Novelty**：**1 类（portfolio-level ideation task）+ 3 类（coverage reward 模块）**。
- **适合 venue**：ACL / EMNLP / NeurIPS（可先做短论文）。

### D4 科研自治刻度与验证义务（Autonomy × Verification）

- **问题**：通用五级自治（Feng et al.）不区分科研风险；没人回答“agent 能否自主投稿/做湿实验/对外通信”，也没有把自治度与所需验证强度绑定。
- **为什么现在做**：AutoResearchClaw 已实现六档 HITL + SmartPause；SafeScientist 证明安全需要过程监督；但二者都没有形成**科研专用刻度**。
- **核心洞察**：二维框架——**自治级别**（建议/分析/执行计算/执行湿实验/投稿/对外沟通）× **验证义务**（自动检查/独立复现/专家审批/伦理审查）；每升一级，验证义务必须增加。
- **最小实验**：分析 20 个现有系统的实际自治度；访谈 20–30 位研究者；做 rubric 与 inter-rater agreement；用 3 个案例验证“刻度能否预测事故/争议”。
- **评估**：评分者一致性、覆盖失败案例、预测效度。
- **风险**：偏概念/综述，技术 novelty 低；适合 position paper 或 workshop，不宜作为主攻。
- **Novelty**：**1 类（新框架/task）**，需实证支撑。

### D5 湿实验 sim2real 基准

- **问题**：实验策略无法大规模预训练，因为真机试错不可逆；现有虚拟环境多为单装置、保真度未知。
- **为什么现在做**：AI X-ray Scientist 证明了“虚拟装置→真机”可行；BioDiscoveryAgent 用模拟器做主动实验；但两者都没有形成标准 benchmark。
- **核心洞察**：建一套带**校准噪声/故障模式/安全约束**的仪器仿真套件 + 迁移协议；评分不是“模拟器分数”，而是“迁移到真机后的样本效率与安全违规率”。
- **最小实验**：从一个公开仪器数据集/合作实验室入手，做 1 个装置的 sim2real 对照；先证明“模拟器排名能预测真机排名”。
- **风险**：成本高、需要实验合作；单篇论文难完成。**建议作为 D1/D2 的下游应用，而不是第一个项目。**
- **Novelty**：**1 类**。

### D6 过程级与长周期评测

- **问题**：现有 benchmark 以终态为主；月级任务、人员交接、预算耗尽、目标漂移未测；LLM judge 缺校准。
- **为什么现在做**：MLR-Bench 已开始过程评测；AstaBench 提供了 harness；ScienceAgentBench 有成本控制——三者可以组合成“过程+长周期”评测。
- **核心洞察**：在现有任务上加**检查点 + 过程 rubric + 中断恢复 + 预算约束**；用专家评分校准 judge；发布“过程分”与“终态分”的差异分析。
- **最小实验**：选 20 个 ScienceAgentBench 任务，加过程 rubric 与中断恢复测试；测过程分与专家分相关性。
- **风险**：标注成本；rubric 主观性。
- **Novelty**：**1 类/2 类**。
- **适合 venue**：NeurIPS D&B / ACL。

---

## 8. 不建议作为主攻的方向（以及理由）

| 方向 | 理由 |
|---|---|
| 再做一个端到端论文生成系统 | 已有 Nature 级系统与多个开源实现；边际 novelty 低，成本高，伦理/评审风险大 |
| 再做一个多 agent 科研角色框架 | 角色分工已饱和；缺的是“协作是否提升科学正确性”的证据，而不是更多角色 |
| 再做一个通用工具调用 agent | ToolUniverse/SciToolAgent/MLGym 已覆盖；除非解决工具质量认证或跨域协议 |
| 再做一个 RAG 综述 agent | PaperQA2/OpenScholar 已是强基线；除非引入新的证据表示或新的评测任务 |
| 再做一个评审打分模型 | DeepReview/ScholarPeer 已多；评审治理与校准才是空白 |
| 直接做“全自动投稿” | 治理、安全、署名、责任问题未解决；不适合作为单篇论文目标 |

---

## 9. 组会汇报提纲（12 分钟）

**Slide 1（1 min）问题**：科研智能体能走到哪一步？我们组该押哪条路线？
**Slide 2（1 min）结论先行**：端到端已过门槛，验证层是瓶颈；六个空白。
**Slide 3（2 min）领域全景**：三条演化主线（文献/组织/验证）+ 四类 novelty 分布。
**Slide 4（2 min）Literature Tree**：1 类 task 只有四个被反复研究；2 类 pipeline 三条主线；4 类工作最多。
**Slide 5（2 min）Challenge→Insight**：五个元 insight；三个未解矛盾（失败归因、趋同、证据审计）。
**Slide 6（2 min）什么没被做**：六个空白 + 现有最接近的工作 + 为什么现在能做。
**Slide 7（1.5 min）推荐方向**：D1 证据账本、D2 失败归因、D3 多样性构思；给最小实验。
**Slide 8（0.5 min）讨论问题**：见下。

**建议抛给组会的问题**：
1. 我们组的目标是发一篇好论文，还是搭一个长期平台？前者选 D3，后者选 D1/D2。
2. 我们有没有湿实验/仪器合作资源？有则 D5 可做，否则不做。
3. 组内是否已有数据/代码资产可复用？D1/D2 可以直接接现有 benchmark。
4. 是否接受“评测/基础设施”类论文？这类论文影响力大但引用慢。
5. 谁来负责与外部系统（PaperQA2/AutoResearchClaw）的对接？

---

## 10. 对组内初稿的修正清单（汇报前必看）

| # | 初稿写法 | 核验结果 | 建议 |
|---|---|---|---|
| 1 | SciNet “1800 万论文关系图” | ICML 2026 页面/arXiv 写 **2.69 亿篇论文元数据 + 8,940 任务** | 用 2.69 亿；强调它是 benchmark 不是 retrieval 方法 |
| 2 | DS-Agent（NeurIPS 2024） | 实际 **ICML 2024**（arXiv:2402.17453） | 改为 ICML 2024 |
| 3 | Robin（Emerald Cloud Lab 系） | Robin 属 **FutureHouse / Edison Scientific**；Nature 655:497–505 (2026)，DOI 10.1038/s41586-026-10652-y；湿实验由人做，定位半自动 | 改机构与定位；不要写成全自动 |
| 4 | AutoLabs（Nature 2026） | **Scientific Reports 16:19554 (2026)**；PNNL；arXiv:2509.25651 | 改 venue |
| 5 | X-ray scientist（Nature 2026） | **Nature Machine Intelligence 2026**，DOI 10.1038/s42256-026-01261-5 | 改 venue；任务仅样品对准 |
| 6 | AI Scientist（Nature 2026-03） | Nature 2026，题名 *Towards end-to-end automation of AI research*，DOI 10.1038/s41586-026-10265-5；v2 是 **ICLR 2025 workshop** 接收，不是主会 | 写“通过 ICLR 2025 workshop 双盲评审”，不要写成主会或 Nature 版 |
| 7 | Co-Scientist（Nature 2026-05） | Nature 655:487–496 (2026)，DOI 10.1038/s41586-026-10644-y；在线 2026-05-19 | 补卷页/DOI |
| 8 | SAGE（多假设失败归因） | 本轮**未找到**；疑似与 “SAGE: Benchmarking Retrieval for Deep Research Agents” 名称冲突 | 找到 DOI 前不要作为已确认文献引用 |
| 9 | ScienceClaw（2026-03 分布式发现） | 已核验的 ScienceClaw 是 **2610.08691（自进化 benchmark）**，与“分布式发现”不是同一篇 | 分开列；不要把两篇混为一条 |
| 10 | AstaBench（2025-08） | arXiv:2510.21652（**2025-10**） | 改日期 |
| 11 | Kosmos（arXiv 2025-11） | 本轮未找到 arXiv/期刊论文；只有 Edison Scientific 公司报告与二手报道；79.4% 等数字为公司口径 | 标注“公司报告，未经同行评审” |
| 12 | AutoDiscovery / Evidence-Informed Beliefs / SAGA / PiEvo / FlowPIE / Narrow Exploration / AIM / Curie / Agent Reviewers / Zhuang 综述 / MatBrain / EmbodiedAct / ERA / Deep Research in Physical Sciences | 本轮均**未验证** | 单列“待补证”，不进入主树 |
| 13 | AutoResearchClaw 的 23 阶段、star 数 | 论文 arXiv:2605.20025 已核验；23 阶段与 star 数为 GitHub/组内材料 | 引用机制可以，star 数不要当学术证据 |
| 14 | SafeScientist “+35%” | 论文元数据已核验；NeurIPS 2025 与 +35% 未独立核对 | 标“组内材料/待核” |
| 15 | DataSciBench（ACL 2026） | 未独立核验 venue | 标待核 |

---

## 11. 两周计划（建议）

**Week 1：补证 + 定方向**
- 补核 §10 中 8 条未验证文献（优先 SAGE、AutoDiscovery、Curie、Narrow Exploration、AstaBench 细节）。
- 精读 5 篇最相关：PaperBench、ScienceAgentBench、MLR-Bench、ScienceClaw、AutoResearchClaw。
- 组内讨论从 D1/D2/D3 中选 1 个主方向 + 1 个备选。

**Week 2：最小实验设计**
- 写 2 页 proposal：问题、gap 证据、方法、最小实验、评估、风险。
- 搭数据/环境：D1 用 PaperBench 日志；D2 收集 200 条失败轨迹；D3 用 Si et al. 主题集。
- 跑通一个基线，确认“现有方法确实做不到”，再决定是否投入。

---

## 12. 已核验核心文献（按层，含 arXiv/DOI）

> 完整五字段卡片见 `papers/`。此处只列元信息，便于汇报时快速引用。

### 任务能力层
- **SciNet** — Shao, Xu, Li 等. ICML 2026. arXiv:2601.03260.
- **OpenScholar** — Asai et al. arXiv:2411.14199 (2024).
- **PaperQA2 / Language agents achieve superhuman synthesis** — Skarlinski et al. arXiv:2409.13740 (2024).
- **SciArena** — AI2 et al. arXiv:2507.01001 (2025).
- **ResearchAgent** — Baek et al. NAACL 2025. arXiv:2404.07738.
- **Si et al., Can LLMs Generate Novel Research Ideas?** — ICLR 2025. arXiv:2409.04109.
- **IdeaScientist** — Jiarui Liu et al. arXiv:2610.04074 (2026).
- **BioDiscoveryAgent** — Roohani et al. ICLR 2025. arXiv:2405.17631.
- **SciToolAgent** — Ding et al. Nature Computational Science (2025). DOI:10.1038/s43588-025-00849-y.
- **AI X-ray Scientist** — Chen et al. Nature Machine Intelligence (2026). DOI:10.1038/s42256-026-01261-5.
- **AutoLabs** — Panapitiya et al. Scientific Reports 16:19554 (2026). arXiv:2509.25651.
- **MLE-bench** — OpenAI. ICLR 2025. arXiv:2410.07095.
- **DS-Agent** — Guo et al. ICML 2024. arXiv:2402.17453.
- **DiscoveryBench** — Google. ICLR 2025. arXiv:2407.01725.
- **SciCode** — Tian et al. NeurIPS 2024. arXiv:2407.13168.
- **AgentReview** — Jin et al. EMNLP 2024. arXiv:2406.12708.
- **DeepReview** — arXiv:2503.08569 (2025).
- **ScholarPeer** — arXiv (2026-01).
- **PaperBench** — OpenAI. arXiv:2504.01848 (2025).
- **REPRO-Bench** — arXiv:2507.18901 (2025).
- **CodeScientist** — AI2. arXiv:2503.22708 (2025).
- **The AI Scientist** — Lu et al. arXiv:2408.06292; Nature (2026). DOI:10.1038/s41586-026-10265-5.
- **AI Scientist-v2** — Yamada et al. arXiv:2504.08066 (2025).

### 系统组织层
- **Co-Scientist** — Gottweis et al. Nature 655:487–496 (2026). DOI:10.1038/s41586-026-10644-y.
- **Virtual Lab** — Swanson et al. Nature 646:716–723 (2025).
- **Robin** — FutureHouse. Nature 655:497–505 (2026). DOI:10.1038/s41586-026-10652-y.
- **Agent Laboratory** — Schmidgall et al. arXiv:2501.04227 (2025).
- **MLGym** — Nathani et al. arXiv:2502.14499 (2025).
- **Denario** — Villaescusa-Navarro et al. arXiv:2510.26887 (2025).
- **Kosmos** — Edison Scientific 公司报告 (2025-11)，无论文 `[公司报告]`.
- **EinsteinArena** — Bianchi et al. arXiv:2606.10402 (2026).
- **Levels of Autonomy for AI Agents** — Feng, McDonald, Zhang. arXiv:2506.12469 (2025).

### 基础设施层
- **ToolUniverse** — Gao et al. arXiv:2509.23426 (2025).
- **ScienceAgentBench** — Chen et al. ICLR 2025. arXiv:2410.05080.
- **AstaBench** — Bragg et al. arXiv:2510.21652 (2025).
- **MLR-Bench** — NeurIPS 2025 D&B. arXiv:2505.19955.
- **SkillFoundry** — Shen et al. arXiv:2604.03964 (2026).
- **ScienceClaw** — Zhang et al. arXiv:2610.08691 (2026).
- **AutoResearchClaw** — Liu et al. arXiv:2605.20025 (2026).
- **SwarmRSI** — Meng et al. arXiv:2610.20431 (2026).
- **SafeScientist** — Zhu et al. arXiv:2505.23559 (2025).
- **Paper2Agent** — Miao et al. arXiv:2509.06917 (2025).
- **AgenticSciML** — Jiang, Karniadakis. arXiv:2511.07262 (2025).

---

## 13. 一句话总结

> **这个领域已经不缺“会写论文的 agent”，缺的是“能让论文被相信的系统”。** 下一阶段的高价值工作，不在于把 pipeline 拉得更长、agent 变得更多，而在于把**证据、失败、多样性、权限**做成可审计、可复用、可验证的基础设施。

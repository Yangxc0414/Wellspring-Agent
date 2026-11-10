# Literature Tree：科学智能体（Scientific Agents / AI Scientist）

> 构建方法：先按「里程碑任务」聚类 → 标出提出该任务的论文（1 类 novelty）→ 在同一任务下找代表性 pipeline/representation 及其首篇（2 类）→ 再往下拆模块（3 类）→ 把「给已有 pipeline 加模块」的工作归为 4 类。
>
> **重要限定**：所有“首篇/最早”均为**本次已核验语料范围内**的判断，不宣称是历史绝对第一。已发现的前驱工作会标注在“前驱/竞争首发性”一栏。组内初稿中无法核验的条目单列为「未验证分支」，不进入主树。
>
> 证据等级：`[已核验]` 论文元数据经 arXiv/期刊核对；`[部分核验]` 会议/数字未独立核对；`[未找到]` 本轮检索未定位；`[推测]` 我的判断。

---

## 0. 一页纸总览

```
科学智能体
├── A. 任务能力层（能做什么）
│   ├── A1 文献检索与综合
│   │   ├── M1 关系感知检索评测 ── SciNet (1类) ── 三层关系任务 (2类)
│   │   ├── M2 高精度文献问答/综合 ── PaperQA2 (1类) ── agentic RAG (2类)
│   │   │     └── OpenScholar：开放模型+自反馈引用校验 (2类/4类)
│   │   └── M3 开放式科研任务众评 ── SciArena (1类) ── Arena+Elo+元评测 (2类)
│   ├── A2 假设生成与探索
│   │   ├── M4 文献接地的研究构思 ── ResearchAgent (1类) ── 文献图+概念库+评审 agent (2类)
│   │   │     └── IdeaScientist：RL 角色分解 (3类)
│   │   ├── M5 想法多样性评测 ── Si et al. (1类) ── 专家盲评协议 (2类)
│   │   ├── M6 长时程假设搜索 ── AutoDiscovery (1类,未验证) ── 贝叶斯惊奇+MCTS (2类)
│   │   └── M7 测试时想法演化 ── PiEvo/FlowPIE (未验证，空分支候选)
│   ├── A3 实验执行与仪器
│   │   ├── M8 闭环基因扰动设计 ── BioDiscoveryAgent (1类) ── LLM+工具+主动选择 (2类)
│   │   ├── M9 多工具编排 ── SciToolAgent (1类/2类) ── 工具KG+RAG规划 (2类)
│   │   ├── M10 真实仪器自主实验 ── AI X-ray Scientist (1类) ── 虚拟装置→真机 (2类)
│   │   └── M11 自主化学实验 ── AutoLabs (2类；前驱 A-Lab/Coscientist)
│   ├── A4 数据分析与建模
│   │   ├── M12 ML 工程评测 ── MLE-bench (1类)
│   │   ├── M13 数据科学 agent ── DS-Agent (1类) ── 案例推理 (2类)
│   │   ├── M14 多步数据驱动发现评测 ── DiscoveryBench (1类)
│   │   ├── M15 科研级代码 ── SciCode (1类)
│   │   └── M16 实验严谨性引擎 ── Curie (1类,未验证)
│   ├── A5 评审与反馈
│   │   ├── M17 评审过程仿真 ── AgentReview (1类) ── 三角色模拟 (2类)
│   │   └── M18 拟人化 LLM 评审 ── DeepReview (1类) ── 深度思考流程 (2类)
│   ├── A6 验证与复现
│   │   ├── M19 论文从零复现评测 ── PaperBench (1类) ── rubric+复现 (2类)
│   │   ├── M20 社科计算可复现 ── REPRO-Bench (1类) ── REPRO-Agent (2类)
│   │   └── M21 证伪优先的科研 agent ── 【空白】
│   └── A7 成果生产
│       └── M22 端到端 AI 研究 ── The AI Scientist (1类) ── 线性流水线 (2类)
│             └── AI Scientist-v2：树搜索+VLM 反馈 (2类/3类)
├── B. 系统组织层（怎么组织）
│   ├── M23 多智能体人机协同 ── Virtual Lab/Co-Scientist (1类/2类) ── 组会/锦标赛 (2类)
│   ├── M24 半自动湿实验回流 ── Robin (2类)
│   ├── M25 研究环境协议 ── MLGym (1类) ── Gym 接口 (2类)
│   ├── M26 集体科研平台 ── EinsteinArena (1类) ── verifier+论坛+共享记忆 (2类)
│   └── M27 科研专用自治刻度 ── 【空白】(Feng et al. 为通用五级)
└── C. 基础设施层（怎么支撑）
    ├── M28 任务级科研评测 ── ScienceAgentBench (1类) ── AstaBench (2类 harness)
    ├── M29 开放式研究过程评测 ── MLR-Bench (1类)
    ├── M30 科研工具生态 ── ToolUniverse (1类) ── Find/Call 标准 (2类)
    ├── M31 技能/知识记忆 ── SkillFoundry / Paper2Agent / Kosmos (2类)
    ├── M32 持续自进化 ── ScienceClaw (1类) ── 三重验证沉淀 (2类)
    ├── M33 科研安全 ── SafeScientist (1类) ── 监督 pipeline (2类)
    └── M34 证据溯源与贡献归因 ── 【空白】
```

---

## 1. 1 类 novelty：提出 milestone task 的论文

> 判定标准：它第一次把某件“以前没人系统评测/定义”的科研能力变成**可执行、可比较的任务**，并给出任务形式化与基线。

| ID | Milestone task | 1 类论文 | 年份/出处 | 为什么是里程碑 | 前驱/竞争首发性 |
|---|---|---|---|---|---|
| M1 | 关系感知文献检索评测 | **SciNet**（Shao, Xu, Li 等） | 2026 / ICML 2026 | 首次把“论文关系”（引用情感、思想路径）变成检索 agent 的可评测任务，2.69 亿论文元数据 + 8,940 任务 | 传统 citation recommendation / SciDocs 只做相关性，不做关系判断 `[推测]` |
| M2 | 高精度科研文献问答与综合 | **PaperQA2**（Skarlinski 等，FutureHouse） | 2024 / arXiv:2409.13740 | 把 agentic RAG 推到“逐 claim 证据绑定 + 与人类专家对比”的任务标准 | 前有单轮 RAG、SciQ；PaperQA2 首次把“科研级综合”作为任务并提出 LitQA2 |
| M3 | 开放式科研任务的人类偏好评测 | **SciArena**（AI2 等） | 2025 / arXiv:2507.01001 | 首个面向真实科研文献任务的 arena + 元评测（judge 是否懂人类偏好） | Chatbot Arena 是通用对话；科研任务的专业性未被覆盖 |
| M4 | 文献接地的开放式研究构思 | **ResearchAgent**（Baek 等） | 2024 / NAACL 2025 | 把“从一篇基础论文出发提出新研究问题”形式化为 idea generation + reviewing 流程 | Si et al. 2024 是**评测**而非系统；IdeaScientist 更晚 |
| M5 | AI 想法的新颖性/多样性评测 | **Si et al., Can LLMs Generate Novel Research Ideas?** | 2024 / ICLR 2025 | 100+ 专家盲评协议，首次把 novelty 与 diversity 分开测量 | 早期 idea benchmark 无专家盲评 |
| M6 | 长时程假设空间搜索 | **AutoDiscovery**（组内注 NeurIPS 2025） | 2025 | 用贝叶斯惊奇度 + MCTS 把“探索欲”形式化 | `[未验证]` 本轮未定位原文，暂不作为主树证据 |
| M8 | 闭环基因扰动实验设计 | **BioDiscoveryAgent**（Roohani 等，Stanford） | 2024 / ICLR 2025 | 首次把“多轮选择基因扰动”做成 agent 闭环评测 | 虚拟细胞线已有，但非 LLM agent 闭环 |
| M9 | 多工具编排的科研任务 | **SciToolAgent**（Ding 等，浙大） | 2025 / Nature Comput. Sci. | 首次以工具知识图谱 + 531 题 benchmark 定义“多工具科研编排” | ToolLLM 等通用工具调用不涉及科学工具依赖与安全 |
| M10 | 真实科学仪器上的自主实验 | **AI X-ray Scientist**（Chen 等，SLAC/Stanford） | 2026 / Nature Mach. Intell. | 首个在真实同步辐射光束线上由 LLM agent 完成多步对准并纠错 | 前有自动化实验脚本、A-Lab，但非 LLM 闭环决策 |
| M12 | ML 工程 agent 评测 | **MLE-bench**（OpenAI） | 2024 / ICLR 2025 | 75 个 Kaggle 任务 + medal 评级，成为 ML agent 的事实标尺 | MLAgentBench 同期/略早，任务形态不同；首发性有争议 |
| M13 | 数据科学 agent | **DS-Agent**（Guo 等） | 2024 / ICML 2024 | 首次把案例推理（CBR）用于数据科学全流程 | 前有 Data-Copilot 等，CBR 记忆是新增量 |
| M14 | 多步数据驱动发现评测 | **DiscoveryBench**（Google） | 2024 / ICLR 2025 | 首个把“数据驱动发现”的多步过程形式化的 benchmark（264 任务） | 前有 DSBench 偏单步；过程形式化是新增量 |
| M15 | 科研级代码生成 | **SciCode**（Tian 等） | 2024 / NeurIPS 2024 | 科学家标注、跨学科、多步代码任务 | HumanEval/MBPP 非科研级 |
| M17 | 同行评审过程仿真 | **AgentReview**（Jin 等） | 2024 / EMNLP 2024 | 首次用 reviewer/author/AC 三角色模拟评审动力学 | 前有单模型评审打分，无过程仿真 |
| M18 | 拟人化 LLM 评审 | **DeepReview** | 2025 / arXiv:2503.08569 | 把“深度思考流程”引入评审，成为后续评审 agent 的基线 | `[部分核验]` 元数据已核验，venue 未核 |
| M19 | 论文从零复现评测 | **PaperBench**（OpenAI） | 2025 / arXiv:2504.01848 | 20 篇 ICML 论文 + rubric 过程评分，量化“复现鸿沟” | 前有 MLReproBench，规模与 rubric 不同 |
| M20 | 社科计算可复现评测 | **REPRO-Bench** | 2025 / arXiv:2507.18901 | 首个社科论文计算可复现 benchmark + REPRO-Agent | 以 CS 为主的复现 benchmark 不覆盖社科 |
| M22 | 端到端自动化 AI 研究 | **The AI Scientist**（Lu 等，Sakana） | 2024 / arXiv:2408.06292；Nature 2026 | 首个可运行、可批量、低成本的 idea→实验→论文→评审闭环 | 前有 FunSearch（只做算法发现）、Coscientist（只做化学实验） |
| M23 | 多智能体人机协同科研 | **Virtual Lab**（Swanson 等） | 2025 / Nature 646 | 首个“AI PI + 专家 agent 组会”并产出湿实验可验证设计 | Co-Scientist 预印本稍晚；两者共享首发性 |
| M25 | 研究 agent 的标准环境 | **MLGym**（Meta） | 2025 / arXiv:2502.14499 | 首个 ML 研究任务的 Gym 接口，使研究策略可 RL 训练 | 前有 AgentBench 等通用环境，非科研 |
| M26 | 集体科研平台 | **EinsteinArena**（Bianchi 等） | 2026 / arXiv:2606.10402 | 首个 agent-native、带 verifier/论坛/共享记忆的开放科研竞技场 | 前有 SWE-bench 等静态 benchmark，无集体记忆 |
| M28 | 任务级科研 agent 评测 | **ScienceAgentBench** | 2024 / ICLR 2025 | 102 个来自 44 篇论文的任务 + 成本控制 + solvable 设置 | 前有 ScienceQA 等知识评测，非工作流执行 |
| M29 | 开放式研究的过程评测 | **MLR-Bench** | 2025 / NeurIPS 2025 D&B | 任务集 + 过程评测 + 判分三组件，评“开放式 ML 研究”而非单点 | 前有 MLE-bench 评工程结果，不评研究过程 |
| M30 | 科研工具生态与调用标准 | **ToolUniverse**（Gao 等，Harvard） | 2025 / arXiv:2509.23426 | 首个统一工具声明 schema + Find/Call 原语 + MCP 生态 | 前有 LangChain tools，非科研专用、无生态治理 |
| M32 | 持续自进化评测 | **ScienceClaw** | 2026 / arXiv:2610.08691 | 首个跨 23 学科的“程序自进化”序列评测，含保留/迁移/成本 | 前有 Voyager 技能库，非科学验证驱动 |
| M33 | 科研 agent 安全评测 | **SafeScientist / SciSafetyBench** | 2025 / arXiv:2505.23559 | 首个风险感知科研安全框架 + 多危害 benchmark | 通用安全 benchmark 不覆盖科研双用途 |

**1 类判定的两个争议点（组会可讲）**：
- M22 与 M23 的首发性：Virtual Lab 的arXiv 版本（2024-11）与 Co-Scientist（2025-02）谁更早取决于版本口径；二者都把“多 agent 组织”作为贡献，但 Virtual Lab 更早给出湿实验验证。
- M12 MLE-bench 与 MLAgentBench：后者（2024-03）更早提出 ML agent 基准，但 MLE-bench 因 Kaggle 任务与 medal 评级成为事实标准。严格首发性应给 MLAgentBench，**MLE-bench 是“标准化+规模化”的里程碑**。

---

## 2. 2 类 novelty：提出代表性 pipeline / representation 的论文

> 判定标准：在某个 milestone task 下，首次给出**可复用的整体流程或中间表示**，后续工作围绕它改进。

| ID | Pipeline / representation | 2 类论文 | 关键表示 | 后续被谁沿用/改进（4 类） |
|---|---|---|---|---|
| P1 | 三层关系任务 + 大规模元数据库 | SciNet | ego / pairwise / path 三层关系标注 | 后续检索 agent 评测（未收集） |
| P2 | Agentic RAG：查询规划→检索→重排→证据聚合→引用 | PaperQA2 | 段落级证据 + claim 绑定 | OpenScholar 加自反馈；SciArena 用检索管线 |
| P3 | 开放模型 + 合成数据 + 自反馈引用校验 | OpenScholar | 4500 万篇 ScholarDB + ScholarQABench | 开源文献综合基线 |
| P4 | Arena + Elo + LLM-judge 元评测 | SciArena | 人类偏好对 + 元评测集 | 后续 arena 类平台 |
| P5 | 文献图 + 概念知识库 + ReviewingAgent | ResearchAgent | 论文图 + 概念节点 | IdeaScientist 改为 RL 角色分解 |
| P6 | 专家盲评 + novelty/diversity 分离 | Si et al. | 受控实验协议 | 后续 AI idea 评测沿用 |
| P7 | LLM + 工具 + 多轮实验选择 | BioDiscoveryAgent | 实验轮次状态 | 主动学习+LLM 先验的后续工作 |
| P8 | 工具知识图谱 + 图 RAG 规划 + 安全审查 | SciToolAgent | SciToolKG（输入/输出/依赖/安全等级） | SciToolAgent-Evo 等 |
| P9 | 虚拟装置预训练 → MCP 工具层 → 真机闭环 | AI X-ray Scientist | 虚拟光束线 + 仪器状态 | sim2real 仪器 agent |
| P10 | 案例推理（CBR）数据科学 agent | DS-Agent | 案例库 + 复用/适配 | 记忆型 DS agent |
| P11 | 多步发现任务形式化 | DiscoveryBench | 任务=数据+问题+多步工作流 | 后续发现类 benchmark |
| P12 | 三角色评审模拟 | AgentReview | reviewer/author/AC 角色状态 | 评审动力学研究 |
| P13 | 深度思考评审流程 | DeepReview | 评审推理链 | ScholarPeer 等 |
| P14 | Rubric + 从零复现 | PaperBench | 复现步骤 rubric | 复现类评测 |
| P15 | idea→experiment→paper→review 线性流水线 | The AI Scientist | 四阶段产物 | v2 树搜索、Denario 模块化、AutoResearchClaw 自愈 |
| P16 | 实验树搜索 + VLM 图表反馈 | AI Scientist-v2 | 实验树节点 | 后续树搜索系统 |
| P17 | AI PI + 专家 agent + 组会协议 | Virtual Lab | 角色 + 会议记录 | 多 agent 科研组织 |
| P18 | 生成/反思/排序/进化/元评审 + Elo 锦标赛 | Co-Scientist | 假设池 + Elo 排名 | 假设生成系统 |
| P19 | 五个专用 agent + 中央编排 + 湿实验回流 | Robin | 文献/新颖性/实验/代码分工 | 半自动生物发现 |
| P20 | 三阶段线性研究助手 + 人类反馈 | Agent Laboratory | 阶段产物 + Co-pilot | 低成本研究助手 |
| P21 | Gym 接口 + 13 任务套件 | MLGym | 状态=代码库/日志，动作=命令/编辑 | RL 训练研究 agent |
| P22 | 结构化世界模型 + 并行 agent rollout | Kosmos | 世界模型（实体/证据/空白） | 长时程科研系统 `[公司报告]` |
| P23 | verifier + 论坛 + 共享记忆 + 排行榜 | EinsteinArena | 问题/尝试/讨论/验证结果 | 集体科研平台 |
| P24 | 统一评测 harness + 多套件 | AstaBench | 任务/环境/评分统一接口 | 评测基础设施 |
| P25 | 工具声明 schema + Find/Call + MCP | ToolUniverse | 工具卡（用途/schema/实现） | 工具生态 |
| P26 | 技能树 + 异构资源抽取 + 维护 | SkillFoundry | 技能树节点 | 技能库 |
| P27 | 程序自进化 + 三重验证沉淀 | ScienceClaw | Skill–Operator 更新 | 自进化系统 |
| P28 | 论文+代码 → 可交互 agent | Paper2Agent | 方法封装 + 测试用例 | 论文复用 |
| P29 | 多 agent 辩论 + 自愈执行 + 跨 run 记忆 + 引文核验 | AutoResearchClaw | 五机制流水线 + 教训库 | 全自主系统集成 |
| P30 | 蜂群变异/选择/交叉 | SwarmRSI | 种群 + 共享结果 | 群体自进化 |
| P31 | 多 agent 协作做 SciML 方法发现 | AgenticSciML | 角色分工 | 领域化多 agent |

---

## 3. 3 类 novelty：提出关键模块的论文

> 判定标准：模块可被插入不同 pipeline，且论文的核心贡献是**这个模块本身**（不是整条流水线）。

| 模块 | 论文 | 插入位置 | 解决什么 | 备注 |
|---|---|---|---|---|
| 自反馈引用校验 | OpenScholar | 文献综合 pipeline 的生成后 | 引用幻觉 | 也可视为 4 类（给 agentic RAG 加模块） |
| ReviewingAgent | ResearchAgent | 构思 pipeline 的评审环节 | 想法质量把关 | 首个“生成-评审”双 agent 构思 |
| RL 角色分解（gap→innovation→writing） | IdeaScientist | 构思 pipeline | 把 ideation 拆成可训练子任务 | 2026，较新 |
| 贝叶斯惊奇度目标 | AutoDiscovery | 假设搜索循环 | 把“探索欲”变成可优化目标 | `[未验证]` |
| 显式信念分布 | Evidence-Informed LLM Beliefs | 搜索循环外部 | 长时程证据累积 | `[未验证]`；与 AutoDiscovery 同组 |
| 工具知识图谱 | SciToolAgent | 工具规划前 | 约束工具链搜索空间 | 可复用到其他工具 agent |
| 安全审查模块 | SciToolAgent | 规划与执行之间 | 危险工具调用 | 规则式 |
| 虚拟装置（sim2real） | AI X-ray Scientist | 训练/开发阶段 | 真机试错成本高 | 可复用到其他仪器 |
| 案例库/案例推理 | DS-Agent | 数据科学任务开始 | 复用历史方案 | 最早的“经验记忆”实现之一 |
| 确定性 7 模块流水线 | DS-STAR | 数据科学分析 | 降低不确定性、提升可复现 | 工程化路线 |
| 深度思考评审链 | DeepReview | 评审 agent | 提升评审解释性 | |
| 共享记忆（跨论文一致性） | Agent Reviewers（OpenReview 2025） | 多篇评审之间 | 评审标准漂移 | `[未找到]` 本轮未核验，暂不纳入主树 |
| VLM 图表审阅 | AI Scientist-v2 | 实验后 | 让 agent 看懂自己的结果图 | |
| Elo 假设锦标赛 | Co-Scientist | 假设排序 | 相对质量比较 | 可独立复用 |
| 结构化世界模型 | Kosmos | 系统中心 | 长程一致性与知识空白识别 | `[公司报告]` |
| 三重验证沉淀门槛 | ScienceClaw | 技能入库前 | 防止错误固化 | 自进化的关键模块 |
| 引文四层核验 | AutoResearchClaw | 成稿前 | 引用造假 | 工程模块 |
| 跨 run 教训库 + 时间衰减 | AutoResearchClaw | 运行之间 | 经验不积累 | MetaClaw |
| 技能树维护（去重/合并/剪枝） | SkillFoundry | 技能库 | 技能膨胀/冲突 | |
| 论文→agent 封装器 | Paper2Agent | 知识复用 | 论文方法难调用 | |
| 风险监督 | SafeScientist | 多 agent 协作 | 危险操作 | |
| 预算/成本控制 | ScienceAgentBench | 评测 harness | 无限试错 | 评测模块也可复用 |

---

## 4. 4 类 novelty：给已有 pipeline 加模块的改进工作

| 工作 | 基线 pipeline | 加了什么 | 效果/定位 | 证据 |
|---|---|---|---|---|
| OpenScholar | PaperQA2 式 agentic RAG | 开放模型 + 合成训练数据 + self-feedback | 开放基线，引用准确率接近专家 | `[已核验]` |
| AI Scientist-v2 | AI Scientist v1 | 去模板 + 实验树搜索 + VLM 读图 | 首篇 AI 生成 workshop 接收论文 | `[已核验]` |
| Denario | AI Scientist 式端到端 | 模块化拆分 + CMBAgent 后端 + 跨 12 学科评估 | 可单模块调用；诚实报告 10% 有趣率、17% 错误率 | `[已核验]` |
| Agent Laboratory | 全自动流水线 | 人给 idea + 三阶段 + 人类反馈 | 成本降约 84% | `[部分核验]` |
| ScholarPeer | DeepReview | 上下文感知 + 多 agent | 评审一致性 | `[已核验]` 元数据 |
| DS-STAR | DS-Agent 等 | 确定性 7 模块 | DABStep 12%→45% | `[已核验]` 元数据，数字待核 |
| DataVoyager | 数据分析 pipeline | 产品化报告 + 透明分析 | 落地形态 | `[已核验]` 元数据 |
| AstaBench | 多个独立 benchmark | 统一 harness | 可比评测 | `[已核验]` |
| AutoResearchClaw | AI Scientist 线性流水线 | 辩论 + 自愈 + HITL + MetaClaw + 引文核验 | 自治度可调、跨 run 记忆 | `[已核验]` |
| ScienceClaw | 技能进化 pipeline | 三重验证 + 23 学科序列评测 | 自进化可测 | `[已核验]` |
| SwarmRSI | 单体 RSI | 蜂群进化 | 群体层面 RSI | `[已核验]`，极新 |
| MLR-Bench | MLE-bench 式结果评测 | 过程评测 + 判分 | 开放式研究评测 | `[已核验]` |
| SafeScientist | 通用科研 agent | 风险监督 + SciSafetyBench | 安全性 +35%（组内材料） | `[部分核验]` |
| IdeaScientist | ResearchAgent 式构思 | RL 训练三个子 agent | 有依据/新颖/可验证 | `[已核验]` 元数据 |
| AgenticSciML | 单 agent SciML | 多角色协作 | 领域化改进 | `[已核验]` |

---

## 5. 未验证分支（组内初稿有、本轮没核验到）

> 这些**不进入主树**，但在组会上值得说明“初稿里有、需要补证”。不要把它们当作已确认文献引用。

| 条目 | 状态 | 处理建议 |
|---|---|---|
| SAGE: One Reflection Is Not Enough（多假设失败归因） | `[未找到]` | 疑似与 “SAGE: Benchmarking Retrieval for Deep Research Agents” 混淆；补 DOI 后再入树 |
| AutoDiscovery（NeurIPS 2025） | `[未验证]` | 找到 OpenReview/arXiv 后归入 M6 |
| Evidence-Informed LLM Beliefs（2606.29182） | `[未验证]` | 若存在，归入 M6 的 3 类模块 |
| SAGA: Goal-Evolving Agents | `[未验证]` | 归入 A2 的“目标演化”分支 |
| PiEvo / FlowPIE / Idea-Evolution | `[未验证]` | 合并为“测试时想法演化”候选分支 |
| AI Research Agents Narrow Scientific Exploration（2026-07） | `[未验证]` | 若存在，是 M5 的关键 4 类反面证据 |
| AIM: Agentic Idea Management | `[未验证]` | 归入“想法管理”分支 |
| Curie（严谨性引擎） | `[未验证]` | 找到后归入 M16 |
| Agent Reviewers（OpenReview 2025） | `[未找到]` | 共享记忆模块暂缺 |
| Zhuang et al. 评审综述 | `[未找到]` | 作为 T5 综述补充 |
| MatBrain / EmbodiedAct / ERA | `[未找到]` | 不纳入 |
| Deep Research in Physical Sciences | `[未找到]` | 不纳入 |
| Zochi（Intology） | `[未核验]` | 商业系统，单独列产业观察 |
| AI-generated figure detection | `[未找到]` | 作为“鉴伪”需求信号 |
| Agentic Economies | `[未找到]` | 治理分支暂缺 |
| ScienceClaw: Coordinating Distributed Discovery（2026-03） | `[未找到]` | 与 2610.08691 区分；后者已核验 |
| From Prompts to Protocols | `[未找到]` | 实验室编排分支暂缺 |
| CSA Autonomy Levels（2026-01） | `[未核验]` | 产业治理报告，非论文 |

---

## 6. 空分支（明确的“没人做/没做好”清单）

> 这是组会最重要的产出：**不是“论文少”，而是“任务定义本身缺失”**。

| 空分支 | 缺什么 | 为什么重要 | 现有最接近的工作 |
|---|---|---|---|
| **证伪优先的科研 agent** | 把可证伪性作为一等目标函数/约束；主动设计“能杀死自己假设”的实验 | 当前系统优化 novelty/performance，天然产生确认偏差；科学进步靠证伪 | PaperBench（只复现）、REPRO-Bench（只复现）、AutoDiscovery（探索而非证伪） |
| **想法多样性/覆盖度作为优化目标** | 把 diversity/coverage 写进 ideation 目标并评测 | 已有证据显示 AI idea 个体新颖但群体趋同；这会让整个科学生态收窄 | Si et al.（只测量）、Narrow Exploration（未验证） |
| **跨系统统一的证据/溯源账本** | 文献、工具调用、代码、实验结果、模型输出的统一 provenance 本体 | 没有它，审计、归因、复现、责任划分都做不到 | Kosmos 的逐句溯源（单系统）、AutoResearchClaw 的引文核验（仅引用） |
| **科研专用自治刻度 + 验证义务** | 区分读文献/跑代码/湿实验/投稿的风险等级，并绑定自动验证强度 | 通用五级自治无法指导“能不能让 agent 自己投稿/做湿实验” | Feng et al.（通用五级）、CSA（治理报告） |
| **湿实验 sim2real 基准** | 安全、廉价、可重复的实验仿真环境与迁移协议 | 实验策略无法大规模预训练；真机试错不可逆 | AI X-ray Scientist 的虚拟光束线（单装置） |
| **失败归因与负面结果复用** | 跨任务记录“为什么失败”，并在后续任务中主动避免 | 当前系统失败即停止或重试，经验不传播 | AutoResearchClaw self-healing（工程）、EvoMap（开源保留负结果） |
| **月级长周期任务评测** | 数周–数月的科研任务、人员交接、预算耗尽、目标漂移 | 现有 benchmark 多为小时级 | MLGym（小时级）、ScienceAgentBench（单任务） |
| **AI 贡献归因与投稿政策技术方案** | 人机贡献量化、AI 生成内容检测、署名/责任 | 评审自动化与论文工厂已现实存在 | 仅有政策讨论，无技术系统 |

---

## 7. 树的阅读方法（组会 5 分钟版）

1. **先看 1 类表**：这个领域已经被定义出来的“任务”只有二十来个；其中真正被反复研究的集中在 M2（文献综合）、M22（端到端）、M19（复现）、M28（评测）。
2. **再看 2 类表**：pipeline 的演化主线只有三条——agentic RAG（P2→P3）、线性→树搜索→世界模型（P15→P16→P22）、单 agent→多角色→集体平台（P17→P18/P19→P23）。
3. **最后看空分支**：证伪、多样性、统一 provenance、科研自治刻度、湿实验 sim2real、失败复用、长周期评测、贡献归因——这八处是“别人还没做”的地方。
4. **4 类工作最多**：说明大部分论文是在已有 pipeline 上加模块；如果我们的工作只是“再加一个模块”， novelty 会被审稿人归到 4 类，需要有强消融或新任务支撑。

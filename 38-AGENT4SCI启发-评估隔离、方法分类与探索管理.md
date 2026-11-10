# 38 · AGENT4SCI 启发：评估隔离、方法分类与探索管理

> 阅读材料：公众号解读《Anthropic：AI 编程智能体能把科学模型改进到什么程度？AGENT4SCI 论文解读》（附件）。本文只提炼机制并映射到本仓库，不把文章中的模型、基准或效果数字当作本仓库已复现结果。AGENT4SCI 的正式主张与数字以原论文为准。

## 1. 这篇文章真正有价值的地方

文章讨论的不是“Agent 会不会做科研”，而是一个更可检验的问题：**当编程智能体拿到论文、代码、数据和指标，持续修改模型时，分数提升是否可信、来自什么、能否重复。**

它给出的关键结论可以压缩成四句话：

1. 在标准化、隔离的测试床上，前沿编程智能体能稳定改善一部分科学 ML 任务；
2. 多数收益来自学习率、架构替换、数据处理、集成等工程方法，而不是对科学结构的理解；
3. 研究构思、实验管理、定期检查三类 Markdown Skills 能提高平均收益，但单项任务仍可能退步；
4. 如果没有独立测试、复现基线、过程审计与验证选择记录，“分数提高”本身不足以支持研究结论。

对本仓库而言，最值得学习的不是“再做一个全自动训练 Agent”，而是**给已有证据闭合系统补上评估完整性（evaluation integrity）与探索过程的对象**。

## 2. 八个可借鉴机制

### 2.1 复现基线，而不是论文数字

AGENT4SCI 先人工复现基线，再让 Agent 相对复现基线改进。论文数字与复现数字可能不同，比较必须使用同一条件。

对我们的映射：claim/run 的 baseline 不能只来自论文摘要；必须有“复现基线”对象、复现条件和差异说明。当前 `RunRecord.baseline` 已有雏形，但缺少 paper vs reproduced 的对照。

### 2.2 三阶段隔离：改进 / 评估 / 审计

- **Improve agent** 只能看论文、代码、训练/验证数据，不能访问测试集；
- **Evaluate agent** 是唯一接触 held-out 的环节；
- **Audit agent** 阅读轨迹，检查测试泄漏、规则改写、结果编造。

这不是提示词约束，而是环境隔离：测试数据不放进改进容器，文件系统不共享。

对我们的映射：S5 运行、claim 人签、closure 是证据闭合；但缺少一个显式的 **EVAL 控制面** 来记录“held-out 是否被访问、评估规则是否冻结、审计是否发生”。

### 2.3 过程审计独立于分数

审计不判断指标高低，只判断获取指标的过程是否合规。审计通过不等于方法科学，审计没发现问题也不等于绝对没问题。

对我们的映射：与现有 gate/lineage 一样，审计应是独立对象，不是 claim 的附属字段。

### 2.4 方法分类：工程改进 vs 领域结构

文章把干预粗略分为超参数、架构、特征、数据增强、损失、集成等工程方法，以及利用任务物理/生物/时间结构的领域方法。分数不能替代方法判断，新颖性还要对照文献。

对我们的映射：需要一份**干预台账**（interventions），记录每次改动的类型、依据与是否只是既有工程组合；claim 只能声明“在什么条件下改善”，不能把工程组合写成机制发现。

### 2.5 验证集也会过拟合

即使不碰测试集，反复根据同一验证集选择方案/种子/集成，也可能让验证分数上升而测试退步。

对我们的映射：需要记录 `validationSelections`，并在审计里把“高频验证选择”标为风险；独立测试访问次数必须限制。

### 2.6 三类 Skills 是过程约束，不是能力魔法

- 研究构思：先查领域 + 方法两条文献线，区分大胆（Tier-1）与稳妥（Tier-2）方案；
- 实验管理：预算、并行、短程 smoke、失败分诊；
- 定期巡检：是否退回纯调参、GPU 是否空闲、探索是否收窄、是否该重排方向。

对我们的映射：现有的 Skills 是“只读检查卡”，正好适合承载这些约束；不需要让 Skill 直接执行训练。

### 2.7 成本与提交可靠性必须一起报告

文章记录了推理时间放大、训练 GPU 小时、首次提交无可用 checkpoint 需要重跑等问题。只报最好分数会高估系统能力。

对我们的映射：EVAL 面板需要记录训练/推理成本和提交/审计状态；后续还应记录重复运行成功率，而不只是最好一次。

### 2.8 结论有清晰适用范围

任务经过七项条件筛选；结果不能外推到所有科学 ML 问题，也不能证明 Agent 具备稳定的科学理解。

对我们的映射：本仓库继续区分 `SIM`、静态控制面与真实 runtime；新增 EVAL 也不能被说成“真实测试隔离已经完成”。

## 3. 已落地到本仓库的改造

### 3.1 EVAL 对象与右侧 EVAL 控制面

`ResearchTask` 新增 `evaluation: EvaluationState`：

```ts
interface EvaluationState {
  baselinePaper: number | null;
  baselineReproduced: number | null;
  hiddenAccessCount: number;      // 0/1，held-out 只评估一次
  validationSelections: number;   // 选择压力
  evalRuleHash: string;           // 评价规则冻结标识
  audit: "pending" | "pass" | "flagged";
  trainCost: number | null;       // GPU·h
  inferenceCost: number | null;   // 相对基线的推理倍数
  interventions: Intervention[];  // engineering / domain 台账
}
```

右侧上下文新增第四个标签 **EVAL**，包含：

- Improve → Evaluate → Audit 三阶段状态；
- held-out 访问 `0/1`、评估规则哈希、审计状态；
- paper baseline / reproduced baseline / 复现差异；
- validation selections 与验证集过拟合提示；
- train cost / inference 倍数 / seeds；
- engineering vs domain 干预占比和逐条台账；
- “提交独立评估（SIM）”与“运行过程审计（SIM）”两个显式动作。

提交评估前要求已有 S5 run；一次运行只允许提交一次 held-out；提交后再次启动手动运行/全自动会被拒绝，必须新建任务或新协议。审计会把 `validationSelections > 10`、规则未冻结、复现基线未登记标为风险。允许/提交/审计都会写入会话 trace。

> 边界：这是前端静态控制面演示，不执行真实 held-out 隔离、训练或密码学审计。真实系统必须由服务端 evaluator/auditor 完成。

### 3.2 四个内置研究治理 Skills

在原有 5 个技能之外新增：

| Skill | 作用 | 状态依据 |
| --- | --- | --- |
| `research-scout` 研究构思 | 双线文献、Tier-1/Tier-2、新颖性对照 | coverage/gap、领域干预数量 |
| `experiment-manager` 实验管理 | 协议冻结、短程 smoke、预算、失败分诊 | protocol/run/budget/seeds |
| `exploration-check` 探索巡检 | 是否退回调参、验证选择压力、探索收窄 | validationSelections、domain share、gap |
| `eval-integrity` 评估隔离 | held-out 次数、规则冻结、复现基线、审计、成本 | EvaluationState |

它们仍是只读检查卡，不调用外部工具、不执行训练、不修改 claim。

### 3.3 持久化与迁移

- `staticAdapter.load` 为旧快照补 `evaluation: emptyEvaluation()`；
- 新任务默认空评估状态；示例“钙钛矿界面钝化”预置一份 SIM 复现基线、验证选择次数、成本与四条干预台账；
- 运行实验/自动 S5a 会登记复现基线与一次验证选择；
- 删除任务/工作区、重置示例仍沿用原逻辑。

### 3.4 与现有证据闭合/RSI 的关系

- **证据闭合**回答“claim 是否有来源与 span 支持”；
- **评估隔离**回答“支持 claim 的分数本身是否可信”；
- **过程审计**回答“分数是怎么得到的”；
- **干预台账**回答“这是工程组合还是领域结构”；
- **RSI**仍然只能提案策略层改动，不触碰 claim/evidence/gate/export。

这四层与 RSI 租约是互补的，不把“指标提升”自动升级成“科学发现”。

## 4. 明确没做的事

1. 没有真实训练、基准测试床或 held-out 测试集；EVAL 数值全部是 SIM。
2. 没有服务端 evaluator/auditor 服务，也没有密码学规则哈希或不可变轨迹。
3. 审计逻辑是启发式：验证选择 > 10、规则未冻结、复现基线缺失会标风险；不是完整学术不端检测。
4. 没有人类研究者对照、重复运行统计、首次提交成功率或真实 GPU 成本。
5. 方法分类只存在前端台账层，没有自动从代码 diff 推断干预类型。
6. 没有把 EVAL 结果接入 claim 的自动拒签；仍需人工解释。

## 5. 下一步优先级

1. **服务端评估服务**：冻结评价脚本、独立 held-out 访问、结果一次性回传、审计日志不可变。
2. **基准/复现 harness**：至少一条真实可复现任务，paper baseline 与 reproduced baseline 分列，跑重复 seeds。
3. **干预分类器**：从 run diff 自动标记 engineering/domain，人工复核；禁止把工程替换写成机制 claim。
4. **重复运行与提交可靠性**：记录首次提交成功、checkpoint 可用、推理时延与成本分布。
5. **EVAL 与 claim/closure 联动**：审计 flagged 时阻断导出或要求额外人签。

## 6. 结论

AGENT4SCI 对本项目最大的启发是：**自动化科研的可靠性，不只取决于 agent 会不会改代码，还取决于系统能否把“改进、评估、审计”三种角色和它们看到的数据分开。**

我们已在淡蓝工作台中加入 EVAL 控制面与四个研究治理 Skill，让复现基线、held-out 次数、验证选择压力、成本、干预类型与审计状态成为可见对象。但它们是控制面与检查卡，不是真实实验隔离。下一阶段若接入真实 runtime，必须先在服务端兑现这些对象，再谈“自动改进”的可宣称能力。

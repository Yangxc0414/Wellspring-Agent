# 56 · TTME 的记忆反馈，照出我们缺的那一层

参考对象：本地 `TTME-main`（*Can Test-Time Memory Evolution Outperform Test-Time Training for
Scientific Discovery?*，Liu/Chen et al.）。它的立场正合我们的约束：**不动权重**，在测试时更新外部记忆，
用执行反馈改写"下一步该怎么想"。我读的是代码不是摘要，逐条对照如下。

## 1. TTME 到底在做什么（读码所得）

| 机制 | 事实 | 出处 |
| --- | --- | --- |
| Guideline Memory | 每条一行 `trigger -> mechanism -> action`，字段只有 `{text, seen, last_seen}` | `ttt/memory/guidelines.py:153-154` |
| 触发 | **每一步都更新，失败也更新** | `ttt/loop.py:195-196` → `manager.py:67-79` |
| 合并 | LLM 只写 ≤3 行，其余全确定性：噪声/模板回声剔除、token-Jaccard ≥0.5 去重并 `seen+1`、`step-last_seen>20` 过期、按 `(seen,last_seen)` 排序截断到 24、渲染 240 字符预算 | `guidelines.py:73-88,134-175` |
| Strategy Memory | 只存"孩子赢过父亲"的策略（描述+分数+谱系，**不存代码**），检索后改写成**针对当前父本的** memo | `memo/transitions.py:46-51`、`memo/stage1.py:100-117` |
| 关键设计 | memo 注入 **64 个子代中的 32 个**，另外 32 个拿对照卡 | `memo/loop.py:26-47`、`config.py:104-105` |
| PUCT | 选的是**父本程序**：`score = Q + c·scale·P·√(1+T)/(1+n)`，失败只加访问数 | `archive/puct.py:115-137,193-195` |
| 防污染 | **没有** holdout/验证门，沙箱分数是唯一裁判；靠引用核验、去重签名、`frozen`（连续 2 次边界不合格就冻结）、家族记忆最多携带 6 步等记账手段 | `microdistill.py:43-75`、`memo/rounds.py:173-201,365-382` |

## 2. 它照出的三个真实缺口

**(a) 我们根本没有 run 内的廉价记忆层。**
我们的"自进化"是 RSI 账本：propose → dry-run → public → hidden → 人签，才能 `active`。那是对的，但它
管的是**能力变更**。我们把"什么都不许自动改"贯彻得太彻底，以致于没有做下面那一层：**自动、低风险、
会过期、只影响提示的教训**。后果是可观测的——同一个 run 里，步骤之间没有任何反馈通道，宿主 Agent
只能靠上下文长度记忆，重复犯同样的可避免错误（比如明知 `origin absent` 会告警还去签）。TTME 每步无条件
更新 guideline、失败也更新，正是这一层的做法。

**(b) 最锋利的一条：记忆需要自带对照。**
TTME 把 memo 只发给一半子代，另一半拿对照卡——**记忆到底有没有用，由本次运行自己的数据每步判定**。
而我们今天是怎么知道"归档 × 门控"有害的？事后单独跑一份声明式因子研究，4 个数据集、3 个功效档
（8/16/32/64 种子），才发现 16 种子下那条看似"归档有效"的正号其实是小样本假象、组合才是稳定伤害。
也就是说：**我们对自己机制的证据是滞后的、离线的，而且一开始是错的。** 如果记忆效果在循环内部就有
对照分臂，这个负效应应该在第一批子代里就浮出来。这是我们和 TTME 之间最实质的设计差距，不是代码量差距。

**(c) 它的防污染比我们弱，这条我们不该学。**
TTME 的唯一裁判是沙箱分数，一条 guideline 不需要指向任何证据。本项目的立身之本恰恰是"生成的文字不许
冒充事实"，所以无引用的教训进提示，正是我们天生要挡的失败模式。

## 3. 已落地（第一片，纯确定性，未接线）

`research_agent/guideline_memory.py` + `tests/test_guideline_memory.py`（9 项通过）+ 规格
`modules/guideline-memory/SPEC.md`（status=draft）。

移植的是确定性记账：三段式解析、单步 ≤3 条、Jaccard ≥0.5 去重印证 `seen+1`、20 步无印证即过期、
`(seen,last_seen)` 排序截断 24、字符预算渲染块、原子写并携带 boundary。

**我们主动加强的一处**：每条记忆必须引用**项目内真实存在的产物路径**。实测两条拒绝——引用指向不存在的
产物 → `sources missing or outside the project`；引用写 `../outside.txt` 想越界 → 同样拒绝（文件确实存在
于项目外，仍不许）。第一版实现还犯了一个具体的错：我用字符类 `[^->\n]` 定义三段式，结果连字符被排除，
任何提到 `from-idea`、`study-evidence.json` 的教训都解析失败——测试直接把整片合并路径打空，改成按
分隔符切分后才绿。**这个 bug 只有测试能抓到，而这正是本项目测试存在的理由。**

边界写进产物：guideline 是提示侧建议，不能创建或修改 Claim、断言、门禁判定或导出数字。

## 4. 明确不移植的部分

- **PUCT 父本选择**：它会改变搜索算法本身，按 `code_fingerprint` 语义会让今天所有研究结论失效；而我们
  当前的结论是关于**现有**循环的。要引入就得作为**新的声明因子**（`parent_selection`）跑一次对照研究，
  而不是替换默认行为。
- **沙箱分数作为唯一裁判**：与本项目的人签门禁不兼容。
- 任何"自动写入并能触达 claim/gate/export"的形态。

## 5. 下一步（按性价比排序）

1. ~~接进生成路径~~ **已完成**：`memory guidelines` 落盘/查看；`block_for(project)` 注入
   `innovation_review._propose` 的生成提示；实测 `host-model turns --prompt` 的 26430 字符中包含记忆块。
2. ~~把记忆效果做成可判定~~ **已完成第一版**：`memory_ab.py` + `memory ab plan|record|compare`，
   两臂只差一个块（新增 `innovation review --no-guidance` → `use_guidance=False`），用运行时**已在执行**的
   确定性检查打分（引用落到 ≥2 个不同来源 / 否证句非空 / `experiment_plan` 过 `validate_plan`），
   配对数 <4 只报 `underpowered` 不给方向。
   **它量出的第一条真实结果就很难看**：`topconf-research-2026` 那次评审被选中的 3 条想法
   `grounded_rate=1.0`、`falsifiable_rate=1.0`，但 **`executable_plan_rate=0.0`**——按今天的档位契约，
   那批想法全都不可执行。这不是示例数字，是工具对自己项目的实测（也是 `57-` 里"跨模块约定缺测试"
   那条判断的具体后果：想法产物与档位契约之间过去没有任何量化关系）。
3. **两臂真实试点已跑完（`propose-only` + 宿主轮次各答一次）**，结果分两段，第二段比第一段更有价值：
   - 第一版 `score_arm` 只用三条运行时**已经在执行**的门（引用落到 ≥2 来源、否证句非空、计划过
     `validate_plan`）。两臂（`guidance_chars` 215 vs 0，各 5 条想法）**四项全 1.0、delta 0.0、方向
     `no_difference`**。原因不是记忆没用，而是**度量选错了**：能存活到产物的想法必然过了这些门，
     天花板上的检查没有分辨力。
   - 于是补三条有动态范围的检查：来源广度均值、**停止规则是否写明 seeds/配对/预算**、是否点名风险。
     重跑立刻出现信号：`power_aware_stopping_rate` **1.0 vs 0.8**、delta +0.2、方向
     `with_memory_better`（1 优 / 0 劣 / 4 平），其余四项 delta 仍为 0。也就是说记忆块确实改变了它
     声称要改变的那一件事（将运行契约写进停止规则），而其它维度没有被无谓地扰动。
   - **不能当作效应量**：两臂都由同一个模型（我）自答，方向部分是构造出来的；且 n=5、仅 1 对不一致，
     `compare` 也只报计数不做统计声明。要出可辩护的效应量，需要不同会话或不同供给分别作答，
     并预先声明配对数与判定阈值。这条边界写进了 `MEMORY_AB_BOUNDARY` 与产物 `reading` 字段。
4. `modules/guideline-memory` 升 pilot 的条件：一轮**非自答**的两臂数据 + 方向与 `55-` 的复现纪律一致。

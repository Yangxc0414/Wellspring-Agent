# 55 · 单数据集 anecdote → 跨数据集复现计数

> 承接 `53-`（声明式因子空间）与 `54-`（闭环可被 Agent 走完）。这两篇解决的是"研究能被执行、
> 被执行的非结果会被如实报告"；本篇解决下一个会被审稿人一句话打死的问题：
> **在一个数据集上集训定，不构成结论。**

## 1. 之前缺的不是统计，是一个能拒绝的对象

`study search` / `study from-idea` 已经能把声明式设计真的跑成研究包，`study_claims.comparison_verdicts`
也已经把每个比较标成 `positive / negative / undecidable / unavailable`。但整个链条上没有任何东西
回答："这个正区间在别的数据上还成立吗？"

把 `dataset` 加成第 5 个搜索因子是最先想到的做法，也是最错的：比较永远对着**参照格**做，参照格
属于某个具体数据集。让一格在 iris、另一格在 wine，差值同时混着"控制回路不同"和"数据难度不同"，
这正是 `51-` 记录过的口径混淆的另一个版本。环境因子与回路因子不能住在同一个设计里。

所以复现必须是**分块（blocking）**而不是因子：同一设计在每个数据集上各跑一次，每个数据集对着
自己的参照格比较，然后在比较名字对齐之后统计。

## 2. 实现：只读、按设计分组、只数判定的数据集

`research_agent/study_replication.py`（schema `study-replication-0.1`）：

1. `load_package()` 读 `<project>/studies/STUDY-*/study-spec.json + study-evidence.json`；
   判定直接复用 `comparison_verdicts`，**不重新推导三态**（单一来源那条不变量继续成立）。
2. `comparability_key()` 取 `{design, metric, budget, min_delta}` 的 sha256 前 16 位。
   **种子数故意排除**：功效允许各数据集不同，但它必须被说出来，于是进了 `warnings`；
   预算不同则直接不是同一个实验，不给分组。
3. `_agree()` 给每个比较一个状态：

   | status | 含义 |
   | --- | --- |
   | `single_dataset` | 只有一个数据集，谈不上复现 |
   | `undecided` | 每个数据集的区间都跨零 |
   | `conflict` | 判定的数据集里出现相反方向 |
   | `one_dataset_decided` | 只有一个数据集训定：**仍是 anecdote** |
   | `consistent` | ≥2 个数据集训定且同向 |

   `generalizes` 只有一种取真：`consistent` 且**组内每个数据集都同向判定**。三个数据集里一个集训定
   两个跨零，不会得到"泛化"这个字。
4. 同一数据集被写了两份 → 归进 `unreplicated`，理由是"同数据是重跑不是复现"。
5. 只读：不重跑搜索、不产 Claim、不改 evidence/claim 的形状，因此已签署断言引用的
   `memory_*` / `gate_*` 度量名不受影响（`53-` 钉住的那条）。

## 3. 本机真实数字（16 种子 × 3 数据集 × 同一 2×2 设计）

`study replicate --project runtime_data/from-idea-check`：

```
packages 4 | status_counts {'undecided': 1, 'one_dataset_decided': 1, 'consistent': 2}
design 93acf117bb219741  datasets ['breast_cancer', 'iris', 'wine']  seeds 16/16/16
  memory_on_gate_on          consistent            negative  decided_in=[breast_cancer, wine]  generalizes=false
  memory_x_gate_interaction  consistent            negative  decided_in=[breast_cancer, iris]  generalizes=false
  memory_on_gate_off         one_dataset_decided   positive  decided_in=[iris]                 generalizes=false
  memory_off_gate_on         undecided                       decided_in=[]                     generalizes=false
unreplicated: pipeline 写出的 wine 设计（min_delta/budget 不同）→ 正确地没有并入本组
```

这三行比之前任何一句都更像结论：

- **"归档 + 贪婪门控"一起用会伤害搜索**：两个独立数据集上负向判定，第三个跨零。
  这是目前最可辩护的发现，也是唯一有资格进 claim 的。
- **"只用归档就更好"明确不泛化**：iris 上 +0.121 CI [0.050, 0.192]，wine/breast_cancer 跨零。
  如果没有这一层，上一轮的报告会把它写成"改进"。
- 交互项与主效应的**判定集合不同**（breast_cancer+iris vs breast_cancer+wine）：这本身就是
  一个该写进讨论的现象，而不是噪声。

`generalizes` 全为 false 是诚实的输出，不是失败：三个数据集里要出现"处处同向判定"，
需要更高功效或更稳的效应。系统能说的是"哪些数据集判定了它"，不是"让它变成 true"。

### 3b. 把功效提到 64 种子：`generalizes=true` 出现了，而 anecdote 死了

同一命令、同一设计、`--seeds 1..64`，写进新项目 `runtime_data/replication-64`（不覆盖 16 种子那三份）：

```
packages 3 | counts {'undecided': 2, 'consistent': 2} | warnings []
design 93acf117bb219741  datasets [breast_cancer, iris, wine]  seeds 64/64/64
  memory_on_gate_on          consistent  negative  decided_in=[全部 3 个]  GENERALIZES=True
      breast_cancer -0.1240 [-0.1724,-0.0755]   iris -0.1070 [-0.1549,-0.0592]   wine -0.1135 [-0.1581,-0.0690]
  memory_x_gate_interaction  consistent  negative  decided_in=[全部 3 个]  GENERALIZES=True
      breast_cancer -0.1276 [-0.1893,-0.0659]   iris -0.0932 [-0.1605,-0.0260]   wine -0.1031 [-0.1694,-0.0368]
  memory_on_gate_off         undecided   decided_in=[]
      breast_cancer -0.0182   iris -0.0143   wine -0.0089   ← 点估计全部回到 0 附近，甚至转负
  memory_off_gate_on         undecided   decided_in=[]
```

这一轮才真正说明这套东西在做科研而不是在产出数字：

1. **出现了可泛化的发现**：两个比较在**全部三个**数据集上同向判定，`generalizes=true`。交互项三个
   值（−0.0932/−0.1031/−0.1276）与 `README` 里 64 种子旧运行器记录的号码**逐位一致**——同一份数据
   由两条不同代码路径得到，这是复现而不是重复打印。
2. **上一轮的 anecdote 被更多数据杀死了**：16 种子时 iris 的 `memory_on_gate_off` 是
   `+0.1208 CI [0.0500, 0.1916]`（看着像"归档有效"），64 种子后三个数据集**全部跨零**、点估计落在
   −0.018…−0.009。所以"只用归档就更好"不是"暂时没泛化"，而是**小样本假象**；没有复现计数这一层，
   它会作为发现写进报告。
3. 结论因此收窄成一句更强的话：**归档与贪婪门控单独都没有好处，两者一起用稳定伤害搜索**
   （三份独立数据、同号、区间不跨零）。
4. `warnings` 为空：三组种子数相同，没有功效不对称可告警——相等就不吵，这也是设计的一部分。

## 5. 功效阶梯：复现的另一半是"同数据、更多种子"

跨数据集只解决"换个环境还成立吗"。§3b 那个 anecdote 的真正死因是另一件事：**同一份数据上
种子太少**。把 16 种子与 64 种子的同一设计放进同一个 `studies/`（`runtime_data/power-ladder`），
`study-replication-0.2` 会做两件新事情：

1. `_power_ladder()` 按 `(design_key, dataset)` 折叠：**最高功效的那份代表该数据集**参与同意计数
   （否则同一批数据会被数成两票，`consistent` 就能被自我重复刷出来）；
2. `_overturned()` 比较同一阶梯的两端：低功效判定为 `positive/negative`、而高功效变成
   `undecidable` → `区间在更高功效下重新跨零`；同号变反号 → `方向在更高功效下翻转`。

本机真实输出（只有该被抓住的那一条被抓住了）：

```
packages 2 | power_ladders 1 | overturned 1
  memory_on_gate_off   STUDY-IRIS-16 positive CI [0.0500,0.1916] → STUDY-IRIS-64 undecidable CI [-0.0630,0.0344]
  （memory_x_gate_interaction 两个功效都是 negative 且判定 → 正确地没有被标为 overturned）
```

三件事因此不同：同数据集**同种子数**重复写只产生一句"identical numbers，这对功效什么也测不出"的
warning，不产生 overturned；`generalizes` 仍要求每个数据集都同向判定；而被推翻的那个包**自己**
不再拿到 `human_gate`：

`loop_ledger._overturned_comparisons()` 把被更高功效推翻的比较从 `decidable_comparisons` 里剔除，
若剔完为空，动作从 `human_gate S5b`（去签）降级为 `study_no_finding`（这是非结果），并在消息里点名
"这条判定不作为可签署依据"。实测（真实包）：`STUDY-IRIS-16 → ['memory_on_gate_off']`、
`STUDY-IRIS-64 → []`——推翻者保留自己的结论，被推翻者不再被建议去签。
第一版这里出过一个真 bug：过滤只按 design+dataset，于是 64 种子包被**自己的**证据判定为"已被推翻"，
是新增的那条测试把它抓出来的。

工作台在 CLOSURE PROFILES 下多一个 `overturned` 行：数据集、比较名、原因、
`positive @16 种子 = 0.1200 → undecidable @64 种子 = -0.0143`，以及一句"这条低功效判定不能签成结论，
已被 <更高功效包> 取代"。

### 3c. 加第四个独立环境：结论更强，同时冒出一个新现象

三个数据集是复现的天花板，所以把 `digits`（sklearn `load_digits`，10 类 64 特征）加进
`search_lab.DATASETS`——注册表改动：`study search`/`pipeline --study-dataset` 的选项与
`study_from_idea` 的拒绝文案都从它生成（原来硬编码着三个名字），档位声明的数据集也自动带出。
同一 2×2 设计、预算 60、digits 32 种子 / 其余 64 种子（`runtime_data/replication-4`）：

```
memory_on_gate_on          consistent  negative  decided_in=[breast_cancer, digits, iris, wine]  GEN=True
    digits -0.1797 [-0.2368,-0.1226]   ← 四个环境里最大的伤害
memory_x_gate_interaction  consistent  negative  decided_in=[breast_cancer, iris, wine]          GEN=False
    digits -0.0078 [-0.0694, 0.0538]   ← 未判定
memory_off_gate_on         one_dataset_decided  negative  decided_in=[digits]                     GEN=False
    digits -0.1625 [-0.2098,-0.1152]   ← 只开门控不开归档，在更难的地形上也伤害搜索
memory_on_gate_off         undecided  decided_in=[]（四环境全部跨零）
```

三条读数，一条比一条重要：

1. **主发现升级为四环境同号判定**：`generalizes=true` 现在覆盖一个 10 类 64 特征的地形，而且那个
   地形上的伤害最大。这是整条链目前最可辩护的一句话。
2. **交互项经功效检验后，真的不泛化**：随后把 digits 也跑到 64 种子（`studies/digits64`，与 32
   种子那份同设计同数据集 → 形成功效阶梯，报告自动取高功效那份代表 digits，`warnings` 归零、
   `overturned` 为空），结果 `memory_x_gate_interaction` 在 digits 上仍未判定，而其余三个环境同号判定
   → `consistent` 但 `generalizes=false`。**混淆已被排除**：这不是 32 种子功效不足，而是交互效应
   确实只在二/三类的小地形上出现。与此同时 `memory_on_gate_on` 是 4/4 同号判定 `generalizes=true`。
   两句合起来就是机制读数：**组合造成的加性伤害普遍存在，超加性的交互是地形依赖的。**
3. **冒出一个旧框架问不出来的现象**：`memory_off_gate_on`（只有门控）在 digits 判定为负、在另外
   三个数据集跨零。`one_dataset_decided` 这个状态正是为它而存在：不放过，也不写成结论。

顺带验证了确定性：改码后 iris/wine/breast_cancer 三份 64 种子包与改码前的 `replication-64`
**逐位相同**（−0.1240/−0.1070/−0.1135）。同时暴露 `code_fingerprint()` 是整文件哈希——纯注册表
改动也会把旧包算成 stale，这条保守性这次由"数值相同"人工判定为无实质影响。

### 3d. 第一个"过早判定的代价"数字：11.1%（27 条低功效判定中 3 条不再成立）

把 `power_audit` 加进报告后，直接对**磁盘上已有的 25 个研究包**（`study replicate --project …` 含同级根）算：

```
ladders 5 | decided_at_lower_power 27 | overturned 3 | reversal_rate 0.1111
by_type   {interval_returns_to_zero: 3}         ← 没有一例是方向翻转
by_power  {8->64: 1, 16->64: 1, 32->64: 1}
per_dataset  iris 10 判定 / 3 被推翻；wine 7/0；breast_cancer 8/0；digits 2/0
```

读数（以及不能说的话）：

1. **在这套数据上，"低功效就下结论"的代价是 11.1%**，且**全部表现为区间回到零**，没有一条是
   符号翻转——方向是稳的，不稳的是"能不能判定"。这决定了防护应当长成"剔除可签署断言"，
   而不是"怀疑结论方向错了"，也正是 `study claim` 现在的行为。
2. **反转全部集中在 iris**（10 条低功效判定中 3 条失手），wine/breast_cancer/digits 为 0/7、0/8、0/2。
   但这**不能读成"iris 更爱骗人"**：只有 iris 被我刻意跑到 8/16/32/64 四档，其余环境大多是单档或两档，
   分母本身就是选择的产物。诚实表述是：**在拥有多档功效覆盖的数据集上，反转率 3/10；其余档口不足以测量。**
3. 这条数字第一次让 `13-` 里的 **N5（闭合代价）**有了可引用的量，也让 `57-` 那句
   "护栏有没有用"从信念变成可测：如果 claim 路径不剔除这 3 条，它们会作为可签署断言进入人签环节。
4. 复现命令：`python -m research_agent study replicate --project <项目>`（默认含同级项目），
   读数在 `power_audit`；工作台在 CLOSURE PROFILES 顶部显示同一句话。

### 3e. 新因子答出一个新问题：贪婪选父本比随机选父本更差（3/3 复现）

`parent_selection` 加进注册表后（第一水平 `uniform` 就是既有行为），第一次跑出一个**过去问不出来**的
问题："保留归档之后，下一步该从归档里挑谁？"设计 = memory × parent_selection 2×2、32 种子 ×
iris/wine/breast_cancer，度量 `improvement_per_evaluation`，两水平共用同一条变异随机流（CRN），
所以差异可归因于策略本身。参照格 = `memory_off_gate_off_parent_selection_uniform`。

| 比较 | breast_cancer | iris | wine | 判定 | `generalizes` |
| --- | --- | --- | --- | --- | --- |
| `memory_on_gate_off_parent_selection_best` | −0.2365 [−0.3008,−0.1721] | −0.1578 [−0.2161,−0.0996] | −0.1922 [−0.2578,−0.1266] | 三处一致负 | **true** |
| `memory_on_gate_off_parent_selection_uniform` | −0.0255 [−0.0939,+0.0428] | **+0.0573 [+0.0031,+0.1114]** | −0.0109 [−0.0786,+0.0567] | 只有 iris 判定 | false |

读数：

1. **"有归档就随机挑父本"其实没有好处**：只有 iris 上为正（且刚好越过零，CI 下界 0.0031），
   另外两个环境跨零、点估计为负。这是同一条 anecdote **第三次**在不同功效档上出现（16 → 64 消失、
   32 又出现、换因子后仍只在 iris 成立）。它现在进不了 claim：`study claim` 会把它留在
   `not_signable`，`generalizes=false` 也写在盘点里。
2. **"有归档但贪婪挑最好的当父本"是稳定伤害**：三个环境同号判定为负、幅度 −0.16 ~ −0.24，
   比之前发现的"归档×门控"组合伤害同量级。机制读法（是解释不是结论）：贪婪选父本把搜索压成
   单点爬山，归档的多样性被自己抵消掉了。
3. 因此本项目现在的完整说法变成：**"保留历史"这件事的价值完全取决于你怎么用它**——
   随机从中取样近乎中性，贪心取最优反而有害，而叠加贪婪验收门控则三处一致最坏。
4. 边界照旧：这测的是确定性搜索回路的控制策略，不是真实智能体的自我修改；数字来自 25→28 个真实
   研究包中的 3 个新包，`study replicate` 可复算（同种子同控制 ⇒ 同数值）。

### 3f. 留出检验：护栏拦下的那条断言，在**全新种子**上也没有复活

§3d 的反转率与 `57-` §3.8 的两臂对照都只用**已经在池子里**的证据做裁判，这构成一个循环风险：
护栏之所以判 `memory_on_gate_off` 不可签署，是因为同项目的 @64 包区间跨零——如果 @64 本身就是运气，
护栏就是"用一个偶然否定了另一个偶然"。要打破循环，必须拿**没参与过这次判定的数据**再跑一次。

设计（两个新包，都不在任何用于拦截的证据池里；`runtime_data/guard-heldout-studies/studies/`）：

| 包 | 种子 | 与拦截证据的关系 | `memory_on_gate_off` | `memory_off_gate_on` | `memory_on_gate_on` |
| --- | --- | --- | --- | --- | --- |
| `STUDY-IRIS-65-128` | 65…128（64 个） | **完全不相交**：@16 用的是 1…16，@64 用的是 1…64 | −0.01094 [−0.05869, +0.03682] 跨零 | −0.03542 [−0.09613, +0.02529] 跨零 | −0.12344 [−0.16870, −0.07818] 负向判定 |
| `STUDY-IRIS-128` | 1…128（超集） | 包含被拦样本，但多 64 个新种子 | −0.01263 [−0.04627, +0.02101] 跨零 | −0.01745 [−0.05926, +0.02436] 跨零 | −0.11523 [−0.14776, −0.08271] 负向判定 |

读法与结论：

1. **护栏没有过度拦截**。那条被拦的 anecdote（@16 上 +0.1208、CI [0.0500, 0.1916]）在**一批从未参与
   判定的新种子**（65…128）上仍然是跨零、点估计 −0.011，与 @64 的 −0.018…−0.009 同一量级。
   这不是"另一个偶然否定了偶然"，而是三次独立抽样（1…16 / 1…64 / 65…128）里它只第一次成立。
2. **不相交样本比超集更有说服力**：`STUDY-IRIS-128` 与前两者共享数据（是嵌套样本），单独看它只能算
   加强；真正切断循环的是 `STUDY-IRIS-65-128`——它与两个旧包**一粒种子都不共用**，功效却相同（64）。
3. **同一批数据里，被保留的结论也站住了**：`memory_on_gate_on` 在两个新包上都是负向判定
   （−0.1234 / −0.1152），与 `55-` §3b/§3c 的 4 环境同号结论同量级；`memory_off_gate_on` 仍跨零
   （除 §3c 里更难的 digits）。也就是说留出检验同时给护栏发了一张"没冤枉人"和一张"也没漏放"的条。
4. 边界：留出检验仍只覆盖 iris（唯一被我刻意跑到多档功效的数据集），且仍是配置层面的结构类比，
   不是任何已发表智能体的复现。这两个包是本轮唯一新增的证据；护栏本身的规则没有因结果而改动。
5. **这条检验还顺带照出一个退化**：两个留出包刚写盘时被 `study replicate` 放进了 `unreplicated`——
   0.20.0 新增 `parent_selection` 因子后，新包的 `design` 多了 `parent_selection=['uniform']` 一项，
   比较键随之改变，而旧包从未声明该因子。也就是说"护栏是否过度拦截"这件事，运行时当时**说不出**，
   只能靠我人工比较两个目录的数值。修好可比性规则（停在在任水平的单水平因子不进比较键，
   见 `57-` §3.10 与 search-study v0.23.0）之后，报告自己给出：iris 阶梯 8 包
   `[8,16,32,64,64,64,64,128]`、被拦断言的 `superseded_by = STUDY-IRIS-128`、
   `memory_on_gate_off` 在该设计组 `status=undecided / decided_in=[]`（4 个数据集都未判定），
   `power_audit` 分母 27→31、反转率 11.1%→9.68%。同一批次重跑 @128 包三位小数逐位相同，
   确定性未受影响。

复现：`study search --dataset iris --seeds 65,66,…,128 --budget 60 --min-delta 0.005`（同控制同种子
⇒ 逐位相同），再 `study replicate --project runtime_data/guard-heldout-studies`；
两臂对照与开火率见 `57-` §3.6/§3.8。

## 6. 接进闭环与页面

- `loop_ledger._replication_action`：研究包存在且该设计只在一个数据集上 → `next_actions` 追加
  `study_replication`，带 `datasets_present / datasets_untried` 和一条可执行命令
  （`study search --dataset <未试> --seeds <沿用> --budget <沿用> 仅多水平 --factors && study replicate`）。
  **它会自己消失**：同设计出现第二个数据集后该设计进入 replicated 组，动作不再出现，不长期 nag。
  没有声明设计的包不给建议（不凭空猜哪个包是"当前这个"）。
  实测三数据集齐备后 `pending_study_actions` 只剩 2 条 `human_gate`，`study_replication` 为 0 条。
- `closure_profiles.detect_project_profiles` schema 升到 `closure-profiles-0.3`，多一个 `replication`
  字段；runtime 的 `/api/project-closures` 与 CLI `closure profiles` 共用它，没有新端点。
  摘要剥掉绝对路径与逐格区间（页面回答"几个数据集判定"，不复制第二份证据）。
  实测 `curl …/api/project-closures?project_dir=runtime_data/from-idea-check` →
  `schema=closure-profiles-0.3, packages=4, groups=1, unreplicated=1`，响应中不含仓库绝对路径。
- 工作台 CLOSURE PROFILES 下新增 `replication` 行：数据集列表、每个比较的状态、
  `decided_in`，以及两句边界文案（`generalizes` 为假时"其余数据集区间跨零：不能说它泛化"，
  种子数不等时"可能只是功效差异"）。`tsc --noEmit` 与 `vite build` 均通过。

### 6b. 复现也可以由想法驱动（补上一个真实空缺）

`study closure` 对本文最强的那条结论给出过一条 warning：
`origin.present: no study-origin.json: this study is not traceable to an idea that asked for it`。
原因很实在：那些包是手写的 `study search` 产出的，而 `study from-idea` 只会跑想法声明的**那一个**
数据集。于是"最有说服力的证据反而说不出它是为谁做的实验"。

现在 `study from-idea --datasets iris,wine,digits`（或 `all`，取自 `DATASETS` 注册表）一次把**同一
声明设计**跑到每个环境，写 `STUDY-<idea>-<dataset>`，每个包都带同一个想法的 `study-origin.json`；
单数据集时的目录名和返回形状不变（流水线研究臂不受影响）。拒绝全部发生在写第一个文件之前：
未知环境（文案列出注册表里的全部环境）、同名重复、目标已有研究而未 `--force`——不会留下半套复现包。
多环境结果返回 `studies[]`、`next`（直接给出 `study replicate --project …`）与一段 boundary，
说明这些包共享设计、只差环境，因此**可以**被计为复现，且每个都保留想法溯源。

`loop status` 侧同步：`study_replication` 动作现在优先给 `study from-idea --datasets <未试环境>`
（带溯源的复现），没有 origin 才退回因子式 `study search`；`study_execution` 动作多出
`replication_option="--datasets all"`。

实测（`runtime_data/idea-replication`，IDEA-01，`--datasets all`，**32 种子 × 4 环境**，
包名 `STUDY-IDEA-01-{breast_cancer,digits,iris,wine}`）：

```
packages 4 | warnings 0（同功效，无需警告）| counts {consistent:2, one_dataset_decided:2}
  memory_on_gate_on          consistent negative decided_in=[breast_cancer, digits, wine]  GEN=False
  memory_x_gate_interaction  consistent negative decided_in=[breast_cancer, iris, wine]    GEN=False
  memory_on_gate_off         one_dataset_decided positive decided_in=[iris]               GEN=False
  memory_off_gate_on         one_dataset_decided negative decided_in=[digits]              GEN=False
closure(STUDY-IDEA-01-digits): unresolved=[claim.present]，warnings=[] ← origin 那条 warning 消失了
```

这一份数据比"全部 GEN=True"更有说服力，因为它把两条真实张力同时摆出来：

1. **溯源补上了**：digits 包的 closure 只剩"没有人签的 claim"这一条未闭合，`origin.present` 警告
   消失——跨环境证据现在说不出"它是为谁做的实验"这个漏洞不存在了。
2. **同一发现在 32 与 64 种子下不一致**：`memory_on_gate_on` 在 64 种子是 4/4 判定（GEN=True），
   在 32 种子上 iris 未判定（GEN=False）；`memory_on_gate_off` 的 iris 正号在 16 种子出现、64 种子
   消失、**32 种子又出现**。这正是 `generalizes` 要求"每个环境都判定"的理由，也是功效阶梯存在的
   理由：把 iris@64 也放进同一个 `studies/`，报告会取高功效那份代表 iris，并自动消掉这条 32 种子的
   正号——不需要人记得这件事。
3. 两条 `one_dataset_decided`（iris 的归档正号、digits 的门控负号）被**记下来而不写成结论**，
   而 digits 的门控负号在 32 与 64 两个功效下都判定为负，说明它是真的地形依赖而非功效假象。

## 7. 边界与复现

边界原文（写进产物，不只在文档里）：

> agreement across datasets is a count, not a test: it cannot create a finding, cannot turn an
> undecidable comparison into a result, and says nothing about datasets that are not listed here

它**不是** meta-analysis：不做异质性检验、不给合并效应量、不产出 p 值。它只做一件审稿人也会做
的事——数一数有几个数据环境真的判定了它，并拒绝把"试过三个"说成"在三个上成立"。

```bash
python -m research_agent study replicate --project <项目> [--output-dir <目录>]
python -m research_agent closure profiles --project <项目>   # replication 字段随盘点一起出
python -m research_agent loop status --project <项目> --run-id RUN-...  # 单数据集时给出该动作
python -m pytest tests/test_study_replication.py tests/test_loop_ledger.py
```

## 8. 仍没做到的

- **overturn 判定只看同一个 `studies/` 目录（本轮发现的新限制）**：`runtime_data/idea-replication`
  里 IDEA-01 的 `memory_on_gate_off`（iris@32 positive）会被 `next_actions` 推荐去签，而同一个人的
  `power-ladder` 项目里同一条比较已被 iris@64 判为未判定。跨项目证据目前互相看不见——要么让复现/
  推翻检查接受额外的 studies 根（`--also <path>`），要么建一个用户级设计登记表。这是下一步最该做的事，
  因为它正好是这条链最需要防的失败模式：**在别的目录里已被推翻的结论，在这里被鼓励签署**。
- 顺带修掉本轮自己引入的闭环 bug：ledger 只找 `STUDY-<idea>`，而 `--datasets all` 写的是
  `STUDY-<idea>-<dataset>`，四环境都跑完的 IDEA-01 曾被报成"从未执行"（会让宿主把四份研究重跑）。
  `_idea_package()` 现在按前缀识别、优先想法声明的环境；实测修复前 `[(study_execution,IDEA-01),
  (study_execution,IDEA-02)]`，修复后 `[(human_gate,IDEA-01→STUDY-IDEA-01-iris), (study_execution,IDEA-02)]`。
- 可执行环境仍只有四个（iris/wine/breast_cancer/digits），"复现"的上限就是四个独立环境；要更强的
  话需要新的可执行档位，而不是把同一档位多跑几遍。
- `code_fingerprint()` 仍是整文件哈希，任何一次编辑（含注释）都会让旧包的 `code.unchanged` 变成
  blocker。本轮试过"canary 相同就降级"，被既有守卫测试正确拒绝（canary 只覆盖 iris 的一个 2×2，
  用它解除阻断不安全），所以最终只加**正向证据**：`study closure --verify-repro` 重跑本包自己的
  控制集并比较 `study_sha256`。实测 `replication-64/studies/iris`（64 种子）：同一份报告里
  `code.unchanged=fail` 与 `code.reproduced=pass` 并存——"代码确实变了，但这些数字在当前代码下
  逐字节重现"第一次成为产物字段，而不是人肉对比。
- `generalizes=true` 已在 64 种子 × 3 数据集上出现两例（见 §3b），但**尚未**变成 claim/closure 的
  一部分：签署路径仍只看单个研究包的比较，跨数据集的复现证据还没进 `evidence_refs`。
- 页面这块**已**在真实 headless Chrome 里逐行确认（`node scripts/web_page_check.mjs --project ladder
  --expect overturned`）：`replication` 组行、`overturned` 行（`positive @16 种子 = 0.1208 →
  undecidable @64 种子 = -0.0143` + "不能签成结论"那句）、`unreplicated` 阶梯说明与边界原文都在
  DOM 里。In-app Browser 那条路仍然不能用——它的视口宽度是 0，React 右侧栏根本不布局。
- 宿主 Agent 侧不是只有网页：走 MCP/HTTP/Python 共用的 dispatch 层实测
  `research_closure_status` 与 `research_status` 的返回里都含 `replication` + `overturned`
  （`crosses zero again` 那条原因文案也在），所以 Claude Code / Codex / Zcode 接进来时看到的是
  同一份判定，不必打开工作台。

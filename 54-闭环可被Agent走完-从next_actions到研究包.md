# 54 闭环可被 Agent 走完：从 next_actions 到研究包

> 状态：已实现，并在真实 stdio MCP 上走了一遍状态推进。
> 代码：`research_agent/loop_ledger.py`（`pending_study_actions`）、
> `research_agent/mcp_server.py`（`_next_actions` 接入，含无 task 记录的原生 run）。
> 规格：`modules/orchestrator`/`modules/integration`（见各自 changelog）。

## 1. 缺口：闭环有每一环，但没有"下一步"

前三轮把环节补齐了：可执行面注册表（`51-`）、独立评审可解除（`52-`）、声明式因子与
idea→experiment 执行（`53-`）。但 `research_next_actions`——宿主 Agent 实际读取的接口——
**看不到研究这一环**：它知道 support ledger、human gold、`experiment approve`，却不知道
"这个 run 有一个已绑定可执行档位、还没有研究包的想法"。

结果是闭环只在人脑里成立。Agent 拿到 G1 之后的动作是空白，只能靠人记得去敲
`study from-idea`。自动化科研的"自动"如果要求操作者自己记得下一步，那它就没有自动。

## 2. 设计：动作指向 CLI，执行仍留在本地

沿用 `experiment_approval` 的既有形状：**动作给出可原样执行的命令，服务器不代为执行**。

| 状态 | `kind` | gate | 语义 |
| --- | --- | --- | --- |
| 有想法、无研究包 | `study_execution` | S5 | 想法绑的是可执行档位，但没跑过；命令里带上 seeds/budget |
| 跑过、无区间排除零 | `study_no_finding` | S5 | **非结果**：加种子/预算或收窄主张，不要重跑到绿灯 |
| 跑过、有可判定比较 | `human_gate` | S5b | 证据就绪，下一步是人的 claim 决定 |
| 跑过且已有 claim 草稿 | （无动作） | — | 不再重复提醒 |

三条都是**同一份数据的投影**，不新增状态存储；判定读的是 `studies/STUDY-<idea_id>/` 目录与
`study-evidence.json` 的区间，因此不存在"动作说有、闭包说没有"的双口径。

无 `task.json` 的原生 run（Qoder 直接建的 run）同样能看到动作：`_next_actions` 原先在这种
run 上只会返回 `inspect`，现在把研究动作并进同一分支——想法在盘上，不该因为缺一条任务记录
就消失。

## 3. 实测：走一遍，状态自己推进

在一份只含 `innovation-review.json`（无研究包）的 project 上，通过真实 stdio MCP 连读两次
`research_next_actions`，中间**原样执行动作里的命令**：

```
BEFORE  study_execution IDEA-01  $ ... study from-idea --idea-id IDEA-01 --seeds 1..8 --budget 60
        study_execution IDEA-02  $ ... study from-idea --idea-id IDEA-02 ...

RUNNING THE ACTION AS WRITTEN → exit 0

AFTER   study_no_finding IDEA-01  "study executed but no comparison excludes zero: this is a
                                   non-result. Add seeds/budget or narrow the claim; do not
                                   re-run until a directional finding appears."
                                   decidable_comparisons=[]
        study_execution  IDEA-02  （仍未执行，动作保留）
```

三件事被这一次walk 证明：动作是**可执行的**（不是提示语）；执行**改变了状态**（IDEA-01 从
"没跑过"变成"跑过且无结论"）；未执行的想法**不会被吞掉**（IDEA-02 仍在队列里）。
最值得注意的是第二件的内容：Agent 得到的是"这是非结果"，而不是一个可以被反复重跑刷出来的
绿色状态——这正是不把不可判定包装成进展的那条线（`51-`/`53-`）。

## 4. 边界

- 服务器只**指向**命令，不执行研究、不签 claim、不越过任何人工门；`HUMAN_ONLY` 边界文案不变；
- 动作只看 top-3 想法，避免在一次状态读取里塞进过多待办；
- `study_no_finding` 不提议任何"再跑一次"的命令：加种子是一个**新的、更贵的设计决定**，
  应当由人显式作出，而不是由提示语顺手引导；
- 动作的存在不等于动作正确：命令里的 seeds/budget 是默认建议，跑之前值得先看
  `study profiles` 的因子空间与 `cannot_test`。

### 4.1 这条边界在一次真实重跑中被抓到

写完上面那句"不要重跑到绿灯"之后，同一次证据整理里就发生了它：IDEA-01（iris）在 8 种子下
**无任何可判定比较**，把种子加到 16 之后 `memory_on_gate_off` 变成可判定；IDEA-02（wine）
同样从 8 的跨零变成 16 的可判定。**加种子确实能把"非结果"变成"结果"**——所以这不是
"再跑一次看看"，而是功效设计的改变，必须留痕。

因此 `study from-idea --force` 现在在覆盖旧包时比较控制参数：若 `seeds`/`budget`/`design`/
`dataset` 任一改变，新 `study-origin.json` 写入

```
revised_from = { changed: ["seeds"], previous_seeds: 8, previous_budget: 60,
                 previous_study_sha256: …, previous_study_spec_sha256: …,
                 note: "… the previous result is no longer on disk and must not be
                        cited alongside these numbers" }
```

参数完全相同的重跑不写这个字段（那只是复现，同一设计同一数据得到逐位相同的结果）。
`runtime_data/from-idea-check/studies/STUDY-IDEA-0{1,2}` 两份产物都带着
`changed=["seeds"], previous_seeds=8` —— 也就是说，本项目第一次把想法跑成结论的那两份证据，
其功效升级在盘上可见，而不是被"我们用了 16 个种子"这句话掩盖。

## 5. 一条命令也能带上研究臂

`next_actions` 让 Agent 知道下一步；`pipeline run --study-dataset iris --study-seeds 8` 让
**一条命令**自己走完 调研 → 想法 → 设计 → **真实执行的研究** → 写作。研究臂不冒充 S5：
它不调用 `RunAgent`、不伪造 RunCapsule/EA，而是产出同一套 `studies/STUDY-<run>/` 包，
`PipelineResult.study` 与 `report.md` 的"搜索研究臂"节直接列出每个比较的三态。

口径在这里被钉死：研究臂的度量**固定**为搜索效率（`improvement_per_evaluation`），设计自己的
`primary_metric` 只作为 `declared_primary_metric` 上下文携带。把内层目标当研究结论，正是
`51-` 里"把文献语料写进 dataset"那次口径混淆的同一形状。

拒绝而不是跳过：数据集不属于该档位（例如 `chemlab`）、或设计声明种子 <4 且未显式
`--study-seeds` 覆盖时，流水线以 `PipelineError: study arm refused: …` 失败——操作者显式要求了
这个臂，静默降级会产出"说做了其实没做"的稿件。

实测（fixture 语料 + iris，8 配对种子 × 预算 60）报告原文：

```
## 搜索研究臂（S5 study arm）
- 研究包：runtime_data/pipeline-study/studies/STUDY-PIPE-… · dataset=iris · seeds=8 · budget=60
- `memory_on_gate_off`：不可判定 · 点估计 0.104167 · 95% 区间 [-0.049149, 0.257483]
- `memory_off_gate_on`：不可判定 · 点估计 0.070833 · 95% 区间 [-0.159178, 0.300845]
- `memory_on_gate_on`：不可判定 · 点估计 -0.041667 · 95% 区间 [-0.228161, 0.144828]
- 本轮没有任何比较的区间排除零：**这是非结果**。…
- 下一步仍是人工：`study claim`（人签）→ `study closure`；报告不写入未签结果数值。
```

`study-origin.json` 的 `source=pipeline_design`，并带上该 run 的 `idea_id`、假设与
`experiment_plan`，所以从一条流水线命令产出的证据也能回答"这些数字是为了检验哪个想法"。
执行入口有两处（`study from-idea` 与流水线研究臂），但只有 `execute_study_plan` 一份实现——
覆盖保护、升级留痕、origin 绑定都在同一处，两个入口不会各自漂移。

可见性也是同一处规定的：研究包默认落在 run 输出旁边的 `studies/`，而那份目录**不在任何
research project 里**，闭包盘点与 `research_status` 就看不见它。流水线因此会显式警告，
`--study-project <project>/studies` 可以把它放进真实项目。实测：

```
$ pipeline run … --study-project runtime_data/from-idea-check/studies
inventoried studies:
  studies/STUDY-IDEA-01                     iris  origin=bound  IDEA-01
  studies/STUDY-IDEA-02                     wine  origin=bound  IDEA-02
  studies/STUDY-PIPE-20261029T125014Z-…     wine  origin=bound  IDEA-01
```

顺带一次真实的副作用观察：这次跑 `pipeline run` 时，仓库默认网关里 `idea/experiment/paper`
已绑到无密钥 host_agent profile，于是流水线在假设生成那一步挂起成宿主交接并打印 exit 3 的
修复指引——正是上一轮为无 key 路径加的那条 CLI 语义，在默认配置下自己生效了。

## 6. 复现

```bash
python -m research_agent loop status --project <项目> --run-id RUN-...   # next_actions 里有 study_*
python -m research_agent study from-idea --project <项目> --run-id RUN-... --idea-id IDEA-01 \
  --seeds 1,2,3,4,5,6,7,8 --budget 60                                     # 原样执行动作
python -m research_agent loop status --project <项目> --run-id RUN-...   # 状态已推进
python -m pytest tests/test_loop_ledger.py tests/test_study_from_idea.py
```

MCP 侧：`research_next_actions({project_dir, run_id})` →
`next_actions[].kind ∈ {study_execution, study_no_finding, human_gate}`，
`study_execution.command` 可直接执行。

> 2026-10-29 追记：这一层现在多了 `study_replication`（单数据集时给出该跑哪个数据集），
> 复现语义见 `55-单数据集anecdote到跨数据集复现计数.md`。另外实测到一个运维事实：
> stdio MCP 服务是长驻进程，改了 `research_agent/` 之后必须 `/mcp reload` 才生效——
> 当天 `research_next_actions` 仍返回旧的 `inspect`，而同一份代码在进程内调用
> `_next_actions()` 返回 2 条 `human_gate`，差别只在服务进程加载的是旧代码。

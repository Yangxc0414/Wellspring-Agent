# 124-组会汇报准备：FlashRSI 跑通与 Harness² 基本理解

> 用途：下次组会前的准备清单与讲稿骨架。
> 状态基线：2026-11-18。所有读数来自本机落盘产物，复跑命令见 §11；不含未测量的主张。
> 一句话：**外部引擎这条供给路径通了，但效应量还测不出来**——这不是失败，是当前证据边界。

---

## 1. 一页结论（开场就说这三句）

1. **FlashRSI 不是"装好了"，是完整演化实验跑完了**：12 次宿主作答零失败、候选被严格改进门拒收、sealed test 落盘。
2. **Harness² 不是"看了文档"，是四个机制级理解 + 桥接 10/10 checklist 全过**：预算恒等式、选择/评分分离、grader tripwire、经验库整树携带。
3. **两者与我们的平台是正交的三件事**：FlashRSI 管"广度"（skill 演化），Harness² 管"深度"（改 harness 自身），我们管"治理"（人签/判定/证据）。三者可以用同一个 localqa 任务面拼起来。

---

## 2. 导师任务回执

| 导师要求 | 状态 | 证据 |
| --- | --- | --- |
| FlashRSI 快速跑通 | **已完成：实验级跑通**（不是安装级） | `runtime_data/flashrsi-localqa/runs/skillopt-miniagent-localqa-20261116-150802-007448/`；`result.json`、`end-summary.json`、6 段 trajectory |
| Harness² 基本了解 | **已完成：四个机制锚点 + 桥接复验** | `design/76` §3；`runtime_data/harness2/latest.json`、`story.json`；10/10 checklist |
| 今天复验 | **通过** | FlashRSI `--check-only`：`Startup checks passed: train=6, dev=3, test=3`；Harness² `probe` + `run --adapter demo --k 1 --mode both`：R=16/16、P=12/12、checklist_ok=true |

---

## 3. FlashRSI 是什么（30 秒版，照着讲）

RUC-NLPIR 的**技能自演化**框架。核心不是训练模型，而是在**冻结模型权重**的前提下，让 agent 的 skill 文件（`skills/main.md`）在任务上试错、反思、改写，然后用 dev 分数做门控——**只有严格变好才接受，平局或变差保留现任**。

它支持的是一类"程序级自改进"：模型不变，可复用的经验（skill 文本）在变。这和我们课题里"冻结权重、只让技能与过程协议演化"的定位是同一条线，区别在于它把"演化 + 选择"做成了可跑的实验管线，我们做的是"证据 + 准入 + 人签"。

---

## 4. 我们是怎么跑通的（这是老师最可能追问的部分）

### 4.1 真正的障碍不是安装，是 Docker

上游 31 个内置 benchmark **全部要求 Docker**：9 个 QA 基准与 hotpotqa(context) 在 `integrations/supplied_context.py:29-30` 直接检查 `shutil.which("docker") is None` 并 raise，其余在 `_startup._CONTAINERS`。本机没有 Docker daemon。

### 4.2 解法：走上游自己文档里的扩展路径

`scripts/flashrsi_localqa_run.py` 在**运行时**注册 `localqa`：它是 `SearchQA` 的子类，只把 `Task.env` 置为 `None`，让任务在原生进程内执行。**零上游文件改动**，复用上游同一份 `examples/data/quickstart.jsonl`、同一套 prompt 渲染、同一个 `text_em_f1` 评分。

这不是绕过评测，是上游 README "How do I add a new benchmark?" 明确支持的扩展方式。

### 4.3 供给：把"模型"换成宿主

target 和 worker 两个角色的 `base_url` 都指向 `research_agent/runtime/openai_compat.py` 起的 shim（`127.0.0.1:8788/v1`），模型名故意用 `host-agent`——避开 `gpt-/o1/o3/o4` 前缀，否则 miniagent 会走 Responses API，而 shim 只实现 chat completions。

每次 LLM 调用变成一条 pending `ModelTurn`，由宿主（本次是 Qoder）经 `research_model_respond` 作答，**哈希绑定 + 形状校验 + 一次性消费**。这解决了 75 号反思里的"宿主作答靠人工转发"缺口——至少这条外部框架路径不再靠复制粘贴。

### 4.4 踩到的坑（讲出来会显得是真的跑过）

首次尝试失败（run `…150555-386209` 保留未删）：httpx 0.28.1 解析本机 `NO_PROXY` 里的 `[::1]` 条目，抛 `InvalidURL: Invalid port: ':1]'`，客户端构造即失败，shim 根本没收到请求。修复是环境级：`NO_PROXY="localhost,127.0.0.1"`，零代码改动。

---

## 5. 跑出了什么（逐条有产物）

run：`runtime_data/flashrsi-localqa/runs/skillopt-miniagent-localqa-20261116-150802-007448`

| 环节 | 实测 | 产物 |
| --- | --- | --- |
| baseline dev（3 题） | EM = 1.0 | `trajectories/00001-baseline.json` |
| train batch（2 题） | EM = 1.0 × 2，单 turn 完成 | `trajectories/00002-train.json` |
| worker 反思 | 1 次调用，产出 1 条 `append` 编辑（可泛化，不含任务答案） | `trajectories/00003-worker.json` |
| candidate dev（3 题） | EM = 1.0，system prompt 已含演化后的 skill | `trajectories/00004-candidate_dev.json` |
| **选择判定** | score 1.0 vs baseline 1.0 → **accepted = false** | `trajectories/00005-decision.json` |
| sealed test（3 题） | **EM = 1.0 / F1 = 1.0** | `result.json` |
| 最终快照 | `ab452d00…`（基线保留）；候选 `04f915f6…` 落盘但未采纳 | `result.json`、`snapshots/` |
| 宿主供给 | 12 条 usage 记录，0 失败；token 全 0 | `end-summary.json` |
| 耗时 | 07:08:03 → 07:11:52 UTC，约 3 分 49 秒（宿主应答延迟主导） | `end-summary.json` |

**最关键的一行是 `accepted = false`。** 它证明的不是"演化失败"，而是"严格改进门在工作"：候选与基线同分时，系统拒绝替换，保留原快照。这和我们要求"平局不得升格为改进"是同一条纪律。

---

## 6. 这个结果怎么读（必须主动说的四条边界）

1. **它验证的是管线与门禁，不是效应量。** 12 题 demo 在强宿主供给下饱和——基线就是满分，没有改进空间。EM=1.0 说明"题会做、链能跑、门会拒"，不说明"FlashRSI 比其他方法好"。
2. **`localqa` 是本地扩展，不是上游 SearchQA 结果，分数不可与榜单比较。** 页面上、汇报里都不要写成"在 SearchQA 上达到 1.0"。
3. **token 全 0 是仪器缺口，不是零成本。** shim 不回报 usage，所以成本不可测；延迟有记录，费用没有。
4. **不能靠"故意答错"制造改进空间。** 那会把"门禁有效"变成"门禁被喂了假数据"。要测效应量，只能换更难题池或更弱供给。

---

## 7. Harness² 基本理解（四个机制，各带源码锚）

Harness² 的核心主张：**让 agent 改自己的 harness（工具、上下文、执行结构），而不只是改提示词**。四个我认为最值得讲的机制：

### 7.1 预算恒等式是硬不变式，不是报告字段

`R = 4k = k 个共享 base + 2k 个候选 + k 个 finals`；`P = 3k = k 个 INV + k 个 DOM + k 个组合`（`core/ledger.py:26-33`）。

`assert_identity` **先查重复 label 再查计数**（`ledger.py:89-113`）。重复 label 能满足计数，但意味着两个阶段写了同一个 run id、一个候选被静默覆盖——所以它抛错，不是警告。

本次桥接实测：`R=16/16、P=12/12`（k=1，2 任务 × 2 模式）。

### 7.2 选择与评分分离

selection 在**匿名化**的 finals 里按行为对比选一个（`core/selection.py:15`，seeded shuffle 保证重跑稳定），**选择时没有真值参与**；judge 是事后测量，且 "Nothing in the method imports this module"（`core/judge.py:15-18`）。judge 失败返回 `None` 而不是 0，`None` 从分母剔除。

这与 FlashRSI 的 dev 分数门控是**两种准入语义**：

| | FlashRSI SkillOpt | Harness² |
| --- | --- | --- |
| 选择依据 | dev 严格改进（真值在环） | 无真值行为对比 + 事后 judge |
| 平局 | 拒收，保留现任 | 匿名对比选一个，judge 事后评判 |
| 适用 | 有标注任务 | 开放世界、无真值 |

### 7.3 grader-verdict tripwire

agent 产出的 harness 树在滚动/入库前会扫描评分标记（文件名 + 正文），命中即拒。原文："such a tree could never afterwards be served as evidence"（`core/context.py:493-519`）。

这和我们平台"旁路产物不进主链"是同构的：**判定结果不得混进后续任务的证据供给**，否则整条链的可信度语义被稀释且不可逆。

### 7.4 经验库整树携带，不摘要

library 按域构造检索，采纳的 harness **整树保存、绝不做摘要**；lesson 必须 `cue / lesson / evidence` 三字段齐全（`core/library.py:15-22`）。

这和 context 的"不截断"（`context.py:18,25`）是同一条设计哲学：**不用截断或摘要换预算**，因为被截掉的那一段可能正是证据。

### 7.5 桥接复验（今天跑的）

```text
R=16/16 · P=12/12 · 2/2 tasks ok · 4 adopted · lessons 4/4 with evidence
10/10 checklist PASS · wall 12.298s
classification: simulation=True · claim_eligible=False
```

十项 checklist：contract / budget / exit=0 / tasks / no-fallback / adopted / lessons / classification / shims / human_gate。

**最后两项要特别讲**：`shims` 显式声明了 Windows 上补的两处（`fcntl.flock`、`tree.read_tree`），`human_gate` 明确"admission stays in the platform CLI"——桥不做准入，准入留在我们的人签链里。

---

## 8. 和我们平台的关系（组会的落点）

| 维度 | FlashRSI | Harness² | Wellspring（我们） |
| --- | --- | --- | --- |
| 改什么 | skill 文本（广度） | harness 自身（深度） | 过程协议与准入（治理） |
| 选择判据 | dev 严格改进，真值在环 | 匿名行为对比 + 事后 judge | 人签 + 判定总线读时重算 |
| 预算纪律 | edit_budget / max_steps | R=4k / P=3k 硬恒等式 | autopilot 策略 SHA-256 + 越界即停 |
| 证据边界 | 不可变 snapshot + 全轨迹 | 不截断 + grader tripwire | span-only + 旁路隔离 |
| 供给 | 外部 API（本次 = 宿主 shim） | Vertex / Codex / OpenCode | host-as-model |

**三者正交，不互相替代。** 这正好回应"科研智能体到底比什么"：不是比谁生成的论文多，而是比**谁的选择可复核、谁的证据可追溯、谁的经验可准入**。

而且 `localqa` 现在可以当**共同任务面**：同一个 12 题池，分别让 FlashRSI、Harness²、我们的 pipeline 跑，比较的不是分数高低，而是"三套准入语义在同一任务上分别拒绝/接受了什么"。这是下一步最值得做的受控对比。

---

## 9. 五分钟讲稿骨架

**0:00–0:40 结论先行**
"老师上次布置的两件事都完成了。FlashRSI 不是装好，是跑完了一次完整演化实验：12 次模型调用零失败、候选被严格门控拒收、sealed test 落盘。Harness² 读了源码，四个机制有代码锚点，桥接 10 项检查全过。今天又复验了一遍，装配和桥接都正常。"

**0:40–2:00 FlashRSI 怎么跑通的**
- 障碍：31 个 benchmark 全要 Docker，本机没有
- 解法：走上游扩展路径注册 localqa，零上游改动
- 供给：openai-compat shim，每次调用哈希绑定宿主作答
- 读数：baseline 满分 → 候选同分 → **拒收** → sealed test 1.0
- 坑：NO_PROXY 的 `[::1]` 让 httpx 直接崩，环境级修复

**2:00–3:20 Harness² 四个机制**
- 预算恒等式先查重复 label
- 选择与评分分离（选择无真值，judge 事后）
- grader tripwire（评分标记不得进证据树）
- 经验库整树携带，不摘要
- 桥接 10/10，`human_gate` 明确准入留在平台

**3:20–4:20 与我们的关系**
- 三引擎正交：广度 / 深度 / 治理
- 共同任务面已具备：localqa
- 下一步不是再加引擎，是给已接通的引擎装测量

**4:20–5:00 边界与下一步**
- 题池饱和，EM=1.0 只证明管线
- token 0 是仪器缺口
- localqa 不可比榜单
- 待定：Docker、ExecPort 注册、更难题池

---

## 10. 可能被问的八个问题（Q&A 预案）

**Q1：EM=1.0 是不是说明效果很好？**
不是。12 题 demo 在强宿主供给下饱和，基线就是满分。它说明题会做、链能跑、门会拒；不说明方法优越。要测效果得换更难题池或更弱供给。

**Q2：accepted=false 是不是演化失败了？**
不是。它说明严格改进门在工作：候选 1.0、基线 1.0，平局保留现任。这正是我们要求的"平局不得升格为改进"。如果它接受了同分候选，反而说明门是假的。

**Q3：为什么不用官方 benchmark？**
31 个内置 benchmark 全部依赖 Docker，本机没有 daemon。localqa 是上游文档支持的扩展路径，复用同一份数据、prompt 和评分，但分数不可与榜单比较。

**Q4：token 为什么是 0？**
shim 只实现 chat completions，不回报 usage。这是仪器缺口，不是零成本；延迟有记录，费用没有。下一步可以在 shim 里记字符数与延迟作为代理用量。

**Q5：Harness² 和 FlashRSI 有什么区别？**
两者都做程序级自改进，但改的对象不同：FlashRSI 改 skill 文本，靠 dev 分数严格改进选择；Harness² 改 harness 自身（工具/上下文/执行结构），选择时无真值，用匿名行为对比 + 事后 judge。一个适合有标注任务，一个适合开放世界。

**Q6：这些和你自己的课题什么关系？**
它们是外部引擎，用来做对照，不替代我们自己的证据链。我们的差异在治理：claim/EA/closure/lineage、人签门、判定总线。三者正交，可以拼在同一个任务面上。

**Q7：这算科研吗，还是工程集成？**
这一轮是工程集成 + 机制理解，产出是可复跑的对照基座，不是研究结论。真正的科研问题是下一步："三套准入语义在同一任务上分别拒绝/接受了什么"——那需要预注册判据和成对比较。

**Q8：下一步做什么？**
按优先级：① 把 localqa 注册成 ExecPort 的一个 face，让外部引擎也走 dispatch 记账；② 给 shim 加成本仪器；③ 换更难题池测效应量；④ Docker 与否需要老师拍板（影响可比性范围）。

---

## 11. 复跑清单（可照抄）

### 11.1 FlashRSI 装配自检（不调模型，几秒）

```bash
cd FlashRSI-main
NO_PROXY="localhost,127.0.0.1" PYTHONUTF8=1 ./.venv/Scripts/python.exe \
  ../scripts/flashrsi_localqa_run.py run \
  --config ../runtime_data/flashrsi-localqa/quickstart.local.yaml \
  --check-only
```

预期：`Startup checks passed: train=6, dev=3, test=3`

### 11.2 FlashRSI 完整复跑（需要宿主在线应答）

```bash
# 终端 1：shim（仓库根，Python 3.8）
python -m research_agent.runtime.openai_compat --port 8788 --wait-seconds 3600 --module flashrsi

# 终端 2：FlashRSI（其 3.12 venv）
cd FlashRSI-main
NO_PROXY="localhost,127.0.0.1" PYTHONUTF8=1 ./.venv/Scripts/python.exe \
  ../scripts/flashrsi_localqa_run.py run \
  --config ../runtime_data/flashrsi-localqa/quickstart.local.yaml
```

宿主每收到一个 pending turn，用 `research_model_respond` 作答；12 turn 跑完约 4 分钟。

### 11.3 Harness² 探测与桥接

```bash
python -m research_agent rsi harness2 probe
python -m research_agent rsi harness2 run --adapter demo --k 1 --mode both
python -m research_agent rsi harness2 status
```

预期：`R=16/16 · P=12/12 · checklist_ok=true`，classification 为 `simulation=True / claim_eligible=False`。

---

## 12. 未完成与下一步（按优先级）

| # | 事项 | 为什么重要 | 量级 |
| --- | --- | --- | --- |
| 1 | ExecPort 注册 `flashrsi` face | 本次运行绕过了 dispatch 记账，外部引擎没进执行面遥测 | 小 |
| 2 | shim 成本仪器（字符数/延迟） | token 全 0，费用不可测 | 小 |
| 3 | 更难题池 / 更弱供给 | 题池饱和，效应量不可测 | 中 |
| 4 | Docker 决策 | 影响能否走上游 31 benchmark 原生路径与容器隔离 | 需老师拍板 |
| 5 | M2 多会话走 shim | 目前只有外部引擎路径走了 shim，M2 仍人工转发 | 小 |

---

## 13. 汇报时不要说的话

- ❌ "FlashRSI 跑出了 1.0，说明效果很好" → ✅ "管线跑通、门禁有效，效应量未测"
- ❌ "在 SearchQA 上达到 1.0" → ✅ "在本地扩展的 localqa 上，分数不可比榜单"
- ❌ "Harness² 也被我们跑通了" → ✅ "桥接通过 10 项接口检查，执行器是 deterministic-demo，属于接口证据"
- ❌ "自改进提升了研究效率" → ✅ "自改进的准入语义可运行；是否提升产出，尚无成对测量"

---

## 14. 证据索引

| 内容 | 位置 |
| --- | --- |
| FlashRSI 跑通与 Harness² 机制详解 | `design/76-FlashRSI真实跑通与Harness2机制理解.md` |
| FlashRSI 运行产物 | `runtime_data/flashrsi-localqa/runs/skillopt-miniagent-localqa-20261116-150802-007448/` |
| Harness² 桥接产物 | `runtime_data/harness2/latest.json`、`story.json` |
| 平台事实基线（11-16 条目） | `docs/fact-baseline.md` 第 21 行 |
| 外部引擎接入路径（上一轮） | `design/74-1124组会准备-实测读数与外部基础设施接入.md` |
| 测量/供给三缺口 | `design/75-系统设计反思与机制合理性评估.md` §3 |

# 134-组会汇报手卡：FlashRSI 与 Harness²

> 用途：组会现场照着讲、被追问时查读数。不是设计档案（完整推导见 `126`）。
> 状态基线：2026-11-20。所有读数来自本机落盘产物，未产生新实验。
> 一句话定位：**外部供给路径通了，但效应量还没测出来——这是边界，不是失败。**

---

## 0. 汇报前 30 秒速览（只看这一块）

**开场三句（背下来）：**

1. FlashRSI 不是装好了，是**完整演化实验跑完了**：12 次宿主作答零失败、候选被严格门控拒收、sealed test 落盘。
2. Harness² 不是看了文档，是**四个机制级理解 + 桥接 10/10**：预算恒等式、选择/评分分离、grader tripwire、经验库整树携带。
3. 两者和我平台**正交**：FlashRSI 管广度、Harness² 管深度、我管治理，可用同一个 localqa 任务面拼起来。

**三条红线（任何一句说错就要补边界）：**

| 不要说 | 要说 |
| --- | --- |
| "FlashRSI 跑出 1.0，效果很好" | 管线跑通、门禁有效，**效应量未测** |
| "在 SearchQA 上达到 1.0" | 本地扩展的 **localqa**，分数不可比榜单 |
| "Harness² 也被我们跑通了" | 桥接过 10 项接口检查，执行器是 deterministic-demo，属**接口证据** |

**如果只记住一个数字**：`accepted = false` —— 候选和基线同分时系统拒绝替换。它证明门控是真的在工作。

---

## 1. 五分钟讲稿（完整句，可直接念）

### 0:00–0:40　结论先行

"老师上次布置的两件事都有结果了。FlashRSI 我跑完了一次完整的演化实验，不是装好——12 次模型调用零失败，候选被严格门控拒收，sealed test 落盘。Harness² 我读了源码，抓了四个机制，每个都有代码锚点，桥接 10 项检查全过。今天又复验了一遍，装配和桥接都正常。我目前的理解是，这两个跟我平台是正交的三件事。"

### 0:40–2:00　FlashRSI 怎么跑通的

"先说障碍：真正的难点不是安装，是 Docker。上游 31 个内置 benchmark 全部依赖 Docker，本机没有 daemon。

解法是走上游自己文档里的扩展路径——运行时注册一个叫 `localqa` 的任务，它是 SearchQA 的子类，只把环境置空让任务在原生进程里跑。零上游文件改动，复用同一份数据、同一套 prompt、同一个评分函数。这不是绕过评测。

供给这块我把模型换成了宿主：`openai-compat` shim 把每次调用变成一条 pending turn，由宿主作答，哈希绑定加形状校验。这就把之前靠人工转发作答的缺口补上了。

读数里最值得讲的是这一行：`accepted = false`。候选 1.0、基线 1.0，同分，系统拒绝替换、保留原快照。这说明严格改进门是真工作的——如果它接受了同分候选，反而说明门是假的。sealed test 是 EM 和 F1 都 1.0。"

"（如果老师追问怎么排错）我第一次跑是失败的，目录还留着：httpx 解析本机 NO_PROXY 里的 `[::1]` 直接抛 InvalidURL，客户端构造就崩了，shim 根本没收到请求。最后环境级修复，零代码改动。"

### 2:00–3:20　Harness² 的四个机制

"Harness² 的核心主张是让 agent 改自己的 harness，不只是改提示词。我抓了四个机制。

第一，预算恒等式是硬不变式，不是报告字段。R 等于 4k、P 等于 3k。而且断言函数先查重复 label 再查计数——重复 label 能满足计数，但意味着两个阶段写了同一个 run id、一个候选被静默覆盖，所以它抛错不是警告。

第二，选择与评分分离。选择在匿名的 finals 里按行为对比做，选择时没有真值参与；judge 是事后测量，源码里明确写了没有任何模块 import 它。这跟 FlashRSI 的 dev 分数门控是两种完全不同的准入语义——一个有真值在环、平局拒收；一个无真值、匿名对比选一个再事后评判。

第三，grader-verdict tripwire。agent 产出的 harness 树在入库前会扫描评分标记，命中即拒。这跟我们平台'旁路产物不进主链'是同构的。

第四，经验库整树携带，不做摘要。lesson 必须 cue、lesson、evidence 三字段齐全。这跟 context 的不截断是同一条设计哲学——不用摘要换预算，因为被截掉的那段可能正是证据。

桥接我跑了，R 16/16、P 12/12、10 项 checklist 全过。最后两项要特别讲：shims 显式声明了 Windows 上补的两处，human_gate 明确准入留在平台 CLI——桥不做准入。"

### 3:20–4:20　和我的课题什么关系

"三者正交，不互相替代。FlashRSI 改 skill 文本管广度，Harness² 改 harness 自身管深度，我的平台管准入和证据。

而且共同任务面已经具备了：`localqa` 同一个 12 题池，可以分别让 FlashRSI、Harness²、我的 pipeline 跑。下一步要比较的不是分数高低，而是三套准入语义在同一任务上分别拒绝和接受了什么。这是我最想做的受控对比。"

### 4:20–5:00　边界与下一步

"我把边界主动说清楚：第一，题池饱和，基线就是满分，EM 1.0 只证明管线和门禁，不证明效应量。第二，localqa 是本地扩展，分数不能跟榜单比。第三，token 全是 0，是仪器缺口不是零成本。

下一步按优先级：把 localqa 注册成 ExecPort 的一个面，让外部引擎也走 dispatch 记账；给 shim 加成本仪器；换更难的题池测效应量。Docker 要不要装，影响可比性范围，这个可能需要老师拍板。"

---

## 2. 老师追问时查这里（读数表）

**FlashRSI** — run `skillopt-miniagent-localqa-20261116-150802-007448`

| 环节 | 读数 | 怎么解读 |
| --- | --- | --- |
| baseline dev（3 题） | EM = 1.0 | 基线满分 → 无改进空间 |
| train batch（2 题） | EM = 1.0 × 2，单 turn | — |
| worker 反思 | 1 次调用，1 条 append 编辑 | 编辑可泛化，不含任务答案 |
| candidate dev | EM = 1.0 | system prompt 已含演化后 skill |
| **选择判定** | **accepted = false** | **同分拒收，保留原快照 `ab452d00…`** |
| 候选快照 | `04f915f6…` | 落盘但未采纳 |
| sealed test（3 题） | EM = 1.0 / F1 = 1.0 | 3 题，统计意义为零 |
| 宿主供给 | 12 条 usage，0 失败，token 全 0 | shim 不报 usage |
| 耗时 | 约 3 分 49 秒 | 宿主应答延迟主导 |

**Harness²** — `runtime_data/harness2/latest.json`、`story.json`（11-18）

```text
R=16/16 · P=12/12 · 2/2 tasks ok · 4 adopted · lessons 4/4 with evidence
10/10 checklist PASS · wall 12.298s
classification: simulation=True · claim_eligible=False
```

十项 checklist：contract / budget / exit=0 / tasks / no-fallback / adopted / lessons / classification / shims / human_gate。

**分级定义（121）**：L1 最小端到端 ✅ / L1.5 效应演示 ❌ / L2 上游官方路径 ❌ / L3 受治理接入 ❌。说"跑通"必须带级别。

---

## 3. 八个高频追问（背答案）

**Q1：EM=1.0 是不是效果很好？**
不是。12 题 demo 在强宿主供给下饱和，基线满分。说明题会做、链能跑、门会拒；不说明方法优越。要测效果得换更难题池或更弱供给。

**Q2：accepted=false 是不是失败了？**
不是。候选 1.0、基线 1.0，平局保留现任。这正是"平局不得升格为改进"。若它接受同分候选，门才是假的。

**Q3：为什么不用官方 benchmark？**
31 个内置 benchmark 全部依赖 Docker，本机没有 daemon。localqa 是上游文档支持的扩展路径，复用同一份数据、prompt、评分，但分数不可比榜单。

**Q4：token 为什么是 0？**
shim 只实现 chat completions，不回报 usage。是仪器缺口，不是零成本；延迟有记录，费用没有。可在 shim 里记字符数作代理用量。

**Q5：Harness² 和 FlashRSI 区别？**
都做程序级自改进，但改的对象不同：FlashRSI 改 skill 文本、靠 dev 严格改进、真值在环；Harness² 改 harness 自身、选择时无真值、匿名行为对比加事后 judge。前者适合有标注任务，后者适合开放世界。

**Q6：跟你课题什么关系？**
外部引擎，用来做对照，不替代我自己的证据链。我的差异在治理：claim/EA/closure/lineage、人签门、判定总线。三者正交，可拼在同一任务面。

**Q7：这算科研还是工程集成？**
这一轮是工程集成 + 机制理解，产出是可复跑的对照基座，不是研究结论。真正的科研问题是下一步："三套准入语义在同一任务上分别拒绝/接受了什么"，那需要预注册判据和成对比较。

**Q8：下一步做什么？**
① localqa 注册成 ExecPort face（这次绕过 dispatch 记账）；② shim 成本仪器；③ 更难题池测效应量；④ Docker 需老师拍板。

---

## 4. 复跑命令（被要求现场演示时用）

```bash
# FlashRSI 装配自检（几秒，不调模型）
cd FlashRSI-main
NO_PROXY="localhost,127.0.0.1" PYTHONUTF8=1 ./.venv/Scripts/python.exe \
  ../scripts/flashrsi_localqa_run.py run \
  --config ../runtime_data/flashrsi-localqa/quickstart.local.yaml --check-only
# 预期：Startup checks passed: train=6, dev=3, test=3

# Harness² 探测与桥接
python -m research_agent rsi harness2 probe
python -m research_agent rsi harness2 run --adapter demo --k 1 --mode both
# 预期：R=16/16 · P=12/12 · checklist_ok=true
```

完整复跑（需宿主在线应答，约 4 分钟）见 `126` §11.2。

---

## 5. 证据索引（老师要产物路径时）

| 内容 | 位置 |
| --- | --- |
| FlashRSI 首跑读数 + 机制详解 | `design/76-FlashRSI真实跑通与Harness2机制理解.md` |
| FlashRSI 分级定义与未验证面 | `design/121-FlashRSI跑通复核-分级定义与未验证面.md` |
| 完整讲稿骨架与 Q&A 来源 | `design/126-组会汇报准备-FlashRSI跑通与Harness2基本理解.md` |
| FlashRSI 运行产物 | `runtime_data/flashrsi-localqa/runs/skillopt-miniagent-localqa-20261116-150802-007448/` |
| 保留的失败 run | `runtime_data/flashrsi-localqa/runs/skillopt-miniagent-localqa-20261116-150555-386209/` |
| Harness² 桥接产物 | `runtime_data/harness2/latest.json`、`story.json` |
| 平台事实基线 | `docs/fact-baseline.md` |

---

## 6. 这份手卡和 126 的区别

- `126` 是**准备材料**：推导、源码锚、机制细节、完整 Q&A，用于会前理解。
- 本手卡是**现场材料**：可念的完整句、一页速览、集中读数表，用于汇报当下。

内容不重复造，全部来自 `126` / `121` / `76` 的已实测读数；本手卡不产生新结论。

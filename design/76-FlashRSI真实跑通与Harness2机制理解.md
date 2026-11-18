# 76-FlashRSI 真实跑通与 Harness² 机制理解——外部引擎从"装好"到"跑完"

> 状态基线：2026-11-16。承接 74（外部基础设施接入路径）与 75（测量/供给三缺口）。本文全部读数来自今日落盘产物（run 目录、story.json、host-model 账本），复跑命令见 §2.4 与 §3.3；不含未经测量的主张。

## 1. 一句话进展

**FlashRSI 第一次跑完完整演化实验**（skillopt × miniagent × localqa：12 次宿主作答零失败，sealed test EM=1.0，"平局拒收"选择判定真实发生）；**Harness² 桥复验 10/10 conformance**（R=16/16、P=12/12）；openai-compat shim 从"已建已测"变为"真实承载外部框架实验"。74 的"安装跑通"升级为"实验跑通"，74 的"实际 shim 待建"更正为"已建且今日承载 12 turn"。

## 2. FlashRSI 端到端实测

### 2.1 为什么需要 localqa（合法扩展，不是绕过）

- 上游 31 个内置 benchmark **全部要求 Docker**：9 个 QA 基准 + hotpotqa(context) 走 `integrations/supplied_context.py:29-30`（`shutil.which("docker") is None` 直接 raise），其余在 `_startup._CONTAINERS`。本机无 Docker daemon——这是 74"Windows/无 Docker 缺口"的根因，容器化是其可复现性根基。
- 走的是上游 README "How do I add a new benchmark?" 的扩展路径：`scripts/flashrsi_localqa_run.py` 在**运行时**注册 `localqa`（SearchQA 子类，仅把 `Task.env` 置 None → 原生进程内执行），复用上游同一份 quickstart.jsonl、同一 prompt 渲染、同一 text_em_f1 评分。**零上游文件改动**；metadata 显式声明 extension/native execution。
- 边界：localqa 是本地扩展实验，**不是上游 SearchQA 结果，分数不可与榜单比较**。

### 2.2 供给与装配

- target/worker 双角色 `base_url` 同指 shim（`http://127.0.0.1:8788/v1`），模型名 `host-agent`——刻意避开 `gpt-/o1/o3/o4` 前缀，否则 miniagent 走 Responses API（`runtime/llm.py:135-137`），shim 只实现 chat completions。
- shim = `research_agent/runtime/openai_compat.py`（平台 3.8 进程），账本 `runtime_data/host-model/turns.json`；每个 LLM 调用 = 一条 pending ModelTurn，宿主经 `research_model_respond` 作答，哈希绑定 + 形状校验 + 一次性消费。
- 演化能改变行为的前提已核实：flat skill `skills/main.md` **内联进 system prompt**（`runtime/workspace.py:104-122`）→ 候选快照的消息哈希不同于基线，shim 的请求哈希 replay 不会把基线答案重放给候选。

### 2.3 读数（run: `runtime_data/flashrsi-localqa/runs/skillopt-miniagent-localqa-20261116-150802-007448`）

| 环节 | 实测 | 锚 |
| --- | --- | --- |
| baseline dev（3 题） | EM=1.0 | trajectories/00001-baseline.json |
| train batch（2 题） | EM=1.0 ×2，单 turn 完成 | trajectories/00002-train.json |
| worker 反思 | 1 次调用，产出 1 条 append 编辑（success 源，support_count=2，可泛化、不含任务答案） | trajectories/00003-worker.json |
| candidate dev（3 题） | EM=1.0，system prompt 已含演化 skill | trajectories/00004-candidate_dev.json |
| **选择判定** | score 1.0 vs baseline 1.0 → **accepted=false**（严格改进门，平局保留现任） | trajectories/00005-decision.json |
| sealed test（3 题） | **EM=1.0 / F1=1.0**，最终快照=基线 ab452d00…（候选 04f915f6… 落盘但未采纳） | result.json + snapshots/ |
| 宿主供给 | 12/12 turn responded，host_label=Qoder，binding={experiment: flashrsi-localqa-quickstart-2026-11-16}，07:08:03→07:11:52 UTC（约 3 分 49 秒，宿主应答延迟主导） | runtime_data/host-model/turns.json |
| 用量 | 12 条 usage 记录、0 失败；**token 全 0**——shim 不报用量，不是零成本（见 §5 缺口③） | end-summary.json |

**读数的意义在管线与门禁行为，不在效应量**：demo 题池在强宿主供给下饱和（基线即满分），改进门没有可接受的空间——"拒收平局"本身就是被验证的语义。宿主按题面尽力作答，未故意答错制造改进空间。

### 2.4 调试记录与复跑

- 首次尝试失败（run …150555-386209 保留）：httpx 0.28.1 解析本机 `NO_PROXY` 中的 `[::1]` 条目抛 `InvalidURL: Invalid port: ':1]'`，客户端构造即失败、shim 未收到请求。**环境级修复**：`NO_PROXY="localhost,127.0.0.1"`，零代码改动。这是 Windows + 代理工具环境的坑，建议进 `scripts/doctor.py`。
- 复跑三步（宿主需在线应答 pending turn）：

```bash
# 1) shim（仓库根，平台 3.8）
python -m research_agent.runtime.openai_compat --port 8788 --wait-seconds 3600 --module flashrsi
# 2) FlashRSI（FlashRSI-main 目录，其 3.12 venv）
cd FlashRSI-main
NO_PROXY="localhost,127.0.0.1" PYTHONUTF8=1 .venv/Scripts/python.exe \
  ../scripts/flashrsi_localqa_run.py run --config ../runtime_data/flashrsi-localqa/quickstart.local.yaml
# 装配自检（不调模型）：同命令加 --check-only
```

## 3. Harness² 基本理解（今日新增的代码锚点）

74 已记录五模块结构与桥接契约；今天补上四个机制级理解，全部有源码锚：

1. **预算恒等式的构成**：`R=4k = k 共享 base + 2k 候选 + k finals`，`P=3k = k INV + k DOM + k 组合`（`core/ledger.py:26-33`；`core/recursion.py:354-460` run_parallel 的 2k 提案→2k rollout→k agg→k final 结构）。`assert_identity` **先查重复 label 再查计数**（`ledger.py:89-113`）——重复 label 能满足计数，但意味着两个阶段写了同一 run id、一个候选被静默覆盖。这不是报告字段，是抛错的硬不变式。
2. **选择与评分分离**：selection 在**匿名化**的 finals 里按行为对比选一个（`core/selection.py:15`，seeded shuffle 保证重跑稳定），**无真值参与**；judge 是事后测量——"Nothing in the method imports this module"，judge 失败=None 而非 0，None 剔出分母（`core/judge.py:15-18`）。与 FlashRSI skillopt 的 dev 分数门控（`algorithms/skillopt/__init__.py:237-274`）是**两种准入语义**：开放世界无真值选择 vs 有真值严格改进。
3. **grader-verdict tripwire**：agent 产出的 harness 树在滚动/入库前扫描评分标记（文件名+正文），命中即拒——"such a tree could never afterwards be served as evidence"（`core/context.py:493-519`）。与我们的旁路产物隔离同构：判定结果不得混进后续任务的证据供给。
4. **经验库整树携带**：library 按域构造检索，采纳的 harness **整树保存、绝不做摘要**，lesson 必须 cue/lesson/evidence 三字段齐全（`core/library.py:15-22, has_experience`）——与 context 的"不截断"（`context.py:18,25`）是同一条设计哲学：不用截断/摘要换预算。

### 3.1 桥复验读数（今日）

`python -m research_agent rsi harness2 run --adapter demo --k 1 --mode both`：

- R=16/16、P=12/12（2 任务 × 2 模式 × 4k/3k，k=1）；2/2 任务 ok；4 组件采纳；lessons 4/4 带证据
- **10/10 conformance PASS**：contract / budget / exit=0 / tasks / no-fallback / adopted / lessons / classification(simulation=True·claim_eligible=False) / shims(fcntl.flock+tree.read_tree 显式声明) / human_gate(准入留在平台 CLI)
- wall 2.183s；产物 `runtime_data/harness2/latest.json` + `story.json`；executor=deterministic-demo → **接口证据，不是研究结果**（seam 边界不变）

### 3.2 与本平台的关系（更新 74 的对照结论）

| 维度 | FlashRSI SkillOpt | Harness² | 本平台 |
| --- | --- | --- | --- |
| 选择判据 | dev 严格改进（真值在环） | 无真值行为对比 + 事后 judge | 人签 + 判定总线读时重算 |
| 预算纪律 | edit_budget / max_steps | R=4k/P=3k 硬恒等式 | autopilot 策略 SHA-256 + 越界即停 |
| 证据边界 | 不可变 Snapshot + 全轨迹 | 不截断 + grader tripwire | span-only + 旁路隔离 |
| 供给 | 外部 API（本次=宿主 shim） | Vertex/Codex/OpenCode | host-as-model（同供给边界见 75 §3.4） |

三者正交：广度对比（13 算法）× 深度递归（改 harness 自身）× 治理准入（人签/判定）。localqa 已可作共同任务面，"同一 benchmark × 多引擎"受控对比的地基具备。

### 3.3 复跑

```bash
python -m research_agent rsi harness2 probe   # 只读：checkout/解释器/适配器
python -m research_agent rsi harness2 run --adapter demo --k 1 --mode both
python -m research_agent rsi harness2 status  # 读 latest.json 的 checklist
```

## 4. 对 74/75 的更正

| 原文 | 更正 |
| --- | --- |
| 74 §5 FlashRSI"安装跑通…CLI 可用" | 升级为**实验跑通**：完整演化 + 选择判定 + sealed test（§2.3） |
| 74 §5"实际 shim 待建" | 过期：shim 已建已测（tests/test_openai_compat.py），今日真实承载 12 turn 零失败 |
| 75 §3.5 / 改进 #5"宿主作答走 shim" | 外部框架路径今日已走 shim（消灭了该路径的人工转发）；**M2 多会话路径仍未走**，保持待办 |
| 74 §5"ExecPort 双面注册后可…" | 澄清：bridge/inprocess/host_agent 三面已接线，**flashrsi 面尚未注册**；今日 FlashRSI 直跑 CLI，未走 dispatch 记账（§5 缺口①） |

## 5. 新缺口与下一步（按优先级）

1. **ExecPort flashrsi 面未注册**：今日运行绕过了 dispatch 记账。下一步按最小修改规则改 `modules/exec-port/SPEC.md` → 注册 localqa launcher 为 face（解释器=FlashRSI venv、授权边界=宿主供给+人工启动），补测试。量级小。
2. **效应量不可测（题池饱和）**：12 题 demo + 强宿主 → 基线满分。要测"演化有没有用"需要更难题池（上游 hf_prepared/真实 SearchQA 需 Docker）或更弱供给；**不能靠故意答错制造空间**。与 75 §3.3"反馈效果未测量"是同一类缺口在外部引擎上的投影。
3. **宿主供给无成本仪器**：shim usage 全 0，token/费用不可测；延迟有记录（trajectory 内 latency_seconds）。改法：shim 回报字符数/应答延迟作为代理用量，或在账本 receipt 上累计——仍不是供应商计费口径。
4. **环境坑未进 doctor**：NO_PROXY `[::1]` × httpx 0.28.1 应在 `scripts/doctor.py` 加一条检查（Windows + FlashRSI venv 场景）。
5. **Docker 决策待决**：装 Docker Desktop（WSL2/重启成本）可解锁上游 31 benchmark 原生路径与容器隔离语义；不装则 localqa 扩展面是唯一无容器路径。两者都合法，区别是证据的可比性范围——需要你拍板。

## 6. 结论

导师要求的两件事今日落地：**FlashRSI 快速跑通**（真实演化实验，非仅安装；全链产物落盘可复跑）与 **Harness² 基本理解**（四个机制级锚点 + 桥复验全绿）。对系统本身，这一步把 75 的"供给层"缺口补上一角：外部框架的模型供给第一次走了哈希绑定的 shim 而非人工转发；但测量层缺口（效应量、成本仪器）依旧诚实敞开——下一步不是再加引擎，而是给已接通的引擎装测量。
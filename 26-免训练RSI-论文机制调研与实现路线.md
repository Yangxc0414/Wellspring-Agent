# 26 · 免训练 RSI：论文机制调研、能力边界与我们的实现路线

> 日期：2026-10-24 · 性质：文献调研 + 机制设计（不是 RSI 效果报告）  
> 目标：在**不改模型权重、不接入 API 的当前阶段**，把“免训练 RSI + 自动科研”拆成可实现的机制；当前代码有受治理控制面、真实 CC-BY 文本 evaluator 与 S5 iris 协议验证，但没有真实研究实验 run/EA/Claim，也没有可宣称的 RSI 能力增益。  
> 相关：[10](10-RSI与自进化反思-科研改进的准入与证据闭合.md)、[11](11-自进化循环设计-准入理由、跨循环继承、迁移与能力增益.md)、[19](19-RSI出题规范对照-自进化运行纪律反思.md)、[23](23-开源自改进机制对照-从A-Evolve-RSI-Anything到我们的Lease-Gated-Runtime.md)、[25](25-受治理的RSI-从研究执行到元改进追踪.md)

## 1. 先定义：什么才算“免训练 RSI”

**免训练**不等于“不学习”。这里定义为：

```text
冻结模型权重（frozen backbone）
+ 可修改 harness：prompt / skill / process / memory / context / control flow / tools
+ 反馈驱动的持久改变
+ 下一轮任务可复用，且在固定实例上可验证
```

它不包含：

- 用 RL/SFT 训练模型（CycleResearcher、SEAL、Evo²/EvoTIDE 等）；
- 只做一次上下文内改写（single-run refinement）；
- 只把记忆越存越大，而不验证是否迁移；
- 让 Agent 改 claim/门槛/评分规则。

真正要追踪的是：**这次改动是否让下一次“做研究”和“改进研究流程”都更好，并且可撤销、可复核。**

## 2. 关键论文与机制（按可借性排序）

| 工作 | 改什么 | 是否训练 | 可借机制 | 对我们的限制 |
| --- | --- | --- | --- | --- |
| **RRSI**（arXiv 2609.24972） | harness：prompt、控制流、工具、记忆、上下文 | 否，模型冻结 | 候选编辑预算退火、探索历史约束、critic 过滤 benchmark-specific 提案、pruner 去掉过小/过贵/失效改动 | 论文报告的是其任务上的增益，**未复现**，不能搬数字 |
| **Darwin Gödel Machine**（arXiv 2505.22954） | Agent 自身代码 | 否 | 开放 archive、父代采样、谱系、并行探索、沙箱/人监督 | 代码自修改风险高；我们不能让 claim/证据代码自改 |
| **SICA**（arXiv 2504.15228） | Agent codebase | 否 | 用工具直接编辑自身实现、benchmark 反馈、非梯度学习 | 只适合 coding benchmark；科研证据链不能靠自改代码 |
| **SIFT**（arXiv 2609.19526） | 自修改候选 | 否 | 低成本候选筛选：LLM-as-judge 两两比较 + 正则化 Bradley-Terry + 只对 promising 节点做昂贵下游评测 | judge 只能做预筛，不能替代 hidden/真实 run |
| **Gödel Agent**（arXiv 2410.04444） | 自身逻辑/求解策略 | 否 | 运行时读取/改写自身逻辑、无固定优化器 | 安全与可解释性弱；不能让它改 claim/门禁 |
| **GEPA**（arXiv 2507.19457） | prompt | 否 | 自然语言反思、Pareto 前沿、少量 rollout 的 prompt 演化 | 只改 prompt；容易把 benchmark 规则写进 prompt |
| **ACE**（arXiv 2510.04618） | context / playbook / memory | 否 | 结构化增量更新，避免 brevity bias 与 context collapse；利用自然执行反馈 | 记忆会污染；必须有来源、scope、撤销 |
| **MASS**（arXiv 2502.02533） | 多 Agent prompt + topology | 否 | 先局部 prompt、再拓扑、再全局 prompt 的交替搜索 | 多 Agent 成本高；不是科研证据运行时 |
| **ReasoningBank**（arXiv 2509.25140） | reasoning memory | 否 | 从成功/失败经验提炼策略，检索后复用 | 自评可能自确认；需要独立验证 |
| **RSI 综述**（arXiv 2607.07663） |  taxonomy | — | 按“改什么 + 闭环程度”分类；评测层级从形式 verifier 到自评；指出 research direction-setting 仍是人类瓶颈 | 说明开放 RSI 仍受限，不能把局部自改进叫 RSI |
| **The Last AI Built by Humans**（arXiv 2609.11873） | 自主性五级：执行→策略→经验→环境→元改进 | — | 用 L1–L5 判断“改的是执行、策略、经验还是改进机制本身” | 当前公开系统最高多在 L3/L4，不能自称 L5 |
| **DeepMind 自改进遗忘研究**（2026-10） | prompt/memory/skill | 否 | 自进化会遗忘旧任务；需要 forgetting / 回归测试 | 不能只看新任务提升 |

> 这组工作共同说明：**免训练 RSI 的难点不是“生成一个更好的 prompt”，而是候选选择、评测独立性、遗忘/迁移、成本与安全继承。**

## 3. 我们的定位：不是“通用自改代码”，而是“受治理的科研 harness RSI”

我们的研究对象是**科研流程本身**：

```text
研究执行：S0–S16 → evidence / EA / manuscript
可改 harness：文献检索策略、筛选顺序、抽取 schema、设计模板、绘图 scene 规则、写作槽位流程
不可改：claim 创建、EA、gate/rubric、导出、署名
```

因此我们不追求 DGM/Gödel Agent 的“改自己的代码”，而是：

- 让 frozen model/固定工具去改 **skill/process/prompt/knowledge**；
- 每个候选进入 `StepLedger`，有 parent、predicted effect、dry-run、public/hidden、人签、lease；
- 让 `MetaTracker` 追踪“预测 vs 实际、保留/拒绝、迁移/遗忘、成本”，而不只是平均分；
- 任何候选不能把“论文写得更好”变成“改 claim 或改评分”。

这与 RRSI 最接近（harness-level、frozen model、regularized selection），但增加了**科研证据闭合 + 人签/租约 + 研究过程的可追溯产物**。

## 4. 建议的免训练 RSI 算法（TF-RSI）

```text
archive = [incumbent]
for cycle in 1..N:
    obs = failure/coverage/cost signals from research runs
    parents = sample(archive, diversity + recent + best)
    cand = proposer(parent, obs)              # frozen LLM later; no weight update
    cand = critic(cand)                       # reject benchmark-specific / unsafe
    cand = pruner(cand, budget)               # reject too small / too expensive / stale
    dry = sandbox(cand)                       # static/schema/golden
    public = evaluate(cand, public_set)       # development-visible
    if not promising: archive.reject(cand); continue
    hidden = evaluate(cand, frozen_hidden)    # sealed; not used to author
    transfer = evaluate(cand, near_ood)       # transfer, not just ID
    forgetting = evaluate(cand, regression)   # old tasks
    decision = policy(public, hidden, transfer, forgetting, cost)
    if decision == accept:
        human_sign(cand); lease(cand); archive.add(cand)
    else:
        archive.reject(cand)                  # preserve negative result
meta = track(predicted vs actual, lineage, retention, transfer, cost)
```

**关键机制（对应论文）**：

- **候选预算退火 + critic/pruner** ← RRSI；避免一次 bundle 太多改动、避免 benchmark-specific 补丁；
- **开放 archive + 父代采样** ← DGM；保留多样性，允许从“踏脚石”继续；
- **快速预筛** ← SIFT；LLM judge 只排序候选，不替代 hidden/真实 run；
- **反思式候选** ← GEPA/ACE/ReasoningBank；但记忆必须带来源/scope/撤销；
- **固定 hidden + OOD + forgetting** ← RSI 综述/Last AI/DeepMind forgetting；
- **人签/租约/撤销** ← 我们的 StageLease/StepLedger；这是与训练型 RSI 的关键差异。

## 5. 评测设计（必须做，否则只是状态机）

固定任务包至少四层：

1. **public**：开发可见，用于候选生成；
2. **hidden**：冻结后独立执行，不能回灌；
3. **near-OOD / transfer**：同任务族但不同领域/数据；
4. **regression/forgetting**：旧任务是否退化。

指标：

- 主任务指标（证据覆盖、有效 run、无支撑句率等，按阶段定义）；
- 成本（token、GPU 时、wall time）；
- 隐藏集与 OOD 的差值；
- 旧任务回归；
- 拒绝/负结果数量；
- 是否触发证据不变量。

**判定**：只有在 hidden 与 transfer 不退化、cost 可接受、无证据违规、且人签后，才可发 lease；单次 public 提升不算 RSI。

## 6. 当前实现与缺口

已有（[25](25-受治理的RSI-从研究执行到元改进追踪.md)）：

- `Candidate / EvalEvidence / StepRecord / Lease / StepLedger`；
- 禁止候选改 claim/evidence/gate/rubric/export/signature；
- dry-run/public/hidden/人签/lease/revoke；
- `MetaTracker` 报告 pending/approved/rejected、active/expired/revoked lease、lineage、warnings、next questions，以及逐 episode 的 predicted/actual；候选可选记录数值 `predicted_metrics`，据此计算 MAE/bias/direction/coverage，自由文本预测显式标为不可校准；
- `Lease.effective_status` 按 TTL 判定过期；expired lease 不参与执行、不能作为父代；多个不同预算的 active lease 会 fail closed；
- 指标含 `coverage_gaps`；预算降低只由 `retrieval_cost` 观测触发，coverage gap 作为不得增加的 guard；
- `CandidateArchive` / `select_parents`：按 hidden 指标与 target 多样性选父代，revoked lease 不再作为父代；
- `EvalEvidence` 支持 `public / hidden / near_ood / regression`；
- `research_agent/research_runner.py`：在 fixture 任务队列上跑完整 S1→paper pipeline，收集 coverage/idea/design/paper 的 observation；`run_research_cycle` 把 research batch 接到 TF-RSI；`active_literature_policy` 只解析 active lease 的 S1 预算，租约后研究批次实际以该预算运行；已有 active 策略时不再生成重复 episode；
- `research_agent/rsi_fixture.py`：另有 `run_confirmation_trial`（CLI `rsi confirm`），用独立 `tasks_confirm.json` 在租约后做 sealed 复核，记录 `used_for_admission: false`，不回写选择/准入；
- `research_agent/rsi_proposer.py`：冻结模型 proposer 接口（`ModelPort`、`FrozenModelProposer`）；DeepSeek adapter 可选，离线测试只用 fake model；
- `research_agent/rsi_fixture.py`：冻结 fixture corpus 上的多候选 TF-RSI 回路（incumbent max_sources=6 vs budget 4/3/2/1）；public 排序后最多两个 finalist 依次过 hidden/near_ood/regression，未进入 finalist 的候选标记 `hidden_held_out`；证据标记 `simulation: true`，即使人签 `capability_claims` 仍为空；`--approve` 才发 lease；
- `research_agent/real_eval.py` + `RealCorpusRetriever`：4 篇 CC-BY 4.0 RSI 论文正文（DGM/SICA/SIFT/ACE），带 license/URL/SHA256 provenance；正文 BM25 检索 + 同一套 public→finalist→hidden gate，证据 `simulation=false`、`claim_eligible=false`；BM25 下 budget2/3 均在 near-OOD 失败被拒，budget4 与 incumbent 同成本，负结果保留；`--retriever minilm` 使用本地 frozen MiniLM 做 abstract 级语义检索，budget2 因 regression 0.833 被拒、budget3 通过（cost 21→18）；`--retriever compare` 用预注册候选集 `{bm25+budget2, minilm+budget3}`，governor 以 near-OOD gate 选中 `minilm+budget3`，`bm25+budget2` 作为负结果保留；lease scope 为 `S1/rsi-ccby-4*`，fixture runner 不会消费；同一 ledger 再跑只返回 skipped 候选；CLI `rsi real-trial`；
- `PipelineRunner(retriever=..., source_scope=["real"])`：同一批 CC-BY 正文可跑完整 S1→idea→design→figure→paper 纵切；实测 4 个 hit、2,287 个真实 span、paper claims 为空，状态 `needs_human`；CLI `pipeline run --real-corpus`；
- `modules/run` + `run execute|claim`：本地 iris/breast_cancer 分类与 ChemLab 真实反应转化回归（MIT 数据，Ridge/R² + mean baseline）；产出 RunCapsule/EA，claim 需人签；`pipeline run --use-s5-lease` 或 `--run-dataset chemlab` 执行真实 run 并产出 EA + claim draft；paper.result.primary 在 draft 阶段 pending，人签 claim 后 `--claim-file --run-dir` 才 bound_claim；ChemLab 实测 Ridge R²≈0.193、mean baseline −0.048、ΔR²≈0.242；同时从 RunCapsule 生成数据图（schematic=false、EA refs、SVG 哈希）并绑定 paper.result.figure；这是受控 baseline 协议验证，不是新发现；
- `bibliography verify`：从冻结 DataCite 快照核验 4 篇 DOI/标题/作者/年份/URL/response 哈希，写 BibliographyCard（metadata-only，不是同行评审）；
- `experiment.freeze` + `protocol freeze`：ready_for_g2 design + completed capsule + 人签 limitation → ProtocolCard（design/capsule 哈希）；pipeline `--protocol-file` 把 method.protocol/limitation 标为 bound_protocol/bound_scope；
- `closure.py` + `closure check|sign`：检查 claim supported、EA 哈希、RunCapsule completed、paper.result.primary bound_claim 与所有槽位；未决槽位 → blocked；只有 ready + 人签才生成 export manifest，`submission=false`；ChemLab 绑定 claim + 数据图 + 冻结 ProtocolCard + 4 条 DataCite 元数据后 11/11 检查 pass、status=ready；人签生成 submission=false 的 export manifest。
- `s5_eval.py` + `rsi s5-trial`：5-seed incumbent vs 4/3/2 seed 候选，在 8 个 iris 协议实例上 public→hidden/near/regression gate；iris 选中 seeds3（cost 10→6、mean −0.0025），breast_cancer 选中 seeds2（cost 10→4、mean −0.0055）；两者均 `run execute --use-lease` 消费并通过 4 个新实例 sealed 复核（iris cost 20→12、breast 20→8）；选择是 dataset-specific，claims 为空；
- 47 个测试。

缺口：

- 没有 **RRSI 式 candidate budget / critic / pruner** 的完整实现；
- frozen LLM proposer 的接口与 DeepSeek adapter 已有，但未发起真实调用；
- 已有 4 篇 CC-BY 正文 probe 与 3 篇 transfer probe；仍没有 peer-review 固定 benchmark、真实研究实验的 run/EA/Claim；
- S5 已有 iris/breast_cancer 分类与 ChemLab R² 协议验证；`bound_claim` 只证明接线，不是论文结果或科学发现。
- predicted/actual 已能写入 ledger；数值预测可算 MAE/bias/direction/coverage，但真实语料数值只是 harness 指标，不能当研究能力校准结论。
- 已跑第二个真实 harness 周期：ChemLab `test_size`→训练子集修复后，seeds2 通过 public/hidden/near-OOD/regression（cost 10→4、mean R² −0.0095、min +0.0402），人签 lease 并由 `run execute --use-lease` 消费；数值校准 `tracked`（cost 预测误差 0，mean 误差 0.0095）。
- 已补 ChemLab held-out 复核：从 418 训练池按行哈希确定性派生 376/42 划分，42 条 held-out 与 22 测试集不重叠且未参与准入；seeds2 复核通过（mean R² +0.00566、min +0.00966、cost 20→8、failed 0），`used_for_admission=false`，仍 `claim_eligible=false`。
- 复核结果已写入 `StepLedger.confirmations`（audit-only，强制 `sealed=true`/`used_for_admission=false`）；MetaTracker 汇总 confirmed/regressed/unsupported，`rsi trace` 可同时看到 capsule 与 ledger confirmation；重复 artifact 幂等，regressed 只告警交人处理。

## 7. 下一步（按顺序，不跳）

1. **已完成**：`CandidateArchive` + `select_parents`（按 hidden 指标与 target 多样性选父代；拒绝项保留）。
2. **已完成**：`EvalEvidence` 支持 `public / hidden / near_ood / regression`；admission 必须 public+hidden，OOD/regression 记录为 transfer/forgetting 证据，缺项会出现在 MetaTracker warnings。
3. **已接 S1 真实文本 probe**：4 篇 CC-BY 论文正文 + 12 个问题，public/hidden/near_ood/regression 回执落盘；S5 已有 iris 协议验证；下一步扩到 peer-review corpus 或真实研究实验 + 固定 seeds。
4. **接 frozen LLM proposer**：`ModelPort`/`FrozenModelProposer`/DeepSeek adapter 已有；下一步在受控环境用 fake model → 固定实例 → 真实调用，生成 1–3 个 skill/process 候选，不能改 claim/gate。
5. **部分完成**：已跑两个真实接受周期（S1 MiniLM+budget3、S5 ChemLab seeds2）并各有人签 lease 与 sealed/unsupported 记录；`MetaTracker` 已报告数值预测/实际。仍缺 peer-review 固定 benchmark 与新的 ChemLab held-out 反应集，不能算能力增益完成。
6. **只有到这一步**才讨论“RSI 有效”；否则只写“受治理的免训练 RSI 控制面”。

### 7.1 本地 research→RSI 跑法

```bash
# 1) 先跑研究队列，产出 observations
python -m research_agent research run   --tasks research_agent/rsi_fixtures/research_tasks.json   --output-dir research_agent/web/data/research-queue

# 2) 跑一轮 research→observation→TF-RSI（默认 pending）
python -m research_agent rsi research-cycle   --tasks research_agent/rsi_fixtures/research_tasks.json   --ledger research_agent/web/data/rsi-ledger.json   --output-dir research_agent/web/data/research-cycle

# 3) 人签后做 sealed 复核（独立任务包，不回流准入）
python -m research_agent rsi confirm   --ledger research_agent/web/data/rsi-ledger.json   --output-dir research_agent/web/data/rsi-confirmation

# 4) 在 4 篇 CC-BY 论文正文上跑真实文本 probe（默认 pending；compare 用预注册候选集）
python -m research_agent rsi real-trial   --ledger research_agent/web/data/rsi-real-ledger.json   --output-dir research_agent/web/data/rsi-real --retriever compare

# 5) 用同一批正文跑 S1→paper 纵切（真实 span，仍无 claims/run/EA）
python -m research_agent pipeline run   --topic "How do self-improving coding agents use archives?"   --language en --venue en_conference --real-corpus   --output-dir research_agent/web/data/real-pipe

# 6) 人签后把 active harness lease 回灌真实 pipeline（MiniLM + 3 sources）
python -m research_agent pipeline run   --topic "How do self-improving coding agents use archives?"   --language en --venue en_conference --use-lease   --lease-scope S1/rsi-ccby-4-model   --ledger research_agent/web/data/rsi-compare-ledger.json   --output-dir research_agent/web/data/real-pipe-lease

# 7) 本地 frozen proposer：生成候选 → 同一套 gate 评测
python -m research_agent rsi propose-model   --model-path ~/.cache/qwen-rsi/Qwen2.5-0.5B-Instruct   --observation "Public BM25 baseline recall=1.0, cost=21, gaps=0; paraphrase-heavy cross-paper questions may lose coverage. Propose a cheaper harness."   --out research_agent/web/data/model-proposal.json
python -m research_agent rsi real-trial   --candidate-file research_agent/web/data/model-proposal.json   --ledger research_agent/web/data/rsi-model-ledger.json   --output-dir research_agent/web/data/rsi-model

# 8) 多 observation 的 prompt 稳定性审计
python -m research_agent rsi model-batch   --model-path ~/.cache/qwen-rsi/Qwen2.5-0.5B-Instruct   --observations research_agent/rsi_fixtures/model_observations.json   --output-dir research_agent/web/data/model-batch   --ledger-root research_agent/web/data/model-batch-ledgers

# 9) 人签后用 4 个新问题做 sealed 保留检查（不回流准入）
python -m research_agent rsi real-confirm   --ledger research_agent/web/data/rsi-compare-ledger.json   --lease-scope S1/rsi-ccby-4-compare   --output-dir research_agent/web/data/rsi-real-confirmation

# 9b) S5 seed-budget 改进（iris；breast_cancer 用 --dataset breast_cancer）
python -m research_agent rsi s5-trial   --ledger research_agent/web/data/rsi-s5-ledger.json   --output-dir research_agent/web/data/rsi-s5

# 9c) 人签后用 4 个新协议实例做 S5 sealed 复核
python -m research_agent rsi s5-confirm   --ledger research_agent/web/data/rsi-s5-ledger.json   --output-dir research_agent/web/data/rsi-s5-confirmation

# 9d) 用 S5 lease 跑 pipeline：真实 run + claim draft；人签后再 --claim-file 绑定
python -m research_agent pipeline run   --topic "Iris protocol validation"   --language en --venue en_conference   --use-s5-lease --s5-ledger research_agent/web/data/rsi-s5-ledger.json   --output-dir research_agent/web/data/pipeline-s5

# 9e) ChemLab 真实反应数据：Ridge/Morgan 指纹 → RunCapsule/EA → 人签 claim → paper bound_claim
python -m research_agent pipeline run   --topic "ChemLab reaction conversion baseline"   --language en --venue en_conference --run-dataset chemlab --run-seeds 3   --output-dir research_agent/web/data/pipeline-chemlab

# 10) held-out 3 篇新论文 / 6 个新问题的迁移复核
python -m research_agent rsi real-confirm   --ledger research_agent/web/data/rsi-compare-ledger.json   --lease-scope S1/rsi-ccby-4-compare   --tasks research_agent/rsi_fixtures/transfer_tasks.json   --corpus modules/literature/fixtures/transfer_corpus.json   --output-dir research_agent/web/data/rsi-transfer-confirmation
```

当前 fixture cycle 产出 2 个 run、8 条 observations（coverage gap / idea G1 / paper pending），TF-RSI 推荐 `candidate-budget2`，但保持 `pending_human`。加 `--approve` 后 lease 生效，`research-under-lease` 以 `max_sources=2` 再跑 2 个任务（4 条 observations，0 errors）；同一 ledger 再跑一轮会识别“与 active 策略重复”，记录 `active_unchanged` 而不是重复开 episode。`rsi confirm` 在独立 `tasks_confirm.json` 上复核（2 个任务，`used_for_admission: false`）。所有 episode 标记 `simulation: true`，`capability_claims` 为空。

真实 probe 走法：`rsi real-trial` 默认 pending；正文 BM25 下 budget2/3 在 near-OOD 均失败被拒，budget4 与 incumbent 同成本，因此不产生可接受候选，负结果保留。同一 ledger 再跑只返回 `deduplicated` 候选，不新增 episode。这正说明真实 evaluator 会否决 fixture 上看似便宜的策略，而不是自动放行。

**两种真实检索的对照**：BM25 下没有安全降预算；改用本地 frozen MiniLM 的 abstract 级语义检索后，budget2 因 regression 丢失覆盖被拒，budget3 通过（cost 21→18，recall/gap 不变）。进一步的 `compare` 模式把 `bm25+budget2` 与 `minilm+budget3` 作为**预注册候选集**，由 public 排序 + hidden/near-OOD/regression gate 选中 `minilm+budget3`，`bm25+budget2` 因 near-OOD 被拒。这说明冻结模型可以进入 harness、且 governor 能在预注册组合中做选择；但候选组合仍由人预先列出，**不是开放式的模型提案**，所以不能宣称 RSI 自己发现了它。

**闭环已回灌**：对 `minilm+budget3` 人签后，`pipeline run --real-corpus --use-lease --ledger ...` 会解析 `S1/rsi-ccby-4-*` lease，实际切换到 MiniLM + 3 sources；输出记录 `active_harness`，S1 得到 3 个 hit、span 全部 `fixture=false`、paper claims 为空。S5 侧另有 iris 协议验证的 RunCapsule/EA/Claim 与 `bound_claim` 接线；两者都还不是真实研究实验证据。

**sealed 保留检查**：`rsi real-confirm` 用 4 个**新问题**复核已签 lease；该任务包不参与选择/准入。MiniLM+budget3 复核通过：recall 1.0 不变、cost 28→24、gap 0，`used_for_admission=false`。这说明在该 4 篇论文范围内 harness 没出现明显遗忘；仍不是跨领域迁移证据。

**held-out 迁移检查**：另外下载 3 篇未参与设计的 CC-BY 论文（Agent Laboratory、The AI Scientist、SEAL），人工写 6 个新问题，作为独立 transfer corpus。已签 MiniLM+budget3 在 transfer 上 recall 1.0、gap 0 不变；但 cost 36→36 持平，因为该 corpus 只有 3 篇，baseline 最多也只能读到 3 篇。结论：**在这组小规模新论文上没有召回/覆盖回归，也没有成本收益**，不能据此宣称通用迁移或效率提升。

**本地 frozen proposer**：`rsi propose-model --model-path ~/.cache/qwen-rsi/Qwen2.5-0.5B-Instruct` 用本地 Qwen2.5-0.5B-Instruct（Apache-2.0，frozen，无训练/无 API）生成候选 JSON；`rsi real-trial --candidate-file` 把候选送入同一套 gate。实测：普通 prompt 先给出非法 target/patch（被 schema 拒绝）；严格 few-shot 下提出 `bm25+budget2`，被 near-OOD 拒绝；改成“paraphrase-heavy cross-paper”公开观察后提出 `minilm+budget3`，通过全部 gate、人签后 lease 被真实 pipeline 消费，`capability_claims` 仍为空。结论：0.5B 模型能进入受治理的提案环，但输出对 prompt 很敏感，不能把一次接受当成模型能力或 RSI 有效性。

**prompt 稳定性审计**：`rsi model-batch` 对 3 条公开 observation 逐条提案/评测：1 条 eligible（`minilm+budget3`），2 条 `bm25+budget2` 因 near-OOD 0.667 被拒，0 个解析错误；每条 gate 结果逐条落盘。接受率 1/3 只是 prompt 敏感性证据，不是能力增益。
**schema-repair 审计（v0.1.26）**：`propose_with_repair` 在格式/策略错误时把错误回灌一次，冻结模型不训练，仍过同一 gate。真实 Qwen 在同一 3 条观察上 **0 次修复、1/3 eligible、2 条 near-OOD 拒绝**——说明瓶颈在候选质量与 gate，不在 JSON 解析；不宣称可靠性提升。

**负迁移结论**：fixture 上 budget2 可接受；换成 4 篇真实论文正文 + BM25 后，budget2/3 都在 near-OOD 丢失覆盖，budget4 又没有成本优势。因此当前 fixture 的“增益”不能外推为真实检索能力，真实 evaluator 必须独立保留；这也是下一步扩到 peer-review corpus 的理由。

当前 harness 只有一个 S1 预算旋钮，所以第二轮就收敛；这不是缺陷，而是避免同一策略重复记账。真正的多周期元 RSI 需要更多**可验证的 harness 旋钮**（query planner / skill / context policy）和真实 evaluator，而不是为了“看起来在进化”反复改同一个数。

### 7.2 本地 TF-RSI fixture 跑法

```bash
# 默认停在 pending_human；--approve 是显式人工准入
python -m research_agent rsi fixture   --ledger research_agent/web/data/rsi-ledger.json   --output-dir research_agent/web/data/rsi-fixture --approve
```

当前 fixture 结果：budget 2 在 hidden/near_ood/regression 的 gold recall 与 incumbent 相同、cost 更低，且 coverage gap 不增加；budget 4/3 没有成本优势，budget 1 被 critic/pruner 以“过激”拒绝。`--approve` 后 budget 2 获得 lease，其他候选保留为负结果；`prediction_audit` 记录预测与 hidden/transfer/regression 的实际差值（含 gap delta）。由于证据全部是 synthetic fixture，`rsi_report.simulation=true` 且 `capability_claims=[]`。它只验证控制回路、隐藏集隔离、租约消费与指标管线，不是科研质量结论。

## 8. 不能宣称

- 不宣称已实现 L5 元改进；公开系统大多停在 L3/L4；
- 不把 RRSI/DGM/SICA/SIFT 的论文增益当成我们的结果；
- 不把 prompt/记忆增长当成能力增长；
- 不把 public 提升当成 hidden/迁移；
- 不让 Agent 自动改 claim/gate/rubric/export；
- 没有 peer-review 固定 benchmark 和两轮真实复评前，不写“免训练 RSI 已跑通”。

## 9. 来源

- RRSI: https://arxiv.org/abs/2609.24972
- DGM: https://arxiv.org/abs/2505.22954
- SICA: https://arxiv.org/abs/2504.15228
- SIFT: https://arxiv.org/abs/2609.19526
- Gödel Agent: https://arxiv.org/abs/2410.04444
- GEPA: https://arxiv.org/abs/2507.19457
- ACE: https://arxiv.org/abs/2510.04618
- MASS: https://arxiv.org/abs/2502.02533
- ReasoningBank: https://arxiv.org/abs/2509.25140
- RSI Survey: https://arxiv.org/abs/2607.07663
- The Last AI Built by Humans: https://arxiv.org/abs/2609.11873
- Awesome RSI: https://github.com/es4er/awesome-rsi

> 上述论文的效果数字均为作者口径，未在本项目复现；本项目的“免训练”指冻结模型权重，当前尚未接真实模型/评测，因此不产生 RSI 能力声明。

# 23 · 开源自改进机制对照：从 A-Evolve、RSI-Anything 到我们的 Lease-Gated Runtime

> 版本：v0.1 · 日期：2026-10-23 · 性质：机制对照 + 实现设计补充  
> 输入：本地 `oss/` 快照（RSI-Anything、AutoResearchClaw、ARIS、AutoResearch、AutoSci、OpenRSI-Index）、[20](20-开源科研Agent框架调研-浙大SciToolAgent与主流技术栈.md)、[21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md)、[22](22-可扩展工程架构与论文创新点-从Demo到可维护证据运行时.md)、[19](19-RSI出题规范对照-自进化运行纪律反思.md)、[11](11-自进化循环设计-准入理由、跨循环继承、迁移与能力增益.md)  
> 边界：本轮**阅读**了公开仓库/快照的结构与关键文档，**没有运行** DeepScientist/CycleResearcher/RSI-Anything/AutoResearchClaw/ARIS 的任何实验；外部效果数字不引用。我们的自进化仍是设计 + SIM，E7/E8 未实测。

---

## 0. 结论

现有“科研 Agent 自改进”大致有四种，不能混为一谈：

1. **单轮内迭代**：同一任务里改代码/改稿/重跑，直到 rubric 或 reviewer 通过。代表：AI-Scientist-v3、ARIS 的 review loop、AutoResearch 的 runner loop。它没有跨轮保留能力。
2. **持久工作区/技能**：把失败经验写成 skill、prompt patch、knowledge entry、state，下次加载。代表：AutoResearchClaw 的 `a-evolve`、AutoResearch 的 `state.md` / memory、DeepScientist 的 `skills/` 与 research map。它可能有跨轮保留，但很多只靠人工/提示词门。
3. **模型/策略学习**：用反馈训练/更新 policy、world model 或 reviewer，保留新 checkpoint。代表：RSI-Anything（policy + world model 的 retained pair）、CycleResearcher（researcher + reviewer 的 RL）。它是真正的参数/行为改变，但训练重、评测门槛高。
4. **准入/元评测层**：不训练模型，也不直接改产物，而是判断“这次改进能不能留下、下一次能不能用”。代表：我们的 EV0–EV4、PF、租约、隐藏评测、step 账本。

**我们的选择**：做第 2 + 第 4 层，而不是第 3 层。即 **技能/过程协议的持久化 + 受控准入**；不训练模型、不自动改 claim/门槛/判据。这样既能体现自改进，又能在毕设周期内落地，并且与“证据闭合/可签署草稿”的主线一致。

---

## 1. 证据与方法

| 材料 | 用途 | 等级 |
| --- | --- | --- |
| `oss/RSI-Anything-main/README.md`、`docs/*` | RSI 的 propose/predict/select/evaluate/learn/retain、retained pair、validation/hidden | 本地快照已读 |
| `oss/AutoResearchClaw-main/.claude/skills/a-evolve/SKILL.md` | Solve→Observe→Evolve→Gate→Reload、skill/prompt/knowledge 三类 mutation | 本地快照已读 |
| `oss/Auto-claude-code-research-in-sleep-main/AGENT_GUIDE.md`、`skills/*` | ARIS 的 reviewer 路由、review loop、edit whitelist、acceptance gate、state 恢复 | 本地快照已读 |
| `oss/AutoResearch-main/README.md`、`ar-runtime/*`、`knowledge_base/agent_memory.md` | Coordinator/Ralph loop、两阶段实验、GPU preflight、memory | 本地快照已读 |
| `oss/AutoSci-main`、`oss/OpenRSI-Index-main` | 自动科研/RSI 评测索引的旁证 | 结构/文档已读 |
| [DeepScientist](https://github.com/ResearAI/DeepScientist) 公开仓库 | 逐轮 prompt 组装、`memory`/`artifact`/`bash_exec` MCP、21 个 `src/skills/*/SKILL.md`、`artifact/guidance.py` 的下一技能建议 | 完整工作树快照已读；README 与 commit `b366244` 哈希一致（未运行） |
| [CycleResearcher](https://github.com/zhu-minjun/Researcher) | RL 训练 researcher/reviewer 的模型级改进 | 仓库/论文入口，未运行；许可证限制见 §3.6 |
| [AI-Scientist-v3](https://github.com/SakanaAI/AI-Scientist-v3) | Docker + coding agent + rubric/自验证的 run 级迭代 | 完整工作树快照已读；README 与 commit `df83138` 哈希一致（未运行） |
| [19](19-RSI出题规范对照-自进化运行纪律反思.md) | 固定实例/租约控制器/隐藏评测/step 账本 | 本项目设计 |

> 说明：clone 状态以 [`oss/full/CLONES.md`](oss/full/CLONES.md) 为准。本文区分三种证据：**完整 git clone（有 `.git`）**、**完整工作树快照（无 `.git`，但与上游 commit 校验过）**、**只读文档/README**。没有运行任何外部实验；未运行的内容不当作已复现。

---

## 2. 四种自改进的分层

| 层 | 改什么 | 保留什么 | 代表 | 主要风险 |
| --- | --- | --- | --- | --- |
| L1 单轮迭代 | 当前代码/稿/实验 | 无（只改本轮 artifact） | AI-Scientist-v3、ARIS review loop | 把“跑通”当成“变强” |
| L2 持久工作区 | skill、prompt、knowledge、state | 文件/技能/记忆 | AutoResearchClaw A-Evolve、AutoResearch、DeepScientist | 没有隐藏评测/租约，污染长期记忆 |
| L3 模型/策略学习 | policy、world model、reviewer | checkpoint/retained pair | RSI-Anything、CycleResearcher | 训练重、选择偏差、不可解释 |
| L4 准入/元评测 | 不改产物，只决定“留不留” | AdmissionRecord/Lease/账本 | 我们的 EV/PF/Lease | 如果没有运行器，只是状态机 |

**关键判断**：L2 最容易被误称为“自进化”。只要生成一个 `SKILL.md` 并放进目录，并不等于它会改进下一次任务；必须有 **固定实例、公开/隐藏评测、父版本对照、成本与负结果、人工准入**。这正是 [19](19-RSI出题规范对照-自进化运行纪律反思.md) 指出的缺口。

---

## 3. 逐项对照

### 3.1 RSI-Anything：真正的 retained pair

公开 README 的核心循环：

```text
Propose → Predict → Select → Evaluate → Learn → Retain
```

- 用一个世界模型预测候选后果，外部评测给反馈，策略/世界模型更新后形成 retained pair；
- 验证集决定是否接受新 pair；测试集（如 F200）在冻结后才用；
- GUI 任务里还做 old/new policy × old/new world 的 2×2 crossing；
- 每轮记录 checkpoint、source/input identity、评测收据；
- 结果在多个域（code/GUI/lab/reaction/immune）上验证。

**能借的**：

- “retained pair”/incumbent 思路：新版本必须严格优于旧版本才替换；
- 公开/验证/隐藏分离；
- 冻结后再做最终评测；
- 2×2 crossing，避免把“换模型”误当成“换策略”；
- 来源/hash/run 目录的审计。

**不能直接借的**：

- 需要训练/更新模型权重，成本高；我们不做 RSI；
- 它的“自主发现”叙事超出 A3；我们的准入只作用于技能/过程协议；
- 外部效果数字不可复用。

### 3.2 AutoResearchClaw A-Evolve：最接近“生成技能”的轻量实现

`a-evolve` 是 prompt-based 技能，核心是：

```text
Solve → Observe → Evolve → Gate → Reload
```

1. **Solve**：收集 run logs、pass/fail、metrics、review feedback；
2. **Observe**：按错误类别、根因、频率、严重度写结构化 observation；
3. **Evolve**：生成三类 artifact——新 Skill、prompt patch、knowledge entry；或 do nothing；
4. **Gate**：检查 specificity、testability、blast radius、consistency；
5. **Reload**：把 artifact 放到 `.claude/skills/evolved/`、prompts、`docs/kb/`，写 evolution log。

**能借的**：

- 失败→观察→候选的标准格式；
- 频率 ≥ 3 才生成 skill，避免一次偶然失败；
- 明确“do nothing”是合法决策；
- blast radius/consistency 的 gate；
- 产物版本日志。

**缺的**：

- 没有固定实例、公开/隐藏评测、租约、撤销传播、成本/负结果账本；
- Gate 是提示词判断，不是运行时硬门；
- 生成的 skill 可以直接被加载，缺少 sandbox/dry-run/人签；
- 没有证据契约（Skill 产物是否能进 claim 不由它管）。

### 3.3 ARIS：adversarial review loop + state，但不是持久技能进化

公开 `AGENT_GUIDE.md` 显示：

- 一个 executor 写代码/论文，独立的 reviewer（不同模型家族）批判；
- `/auto-review-loop` 在论文/结果上迭代，`REVIEW_STATE.json` 支持上下文压缩后恢复；
- acceptance gate 规定谁能 ACCEPT；edit whitelist 限制可改路径；
- 失败 ideas 进入 anti-repetition memory；
- 明确“同家族 review 只能驱动修订，不能算独立语义评审”。

**能借的**：

- 独立 reviewer/不同模型家族；同模型自评不算证据；
- edit whitelist（修改范围硬约束）；
- state 文件/断点恢复；
- 失败 ideas 反重复记忆；
- acceptance gate 的“谁有权接受”。

**缺的**：

- 主要优化当前论文/实验，不是跨任务技能保留；
- review 仍是模拟/内部评审，不能冒充真实同行评审；
- 没有 claim–EA–closure 的证据链。

### 3.4 AutoResearch（EvoMap）：可恢复 loop + 实验纪律

公开 README / `ar-runtime` 显示：

- Coordinator 调度 planner/coder/reviewer/runner；
- Ralph-style loop 用 `state.md` 恢复，每轮只推进一个未完成单元；
- 两阶段实验协议（预实验→主实验）；
- GPU preflight（RED/YELLOW/GREEN）、资源预算；
- `knowledge_base/agent_memory.md` 提醒“成功回答 ≠ 中间 memory 有用”，要求 no-memory control。

**能借的**：

- **可恢复状态机**，每轮一个单元，避免无限 loop；
- 实验前资源/安全 preflight；
- memory 的 no-memory 对照；
- 两阶段实验（探索/确证分开）。

**缺的**：

- 仍然以“把研究跑出来”为目标，缺少跨轮准入与证据闭合；
- 记忆是否有用需要对照，没有统一 hidden eval/lease；
- 不是证据运行时。

### 3.5 DeepScientist：本地工作区 + skills + research map

公开仓库显示：

- 本地优先 daemon，Python 引擎 + TypeScript/React UI；
- `src/skills/` 有 21 个技能：intake-audit / scout / idea / baseline / experiment / analysis-campaign / decision / write / figure-polish / paper-outline / paper-plot / references / review / finalize / rebuttal / optimize / science / nature-data / nature-figure / nature-paper2ppt / nature-polishing；
- `src/deepscientist/artifact/guidance.py` 会根据当前阶段与记录给出 `recommended_skill`、`recommended_action`、`why_now` 和若干 `artifact.record(...)` 动作；这是**流程建议**，不是准入判决；
- 可选 Claude Code/Codex/OpenCode；Docker/本地运行。

更关键的是它的 prompt 维护方式。`docs/en/14_PROMPT_SKILLS_AND_MCP_GUIDE.md` 明确说：不存在一个静态 mega-prompt；每一轮都从 system prompt、shared interaction contract、runtime state、quest files、startup contract、priority memory、connector rules、active skill 重新组装。Agent 只通过三个内置 MCP 命名空间工作：`memory`、`artifact`、`bash_exec`。`docs/en/07_MEMORY_AND_MCP.md` 把三者分工写成 “artifact drives the quest / memory reduces rediscovery cost / bash_exec runs durable shell work”，并明确 memory 不能作为路线决策的唯一依据。

它的 quest-local prompt mirror 存放在 `quest_root/.codex/prompts/`；每轮运行前与仓库 `src/prompts/` 比较，源变了或本地漂移就刷新，刷新前把旧树备份到 `quest_root/.codex/prompt_versions/<backup_id>/`。**默认让旧 quest 使用最新 prompt 合约**，历史版本只用于显式 replay。

**能借的**：

- 本地优先、daemon + UI + skills 的工程形态；
- 技能目录分类（可直接作为我们的 builtin catalog 参考）；
- 逐轮重建 prompt、prompt 版本备份、`artifact` 作为任务连续性主干；这比“所有规则塞进 system prompt”更适合长任务；
- research map/记忆的持久化；
- 完整的 React UI 栈（Vite/Radix/TanStack/xyflow/Monaco/Tiptap/Playwright）。

**需要补的 / 不能直接照搬的**：

- **prompt 自动刷新没有准入门**：旧 quest 默认吃最新 prompt，只留备份，没有固定实例上的公开/隐藏评测、没有父版本对照、没有租约与撤销传播。它解决了“可回放”，没有解决“这次改动是否真的更好”；
- memory 是降低重复发现成本的检索层，不是带来源、有效期、冲突与撤销的记忆准入层；`memory` 可以影响下一轮，但没有我们的 EA/Claim 级证据契约；
- 按公开目录，skill 生命周期、证据契约、租约、撤销传播、隐藏评测没有形成我们要求的硬门；需要在我们的 Skill Runtime 中补齐；
- “research map 越跑越大”不等于“能力越强”；必须用固定实例/隐藏评测证明；
- 全自主叙事与 A3 不一致。

> 对照结论：DeepScientist 的 prompt 自更新属于 **L2 持久化 + 隐式变更**，不是 L4 准入。我们的差异不是“也做一个 skills 目录”，而是把每次 skill/prompt/process 变更放进 `EV0–EV4 + 公开/隐藏评测 + lease + revoke` 的可审计闭环。

### 3.6 CycleResearcher：模型级 RL，不是运行时技能

公开资料显示：

- 用 CycleResearcher（policy）和 CycleReviewer（reward）迭代，自动评审驱动研究改进；
- 训练数据/模型权重/评测；属于 L3，而非 L2；
- 有论文/代码，但训练成本高、泛化未证。

**许可证事实（2026-10-23 核对 `LICENSE.md`）**：它不是 MIT/Apache。仓库使用 *CycleResearcher License*（自称基于 Mistral AI Research License），要求访问者先提交姓名/单位/机构邮箱/研究目的并接受条款；仅允许非商业学术/教育用途；禁止商业使用、禁止未披露直接投稿、禁止把模拟实验当真实数据、禁止以不同条款再分发。GitHub API 因此把它标成 `NOASSERTION`。

**能借的**：

- “自动评审作为反馈”的思路；
- 训练/评测分离、reviewer 独立。

**不借**：

- **不复用其代码/模型/权重，不打包进我们的交付物，不再分发快照**；只做本地只读对照。若未来要使用，先由作者确认注册与授权；
- 我们的毕设不训练科研大模型；不自称 RSI；
- 自动评审不能替代真实同行评审；
- 效果数字不可复用。

### 3.7 AI-Scientist-v3：run 内自验证，不是跨轮自进化

README 形态：

- `task.md` → coding agents → 想法/实验/rubric/基线/消融/最终评测/论文；
- 每阶段一个 run 目录；Docker；编码 Agent 全权限警告；
- 有 rubric/self-verification，但主要是**单次 run 内**的迭代。

**能借的**：

- run 目录、Docker、rubric、自验证；
- 编码 Agent 的 harness 隔离；
- 失败/重试的记录。

**不能借**：

- 把单轮内“改到通过”称为“系统自我进化”；
- 让编码 Agent 继承 API key/宿主权限；
- 外部效果数字。

### 3.8 OpenRSI-Index：评测索引，不是 Agent

它是 RSI/科研 Agent 的索引/评测层，不是自改进运行时；可借其“公开证据/评测”视角，但不能当组件。

---

## 4. 对照表

| 系统 | 改进层 | 是否跨轮保留 | 公开/隐藏分离 | 人签/租约 | 证据闭合 | 我们能借什么 |
| --- | --- | --- | --- | --- | --- | --- |
| RSI-Anything | L3 模型/策略 | 是（retained pair） | 有 validation/F200 | 部分接受机制 | 否 | retained/2×2/冻结评测 |
| AutoResearchClaw A-Evolve | L2 技能/prompt/knowledge | 是（文件） | 无 | 提示词 gate | 否 | Solve→Observe→Evolve→Gate→Reload |
| ARIS | L1/L2 review loop | 部分（state/memory） | 无严格 hidden | acceptance gate | 否 | 独立 reviewer/edit whitelist/state |
| AutoResearch | L1/L2 loop+memory | 部分（state.md） | 无 | 人工/流程 | 否 | 可恢复状态机/GPU preflight/no-memory 对照 |
| DeepScientist | L2 工作区/skills | 是（prompt mirror + research map） | 未见硬门 | 未见硬门；prompt 自动刷新 | 否 | 本地 first/技能目录/prompt 版本备份/UI |
| CycleResearcher | L3 模型 RL | 是（权重） | 训练/测试分离 | 无 | 否 | reviewer 反馈、独立评测（**许可限制，不复用**） |
| AI-Scientist-v3 | L1 run 内 | 否 | 有最终评测 | 否 | 否 | Docker/run 目录/rubric |
| 我们的目标 | L2 + L4 | 技能/协议 lease | 强制 public/hidden | 强制人签/租约 | 是 | 证据闭合 + 受控自进化 |

> DeepScientist 的“prompt mirror 自动刷新 + 旧版本备份”说明它已经把 **prompt 当成可演进的运行时对象**；但默认让旧 quest 吃最新 prompt，只解决可回放，不解决“改动是否更好”。这正是我们加 EV/隐藏评测/lease 的位置。
>
> CycleResearcher 的 *CycleResearcher License* 要求注册、非商业、披露，禁止未披露投稿与再分发；本表只做机制对照，不复用其代码/模型/权重。

---

## 5. 我们的机制：Lease-Gated Skill/Process Improvement

### 5.1 对象

```text
Observation         # 失败/低效证据（run artifact、日志、review）
SkillCandidate      # 新 skill / patch / prompt / knowledge
DryRunReceipt       # 沙箱 dry-run + golden
PublicEval          # 开发可见的 validation 结果
HiddenEval           # 冻结后的独立验收，不回灌
StepLedger           # 父版本、成本、对照、负结果
AdmissionRecord      # EV1–EV4 + 人签理由
Lease                # 版本、scope、到期、复评、撤销指针
ProcessProtocol      # PF-P0–P8，只改阶段执行，不改 claim
```

### 5.2 生命周期

```text
observe → propose → static/permission check → dry-run
→ public eval → shadow/pilot → hidden eval
→ EV0–EV4 → human admission → lease(active) → monitor
→ expire / revoke → dependency review / rollback
```

**硬门**：

- 没有 dry-run + golden，不能 pilot；
- 没有 public vs hidden 分离，不能准入；
- 没有 step ledger / 父版本/成本/负结果，不能声称“改进”；
- 没有 human admission，不能 active；
- 撤销必须传播到依赖 artifact；不能只改状态；
- 不能修改 claim、EA、门槛、判据、署名；只改技能/过程。

### 5.3 代码接口（设计）

```python
class SelfImprovementService:
    def observe(self, run_id: str) -> list[Observation]: ...
    def propose(self, observations: list[Observation]) -> list[Candidate]: ...
    def check(self, candidate: Candidate) -> GateReport: ...
    def dry_run(self, candidate: Candidate) -> DryRunReceipt: ...
    def public_eval(self, candidate: Candidate) -> PublicEval: ...
    def shadow(self, candidate: Candidate) -> ShadowReceipt: ...
    def hidden_eval(self, candidate: Candidate, frozen_artifact: Artifact) -> HiddenEval: ...
    def admit(self, candidate: Candidate, decision: HumanDecision) -> AdmissionRecord: ...
    def issue_lease(self, candidate: Candidate, scope: Scope) -> Lease: ...
    def revoke(self, lease_id: str, reason: str) -> RevocationReport: ...
```

- `Candidate` 只能改 skill/prompt/knowledge/process；不能改 claim/gate/policy。
- `HiddenEval` 在 final artifact 冻结后独立执行；结果不回写 candidate 选择。
- `LeaseController` 在 P0 前校验 skill/process 的 active lease；没有则拒绝确证运行。
- `RevocationReport` 沿 `SkillRun → Artifact → Claim/EA → Manuscript/Figure` 计算闭包。

### 5.4 步骤账本（最小字段）

```json
{
  "candidate_id": "C-014",
  "parent": "C-013",
  "type": "skill|prompt|knowledge|process",
  "artifact_hash": "sha256:...",
  "dry_run": "RCPT-...",
  "public_eval": {"metric": "...", "value": 0.82, "n": 50},
  "hidden_eval": {"status": "sealed", "metric": "...", "value": 0.79},
  "comparisons": [{"baseline": "incumbent", "delta": 0.03, "ci": "..."}],
  "cost": {"tokens": 102400, "cny": 6.8, "minutes": 42},
  "negative_results": ["..."],
  "human": {"decision": "approved", "signer": "...", "reason": "..."},
  "lease": {"ttl_days": 90, "scope": "..."}
}
```

### 5.5 自改进的“四问”映射

| 问 | 我们的实现 |
| --- | --- |
| EV1 为何被接受 | 理由链 + public/hidden 证据 + 人签；不是单一分数 |
| EV2 能否保留 | lease + 版本/谱系/依赖/到期/复评；回滚恢复快照 |
| EV3 能否迁移 | ScopePassport；近域 pilot，远域拒绝；相似度不是许可 |
| EV4 能否增益 | 固定实例、留出任务、对照、成本、区间；未跑不写增益 |

### 5.6 与 A-Evolve 的差异

A-Evolve 是“诊断 + 生成 artifact + 提示词 gate”；我们保留它的 **observation 格式/生成技能/频率阈值/blast radius/do nothing**，但加上：

- 运行时硬门（dry-run/golden/lease/revoke）；
- 固定实例/public-hidden/step ledger；
- 计算/人工成本与负结果；
- 证据契约与 claim 隔离。

### 5.7 与 RSI-Anything 的差异

RSI-Anything 改变 policy/world model；我们只改 **skill/process**。借它的：

- retained/incumbent（严格优于才替换）；
- validation vs final hidden；
- 2×2 crossing（旧/新技能 × 旧/新任务）；
- 冻结模型/产物后再最终验收；
- checkpoint/source identity 审计。

不借：训练模型、自主发现叙事、外部效果数字。

---

## 6. Demo 应该怎么体现

现有 evolution 镜头已经有 EV1–EV4、租约、过程反馈，但更像“面板”。建议改成一条可读的**自改进流水线**：

```text
P4 失败记录 / P7 人工退回
→ Observation（错误类别/频率/根因）
→ Candidate（skill / prompt / knowledge / do nothing）
→ Dry-run（沙箱 + golden）
→ Public eval（验证集）
→ Hidden eval（冻结后，封存）
→ EV1–EV4
→ 人签
→ Lease（scope/TTL/回滚）
→ 下一次 P0 前校验 → 成功/拒绝/撤销
```

- 每一步显示 artifact/收据/成本/负结果；
- Hidden eval 未冻结前显示 `SEALED`，不展示数值；
- 候选不能自动 active；
- 撤销时展示依赖闭包，而不是“删一行”；
- 全部标 SIM，直到 E7/E8 真正跑过。

> 逐阶段怎么定义“有效”（S1 文献 / S2–S3 Idea / S4–S5 实验 / S6 图表 / S8–S12 写作 / S13–S16 核验）、每段固定实例与主指标、以及可借的本地 skill 清单，见 [21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md) §9.9–§9.13；需要同时跑多个 Agent 的阶段（S1/S2/S3/S5/S6/S9/S10/S11/S13/S14）的 fan-out、合并、隔离与 `TeamPolicyLease` 见同文 §9.14；“论文与实验同时进行”的双轨/同步屏障与 `OverlapPolicyLease` 见 §9.15。这里不重复，避免两套口径。

---

## 7. 先实现什么（建议）

### P0：一条最小自改进链（1–2 周）

1. 固定一个任务与一个失败（例如 P4 的一次 run failure）；
2. 用 DeepSeek 生成 observation/candidate（skill 或 prompt patch）；
3. 沙箱 dry-run + 2 个 golden case；
4. public eval（固定验证集）；
5. 人工审核 → pilot lease；
6. 下一次 P0 前校验 lease；撤销时标记依赖 artifact；
7. 写 step ledger 与拒绝/回滚记录。

**先不要**：自动下载任意 Skill、自动 active、自动改 claim、训练模型、无限 loop。

### P1：E7/E8

- 固定实例、统一预算、父/子版本、公开/隐藏分离；
- 2×2 crossing/incumbent guard；
- 只报告固定实例上的结果；不宣称通用能力增益。

---

## 8. 不能宣称

- 不宣称“系统会自我进化/越跑越强”，除非 E7/E8 在固定实例上完成；
- 不把 `SKILL.md` 的生成当成能力提升；
- 不把单轮内“改到通过”当成跨轮自改进；
- 不自动下载/执行互联网 Skill；
- 不用 RSI-Anything/CycleResearcher 的效果数字；
- 不让技能修改 claim/门槛/判据；自改进只作用于执行与过程。

---

## 9. 证据状态

- 本轮只读 `oss/` 与 `oss/full/` 中的公开仓库副本；**未运行**任何外部框架的实验；
- 完整 git clone（有 `.git`，非浅拷贝）：SciToolAgent、DeepScientist、CycleResearcher/Researcher、AI-Scientist-v3；其余 10 个为**完整工作树快照**（无 `.git`），`HKUDS/AI-Researcher` 因工作树 901 MB 停在 `partial`；
- **逐仓 commit、branch、许可证、子模块/LFS、中断记录以 [`oss/full/CLONES.md`](oss/full/CLONES.md) 为准**；没有 `.git` 的副本不写成“完整 clone”；
- CycleResearcher 使用研究专用许可证（非 OSI），**只读对照，不复用/不打包/不再分发**；
- 我们的 EV/PF/lease 仍是设计与 SIM 演示；E7/E8 未实测；
- 任何“自改进有效”的结论必须来自固定实例 + 隐藏评测 + 人签，不接受单次演示或自报。

---

## 10. 来源

| 来源 | 用途 | 等级 |
| --- | --- | --- |
| `oss/RSI-Anything-main/README.md`、`docs/workflow.md`、`docs/benchmarks.md`、`tasks/gui/RESULTS.md` | RSI 循环、retained pair、validation/hidden、2×2 | 本地快照已读 |
| `oss/AutoResearchClaw-main/.claude/skills/a-evolve/SKILL.md` | Solve→Observe→Evolve→Gate→Reload、mutation/gate | 本地快照已读 |
| `oss/Auto-claude-code-research-in-sleep-main/AGENT_GUIDE.md` | adversarial review、state、edit whitelist、acceptance gate | 本地快照已读 |
| `oss/AutoResearch-main/README.md`、`ar-runtime/README.md`、`knowledge_base/agent_memory.md` | coordinator/Ralph loop、GPU preflight、memory 对照 | 本地快照已读 |
| `oss/AutoSci-main`、`oss/OpenRSI-Index-main` | 自动科研/RSI 评测旁证 | 结构/文档已读 |
| [ResearAI/DeepScientist](https://github.com/ResearAI/DeepScientist) | 本地优先、逐轮 prompt、skills、memory/artifact、guidance | 完整 git clone `b366244`（未运行） |
| [zhu-minjun/Researcher](https://github.com/zhu-minjun/Researcher) | CycleResearcher | 完整 git clone `8c1b253`；许可证限制（未运行） |
| [SakanaAI/AI-Scientist-v3](https://github.com/SakanaAI/AI-Scientist-v3) | Docker/run dir/rubric/self-verification | 完整 git clone `df83138`（未运行） |
| [19](19-RSI出题规范对照-自进化运行纪律反思.md) | 固定实例/租约控制器/hidden/step 账本 | 本项目设计 |
| [21](21-可落地系统设计与DeepSeek集成-证据闭合论文产出与Skill自进化.md) | 运行时/API/Skill/DeepSeek | 本项目设计 |
| [22](22-可扩展工程架构与论文创新点-从Demo到可维护证据运行时.md) | 端口/模块/不变量/论文贡献 | 本项目设计 |

> 外部效果数字、star 数、SOTA 提升未作为本文结论；未运行的内容保持“待验证”。

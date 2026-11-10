# 44 · Anthropic Sub-Agent + Loop 反思：单 Loop、渐进披露与证据治理

> 日期：2026-10-25  
> 参考：Anthropic, *Building agents: When to fold subagents into your main agent loop*（厂商 blog，非同行评审），以及其多智能体 research system 文章、LangChain multi-agent 架构文章。  
> 边界：本文是设计反思，不把厂商 blog 的“单 Loop 更快/更好”当成我们的实测结果；我们尚未做 A/B。

## 0. 判断

Anthropic 这篇文章的核心不是“subagent 没用”，而是：

> **默认用单 Agent Loop + 渐进披露的 skills/tools；只有上下文膨胀、并行且用完即弃、工具/指令冲突这三类情形才保留 subagent。**

这直接命中我们当前系统的三个风险：

1. **组织架构图式的 Agent 设计**：13 个模块、9 个阶段、1+4 多智能体、可批量创建的子智能体；这很像“每个团队一个 agent，再加 orchestrator”。
2. **把“角色”当成“运行时”**：coverage/citation/protocol/evidence 等审阅角色，本质是白名单 checks，应该由主 Loop 作为 tool/skill 调用，而不是独立 agent。
3. **评估滞后**：我们的 EVAL 仍是前端 SIM；没有端到端黄金集，无法判断折叠 subagent 到底变好还是变差。

但也不能全盘照搬：我们的差异化是**证据治理**。单 Loop 可以提高研究执行的质量与效率，但 claim/EA/gate/closure/signature 不能交给模型自由决定。正确目标是：

> **单 Research Loop 负责研究与工具调用；非 LLM 的证据治理层负责准入、签名、闭包与变更传播。**

## 1. 文章主张与证据等级

文章的关键主张：

- 多个企业部署对比中，“单 Agent Loop + 渐进披露 skills/tools”在质量、成本、延迟上优于“一个 super-prompt”和“多 subagent 编排”；
- 有客户实测单 Loop 约快 2 倍；
- Claude Code 面向新模型的系统提示词砍掉 80%+，部分来自 skills/tools 渐进披露；
- subagent 保留条件只有三类：上下文膨胀导致可测退化、并行且用完即弃的干净上下文、单个 agent 选不对工具或指令冲突；
- 迁移要评估先行，一次只折叠一个；折叠后变差就保留 subagent；
- 工具按用户意图分组；系统提示词里工具定义超过 30–50 个，工具选择开始退化；
- “Agent 记忆的尽头是 RAG”。

证据等级：`[厂商 blog]`。这些是架构经验，不是独立复现的实验；不能写成我们的结果。

## 2. 对照我们的系统：哪里像组织架构图

| 我们的设计 | 文章视角 | 判断 |
| --- | --- | --- |
| 13 个模块/Agent 角色 | 每个团队一个 agent + central orchestrator | **高风险**：多数应折叠为 tools/skills |
| 9 阶段固定流水线 | 模型自己写计划并随结果修订 | **高风险**：阶段是 harness 的视图，不应成为固定多 Agent 编排 |
| 1+4 多智能体拓扑（scout/builder/executor/auditor） | 默认单 Loop；subagent 只在特定情形 | **需要重定位**：S1 scout 可保留为并行 tool；其他角色应折叠 |
| 手动子智能体批量创建（coverage/citation/protocol/evidence/figure/closure） | 白名单 checks 应是 tools/skills | **应改名为 Review Pack / 审阅技能包**，不是默认 subagent |
| 4 个并列右栏 tab + 9 阶段 rail | 单 Loop 的 tool trace + gates | **前端应简化**：tool receipts + gate checklist |
| 固定 S1→META 全自动 | 模型第一轮写计划，执行中修订 | **高风险**：全自动应变成单 Loop + 预算/门禁，而不是固定 9 步 |
| Literature Memory（覆盖/缺口/预算） | 记忆最终是 RAG | **可保留为过程记忆**，但应增加 evidence RAG index |
| RSI/Lease/Closure/Lineage | 不属于 agent 编排 | **明确保留为外部治理层**，不折叠进 Loop |
| Skills 三态/按需加载 | 渐进披露 skills | **方向正确，保留并强化** |
| 25 个用户命令 + 10 个 Skill | 工具定义过多会退化 | 用户命令可保留；**模型 tools 必须收敛到 ~10–12 个** |

## 3. 哪些 subagent 该保留，哪些该折叠

### 保留

1. **S1 facet scouts（如果真实并行）**：core/survey、method/evaluation、limitation/recent 三个检索面向可以并行、上下文独立、结果用完即弃；这是文章允许的“并行 + 干净上下文”情形。前提是它们返回 `SourceHit/Span`，不是互相传话的摘要。
2. **可选 Review Pack**：只有在需要独立视角、且能并行时，把 coverage/citation/protocol/evidence/closure 作为多个审阅者并行跑；它们仍然是只读 checks，不写 Claim。
3. **RSI/治理 lane**：不是 subagent，是独立的评估/准入/租约控制面；保留。

### 折叠

1. **S2–S3 假设收敛**：它需要看到 S1 的完整 span 上下文；拆成 agent 会丢细节。折叠为主 Loop 的一个 `propose_hypotheses` tool/skill。
2. **S4 设计 / S8–S12 写作槽位**：都是同一上下文里的结构化产出；折叠为 `design_protocol` / `bind_paper_slots` tools。
3. **S6 图 / S13 书目 / 部分 closure 检查**：确定性检查，不需要 agent；作为 tool 或后置 gate。
4. **自定义审阅角色**：默认折叠为 `review_pack` tool；只有并行独立审阅时，才展开为多个只读 reviewer。UI 应从“子智能体”改为“审阅包”。
5. **固定 9 阶段全自动**：改为单 Loop + 预算/门禁；阶段 rail 只作为 tool trace 的可视化，不是执行器。

### 不折叠（关键边界）

- Claim/EA 写入、gate 判定、closure、signature、export：**不能变成模型可调用的写工具**。模型只能提出 `ClaimDraft`，人签与 closure 在外部治理层完成。
- Lease/RSI admission：模型不能授予自己租约；必须人签。
- Held-out/hidden：不能进入模型上下文。

## 3.1 我们现在的 subagent 调用路径（代码事实）

先把“能配置 / 能调用 / 能在主对话调用”分清：

| 层 | 当前实现 | 真实状态 |
| --- | --- | --- |
| 配置 | 设置页 `AgentManagement` + `/api/agents/custom` | WIRED：可增删改、启停、批量创建 |
| 编排调用 | `run_orchestration` 读取 `enabled_only=True` 的 custom agents，调用 `advisory_notes(custom_agents, merged, idea)` | WIRED，但只在 orchestration 的 S1–S3 stop point |
| 实际检查 | `CURRENT_ADVISORY_CHECKS = {coverage, citation, hypothesis}` | 只有这三类执行；protocol/evidence/figure/closure 返回 `deferred` |
| 前端展示 | `OrchestrationOverview` 显示 advisory notes；`AgentManagement` 管理角色 | WIRED，但不在主对话 |
| 主对话调用 | `sendMessage` 没有 custom agent / `@agent` 分支 | **ABSENT** |
| 执行性质 | 确定性白名单 check，不是 LLM subagent，不写 Claim/EA/gate | 本质是 advisory **tool**，不是 agent |

代码位置：

- `orchestrator.py:164-165`：`custom_store.list(enabled_only=True)`；
- `orchestrator.py:282`：`advisory_notes(custom_agents, merged, idea_result)`；
- `orchestration/advisories.py:7`：只执行 coverage/citation/hypothesis，其他 check deferred；
- `runtime/app.py:441`：orchestration 接收 custom agents；没有“调用单个子智能体”的 chat 端点；
- `workspaceStore.ts:1525`：`sendMessage` 没有 custom agent 分支。

所以更准确的说法是：

> **我们能“配置子智能体”，也能在编排的 S1–S3 里“运行 advisory checks”；但主对话没有调用入口，而且它们不是 LLM subagent。**

这也解释了为什么批量创建 protocol/evidence/figure/closure 角色后，它们在当前 stop point 里可能只是 `deferred`——UI 很容易让人误以为“配置了就生效”。

## 3.2 可调用 ≠ 应默认调用

Anthropic 文章并不反对 subagent，反对的是**把 subagent 当默认架构**。我们的调用路径正好可以分成两类：

### 可以保留的调用

1. **S1 facet scouts**：并行检索，独立上下文，返回 `SourceHit/Span`；
2. **Review Pack**：在 fan-in、G1 前、签署前、closure 前运行一组独立只读检查；
3. **独立 red-team reviewer**：高 stakes claim 的对抗性审阅，必须有干净上下文和 typed output。

### 不应该做成默认调用

- 把 literature/idea/experiment/paper 各做成一个 agent，然后让 orchestrator 传话；
- 每次用户说话都自动 fork 多个 reviewer；
- 让 review agent 拥有写 Claim/EA/gate/closure 的工具；
- 把 `deferred` 的 protocol/evidence/figure/closure check 包装成“已运行”。

## 3.3 Review Pack：推荐的 subagent 调用方式

把“多个子智能体”收敛成一个 **Review Pack tool**：

```text
review_pack(
  task_id,
  evidence_refs,       # span/EA/claim refs
  checks: ["coverage","citation","hypothesis"],
  budget: {max_reviewers: 3, timeout_ms: ...}
) -> {
  findings: [{check, status, summary, refs, reviewer}],
  boundary: "advisory only"
}
```

调用时机：

- S1 fan-in 后：coverage/citation；
- G1 前：hypothesis；
- 签署前：evidence（如果已实现）；
- closure 前：closure/figure（如果已实现）。

交互：

- 默认一个“审阅包”按钮/ `/review`，不是十个 agent 入口；
- 运行后显示一条 compact receipt：`Review Pack · 3 checks · 2 warn · 1 deferred`；
- 只有用户显式 `@reviewer` 时才调用单个 reviewer；
- 结果只读、不写 Claim/EA/gate，不自动推进流程；
- 若 pack 只是确定性 checks，就把它标成 tool，不要叫 subagent。

评估：

- 先比较“无 review / 单 Loop 自检 / Review Pack”在 10–20 条任务上的质量、延迟、成本；
- 如果 Review Pack 没有可测收益，就把它折叠成主 Loop 的普通检查步骤；
- 如果它显著降低错误率，再保留为可选并行 subagent。

### 3.4 已落地的最小 Review Pack（2026-10-25）

把上面的设计先做成一个最小可用的会话动作：

- 新增 `apps/web/src/domain/reviewPack.ts`：把当前 task 的 coverage/citation/hypothesis/protocol/evidence/figure/closure 映射为 advisory findings；
- 新增 `runReviewPack`：通过 `/review` 或 Composer 建议触发；读取已启用的自定义子智能体；没有启用项时使用三条默认审阅（覆盖/引用/假设）；
- 结果以一张 compact `review-pack` 卡进入对话，包含 `reviewers / checks / pass / warn / deferred / blocked` 与逐项 summary；
- 明确写出“只读 deterministic checks：不调用 LLM、不写 Claim/EA/gate、不替代人工签署”；
- 不新增多 agent 面板，也不把 deferred check 说成已执行。

同时补了一个破坏性回退的守卫：已有 `signed` claim 时，`/run` 与启动/单步全自动会被拒绝，避免重跑把签名静默重置为 `unsigned`；Composer 在签署后的主建议也改为“运行审阅包 / 生成写作槽位 / 查看证据链”。

已验证：签署后 `/run` 被拒且 claim 保持 `signed`；`/review` 生成 2 reviewers / 3 checks 的 receipt；1440/390 无横向溢出、无 console error。

仍未解决：closure 入口与 `flowFor(task)` 的统一状态机；Review Pack 仍依赖前端快照/当前任务状态，不是独立 LLM subagent，也没有真实跨 reviewer 并行与成本账本。

## 4. 目标架构：单 Loop + 工具 + 证据治理

```text
┌─────────────────────────────────────────────┐
│ Research Loop（一个模型 / 一个上下文窗口）    │
│  plan → tool calls → observe → revise       │
│  tools: search_sources / read_pdf /          │
│         extract_span / propose_hypotheses /  │
│         design_protocol / run_experiment /   │
│         bind_slots / review_pack /           │
│         search_evidence                      │
│  skills: 渐进披露（procedure knowledge）      │
└───────────────┬─────────────────────────────┘
                │ typed artifacts
┌───────────────▼─────────────────────────────┐
│ Evidence Governance（非 LLM，不可写面）       │
│  ClaimDraft → 人签 → EA → Closure → Export   │
│  Lineage / ChangeImpact / Lease / RSI        │
└─────────────────────────────────────────────┘
```

关键点：

- **Loop 自己写计划、自己执行、自己修订**；不把计划交给 orchestrator 再传话。
- **工具按意图分组**，不是一 API 一 tool；模型工具控制在 10–12 个，用户命令可以另算。
- **Skill 是程序性知识**，加载后影响 Loop 的做法；不是独立 Agent。
- **Memory 是证据 RAG**：`search_evidence` 在 sources/spans/claims/decisions 上检索；结构化证据仍是权威源，RAG 只是检索层。
- **治理层不在 Loop 内**：它不参与“研究下一步”，只决定“能不能声称、能不能导出”。

## 5. 前端如何呈现

文章对前端的启示不是“少画图”，而是**不要把内部编排画成组织架构**。

1. **一个对话 + 一个案卷**：主 Loop 的 tool calls 以 inline receipt 出现；右栏是当前证据对象。
2. **阶段 rail 降级为 tool trace**：9 阶段可以保留为历史/审计视图，但默认不铺满一屏；当前步骤 + 下一步足够。
3. **Review Pack 取代“子智能体”主导航**：默认一个审阅包；需要并行独立视角时再展开多个 reviewer。
4. **不再默认展示多智能体拓扑**：拓扑是审计视图，不是主界面。
5. **Next Action 条**：由 `flowFor(task)` 驱动；不是按 mode 猜。
6. **预算/成本可见**：单 Loop 的轮次、token、工具调用次数、延迟；这比“支持多少 Agent”更重要。
7. **保留治理状态**：Claim/EA/Gate/Closure 仍是第一等对象；它们不是 tool receipt。

这与 `41-` 的 Evidence Desk 方向一致：对话是桌面，右栏是案卷，工具调用是 receipt，阶段是 trace。

## 6. 评估先行：一次只折叠一个

Anthropic 的迁移方法可以直接借用：

### 第一步：建立端到端 eval

- 10–20 个黄金任务（真实主题 + 证据 + 期望产物）；
- 指标：任务完成率、claim 支持正确率、工具选择正确率、closure 通过率、延迟、token、成本；
- 每个 skill/tool 一个小 eval（哪怕 10 条）；
- 先测当前 9 阶段基线和当前多 agent 配置。

### 第二步：折叠一个

建议顺序：

1. **S2–S3 假设收敛** → 主 Loop 的 `propose_hypotheses`；
2. **S4 设计 / S8–S12 槽位** → `design_protocol` / `bind_slots`；
3. **自定义审阅角色** → `review_pack` tool；默认一个，按需并行；
4. **S1 scouts** 保留为并行 tool，最后再评估是否折叠；
5. **9 阶段全自动** → 单 Loop + 预算/门禁；阶段 rail 只做 trace。

每次只改一个，跑 3–5 次（文章提醒：有些问题两次才出现一次），比较：

- 质量是否下降；
- 延迟/成本是否下降；
- 证据闭合是否仍成立；
- 工具选择是否退化。

变差就保留 subagent；不要为了“架构统一”强行折叠。

## 7. 与现有文档/实现的关系

- `09-` 的 13 Agent/9 门禁/五类流程：作为**逻辑视图**保留，但不再是默认运行时；实际运行时收敛为单 Loop + tools/gates。
- `17-` 的微服务/bounded context：保留证据、closure、audit；不要按阶段拆服务。
- `18-` 的 1+4 多智能体：把“4 类职责”重定位为 Review Pack/并行检索，不默认启用。
- `40-` 的 Claude Code 分层：继续保留 Command/Skill/Agent/Permission 的区分；Agent 只作为可选并行审阅。
- `41-` 的 Evidence Desk：与新方向一致；阶段 rail 降级、Next Action 上升。
- `42-` 的后端创新：不变——单 Loop 不改变 claim/closure/lineage/RSI 的治理需求，反而更需要它们。
- 最近做的“批量新建子智能体”：保留配置能力，但 UI 文案改为“审阅包/Review Pack”，默认只建一个；多角色是并行审阅的可选配置，不是系统默认。

## 8. 风险与不可宣称

- 文章是厂商 blog，不是独立 benchmark；“单 Loop 快 2 倍/质量更好”不能写成我们的结果；
- 单 Loop 可能带来上下文膨胀、工具选择退化、长运行成本；
- 折叠 subagent 可能破坏某些流程（文章自己也举了反例）；
- 我们的证据治理层比文章的 harness 更重，可能增加延迟；但这是差异化，不应为了速度删掉；
- 在真实 eval 之前，不能宣称“单 Loop 更适合我们的系统”。

## 9. 结论

我们最该反思的不是“subagent 数量”，而是**是否把组织架构误当成了 Agent 架构**：

> 13 个模块、9 个阶段、1+4 多智能体和批量审阅角色，不应默认全部成为运行时 Agent。  
> 默认应是：一个 Research Loop + 渐进披露的 skills/tools + 一个非 LLM 的证据治理层；subagent 只在并行、干净上下文、可测收益时保留。

如果只做一件事：**先建 10–20 条端到端 eval，再折叠 S2–S3 假设收敛**。这比继续增加子智能体配置或阶段更能让系统变清晰。

一句话：

> 我们不是要做一个“多 Agent 科研组织”，而是要做一个**单 Loop 研究助手 + 可审计证据运行时**；多 Agent 是可选工具，不是身份。

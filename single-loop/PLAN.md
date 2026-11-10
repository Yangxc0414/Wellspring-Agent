# Single loop plan

Audit date: 2026-10-25  
Repo and commit: 主项目目录当前不是 git 仓库；前端镜像远端为 `Yangxc0414/research-agent` 的 `main`（当前评审包部署对应 commit `6fb4c26bb769e03f1df6a3d66d1b9330d72cfba7`）。  
Reference kit: `research/anthropic/repos/single-agent-loop-kit` @ `c43796287b83bec847db923f07131d1cc8de750d`（Apache-2.0）。

## Status

- [ ] Verdicts agreed with the person (end of step 0)
- [ ] Main eval agreed and baseline measured (end of step 1)

A new session picks up at the first unticked box here, then at the first unticked item in the worklist.

## Verdicts

| Agent/模块 | Verdict | Why, in one sentence | Evidence | Confidence |
| --- | --- | --- | --- | --- |
| orchestrator | `main` | 当前最接近路由/编排入口；但它是确定性 plan/fan-in，不是模型 Loop，必须重建为单 Loop | `research_agent/orchestrator.py:144`；`orchestration/plan.py` | high |
| research_pipeline | `fold` | S1→S6→S8–S12 是固定 workflow，固定步骤应该是代码/工具，不是常驻 Agent | `pipeline.py:114` | high |
| s1_facet_scouts | `merge:literature` | 三个 scout 读同一合并证据、按 facet 并行；应收敛成一个并行检索工具 | `orchestration/plan.py:288` | medium |
| literature | `fold` | 检索/解析/span 应是 `search_sources` 工具；span-only 规则留在 harness | `modules/literature.py:464` | high |
| idea | `fold` | 候选生成是同一上下文里的结构化提案，不应丢给独立 Agent | `modules/idea.py:60` | high |
| experiment | `fold` | 协议设计是 `design_protocol` 工具；硬门 G2 仍在 harness | `modules/experiment.py:46` | high |
| figure | `fold` | 确定性 SVG 渲染，适合 `render_figure` 工具 | `modules/figure.py` | high |
| paper | `fold` | 5 个槽位契约，适合 `bind_paper_slots` 工具 | `modules/paper.py:70` | high |
| grant | `fold` | 基金写作 profile/slots，不是独立 Agent | `modules/grant.py:70` | high |
| run | `as-tool` | 真实本地计算，返回 capsule/EA，适合有边界的一次工具调用 | `modules/run.py:59` | high |
| bibliography | `fold` | 书目形状检查应是 `verify_bibliography` 工具/门禁 | `bibliography.py:23` | high |
| closure | `keep` | 治理/导出硬门，永远不能变成模型可写工具 | `closure.py:35` | high |
| lineage | `keep` | 内容哈希图与变更传播是审计层，不是 Agent | `lineage.py:179` | high |
| rsi | `keep` | 候选/准入/租约是元治理 lane，不是 subagent | `rsi.py:364` | high |
| skills | `fold` | 目录与 instructions 应通过 `load_skill` 渐进披露 | `skill_registry.py:59` | high |
| custom_advisory_agents | `as-tool` | 白名单 checks 应作为一个 Review Pack 工具；当前只有 coverage/citation/hypothesis 执行 | `orchestration/advisories.py:7` | high |
| review_pack_frontend | `as-tool` | 已落地的 `/review` 只读 receipt，是多 reviewer 收成一个工具的示例 | `apps/web/src/domain/reviewPack.ts` | high |
| nine_stage_auto | `fold` | 固定 9 阶段 timer 即使 closure 受阻也继续到 META；固定步骤应是代码/tool trace | `workspaceStore.ts:715` | high |

### Glue that goes away as subagents fold

- `pipeline.py` 的固定 S1→S6→S8–S12 顺序；
- `orchestration/plan.py` 的 facet 分配与 fan-in 传话；
- `workspaceStore` 里 `advanceAuto` 的 9 阶段 timer 与 stage 索引；
- `suggestionsFor` 按 `mode` 猜下一步；应由 `flowFor(task)` 替代；
- 自定义审阅角色的“多 Agent 面板”入口；收敛为 Review Pack。

### Prompt notes

- 我们的模块没有真正的 system prompt（多为规则/模板），所以这不是“13 个 LLM Agent”，而是**确定性 workflow + 一个尚不存在的 Research Loop**；这是本次审计最重要的发现。
- 硬限制必须留在 harness：span-only、EA/claim、G2 预注册、G5 closure、signature/export、held-out。
- 若未来加 system prompt，只保留“何时调用哪个工具/skill”，不要把口径、证据规则和门禁写进模型可改的文本。
- 前端文案/建议不要充当 prompt；`mode` 是视图，不是 phase。

## Evals

| Eval | What it measures | What to do with it |
| --- | --- | --- |
| `python -m unittest discover -s tests -v` | 135 个单元/契约测试 | 作为工程回归基线，不作为科研能力分数 |
| 前端 `/review` 流程 | 审阅包 findings、状态、移动端 | 作为交互回归，不作为质量收益 |
| 端到端 golden tasks（待建） | 任务完成、证据闭合、工具选择、延迟/成本 | **Step 1 必须先建这个** |

Main metric（建议）：**task completion + evidence invariants（span/EA/claim/closure）+ latency/tokens/error**；不是“调用了多少 Agent”。

Gaps noticed:

- 没有真实 LLM Loop；
- 没有端到端 golden eval；
- closure/export 主流程未闭环；
- Review Pack 是确定性 checks，未证明比“无 review / 主 Loop 自检”更好；
- 没有真实并行、独立上下文与成本账本。

Chains with no task (from code/flow, no `chain_coverage.py` export yet):

- S1 → idea → design → freeze → run → sign → closure；
- S1 → Review Pack → claim；
- run → EA → claim → closure → export；
- dataset/code change → lineage impact → stale → re-export；
- 9-stage auto → claim gate → S13 blocked。

Break map:

| What could break | Tasks that would notice | Gap, and the task to add |
| --- | --- | --- |
| Dropped handoff | 无端到端 eval | 加 S1→idea→design→run 任务 |
| Lost rule | span-only 单测；无 closure 语义测试 | 加“摘要-only 不得生成 span”端到端任务 |
| Shortcut | 无“无 EA claim”任务 | 加 forged-claim / no-EA 任务 |
| Wrong pick | Review Pack 手动；无选择准确率任务 | 加 reviewer/tool 选择 eval |
| Unwanted write | 已签 claim 重跑守卫 | 加 signed-claim rerun 任务 |
| Lost thread | 无会话恢复任务 | 加 localStorage/快照恢复任务 |
| Unhappy path | 无 closure blocked 任务 | 加 closure 9/11 与未决项任务 |

Baseline (variant `baseline`):

- 工程：`python -m unittest discover -s tests -v` 最近一次 **135 tests OK**；
- 前端：线上 `/review` 生成 2 reviewers / 3 checks；签署后 `/run` 被拒，claim 保持 `signed`；静态模式 0 `/api` 请求、无 console error；1440/390 无横向溢出；
- 未测：task completion、latency/tokens、Review Pack 与无 review 的对照、真实模型调用；
- 参考 kit 自身：48 tests 在 Python 3.12 全部通过；本仓库默认 Python 3.8 下因 `Path.is_relative_to` 失败（3 failures / 8 errors），所以 kit 代码不能直接复制进当前 runtime；
- 因此：**还没有可用来决定 fold 的 scored baseline**。

## Worklist

Merges first, then folds, then as-tool changes. Highest traffic first inside each group. One line per change. Each variant is compared with the last one that was kept.

- [ ] 1. 建 10–20 条端到端 golden eval 与 baseline · variant: `baseline` · compared with: — · result: 待跑
- [ ] 2. 建 `research_loop` + tools/skills + budget/write gate 的骨架 · variant: `v0-loop` · compared with: `baseline` · result: 待跑
- [ ] 3. 把 S2–S3 假设收敛 fold 进主 Loop · variant: `v1-idea` · compared with: `v0-loop` · result: 待跑
- [ ] 4. 把 S4 设计 / S8–S12 槽位 fold 成工具 · variant: `v2-design-paper` · compared with: `v1-idea` · result: 待跑
- [ ] 5. 评估 Review Pack 作为 as-tool 是否带来可测收益（已落地） · variant: `v3-review` · compared with: `v2-design-paper` · result: 待跑
- [ ] 6. 决定 S1 scouts：并行检索工具 vs 保留独立上下文 · variant: `v4-scouts` · compared with: `v3-review` · result: 待跑
- [ ] 7. 保持 run/closure/lineage/RSI 为 tool/gate，不折叠 · variant: `v5-governance` · compared with: — · result: 待定

## Changes

### Item 0: Review Pack as-tool（已落地，但未计分）

Comparison with baseline: **无 scored 对照**；不能声称质量提升。

- 变更：`apps/web/src/domain/reviewPack.ts`、`/review` 命令、`review-pack` 卡；把多个审阅角色收成一个只读 receipt；没有 LLM、Claim/EA/gate 写入。
- 变更：已签 claim 时 `/run`、启动/单步全自动被拒，避免签名被静默覆盖（`workspaceStore.ts`）。
- 验证：线上 `/review` 2 reviewers / 3 checks；签署后 `/run` 被拒；静态模式 0 `/api`、0 4xx/5xx、无 console error；1440/390 无横向溢出。
- 未测：是否比“无 Review Pack / 主 Loop 自检”更好；延迟/成本；真实 reviewer 的独立上下文。
- 结论：这是 `as-tool` 的最小实现，**不是**单 Loop 迁移完成，也不能作为质量收益证据。

## Open questions for owners

- “Main” 究竟是哪个对象？当前没有真正的 LLM Loop；orchestrator 只是确定性 plan/fan-in。
- 端到端 eval 的 10–20 个任务如何定义？用 fixture、ChemLab，还是允许真实模型调用？
- `closure` 在主流程中的入口由谁提供？当前静态前端没有 closure run 按钮，G5 永远 blocked。
- S1 scouts 是否值得保留独立上下文？当前是确定性 fixture，没有真实并行/成本数据。
- 下载的 `skills` 仓库包含 source-available 的 docx/pdf/pptx/xlsx；只能本地参考，不能直接作为开源交付物。

## Left as it is, and why

- `closure`、`lineage`、`rsi`：治理/审计层，不是会说话的 Agent；不能折叠进模型 Loop。
- `run`：真实计算 + capsule/EA，适合作为有边界的 tool，而不是主 Loop 的一部分。
- 未来的 `research_loop` 不拥有 Claim/EA/gate/closure/signature；这些是不可写面。

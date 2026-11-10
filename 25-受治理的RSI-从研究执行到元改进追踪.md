# 25 · 受治理的 RSI：从研究执行到元改进追踪

> 日期：2026-10-24 · 性质：长期路线 + 控制面实现记录（不是 RSI 效果报告）  
> 代码：[`research_agent/rsi.py`](research_agent/rsi.py) · 规格：[`modules/rsi/SPEC.md`](modules/rsi/SPEC.md) · 相关：[10](10-RSI与自进化反思-科研改进的准入与证据闭合.md)、[11](11-自进化循环设计-准入理由、跨循环继承、迁移与能力增益.md)、[19](19-RSI出题规范对照-自进化运行纪律反思.md)、[23](23-开源自改进机制对照-从A-Evolve-RSI-Anything到我们的Lease-Gated-Runtime.md)

## 1. 先给结论

“让一个 Agent 改自己的 prompt、再去写论文”不是 RSI，它只是**未受治理的自我改写**。  
真正要做的是一条三层闭环：

```text
研究执行环：Task → S0–S16 → artifact / EA / manuscript
改进环：   Observation → Candidate → dry-run → public → hidden
          → EV0–EV4 → 人签 → Lease → monitor / revoke
元 RSI 环：episode 组合 → 预测 vs 实际 → 保留/迁移/成本/负结果
          → 下一轮实验选择；审计自己的“改进”主张
```

当前项目有 fixture 纵切、真实 CC-BY 文本 evaluator、S5 iris 协议验证（RunCapsule/EA/人签 Claim）和控制面骨架；**没有真实研究实验 run/EA/Claim，也没有可宣称的 RSI 能力增益**。

## 2. “自己追踪 RSI”应该追什么

不是让 Agent 自己写一句“我变强了”，而是让系统留下可外部复核的 episode：

| 对象 | 内容 |
| --- | --- |
| `Observation` | 哪个 run/阶段失败、哪个指标不足、哪个 evidence 缺口 |
| `Candidate` | 只允许 skill / process / prompt / knowledge；不能改 claim/evidence/gate/rubric/export/signature |
| `DryRun` | 固定 fixture 上的静态/沙箱回执 |
| `PublicEval` | 开发可见验证集；记录 n、artifact_ref、指标 |
| `HiddenEval` | 冻结后执行；不回灌候选选择 |
| `Decision` | pending_human / approved / rejected / no_decision |
| `Lease` | scope、TTL、复评、撤销；不是永久升级 |
| `MetaReport` | 候选组合、lineage、active/revoked、负结果、下一问 |

`MetaTracker` 的职责是**追踪改进过程本身**：哪些候选被拒、为什么、是否有 hidden 证据、哪些 lease 还在、哪些下一轮问题没有回答。它不是“自我表扬器”。

## 3. 当前代码做到哪一步

`research_agent/rsi.py` 已实现：

- `Candidate` / `EvalEvidence` / `StepRecord` / `Lease` / `StepLedger`；
- `GovernancePolicy`：拒绝 claim/evidence/gate/rubric/export/signature/authorship；禁止空 patch/理由/预测；
- `RSIController.propose`：只写 `pending_human`，不自动准入；
- `admit`：要求 dry-run、public+hidden passed、人签理由、scope；通过后才发 active lease；
- `reject`：保留负结果；
- `revoke`：保留记录并标记依赖产物需复核；
- `MetaTracker`：episode 计数、pending/approved/rejected、active/expired/revoked lease、lineage、warnings、next questions，以及逐 episode 的 predicted/actual；
- `Lease.effective_status`：按 TTL 判定过期；expired lease 不参与执行或父代选择；不同预算的 active lease 冲突时 fail closed；
- `record_actuals`：把预测-实际写入 ledger，供后续周期审计；
- `CandidateArchive`：按 target/hidden 指标选父代，保留多样性；
- `EvalEvidence`：public / hidden / near_ood / regression 四类 split；fixture 证据带 `simulation: true`；
- `rsi_fixture.py`：public 按 cost 排序，最多两个 finalist 依次过 hidden/near_ood/regression；排序不看 hidden，未进入 finalist 的候选不接触 hidden；指标含 coverage_gaps，候选不得增加 gap；预算降低只由 cost 观测触发，coverage gap 不是降低预算的理由；同一 benchmark 的 target+patch+scope 已存在时跳过，不重复开 episode；
- `research_runner.py`：`active_literature_policy(expected_scope="S1/fixture")` 只解析未过期且 scope 匹配的 active lease；real probe 的 lease 不会跨 benchmark 生效；租约后研究批次实际使用该预算；已有 active 策略时不再重复开 episode；
- `rsi_fixture.run_confirmation_trial` / `rsi confirm`：租约后用独立 `tasks_confirm.json` 做 sealed 复核，`used_for_admission: false`，无 active lease 时返回 `no_active_lease`；
- `real_eval.py` + `RealCorpusRetriever` / `MiniLMRetriever`：四篇 CC-BY 4.0 RSI 论文正文（DGM/SICA/SIFT/ACE），逐篇 license/URL/SHA256 provenance；正文 BM25 为默认；可选本地 frozen MiniLM 做 abstract 级语义检索；compare 模式把 `bm25+budget2` 与 `minilm+budget3` 作为预注册候选集，由 public 排序 + hidden/near-OOD/regression gate 选择，候选仍需人预先列出；证据 `simulation=false`、`claim_eligible=false`；
- `MetaTracker` 对 simulated 或 harness-only episode 保持 `capability_claims=[]`，即使人签也不写能力增益；
- CLI：`python -m research_agent rsi propose|status|admit|reject|revoke`。

没有实现：真实研究实验执行（当前只有 iris 协议验证）、peer-review 固定 evaluator、两轮真实复评。**没有这些，不能说系统在 RSI。**

## 4. 五级路线

| 级别 | 目标 | 进入条件 | 当前 |
| --- | --- | --- | --- |
| R0 | 可运行研究纵切 + 规格 + SVG/稿件边界 | 模块/测试通过 | 已做（fixture） |
| R1 | 真实研究执行：检索/模型/run/EA/claim | 接 OpenAlex/模型/沙箱；固定实例与预算 | 部分：S5 iris 协议验证已通；真实研究实验未接 |
| R2 | 单阶段改进环（建议先 S5 或 S1） | 固定实例、public/hidden、dry-run、人签 | fixture + CC-BY probe；S1 选中 MiniLM+budget3；S5 iris→seeds3、breast_cancer→seeds2，均被 run 消费并 sealed 复核；pipeline 用 S5 lease 跑真实 run，claim draft 人签后才 bound_claim；ChemLab 受控 baseline（Ridge R²0.193 vs −0.048）→ 人签 claim → 数据图 bound_figure；protocol 冻结 + 数据图 + DataCite 元数据后 closure 11/11 ready，人签 export manifest（submission=false） |
| R3 | 元 RSI：候选组合、预测 vs 实际、迁移/成本 | 至少 2 个 R2 周期、独立 hidden | fixture 重复周期 + sealed confirm 已跑；真实迁移/成本未做 |
| R4 | 长时程：漂移/遗忘/撤销传播/预算调度 | 多任务、多阶段、稳定日志 | 未做 |

**顺序不能反**：先有真实执行与评测，再谈自动研究；先有单阶段改进，再谈元 RSI。否则只会优化 fixture 或 rubric。

## 5. “自己做 research” 的边界

可以逐步自动化：

- 任务队列、阶段调度、失败重试、预算/停止条件；
- 在固定任务上自动跑 S0–S16，产出草稿、图、证据包；当前已有 fixture 与 CC-BY 正文两种输入；
- 在 CC-BY 正文上跑真实 S1→paper 纵切，产出 2k+ 真实 span、示意 Fig 与 results-pending 稿约，仍不创建 Claim；
- 在固定的改进实验里自动提出候选、跑 dry-run/public；
- 自动生成下一轮**建议**，但 hidden 结果不参与选择，active 必须人签。

不能自动化：

- 自动改 claim/判据/门槛/署名；
- 自动投稿、自动冒充同行评审；
- 自动把 fixture 或一次 demo 写成能力增益；
- 无授权抓取中文库；
- 无 human sign 的永久技能升级。

## 6. 关键风险

| 风险 | 机制 |
| --- | --- |
| reward hacking / 过拟合 public | hidden 冻结、2×2、incumbent guard、负结果保留 |
| 评测泄漏 | hidden 不进入候选作者可见上下文；独立 evaluator |
| 自我改写失控 | policy 禁改 claim/gate/rubric/export；租约 + 撤销 |
| “越跑越大”被当成“越跑越强” | MetaTracker 看迁移、成本、保留与负结果，不看记忆条数 |
| 成本爆炸 | 固定预算、每 episode 成本、停止条件 |
| 证据污染 | 改进只作用于 skill/process；claim 仍只由 Evidence 创建 |

## 7. 下一步（按顺序）

1. **接一个真实 evaluator**：已接 S1 的 CC-BY 正文 probe（4 篇论文、12 个问题）；下一步换/扩到 peer-review 固定 corpus，或 S5 的 Docker + 固定 seeds。
2. **把 RSIController 接进 pipeline**：fixture runner 已消费 active lease；下一步让 pipeline 产出 observation 与 public/hidden receipt，没有 receipt 就停在 pending。
3. **实现 MetaTracker 的预测-实际表**：已完成逐 episode predicted/actual 与控制面汇总；下一步接真实 peer-review 数据做校准，不把 fixture/iris 数值当结论。
4. **做 2 个 R2 周期 + 1 个 hidden 复评**，再讨论 R3；fixture 与 CC-BY probe 已能跑重复周期和 sealed confirm，但问题仍是人工命题。
5. **只在这之后**写“RSI”相关论文主张；当前只能说“受治理的改进控制面已实现，evaluator 未接”。

## 8. 论文机制调研

免训练 RSI 的论文对照与 TF-RSI 算法见 [26](26-免训练RSI-论文机制调研与实现路线.md)：RRSI 的 regularized candidate proposal/selection、DGM 的 archive、SIFT 的 judge 预筛、GEPA/ACE/ReasoningBank 的反思/上下文/记忆，以及 fixed hidden/OOD/forgetting 的必要性。

## 9. 不能宣称

- 不宣称“系统会自己越跑越强”；
- 不宣称“已实现 RSI”；
- 不把 `pending_human` 写成“自动改进”；
- 不把 RSI-Anything/CycleResearcher 的效果数字搬过来；
- 不把候选生成当作能力提升。

> RSI 的真正难点不是“让模型改自己”，而是**让改动在固定实例上被独立证明、被保留、能迁移、可撤销，并且不污染证据链**。这份控制面是为此存在的，不是替代它。

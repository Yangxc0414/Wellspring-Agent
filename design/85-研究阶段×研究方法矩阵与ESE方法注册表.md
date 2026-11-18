# 85-研究阶段 × 研究方法：把导师的二维矩阵做成可执行的数据

> 状态基线：2026-11-18。承接 78（导师方法论矩阵的首次对照）、80（ESE 评测层）、81（ESE 内核）、83（记忆与自改进）。
> 本轮交付：`modules/method-registry/`（SPEC + `registry.json`）+ `research_agent/method_registry.py` + CLI `method` 组 + 18 例测试 + 本文。
> 边界：注册表是**数据/只读投影**，检查结果是 **advisory**，不接门禁、不改 claim/EA/signature。方法内容不替代精读原文。

---

## 0. 结论先行

导师给的不是"再补一门课"，而是一个**维度**：研究阶段（阶段）× 研究方法（方法）= 具体阶段性任务，任务在方法论约束下开展，每种方法都有指导性论文/书籍。

用系统语言翻译：

| 导师的话 | 系统里的东西 | 现状 |
| --- | --- | --- |
| 研究阶段 | S0–S16（`loop_ledger` 已有一等投影） | **有** |
| 研究方法 | 方法维度 | **没有**：所有研究共用一套通用设计清单 |
| 交叉 = 阶段性任务 | 任务卡（stage × method） | **本轮新增** |
| 方法论约束 | 指导文献 + 必填协议字段 + 报告章节 + 检查项 | **本轮新增** |

所以本轮做的事是：**把"方法"从散文/个人习惯，变成注册表里的数据、CLI 可查询的投影、以及可核对的检查项**。ESE 先行；数学/其它领域以后可各自挂注册表。

---

## 1. 为什么现有系统不够：四个"无方法差异"

1. **设计审计无方法差异**：`design_audit` 的清单（seeds/controls/effect size/power/…）对实验合适，对 SLR、案例研究、仓库挖掘几乎没有意义；反过来，SLR 的检索协议、案例的链式证据、挖掘的时间切分都不在清单里。
2. **预注册无方法差异**：`study_preregistration` 只有 question / hypothesis / analysis / decision_rule 四个判断字段；受控实验还需要随机化、区组、样本量与功效、停止规则；SLR 需要检索式与纳入排除；挖掘需要抽样框与时间切分。
3. **报告结构无方法差异**：手稿审计按固定章节与引用/数值检查，不区分"这是实验报告还是案例研究"；PRISMA 计数、链式证据、污染检查都不在审计项里。
4. **claim 不记录方法**：一条 claim 无法回答"它是用什么方法得到的"。这直接影响 scope 与失效条件——实验的失效条件是"因子/样本变化"，挖掘的失效条件是"时间窗/生态变化"，SLR 的失效条件是"检索日期/数据库变化"。

> 一句判断：之前的系统是**阶段驱动**的；导师要的是**阶段 × 方法驱动**。缺的不是流程，是方法维度的数据。

---

## 2. 设计：注册表（数据）→ 投影（矩阵/任务卡）→ 检查（advisory）

### 2.1 分层

```text
modules/method-registry/registry.json      ← 唯一数据源（9 方法 × 10 阶段）
        │  load + fail-closed validate
research_agent/method_registry.py          ← 纯函数投影，无 IO 副作用
        │
        ├─ matrix(stage)      阶段 × 方法：该阶段有哪些方法可用、各自任务
        ├─ task_card(stage, m) 合并视图：必填字段 / artifact / 检查 / 报告章节 / 文献 / cannot_support
        └─ check(m, payload)   advisory：逐检查项 pass/missing（不改门禁）
        │
CLI: python -m research_agent method list|show|matrix|card|check
```

### 2.2 为什么是"数据"而不是"代码"

AGENTS §3.0 的扩展优先原则：能数据化的不要硬编码。方法条目会随读文献不断修订（新增检查项、修订报告章节），把它写进 JSON 才能：

- 只改数据、不改代码、不跑全量测试；
- 人可以直接读/审/引用（每条都带 citation 与 "mandates"）；
- 未来别的领域（数学的证明方法、HCI 的访谈法）可以并列加注册表，而不是改内核。

### 2.3 为什么检查是 advisory

门禁（G2/S5b/closure）的语义变更必须人工确认（AGENTS §7）。所以本轮：

- `method check` 输出 `advisory_ok | advisory_missing`，列出缺失字段与严重度；
- **没有任何** pipeline / claim / closure 代码读取它；
- 接门禁的路径写在 §7 的"下一步"，需要一次单独的设计评审。

---

## 3. 注册表内容：9 个 ESE 方法

| id | 方法 | 阶段 | 必填协议字段（摘要） | 关键指导文献 |
| --- | --- | --- | --- | --- |
| `systematic-literature-review` | 系统文献综述 | S0/S1/S1b/S8-S12 | research_questions, search_strategy, databases, search_date, inclusion/exclusion, quality_assessment, synthesis | Kitchenham & Charters 2007；Wohlin 2014（滚雪球）；PRISMA 2020 |
| `repository-mining` | 仓库挖掘 | S1/S4/S5/S5b | sampling_frame, project_selection, time_window, time_split, dedup_policy, label_source, license_check | Kalliamvakou 2014；Bird 2009；Hassan 2009 |
| `controlled-experiment` | 受控实验 | S2-S3/S4/S5/S5b/S8-S12 | hypothesis, factors, levels, randomization, blocking, sample_size, power_analysis, analysis_plan, stopping_rule | Wohlin 2012；Kitchenham 2002；Jedlitschka 2008；Ralph 2020 |
| `quasi-experiment` | 准实验 | S4/S5/S5b | treatment, comparison_group, assignment_rule, confounders, identification_strategy, sensitivity_analysis | Shadish, Cook & Campbell 2002；Ralph 2020 |
| `benchmark-evaluation` | 基准评测 | S4/S5/S5b/S8-S12 | benchmark, benchmark_version, contamination_check, budget_matching, baselines, saturation_note | Sim 2003；Ralph 2020；Sainz 2023（污染） |
| `case-study` | 案例研究 | S0/S1/S4/S5/S8-S12 | research_questions, case_selection, data_sources, chain_of_evidence, triangulation, member_checking, ethics | Runeson & Höst 2009；Yin 2018；Ralph 2020 |
| `survey` | 问卷/访谈 | S0/S1/S5/S8-S12 | population, sampling_frame, sampling_method, instrument, pilot, response_rate_plan, consent | Kitchenham & Pfleeger 2008；Ralph 2020 |
| `design-science` | 设计科学 | S0/S2-S3/S4/S8-S12 | design_problem, requirements, artifact, evaluation_strategy, contribution_type, boundary_conditions | Hevner 2004；Wieringa 2014；Johannesson & Perjons 2014 |
| `action-research` | 行动研究 | S0/S4/S5/S8-S12 | intervention, stakeholders, cycles, reflection_record, researcher_role, ethics | Avison 1999；Ralph 2020 |

每条方法还固定带：

- `cannot_support`（结构性防止过度宣称，例如案例研究不能支持"统计泛化"）；
- `threat_focus`（该方法最该防的效度威胁）；
- `reporting_sections`（写作阶段的方法特定章节）；
- `stage_tasks`（每个适用阶段的**具体任务**——这是矩阵真正可执行的部分）。

> 文献条目是导航而非复述；引用版本需要在 Phase 1 精读时核对（见 §8 风险）。

---

## 4. 阶段 × 方法矩阵（可执行部分）

`method matrix --stage <S>` 的输出就是下表的一行。示例（S4 设计阶段）：

| 方法 | 该阶段在方法约束下的任务 |
| --- | --- |
| repository-mining | 时间切分必须先于建模；去重策略与标签来源写进预注册 |
| controlled-experiment | 预注册：随机化、区组、主指标、分析计划、停止规则；设计冻结后才执行 |
| quasi-experiment | 先写识别策略与识别假设，再选数据；混杂必须逐条列 |
| benchmark-evaluation | 先写污染检查与预算匹配；基线必须可复现 |
| case-study | 写数据收集与分析协议；伦理与匿名先于采集 |
| design-science | 评估策略（人工/案例/基准）先于实现 |
| action-research | 写循环计划与反思机制 |

这张表解决了原系统的一个具体问题：**S4 的"设计审计"不再对所有人问同一组问题**。案例研究被问"链式证据、伦理、三角"，实验被问"功效、随机化、停止规则"。

---

## 5. 使用方式（已实现）

```bash
# 1) 看有哪些方法
python -m research_agent method list

# 2) 看某个方法的定义（协议字段、检查项、报告章节、文献）
python -m research_agent method show controlled-experiment

# 3) 看某阶段的全部方法任务
python -m research_agent method matrix --stage S4

# 4) 取任务卡（stage + method）
python -m research_agent method card --stage S4 --method controlled-experiment

# 5) 用真实设计文件做 advisory 检查
python -m research_agent method check --method controlled-experiment \
  --design runtime_data/e2e-closed-loop/runs/RUN-E2E-02/experiment.json
```

第 5 步在真实产物上的输出（示例）：缺失 `power_analysis`、`randomization` 等会被逐条列出，并标 `status: advisory_missing`；**它不会阻断任何流程**。

---

## 6. 与现有资产的接线（已做 / 待做）

| 现有资产 | 现在 | 建议接线（需单独评审） |
| --- | --- | --- |
| `study_preregistration.py` | 4 个判断字段 + baseline | 增加只读 `method` 字段与 `method_fields`（不改变冻结/哈希语义） |
| `design_audit.py` | 通用清单 | 先并列输出 `method_check`，不替换原清单；人看两份 |
| `writing_audit` / 手稿章节 | 固定章节 | 从 `reporting_sections` 派生方法特定章节检查（warning） |
| `claim` | 不记方法 | 增加只读 `method` 字段，用于失效条件与 scope |
| `prototypes/ese/memory_graph.py` | 12 类节点 | 增加 `method` 节点/关系，让记忆能按方法检索（"这条失败是挖掘方法特有的"） |
| `rsi` recipe | 阶段配方 | recipe 增加 `method_scope`：方法级配方演化（design/83 §6） |
| demo / 图 | 阶段投影 | 新增"阶段 × 方法"投影图（roadmap） |

原则不变：**先只读扩展，再谈门禁**。

---

## 7. 下一步（按风险排序）

| 优先级 | 动作 | 风险 | 需要什么 |
| --- | --- | --- | --- |
| P1 | 在 `design_audit` 输出里并列 `method_check`（advisory） | 低 | 一个测试 + 一次人工确认 |
| P1 | 预注册增加只读 `method` 字段（不参与哈希/冻结判定） | 低-中 | SPEC 契约变更 + 测试 |
| P2 | 手稿审计按 `reporting_sections` 增加方法特定 warning | 中 | 章节映射表 + 回归 |
| P2 | claim 增加只读 `method` 与 `method_scope` | 中 | 涉及 claim 字段，必须人工确认 |
| P3 | 把 `method check` 的 blocker 接入 G2 前置检查 | **高** | 门禁变更 → 人工评审 + 预注册判据 |
| P3 | 按方法分层的 held-out 研究任务（design/83 M3） | 中 | 任务集与评分 |

---

## 8. 风险

| 风险 | 表现 | 防线 |
| --- | --- | --- |
| 方法条目膨胀 | 每个方法都想要 20 个检查项，最后没人看 | 每个方法 ≤6 条检查；blocker 只留最不可缺的 |
| 文献失真 | 引用版本/主张与原文不符 | 每条含 mandates 摘要；Phase 1 精读核对；不把注册表当原文 |
| 检查变成门禁 | "顺手"把 advisory 接成 blocker | 代码边界：本模块不写任何 gate 状态；接门禁须单独文档 |
| 方法错配 | 用实验的字段要求案例研究 | `applicable` + 每方法独立检查；矩阵只显示适用项 |
| 过度形式化 | 填字段完成 = 研究完成 | 字段只是必要条件；claim 仍需证据、区间、复现 |

---

## 9. 验收

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 注册表完整性/矩阵/任务卡/检查 | `python -m unittest tests.test_method_registry` | **18 项 OK** |
| 新增模块不影响派生物 | `python -m research_agent plugin export` + `workspace export` | 通过；`test_plugin_bundle` + `test_workspace` OK |
| CLI 只读 | `method list/show/matrix/card/check` | 输出 JSON；未知方法/阶段返回 2 |
| 真实设计检查 | 对 `runtime_data/e2e-closed-loop/.../experiment.json` 跑 `method check` | 报缺失字段，不阻断 |

---

## 10. 一句话总结

导师给的矩阵，落到系统里不是一份新文档，而是**方法维度的一等数据**：阶段决定"现在该做什么"，方法决定"这件事必须怎么写、必须报告什么、最该防什么威胁"。本轮把这条维度做成了注册表 + 任务卡 + advisory 检查；下一步才是把它接进设计审计与预注册——**先让方法被看见，再让方法被强制执行**。

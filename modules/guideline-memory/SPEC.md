---
id: guideline-memory
name: 记忆反馈（Guideline Memory）
stage: META
version: 0.3.1
status: draft
owner: research-agent
inputs: ["GuidelineProposal"]
outputs: ["GuidelineStore", "GuidelineBlock"]
tools: ["memory.guidelines"]
gates: []
invariants:
  - 纯确定性记账：产线只允许出现在宿主模型轮次里，本模块不调用模型、不训练、不参数化
  - 每条记忆必须引用项目内真实存在的产物路径，引用缺失或越界一律拒绝入库
  - 记忆是提示侧建议，不是能力：不得创建或修改 Claim、断言、门禁判定或导出数字
  - 同一课只计一次印证：token-Jaccard ≥ 0.5 视为重复，seen+1 而不是新增近似重复
  - 无人再印证的记忆会过期（STALE_STEPS），而不是永久留在提示里
  - 单步最多落地 3 条，总表上限 24 条，渲染块受字符预算约束
  - 记忆效果必须由 run 内对照判定：memory_ab 两臂只允许差一个 guideline 块，比较用运行时已在执行的确定性检查（引用落地到 ≥2 个不同来源、否证句非空、experiment_plan 通过 validate_plan）；配对数 <4 时只报 underpowered，不给方向
  - A/B 的度量必须有动态范围：已在输出路径上强制执行的门（引用落地、否证非空、计划过 validate_plan）对存活想法必然接近满分，不能用来分辨两臂；分辨力来自有变化空间的检查（来源广度、停止规则是否写明种子/配对/预算、风险是否点名）
---

# Guideline Memory — Purpose

把 TTME（`TTME-main/ttt/memory/guidelines.py`）里"执行反馈 → 外部记忆 → 影响后续生成"的**确定性记账**
移植进本项目：一个 run 的教训以 `trigger -> mechanism -> action` 一行形式存在 `<project>/memory/guidelines.json`，
按印证次数排序、过期淘汰、限量渲染成提示块。

# Contract

- `parse_entry(text)`：只接受三段式；分隔符切分，允许连字符与点（`from-idea`、`study-evidence.json` 必须可写）。
- `merge(entries, proposed, step, project)`：schema 门 → **产物引用门**（路径必须在项目内且存在）→
  去重印证 → 过期 → 按 `(seen, last_seen)` 排序截断；返回 `entries/accepted/rejected/expired`。
- `render_block(entries, step)`：字符预算内的提示块，每条带印证次数与来源产物。
- `load/save`：原子写，携带 `boundary`。

# Current Implementation

`research_agent/guideline_memory.py`。尚未接线：CLI `memory guidelines`、宿主模型轮次产线、
`writing pack`/`idea` 生成时的块注入都在下一步。

# Boundaries

不训练、不推理、不调模型；不写 Claim/EA/gate/signature；不参与 closure 判定。
记忆只影响"下一次怎么想/怎么写提示"，不影响任何已签署事实。

# Minimal Change Workflow

1. 改本文件或 `research_agent/guideline_memory.py`；
2. 升 version + Changelog；
3. 跑 `python -m unittest tests.test_guideline_memory`；
4. 若要接进生成路径，改的是消费方的 prompt 组装，不改本模块的判定语义。

# Changelog

- 2026-10-29 · v0.1.0 · status=draft · 初始实现：TTME 的确定性记账移植 + 本项目自有的产物引用门；9 项测试通过。

## Changelog

- 2026-11-11 · v0.4.0 · status=draft · M1/M2 收尾的会话模式（73- 号 §2.1）：memory-ab schema 升 0.2——`record()` 增 `session` 参数（session_id/host_label，存入 arms[arm].session）；`compare()` 增 `session_mode`（single/multi）：multi 强制两臂 host_label 互异（相同或缺失即 blocked，拒绝方向解读——同源偏差必须被排除而不是被忽略），single 附同源偏差边界文案（同会话 A/B 只证明流程不证明增益）；CLI `memory ab record --session-host-label/--session-id`、`memory ab compare --sessions single|multi`（默认 single 与升级前行为兼容，旧 ab.json 可读）。tests/test_memory_ab 增 SessionModeTest 8 项。输出契约 additive 增 session 字段，升 minor。
- 2026-10-30 · v0.3.1 · status=draft · 2026-10-30 · v0.3.1 · status=draft · 0.3.1（2026-10-30）：两臂真实试点跑通后先暴露了度量本身的错误。第一版 score_arm 只用三条运行时已在执行的门，实测两臂（topconf-research-2026，guidance_chars 215 vs 0，各 5 条想法）全部 1.0、delta 0.0、方向 no_difference——门在存活想法上 saturated，没有分辨力。新增三条有动态范围的检查：distinct_sources_mean、power_aware_stopping_rate（停止规则写明 seeds/配对/预算）、risk_noted_rate，配对符号改用 score_wide（保留 gates_only 作对照）。重跑得 power_aware_stopping_rate 1.0 vs 0.8、delta +0.2、方向 with_memory_better（1 优于、0 劣于、4 平），其余四项 delta 仍为 0。诚实边界写进产物与 compare.reading：两臂都由同一模型自答，这只能证明度量与流程有分辨力，不能当作记忆增益的效应量；n=5 且仅 1 对不一致，也不做任何统计声明。测试 7 项通过（含 CLI 全链）。
- 2026-10-30 · v0.3.0 · status=draft · 2026-10-30 · v0.3.0 · status=draft · 0.3.0（2026-10-30）：把 TTME 的对照卡思想做成可用工具，回答"记忆到底有没有用"。新增 research_agent/memory_ab.py（score_arm / compare / record / analysis）与 CLI memory ab plan|record|compare：两臂 ideas 按同一组确定性检查打分并做配对读出，delta、逐对符号计数、少于 4 对只报 underpowered。生成侧加开关 innovation review --no-guidance → run_innovation_review(use_guidance=False)，使两臂只差那一个块。真实产物试跑（topconf-research-2026 的 3 条被选想法 + writing pack 的 16 张 REF 卡）：grounded_rate=1.0、falsifiable_rate=1.0、executable_plan_rate=0.0——即那份评审选出的想法按今天的档位契约全都不可执行，这是本工具自己量出来的真实缺陷，不是示例数字；只记一臂时 compare 正确返回 incomplete 并给出下一步。测试 7 项（含 CLI 子进程走 plan/record/compare 全链）。修掉一处自己写下的格式化 bug（then 里两个 %s 只喂了一个参数，由 CLI 试跑暴露）。边界：这只能说两臂在运行时自有检查上的差别，不能声称记忆导致了发现。
- 2026-10-30 · v0.2.0 · status=draft · 2026-10-29 · v0.2.0 · status=draft · 接线完成：block_for(project) 注入 innovation_review._propose 的生成提示（run_innovation_review 从项目记忆取块），新增 CLI memory guidelines --project P [--propose-file JSON --step N]（读/合并/落盘）。实测：在 runtime_data/topconf-research-2026 记入一条引用真实产物的教训后，host-model turns --prompt 输出 26430 字符中包含标题"本 run 已确认的做法"与课文文本 study from-idea --datasets all，即记忆真的到达宿主模型待答提示；随后以 host-model respond 回答 MT-bd0cf160ae57，账本 counts 由 pending=1 变为 responded=1。新增 2 项消费侧测试（11 项通过）。边界不变：提示侧建议，不能触达 Claim/断言/门禁/导出数字。

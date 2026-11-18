# 92-durable 失败图谱与能力指标的第一条读数

> 状态基线：2026-11-18。承接 83（记忆与自改进）、90（能力指标空态）、91（演示主线）。
> 本轮交付：`research_agent/failures/atlas.json`（6 条真实 durable 失败）+ 记忆图摄入 + 测试 + demo 能力指标更新。
> 边界：失败条目全部来自本会话真实踩坑（有证据路径）；不含推测、不含 operational 失败。

---

## 1. 为什么先做失败图谱

设计 83 的 M3 把"能力指标"卡在两个前置物上：**durable 失败节点**与 **held-out 研究任务**。没有前者，"失败复用率"永远是 0/0；没有后者，"改进"不可测。

本轮先做前者，因为它在真实使用中已经积累够了：

| 失败 id | 类型 | 现象（真实） | 证据 |
| --- | --- | --- | --- |
| FA-20261118-01 | design_flaw | S1b 综合只认 `DEEPSEEK_API_KEY`，配了网关也失败 | design/87 §2、`test_literature_synthesis` |
| FA-20261118-02 | design_flaw | 写作模型失败时静默回退 deterministic，产物无痕迹 | design/86 §3 F5、`test_pipeline` |
| FA-20261118-03 | design_flaw | 模型设计的 `primary_metric` 是句子、`budget` 无可测口径，`design.required` 仍 pass | design/86 §2.3 |
| FA-20261118-04 | design_flaw | 词法预审把 "rankings/gaps" 判成无指标 | design/86 §3 F4、`test_idea_review` |
| FA-20261118-05 | design_flaw | 演示页幕数写死 6，扩展成 7 幕后 JS 仍显示 "X / 06" | design/91 §1、`site/innovation/app.js` |
| FA-20261118-06 | design_flaw | 裸 profile id 被静默忽略，回退规则模板且退出码 0 | design/86 §3 F1、`test_model_profile_resolution` |

每条的 `retry_condition` 都写成**可检查的复现条件**（例如"grep 显示没有新阶段直接读 provider env"），而不是"以后注意"。

---

## 2. 代码改动

1. **数据**：`research_agent/failures/atlas.json`（`failure-atlas-0.1`），字段：failure_id / kind / scope / observed / diagnosis / retry_condition / evidence / recorded_at。加载时 fail-closed：schema 不符、缺字段、重复 id、evidence 非列表都拒绝。
2. **摄入**：`prototypes/ese/memory_graph.py` 新增 `load_failure_atlas` / `ingest_failure_atlas`，并让 `ingest_project(..., failure_atlas=...)` 合并节点；准入沿用同一规则——**durable 进图谱，operational 拒绝**。
3. **扫描器**：`scripts/research_memory_scan.py` 自动发现 `research_agent/failures/atlas.json`（或 `--failures` 指定），输出新增 `failure_atlas` 字段。
4. **测试**：`tests/test_memory_graph` 新增 5 例（durable 准入 / operational 拒绝 / 仓库 atlas 可加载 / schema 与缺字段拒绝 / 项目摄入后 pack 的 failures 非空）。

---

## 3. 第一条读数（真实）

```bash
python scripts/research_memory_scan.py --project runtime_data/e2e-closed-loop
```

```text
artifacts: 10 | nodes: 23 | edges: 3
failure atlas: research_agent/failures/atlas.json
  failure/admitted: 6
pack[idea]:       4390/8000 chars | failures:6 ...
pack[experiment]: 4061/8000 chars | failures:6 ...
pack[paper]:      4061/8000 chars | failures:6 ...
```

读法（不夸大）：

- **已测**：图谱有 6 条 durable 失败；三个阶段的 pack 都带 failures 节（永不裁剪）。
- **未测**："失败复用率"——因为 **pipeline 还没有在设计前读取记忆包**。pack 存在 ≠ 被消费；这正是设计 83 的 M3-3 要测的。
- **仍未测**：held-out 改进、claim 存活率、human-minutes。

---

## 4. demo 的更新

能力指标表（90）里"失败复用率"一行从"未测、无节点"改为：

> 图谱已有 6 条 durable 失败（真实踩坑）；记忆包已能带出失败节；**复用率仍未测**——管线尚未在设计前消费记忆包。

「两条循环」的"缺"行同步改为：失败图谱已有节点，但管线尚未读取；「已有」行把 17 节点更新为 **23 节点 / 6 条失败**。

---

## 5. 下一步（M3 剩余）

| 步骤 | 动作 | 验收 |
| --- | --- | --- |
| M3-1 ✅ | durable 失败节点 | 6 条、可被 pack 读取、不被裁剪 |
| M3-2 | 3 个 held-out 研究任务（idea / experiment / paper） | 有金标准评分、未参与设计 |
| M3-3 | 把 pack 接进 S2/S4 输入（只读注入，不改门禁） | pipeline 跑一次后，idea/experiment 产物记录"读取了哪几条失败" |
| M3-4 | 统计失败复用率与 held-out 改进 | 区间 + 功效；不足则如实报 underpowered |

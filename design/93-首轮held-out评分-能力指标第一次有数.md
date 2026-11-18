# 93-首轮 held-out 评分：能力指标第一次有数（12/14）

> 状态基线：2026-11-18。承接 90（能力指标空态）、92（durable 失败图谱）。
> 本轮交付：`research_agent/eval/heldout_tasks.json`（冻结任务卡 + rubric）+ `research_agent/heldout_eval.py` + `scripts/heldout_eval.py` + 6 例测试；并对一张**先冻结、后执行**的任务卡给出首轮读数。
> 边界：rubric 是确定性的"符合性检查"，不是科学质量评分；n=1 不构成方向性结论。

---

## 1. 做了什么

1. **冻结任务卡**：`HO-20261118-A`（topic: *Evidence-bound evaluation of LLM coding agents on repository-level tasks*），三条轴共用一张卡，rubric 在跑之前写死。
2. **确定性 rubric（14 项检查）**：
   - idea（4）：候选数 ≥3、每条候选至少 1 个 evidence_ref 能解析到同 run 的 span、每条有 falsification、lens ≥2；
   - experiment（6）：五个字段非空、metric 是指标标识而非句子、budget 含可测数字、controls ≥2、seeds ≥3、stopping rule 非空；
   - paper（4）：八节齐全、每节非空、Results 保持 pending、≥4 个不同证据 span 引用。
3. **执行器**：`scripts/heldout_eval.py --run-dir <run>`，输出 Markdown/JSON；缺失产物记为 `not_run`（**不得算 pass**）。
4. **先冻结、后执行**：rubric 写完后才跑 `pipeline run`（同一 AutoDL DeepSeek-V4.1-Flash 供给），产出目录 `runtime_data/heldout-20261118-a`。

---

## 2. 首轮读数（真实）

```text
Held-out evaluation: HO-20261118-A
score: 12/14

idea (4/4)         candidates 3 · grounded 3/3 · falsifiable · lenses>=2
experiment (4/6)   fields/controls/seeds/stopping pass
                   FAIL metric_shape: "Repository-level task success rate, measured by test-based c…"
                   FAIL budget: "Reuse existing repository-level benchmark runs and open-weig…"
paper (4/4)        8 sections · non-empty · Results pending_evidence · 31 distinct span citations
```

读法：

- **idea 轴全过**：候选确实从同 run 的证据出发，否证条件与 lens 都在。
- **experiment 轴是短板**：与 design/86 的观察一致——模型把 `primary_metric` 写成一句话、`budget` 写成"复用现有 benchmark"；结构字段齐全，但 S5 无法直接执行。这不是 rubric 过严，而是真实缺陷。
- **paper 轴全过**：写作仍然守住边界（Results 保持 pending、引用可解析到 span）。

---

## 3. 为什么这算"能力指标第一次有数"

- 之前的"能力指标"全部是空态（design/90）；现在至少有一项**预注册、可复跑、带分母**的读数；
- 它不是"模型自评分数"，而是对产物的确定性检查，任何人可用同一命令复现；
- 它同时暴露了改进方向（experiment 轴），可以用来比较下一次配方改动——这正是 design/83 M3-3 需要的"评估任务"。

**不能说的事**：n=1，不能说明流程变好或变坏；rubric 只测符合性，不测科学价值；所有数字仍来自单次 run。

---

## 4. 验收

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 评估器测试 | `python -m unittest tests.test_heldout_eval` | 6 项 OK（含缺失产物 not_run、句子 metric 失败、Results 非 pending 失败） |
| 首轮评分 | `python scripts/heldout_eval.py --run-dir runtime_data/heldout-20261118-a` | 12/14，报告写入 run 目录 |
| 站点 | `build-site` / `check-site` | ok；demo 能力指标表更新为"首轮 12/14（n=1）" |
| 发布 | `build_release --check` | drift 0 |

---

## 5. 下一步

1. **补多张任务卡**（≥3 张，不同主题），否则无法区分"配方改动有效"与"这张卡恰好简单"；
2. **配方对照**：同一 rubric 下跑 baseline vs +memory pack（M3-3），区间跨零就如实报 underpowered；
3. **把 pack 接进 S2/S4 输入**：让"读取了哪几条 durable 失败"进入产物，才能统计失败复用率；
4. **experiment 轴的修复**：把 metric/budget 形状从 warning 升级为 G2 前置检查需要人工确认（门禁变更）。

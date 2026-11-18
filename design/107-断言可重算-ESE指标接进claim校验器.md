# 107-断言可重算：ESE 指标接进 claim 校验器

> 状态基线：2026-11-18。承接 106（探索性结果接进 S5 制品族）。
> 本轮补上 106 留下的第一件事：让 `run claim` 的数值断言能在 ESE 胶囊上**被重算**，而不是只能写 legacy 断言。
> 边界：只验证"断言可重算"；签名仍是人签步骤，本轮没有代签。

---

## 1. 做法（不改 run 模块）

claim 校验器 `verify_claim_assertions` 的规则很简单：给定 metric 名，先看是否等于 capsule.metric_name 或 "mean"；否则在 metrics.json 的每条记录里找同名字段取均值。

所以本轮只改**发射的制品形状**：

- capsule.metric_name 从 "test co-change rate" 改为标识符 **test_cochange_rate**；
- metrics.json 的每仓库行用 repo_rate（不与 claim 指标重名）；
- 末尾追加一行 pooled 行，带 claim 级指标：
  - test_cochange_rate = 0.3749
  - bugfix_difference = 0.046
  - adjusted_difference = 0.0681
  - time_split_difference = 0.132
- capsule.metrics_by_seed 也带 test_cochange_rate 与 adjusted_difference。

这样 `_metric_value` 对 test_cochange_rate 只会命中 pooled 行（per-repo 行没有同名字段），不会把三个仓库的率误平均。

---

## 2. 真实重算结果

```text
assertion 1: metric=test_cochange_rate value=0.3749 ==  -> observed 0.3749  pass
assertion 2: metric=adjusted_difference value=0.0681 ==  -> observed 0.0681  pass
wrong value 0.99                                        -> fail（正确失败）
run-contract check: status=attention, blockers=[], warning=[min_delta not verifiable, no paired baseline]
```

也就是说：**人现在可以用结构化断言签这条 ESE 结论，系统能独立重算数值**，而不只是相信一段 prose。

---

## 3. 人签命令（由人执行，不由 agent 执行）

```bash
python -m research_agent run claim \
  --capsule runtime_data/ese-ms-20261118-03/run/run-capsule.json \
  --ea runtime_data/ese-ms-20261118-03/run/ea.json \
  --statement "In three Python OSS projects, 37.5% of source-touching commits also touch tests (95% CI 36.2-38.8); bug-fix commits +4.6pp, MH-adjusted +6.8pp, heterogeneous by project." \
  --assertion "metric=test_cochange_rate,value=0.3749,comparator=>=,tolerance=0.001" \
  --assertion "metric=adjusted_difference,value=0.0681,comparator=>=,tolerance=0.001" \
  --scope S5/ESE-MS-20261118-03 \
  --human-reason "checked protocol, repos and labels; scope limited to three Python projects"
```

说明：断言解析器只按第一个 = 切分，所以等值断言写成 \`comparator==\`（三段 = 号）时会得到 ==；上面用 >= 表达"至少达到"的弱断言，避免等价字符串的歧义。

## 4. 仍未完成

1. min_delta 警告：没有配对 baseline（配对研究才有 Δ）；这不是本轮要消除的，是要保留的诚实警告；
2. closure/lineage 尚未消费 ESE 胶囊（闭包检查、变更传播还只认 ML run）；
3. `analysis.stratification` 还没进 method-registry 字段，协议检查查不到它。

---

## 5. 验收

| 项 | 结果 |
| --- | --- |
| 断言重算 | test_cochange_rate 0.3749 pass；adjusted_difference 0.0681 pass；错值 fail |
| 契约校验 | 0 blockers；1 条应保留警告（no paired baseline） |
| 执行器测试 | tests.test_ese_exec 6 项 OK（新增断言 pass/fail 两例） |
| 规格 | modules/ese-exec/SPEC.md 0.4.1 |

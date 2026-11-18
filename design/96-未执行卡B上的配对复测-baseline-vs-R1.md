# 96-未执行卡 B 上的配对复测：baseline 12 vs R1 13.3（n=3，underpowered）

> 状态基线：2026-11-18。承接 95（A 卡四臂）与 93/94。
> 本轮第一次在**未执行过的冻结卡**（HO-20261118-B）上比较 baseline 与 R1 硬化记忆包，每臂 3 次。
> 边界：n=3 < MIN_PAIRS=4，underpowered；只报原始配对差，不下方向结论。

---

## 1. 设置

| 项 | 值 |
| --- | --- |
| 任务卡 | `HO-20261118-B`（"Does typed memory of past failures change experiment design quality for LLM agents?"，冻结于执行前，此前从未执行） |
| 臂 | baseline（无记忆） vs R1（硬化记忆包 `memory-pack-idea-hardened.json`，sha256 记录在每次 run 的 `demo.json`） |
| 重复 | 每臂 3 次（独立 run，同供给、同 topic、同参数） |
| 写作 | `--writer off`（paper 轴保持确定性草稿，减少调用成本；paper 轴分数仍计入 rubric） |
| 评分 | 同一冻结 rubric（14 项），`scripts/heldout_eval.py` |
| 汇总 | 新脚本 `scripts/ablation_summary.py`（配对差、均值、underpowered 守卫） |

命令：

```bash
python scripts/ablation_summary.py --task-id HO-20261118-B \
  --arm baseline=runtime_data/ho-b-base-1,runtime_data/ho-b-base-2,runtime_data/ho-b-base-3 \
  --arm r1=runtime_data/ho-b-r1-1,runtime_data/ho-b-r1-2,runtime_data/ho-b-r1-3
```

---

## 2. 结果（真实）

```text
baseline: n=3 scores=[12, 12, 12] mean=12.0   (idea 4.0 / experiment 4.0 / paper 4.0)
r1:       n=3 scores=[14, 13, 13] mean=13.333 (idea 4.0 / experiment 5.333 / paper 4.0)

paired baseline -> r1: diffs=[2, 1, 1] mean=1.333 n=3 underpowered=True
```

读法：

- **idea 与 paper 轴已到 ceiling**（4/4 两边都是），在当前 rubric 下无法再区分；差异全部落在 **experiment 轴**（4.0 → 5.33）。
- R1 的三次里有两次仍差一项（13/14），说明硬化约束不是每次都生效；**模型采样随机性**是真实存在的，这正是需要 k 次重复的原因。
- baseline 三次完全一致（12/12/12），说明在这个任务上 baseline 的失败模式很稳定（metric 句子 + budget prose）。

---

## 3. 能说与不能说

**能说**：

1. 在**未执行过的卡**上，R1 的配对差为正（[2,1,1]），且三次均非负；
2. 失败集中在 experiment 轴，与 A 卡的观察一致——方法（硬化约束）确实作用在预期位置；
3. 评分流程与 provenance（每次 run 的 `memory_pack` sha256）可复跑、可归因。

**不能说**：

1. **n=3 < 4，underpowered**：不能报"方向"或"提升幅度"；区间/显著性都还谈不上；
2. idea/paper 轴 ceiling 意味着当前 rubric 对这两轴已饱和，需要更难的任务卡或更细的检查项，而不是"两边都满分就说明好"；
3. rubric 仍是符合性检查，不是科学价值评分。

---

## 4. 补到 n=4：越过 underpowered 守卫（仍不是统计结论）

同日补跑每臂第 4 次（同设置、同供给、同 topic）：

    baseline: n=4 scores=[12,12,12,12] mean=12.0   (experiment 4.0)
    r1:       n=4 scores=[14,13,13,13] mean=13.25  (experiment 5.25)
    paired baseline -> r1: diffs=[2,1,1,1] mean=+1.25 n=4 underpowered=False

读法（严格）：

- 越过**预注册的 underpowered 守卫**（n>=4），四对差全部非负，均值 +1.25；
- 若只做符号检验（4/4 为正），单侧 p=0.0625、双侧 0.125——**不能宣称显著**，也没有算区间；
- 差异仍全部在 experiment 轴；idea/paper 在 rubric 下已 ceiling；
- rubric 是符合性检查，不是研究质量；这条结论只能说"硬化记忆包让草稿更常满足 experiment 的形状要求"，不能说"R1 提升了研究能力"。

## 5. 下一步

| 步骤 | 动作 |
| --- | --- |
| 1 | 每臂补到 k≥4（最好 6），并在卡 C（中文/paper 轴）上重复；writing 打开以覆盖 paper 轴 |
| 2 | 提升 rubric 难度：idea 轴加入"与 prior art 的差异是否可检验"，paper 轴加入"引用覆盖/数值可追溯"的更强检查 |
| 3 | 若 R1 在 B/C 上都稳定优于 baseline，才把 R1 作为默认配方候选提交人签（门禁不变，仅改 pipeline 默认注入） |

---

## 5. 验收

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 6 次独立 run | `pipeline run … --writer off [--memory-pack …]` | 全部完成，退出码 0 |
| 评分汇总 | `scripts/ablation_summary.py` | baseline 12/12/12；R1 14/13/13；paired mean +1.333；underpowered=True |
| 仓库 | release `content_drift: 0`；`repo_hygiene` 0 blocker（本轮结束时复核） |

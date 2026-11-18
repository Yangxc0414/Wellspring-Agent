# 94-记忆注入的首次配对实验：baseline vs +memory pack（12/14 vs 12/14）

> 状态基线：2026-11-18。承接 92（失败图谱）、93（首轮 held-out 评分）。
> 本轮把"pack 接进 S2/S4 输入"从 roadmap 变成可执行机制，并做了第一次**配对**对照。
> 边界：n=1 任务、每臂 1 次运行，属 underpowered；不下方向性结论。

---

## 1. 机制：只读注入，不改门禁

`pipeline run --memory-pack <pack.json|md>`：

- 从记忆包中取 **failures 节**（永不裁剪），截断到 8000 字符；
- 以 `memory_of_past_failures` 字段加入 S2 idea 与 S4 experiment 的模型 payload（adapter 原样 JSON 发送，模型可见）；
- 运行结果与 `demo.json` 记录 `memory_pack: {path, sha256, chars}`——**这次 run 读过哪份记忆**可追溯；
- 不写回、不改任何门禁/Claim；没有 pack 时行为与之前逐字节一致。

测试：`tests/test_memory_pack_injection.py` 6 例（取 failures 不取 claims、md 直读、缺文件/空失败节报错、wrapper 不改调用方 payload、原 payload 保留）。

---

## 2. 首次配对实验

| 项 | 值 |
| --- | --- |
| 任务卡 | `HO-20261118-A`（冻结于执行前） |
| topic | Evidence-bound evaluation of LLM coding agents on repository-level tasks |
| 供给 | AutoDL DeepSeek-V4.1-Flash-1017（idea/experiment/writer/planner/judge 同 profile） |
| 记忆包 | `runtime_data/e2e-closed-loop/memory/memory-pack-idea.json`（sha256 `22e3e74b…`，1821 字符，6 条 durable 失败） |
| baseline | `runtime_data/heldout-20261118-a` |
| +memory | `runtime_data/heldout-20261118-a-mem` |

| 轴 | baseline | +memory |
| --- | --- | --- |
| idea | 4/4 | 4/4 |
| experiment | 4/6（metric_shape、budget 失败） | 4/6（同样两项失败） |
| paper | 4/4 | 4/4 |
| **总分** | **12/14** | **12/14** |

产物差异（不是评分差异）：

- baseline metric："Repository-level task success rate, measured by test-based c…"
- +memory metric："Paired difference in repository-level task success rate, bas…"
- +memory budget："Pilot-calibrated and capped per arm; track API tokens, wall-…"

即：模型**读到了**失败记忆（措辞明显变化），但仍把 metric 写成句子、budget 写成说明性文字——rubric 两项目标没有被满足。

---

## 3. 诚实读法

1. **无差异，且 underpowered**：n=1 任务、每臂 1 次，模型还有采样随机性；既不能说"记忆有效"，也不能说"记忆无效"。
2. **失败模式很具体**：记忆里明明有 FA-20261118-03（"metric 是句子、budget 不可测"），模型仍复现它。说明"把失败列表塞进 prompt"不等于"模型会遵守"——需要更强的约束（检查清单/结构化模板/形状校验回环）。
3. **这正是自改进该做的事**：候选配方 = 在 pack 里附"metric 必须是 identifier、budget 必须含数字"的硬性 checklist，或加一次"形状校验失败则重写"的修复回路；然后**同一 rubric** 下再配对比较。
4. **不能拿"措辞更好"当改进**：评分只看可执行性；写得更像论文但 metric 仍不可用，就是没改善。

---

## 4. 下一步（配方候选，不是结论）

| 候选 | 改动 | 预期 rubric 影响 |
| --- | --- | --- |
| R1 | memory pack 增加 hardening checklist（metric identifier / budget 可测 / 引用必须是 span id） | 直接针对 experiment 两项目标 |
| R2 | 设计阶段加一次形状修复回路（检查失败→带错误重写一次） | 同上，成本 +1 次调用 |
| R3 | 每臂重复 k≥3 次、3 张任务卡（B/C 已冻结未执行） | 从 underpowered 走向可判定 |

---

## 5. 验收

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 注入测试 | `python -m unittest tests.test_memory_pack_injection` | 6 项 OK |
| 评估器 + pipeline 回归 | 同上 + `test_heldout_eval` + `test_pipeline` | 44 项 OK |
| 两臂运行 | `pipeline run … --memory-pack …` | 均成功，`memory_pack` provenance 写入 demo.json |
| 两臂评分 | `scripts/heldout_eval.py --run-dir …` | 12/14 vs 12/14；报告写入各自 run 目录 |

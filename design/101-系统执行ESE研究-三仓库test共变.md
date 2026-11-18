# 101-系统真的执行了一条 ESE 研究：三仓库 test co-change 研究（真实结果）

> 状态基线：2026-11-18。承接 99/100（ESE 模式与方法检查），本轮补上"执行"。
> 结果来自 3 个真实公开 Python 仓库（click / requests / httpx）的 git 历史，由 `research_agent/ese_exec.py` 从冻结协议执行。
> 边界：探索性 repository-mining；标签是路径/提交消息启发式；**没有 Claim/EA/签名**，不是可签署结论。

---

## 1. 从"能设计"到"能执行"缺了什么

之前流水线能：S1 接 SE 语料 → S2 生成候选 → S4 给出设计 + 方法协议缺口。
缺的是把协议**真的跑在数据上**。本轮新增：

- `research_agent/ese_exec.py`：协议驱动的 repository-mining 执行器（提取 → 标签 → Wilson 区间 → 置换检验 → 结果制品）；
- `scripts/run_ese_study.py`：一条命令跑协议；
- `modules/ese-exec/SPEC.md`：新模块合同（只读、无 Claim、无门禁）；
- 冻结协议：`research_agent/eval/ese_protocols/msr-cochange-v2.json`（`ESE-MS-20261118-02`）。

协议已通过 method registry 的 repository-mining 检查：**advisory_ok（8/8 字段齐全）**——sampling_frame / project_selection / time_window / time_split / dedup_policy / label_source / license_check / extraction_script。

---

## 2. 数据与协议

| 项 | 值 |
| --- | --- |
| 仓库 | click（BSD-3，3416 commits）、requests（Apache-2.0，6496）、httpx（BSD-3，1527） |
| 单位 | 触碰至少一个 `.py` 文件的提交（合并提交排除） |
| 时间窗 | 2000-01-01 至 2026-11-18 |
| outcome | 同提交还触碰 `tests/`、`test_*.py`、`*_test.py` |
| bug-fix 标签 | 提交标题匹配 fix/bug/issue/regression/hotfix/patch |
| 统计 | Wilson 95% 区间；两侧置换检验 1000 次，seed=42 |
| 时间切分 | 每仓库按提交日期中位数分早/晚两半 |

---

## 3. 结果（真实，可复跑）

| 仓库 | 源码提交 | 同时改测试 | 比率 | 95% CI |
| --- | --- | --- | --- | --- |
| click | 1328 | 588 | 0.443 | [0.416, 0.470] |
| requests | 2824 | 760 | 0.269 | [0.253, 0.286] |
| httpx | 980 | 576 | 0.588 | [0.557, 0.618] |

**合并：1924/5132 = 37.5%，95% CI [36.2%, 38.8%]。**

回答三个预注册问题：

- **RQ1**：约 **37.5%** 的源码提交会在同一提交里同时改测试（区间窄，样本 5132）。
- **RQ2**：bug-fix 提交 **41.4%**（352/851）vs 其他 **36.7%**（1572/4281），差 **+4.6pp**，置换检验 p=0.015（n=1000）。
- **RQ3**：早期一半 **30.9%**（795/2572）vs 晚期一半 **44.1%**（1129/2560），差 **+13.2pp**，p=0.001——这三个仓库的测试共变率随历史显著上升。

解释必须克制：这是**描述性、探索性**结果；时间上升可能来自流程成熟、CI 普及、提交粒度变化等混杂因素，不能当因果。

---

## 4. 这算不算"系统执行了 ESE 研究"

算**执行**，不算**结论**：

- 是：真实 SE 数据（三个 OSS 仓库的完整 git 历史）、预注册协议、方法规范检查通过、确定性统计与可复跑命令、结果制品；
- 不是：没有 S5 RunCapsule/EA、没有 G2/S5b 人签、没有独立复现；标签启发式会误分类（例如把 "issue" 普通用词判成 bug-fix）；三仓库是目的性抽样，不能外推。

下一步若要变成可签署结论：把该协议登记为 S4 设计 → 人签 G2 → 以本执行器作为 S5 执行面（或接入 `experiment` 链）→ 生成结果胶囊 → 人签 S5b Claim → closure/lineage。目前系统已具备"协议→执行→结果"的前半段。

---

## 5. 验收

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 执行器测试 | `python -m unittest tests.test_ese_exec` | 5 项 OK（提取/过滤、区间、置换、协议校验、结果文件） |
| 协议检查 | method registry repository-mining | **advisory_ok（8/8）** |
| 真实执行 | `python scripts/run_ese_study.py --protocol …v2.json` | 3 仓库、5132 提交、结果写入 `runtime_data/ese-ms-20261118-02` |
| 复跑 | 同命令 | 数字可复现（固定 seed） |

**一句话**：现在可以说"我们的科研智能体系统执行了一条 repository-mining ESE 研究，得到 37.5% 的 test co-change 率（95% CI 36.2–38.8），并观察到时间上升与 bug-fix 差异"——但只能以探索性证据的口吻说。

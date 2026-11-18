# 98-第一条真实 ESE 研究：证据门控研究智能体的 durable 缺陷案例研究

> 状态基线：2026-11-18。承接 97（定位澄清：此前测的是智能体产出，不是 ESE 现象）。
> 本轮交付第一条**以软件工程制品为对象**的实证研究：对 `research_agent/failures/atlas.json` 中 6 条 durable 缺陷做案例研究（case study），编码其检测机制与修复方式。
> 边界：单项目、单作者、目的性抽样 n=6；只做描述性统计，不做总体推断；无人类受试者。

---

## 1. 研究问题

- **RQ1**：在证据门控的研究智能体里，会出现哪些类别的 durable 缺陷？
- **RQ2**：每个缺陷是被什么机制发现的？
- **RQ3**：修复形态是什么（改代码/加测试/改文档），是否补了回归测试？

---

## 2. 方法：按 method registry 的 case-study 任务卡执行

`python -m research_agent method card --stage S4 --method case-study` 要求：`research_questions / case_selection / data_sources / chain_of_evidence / triangulation / member_checking / analysis_strategy / ethics`。逐项落实：

| 字段 | 本研究 |
| --- | --- |
| research_questions | 见 §1（RQ1–RQ3） |
| case_selection | `research_agent/failures/atlas.json` 在 2026-11-18 记录的全部 6 条 durable 失败；operational 失败按定义排除 |
| data_sources | atlas 本身、design/86、design/87、design/91、`tests/` 中的回归测试 |
| chain_of_evidence | 每条 failure id → atlas 的 evidence 路径 → 设计记录 → 对应测试/手工检查 |
| triangulation | atlas 记录 + 设计文档 + 代码/测试三处对齐 |
| member_checking | **未做**（单作者）；作为威胁列出 |
| analysis_strategy | 目的性编码（检测机制 / 修复类型 / 是否补测试），描述性计数 |
| ethics | 仅内部工程制品；无人类受试者、无个人数据 |

编码本：`research_agent/eval/case_study_codings.json`（`case-study-codings-0.1`）。编码类别在跑之前固定：

- detection_mechanism ∈ {real_model_run, heldout_rubric, browser_check, contract_test}
- fix_type ∈ {code, code_and_test, config, docs}
- regression_test ∈ {yes, no}

报告脚本：`scripts/case_study_report.py`（只读、可复跑；校验每条 atlas 失败都有且只有一条编码）。

---

## 3. 结果（n=6，描述性）

| id | 阶段 | 检测机制 | 修复 | 回归测试 |
| --- | --- | --- | --- | --- |
| FA-20261118-01 | S1b | real_model_run | code_and_test | yes |
| FA-20261118-02 | S8 | real_model_run | code_and_test | yes |
| FA-20261118-03 | S4 | heldout_rubric | code_and_test | yes |
| FA-20261118-04 | S2-S3 | real_model_run | code_and_test | yes |
| FA-20261118-05 | demo-UI | browser_check | code | **no** |
| FA-20261118-06 | CLI | real_model_run | code_and_test | yes |

聚合：

```text
RQ2 detection:  real_model_run 4 · heldout_rubric 1 · browser_check 1 · contract_test 0
RQ3 fix_type:   code_and_test 5 · code 1
RQ3 regression: yes 5/6 (0.833)
RQ1 kind:       6/6 design_flaw（atlas 只收 durable；operational 被定义排除）
```

---

## 4. 讨论（只基于这 6 个案例）

1. **真实模型运行是主要 oracle（4/6）**：四个缺陷只有在真实调用/真实产物里才暴露（网关断点、静默回退、词法误判、裸 profile id）。契约测试与单元测试没有先发现它们。
2. **rubric 能抓到一类（1/6）**：S4 设计字段"结构齐全但不可执行"是由 held-out rubric 抓到的，说明冻结的评估 rubric 有独立价值。
3. **浏览器渲染检查抓到 1 个**：派生数字写死的问题，单元测试看不到，只有真实渲染暴露。
4. **修复几乎都伴随回归测试（5/6）**：唯一没补测试的是 demo UI 的计数 bug——这类"渲染层"缺陷目前没有自动回归，是明确的缺口。
5. **类别单一**：6 条全是 `design_flaw`，因为 atlas 只收 durable 失败且目前案例都来自集成/接口设计。不能据此说"研究智能体只有设计缺陷"。

---

## 5. 效度威胁（按 ESE 习惯分四类）

| 类别 | 威胁 | 缓解/说明 |
| --- | --- | --- |
| Construct | "durable 缺陷"由我们自己的分类定义；`design_flaw` 是个宽类别 | 编码本与枚举先于分析固定；atlas 定义见 design/83 |
| Internal | 编码者是开发者本人（自反性）；无第二编码者 | 明确声明；未来加第二编码者与一致性（κ） |
| External | 单项目、单作者、6 个案例、单日记录 | 结论限定在"本项目的集成/接口缺陷"，不外推 |
| Conclusion | 无区间、无对照；n 小 | 只报计数；不宣称比例或因果 |

其他：没有 member checking；没有 operational 失败样本；案例来自 2026-11-18 一天的开发，不能代表长期分布。

---

## 6. 复现

```bash
python scripts/case_study_report.py --out runtime_data/case-study/report.md
python -m unittest tests.test_case_study_report
```

产物：`runtime_data/case-study/report.md`（本机）；编码与 atlas 随仓库分发，报告可由二者重算。

---

## 7. 这条研究在整体中的位置

- 这是 design/97 所说"以 SE 制品为对象"的第一条真实 ESE 研究（案例研究），对象是**软件缺陷**，不是智能体草稿；
- 它同时验证了 method registry 的 case-study 任务卡可执行（字段都能填、检查项可对照）；
- 它暴露的缺口（渲染层无回归测试、无第二编码者、operational 失败未采样）可以直接转成下一轮改进项——这正是"失败即资产"的闭环。

**不能说**：这 6 个案例能代表研究智能体的缺陷分布，或能证明证据门控减少了缺陷——没有对照，也没有足够样本。

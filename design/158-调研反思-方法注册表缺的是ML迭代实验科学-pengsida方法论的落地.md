# 调研反思：方法注册表缺的是"ML 迭代实验科学"——pengsida 方法论的落地与"加方法=加数据"的实证

> 状态基线：2026-11-21。承接 156（治理元模型+组合进注册表）、157（研究/工程/经验本质区别）、研讨纪要（方法差异指导智能体设计与基线对比）。
> 调研工具：pengsida-research skill（learning_research 全量方法论）。本文新增第十个方法 `ml-iterative-experiment`（注册表 0.4，含 8 个新词表标签）——**这是"加方法=加数据，不改执行器"主张的第一次真实执行**。

---

## 0. 一句话结论

用科研方法论 skill 做方法调研，发现注册表的真正缺口不是又一种"社会科学方法"，而是 **ML/AI 研究的实验形态**：goal-driven roadmap、最小可行实验（MV 二元标准）、一次一因素、toy 实验、失败案例分析、实验日志五要素、消融/SOTA 对比、多种子区间披露——这套实践方法论与"受控实验/仓库挖掘"是**不同形状的方法**（迭代式、非线性、大量小实验），而注册表里没有它。本轮以 pengsida learning_research + Agarwal 2021 为文献依据，把它作为第十个方法完整声明进注册表——**零后端改动，全部治理门/标签/矩阵/详情卡自动继承**。

## 1. skill 调研发现的方法形状（与注册表既有方法的对比）

| 维度 | 受控实验（既有） | ML 迭代实验（新增） |
|---|---|---|
| 顺序形态 | 线性：假设→方案→执行→判定 | **迭代环**：idea→最小可行实验→控制变量定位→pivot→再迭代 |
| 实验单位 | 一次受控比较 | 大量小实验（MV 标准、toy setting、一次一因素） |
| 核心证据 | 受控条件下的测量 + 检验 | **实验记录五要素** + 消融表 + failure case 分析 |
| 可复现性 | 预注册 + 随机化 | 多种子区间披露（Agarwal 2021）+ 快照/脚本 |
| 关键威胁 | 混杂/无随机 | 不 work 的定位错误、盲目调参、local minima |

这个方法形状在方法学文献里是标准的（exploratory vs confirmatory 的 ML 实践形态；Easterbrook 2008 的策略谱系未覆盖 ML 迭代科学），pengsida learning_research 是它目前最系统的公开实践手册。

## 2. 注册表声明（0.4，零后端改动）

- **fit_stages**：S1（先 search 再 re-search + 开源代码蒸馏）→ S2-S3（failure case 收敛 idea + problem-driven 四问）→ S4（最小可行实验设计 + 消融/对比计划）→ S5（迭代执行：实验日志五要素 + 控制变量）→ S5b（预注册主指标 + 多种子区间）→ S6（failure case 可视化）→ S8–S12（Intro 倒推/正推 + Method 三元素）；
- **协议字段**：goal_roadmap / minimal_viable_criterion / toy_setting / exploration_points / one_factor_at_a_time / primary_metric / seeds / ablation_plan / baseline_comparison / experiment_log；
- **检查项**：experiment.log（blocker）、mv.criterion（blocker）、one.factor / ablation.study / baseline.comparison / seed.disclosure（warn）；
- **cannot_support**：理论证明 / 单次实验外推 / 未披露种子的可复现声明 / 因果机制（除非受控+随机）；
- **评估维度**（带出处）：可复现性（Agarwal 2021）· 判别力（消融）· 外部效度（toy→real 差距）· 迭代有效性（失败分析）；
- **新词表标签 8 个**：消融实验 / 最小可行实验 / 一次一因素 / 失败案例分析 / 实验日志 / SOTA 对比 / 种子披露 / toy 实验。

## 3. "加方法=加数据"的实证（156 主张的验证）

本轮执行了 156 §5-2 的可证伪主张：新增 ml-iterative-experiment **未改一行后端执行器**——
- python：`tests/test_method_registry` + `test_workspace` 40/40（含三维/标签 fail-closed 自动覆盖新方法）；快照重导；
- 前端：方法矩阵自动 10 行；详情卡自动渲染三维/标签/槽位任务卡/证据类型（"一手迭代测量（多种子 + 消融）"）；标签矩阵自动出现 8 个新标签并标注"机器学习迭代实验"；EVIDENCE_PROFILES 补第十个画像（kind/basis/baselinePolicy）；
- 治理门语义零改动：S5b 门、claim 边界、cannot_support 全部继承。

**排障记录**：注册表 stage id 用 ASCII 连字符（S2-S3），而前端/转录用 en-dash（S2–S3）——迁移脚本首跑因 "unknown stages S2–S3" 失败；从 git 恢复 registry 后修正连字符重跑成功。两套连字符并存是 design/135 登记的词表分叉又一例，加剧了数据迁移的脆弱性。

## 4. 已实测

- typecheck 通过；web `test:unit` 57/57（evidenceProfile 断言更新为十方法）；`python` method_registry/workspace/release_surface 45 测 OK。
- 静态构建实测：矩阵 10 行；ML 方法详情卡三维/标签/槽位任务卡/证据类型全渲染（截图）；标签矩阵自动出现 8 个新标签。
- `docs_audit` / `repo_hygiene` / readiness 通过；发行副本 `--prune` 同步 + 完整性测试 OK。

## 5. 设计主张（可证伪）

1. ML 迭代实验科学是一个**独立的方法形状**（与受控实验正交：迭代环 vs 线性、实验日志 vs 预注册测量、多种子区间 vs 单点比较）——若发现它能被受控实验的协议字段完全表达，本建模即被推翻；
2. 注册表作为方法数据的**扩展性**已被真实执行：加第十个方法只用了数据 + 一个迁移脚本；
3. pengsida learning_research 作为实践方法论的文献地位：公开、结构化、52 文档——是 ML 实验方法的合法 guideline 来源（与 Kitchenham 之于 SLR 同级，但属于实践手册而非学术标准——已在 guidelines 中如实标注类型）。

## 6. 边界与下一步

- ml-iterative-experiment 的 fit_stages 含 S5b/S6/S8-S12，但**注册表没有它到执行器的绑定**（与其他方法一样，执行仍走固定 pipeline）——组合驱动执行器迁移（156 §4）后此方法才真正可执行；
- pengsida 方法论中的"goal-driven roadmap"维度（研究范式层）尚未进注册表——它是比方法更高一层的"研究组合"声明，候选 roadmap；
- 消融实验/种子披露等标签暂未挂到受控实验/基准评测（它们同样适用）——待下一轮标签扩充。

## 7. Changelog

- python：`modules/method-registry/registry.json` 增第十方法 ml-iterative-experiment + 词表 8 项（scripts/add_ml_method.py）；快照重导。
- `apps/web`：`methodModel.ts` EVIDENCE_PROFILES 增 ml-iterative-experiment；`tests/evidenceProfile.test.ts` 十方法断言。

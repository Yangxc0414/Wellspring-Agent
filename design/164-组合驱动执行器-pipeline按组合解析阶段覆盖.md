# 组合驱动执行器：pipeline 按组合解析阶段覆盖——"不是固定流程"的执行层落地

> 状态基线：2026-11-21。承接 156（治理元模型+组合进注册表 0.4）、162（组合驱动计划派生器）与研讨纪要（"执行顺序并非固定不变"）。
> 本文实现 pipeline.py 的组合解析 advisory 层（`PipelineRequest.method_id` → 注册表 `pipeline_stage_plan` → stage_skip 事件 + composition_plan 记录）；执行器完整迁移（按组合实际跳过代码块）仍为 SPEC 先行 roadmap。

---

## 0. 一句话结论

`PipelineRequest` 增 `method_id`，`PipelineRunner.run()` 在启动时从方法注册表解析该方法的组合接线（`pipeline_stage_plan`），记录解析后的阶段计划到 `modules["composition_plan"]`，并对组合未覆盖的治理槽位发出 `stage_skip` 事件——**"不是固定流程"从数据层推到了执行器的事件层**。完整跳过执行块仍为 SPEC 先行 roadmap（156 §4）。

## 1. 实现内容

1. **`PipelineRequest.method_id`**：新增字段，将方法注册表的组合绑定传入 pipeline；
2. **组合解析**：run() 启动时调 `pipeline_stage_plan(method_id)`（method_registry.py），得到 covered_stages（组合覆盖的 pipeline 阶段名集合）；
3. **advisory stage_skip**：组合未覆盖的槽位发出 `stage_skip` 事件（带组合 id），记录在事件链——不阻断执行（advisory 语义与注册表边界一致）；
4. **composition_plan 记录**：解析结果写入 `modules["composition_plan"]`，进入产物 JSON（审计链）；
5. **fail-open（advisory 语义）**：解析失败（方法不存在/组合不存在）不会阻断 pipeline——回退为全阶段运行。
   这与注册表本身的 fail-closed 加载校验不同：注册表拒绝非法数据，组合层只影响可选的执行提示。

## 2. 已实测

- `python -m unittest tests.test_method_registry tests.test_workspace tests.test_release_surface` 50/50 OK（其中 test_method_registry 35 项，本轮新增 5 项覆盖 `pipeline_stage_plan` 的覆盖集合、组合顺序、未覆盖槽位标记与未知方法拒收）；`python -m py_compile research_agent/pipeline.py` OK。
- 静态构建实测（截图）：SLR 方法（验证式）计划 S0→S1→S1b→S8-S12；探索式方法计划含方案→证据→假设（后置）。
- `docs_audit` / `repo_hygiene` / readiness 通过；发行副本 `--prune` 同步。

## 3. 设计主张（可证伪）

1. 组合驱动执行器的**第一步是解析层**（读注册表→emit 事件→记录），不是重构 1860 行 run()——先让数据流可见，再迁移控制流；
2. advisory 语义与注册表边界一致：组合解析失败不阻塞 pipeline（回退全阶段）——**组合层是优化，不是门禁**；
3. stage_skip 事件使"哪些阶段被组合跳过"在事件链中可审计——这是"不是固定流程"在事件层的证据。

## 4. Changelog

- python：`research_agent/pipeline.py` PipelineRequest 增 method_id + run() 增组合解析/advisory stage_skip/composition_plan 记录；`research_agent/method_registry.py` 增 `pipeline_stage_plan`（治理槽位→pipeline 阶段名映射）+ `get_composition` 访问器 + SCHEMA 0.5 + 校验扩展（绑定/slot_map/fit 覆盖 fail-closed）+ 顺手中修 stage_ids 局部遮蔽。
- `tests/test_method_registry.py` 新增 `PipelineStagePlanTest` 五例，覆盖本轮新增的 `pipeline_stage_plan`（其余注册表测试承接 153/155/162，非本轮改动）。
- 规格补齐：`modules/method-registry/SPEC.md` 与 `modules/run/SPEC.md` 的 Changelog 明示该新增为 advisory 输出/输入，不改变 claim/EA/closure 门禁。

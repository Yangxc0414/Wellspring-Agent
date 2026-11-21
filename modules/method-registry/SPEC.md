---
id: method-registry
name: 研究方法注册表（阶段 × 方法）
stage: META
version: 0.3.0
status: draft
owner: research-agent
inputs:
  - StageId
  - MethodId
  - DesignPayload
outputs:
  - MethodList
  - MethodDefinition
  - StageMethodMatrix
  - TaskCard
  - MethodCheckReport
  - PipelineStagePlan  # advisory projection: composition slots -> pipeline stage names
tools:
  - method.list
  - method.show
  - method.matrix
  - method.card
  - method.check
gates: []
invariants:
  - 注册表是数据不是门禁：检查结果只作 advisory，不改变 claim/EA/closure/signature 语义
  - 每个方法必须声明非空 cannot_support，否则拒绝加载
  - 每个方法必须引用至少一条指导性文献（key/citation/mandates 齐全）
  - fit_stages 与 stage_tasks 必须落在已声明阶段内；未知阶段直接拒绝
  - 缺字段按 fail-closed 报告；TODO(...) 占位等同未填写
  - 不联网、不写项目产物、不创建 Claim
---

# 研究方法注册表（阶段 × 方法）

## Purpose

把导师提出的「研究阶段 × 研究方法」二维矩阵变成**可执行的数据**：给定阶段与方法，产出一张任务卡——该阶段在方法约束下必须写清哪些协议字段、产出哪些 artifact、按哪些章节报告、最常见的缺陷是什么。

本模块明确不解决：不实现统计检验、不生成研究内容、不替代 G2/S5b 的人工判断；它只把"方法要求什么"显式化，让人和 agent 都能核对。

## Contract

- 输入：
  - `StageId`：`S0` / `S1` / `S1b` / `S2-S3` / `S4` / `S5` / `S5b` / `S6` / `S8-S12` / `S13-S16`
  - `MethodId`：注册表内的 9 个方法之一（SLR、仓库挖掘、受控实验、准实验、基准评测、案例研究、调查、设计科学、行动研究）
  - `DesignPayload`：任意设计/预注册 JSON（`experiment.json`、study preregistration 等）
- 输出：
  - `MethodList` / `MethodDefinition`
  - `StageMethodMatrix`：每个阶段的 (方法, 该阶段任务, 检查项)
  - `TaskCard`：stage + method 合并后的必填字段、artifact、检查、报告章节、指导文献、`cannot_support`、`applicable`
  - `MethodCheckReport`：逐检查项 pass/missing + `status=advisory_ok|advisory_missing`
- 失败：
  - 注册表 schema 不符、id 重复、未知阶段、缺 cannot_support/guidelines/checks → `MethodRegistryError`
  - 未知方法/阶段 → 报错并列出已知值
- 证据边界：只读投影；`MethodCheckReport` **不是门禁判定**，不写任何文件。

## Current Implementation

- 数据：`modules/method-registry/registry.json`（`ese-method-registry-0.1`，9 方法 × 10 阶段）——方法的指导文献、协议字段、效度重点、artifact、`cannot_support`、检查项、报告章节与逐阶段任务。
- 代码：`research_agent/method_registry.py`——`load_registry`（含 fail-closed 校验）、`list_methods`、`get_method`、`matrix`、`task_card`、`check`。
- CLI：`python -m research_agent method list|show|matrix|card|check`（只读；`check` 读设计 JSON 并输出 advisory 报告）。
- 测试：`tests/test_method_registry.py`（18 例：注册表完整性、矩阵、任务卡、advisory 检查、TODO 占位、CLI 退出码）。
- 不联网；不改任何产物；Python 3.8 兼容。

## Boundaries

- **不是门禁**：`method check` 返回 `advisory_missing` 也不会阻断 pipeline、claim 或 closure；接门禁需要单独的设计评审与人工确认。
- **不是方法的替代品**：注册表只记录"该方法的指导文献要求什么"，不保证执行质量；方法能力由人和评审判断。
- **不覆盖数学/自然科学方法**：当前注册表只覆盖 ESE 方法；其它领域应新增注册表条目或独立注册表。
- **不自动写协议**：任务卡给出字段名与要求，内容仍由人/agent 填写并负责任。
- 文献条目是**导航**，不是对原文的复述；引用准确性需在精读时核对版本。

## Minimal Change Workflow

1. 先改 `registry.json`（新增方法或检查项）并保持 schema；
2. 跑 `python -m unittest tests.test_method_registry`；
3. 若新增 CLI 命令：`python -m research_agent plugin export`；
4. 若模块版本变化：`python -m research_agent workspace export`；
5. 不把检查项直接接进门禁；如确需，另写设计文档并人工确认。

## Changelog

- 2026-11-21 · v0.3.0 · status=draft · 新增 advisory 输出 `pipeline_stage_plan(method_id)`：把组合驱动的槽位计划投影为 pipeline 阶段名集合，供执行器记录与发事件。契约变化仅为新增只读输出；注册表本身仍是数据不是门禁，fail-closed 加载校验不变，claim/EA/closure/signature 语义不变。实现对应 design/164，测试 `PipelineStagePlanTest` 五例。

- 2026-11-18 · v0.2.0 · status=draft · repository-mining 检查新增 mining.analysis（warn）：要求 analysis.stratification 与 analysis.permutation；advisory 语义不变
- 0.1.0（2026-11-18）：首版。9 个 ESE 方法 × 10 个阶段；任务卡、矩阵、advisory 检查与 CLI；18 例测试。承接设计文档 85。

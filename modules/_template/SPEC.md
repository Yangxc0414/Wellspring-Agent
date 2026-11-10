---
id: example-module
name: 示例模块
stage: S0
version: 0.1.0
status: draft
owner: research-agent
inputs:
  - InputType
outputs:
  - OutputType
tools:
  - port.name
gates:
  - G0
invariants:
  - 不创建 Claim
---

# 示例模块

## Purpose

一句话说明这个子智能体解决什么问题、在哪个阶段、明确不解决什么。

## Contract

- 输入：`InputType`
- 输出：`OutputType`
- 失败：写明失败状态与路由；不得静默降级。
- 证据边界：不创建 Claim / EA / Verdict；只写本模块允许的 artifact。

## Current Implementation

- 端口：
- 适配器：
- 是否联网：
- fixture：

## Boundaries

- 不能做什么；
- 哪些字段/动作需要人工或下游模块完成。

## Minimal Change Workflow

1. 先改本文件的 `Contract` 或本节；
2. 升 `version`，在 Changelog 追加说明；
3. 改代码 + 测试；
4. `python -m unittest discover -s tests -v`。

## Changelog

- 2026-10-23 · v0.1.0 · 初始模板。

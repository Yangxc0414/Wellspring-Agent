---
id: memory-port
name: 记忆写入端口
stage: META
version: 0.1.0
status: draft
owner: research-agent
inputs:
  - ProposedMemoryEntry
  - ProjectDirectory
outputs:
  - MemoryAdmissionReport
tools:
  - memory.guidelines
gates: []
invariants:
  - 端口只做准入决定，不写记忆本体——写入仍走各记忆模块自己的 save（单一写入路径）
  - 默认策略 store_all = 现状行为逐字节一致；其余三种策略显式 opt-in
  - 每条候选的准入决定（decision/reason）进 MemoryAdmissionReport，fail-visible
  - 未知策略名直接拒绝（ValueError），不静默回退 store_all
  - 策略不产生证据资格：进记忆的是提示供建议，永远到不了 Claim/EA/gate
---

# 记忆写入端口（MemoryWritePort）

## Purpose

把「一条经验什么时候能安全写入记忆」从各记忆模块的隐式行为提升为可插拔的准入策略对象，服务 71-§4.3 与 M2 四存储策略对照实验（全存 / 全不存 / 重放后存 / 独立验证后存）。解决的具体问题：M2 需要「同一批候选在不同准入策略下进不进记忆」成为可测对象；当前四个记忆存储各自写入、准入未成策略。明确不解决：不产生证据资格（进记忆的是提示供建议）；不测量跨任务收益（那需要不同会话/不同供给，fact-baseline 边界已写）；不做记忆检索（读路径不变）。

## Contract

- 输入：proposed 候选列表（`{text, sources, verification?}`）、策略 id、项目目录。
- 输出：`memory-admission-0.1`——`rows`（每条 `text[:120]/decision/reason`）、`admitted`（原序透传给 merge）、`counts`、`boundary`。
- 四策略（v0.1.0）：
  - `store_all`：全部准入（现状基线）；
  - `store_none`：全部拒绝（对照臂）；
  - `replay_then_store`：候选 sources 引用的每个项目内文件都存在且可读才存（可重放检查）；
  - `independent_verify_then_store`：候选携带 `verification: {source, sha256}` 且 sha256 与该文件实际哈希一致才存（独立验证回执——验证来源不得是候选自己的 sources 之一，否则不算独立）。
- 失败：未知策略 → ValueError；项目目录不存在 → ValueError。
- 复算语义：准入决定是纯函数（文件存在性 + 哈希比对），无墙钟字段。

## Current Implementation

- `research_agent/memory_port.py`：`admit(proposed, *, strategy, project)` 纯函数。
- CLI：`memory guidelines --propose-file F [--admission store_all]`——admitted 透传给 `guideline_memory.merge`，输出新增 `admission` 字段（additive）；默认 store_all 与迁移前行为逐字节一致。
- 是否联网：否。fixture：测试用临时目录伪造 sources 与 verification 回执。

## Boundaries

- v1 的 replay 检查是「来源存在且可读」；span 级重放（引用文本仍在原文同位置）需要来源卡绑定，登记 roadmap。
- v1 只接 guideline_memory（trigger→mechanism→action）；literature_memory / 世代台账 / memory_ab 的写入收敛登记 roadmap。
- 策略→收益的测量（M2 全量）需要多会话/不同供给的作答，本端口只提供准入决定这个被测对象。

## Minimal Change Workflow

1. 新增策略：先在本 SPEC Contract 增行 → memory_port 加 `_decide` 分支 → tests/test_memory_port 加行为断言 → version 升 minor。
2. 接入第二个记忆存储：先在对应模块 SPEC 记录接线，再动本模块，version 升 minor。

## Changelog

- 2026-11-11 · v0.1.0 · status=draft · 初始实现：四准入策略（store_all/store_none/replay_then_store/independent_verify_then_store）+ `memory guidelines --admission` 接线（默认 store_all 逐字节一致，输出 additive 增 admission 字段）+ `scripts/m2_memory_strategies.py` 四策略对照 harness。tests/test_memory_port 钉四策略行为、未知策略拒绝、默认一致性。

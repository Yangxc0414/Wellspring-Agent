---
id: exec-port
name: 执行面接缝
stage: META
version: 0.2.0
status: pilot
owner: research-agent
inputs:
  - ExecFace
outputs:
  - ExecPortProjection
tools:
  - exec.faces
gates: []
invariants:
  - 只读描述执行面池；注册只记录 kind/interpreter/authorization，不启动/杀害/调度进程
  - 不重构现有 dispatch；路由经端口分派是 roadmap，现有三执行面行为不变
  - 不创建 Claim/EA/Verdict/gate/signature；执行授权与审计语义不变
  - 不消除双解释器（平台 3.8 / Harness² 3.12 桥 / 外部 host 三面真实存在）
---

# 执行面接缝（ExecPort · META）

## Purpose

把图④「隔离执行单元池」从叙事变成可注册的接缝：单一对象命名三个真实执行面（inprocess / bridge / host_agent）及其解释器与授权边界，新执行面（conda/docker/remote）在此注册。明确不解决：不做路由重构、不做进程监督、不产生证据或签核。

## Contract

- 输入：`ExecFace(kind, name, interpreter, entry, isolation, authorization)`。
- 输出：`exec-port-0.1` 只读投影（`faces` 按 kind 排序 + `boundary`）。
- `register_face`：kind 空或重复 → `ExecPortError`；`resolve(kind)` 未知 → 拒绝并列出已注册面。
- 失败：不得静默降级；未知 kind 显式报错。
- 证据边界：不创建 Claim/EA/Verdict/gate/signature；只描述，不执行。

## Current Implementation

- 端口：`research_agent/execport/exec_port.py`，预注册三面——inprocess（`executable.py`，3.8，同进程确定性）、bridge（`rsi_harness2.py`，3.12 独立桥进程）、host_agent（`host_model.py`，外部宿主供模型、零 key）。
- CLI：`python -m research_agent exec faces`（只读）。
- 是否联网：否。fixture：测试直接注册/解析，不启动进程。

## Boundaries

- 路由层今天仍直接调用各面；「只经端口分派」是 roadmap，不在本轮重构。
- 不是进程监督器；不能知道外部 job 是否运行，也不能杀死它。
- 执行授权（人批/租约/autopilot 策略）仍由原有模块负责，本端口不放宽。

## Minimal Change Workflow

1. 先改本文件 Contract；
2. 升 version + Changelog；
3. 改 `execport/exec_port.py` + `tests/test_exec_port.py`；
4. 新增 CLI 命令后跑 `plugin export`，改 SPEC 后跑 `workspace export`。

## Changelog

- 2026-11-12 · v0.2.0 · status=pilot · 路由分派接入（71-§5 步 5 收口）：`begin_dispatch(kind, subject)` 成为分派门禁——未注册/未知 kind 在此拒绝执行（ExecPortError），已注册面发 ticket 并记 provenance（`_DISPATCH_COUNTS` + 200 条环形日志）；`end_dispatch(ticket, status)` 标记 completed/failed_*；`describe()` 增 `dispatch_stats`。三个真实分派点接线：bridge=rsi_harness2.run_bridge（超时/启动失败标 failed_*，artifact 增 exec_face.completed）、inprocess=modules/run.py S5 协议执行（Execute 门禁 + 两返回点 end_dispatch）、host_agent=models/gateway.py 宿主 turn（port.complete 前后包络）。端口自身从不启动/调度进程；失败路径用 try/except 包络保证接缝永不阻断执行。tests/test_exec_port 增 DispatchTest 3 项。升 minor。
- 2026-11-11 · v0.1.0 · status=draft · 初始接缝：预注册三执行面 + 只读投影 + `exec faces`；可注册新面、未知 kind 拒绝；不重构路由、不启动进程（71-§4.4 步 5 第一半）。
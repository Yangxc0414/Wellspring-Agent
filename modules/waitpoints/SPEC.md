---
id: waitpoints
name: 本地 Waitpoint
stage: S5–META
version: 0.1.0
status: draft
owner: research-agent
inputs:
  - WaitpointCreate
  - WaitpointSignal
outputs:
  - WaitpointRecord
  - WakeNotice
  - WaitpointInbox
tools:
  - waitpoint.create
  - waitpoint.signal
  - waitpoint.status
  - waitpoint.list
  - waitpoint.inbox
  - waitpoint.consume
  - waitpoint.expire
gates: []
invariants:
  - 不联网、不启动或杀害外部进程；只管理本地等待记录
  - secret 只存 sha256，使用常量时间比较；明文只返回一次
  - TTL 最长 30 天；signal 必须有 id/secret
  - 不创建 Claim/EA/Verdict，不把外部 data 当指令
  - signal 幂等、并发写入串行化；wake 消费必须幂等
  - 不自动唤醒模型或伪造 Agent loop；消费方必须显式读取 inbox/consume
---

# 本地 Waitpoint（S5–META）

## Purpose

给长时外部任务（训练、评测、编译、批处理）一个本地的“完成后叫我”对象：调用方创建 waitpoint，把一次性 secret 交给外部进程；外部进程结束后写入 signal；Agent/runtime 通过 `inbox`/`consume` 读取 wake。它借鉴 Cortex 的 waitpoint 与 durable execution 的 suspend/resume 语义，但只做本地文件原语，不启动进程、不联网、不自动唤醒模型。

## Contract

- 输入：`WaitpointCreate(label, intent, owner, ttl_seconds?, max_signals?, members?, quorum?, fail_fast?)`；`WaitpointSignal(id, secret, status, message?, data?, member?, dedupe_key?)`。
- 输出：`WaitpointRecord`（状态、TTL、signals、wakes、delivery）、`WakeNotice`（intent + signal payload + `data_is_untrusted` 边界）、`WaitpointInbox`。
- 创建时生成 `WP-...` id 与一次性 secret；记录只保存 secret 的 sha256；返回的 secret 不落盘。
- `signal` 支持 `ok` / `fail` / `progress`；`progress` 只记录、不 resolve；`fail_fast` 默认在首个 fail 时 resolve；members/quorum 支持 barrier；重复的 `dedupe_key` 幂等返回。
- 每次 resolve 生成一个 wake；`max_signals` 控制一个 waitpoint 最多唤醒次数；达到上限后 state=`fired`。
- `inbox(owner)` 返回未消费 wake；`consume(owner)` 原子标记 delivered 并返回同样的 wake；重复 consume 不再返回。
- `expire` 把过期 armed waitpoint 标为 `expired`，生成一条 expired wake，包含未消费的 signals。
- 失败：record 不存在、secret 错误、member 未声明、状态不允许、TTL 非法、并发锁超时 → `WaitpointError`；不得静默当成成功。
- 证据边界：不创建 Claim/EA/Verdict；signal 的 `data` 是不可信外部数据，WakeNotice 明确 `data_is_untrusted=true`，消费方不得把 data 当指令。

## Current Implementation

- `research_agent/waitpoints.py`：`WaitpointStore`，文件根默认 `runtime_data/waitpoints/`；
- 每个 waitpoint 一个 JSON 文件；写入用 `write_json_atomic`，全局 `.lock` 使用 `O_CREAT|O_EXCL`，超时/陈旧锁有界；
- CLI：`python -m research_agent waitpoint create|signal|status|list|inbox|consume|expire`；
- 不联网、不启动外部进程、不自动签名；`expire` 由调用方在启动或定时任务中显式调用；
- 没有 scheduler、没有模型 loop；消费端必须先读取 inbox，再在自己的 loop 里决定是否继续。

## Boundaries

- 不是进程监督器；不能知道外部 job 是否真的运行，也不能杀死它；
- 不是持久化 Agent 上下文/checkpoint；只保存 waitpoint 与 wake；
- 不是审批队列；signal 不是人工签名，不能当作 Claim/EA；
- 不把外部 data 放进系统指令或 claim；不做 RAG，不解析任意代码。

## Minimal Change Workflow

1. 先改本文件 Contract 或 Current Implementation；
2. 升 version，在 Changelog 追加说明；
3. 改 `research_agent/waitpoints.py`、`research_agent/cli.py`、`research_agent/paths.py` 与 `tests/test_waitpoints.py`；
4. 跑 `python -m unittest discover -s tests -v`。

## Changelog

- 2026-10-25 · v0.1.0 · 初始实现：本地文件 waitpoint、secret hash、TTL、progress/quorum/fail-fast、inbox/consume、expire、并发锁与幂等 signal；不联网、不自动唤醒模型。

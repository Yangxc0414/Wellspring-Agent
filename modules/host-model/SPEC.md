---
id: host-model
name: 宿主模型交接
stage: META
version: 0.7.0
status: pilot
owner: research-agent
inputs:
  - ModelPortRequest
outputs:
  - ModelTurn
  - ModelTurnReceipt
tools:
  - host_model.pending
  - host_model.respond
gates:
  - 无（本模块不创建人工门；它只是把生成步骤交给宿主 Agent）
invariants:
  - 宿主提交只算能力输出，不算证据；下游审计与门禁必须原样执行
  - turn 与请求文本 SHA-256 绑定，提交时重算不一致即拒绝
  - 一次性消费：responded 的 turn 不可重复改写
  - 过期 turn 不可提交
  - host_label 是"自报且未验证"，不得作为模型独立性或质量的证明
  - 请求哈希重放只在同一 profile 内生效：同一提示词发给两个批评供给时必须各问一次，不得把一份回答复用给两者
  - 端口必须携带可核对的供给指纹（provider_id / provider_kind / model_name）与已消费 turn_id 列表，供面板把分数归因到实际回答者
  - 面板可以证明"同一宿主回答了全部批评角色"，从而拒绝承认独立；它不能证明不同宿主的答案彼此独立
  - 本模块不提供 sign/approve/freeze/claim/publish
---

# 宿主模型交接（Host-as-Model）

## Purpose

让科研运行时在**不持有任何外部 API key** 的前提下获得生成能力：把"需要模型"这一步
变成一个可持久、可校验、可审计的**交接物**（`ModelTurn`），由当前调用本系统的宿主
Agent（Qoder / Claude Code / Codex / Zcode）用它自己的模型完成，再把结果交回来。

解决的问题：本系统的证据与门禁必须固定，但模型接入不该固定。宿主 Agent 已经是一个
在循环里的强模型；要求用户再配一份 key，既提高接入门槛，又把"谁生成了这段文字"
变成系统外的事实。反转之后，生成步骤显式出现在证据链里。

不解决：不训练模型、不做模型路由优化、不证明宿主真的用了它自报的模型。

## Contract

- 输入：一个 `ModelPort` 请求（`messages`、`json_mode`、`module`、`purpose`）。
- 输出：
  - `ModelTurn`：`turn_id`、`status`、`messages_sha256`、`request`（system/user 原文）、
    `expects`（形状要求）、`sink`（可选：完成后要写入的项目内相对路径）、`expires_at`；
  - `ModelTurnReceipt`：提交后的回执，含 `text_sha256`、`host_label`、`submitted_at`、
    `validation`。
- 状态机：`pending → responded`；`pending → expired`；提交校验失败 → 保持 `pending`
  并返回错误（不写入半成品）。
- 失败：`ModelTurnPending`（显式挂起信号，携带 `turn_id`）。调用方**不得**把它当成
  "模型不可用"静默降级为模板；必须把 `turn_id` 透出给宿主。
- 供给指纹：端口暴露 `provider_id`、`provider_kind`、`model_name`、`model_id`；
  `turn_ids` 记录本端口消费过的交接，`answered_by()` 从账本读回实际回答者的 `host_label` 列表
  （pending 时为空）。批评面板用它们把分数归因到真实回答者。
- 重放范围：`find_by_hash(sha, profile_id)`——同一账本里不同 profile 的相同提示词是两次独立请求。
- 证据边界：提交的内容与网关模型返回的内容受同一套下游约束（span-only、引用白名单、
  `allowed_result_numbers`、章节与占位符审计、fixture 检查）。本模块不放宽任何门禁。

## Current Implementation

- 端口：`research_agent/host_model.py::HostModelPort` 实现既有 `ModelPort` 协议
  （`model_id` + `complete(messages, json_mode)`），因此所有已接入网关的模块
  （idea / experiment / paper / judge / rsi / revision / external_skills）无需改动即可使用。
- Provider：`models/types.py` 新增 `kind="host_agent"`；该 kind 不需要 key，也不需要
  `base_url`，`ModelGateway.complete` 对它走账本而不是网络请求。
- 绑定：`GatewayStore.bindings[module] = "host.<profile>"` 即可让该模块的生成步骤转交宿主。
- 账本：`runtime_data/host-model/turns.json`（原子写，单一默认路径，避免多份状态）。
- 是否联网：否。本模块本身不发起任何网络请求。
- fixture：无。turn 内容是真实提交内容；宿主自报标签不参与判定。
- 归因（v0.2.0）：`HostModelPort` 携带 `provider_id / provider_kind / model_name`，`turn_ids`
  记录本端口消费过的交接，`answered_by()` 从账本取回实际回答者的 `host_label`；
  `research_agent/independence.py` 用它把"配置上独立"与"实际上是同一个宿主"分开。
- 只读面板：`GET /api/host-model/panel` 返回 `model_catalog.critic_panel()`（角色→可用 profile、
  可区分供给数、缺多少），不含 key、base_url 或路径；写侧仍只有 respond/void。

## Boundaries

- 不把宿主提交写成 Claim/EA/Verdict/Signature；不写 `human_reason`。
- 不因为"有内容回来了"就跳过审计：`research_manuscript_audit`、支持面板、闭包校验照旧。
- 不提供任意文件写入：`sink` 只能是相对项目根的路径，提交时按既有"必须留在项目/运行数据内"
  的校验解析。
- 不承诺模型质量或独立性；`host_label` 只用于溯源叙述。
- 不在 MCP/HTTP 暴露 approve/sign/freeze/publish；`research_model_respond` 是能力回执，
  不是人工门。

## Minimal Change Workflow

1. 改本文件的 `Contract` 或 `invariants`（契约变化升 minor）。
2. 改 `research_agent/host_model.py`；需要新校验时优先扩展 `expects`，不要在调用方复制校验。
3. 加/改 `tests/test_host_model.py`，至少覆盖：哈希绑定、一次性消费、过期、校验失败不落盘、
   `ModelTurnPending` 不被静默降级。
4. 跑 `python -m unittest discover -s tests`。

## Changelog

- 2026-11-03 · v0.7.0 · status=pilot · 契约输出升 host-contract-0.3：face_coverage 增加 reverse 段（未到达表面分类计数、截断状态与边界），宿主一次协商即可读到"MCP 面够不到什么、哪些缺席还没写理由"。tests/test_handoff 的 schema pin 同步到 0.3，属预期升版。
- 2026-11-03 · v0.6.0 · status=pilot · 契约输出升 host-contract-0.2：新增 face_coverage 字段，宿主做一次协商即可读到"哪个能力由哪一面服务"（faces 计数、已声明/未核验条目、未核验清单与边界），不再需要自行 import face_coverage；同时因为这里不导入 runtime，HTTP 目标显式标 http_targets_verified=false 并在 boundary 里说明未经校验，不装作查过。build.boundary 改为直接给出对照命令：与新起的 `python -m research_agent handoff contract` 比指纹，不同即说明常驻服务在跑旧代码必须重启——"调用成功"不等于"行为是当前代码"。矩阵构建失败时也如实返回 error 字段而不是省略该节。用例 3 个新增（契约含矩阵且如实标注未校验、boundary 含对照命令、include_http=True 时仍逐条校验 HTTP 声明）；tests/test_handoff 里的 schema pin 同步到 0.2（这是本次契约变更的预期升版，不是放宽断言）。
- 2026-10-30 · v0.4.2 · status=pilot · 0.4.2（2026-10-30）：修掉协商里的一处误报：会调用工具的宿主不该因为 handoff 目录不可写而被判 no_writable_handoff_directory——它根本不走文件通道。实测 can_call_tools+can_serve_model 在 outbox 指向不可写路径时仍报该 blocker，与"平台宿主免 key 直接可用"的目标冲突。现在该 blocker 只在既不能调工具、也不能写文件时才出现；tests.test_handoff 同步补了正反两面（纯文件宿主必须报、工具宿主不得报）。无判定语义变化，升 patch。
- 2026-10-30 · v0.4.1 · status=pilot · 0.4.1（2026-10-30）：协商结果现在可从任一传输取得。host_contract() 保持唯一实现，MCP 侧新增只读工具 research_host_contract 直接调用它（见 integration 0.26.0），CLI 侧 handoff contract 不变；因此插件宿主"先协商再降级"不再依赖宿主能执行 shell。工具与 CLI 两条路对同一 capabilities 声明返回同一 schema 与同一 blocked 列表（本轮实测一致：5 个挂起阶段、6 项人工门）。无判定语义变化，升 patch。
- 2026-10-30 · v0.4.0 · status=pilot · 0.4.0（2026-10-30）：宿主接入从"假定会 MCP、假定能当模型"改成**先协商再降级**。新增 research_agent/host_contract.py 与 CLI handoff contract：只读返回 build 指纹、四种传输（进程内 / HTTP / MCP stdio / file-drop，含对 handoff 目录的真实写探针）、模型供给现状（绑定表、哪些 profile 是 keyless host_agent、哪些阶段会挂起、哪些模块没绑定）、按宿主声明能力算出的 blocked 列表与对应的下一步命令，以及**对任何传输都不可用**的六项人工门。宿主可声明 can_call_tools / can_write_files / can_serve_model / long_sessions，未知声明会被原样报告而不是静默接受。实测：只声明前两项时返回 blocked=model_stages_suspend_without_a_host_model（因为 idea/experiment/paper 都绑在 keyless host-agent 上，5 个阶段会挂起等待宿主作答），补声明 can_serve_model 后该项消失；handoff 目录指向一个文件下的路径时 file_drop=false 并给出可执行下一步。新增 6 项测试（含"人工门清单不因宿主声明更多能力而变化"与一条被替换掉的自我比较式空断言——空断言正是本仓库反复批评的模式）。契约变化：新增只读协商面；判定语义与人工门位置未移动。
- 2026-10-30 · v0.3.0 · status=pilot · 0.3.0（2026-10-30）：宿主接入从"只有 MCP 一条路"变成"传输可换、契约不变"。新增 research_agent/handoff.py 与 CLI handoff export|import|status：把 pending 轮次写成 inbox/MT-xxx.json（含请求原文、expects 形状、messages_sha256、过期时间与 answer_file 路径与格式说明），外部 agent 只需读写文件即可把答案写进 outbox/MT-xxx.answer.json；导入走**同一个** ModelTurnLedger.respond 路径，因此形状校验、哈希绑定、一次性消费、过期与 reject_count 记录全部沿用，没有第二套规则。答案格式接受 {"text": string} 或 {"json": any}，其余一律拒绝。边界写进每个产物：handoff 目录只能携带模型能力输出，不能签核/批准/冻结/闭合/导出，且系统不从宿主写的文件里读任何门禁决定。动机是今天实测到的两件事：(1) Qoder 里长驻 stdio 连接器会缓存旧模块（新进程指纹 439dcec80cafdbbb 对宿主无 build 字段），file-drop 路径没有长驻进程，结构上不存在这类陈旧；(2) 目标形态是"一个平台 + 一个即插即用插件"，插件宿主（Codex/Zcode/Qoder）能力差异在权限与会话形态，不在协议，所以接入面必须能降级而不是假定 MCP 可用。实测：tests/test_handoff 7 项 OK（完整往返、形状错误被拒且轮次仍 pending 并计 reject_count、答案格式非法不动账本、status 报告待答清单、未 export 就 import 报错而非静默成功、二次导入被拒"already responded"、产物内不含任何门禁动词且只建 inbox/outbox 两目录）；CLI 子进程往返 OK；tests.test_mcp/test_cli/test_host_model/test_workspace 50 项 OK。契约变化：新增一种宿主传输与其命令面；判定语义与人工门位置未移动。
- 2026-10-30 · v0.2.1 · status=pilot · 0.2.1（2026-10-30）：经 gateway 走的宿主轮次不再丢失阶段标识。ModelGateway.complete/_complete/_complete_host 新增可选 host_module / host_purpose 透传，paper 写手显式传入 module=paper、purpose=S8 non-result sections。此前 idea/experiment 走 adapters.research_models._port_for 时带标识，而写手直接调 gateway，导致挂起消息打印 module=? purpose=?，宿主必须 dump 整段提示词才知道是哪一阶段在等。实测：新产生的轮次 MT-c87623d4797a 记录 module=paper purpose=S8 non-result sections；按哈希重放的旧轮次不受影响（重放匹配的是请求哈希，不是标识）。契约未变（ModelTurn 早已有这两个字段），升 patch。
- 2026-10-29 · v0.2.0 · status=pilot · 0.2.0（2026-10-29）：交接可归因。find_by_hash 增加 profile 维度，避免同一提示词发给两个批评供给时把一份宿主回答复用给两者；HostModelPort 暴露 provider_id/provider_kind/model_name 与 turn_ids/answered_by()，pending 也记账；新增只读 GET /api/host-model/panel。实测：三个 host profile 配置互异但三次批评都由同一宿主回答，面板据此拒绝承认独立评审。契约变化：重放范围与端口属性。
- 0.1.0（2026-10-29）：新建模块。`HostModelPort` + `ModelTurnLedger` + `host_agent`
  provider kind + `research_model_turns` / `research_model_respond` 两个 MCP/HTTP 工具。

# 宿主模型交接：无外部 API key 的科研运行时

> 状态：2026-10-29 实现并实测。契约见 [`modules/host-model/SPEC.md`](modules/host-model/SPEC.md)，
> 架构位置见 [`ARCHITECTURE.md`](ARCHITECTURE.md) §2「生成能力从哪来」。本文记录**为什么这样设计、
> 机制到底做了什么、验证到哪一步、以及不能说什么**。

## 1. 问题：证据必须固定，模型不该固定

在此之前，本系统的生成能力全部落在外部 provider key 上：`ModelGateway` 只认
OpenAI / Anthropic / Azure / OpenAI-compatible 四类端点，`manuscript_writer` 与
`innovation_review` 还各自硬编码读 `DEEPSEEK_API_KEY`。这带来三个不是"配置麻烦"的问题：

1. **接入门槛与"可被任意 Agent 调用"自相矛盾**。我们已经把 37 个工具通过 MCP 暴露给
   Qoder / Claude Code / Codex / Zcode，但宿主一旦想跑真正有模型参与的流程，就必须在系统外
   再配一份密钥——而这件系统对外宣称的能力恰恰是"流程可组合、接入方式可换"。
2. **"谁生成了这段文字"成为系统外的事实**。我们有引用白名单、`allowed_result_numbers`、
   span-only、支持面板、closure 哈希链，但生成主体本身在账本里不留痕。
3. **两条并行的模型解析路径**。`_gateway_port`（idea/experiment）与 `DEEPSEEK_API_KEY`
   （写作/评审）互不相干，同一份 profile 配置对一半流程生效。这是实现债，也是叙事漏洞。

## 2. 机制：把"需要模型"变成一种可审计的交接物

反转点是：MCP 宿主 Agent 本身就在一个循环里，而且它已经带着一个强模型。所以让运行时
**向宿主请求一次生成**，而不是向 provider 发起一次调用。

```text
模块需要一次生成（ModelPort.complete）
  → 落一条 pending ModelTurn
      turn_id、请求原文、messages_sha256、期望形状 expects、可选 sink、TTL
  → 抛 ModelTurnPending（携带 turn_id）
  → 工具层结构化返回 status=awaiting_host_model + 续跑说明
  → 宿主用 research_model_turns 读回提示词原文
  → 宿主用自己的模型作答 → research_model_respond 提交
      按请求哈希绑定 · 形状/键/数组校验 · 一次性消费 · 过期不可提交 · 被拒不写半成品
  → 重跑同一条命令：find_by_hash 命中已答 turn，直接重放答案
```

三条设计决定值得单独说：

**（一）接缝只有一处。** `ModelPort` 早已是唯一协议（`model_id` + `complete(messages, json_mode)`），
所以 `HostModelPort` 实现它之后，idea / experiment / paper / judge / rsi / revision / external_skills
**全部**无需改动即可换成宿主供给；provider 只需新增 `kind="host_agent"`（无 key、无 base_url）。
这是把原来两条路径收敛成一条的机会。

**（二）挂起不是失败，也绝不能被静默降级吞掉。** 代码里到处是"模型不可用 → 退回规则模板"的
善意降级。对宿主交接来说这正是最危险的语义：如果 `ModelTurnPending` 被当成"模型不可用"，
系统会假装跑过并给出模板产物。因此：

- `ModelTurnPending` 继承 `ModelRequiredError`，使既有的 `isinstance(exc, ModelRequiredError): raise`
  传播点自然生效；
- 在 `_complete_json`、`paper_writer` 里显式 `except ModelTurnPending: raise`，抢在通用
  `except Exception` 之前；
- `TaskAgent` 用独立的 `awaiting_host_model` 状态收口，写 `awaiting-host-model.json`
  （**不写 `failure.json`**）；`research_next_actions` 返回 `kind=host_model` 并直接给出续跑指令。

**（三）复用身份是请求哈希，不是 turn id。** `messages_sha256` 由消息规范化后计算。这带来一个
此前没有的性质：**任何中途停下的流程，靠"重跑同一条命令"就能续上**，不需要 checkpoint、
不需要恢复进程状态。turn id 每次随机，所以答案文件按请求哈希命名才可跨 run 复用。

## 3. 安全分析：交接为什么不能成为绕过口

| 风险 | 约束 | 代码位置 |
| --- | --- | --- |
| 答非所问（回答 A 的问题、交给 B 的步骤） | 提交时重算 `messages_sha256`，与 turn 不一致即拒 | `host_model.py::respond` |
| 反复改写已生效的答案 | 一次性消费：`responded` 后再提交报错 | 同上 |
| 陈旧答案复活 | 过期 turn 不可提交；`pending → expired` 只读派生 | `_with_effective_status` |
| 半成品写入项目 | 校验不过保持 pending、不写 sink；sink 必须留在项目根内 | `_write_sink` + `project._inside` |
| 宿主把提交当签核 | 只存文本与回执；不能 approve/claim/sign/freeze/publish；下游审计照旧 | SPEC invariants |
| 静默降级冒充模型输出 | `ModelTurnPending` 显式传播，`awaiting_host_model` 是独立状态 | `_complete_json`、`task_agent.py` |
| 无证据也发起生成 | S4 在 `request.evidence` 为空时跳过模型 designer 并记 warning | `modules/experiment.py` |
| 账本分裂（读写不同路径） | `resolve_ledger_path()` 单一解析，所有构造点共用 | `host_model.py` |

同时必须说清**没有**得到的保证：`host_label` 由宿主自报且未验证，不能据此主张模型独立性、
多样性或质量；提交内容通过审计只说明它符合结构与数值边界，不说明它正确。

## 4. 实测到哪一步

| 项 | 结果 |
| --- | --- |
| MCP 工具面 | 37 工具（新增 `research_model_turns` / `research_model_respond`），无 sign/approve/freeze/publish |
| 真实 stdio MCP 闭环 | `scripts/host_model_loop_test.py`：S1 检索 → S2 假设（宿主作答）→ S4 设计（宿主作答）→ `status=completed`，**6/6 检查通过**，G1 仍为 `candidates_need_human` |
| 答案可复用 | 账本清空重跑：两次答案按请求哈希命中，无需重新作答即推进到 `completed` |
| 校验拒绝路径 | 非 JSON 提交被拒且 turn 保持 pending；`responded` 后重复提交报错 |
| 写作链路 | `research_innovation_review` 以 `awaiting_host_model` 结构化返回并可作答续跑（多轮评审会排队多个 turn，批量作答在 roadmap） |
| 单元测试 | `tests/test_host_model.py` 12 项：哈希绑定、一次性消费、过期、被拒不落盘、`ModelTurnPending` 不降级、`_gateway_port` 零 key 解析 |
| 全量回归 | 559 tests（`python -m unittest discover -s tests`） |

## 5. 顺带修掉的实现债

这些问题是在跑宿主闭环时暴露的，不修就会在真实使用中咬人：

- **`GatewayStore()` 无路径时只在内存里改、从不落盘**：绑定报成功但什么都没写。现在 CLI 与
  网关解析统一走 `default_store_path()`（env 优先，再仓库默认）。
- **CLI 有 10 处硬编码默认 store 路径、不认 `RESEARCH_AGENT_MODEL_STORE`**，与 MCP 行为不一致；
  统一后 `tests/test_cli.py` 才真正 hermetic——此前它继承开发者环境变量，意味着测试可能在
  开发者机器上打真实网络。
- **`spec update --tool` 是整体替换语义**：一次追加把 35 条工具清单冲成 2 条。改为默认追加去重，
  并保留 `--replace-lists`；两个测试锁定该语义。
- **S4 在 `evidence` 为空时仍向模型要设计**：违反 span-only 精神，现跳过并记 warning。

## 6. 与调研到的 Skill 生态的关系

`47-` 精读的九个仓库（CCFA-Skills、academic-research-skills、Awesome-Journal-Skills、ECC、
deer-flow、last30days-skill、scientific-agent-skills 等）共同做法是：**Skill 写"怎么做"，
模型由宿主提供**。它们不需要自带 provider key，因为宿主就是模型——这与我们的反转在方向上
一致。差别在于它们停在"技能目录 + 固定 recipe"，而我们在交接外面套了一层运行时门禁：
提交结果仍要过引用白名单、结果数值上限、章节与 fixture 审计、支持面板与闭包。

因此这条线的定位不是"我们也能用宿主模型"，而是：**宿主模型可以成为一个被约束的能力供给方，
而不是一个可以改写证据规则的调用方**。这也让 `SkillRuntime`（roadmap）与 Host-as-Model 可以
共用同一前提——Skill 与宿主都只能调白名单工具，都不能签核。

## 7. 还不能说什么

- 不是"任意领域全自动科研"；宿主作答只消除了密钥，不消除人工门；
- 不能声称宿主作答带来质量提升：本轮只验证**流程与门禁语义**，没有与外部 provider 做 A/B；
- 多轮评审的批量作答、`sink` 接到写作包绑定草稿、judge/support panel 走宿主供给，都还在 roadmap；
- turn 账本不是断点恢复框架：状态在账本里，不在进程里。

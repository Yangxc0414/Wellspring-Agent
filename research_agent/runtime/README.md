# Local Runtime (FastAPI)

本地 research runtime：把现有 `PipelineRunner` 暴露为 localhost API，并给
`site/live/` 提供真实执行、SSE 事件、产物读取与只读 RSI 审计。

它**不是**云端后端：默认只绑定 `127.0.0.1`，没有鉴权、租户、数据库或沙箱。
不要把端口暴露到公网；需要远程访问时先在反代层加认证与 TLS。

## 启动

```bash
# 终端 1：runtime
python -m research_agent.runtime --port 8787

# 终端 2：静态站点（live 页在 site/live/）
python -m http.server 8000 --directory site

# 打开
# http://127.0.0.1:8000/live/
```

依赖：

```bash
pip install -r requirements-runtime.txt
```

`--host` 默认 `127.0.0.1`；非 loopback 地址必须显式加 `--allow-remote`，但这
只适合你自己控制的反代，不应直接暴露。

## 运行模式

```bash
# 默认：测试/回归，允许 fixture 与规则回退
python -m research_agent.runtime --port 8787

# 生产：必须模型 wired + bound + key；否则 POST /api/runs 返回 503
RESEARCH_AGENT_MODE=production python -m research_agent.runtime --port 8787
```

`/api/health` 返回 `research_mode`、`production_ready` 与逐模块 `model_readiness.blocking`。当前 `idea`/`experiment` 仍是规则模板，因此 production readiness 会明确阻断，而不是静默回退。

## API

| Method | Path | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务状态、test/production 模式、模型 readiness、队列、RSI 只读标记、CORS 来源 |
| GET | `/api/research/capabilities` | 框架无关能力清单：38 tools、JSON Schema、OpenAI function schema、人类门边界 |
| GET | `/api/research/health` | 科研工具桥健康检查；不返回绝对 root |
| POST | `/api/research/tools/{tool_name}` | 统一 JSON 工具调用；loopback 默认，非 loopback 需 Bearer token |
| POST | `/api/runs` | 提交一次 pipeline；202 + `job_id` |
| GET | `/api/runs` | 最近任务（从 `jobs/<id>/job.json` 恢复，重启后仍可列出） |
| GET | `/api/runs/{id}` | 任务状态、结果摘要、错误 |
| GET | `/api/runs/{id}/events?after=` | JSON 事件列表（轮询 fallback） |
| GET | `/api/runs/{id}/events/stream` | SSE 事件流 |
| GET | `/api/runs/{id}/artifacts` | 产物列表（相对路径、大小、kind） |
| GET | `/api/runs/{id}/artifacts/{path}` | 只读下载/预览，限制在 job 目录内 |
| GET | `/api/rsi/ledgers` | 允许根目录下 `schema_version=rsi-0.1` 的账本 |
| GET | `/api/rsi/status?ledger=` | 只读 MetaTracker 报告 |
| GET | `/api/rsi/story?ledger=` | 只读重建 episode→gates→lease→confirmation 审计故事；不回流准入 |
| GET | `/api/rsi/trace?ledger=&scope=&capsule=&confirmation=` | 只读 lease→run→confirmation 校验 |
| GET | `/api/models` | provider/profile/binding 状态；只返回 masked key，不返回明文 |
| POST | `/api/models/providers` | 新建/更新 provider；可选 `api_key` 只写 session 内存 |
| DELETE | `/api/models/providers/{id}/key` | 清除 session key |
| POST | `/api/models/providers/{id}/refresh` | 调 provider `/models` 刷新模型列表 |
| POST | `/api/models/profiles` | 新建/更新模型档案（thinking/max_tokens/extra_body） |
| POST | `/api/models/bindings` | 模块 → profile；仅 `rsi` 当前是 WIRED |
| POST | `/api/models/probe` | 发送一条真实模型请求；产生 API 费用 |
| GET | `/api/models/calls` | 最近 100 次调用元数据；无 prompt/response/key |
| GET | `/api/workspace/agents` | 只读 SPEC 注册表（模块/阶段/版本/工具/门禁/不变量） |
| GET | `/api/orchestrator/topology` | 静态角色/并行 scout/typed handoff/人工门拓扑模板；不执行 |
| GET | `/api/orchestrator/plan?topic=&max_sources=&source=` | 按主题与文献记忆生成协作计划；只读，不运行 scout |
| GET | `/api/literature/memory?limit=` | 文献覆盖记忆快照（面向 coverage/yield/gap）；不含摘要或 span 文本 |
| GET | `/api/agents/custom` | 手动注册的 advisory 子智能体；只含白名单 checks 与派生 tools/outputs |
| POST | `/api/agents/custom` | 新增 advisory 子智能体；校验 checks/role，不接受任意 prompt 或代码 |
| PATCH | `/api/agents/custom/{id}` | 启停或修改名称/用途/checks |
| DELETE | `/api/agents/custom/{id}` | 删除自定义 advisory 子智能体 |
| GET | `/api/evolution/policy` | 自进化 master switch、三个安全 scope 与 locked 不可变面 |
| POST | `/api/evolution/policy` | 切换 master/scope；拒绝 claim/gate/rubric/held-out 等不可变 scope |
| GET | `/api/skills` | 本地技能目录；imported 默认停用、untrusted、execution=not_available |
| POST | `/api/skills/import` | 登记前端对话/导入的 SkillManifest；只做校验与目录，不执行 scripts |
| PATCH | `/api/skills/{id}` | 切换技能目录可见性；不授予执行权限 |
| DELETE | `/api/skills/{id}` | 删除技能目录项 |
| GET | `/api/workspace/commands` | 描述性 CLI 命令目录；不执行 shell |
| GET | `/api/workspace/memory` | 本地工作记忆；明确 `not evidence` |
| POST | `/api/workspace/memory` | 写入决策/偏好/约束/笔记；长度与数量受限 |
| DELETE | `/api/workspace/memory/{id}` | 删除一条本地记忆 |
| POST | `/api/workspace/actions/automation-plan` | 生成受治理运行计划（阶段/门禁/预算/指纹），不执行 |
| POST | `/api/workspace/actions/skill` | 运行后端只读技能：literature-brief / hypothesis-triage / protocol-review / evidence-boundary |
| GET | `/api/workspace/archive` | 本地任务归档索引 |
| POST | `/api/workspace/archive` | 保存任务 JSON 快照；拒绝 secret 字段与 >2MB |
| GET | `/api/workspace/archive/{id}` | 读取归档快照 |
| DELETE | `/api/workspace/archive/{id}` | 删除归档 |

创建任务示例：

```bash
curl -s http://127.0.0.1:8787/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"topic":"钙钛矿界面钝化","language":"zh","venue_type":"zh_core_journal","max_sources":4}'
```

字段限制：`topic` 2–500 字；`max_sources` 1–12；`run_seeds` 1–10；`real_corpus`
只读本地 `modules/literature/fixtures/real_corpus.json`；`run_dataset` 可为
`iris / breast_cancer / chemlab`。

## 边界

- **没有** `/approve`、`/claim`、`/sign` 端点。人工准入、Claim 与签署仍在
  CLI/人工流程；前端不能代替作者或 PI。
- `/api/workspace/actions/*` 只编排现有模块或返回确定性计划；`automation-plan` 不启动 pipeline，`skill` 不创建 Claim/EA。
- `/api/orchestrator/*` 与 `/api/literature/memory` 只读：编排器只在 CLI 中执行 fan-out，runtime 不执行 scout 写入、技能准入或人工门。
- `/api/agents/custom` 只登记白名单 advisory checks；`/api/evolution/policy` 只切换过程/技能可见性，不能解锁 Claim/EA/gate，也不会撤销已有 lease/confirmation。
- `/api/skills*` 是技能目录与校验端点，不是执行器：不运行 scripts、不调用外部工具，`allowed-tools` 只是声明；执行能力始终是 `not_available`。
- `/api/workspace/memory` 与 `/api/workspace/archive` 是本地工作区记录，不是证据：
  不创建/修改 Claim、EA、Closure、Signature，也不进入导出门禁。归档只接受任务 JSON
  快照，拒绝 `api_key`/`authorization`/`token` 等 secret 字段，单条上限 2MB。
- pipeline 不调用外部 API；CC-BY 正文是本地冻结 fixture。模型网关是独立边界：
  只有 `/api/models/probe` 或显式 `rsi propose-model --profile` 会联网。
- 模型密钥不存在配置文件里：环境变量由 runtime 进程读取；session key 只在内存，
  重启失效；API 只返回 `configured/key_source/masked_key`。模型页见
  `site/models/`，设计见 `29-`。
- 任务单 worker 串行执行；事件与结果只保存在 job 目录（不做数据库持久化），产物写入
  `runtime_data/jobs/<job_id>/`。每个 job 另有 `job.json` 保存状态、事件与结果摘要；
  runtime 重启后会恢复已完成任务的列表、事件和产物链接，旧的 `queued/running`
  任务会标为 `failed` 并注明“interrupted by runtime restart”，不会伪装成完成。
  `job.json` 不出现在 artifact 列表中。
- 任务执行异常时写 `task-error.txt` 与 `failure.json`（error_type/retryable/
  suggested_action）；前端 runtime 卡片直接显示“可重试/需人工修复”和修复建议，
  但不会自动重试或改变 claim/gate。
- RSI 端点只读；只允许访问 `research_agent/web/data/` 与 `runtime_data/`。
- 产物访问会拒绝 `..`、绝对路径、越界软链接与超过 20 MB 的文件。
- GitHub Pages 是 HTTPS 静态站点，不能运行 Python；页面从 HTTPS 调本地 HTTP
  会被 mixed content 拦截。请本地打开 Live 页，或把 runtime 放到 HTTPS 反代后。

## 测试

```bash
python -m unittest tests.test_runtime -v
```

测试覆盖：健康检查、请求校验、fixture pipeline、CC-BY 真实文本、
事件/产物读取、路径越界阻断、RSI 只读状态与账本根限制，以及模型网关
provider/profile/binding、key 脱敏与清除、公网明文 URL 拒绝。

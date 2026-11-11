---
title: 多模型接入：OpenAI / Anthropic / 兼容端点、API Key 与思考参数设计
date: 2026-10-24
status: design + MVP
scope: research_agent/models + runtime API + site/models + CLI
related: [17, 21, 22, 27, 28]
---

# 多模型接入：OpenAI / Anthropic / 兼容端点、API Key 与思考参数

> 目标：让平台接入**任意标准 OpenAI / Anthropic HTTP API**（含 OpenAI-compatible、Azure OpenAI、本地 Ollama/vLLM），支持模型选择、每模块绑定与思考参数，同时做到：**密钥不落仓库、不回传浏览器、不进 artifact、不写日志；模型调用可审计；模块不能借模型绕过 claim/EA/gate。**

---

## 0. 结论

1. **不做“模型插件市场”，做一层受控的 Model Gateway。** 供应商差异只在网关内翻译；模块只依赖 `ModelPort`/profile id，不接触 key、base URL 或 provider SDK。
2. **密钥只有两个来源：环境变量（推荐）或本地 runtime 内存（session）。** 配置文件只保存 `api_key_env` 的名字，不保存值；session key 重启即失效；API 只返回 `configured/masked_key/key_source`。
3. **思考参数不是统一字段。** OpenAI 用 `reasoning_effort` + `max_completion_tokens`；Anthropic 用 `thinking.budget_tokens`，且 `max_tokens > budget`；兼容端点没有标准，必须用 `extra_body` 显式声明，不能假装统一。
4. **模型选择分为两层：Provider → Model Profile → Module Binding。** Profile 固定 provider/model/thinking/max_tokens/temperature；Binding 把模块映射到 profile。当前只有 `rsi` 有真实消费者；其余模块标 `CONFIG ONLY`，不会偷偷改变行为。
5. **所有调用只记录元数据**：provider、model、thinking、usage、latency、request id、成功/失败；不记录 prompt/response，不记录 key。
6. **不把模型接入当成能力提升。** 接入 API 只改变“谁来生成”，不改变 claim/EA/gate；RSI 提案仍是不可信输入，仍要过 public/hidden 与人签。

---

## 1. 支持范围与边界

### 1.1 支持的端点

| 类型 | 协议 | 认证 | 模型列表 | 备注 |
|---|---|---|---|---|
| `openai` | `POST /v1/chat/completions` | `Authorization: Bearer` | `GET /v1/models` | 标准 OpenAI |
| `azure_openai` | `POST .../chat/completions?api-version=` | `api-key` header | 不支持自动列表 | 手动填 deployment 名 |
| `anthropic` | `POST /v1/messages` | `x-api-key` + `anthropic-version` | `GET /v1/models`（失败则手动） | 标准 Anthropic |
| `openai_compatible` | `POST .../chat/completions` | Bearer（多数） | `GET .../models` 尽力而为 | Ollama/vLLM/DeepSeek/OpenRouter 等 |

### 1.2 非目标

- 不做工具调用、文件上传、图片/音频、流式 token 的前端渲染（当前网关是文本 JSON，非流式）。
- 不自动重试 401/403/400；只对 429/5xx/网络错误做有限重试。
- 不把 provider 的隐藏思维链写入 artifact、日志或前端；只返回可见文本。
- 不自动为所有模块生成内容；接入 ≠ 模块行为改变。
- 不将 API key 持久化到 `models.json`、`.env` 或浏览器 localStorage。

### 1.3 与现有静态 `models.json` 的关系

`research_agent/web/data/models.json` 是**静态说明快照**，用于工作台展示“模块原本绑定什么”。真实可用的 provider/profile 在 runtime 的 `runtime_data/model_gateway.json`（非密配置），密钥在环境变量或 runtime 内存。两者不要混读：静态快照不是可用配置。

---

## 2. 配置对象

```text
ProviderConfig
  provider_id, kind, label, base_url, api_key_env,
  api_version, allow_private_network, models[]

ModelProfile
  profile_id, provider_id, model, label,
  thinking { mode: off|effort|budget, effort, budget_tokens },
  max_tokens, temperature, top_p, json_mode, extra_body{}

Binding
  module -> profile_id
```

### 2.1 Provider

- ID 限制 `[A-Za-z0-9_-]{1,40}`；`base_url` 必须是 http(s) 且无内嵌账号密码。
- `http` 只允许 `localhost/127.0.0.1`；公网明文拒绝；私有网段需显式 `allow_private_network=true`（本地 Ollama/vLLM 默认允许该 provider）。
- `api_key_env` 是环境变量名，不是值；默认按 provider 类型取 `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`AZURE_OPENAI_API_KEY`/`OPENAI_COMPATIBLE_API_KEY`。
- `models[]` 来自用户输入或 `/models` 刷新；不硬编码模型清单，避免模型更新后配置过期。

### 2.2 Profile

- 一个 profile 固定一个 provider + model；同一模型可以有多个 profile（例如 `gpt-5-high`、`gpt-5-cheap`）。
- `thinking` 是**声明**，不是保证：是否支持由模型/供应商决定；不支持时 provider 会返回 400，界面显示错误，不静默降级。
- `extra_body` 只允许供应商特定字段；`model`/`messages`/`stream` 禁止覆盖，避免绕过网关。
- `max_tokens` 上限 128k；`temperature` 0–2；`top_p` 0–1。
- 能力字段：`context_window`（8k–2M）、`max_output_tokens`（≤ context_window）、`thinking_supported`；`max_tokens ≤ max_output_tokens`。这些值来自接入配置/模型文档，不由前端猜测；不支持思考时 `thinking.mode` 必须为 `off`。

### 2.3 Binding

允许模块：`literature`、`idea`、`experiment`、`paper`、`rsi`。

| 模块 | 当前消费者 | 状态 | 边界 |
|---|---|---|---|
| `rsi` | `rsi propose-model --profile` | **WIRED** | 提案只走 gateway；仍过 GovernancePolicy + public/hidden + 人签 |
| `literature` | 暂无 | CONFIG ONLY | 接入后只允许 QueryPlan/筛选，不创建 Span/Claim |
| `idea` | 暂无 | CONFIG ONLY | 只能产候选，保留 falsification 与人工 G1 |
| `experiment` | 暂无 | CONFIG ONLY | 不得自动冻结 protocol 或生成结果数字 |
| `paper` | 暂无 | CONFIG ONLY | 只能写有证据的段落；结果槽仍由 claim/EA 绑定 |

> 界面显示 `WIRED` / `CONFIG ONLY`，不是装饰：`CONFIG ONLY` 的绑定只是保存配置，不会改变当前 pipeline 行为。

---

## 3. 思考参数：供应商翻译表

### 3.1 OpenAI / Azure OpenAI

| 用户选择 | 请求字段 | 其他 |
|---|---|---|
| `off` | 不传 reasoning | 可传 `temperature`/`top_p`；`max_tokens` |
| `effort=minimal/low/medium/high` | `reasoning_effort` | 使用 `max_completion_tokens`；省略 `temperature`/`top_p` |
| `budget` | 不支持 | 返回 400，提示改用 `effort` |

**注意**：`reasoning_effort` 只对 reasoning 模型有意义；非 reasoning 模型可能忽略或 400。界面明确写“仅对 reasoning 模型有效”，不替用户猜模型能力。

### 3.2 Anthropic

| 用户选择 | 请求字段 | 其他 |
|---|---|---|
| `off` | 不传 thinking | 可传 temperature/top_p；`max_tokens` |
| `effort=minimal/low` | `thinking.budget_tokens=1024` | `max_tokens = max(max_tokens, budget+1024)`；省略 temperature/top_p |
| `effort=medium` | `thinking.budget_tokens=4096` | 同上 |
| `effort=high` | `thinking.budget_tokens=8192` | 同上 |
| `budget=N` | `thinking.budget_tokens=N`（1024–32000） | `max_tokens > N`；省略 temperature/top_p |

**理由**：Anthropic 的 extended thinking 不接受 `reasoning_effort`；用 budget 是官方语义。effort 只是 UI 的便捷映射，实际仍发 budget。

### 3.3 OpenAI-compatible

没有统一标准：

- `effort`：网关透传 `reasoning_effort`（部分兼容端点支持）。
- `budget`：必须在 `extra_body` 中显式提供供应商字段，例如：
  ```json
  {"enable_thinking": true, "thinking_budget": 4096}
  ```
  否则配置阶段直接拒绝，避免“看起来设置了 budget、实际没发”。
- `off`：网关删除 `thinking`/`reasoning_effort`；但 `extra_body` 中的自定义 thinking 字段若存在，需用户自行清理（界面提示）。

### 3.4 JSON 模式

- OpenAI/Azure/兼容：发送 `response_format={"type":"json_object"}`；由 provider 决定是否支持。
- Anthropic：不发送 `response_format`；返回 `json_mode_applied=false`，由调用方（如 proposer）解析文本。界面显示“best-effort”。
- **不把 JSON 模式当结构保证**：仍然要 schema 校验；RSI 提案仍走 `GovernancePolicy`。

---

## 4. 密钥与安全设计

### 4.1 密钥来源

```text
1) session key: 用户在本地模型页粘贴 → POST /api/models/providers
   → 只写 runtime 内存；重启失效；DELETE 可清除
2) env key:    OPENAI_API_KEY / ANTHROPIC_API_KEY / ...
   → runtime 进程启动时/请求时读取；不经过浏览器
```

**不提供“写入 .env”按钮**。如果用户想持久化，自己在 shell/系统环境里设置；runtime 进程读取。这样避免“页面写密钥到仓库”的事故。

### 4.2 不泄漏

- API 返回：`configured`、`key_source`（`env:OPENAI_API_KEY` 或 `session`）、`masked_key`（首 4 + 尾 4）；**不返回明文**。
- 配置文件：`GatewayStore` 递归检查 `api_key/key/secret/token/authorization` 字段；发现即拒绝保存/加载。
- 错误：provider 返回的错误消息经过 `redact_text`，替换 key 与 `sk-...` 模式；错误对象不包含 key。
- 日志：不记录 prompt/response；只记录 provider/model/usage/latency/request_id/ok。
- artifact：模型调用日志在 runtime 内存（最近 100 条），不写 pipeline artifact；`demo.json`/`paper.json` 不含 key。
- 浏览器：key 输入框 `type=password`，提交后清空；不使用 localStorage 保存 key；页面只保存 API base URL。

### 4.3 网络与运行时

- runtime 默认只监听 `127.0.0.1:8787`；模型页与 runtime 都只应本地打开。
- CORS 白名单仅本地端口与 Pages 域名；不开放 `*`。
- URL 策略：拒绝公网 http、拒绝 metadata 端点、私有网段需显式 opt-in；DNS rebinding 是残余风险，文档写明“不要暴露 runtime 到不可信网络”。
- 超时 120s，可配；429/5xx 最多 2 次重试；401/403/400 不重试。
- 请求体上限 20k 字符（probe），避免误用大 payload。

### 4.4 威胁模型（明确写出）

| 威胁 | 现状 | 说明 |
|---|---|---|
| 浏览器扩展/本机恶意进程读取页面输入 | 无法防御 | key 仍在本机内存；不要在共享机器使用 |
| runtime 被暴露到公网 | 默认不允许 | 只监听 localhost；CORS 白名单；不要反代到公网 |
| 供应商记录请求 | 供应商侧 | 由 provider 的隐私政策决定；平台不额外留存 |
| 模型输出包含敏感内容 | 可能 | 不作为 claim 证据；probe 结果只显示不落盘 |
| SSRF 到内网 | 部分防御 | 私有网段 opt-in；DNS rebinding 残余 |
| 供应链/模型后门 | 未解决 | 模型输出是不可信输入；不绕过 gate |

---

## 5. Runtime API

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/models` | providers（含 key 状态）、profiles、bindings、wired、security |
| POST | `/api/models/providers` | 新建/更新 provider；可选 `api_key`（session only） |
| DELETE | `/api/models/providers/{id}/key` | 清除 session key |
| POST | `/api/models/providers/{id}/refresh` | 调 `/models` 刷新模型列表 |
| POST | `/api/models/profiles` | 新建/更新 profile |
| POST | `/api/models/bindings` | 模块 → profile |
| POST | `/api/models/probe` | 发一条真实请求，返回文本/usage/thinking/latency |
| GET | `/api/models/calls` | 最近 100 次调用元数据（无 prompt） |

`GET /api/models` 不要求 key；`probe`/`refresh` 需要 provider 已配置 key，否则 400 并给出环境变量名。

---

## 6. UI 设计（`site/models/`）

### 6.1 页面结构

1. **顶部**：API base、连接状态、runtime 健康。
2. **Hero**：一句话原则“把模型接进来，但不把密钥交出去”；三张安全卡（KEY SOURCE / TRANSPORT / LOGGING）。
3. **01 Providers**：provider 列表（状态/模型数/key source/masked key）+ 编辑表单 + 刷新模型 + 清除 session key。
4. **02 Model Profiles**：profile 列表 + 新建/编辑；provider/model/thinking/max_tokens/temperature/JSON/extra_body。
5. **03 Probe**：选 profile，发一条真实请求；显示文本、usage、thinking applied、latency、request id；明确“会产生费用”。
6. **04 Bindings**：五个模块的选择器；`WIRED`/`CONFIG ONLY` 状态。
7. **05 Call Log**：只显示元数据，不含 prompt/response。
8. **Footer**：本地运行、密钥不落盘提示。

### 6.2 交互原则

- **不隐藏成本**：Probe 按钮旁写明会产生 API 费用。
- **不隐藏能力差异**：thinking 字段随 provider 变化；OpenAI 的 budget 选项禁用；Anthropic 的 effort→budget 映射写在表单下方。
- **不假装绑定生效**：`CONFIG ONLY` 明确显示；`rsi` 显示 `WIRED` 与 CLI 消费方式。
- **不显示密钥**：key 输入框只写不读；已配置时显示 masked + source。
- **错误可操作**：401/429/超时都显示 provider 消息（已脱敏）与下一步建议。
- **移动端**：单列；表单不溢出；Probe 输出可滚动。

### 6.3 视觉

- 沿用站点宋体大标题、等宽 kicker、淡蓝网格、细线直角；
- 状态色只表达语义：绿=ready/ok，红=key missing/error，蓝=可操作；
- 不使用“模型能力评分”之类无来源数字；不显示假的 token 成本。

---

## 7. CLI 与模块接入

### 7.1 RSI proposer（已接通）

```bash
# 先在模型页或写入 runtime_data/model_gateway.json 创建 profile
export OPENAI_API_KEY=...
python -m research_agent rsi propose-model \
  --profile rsi-proposer \
  --store runtime_data/model_gateway.json \
  --observation "Public BM25 baseline recall=1.0, cost=21, gaps=0." \
  --out research_agent/web/data/model-proposal.json
```

- `FrozenModelProposer` 仍要求 JSON schema；`GovernancePolicy` 仍检查 target/patch；候选仍要 `rsi real-trial`。
- 没有 profile 时仍可用 `--model-path` 走本地 Qwen；两种路径不混用。
- API key 只从环境变量读取（CLI 进程没有 runtime 的 session key 内存）。

### 7.2 其他模块（未接通）

`literature`/`idea`/`experiment`/`paper` 仍是本地规则/BM25；模型绑定只保存配置，不改变 pipeline。下一阶段按以下顺序接：

1. `literature` query plan（只产 QueryPlan，不产 Span/Claim）；
2. `paper` 段落草稿（只写有证据的槽位，结果槽仍绑 claim/EA）；
3. `idea` 候选（保留 falsification 与 G1）；
4. `experiment` 设计草稿（人冻结 G2）。

**任何模块接入前必须先在对应 `modules/<id>/SPEC.md` 写 adapter、权限、错误与证据边界。**

---

## 8. 失败模式与处理

| 场景 | 行为 |
|---|---|
| 无 key | 400，提示设置 `OPENAI_API_KEY` 或 session key；不发请求 |
| 401/403 | 原样返回（脱敏）provider 消息；不重试 |
| 429 | 1.8s 内最多 2 次退避重试；仍失败显示 429 |
| 5xx/网络 | 最多 2 次重试；超时 120s |
| 模型不存在 | 400/404 provider 消息；提示刷新模型列表 |
| thinking 不支持 | provider 400；界面显示原始错误；不自动降级（避免静默改变证据条件） |
| Anthropic max_tokens ≤ budget | 网关自动提升到 `budget+1024`（上限 64k） |
| OpenAI budget | 配置阶段 400，要求 effort |
| 兼容端点 budget 无 extra_body | 配置阶段 400 |
| JSON 模式不支持 | 返回 `json_mode_applied=false`；调用方自行 schema 校验 |
| 响应无文本 | 502；不把 thinking 块当文本 |
| key 出现在错误消息 | 替换为 `[redacted]`；错误对象不含 key |

---

## 9. 验收与测试

### 9.1 已实现并测试

- 全量测试 **70 tests OK**（含 9 个模型网关测试、2 个 runtime 模型端点测试、1 个 CLI 参数测试）；
- OpenAI 请求体：`reasoning_effort`、`max_completion_tokens`、省略 temperature/top_p、`response_format`；
- Anthropic 请求体：`thinking.budget_tokens`、`max_tokens > budget`、system 提升、省略 temperature/top_p、`x-api-key`/`anthropic-version`；
- 兼容端点：effort 透传、budget 需 `extra_body`；
- 列表/错误/超时/重试/脱敏；
- 配置存储不含 key；session key 不落盘；snapshot 不含 key；call log 不含 prompt；
- runtime API：provider/profile/binding 创建；清除 key 后 probe 400；公网 http 拒绝；
- 前端：provider/profile/binding 创建、移动端与桌面端无 console error、无页面级横向溢出。

### 9.2 待补

- 真实 OpenAI/Anthropic 账户的端到端 probe（当前测试用本地假服务器，不调用外部 API）；
- Azure OpenAI 实际 deployment 路径/租户验证；
- 流式输出、工具调用、图片输入；
- 速率限制/预算控制的全局配额；
- key 的 OS keychain 集成（可选，不默认）；
- 供应商模型能力元数据（context window、reasoning 支持）自动发现；
- 端到端把 `literature`/`paper` 接上 profile（需先改模块 SPEC）。

---

## 10. 不能宣称

- 不能写“支持所有 OpenAI/Anthropic 特性”：只支持标准文本 chat/messages 路径；工具、流式、图片、批处理未实现。
- 不能写“模型选择会提升科研能力”：绑定 ≠ 能力；当前只有 RSI proposer 接通。
- 不能写“密钥绝对安全”：本地 runtime 只做了不落盘、不回传、脱敏与网络策略；本机恶意进程/浏览器扩展不在防御范围。
- 不能写“thinking 参数已经统一”：它是供应商翻译，不是统一语义；不同模型的 reasoning 不可直接比较。
- 不能写“API 调用结果可作证据”：模型输出仍是不可信输入，不能绕过 claim/EA/gate。

---

## 11. 代码与入口

- 网关：`research_agent/models/{types,store,gateway,service}.py`
- runtime：`research_agent/runtime/app.py` 的 `/api/models*`
- 页面：`site/models/{index.html,models.css,models.js}`
- CLI：`python -m research_agent rsi propose-model --profile ...`
- 测试：`tests/test_models.py`、`tests/test_runtime.py`
- 静态说明：`research_agent/web/data/models.json`（仅展示，不是可用配置）

*本文档是设计与实现记录；外部 provider 的实际行为以其官方 API 为准。*

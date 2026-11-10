---
title: 插件与 MCP 接入：GitHub MCP、工具发现与逐次审批
date: 2026-10-24
status: design + static UI
scope: site/agent PLUGINS drawer; MCP preset; tool approval; no live transport
related: [16, 17, 18, 21, 31, 33]
---

# 插件与 MCP 接入：GitHub MCP、工具发现与逐次审批

> 目标：让工作台可以接入 MCP server（第一个是 GitHub MCP），但**不把“装插件”变成“执行任意代码”**。插件只暴露工具；工具调用必须在对话中逐次批准；结果是不可信外部内容，不能直接成为 claim/EA/证据。
> 本轮是静态 UI + 状态机：登记 GitHub 远端、展示 toolsets、按对话启用、模拟工具发现/调用/审批；**不发起真实 MCP 连接**。

---

## 0. 结论

1. **插件 = MCP server + 工具白名单 + 权限 + 审批策略**，不是一个可以任意执行代码的 prompt 包。
2. **GitHub MCP 用官方远程端点**：`https://api.githubcopilot.com/mcp/`，Streamable HTTP，OAuth；优先只读，toolsets 可收窄。来源见文末。
3. **密钥/OAuth 留在 runtime**，浏览器只看到 `auth=oauth` 或环境变量名，不存 token。
4. **按对话启用**：同一个 MCP server 可以安装在全局 registry，但只在当前 conversation 勾选启用；不同对话可以隔离工具权限。
5. **工具发现是登记，不是自动信任**：先 `probe`/`tools/list` 展示能力，再由用户启用；写工具默认关闭。
6. **每次工具调用必须人工批准**：`proposed → approved/denied → result`；拒绝不执行；结果标 `UNTRUSTED`。
7. **工具结果不是证据**：可以成为线索/候选输入，但必须人工核对，不能自动创建 Claim/EA，不能绕过 gate。
8. **静态版不假装已连接**：状态标 `SIM READY`，测试连接只模拟；真实 MCP transport 留在 runtime adapter。

---

## 1. 插件、Skill、MCP 的区别

| 层 | 是什么 | 谁执行 | 能做什么 | 不能做什么 |
|---|---|---|---|---|
| Skill | 过程性知识/模板/检查点 | Agent/runtime | 改变工作流、提示、预检 | 不能直接写 Claim/EA |
| Plugin | 能力包/manifest + 权限 + 生命周期 | runtime | 提供检索、工具、导出等能力 | 不能绕过证据门 |
| MCP server | 通过标准协议暴露 tools/resources/prompts | 外部进程/HTTP | 提供工具调用 | 不由浏览器直接执行 |

**本页只处理 MCP server 作为“插件”的接入面**；Skill 仍是 `modules/*/SPEC` 的过程包，不与 MCP 混为一谈。

---

## 2. GitHub MCP 预设

```text
name:        GitHub MCP
transport:   streamable-http
endpoint:    https://api.githubcopilot.com/mcp/
auth:        OAuth（runtime）
readonly:    true（优先）
toolsets:    repos, issues, pull_requests（可收窄）
```

- GitHub 官方远程 MCP 使用 Streamable HTTP + OAuth；详见 GitHub MCP Server 文档与远程 MCP 目录。
- 默认只读：`X-MCP-Readonly`/`--read-only` 或只读端点；写操作（issue/PR 修改）默认不启用。
- 可通过 toolsets 收窄，减少上下文占用与误调用。
- 本地 `github-mcp-server`（Docker/stdio）不在浏览器直接执行；如需本地 stdio，由 runtime 管理进程与权限。

> 端点/工具集名称可能随 GitHub MCP 版本变化，真实接入以官方文档为准；本页只保存可编辑配置。

---

## 3. 数据结构

```text
Plugin
  id, name, preset
  transport: streamable-http | sse | stdio
  url, auth: oauth | env | none
  readonly, toolsets[]
  status: registered | needs_auth | ready | disabled | error
  note, installedAt

ToolCall
  id, plugin_id, tool
  args (summary, not secret)
  status: proposed | approved | denied | result | error
  requested_at / approved_at
  result_ref / untrusted=true
```

- `url` 允许手动编辑；不把 OAuth token 放入 URL。
- `args` 只存摘要；不把 GitHub token、私有正文写进日志/artifact。
- 一个 tool call 只能被批准一次；重复点击幂等。
- 工具结果落 artifact 时必须带 `source=mcp`、`untrusted=true`、工具名/参数摘要/hash。

---

## 4. UI 与状态机

### 4.1 入口

- Composer 上方 `PLUGINS n` chip：显示当前对话已启用插件数。
- 左下角“设置与工具” → “插件 / MCP”。
- 命令面板 `插件与 MCP`；`/plugins` 打开面板。

### 4.2 插件面板

```text
PLUGINS / MCP
[GitHub MCP]              SIM READY
streamable-http · oauth · READ ONLY
repos  issues  pull_requests
SIM · 未真实连接；OAuth/token 由 runtime 保管
[✓] 本对话启用

RECENT TOOL CALLS
list_issues   approved
issues · query=research-agent

[+] 接入 MCP Server
预设 / 名称 / Endpoint / 认证 / 工具集 / 只读
[测试连接 (SIM)] [保存并启用]
```

- 预设：GitHub / Custom Streamable HTTP / Local MCP（仅登记，不执行）。
- `测试连接（SIM）` 只模拟；真实连接需要 runtime + OAuth/token。
- “本对话启用”保存到 project，不污染其他对话。

### 4.3 工具调用卡

```text
MCP TOOL CALL                    APPROVAL REQUIRED
github · list_issues
issues · query=research-agent
工具结果不可信；不会自动进入 claim/EA/evidence。需要逐次批准。
[允许一次] [拒绝]
```

- 批准后：系统事件 `TOOL APPROVED` + `MCP RESULT` 卡，标 `UNTRUSTED`。
- 拒绝后：`TOOL DENIED`，不执行、不产生结果。
- 结果卡最多显示摘要；原文/大结果应作为 artifact 引用，不塞进聊天。

### 4.4 状态机

```text
registered → needs_auth → ready → enabled(per conversation)
                         ↘ disabled
tool call: proposed → approved → result
                 ↘ denied
```

- 插件未启用时询问 GitHub 工具：Agent 不调用，提示先启用。
- 写工具默认不显示；如需启用，必须单独确认 scope 与写权限。

---

## 5. 安全边界

| 风险 | 处理 |
|---|---|
| token/OAuth 泄漏 | 只存 runtime；浏览器只显示 `oauth`/环境变量名 |
| 任意代码执行 | 浏览器不启动 stdio；Local MCP 仅登记；stdio 由 runtime 管理 |
| SSRF / 内网 | runtime 侧 URL 策略；默认只允许 HTTPS 公共端点；私有网络显式 opt-in |
| 工具权限过大 | 只读优先；toolsets 白名单；写操作单独审批 |
| 提示注入 | 工具结果标 `UNTRUSTED`，不进入系统指令层；不自动生成 Claim |
| 工具结果污染证据 | 只作线索；Claim 仍需人工/EA/gate |
| 误调用/重复 | 每次调用需批准；idempotency key；调用日志 |
| 恶意 MCP server | 安装前 manifest/权限检查；不允许它改系统 prompt；可撤销/禁用 |
| 审计 | 记录 plugin/tool/args 摘要/time/approver/result hash，不记录 token |

---

## 6. 静态实现与未来 API

### 6.1 本轮已实现（静态）

- `PLUGINS` chip 与抽屉；
- GitHub MCP 预设（端点/OAuth/只读/toolsets）；
- 本对话启用/停用；
- 添加 Custom / Local MCP（仅登记）；
- 模拟测试连接；
- 自然语言“用 GitHub MCP 查 issue” → `MCP TOOL CALL` 卡；
- 允许一次 → `MCP RESULT`（UNTRUSTED）；拒绝 → denied；
- 最近调用列表；Header/RUN 侧栏计数。

### 6.2 未来 runtime API

```http
GET  /api/plugins
POST /api/plugins
GET  /api/plugins/{id}
POST /api/plugins/{id}/probe       # initialize + tools/list
POST /api/plugins/{id}/enable      # per conversation
POST /api/tool-calls               # proposed
POST /api/tool-calls/{id}/approve
POST /api/tool-calls/{id}/deny
GET  /api/tool-calls/{id}
```

- `probe`/`tools/call` 在 runtime 内完成 MCP handshake，浏览器不直接连 MCP。
- OAuth 由 runtime/local callback 处理；token 不入浏览器、不入 artifact。
- SSE 事件：`plugin_status`、`tool_call_proposed`、`tool_call_approved`、`tool_result`、`tool_error`。
- 服务端拒绝：未启用插件、只读模式下的写工具、未审批调用、越权 scope、重复 approval。
- 工具结果写入 artifact store 时带 `source=mcp`、`untrusted=true`、tool/args hash；不自动创建 Claim。

---

## 7. 验收

- [x] GitHub MCP 预设（端点、OAuth、只读、toolsets）；
- [x] 插件面板、按对话启用、最近调用；
- [x] GitHub 工具调用卡、允许/拒绝、UNTRUSTED 结果；
- [x] 未启用时拒绝调用并提示；
- [x] 静态测试连接与安全说明；
- [x] 1440/390 无 console error/横向溢出；
- [ ] 真实 MCP initialize/tools/list/tools/call（未来 runtime）；
- [ ] OAuth 流程、token 存储、SSRF 策略、写工具审批（未来）；
- [ ] 工具结果 artifact 化与审计（未来）。

---

## 8. 不可宣称

- 不能写“已经接入 GitHub MCP”：本轮是**静态登记 + 模拟调用**，没有真实网络连接。
- 不能写“插件结果可作证据”：工具输出是不可信外部内容，必须人工核对。
- 不能写“支持任意 MCP server”：stdio 本地执行、OAuth、写工具与资源/提示协议仍未实现。
- 不能写“插件可以绕过 claim/gate”：插件只提供工具，证据门不变。

---

## 9. 来源

- GitHub 官方远程 MCP：Streamable HTTP 端点 `https://api.githubcopilot.com/mcp/`、OAuth；远程 MCP 目录：<https://mcpservers.org/zh-CN/remote-mcp-servers/github>
- GitHub MCP Server 远程/本地配置与只读/toolsets 说明（社区整理，2026-09）：<https://blog.gitcode.com/e9bfd7acdb62d58f3eef235f3b79cc2a.html>
- 本地设计参考：`16-`（Skill 生态）、`17-` §2.4（插件契约）、`18-`（Pages 与 runtime 边界）、`21-`（SSE/审批）、`31-`/`33-`（单页工作台与运行中指导）。

*本轮为静态设计/实现；真实 MCP transport 与 OAuth 在后续 runtime adapter 中实现。*

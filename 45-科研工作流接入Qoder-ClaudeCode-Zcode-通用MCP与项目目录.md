---
title: 科研工作流接入 Qoder / Claude Code / Zcode：通用 MCP、项目目录与可复现产物
date: 2026-10-26
status: implemented + demo verified
scope: MCP / HTTP JSON / Python SDK; project folder; human-gate tools excluded
related: [34, 40, 44]
---

# 科研工作流接入 Qoder / Claude Code / Zcode

> 本文是接入设计的专题记录；当前工具数、HTTP/SDK 与人工门边界以 [`ARCHITECTURE.md`](ARCHITECTURE.md)、[`integrations/README.md`](integrations/README.md)、[`integrations/FRAMEWORKS.md`](integrations/FRAMEWORKS.md) 为准。

> 目标：不把科研流水线锁死在本项目的网页里，而是让常用的 Coding Agent 直接调用它；所有产物进入用户指定文件夹；人工门不进 MCP。

## 0. 结论

1. **统一入口选 MCP，而不是为每个平台写一套插件。** Qoder、Claude Code、Zcode 都支持标准 MCP stdio；同一份 `research_agent.mcp_server` 可以在三端复用。
2. **平台差异放在 Skill/配置层。** 项目级 `.mcp.json` 负责启动，`.qoder/skills`、`.claude/skills`、`.zcode/skills` 负责“什么时候用、怎么用、哪些事不能做”。
3. **输出契约是项目目录。** 用户给一个 project 文件夹；每次任务写入 `runs/<RUN-ID>/`，包含 `run-context.json`、`task.json`、`task-report.md` 与阶段产物。
4. **MCP 只做执行与读取。** 不提供 claim 签署、protocol freeze、closure sign、bundle publish 或 gate approve 工具；这些仍由人在 CLI 完成。
5. **已做真实 stdio 演示。** 初始化项目、文献综述、strict 假设任务、读取产物全部通过；strict 任务如实停在 G1。

## 1. 平台调研

| 平台 | MCP | 技能/规则 | 结论 |
| --- | --- | --- | --- |
| Qoder | `.mcp.json` / 设置中的 MCP 连接器；支持 stdio | `.qoder/skills/<name>/SKILL.md`；项目级与用户级 | 用同一 MCP + `.qoder` 技能 |
| Claude Code | 项目 `.mcp.json`；stdio | `.claude/skills/<name>/SKILL.md`；也支持 plugin manifest | 用同一 MCP + `.claude` 技能 |
| Zcode | 设置 → MCP 服务器；stdio / SSE / HTTP | 本地资料显示可使用 `.zcode/skills`；不同版本支持度可能不同 | 用同一 MCP；技能作为可选层 |

Qoder 的关键路径是 `.qoder/skills/` 与 MCP JSON；Claude Code 的关键路径是 `.claude/skills/` 与 `.mcp.json`；Zcode 的官方文档明确支持 stdio/SSE/HTTP 三类 MCP，本地实现对 Zcode 的项目配置也有 `.zcode/skills`、`.zcode/agents`、`zcode.json` 的记录。参考：

- Qoder 指南（Skills/MCP 配置路径）：<https://adg.csdn.net/6a59bd16662f9a54cb903a7e.html>
- Qoder CLI 结构反查（`.mcp.json`、`.claude` 兼容、`.qoder` 配置）：<https://github.com/alingse/qodercli-reverse/blob/main/docs/11-decompiled-gap-analysis.md>
- Zcode 官方 MCP 文档：<https://zcode.z.ai/cn/docs/mcp-services>
- Zcode MCP 与 Skill 对比：<https://lpnh.cn/news/1995375>
- Claude Code 插件/技能/MCP 规范：本地 `claude-code-main/plugins/plugin-dev/skills/`（官方插件开发技能）

## 2. 开源对照

本轮对照了本地 `oss/` 与 `claude-code-main/` 的实现：

- **`oss/Auto-claude-code-research-in-sleep-main/mcp-servers/*/server.py`**：纯 Python 手写 JSON-RPC，同时兼容 NDJSON 与 LSP Content-Length；协议帧自动检测；stdout 只用于协议。
- **`oss/full/ResearAI__DeepScientist/src/deepscientist/mcp/`**：按角色拆 memory/artifact/bash_exec 三个 server；工具名动词化；`McpContext.from_env()` + `require_quest_root()` 在服务端强制 workspace 边界；runner 为每个 Claude 任务写独立 `mcp.json`。
- **反模式（`researchclaw/hitl/adapters/mcp_adapter.py`）**：把 `hitl_approve_stage` 暴露成 MCP 工具，模型可以批准自己的门。本项目明确禁止。

由此得到四条设计规则：

1. transport 双帧兼容，stdout 绝不混入日志；
2. 工具名动词化、职责窄，不做一个万能 `research()`；
3. root 由环境变量传入，服务端每次重新校验，不信任调用方路径；
4. 人工门不进入工具面。

## 3. 我们的实现

### 3.1 架构

```text
Qoder / Claude Code / Zcode
        │ stdio JSON-RPC (NDJSON or Content-Length)
        ▼
research_agent.mcp_server
  ├─ Transport（双帧、stdout 隔离）
  ├─ 参数校验 / root 边界 / 工具白名单
  ├─ ResearchMCPService
  │    ├─ project.py（项目目录与 run index）
  │    └─ TaskAgent（S1–S12，复用既有模块）
  └─ ModelGateway（按环境变量与 model store 解析）
        │
        ▼
<project>/runs/<RUN-ID>/
  run-context.json  task-plan.json  task.json  task-report.md
  literature.json / idea.json / experiment.json / run/ / paper.md
  failure.json / startup-error.json
```

### 3.2 工具表

| 工具 | 读/写 | 作用 | 人工门 |
| --- | --- | --- | --- |
| `research_project_init` | 写 | 创建 `project.json` 与固定目录 | 否 |
| `research_plan` | 只读 | 路由、步骤、门、warnings；不执行 | 否 |
| `research_run` | 写 | 执行任务，写到 `runs/<RUN-ID>/` | 跑到门即停 |
| `research_status` | 只读 | 最近 run 的状态/route/stopped_at/failure | 否 |
| `research_list_artifacts` | 只读 | 列出 run 内产物 | 否 |
| `research_read_artifact` | 只读 | 读取文本产物（有大小上限） | 否 |
| `research_next_actions` | 只读 | 返回 G1/G2/S5b/G5 的 CLI 命令与 resume 参数 | 只展示，不执行 |
| `research_skill_list` | 只读 | 目录投影：enabled/license/has_scripts/risk_flags；不含 instructions/路径 | 否 |
| `research_skill_invoke` | 外部模型调用 | enabled 且无 scripts 的 SKILL.md 做 instruction-only advisory；可选成功后蒸馏 | 否 |
| `research_skill_distill` | 写 | 把 enabled Skill 复制为 project notes 下 disabled `local-*` 候选 | 需 license + human_reason；人审后启用 |
| `research_manuscript_revise` | 写 | 已有手稿 + 数据 → 修订稿/指标/图/审计/MD/TeX/DOCX/PDF | 不替代人签/投稿决定；无 profile 为 copy mode |
| `research_writing_pack` | 写 | run → 真实来源卡/span/写作契约，写到 `writing-pack.json/md` | 不签核；未签核 Claim 不发布结果数值 |
| `research_manuscript_audit` | 写 | Qoder 草稿 → 引用/数值/章节/占位符/fixture 预审 | 最多 `ready_for_human_review`；不是同行评审 |
| `research_conference_fetch` | 网络/写 | 按 venue/year 下载 arXiv 公开 PDF，过滤 workshop/symposium/preprint/非 agent 标题 | venue 来自 comment，未独立核验；不是完整 proceedings 抓取 |
| `research_literature_synthesis` | 模型/写 | 多篇来源 → 主题×来源矩阵，记录一致/张力/未使用来源 | 每主题至少 2 篇；不是语义蕴含证明 |
| `research_innovation_review` | 模型/写 | S1 run → 缺口/候选 → novelty/evidence/feasibility 三评审 → 修订 → 再评审 | 评分只是 advisory；不运行实验、不写 Claim |
| `research_manuscript_draft` | 模型/写 | 写作包+创新评审 → 中文立场/综述初稿 → 确定性审计 | 不伪造实验/数字；需真实模型 key |
| `research_manuscript_review` | 模型/写 | rubric 评审 → 修订 → 再评审 | 审计不变差才接受；submission_ready=false |
| `research_experiment_codegen` | 写 | S4 设计 + 项目内 CSV → 自包含实验包（spec/runner/README/manifest） | MCP 只生成代码；执行/approve/ingest/claim 仅本地 CLI，不创建 EA |
| `research_figure_templates` | 只读 | 列出 vendored AstraDraw scene 模板 | 模板仅视觉先验 |
| `research_figure_render` | 写 | scene/模板 → 项目内 SVG/PNG/audit/manifest | 不执行 vendor Node 导出 |
| `research_literature_fetch` | 网络/写 | 显式 allow_network 搜索/下载 arXiv 公开 PDF 到 inputs | 不绕过付费墙；下载不是证据 |

没有 `sign`、`approve`、`freeze`、`publish`、`export`、`skill enable` 或 trusted script 工具。`g1_decision_file`、`protocol_file`、`claim_file` 只能作为已存在的人工产物被消费。

### 3.3 项目目录

```text
<project>/
  project.json                 # schema / project_id / paths / boundary
  inputs/                      # source=local 的 PDF/TXT/MD
  runs/
    RUN-20261026T054836Z-242a33/
      run-context.json         # run_id / clientInfo / 请求摘要 / boundary
      task-plan.json
      task.json
      task-report.md
      literature.json
      q0.json
      ...
    index.json                 # 最近 run 索引
  protocols/                   # 人工冻结的 ProtocolCard
  claims/                      # 人签 ClaimRecord
  closure/                     # closure / 签名 / bundle
  notes/
    skill-invocations/         # advisory 回执
    skill-library/             # disabled 蒸馏候选
    skill-distillations/       # 蒸馏回执
  revisions/                   # 已有手稿修订：审计/diff/图/导出包（按需创建）
  figures/                     # AstraDraw 方法示意图：scene/svg/png/manifest
```

### 3.4 安全边界

- `--root` / `RESEARCH_AGENT_MCP_ROOT` 是唯一允许根；`project_dir` 越界、`..`、symlink 逃逸都拒绝；
- 产物读取只允许 run 目录内的文本文件，限 400k 字符；
- API key 只从 MCP 进程环境变量读取；不写入项目、不进入工具参数；
- `RESEARCH_AGENT_MODE=production` 时，缺 model binding/key 直接失败并写 `startup-error.json`，不静默回退；
- `source=local` 在创建 run 之前检查 `inputs/`，没有 PDF/TXT/MD 直接报错，不产生空 run；
- MCP 不执行外部 Skill scripts；带脚本 Skill 的全权限调用只在本地 CLI 显式 `--trusted-scripts` 下发生，继承用户环境与 OS 权限，不是 sandbox；
- MCP 蒸馏只写 disabled 候选，不自动启用；候选必须由人 review 后在 CLI `skill enable`；
- stdout 只输出协议；库日志与 traceback 走 stderr。

## 4. 接入方式

### Qoder

已放置：

- `.mcp.json`
- `.qoder/skills/research-workflow/SKILL.md`

打开本仓库后，确认 MCP 连接器出现 `research-agent`；必要时在 MCP 设置中手动添加
`python <绝对根目录>/scripts/research_mcp_server.py --root <绝对根目录>`，并设置 `PYTHONPATH`、
`RESEARCH_AGENT_MCP_ROOT` 与 `PYTHONIOENCODING=utf-8`；启动器会固定 cwd 和 import path，避免从 Qoder
安装目录加载到旧代码。`/skills reload` 后技能可用。

本机已通过 Qoder MCP 管理注册 user-scope `research-agent`：连接状态 `ready`，工具列表返回 34 个工具。注册记录在 `runtime_data/integrations/qoder-registration.json`；当前对话若尚未刷新工具目录，重启会话或 `/mcp reload` 后即可在工具面板看到。

### Claude Code

已放置：

- `.mcp.json`
- `.claude/skills/research-workflow/SKILL.md`

首次启动会提示信任项目级 MCP server；确认后可直接用自然语言调用。

### Zcode

在 **设置 → MCP 服务器 → 新建** 选择 stdio，命令与参数同上；参考
`integrations/mcp/zcode.mcp.json`。技能副本在 `.zcode/skills/research-workflow/`。
Zcode 子进程不保证继承 shell 环境，模型 key 要显式配置到 MCP 环境变量。

### 其他智能体框架（HTTP / Python SDK）

MCP 不是唯一入口。启动本地 runtime 后，任意框架可调用同一套工具：

```bash
python -m research_agent.runtime --port 8787
# 远程访问设置 RESEARCH_AGENT_API_TOKEN
```

- `GET /api/research/capabilities`：34 个工具的 JSON Schema + OpenAI function schema；
- `POST /api/research/tools/{tool_name}`：统一 JSON 调用；
- `ResearchAgentClient`：跨进程 Python SDK；
- `LocalResearchAgent`：进程内嵌；
- 默认 loopback；远程必须 token/TLS；无 sign/approve/freeze/publish。

详见 `integrations/FRAMEWORKS.md`。真实 HTTP 桥接演示：

```bash
python scripts/framework_bridge_demo.py
```

### 使用示例

- “用 research-workflow 在 `research-project/inputs` 上做一轮文献综述，输出到 `research-project`。”
- “strict 模式生成三个可证伪假设，停在 G1，并给出人签命令。”
- “读取刚才的 run，告诉我为什么失败，以及下一步怎么修。”
- “列出这次 run 的产物，并给我 closure sign 的命令。”

## 5. 实际演示

命令：

```bash
python scripts/research_mcp_demo.py \
  --project runtime_data/integrations/mcp-demo-project \
  --output runtime_data/integrations/mcp-demo
```

结果（fixture，仅验证接线与边界，不可当真实证据）：

| Run | 类型 | 结果 | 关键产物 |
| --- | --- | --- | --- |
| `RUN-20261026T054836Z-242a33` | literature_review | `completed`，3 sources / 5 spans / 3 gaps | `task-report.md`、`literature.json`、`q0.json`、`task.json` |
| `RUN-20261026T054836Z-31d306` | hypothesis_design (strict) | `needs_human`，停在 G1 | `idea.json`、`literature.json`、`task-report.md` |

G1 的下一步由服务返回，但**不执行**：

```json
{
  "kind": "human_gate",
  "gate": "G1",
  "resume": {
    "g1_decision_file": "runs/RUN-20261026T054836Z-31d306/g1-decision.json"
  }
}
```

调用记录在 `runtime_data/integrations/mcp-demo/transcript.json`，共 10 条 MCP 消息；服务日志在
`stderr.log`，stdout 只包含协议响应。项目目录包含 `project.json`、两个 run 目录和
`runs/index.json`。

## 6. 与现有工作流的关系

- **不替代网页 runtime。** 网页适合人看证据、门禁与产物；MCP 适合让 Coding Agent 在项目里执行与读取。
- **不绕过证据边界。** 所有 run 复用 TaskAgent/PipelineRunner；MCP 只是新的入口。
- **不共享密钥。** 网页 runtime 的 session key 不会进入 MCP 进程；两边各自从环境变量/model store 解析。
- **不把 fixture 当结果。** 技能明确要求标注 fixture；local/openalex 的证据含义与原流水线一致。

## 7. 局限与下一步

1. 长任务同步执行，暂不支持 MCP progress notification；大实验可能需要更长客户端超时或后台 job 适配。
2. 已实现 stdio MCP + 本地 HTTP JSON + Python SDK；HTTP 默认 loopback，远程需要 token/TLS/反代。MCP progress notification 与多租户配额仍未实现。
3. Zcode 的技能目录支持随版本变化；MCP 工具不受影响，但技能触发可能需要手动配置。
4. MCP 进程不共享浏览器 session key；production 用户需在环境中配置 provider key。
5. 目前没有 `closure verify-bundle` 的 MCP 读取封装；可通过 `research_list_artifacts` + `research_read_artifact` 读取产物，签核仍在 CLI。

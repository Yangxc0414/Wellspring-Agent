# 接入其他智能体框架

科研智能体的核心不是绑定 Qoder，而是同一套 **project + tools + human gates**。当前提供三种适配器，三者共用 `research_agent.mcp_server` 的同一套工具契约：

```text
MCP stdio        Qoder / Claude Code / Codex / Zcode / Cursor
HTTP JSON        LangGraph / CrewAI / AutoGen / Dify / n8n / 自研后端
Python SDK       Python 进程内嵌（LocalResearchAgent）或跨进程（ResearchAgentClient）
```

工具数量：23。能力清单位于 `modules/integration/SPEC.md` 与运行时 `/api/research/capabilities`。

## 1. 启动 HTTP adapter

```bash
# 本机默认只允许 loopback
python -m research_agent.runtime --port 8787

# 远程/容器访问必须设置 token
RESEARCH_AGENT_API_TOKEN=<random-token> \
  python -m research_agent.runtime --host 0.0.0.0 --allow-remote --port 8787
```

- `GET /api/research/capabilities`：工具 JSON Schema、OpenAI function schema、人类门边界；
- `GET /api/research/health`：健康检查；
- `POST /api/research/tools/{tool_name}`：统一工具调用；
- 无 token 时仅允许 loopback；非 loopback 返回 403；
- 没有 `sign` / `approve` / `freeze` / `publish` / `export` 工具。

## 2. 先用 capabilities 发现工具

```bash
python -m research_agent.framework_api --root <ABSOLUTE_RESEARCH_ROOT> > capabilities.json
curl -H "Authorization: Bearer $RESEARCH_AGENT_API_TOKEN" \
  http://127.0.0.1:8787/api/research/capabilities
```

返回中的 `openai_tools` 可以直接作为 OpenAI / DeepSeek / Qwen 的 function-calling 工具定义；`tools[].input_schema` 是原始 JSON Schema。

## 3. HTTP JSON 调用

```bash
curl -X POST http://127.0.0.1:8787/api/research/tools/research_project_init \
  -H "Authorization: Bearer $RESEARCH_AGENT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_dir":"demo","name":"Framework Demo"}'

curl -X POST http://127.0.0.1:8787/api/research/tools/research_plan \
  -H "Authorization: Bearer $RESEARCH_AGENT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"project_dir":"demo","goal":"钙钛矿钝化 文献综述","task_type":"literature_review","source":"local"}'
```

返回：

```json
{
  "schema_version": "research-agent-tool-call-0.1",
  "tool": "research_plan",
  "result": {"plan": {"route": "literature_review", "...": "..."}},
  "is_error": false
}
```

## 4. Python SDK

跨进程：

```python
from research_agent.client import ResearchAgentClient

client = ResearchAgentClient(
    "http://127.0.0.1:8787",
    token="<RESEARCH_AGENT_API_TOKEN>",
)
client.init_project("demo", "Framework Demo")
plan = client.plan(
    project_dir="demo",
    goal="钙钛矿钝化 文献综述",
    task_type="literature_review",
    source="local",
)
print(plan["plan"]["route"])
```

进程内嵌：

```python
from pathlib import Path
from research_agent.client import LocalResearchAgent

agent = LocalResearchAgent(Path("/absolute/research/root"))
print(agent.call_tool("research_status", {"project_dir": "demo"}))
```

## 5. OpenAI / LangGraph / CrewAI / AutoGen

### OpenAI function calling

1. 读取 `capabilities.openai_tools`；
2. 把它作为 `tools` 传给模型；
3. 模型返回 `tool_call.function.name/arguments`；
4. 调 `POST /api/research/tools/{name}` 或将 `name/arguments` 交给 `client.call_tool`；
5. 把 `result` 作为工具消息回填。

关键：**工具执行在科研智能体侧，不在外层模型侧**。外层模型只能选择工具，不能直接签 Claim 或改 gate。

### LangGraph

```python
from research_agent.client import ResearchAgentClient

client = ResearchAgentClient(token=os.environ["RESEARCH_AGENT_API_TOKEN"])

def research_node(tool_name: str, arguments: dict):
    return client.call_tool(tool_name, arguments)

# 将 client.openai_tools() 转成 LangGraph tool node；
# 每个 tool node 最终调用 research_node(name, args)。
```

### CrewAI

```python
from crewai.tools import tool
from research_agent.client import ResearchAgentClient

client = ResearchAgentClient(token=os.environ["RESEARCH_AGENT_API_TOKEN"])

@tool("research_plan")
def research_plan(goal: str, project_dir: str = "demo", source: str = "local"):
    """Plan a bounded research task through the local research agent."""
    return client.call_tool("research_plan", {
        "project_dir": project_dir, "goal": goal,
        "task_type": "literature_review", "source": source,
    })
```

### AutoGen

把同一个 `ResearchAgentClient.call_tool` 包成 `FunctionTool` / 自定义 tool；不要为每个 agent 重写科研逻辑。

## 6. 推荐接入顺序

```text
research_project_init
→ research_plan
→ research_run
→ research_status / research_next_actions
→ research_list_artifacts / research_read_artifact
```

已有论文改写：

```text
research_manuscript_revise（draft + data + metrics/figures + profile）
```

外部 Skill：

```text
research_skill_list → research_skill_invoke → research_skill_distill
```

## 7. 人类门与状态

任何适配器都不得把 `needs_human` 说成 `completed`。完整闭环是：

```text
外部 Agent 编排 → 科研智能体执行 → 人类 CLI 签核 → 外部 Agent 续跑
```

G1/G2/S5b/G5、Claim/closure/export 仍只走 CLI。HTTP adapter 没有这些端点。

## 8. 安全边界

- 默认 loopback；远程必须 token + TLS/反代；
- `project_dir` 必须位于 `RESEARCH_AGENT_API_ROOT`；
- 不暴露 API key、模型密钥、绝对本地路径或内部 prompt；
- 外部 Skill 调用为 instruction-only advisory；脚本只在本地 CLI 显式 `--trusted-scripts`；
- 无多租户配额；生产部署需自行加鉴权、审计和限流。

## 9. 兼容性

| 框架 | 接入方式 | 状态 |
| --- | --- | --- |
| Qoder | MCP stdio | 已验证 38 tools ready |
| Claude Code | MCP stdio | 配置已放置 |
| Zcode | MCP stdio | 配置已放置 |
| LangGraph | Python SDK / HTTP tool | 适配接口已提供 |
| CrewAI | Python SDK / HTTP tool | 适配接口已提供 |
| AutoGen | Python SDK / HTTP tool | 适配接口已提供 |
| Dify / n8n / 自研 | HTTP JSON | 适配接口已提供 |

“适配接口已提供”不等于已逐框架跑真实集成；各框架版本和 tool wrapper 仍需按其官方 API 做一次 smoke test。

"""Framework-agnostic research-agent API.

MCP, HTTP JSON and the Python client all dispatch through this layer. The tool
names and JSON schemas are the same as the MCP server; adapters must not copy
business logic.
"""

from pathlib import Path
from typing import Any, Dict

from .mcp_server import (
    HUMAN_ONLY,
    SERVER_NAME,
    SERVER_VERSION,
    TOOL_NAMES,
    TOOLS,
    ResearchMCPService,
    dispatch_tool,
)

CAPABILITIES_SCHEMA = "research-agent-capabilities-0.1"


class ResearchAgentAPIError(ValueError):
    pass


class ResearchAgentAPI:
    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ResearchAgentAPIError("research API root is not a directory: %s" % self.root)
        self.service = ResearchMCPService(self.root)

    def capabilities(self) -> Dict[str, Any]:
        from .paths import build_info

        tools = []
        openai_tools = []
        for item in TOOLS:
            schema = dict(item.get("inputSchema") or {})
            tools.append(
                {
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "input_schema": schema,
                    "annotations": dict(item.get("annotations") or {}),
                }
            )
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": item.get("name"),
                        "description": item.get("description"),
                        "parameters": schema,
                    },
                }
            )
        return {
            "schema_version": CAPABILITIES_SCHEMA,
            "server": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "build": build_info(),
            "protocols": {
                "mcp_stdio": {
                    "command": "python -m research_agent.mcp_server --root <ABSOLUTE_RESEARCH_ROOT>",
                    "framing": "newline-delimited JSON or LSP Content-Length",
                },
                "http_json": {
                    "capabilities": "/api/research/capabilities",
                    "call": "POST /api/research/tools/{tool_name}",
                    "auth": "Bearer RESEARCH_AGENT_API_TOKEN when exposed beyond loopback",
                },
                "python_sdk": "research_agent.client.ResearchAgentClient",
            },
            "tools": tools,
            "tool_names": list(TOOL_NAMES),
            "openai_tools": openai_tools,
            "human_gates": ["Q0", "G1", "G2", "S5b", "G5"],
            "human_only": HUMAN_ONLY,
            "project_required": True,
            "artifact_roots": ["runs", "revisions", "notes"],
            "boundary": (
                "no sign/approve/freeze/publish/export tool; calls stay inside the "
                "configured project root; skill invocation is advisory, trusted scripts "
                "are local-CLI opt-in only"
            ),
        }

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if name not in TOOL_NAMES:
            raise ResearchAgentAPIError("unknown tool: " + str(name))
        if not isinstance(arguments, dict):
            raise ResearchAgentAPIError("tool arguments must be an object")
        result = dispatch_tool(self.service, name, arguments)
        if result.get("isError"):
            structured = result.get("structuredContent") or {}
            raise ResearchAgentAPIError(str(structured.get("error") or "tool failed"))
        return {
            "schema_version": "research-agent-tool-call-0.1",
            "tool": name,
            "result": result.get("structuredContent") or {},
            "is_error": False,
        }

    def health(self) -> Dict[str, Any]:
        return {
            "schema_version": "research-agent-api-health-0.1",
            "status": "ok",
            "server": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "root_configured": True,
            "tool_count": len(TOOL_NAMES),
            "human_sign": False,
            "boundary": HUMAN_ONLY,
        }


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Print research-agent capability manifest")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    print(json.dumps(ResearchAgentAPI(Path(args.root)).capabilities(), ensure_ascii=False, indent=2))

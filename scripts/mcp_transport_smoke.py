"""Client-agnostic stdio MCP handshake smoke test."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from research_mcp_demo import MCPClient


def main() -> int:
    root = Path(sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--root" else ROOT)
    client = MCPClient(root, {"RESEARCH_AGENT_MODE": "test"})
    init = client.request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "transport-smoke", "version": "0.1"},
            "capabilities": {},
        },
    )
    client.notify("notifications/initialized")
    tools = client.request("tools/list").get("tools", [])
    names = {item.get("name") for item in tools}
    result = {
        "result": "pass" if "research_status" in names and len(tools) >= 30 else "fail",
        "server": init.get("serverInfo"),
        "tool_count": len(tools),
        "has_status": "research_status" in names,
        "boundary": "transport smoke only; no model key, no research run, no signature",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

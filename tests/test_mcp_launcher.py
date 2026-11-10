"""The Qoder plugin entry point must start over real stdio and serve tools."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MCPLauncherTest(unittest.TestCase):
    def test_launcher_initializes_lists_tools_and_creates_a_grant_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            env = dict(
                os.environ,
                RESEARCH_AGENT_MODE="test",
                RESEARCH_AGENT_MODEL_STORE=str(root / "model_gateway.json"),
                RESEARCH_AGENT_SKILL_REGISTRY=str(root / "skills.json"),
                RESEARCH_AGENT_SKILL_USAGE=str(root / "skill_usage.json"),
            )
            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "launcher-test", "version": "0"},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": "demo", "name": "launcher test"},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "research_grant_template",
                        "arguments": {
                            "project_dir": "demo",
                            "scheme": "nsfc",
                            "output": "grant-template.json",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "research_venue_audit",
                        "arguments": {
                            "project_dir": "demo",
                            "file": "grant-template.json",
                            "kind": "grant",
                            "scheme": "nsfc",
                        },
                    },
                },
            ]
            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/research_mcp_server.py"),
                    "--root",
                    str(root),
                ],
                input="\n".join(json.dumps(message) for message in messages) + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
                env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            responses = [
                json.loads(line)
                for line in proc.stdout.splitlines()
                if line.strip()
            ]
            by_id = {item.get("id"): item for item in responses}
            self.assertEqual(by_id[1]["result"]["serverInfo"]["name"], "research-agent")
            names = {tool["name"] for tool in by_id[2]["result"]["tools"]}
            self.assertIn("research_grant_template", names)
            self.assertIn("research_venue_audit", names)
            self.assertFalse(by_id[3].get("error"))
            self.assertTrue((root / "demo" / "project.json").is_file())
            created = by_id[4]["result"]["structuredContent"]
            self.assertEqual(created["path"], "grant-template.json")
            audited = by_id[5]["result"]["structuredContent"]
            self.assertEqual(audited["status"], "blocked")
            self.assertFalse(audited["submission_ready"])


if __name__ == "__main__":
    unittest.main()

"""Qoder can create a blank grant scaffold and then audit it over MCP."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent.mcp_server import ResearchMCPService, TOOL_NAMES, TOOLS, dispatch_tool


class GrantTemplateMCPTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.env = mock.patch.dict(
            os.environ,
            {
                "RESEARCH_AGENT_MODE": "test",
                "RESEARCH_AGENT_MODEL_STORE": str(self.root / "model_gateway.json"),
                "RESEARCH_AGENT_SKILL_REGISTRY": str(self.root / "skills.json"),
                "RESEARCH_AGENT_SKILL_USAGE": str(self.root / "skill_usage.json"),
            },
        )
        self.env.start()
        self.log_patch = mock.patch("research_agent.mcp_server._log", lambda _message: None)
        self.log_patch.start()
        self.service = ResearchMCPService(self.root)
        self.service.init({"project_dir": "probe", "name": "grant template"})
        self.project = self.root / "probe"

    def tearDown(self):
        self.log_patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_tool_is_declared_without_gate_authority(self):
        self.assertIn("research_grant_template", TOOL_NAMES)
        tool = next(item for item in TOOLS if item["name"] == "research_grant_template")
        self.assertNotEqual(tool.get("annotations", {}).get("readOnlyHint"), True)
        properties = tool["inputSchema"]["properties"]
        for forbidden in ("sign", "approve", "publish", "submit"):
            self.assertNotIn(forbidden, properties)

    def test_template_then_blank_audit_blocks(self):
        created = dispatch_tool(
            self.service,
            "research_grant_template",
            {"project_dir": "probe", "scheme": "nssfc", "output": "grant/draft.json"},
        )
        self.assertFalse(created["isError"])
        data = json.loads((self.project / "grant/draft.json").read_text(encoding="utf-8"))
        self.assertEqual(data["scheme"], "nssfc")
        self.assertTrue(data["anonymous"])
        self.assertTrue(all(value == "" for value in data["sections"].values()))

        audited = dispatch_tool(
            self.service,
            "research_venue_audit",
            {
                "project_dir": "probe",
                "file": "grant/draft.json",
                "kind": "grant",
                "scheme": "nssfc",
                "anonymous": True,
                "identity_removed": True,
                "ai_statement": True,
            },
        )
        self.assertFalse(audited["isError"])
        self.assertEqual(audited["structuredContent"]["status"], "blocked")
        self.assertTrue(
            any(item.startswith("module.") for item in audited["structuredContent"]["blockers"])
        )

    def test_output_outside_the_project_is_refused(self):
        from research_agent.project import ProjectError

        with self.assertRaises(ProjectError):
            dispatch_tool(
                self.service,
                "research_grant_template",
                {"project_dir": "probe", "scheme": "nsfc", "output": "../outside.json"},
            )


if __name__ == "__main__":
    unittest.main()

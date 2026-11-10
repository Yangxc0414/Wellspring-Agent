import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent.client import LocalResearchAgent, ResearchAgentClient
from research_agent.framework_api import ResearchAgentAPI
from research_agent.mcp_server import TOOL_NAMES


class FrameworkAPITest(unittest.TestCase):
    def test_capabilities_and_local_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = ResearchAgentAPI(root)
            capabilities = api.capabilities()
            self.assertEqual(capabilities["schema_version"], "research-agent-capabilities-0.1")
            self.assertEqual(capabilities["tool_names"], list(TOOL_NAMES))
            self.assertEqual(len(capabilities["tools"]), len(TOOL_NAMES))
            self.assertEqual(len(capabilities["openai_tools"]), len(TOOL_NAMES))
            self.assertTrue(capabilities["human_gates"])
            self.assertIn("sign", capabilities["human_only"])
            self.assertNotIn("api_key", str(capabilities).lower())

            local = LocalResearchAgent(root)
            created = local.call_tool(
                "research_project_init", {"project_dir": "demo", "name": "Framework Demo"}
            )
            self.assertTrue(created["created"])
            plan = local.call_tool(
                "research_plan",
                {
                    "project_dir": "demo",
                    "goal": "测试框架 API 的文献综述",
                    "task_type": "literature_review",
                    "source": "fixture",
                },
            )
            self.assertEqual(plan["plan"]["route"], "literature_review")

    def test_build_fingerprint_reaches_every_entry_point(self):
        # Without this a host cannot tell a missing feature from a stale long-lived server.
        with tempfile.TemporaryDirectory() as tmp:
            api = ResearchAgentAPI(Path(tmp))
            build = api.capabilities()["build"]
            self.assertRegex(build["fingerprint"], r"^[0-9a-f]{16}$")
            self.assertGreater(build["source_files"], 50)
            self.assertIn("stale", build["boundary"].lower())
            api.call_tool("research_project_init", {"project_dir": "demo", "name": "Probe"})
            status = api.call_tool("research_status", {"project_dir": "demo"})["result"]
            self.assertEqual(status["build"]["fingerprint"], build["fingerprint"])

    def test_http_client_sets_bearer_token_and_parses_result(self):
        calls = []

        def fake_urlopen(request, timeout=None):
            calls.append(request)
            payload = json.dumps({
                "schema_version": "research-agent-tool-call-0.1",
                "tool": "research_health",
                "result": {"status": "ok"},
                "is_error": False,
            }).encode("utf-8")
            return io.BytesIO(payload)

        with mock.patch("research_agent.client.urllib.request.urlopen", side_effect=fake_urlopen):
            client = ResearchAgentClient("http://127.0.0.1:8787", token="secret")
            result = client.call_tool("research_health", {})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(calls[0].get_header("Authorization"), "Bearer secret")

    def test_unknown_tool_and_bad_arguments_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            api = ResearchAgentAPI(Path(tmp))
            with self.assertRaises(ValueError):
                api.call_tool("made_up_tool", {})
            with self.assertRaises(ValueError):
                api.call_tool("research_project_init", [])


if __name__ == "__main__":
    unittest.main()

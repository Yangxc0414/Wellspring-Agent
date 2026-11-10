import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from research_agent.cli import main
from research_agent.mcp_server import TOOL_NAMES, TOOLS
from research_agent.project import init_project, project_status
from research_agent.specs import SpecStore

ROOT = Path(__file__).resolve().parents[1]
SKILLS = (
    ROOT / ".qoder" / "skills" / "research-workflow" / "SKILL.md",
    ROOT / ".claude" / "skills" / "research-workflow" / "SKILL.md",
    ROOT / ".zcode" / "skills" / "research-workflow" / "SKILL.md",
)


class IntegrationFilesTest(unittest.TestCase):
    def test_platform_skill_copies_match_and_are_valid(self):
        texts = [path.read_text(encoding="utf-8") for path in SKILLS]
        self.assertEqual(len(set(texts)), 1)
        text = texts[0]
        lines = text.splitlines()
        self.assertEqual(lines[0], "---")
        closing = lines.index("---", 1)
        frontmatter = lines[1:closing]
        keys = {}
        for line in frontmatter:
            if ":" in line:
                key, value = line.split(":", 1)
                keys[key.strip()] = value.strip()
        self.assertEqual(keys.get("name"), "research-workflow")
        self.assertTrue(keys.get("description"))
        self.assertLessEqual(len(keys["description"]), 1024)
        self.assertLess(len(lines), 500)
        self.assertNotIn("TODO:", text)

    def test_root_mcp_config_is_bounded_and_secret_free(self):
        path = ROOT / ".mcp.json"
        if not path.is_file():
            self.skipTest("local .mcp.json is gitignored; the portable example is checked below")
        payload = json.loads(path.read_text(encoding="utf-8"))
        server = payload["mcpServers"]["research-agent"]
        self.assertEqual(server["type"], "stdio")
        self.assertIn("scripts/research_mcp_server.py", " ".join(server["args"]))
        self.assertEqual(server["env"]["RESEARCH_AGENT_MCP_ROOT"], str(ROOT).replace("\\", "/"))
        self.assertEqual(server["env"]["PYTHONPATH"], str(ROOT).replace("\\", "/"))
        self.assertEqual(server["env"]["PYTHONIOENCODING"], "utf-8")
        serialized = json.dumps(payload).lower()
        for secret in ("api_key", "authorization", "password", "secret", "token"):
            self.assertNotIn(secret, serialized)

    def test_root_mcp_example_is_portable_and_secret_free(self):
        path = ROOT / ".mcp.json.example"
        payload = json.loads(path.read_text(encoding="utf-8"))
        server = payload["mcpServers"]["research-agent"]
        self.assertEqual(server["type"], "stdio")
        self.assertIn("scripts/research_mcp_server.py", " ".join(server["args"]))
        serialized = json.dumps(payload)
        self.assertIn("<ABSOLUTE_PATH_TO_REPO>", serialized)
        self.assertNotIn(str(ROOT).replace("\\", "/"), serialized)
        self.assertNotIn(str(ROOT).replace("\\", "\\\\"), serialized)
        lowered = serialized.lower()
        for secret in ("api_key", "authorization", "password", "secret", "token"):
            self.assertNotIn(secret, lowered)

    def test_mcp_examples_use_the_repository_launcher(self):
        for name in ("qoder-claude.mcp.example.json", "zcode.mcp.json"):
            path = ROOT / "integrations" / "mcp" / name
            payload = json.loads(path.read_text(encoding="utf-8"))
            server = payload["mcpServers"]["research-agent"]
            args = " ".join(server["args"])
            self.assertIn("scripts/research_mcp_server.py", args)
            self.assertNotIn("-m research_agent.mcp_server", args)
            self.assertEqual(server["env"]["PYTHONIOENCODING"], "utf-8")

    def test_mcp_tool_contract_matches_integration_spec(self):
        spec = SpecStore().load("integration")
        schema_names = tuple(item["name"] for item in TOOLS)
        self.assertEqual(schema_names, TOOL_NAMES)
        # the spec is the source of truth for the tool surface; a hand-copied count here would
        # only ever remind the author to edit the test, which is the failure mode we keep hitting
        self.assertEqual(sorted(TOOL_NAMES), sorted(spec.tools))
        status_tool = next(item for item in TOOLS if item["name"] == "research_status")
        self.assertIn("experiment_inventory", status_tool["description"])
        self.assertFalse(
            any(
                word in name
                for name in TOOL_NAMES
                for word in ("sign", "approve", "freeze", "publish")
            )
        )

    def test_project_module_and_cli_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "paper"
            first = init_project(target, "Paper")
            self.assertTrue(first["created"])
            second = init_project(target, "Paper")
            self.assertFalse(second["created"])
            for folder in ("inputs", "runs", "protocols", "claims", "closure", "notes"):
                self.assertTrue((target / folder).is_dir())
            self.assertEqual(project_status(target)["runs"], [])

            cli_target = Path(tmp) / "cli-project"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["project", "init", "--dir", str(cli_target), "--name", "CLI"])
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertTrue(payload["created"])
            self.assertTrue((cli_target / "project.json").is_file())


if __name__ == "__main__":
    unittest.main()

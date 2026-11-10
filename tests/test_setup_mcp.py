import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("setup_mcp", ROOT / "scripts/setup_mcp.py")
setup_mcp = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(setup_mcp)


class SetupMcpTest(unittest.TestCase):
    def _root(self, parent: Path) -> Path:
        root = parent / "repo"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "research_mcp_server.py").write_text("", encoding="utf-8")
        return root

    def test_config_is_portable_to_the_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(Path(tmp))
            config = setup_mcp.build_config(root)
        server = config["mcpServers"]["research-agent"]
        self.assertEqual(server["type"], "stdio")
        self.assertIn("scripts/research_mcp_server.py", " ".join(server["args"]))
        self.assertEqual(server["env"]["RESEARCH_AGENT_MCP_ROOT"], root.as_posix())
        self.assertEqual(server["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertNotIn("token", json.dumps(config).lower())

    def test_write_refuses_to_clobber_and_force_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(Path(tmp))
            output = Path(tmp) / "out" / ".mcp.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(setup_mcp.main(["--root", str(root), "--output", str(output)]), 0)
            self.assertTrue(output.is_file())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(setup_mcp.main(["--root", str(root), "--output", str(output)]), 1)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    setup_mcp.main(["--root", str(root), "--output", str(output), "--force"]),
                    0,
                )
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                payload["mcpServers"]["research-agent"]["env"]["PYTHONPATH"],
                root.as_posix(),
            )

    def test_print_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._root(Path(tmp))
            output = Path(tmp) / ".mcp.json"
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                self.assertEqual(
                    setup_mcp.main(["--root", str(root), "--output", str(output), "--print"]),
                    0,
                )
            self.assertFalse(output.exists())
            self.assertIn("research_mcp_server.py", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()

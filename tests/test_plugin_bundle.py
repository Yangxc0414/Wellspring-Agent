"""The plugin bundle is generated, so a stale fragment must be a test failure, not a surprise."""

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "plugin"


class PluginBundleTest(unittest.TestCase):
    def _files(self, root=None):
        from research_agent.plugin_bundle import files

        return files(root or "<RESEARCH_AGENT_ROOT>")

    def test_committed_bundle_matches_a_fresh_derivation(self):
        from research_agent.plugin_bundle import verify

        report = verify(BUNDLE)
        self.assertTrue(
            report["in_sync"],
            "regenerate with `python -m research_agent plugin export`: %s" % report,
        )

    def test_export_writes_every_file_and_materializes_the_root(self):
        from research_agent.plugin_bundle import export

        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "plugin"
            report = export(target, root="/opt/research-agent")
            self.assertEqual(len(report["files"]), len(self._files()))
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["root"], "/opt/research-agent")
            joined = json.dumps(manifest["entrypoints"])
            self.assertNotIn("<RESEARCH_AGENT_ROOT>", joined)
            self.assertIn("/opt/research-agent/scripts/research_mcp_server.py", joined)
            codex = (target / "mcp.codex.toml").read_text(encoding="utf-8")
            self.assertIn("[mcp_servers.research-agent]", codex)
            qoder = json.loads((target / "mcp.qoder.json").read_text(encoding="utf-8"))
            self.assertEqual(qoder["mcpServers"]["research-agent"]["type"], "stdio")

    def test_the_bundle_carries_no_gate_authority(self):
        from research_agent.host_contract import GATE_VERBS

        manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(list(GATE_VERBS), manifest["human_only"])
        lowered = json.dumps(manifest["entrypoints"]).lower()
        for verb in ("sign", "approve", "freeze", "publish"):
            self.assertNotIn(verb, lowered, manifest["entrypoints"])
        self.assertIn("autopilot policy", manifest["boundary"])
        self.assertIn("never create or widen", manifest["boundary"])

    def test_the_skill_tells_the_host_to_negotiate_then_stop(self):
        skill = (BUNDLE / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("handoff contract", skill)
        self.assertIn("handoff export", skill)
        self.assertIn("Stop at the gate", skill)
        # The host needs to know where the human command lives, otherwise "show the CLI command"
        # is an instruction it cannot carry out.
        self.assertIn("claim_draft.command", skill)
        # The pre-authorized path is the only way the host may cross a gate, and it may not
        # author the authorization itself.
        self.assertIn("autopilot research", skill)
        self.assertIn("autopilot run", skill)
        self.assertIn("Never write a policy", skill)

    def test_verify_notices_a_hand_edited_fragment(self):
        from research_agent.plugin_bundle import _write, verify

        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "plugin"
            for name, text in self._files().items():
                (target / name).parent.mkdir(parents=True, exist_ok=True)
                _write(target / name, text)
            self.assertTrue(verify(target)["in_sync"])
            (target / "mcp.qoder.json").write_text("{}\n", encoding="utf-8")
            report = verify(target)
            self.assertFalse(report["in_sync"])
            self.assertEqual(report["stale"], ["mcp.qoder.json"])
            (target / "extra.md").write_text("x\n", encoding="utf-8")
            self.assertEqual(verify(target)["unexpected"], ["extra.md"])


if __name__ == "__main__":
    unittest.main()

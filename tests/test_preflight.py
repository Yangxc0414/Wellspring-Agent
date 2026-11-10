"""Preflight must catch the exact drift this repository actually suffered, or it is decoration."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.cli import main
from research_agent.preflight import (
    build_preflight,
    registry_freshness,
    spec_self_consistency,
    tool_surface_parity,
)

_HEAD = """---
id: {mid}
name: 名称
stage: S5
version: 0.2.0
status: pilot
owner: research-agent
---

## Changelog

{entry}
"""


class PreflightTest(unittest.TestCase):
    def _modules(self, root: Path, changelog_entry: str) -> Path:
        modules = root / "modules"
        one = modules / "demo"
        one.mkdir(parents=True)
        (one / "SPEC.md").write_text(
            _HEAD.format(mid="demo", entry=changelog_entry), encoding="utf-8"
        )
        return modules

    def test_a_version_bump_without_its_changelog_line_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            modules = self._modules(Path(tmp), "- 2026-01-01 · v0.1.0 · status=pilot · 旧条目")
            result = spec_self_consistency(modules)
            self.assertEqual(result["checked"], 1)
            self.assertEqual(len(result["stale"]), 1)
            self.assertIn("no Changelog entry", result["stale"][0]["problem"])

    def test_a_matching_changelog_line_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            modules = self._modules(Path(tmp), "- 2026-01-01 · v0.2.0 · status=pilot · 新条目")
            self.assertEqual(spec_self_consistency(modules)["stale"], [])

    def test_an_exported_registry_behind_the_specs_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "agent-registry.json"
            target.write_text(
                json.dumps({"agents": [{"id": "literature", "version": "0.0.1"}]}),
                encoding="utf-8",
            )
            result = registry_freshness(target)
            self.assertEqual(result["status"], "stale")
            changed = {item["id"] for item in result["changed"]}
            self.assertIn("literature", changed)

    def test_the_live_repository_passes_and_not_because_it_checked_nothing(self):
        report = build_preflight()
        self.assertEqual(report["status"], "fresh", report["blockers"])
        self.assertGreaterEqual(report["checks"]["spec_self_consistency"]["checked"], 25)
        from research_agent.mcp_server import TOOL_NAMES

        self.assertEqual(report["checks"]["tool_surfaces"]["tools"], len(TOOL_NAMES))
        self.assertGreaterEqual(len(TOOL_NAMES), 40)
        self.assertGreaterEqual(report["checks"]["registry"]["agents_live"], 25)
        self.assertIn("not that behaviour is correct", report["boundary"])

    def test_tool_surface_parity_is_measured_not_assumed(self):
        parity = tool_surface_parity()
        self.assertEqual(parity["status"], "fresh", parity["problems"])

    def test_cli_exits_zero_when_the_chain_is_current(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["workspace", "preflight"]), 0)


if __name__ == "__main__":
    unittest.main()

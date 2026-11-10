"""The host-facing skill file is a contract, so it gets guarded like one.

Three client folders carry a copy of it, and its tool names must exist on the server.
Neither was verified before, which is how a duplicated section number, a CRLF drift and
stale tool references all survived silently.
"""

import re
import unittest
from pathlib import Path

from research_agent.mcp_server import TOOL_NAMES

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / ".qoder" / "skills" / "research-workflow" / "SKILL.md"
TARGETS = (
    ROOT / ".claude" / "skills" / "research-workflow" / "SKILL.md",
    ROOT / ".zcode" / "skills" / "research-workflow" / "SKILL.md",
)


class IntegrationSkillContractTest(unittest.TestCase):
    def setUp(self):
        self.text = CANONICAL.read_text(encoding="utf-8")

    def test_every_client_copy_matches_the_canonical_file(self):
        canonical = self.text.replace("\r\n", "\n")
        for target in TARGETS:
            self.assertTrue(target.is_file(), "missing client skill: " + str(target))
            self.assertEqual(
                target.read_text(encoding="utf-8").replace("\r\n", "\n"),
                canonical,
                "run scripts/sync_integration_skills.py: " + str(target),
            )

    def test_section_numbers_are_unique(self):
        numbers = re.findall(r"^## (\d+[a-z]?)\.", self.text, re.M)
        self.assertEqual(
            len(numbers), len(set(numbers)), "duplicated section number in SKILL.md: %s" % numbers
        )

    def test_named_tools_exist_on_the_server(self):
        # names appear either in backticks (prose) or as a call (code fence); module paths
        # such as `python -m research_agent` or research_mcp_server.py are not tool names
        named = set(re.findall(r"`(research_[a-z_]+)`", self.text)) | set(
            re.findall(r"\b(research_[a-z_]+)\(", self.text)
        )
        unknown = sorted(named - set(TOOL_NAMES))
        self.assertTrue(named, "the skill names no tools at all")
        self.assertEqual(
            unknown,
            [],
            "the skill instructs the host to call tools that do not exist: %s" % unknown,
        )

    def test_host_reachable_innovation_surfaces_are_documented(self):
        for tool in ("research_skill_packs", "research_mandate_status", "research_next_actions"):
            self.assertIn(tool, self.text, tool + " must be reachable from the skill guide")
        self.assertIn("pack_scope", self.text, "coverage guidance must teach the partial window")


if __name__ == "__main__":
    unittest.main()

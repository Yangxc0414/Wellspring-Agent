"""The MCP face must route and score a skill pack exactly as the CLI face does.

Found by calling the tool through Qoder: coverage rejected a pack_root plus venue that the CLI
accepts, its rubric window defaulted to 60 items where the CLI uses 200, and neither face reported
which venue the confidence came from.
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.cli import build_parser
from research_agent.mcp_server import ProjectError, ResearchMCPService
from research_agent.pack_audit import resolve_pack_dir
from research_agent.skill_packs import DEFAULT_MAX_ITEMS, coverage_report, scan_pack
from tests.test_skill_packs import _make_repo

ARTIFACT = {"question": "remove author identity and affiliation from the submission"}


class McpSkillPackRoutingTest(unittest.TestCase):
    def _setup(self, root: Path) -> Path:
        repo = _make_repo(root)
        artifact = root / "artifact.json"
        artifact.write_text(json.dumps(ARTIFACT), encoding="utf-8")
        return repo

    def test_coverage_accepts_pack_root_and_venue(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._setup(root)
            service = ResearchMCPService(root)
            payload = service.skill_packs(
                {
                    "action": "coverage",
                    "pack_root": str(repo),
                    "venue": "Demo Journal",
                    "artifact": "artifact.json",
                }
            )["structuredContent"]
            self.assertEqual(payload["pack"], "Demo-Skills")
            self.assertEqual(payload["route"]["venue_id"], "demo-journal")
            self.assertIn(payload["route_confidence"], ("medium", "high"))
            self.assertEqual(payload["pack_scope"]["max_items"], DEFAULT_MAX_ITEMS)

    def test_both_faces_score_the_same_window_of_the_same_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self._setup(root)
            service = ResearchMCPService(root)
            via_mcp = service.skill_packs(
                {
                    "action": "coverage",
                    "pack_root": str(repo),
                    "venue": "Demo Journal",
                    "artifact": "artifact.json",
                }
            )["structuredContent"]
            pack_dir = resolve_pack_dir("", str(repo), "Demo Journal")
            pack = scan_pack(Path(pack_dir), stage="", max_items=DEFAULT_MAX_ITEMS, stages=[])
            via_library = coverage_report(
                pack["checklist"], json.dumps(ARTIFACT), stage="", stages=[]
            )
            for key in ("items", "covered", "missing", "unmatched", "near_miss"):
                self.assertEqual(via_mcp[key], via_library[key], key)
            self.assertEqual(
                via_mcp["pack_scope"]["checklist_total"],
                pack["checklist_total"],
                "the denominator must travel with the score on both faces",
            )
            self.assertFalse(via_mcp["pack_scope"]["truncated"])

    def test_no_pack_argument_says_what_to_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            service = ResearchMCPService(root)
            with self.assertRaises(ProjectError) as raised:
                service.skill_packs({"action": "coverage", "artifact": "artifact.json"})
            message = str(raised.exception)
            self.assertIn("pack_dir", message)
            self.assertIn("venue", message)


class RubricWindowDefaultTest(unittest.TestCase):
    def test_cli_and_mcp_share_one_default(self):
        parser = build_parser()
        for argv in (
            ["skill", "coverage", "--pack", "p", "--file", "f"],
            ["skill", "pack", "--path", "p"],
        ):
            namespace = parser.parse_args(argv)
            self.assertEqual(namespace.max_items, DEFAULT_MAX_ITEMS, " ".join(argv))


if __name__ == "__main__":
    unittest.main()

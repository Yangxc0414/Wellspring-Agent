"""The MCP face must give the same provenance verdict as the library and reject unknown args."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.mcp_server import ProjectError, ResearchMCPService
from research_agent.number_provenance import draft_numbers, provenance_for_draft


class McpNumberProvenanceTest(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        study = root / "studies"
        study.mkdir()
        (study / "study.json").write_text(json.dumps({"auc": -0.40651}), encoding="utf-8")
        paper = root / "paper"
        paper.mkdir()
        (paper / "draft.md").write_text(
            "iris -0.40651 and -0.999999 which exists nowhere\n", encoding="utf-8"
        )

    def test_service_verdict_equals_the_library_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            service = ResearchMCPService(root)
            payload = service.number_provenance({"draft": "paper/draft.md", "corpus": "."})
            inner = payload["structuredContent"]
            # both faces go through provenance_for_draft; comparing against the raw
            # build_provenance default would compare against a circular corpus
            direct = provenance_for_draft(root / "paper" / "draft.md", root)
            self.assertEqual(inner["decimals_total"], direct["decimals_total"])
            self.assertEqual(inner["decimals_traced"], direct["decimals_traced"])
            self.assertEqual(inner["decimals_untraced"], direct["decimals_untraced"])
            self.assertEqual(inner["counts_certified"], 0)
            self.assertIn("-0.999999", inner["decimals_untraced"])
            self.assertNotIn("-0.40651", inner["decimals_untraced"])

    def test_unknown_argument_is_rejected_not_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            service = ResearchMCPService(root)
            with self.assertRaises(ProjectError):
                service.number_provenance(
                    {"draft": "paper/draft.md", "corpus": ".", "sign": True}
                )


if __name__ == "__main__":
    unittest.main()

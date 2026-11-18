"""Agent-driven ESE exploration: protocol drafting, reflection, note rendering."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent import ese_explore  # noqa: E402


class EseExploreTest(unittest.TestCase):
    def test_protocol_has_all_repository_mining_fields(self):
        protocol = ese_explore.draft_protocol(
            "Do bug-fix commits touch tests more often?",
            {"primary_metric": "test co-change rate", "hypothesis": "h"},
            ["/tmp/click", "/tmp/requests"],
            "ESE-EX-1",
        )
        for field in ("sampling_frame", "project_selection", "time_window", "time_split",
                      "dedup_policy", "label_source", "license_check", "extraction_script"):
            self.assertTrue(protocol.get(field), field)
        self.assertEqual(protocol["method"], "repository-mining")
        self.assertEqual(len(protocol["sampling_frame"]["repos"]), 2)

    def test_protocol_requires_question_and_repos(self):
        with self.assertRaises(ese_explore.EseExploreError):
            ese_explore.draft_protocol("", {}, ["/tmp/a"], "S")
        with self.assertRaises(ese_explore.EseExploreError):
            ese_explore.draft_protocol("q", {}, [], "S")

    def test_reflection_states_limits_and_next_question(self):
        result = {
            "pooled": {
                "commits": 100, "test_cochange": 40, "rate": 0.4, "ci": [0.31, 0.49],
                "bugfix": {"rate": 0.5, "hits": 20, "total": 40},
                "non_bugfix": {"rate": 0.33, "hits": 20, "total": 60},
                "difference": 0.17,
                "permutation": {"p_value_two_sided": 0.01},
            },
            "time_split": {
                "early": {"rate": 0.3}, "late": {"rate": 0.5}, "difference": 0.2,
                "permutation": {"p_value_two_sided": 0.001},
            },
        }
        reflection = ese_explore.reflect(result, {})
        text = " ".join(reflection["observations"])
        self.assertIn("0.400", text)
        self.assertIn("p=0.0100", text)
        self.assertIn("causal", text)
        self.assertIn("Next question", reflection["next_question"])

    def test_note_renders_without_pipeline_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "pipeline"
            out.mkdir()
            (out / "literature.json").write_text(json.dumps({"hits": [], "spans": []}), encoding="utf-8")
            note = ese_explore.render_note(
                "q", "S", {"sources": [], "span_count": 0, "fixture_mode": False},
                [], {"hypothesis": "h", "status": "needs_human"},
                {"sampling_frame": {}, "project_selection": "x"}, {}, {"observations": [], "next_question": "n"},
                "p", "r",
            )
            self.assertIn("no SE corpus", note)
            self.assertIn("missing:", note)


if __name__ == "__main__":
    unittest.main()

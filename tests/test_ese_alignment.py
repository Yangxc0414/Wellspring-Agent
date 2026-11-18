"""Question-idea alignment: the exploration must not execute an unrelated question."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent import ese_explore  # noqa: E402


class AlignmentTest(unittest.TestCase):
    def test_aligned_question(self):
        ideas = [{
            "title": "Bug-fix commits and test co-change in Python projects",
            "hypothesis": "bug-fix commits touch tests more often than other commits",
            "falsification": "no difference in test co-change",
        }]
        link = ese_explore.alignment("Do bug-fix commits touch tests more often in Python projects?", ideas)
        self.assertEqual(link["status"], "aligned")
        self.assertGreaterEqual(link["overlap_ratio"], 0.2)

    def test_unrelated_question_is_weak(self):
        ideas = [{
            "title": "Flaky test vocabulary in Swift",
            "hypothesis": "vocabulary clusters explain flakiness",
            "falsification": "clusters do not explain",
        }]
        link = ese_explore.alignment("Which database indexes reduce latency?", ideas)
        self.assertEqual(link["status"], "weak")
        self.assertEqual(link["shared_terms"], [])


if __name__ == "__main__":
    unittest.main()

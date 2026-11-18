"""Ablation summary: arm parsing and underpowered guard."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.ablation_summary as summary  # noqa: E402


class AblationSummaryTest(unittest.TestCase):
    def test_parse_arm_splits_name_and_dirs(self):
        name, dirs = summary.parse_arm("baseline=a,b,c")
        self.assertEqual(name, "baseline")
        self.assertEqual(dirs, ["a", "b", "c"])

    def test_parse_arm_rejects_empty(self):
        with self.assertRaises(SystemExit):
            summary.parse_arm("baseline=")

    def test_parse_arm_requires_equals(self):
        with self.assertRaises(SystemExit):
            summary.parse_arm("baseline")


class PairedIntervalTest(unittest.TestCase):
    def test_interval_for_four_diffs(self):
        result = summary.paired_interval([2, 1, 1, 1])
        self.assertEqual(result["mean"], 1.25)
        self.assertLess(result["ci_low"], 1.25)
        self.assertGreater(result["ci_high"], 1.25)
        self.assertAlmostEqual(result["sign_test_two_sided_p"], 0.125)

    def test_single_pair_has_no_interval(self):
        result = summary.paired_interval([1])
        self.assertIsNone(result["ci_low"])
        self.assertEqual(result["sign_test_two_sided_p"], 1.0)

    def test_empty_is_safe(self):
        result = summary.paired_interval([])
        self.assertIsNone(result["ci_low"])


if __name__ == "__main__":
    unittest.main()

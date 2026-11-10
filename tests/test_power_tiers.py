"""Power tiers, with "never estimated" kept distinct from "cannot be estimated".

Measured across 142 stored packages: 235 comparisons carry a power estimate, and of the 196 that
do not, 195 have a full effect and interval and no recorded reason either - they simply predate the
ladder. Collapsing those into one bucket would read as "too small to judge" when the truth is
"nobody ever judged it", which is the distinction a reviewer is entitled to.
"""

import io
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.study_package import build_study_package, power_tiers
from tests.test_study_package import fixture_package


def _evidence(rows, seeds):
    return {"seeds": list(seeds), "comparison": rows}


class PowerTierTest(unittest.TestCase):
    def test_a_run_that_reaches_the_needed_seeds_is_confirmatory(self):
        got = power_tiers(_evidence({"a": {"seeds_for_80pct": 8}}, [1, 2, 3, 4, 5, 6, 7, 8]))
        self.assertEqual(got["confirmatory"], 1)
        self.assertEqual(got["exploratory"], 0)
        self.assertTrue(got["has_confirmatory"])
        self.assertIsNone(got["worst_gap_multiple"])
        self.assertEqual(got["comparisons"], 1)

    def test_a_shorter_run_is_exploratory_and_keeps_the_recorded_requirement(self):
        got = power_tiers(
            _evidence({"a": {"seeds_for_80pct": 4096}, "b": {"seeds_for_80pct": 32}}, list(range(1, 17)))
        )
        self.assertEqual(got["confirmatory"], 0)
        self.assertEqual(got["exploratory"], 2)
        self.assertEqual(got["paired_seeds"], 16)
        self.assertEqual(got["worst_gap_seeds_needed"], 4096)
        self.assertEqual(got["worst_gap_multiple"], 256.0)
        self.assertFalse(got["has_confirmatory"])

    def test_a_declined_row_is_not_counted_as_a_missing_estimate(self):
        got = power_tiers(
            _evidence({"a": {"mean_diff": 0.01, "ci95_low": None, "reason": "needs >= 4 seeds"}}, [1, 2])
        )
        self.assertEqual(got["declined_with_reason"], 1)
        self.assertEqual(got["never_estimated"], 0)
        self.assertEqual(got["unestimable"], 0)

    def test_a_full_statistic_with_no_estimate_is_never_estimated_not_unestimable(self):
        got = power_tiers(_evidence({"a": {"mean_diff": -0.018, "ci95_low": -0.06, "ci95_high": 0.02}}, [1, 2, 3]))
        self.assertEqual(got["never_estimated"], 1)
        self.assertEqual(got["unestimable"], 0)
        self.assertEqual(got["declined_with_reason"], 0)

    def test_a_row_without_statistics_is_unestimable(self):
        got = power_tiers(_evidence({"a": {}, "b": {"mean_diff": None}}, [1, 2, 3]))
        self.assertEqual(got["unestimable"], 2)
        self.assertEqual(got["never_estimated"], 0)

    def test_every_comparison_lands_in_exactly_one_bucket(self):
        got = power_tiers(
            _evidence(
                {
                    "a": {"seeds_for_80pct": 8},
                    "b": {"seeds_for_80pct": 64},
                    "c": {"reason": "needs >= 4 seeds"},
                    "d": {"mean_diff": 0.01, "ci95_low": -0.01, "ci95_high": 0.03},
                    "e": {},
                },
                list(range(1, 17)),
            )
        )
        self.assertEqual(
            got["comparisons"],
            got["confirmatory"]
            + got["exploratory"]
            + got["declined_with_reason"]
            + got["never_estimated"]
            + got["unestimable"],
        )
        self.assertEqual(got["comparisons"], 5)

    def test_zero_seeds_never_produces_a_division_or_a_false_confirmatory(self):
        got = power_tiers(_evidence({"a": {"seeds_for_80pct": 8}}, []))
        self.assertEqual(got["paired_seeds"], 0)
        self.assertEqual(got["exploratory"], 1)
        self.assertFalse(got["has_confirmatory"])


class PowerTierBundleTest(unittest.TestCase):
    def test_the_bundle_carries_the_tier_and_the_reading_of_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_study_package(fixture_package(), output=Path(tmp) / "reader", language="en")
            with io.open(result["manifest"], encoding="utf-8") as handle:
                manifest = json.load(handle)
            with io.open(result["readme"], encoding="utf-8") as handle:
                document = handle.read()
            with io.open(Path(result["study_dir"]) / "study-evidence.json", encoding="utf-8") as handle:
                comparisons = len((json.load(handle) or {}).get("comparison") or {})
        tiers = manifest["power_tiers"]
        self.assertEqual(tiers["schema_version"], "study-power-tiers-0.2")
        self.assertEqual(tiers["comparisons"], comparisons)
        self.assertIn("power tier of the", document)
        self.assertIn("never estimated", document)
        self.assertIn("mechanism check", document)
        self.assertIn("declined_with_reason", tiers["boundary"])


if __name__ == "__main__":
    unittest.main()

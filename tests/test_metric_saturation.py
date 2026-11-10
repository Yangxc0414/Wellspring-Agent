"""Ceiling-censoring audit: report the risk, never rewrite the registered metric."""

import unittest

from research_agent.metric_saturation import (
    interaction_sensitivity,
    normalized_run,
    saturation_report,
)


def _study(best_scores, roots=None):
    roots = roots or [0.5] * len(best_scores)
    runs = [
        {"best_score": best, "root_score": root}
        for best, root in zip(best_scores, roots)
    ]
    cells = [
        {"cell_id": "memory_off_gate_on_archive_off", "runs": runs[: len(runs) // 2]},
        {"cell_id": "memory_on_gate_on_archive_off", "runs": runs[len(runs) // 2 :]},
    ]
    return {"cells": cells}


class MetricSaturationTest(unittest.TestCase):
    def test_mass_at_the_ceiling_is_flagged(self):
        report = saturation_report(_study([1.0, 1.0, 0.8, 0.9]))
        self.assertTrue(report["available"])
        self.assertTrue(report["saturated"])
        self.assertEqual(report["ceiling_runs"], 2)
        self.assertEqual(report["ceiling_share"], 0.5)
        self.assertIn("right-censored", report["detail"])

    def test_headroom_above_threshold_is_not_flagged(self):
        report = saturation_report(_study([0.97, 0.96, 0.95, 0.94]))
        self.assertTrue(report["available"])
        self.assertFalse(report["saturated"])
        self.assertEqual(report["ceiling_runs"], 0)

    def test_root_at_ceiling_is_counted_separately(self):
        report = saturation_report(_study([1.0, 1.0, 1.0, 0.9], roots=[1.0, 1.0, 1.0, 0.5]))
        self.assertEqual(report["root_ceiling_runs"], 3)

    def test_unbounded_scores_are_not_judged(self):
        report = saturation_report(_study([12.5, 11.0, 10.0, 9.0]))
        self.assertFalse(report["available"])
        self.assertFalse(report["saturated"])
        self.assertIn("not bounded", report["reason"])

    def test_study_without_runs_is_not_judged(self):
        report = saturation_report({})
        self.assertFalse(report["available"])
        self.assertEqual(report["reason"], "study has no scored runs")


class NormalizedCurveTest(unittest.TestCase):
    def test_normalized_auc_matches_a_hand_computed_curve(self):
        run = {
            "nodes": [
                {"evaluations": 1, "score": 0.5},
                {"evaluations": 2, "score": 0.6},
                {"evaluations": 3, "score": 0.8},
                {"evaluations": 4, "score": 1.0},
            ]
        }
        result = normalized_run(run)
        self.assertAlmostEqual(result["auc"], 0.6, places=6)
        self.assertAlmostEqual(result["gain"], 1.0, places=6)
        self.assertEqual(result["first_ceiling"], 4)
        self.assertEqual(result["evals_after_ceiling"], 0)

    def test_the_curve_is_exported_only_when_asked(self):
        run = {
            "nodes": [
                {"evaluations": 1, "score": 0.5},
                {"evaluations": 2, "score": 0.8},
                {"evaluations": 3, "score": 0.7},
            ]
        }
        plain = normalized_run(run)
        self.assertNotIn("curve", plain, "stored summaries must keep their shape by default")
        with_curve = normalized_run(run, include_curve=True)
        self.assertEqual(with_curve["auc"], plain["auc"], "asking for the curve must not move the number")
        self.assertEqual(
            with_curve["curve"],
            [
                {"evaluations": 1, "best": 0.5},
                {"evaluations": 2, "best": 0.8},
                {"evaluations": 3, "best": 0.8},
            ],
        )
        self.assertEqual(with_curve["root"], 0.5)
        self.assertEqual(len(with_curve["curve"]), len(run["nodes"]))

    def test_a_run_starting_at_the_ceiling_is_not_normalized(self):
        run = {"nodes": [{"evaluations": 1, "score": 1.0}, {"evaluations": 2, "score": 1.0}]}
        self.assertIsNone(normalized_run(run))

    def test_out_of_range_scores_are_not_normalized(self):
        run = {"nodes": [{"evaluations": 1, "score": 0.5}, {"evaluations": 2, "score": 2.0}]}
        self.assertIsNone(normalized_run(run))


class InteractionSensitivityTest(unittest.TestCase):
    def _study(self):
        curve = [
            {"evaluations": 1, "score": 0.5},
            {"evaluations": 2, "score": 0.6},
            {"evaluations": 3, "score": 0.8},
            {"evaluations": 4, "score": 1.0},
        ]
        raws = {
            (False, "off"): 0.1,
            (False, "negative"): 0.5,
            (True, "off"): 0.2,
            (True, "negative"): 0.3,
        }
        cells = []
        for (memory, archive), raw in raws.items():
            runs = [
                {
                    "seed": seed,
                    "improvement_per_evaluation": raw,
                    "nodes": [dict(node) for node in curve],
                }
                for seed in range(1, 5)
            ]
            cells.append({"memory": memory, "archive": archive, "runs": runs})
        return {"cells": cells}

    def test_raw_count_can_decide_while_the_curve_does_not_move(self):
        report = interaction_sensitivity(self._study())
        self.assertTrue(report["available"])
        self.assertAlmostEqual(report["raw"]["mean_interaction"], -0.3, places=6)
        self.assertTrue(report["raw"]["decidable"])
        self.assertAlmostEqual(report["normalized_auc"]["mean_interaction"], 0.0, places=6)
        self.assertFalse(report["normalized_auc"]["decidable"])
        self.assertEqual(report["complete_case_seeds"], 4)

    def test_a_design_without_four_cells_is_not_judged(self):
        report = interaction_sensitivity({"cells": []})
        self.assertFalse(report["available"])
        self.assertIn("no cells", report["reason"])
        partial = self._study()
        partial["cells"] = partial["cells"][:3]
        report = interaction_sensitivity(partial)
        self.assertFalse(report["available"])
        self.assertIn("2x2", report["reason"])

    def test_a_mixed_window_study_is_refused(self):
        study = self._study()
        study["cells"].append(
            {
                "memory": False,
                "archive": "recent",
                "archive_window": "recent",
                "runs": study["cells"][0]["runs"],
            }
        )
        study["cells"][0]["archive_window"] = "all"
        report = interaction_sensitivity(study)
        self.assertFalse(report["available"])
        self.assertIn("archive_window", report["reason"])


if __name__ == "__main__":
    unittest.main()

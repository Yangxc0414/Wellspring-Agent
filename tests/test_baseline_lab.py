"""The tuned reference must be budget-matched, paired, deterministic, and refuse when it cannot be."""

import copy
import json
import unittest

from research_agent.baseline_lab import (
    compare_with_study,
    fits_within_budget,
    grid_size,
    run_baseline,
    tune_one_dataset,
)


def _mini_study(budget: int) -> dict:
    return {
        "dataset": "iris",
        "budget": budget,
        "seeds": [1, 2],
        "cells": [
            {
                "cell_id": "memory_on_gate_on",
                "runs": [
                    {"seed": 1, "best_score": 0.97},
                    {"seed": 2, "best_score": 0.99},
                ],
            }
        ],
    }


class BaselineLabTest(unittest.TestCase):
    def test_fold_count_is_capped_by_the_study_budget(self):
        size = grid_size()
        self.assertEqual(fits_within_budget(size * 5), 5)
        self.assertEqual(fits_within_budget(size * 2 - 1), 1)
        self.assertEqual(fits_within_budget(size - 1), 0)

    def test_comparison_refuses_when_no_budget_matched_baseline_exists(self):
        with self.assertRaises(ValueError) as ctx:
            compare_with_study(_mini_study(grid_size() + 1))
        self.assertIn("cannot afford", str(ctx.exception))

    def test_paired_delta_and_budget_flag_on_a_real_dataset(self):
        result = compare_with_study(_mini_study(60))
        self.assertTrue(result["budget_matched"], result["baseline_fits_per_seed"])
        self.assertLessEqual(result["baseline_fits_per_seed"], 60)
        cell = result["cells"][0]
        self.assertEqual(cell["seeds_compared"], 2)
        first = cell["per_seed"][0]
        self.assertAlmostEqual(
            first["delta"],
            round(first["study_best_score"] - first["baseline_held_out"], 6),
            places=6,
        )
        self.assertIn("paired difference", result["boundary"])

    def test_seeds_absent_from_the_study_are_not_compared(self):
        result = compare_with_study(_mini_study(60), seeds=[1, 999])
        self.assertEqual(result["seeds"], [1])
        self.assertEqual(result["cells"][0]["seeds_compared"], 1)

    def test_the_reference_is_deterministic_per_seed(self):
        first = tune_one_dataset("iris", 3, folds=2)
        again = tune_one_dataset("iris", 3, folds=2)
        self.assertEqual(first, again)
        self.assertEqual(first["evaluations_spent"], grid_size() * 2)

    def test_unknown_dataset_is_rejected_before_any_fit(self):
        with self.assertRaises(ValueError):
            run_baseline(["mnist"], [1])


class ToMarkdownTableTest(unittest.TestCase):
    """The paper table is rendered from the artifact keys, so a column cannot lie about its source."""

    def _report(self, **overrides):
        interval = {"mean_diff": 0.02, "ci95_low": 0.01, "ci95_high": 0.03, "underpowered": False}
        cell = {
            "cell_id": "memory_on_gate_on",
            "seeds_compared": 24,
            "study_mean_best": 0.975926,
            "baseline_mean_held_out": 0.956482,
            "mean_delta": 0.019444,
            "paired_interval": interval,
            "seeds_where_study_wins": 12,
            "seeds_where_baseline_wins": 0,
            "seeds_tied": 12,
        }
        cell.update(overrides.pop("cell", {}))
        report = {
            "dataset": "iris",
            "folds": 3,
            "grid_size": 19,
            "baseline_fits_per_seed": 57,
            "study_budget": 60,
            "budget_matched": True,
            "cells": [cell],
        }
        report.update({key: value for key, value in overrides.items() if key != "cell"})
        return report

    def test_header_and_rows_share_one_column_spec(self):
        from research_agent.baseline_lab import to_markdown

        table = to_markdown([self._report()], title="# t")
        lines = [line for line in table["markdown"].split("\n") if line.startswith("|")]
        columns = len(table["columns"])
        self.assertEqual(len(lines), 3, "title row, separator and one data row")
        for line in lines:
            self.assertEqual(len(line.strip().strip("|").split("|")), columns)
        row = table["rows"][0]
        # the column named study_mean_best must carry the study score, not the opponent's
        self.assertEqual(row["study_mean_best"], 0.975926)
        self.assertEqual(row["baseline_mean_held_out"], 0.956482)
        self.assertIn("0.975926", table["markdown"])

    def test_absent_key_raises_instead_of_rendering_a_blank(self):
        from research_agent.baseline_lab import to_markdown

        broken = self._report(
            cell={"seeds_where_baseline_wins": None}
        )
        del broken["cells"][0]["seeds_where_baseline_wins"]
        with self.assertRaises(KeyError) as raised:
            to_markdown([broken])
        self.assertIn("study baseline", str(raised.exception))

    def test_missing_interval_is_not_reported_as_withheld_for_power(self):
        from research_agent.baseline_lab import to_markdown

        def data_row(table):
            return [line for line in table["markdown"].split("\n") if line.startswith("| iris")][0]

        uncomputed = to_markdown([self._report(cell={"paired_interval": None})])
        self.assertEqual(uncomputed["rows"][0]["ci95_low"], "not computed")
        self.assertNotIn("withheld", data_row(uncomputed))
        weak = to_markdown(
            [
                self._report(
                    cell={
                        "paired_interval": {
                            "mean_diff": 0.005,
                            "ci95_low": None,
                            "ci95_high": None,
                            "underpowered": True,
                        }
                    }
                )
            ]
        )
        self.assertEqual(weak["rows"][0]["ci95_low"], "withheld(low power)")
        self.assertNotIn("not computed", data_row(weak))

    def test_empty_report_set_is_an_error_not_an_empty_table(self):
        from research_agent.baseline_lab import to_markdown

        with self.assertRaises(ValueError):
            to_markdown([self._report(cells=[])])


class TrivialBaselineTest(unittest.TestCase):
    """The trivial rows an ACL design rubric asks for, and their accounting limits."""

    def test_values_are_bounded_and_cover_every_seed(self):
        from research_agent.baseline_lab import trivial_baselines

        result = trivial_baselines("iris", [1, 2, 3, 4])
        values = result["values"]
        self.assertEqual(sorted(values), ["majority_class", "random_label"])
        for name in values:
            row = values[name]
            self.assertEqual(row["n"], 4)
            self.assertTrue(0.0 <= row["mean"] <= 1.0, name)
            self.assertIsNone(row["std"]) if row["n"] == 1 else self.assertGreaterEqual(row["std"], 0.0)

    def test_majority_class_on_balanced_iris_is_the_chance_rate(self):
        from research_agent.baseline_lab import trivial_baselines

        row = trivial_baselines("iris", [1, 2, 3])["values"]["majority_class"]
        self.assertAlmostEqual(row["mean"], 1.0 / 3.0, places=6, msg="iris splits evenly across 3 classes")

    def test_the_note_refuses_to_present_trivial_rows_as_budget_matched(self):
        from research_agent.baseline_lab import TRIVIAL_BASELINE_NOTE, trivial_baselines

        self.assertIn("zero-fit", TRIVIAL_BASELINE_NOTE)
        self.assertIn("not budget-matched", TRIVIAL_BASELINE_NOTE)
        self.assertIn("single-feature", trivial_baselines("wine", [1])["note"])

if __name__ == "__main__":
    unittest.main()

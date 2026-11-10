"""The study signing brief is a projection: it may not invent a number or hide a refusal."""

import json
import re
import tempfile
import unittest
from pathlib import Path

from research_agent.search_lab import write_study_package
from research_agent.study_claims import build_study_brief, build_study_claim


def _decimal_tokens(text: str) -> set:
    return set(re.findall(r"[-+]?\d+\.\d+", text))


class StudyBriefLanguageTest(unittest.TestCase):
    """The brief's labels are switchable; its numbers, verdicts and hashes are not.

    Why this exists: a signing brief that only renders in Chinese is scored as mixed script by
    the English rubric packs (#51), so the decision document for an English submission used to
    disqualify itself. Language may change nothing but the labels.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self) -> Path:
        directory = self.root / "study"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 9)), budget=60)
        return directory

    def test_english_brief_carries_no_cjk_and_keeps_every_reading(self):
        directory = self._package()
        zh = build_study_brief(directory)
        en = build_study_brief(directory, language="en")
        self.assertEqual(len(set(re.findall(r"[^\x00-\x7F]", en["markdown"]))), 0, en["markdown"][:200])
        self.assertIn("Signable comparisons", en["markdown"])
        self.assertIn("Undecidable or refused comparisons", en["markdown"])
        for key in (
            "dataset",
            "seeds",
            "budget",
            "signable_comparisons",
            "refused_comparisons",
            "baseline_bound",
            "baseline_sha256",
            "origin_state",
            "reproduction_command",
        ):
            self.assertEqual(zh[key], en[key], key)

    def test_labels_are_the_only_difference_between_the_two_renderings(self):
        directory = self._package()
        from research_agent.study_claims import BRIEF_LABELS

        zh = build_study_brief(directory)["markdown"]
        en = build_study_brief(directory, language="en")["markdown"]
        for key in ("title", "signable_heading", "path_heading"):
            self.assertIn(BRIEF_LABELS["zh"][key].split("（")[0].split(":")[0], zh)
            self.assertNotIn(BRIEF_LABELS["zh"][key], en)
            self.assertIn(BRIEF_LABELS["en"][key], en)

    def test_unknown_language_is_refused_not_silently_defaulted(self):
        directory = self._package()
        with self.assertRaises(ValueError) as raised:
            build_study_brief(directory, language="fr")
        self.assertIn("unknown brief language", str(raised.exception))
        self.assertIn("zh/en", str(raised.exception))

    def test_script_share_moves_from_zh_to_latin_so_english_rubrics_stay_confident(self):
        from research_agent.skill_packs import _cjk_token_share, _dominant_script

        directory = self._package()
        zh = build_study_brief(directory)["markdown"]
        en = build_study_brief(directory, language="en")["markdown"]
        self.assertEqual(_dominant_script(_cjk_token_share(zh)), "zh")
        self.assertEqual(_dominant_script(_cjk_token_share(en)), "latin")


    def _write_prereg(self, directory: Path, why: str) -> None:
        (directory / "study-preregistration.json").write_text(
            json.dumps(
                {
                    "schema_version": "study-preregistration-0.1",
                    "question": "does the acceptance gate pay for itself",
                    "hypothesis": "the gate raises improvement per evaluation",
                    "analysis": "seed-paired comparison with a 95% interval",
                    "decision_rule": "only intervals excluding zero become assertions",
                    "design": {},
                    "seeds": [1, 2, 3, 4],
                    "budget": 20,
                    "dataset": "iris",
                    "baseline": {"kind": "external_file", "file": "tuned-baseline.json", "why": why},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def test_an_english_brief_discloses_fields_authored_in_another_script(self):
        # English labels do not make an artifact English: the plan text is quoted verbatim, and one
        # Chinese `baseline.why` line was measured at 22.8% CJK tokens — mixed script to a rubric.
        directory = self._package()
        self._write_prereg(directory, "主张要对抗同预算下调优过的强参照")

        brief = build_study_brief(directory, language="en")
        self.assertIn("Script disclosure", brief["markdown"])
        self.assertEqual(brief["foreign_script_fields"], ["preregistration.baseline.why"])
        self.assertIn("quoted verbatim", brief["markdown"])

    def test_an_english_prereg_keeps_the_english_brief_monolingual(self):
        directory = self._package()
        self._write_prereg(directory, "the opponent is a budget-matched tuned reference")

        brief = build_study_brief(directory, language="en")
        self.assertEqual(brief["foreign_script_fields"], [])
        self.assertNotIn("Script disclosure", brief["markdown"])
        self.assertEqual(len(set(re.findall(r"[^\x00-\x7F]", brief["markdown"]))), 0)


class StudyBriefTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self) -> Path:
        directory = self.root / "study"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 9)), budget=60)
        return directory

    def test_brief_projection_invents_no_numbers(self) -> None:
        directory = self._package()
        brief = build_study_brief(directory)
        package_text = json.dumps(
            [
                json.loads((directory / name).read_text(encoding="utf-8"))
                for name in ("study.json", "study-evidence.json", "study-spec.json")
            ],
            ensure_ascii=False,
        )
        invented = _decimal_tokens(brief["markdown"]) - _decimal_tokens(package_text)
        self.assertEqual(invented, set(), "the brief carried numbers the package does not contain")
        self.assertIn("可签署比较", brief["markdown"])
        self.assertIn("被判不可判定/拒绝的比较", brief["markdown"])
        self.assertIn("study search", brief["reproduction_command"])
        from research_agent.study_claims import comparison_verdicts

        evidence = json.loads((directory / "study-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(brief["signable_comparisons"] + brief["refused_comparisons"]),
            sorted(row["comparison"] for row in comparison_verdicts(evidence)),
            "the brief must show every comparison, not only the flattering ones",
        )
        self.assertIn("not a claim, not a signature", brief["boundary"])

    def test_reproduction_command_carries_the_recorded_parameters(self) -> None:
        directory = self._package()
        brief = build_study_brief(directory)
        command = brief["reproduction_command"]
        self.assertIn("--dataset iris", command)
        self.assertIn("--seeds 1,2,3,4,5,6,7,8", command)
        self.assertIn("--budget 60", command)

    def test_bound_baseline_is_reported_with_its_hash_and_cited_in_the_command(self) -> None:
        directory = self._package()
        report = self.root / "tuned.json"
        report.write_text(
            json.dumps(
                {
                    "schema_version": "tuned-baseline-comparison-0.1",
                    "dataset": "iris",
                    "study_budget": 60,
                    "folds": 3,
                    "grid_size": 19,
                    "baseline_fits_per_seed": 57,
                    "budget_matched": True,
                    "seeds": list(range(1, 9)),
                    "cells": [{"cell_id": "memory_on_gate_on", "mean_delta": 0.02}],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        build_study_claim(
            directory,
            "接受门控提高了单位验证算力的改进率",
            "checked the paired interval",
            "S5/search/iris",
            baseline_file=str(report),
        )
        brief = build_study_brief(directory)
        self.assertTrue(brief["baseline_bound"])
        self.assertEqual(len(brief["baseline_sha256"]), 64)
        self.assertIn("已在包内", brief["markdown"])
        self.assertIn("--baseline-file tuned-baseline.json", brief["reproduction_command"])

    def test_missing_package_is_an_error_not_an_empty_brief(self) -> None:
        with self.assertRaises(ValueError):
            build_study_brief(self.root / "absent")

    def test_output_flag_writes_the_markdown(self) -> None:
        directory = self._package()
        handle = self.root / "brief.md"
        brief = build_study_brief(directory, output=handle)
        self.assertEqual(handle.read_text(encoding="utf-8"), brief["markdown"])
        self.assertEqual(brief["output"], str(handle))


class ComparisonReadingTest(unittest.TestCase):
    """"positive" was being read as "the registered hypothesis held"; the sign needs its base."""

    def test_a_cell_positive_against_the_reference_says_beats_not_improves(self):
        from research_agent.study_claims import _comparison_reading

        reading = _comparison_reading(
            {"comparator": "memory_on_gate_on", "state": "positive"}, "memory_on_gate_on"
        )
        self.assertEqual(reading, "beats the declared reference cell")

    def test_an_interaction_contrast_is_never_called_a_win_or_loss_against_a_cell(self):
        # measured on the 128-seed iris package: the interaction row's comparator is
        # difference-of-differences, so "loses to the reference cell" would have been false text
        from research_agent.study_claims import _comparison_reading

        reading = _comparison_reading(
            {"comparator": "difference-of-differences", "state": "negative"}, "memory_on_gate_on"
        )
        self.assertNotIn("reference cell", reading)
        self.assertIn("difference-of-differences contrast, below zero", reading)

    def test_the_sign_is_tied_to_the_reference_the_package_declared(self):
        from research_agent.study_claims import _comparison_reading

        reading = _comparison_reading(
            {"comparator": "memory_off_gate_off", "state": "positive"}, "memory_on_gate_on"
        )
        self.assertNotIn("reference cell", reading)
        self.assertIn("memory_off_gate_off", reading)

    def test_undecidable_stays_undecidable(self):
        from research_agent.study_claims import _comparison_reading

        self.assertEqual(
            _comparison_reading({"comparator": "memory_on_gate_on", "state": "undecidable"}, "memory_on_gate_on"),
            "undecidable against the declared reference cell",
        )


class NonPrimaryDecidableTest(unittest.TestCase):
    """An empty signable list must not be read as "no effect" when another metric decided."""

    def _evidence(self):
        return {
            "primary_metric": "improvement_per_evaluation",
            "decomposition": {
                "contrasts_vs_reference": [
                    {
                        "cell_id": "memory_on_gate_off",
                        "paired_interval_best_score": {
                            "mean_diff": 0.02951, "ci95_low": 0.01685, "ci95_high": 0.04218,
                        },
                        "paired_interval_improvement_per_evaluation": {
                            "mean_diff": -0.01432, "ci95_low": -0.06303, "ci95_high": 0.03438,
                        },
                    }
                ]
            },
        }

    def test_only_the_secondary_metric_that_excludes_zero_is_surfaced(self):
        from research_agent.study_claims import _non_primary_decidable

        rows = _non_primary_decidable(self._evidence())
        self.assertEqual([r["metric"] for r in rows], ["best_score"])
        self.assertEqual(rows[0]["ci95"], [0.01685, 0.04218])

    def test_the_primary_metric_is_never_duplicated_into_the_secondary_list(self):
        from research_agent.study_claims import _non_primary_decidable

        evidence = self._evidence()
        evidence["decomposition"]["contrasts_vs_reference"][0][
            "paired_interval_improvement_per_evaluation"
        ] = {"mean_diff": 0.9, "ci95_low": 0.5, "ci95_high": 1.2}
        rows = _non_primary_decidable(evidence)
        self.assertNotIn("improvement_per_evaluation", [r["metric"] for r in rows])

    def test_a_crossing_secondary_interval_stays_invisible_as_a_finding(self):
        from research_agent.study_claims import _non_primary_decidable

        evidence = self._evidence()
        evidence["decomposition"]["contrasts_vs_reference"][0][
            "paired_interval_best_score"
        ] = {"mean_diff": 0.001, "ci95_low": -0.02, "ci95_high": 0.03}
        self.assertEqual(_non_primary_decidable(evidence), [])


if __name__ == "__main__":
    unittest.main()

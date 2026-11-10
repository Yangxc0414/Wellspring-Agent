"""The improvement-search study must be deterministic, hash-bound and honest about power."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.search_lab import (
    PROVENANCE_BOUNDARY,
    build_evidence_package,
    interaction_contrast,
    run_condition,
    run_study,
    study_profile_summary,
    write_study_package,
)


def _root_signature(run):
    """Signature of the root configuration: it changes iff the starting point changed."""
    root = (run.get("nodes") or [{}])[0]
    return str((root.get("config") or {}).get("signature") or "")


class DeclarativeDesignTests(unittest.TestCase):
    """The factor space is data now, so the checks that matter are validation and naming."""

    def test_unknown_factor_and_level_are_rejected(self):
        from research_agent.search_lab import normalize_design

        with self.assertRaises(ValueError) as caught:
            normalize_design({"temperature": [0.1, 0.5]}, 0.005)
        self.assertIn("unknown factor", str(caught.exception))
        self.assertIn("memory", str(caught.exception))
        with self.assertRaises(ValueError) as caught:
            normalize_design({"operators": ["randomize_everything"]}, 0.005)
        self.assertIn("unknown level", str(caught.exception))

    def test_wide_design_is_refused_rather_than_run(self):
        from research_agent.search_lab import MAX_DESIGN_CELLS, normalize_design

        wide = {
            "memory": [False, True],
            "gate": [False, True],
            "operators": sorted(["all", "feature_only", "knob_only", "no_switch", "classifier_only"]),
        }
        self.assertGreater(2 * 2 * len(wide["operators"]), MAX_DESIGN_CELLS)
        with self.assertRaises(ValueError) as caught:
            normalize_design(wide, 0.005)
        self.assertIn("the limit is", str(caught.exception))

    def test_default_design_keeps_the_legacy_cell_names(self):
        # Signed claims already cite these names; renaming them would break the record.
        study = run_study(dataset="iris", seeds=[1, 2, 3, 4], budget=15)
        self.assertEqual(
            [cell["cell_id"] for cell in study["cells"]],
            ["memory_off_gate_off", "memory_on_gate_off", "memory_off_gate_on", "memory_on_gate_on"],
        )
        self.assertEqual(study["reference_cell"], "memory_off_gate_off")
        self.assertTrue(interaction_contrast(study)["available"])

    def test_declared_operator_design_varies_only_what_was_asked(self):
        study = run_study(
            dataset="wine",
            seeds=[1, 2, 3, 4],
            budget=15,
            design={"operators": ["all", "feature_only"]},
        )
        ids = [cell["cell_id"] for cell in study["cells"]]
        self.assertEqual(
            ids, ["memory_off_gate_off_operators_all", "memory_off_gate_off_operators_feature_only"]
        )
        # The reference is the first declared level, and unvaried factors stay out of the name.
        self.assertEqual(study["reference_cell"], ids[0])
        self.assertEqual(study["decomposition"]["memory_x_gate_interaction"], None)
        self.assertIn("contrasts_vs_reference", study["decomposition"])
        self.assertFalse(interaction_contrast(study)["available"])
        self.assertEqual(
            interaction_contrast(study)["reason"],
            "design does not vary exactly two factors (found 1)",
        )

    def test_archive_without_gate_on_is_reported_inert(self):
        from research_agent.search_lab import archive_inert_warning

        self.assertIn(
            "inert",
            archive_inert_warning({"archive": ["off", "negative"], "gate": [False]}),
        )
        self.assertEqual(
            archive_inert_warning({"archive": ["off", "negative"], "gate": [True]}), ""
        )
        self.assertEqual(
            archive_inert_warning({"archive": ["off", "negative"], "gate": [False, True]}), ""
        )
        self.assertEqual(
            archive_inert_warning({"archive": ["off"], "gate": [False]}), ""
        )

    def test_conditional_interactions_report_each_window_and_the_three_way(self):
        from research_agent.search_lab import conditional_interactions

        def cell(memory, archive, window, value):
            return {
                "memory": memory,
                "archive": archive,
                "archive_window": window,
                "gate": True,
                "runs": [{"improvement_per_evaluation": value} for _ in range(4)],
            }

        study = {
            "design": {
                "memory": [False, True],
                "archive": ["off", "negative"],
                "archive_window": ["all", "recent"],
            },
            "cells": [
                cell(False, "off", "all", 0.0),
                cell(False, "negative", "all", 1.0),
                cell(True, "off", "all", 0.0),
                cell(True, "negative", "all", 0.0),
                cell(False, "off", "recent", 0.0),
                cell(False, "negative", "recent", 0.5),
                cell(True, "off", "recent", 0.0),
                cell(True, "negative", "recent", 0.0),
            ],
        }
        result = conditional_interactions(study)
        self.assertTrue(result["available"])
        self.assertEqual(result["levels"], ["all", "recent"])
        self.assertEqual(
            result["slices"]["all"]["mean_interaction"], -1.0
        )
        self.assertEqual(
            result["slices"]["recent"]["mean_interaction"], -0.5
        )
        self.assertEqual(
            result["three_way"]["mean_interaction"], 0.5
        )
        self.assertTrue(result["three_way"]["decidable"])
        from research_agent.study_claims import comparison_verdicts

        names = [
            row["comparison"]
            for row in comparison_verdicts({"conditional_interactions": result})
        ]
        self.assertIn("memory_x_archive_interaction@archive_window=all", names)
        self.assertIn("memory_x_archive_interaction@archive_window=recent", names)
        self.assertIn("memory_x_archive_x_archive_window_interaction", names)

    def test_memory_by_archive_interaction_uses_the_declared_levels(self):
        def cell(memory, archive, values):
            return {
                "memory": memory,
                "archive": archive,
                "runs": [{"improvement_per_evaluation": value} for value in values],
            }

        study = {
            "design": {"memory": [False, True], "archive": ["off", "negative"]},
            "cells": [
                cell(False, "off", [0.0, 0.0, 0.0, 0.0]),
                cell(False, "negative", [1.0, 1.0, 1.0, 1.0]),
                cell(True, "off", [0.0, 0.0, 0.0, 0.0]),
                cell(True, "negative", [0.0, 0.0, 0.0, 0.0]),
            ],
        }
        contrast = interaction_contrast(study)
        self.assertTrue(contrast["available"])
        self.assertEqual(contrast["name"], "memory_x_archive_interaction")
        self.assertEqual(contrast["factors"], ["memory", "archive"])
        self.assertEqual(contrast["levels"]["archive"], ["off", "negative"])
        self.assertEqual(contrast["mean_interaction"], -1.0)
        self.assertTrue(contrast["decidable"])

    def test_gate_threshold_can_be_the_varied_factor(self):
        study = run_study(
            dataset="iris", seeds=[1, 2], budget=12, design={"gate": [True], "min_delta": [0.005, 0.05]}
        )
        self.assertEqual(
            [cell["cell_id"] for cell in study["cells"]],
            ["memory_off_gate_on_min_delta_0_005", "memory_off_gate_on_min_delta_0_05"],
        )
        self.assertTrue(all(cell["gate"] for cell in study["cells"]))

    def test_profile_advertises_the_factor_space(self):
        profile = study_profile_summary()
        self.assertEqual(
            sorted(profile["factors"]),
            ["archive", "archive_window", "gate", "memory", "min_delta", "operators",
             "parent_selection", "root"],
        )
        self.assertIn("feature_only", profile["operator_sets"])
        self.assertIn("any declared factorial over the registered controls", profile["supports"])

    def test_paired_interval_reports_width_and_a_seed_cliff_free_informativeness(self):
        from research_agent.search_lab import _paired_diff_interval

        tight = _paired_diff_interval(
            [0.90 + 0.02 * index for index in range(24)],
            [0.90 + 0.01 * index for index in range(24)],
        )
        self.assertLess(tight["ci_width"], abs(tight["mean_diff"]))
        self.assertTrue(tight["informative"], tight)
        self.assertNotIn("reading", tight)

        wide = _paired_diff_interval(
            [0.5 + (1 if index % 2 else -1) * (index % 7) * 0.05 for index in range(24)],
            [0.5 + (1 if index % 3 else -1) * (index % 5) * 0.05 for index in range(24)],
        )
        if wide["mean_diff"]:
            self.assertGreater(wide["ci_width"], abs(wide["mean_diff"]))
            self.assertFalse(wide["informative"])
            self.assertIn("magnitude is not", wide["reading"])
        self.assertIn("seeds_for_80pct", wide)

    def test_varying_the_start_warns_that_the_rate_is_not_comparable(self):
        from research_agent.search_lab import run_study

        study = run_study(
            dataset="iris",
            seeds=[1, 2],
            budget=10,
            design={"memory": [True], "gate": [True], "root": ["random_subset", "all_features"]},
        )
        caveats = study["decomposition"].get("metric_caveats") or []
        self.assertTrue(any("not comparable across cells" in text for text in caveats))
        fixed = run_study(dataset="iris", seeds=[1, 2], budget=10)
        self.assertEqual(fixed["decomposition"].get("metric_caveats"), [])

        # the full 2x2 branch has to carry the same warning when the start also varies
        wide = run_study(
            dataset="iris",
            seeds=[1, 2],
            budget=8,
            design={
                "memory": [False, True],
                "gate": [False, True],
                "root": ["random_subset", "all_features"],
            },
        )
        caveats = wide["decomposition"].get("metric_caveats") or []
        self.assertTrue(any("not comparable across cells" in text for text in caveats),
                        "main-effect branch must not hide the non-comparability of the rate")

    def test_root_start_policy_keeps_the_incumbent_and_offers_a_full_feature_arm(self):
        from research_agent.search_lab import run_condition, run_study

        # declaring nothing must not rename or duplicate the incumbent cells
        default = run_study(dataset="iris", seeds=[1], budget=12)
        self.assertTrue(all("root" not in cell["cell_id"] for cell in default["cells"]))
        self.assertTrue(all(cell["runs"][0]["root_policy"] == "random_subset" for cell in default["cells"]))

        incumbent = run_condition(
            dataset="digits", seed=1, budget=12, archive=True, gate=True
        )
        full = run_condition(
            dataset="digits", seed=1, budget=12, archive=True, gate=True,
            root_policy="all_features",
        )
        # digits has 64 features, so a random subset and the full set are different starting
        # points; on a 4-feature set they can coincide, which is not a bug in the policy
        self.assertNotEqual(incumbent["root_score"], full["root_score"])
        self.assertNotEqual(_root_signature(incumbent), _root_signature(full))
        self.assertTrue(_root_signature(full))
        self.assertTrue(full["condition"].endswith("/root=all_features"))
        self.assertNotIn("root", incumbent["condition"])
        self.assertEqual(incumbent["controls"]["root_policy"], "random_subset")
        with self.assertRaises(ValueError):
            run_condition(
                dataset="iris", seed=1, budget=4, archive=False, gate=False,
                root_policy="everything",
            )

    def test_archive_factor_is_off_by_default_and_has_a_negative_arm(self):
        from research_agent.search_lab import run_condition, run_study

        default = run_study(dataset="iris", seeds=[1, 2], budget=20)
        self.assertTrue(all("archive" not in cell["cell_id"] for cell in default["cells"]))
        self.assertTrue(all(cell["archive"] == "off" for cell in default["cells"]))
        self.assertTrue(all(cell["archive_window"] == "all" for cell in default["cells"]))

        negative = run_condition(
            "iris", 1, 40, archive=True, gate=True, archive_mode="negative"
        )
        self.assertEqual(negative["archive"], "negative")
        self.assertIn("archive", negative["controls"])
        self.assertGreaterEqual(negative["archive_hits"], 0)
        if negative["archive_hits"]:
            self.assertIsNotNone(negative["archive_age_mean"])
        recent = run_condition(
            "iris", 1, 40, archive=True, gate=True,
            archive_mode="negative", archive_window="recent",
        )
        self.assertEqual(recent["archive_window"], "recent")
        self.assertIn("window=recent", recent["condition"])

    def test_cells_reveal_a_hypothesis_the_2x2_could_not_ask(self):
        # Restricting the operator space is a real question about search, and it has to run
        # through the same evidence path so its contrasts get intervals too.
        study = run_study(
            dataset="breast_cancer",
            seeds=[1, 2, 3, 4],
            budget=20,
            design={"operators": ["all", "classifier_only"]},
        )
        evidence = build_evidence_package(study)
        comparison = evidence["comparison"]["memory_off_gate_off_operators_classifier_only"]
        self.assertEqual(comparison["comparator"], "memory_off_gate_off_operators_all")
        self.assertEqual(
            set(comparison) >= {"mean_diff", "ci95_low", "ci95_high", "n", "underpowered"}, True
        )


class DatasetRegistryTests(unittest.TestCase):
    """Replication counts environments, so the registry is the only place they may live."""

    def test_four_public_environments_are_executable(self):
        from research_agent.search_lab import DATASETS

        profile = study_profile_summary()
        self.assertEqual(profile["datasets"], sorted(DATASETS))
        self.assertIn("digits", profile["datasets"])

    def test_the_fourth_environment_is_a_harder_landscape_not_another_easy_one(self):
        from research_agent.search_lab import DATASETS

        # agreement across four views of the same easy problem would be worth nothing
        self.assertEqual(DATASETS["digits"]["classes"], 10)


class IncumbentRegistryTests(unittest.TestCase):
    """`study_replication` drops fixed-at-incumbent factors, so incumbent must mean "old behaviour".

    If a factor's first level ever stops equaling the runner's default, an experiment that changed
    that control would silently merge with the pre-change packages, so this is checked against the
    runner's own signature instead of against a second hand-written constant.
    """

    def test_incumbent_level_equals_the_runner_default(self):
        import inspect

        from research_agent.search_lab import INCUMBENT_LEVEL, OPERATOR_SETS, SEARCH_FACTORS

        defaults = {
            name: parameter.default
            for name, parameter in inspect.signature(run_condition).parameters.items()
            if parameter.default is not inspect.Parameter.empty
        }
        shared = set(defaults) & set(SEARCH_FACTORS)
        self.assertTrue(shared)
        for factor in sorted(shared):
            if factor == "operators":
                # the registry names operator sets, the runner receives the tuple behind the name
                self.assertEqual(OPERATOR_SETS[INCUMBENT_LEVEL[factor]], defaults[factor], factor)
            else:
                self.assertEqual(INCUMBENT_LEVEL[factor], defaults[factor], factor)
        self.assertIn("parent_selection", shared)
        self.assertIn("min_delta", shared)

    def test_the_boolean_axes_incumbent_is_the_off_cell(self):
        from research_agent.search_lab import INCUMBENT_LEVEL

        # memory=off / gate=off is the loop as it behaved before either control existed
        self.assertIs(INCUMBENT_LEVEL["memory"], False)
        self.assertIs(INCUMBENT_LEVEL["gate"], False)


class SearchStudyTests(unittest.TestCase):
    def test_condition_is_deterministic_and_budget_bounded(self):
        first = run_condition("iris", seed=7, budget=12, archive=True, gate=True)
        second = run_condition("iris", seed=7, budget=12, archive=True, gate=True)
        self.assertEqual(first["nodes"], second["nodes"])
        self.assertEqual(first["evaluations"], 12)
        self.assertEqual(len(first["nodes"]), 12)

    def test_gate_reduces_accepted_count_without_memory(self):
        without_gate = run_condition("iris", seed=3, budget=25, archive=False, gate=False)
        with_gate = run_condition("iris", seed=3, budget=25, archive=False, gate=True)
        self.assertGreater(without_gate["accepted"], with_gate["accepted"])
        self.assertGreater(with_gate["gate_rejections"], 0)

    def test_archive_is_the_only_way_to_get_a_multi_generation_lineage(self):
        # Without an archive every proposal's parent is the root, so depth is structurally
        # capped at two; deeper lineages can only come from retained memory.
        no_memory = [
            run_condition("iris", seed=seed, budget=30, archive=False, gate=False)
            for seed in (2, 5, 9)
        ]
        with_memory = [
            run_condition("iris", seed=seed, budget=30, archive=True, gate=False)
            for seed in (2, 5, 9)
        ]
        self.assertTrue(all(item["lineage_depth"] <= 2 for item in no_memory))
        for item in no_memory:
            self.assertTrue(
                all(
                    node["parent_id"] in ("", "N000")
                    for node in item["nodes"]
                    if node["node_id"] != "N000"
                )
            )
        self.assertGreater(max(item["lineage_depth"] for item in with_memory), 2)

    def test_study_reports_both_main_effects_and_the_interaction(self):
        study = run_study(dataset="iris", seeds=[1, 2, 3], budget=15)
        self.assertEqual(len(study["cells"]), 4)
        for key in ("memory_main_effect", "gate_main_effect", "memory_x_gate_interaction"):
            self.assertIn(key, study["decomposition"])
        self.assertEqual(len(study["study_sha256"]), 64)
        self.assertTrue(study["analogue"])
        self.assertEqual(study["not_a_reproduction_of"], ["DGM", "SICA", "ACE", "SIFT"])
        self.assertIn("not a reproduction", study["boundary"])

    def test_evidence_envelope_matches_the_shape_the_writing_pack_consumes(self):
        study = run_study(dataset="wine", seeds=[1, 2, 3], budget=15)
        evidence = build_evidence_package(study)
        self.assertEqual(evidence["primary_metric"], "improvement_per_evaluation")
        for name in (
            "memory_off_gate_off",
            "memory_off_gate_on",
            "memory_on_gate_off",
            "memory_on_gate_on",
        ):
            metrics = evidence["metrics_summary"]["improvement_per_evaluation." + name]
            self.assertIn("mean", metrics)
            self.assertIn("std", metrics)
        for item in evidence["comparison"].values():
            for key in ("mean_diff", "ci95_low", "ci95_high"):
                self.assertIn(key, item)
        self.assertTrue(evidence["exploratory"])
        self.assertFalse(evidence["significance_claimed"])

    def test_writing_package_separates_supported_from_underpowered(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = write_study_package(
                Path(tmp) / "study", dataset="iris", seeds=[1, 2], budget=12
            )
            output = Path(result["output_dir"])
            for name in ("study-spec.json", "study.json", "study-evidence.json"):
                self.assertTrue((output / name).is_file(), name)
            payload = json.loads(
                (output / "study-evidence.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["study_spec_sha256"], result["hashes"]["spec"])
            self.assertEqual(payload["study_sha256"], result["hashes"]["study"])
            # two seeds cannot resolve any interval: the runner must say so rather than
            # letting a point estimate pass as a finding
            self.assertEqual(result["directional_supported"], [])
            self.assertEqual(len(result["interval_covers_zero"]), 3)
            self.assertEqual(payload["boundary"], PROVENANCE_BOUNDARY)

    def test_two_seeds_with_zero_within_pair_variance_cannot_look_decidable(self):
        # Two equal paired differences give zero variance, which collapses a t-interval onto
        # the point estimate: a fluke would otherwise be signed into a paper.
        from research_agent.search_lab import _paired_diff_interval

        outcome = _paired_diff_interval([0.9, 0.9], [0.5, 0.5])
        self.assertEqual(outcome["mean_diff"], 0.4)
        self.assertIsNone(outcome["ci95_low"])
        self.assertIsNone(outcome["ci95_high"])
        self.assertTrue(outcome["underpowered"])

    def test_underpowered_study_exposes_no_directional_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = write_study_package(
                Path(tmp) / "study", dataset="wine", seeds=[1, 2], budget=20
            )
        self.assertEqual(result["directional_supported"], [])
        self.assertTrue(result["underpowered"])
        self.assertEqual(len(result["interval_covers_zero"]), 3)

    def test_min_decision_seeds_is_declared_in_the_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = write_study_package(
                Path(tmp) / "study", dataset="iris", seeds=[1, 2, 3, 4], budget=15
            )
            payload = json.loads(
                (Path(result["output_dir"]) / "study-evidence.json").read_text(encoding="utf-8")
            )
        self.assertEqual(payload["min_decision_seeds"], 4)
        self.assertFalse(payload["underpowered"])

    def test_interaction_interval_matches_the_sign_of_the_point_estimate(self):
        # A mirrored difference-of-differences has the same magnitude and the opposite sign;
        # pinning it to the decomposition field is what stops an inverted conclusion.
        study = run_study(dataset="iris", seeds=[1, 2, 3, 4, 5, 6, 7, 8], budget=40)
        contrast = interaction_contrast(study)
        point = study["decomposition"]["memory_x_gate_interaction"]
        self.assertTrue(contrast["available"])
        self.assertEqual(contrast["mean_interaction"], point)
        self.assertLess(point, 0, "this design's memory x gate interaction is negative")

    def test_interaction_interval_is_withheld_when_underpowered(self):
        study = run_study(dataset="iris", seeds=[1, 2], budget=20)
        contrast = interaction_contrast(study)
        self.assertTrue(contrast["underpowered"])
        self.assertIsNone(contrast["ci95_low"])

    def test_profile_declares_what_it_cannot_test(self):
        profile = study_profile_summary()
        self.assertEqual(profile["id"], "search_factorial")
        self.assertIn("improvement per unit validation compute", profile["supports"])
        self.assertTrue(
            any("reproduction" in item for item in profile["does_not_support"]),
            "the profile must name its own external-validity limit",
        )



class PowerPlanningTest(unittest.TestCase):
    """An undecidable result must say how much more evidence the same design would need."""

    def test_estimate_follows_signal_to_noise(self):
        from research_agent.search_lab import seeds_for_80pct

        self.assertEqual(seeds_for_80pct([0.0, 1.0, 2.0]), 8)  # mean 1, sd 1 -> ~7.84 -> 8
        self.assertEqual(seeds_for_80pct([0.5, 0.5, 0.5]), 3)  # no spread: already exact
        self.assertIsNone(seeds_for_80pct([-1.0, 1.0]))  # no effect to power against
        self.assertIsNone(seeds_for_80pct([0.4]))  # too few seeds to estimate

    def test_estimate_is_never_below_the_seeds_already_run(self):
        from research_agent.search_lab import seeds_for_80pct

        self.assertGreater(seeds_for_80pct([0.0, 5.0, 10.0]), 3)

    def test_evidence_carries_the_estimate_and_its_boundary(self):
        from research_agent.search_lab import build_evidence_package, run_study

        study = run_study("iris", [1, 2, 3, 4], budget=12)
        evidence = build_evidence_package(study)
        for comparison in evidence["comparison"].values():
            self.assertIn("seeds_for_80pct", comparison)
            self.assertIn("not used by any gate", comparison["power_note"])

class TimingIsNotContentTest(unittest.TestCase):
    """Wall-clock is disclosure: a hash that covers seconds cannot be reproduced by re-running.

    Recorded before the fix: two runs of the same canary controls differed only in
    `elapsed_seconds` (0.098 against 0.094), so `study_sha256` differed, so `algorithm_canary()`
    disagreed with itself seconds apart, and `code.canary_stable` failed against a package the
    same code had just written. The reproducibility instrument was measuring the machine.
    """

    def _controls(self):
        from research_agent.search_lab import CANARY_CONTROLS, run_study

        return run_study(
            dataset=CANARY_CONTROLS["dataset"],
            seeds=list(CANARY_CONTROLS["seeds"]),
            budget=int(CANARY_CONTROLS["budget"]),
            design={key: list(value) for key, value in CANARY_CONTROLS["design"].items()},
        )

    def test_two_runs_of_the_same_controls_share_one_study_hash(self):
        first, second = self._controls(), self._controls()
        self.assertEqual(first["study_sha256"], second["study_sha256"])
        self.assertEqual(
            [cell["mean_improvement_per_evaluation"] for cell in first["cells"]],
            [cell["mean_improvement_per_evaluation"] for cell in second["cells"]],
        )
        self.assertTrue(
            all("elapsed_seconds" in cell for cell in first["cells"]),
            "timing stays disclosed; it is only excluded from the hashed view",
        )

    def test_algorithm_canary_reproduces_within_one_session(self):
        from research_agent.search_lab import algorithm_canary

        self.assertEqual(algorithm_canary(), algorithm_canary())

    def test_spec_hash_ignores_seconds_but_still_binds_libraries(self):
        from research_agent.search_lab import spec_sha256_of

        base = {"dataset": "iris", "environment": {"study_wall_seconds": 1.0, "sklearn": "1.3.2"}}
        slower = {"dataset": "iris", "environment": {"study_wall_seconds": 99.0, "sklearn": "1.3.2"}}
        other_lib = {"dataset": "iris", "environment": {"study_wall_seconds": 1.0, "sklearn": "1.4.0"}}
        self.assertEqual(spec_sha256_of(base), spec_sha256_of(slower))
        self.assertNotEqual(spec_sha256_of(base), spec_sha256_of(other_lib))

    def test_closure_of_a_fresh_package_fails_no_chain_identity_check(self):
        import tempfile

        from research_agent.search_lab import write_study_package
        from research_agent.study_closure import check_study_closure

        # What a package written by this code must never be blamed for: its own hashes, its own
        # fingerprint, or a canary that cannot reproduce. Whether it found a decidable comparison
        # is a research outcome, not a chain defect, so it is deliberately not asserted here.
        chain = (
            "spec.present",
            "study.present",
            "evidence.present",
            "study.bound_to_spec",
            "study.self_hash",
            "evidence.bound_to_study",
            "evidence.bound_to_spec",
            "evidence.self_hash",
            "code.unchanged",
            "code.canary_stable",
        )
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw) / "fresh"
            write_study_package(directory, dataset="iris", seeds=[1, 2, 3, 4], budget=20)
            report = check_study_closure(directory)
            status = {item["id"]: item["status"] for item in report["checks"]}
            broken = [name for name in chain if status.get(name) != "pass"]
            self.assertEqual(broken, [], "chain identity checks must pass for a fresh package: " + str(broken))


if __name__ == "__main__":
    unittest.main()

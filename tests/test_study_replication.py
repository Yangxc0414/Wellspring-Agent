"""Cross-dataset replication counts: what may and may not be called a replicated finding."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.study_replication import (
    build_replication_report,
    comparable_design,
    comparability_key,
    load_package,
    overturn_kind,
    write_replication_report,
)

DESIGN = {"memory": ["False", "True"], "gate": ["False", "True"]}


def _evidence(dataset, seeds, comparison):
    return {
        "dataset": dataset,
        "seeds": seeds,
        "budget": 60,
        "min_delta": 0.005,
        "primary_metric": "improvement_per_evaluation",
        "underpowered": len(seeds) < 4,
        "comparison": comparison,
        "interaction_inference": {},
    }


def _package(dataset, seeds=(1, 2, 3, 4), comparison=None):
    return {
        "directory": "STUDY-%s" % dataset,
        "dataset": dataset,
        "design": DESIGN,
        "metric": "improvement_per_evaluation",
        "budget": 60,
        "min_delta": 0.005,
        "seeds": len(seeds),
        "seed_set": list(seeds),
        "underpowered": len(seeds) < 4,
        "comparisons": [
            {
                "comparison": name,
                "comparator": "memory_off_gate_off",
                "mean_diff": item["mean_diff"],
                "ci95": [item["ci95_low"], item["ci95_high"]],
                "state": (
                    "positive"
                    if item["ci95_low"] > 0
                    else "negative"
                    if item["ci95_high"] < 0
                    else "undecidable"
                ),
            }
            for name, item in (comparison or {}).items()
        ],
    }


def _decided(diff):
    low, high = sorted((diff / 2, diff * 2))
    return {"mean_diff": diff, "ci95_low": low, "ci95_high": high}


def _crossing(diff):
    return {"mean_diff": diff, "ci95_low": -0.01, "ci95_high": 0.01}


class StatusTests(unittest.TestCase):
    def test_seed_scope_excludes_disjoint_seed_ranges(self):
        def package(dataset, seeds, diff):
            return _package(
                dataset,
                seeds=seeds,
                comparison={"memory_on_gate_off": _decided(diff)},
            )

        packages = [
            package("iris", (1, 2, 3, 4), 0.10),
            package("iris", (5, 6, 7, 8), 0.10),
            package("wine", (1, 2, 3, 4), 0.10),
            package("wine", (5, 6, 7, 8), 0.10),
        ]
        report = build_replication_report(
            Path("unused"), packages=packages, seed_scope=[1, 2, 3, 4]
        )
        group = report["replicated"][0]
        self.assertEqual(group["datasets"], ["iris", "wine"])
        self.assertEqual(sorted(group["packages"]), ["iris", "wine"])
        self.assertTrue(
            any("seed-scope excluded" in item for item in report["warnings"])
        )

    def test_agreement_needs_two_decidable_datasets(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", comparison={"memory_on_gate_off": _decided(0.12)}),
                _package("wine", comparison={"memory_on_gate_off": _decided(0.05)}),
            ],
        )
        result = report["replicated"][0]["comparisons"]["memory_on_gate_off"]
        self.assertEqual(result["status"], "consistent")
        self.assertEqual(result["direction"], "positive")
        self.assertEqual(result["decided_in"], ["iris", "wine"])
        self.assertTrue(result["generalizes"])

    def test_one_decidable_dataset_stays_an_anecdote(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", comparison={"memory_on_gate_off": _decided(0.12)}),
                _package("wine", comparison={"memory_on_gate_off": _crossing(0.03)}),
                _package("breast_cancer", comparison={"memory_on_gate_off": _crossing(-0.02)}),
            ],
        )
        result = report["replicated"][0]["comparisons"]["memory_on_gate_off"]
        self.assertEqual(result["status"], "one_dataset_decided")
        self.assertFalse(result["generalizes"])

    def test_opposite_decidable_signs_are_reported_as_conflict(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", comparison={"memory_on_gate_on": _decided(0.1)}),
                _package("wine", comparison={"memory_on_gate_on": _decided(-0.1)}),
            ],
        )
        result = report["replicated"][0]["comparisons"]["memory_on_gate_on"]
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["direction"], "")
        self.assertEqual(result["decided_in"], ["iris", "wine"])

    def test_undecided_group_reports_nothing_as_replicated(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", comparison={"memory_off_gate_on": _crossing(0.12)}),
                _package("wine", comparison={"memory_off_gate_on": _crossing(0.02)}),
            ],
        )
        result = report["replicated"][0]["comparisons"]["memory_off_gate_on"]
        self.assertEqual(result["status"], "undecided")
        self.assertEqual(result["decided_in"], [])

    def test_positive_point_estimate_crossing_zero_never_counts_as_agreement(self):
        # The failure mode this module exists to prevent: two datasets with the same positive
        # estimate but wide intervals must not read as "replicated".
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", comparison={"memory_on_gate_off": _crossing(0.9)}),
                _package("wine", comparison={"memory_on_gate_off": _crossing(0.9)}),
            ],
        )
        self.assertEqual(
            report["replicated"][0]["comparisons"]["memory_on_gate_off"]["status"], "undecided"
        )


class ComparabilityTests(unittest.TestCase):
    def test_different_budget_is_not_a_replication(self):
        first = _package("iris")
        second = dict(_package("wine"), budget=120)
        self.assertNotEqual(comparability_key(first), comparability_key(second))

    def test_seed_count_may_differ_but_is_surfaced(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", seeds=(1, 2, 3, 4, 5, 6, 7, 8), comparison={"a": _decided(0.1)}),
                _package("wine", seeds=(1, 2, 3, 4), comparison={"a": _decided(0.1)}),
            ],
        )
        self.assertEqual(len(report["replicated"]), 1)
        self.assertEqual(len(report["warnings"]), 1)
        self.assertIn("seed counts", report["warnings"][0])

    def test_same_dataset_at_two_powers_is_a_ladder_not_a_replication(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", seeds=(1, 2, 3, 4), comparison={"memory_on_gate_off": _decided(0.12)}),
                _package(
                    "iris",
                    seeds=tuple(range(1, 65)),
                    comparison={"memory_on_gate_off": _crossing(-0.01)},
                ),
            ],
        )
        self.assertEqual(report["replicated"], [])
        self.assertIn("seed counts", report["unreplicated"][0]["reason"])
        self.assertEqual(len(report["power_ladders"]), 1)
        overturned = report["overturned"]
        self.assertEqual(len(overturned), 1)
        self.assertEqual(overturned[0]["comparison"], "memory_on_gate_off")
        self.assertEqual(overturned[0]["decided_at"]["seeds"], 4)
        self.assertEqual(overturned[0]["at_higher_power"]["seeds"], 64)
        self.assertIn("crosses zero again", overturned[0]["reason"])

    def test_a_verdict_that_survives_more_power_is_not_overturned(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", seeds=(1, 2, 3, 4), comparison={"memory_on_gate_on": _decided(-0.29)}),
                _package(
                    "iris",
                    seeds=tuple(range(1, 65)),
                    comparison={"memory_on_gate_on": _decided(-0.09)},
                ),
            ],
        )
        self.assertEqual(report["overturned"], [])

    def test_same_dataset_at_the_same_power_tests_nothing(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                _package("iris", comparison={"memory_on_gate_off": _decided(0.12)}),
                _package("iris", comparison={"memory_on_gate_off": _decided(0.12)}),
            ],
        )
        self.assertEqual(report["overturned"], [])
        self.assertEqual(len(report["power_ladders"]), 1)
        self.assertIn("identical numbers", " ".join(report["warnings"]))
        # the agreement count must not be inflated by a re-run of the same data
        self.assertEqual(report["replicated"], [])


class DirectoryTests(unittest.TestCase):
    def _write(self, root, name, evidence):
        directory = Path(root) / "studies" / name
        directory.mkdir(parents=True)
        (directory / "study-spec.json").write_text(
            json.dumps({"design": DESIGN, "dataset": evidence["dataset"]}), encoding="utf-8"
        )
        (directory / "study-evidence.json").write_text(
            json.dumps(evidence), encoding="utf-8"
        )
        return directory

    def test_scans_real_packages_and_loads_verdicts_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(
                tmp,
                "STUDY-A",
                _evidence("iris", [1, 2, 3, 4], {"memory_on_gate_off": _decided(0.12)}),
            )
            self._write(
                tmp,
                "STUDY-B",
                _evidence("wine", [1, 2, 3, 4], {"memory_on_gate_off": _decided(0.07)}),
            )
            (Path(tmp) / "studies" / "NOT-A-STUDY").mkdir()
            report = build_replication_report(Path(tmp) / "studies")
            self.assertEqual(report["packages"], 2)
            loaded = load_package(Path(tmp) / "studies" / "STUDY-A")
            self.assertEqual(loaded["comparisons"][0]["state"], "positive")
            self.assertEqual(
                report["replicated"][0]["comparisons"]["memory_on_gate_off"]["status"],
                "consistent",
            )

    def test_missing_directory_is_empty_report(self):
        report = build_replication_report(Path("does-not-exist") / "studies")
        self.assertEqual(report["packages"], 0)
        self.assertEqual(report["replicated"], [])

    def test_report_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = build_replication_report(Path(tmp), packages=[_package("iris")])
            path = write_replication_report(report, Path(tmp) / "replication")
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["packages"], 1)


class ComparableDesignTests(unittest.TestCase):
    """Adding a factor to the registry must not retire the evidence written before it existed."""

    def _write(self, root, name, design, seeds, comparison):
        directory = Path(root) / "studies" / name
        directory.mkdir(parents=True)
        (directory / "study-spec.json").write_text(
            json.dumps({"design": design, "dataset": "iris"}), encoding="utf-8"
        )
        (directory / "study-evidence.json").write_text(
            json.dumps(_evidence("iris", seeds, comparison)), encoding="utf-8"
        )
        return directory

    def test_incumbent_fixed_factors_leave_the_key(self):
        labels = comparable_design(
            {
                "memory": ["False", "True"],
                "gate": ["False", "True"],
                "operators": ["all"],
                "min_delta": ["0.005"],
                "parent_selection": ["uniform"],
            }
        )
        self.assertEqual(labels, {"gate": ["False", "True"], "memory": ["False", "True"]})

    def test_a_control_that_left_its_incumbent_level_still_separates_experiments(self):
        incumbent = comparable_design({"memory": ["False", "True"], "operators": ["all"]})
        changed = comparable_design({"memory": ["False", "True"], "operators": ["feature_only"]})
        self.assertNotEqual(incumbent, changed)
        # an unknown factor is never dropped: with no incumbent there is nothing to compare against
        self.assertEqual(comparable_design({"new_axis": ["a"]}), {"new_axis": ["a"]})

    def test_new_factor_at_incumbent_keeps_the_same_comparability_key(self):
        before = _package("iris", comparison={"memory_on_gate_off": _decided(0.12)})
        after = dict(before, design=dict(before["design"], parent_selection=["uniform"]))
        left = dict(before, design=dict(before["design"], parent_selection=["best"]))
        self.assertEqual(comparability_key(before), comparability_key(after))
        self.assertNotEqual(comparability_key(before), comparability_key(left))

    def test_report_groups_across_the_registry_change_and_still_overturns(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_design = {
                "memory": ["False", "True"],
                "gate": ["False", "True"],
                "operators": ["all"],
                "min_delta": ["0.005"],
            }
            new_design = dict(old_design, parent_selection=["uniform"])
            self._write(tmp, "OLD-16", old_design, [1, 2, 3, 4], {"memory_on_gate_off": _decided(0.12)})
            self._write(
                tmp,
                "NEW-128",
                new_design,
                list(range(1, 129)),
                {"memory_on_gate_off": _crossing(-0.01)},
            )
            report = build_replication_report(Path(tmp) / "studies")
            self.assertEqual(report["packages"], 2)
            self.assertEqual(len(report["power_ladders"]), 1)
            self.assertEqual(
                [p["directory"] for p in report["power_ladders"][0]["packages"]],
                ["OLD-16", "NEW-128"],
            )
            self.assertEqual(
                [item["comparison"] for item in report["overturned"]], ["memory_on_gate_off"]
            )
            self.assertEqual(report["overturned"][0]["at_higher_power"]["directory"], "NEW-128")


    def test_the_arbiter_says_whether_it_reused_the_offered_seeds(self):
        nested = {"design": DESIGN, "dataset": "iris", "underpowered": False,
                  "metric": "m", "budget": 60, "min_delta": 0.005}
        low = dict(nested, directory="LOW", seeds=3, seed_set=[1, 2, 3],
                   comparisons=[{"comparison": "c", "state": "positive", "mean_diff": 0.1, "ci95": [0.02, 0.2]}])
        strong_nested = dict(nested, directory="HIGH", seeds=6, seed_set=[1, 2, 3, 4, 5, 6],
                             comparisons=[{"comparison": "c", "state": "undecidable", "mean_diff": 0.01,
                                           "ci95": [-0.05, 0.06]}])
        strong_fresh = dict(strong_nested, directory="FRESH", seed_set=[7, 8, 9, 10, 11, 12])
        report = build_replication_report(Path("unused"), packages=[low, strong_nested])
        item = report["overturned"][0]
        self.assertEqual(item["shared_seeds"], 3)
        self.assertFalse(item["arbiter_independent"])
        report = build_replication_report(Path("unused"), packages=[low, strong_fresh])
        item = report["overturned"][0]
        self.assertEqual(item["shared_seeds"], 0)
        self.assertTrue(item["arbiter_independent"])
        # a hand-built package without seed identity reports unknown, never "independent"
        report = build_replication_report(
            Path("unused"), packages=[dict(low, seed_set=None), dict(strong_nested, seed_set=None)]
        )
        self.assertIsNone(report["overturned"][0]["shared_seeds"])
        self.assertIsNone(report["overturned"][0]["arbiter_independent"])


    def test_the_arbiter_says_whether_it_bounds_the_claimed_size(self):
        self.assertEqual(
            overturn_kind("positive", 0.31, "negative", [-0.4, -0.1]), "sign_reversal"
        )
        self.assertEqual(
            overturn_kind("positive", 0.31, "undecidable", [-0.03, 0.19]), "effect_bounded"
        )
        self.assertEqual(
            overturn_kind("positive", 0.10, "undecidable", [-0.05, 0.20]),
            "arbiter_uninformative",
        )
        self.assertIsNone(overturn_kind("positive", 0.10, "undecidable", None))
        self.assertIsNone(overturn_kind("undecidable", None, "undecidable", [-0.05, 0.20]))

    def test_overturned_items_carry_the_bound_and_independence(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._write(
                tmp,
                "LOW",
                DESIGN,
                [1, 2, 3, 4],
                {"memory_on_gate_off": {"mean_diff": 0.31, "ci95_low": 0.12, "ci95_high": 0.5}},
            )
            self._write(
                tmp,
                "HIGH",
                DESIGN,
                list(range(5, 53)),
                {"memory_on_gate_off": {"mean_diff": 0.07, "ci95_low": -0.03, "ci95_high": 0.19}},
            )
            item = build_replication_report(Path(tmp) / "studies")["overturned"][0]
            self.assertEqual(item["overturn_kind"], "effect_bounded")
            self.assertEqual(item["claimed_effect"], 0.31)
            self.assertEqual(item["arbiter_bound"], 0.19)
            self.assertEqual(item["shared_seeds"], 0)
            self.assertTrue(item["arbiter_independent"])


class ScopeLabelTest(unittest.TestCase):
    """Headline counts must say which roots they cover, in both entry paths."""

    def test_explicit_packages_still_report_a_scope(self):
        # the first version only defined the scanned roots on the collect-from-disk path, so the
        # explicit-packages entry point raised NameError; a scope field that exists in one path
        # and not the other is a labelling bug, not a missing feature.
        import tempfile

        from research_agent.study_replication import build_replication_report

        with tempfile.TemporaryDirectory() as raw:
            studies = Path(raw) / "studies"
            studies.mkdir(parents=True)
            report = build_replication_report(studies, packages=[])
        self.assertEqual(report["scope"]["root_count"], 1)
        self.assertEqual(report["scope"]["packages"], 0)
        self.assertIsInstance(report["scope"]["packages_on_disk"], int)

    def test_sibling_mode_names_every_root_it_counted(self):
        import tempfile

        from research_agent.study_replication import build_replication_report

        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            own = base / "proj" / "studies"
            sibling = base / "other" / "studies"
            own.mkdir(parents=True)
            sibling.mkdir(parents=True)
            project_only = build_replication_report(own, siblings=False)
            with_siblings = build_replication_report(own, siblings=True)
        self.assertEqual(project_only["scope"]["root_count"], 1)
        self.assertEqual(with_siblings["scope"]["root_count"], 2)
        self.assertTrue(all(isinstance(key, str) for key in with_siblings["scope"]["packages_by_root"]))

    def test_counts_on_disk_and_after_deduplication_are_both_reported(self):
        import tempfile

        from research_agent.study_replication import build_replication_report

        with tempfile.TemporaryDirectory() as raw:
            studies = Path(raw) / "studies"
            studies.mkdir(parents=True)
            report = build_replication_report(studies, siblings=False)
        scope = report["scope"]
        self.assertLessEqual(scope["packages"], scope["packages_on_disk"])


class SecondaryMetricReplicationTest(unittest.TestCase):
    """A metric the replication count ignored decided 4/4 environments; the count said zero."""

    def _package_with_secondary(self, dataset, secondary):
        from research_agent.study_replication import _secondary_verdicts

        crossing = {"memory_on_gate_off": _crossing(0.03)}
        pkg = _package(dataset, comparison=crossing)
        evidence = _evidence(dataset, [1, 2, 3, 4], crossing)
        evidence["decomposition"] = {
            "contrasts_vs_reference": [
                {"cell_id": "memory_on_gate_off", "paired_interval_best_score": secondary}
            ]
        }
        pkg["secondary"] = _secondary_verdicts(evidence)
        return pkg

    def test_a_secondary_metric_gets_its_own_replication_count(self):
        decided = {"mean_diff": 0.0295, "ci95_low": 0.0168, "ci95_high": 0.0421}
        report = build_replication_report(
            Path("unused"),
            packages=[
                self._package_with_secondary("iris", decided),
                self._package_with_secondary("wine", {"mean_diff": 0.0113, "ci95_low": 0.0038, "ci95_high": 0.0188}),
            ],
        )
        group = report["replicated"][0]
        self.assertEqual(group["comparisons"]["memory_on_gate_off"]["status"], "undecided")
        secondary = group["secondary_metrics"]["best_score"]["memory_on_gate_off"]
        self.assertEqual(secondary["status"], "consistent")
        self.assertEqual(sorted(secondary["decided_in"]), ["iris", "wine"])
        self.assertTrue(secondary["generalizes"])

    def test_the_primary_being_undecided_is_called_out_as_a_two_metric_read(self):
        decided = {"mean_diff": 0.0295, "ci95_low": 0.0168, "ci95_high": 0.0421}
        report = build_replication_report(
            Path("unused"),
            packages=[
                self._package_with_secondary("iris", decided),
                self._package_with_secondary("wine", decided),
            ],
        )
        self.assertTrue(
            any("two separate replications" in str(item) for item in report["warnings"]),
            report["warnings"],
        )

    def test_a_crossing_secondary_interval_invents_no_replication(self):
        report = build_replication_report(
            Path("unused"),
            packages=[
                self._package_with_secondary("iris", {"mean_diff": 0.01, "ci95_low": -0.02, "ci95_high": 0.04}),
                self._package_with_secondary("wine", {"mean_diff": 0.01, "ci95_low": -0.02, "ci95_high": 0.04}),
            ],
        )
        group = report["replicated"][0]
        secondary = group["secondary_metrics"]["best_score"]["memory_on_gate_off"]
        self.assertEqual(secondary["decided_in"], [])
        self.assertFalse(secondary["generalizes"])
        self.assertFalse(any("two separate replications" in str(item) for item in report["warnings"]))

    def test_the_primary_metric_is_never_counted_twice(self):
        from research_agent.study_replication import _secondary_verdicts

        evidence = {
            "primary_metric": "improvement_per_evaluation",
            "decomposition": {
                "contrasts_vs_reference": [
                    {
                        "cell_id": "memory_on_gate_off",
                        "paired_interval_best_score": {"mean_diff": 0.03, "ci95_low": 0.01, "ci95_high": 0.05},
                        "paired_interval_improvement_per_evaluation": {
                            "mean_diff": 0.03, "ci95_low": 0.01, "ci95_high": 0.05,
                        },
                    }
                ]
            },
        }
        metrics = {row["metric"] for row in _secondary_verdicts(evidence)}
        self.assertEqual(metrics, {"best_score"})


class LockedSiblingTest(unittest.TestCase):
    def test_an_unreadable_directory_does_not_abort_the_sibling_scan(self):
        from unittest.mock import patch

        from research_agent.study_replication import sibling_studies_dirs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            studies = root / "proj" / "studies"
            studies.mkdir(parents=True)
            (root / "locked" / "studies").mkdir(parents=True)
            real_is_dir = Path.is_dir

            def flaky(self):
                if "locked" in str(self):
                    raise PermissionError("denied by the OS")
                return real_is_dir(self)

            with patch.object(Path, "is_dir", flaky):
                found = sibling_studies_dirs(studies)
            self.assertEqual(found, [studies])


if __name__ == "__main__":
    unittest.main()

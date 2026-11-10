"""Study findings reach a paper only through a decidable, signed, hash-bound claim."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.study_claims import (
    OVERTURNED,
    build_study_claim,
    decidable_assertions,
)
from research_agent.search_lab import write_study_package
from research_agent.storage import write_json_atomic


def _evidence(comparison, primary="improvement_per_evaluation", dataset="iris"):
    return {
        "dataset": dataset,
        "primary_metric": primary,
        "study_sha256": "a" * 64,
        "study_spec_sha256": "b" * 64,
        "evidence_sha256": "c" * 64,
        "seeds": [1, 2],
        "budget": 12,
        "decomposition": {"gate_main_effect": 0.1},
        "comparison": comparison,
    }


class DecidableAssertionTest(unittest.TestCase):
    def test_only_interval_decidable_comparisons_become_assertions(self):
        split = decidable_assertions(
            _evidence(
                {
                    "gate_on": {"mean_diff": 0.17, "ci95_low": 0.04, "ci95_high": 0.29, "comparator": "base"},
                    "memory_on": {"mean_diff": 0.06, "ci95_low": -0.03, "ci95_high": 0.16, "comparator": "base"},
                    "both": {"mean_diff": -0.05, "ci95_low": -0.14, "ci95_high": -0.004, "comparator": "base"},
                }
            ),
            "iris",
        )
        self.assertEqual(len(split["assertions"]), 2)
        self.assertEqual(len(split["rejected"]), 1)
        self.assertEqual(split["rejected"][0]["comparison"], "memory_on")
        self.assertIn("covers zero", split["rejected"][0]["reason"])
        directions = {item.comparator for item in split["assertions"]}
        self.assertEqual(directions, {">", "<"}, "a negative decidable effect must be signed as such")

    def test_missing_interval_is_rejected_not_guessed(self):
        split = decidable_assertions(
            _evidence({"gate_on": {"mean_diff": 0.2, "ci95_low": None, "ci95_high": None}}), "iris"
        )
        self.assertEqual(split["assertions"], [])
        self.assertEqual(split["rejected"][0]["reason"], "interval unavailable")

    def test_metric_name_carries_the_dataset_so_two_studies_do_not_collide(self):
        split = decidable_assertions(
            _evidence({"gate_on": {"mean_diff": 0.17, "ci95_low": 0.04, "ci95_high": 0.29}}, dataset="wine"),
            "wine",
        )
        # The metric names the comparison too, so two comparisons of one study never collide.
        self.assertIn(".wine.gate_on", split["assertions"][0].metric)


    def test_decidable_interaction_becomes_a_signable_assertion(self):
        # The study's real question is the interaction; if only main effects were signable,
        # the conclusion could not be claimed at all.
        split = decidable_assertions(
            _evidence_with_interaction(
                mean_interaction=-0.165, low=-0.233, high=-0.097
            ),
            "iris",
        )
        metrics = [item.metric for item in split["assertions"]]
        self.assertTrue(any("memory_x_gate_interaction" in item for item in metrics), metrics)
        interaction = next(
            item for item in split["assertions"] if "memory_x_gate_interaction" in item.metric
        )
        self.assertEqual(interaction.comparator, "<")
        self.assertEqual(interaction.observed, -0.165)

    def test_underpowered_interaction_is_refused_like_any_other_comparison(self):
        split = decidable_assertions(
            _evidence_with_interaction(mean_interaction=-0.16, low=None, high=None), "iris"
        )
        refused = {item["comparison"] for item in split["rejected"]}
        self.assertIn("memory_x_gate_interaction", refused)


def _evidence_with_interaction(mean_interaction, low, high):
    evidence = {
        "dataset": "iris",
        "primary_metric": "improvement_per_evaluation",
        "comparison": {
            "memory_off_gate_on": {"mean_diff": 0.17, "ci95_low": 0.04, "ci95_high": 0.29}
        },
        "interaction_inference": {
            "available": True,
            "mean_interaction": mean_interaction,
            "ci95_low": low,
            "ci95_high": high,
            "n": 64,
            "underpowered": low is None,
        },
    }
    return evidence


class StudyClaimDraftTest(unittest.TestCase):
    def _study(self, tmp: Path, seeds, budget: int = 12) -> Path:
        directory = tmp / "study"
        write_study_package(directory, dataset="iris", seeds=seeds, budget=budget)
        return directory

    def test_draft_is_unsigned_and_bound_to_three_distinct_hashes(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            directory = self._study(tmp, list(range(1, 9)), budget=60)
            result = build_study_claim(
                directory,
                "开启接受门控提高了单位验证算力的改进率",
                "checked the paired interval and the lineage log",
                "S5/search/iris",
            )
            self.assertEqual(result["status"], "draft")
            self.assertGreaterEqual(result["signable_assertions"], 1)
            draft = json.loads((directory / "claim-draft.json").read_text(encoding="utf-8"))
            self.assertEqual(draft["status"], "draft")
            self.assertEqual(draft["human_reason"], "checked the paired interval and the lineage log")
            refs = " ".join(draft["evidence_refs"])
            fragments = [part.split("#")[1] for part in draft["evidence_refs"]]
            self.assertEqual(len(set(fragments)), 3, refs)
            self.assertIn("study.json#", refs)
            self.assertIn("study-evidence.json#", refs)
            observed = [item["observed"] for item in draft["assertions"]]
            self.assertTrue(all(isinstance(value, float) for value in observed))
            self.assertEqual(
                draft["verification"]["signing_rule"],
                "only comparisons whose 95% interval excludes zero became assertions",
            )
            self.assertTrue(draft["verification"]["not_signable"])
            self.assertTrue(any("analogue" in item for item in draft["warnings"]))

    def test_nothing_decidable_refuses_to_produce_a_claim(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = self._study(Path(raw), [1, 2], budget=12)
            with self.assertRaises(ValueError) as raised:
                build_study_claim(directory, "x", "reason", "S5/search/iris")
        message = str(raised.exception)
        self.assertIn("nothing is signable", message)
        self.assertIn("narrow the claim", message)

    def test_missing_evidence_is_an_error_not_an_empty_claim(self):
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(ValueError):
                build_study_claim(Path(raw) / "absent", "x", "reason", "S5/search/iris")


class TunedBaselineBindingTests(unittest.TestCase):
    """A claim may bind the tuned external opponent: the copy is byte-exact or it is refused."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _study(self, dataset: str = "iris") -> Path:
        directory = self.root / "study"
        write_study_package(directory, dataset=dataset, seeds=list(range(1, 9)), budget=60)
        return directory

    def _report(self, dataset: str = "iris") -> Path:
        path = self.root / ("tuned-" + dataset + ".json")
        path.write_text(
            json.dumps(
                {
                    "schema_version": "tuned-baseline-comparison-0.1",
                    "dataset": dataset,
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
        return path

    def test_missing_baseline_refuses_before_writing_a_draft(self):
        directory = self._study()
        with self.assertRaises(ValueError) as raised:
            build_study_claim(
                directory,
                "x",
                "reason",
                "S5/search/iris",
                baseline_file=str(self.root / "absent.json"),
            )
        self.assertIn("no tuned baseline to bind", str(raised.exception))
        self.assertFalse((directory / "claim-draft.json").exists())

    def test_baseline_from_another_dataset_is_refused(self):
        directory = self._study()
        with self.assertRaises(ValueError) as raised:
            build_study_claim(
                directory, "x", "reason", "S5/search/iris",
                baseline_file=str(self._report("digits")),
            )
        self.assertIn("wrong opponent", str(raised.exception))

    def test_baseline_sharing_no_seed_is_refused(self):
        directory = self._study()
        path = self._report("iris")
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["seeds"] = [91, 92]
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError) as raised:
            build_study_claim(
                directory, "x", "reason", "S5/search/iris", baseline_file=str(path)
            )
        self.assertIn("shares no seed", str(raised.exception))

    def test_bound_baseline_is_stored_verbatim_and_hashed_into_the_claim(self):
        import hashlib

        from research_agent.study_claims import BASELINE_FILENAME

        directory = self._study()
        report = self._report()
        source_bytes = report.read_bytes()
        unbound = build_study_claim(directory, "同一句主张", "reason", "S5/search/iris")
        result = build_study_claim(
            directory, "同一句主张", "reason", "S5/search/iris", baseline_file=str(report)
        )
        self.assertTrue(result["tuned_baseline"]["bound"])
        stored = directory / BASELINE_FILENAME
        self.assertEqual(stored.read_bytes(), source_bytes)
        sha = hashlib.sha256(source_bytes).hexdigest()
        self.assertEqual(result["tuned_baseline"]["sha256"], sha)
        draft = json.loads((directory / "claim-draft.json").read_text(encoding="utf-8"))
        self.assertIn("%s#%s" % (BASELINE_FILENAME, sha[:12]), draft["evidence_refs"])
        self.assertEqual(draft["verification"]["baseline_sha256"], sha)
        digest = draft["verification"]["baseline_digest"]
        self.assertEqual(digest["baseline_fits_per_seed"], 57)
        self.assertEqual(digest["folds"], 3)
        self.assertTrue(digest["budget_matched"])
        self.assertTrue(
            any("tuned opponent" in item for item in draft["warnings"]), draft["warnings"]
        )
        self.assertNotEqual(unbound["claim_id"], result["claim_id"])

    def test_unbound_claim_keeps_the_pre_binding_hash_input(self):
        import hashlib

        directory = self._study()
        evidence = json.loads((directory / "study-evidence.json").read_text(encoding="utf-8"))
        statement = "接受门控提高了单位验证算力的改进率"
        result = build_study_claim(directory, statement, "reason", "S5/search/iris")
        expected = (
            "CLM-STUDY-"
            + hashlib.sha256(
                (statement + "iris" + str(evidence.get("study_sha256", ""))).encode("utf-8")
            ).hexdigest()[:10]
        )
        self.assertEqual(result["claim_id"], expected)
        draft = json.loads((directory / "claim-draft.json").read_text(encoding="utf-8"))
        self.assertFalse(any("tuned-baseline" in item for item in draft["evidence_refs"]))
        self.assertEqual(draft["verification"]["baseline_sha256"], "")
        self.assertEqual(draft["verification"]["baseline_digest"], {})
        self.assertTrue(
            any("no tuned baseline is bound" in item for item in draft["warnings"]),
            draft["warnings"],
        )


class GuardExperimentTests(unittest.TestCase):
    """The counterfactual arm shows what the guard blocked, and can never sign it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        weak = {
            "memory_on_gate_off": {"mean_diff": 0.12, "ci95_low": 0.05, "ci95_high": 0.19},
            "memory_off_gate_on": {"mean_diff": -0.09, "ci95_low": -0.15, "ci95_high": -0.03},
        }
        strong = {
            "memory_on_gate_off": {"mean_diff": -0.01, "ci95_low": -0.06, "ci95_high": 0.03},
            "memory_off_gate_on": {"mean_diff": -0.08, "ci95_low": -0.14, "ci95_high": -0.02},
        }
        self.weak = self._write("STUDY-W", 4, weak, "d" * 64)
        self.weak_alone = self._write(
            "STUDY-W2", 4, {"memory_on_gate_off": weak["memory_on_gate_off"]}, "e" * 64
        )
        self._write("STUDY-S", 64, strong, "f" * 64)

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name: str, seed_count: int, comparison: dict, spec_sha: str) -> Path:
        directory = self.root / "studies" / name
        directory.mkdir(parents=True)
        write_json_atomic(
            directory / "study-spec.json",
            {"design": {"memory": [False, True], "gate": [False, True]}, "dataset": "iris"},
        )
        write_json_atomic(
            directory / "study-evidence.json",
            {
                "dataset": "iris",
                "primary_metric": "improvement_per_evaluation",
                "study_spec_sha256": spec_sha,
                "seeds": list(range(1, seed_count + 1)),
                "budget": 60,
                "min_delta": 0.005,
                "decomposition": {"gate_main_effect": 0.1},
                "comparison": comparison,
                "interaction_inference": {},
                "underpowered": seed_count < 4,
            },
        )
        return directory

    def _claim(self, directory: Path, guard: bool, sign: bool = False):
        return build_study_claim(
            directory,
            statement="归档提升 iris 上的搜索效率",
            human_reason="对照实验记录",
            scope="E1/PILOT",
            sign=sign,
            use_replication_guard=guard,
        )

    def test_partial_overturn_keeps_the_surviving_assertion_and_records_the_blocked_one(self):
        result = self._claim(self.weak, True)
        self.assertEqual(result["signable_assertions"], 1)
        draft = json.loads((self.weak / "claim-draft.json").read_text(encoding="utf-8"))
        rejected = [item for item in draft["verification"]["not_signable"] if item.get("comparison")]
        blocked = [item for item in rejected if item["comparison"] == "memory_on_gate_off"]
        self.assertEqual(len(blocked), 1, rejected)
        self.assertEqual(blocked[0]["reason"], OVERTURNED)
        self.assertEqual(blocked[0]["detail"]["superseded_by"], "STUDY-S")
        self.assertTrue(draft["verification"]["replication"]["guard_enabled"])

    def test_full_overturn_refuses_the_guarded_claim_instead_of_signing_nothing(self):
        with self.assertRaises(ValueError) as refused:
            self._claim(self.weak_alone, True)
        message = str(refused.exception)
        self.assertIn("nothing here is signable", message)
        self.assertIn("memory_on_gate_off", message)

    def test_unguarded_arm_offers_the_overturned_assertion_but_still_reports_it(self):
        unguarded = self._claim(self.weak, False)
        self.assertEqual(unguarded["signable_assertions"], 2)
        draft = json.loads((self.weak / "claim-draft-unguarded.json").read_text(encoding="utf-8"))
        self.assertEqual(draft["status"], "draft")
        replication = draft["verification"]["replication"]
        self.assertFalse(replication["guard_enabled"])
        self.assertEqual(
            [item["comparison"] for item in replication["overturned"]], ["memory_on_gate_off"]
        )

    def test_unguarded_draft_lands_in_its_own_file_and_cannot_be_signed(self):
        result = self._claim(self.weak, False)
        self.assertTrue(result["claim_file"].endswith("claim-draft-unguarded.json"))
        self.assertFalse((self.weak / "claim-draft.json").exists())
        self.assertFalse((self.weak / "claim.json").exists())
        with self.assertRaises(ValueError) as refused:
            self._claim(self.weak, False, sign=True)
        self.assertIn("cannot produce a signed claim", str(refused.exception))

    def test_guarded_assertions_are_never_more_than_the_unguarded_ones(self):
        """The guard's invariant is containment, not severity: same pool, subset of assertions."""
        guarded = self._claim(self.weak, True)
        unguarded = self._claim(self.weak, False)
        kept = {item["metric"] for item in json.loads(
            (self.weak / "claim-draft.json").read_text(encoding="utf-8"))["assertions"]}
        offered = {item["metric"] for item in json.loads(
            (self.weak / "claim-draft-unguarded.json").read_text(encoding="utf-8"))["assertions"]}
        self.assertTrue(kept <= offered, (kept, offered))
        self.assertEqual(unguarded["signable_assertions"], len(offered))
        self.assertLess(len(kept), len(offered))

    def test_guarded_signing_still_refuses_a_package_whose_only_verdict_was_unreproduced(self):
        with self.assertRaises(ValueError):
            self._claim(self.weak_alone, True, sign=True)


if __name__ == "__main__":
    unittest.main()


class GridReportShapeTests(unittest.TestCase):
    """The grid path writes one schema with `datasets`; it must still be bindable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _study(self) -> Path:
        directory = self.root / "study"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 9)), budget=60)
        return directory

    def _grid_report(self, datasets) -> Path:
        path = self.root / "grid.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "tuned-baseline-0.1",
                    "datasets": list(datasets),
                    "seeds": list(range(1, 9)),
                    "folds": 3,
                    "per_dataset": {name: {"seeds": 8} for name in datasets},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def test_a_one_environment_grid_report_binds_like_the_paired_report(self):
        directory = self._study()
        result = build_study_claim(
            directory, "x", "reason", "S5/search/iris",
            baseline_file=str(self._grid_report(["iris"])),
        )
        self.assertTrue(result["tuned_baseline"]["bound"])

    def test_a_multi_environment_grid_report_is_refused_as_ambiguous(self):
        directory = self._study()
        with self.assertRaises(ValueError) as raised:
            build_study_claim(
                directory, "x", "reason", "S5/search/iris",
                baseline_file=str(self._grid_report(["iris", "wine"])),
            )
        self.assertIn("no single dataset", str(raised.exception))

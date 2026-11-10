"""An idea's plan must be executable, not just describable — and refusal must be loud."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.project import init_project
from research_agent.search_lab import spec_sha256_of
from research_agent.storage import read_json, write_json_atomic
from research_agent.study_from_idea import (
    StudyFromIdeaError,
    plan_to_controls,
    run_study_from_idea,
)


def _review(project: Path, run_id: str, plan: dict) -> None:
    directory = project / "runs" / run_id
    directory.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        directory / "innovation-review.json",
        {
            "schema_version": "innovation-review-0.2",
            "run_id": run_id,
            "selected_ideas": [
                {
                    "idea_id": "IDEA-01",
                    "title": "算子空间宽度是否改变门控的收益",
                    "mechanism": "限制变异算子集合会改变单位算力改进率",
                    "falsification": "两个算子档位的配对区间跨零",
                    "experiment_plan": plan,
                }
            ],
            "final_ideas": [],
        },
    )


class StudyFromIdeaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        init_project(self.project, "from-idea")

    def tearDown(self):
        self.tmp.cleanup()

    def test_executes_the_declared_design_and_binds_provenance(self):
        plan = {
            "profile": "search_factorial",
            "dataset": "wine",
            "baseline": "operators=all",
            "metric": "improvement_per_evaluation",
            "stopping_rule": "8 paired seeds",
            "design": {"gate": ["on"], "operators": ["all", "feature_only"]},
        }
        _review(self.project, "RUN-FROM-IDEA", plan)
        result = run_study_from_idea(
            self.project, "RUN-FROM-IDEA", "IDEA-01", seeds=[1, 2, 3, 4, 5, 6, 7, 8], budget=20
        )
        self.assertEqual(result["status"], "executed")
        directory = Path(result["study_dir"])
        self.assertTrue((directory / "study.json").is_file())
        origin = read_json(directory / "study-origin.json")
        self.assertEqual(origin["idea_id"], "IDEA-01")
        self.assertEqual(origin["experiment_plan"], plan)
        self.assertEqual(origin["falsification"], "两个算子档位的配对区间跨零")
        # The origin is bound to the spec it describes, so a swapped-in study is detectable.
        spec = read_json(directory / "study-spec.json")
        self.assertEqual(origin["study_spec_sha256"], spec_sha256_of(spec))
        self.assertEqual(origin["resolved_controls"]["design"]["operators"], ["all", "feature_only"])
        # Names come from the declared design, and only the varied factor is in them.
        names = sorted(result["comparison"])
        self.assertEqual(names, ["memory_off_gate_on_operators_feature_only"])
        self.assertFalse(result["underpowered"])

    def test_datasets_flag_runs_one_environment_per_package_and_keeps_provenance(self):
        plan = {
            "profile": "search_factorial",
            "dataset": "wine",
            "metric": "improvement_per_evaluation",
            "design": {"gate": ["on"], "operators": ["all", "feature_only"]},
        }
        _review(self.project, "RUN-MULTI-ENV", plan)
        result = run_study_from_idea(
            self.project,
            "RUN-MULTI-ENV",
            "IDEA-01",
            seeds=[1, 2, 3, 4],
            budget=20,
            datasets="iris,wine",
        )
        self.assertEqual(result["datasets"], ["iris", "wine"])
        self.assertEqual(len(result["studies"]), 2)
        self.assertIn("study replicate", result["next"])
        for item in result["studies"]:
            directory = Path(item["study_dir"])
            self.assertTrue((directory / "study.json").is_file())
            origin = read_json(directory / "study-origin.json")
            # the whole point: a cross-environment result stays traceable to the idea
            self.assertEqual(origin["idea_id"], "IDEA-01")
            self.assertEqual(origin["resolved_controls"]["dataset"], item["dataset"])

    def test_a_single_explicit_environment_is_not_written_to_the_plan_directory(self):
        plan = {
            "profile": "search_factorial",
            "dataset": "wine",
            "metric": "improvement_per_evaluation",
            "design": {"gate": ["on"], "operators": ["all", "feature_only"]},
        }
        _review(self.project, "RUN-ONE-ENV", plan)
        result = run_study_from_idea(
            self.project,
            "RUN-ONE-ENV",
            "IDEA-01",
            seeds=[1, 2, 3, 4],
            budget=20,
            datasets="iris",
        )
        self.assertEqual(Path(result["study_dir"]).name, "STUDY-IDEA-01-iris")
        self.assertFalse(
            (self.project / "studies" / "STUDY-IDEA-01" / "study.json").exists(),
            "an explicit environment must not overwrite the plan-dataset package",
        )

    def test_unknown_environment_is_refused_before_any_package_is_written(self):
        plan = {
            "profile": "search_factorial",
            "dataset": "wine",
            "metric": "improvement_per_evaluation",
            "design": {"gate": ["on"], "operators": ["all", "feature_only"]},
        }
        _review(self.project, "RUN-BAD-ENV", plan)
        with self.assertRaises(StudyFromIdeaError) as caught:
            run_study_from_idea(
                self.project, "RUN-BAD-ENV", "IDEA-01", seeds=[1, 2, 3, 4], datasets="iris,chemlab"
            )
        self.assertIn("chemlab", str(caught.exception))
        # the refusal names the registry, not a hardcoded trio
        self.assertIn("digits", str(caught.exception))
        self.assertFalse(
            (self.project / "studies" / "STUDY-IDEA-01-iris" / "study.json").is_file()
        )

    def test_plan_without_a_profile_is_refused(self):
        _review(self.project, "RUN-NO-PROFILE", {"dataset": "wine", "metric": "best_score"})
        with self.assertRaises(StudyFromIdeaError) as caught:
            run_study_from_idea(self.project, "RUN-NO-PROFILE", "IDEA-01", seeds=[1, 2, 3, 4])
        self.assertIn("not executable here", str(caught.exception))

    def test_plan_bound_to_another_profile_names_that_profile(self):
        plan = {
            "profile": "protocol_run",
            "dataset": "chemlab",
            "metric": "accuracy",
            "baseline": "seed 0",
            "stopping_rule": "5 seeds",
        }
        _review(self.project, "RUN-OTHER", plan)
        with self.assertRaises(StudyFromIdeaError) as caught:
            run_study_from_idea(self.project, "RUN-OTHER", "IDEA-01", seeds=[1, 2, 3, 4])
        self.assertIn("protocol_run", str(caught.exception))

    def test_dataset_refusal_names_every_registered_environment(self):
        from research_agent.search_lab import DATASETS
        from research_agent.study_from_idea import StudyFromIdeaError, plan_to_controls

        with self.assertRaises(StudyFromIdeaError) as refused:
            plan_to_controls(
                {
                    "profile": "search_factorial",
                    "executable": {"profile": "search_factorial"},
                    "dataset": "chemlab",
                }
            )
        for name in sorted(DATASETS):
            self.assertIn(name, str(refused.exception))

    def test_too_few_seeds_refused_before_anything_is_written(self):
        plan = {
            "profile": "search_factorial",
            "dataset": "iris",
            "metric": "best_score",
            "baseline": "memory_off_gate_off",
            "stopping_rule": "3 seeds",
            "design": {"memory": [False, True], "gate": [False, True]},
        }
        _review(self.project, "RUN-THIN", plan)
        with self.assertRaises(StudyFromIdeaError) as caught:
            run_study_from_idea(self.project, "RUN-THIN", "IDEA-01", seeds=[1, 2, 3])
        self.assertIn("at least 4 paired seeds", str(caught.exception))
        self.assertFalse((self.project / "studies" / "STUDY-IDEA-01" / "study.json").exists())

    def test_existing_study_is_not_overwritten_silently(self):
        plan = {
            "profile": "search_factorial",
            "dataset": "iris",
            "metric": "improvement_per_evaluation",
            "baseline": "memory_off_gate_off",
            "stopping_rule": "4 seeds",
            "design": {"memory": [False, True], "gate": [False, True]},
        }
        _review(self.project, "RUN-AGAIN", plan)
        run_study_from_idea(self.project, "RUN-AGAIN", "IDEA-01", seeds=[1, 2, 3, 4], budget=12)
        with self.assertRaises(StudyFromIdeaError) as caught:
            run_study_from_idea(self.project, "RUN-AGAIN", "IDEA-01", seeds=[1, 2, 3, 4], budget=12)
        self.assertIn("--force", str(caught.exception))

    def test_unknown_idea_lists_the_ids_that_exist(self):
        _review(self.project, "RUN-MISS", {"profile": "search_factorial", "dataset": "iris"})
        with self.assertRaises(StudyFromIdeaError) as caught:
            run_study_from_idea(self.project, "RUN-MISS", "IDEA-42", seeds=[1, 2, 3, 4])
        self.assertIn("IDEA-01", str(caught.exception))

    def test_raising_power_on_a_force_rerun_is_recorded(self):
        plan = {
            "profile": "search_factorial",
            "dataset": "iris",
            "metric": "improvement_per_evaluation",
            "baseline": "memory_off_gate_off",
            "stopping_rule": "4 seeds",
            "design": {"memory": [False, True], "gate": [False, True]},
        }
        _review(self.project, "RUN-ESCALATE", plan)
        run_study_from_idea(self.project, "RUN-ESCALATE", "IDEA-01", seeds=[1, 2, 3, 4], budget=12)
        same = run_study_from_idea(
            self.project,
            "RUN-ESCALATE",
            "IDEA-01",
            seeds=[1, 2, 3, 4],
            budget=12,
            force=True,
        )
        self.assertIsNone(same["revised_from"], "an identical re-run is not a design change")
        raised = run_study_from_idea(
            self.project,
            "RUN-ESCALATE",
            "IDEA-01",
            seeds=[1, 2, 3, 4, 5, 6, 7, 8],
            budget=12,
            force=True,
        )
        revised = raised["revised_from"]
        self.assertEqual(revised["changed"], ["seeds"])
        self.assertEqual(revised["previous_seeds"], 4)
        self.assertIn("must not be cited", revised["note"])
        origin = read_json(Path(raised["study_dir"]) / "study-origin.json")
        self.assertEqual(origin["revised_from"]["previous_seeds"], 4)

    def test_controls_translation_keeps_min_delta_declared_by_the_plan(self):
        controls = plan_to_controls(
            {
                "profile": "search_factorial",
                "dataset": "iris",
                "metric": "improvement_per_evaluation",
                "baseline": "memory_off_gate_off",
                "stopping_rule": "8 seeds",
                "min_delta": 0.02,
                "design": {"min_delta": ["0.02", "0.05"]},
            }
        )
        self.assertEqual(controls["min_delta"], 0.02)
        self.assertEqual(controls["design"]["min_delta"], ["0.02", "0.05"])

    def test_plan_naming_registered_factors_without_a_design_is_refused(self):
        with self.assertRaises(StudyFromIdeaError) as raised:
            plan_to_controls(
                {
                    "profile": "search_factorial",
                    "dataset": "breast_cancer",
                    "metric": "improvement_per_evaluation",
                    "baseline": "archive=negative + archive_window=all",
                    "stopping_rule": "32 seeds; archive_window=all|recent",
                }
            )
        self.assertIn("experiment_plan.design", str(raised.exception))

    def test_plan_with_a_design_runs_the_declared_factor_levels(self):
        controls = plan_to_controls(
            {
                "profile": "search_factorial",
                "dataset": "breast_cancer",
                "metric": "improvement_per_evaluation",
                "baseline": "archive=negative + archive_window=all",
                "stopping_rule": "32 seeds; all vs recent",
                "design": {"archive": ["negative"], "archive_window": ["all", "recent"]},
            }
        )
        self.assertEqual(controls["design"]["archive_window"], ["all", "recent"])
        self.assertEqual(controls["design"]["archive"], ["negative"])


class IdeaProvenanceBindingTest(unittest.TestCase):
    """A signed claim must name the idea its numbers were produced to test, or refuse."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name) / "STUDY-IDEA-07"
        self.directory.mkdir()
        write_json_atomic(
            self.directory / "study-spec.json",
            {"schema_version": "search-study-spec-0.3", "dataset": "iris", "seeds": [1, 2, 3, 4]},
        )
        write_json_atomic(
            self.directory / "study.json",
            {"study_sha256": "study-hash", "cells": [], "decomposition": {}},
        )
        write_json_atomic(
            self.directory / "study-evidence.json",
            {
                "dataset": "iris",
                "seeds": [1, 2, 3, 4],
                "budget": 60,
                "study_sha256": "study-hash",
                "study_spec_sha256": "spec-hash",
                "evidence_sha256": "evidence-hash",
                "primary_metric": "improvement_per_evaluation",
                "comparison": {
                    "memory_on_gate_on": {
                        "mean_diff": -0.09,
                        "ci95_low": -0.14,
                        "ci95_high": -0.04,
                        "comparator": "memory_off_gate_off",
                    }
                },
                "interaction_inference": {"available": False},
                "decomposition": {},
            },
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _bind_origin(self) -> None:
        from research_agent.search_lab import spec_sha256_of

        spec = read_json(self.directory / "study-spec.json")
        write_json_atomic(
            self.directory / "study-origin.json",
            {
                "schema_version": "study-origin-0.1",
                "idea_id": "IDEA-07",
                "idea_title": "门控与档案的交互",
                "falsification": "交互区间排除零则主张被支持",
                "study_spec_sha256": spec_sha256_of(spec),
            },
        )

    def test_bound_origin_becomes_a_fourth_evidence_reference(self):
        from research_agent.study_claims import build_study_claim

        self._bind_origin()
        result = build_study_claim(
            self.directory, "门控提高单位算力改进率", "checked the interval", "S5/prov"
        )
        claim = read_json(Path(result["claim_file"]))
        self.assertEqual(result["idea_provenance"]["state"], "bound")
        self.assertEqual(result["idea_provenance"]["idea_id"], "IDEA-07")
        self.assertEqual(len(claim["evidence_refs"]), 4)
        self.assertTrue(any("study-origin.json#" in ref for ref in claim["evidence_refs"]))
        self.assertEqual(claim["verification"]["idea_provenance"]["state"], "bound")
        self.assertFalse(
            any("no study-origin.json" in item for item in claim["warnings"]),
            "a bound idea must not carry the untraceable warning",
        )

    def test_absent_origin_drafts_but_says_it_is_untraceable(self):
        from research_agent.study_claims import build_study_claim

        result = build_study_claim(self.directory, "x", "reason", "S5/prov")
        claim = read_json(Path(result["claim_file"]))
        self.assertEqual(result["idea_provenance"]["state"], "absent")
        self.assertEqual(len(claim["evidence_refs"]), 3)
        self.assertTrue(any("no study-origin.json" in item for item in claim["warnings"]))

    def test_stale_origin_refuses_the_claim_and_blocks_closure(self):
        from research_agent.study_claims import build_study_claim
        from research_agent.study_closure import check_study_closure

        self._bind_origin()
        spec = read_json(self.directory / "study-spec.json")
        write_json_atomic(self.directory / "study-spec.json", dict(spec, seeds=[1, 2, 3, 4, 5]))

        with self.assertRaises(ValueError) as caught:
            build_study_claim(self.directory, "x", "reason", "S5/prov")
        self.assertIn("no longer describes this study", str(caught.exception))

        report = check_study_closure(self.directory)
        failed = [item["id"] for item in report["checks"] if item["status"] == "fail"]
        self.assertIn("origin.matches_study", failed)
        self.assertTrue(any(item.startswith("origin.matches_study") for item in report["unresolved"]))
        self.assertTrue(
            any("is stale" in item for item in report["warnings"]),
            "a diverged sidecar must not be reported as a missing one",
        )


class PreRegistrationAttributionTest(unittest.TestCase):
    """Idea attribution and pre-registration used to be reachable only on separate commands.

    Measured over the whole corpus: 27 packages carried `study-origin.json`, 26 carried
    `study-preregistration.json`, and **zero** carried both, because `study search` accepted
    `--preregistration` while `study from-idea` did not. The paper-shaped artifact — an idea that
    asked for a study, declared before the study ran — was unreachable through any command.
    """

    PLAN = {
        "profile": "search_factorial",
        "dataset": "wine",
        "baseline": "operators=all",
        "metric": "improvement_per_evaluation",
        "stopping_rule": "4 paired seeds",
        "design": {"gate": ["on"], "operators": ["all", "feature_only"]},
    }

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        init_project(self.project, "prereg-attribution")

    def tearDown(self):
        self.tmp.cleanup()

    def _plan_file(self, design, dataset, seeds, budget):
        handle = self.root / "plan.json"
        handle.write_text(
            json.dumps(
                {
                    "schema_version": "study-preregistration-0.1",
                    "question": "算子空间宽度是否改变门控在 wine 上的收益",
                    "hypothesis": "限制变异算子会降低单位算力改进率",
                    "analysis": "按种子配对比较并给出 95% 区间",
                    "decision_rule": "区间含 0 一律不签",
                    "design": design,
                    "seeds": seeds,
                    "budget": budget,
                    "dataset": dataset,
                    "baseline": {"kind": "none", "why": "只与研究内部参照格比较"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return handle

    def test_one_command_produces_both_attribution_and_pre_registration(self):
        from research_agent.study_closure import check_study_closure

        _review(self.project, "RUN-PREREG", self.PLAN)
        probe = run_study_from_idea(
            self.project, "RUN-PREREG", "IDEA-01", seeds=[1, 2, 3, 4], budget=12
        )
        # the plan declares the resolved design, so it is read back from a real run instead of guessed
        plan_file = self._plan_file(
            probe["design"], probe["dataset"], [1, 2, 3, 4], 12
        )
        result = run_study_from_idea(
            self.project,
            "RUN-PREREG",
            "IDEA-01",
            seeds=[1, 2, 3, 4],
            budget=12,
            output_root=self.root / "declared",
            preregistration=str(plan_file),
        )
        directory = Path(result["study_dir"])
        self.assertTrue(result["preregistered"])
        self.assertTrue((directory / "study-origin.json").is_file())
        self.assertTrue((directory / "study-preregistration.json").is_file())
        status = {item["id"]: item["status"] for item in check_study_closure(directory)["checks"]}
        self.assertEqual(status.get("origin.present"), "pass")
        self.assertEqual(status.get("preregistration.present"), "pass")
        self.assertEqual(status.get("preregistration.bound"), "pass")

    def test_a_plan_declared_for_another_dataset_is_refused_before_any_compute(self):
        _review(self.project, "RUN-PREREG-MISMATCH", self.PLAN)
        plan_file = self._plan_file({"gate": [True]}, "iris", [1, 2, 3, 4], 12)
        with self.assertRaises(ValueError) as raised:
            run_study_from_idea(
                self.project,
                "RUN-PREREG-MISMATCH",
                "IDEA-01",
                seeds=[1, 2, 3, 4],
                budget=12,
                output_root=self.root / "refused",
                preregistration=str(plan_file),
            )
        self.assertIn("does not match", str(raised.exception))
        refused = self.root / "refused"
        self.assertEqual(
            list(refused.glob("*/study.json")) if refused.is_dir() else [],
            [],
            "a plan that does not match the run must be refused before any compute is spent",
        )

    def test_one_plan_cannot_claim_several_datasets(self):
        _review(self.project, "RUN-PREREG-MULTI", self.PLAN)
        plan_file = self._plan_file({"gate": [True]}, "wine", [1, 2, 3, 4], 12)
        with self.assertRaises(StudyFromIdeaError) as raised:
            run_study_from_idea(
                self.project,
                "RUN-PREREG-MULTI",
                "IDEA-01",
                seeds=[1, 2, 3, 4],
                budget=12,
                datasets="wine,iris",
                preregistration=str(plan_file),
            )
        self.assertIn("one declared plan binds one dataset", str(raised.exception))


if __name__ == "__main__":
    unittest.main()


class PlanTestabilityTest(unittest.TestCase):
    """A plan whose hypothesis names only held-fixed controls must be refused before compute."""

    def test_a_plan_naming_only_fixed_controls_is_refused_before_it_runs(self):
        from research_agent.study_from_idea import StudyFromIdeaError, execute_study_plan

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan = {
            "profile": "search_factorial",
            "dataset": "iris",
            "baseline": "no archive, no gate",
            "metric": "improvement_per_evaluation",
            "stopping_rule": "8 paired seeds",
            "design": {"gate": ["on"], "memory": [False, True], "operators": ["all"]},
        }
        with self.assertRaises(StudyFromIdeaError) as raised:
            execute_study_plan(
                Path(tmp.name) / "study",
                plan,
                provenance={
                    "idea_id": "IDEA-99",
                    "hypothesis": "收窄变异算子空间会降低单位验证算力的改进率",
                    "falsification": "两个算子档位的配对区间跨零",
                },
                seeds=list(range(1, 9)),
                budget=40,
            )
        self.assertIn("cannot test its own hypothesis", str(raised.exception))
        self.assertFalse((Path(tmp.name) / "study" / "study.json").exists())

    def test_a_plan_naming_one_varied_and_one_fixed_control_runs_with_a_recorded_context(self):
        from research_agent.study_from_idea import execute_study_plan

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        plan = {
            "profile": "search_factorial",
            "dataset": "iris",
            "baseline": "no archive, no gate",
            "metric": "improvement_per_evaluation",
            "stopping_rule": "8 paired seeds",
            "design": {"gate": ["on"], "operators": ["all", "feature_only"]},
        }
        result = execute_study_plan(
            Path(tmp.name) / "study",
            plan,
            provenance={
                "idea_id": "IDEA-98",
                "hypothesis": "在开门控的条件下收窄算子空间会改变单位算力改进率",
                "falsification": "两个算子档位的配对区间跨零",
            },
            seeds=list(range(1, 9)),
            budget=40,
        )
        self.assertEqual(result["status"], "executed")
        self.assertEqual(len(result["warnings"]), 1)
        self.assertIn("context controls", result["warnings"][0])
        self.assertIn("gate", result["warnings"][0])

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.loop_ledger import _replication_action, build_loop_ledger
from research_agent.storage import write_json_atomic
from tests.writing_support import RUN_ID, make_writing_project


class LoopLedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_review_mode_marks_empirical_stages_skipped(self):
        project = make_writing_project(self.root, with_run=False)
        run = project / "runs" / RUN_ID
        for name in ("experiment.json", "design-audit.json"):
            path = run / name
            if path.is_file():
                path.unlink()
        write_json_atomic(run / "q0.json", {"status": "pass", "reason": "ok"})
        write_json_atomic(
            run / "synthesis-matrix.json",
            {
                "theme_count": 2,
                "themes": [
                    {"theme_id": "TH-01", "name": "A", "source_count": 2},
                    {"theme_id": "TH-02", "name": "B", "source_count": 2},
                ],
            },
        )
        write_json_atomic(
            run / "innovation-review.json",
            {"iterations": [{"overall": 5.0}, {"overall": 6.0}]},
        )
        review_dir = run / "manuscript-review-v2"
        review_dir.mkdir()
        write_json_atomic(
            review_dir / "manuscript-review.json",
            {
                "score_progression": [6.0, 6.5],
                "accepted_revisions": 1,
                "status": "needs_more_work",
                "best_score": 6.5,
            },
        )
        result = build_loop_ledger(project, RUN_ID)
        self.assertEqual(result["mode"], "review")
        stages = {item["stage_id"]: item for item in result["stages"]}
        self.assertEqual(stages["S1"]["status"], "done")
        self.assertEqual(stages["S1b"]["status"], "done")
        self.assertEqual(stages["S2-S3"]["status"], "done")
        self.assertEqual(stages["S4"]["status"], "skipped_review_mode")
        self.assertEqual(stages["S5"]["status"], "skipped_review_mode")
        self.assertEqual(stages["S5b"]["status"], "skipped_review_mode")
        gates = {item["gate"]: item["status"] for item in result["gates"]}
        self.assertEqual(gates["Q0"], "pass")
        self.assertEqual(gates["G1"], "skipped_review_mode")
        self.assertTrue(
            any("manuscript-review-v2" in item for item in stages["S8-S12"]["artifacts"])
        )
        self.assertEqual(result["iterations"]["manuscript_scores"], [6.0, 6.5])
        self.assertEqual(result["iterations"]["synthesis_themes"], 2)
        self.assertTrue((run / "research-loop.json").is_file())
        self.assertTrue((run / "research-loop.md").is_file())

    def test_empirical_mode_reports_run_and_pending_claim(self):
        project = make_writing_project(self.root, signed=False)
        run = project / "runs" / RUN_ID
        write_json_atomic(
            run / "q0.json",
            {"status": "pass", "reason": "ok"},
        )
        result = build_loop_ledger(project, RUN_ID)
        self.assertEqual(result["mode"], "empirical")
        stages = {item["stage_id"]: item for item in result["stages"]}
        self.assertEqual(stages["S5"]["status"], "done")
        self.assertEqual(stages["S5b"]["status"], "needs_human")
        gates = {item["gate"]: item["status"] for item in result["gates"]}
        self.assertEqual(gates["S5b"], "needs_human")
        self.assertTrue(
            any(item.get("kind") == "human_gate" for item in result["next_actions"])
        )

    def test_missing_synthesis_is_a_next_action(self):
        project = make_writing_project(self.root)
        result = build_loop_ledger(project, RUN_ID)
        self.assertTrue(
            any(item.get("kind") == "synthesis" for item in result["next_actions"])
        )


def make_study_project(root: Path, idea_id: str = "IDEA-07") -> Path:
    """A run whose review selected one idea bound to the executable search profile."""
    project = make_writing_project(root)
    plan = {
        "profile": "search_factorial",
        "dataset": "iris",
        "baseline": "memory_off_gate_off",
        "metric": "improvement_per_evaluation",
        "stopping_rule": "8 paired seeds",
    }
    write_json_atomic(
        project / "runs" / RUN_ID / "innovation-review.json",
        {
            "schema_version": "innovation-review-0.2",
            "run_id": RUN_ID,
            "selected_ideas": [
                {
                    "idea_id": idea_id,
                    "title": "算子空间宽度",
                    "falsification": "配对区间跨零则被否证",
                    "experiment_plan": plan,
                }
            ],
            "final_ideas": [],
        },
    )
    return project


class StudyActionTests(unittest.TestCase):
    """An executable idea must surface as the next step, and a non-result must say so."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _project(self, idea_id: str = "IDEA-07") -> Path:
        return make_study_project(self.root, idea_id)

    def test_missing_package_points_at_the_cli_instead_of_running_it(self):
        result = build_loop_ledger(self._project(), RUN_ID)
        action = next(
            item for item in result["next_actions"] if item.get("kind") == "study_execution"
        )
        self.assertEqual(action["idea_id"], "IDEA-07")
        self.assertIn("study from-idea", action["command"])
        self.assertNotIn("claim", action["command"])
        self.assertIn("no study package exists yet", action["message"])

    def test_executed_study_without_a_finding_is_reported_as_a_non_result(self):
        project = self._project()
        package = project / "studies" / "STUDY-IDEA-07"
        (package / "study.json").parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(package / "study.json", {"study_sha256": "x"})
        write_json_atomic(
            package / "study-evidence.json",
            {
                "comparison": {
                    "memory_on_gate_on": {"mean_diff": 0.02, "ci95_low": -0.05, "ci95_high": 0.09}
                }
            },
        )
        result = build_loop_ledger(project, RUN_ID)
        action = next(
            item for item in result["next_actions"] if item.get("kind") == "study_no_finding"
        )
        self.assertEqual(action["decidable_comparisons"], [])
        self.assertIn("non-result", action["message"])
        # a non-result must not be handed a signature command: the projection has to be
        # no more encouraging than the evidence it reads
        self.assertFalse(action["claimable"])
        self.assertNotIn("study claim", action["command"])
        self.assertIn("study replicate", action["command"])
        self.assertIn("No claim command is offered", action["message"])
        self.assertNotIn("study_execution", [item.get("kind") for item in result["next_actions"]])

    def test_decidable_study_moves_the_caller_to_the_claim_gate(self):
        project = self._project("IDEA-08")
        package = project / "studies" / "STUDY-IDEA-08"
        package.mkdir(parents=True)
        write_json_atomic(package / "study.json", {"study_sha256": "x"})
        write_json_atomic(
            package / "study-evidence.json",
            {
                "comparison": {
                    "memory_on_gate_on": {"mean_diff": -0.12, "ci95_low": -0.2, "ci95_high": -0.04}
                }
            },
        )
        result = build_loop_ledger(project, RUN_ID)
        action = next(
            item
            for item in result["next_actions"]
            if item.get("kind") == "human_gate" and item.get("idea_id") == "IDEA-08"
        )
        self.assertEqual(action["idea_id"], "IDEA-08")
        self.assertIn("study claim", action["command"])
        self.assertTrue(action["claimable"])
        self.assertEqual(action["decidable_comparisons"], ["memory_on_gate_on"])

    def test_a_signed_package_stops_nagging(self):
        project = self._project("IDEA-09")
        package = project / "studies" / "STUDY-IDEA-09"
        package.mkdir(parents=True)
        write_json_atomic(package / "study.json", {"study_sha256": "x"})
        write_json_atomic(package / "claim-draft.json", {"status": "draft"})
        result = build_loop_ledger(project, RUN_ID)
        self.assertFalse(
            any(
                item.get("idea_id") == "IDEA-09"
                for item in result["next_actions"]
                if "study" in str(item.get("kind"))
            ),
            "an idea whose study already has a claim draft must not be repeated",
        )


class ReplicationActionTests(unittest.TestCase):
    """A single-dataset design must be named as unreplicated, and stop nagging once it isn't."""

    DESIGN = {"memory": [False, True], "gate": [False, True], "min_delta": [0.005]}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self, name: str, dataset: str) -> Path:
        package = self.root / "studies" / name
        package.mkdir(parents=True)
        write_json_atomic(package / "study-spec.json", {"design": self.DESIGN, "dataset": dataset})
        write_json_atomic(
            package / "study-evidence.json",
            {
                "dataset": dataset,
                "budget": 60,
                "seeds": [1, 2, 3, 4],
                "primary_metric": "improvement_per_evaluation",
                "comparison": {
                    "memory_on_gate_off": {"mean_diff": 0.12, "ci95_low": 0.05, "ci95_high": 0.19}
                },
            },
        )
        return package

    def _evidence(self, package: Path) -> dict:
        return json.loads((package / "study-evidence.json").read_text(encoding="utf-8"))

    def test_one_dataset_names_the_dataset_that_would_test_it(self):
        package = self._package("STUDY-IDEA-09", "iris")
        actions = _replication_action(self.root, package, self._evidence(package))
        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["kind"], "study_replication")
        self.assertEqual(action["datasets_present"], ["iris"])
        self.assertIn("breast_cancer", action["datasets_untried"])
        self.assertIn("--dataset breast_cancer", action["command"])
        self.assertIn("study replicate", action["command"])
        # multi-level factors only, so a single-level factor never becomes a command flag
        self.assertIn("--factors memory=False,True", action["command"])
        self.assertNotIn("--factors min_delta", action["command"])
        self.assertIn("says nothing about whether the effect generalises", action["message"])

    def test_silence_once_a_second_dataset_runs_the_same_design(self):
        first = self._package("STUDY-IDEA-09", "iris")
        second = self._package("STUDY-IDEA-10", "wine")
        evidence = self._evidence(first)
        self.assertEqual(_replication_action(self.root, first, evidence), [])
        self.assertEqual(_replication_action(self.root, second, evidence), [])

    def test_a_package_without_a_declared_design_gets_no_advice(self):
        package = self.root / "studies" / "STUDY-IDEA-11"
        package.mkdir(parents=True)
        write_json_atomic(package / "study-evidence.json", {"dataset": "iris", "comparison": {}})
        self.assertEqual(_replication_action(self.root, package, {"dataset": "iris"}), [])


    def test_a_higher_power_study_removes_the_signable_suggestion(self):
        from research_agent.loop_ledger import _overturned_comparisons

        weak = self._package("STUDY-IDEA-12", "iris")
        strong = self._package("STUDY-IDEA-13", "iris")
        # same design, same dataset, more seeds: the positive verdict no longer excludes zero
        for package, seeds in ((weak, [1, 2, 3, 4]), (strong, list(range(1, 65)))):
            evidence = json.loads((package / "study-evidence.json").read_text(encoding="utf-8"))
            evidence["seeds"] = seeds
            evidence["comparison"]["memory_on_gate_off"] = (
                {"mean_diff": 0.12, "ci95_low": 0.05, "ci95_high": 0.19}
                if package is weak
                else {"mean_diff": -0.014, "ci95_low": -0.063, "ci95_high": 0.034}
            )
            write_json_atomic(package / "study-evidence.json", evidence)
        self.assertEqual(_overturned_comparisons(self.root, weak), ["memory_on_gate_off"])
        self.assertEqual(_overturned_comparisons(self.root, strong), [])


    def test_multi_environment_packages_count_as_this_idea_being_executed(self):
        from research_agent.loop_ledger import _idea_package

        first = self._package("STUDY-IDEA-20-iris", "iris")
        second = self._package("STUDY-IDEA-20-wine", "wine")
        for package in (first, second):
            write_json_atomic(package / "study.json", {"study_sha256": "x"})
        # the environment the idea declared is preferred, otherwise the first sibling
        self.assertEqual(_idea_package(self.root, "IDEA-20", "wine").name, "STUDY-IDEA-20-wine")
        self.assertEqual(_idea_package(self.root, "IDEA-20", "nothing").name, "STUDY-IDEA-20-iris")
        self.assertIsNone(_idea_package(self.root, "IDEA-21", "iris"))


class McpNextActionSurfaceTests(unittest.TestCase):
    """research_next_actions is what a host agent reads; the study step has to appear there."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_study_execution_reaches_the_mcp_action_list(self):
        from research_agent.mcp_server import ResearchMCPService

        project = make_study_project(self.root, "IDEA-11")
        write_json_atomic(
            project / "runs" / RUN_ID / "task.json",
            {
                "status": "completed",
                "stopped_at": "G1",
                "task_type": "hypothesis_design",
                "plan": {"goal": "算子空间与门控", "route": "hypothesis_design"},
                "artifacts": {},
            },
        )
        service = ResearchMCPService(self.root)
        response = service.next_actions(
            {"project_dir": str(project), "run_id": RUN_ID}
        )
        self.assertFalse(response.get("isError"), response)
        actions = response["structuredContent"]["next_actions"]
        study = [item for item in actions if item.get("kind") == "study_execution"]
        self.assertEqual([item["idea_id"] for item in study], ["IDEA-11"])
        self.assertIn("study from-idea", study[0]["command"])


class StudyGuidanceBaselineTest(unittest.TestCase):
    """The claim command the ledger hands a human must carry the opponent and the caveats."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name) / "proj"
        self.package = self.project / "studies" / "STUDY-IDEA-01"
        self.package.mkdir(parents=True)
        write_json_atomic(
            self.package / "study.json",
            {
                "dataset": "iris",
                "seeds": [1, 2, 3, 4],
                "budget": 60,
                "design": {"memory": [False, True], "gate": [False, True]},
                "study_sha256": "a" * 64,
            },
        )
        self.evidence = {
            "dataset": "iris",
            "seeds": [1, 2, 3, 4],
            "budget": 60,
            "code_fingerprint": "deadbeef",
            "comparison": {
                "memory_on_gate_on": {"ci95_low": 0.01, "ci95_high": 0.05, "mean_diff": 0.03}
            },
        }
        write_json_atomic(self.package / "study-evidence.json", self.evidence)
        write_json_atomic(
            self.package / "study-spec.json",
            {"dataset": "iris", "seeds": [1, 2, 3, 4], "code_fingerprint": "deadbeef"},
        )
        self.innovation = {
            "selected_ideas": [
                {
                    "idea_id": "IDEA-01",
                    "experiment_plan": {
                        "profile": "search_factorial",
                        "dataset": "iris",
                        "metric": "improvement_per_evaluation",
                    },
                }
            ]
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _actions(self):
        from research_agent.loop_ledger import pending_study_actions

        return pending_study_actions(self.project, "RUN-X", self.innovation)

    def test_no_opponent_says_so_and_offers_no_flag(self):
        action = self._actions()[0]
        self.assertEqual(action["kind"], "human_gate")
        self.assertNotIn("--baseline-file", action["command"])
        self.assertIn("no tuned baseline is bound", action["message"])
        self.assertFalse(action["tuned_baseline"]["bound_in_command"])

    def test_a_matching_report_beside_the_study_is_named_in_the_command(self):
        write_json_atomic(
            self.project / "studies" / "tuned-baseline-iris.json",
            {"dataset": "iris", "seeds": [1, 2, 3, 4], "cells": []},
        )
        action = self._actions()[0]
        self.assertTrue(action["tuned_baseline"]["bound_in_command"])
        self.assertIn("--baseline-file", action["command"])
        self.assertIn("tuned-baseline-iris.json", action["command"])
        self.assertIn("bind it with --baseline-file", action["message"])

    def test_a_report_from_another_environment_is_not_offered(self):
        write_json_atomic(
            self.project / "studies" / "tuned-baseline-wine.json",
            {"dataset": "wine", "seeds": [1, 2, 3, 4], "cells": []},
        )
        action = self._actions()[0]
        self.assertNotIn("--baseline-file", action["command"])
        self.assertEqual(action["tuned_baseline"]["candidate"], "")

    def test_a_non_result_never_claims_an_opponent_was_found(self):
        self.evidence["comparison"]["memory_on_gate_on"] = {
            "ci95_low": -0.01,
            "ci95_high": 0.05,
            "mean_diff": 0.02,
        }
        write_json_atomic(self.package / "study-evidence.json", self.evidence)
        write_json_atomic(
            self.project / "studies" / "tuned-baseline-iris.json",
            {"dataset": "iris", "seeds": [1, 2, 3, 4], "cells": []},
        )
        action = [item for item in self._actions() if item.get("idea_id") == "IDEA-01"][0]
        self.assertEqual(action["kind"], "study_no_finding")
        # a non-result has no opponent to bind: talking about one would imply a claim exists
        self.assertNotIn("opponent", action["message"])
        self.assertNotIn("--baseline-file", action["command"])

    def test_stale_code_is_declared_before_the_human_is_pointed_at_the_gate(self):
        action = self._actions()[0]
        self.assertTrue(action["code_stale"])
        self.assertIn("code.unchanged", action["message"])
        self.assertIn("verify-repro", action["message"])


if __name__ == "__main__":
    unittest.main()

"""Mandate projection aggregates run capsules without creating authority."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.cli import main
from research_agent.mandate import build_mandate_status
from research_agent.project import init_project


def _project(tmp: Path) -> Path:
    project = tmp / "project"
    init_project(project, "Mandate Test")
    return project


def _capsule(project: Path, run_id: str, blockers, actions) -> Path:
    run = project / "runs" / run_id
    run.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "loop-capsule-0.1",
        "run_id": run_id,
        "task_status": "blocked" if blockers else "completed",
        "blockers": list(blockers),
        "next_actions": list(actions),
        "human_gates": {"G1": "pending"} if actions else {},
        "boundary": "read-only projection of run artifacts",
    }
    path = run / "loop-capsule.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _autopilot(project: Path, max_runs: int, used: int) -> None:
    policy_dir = project / "autopilot"
    policy_dir.mkdir(exist_ok=True)
    (policy_dir / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": "autopilot-policy-0.1",
                "policy_id": "AUTO-1",
                "authorized_by": "project owner",
                "scope": "S5/demo/iris",
                "datasets": ["iris"],
                "min_seeds": 3,
                "max_runs": max_runs,
                "expires_at": "2099-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (policy_dir / "ledger.json").write_text(
        json.dumps(
            {
                "schema_version": "autopilot-ledger-0.1",
                "runs": [
                    {"policy_id": "AUTO-1", "run_id": "RUN-%d" % index, "status": "completed"}
                    for index in range(used)
                ],
            }
        ),
        encoding="utf-8",
    )


class MandateStatusTest(unittest.TestCase):
    def test_blockers_become_triggers_plans_and_obligations(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(
                project,
                "RUN-1",
                ["G1_IDEA_SELECTION_REQUIRED", "CLAIM_UNSIGNED"],
                [{"owner": "human", "gate": "G1", "command": "python -m research_agent flow g1 ..."}],
            )
            result = build_mandate_status(project)
            self.assertEqual(result["schema_version"], "research-mandate-0.1")
            self.assertEqual(result["status"], "needs_human")
            self.assertEqual(result["counts"]["open_blockers"], 2)
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("G1_IDEA_SELECTION_REQUIRED", codes)
            self.assertIn("CLAIM_UNSIGNED", codes)
            self.assertEqual(result["stages"]["plan"][0]["gate"], "G1")
            self.assertIn("CLAIM_UNSIGNED", result["stages"]["obligations"])
            self.assertTrue(result["stages"]["verification"]["not_evidence"])
            self.assertIn("human-only", result["stages"]["approval"]["delegation"])
            self.assertIn("does not create evidence", result["boundary"])
            self.assertTrue(result["stages"]["context"]["runs"][0]["capsule_sha256"])

    def test_expired_policy_stops_the_mandate(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            policy_dir = project / "autopilot"
            policy_dir.mkdir()
            (policy_dir / "policy.json").write_text(
                json.dumps(
                    {
                        "schema_version": "autopilot-policy-0.1",
                        "authorized_by": "project owner",
                        "scope": "S5/demo/iris",
                        "datasets": ["iris"],
                        "min_seeds": 3,
                        "max_runs": 1,
                        "expires_at": "2020-01-01T00:00:00+00:00",
                    }
                ),
                encoding="utf-8",
            )
            result = build_mandate_status(project)
            self.assertEqual(result["status"], "stopped")
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("AUTOPILOT_POLICY_EXPIRED", codes)
            self.assertEqual(result["stages"]["approval"]["policy_state"], "expired")

    def test_exhausted_policy_stops_the_mandate(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            _autopilot(project, max_runs=1, used=1)
            result = build_mandate_status(project)
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(result["stages"]["approval"]["policy_state"], "exhausted")
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("AUTOPILOT_POLICY_EXHAUSTED", codes)
            summary = result["stages"]["context"]["policy"]["summary"]
            self.assertEqual(summary["runs_used"], 1)
            self.assertEqual(summary["remaining_runs"], 0)

    def test_policy_with_remaining_budget_stays_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            _autopilot(project, max_runs=2, used=1)
            result = build_mandate_status(project)
            self.assertEqual(result["status"], "active")
            self.assertEqual(result["stages"]["context"]["policy"]["summary"]["remaining_runs"], 1)

    def test_invalid_ledger_is_not_silently_treated_as_zero_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            _autopilot(project, max_runs=1, used=1)
            (project / "autopilot" / "ledger.json").write_text("{bad json", encoding="utf-8")
            result = build_mandate_status(project)
            self.assertEqual(result["status"], "needs_human")
            self.assertEqual(result["stages"]["approval"]["policy_state"], "invalid")
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("AUTOPILOT_POLICY_INVALID", codes)
            self.assertEqual(
                result["stages"]["context"]["policy"]["summary"]["ledger_state"], "invalid"
            )

    def test_truncated_scan_is_partial_not_optimistic(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-A", [], [])
            _capsule(project, "RUN-B", ["CLAIM_UNSIGNED"], [])
            result = build_mandate_status(project, max_runs=1)
            self.assertEqual(result["status"], "partial")
            self.assertTrue(result["counts"]["truncated"])
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("MANDATE_SCOPE_TRUNCATED", codes)
            self.assertEqual(result["stages"]["acceptance"]["status"], "partial")

    def test_truncated_window_with_a_real_blocker_still_needs_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-A", ["CLAIM_UNSIGNED"], [])
            _capsule(project, "RUN-B", [], [])
            result = build_mandate_status(project, max_runs=1)
            self.assertEqual(result["status"], "needs_human")
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("MANDATE_SCOPE_TRUNCATED", codes)
            self.assertIn("CLAIM_UNSIGNED", codes)

    def test_clean_run_is_active_and_missing_capsule_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            self.assertEqual(build_mandate_status(project)["status"], "active")
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            self.assertEqual(build_mandate_status(project)["status"], "empty")

    def test_invalid_capsule_is_a_trigger_not_a_silent_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            run = project / "runs" / "RUN-BAD"
            run.mkdir(parents=True)
            (run / "loop-capsule.json").write_text("{not json", encoding="utf-8")
            result = build_mandate_status(project)
            self.assertEqual(result["status"], "needs_human")
            self.assertEqual(result["counts"]["invalid_capsules"], 1)
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("INVALID_RUN_CAPSULE", codes)

    def test_cli_prints_json_and_returns_nonzero_when_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", ["CLAIM_UNSIGNED"], [])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["mandate", "status", "--project", str(project)])
            self.assertEqual(code, 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["status"], "needs_human")

            policy_dir = project / "autopilot"
            policy_dir.mkdir()
            (policy_dir / "policy.json").write_text(
                json.dumps({"authorized_by": "owner", "expires_at": "2020-01-01T00:00:00Z"}),
                encoding="utf-8",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["mandate", "status", "--project", str(project)])
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(out.getvalue())["status"], "stopped")


if __name__ == "__main__":
    unittest.main()

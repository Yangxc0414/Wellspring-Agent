"""Mandate projection aggregates run capsules without creating authority.

mandate 0.3.0 起为读时重算语义：产物为准，loop-capsule 快照只在重算失败时兜底
（CAPSULE_RECOMPUTE_FAILED 显式触发 + 总线交叉核验第二道保险）。缺失产物不是
pass——只有快照、没有产物的 run 重算出诚实 blockers，而不是相信快照旧状态。
"""

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
    """读时重算语义（mandate 0.3.0）：产物为准，快照只是重算失败时的兜底。"""

    def _recomputed_codes(self, result, run_id):
        return [
            item["code"]
            for item in result["stages"]["trigger"]
            if item.get("kind") == "blocker" and item.get("run_id") == run_id
        ]

    def _runs(self, result):
        return {
            item.get("run_id"): item
            for item in result["stages"]["context"]["runs"]
            if isinstance(item, dict)
        }

    def test_snapshot_only_run_recomputes_to_honest_blockers(self):
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
            # 产物为准：快照里伪造的 blockers 不再直达触发，重算给出诚实读数
            codes = self._recomputed_codes(result, "RUN-1")
            self.assertIn("S1_NO_LOCATABLE_SPANS", codes)
            self.assertIn("S5_NOT_RUN", codes)
            self.assertIn("CLOSURE_NOT_RUN", codes)
            self.assertNotIn("CLAIM_UNSIGNED", codes)
            run_row = self._runs(result)["RUN-1"]
            self.assertEqual(run_row["capsule_source"], "recomputed")
            self.assertEqual(sorted(result["stages"]["obligations"]), sorted(set(codes)))
            self.assertTrue(result["stages"]["verification"]["not_evidence"])

    def test_read_time_recompute_ignores_stale_snapshot(self):
        # 旧语义（快照 + 总线交叉核验）被读时重算取代：run 有真实产物时，
        # 快照里的 stale CLOSURE_UNSIGNED 不再出现，也不需要 suppression。
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(
                project,
                "RUN-A",
                ["CLOSURE_UNSIGNED"],
                [
                    {
                        "owner": "human",
                        "gate": "G5",
                        "command": 'python -m research_agent closure sign --report x --human-reason "..."',
                    }
                ],
            )
            run = project / "runs" / "RUN-A"
            (run / "run").mkdir(parents=True, exist_ok=True)
            (run / "run" / "run-capsule.json").write_text(
                json.dumps({"schema_version": "run-capsule-0.1", "run_id": "RUN-A", "status": "completed"}),
                encoding="utf-8",
            )
            (run / "closure").mkdir(parents=True, exist_ok=True)
            (run / "closure" / "closure-report.json").write_text(
                json.dumps({"report_id": "CR", "status": "ready", "closure_profile": "canonical_run"}),
                encoding="utf-8",
            )
            (run / "closure-signature").mkdir(parents=True, exist_ok=True)
            (run / "closure-signature" / "signature.json").write_text(
                json.dumps({"signature_id": "SIG", "human_reason": "[delegated:autopilot] policy ok"}),
                encoding="utf-8",
            )
            (run / "claim").mkdir(parents=True, exist_ok=True)
            (run / "claim" / "claim.json").write_text(
                json.dumps({"claim_id": "CLM", "status": "approved"}),
                encoding="utf-8",
            )
            result = build_mandate_status(project)
            run_row = self._runs(result)["RUN-A"]
            self.assertEqual(run_row["capsule_source"], "recomputed")
            self.assertNotIn("CLOSURE_UNSIGNED", run_row["blockers"])
            codes = self._recomputed_codes(result, "RUN-A")
            self.assertNotIn("CLOSURE_UNSIGNED", codes)
            plan_commands = [p.get("command") for p in result["stages"]["plan"]]
            self.assertFalse(any("closure sign" in str(c) for c in plan_commands))

    def test_recompute_failure_falls_back_to_snapshot_with_visible_trigger(self):
        # 重算失败的兜底路径：回退快照 + CAPSULE_RECOMPUTE_FAILED 显式触发；
        # 此时总线交叉核验仍是第二道保险（stale_snapshot_suppressed）。
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-B", ["CLAIM_UNSIGNED"], [])
            import research_agent.loop_capsule as loop_capsule_module

            original = loop_capsule_module.build_loop_capsule

            def _broken(root):
                raise RuntimeError("simulated recompute failure")

            loop_capsule_module.build_loop_capsule = _broken
            try:
                result = build_mandate_status(project)
            finally:
                loop_capsule_module.build_loop_capsule = original
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("CAPSULE_RECOMPUTE_FAILED", codes)
            run_row = self._runs(result)["RUN-B"]
            self.assertEqual(run_row["capsule_source"], "snapshot_fallback")
            # 快照兜底时总线交叉核验仍生效（本例 CLAIM_UNSIGNED 与总线无冲突则照旧）
            self.assertEqual(run_row["blockers"], ["CLAIM_UNSIGNED"])

    def test_expired_policy_stops_the_mandate(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            _autopilot(project, max_runs=1, used=0)
            (project / "autopilot" / "policy.json").write_text(
                json.dumps(
                    {
                        "schema_version": "autopilot-policy-0.1",
                        "policy_id": "AUTO-1",
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

    def test_policy_budget_is_reported_even_when_runs_need_human(self):
        # 预算记账独立于 run 状态：重算后无产物 run 是 needs_human（缺失产物不是
        # pass），但剩余预算仍然如实报出——两件事不混读。
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            _autopilot(project, max_runs=2, used=1)
            result = build_mandate_status(project)
            self.assertEqual(result["status"], "needs_human")
            self.assertEqual(result["stages"]["context"]["policy"]["summary"]["remaining_runs"], 1)

    def test_invalid_ledger_is_not_silently_treated_as_zero_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            _autopilot(project, max_runs=1, used=1)
            (project / "autopilot" / "ledger.json").write_text("{bad json", encoding="utf-8")
            result = build_mandate_status(project)
            self.assertEqual(result["stages"]["approval"]["policy_state"], "invalid")
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("AUTOPILOT_POLICY_INVALID", codes)
            self.assertEqual(
                result["stages"]["context"]["policy"]["summary"]["ledger_state"], "invalid"
            )

    def test_truncated_scan_with_recomputed_blockers_needs_human(self):
        # 截断窗口 + 重算出真实 blockers → needs_human；partial 只留给重算后
        # 确实干净且被截断的窗口（缺失产物不是 pass）。
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-A", [], [])
            _capsule(project, "RUN-B", ["CLAIM_UNSIGNED"], [])
            result = build_mandate_status(project, max_runs=1)
            self.assertTrue(result["counts"]["truncated"])
            codes = [item["code"] for item in result["stages"]["trigger"]]
            self.assertIn("MANDATE_SCOPE_TRUNCATED", codes)
            self.assertEqual(result["stages"]["acceptance"]["status"], "needs_human")
            self.assertTrue(result["counts"]["open_blockers"] > 0)

    def test_missing_artifacts_are_not_pass_and_missing_capsule_is_empty(self):
        # 既有不变量「缺失 artifact 不是 pass」在读时重算下的直接体现。
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            _capsule(project, "RUN-1", [], [])
            result = build_mandate_status(project)
            self.assertEqual(result["status"], "needs_human")
            self.assertEqual(self._runs(result)["RUN-1"]["capsule_source"], "recomputed")
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            self.assertEqual(build_mandate_status(project)["status"], "empty")

    def test_malformed_snapshot_is_superseded_by_recompute(self):
        # 快照损坏不再是触发：重算不读快照，产物为准；损坏的快照只是无用文件。
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(Path(tmp))
            run = project / "runs" / "RUN-BAD"
            run.mkdir(parents=True)
            (run / "loop-capsule.json").write_text("{not json", encoding="utf-8")
            result = build_mandate_status(project)
            self.assertEqual(result["status"], "needs_human")
            self.assertEqual(result["counts"]["invalid_capsules"], 0)
            run_row = self._runs(result)["RUN-BAD"]
            self.assertEqual(run_row["capsule_source"], "recomputed")

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

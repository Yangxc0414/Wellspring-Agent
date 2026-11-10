"""FeedbackPort acceptance: with all loops off, today's behavior is byte-identical.

The port is the seam where a verdict changes the next action (71-§5 step 2);
its first loop (lineage_reverify) is read-only by construction, and the gate
defaults to reject for anything that would mutate a gated artifact.
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.feedback import (
    FEEDBACK_SCHEMA,
    _gate_lineage_reverify,
    run_feedback,
)
from research_agent.lineage import LineageAgent, write_manifest
from research_agent.verdict_ledger import collect


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fabricate_run(root: Path, run_id: str = "RUN-TEST-01") -> Path:
    _write(root / "project.json", {"schema_version": "project-0.1", "name": "feedback-test"})
    run = root / "runs" / run_id
    _write(
        run / "run" / "run-capsule.json",
        {
            "schema_version": "run-capsule-0.1",
            "run_id": run_id,
            "status": "completed",
            "dataset_sha256": "a" * 64,
            "dataset_id": "sklearn:iris",
            "code_sha256": "b" * 64,
        },
    )
    _write(run / "run" / "ea.json", {"schema_version": "ea-0.1"})
    _write(run / "claim" / "claim.json", {"claim_id": "CLM-1", "status": "approved", "statement": "accuracy >= 0.9"})
    return run


def _snapshot(root: Path):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


import hashlib


class FeedbackPortTest(unittest.TestCase):
    def test_disabled_by_default_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root)
            before = _snapshot(root)
            result = run_feedback(root)
            self.assertEqual(result["status"], "disabled")
            self.assertEqual(result["rows"], 0)
            self.assertEqual(_snapshot(root), before)

    def test_disabled_port_leaves_projections_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root)
            baseline = json.dumps(collect(root), ensure_ascii=False, sort_keys=True)
            run_feedback(root)  # disabled run in between
            after = json.dumps(collect(root), ensure_ascii=False, sort_keys=True)
            self.assertEqual(baseline, after)

    def test_lineage_reverify_records_fresh_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = _fabricate_run(root)
            manifest = LineageAgent().build(run)
            write_manifest(manifest, run / "lineage")
            ledger = run_feedback(root, loops=["lineage_reverify"])
            self.assertEqual(ledger["status"], "ran")
            self.assertEqual(len(ledger["rows"]), 1)
            row = ledger["rows"][0]
            self.assertEqual(row["loop_id"], "lineage_reverify")
            self.assertEqual(row["observation"]["state"], "clean")
            self.assertEqual(row["gate_decision"]["decision"], "auto_allowed")
            self.assertEqual(row["effect"]["effect"], "recorded_receipt")
            self.assertTrue((root / "feedback-ledger.json").is_file())

    def test_lineage_reverify_flags_stale_and_proposes_human_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = _fabricate_run(root)
            manifest = LineageAgent().build(run)
            write_manifest(manifest, run / "lineage")
            _write(run / "claim" / "claim.json", {"claim_id": "CLM-1", "status": "approved", "statement": "accuracy >= 0.95"})
            ledger = run_feedback(root, loops=["lineage_reverify"])
            row = ledger["rows"][0]
            self.assertGreater(row["observation"]["stale"], 0)
            self.assertIn("re-sign", row["proposal"]["human_action"])
            self.assertEqual(row["effect"]["effect"], "recorded_receipt")

    def test_rerun_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = _fabricate_run(root)
            manifest = LineageAgent().build(run)
            write_manifest(manifest, run / "lineage")
            first = json.dumps(run_feedback(root, loops=["lineage_reverify"]), ensure_ascii=False, sort_keys=True)
            second = json.dumps(run_feedback(root, loops=["lineage_reverify"]), ensure_ascii=False, sort_keys=True)
            self.assertEqual(first, second)

    def test_unknown_loop_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root)
            with self.assertRaises(ValueError):
                run_feedback(root, loops=["not_a_loop"])

    def test_t6b_falsification_loop_records_constraint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root)
            studies = root / "studies" / "STUDY-iris"
            _write(
                studies / "study-origin.json",
                {"idea_id": "IDEA-01", "falsification": "if the gated run accepts no fewer bogus steps on held-out tasks, the gate adds no selection value"},
            )
            _write(studies / "claim.json", {"status": "approved"})
            ledger = run_feedback(root, loops=["t6b_falsification"])
            self.assertEqual(ledger["status"], "ran")
            row = ledger["rows"][0]
            self.assertEqual(row["observation"]["state"], "falsification_bound")
            self.assertIn("carry the executed falsification condition", row["proposal"]["constraint"])
            self.assertEqual(row["gate_decision"]["decision"], "auto_allowed")
            self.assertEqual(row["effect"]["effect"], "recorded_constraint")

    def test_t6b_flags_missing_falsification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root)
            studies = root / "studies" / "STUDY-iris"
            _write(studies / "study-origin.json", {"idea_id": "IDEA-01", "falsification": ""})
            ledger = run_feedback(root, loops=["t6b_falsification"])
            row = ledger["rows"][0]
            self.assertEqual(row["observation"]["state"], "no_falsification_bound")
            self.assertIn("bind a falsification condition", row["proposal"]["constraint"])

    def test_gate_rejects_mutating_proposals(self):
        decision = _gate_lineage_reverify(
            {"kind": "rewrite_claim", "read_only": False, "subject": "runs/RUN-TEST-01"}
        )
        self.assertEqual(decision["decision"], "rejected")


class VerdictActionTableTest(unittest.TestCase):
    """决策表：verdict 行 → 确定性动作；矛盾与不变量违例升级人工。"""

    def _row(self, subject, kind, status):
        return {"subject": subject, "kind": kind, "status": status}

    def test_signed_closure_maps_to_verify_bundle(self):
        from research_agent.feedback import verdict_action_table

        table = verdict_action_table(
            [
                self._row("runs/R-1", "claim", "signed"),
                self._row("runs/R-1", "closure", "signed"),
            ]
        )
        self.assertEqual(table["actions"][0]["action"], "verify_bundle")
        self.assertEqual(table["actions"][0]["basis"], {"kind": "closure", "status": "signed"})

    def test_ready_closure_with_signed_claim_maps_to_closure_sign_human(self):
        from research_agent.feedback import verdict_action_table

        table = verdict_action_table(
            [
                self._row("runs/R-1", "claim", "signed"),
                self._row("runs/R-1", "closure", "ready"),
            ]
        )
        self.assertEqual(table["actions"][0]["action"], "closure_sign_human")

    def test_claim_draft_maps_to_claim_sign_human(self):
        from research_agent.feedback import verdict_action_table

        table = verdict_action_table([self._row("runs/R-1", "claim", "draft")])
        self.assertEqual(table["actions"][0]["action"], "claim_sign_human")

    def test_conflicting_statuses_escalate(self):
        from research_agent.feedback import verdict_action_table

        table = verdict_action_table(
            [
                self._row("runs/R-1", "closure", "signed"),
                self._row("runs/R-1", "closure", "missing"),
            ]
        )
        self.assertEqual(table["actions"][0]["action"], "escalate_conflict")

    def test_signed_closure_over_unsigned_claim_escalates(self):
        from research_agent.feedback import verdict_action_table

        table = verdict_action_table(
            [
                self._row("runs/R-1", "claim", "draft"),
                self._row("runs/R-1", "closure", "signed"),
            ]
        )
        self.assertEqual(table["actions"][0]["action"], "escalate_conflict")

    def test_deterministic(self):
        from research_agent.feedback import verdict_action_table

        rows = [
            self._row("runs/R-1", "claim", "signed"),
            self._row("runs/R-2", "claim", "draft"),
            self._row("runs/R-2", "closure", "ready"),
        ]
        self.assertEqual(
            json.dumps(verdict_action_table(rows), sort_keys=True),
            json.dumps(verdict_action_table(list(reversed(rows))), sort_keys=True),
        )


class M1HarnessTest(unittest.TestCase):
    def test_harness_runs_and_reports_a_verdict(self):
        import importlib.util
        from tests.test_verdict_ledger import _fabricate_run

        spec = importlib.util.spec_from_file_location(
            "m1_feedback_sensitivity", str(Path(__file__).resolve().parents[1] / "scripts" / "m1_feedback_sensitivity.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root, signed=True, capsule_blockers=["CLOSURE_UNSIGNED"])
            out = root / "m1"
            result = module.run(root)
            self.assertIn(result["verdict"], ("supported", "not_supported"))
            self.assertEqual(result["metrics"]["real_match_rate"], 1.0)
            self.assertGreater(result["metrics"]["contradictory_escalations"], 0)
            module.main(["--project", str(root), "--output-dir", str(out)])
            self.assertTrue((out / "result.json").is_file())


if __name__ == "__main__":
    unittest.main()

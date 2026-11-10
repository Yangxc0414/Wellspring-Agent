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

    def test_gate_rejects_mutating_proposals(self):
        decision = _gate_lineage_reverify(
            {"kind": "rewrite_claim", "read_only": False, "subject": "runs/RUN-TEST-01"}
        )
        self.assertEqual(decision["decision"], "rejected")


if __name__ == "__main__":
    unittest.main()

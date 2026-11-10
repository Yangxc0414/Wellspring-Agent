"""The verdict ledger must be a deterministic projection with visible drift.

Consumers used to trust loop-capsule.json blockers that go stale the moment a
delegated signature lands after the snapshot was written; the ledger re-derives
every verdict from its single-point producer and pairs it with the snapshot, so
the drift is a row instead of a silent wrong next_action.
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.verdict_ledger import VERDICT_SCHEMA, collect, write_ledger


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fabricate_run(
    root: Path,
    run_id: str = "RUN-TEST-01",
    signed: bool = True,
    capsule_blockers=None,
    capsule_broken: bool = False,
    closure_status: str = "ready",
    closure_in_run_subdir: bool = False,
) -> Path:
    _write(root / "project.json", {"schema_version": "project-0.1", "name": "verdict-test"})
    run = root / "runs" / run_id
    _write(run / "run" / "run-capsule.json", {"schema_version": "run-capsule-0.1", "status": "completed"})
    _write(run / "run" / "ea.json", {"schema_version": "ea-0.1"})
    closure_path = run / "run" / "closure-report.json" if closure_in_run_subdir else run / "closure" / "closure-report.json"
    _write(closure_path, {"report_id": "CR-" + run_id, "status": closure_status, "closure_profile": "canonical_run"})
    if signed:
        _write(
            run / "closure-signature" / "signature.json",
            {"signature_id": "SIG-" + run_id, "human_reason": "[delegated:autopilot] test policy"},
        )
        _write(run / "claim" / "claim.json", {"claim_id": "CLM-" + run_id, "status": "approved"})
    else:
        _write(run / "run" / "claim-draft.json", {"schema_version": "claim-draft-0.1"})
    if capsule_broken:
        (run / "loop-capsule.json").parent.mkdir(parents=True, exist_ok=True)
        (run / "loop-capsule.json").write_text("{not json", encoding="utf-8")
    elif capsule_blockers is not None:
        _write(
            run / "loop-capsule.json",
            {"schema_version": "loop-capsule-0.1", "blockers": list(capsule_blockers), "next_actions": []},
        )
    return run


def _rows(ledger, kind: str):
    return [row for row in ledger["rows"] if row["kind"] == kind]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VerdictLedgerTest(unittest.TestCase):
    def test_signed_run_yields_closure_claim_and_drift_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(
                root,
                signed=True,
                capsule_blockers=["CLOSURE_UNSIGNED", "WRITING_AUDIT_BLOCKED", "FIXTURE_ONLY"],
            )
            ledger = collect(root)
            self.assertEqual(ledger["schema_version"], VERDICT_SCHEMA)
            closure = _rows(ledger, "closure")
            self.assertEqual(len(closure), 1)
            self.assertEqual(closure[0]["status"], "signed")
            self.assertTrue(closure[0]["delegated"])
            self.assertEqual(closure[0]["subject"], "runs/RUN-TEST-01")
            claims = _rows(ledger, "claim")
            self.assertEqual(claims[0]["status"], "signed")
            drift = _rows(ledger, "snapshot_drift")
            self.assertEqual(len(drift), 1)
            self.assertEqual(drift[0]["snapshot"], "CLOSURE_UNSIGNED")
            self.assertEqual(drift[0]["recomputed"], "signed")
            self.assertEqual(ledger["counts"]["drift"], 1)

    def test_rows_bind_the_artifact_they_were_derived_from(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = _fabricate_run(root, signed=True, capsule_blockers=[])
            ledger = collect(root)
            closure = _rows(ledger, "closure")[0]
            self.assertEqual(
                closure["source_path"],
                "runs/RUN-TEST-01/closure/closure-report.json",
            )
            self.assertEqual(closure["source_sha256"], _sha256(run / "closure" / "closure-report.json"))
            claim = _rows(ledger, "claim")[0]
            self.assertEqual(claim["source_path"], "runs/RUN-TEST-01/claim/claim.json")
            self.assertEqual(claim["source_sha256"], _sha256(run / "claim" / "claim.json"))

    def test_collect_is_deterministic_and_write_is_replayable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root, signed=True, capsule_blockers=["CLOSURE_UNSIGNED"])
            first = json.dumps(collect(root), ensure_ascii=False, sort_keys=True)
            second = json.dumps(collect(root), ensure_ascii=False, sort_keys=True)
            self.assertEqual(first, second)
            out = root / "verdict-ledger.json"
            write_ledger(out, collect(root))
            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(json.dumps(written, ensure_ascii=False, sort_keys=True), first)

    def test_closure_in_run_subdir_is_still_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root, signed=True, capsule_blockers=[], closure_in_run_subdir=True)
            ledger = collect(root)
            closure = _rows(ledger, "closure")[0]
            self.assertEqual(closure["source_path"], "runs/RUN-TEST-01/run/closure-report.json")
            self.assertEqual(closure["source_sha256"], _sha256(root / "runs/RUN-TEST-01/run/closure-report.json"))

    def test_unsigned_run_with_honest_snapshot_has_no_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root, signed=False, capsule_blockers=["CLOSURE_UNSIGNED"], closure_status="ready")
            ledger = collect(root)
            self.assertEqual(_rows(ledger, "snapshot_drift"), [])
            self.assertEqual(_rows(ledger, "closure")[0]["status"], "ready")
            self.assertEqual(_rows(ledger, "claim")[0]["status"], "draft")

    def test_broken_capsule_snapshot_fails_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root, signed=True, capsule_broken=True)
            ledger = collect(root)
            drift = _rows(ledger, "snapshot_drift")
            self.assertEqual(len(drift), 1)
            self.assertEqual(drift[0]["status"], "unreadable")

    def test_missing_project_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                collect(Path(tmp) / "nope")

    def test_no_absolute_paths_in_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root, signed=True, capsule_blockers=["CLOSURE_UNSIGNED"])
            text = json.dumps(collect(root), ensure_ascii=False)
            drive = tmp.split(":")[0] + ":"
            self.assertNotIn(drive, text)
            self.assertNotIn(tmp.replace("\\", "/"), text.replace("\\", "/"))


class ConsumerMigrationTest(unittest.TestCase):
    """research_status 的 capsule 摘要必须读判定总线：已签闭包不得再喊 closure sign。"""

    def _summary(self, root: Path):
        from research_agent.mcp_server import _loop_capsule_summary

        return _loop_capsule_summary(root / "runs" / "RUN-TEST-01")

    def test_signed_closure_overrides_stale_snapshot_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root, signed=True, capsule_blockers=["CLOSURE_UNSIGNED", "FIXTURE_ONLY"])
            summary = self._summary(root)
            self.assertNotIn("CLOSURE_UNSIGNED", summary["blockers"])
            self.assertIn("FIXTURE_ONLY", summary["blockers"])
            override = summary["verdict_override"]
            self.assertEqual(override["recomputed"], "signed")
            self.assertEqual(override["snapshot"], "CLOSURE_UNSIGNED")
            self.assertTrue(override["source_sha256"])
            for action in summary["next_actions"]:
                self.assertNotIn("closure sign", str(action.get("command") or ""))

    def test_consistent_snapshot_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root, signed=False, capsule_blockers=["CLOSURE_UNSIGNED"], closure_status="ready")
            capsule_payload = {
                "run_id": "RUN-TEST-01",
                "blockers": ["CLOSURE_UNSIGNED"],
                "next_actions": [{"owner": "human", "gate": "G5", "command": "python -m research_agent closure sign --report x"}],
                "nodes": [],
                "boundary": "test",
            }
            (root / "runs" / "RUN-TEST-01" / "loop-capsule.json").write_text(
                json.dumps(capsule_payload, ensure_ascii=False), encoding="utf-8"
            )
            summary = self._summary(root)
            self.assertIsNone(summary["verdict_override"])
            self.assertEqual(summary["blockers"], ["CLOSURE_UNSIGNED"])
            self.assertEqual(len(summary["next_actions"]), 1)

    def test_missing_capsule_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.joinpath("runs", "RUN-TEST-01").mkdir(parents=True)
            self.assertEqual(self._summary(root), {})


if __name__ == "__main__":
    unittest.main()

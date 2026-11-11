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
    generation_constraints,
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

    def test_belief_revision_loop_records_constraints_from_real_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root)
            run = root / "runs" / "RUN-TEST-01"
            _write(
                run / "idea.json",
                {
                    "candidates": [
                        {"idea_id": "IDEA-01", "title": "[Mechanism] A", "lens": "mechanism", "status": "candidate", "source_count": 2},
                        {"idea_id": "IDEA-02", "title": "[Mechanism] B", "lens": "mechanism", "status": "candidate", "source_count": 1},
                    ]
                },
            )
            _write(
                run / "idea-review.json",
                {
                    "reviews": [
                        {"idea_id": "IDEA-01", "recommendation": "revise", "reasons": ["single source"]},
                        {"idea_id": "IDEA-02", "recommendation": "approve", "reasons": []},
                    ]
                },
            )
            ledger = run_feedback(root, loops=["belief_revision"])
            rows = {r["observation"]["subject"]: r for r in ledger["rows"]}
            self.assertIn("runs/RUN-TEST-01/IDEA-01", rows)
            self.assertIn("runs/RUN-TEST-01/IDEA-02", rows)
            self.assertIn("revise or drop", rows["runs/RUN-TEST-01/IDEA-01"]["proposal"]["constraint"])
            self.assertIn("carry forward", rows["runs/RUN-TEST-01/IDEA-02"]["proposal"]["constraint"])

    def test_homogeneity_loop_flags_dominant_lens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root)
            run = root / "runs" / "RUN-TEST-01"
            _write(
                run / "idea.json",
                {
                    "candidates": [
                        {"idea_id": "IDEA-0%d" % i, "title": "C%d" % i, "lens": "mechanism", "source_count": 3}
                        for i in (1, 2, 3)
                    ]
                },
            )
            ledger = run_feedback(root, loops=["homogeneity"])
            self.assertEqual(len(ledger["rows"]), 1)
            row = ledger["rows"][0]
            self.assertEqual(row["observation"]["state"], "homogeneous")
            self.assertIn("two distinct lenses", row["proposal"]["constraint"])

    def test_homogeneity_diverse_candidates_carry_no_constraint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _fabricate_run(root)
            run = root / "runs" / "RUN-TEST-01"
            _write(
                run / "idea.json",
                {
                    "candidates": [
                        {"idea_id": "IDEA-1", "title": "A", "lens": "mechanism", "source_count": 3},
                        {"idea_id": "IDEA-2", "title": "B", "lens": "evaluation", "source_count": 3},
                        {"idea_id": "IDEA-3", "title": "C", "lens": "transfer", "source_count": 3},
                    ]
                },
            )
            ledger = run_feedback(root, loops=["homogeneity"])
            self.assertEqual(ledger["rows"], [])

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


class GenerationConstraintsTest(unittest.TestCase):
    def _study(self, root: Path) -> Path:
        study = root / "studies" / "STUDY-CONS"
        _write(
            study / "study-origin.json",
            {"falsification": "effect reverses under doubled seeds", "idea_id": "IDEA-01"},
        )
        return study

    def test_missing_ledger_is_empty_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = _snapshot(root)
            payload = generation_constraints(root)
            self.assertEqual(payload["constraints"], [])
            self.assertEqual(payload["stale"], [])
            self.assertEqual(_snapshot(root), before)

    def test_fresh_constraint_passes_and_stale_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            study = self._study(root)
            run_feedback(root, loops=["t6b_falsification"])
            fresh = generation_constraints(root)
            self.assertEqual(len(fresh["constraints"]), 1)
            self.assertEqual(fresh["stale"], [])
            entry = fresh["constraints"][0]
            self.assertEqual(entry["loop_id"], "t6b_falsification")
            self.assertTrue(entry["source_sha256"])
            _write(
                study / "study-origin.json",
                {"falsification": "changed condition", "idea_id": "IDEA-01"},
            )
            stale = generation_constraints(root)
            self.assertEqual(stale["constraints"], [])
            self.assertEqual(len(stale["stale"]), 1)
            self.assertIn("changed", stale["stale"][0]["reason"])

    def test_belief_constraint_invalidated_when_review_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "runs" / "RUN-TEST-01"
            _write(
                run / "idea.json",
                {"candidates": [{"idea_id": "IDEA-01", "title": "T", "lens": "mechanism", "source_count": 2}]},
            )
            _write(
                run / "idea-review.json",
                {"reviews": [{"idea_id": "IDEA-01", "recommendation": "revise", "reasons": ["single source"]}]},
            )
            run_feedback(root, loops=["belief_revision"])
            fresh = generation_constraints(root)
            self.assertEqual(len(fresh["constraints"]), 1)
            _write(
                run / "idea-review.json",
                {"reviews": [{"idea_id": "IDEA-01", "recommendation": "approve", "reasons": []}]},
            )
            stale = generation_constraints(root)
            self.assertEqual(stale["constraints"], [])
            self.assertEqual(len(stale["stale"]), 1)

    def test_typed_constraint_kind_and_payload_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._study(root)
            run_feedback(root, loops=["t6b_falsification"])
            entry = generation_constraints(root)["constraints"][0]
            self.assertEqual(entry["constraint_kind"], "carry_falsification")
            self.assertEqual(
                entry["payload"]["falsification"], "effect reverses under doubled seeds"
            )
            self.assertNotIn("legacy_inferred", entry)

    def test_legacy_text_only_rows_are_inferred_at_the_consumer_edge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._study(root)
            run_feedback(root, loops=["t6b_falsification"])
            ledger = json.loads((root / "feedback-ledger.json").read_text(encoding="utf-8"))
            for row in ledger["rows"]:
                row["proposal"].pop("constraint_kind", None)
                row["proposal"].pop("payload", None)
            _write(root / "feedback-ledger.json", ledger)
            entry = generation_constraints(root)["constraints"][0]
            self.assertEqual(entry["constraint_kind"], "carry_falsification")
            self.assertEqual(
                entry["payload"]["falsification"], "effect reverses under doubled seeds"
            )
            self.assertTrue(entry["legacy_inferred"])

    def test_deterministic_and_gate_rejected_rows_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._study(root)
            run_feedback(root, loops=["t6b_falsification"])
            first = json.dumps(generation_constraints(root), sort_keys=True)
            second = json.dumps(generation_constraints(root), sort_keys=True)
            self.assertEqual(first, second)
            ledger = json.loads((root / "feedback-ledger.json").read_text(encoding="utf-8"))
            ledger["rows"][0]["gate_decision"] = {"decision": "rejected", "reason": "test"}
            _write(root / "feedback-ledger.json", ledger)
            self.assertEqual(generation_constraints(root)["constraints"], [])


if __name__ == "__main__":
    unittest.main()

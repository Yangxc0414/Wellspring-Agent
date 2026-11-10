import json
import tempfile
import unittest
from pathlib import Path

from research_agent.evolution_policy import EvolutionPolicyStore
from research_agent.rsi import (
    Candidate,
    EvalEvidence,
    GovernancePolicy,
    RSIController,
    RSIPolicyError,
    StepLedger,
)


def evidence(split, status="passed", simulation=False, value=0.9, **overrides):
    values = {
        "split": split,
        "status": status,
        "artifact_ref": "artifact-%s.json" % split,
        "metrics": {"coverage": value},
        "n": 10,
        "simulation": simulation,
        "claim_eligible": True,
        "evaluator": "test-evaluator",
        "artifact_sha256": "a" * 64,
        "task_pack_sha256": "b" * 64,
    }
    values.update(overrides)
    return EvalEvidence(**values)


class RSIGovernanceUpgradeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "rsi-ledger.json"
        self.ledger = StepLedger(self.path)
        self.controller = RSIController(self.ledger)

    def tearDown(self):
        self.tmp.cleanup()

    def _candidate(self):
        return Candidate(
            kind="process",
            target="literature.query_planner",
            patch="add a review subquery",
            rationale="thin coverage",
            predicted_effect="one more full-text source",
            scope="S1/zh",
            proposer="agent-proposer",
        )

    def test_strict_admission_requires_all_splits_and_sealed_hashes(self):
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-1")
        with self.assertRaises(RSIPolicyError):
            self.controller.admit(
                record.episode_id, evidence("public"), evidence("hidden"),
                "approved", "S1/zh", strict=True,
            )
        with self.assertRaises(RSIPolicyError):
            self.controller.admit(
                record.episode_id,
                evidence("public", simulation=True),
                evidence("hidden"),
                "approved",
                "S1/zh",
                30,
                near_ood_eval=evidence("near_ood"),
                regression_eval=evidence("regression"),
                strict=True,
            )
        with self.assertRaises(RSIPolicyError):
            self.controller.admit(
                record.episode_id,
                evidence("public", evaluator=""),
                evidence("hidden"),
                "approved",
                "S1/zh",
                30,
                near_ood_eval=evidence("near_ood"),
                regression_eval=evidence("regression"),
                strict=True,
            )
        with self.assertRaises(RSIPolicyError):
            self.controller.admit(
                record.episode_id,
                evidence("public", artifact_sha256=""),
                evidence("hidden"),
                "approved",
                "S1/zh",
                30,
                near_ood_eval=evidence("near_ood"),
                regression_eval=evidence("regression"),
                strict=True,
            )

    def test_strict_admission_records_provenance_and_active_claim(self):
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-2")
        admitted = self.controller.admit(
            record.episode_id,
            evidence("public"),
            evidence("hidden"),
            "approved after review",
            "S1/zh",
            30,
            near_ood_eval=evidence("near_ood"),
            regression_eval=evidence("regression"),
            strict=True,
            approved_by="pi-local",
        )
        self.assertEqual(admitted.decision, "approved")
        self.assertEqual(admitted.admission_mode, "strict")
        self.assertEqual(admitted.approved_by, "pi-local")
        self.assertEqual(len(admitted.evidence_digest), 64)
        self.assertEqual(admitted.candidate.proposer, "agent-proposer")
        claims = self.controller.report()["capability_claims"]
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["episode_id"], record.episode_id)

    def test_evidence_cannot_be_replaced_after_evaluation(self):
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-3")
        public = evidence("public", value=0.9)
        self.controller.evaluate(record.episode_id, public, evidence("hidden"))
        with self.assertRaises(RSIPolicyError):
            self.controller.admit(
                record.episode_id,
                evidence("public", value=0.99),
                evidence("hidden"),
                "approved",
                "S1/zh",
            )

    def test_revoked_lease_withholds_capability_claim(self):
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-4")
        admitted = self.controller.admit(
            record.episode_id, evidence("public"), evidence("hidden"),
            "approved", "S1/zh", 30,
        )
        self.assertEqual(len(self.controller.report()["capability_claims"]), 1)
        self.controller.revoke(admitted.lease_id, "hidden drift")
        report = self.controller.report()
        self.assertEqual(report["capability_claims"], [])
        self.assertTrue(any("without an active lease" in item for item in report["warnings"]))

    def test_event_log_is_hash_chained_and_tamper_evident(self):
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-5")
        self.controller.admit(
            record.episode_id, evidence("public"), evidence("hidden"),
            "approved", "S1/zh", 30,
        )
        self.controller.revoke(record.lease_id, "rollback")
        verified = self.controller.report()["event_log"]
        self.assertTrue(verified["ok"], verified)
        self.assertGreaterEqual(verified["count"], 3)
        lines = self.path.with_name(self.path.name + ".events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        entry = json.loads(lines[0])
        entry["payload"]["target"] = "tampered.target"
        lines[0] = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        self.path.with_name(self.path.name + ".events.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        broken = StepLedger.load(self.path).verify_events()
        self.assertFalse(broken["ok"])
        self.assertTrue(broken["errors"])
        with self.assertRaises(RSIPolicyError):
            RSIController(StepLedger.load(self.path)).propose(
                self._candidate(), dry_run_ref="DRY-AFTER-TAMPER"
            )


class PolicyUpgradeTest(unittest.TestCase):
    def test_unknown_and_locked_targets_default_deny(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = EvolutionPolicyStore(Path(tmp) / "policy.json")
            self.assertFalse(store.allows_candidate("process", "custom.unknown_scope"))
            self.assertFalse(store.allows_candidate("process", "closure.report"))
            self.assertFalse(store.allows_candidate("process", "heldout.pack"))
            self.assertTrue(store.allows_candidate("skill", "skill:my-new-skill"))
            self.assertTrue(store.allows_candidate("skill", "literature.query_planner"))

    def test_governance_rejects_closure_and_heldout_targets(self):
        candidate = Candidate(
            kind="process",
            target="closure.report",
            patch="x",
            rationale="r",
            predicted_effect="p",
        )
        with self.assertRaises(RSIPolicyError):
            GovernancePolicy.check(candidate)
        candidate.target = "heldout.pack"
        with self.assertRaises(RSIPolicyError):
            GovernancePolicy.check(candidate)


if __name__ == "__main__":
    unittest.main()

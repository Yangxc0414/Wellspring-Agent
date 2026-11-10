import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from research_agent.adapters import MiniLMRetriever, RealCorpusError, RealCorpusRetriever
from research_agent.rsi import (
    Candidate, EvalEvidence, GovernancePolicy, MetaTracker, RSIController,
    RSIPolicyError, StepLedger, ledger_story, trace_research,
)
from research_agent.rsi_fixture import (
    active_literature_policy, run_confirmation_trial, run_fixture_trial,
)
from research_agent.real_eval import resolve_active_harness, run_real_confirmation, run_real_trial


class GovernedRSITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self.tmp.name) / "rsi-ledger.json"
        self.ledger = StepLedger(self.ledger_path)
        self.controller = RSIController(self.ledger)

    def tearDown(self):
        self.tmp.cleanup()

    def _candidate(self, target="literature.query_planner", kind="skill"):
        return Candidate(
            kind=kind, target=target, patch="add a review subquery",
            rationale="coverage was thin", predicted_effect="one more full-text source",
            parent_id="incumbent", scope="S1/zh_core_journal",
        )

    def test_policy_rejects_claims_and_gates(self):
        for target in ("claim.text", "gate.G2", "rubric.threshold", "export.manifest"):
            with self.assertRaises(RSIPolicyError):
                GovernancePolicy.check(self._candidate(target=target))
        GovernancePolicy.check(self._candidate())

    def test_propose_is_pending_without_fake_capability(self):
        record = self.controller.propose(self._candidate(), observation="thin coverage", dry_run_ref="DRY-1")
        self.assertEqual(record.decision, "pending_human")
        self.assertEqual(self.controller.report()["pending"], 1)
        self.assertEqual(self.controller.report()["capability_claims"], [])
        self.assertTrue(any("no hidden evaluation" in w for w in self.controller.report()["warnings"]))

    def test_meta_tracker_calibrates_numeric_predictions(self):
        candidate = Candidate(
            kind="process",
            target="literature.retrieval.budget",
            patch='{"retriever": "minilm", "max_sources": 3}',
            rationale="cheaper harness trial",
            predicted_effect="hidden cost -4, no recall loss",
            scope="S1/real-probe",
            predicted_metrics={"hidden_cost_delta": -4.0, "hidden_recall_delta": 0.0},
        )
        record = self.controller.propose(candidate, dry_run_ref="DRY-TRACK")
        self.controller.record_actuals(
            record.episode_id,
            {"hidden_cost_delta": -7.0, "hidden_recall_delta": 0.0, "hidden_gap_delta": 0},
        )
        tracking = self.controller.report()["tracking"]
        self.assertEqual(tracking["status"], "tracked")
        self.assertEqual(tracking["compared_episodes"], 1)
        self.assertEqual(tracking["metrics"]["hidden_cost_delta"]["mae"], 3.0)
        self.assertEqual(tracking["metrics"]["hidden_cost_delta"]["bias"], -3.0)
        self.assertEqual(tracking["metrics"]["hidden_cost_delta"]["direction_agreement"], 1.0)
        self.assertEqual(tracking["metrics"]["hidden_recall_delta"]["mae"], 0.0)
        reloaded = StepLedger.load(self.ledger_path)
        self.assertEqual(
            reloaded.episodes[0].candidate.predicted_metrics["hidden_cost_delta"], -4.0
        )

        unpredicted = self.controller.propose(self._candidate(), dry_run_ref="DRY-FREE")
        self.controller.record_actuals(unpredicted.episode_id, {"hidden_cost_delta": -2.0})
        tracking = self.controller.report()["tracking"]
        self.assertEqual(tracking["status"], "partial")
        self.assertEqual(tracking["coverage"], 0.5)
        self.assertTrue(any("calibration covers a subset" in w for w in self.controller.report()["warnings"]))
        self.assertEqual(self.controller.report()["capability_claims"], [])

        with self.assertRaises(RSIPolicyError):
            Candidate(
                kind="process", target="literature.retrieval.budget", patch="{}",
                rationale="bad prediction", predicted_effect="lower cost",
                predicted_metrics={"hidden_cost_delta": "lower"},
            )

    def test_confirmation_record_is_audit_only(self):
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-CONF")
        public = EvalEvidence(
            "public", "passed", "ART-CP", {"coverage": 0.8}, 2, claim_eligible=False
        )
        hidden = EvalEvidence(
            "hidden", "passed", "ART-CH", {"coverage": 0.8}, 2, claim_eligible=False
        )
        self.controller.admit(record.episode_id, public, hidden, "operator approval", "S1/zh", 30)
        confirmation = {
            "sealed": True, "used_for_admission": False, "status": "confirmed",
            "passed": True, "scope": "S1/zh", "split": "hidden",
            "delta": {"coverage": 0.0},
        }
        entry = self.controller.record_confirmation(record.episode_id, confirmation, "test")
        self.assertEqual(entry["status"], "confirmed")
        report = self.controller.report()
        self.assertEqual(report["confirmations"]["confirmed"], 1)
        self.assertEqual(report["capability_claims"], [])
        duplicate = self.controller.record_confirmation(record.episode_id, confirmation)
        self.assertEqual(duplicate["artifact_sha256"], entry["artifact_sha256"])
        self.assertEqual(len(self.controller.ledger.confirmations), 1)
        with self.assertRaises(RSIPolicyError):
            self.controller.record_confirmation(
                record.episode_id, dict(confirmation, used_for_admission=True)
            )
        with self.assertRaises(RSIPolicyError):
            self.controller.record_confirmation(
                record.episode_id, dict(confirmation, sealed=False)
            )
        with self.assertRaises(RSIPolicyError):
            self.controller.record_confirmation(
                record.episode_id, dict(confirmation, passed=False)
            )
        with self.assertRaises(RSIPolicyError):
            self.controller.record_confirmation(
                record.episode_id, dict(confirmation, scope="S9/other")
            )
        with self.assertRaises(RSIPolicyError):
            self.controller.record_confirmation(
                record.episode_id, dict(confirmation, delta={"coverage": "high"})
            )

    def test_trace_links_admitted_lease_to_research_run(self):
        record = self.controller.propose(
            Candidate(
                kind="process", target="experiment.run.seeds",
                patch='{"seeds": 2}', rationale="seed trial",
                predicted_effect="lower cost", scope="S5/demo/trace",
            ),
            dry_run_ref="DRY-TRACE",
        )
        public = EvalEvidence(
            "public", "passed", "ART-P", {"mean_score": 0.9}, 2, claim_eligible=False
        )
        hidden = EvalEvidence(
            "hidden", "passed", "ART-H", {"mean_score": 0.9}, 2, claim_eligible=False
        )
        self.controller.admit(
            record.episode_id, public, hidden, "operator approval", "S5/demo/trace", 30
        )
        capsule_path = Path(self.tmp.name) / "run-capsule.json"
        capsule = {
            "run_id": "RUN-TRACE", "status": "completed", "seeds": [17, 18],
            "dataset_id": "trace:local", "metric_name": "accuracy", "mean": 0.9,
        }
        capsule_path.write_text(json.dumps(capsule), encoding="utf-8")
        result = trace_research(self.ledger_path, "S5/demo/trace", capsule_path)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"], "traceable")
        self.assertTrue(any("no confirmation" in warning for warning in result["warnings"]))

        confirmation_path = Path(self.tmp.name) / "confirmation.json"
        confirmation_path.write_text(json.dumps({
            "sealed": True, "used_for_admission": False,
            "status": "confirmed", "passed": True, "scope": "S5/demo/trace",
        }), encoding="utf-8")
        linked = trace_research(
            self.ledger_path, "S5/demo/trace", capsule_path, confirmation_path
        )
        self.assertTrue(linked["ok"])
        self.assertEqual(linked["confirmation"]["status"], "confirmed")
        self.assertTrue(any("not recorded in ledger" in w for w in linked["warnings"]))

        payload = {
            "sealed": True, "used_for_admission": False, "status": "confirmed",
            "passed": True, "scope": "S5/demo/trace", "delta": {"mean": 0.0},
        }
        entry = self.controller.record_confirmation(record.episode_id, payload)
        recorded_path = Path(self.tmp.name) / "confirmation-recorded.json"
        recorded_path.write_text(
            json.dumps(dict(payload, ledger_confirmation=entry)), encoding="utf-8"
        )
        traced = trace_research(
            self.ledger_path, "S5/demo/trace", capsule_path, recorded_path
        )
        self.assertTrue(traced["checks"]["confirmation_in_ledger"])

        capsule["seeds"] = [17]
        capsule_path.write_text(json.dumps(capsule), encoding="utf-8")
        mismatch = trace_research(self.ledger_path, "S5/demo/trace", capsule_path)
        self.assertFalse(mismatch["ok"])
        self.assertFalse(mismatch["checks"]["seed_budget_applied"])

    def test_legacy_ledger_without_numeric_predictions_is_uncalibrated(self):
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-LEGACY")
        self.controller.record_actuals(record.episode_id, {"coverage": 0.8})
        data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        for episode in data["episodes"]:
            episode["candidate"].pop("predicted_metrics", None)
        self.ledger_path.write_text(json.dumps(data), encoding="utf-8")
        report = MetaTracker().report(StepLedger.load(self.ledger_path))
        self.assertEqual(report["tracking"]["status"], "uncalibrated")
        self.assertEqual(report["tracking"]["coverage"], 0.0)
        self.assertTrue(any("calibration unavailable" in w for w in report["warnings"]))

    def test_admit_requires_dry_run_public_hidden_and_reason(self):
        without_dry = self.controller.propose(self._candidate())
        public = EvalEvidence("public", "passed", "ART-PUB-1", {"coverage": 0.8}, 20)
        hidden = EvalEvidence("hidden", "passed", "ART-HID-1", {"coverage": 0.77}, 10)
        with self.assertRaises(RSIPolicyError):
            self.controller.admit(without_dry.episode_id, public, hidden, "ok", "S1")
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-2")
        with self.assertRaises(RSIPolicyError):
            self.controller.admit(record.episode_id, public, EvalEvidence("hidden", "failed", "ART-HID-2"), "ok", "S1")
        with self.assertRaises(RSIPolicyError):
            self.controller.admit(record.episode_id, public, hidden, "", "S1")

    def test_admit_issues_lease_and_revoke_preserves_record(self):
        record = self.controller.propose(self._candidate(), dry_run_ref="DRY-3")
        public = EvalEvidence("public", "passed", "ART-PUB-2", {"coverage": 0.8}, 20)
        hidden = EvalEvidence("hidden", "passed", "ART-HID-3", {"coverage": 0.77}, 10)
        near = EvalEvidence("near_ood", "passed", "ART-OOD-1", {"coverage": 0.71}, 6)
        regression = EvalEvidence("regression", "passed", "ART-REG-1", {"coverage": 0.79}, 10)
        admitted = self.controller.admit(
            record.episode_id, public, hidden, "fixed instance reviewed", "S1/zh", 30,
            near_ood_eval=near, regression_eval=regression,
        )
        self.assertEqual(admitted.decision, "approved")
        self.assertTrue(admitted.lease_id)
        report = self.controller.report()
        self.assertEqual(report["approved"], 1)
        self.assertEqual(report["active_leases"], 1)
        self.assertEqual(report["capability_claims"][0]["n"], 10)
        self.assertEqual(report["capability_claims"][0]["near_ood_metrics"]["coverage"], 0.71)
        self.assertEqual(report["capability_claims"][0]["regression_metrics"]["coverage"], 0.79)
        lease = self.ledger.find_lease(admitted.lease_id)
        created = date.fromisoformat(lease.created_at[:10])
        self.assertEqual(lease.expires_on(), (created + timedelta(days=30)).isoformat())
        self.controller.revoke(lease.lease_id, "hidden drift")
        report = self.controller.report()
        self.assertEqual(report["active_leases"], 0)
        self.assertEqual(report["revoked_leases"], 1)
        self.assertEqual(report["suggested_parents"], [])
        self.assertTrue(any("lease revoked" in note for note in admitted.notes))

    def test_archive_keeps_diverse_approved_parents(self):
        first = self.controller.propose(self._candidate("literature.query_planner"), dry_run_ref="DRY-A")
        second = self.controller.propose(
            Candidate(kind="skill", target="figure.scene_rules", patch="add legend",
                      rationale="legend missing", predicted_effect="readability", scope="S6"),
            dry_run_ref="DRY-B",
        )
        self.controller.admit(first.episode_id, EvalEvidence("public", "passed", "A", {"coverage": 0.7}, 10),
                              EvalEvidence("hidden", "passed", "B", {"coverage": 0.7}, 5), "ok", "S1")
        self.controller.admit(second.episode_id, EvalEvidence("public", "passed", "C", {"audit": 0.9}, 10),
                              EvalEvidence("hidden", "passed", "D", {"audit": 0.9}, 5), "ok", "S6")
        rejected = self.controller.propose(self._candidate("literature.screening_order"), dry_run_ref="DRY-C")
        self.controller.reject(rejected.episode_id, "negative result")
        report = self.controller.report()
        self.assertEqual(report["archive"]["literature.query_planner"]["approved"], 1)
        self.assertEqual(report["archive"]["figure.scene_rules"]["approved"], 1)
        self.assertEqual(len(report["suggested_parents"]), 2)
        self.assertNotIn(rejected.episode_id, report["suggested_parents"])
        self.assertEqual(self.controller.archive().select_parents(1)[0], second.episode_id)

    def test_tf_rsi_fixture_pending_then_human_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            pending = run_fixture_trial(
                Path(tmp) / "pending.json", Path(tmp) / "pending-out", human_approve=False
            )
            self.assertTrue(pending["would_accept"])
            self.assertTrue(pending["simulation"])
            self.assertTrue(pending["rsi_report"]["simulation"])
            self.assertEqual(sum(1 for c in pending["candidates"] if "hidden" in c), 1)
            self.assertEqual(sum(1 for c in pending["candidates"] if c.get("hidden_held_out")), 2)
            self.assertIn("public cost", pending["selection"])
            self.assertEqual(pending["decision"], "pending_human")
            self.assertEqual(len(pending["candidates"]), 4)
            self.assertEqual(pending["rsi_report"]["active_leases"], 0)
            approved = run_fixture_trial(
                Path(tmp) / "approved.json", Path(tmp) / "approved-out", human_approve=True
            )
            self.assertEqual(approved["decision"], "approved")
            self.assertEqual(approved["rsi_report"]["active_leases"], 1)
            self.assertEqual(approved["rsi_report"]["approved"], 1)
            self.assertEqual(approved["rsi_report"]["rejected"], 3)
            self.assertTrue(any(c.get("pruned") == "min_sources" for c in approved["candidates"]))
            self.assertTrue(approved["rsi_report"]["simulation"])
            self.assertEqual(approved["rsi_report"]["capability_claims"], [])
            self.assertTrue(any("no capability claim" in w for w in approved["rsi_report"]["warnings"]))
            self.assertEqual(approved["prediction_audit"]["actual"]["hidden_recall_delta"], 0.0)
            self.assertLess(approved["prediction_audit"]["actual"]["hidden_cost_delta"], 0)
            self.assertLessEqual(approved["prediction_audit"]["actual"]["hidden_gap_delta"], 0)
            self.assertIn("coverage_gaps", approved["baseline"]["hidden"])
            audit = approved["rsi_report"]["prediction_audit"]
            self.assertEqual(len(audit), 1)
            self.assertEqual(audit[0]["decision"], "approved")
            self.assertLess(audit[0]["actual"]["hidden_cost_delta"], 0)
            confirmation = run_confirmation_trial(
                Path(tmp) / "approved.json", Path(tmp) / "confirmation"
            )
            self.assertTrue(confirmation["sealed"])
            self.assertFalse(confirmation["used_for_admission"])
            self.assertEqual(confirmation["status"], "confirmed")
            self.assertEqual(confirmation["policy"]["max_sources"], 2)
            self.assertEqual(confirmation["n"], 2)
            self.assertTrue(confirmation["passed"])
            self.assertGreaterEqual(confirmation["delta"]["gold_recall"], 0)
            self.assertLessEqual(confirmation["delta"]["cost"], 0)
            no_lease = run_confirmation_trial(
                Path(tmp) / "missing.json", Path(tmp) / "confirmation-none"
            )
            self.assertEqual(no_lease["status"], "no_active_lease")
            self.assertFalse(no_lease["used_for_admission"])

    def test_expired_and_conflicting_active_leases(self):
        def budget_candidate(size):
            return Candidate(
                kind="process",
                target="literature.retrieval.budget",
                patch=json.dumps({"max_sources": size}),
                rationale="cost observation",
                predicted_effect="non-inferior coverage with fewer sources",
                scope="S1/fixture",
            )

        public = EvalEvidence("public", "passed", "ART-PUB-TTL", {"coverage": 0.8}, 10)
        hidden = EvalEvidence("hidden", "passed", "ART-HID-TTL", {"coverage": 0.8}, 10)
        first = self.controller.propose(budget_candidate(2), dry_run_ref="DRY-TTL-1", simulation=True)
        second = self.controller.propose(budget_candidate(3), dry_run_ref="DRY-TTL-2", simulation=True)
        self.controller.evaluate(first.episode_id, public, hidden)
        self.controller.evaluate(second.episode_id, public, hidden)
        self.controller.admit(first.episode_id, public, hidden, "approved budget 2", "S1", 30)
        self.controller.admit(second.episode_id, public, hidden, "approved budget 3", "S1", 30)
        with self.assertRaises(RSIPolicyError):
            active_literature_policy(self.ledger_path)

        lease = next(l for l in self.ledger.leases if l.candidate_id == second.candidate.candidate_id)
        lease.created_at = (date.today() - timedelta(days=60)).isoformat() + "T00:00:00+00:00"
        self.ledger.save()
        resolved = active_literature_policy(self.ledger_path)
        self.assertEqual(resolved["max_sources"], 2)
        report = self.controller.report()
        self.assertEqual(report["expired_leases"], 1)
        self.assertEqual(report["active_leases"], 1)
        self.assertTrue(any("expired lease" in warning for warning in report["warnings"]))
        self.assertEqual(report["suggested_parents"], [first.episode_id])

    def test_real_ccby_trial_retains_negative_result_and_harness_claim_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            pending = run_real_trial(
                Path(tmp) / "real-pending.json", Path(tmp) / "real-pending"
            )
            self.assertEqual(pending["benchmark"], "rsi-ccby-4")
            self.assertFalse(pending["fixture"])
            self.assertFalse(pending["simulation"])
            self.assertIsNone(pending["chosen"])
            self.assertEqual(pending["decision"], "no_candidate")
            by_policy = {c["policy"]["policy_id"]: c for c in pending["candidates"]}
            self.assertEqual(by_policy["candidate-budget2"]["decision"], "rejected")
            self.assertLess(by_policy["candidate-budget2"]["near_ood"]["gold_recall"], 1.0)
            self.assertEqual(by_policy["candidate-budget3"]["decision"], "rejected")
            self.assertLess(by_policy["candidate-budget3"]["near_ood"]["gold_recall"], 1.0)
            self.assertTrue(by_policy["candidate-budget4"].get("hidden_held_out"))
            self.assertEqual(
                sum(1 for item in pending["rsi_report"]["prediction_audit"] if item["decision"] == "rejected"),
                2,
            )
            repeated = run_real_trial(
                Path(tmp) / "real-pending.json", Path(tmp) / "real-pending-repeat"
            )
            self.assertEqual(repeated["decision"], "no_candidate")
            self.assertEqual(repeated["rsi_report"]["episodes"], pending["rsi_report"]["episodes"])
            self.assertTrue(all(c.get("deduplicated") for c in repeated["candidates"]))

            ledger = StepLedger(Path(tmp) / "real-manual.json")
            controller = RSIController(ledger)
            record = controller.propose(
                Candidate(
                    kind="process", target="literature.retrieval.budget",
                    patch=json.dumps({"max_sources": 3, "retriever": "minilm"}),
                    rationale="harness-only probe",
                    predicted_effect="no capability claim", scope="S1/rsi-ccby-4-compare",
                ),
                dry_run_ref="DRY-REAL", simulation=False,
            )
            public = EvalEvidence("public", "passed", "ART-REAL-P", {"gold_recall": 1.0}, 12,
                                  simulation=False, claim_eligible=False)
            hidden = EvalEvidence("hidden", "passed", "ART-REAL-H", {"gold_recall": 1.0}, 12,
                                  simulation=False, claim_eligible=False)
            near = EvalEvidence("near_ood", "passed", "ART-REAL-N", {"gold_recall": 1.0}, 12,
                                simulation=False, claim_eligible=False)
            regression = EvalEvidence("regression", "passed", "ART-REAL-R", {"gold_recall": 1.0}, 12,
                                      simulation=False, claim_eligible=False)
            controller.evaluate(record.episode_id, public, hidden, near, regression)
            controller.admit(record.episode_id, public, hidden, "harness-only review",
                             "S1/rsi-ccby-4-compare", 30, near_ood_eval=near, regression_eval=regression)
            report = controller.report()
            self.assertEqual(report["active_leases"], 1)
            self.assertEqual(report["capability_claims"], [])
            self.assertTrue(any("harness-only" in warning for warning in report["warnings"]))
            resolved = resolve_active_harness(ledger.path, "S1/rsi-ccby-4-compare")
            self.assertEqual(resolved["retriever"], "minilm")
            self.assertEqual(resolved["max_sources"], 3)
            scoped = run_confirmation_trial(ledger.path, Path(tmp) / "real-manual-confirm")
            self.assertEqual(scoped["status"], "no_active_lease")

            confirm_ledger = StepLedger(Path(tmp) / "real-confirm-ledger.json")
            confirm_controller = RSIController(confirm_ledger)
            confirm_record = confirm_controller.propose(
                Candidate(
                    kind="process", target="literature.retrieval.budget",
                    patch=json.dumps({"max_sources": 3, "retriever": "bm25"}),
                    rationale="sealed confirm", predicted_effect="retain coverage",
                    scope="S1/rsi-ccby-4-confirm-bm25",
                ),
                dry_run_ref="DRY-CONFIRM", simulation=False,
            )
            confirm_controller.evaluate(confirm_record.episode_id, public, hidden, near, regression)
            confirm_controller.admit(
                confirm_record.episode_id, public, hidden, "sealed confirm",
                "S1/rsi-ccby-4-confirm-bm25", 30, near_ood_eval=near, regression_eval=regression,
            )
            sealed = run_real_confirmation(
                confirm_ledger.path, Path(tmp) / "real-confirm-out",
                "S1/rsi-ccby-4-confirm-bm25",
            )
            self.assertEqual(sealed["status"], "confirmed")
            self.assertTrue(sealed["sealed"])
            self.assertFalse(sealed["used_for_admission"])
            self.assertEqual(sealed["n"], 4)
            self.assertTrue(sealed["passed"])
            self.assertLessEqual(sealed["delta"]["coverage_gaps"], 0)

            bad = Path(tmp) / "bad-corpus.json"
            bad.write_text(json.dumps({
                "corpus_kind": "real", "fixture": False,
                "papers": [{
                    "source_id": "X", "fixture": False, "full_text": True,
                    "license": "ARXIV", "url": "https://example.org/x",
                    "sections": [{"name": "S", "text": "some text"}],
                }],
            }), encoding="utf-8")
            with self.assertRaises(RealCorpusError):
                RealCorpusRetriever(bad)

            root = Path(__file__).resolve().parents[1]
            def fake_encoder(texts):
                return [
                    [1.0 if "context engineering" in text.lower() else 0.0,
                     1.0 if "darwin" in text.lower() else 0.0]
                    for text in texts
                ]
            semantic = MiniLMRetriever(
                root / "modules" / "literature" / "fixtures" / "real_corpus.json",
                encoder=fake_encoder,
            )
            self.assertEqual(
                semantic.search("Agentic Context Engineering", 2)[0].source_id,
                "ARXIV-2510.04618",
            )
            if os.environ.get("RUN_MINILM_TEST") == "1":
                mini = run_real_trial(
                    Path(tmp) / "real-mini.json", Path(tmp) / "real-mini",
                    retriever_kind="minilm",
                )
                self.assertEqual(mini["retriever"], "minilm")
                self.assertEqual(mini["benchmark"], "rsi-ccby-4-minilm-abstract")
                self.assertEqual(mini["chosen"], "candidate-budget3")
                self.assertEqual(mini["rsi_report"]["capability_claims"], [])
                compare = run_real_trial(
                    Path(tmp) / "real-compare.json", Path(tmp) / "real-compare",
                    retriever_kind="compare",
                )
                self.assertEqual(compare["benchmark"], "rsi-ccby-4-compare")
                self.assertEqual(compare["chosen"], "candidate-minilm-budget3")
                by_id = {c["policy"]["policy_id"]: c for c in compare["candidates"]}
                self.assertEqual(by_id["candidate-bm25-budget2"]["decision"], "rejected")
                self.assertEqual(compare["rsi_report"]["capability_claims"], [])

    def test_reject_and_persistence(self):
        record = self.controller.reject(self.controller.propose(self._candidate()).episode_id, "cost too high")
        self.assertEqual(record.decision, "rejected")
        loaded = StepLedger.load(self.ledger_path)
        self.assertEqual(len(loaded.episodes), 1)
        self.assertEqual(loaded.episodes[0].decision, "rejected")
        self.assertEqual(loaded.episodes[0].reason, "cost too high")


class RejectionVerdictTest(unittest.TestCase):
    """The gate is judged too: a round that rejected nothing has taught nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = StepLedger(Path(self.tmp.name) / "rsi-ledger.json")
        self.controller = RSIController(self.ledger)

    def tearDown(self):
        self.tmp.cleanup()

    def _candidate(self, target="literature.query_planner"):
        return Candidate(
            kind="skill", target=target, patch="add a review subquery",
            rationale="coverage was thin", predicted_effect="one more full-text source",
            parent_id="incumbent", scope="S1/zh_core_journal",
        )

    def _evidence(self, split):
        return EvalEvidence(split, "passed", "ART-" + split, {"coverage": 0.8}, 2, claim_eligible=False)

    def _admit(self, dry_run_ref):
        record = self.controller.propose(self._candidate(), dry_run_ref=dry_run_ref)
        self.controller.admit(
            record.episode_id, self._evidence("public"), self._evidence("hidden"),
            "operator approval", "S1/zh", 30,
        )
        return record

    def test_empty_ledger_reads_no_episodes_not_a_clean_sheet(self):
        summary = ledger_story(self.ledger)["summary"]
        self.assertEqual(summary["gate_verdict"], "no_episodes")
        self.assertIsNone(summary["rejection_rate"])

    def test_pending_round_is_awaiting_a_decision_not_uninformative(self):
        self.controller.propose(self._candidate(), observation="thin coverage", dry_run_ref="DRY-V1")
        summary = ledger_story(self.ledger)["summary"]
        self.assertEqual(summary["decided"], 0)
        self.assertEqual(summary["gate_verdict"], "awaiting_decisions")

    def test_a_round_that_rejected_nothing_is_marked_gate_uninformative(self):
        self._admit("DRY-V2")
        summary = ledger_story(self.ledger)["summary"]
        self.assertEqual(summary["decided"], 1)
        self.assertEqual(summary["rejection_rate"], 0.0)
        self.assertEqual(summary["gate_verdict"], "gate_uninformative")

    def test_one_rejection_makes_the_round_informative_and_counts_it_once(self):
        self._admit("DRY-V3")
        rejected = self.controller.propose(
            self._candidate(target="experiment.runner"), dry_run_ref="DRY-V4"
        )
        self.controller.reject(rejected.episode_id, "cost too high")
        summary = ledger_story(self.ledger)["summary"]
        self.assertEqual(summary["decided"], summary["approved"] + summary["rejected"])
        self.assertEqual(summary["rejection_rate"], 0.5)
        self.assertEqual(summary["gate_verdict"], "informative")

    def test_gate_stops_name_the_gate_that_never_fired(self):
        self.controller.propose(self._candidate(), dry_run_ref="DRY-V5")
        stops = ledger_story(self.ledger)["summary"]["gate_stops"]
        self.assertIn("hidden:missing", stops)
        self.assertNotIn("dry-run:passed", stops)


if __name__ == "__main__":
    unittest.main()

"""The self-evolution return edge: a failed post-lease check must reach the runtime.

Promotion stays human-only. Demotion is automatic, because it only restores the incumbent.
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.evolution_active import ActivePolicyStore
from research_agent.evolution_policy import EvolutionPolicyStore
from research_agent.rsi import Candidate, EvalEvidence, RSIController, StepLedger


def _eval(split: str) -> EvalEvidence:
    return EvalEvidence(
        split=split,
        status="passed",
        artifact_ref="artifact-%s.json" % split,
        metrics={"coverage": 0.9},
        n=10,
        simulation=False,
        claim_eligible=True,
        evaluator="test-evaluator",
        artifact_sha256="a" * 64,
        task_pack_sha256="b" * 64,
    )


def _confirmation(status: str, passed: bool) -> dict:
    return {
        "sealed": True,
        "used_for_admission": False,
        "status": status,
        "passed": passed,
        "scope": "S1/test",
        "split": "hidden",
        "delta": {"coverage": -0.2 if not passed else 0.01},
    }


class ClosedEvolutionLoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger_path = self.root / "rsi.json"
        self.active_path = self.root / "evolution_active.json"
        self.policy_path = self.root / "evolution_policy.json"

    def _lease(self) -> str:
        controller = RSIController(StepLedger(self.ledger_path))
        record = controller.propose(
            Candidate(
                kind="process",
                target="literature.retrieval.budget",
                patch=json.dumps({"retriever": "bm25", "max_sources": 3}),
                rationale="healthy coverage at lower budget",
                predicted_effect="same coverage with fewer sources",
                scope="S1/test",
                proposer="test",
            ),
            dry_run_ref="DRY-1",
        )
        controller.admit(
            record.episode_id,
            _eval("public"),
            _eval("hidden"),
            "approved after review",
            "S1/test",
            30,
            near_ood_eval=_eval("near_ood"),
            regression_eval=_eval("regression"),
        )
        lease_id = [lease.lease_id for lease in controller.ledger.leases if lease.status == "active"][0]
        ActivePolicyStore(self.active_path).activate(
            self.ledger_path,
            "S1/test",
            "checked lease and splits",
            evolution_policy_path=self.policy_path,
        )
        return lease_id

    def test_revoked_lease_stops_reaching_the_runtime(self):
        lease_id = self._lease()
        store = ActivePolicyStore(self.active_path)
        self.assertIsNotNone(store.resolve("literature.retrieval.budget"))

        controller = RSIController(StepLedger.load(self.ledger_path))
        controller.revoke(lease_id, "human saw a regression")

        self.assertIsNone(store.resolve("literature.retrieval.budget"))
        snapshot = store.snapshot()
        self.assertIsNone(snapshot["active"])
        self.assertGreaterEqual(snapshot["auto_deactivations"], 1)
        self.assertTrue(
            any(item.get("event") == "auto_deactivated" for item in store._load()["history"])
        )

    def test_unregistered_scope_cannot_activate_even_with_a_lease(self):
        EvolutionPolicyStore(self.policy_path).update(
            enabled=True,
            scopes={
                "literature.memory_order": True,
                "literature.query_planner": True,
                "orchestrator.facet_budget": True,
                "literature.retrieval.budget": False,
            },
        )
        controller = RSIController(StepLedger(self.ledger_path))
        record = controller.propose(
            Candidate(
                kind="process",
                target="literature.retrieval.budget",
                patch=json.dumps({"retriever": "bm25", "max_sources": 3}),
                rationale="x",
                predicted_effect="y",
                scope="S1/test",
                proposer="test",
            ),
            dry_run_ref="DRY-2",
        )
        controller.admit(
            record.episode_id,
            _eval("public"),
            _eval("hidden"),
            "ok",
            "S1/test",
            30,
            near_ood_eval=_eval("near_ood"),
            regression_eval=_eval("regression"),
        )
        with self.assertRaises(Exception) as raised:
            ActivePolicyStore(self.active_path).activate(
                self.ledger_path,
                "S1/test",
                "reason",
                evolution_policy_path=self.policy_path,
            )
        self.assertIn("blocks target scope", str(raised.exception))

    def test_regression_confirmation_demotes_without_any_human_step(self):
        self._lease()
        store = ActivePolicyStore(self.active_path)
        self.assertIsNotNone(store.resolve("literature.retrieval.budget"))

        controller = RSIController(StepLedger.load(self.ledger_path))
        episode = controller.ledger.episodes[0]
        outcome = controller.record_confirmation(
            episode.episode_id, _confirmation("regressed", False), note="post-lease check"
        )
        self.assertTrue(outcome["demotion"]["performed"])
        self.assertIsNone(store.resolve("literature.retrieval.budget"))
        self.assertEqual(
            [lease.status for lease in controller.ledger.leases], ["revoked"]
        )

    def test_passed_confirmation_never_changes_state(self):
        lease_id = self._lease()
        controller = RSIController(StepLedger.load(self.ledger_path))
        episode = controller.ledger.episodes[0]
        outcome = controller.record_confirmation(
            episode.episode_id, _confirmation("confirmed", True), note="healthy"
        )
        self.assertFalse(outcome["demotion"]["performed"])
        self.assertEqual(
            [lease.status for lease in controller.ledger.leases if lease.lease_id == lease_id],
            ["active"],
        )
        self.assertIsNotNone(ActivePolicyStore(self.active_path).resolve("literature.retrieval.budget"))

    def test_snapshot_does_not_expose_the_ledger_path(self):
        self._lease()
        snapshot = ActivePolicyStore(self.active_path).snapshot()
        self.assertNotIn("ledger_path", json.dumps(snapshot["active"]))
        self.assertEqual(snapshot["active"]["lease_state"], "active")


if __name__ == "__main__":
    unittest.main()

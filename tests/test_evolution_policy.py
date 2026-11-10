import json
import tempfile
import unittest
from pathlib import Path

from research_agent.evolution_policy import EvolutionPolicyError, EvolutionPolicyStore


class EvolutionPolicyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "evolution_policy.json"
        self.store = EvolutionPolicyStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_policy_is_visible_and_scoped(self):
        snapshot = self.store.snapshot()
        self.assertTrue(snapshot["enabled"])
        self.assertEqual(
            {item["id"] for item in snapshot["scopes"]},
            {
                "literature.memory_order",
                "literature.query_planner",
                "orchestrator.facet_budget",
                "literature.retrieval.budget",
                "experiment.run.seeds",
                # The Harness² seam registers its editable surface here so that adopted
                # harness edits still pass the admission gate instead of bypassing it.
                "harness2.harness",
            },
        )
        # Every target the runtime can actually consume must be a registered scope,
        # otherwise the admission gate cannot govern it.
        from research_agent.evolution_active import SUPPORTED_TARGETS

        self.assertTrue(
            set(SUPPORTED_TARGETS).issubset({item["id"] for item in snapshot["scopes"]}),
            "consumable targets must be registered in SAFE_SCOPES",
        )
        self.assertTrue(all(item["enabled"] for item in snapshot["scopes"]))
        locked = {item["id"] for item in snapshot["locked"]}
        self.assertIn("claim.statement", locked)
        self.assertIn("gate.decision", locked)
        self.assertIn("heldout", locked)
        self.assertIn("never unlocks", snapshot["boundary"])

    def test_update_persists_master_and_scope_values(self):
        updated = self.store.update(
            enabled=False,
            scopes={"literature.query_planner": False, "orchestrator.facet_budget": True},
        )
        self.assertFalse(updated["enabled"])
        self.assertFalse(updated["scopes"]["literature.query_planner"])
        self.assertTrue(updated["scopes"]["orchestrator.facet_budget"])
        reopened = EvolutionPolicyStore(self.path).snapshot()
        self.assertFalse(reopened["enabled"])
        self.assertFalse(reopened["scopes"][0]["effective"])
        self.assertFalse(reopened["scopes"][1]["enabled"])
        self.assertFalse(reopened["scopes"][1]["effective"])
        self.assertTrue(reopened["scopes"][2]["enabled"])
        self.assertFalse(reopened["scopes"][2]["effective"])

    def test_immutable_and_unknown_scopes_are_rejected(self):
        with self.assertRaises(EvolutionPolicyError):
            self.store.update(scopes={"claim.statement": True})
        with self.assertRaises(EvolutionPolicyError):
            self.store.update(scopes={"gate.decision": True})
        with self.assertRaises(EvolutionPolicyError):
            self.store.update(scopes={"not.a.scope": True})
        with self.assertRaises(EvolutionPolicyError):
            self.store.update()
        with self.assertRaises(EvolutionPolicyError):
            self.store.update(enabled="yes")  # type: ignore[arg-type]

    def test_allow_candidate_matches_safe_scope_mapping(self):
        self.assertTrue(self.store.allows_candidate("skill", "literature.query_planner"))
        self.assertTrue(self.store.allows_candidate("process", "orchestrator.facet_budget"))
        self.store.update(scopes={"literature.query_planner": False})
        self.assertFalse(self.store.allows_candidate("skill", "literature.query_planner"))
        self.assertTrue(self.store.allows_candidate("process", "orchestrator.facet_budget"))
        self.assertTrue(self.store.allows_memory_order())
        self.store.update(enabled=False)
        self.assertFalse(self.store.allows_candidate("process", "orchestrator.facet_budget"))
        self.assertFalse(self.store.allows_memory_order())

    def test_export_writes_web_snapshot(self):
        output = Path(self.tmp.name) / "public" / "evolution-policy.json"
        result = self.store.export(output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(result["enabled"])
        self.assertEqual(payload["schema_version"], "evolution-policy-0.1")
        self.assertTrue(payload["scopes"])
        self.assertTrue(payload["locked"])


if __name__ == "__main__":
    unittest.main()

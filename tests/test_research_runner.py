import json
import tempfile
import unittest
from pathlib import Path

from research_agent.research_runner import ResearchRunner, load_research_tasks, run_research_cycle

ROOT = Path(__file__).resolve().parents[1]


class ResearchRunnerTest(unittest.TestCase):
    def test_fixture_queue_emits_observations_and_artifacts(self):
        tasks = load_research_tasks(ROOT / "research_agent" / "rsi_fixtures" / "research_tasks.json")
        with tempfile.TemporaryDirectory() as tmp:
            batch = ResearchRunner(Path(tmp)).run(tasks)
            self.assertTrue(batch["fixture"])
            self.assertEqual(batch["summary"]["runs"], 2)
            self.assertGreaterEqual(batch["summary"]["observations"], 4)
            self.assertEqual(batch["summary"]["errors"], 0)
            for run in batch["runs"]:
                self.assertTrue(Path(run["paths"]["demo"]).is_file())
                self.assertTrue(Path(run["paths"]["figure"]).is_file())
                demo = json.loads(Path(run["paths"]["demo"]).read_text(encoding="utf-8"))
                self.assertEqual(demo["modules"]["paper"]["claims"], [])
            kinds = {obs["kind"] for obs in batch["observations"]}
            self.assertIn("idea_needs_human", kinds)
            self.assertIn("paper_pending_evidence", kinds)
            self.assertIn("retrieval_cost", kinds)


    def test_research_to_rsi_cycle_is_explicitly_pending(self):
        tasks = load_research_tasks(ROOT / "research_agent" / "rsi_fixtures" / "research_tasks.json")
        with tempfile.TemporaryDirectory() as tmp:
            cycle = run_research_cycle(tasks, Path(tmp) / "ledger.json", Path(tmp) / "cycle", human_approve=False)
            self.assertEqual(cycle["research"]["tasks"], 2)
            self.assertGreater(cycle["research"]["observations"], 0)
            self.assertEqual(cycle["proposal"]["target"], "literature.retrieval.budget")
            self.assertIn("max_sources", cycle["proposal"]["patch"])
            self.assertEqual(cycle["proposal"]["trigger"], "retrieval_cost")
            self.assertTrue(cycle["rsi"]["report"]["prediction_audit"])
            self.assertEqual(cycle["rsi"]["decision"], "pending_human")
            self.assertEqual(cycle["rsi"]["report"]["active_leases"], 0)
            self.assertIsNone(cycle["rsi"]["active_policy"])
            self.assertIsNone(cycle["rsi"]["post_lease_research"])
            self.assertEqual(cycle["research"]["max_sources"], 6)
            approved = run_research_cycle(
                tasks, Path(tmp) / "ledger-approved.json", Path(tmp) / "cycle-approved", human_approve=True
            )
            self.assertEqual(approved["rsi"]["decision"], "approved")
            self.assertEqual(approved["rsi"]["report"]["active_leases"], 1)
            self.assertEqual(approved["rsi"]["active_policy"]["max_sources"], 2)
            self.assertEqual(approved["rsi"]["report"]["prediction_audit"][0]["decision"], "approved")
            self.assertEqual(approved["rsi"]["post_lease_research"]["max_sources"], 2)
            self.assertEqual(approved["rsi"]["post_lease_research"]["errors"], 0)
            self.assertTrue(Path(approved["rsi"]["post_lease_research"]["path"]).is_file())
            second = run_research_cycle(
                tasks, Path(tmp) / "ledger-approved.json", Path(tmp) / "cycle-second", human_approve=False
            )
            self.assertTrue(second["rsi"]["duplicate_active"])
            self.assertEqual(second["rsi"]["decision"], "active_unchanged")
            self.assertFalse(second["proposal"]["recorded"])
            self.assertEqual(second["rsi"]["report"]["episodes"], 1)
            self.assertEqual(second["rsi"]["post_lease_research"]["max_sources"], 2)
            self.assertEqual(second["rsi"]["report"]["capability_claims"], [])


if __name__ == "__main__":
    unittest.main()

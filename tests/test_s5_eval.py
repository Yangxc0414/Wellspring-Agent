import json
import tempfile
import unittest
from pathlib import Path

from research_agent.contracts import RunRequest
from research_agent.modules.run import RunAgent
from research_agent.s5_eval import (
    _evaluate, resolve_s5_seed_policy, run_s5_confirmation, run_s5_trial,
)
from research_agent.specs import SpecStore


class S5EvalTest(unittest.TestCase):
    def test_chemlab_uses_r2_and_holdout_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            agent = RunAgent(SpecStore().load("run"))
            result = _evaluate(
                agent, 2, "public", Path(tmp), dataset="chemlab",
                tasks=(
                    {"task_id": "S5-CHEM-A", "split": "public", "test_size": 0.2},
                    {"task_id": "S5-CHEM-B", "split": "public", "test_size": 0.4},
                ),
            )
            self.assertIn("mean_r2", result["metrics"])
            self.assertIn("mean_score", result["metrics"])
            self.assertNotIn("mean_accuracy", result["metrics"])
            self.assertEqual(result["metrics"]["cost"], 4)
            receipt = json.loads(Path(result["receipt"]).read_text(encoding="utf-8"))
            task_means = {task["task_id"]: task["mean"] for task in receipt["tasks"]}
            self.assertNotEqual(task_means["S5-CHEM-A"], task_means["S5-CHEM-B"])
            holdout = agent.execute(
                RunRequest("P-CHEM-HOLDOUT", dataset="chemlab", seeds=1, split="holdout"),
                Path(tmp) / "holdout",
            )
            self.assertEqual(holdout["capsule"]["dataset_id"], "chemlab:morgan:376train+42holdout")
            self.assertEqual(holdout["capsule"]["status"], "completed")
            confirmation = run_s5_confirmation(
                Path(tmp) / "ledger.json", Path(tmp) / "confirm", dataset="chemlab"
            )
            self.assertEqual(confirmation["status"], "no_active_lease")
            self.assertFalse(confirmation["used_for_admission"])

    def test_breast_cancer_selects_different_seed_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            trial = run_s5_trial(
                Path(tmp) / "bc-ledger.json", Path(tmp) / "bc-trial",
                dataset="breast_cancer",
            )
            self.assertEqual(trial["chosen"], 2)
            self.assertEqual(trial["decision"], "pending_human")
            self.assertLess(trial["prediction_audit"]["actual"]["hidden_cost_delta"], 0)
            approved = run_s5_trial(
                Path(tmp) / "bc-approved.json", Path(tmp) / "bc-approved",
                human_approve=True, dataset="breast_cancer",
            )
            self.assertEqual(approved["decision"], "approved")
            confirmation = run_s5_confirmation(
                Path(tmp) / "bc-approved.json", Path(tmp) / "bc-confirm",
                dataset="breast_cancer",
            )
            self.assertEqual(confirmation["status"], "confirmed")
            self.assertFalse(confirmation["used_for_admission"])
            self.assertLess(confirmation["delta"]["cost"], 0)

    def test_seed_budget_trial_selects_three_and_requires_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            pending = run_s5_trial(
                Path(tmp) / "ledger.json", Path(tmp) / "pending", human_approve=False
            )
            self.assertEqual(pending["chosen"], 3)
            self.assertEqual(pending["decision"], "pending_human")
            by_seeds = {item["seeds"]: item for item in pending["candidates"]}
            self.assertFalse(by_seeds[2]["public_ok"])
            self.assertTrue(by_seeds[3]["would_accept"])
            self.assertLess(pending["prediction_audit"]["actual"]["hidden_cost_delta"], 0)
            self.assertEqual(pending["rsi_report"]["capability_claims"], [])

            approved = run_s5_trial(
                Path(tmp) / "ledger-approved.json", Path(tmp) / "approved", human_approve=True
            )
            self.assertEqual(approved["decision"], "approved")
            self.assertEqual(approved["rsi_report"]["active_leases"], 1)
            self.assertEqual(approved["rsi_report"]["capability_claims"], [])
            lease = resolve_s5_seed_policy(
                Path(tmp) / "ledger-approved.json", "S5/demo/iris"
            )
            self.assertEqual(lease["seeds"], 3)
            applied = RunAgent(SpecStore().load("run")).execute(
                RunRequest("P-APPLY", seeds=lease["seeds"]),
                Path(tmp) / "applied",
            )
            self.assertEqual(applied["capsule"]["seeds"], [17, 18, 19])
            confirmation = run_s5_confirmation(
                Path(tmp) / "ledger-approved.json", Path(tmp) / "confirm",
                dataset="iris", scope="S5/demo/iris",
            )
            self.assertEqual(confirmation["status"], "confirmed")
            self.assertTrue(confirmation["sealed"])
            self.assertFalse(confirmation["used_for_admission"])
            self.assertEqual(confirmation["n"], 4)
            self.assertLess(confirmation["delta"]["cost"], 0)
            self.assertEqual(confirmation["ledger_confirmation"]["status"], "confirmed")


if __name__ == "__main__":
    unittest.main()

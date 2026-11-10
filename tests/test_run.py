import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.contracts import RunRequest
from research_agent.modules.run import RunAgent, RunError
from research_agent.specs import SpecStore


class RunAgentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = RunAgent(SpecStore().load("run"))

    def test_execute_creates_capsule_and_ea_then_claim_requires_human(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.agent.execute(RunRequest("P-TEST", seeds=3), root / "run")
            capsule = result["capsule"]
            evidence = result["evidence"]
            self.assertEqual(capsule["status"], "completed")
            self.assertEqual(len(capsule["metrics_by_seed"]), 3)
            self.assertGreaterEqual(capsule["mean"], 0.8)
            self.assertEqual(len(capsule["dataset_sha256"]), 64)
            self.assertEqual(len(capsule["code_sha256"]), 64)
            self.assertEqual(len(capsule["protocol_sha256"]), 64)
            metrics = json.loads((root / "run" / "metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(len(metrics), 3)
            self.assertEqual(
                hashlib.sha256((root / "run" / "metrics.json").read_bytes()).hexdigest(),
                evidence["sha256"],
            )
            self.assertTrue(evidence["immutable"])
            self.assertEqual(evidence["source"], "run")
            self.assertEqual(evidence["run_id"], capsule["run_id"])
            with self.assertRaises(RunError):
                self.agent.claim(
                    root / "run" / "run-capsule.json",
                    root / "run" / "ea.json",
                    "claim without signature",
                    "",
                    "S5/demo/iris",
                    root / "claim",
                )
            claim = self.agent.claim(
                root / "run" / "run-capsule.json",
                root / "run" / "ea.json",
                "Iris protocol reaches mean accuracy over three seeds.",
                "Checked capsule and EA hash.",
                "S5/demo/iris",
                root / "claim",
            )
            self.assertEqual(claim["claim"]["status"], "supported")
            self.assertEqual(claim["claim"]["evidence_refs"], [evidence["artifact_id"]])
            self.assertTrue((root / "claim" / "claim.json").is_file())

    def test_structured_claim_assertions_are_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.agent.execute(RunRequest("P-ASSERT", seeds=3), root / "run")
            mean = result["capsule"]["mean"]
            claim = self.agent.claim(
                root / "run" / "run-capsule.json",
                root / "run" / "ea.json",
                "Iris mean accuracy is at the measured level.",
                "Checked capsule and EA hash.",
                "S5/demo/iris",
                root / "claim-ok",
                assertions=[
                    {
                        "metric": "accuracy",
                        "comparator": ">=",
                        "value": mean,
                        "tolerance": 1e-9,
                    }
                ],
            )
            record = claim["claim"]
            self.assertEqual(record["claim_type"], "numerical")
            self.assertEqual(len(record["assertions"]), 1)
            self.assertEqual(record["assertions"][0]["status"], "pass")
            self.assertEqual(record["verification"]["passed"], 1)

            with self.assertRaises(RunError):
                self.agent.claim(
                    root / "run" / "run-capsule.json",
                    root / "run" / "ea.json",
                    "Iris mean accuracy is 2.0.",
                    "Checked capsule and EA hash.",
                    "S5/demo/iris",
                    root / "claim-bad",
                    assertions=[
                        {
                            "metric": "accuracy",
                            "comparator": ">=",
                            "value": 2.0,
                            "tolerance": 0.0,
                        }
                    ],
                )

    def test_chemlab_real_data_run_and_human_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.agent.execute(
                RunRequest("P-CHEMLAB", dataset="chemlab", seeds=2),
                root / "chem",
            )
            capsule = result["capsule"]
            self.assertEqual(capsule["status"], "completed")
            self.assertEqual(capsule["metric_name"], "r2")
            self.assertEqual(capsule["dataset_id"], "chemlab:morgan:418train+22test")
            self.assertEqual(len(capsule["metrics_by_seed"]), 2)
            self.assertIn("r2", capsule["metrics_by_seed"][0])
            self.assertIn("mae", capsule["metrics_by_seed"][0])
            self.assertGreater(capsule["metrics_by_seed"][0]["delta_r2"], 0)
            claim = self.agent.claim(
                root / "chem" / "run-capsule.json",
                root / "chem" / "ea.json",
                "ChemLab baseline reaches measured R2 on the fixed test split.",
                "Protocol validation only; checked hashes.",
                "S5/demo/chemlab",
                root / "chem-claim",
            )
            self.assertEqual(claim["claim"]["status"], "supported")
            self.assertTrue(claim["claim"]["evidence_refs"])
            self.assertIn("S5/demo/chemlab", claim["claim"]["warnings"][0])
            self.assertNotIn("iris", claim["claim"]["warnings"][0])

    def test_breast_cancer_scope_and_claim_scope_must_match_ea(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.agent.execute(
                RunRequest("P-BC", dataset="breast_cancer", seeds=2),
                root / "bc",
            )
            self.assertEqual(result["evidence"]["scope"], "S5/demo/breast_cancer")
            with self.assertRaises(RunError):
                self.agent.claim(
                    root / "bc" / "run-capsule.json",
                    root / "bc" / "ea.json",
                    "Wrongly scoped claim.",
                    "Checked hashes.",
                    "S5/demo/iris",
                    root / "wrong-claim",
                )
            claim = self.agent.claim(
                root / "bc" / "run-capsule.json",
                root / "bc" / "ea.json",
                "Breast-cancer protocol reaches measured accuracy.",
                "Protocol validation only; checked hashes.",
                "S5/demo/breast_cancer",
                root / "bc-claim",
            )
            self.assertEqual(claim["claim"]["scope"], "S5/demo/breast_cancer")
            self.assertIn("S5/demo/breast_cancer", claim["claim"]["warnings"][0])
            self.assertNotIn("iris", claim["claim"]["warnings"][0])

    def test_validation_rejects_unsupported_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RunError):
                self.agent.execute(RunRequest("P", seeds=0), Path(tmp))
            with self.assertRaises(RunError):
                self.agent.execute(RunRequest("P", dataset="unknown"), Path(tmp))


if __name__ == "__main__":
    unittest.main()

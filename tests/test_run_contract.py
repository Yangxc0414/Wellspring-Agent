import hashlib
import tempfile
import unittest
from pathlib import Path

from research_agent.run_contract import build_run_contract, verify_run_contract


def run_module(root: Path, seeds=(17, 18, 19)):
    for name in ("run-capsule.json", "ea.json", "metrics.json", "claim-draft.json"):
        (root / name).write_text("{}", encoding="utf-8")
    metrics = root / "metrics.json"
    capsule = {
        "run_id": "RUN-TEST",
        "protocol_id": "PROT-1",
        "dataset_id": "iris",
        "seeds": list(seeds),
        "metric_name": "accuracy",
        "mean": 0.93,
        "std": 0.01,
        "status": "completed",
    }
    evidence = {
        "path": str(metrics),
        "sha256": hashlib.sha256(metrics.read_bytes()).hexdigest(),
    }
    return {"capsule": capsule, "evidence": evidence, "paths": {"capsule": str(root / "run-capsule.json")}}


class RunContractTest(unittest.TestCase):
    def test_contract_and_allowlist_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = run_module(root)
            contract = build_run_contract(
                {"protocol_id": "PROT-1", "design_sha256": "a" * 64},
                {"seeds": 3},
                module,
            )
            self.assertEqual(len(contract["contract_sha256"]), 64)
            check = verify_run_contract(contract, module, run_dir=root)
            self.assertEqual(check["status"], "attention")
            self.assertEqual(check["blockers"], [])
            self.assertTrue(any("min_delta" in item for item in check["warnings"]))
            ids = {item["id"] for item in check["checks"]}
            self.assertIn("identity.seeds", ids)
            self.assertIn("evidence.hash", ids)
            self.assertIn("artifacts.required", ids)

    def test_seed_mismatch_and_missing_artifact_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = run_module(root)
            contract = build_run_contract(
                {"protocol_id": "PROT-1", "design_sha256": "a" * 64},
                {},
                module,
            )
            module["capsule"]["seeds"] = [17]
            check = verify_run_contract(contract, module, run_dir=root)
            self.assertEqual(check["status"], "blocked")
            self.assertTrue(any("identity.seeds" in item for item in check["blockers"]))
            module["capsule"]["seeds"] = [17, 18, 19]
            (root / "ea.json").unlink()
            missing = verify_run_contract(contract, module, run_dir=root)
            self.assertEqual(missing["status"], "blocked")
            self.assertTrue(any("artifacts.required" in item for item in missing["blockers"]))

    def test_min_delta_uses_paired_baseline_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = run_module(root)
            module["capsule"]["metric_name"] = "r2"
            module["capsule"]["metrics_by_seed"] = [
                {"seed": 17, "r2": 0.52, "baseline_r2": 0.40},
                {"seed": 18, "r2": 0.55, "baseline_r2": 0.42},
                {"seed": 19, "r2": 0.48, "baseline_r2": 0.41},
            ]
            contract = build_run_contract(
                {"protocol_id": "PROT-1", "design_sha256": "a" * 64, "min_delta": 0.05},
                {},
                module,
            )
            passed = verify_run_contract(contract, module, run_dir=root)
            self.assertEqual(passed["status"], "pass", passed)
            min_delta = next(item for item in passed["checks"] if item["id"] == "min_delta")
            self.assertEqual(min_delta["status"], "pass")
            self.assertIn("observed=0.106667", min_delta["detail"])

            module["capsule"]["metrics_by_seed"] = [
                {"seed": 17, "r2": 0.41, "baseline_r2": 0.40},
            ]
            failed = verify_run_contract(contract, module, run_dir=root)
            self.assertEqual(failed["status"], "blocked", failed)
            self.assertTrue(any("min_delta" in item for item in failed["blockers"]))

    def test_protocol_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = run_module(root)
            contract = build_run_contract({"protocol_id": "PROT-1"}, {}, module)
            module["capsule"]["protocol_id"] = "PROT-OTHER"
            check = verify_run_contract(contract, module, run_dir=root)
            self.assertEqual(check["status"], "blocked")
            self.assertTrue(any("identity.protocol" in item for item in check["blockers"]))


if __name__ == "__main__":
    unittest.main()

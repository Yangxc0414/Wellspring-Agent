import tempfile
import unittest
from pathlib import Path

from research_agent.benchmark import run_internal_benchmark


class InternalBenchmarkTest(unittest.TestCase):
    def test_support_audit_oracle_nop(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = run_internal_benchmark(Path(tmp), include_closure=False)
            self.assertEqual(report["summary"]["failed"], 0)
            self.assertIn("not an external capability benchmark", report["boundary"])
            self.assertTrue((Path(tmp) / "benchmark.json").is_file())
            case = report["cases"][0]
            self.assertEqual(case["case_id"], "support-oracle-nop")
            self.assertEqual(case["nop_supported"], 0)
            self.assertEqual(case["heuristic_supported"], 0)

    def test_strict_flow_and_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = run_internal_benchmark(Path(tmp), include_closure=True)
            self.assertEqual(report["summary"]["failed"], 0, report)
            case = next(
                item for item in report["cases"]
                if item["case_id"] == "strict-pre-registration-and-closure"
            )
            self.assertEqual(case["status"], "pass")
            self.assertEqual(case["closure"], "ready")


if __name__ == "__main__":
    unittest.main()

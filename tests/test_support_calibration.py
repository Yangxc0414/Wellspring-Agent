import tempfile
import unittest
from pathlib import Path

from research_agent.support_calibration import (
    evaluate_support_cases,
    load_cases,
    render_support_calibration,
)


class SupportCalibrationTest(unittest.TestCase):
    def test_cases_load_with_expected_and_mode(self):
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 10)
        ids = {case["id"] for case in cases}
        self.assertIn("CAL-01", ids)
        self.assertTrue(any(case["expected"] == "not_required" for case in cases))
        self.assertTrue(any(case["expected"] == "contradicted" for case in cases))

    def test_perfect_fake_judge_scores_one_and_skips_proposals(self):
        cases = load_cases()
        expected = {case["id"]: case["expected"] for case in cases}
        claim_cases = [case for case in cases if case["mode"] == "claim"]
        calls = {"count": 0}

        def judge(payload):
            calls["count"] += 1
            item = payload["items"][0]
            refs = [entry["ref"] for entry in item["evidence"]]
            return [
                {
                    "id": item["id"],
                    "status": expected[item["id"]],
                    "rationale": "calibration fake",
                    "evidence_refs": refs,
                }
            ]

        report = evaluate_support_cases(
            cases, judge, votes=3, model_id="fake:calibration"
        )
        self.assertEqual(report["accuracy"], 1.0)
        self.assertEqual(report["correct"], len(cases))
        self.assertEqual(calls["count"], len(claim_cases) * 3)
        self.assertEqual(report["failures"], [])
        self.assertIn("not_required", report["per_status"])

    def test_wrong_judge_produces_failures_and_metrics(self):
        cases = load_cases()

        def judge(payload):
            item = payload["items"][0]
            return [
                {
                    "id": item["id"],
                    "status": "insufficient",
                    "rationale": "always insufficient",
                    "evidence_refs": [],
                }
            ]

        report = evaluate_support_cases(cases, judge, votes=1, model_id="fake:wrong")
        self.assertLess(report["accuracy"], 1.0)
        self.assertTrue(report["failures"])
        self.assertGreater(report["confusion"]["supported"]["insufficient"], 0)
        markdown = render_support_calibration(report)
        self.assertIn("Support Judge Calibration", markdown)
        self.assertIn("Failures", markdown)


if __name__ == "__main__":
    unittest.main()

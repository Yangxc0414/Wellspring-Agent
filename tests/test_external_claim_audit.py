import unittest
from pathlib import Path

from research_agent.external_claim_audit import (
    build_external_claim_package,
    run_claim_audit,
)

EXTERNAL_ROOT = Path("D:/Users/20691/Downloads/Research Skill调研/scientific-agent-skills-main")


def _registry(status: str = "verified_anchor"):
    return {
        "entries": [
            {
                "section": "结果",
                "sentence": "T80 为 0.93。",
                "evidence_rows": [
                    {
                        "span_id": "S1",
                        "quote": "T80 为 0.93。",
                        "status": status,
                    }
                ],
            }
        ]
    }


class ExternalClaimAuditTest(unittest.TestCase):
    def test_package_builds_markers_and_verified_sources(self):
        package = build_external_claim_package(
            _registry(), {"spans": [{"span_id": "S1", "source_id": "SRC-1"}]}
        )
        self.assertEqual(package["claim_count"], 1)
        self.assertEqual(package["source_count"], 1)
        self.assertIn("[claim:C001]", package["claim_lines"][0])
        self.assertIn("[evidence:E001]", package["claim_lines"][0])
        self.assertEqual(package["sources"][0]["verification"]["status"], "verified")

    @unittest.skipUnless(EXTERNAL_ROOT.is_dir(), "external skill root not installed")
    def test_external_claim_audit_passes_verified_anchor(self):
        result = run_claim_audit(
            _registry(),
            {"spans": [{"span_id": "S1", "source_id": "SRC-1"}]},
            EXTERNAL_ROOT,
        )
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["summary"]["errors"], 0)

    @unittest.skipUnless(EXTERNAL_ROOT.is_dir(), "external skill root not installed")
    def test_external_claim_audit_blocks_unverified_evidence(self):
        result = run_claim_audit(
            _registry("candidate"),
            {"spans": [{"span_id": "S1", "source_id": "SRC-1"}]},
            EXTERNAL_ROOT,
        )
        self.assertEqual(result["status"], "blocked", result)
        codes = {item.get("code") for item in result["issues"]}
        self.assertTrue(
            {"CLAIM_NOT_VERIFIED", "UNVERIFIED_CLAIM_EVIDENCE"} & codes,
            codes,
        )


if __name__ == "__main__":
    unittest.main()

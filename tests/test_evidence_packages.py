import unittest

from research_agent.evidence_packages import summarize_evidence_packages


class EvidencePackageTest(unittest.TestCase):
    def test_empty_bundle_reports_missing_and_not_run(self):
        packages = summarize_evidence_packages({}, [])
        by_id = {item["id"]: item for item in packages}
        self.assertEqual(len(packages), 10)
        self.assertEqual(by_id["literature"]["status"], "missing")
        self.assertEqual(by_id["claim"]["status"], "missing")
        self.assertEqual(by_id["closure"]["status"], "not_run")
        self.assertIn("摘要-only", by_id["literature"]["boundary"])

    def test_ready_bundle_exposes_package_evidence(self):
        modules = {
            "literature": {
                "hits": [{"full_text": True}, {"full_text": False}],
                "spans": [{"span_id": "S-1"}],
                "coverage": {"gaps": [{"code": "G-1"}]},
                "brief": {"saturation": "saturated", "gaps": []},
            },
            "idea": {"candidates": [{"idea_id": "IDEA-01"}]},
            "experiment": {
                "design_id": "DESIGN-1",
                "status": "ready_for_g2",
                "baseline": "majority",
                "primary_metric": "accuracy",
                "seeds": 3,
            },
            "protocol": {
                "protocol_id": "PROT-1",
                "design_sha256": "a" * 64,
                "status": "frozen",
            },
            "run": {
                "capsule": {
                    "run_id": "RUN-1",
                    "dataset_id": "iris",
                    "seeds": [1, 2, 3],
                    "metric_name": "accuracy",
                    "status": "completed",
                },
                "evidence": {"artifact_id": "EA-1"},
                "claim_draft_record": {"statement": "draft", "scope": "S5/demo/iris"},
                "result_figure": {"figure_id": "FIG-1"},
            },
            "figure": {"figure_id": "FIG-SCHEMATIC"},
            "paper": {
                "claims": ["CLAIM-1"],
                "slots": [{"id": "result.primary", "status": "bound_claim"}],
                "draft": [{"section": "Introduction"}],
                "profile": {"venue_type": "en_conference"},
            },
        }
        by_id = {
            item["id"]: item
            for item in summarize_evidence_packages(
                modules, [{"gate": "G5", "status": "pass", "reason": "closed"}]
            )
        }
        self.assertEqual(by_id["literature"]["status"], "ready")
        self.assertEqual(by_id["idea"]["status"], "needs_human")
        self.assertEqual(by_id["design"]["status"], "needs_human")
        self.assertEqual(by_id["protocol"]["status"], "ready")
        self.assertEqual(by_id["run"]["status"], "ready")
        self.assertEqual(by_id["ea"]["status"], "ready")
        self.assertEqual(by_id["claim"]["status"], "ready")
        self.assertEqual(by_id["figure"]["status"], "ready")
        self.assertEqual(by_id["paper"]["status"], "ready")
        self.assertEqual(by_id["closure"]["status"], "ready")

    def test_draft_and_schematic_do_not_look_final(self):
        modules = {
            "literature": {
                "hits": [{"full_text": True}],
                "spans": [{"span_id": "S-1"}],
                "brief": {"saturation": "partial"},
            },
            "experiment": {"status": "needs_human", "hypothesis": "h", "seeds": 3},
            "run": {
                "capsule": {"run_id": "RUN-1", "dataset_id": "iris", "seeds": [1], "status": "completed"},
                "claim_draft_record": {"statement": "draft", "scope": "S5/demo/iris"},
            },
            "figure": {"figure_id": "FIG-SCHEMATIC"},
            "paper": {"slots": [{"id": "result.primary", "status": "pending_evidence"}], "draft": [{}]},
        }
        by_id = {item["id"]: item for item in summarize_evidence_packages(modules, [])}
        self.assertEqual(by_id["literature"]["status"], "partial")
        self.assertEqual(by_id["claim"]["status"], "needs_signature")
        self.assertEqual(by_id["figure"]["status"], "partial")
        self.assertEqual(by_id["paper"]["status"], "needs_human")
        self.assertEqual(by_id["closure"]["status"], "not_run")
        self.assertIn("未签", by_id["claim"]["detail"])


if __name__ == "__main__":
    unittest.main()

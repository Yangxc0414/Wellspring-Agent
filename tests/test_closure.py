import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.closure import ClosureAgent, ClosureError, audit_pipeline_bundle
from research_agent.pipeline import PipelineRequest, PipelineRunner, write_pipeline_artifacts


class ClosureTest(unittest.TestCase):
    def _write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def test_blocked_until_all_slots_and_ea_hash_are_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "metrics.json"
            metrics.write_text("[]\n", encoding="utf-8")
            ea = {
                "artifact_id": "EA-TEST",
                "kind": "metric",
                "run_id": "RUN-TEST",
                "path": str(metrics),
                "sha256": hashlib.sha256(metrics.read_bytes()).hexdigest(),
                "source": "run",
                "captured_at": "2026-10-24T00:00:00+00:00",
                "immutable": True,
                "scope": "S5/demo/iris",
            }
            claim = {
                "claim_id": "CLM-TEST",
                "statement": "demo",
                "evidence_refs": ["EA-TEST"],
                "scope": "S5/demo/iris",
                "status": "supported",
                "human_reason": "checked",
            }
            capsule = root / "run-capsule.json"
            capsule.write_text(
                json.dumps({"status": "completed", "run_id": "RUN-TEST"}),
                encoding="utf-8",
            )
            bib_entries = [
                {"doi": "10.48550/arxiv.2505.22954", "title": "A", "authors": ["X"], "year": 2025, "url": "https://example.org/a", "response_sha256": "a" * 64},
                {"doi": "10.48550/arxiv.2504.15228", "title": "B", "authors": ["Y"], "year": 2025, "url": "https://example.org/b", "response_sha256": "b" * 64},
            ]
            bib_hash = hashlib.sha256(
                json.dumps(bib_entries, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
            protocol = {
                "protocol_id": "PROT-TEST",
                "status": "frozen",
                "human_reason": "signed",
                "limitation": "demo only",
                "capsule_sha256": hashlib.sha256(capsule.read_bytes()).hexdigest(),
            }
            demo = {
                "modules": {
                    "bibliography": {
                        "card_id": "BIB-TEST",
                        "status": "verified_datacite_snapshot",
                        "verification_source": "datacite_api_snapshot",
                        "entry_count": 2,
                        "entries": bib_entries,
                        "card_sha256": bib_hash,
                    },
                    "protocol": protocol,
                    "run": {
                        "status": "completed",
                        "capsule": {"status": "completed"},
                        "evidence": ea,
                        "paths": {"capsule": str(capsule)},
                    },
                    "paper": {
                        "claims": ["CLM-TEST"],
                        "slots": [
                            {"slot_id": "result.primary", "status": "bound_claim"},
                            {"slot_id": "limitation", "status": "pending_evidence"},
                        ],
                    },
                }
            }
            demo_path = root / "demo.json"
            claim_path = root / "claim.json"
            figure_svg = root / "result-figure.svg"
            figure_svg.write_text("<svg/>\n", encoding="utf-8")
            demo["modules"]["run"]["result_figure"] = {
                "figure_id": "FIG-TEST",
                "manifest": {
                    "figure_id": "FIG-TEST",
                    "schematic": False,
                    "svg_sha256": hashlib.sha256(figure_svg.read_bytes()).hexdigest(),
                    "evidence_refs": ["EA-TEST"],
                },
                "paths": {"svg": str(figure_svg)},
            }
            self._write(demo_path, demo)
            self._write(claim_path, claim)
            self._write(root / "protocol.json", protocol)
            self._write(root / "bibliography.json", demo["modules"]["bibliography"])
            self._write(root / "result-figure.manifest.json", demo["modules"]["run"]["result_figure"]["manifest"])
            agent = ClosureAgent()
            report = agent.check(demo_path, claim_path, root / "closure")
            self.assertEqual(report["report"]["status"], "blocked")
            self.assertEqual(report["report"]["unresolved"], ["limitation"])
            obligations = json.loads(Path(report["obligations"]).read_text(encoding="utf-8"))
            self.assertGreaterEqual(obligations["summary"]["open"], 1)
            self.assertEqual(obligations["summary"]["status"], "blocked")
            self.assertTrue(obligations["obligations"][0]["history"])
            with self.assertRaises(ClosureError):
                agent.sign(
                    Path(report["path"]), demo_path, claim_path,
                    "not ready", root / "signature",
                )

            demo["modules"]["paper"]["slots"][1]["status"] = "bound_claim"
            demo["modules"]["paper"]["slots"].append({"slot_id": "citation.related", "status": "bound_bibliography"})
            demo["modules"]["paper"]["slots"].append({"slot_id": "result.figure", "status": "bound_figure"})
            self._write(demo_path, demo)

            protocol_file = root / "protocol.json"
            protocol_file.unlink()
            missing_protocol = agent.check(demo_path, claim_path, root / "closure-missing-protocol")
            missing_checks = {item["name"]: item for item in missing_protocol["report"]["checks"]}
            self.assertEqual(missing_protocol["report"]["status"], "blocked")
            self.assertEqual(missing_checks["protocol_artifact"]["status"], "fail")
            self._write(protocol_file, protocol)

            panel_path = root / "support-panel.json"
            self._write(
                panel_path,
                {"status": "needs_human", "pending_human": ["SUP-01"]},
            )
            pending_panel = agent.check(demo_path, claim_path, root / "closure-panel")
            panel_checks = {
                item["name"]: item for item in pending_panel["report"]["checks"]
            }
            self.assertEqual(pending_panel["report"]["status"], "blocked")
            self.assertEqual(panel_checks["support_panel_ready"]["status"], "fail")
            self.assertIn(str(panel_path), pending_panel["report"]["artifact_refs"])

            self._write(panel_path, {"status": "ready", "pending_human": []})
            ready = agent.check(demo_path, claim_path, root / "closure-ready")
            self.assertEqual(ready["report"]["status"], "ready")
            self.assertEqual(ready["report"]["closure_profile"], "canonical_run")
            self.assertIn(str(protocol_file), ready["report"]["artifact_refs"])
            self.assertIn(str(root / "bibliography.json"), ready["report"]["artifact_refs"])
            self.assertIn(str(root / "result-figure.manifest.json"), ready["report"]["artifact_refs"])
            self.assertIn(str(panel_path), ready["report"]["artifact_refs"])
            signed = agent.sign(
                Path(ready["path"]), demo_path, claim_path,
                "checked demo scope", root / "signature",
            )
            self.assertFalse(signed["signature"]["submission"])
            self.assertTrue(Path(signed["manifest"]).is_file())

            published = agent.publish(Path(signed["manifest"]), root / "bundles")
            self.assertEqual(published["status"], "sealed")
            self.assertTrue(published["signed"])
            self.assertGreaterEqual(published["artifact_count"], 8)
            bundle = Path(published["bundle"])
            verification = agent.verify_bundle(bundle)
            self.assertEqual(verification["status"], "clean")
            self.assertGreaterEqual(verification["artifact_count"], 5)
            with self.assertRaises(ClosureError):
                agent.publish(Path(signed["manifest"]), root / "bundles")

            sealed = json.loads((bundle / "bundle-manifest.json").read_text(encoding="utf-8"))
            artifact = next(entry for entry in sealed["files"] if entry["role"] == "artifact")
            (bundle / artifact["bundle_path"]).write_text("tampered\n", encoding="utf-8")
            self.assertEqual(agent.verify_bundle(bundle)["status"], "stale")

            bad_manifest = root / "bad-export.json"
            payload = json.loads(Path(signed["manifest"]).read_text(encoding="utf-8"))
            payload["submission"] = True
            self._write(bad_manifest, payload)
            with self.assertRaises(ClosureError):
                agent.publish(bad_manifest, root / "bad-bundle")

            metrics.write_text("tampered\n", encoding="utf-8")
            stale = agent.check(demo_path, claim_path, root / "closure-tampered")
            self.assertEqual(stale["report"]["status"], "blocked")
            checks = {item["name"]: item for item in stale["report"]["checks"]}
            self.assertEqual(checks["ea_hash"]["status"], "fail")
            with self.assertRaises(ClosureError):
                agent.sign(
                    Path(ready["path"]), demo_path, claim_path,
                    "stale report must not sign", root / "signature-stale",
                )
            self.assertFalse((root / "signature-stale" / "signature.json").exists())


class StaticClosureAuditTest(unittest.TestCase):
    def test_pipeline_bundle_is_structurally_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = PipelineRunner().run(
                PipelineRequest(
                    topic="钙钛矿 界面 钝化 湿热稳定性",
                    language="zh",
                    venue_type="zh_core_journal",
                    run_id="PIPE-AUDIT-TEST",
                )
            )
            write_pipeline_artifacts(result, root)
            report = audit_pipeline_bundle(root)
            self.assertEqual(report["status"], "structurally_consistent_but_not_closed")
            self.assertEqual(report["summary"]["fail"], 0)
            checks = {item["id"]: item for item in report["checks"]}
            self.assertEqual(checks["s1_span_source_link"]["status"], "pass")
            self.assertEqual(checks["s2_candidate_grounding"]["status"], "pass")
            self.assertEqual(checks["s4_design_grounding"]["status"], "pass")
            self.assertEqual(checks["paper_readable_draft"]["status"], "pass")

    def test_audit_fails_when_a_span_cites_an_unknown_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = PipelineRunner().run(
                PipelineRequest(
                    topic="钙钛矿 界面 钝化 湿热稳定性",
                    language="zh",
                    venue_type="zh_core_journal",
                    run_id="PIPE-AUDIT-TAMPER",
                )
            )
            write_pipeline_artifacts(result, root)
            demo_path = root / "demo.json"
            demo = json.loads(demo_path.read_text(encoding="utf-8"))
            demo["modules"]["literature"]["spans"][0]["source_id"] = "FX-MISSING"
            demo_path.write_text(json.dumps(demo, ensure_ascii=False), encoding="utf-8")
            report = audit_pipeline_bundle(root)
            self.assertEqual(report["status"], "structural_failure")
            checks = {item["id"]: item for item in report["checks"]}
            self.assertEqual(checks["s1_span_source_link"]["status"], "fail")


if __name__ == "__main__":
    unittest.main()

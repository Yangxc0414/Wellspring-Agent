import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research_agent.lineage import LineageAgent, LineageError, write_manifest


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LineageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "bundle"
        root = self.root
        (root / "run" / "run").mkdir(parents=True)
        (root / "bound").mkdir(parents=True)
        (root / "claim").mkdir(parents=True)
        (root / "protocol").mkdir(parents=True)
        (root / "bibliography").mkdir(parents=True)
        (root / "closure").mkdir(parents=True)
        (root / "signature").mkdir(parents=True)

        metrics = root / "run" / "run" / "metrics.json"
        metrics.write_text("[{\"seed\": 17, \"r2\": 0.2}]\n", encoding="utf-8")
        capsule = {
            "run_id": "RUN-1",
            "protocol_id": "P-1",
            "protocol_sha256": "p" * 64,
            "dataset_id": "demo",
            "dataset_sha256": "d" * 64,
            "code_sha256": "c" * 64,
            "model": "ridge",
            "seeds": [17],
            "test_size": 0.3,
            "metric_name": "r2",
            "metrics_by_seed": [{"seed": 17, "r2": 0.2}],
            "mean": 0.2,
            "std": 0.0,
            "environment": {},
            "status": "completed",
            "artifacts": {"metrics": str(metrics)},
            "created_at": "2026-01-01T00:00:00+00:00",
            "warnings": [],
        }
        _write(root / "run" / "run" / "run-capsule.json", capsule)

        ea = {
            "artifact_id": "EA-1",
            "kind": "metric",
            "run_id": "RUN-1",
            "path": str(metrics),
            "sha256": _sha(metrics),
            "source": "run",
            "captured_at": "2026-01-01T00:00:00+00:00",
            "immutable": True,
            "scope": "S5/demo/chem",
        }
        _write(root / "run" / "run" / "ea.json", ea)

        claim = {
            "claim_id": "CLM-1",
            "statement": "Ridge is better.",
            "evidence_refs": ["EA-1"],
            "scope": "S5/demo/chem",
            "status": "supported",
            "human_reason": "checked",
            "created_at": "2026-01-01T00:00:00+00:00",
            "warnings": [],
        }
        _write(root / "claim" / "claim.json", claim)

        _write(root / "protocol" / "protocol-card.json", {
            "protocol_id": "PROT-1",
            "status": "frozen",
            "human_reason": "checked",
            "limitation": "demo",
            "capsule_sha256": _sha(root / "run" / "run" / "run-capsule.json"),
        })
        _write(root / "bibliography" / "bibliography-card.json", {
            "card_id": "BIB-1",
            "status": "verified_datacite_snapshot",
            "entry_count": 2,
        })

        svg = root / "run" / "run" / "result-figure.svg"
        svg.write_text("<svg/>\n", encoding="utf-8")
        figure = {
            "figure_id": "FIG-1",
            "schematic": False,
            "svg_sha256": _sha(svg),
            "data_sha256": _sha(metrics),
            "evidence_refs": ["EA-1"],
        }
        _write(root / "run" / "run" / "result-figure.manifest.json", figure)

        paper = {
            "title": "Demo paper",
            "status": "needs_evidence",
            "claims": ["CLM-1"],
            "slots": [
                {"slot_id": "method.protocol", "section": "Method", "status": "bound_protocol"},
                {"slot_id": "result.primary", "section": "Results", "status": "bound_claim"},
                {"slot_id": "result.figure", "section": "Results", "status": "bound_figure"},
                {"slot_id": "limitation", "section": "Discussion", "status": "bound_scope"},
                {"slot_id": "citation.related", "section": "Related Work", "status": "bound_bibliography"},
            ],
        }
        _write(root / "bound" / "paper.json", paper)
        _write(root / "bound" / "demo.json", {
            "modules": {
                "run": {"capsule": capsule, "evidence": ea},
                "paper": paper,
                "protocol": {"protocol_id": "PROT-1", "status": "frozen"},
                "bibliography": {"card_id": "BIB-1", "status": "verified_datacite_snapshot"},
            }
        })
        _write(root / "closure" / "closure-report.json", {
            "report_id": "CLR-1",
            "status": "ready",
            "checks": [],
            "unresolved": [],
        })
        _write(root / "signature" / "signature.json", {
            "signature_id": "SIG-1",
            "report_id": "CLR-1",
            "human_reason": "checked",
            "submission": False,
        })
        _write(root / "signature" / "export-manifest.json", {
            "report_id": "CLR-1",
            "submission": False,
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_verifies_hmac_signature_when_signer_store_is_supplied(self):
        from research_agent.signers import SignerStore

        signers = SignerStore(Path(self.tmp.name) / "signers.json")
        signer = signers.create("PI")
        export_path = self.root / "signature" / "export-manifest.json"
        payload = {
            "schema_version": "closure-signature-0.2",
            "report_id": "CLR-1",
            "export_manifest_sha256": _sha(export_path),
            "human_reason": "checked",
            "submission": False,
        }
        signed = signers.sign(signer["signer_id"], payload)
        _write(self.root / "signature" / "signature.json", {
            "signature_id": "SIG-1",
            "report_id": "CLR-1",
            "human_reason": "checked",
            "submission": False,
            **signed,
        })
        manifest = LineageAgent().build(self.root, signer_store=signers)
        signature = next(node for node in manifest["nodes"] if node["kind"] == "signature")
        self.assertIs(signature["metadata"]["signature_verified"], True)
        self.assertEqual(signature["metadata"]["scheme"], "hmac-sha256-local")

    def test_build_contains_claim_slots_and_signature_lineage(self):
        manifest = LineageAgent().build(self.root)
        self.assertEqual(manifest["status"], "complete")
        kinds = {node["kind"] for node in manifest["nodes"]}
        self.assertTrue({"dataset", "run", "evidence", "claim", "protocol", "bibliography", "figure", "paper_slot", "paper", "closure", "signature"} <= kinds)
        claim = next(node for node in manifest["nodes"] if node["kind"] == "claim")
        self.assertEqual(claim["label"], "CLM-1")
        self.assertIn("ea:EA-1", claim["dependencies"])
        closure = next(node for node in manifest["nodes"] if node["kind"] == "closure")
        self.assertIn("paper:manuscript", closure["dependencies"])
        self.assertTrue(any(node["node_id"].startswith("signature:") for node in manifest["nodes"]))

    def test_dataset_hash_change_propagates_to_claim_slots_closure_signature(self):
        agent = LineageAgent()
        manifest = agent.build(self.root)
        baseline = Path(self.tmp.name) / "lineage.json"
        write_manifest(manifest, baseline.parent)
        changed = Path(self.tmp.name) / "changed"
        shutil.copytree(self.root, changed)
        capsule_path = changed / "run" / "run" / "run-capsule.json"
        capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
        capsule["dataset_sha256"] = "e" * 64
        _write(capsule_path, capsule)
        impact = agent.impact(baseline, changed)
        self.assertEqual(impact["status"], "stale")
        self.assertIn("claim:CLM-1", impact["stale_claims"])
        self.assertIn("slot:result.primary", impact["stale_slots"])
        self.assertIn("figure:FIG-1", impact["stale_figures"])
        self.assertTrue(impact["requires_reclosure"])
        self.assertTrue(impact["requires_resign"])
        self.assertFalse(impact["export_allowed"])
        self.assertGreaterEqual(impact["action_counts"].get("rerun", 0), 1)
        self.assertGreaterEqual(impact["action_counts"].get("rewrite", 0), 1)
        self.assertGreaterEqual(impact["action_counts"].get("recheck", 0), 1)
        self.assertTrue(any("rerun S5" in step for step in impact["next_steps"]))
        self.assertTrue(any("fresh human signature" in step for step in impact["next_steps"]))
        self.assertTrue(any(item["node_id"] == "dataset:" + "e" * 12 for item in impact["changed"]))
        self.assertTrue(any(item["node_id"] == "run:RUN-1" for item in impact["stale"]))

    def test_verify_detects_tampered_claim_and_clean_snapshot(self):
        agent = LineageAgent()
        manifest = agent.build(self.root)
        baseline = Path(self.tmp.name) / "lineage.json"
        write_manifest(manifest, baseline.parent)
        clean = agent.verify(baseline, self.root)
        self.assertEqual(clean["status"], "clean")
        self.assertEqual(clean["dispositions"], [])
        self.assertEqual(clean["action_counts"], {})
        self.assertEqual(clean["next_steps"], [])
        claim_path = self.root / "claim" / "claim.json"
        claim = json.loads(claim_path.read_text(encoding="utf-8"))
        claim["statement"] = "Tampered claim."
        _write(claim_path, claim)
        dirty = agent.verify(baseline, self.root)
        self.assertEqual(dirty["status"], "stale")
        self.assertIn("claim:CLM-1", dirty["stale_claims"])
        self.assertTrue(dirty["requires_resign"])

    def test_bundle_without_capsule_is_rejected(self):
        capsule_path = self.root / "run" / "run" / "run-capsule.json"
        capsule_path.unlink()
        with self.assertRaises(LineageError):
            LineageAgent().build(self.root)


if __name__ == "__main__":
    unittest.main()

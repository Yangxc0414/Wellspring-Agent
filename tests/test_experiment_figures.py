import hashlib
import tempfile
import unittest
from pathlib import Path

from research_agent.experiment_closure import check_experiment_closure
from research_agent.experiment_figures import (
    build_result_figure,
    result_figure_manifest_path,
    verify_result_figure,
)
from research_agent.writing_audit import audit_manuscript
from research_agent.writing_pack import build_writing_pack
from tests.test_experiment_closure import _prepare
from tests.writing_support import RUN_ID, write_draft


class ExperimentFigureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project, self.package = _prepare(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_figure_is_data_backed_and_bound_to_evidence(self):
        manifest = build_result_figure(self.project, "EXP-CLOSURE")
        self.assertFalse(manifest["schematic"])
        self.assertEqual(manifest["kind"], "data_result_plot")
        self.assertEqual(manifest["renderer"], "matplotlib")
        self.assertFalse(manifest["astradraw"])
        self.assertEqual(len(manifest["rows"]), 6)
        self.assertTrue(Path(manifest["png"]).is_file())
        self.assertTrue(Path(manifest["svg"]).is_file())
        evidence = self.package / "experiment-evidence.json"
        self.assertEqual(
            manifest["evidence_sha256"],
            hashlib.sha256(evidence.read_bytes()).hexdigest(),
        )
        verify = verify_result_figure(Path(manifest["manifest"]), project=self.project)
        self.assertEqual(verify["status"], "clean", verify)

        Path(manifest["png"]).write_bytes(b"tampered\n")
        stale = verify_result_figure(Path(manifest["manifest"]), project=self.project)
        self.assertEqual(stale["status"], "stale")

    def test_pack_and_closure_bind_figure(self):
        build_result_figure(self.project, "EXP-CLOSURE")
        pack = build_writing_pack(self.project, RUN_ID, experiment_id="EXP-CLOSURE")
        figure = pack["experiment_package"]["figure"]
        self.assertIsNotNone(figure)
        self.assertFalse(figure["schematic"])
        self.assertIn("图 1", figure["caption"])
        self.assertTrue(figure["manifest"].endswith("figure-manifest.json"))

        report = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(report["status"], "ready_for_human_signature", report["blockers"])
        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual(checks["figure.binding"]["status"], "pass")
        self.assertEqual(checks["figure.not_schematic"]["status"], "pass")
        self.assertEqual(checks["figure.data_result_plot"]["status"], "pass")
        self.assertEqual(report["figure"]["status"], "clean")
        self.assertTrue(
            any("figure-manifest.json" in item for item in report["artifact_refs"])
        )

    def test_manuscript_must_reference_the_verified_figure(self):
        build_result_figure(self.project, "EXP-CLOSURE")
        pack = build_writing_pack(self.project, RUN_ID, experiment_id="EXP-CLOSURE")
        draft = write_draft(
            self.root / "figure.md",
            result_text="图 1 展示了不同方法的均值与标准差。",
        )
        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "ready_for_human_review", audit["blockers"])

        missing = write_draft(
            self.root / "missing-figure.md",
            result_text="结果表明所提框架在多数设置下优于基线。",
        )
        audit = audit_manuscript(missing, pack=pack)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(any("figure.referenced" in item for item in audit["blockers"]))


if __name__ == "__main__":
    unittest.main()

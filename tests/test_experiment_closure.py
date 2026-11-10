import json
import tempfile
import unittest
from pathlib import Path

from research_agent.experiment_closure import (
    ExperimentClosureError,
    build_experiment_lineage,
    check_experiment_closure,
    sign_experiment_closure,
    verify_experiment_lineage,
)
from research_agent.experiment_codegen import generate_experiment_code
from research_agent.experiment_runner import (
    approve_experiment,
    execute_experiment,
    ingest_experiment,
    sign_experiment_claim,
)
from research_agent.signers import SignerStore
from tests.writing_support import RUN_ID, make_writing_project


def _prepare(root: Path):
    project = make_writing_project(root)
    data = project / "data.csv"
    rows = ["x1,x2,y"]
    for index in range(40):
        rows.append("%d,%d,%d" % (index, index % 5, index * 2 + (index % 4)))
    data.write_text("\n".join(rows) + "\n", encoding="utf-8")
    generated = generate_experiment_code(
        project,
        RUN_ID,
        data_path="data.csv",
        target="y",
        features=["x1", "x2"],
        task="regression",
        methods=["dummy", "ridge"],
        seeds=3,
        experiment_id="EXP-CLOSURE",
    )
    package = Path(generated["output_dir"])
    approve_experiment(project, "EXP-CLOSURE", "closure test")
    execution = execute_experiment(project, "EXP-CLOSURE", allow_execute=True)
    if execution["status"] != "completed":
        raise AssertionError(execution)
    ingest_experiment(project, "EXP-CLOSURE")
    sign_experiment_claim(
        project,
        "EXP-CLOSURE",
        "Ridge improves R2 over the dummy baseline in this local test protocol.",
        "checked synthetic protocol",
        ["metric=r2,value=0.0,comparator=>=,tolerance=0.01"],
    )
    return project, package


class ExperimentClosureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project, self.package = _prepare(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_closure_ready_and_signature_ready(self):
        report = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(report["status"], "ready_for_human_signature", report["blockers"])
        self.assertEqual(report["closure_profile"], "local_experiment")
        self.assertTrue((self.package / "experiment-closure" / "closure-report.json").is_file())
        signers = SignerStore(self.root / "signers.json")
        signer = signers.create("closure-test")
        signed = sign_experiment_closure(
            self.project,
            "EXP-CLOSURE",
            self.package / "experiment-closure" / "closure-report.json",
            "checked experiment evidence",
            signer_store=signers,
            signer_id=signer["signer_id"],
        )
        self.assertFalse(signed["signature"]["submission"])
        self.assertTrue(Path(signed["signature_path"]).is_file())
        self.assertTrue(Path(signed["manifest"]).is_file())

    def test_missing_claim_blocks_closure(self):
        claim = self.package / "claim.json"
        claim.rename(self.package / "claim.hold.json")
        report = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("claim.supported" in item for item in report["blockers"]))

    def test_tampered_metrics_blocks_closure(self):
        metrics = self.package / "outputs" / "metrics.json"
        metrics.write_text(json.dumps({"tampered": True}), encoding="utf-8")
        report = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any("output.metrics.json" in item for item in report["blockers"]))

    def test_sign_requires_ready_report_and_reason(self):
        with self.assertRaises(ExperimentClosureError):
            sign_experiment_closure(
                self.project,
                "EXP-CLOSURE",
                self.package / "experiment-closure" / "closure-report.json",
                "",
            )
        report = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(report["status"], "ready_for_human_signature")
        with self.assertRaises(ExperimentClosureError):
            sign_experiment_closure(
                self.project,
                "EXP-CLOSURE",
                self.package / "experiment-closure" / "closure-report.json",
                "",
            )

    def test_tampered_results_table_blocks_closure(self):
        report = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(report["status"], "ready_for_human_signature", report["blockers"])
        table = self.package / "outputs" / "results-table.md"
        table.write_text("tampered table\n", encoding="utf-8")
        stale = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(stale["status"], "blocked")
        checks = {item["id"]: item for item in stale["checks"]}
        self.assertEqual(checks["results_table.hash"]["status"], "fail")

    def test_support_panel_gates_closure_and_enters_lineage(self):
        panel_path = self.project / "runs" / RUN_ID / "support-panel.json"
        panel_path.write_text(
            json.dumps({"status": "needs_human", "pending_human": ["SUP-01"]}),
            encoding="utf-8",
        )
        blocked = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(blocked["status"], "blocked")
        self.assertTrue(any(item.startswith("support_panel.ready") for item in blocked["blockers"]))

        panel_path.write_text(
            json.dumps(
                {
                    "status": "ready",
                    "pending_human": [],
                    "draft_sha256": "a" * 64,
                    "panel_fingerprint": "f" * 64,
                }
            ),
            encoding="utf-8",
        )
        clean = check_experiment_closure(self.project, "EXP-CLOSURE")
        self.assertEqual(clean["status"], "ready_for_human_signature", clean["blockers"])
        self.assertEqual(clean["support_panel"]["status"], "ready")
        self.assertIn(str(panel_path), clean["artifact_refs"])

        lineage = build_experiment_lineage(self.project, "EXP-CLOSURE")
        self.assertIn("support_panel", {node["node_id"] for node in lineage["nodes"]})
        self.assertEqual(verify_experiment_lineage(self.project, "EXP-CLOSURE")["status"], "fresh")

        manuscript = self.root / "draft.md"
        manuscript.write_text("# 结果\n\n本文报告本地实验结果。", encoding="utf-8")
        stale = check_experiment_closure(
            self.project, "EXP-CLOSURE", manuscript=manuscript
        )
        self.assertTrue(
            any(item.startswith("support_panel.manuscript") for item in stale["blockers"])
        )

    def test_lineage_build_and_stale_detection(self):
        check_experiment_closure(self.project, "EXP-CLOSURE")
        lineage = build_experiment_lineage(self.project, "EXP-CLOSURE")
        self.assertGreaterEqual(len(lineage["nodes"]), 7)
        fresh = verify_experiment_lineage(self.project, "EXP-CLOSURE")
        self.assertEqual(fresh["status"], "fresh")
        with open(str(self.package / "claim.json"), "a", encoding="utf-8") as handle:
            handle.write("\n")
        stale = verify_experiment_lineage(self.project, "EXP-CLOSURE")
        self.assertEqual(stale["status"], "stale")
        self.assertIn("claim", stale["stale"])


if __name__ == "__main__":
    unittest.main()

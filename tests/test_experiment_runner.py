import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.experiment_codegen import generate_experiment_code
from research_agent.experiment_runner import (
    ExperimentExecutionError,
    approve_experiment,
    execute_experiment,
    preflight_experiment,
    experiment_status,
    ingest_experiment,
    sign_experiment_claim,
)
from research_agent.storage import write_json_atomic
from research_agent.writing_audit import audit_manuscript
from research_agent.writing_pack import build_writing_pack
from tests.writing_support import RUN_ID, make_writing_project, write_draft


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExperimentRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_writing_project(self.root)
        self.data = self.project / "data.csv"
        rows = ["x1,x2,y"]
        for index in range(30):
            rows.append("%d,%d,%d" % (index, index % 5, index * 2 + (index % 3)))
        self.data.write_text("\n".join(rows) + "\n", encoding="utf-8")
        self.generated = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="data.csv",
            target="y",
            features=["x1", "x2"],
            task="regression",
            methods=["dummy", "ridge"],
            seeds=3,
            experiment_id="EXP-RUNNER",
        )
        self.package = Path(self.generated["output_dir"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_execution_requires_explicit_approval_and_flag(self):
        with self.assertRaises(ExperimentExecutionError):
            execute_experiment(self.project, "EXP-RUNNER", allow_execute=False)
        with self.assertRaises(ExperimentExecutionError):
            execute_experiment(self.project, "EXP-RUNNER", allow_execute=True)
        with self.assertRaises(ExperimentExecutionError):
            approve_experiment(self.project, "EXP-RUNNER", "")

    def test_preflight_dry_run_does_not_create_execution_or_evidence(self):
        result = preflight_experiment(self.project, "EXP-RUNNER")
        self.assertEqual(result["status"], "passed", result)
        self.assertTrue((self.package / "preflight.json").is_file())
        self.assertFalse((self.package / "execution.json").exists())
        self.assertFalse((self.package / "experiment-evidence.json").exists())
        self.assertFalse((self.package / "claim.json").exists())
        status = experiment_status(self.project, "EXP-RUNNER")
        self.assertEqual(status["stages"]["preflight"], "passed")

    def test_preflight_rejects_changed_data(self):
        with open(str(self.data), "a", encoding="utf-8") as handle:
            handle.write("99,99,99\n")
        with self.assertRaises(ExperimentExecutionError):
            preflight_experiment(self.project, "EXP-RUNNER")

    def test_approval_then_dry_run_execution_is_not_evidence(self):
        approve_experiment(self.project, "EXP-RUNNER", "schema check only")
        execution = execute_experiment(
            self.project, "EXP-RUNNER", allow_execute=True, dry_run=True
        )
        self.assertEqual(execution["status"], "completed")
        self.assertTrue(execution["dry_run"])
        self.assertTrue((self.package / "execution.json").is_file())
        evidence = ingest_experiment(self.project, "EXP-RUNNER")
        self.assertEqual(evidence["status"], "blocked")
        self.assertTrue(any("dry_run" in item for item in evidence["blockers"]))

    def test_execute_generated_runner_on_synthetic_data_writes_receipt(self):
        approve_experiment(self.project, "EXP-RUNNER", "synthetic code test")
        execution = execute_experiment(self.project, "EXP-RUNNER", allow_execute=True)
        self.assertEqual(execution["status"], "completed", execution)
        self.assertIn("run-receipt.json", execution["artifacts"])
        evidence = ingest_experiment(self.project, "EXP-RUNNER")
        self.assertEqual(evidence["status"], "verified", evidence["blockers"])
        self.assertEqual(evidence["primary_method"], "ridge")
        self.assertIn("ridge_vs_dummy", evidence["comparison"])
        self.assertIn("sign_test_p", evidence["comparison"]["ridge_vs_dummy"])
        self.assertTrue((self.package / "outputs" / "metrics.json").is_file())
        self.assertTrue(evidence["results_table"].endswith("results-table.md"))
        self.assertEqual(len(evidence["results_table_sha256"]), 64)

    def test_confirmatory_run_binds_approved_ridge_alpha(self):
        approval = approve_experiment(
            self.project, "EXP-RUNNER", "confirm selected sweep alpha", ridge_alpha=10.0
        )
        self.assertEqual(approval["ridge_alpha"], 10.0)
        with self.assertRaises(ExperimentExecutionError):
            execute_experiment(
                self.project,
                "EXP-RUNNER",
                allow_execute=True,
                dry_run=True,
                ridge_alpha=1.0,
            )
        execution = execute_experiment(
            self.project, "EXP-RUNNER", allow_execute=True, ridge_alpha=10.0
        )
        self.assertEqual(execution["status"], "completed", execution)
        self.assertEqual(execution["ridge_alpha"], 10.0)
        evidence = ingest_experiment(self.project, "EXP-RUNNER")
        self.assertEqual(evidence["status"], "verified", evidence["blockers"])
        self.assertEqual(evidence["ridge_alpha"], 10.0)
        self.assertEqual(evidence["receipt"]["ridge_alpha"], 10.0)
        claim = sign_experiment_claim(
            self.project,
            "EXP-RUNNER",
            "The approved ridge alpha reproduces the selected sweep configuration.",
            "checked alpha/data/metrics",
            ["metric=r2,value=-1.0,comparator=>=,tolerance=0.01"],
        )
        self.assertEqual(claim["status"], "supported")
        self.assertEqual(claim["ridge_alpha"], 10.0)
        self.assertEqual(claim["cv_folds"], 0)
        self.assertEqual(claim["results_table_sha256"], evidence["results_table_sha256"])

    def test_changed_data_after_approval_is_rejected(self):
        approve_experiment(self.project, "EXP-RUNNER", "approved")
        with open(str(self.data), "a", encoding="utf-8") as handle:
            handle.write("99,99,99\n")
        with self.assertRaises(ExperimentExecutionError):
            execute_experiment(self.project, "EXP-RUNNER", allow_execute=True, dry_run=True)

    def _write_synthetic_outputs(self):
        spec = json.loads((self.package / "experiment-spec.json").read_text(encoding="utf-8"))
        spec_sha = _sha(self.package / "experiment-spec.json")
        code_sha = _sha(self.package / "run_experiment.py")
        data_sha = _sha(self.data)
        metrics = {
            "by_seed": [
                {"seed": 0, "method": "ridge", "metrics": {"r2": 0.94}},
                {"seed": 1, "method": "ridge", "metrics": {"r2": 0.95}},
                {"seed": 2, "method": "ridge", "metrics": {"r2": 0.96}},
            ],
            "aggregate": {
                "ridge": {"r2": {"mean": 0.95, "std": 0.01, "by_seed": [0.94, 0.95, 0.96]}}
            },
        }
        outputs = self.package / "outputs"
        outputs.mkdir(exist_ok=True)
        write_json_atomic(outputs / "metrics.json", metrics)
        (outputs / "predictions.csv").write_text("row_index,seed,method,prediction\n0,0,ridge,1\n", encoding="utf-8")
        receipt = {
            "schema_version": "local-experiment-receipt-0.1",
            "experiment_id": "EXP-RUNNER",
            "status": "completed_local",
            "seeds": [0, 1, 2],
            "spec_sha256": spec_sha,
            "code_sha256": code_sha,
            "data_sha256": data_sha,
            "metrics": metrics["aggregate"],
        }
        write_json_atomic(outputs / "run-receipt.json", receipt)
        artifacts = []
        for name in ("metrics.json", "predictions.csv", "run-receipt.json"):
            path = outputs / name
            artifacts.append({"name": name, "sha256": _sha(path), "bytes": path.stat().st_size})
        write_json_atomic(outputs / "artifact-manifest.json", {"artifacts": artifacts})
        execution = {
            "schema_version": "experiment-execution-0.1",
            "experiment_id": "EXP-RUNNER",
            "status": "completed",
            "dry_run": False,
            "data_sha256": data_sha,
            "spec_sha256": spec_sha,
            "code_sha256": code_sha,
        }
        write_json_atomic(self.package / "execution.json", execution)
        return spec

    def test_ingest_and_signed_claim(self):
        self._write_synthetic_outputs()
        evidence = ingest_experiment(self.project, "EXP-RUNNER")
        self.assertEqual(evidence["status"], "verified")
        self.assertEqual(evidence["primary_method"], "ridge")
        self.assertEqual(evidence["primary_metric"], "r2")
        self.assertAlmostEqual(evidence["mean"], 0.95)
        claim = sign_experiment_claim(
            self.project,
            "EXP-RUNNER",
            "Ridge improves R2 over the dummy baseline in this local protocol.",
            "checked metrics and seeds",
            ["metric=r2,value=0.9,comparator=>=,tolerance=0.01"],
        )
        self.assertEqual(claim["status"], "supported")
        self.assertEqual(claim["assertions"][0]["status"], "pass")
        self.assertTrue((self.package / "claim.json").is_file())
        with self.assertRaises(ExperimentExecutionError):
            sign_experiment_claim(
                self.project, "EXP-RUNNER", "bad", "checked",
                ["metric=r2,value=0.99,comparator=>=,tolerance=0.001"],
            )

    def test_verified_experiment_claim_flows_into_writing_pack(self):
        self._write_synthetic_outputs()
        ingest_experiment(self.project, "EXP-RUNNER")
        pack = build_writing_pack(self.project, RUN_ID, experiment_id="EXP-RUNNER")
        self.assertEqual(pack["claim"]["status"], "draft_needs_human")
        self.assertEqual(pack["writing_contract"]["article_type"], "reproduction")
        self.assertEqual(pack["writing_contract"]["allowed_result_numbers"], [])
        draft = write_draft(self.root / "draft.md", result_text="R² 均值为 0.95。")
        blocked = audit_manuscript(draft, pack=pack)
        self.assertEqual(blocked["status"], "blocked")

        sign_experiment_claim(
            self.project,
            "EXP-RUNNER",
            "Ridge improves R2 over the dummy baseline in this local protocol.",
            "checked metrics and seeds",
            ["metric=r2,value=0.9,comparator=>=,tolerance=0.01"],
        )
        signed_pack = build_writing_pack(self.project, RUN_ID, experiment_id="EXP-RUNNER")
        self.assertEqual(signed_pack["claim"]["status"], "signed")
        self.assertIn("0.95", signed_pack["writing_contract"]["allowed_result_numbers"])
        ready = audit_manuscript(draft, pack=signed_pack)
        self.assertEqual(ready["status"], "ready_for_human_review", ready["blockers"])

    def test_status_reports_next_human_or_cli_action(self):
        status = experiment_status(self.project, "EXP-RUNNER")
        self.assertEqual(status["stages"]["approval"], "missing")
        self.assertEqual(status["next_action"], "experiment approve")
        approve_experiment(self.project, "EXP-RUNNER", "status test")
        self._write_synthetic_outputs()
        ingest_experiment(self.project, "EXP-RUNNER")
        status = experiment_status(self.project, "EXP-RUNNER")
        self.assertEqual(status["stages"]["evidence"], "verified")
        self.assertEqual(status["evidence_summary"]["status"], "verified")
        self.assertEqual(status["evidence_summary"]["mean"], 0.95)
        self.assertIn("data_audit_status", status["evidence_summary"])
        self.assertEqual(status["next_action"], "experiment claim (human only)")
        sign_experiment_claim(
            self.project, "EXP-RUNNER", "statement", "checked",
            ["metric=r2,value=0.9,comparator=>=,tolerance=0.01"],
        )
        status = experiment_status(self.project, "EXP-RUNNER")
        self.assertEqual(status["stages"]["claim"], "signed")
        self.assertEqual(status["next_action"], "experiment closure")

        panel_path = self.project / "runs" / RUN_ID / "support-panel.json"
        panel_path.write_text(
            json.dumps({"status": "needs_human", "pending_human": ["SUP-01"]}),
            encoding="utf-8",
        )
        status = experiment_status(self.project, "EXP-RUNNER")
        self.assertEqual(status["stages"]["support_panel"], "needs_human")
        self.assertEqual(status["support_panel"]["pending_human"], 1)
        self.assertEqual(status["next_action"], "support adjudication (human only)")
        panel_path.write_text(
            json.dumps({"status": "ready", "pending_human": []}), encoding="utf-8"
        )
        status = experiment_status(self.project, "EXP-RUNNER")
        self.assertEqual(status["stages"]["support_panel"], "ready")
        self.assertEqual(status["next_action"], "experiment closure")

    def test_claim_requires_verified_evidence(self):
        with self.assertRaises(ExperimentExecutionError):
            sign_experiment_claim(
                self.project, "EXP-RUNNER", "statement", "reason", []
            )

    def test_tampered_metrics_are_blocked(self):
        self._write_synthetic_outputs()
        metrics_path = self.package / "outputs" / "metrics.json"
        write_json_atomic(metrics_path, {"by_seed": [], "aggregate": {}})
        evidence = ingest_experiment(self.project, "EXP-RUNNER")
        self.assertEqual(evidence["status"], "blocked")
        self.assertTrue(any("artifact.metrics.json" in item for item in evidence["blockers"]))


if __name__ == "__main__":
    unittest.main()

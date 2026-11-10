import json
import tempfile
import unittest
from pathlib import Path

from research_agent.experiment_codegen import generate_experiment_code
from research_agent.experiment_runner import (
    ExperimentExecutionError,
    approve_sweep,
    execute_sweep,
    experiment_status,
    ingest_sweep,
    sweep_status,
)
from tests.writing_support import RUN_ID, make_writing_project


class ExperimentSweepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_writing_project(self.root)
        data = self.project / "data.csv"
        rows = ["x1,x2,y"]
        for index in range(30):
            rows.append(
                "%d,%d,%d" % (index, index % 5, index * 2 + (index % 4))
            )
        data.write_text("\n".join(rows) + "\n", encoding="utf-8")
        generated = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="data.csv",
            target="y",
            features=["x1", "x2"],
            task="regression",
            methods=["dummy", "ridge"],
            seeds=2,
            cv_folds=3,
            experiment_id="EXP-SWEEP-RUN",
            alpha_grid=[0.1, 1, 10],
        )
        self.package = Path(generated["output_dir"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_sweep_approve_run_ingest_is_exploratory_only(self):
        approval = approve_sweep(self.project, "EXP-SWEEP-RUN", "checked sweep plan")
        self.assertEqual(
            approval["schema_version"], "experiment-sweep-approval-0.1"
        )
        execution = execute_sweep(self.project, "EXP-SWEEP-RUN", allow_execute=True)
        self.assertEqual(execution["status"], "completed", execution)
        self.assertTrue((self.package / "sweep-execution.json").is_file())
        self.assertTrue((self.package / "outputs" / "sweep-results.json").is_file())

        results = json.loads(
            (self.package / "outputs" / "sweep-results.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(results["rows"]), 2 * 3 * 3)
        self.assertEqual(results["cv_folds"], 3)
        evidence = ingest_sweep(self.project, "EXP-SWEEP-RUN")
        self.assertEqual(evidence["status"], "verified_exploratory", evidence)
        self.assertIn(str(evidence["best_alpha"]), [str(value) for value in evidence["values"]])
        self.assertEqual(evidence["cv_folds"], 3)
        self.assertFalse((self.package / "claim.json").exists())
        self.assertFalse((self.package / "experiment-evidence.json").exists())

        status = sweep_status(self.project, "EXP-SWEEP-RUN")
        self.assertEqual(status["stages"]["sweep_evidence"], "verified_exploratory")
        self.assertEqual(status["best_alpha"], evidence["best_alpha"])
        full = experiment_status(self.project, "EXP-SWEEP-RUN")
        self.assertEqual(full["sweep"]["stages"]["sweep_evidence"], "verified_exploratory")

    def test_sweep_requires_approval_and_allows_dry_run_only(self):
        with self.assertRaises(ExperimentExecutionError):
            execute_sweep(self.project, "EXP-SWEEP-RUN", allow_execute=False)
        approve_sweep(self.project, "EXP-SWEEP-RUN", "checked dry run")
        dry = execute_sweep(self.project, "EXP-SWEEP-RUN", allow_execute=True, dry_run=True)
        self.assertEqual(dry["status"], "completed")
        evidence = ingest_sweep(self.project, "EXP-SWEEP-RUN")
        self.assertEqual(evidence["status"], "blocked")
        self.assertIn("execution.not_dry_run", " ".join(evidence["blockers"]))

    def test_sweep_detects_tampered_results(self):
        approve_sweep(self.project, "EXP-SWEEP-RUN", "checked hash test")
        execute_sweep(self.project, "EXP-SWEEP-RUN", allow_execute=True)
        results = self.package / "outputs" / "sweep-results.json"
        payload = json.loads(results.read_text(encoding="utf-8"))
        payload["selection"]["best_alpha"] = 999
        results.write_text(json.dumps(payload), encoding="utf-8")
        evidence = ingest_sweep(self.project, "EXP-SWEEP-RUN")
        self.assertEqual(evidence["status"], "blocked")
        self.assertTrue(
            any("artifact.sweep-results.json" in item for item in evidence["blockers"])
        )


if __name__ == "__main__":
    unittest.main()

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_agent.experiment_codegen import (
    ExperimentCodegenError,
    generate_experiment_code,
)
from tests.writing_support import RUN_ID, make_writing_project


class ExperimentCodegenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = make_writing_project(self.root)
        self.data = self.project / "data.csv"
        rows = ["x1,x2,y"]
        for index in range(30):
            rows.append("%d,%d,%d" % (index, index % 7, index * 2 + (index % 3)))
        self.data.write_text("\n".join(rows) + "\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_generates_spec_runner_and_manifest_without_execution(self):
        result = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="data.csv",
            target="y",
            features=["x1", "x2"],
            task="regression",
            methods=["dummy", "ridge"],
            seeds=3,
            experiment_id="EXP-TEST",
        )
        self.assertEqual(result["status"], "generated")
        self.assertEqual(result["execution"], "not_run")
        output = Path(result["output_dir"])
        for name in (
            "experiment-spec.json",
            "run_experiment.py",
            "requirements.txt",
            "README.md",
            "code-manifest.json",
        ):
            self.assertTrue((output / name).is_file(), name)
        spec = json.loads((output / "experiment-spec.json").read_text(encoding="utf-8"))
        self.assertEqual(spec["experiment_id"], "EXP-TEST")
        self.assertEqual(spec["data"]["target"], "y")
        self.assertEqual(spec["data"]["features"], ["x1", "x2"])
        self.assertEqual(spec["design"]["seeds"], [0, 1, 2])
        self.assertEqual(spec["design"]["status"], "draft_needs_g2")
        self.assertIn("not a RunCapsule", spec["boundary"])
        manifest = json.loads((output / "code-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["execution"], "not_run")
        self.assertEqual(len(manifest["files"]), 4)
        self.assertFalse((output / "outputs" / "run-receipt.json").exists())

        compiled = subprocess.run(
            [sys.executable, "-m", "py_compile", str(output / "run_experiment.py")],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(compiled.returncode, 0, compiled.stderr)

    def test_alpha_grid_adds_sweep_plan_and_script(self):
        result = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="data.csv",
            target="y",
            features=["x1", "x2"],
            task="regression",
            methods=["dummy", "ridge"],
            seeds=3,
            experiment_id="EXP-SWEEP",
            alpha_grid=[1, 0.1, 10, 1],
        )
        spec = result["spec"]
        self.assertEqual(spec["sweep"]["values"], [0.1, 1.0, 10.0])
        self.assertEqual(spec["sweep"]["status"], "planned_local_only")
        self.assertIn("not wired", spec["sweep"]["note"])
        output = Path(result["output_dir"])
        self.assertTrue((output / "run_sweep.py").is_file())
        compiled = compile(
            (output / "run_sweep.py").read_text(encoding="utf-8"),
            str(output / "run_sweep.py"),
            "exec",
        )
        self.assertIsNotNone(compiled)
        manifest = json.loads((output / "code-manifest.json").read_text(encoding="utf-8"))
        names = {item["name"] for item in manifest["files"]}
        self.assertIn("run_sweep.py", names)
        self.assertIn("Parameter sweep", (output / "README.md").read_text(encoding="utf-8"))
        self.assertIn("run_sweep.py", result["next_action"])

    def test_alpha_grid_rejects_invalid_plans(self):
        with self.assertRaises(ExperimentCodegenError):
            generate_experiment_code(
                self.project,
                RUN_ID,
                data_path="data.csv",
                target="y",
                features=["x1", "x2"],
                task="classification",
                methods=["dummy", "logistic"],
                seeds=3,
                experiment_id="EXP-SWEEP-BAD",
                alpha_grid=[0.1, 1],
            )
        with self.assertRaises(ExperimentCodegenError):
            generate_experiment_code(
                self.project,
                RUN_ID,
                data_path="data.csv",
                target="y",
                features=["x1", "x2"],
                task="regression",
                methods=["dummy", "ridge"],
                seeds=3,
                experiment_id="EXP-SWEEP-ONE",
                alpha_grid=[1],
            )
        with self.assertRaises(ExperimentCodegenError):
            generate_experiment_code(
                self.project,
                RUN_ID,
                data_path="data.csv",
                target="y",
                features=["x1", "x2"],
                task="regression",
                methods=["dummy", "ridge"],
                seeds=3,
                experiment_id="EXP-SWEEP-NEG",
                alpha_grid=[-1, 1],
            )

    def test_tree_baselines_generate_and_execute(self):
        result = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="data.csv",
            target="y",
            features=["x1", "x2"],
            task="regression",
            methods=["dummy", "random_forest", "gradient_boosting"],
            seeds=2,
            experiment_id="EXP-TREES",
        )
        output = Path(result["output_dir"])
        run = subprocess.run(
            [sys.executable, "run_experiment.py"],
            cwd=str(output),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        metrics = json.loads((output / "outputs" / "metrics.json").read_text(encoding="utf-8"))
        self.assertIn("random_forest", metrics["aggregate"])
        self.assertIn("gradient_boosting", metrics["aggregate"])
        self.assertGreaterEqual(metrics["aggregate"]["random_forest"]["r2"]["mean"], -1.0)
        self.assertIn("gradient_boosting_vs_dummy", metrics["comparison"])
        comparison = metrics["comparison"]["gradient_boosting_vs_dummy"]
        self.assertIn("ci95_low", comparison)
        self.assertIn("bootstrap_ci95_low", comparison)
        self.assertIn("sign_test_p", comparison)
        self.assertTrue((output / "outputs" / "results-table.md").is_file())
        self.assertIn("gradient_boosting", (output / "outputs" / "results-table.md").read_text(encoding="utf-8"))

        classification = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="data.csv",
            target="y",
            features=["x1", "x2"],
            task="classification",
            methods=["dummy", "gradient_boosting"],
            seeds=2,
            experiment_id="EXP-TREES-CLS",
        )
        spec = classification["spec"]
        self.assertIn("gradient_boosting", spec["design"]["methods"])

    def test_kfold_cv_produces_fold_level_metrics(self):
        result = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="data.csv",
            target="y",
            features=["x1", "x2"],
            task="regression",
            methods=["dummy", "ridge"],
            seeds=2,
            cv_folds=5,
            experiment_id="EXP-CV",
        )
        output = Path(result["output_dir"])
        run = subprocess.run(
            [sys.executable, "run_experiment.py"],
            cwd=str(output),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        metrics = json.loads((output / "outputs" / "metrics.json").read_text(encoding="utf-8"))
        self.assertEqual(len(metrics["by_seed"]), 20)
        self.assertEqual(metrics["comparison"]["ridge_vs_dummy"]["n"], 10)
        receipt = json.loads((output / "outputs" / "run-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["cv_folds"], 5)

    def test_dry_run_validates_schema_without_training(self):
        result = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="data.csv",
            target="y",
            features=["x1", "x2"],
            seeds=3,
            experiment_id="EXP-DRY",
        )
        output = Path(result["output_dir"])
        dry = subprocess.run(
            [sys.executable, "run_experiment.py", "--dry-run"],
            cwd=str(output),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        payload = json.loads(dry.stdout)
        self.assertEqual(payload["status"], "dry_run_ok")
        self.assertEqual(payload["rows"], 30)
        self.assertEqual(payload["target"], "y")

    def test_data_audit_flags_constant_id_and_target_leakage(self):
        audit_data = self.project / "audit.csv"
        lines = ["sample_id,x_const,y,y_copy"]
        for index in range(30):
            lines.append("S%03d,1,%d,%d" % (index, index, index))
        audit_data.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="audit.csv",
            target="y",
            features=["sample_id", "x_const", "y_copy"],
            task="regression",
            methods=["dummy", "ridge"],
            seeds=2,
            experiment_id="EXP-AUDIT",
        )
        audit = result["data_audit"]
        self.assertEqual(audit["status"], "warn")
        self.assertTrue(any("features.id_like" in item for item in audit["warnings"]))
        self.assertTrue(any("features.constant" in item for item in audit["warnings"]))
        self.assertTrue(
            any("features.target_correlation" in item for item in audit["warnings"])
        )
        readme = (Path(result["output_dir"]) / "README.md").read_text(encoding="utf-8")
        self.assertIn("Data audit", readme)
        self.assertIn("features.id_like", readme)

    def test_data_audit_flags_target_copy_for_classification(self):
        copy_data = self.project / "target_copy.csv"
        lines = ["x1,y,y_copy"]
        for index in range(30):
            value = index % 2
            lines.append("%d,%d,%d" % (index, value, value))
        copy_data.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="target_copy.csv",
            target="y",
            features=["x1", "y_copy"],
            task="classification",
            methods=["dummy", "logistic"],
            seeds=2,
            experiment_id="EXP-AUDIT-CLASS",
        )
        self.assertTrue(
            any("target.copy" in item for item in result["data_audit"]["warnings"])
        )

    def test_data_audit_flags_duplicate_rows(self):
        duplicate_data = self.project / "duplicate.csv"
        lines = ["x1,y"]
        for index in range(30):
            lines.append("%d,%d" % (index % 3, index))
        lines.append("0,0")
        lines.append("1,1")
        duplicate_data.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = generate_experiment_code(
            self.project,
            RUN_ID,
            data_path="duplicate.csv",
            target="y",
            features=["x1"],
            task="regression",
            methods=["dummy", "ridge"],
            seeds=2,
            experiment_id="EXP-AUDIT-DUP",
        )
        self.assertTrue(
            any("duplicates.rows" in item for item in result["data_audit"]["warnings"])
        )

    def test_target_in_features_is_rejected(self):
        with self.assertRaises(ExperimentCodegenError):
            generate_experiment_code(
                self.project,
                RUN_ID,
                data_path="data.csv",
                target="y",
                features=["x1", "y"],
            )

    def test_missing_column_is_rejected(self):
        with self.assertRaises(ExperimentCodegenError):
            generate_experiment_code(
                self.project,
                RUN_ID,
                data_path="data.csv",
                target="y",
                features=["x1", "missing"],
            )

    def test_data_outside_project_is_rejected(self):
        outside = Path(self.root) / "outside.csv"
        outside.write_text("x1,y\n1,2\n", encoding="utf-8")
        with self.assertRaises(ExperimentCodegenError):
            generate_experiment_code(
                self.project,
                RUN_ID,
                data_path=str(outside),
                target="y",
                features=["x1"],
            )

    def test_method_task_mismatch_is_rejected(self):
        with self.assertRaises(ExperimentCodegenError):
            generate_experiment_code(
                self.project,
                RUN_ID,
                data_path="data.csv",
                target="y",
                features=["x1"],
                task="classification",
                methods=["dummy", "ridge"],
            )


if __name__ == "__main__":
    unittest.main()

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_agent.experiment_codegen import generate_experiment_code
from tests.writing_support import RUN_ID, make_writing_project

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "breast_cancer_sample.csv"


class RealDataPathTest(unittest.TestCase):
    def test_multi_feature_classification_with_cv_and_tree_baselines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            target = project / "data.csv"
            target.write_bytes(FIXTURE.read_bytes())
            with open(str(target), "r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle))
            features = [name for name in header if name != "target"]
            generated = generate_experiment_code(
                project,
                RUN_ID,
                data_path="data.csv",
                target="target",
                features=features,
                task="classification",
                methods=["dummy", "logistic", "random_forest", "gradient_boosting"],
                metric="accuracy",
                seeds=2,
                cv_folds=5,
                experiment_id="EXP-REALDATA",
            )
            output = Path(generated["output_dir"])
            run = subprocess.run(
                [sys.executable, "run_experiment.py"],
                cwd=str(output),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=240,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            metrics = json.loads(
                (output / "outputs" / "metrics.json").read_text(encoding="utf-8")
            )
            for method in ("dummy", "logistic", "random_forest", "gradient_boosting"):
                self.assertIn(method, metrics["aggregate"])
            comparison = metrics["comparison"]["gradient_boosting_vs_dummy"]
            self.assertEqual(comparison["n"], 10)
            self.assertIn("bootstrap_ci95_low", comparison)
            self.assertIn("sign_test_p", comparison)
            self.assertTrue((output / "outputs" / "results-table.md").is_file())
            receipt = json.loads(
                (output / "outputs" / "run-receipt.json").read_text(encoding="utf-8")
            )
            self.assertEqual(receipt["cv_folds"], 5)
            spec = json.loads(
                (output / "experiment-spec.json").read_text(encoding="utf-8")
            )
            self.assertEqual(spec["data_audit"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from research_agent.cli import main
from research_agent.experiment_consistency import (
    ExperimentConsistencyError,
    build_consistency_registry,
)
from research_agent.external_consistency_gate import run_consistency_check

EXTERNAL_ROOT = Path("D:/Users/20691/Downloads/Research Skill调研/scientific-agent-skills-main")


def _fixture(root: Path, *, claim: bool = True, evidence_status: str = "verified"):
    project = root / "project"
    package = project / "experiments" / "EXP-CONS"
    package.mkdir(parents=True)
    (package / "experiment-spec.json").write_text(
        json.dumps(
            {
                "experiment_id": "EXP-CONS",
                "data": {"rows": 48},
                "design": {"task": "regression", "methods": ["dummy", "ridge"]},
            }
        ),
        encoding="utf-8",
    )
    (package / "experiment-evidence.json").write_text(
        json.dumps(
            {
                "status": evidence_status,
                "metrics": {
                    "aggregate": {
                        "dummy": {"r2": {"mean": 0.11, "std": 0.02}},
                        "ridge": {"r2": {"mean": 0.82, "std": 0.03}},
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    if claim:
        (package / "claim.json").write_text(
            json.dumps({"status": "supported"}), encoding="utf-8"
        )
    return project, package


class ExperimentConsistencyTest(unittest.TestCase):
    def test_registry_is_derived_from_verified_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, package = _fixture(Path(tmp))
            result = build_consistency_registry(project, "EXP-CONS")
            registry = result["registry"]
            self.assertEqual(result["schema_version"], "experiment-consistency-registry-0.1")
            self.assertEqual(result["claim_status"], "signed")
            self.assertEqual(result["analysis_intent"], "confirmatory")
            self.assertEqual(registry["schema_version"], "1.0")
            self.assertEqual(len(registry["numeric_facts"]), 4)
            self.assertEqual(len(registry["methods"]), 2)
            self.assertEqual(len(registry["results"]), 2)
            self.assertTrue(all(item["sample_size"] == 48 for item in registry["results"]))
            self.assertTrue(all(item["analysis_intent"] == "confirmatory" for item in registry["results"]))
            self.assertNotIn(str(project), json.dumps(registry))
            self.assertIn("dataset row count", result["boundary"].lower())
            self.assertEqual(result["source_hashes"]["claim_sha256"], result["source_hashes"]["claim_sha256"])
            self.assertTrue(result["source_hashes"]["evidence_sha256"])

    def test_unsigned_claim_is_exploratory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _ = _fixture(Path(tmp), claim=False)
            result = build_consistency_registry(project, "EXP-CONS")
        self.assertEqual(result["claim_status"], "unsigned")
        self.assertEqual(result["analysis_intent"], "exploratory")

    def test_unverified_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _ = _fixture(Path(tmp), evidence_status="candidate")
            with self.assertRaises(ExperimentConsistencyError):
                build_consistency_registry(project, "EXP-CONS")

    def test_invalid_experiment_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _ = _fixture(Path(tmp))
            with self.assertRaises(ExperimentConsistencyError):
                build_consistency_registry(project, "../runs")

    @unittest.skipUnless(EXTERNAL_ROOT.is_dir(), "external skill root not installed")
    def test_generated_registry_passes_external_consistency(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, package = _fixture(Path(tmp))
            result = build_consistency_registry(project, "EXP-CONS")
            registry_path = package / "consistency.json"
            registry_path.write_text(json.dumps(result["registry"]), encoding="utf-8")
            checked = run_consistency_check(registry_path, EXTERNAL_ROOT)
        self.assertEqual(checked["status"], "ready", checked)
        self.assertEqual(checked["summary"]["errors"], 0)

    def test_cli_writes_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, package = _fixture(Path(tmp))
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "experiment",
                        "consistency-registry",
                        "--project",
                        str(project),
                        "--experiment-id",
                        "EXP-CONS",
                        "--output",
                        "experiments/EXP-CONS/consistency.json",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue((package / "consistency.json").is_file())
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["registry"]["schema_version"], "1.0")
            self.assertEqual(payload["output"], str(package / "consistency.json"))


if __name__ == "__main__":
    unittest.main()

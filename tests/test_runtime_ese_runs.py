"""Runtime ESE runs view: scanner fields and read-only API/page."""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.runtime.app import create_app
from research_agent.runtime.ese_runs import scan_ese_runs, summary
from research_agent.runtime.jobs import default_settings


def _write_study(root, name="ese-ms-test"):
    directory = Path(root) / "runtime_data" / name
    (directory / "run").mkdir(parents=True)
    (directory / "result.json").write_text(json.dumps({
        "study_id": "ESE-MS-TEST-01",
        "pooled": {"commits": 100, "rate": 0.375, "ci": [0.31, 0.44], "difference": 0.046},
        "stratified": {"adjusted_difference": 0.068},
    }), encoding="utf-8")
    (directory / "run" / "run-capsule.json").write_text(json.dumps({
        "run_id": "ESE-MS-TEST-01", "status": "completed",
    }), encoding="utf-8")
    return directory


class EseRunsScannerTest(unittest.TestCase):
    def test_scan_reads_study_fields_and_capsule(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_study(tmp)
            runs = scan_ese_runs(Path(tmp) / "runtime_data")
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["study_id"], "ESE-MS-TEST-01")
        self.assertEqual(runs[0]["commits"], 100)
        self.assertEqual(runs[0]["status"], "completed")
        self.assertEqual(len(runs[0]["capsule_sha256"]), 64)

    def test_missing_directory_and_empty_runs_are_safe(self):
        self.assertEqual(scan_ese_runs("/does/not/exist"), [])
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(summary(tmp)["count"], 0)


class EseRunsEndpointTest(unittest.TestCase):
    def test_api_and_page_show_the_study(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_study(root)
            settings = default_settings()
            settings.repo_root = root
            settings.jobs_root = root / "jobs"
            settings.workspace_memory_path = root / "workspace_memory.json"
            settings.workspace_archive_root = root / "archive"
            settings.literature_memory_path = root / "literature_memory.json"
            settings.custom_agents_path = root / "custom_agents.json"
            settings.evolution_policy_path = root / "evolution_policy.json"
            settings.skill_registry_path = root / "skills.json"
            settings.model_store_path = root / "model_gateway.json"
            app = create_app(settings)
            with TestClient(app) as client:
                payload = client.get("/api/ese/runs").json()
                page = client.get("/")
        self.assertEqual(payload["schema"], "runtime-ese-runs-0.1")
        self.assertEqual(payload["count"], 1)
        self.assertIn("ESE-MS-TEST-01", page.text)
        self.assertIn("Read-only", page.text)


if __name__ == "__main__":
    unittest.main()

"""Workbench ESE snapshot: generated, schema-checked, no hand-written runs."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_web_ese_runs import build  # noqa: E402


class WebEseRunsTest(unittest.TestCase):
    def test_build_writes_schema_and_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan_root = Path(tmp) / "runtime_data"
            study = scan_root / "ese-ms-x"
            (study / "run").mkdir(parents=True)
            (study / "result.json").write_text(json.dumps({
                "study_id": "ESE-X",
                "pooled": {"commits": 10, "rate": 0.5, "ci": [0.2, 0.8]},
                "stratified": {"adjusted_difference": 0.1},
            }), encoding="utf-8")
            out = Path(tmp) / "ese-runs.json"
            payload = build(scan_root, out)
            written = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "runtime-ese-runs-0.1")
        self.assertEqual(written["count"], 1)
        self.assertEqual(written["runs"][0]["study_id"], "ESE-X")

    def test_shipped_snapshot_is_valid(self):
        path = ROOT / "apps" / "web" / "public" / "ese-runs.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "runtime-ese-runs-0.1")
        self.assertIsInstance(payload["runs"], list)
        self.assertIn("boundary", payload)


if __name__ == "__main__":
    unittest.main()

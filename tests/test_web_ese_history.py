import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_web_ese_history as history  # noqa: E402

HISTORY = ROOT / "apps" / "web" / "public" / "ese-history.json"


class EseHistoryTest(unittest.TestCase):
    def test_history_matches_runtime_data(self):
        ok, problems = history.validate(HISTORY, ROOT)
        self.assertTrue(ok, problems)

    def test_count_matches_entries(self):
        payload = json.loads(HISTORY.read_text(encoding="utf-8"))
        self.assertEqual(payload["count"], len(payload["entries"]))
        self.assertGreaterEqual(payload["count"], 3)

    def test_tampered_number_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = json.loads(HISTORY.read_text(encoding="utf-8"))
            payload["entries"][0]["verify"]["expect"]["commits"] = 1
            target = Path(tmp) / "ese-history.json"
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            ok, problems = history.validate(target, ROOT)
            self.assertFalse(ok)
            self.assertTrue(any("commits" in problem for problem in problems))

    def test_missing_artifact_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = json.loads(HISTORY.read_text(encoding="utf-8"))
            payload["entries"][0]["verify"]["path"] = "runtime_data/absent/result.json"
            target = Path(tmp) / "ese-history.json"
            target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            ok, problems = history.validate(target, ROOT)
            self.assertFalse(ok)
            self.assertTrue(any("不存在" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()

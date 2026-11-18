"""Design archive audit: duplicate numbers, index targets, count claims."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.docs_audit as docs_audit  # noqa: E402


def _write(root, relative, text):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class RepoAuditTest(unittest.TestCase):
    def test_repository_archive_is_consistent(self):
        report = docs_audit.audit(ROOT)
        self.assertEqual(report["status"], "ok", report["blockers"])
        self.assertGreaterEqual(report["count"], 120)
        self.assertEqual(report["blockers"], [])


class SyntheticAuditTest(unittest.TestCase):
    def _root(self, tmp, files, index, readme):
        _write(tmp, "README.md", readme)
        _write(tmp, "design/README.md", index)
        for name, text in files.items():
            _write(tmp, "design/" + name, text)
        return tmp

    def test_duplicate_numbers_are_blockers(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._root(
                tmp,
                {"1-a.md": "a", "1-b.md": "b"},
                "编号 00–1（2 份）",
                "00–1 共 2 份",
            )
            report = docs_audit.audit(tmp)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["blockers"][0]["kind"], "duplicate_number")

    def test_missing_index_target_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._root(
                tmp,
                {"1-a.md": "a"},
                "编号 00–1（1 份）\n[gone](9-missing.md)",
                "00–1 共 1 份",
            )
            report = docs_audit.audit(tmp)
        kinds = [item["kind"] for item in report["blockers"]]
        self.assertIn("index_missing_target", kinds)

    def test_count_mismatch_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._root(
                tmp,
                {"1-a.md": "a"},
                "编号 00–1（1 份）",
                "00–9 共 9 份",
            )
            report = docs_audit.audit(tmp)
        kinds = [item["kind"] for item in report["blockers"]]
        self.assertIn("readme_count_mismatch", kinds)

    def test_missing_design_dir_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, "README.md", "00–1 共 1 份")
            report = docs_audit.audit(tmp)
        self.assertEqual(report["status"], "blocked")


if __name__ == "__main__":
    unittest.main()

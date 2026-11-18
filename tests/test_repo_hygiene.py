"""Repo hygiene checker: the repository must pass its own check, and the check must fail."""

import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("repo_hygiene", ROOT / "scripts/repo_hygiene.py")
repo_hygiene = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(repo_hygiene)


class RepositoryHygieneTest(unittest.TestCase):
    def test_repository_passes_hygiene(self):
        report = repo_hygiene.check_hygiene(str(ROOT))
        self.assertEqual(report["status"], "ok", report["blockers"])
        self.assertEqual(report["blockers"], [])

    def test_site_copy_drift_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "demo").mkdir(parents=True)
            (root / "site" / "demo").mkdir(parents=True)
            (root / "demo" / "index.html").write_text("new", encoding="utf-8")
            (root / "site" / "demo" / "index.html").write_text("old", encoding="utf-8")
            blockers = repo_hygiene.check_site_copies(str(root))
            kinds = [item["kind"] for item in blockers]
            self.assertIn("site_copy_drift", kinds)

    def test_missing_source_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            blockers = repo_hygiene.check_site_copies(tmp)
            kinds = [item["kind"] for item in blockers]
            self.assertIn("site_source_missing", kinds)

    def test_stale_workflow_path_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "pages.yml").write_text(
                "on:\n  push:\n    paths:\n"
                "      - \"site/**\"\n"
                "      - \"16-does-not-exist.md\"\n",
                encoding="utf-8",
            )
            blockers = repo_hygiene.check_workflow_paths(str(root))
            missing = [item for item in blockers if item["kind"] == "workflow_path_missing"]
            self.assertEqual(len(missing), 1)
            self.assertEqual(missing[0]["path"], "16-does-not-exist.md")

    def test_glob_workflow_paths_are_not_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            (workflows / "pages.yml").write_text(
                "on:\n  push:\n    paths:\n      - \"site/**\"\n      - \"*.md\"\n",
                encoding="utf-8",
            )
            self.assertEqual(repo_hygiene.check_workflow_paths(str(root)), [])


if __name__ == "__main__":
    unittest.main()

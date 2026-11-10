import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("release_check", ROOT / "scripts/release_check.py")
release_check = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(release_check)


class ReleaseSurfaceTest(unittest.TestCase):
    def test_repository_surface_has_no_blockers(self):
        report = release_check.check_release(ROOT)
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["status"], "ok")
        # the license decision was made (Apache-2.0, root LICENSE committed): a missing
        # license must regress to a visible warning, and its presence must be recorded
        self.assertFalse(
            any(item.get("kind") == "license" and "pending" in str(item.get("status", "")) for item in report["warnings"]),
            "a chosen root LICENSE must clear the pending-license warning",
        )
        self.assertTrue(
            any(item.get("kind") == "license" and item.get("status") == "root LICENSE present" for item in report["info"]),
            "the release surface must record that the root LICENSE exists",
        )

    def test_public_release_requires_a_chosen_license(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = release_check.check_release(Path(tmp), for_public_release=True)
        kinds = [item.get("kind") for item in report["blockers"]]
        self.assertIn("license", kinds)
        self.assertIn("missing_doc", kinds)
        self.assertIn("missing_gitignore", kinds)

    def test_secret_and_local_path_scanners(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "leak.py").write_text(
                'api_key = "sk-' + "a" * 24 + '"\n'
                'path = "C:/Users/alice/project"\n',
                encoding="utf-8",
            )
            self.assertEqual(len(release_check._scan_secrets(root)), 1)
            paths = release_check._scan_local_paths(root)
            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0]["path"], "leak.py")
            self.assertEqual(paths[0]["severity"], "blocker")

    def test_gitignore_covers_local_only_trees(self):
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in release_check.REQUIRED_GITIGNORE:
            self.assertIn(pattern, text)

    def test_delivery_docs_state_the_boundaries(self):
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        for token in ("OPENAI_API_KEY", "not a sandbox", "runtime_data", "human"):
            self.assertIn(token, security)
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        for token in ("AstraDraw", "PyMuPDF", "CC BY-NC", "CycleResearcher"):
            self.assertIn(token, notices)
        licensing = (ROOT / "LICENSING.md").read_text(encoding="utf-8")
        self.assertIn("The code license is chosen: Apache-2.0", licensing)


if __name__ == "__main__":
    unittest.main()

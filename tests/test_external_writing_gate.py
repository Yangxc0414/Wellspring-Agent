import json
import tempfile
import unittest
from pathlib import Path

from research_agent.external_writing_gate import (
    ExternalWritingGateError,
    run_writing_lint,
)


def _root(tmp: Path, status: str, issues) -> Path:
    root = tmp / "external"
    script = root / "skills" / "scientific-writing" / "scripts" / "lint_manuscript.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({'tool': 'lint_manuscript', 'status': %r, "
        "'summary': {'errors': %d, 'warnings': %d}, 'issues': %r}))\n"
        % (status, 1 if status == "fail" else 0, len(issues), issues),
        encoding="utf-8",
    )
    return root


class ExternalWritingGateTest(unittest.TestCase):
    def test_whitelisted_lint_is_read_only_and_maps_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_root = _root(
                root,
                "pass",
                [{"severity": "warning", "code": "CONFIDENTIALITY_GATE_NOT_CHECKED"}],
            )
            draft = root / "draft.md"
            draft.write_text("# Draft\n\nNo placeholders here.\n", encoding="utf-8")
            before = draft.read_bytes()
            result = run_writing_lint(draft, skill_root)
            self.assertEqual(result["status"], "attention")
            self.assertEqual(result["external_status"], "pass")
            self.assertEqual(result["tool"], "scientific-writing.lint_manuscript")
            self.assertEqual(result["summary"]["warnings"], 1)
            self.assertIn("read-only", result["boundary"])
            self.assertEqual(draft.read_bytes(), before)

    def test_external_error_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_root = _root(
                root,
                "fail",
                [{"severity": "error", "code": "PLACEHOLDER_FOUND"}],
            )
            draft = root / "draft.md"
            draft.write_text("# Draft\n\nTODO\n", encoding="utf-8")
            result = run_writing_lint(draft, skill_root)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["issues"][0]["code"], "PLACEHOLDER_FOUND")

    def test_missing_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = Path(tmp) / "draft.md"
            draft.write_text("# Draft\n", encoding="utf-8")
            with self.assertRaises(ExternalWritingGateError):
                run_writing_lint(draft, Path(tmp) / "missing")


if __name__ == "__main__":
    unittest.main()

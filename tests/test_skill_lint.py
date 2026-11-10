import tempfile
import unittest
from pathlib import Path

from research_agent.skill_lint import lint_skill_directory, lint_skill_file


def write_skill(root: Path, name: str, description: str = "Use when testing a skill.", body: str = "# Test\n") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(
        "---\nname: %s\ndescription: %s\n---\n\n%s" % (name, description, body),
        encoding="utf-8",
    )
    return path


class SkillLintTest(unittest.TestCase):
    def test_valid_skill_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_skill(root, "literature-review")
            result = lint_skill_file(path)
            self.assertEqual(result["status"], "valid")
            self.assertEqual(result["errors"], [])
            report = lint_skill_directory(root)
            self.assertEqual(report["skill_count"], 1)
            self.assertEqual(report["status"], "valid")

    def test_manifest_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "bad" / "SKILL.md"
            path.parent.mkdir()
            path.write_text("---\nname: Bad Name\ndescription: 测试\n---\n", encoding="utf-8")
            result = lint_skill_file(path)
            self.assertEqual(result["status"], "invalid")
            self.assertTrue(any("lowercase" in item for item in result["errors"]))
            missing = root / "missing" / "SKILL.md"
            missing.parent.mkdir()
            missing.write_text("# no frontmatter\n", encoding="utf-8")
            self.assertEqual(lint_skill_file(missing)["status"], "invalid")

    def test_dangerous_script_and_link_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_skill(root, "unsafe", body="# Test\n\n[bad](../../outside.md)\n")
            scripts = path.parent / "scripts"
            scripts.mkdir()
            (scripts / "run.py").write_text("import subprocess\nsubprocess.run(['echo', 'x'])\n", encoding="utf-8")
            result = lint_skill_file(path)
            self.assertEqual(result["status"], "invalid")
            joined = " ".join(result["errors"])
            self.assertIn("dangerous script", joined)
            self.assertIn("link escapes", joined)

    def test_duplicate_names_and_long_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "same")
            second = root / "copy" / "SKILL.md"
            second.parent.mkdir()
            second.write_text(
                "---\nname: same\ndescription: Use when duplicating.\n---\n# Copy\n",
                encoding="utf-8",
            )
            report = lint_skill_directory(root)
            self.assertEqual(report["status"], "invalid")
            self.assertTrue(any("duplicate skill name" in item for item in report["errors"]))
            long_body = "\n".join("line %d" % index for index in range(501))
            long_path = write_skill(root, "long", body=long_body)
            result = lint_skill_file(long_path)
            self.assertTrue(any("body exceeds" in item for item in result["errors"]))

    def test_unknown_frontmatter_is_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "warn" / "SKILL.md"
            path.parent.mkdir()
            path.write_text(
                "---\nname: warning-skill\ndescription: Use when warning.\nextra: value\n---\n# W\n",
                encoding="utf-8",
            )
            result = lint_skill_file(path)
            self.assertEqual(result["status"], "attention")
            self.assertTrue(any("unknown frontmatter" in item for item in result["warnings"]))


if __name__ == "__main__":
    unittest.main()

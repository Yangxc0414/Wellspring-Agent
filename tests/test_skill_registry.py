import tempfile
import unittest
from pathlib import Path

from research_agent.skill_registry import (
    SkillError,
    SkillRegistryStore,
    manifest_from_payload,
    parse_skill_markdown,
    scan_skill_directory,
)

VALID = """---
name: citation-check
description: Check that claim refs point to locatable spans.
allowed-tools: evidence.inspect, Bash(git:*)
license: MIT
version: 1.2.0
---

# Citation check

Use read-only checks.
"""


class SkillParserTest(unittest.TestCase):
    def test_parse_skill_marks_untrusted_and_risk_flags(self):
        skill = parse_skill_markdown(VALID, "my-skills/citation-check/SKILL.md", "citation-check", has_scripts=True)
        self.assertTrue(skill.untrusted)
        self.assertEqual(skill.execution, "not_available")
        self.assertFalse(skill.enabled)
        self.assertEqual(skill.source, "imported")
        self.assertEqual(skill.version, "1.2.0")
        self.assertEqual(skill.license, "MIT")
        self.assertIn("shell_capable", skill.risk_flags)
        self.assertIn("has_scripts", skill.risk_flags)
        self.assertTrue(skill.content_hash)
        self.assertIn("Use read-only checks", skill.instructions)

    def test_parse_rejects_missing_metadata_and_oversize(self):
        with self.assertRaises(SkillError):
            parse_skill_markdown("no frontmatter", "x.md")
        with self.assertRaises(SkillError):
            parse_skill_markdown("---\nname: x\n---\nbody", "x.md")
        with self.assertRaises(SkillError):
            parse_skill_markdown("---\nname: x\n" + "x" * (200 * 1024) + "\n---\nbody", "x.md")

    def test_payload_validation_and_enabled_flag(self):
        manifest = manifest_from_payload(
            {
                "name": "Review",
                "description": "Review refs",
                "instructions": "Check each ref.",
                "tools": ["evidence.inspect", "Write"],
                "source": "custom",
                "enabled": True,
            }
        )
        self.assertEqual(manifest.source, "custom")
        self.assertTrue(manifest.enabled)
        self.assertIn("write_capable", manifest.risk_flags)
        with self.assertRaises(SkillError):
            manifest_from_payload({"name": "x", "description": "y", "instructions": "", "source": "custom"})
        with self.assertRaises(SkillError):
            manifest_from_payload({"name": "x", "description": "y", "instructions": "z", "source": "other"})


class SkillRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = SkillRegistryStore(self.root / "skills.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_register_deduplicate_toggle_delete_and_boundary(self):
        manifest = parse_skill_markdown(VALID, "x/SKILL.md")
        record, created = self.store.register(manifest)
        self.assertTrue(created)
        self.assertEqual(record["name"], "citation-check")
        again, created_again = self.store.register(manifest)
        self.assertFalse(created_again)
        self.assertEqual(again["id"], record["id"])
        self.assertTrue(self.store.set_enabled(record["id"], True)["enabled"])
        snapshot = self.store.snapshot()
        self.assertEqual(snapshot["count"], 1)
        self.assertIn("untrusted", snapshot["boundary"])
        self.assertIn("not_available", snapshot["skills"][0]["execution"])
        self.assertTrue(self.store.delete(record["id"]))
        self.assertFalse(self.store.delete(record["id"]))

    def test_scan_finds_skill_md_flat_md_and_detects_scripts(self):
        skill_dir = self.root / "corpus" / "citation-check"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(VALID, encoding="utf-8")
        scripts = skill_dir / "scripts"
        scripts.mkdir()
        (scripts / "check.py").write_text("print('not executed')", encoding="utf-8")
        data_only = self.root / "corpus" / "data-only"
        data_only.mkdir()
        (data_only / "SKILL.md").write_text(
            "---\nname: data-only\ndescription: Data resources only.\n---\nbody",
            encoding="utf-8",
        )
        (data_only / "scripts").mkdir()
        (data_only / "scripts" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
        (self.root / "corpus" / "flat.md").write_text(
            "---\nname: flat-review\ndescription: Flat review.\n---\nbody", encoding="utf-8"
        )
        bad = self.root / "corpus" / "bad"
        bad.mkdir()
        (bad / "SKILL.md").write_text("---\nname: bad\n---\nbody", encoding="utf-8")
        (self.root / "corpus" / "plain.md").write_text("no frontmatter", encoding="utf-8")
        result = scan_skill_directory(self.root / "corpus")
        self.assertEqual(len(result.skills), 3)
        self.assertGreaterEqual(len(result.skipped), 2)
        by_name = {skill.name: skill for skill in result.skills}
        self.assertTrue(by_name["citation-check"].has_scripts)
        self.assertIn("has_scripts", by_name["citation-check"].risk_flags)
        self.assertFalse(by_name["data-only"].has_scripts)
        imported = self.store.import_directory(self.root / "corpus")
        self.assertEqual(imported["snapshot"]["count"], 3)
        self.assertEqual(len(imported["rejected"]), 2)


if __name__ == "__main__":
    unittest.main()

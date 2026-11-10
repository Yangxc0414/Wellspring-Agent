import tempfile
import unittest
from pathlib import Path

from research_agent.specs import SpecError, SpecStore


SPEC_TEXT = """---
id: demo
name: 示例模块
stage: S1
version: 0.1.0
status: draft
owner: research-agent
inputs:
  - question
outputs:
  - Result
tools:
  - retriever.search
gates:
  - Q0
invariants:
  - 不创建 Claim
---

# 示例模块

## Purpose

用于测试。

## Contract

- 输入：question
- 输出：Result
- 不创建 Claim。

## Current Implementation

Old note.

## Boundaries

- 不联网。

## Changelog

- 2026-10-23 · v0.1.0 · 初始。
"""


class SpecStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "modules"
        module_dir = self.root / "demo"
        module_dir.mkdir(parents=True)
        self.path = module_dir / "SPEC.md"
        self.path.write_text(SPEC_TEXT, encoding="utf-8")
        self.store = SpecStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_and_load(self):
        specs = self.store.list_specs()
        self.assertEqual([spec.id for spec in specs], ["demo"])
        spec = self.store.load("demo")
        self.assertEqual(spec.version, "0.1.0")
        self.assertEqual(spec.outputs, ["Result"])
        self.assertIn("## Contract", spec.body)

    def test_real_module_specs_load_and_declare_invariants(self):
        store = SpecStore()
        specs = {spec.id: spec for spec in store.list_specs()}
        self.assertIn("literature", specs)
        self.assertIn("writing", specs)
        self.assertIn("integration", specs)
        self.assertEqual(specs["writing"].stage, "S8–S12")
        for spec in specs.values():
            self.assertTrue(spec.version, spec.id)
            self.assertTrue(spec.invariants, spec.id)
            self.assertTrue(spec.body, spec.id)

    def test_minimal_update_preserves_body_and_other_fields(self):
        spec = self.store.update(
            "demo",
            version="0.1.1",
            status="pilot",
            changelog="最小改进：补充一个验证点",
        )
        self.assertEqual(spec.version, "0.1.1")
        self.assertEqual(spec.status, "pilot")
        self.assertEqual(spec.inputs, ["question"])
        self.assertEqual(spec.tools, ["retriever.search"])
        self.assertIn("## Contract", spec.body)
        self.assertIn("Old note.", spec.body)
        self.assertIn("最小改进：补充一个验证点", spec.body)
        self.assertIn("v0.1.1", spec.body)
        self.assertEqual(self.store.load("demo").version, "0.1.1")

    def test_patch_section_only_changes_target(self):
        spec = self.store.patch_section("demo", "Current Implementation", "New note only.")
        self.assertIn("New note only.", spec.body)
        self.assertNotIn("Old note.", spec.body)
        self.assertIn("## Contract", spec.body)
        self.assertIn("不创建 Claim", spec.body)
        self.assertIn("## Boundaries", spec.body)

    def test_update_requires_changelog(self):
        with self.assertRaises(SpecError):
            self.store.update("demo", version="0.1.1")

    def test_list_updates_append_instead_of_replacing(self):
        self.store.update("demo", version="0.1.1", tools=["parser.spans"], changelog="add a tool")
        spec = self.store.load("demo")
        self.assertEqual(spec.tools, ["retriever.search", "parser.spans"])
        self.assertEqual(spec.inputs, ["question"])

    def test_replace_lists_is_still_available(self):
        self.store.update(
            "demo", version="0.1.1", tools=["only.this"], changelog="replace", replace_lists=True
        )
        self.assertEqual(self.store.load("demo").tools, ["only.this"])

    def test_invalid_version_is_rejected_before_write(self):
        with self.assertRaises(SpecError):
            self.store.update("demo", version="next", changelog="bad")
        self.assertEqual(self.store.load("demo").version, "0.1.0")


if __name__ == "__main__":
    unittest.main()

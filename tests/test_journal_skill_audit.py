import tempfile
import unittest
from pathlib import Path

import hashlib
import json

from research_agent.journal_skill_audit import (
    audit_journal_style,
    journal_style_brief,
    verify_journal_profiles,
)
from research_agent.manuscript_writer import _writer_prompt
from research_agent.revision_io import read_draft
from research_agent.writing_audit import audit_manuscript
from research_agent.writing_pack import build_writing_pack
from tests.writing_support import RUN_ID, make_writing_project, write_draft


class JournalSkillAuditTest(unittest.TestCase):
    def test_software_profile_flags_missing_journal_fields(self):
        text = """# 标题

## 摘要

本文针对缺陷定位问题，提出一种方法，实验结果表明该方法有效，结论对软件工程实践有意义。

## 参考文献

[REF-01] A paper title. 2024.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(text, encoding="utf-8")
            result = audit_journal_style(read_draft(path), "software_journal")
        self.assertEqual(result["status"], "needs_revision")
        self.assertIn("keywords.count", result["failed"])
        self.assertIn("classification.present", result["failed"])
        self.assertIn("references.gb7714", result["failed"])
        self.assertEqual(result["sources"][0]["license"], "MIT")

    def test_compliant_profile_passes_core_checks(self):
        text = """# 软件缺陷定位方法

## 摘要

本文针对软件缺陷定位问题，提出一种基于证据的定位方法，实验结果表明该方法提升了定位效果，结论对软件测试实践有启示。

**关键词**：缺陷定位；软件测试；证据审计；程序分析；实证研究

**中图分类号**：TP311

## Abstract

This paper addresses software defect localization with an evidence-based method.

**Key words**: defect localization; software testing; evidence audit; program analysis; empirical study

## 引言

软件缺陷定位是一个重要问题。已有工作存在证据不足。本文的贡献是证据审计方法。我们给出实验证据。最后讨论局限。

## 方法与实验

方法说明。

## 讨论

### 威胁有效性

构造效度、内部效度、外部效度与结论效度分别讨论。

## 参考文献

[1] 张三, 李四. 缺陷定位方法[J]. 软件学报, 2024, 35(1): 1-10.
[2] Smith J. Testing software[C]//Proceedings of ICSE. 2024: 1-10.
"""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "draft.md"
            path.write_text(text, encoding="utf-8")
            result = audit_journal_style(read_draft(path), "software_journal")
        self.assertIn(result["status"], ("pass", "warn"))
        self.assertNotIn("keywords.count", result["failed"])
        self.assertNotIn("references.gb7714", result["failed"])
        self.assertNotIn("threats.present", result["failed"])

    def test_journal_style_brief_is_injected_into_writer_prompt(self):
        self.assertIn("中图分类号", journal_style_brief("software_journal"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            pack = build_writing_pack(project, RUN_ID, venue="software_journal")
            prompt = _writer_prompt(pack, {"gaps": [], "final_ideas": []})[1]["content"]
        self.assertIn("目标期刊规范", prompt)
        self.assertIn("中图分类号", prompt)
        self.assertIn("GB/T 7714", prompt)

    def test_profile_verification_detects_source_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            skill = root / "packs" / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("# demo\n", encoding="utf-8")
            license_file = root / "LICENSE"
            license_file.write_text("MIT License\n", encoding="utf-8")
            profile = {
                "profiles": {
                    "demo": {
                        "license_path": "LICENSE",
                        "license_sha256": hashlib.sha256(license_file.read_bytes()).hexdigest(),
                        "sources": [
                            {
                                "skill": "demo",
                                "path": "packs/skills/demo/SKILL.md",
                                "sha256": hashlib.sha256(skill.read_bytes()).hexdigest(),
                            }
                        ],
                    }
                }
            }
            profiles_path = Path(tmp) / "profiles.json"
            profiles_path.write_text(json.dumps(profile), encoding="utf-8")
            verified = verify_journal_profiles(root, profiles_path)
            self.assertEqual(verified["status"], "verified")
            skill.write_text("# changed\n", encoding="utf-8")
            stale = verify_journal_profiles(root, profiles_path)
            self.assertEqual(stale["status"], "stale")
            self.assertTrue(stale["stale"])

    def test_pipeline_writer_profiles_include_journal_skills(self):
        from research_agent.adapters.paper_writer import WRITER_SYSTEM
        from research_agent.modules.paper import PROFILES

        self.assertIn("software_journal", PROFILES)
        self.assertIn("computer_journal", PROFILES)
        self.assertIn("journal_style", WRITER_SYSTEM)

    def test_writing_audit_carries_journal_style_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root, signed=True)
            pack = build_writing_pack(project, RUN_ID)
            draft = write_draft(root / "draft.md", result_text="无数字。")
            audit = audit_manuscript(draft, pack=pack, venue="computer_journal")
        self.assertIn("journal_style", audit)
        self.assertEqual(audit["journal_style"]["venue_id"], "computer_journal")
        self.assertTrue(audit["journal_style"]["sources"])


if __name__ == "__main__":
    unittest.main()

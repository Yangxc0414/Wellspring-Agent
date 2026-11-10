"""Chinese-journal and grant submission audits: structural checks only."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.revision_types import Block, DraftDocument, Section
from research_agent.venue_audit import (
    audit_chinese_journal,
    audit_grant,
    manuscript_from_draft,
)


def _manuscript():
    abstract = "本文研究科研智能体的证据审计方法。" * 20
    sections = [
        {"label": "引言", "text": "研究背景与问题。" * 20},
        {"label": "相关工作", "text": "已有工作与差异。" * 20},
        {"label": "方法", "text": "方法设计与证据链。" * 20},
        {"label": "实验", "text": "实验设置与基线。" * 20},
        {"label": "结果", "text": "结果与分析。" * 20},
        {"label": "讨论", "text": "讨论与局限。" * 20},
        {"label": "结论", "text": "结论。基金项目：示例基金（No. 0000）。创新点：证据审计。数据可用：代码与数据已公开。" * 5},
    ]
    references = [
        {"title": "中文文献%d" % index if index < 4 else "English reference %d" % index,
         "text": "", "verified": True}
        for index in range(8)
    ]
    return {
        "abstract": abstract,
        "keywords": ["科研智能体", "证据审计", "复现", "实验设计", "写作"],
        "sections": sections,
        "references": references,
    }


def _grant_sections(scheme="nsfc"):
    from research_agent.modules.grant import SCHEMES

    return {module: "研究内容与依据。" * 30 for module in SCHEMES[scheme]["modules"]}


class ChineseJournalAuditTest(unittest.TestCase):
    def test_a_complete_chinese_manuscript_is_ready_for_human(self):
        result = audit_chinese_journal(_manuscript())
        self.assertEqual(result["status"], "ready_for_human", result["blockers"])
        self.assertFalse(result["submission_ready"])
        self.assertEqual(result["track"], "zh_journal:zh_core_journal")

    def test_missing_method_section_blocks(self):
        manuscript = _manuscript()
        manuscript["sections"] = [
            section for section in manuscript["sections"] if section["label"] != "方法"
        ]
        result = audit_chinese_journal(manuscript)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item.startswith("section.方法") for item in result["blockers"]))

    def test_english_only_references_are_a_warning(self):
        manuscript = _manuscript()
        for reference in manuscript["references"]:
            reference["title"] = "English only"
        result = audit_chinese_journal(manuscript)
        self.assertEqual(result["status"], "needs_revision")
        self.assertTrue(any(item.startswith("references.chinese") for item in result["warnings"]))

    def test_a_non_chinese_profile_is_refused(self):
        with self.assertRaises(ValueError):
            audit_chinese_journal(_manuscript(), profile_name="software_journal_x")


class GrantAuditTest(unittest.TestCase):
    def test_a_complete_nsfc_skeleton_is_ready_for_human(self):
        result = audit_grant(
            _grant_sections("nsfc"), scheme="nsfc", evidence_refs=["prior-work"],
            ai_statement=True,
        )
        self.assertEqual(result["status"], "ready_for_human", result["blockers"])
        self.assertFalse(result["submission_ready"])

    def test_missing_innovation_blocks(self):
        sections = _grant_sections("nsfc")
        sections.pop("创新点")
        result = audit_grant(sections, scheme="nsfc", evidence_refs=["ref"], ai_statement=True)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item.startswith("innovation.stated") for item in result["blockers"]))

    def test_nssfc_requires_anonymous_review(self):
        result = audit_grant(_grant_sections("nssfc"), scheme="nssfc",
                             evidence_refs=["ref"], ai_statement=True)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any(item.startswith("anonymity.confirmed") for item in result["blockers"]))
        confirmed = audit_grant(_grant_sections("nssfc"), scheme="nssfc",
                                evidence_refs=["ref"], anonymous=True,
                                identity_removed=True, ai_statement=True)
        self.assertEqual(confirmed["status"], "ready_for_human", confirmed["blockers"])

    def test_unknown_scheme_is_refused(self):
        with self.assertRaises(ValueError):
            audit_grant({"立项依据": "text"}, scheme="unknown")


class DraftAdapterTest(unittest.TestCase):
    def test_draft_is_adapted_without_losing_sections_or_keywords(self):
        document = DraftDocument(
            title="测试",
            sections=[
                Section("摘要", 1, [Block("paragraph", "本文研究证据审计。关键词：科研智能体；证据链")]),
                Section("引言", 1, [Block("paragraph", "研究背景。")]),
            ],
        )
        view = manuscript_from_draft(
            document,
            [{"title": "中文文献", "text": "", "verified": True}],
        )
        self.assertTrue(view["abstract"].startswith("本文研究"))
        self.assertEqual(view["keywords"], ["科研智能体", "证据链"])
        self.assertEqual([item["label"] for item in view["sections"]], ["摘要", "引言"])
        self.assertTrue(view["references"][0]["verified"])


class VenueAuditCLITest(unittest.TestCase):
    def test_cli_audits_a_chinese_manuscript(self):
        from research_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "manuscript.json"
            path.write_text(json.dumps(_manuscript(), ensure_ascii=False), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["venue", "audit", "--kind", "zh_journal", "--file", str(path)])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "ready_for_human")
            self.assertFalse(result["submission_ready"])

    def test_cli_audits_a_grant_section_file(self):
        from research_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "grant.json"
            path.write_text(
                json.dumps(
                    {"sections": _grant_sections("nssfc"), "evidence_refs": ["prior"]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([
                    "venue", "audit", "--kind", "grant", "--scheme", "nssfc",
                    "--anonymous", "--identity-removed", "--ai-statement",
                    "--file", str(path),
                ])
            self.assertEqual(code, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "ready_for_human")
            self.assertEqual(result["track"], "grant:nssfc")


if __name__ == "__main__":
    unittest.main()

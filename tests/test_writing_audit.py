import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict
from typing import Any, Dict

from research_agent.project import run_dir
from research_agent.writing_audit import audit_manuscript, write_audit
from research_agent.writing_pack import build_writing_pack, ensure_pack_marker
from tests.writing_support import RUN_ID, make_writing_project, write_draft


class WritingAuditScriptPunctuationTest(unittest.TestCase):
    """A draft whose punctuation script contradicts the pack's declared language is a defect.

    The bug this guards: an English draft shipped with the Chinese keyword label
    「关键词：**…** because the renderer hard-coded full-width marks. Every other audit line
    was green, so only a check that names the leaked marks can catch it.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _check(audit: Dict[str, Any]) -> Dict[str, Any]:
        return next(item for item in audit["checks"] if item["id"] == "script.punctuation")

    def test_chinese_draft_with_chinese_punctuation_passes(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "zh.md", result_text="无数字。")

        audit = audit_manuscript(draft, pack=pack)
        check = self._check(audit)
        self.assertEqual(check["status"], "pass")
        self.assertIn("han characters:", check["detail"])

    def test_english_draft_with_fullwidth_chinese_label_is_flagged(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID, language="en", venue="en_conference")
        draft_path = self.root / "en.md"
        draft_path.write_text(
            "# Test Manuscript\n\n## Abstract\n\n"
            "**关键词：** 学习曲线；决策；评估。 This sentence cites [REF-01].\n",
            encoding="utf-8",
        )

        audit = audit_manuscript(draft_path, pack=pack)
        check = self._check(audit)
        self.assertEqual(check["status"], "fail")
        self.assertEqual(check["severity"], "warning")
        self.assertIn("CJK punctuation: 4", check["detail"])
        self.assertIn("han characters: 11", check["detail"])
        self.assertTrue(any("script.punctuation" in item for item in audit["warnings"]))

    def test_chinese_draft_with_halfwidth_mark_between_han_characters_is_flagged(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "zh_mix.md", result_text="方法,结果。")

        audit = audit_manuscript(draft, pack=pack)
        check = self._check(audit)
        self.assertEqual(check["status"], "fail")
        self.assertIn("half-width marks between Han characters: 1", check["detail"])

    def test_missing_language_is_reported_as_unassessable_not_silently_green(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID)
        pack.pop("language")
        draft = write_draft(self.root / "nolang.md", result_text="无数字。")

        audit = audit_manuscript(draft, pack=pack)
        check = self._check(audit)
        self.assertEqual(check["status"], "pass")
        self.assertTrue(check["detail"].startswith("not_assessable"))
        self.assertTrue(any("script.punctuation not_assessable" in item for item in audit["warnings"]))


class WritingAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_unsigned_reproduction_with_result_numbers_is_blocked(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="R² 均值为 0.1438，ΔR² 为 0.187。")

        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "blocked")
        self.assertFalse(audit["submission_ready"])
        self.assertTrue(any(item.startswith("claim.signed") for item in audit["blockers"]))
        self.assertTrue(any("results.numbers_without_claim" in item for item in audit["blockers"]))
        self.assertEqual(audit["result_number_count"], 2)

    def test_signed_reproduction_with_known_numbers_is_ready_for_human_review(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="R² 均值为 0.1438，ΔR² 为 0.187。")

        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "ready_for_human_review")
        self.assertFalse(audit["submission_ready"])
        self.assertFalse(audit["blockers"])
        self.assertTrue(any("preprint" in item for item in audit["warnings"]))
        self.assertTrue(audit["draft_sha256"])

    def test_chinese_venue_audit_is_advisory_and_does_not_change_status(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "venue.md", result_text="无数字。")

        audit = audit_manuscript(draft, pack=pack, venue="zh_core_journal")
        self.assertIn("venue_audit", audit)
        self.assertEqual(audit["status"], "ready_for_human_review", audit["blockers"])
        self.assertTrue(
            any(item.startswith("venue_audit.") for item in audit["warnings"]),
            audit["warnings"],
        )

    def test_non_chinese_venue_skips_the_adapter(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "en.md", result_text="无数字。")
        audit = audit_manuscript(draft, pack=pack, venue="en_conference")
        self.assertNotIn("venue_audit", audit)

    def test_signed_reproduction_allows_verified_design_constants(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(
            self.root / "draft.md", result_text="在 3 个 seed 下，R² 均值为 0.1438。"
        )

        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "ready_for_human_review", audit["blockers"])
        self.assertIn("3", pack["writing_contract"]["allowed_design_numbers"])

    def test_untraceable_signed_number_is_blocked(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="R² 均值为 0.9999。")

        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(any("results.numbers_traceable" in item for item in audit["blockers"]))

    def test_signed_reproduction_checks_abstract_numbers(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="无数字。")
        body = draft.read_text(encoding="utf-8").replace(
            "本文研究学习曲线在数据采集决策中的作用 [REF-01]。",
            "本文报告 R² 为 0.9999 [REF-01]。",
        )
        draft.write_text(body, encoding="utf-8")

        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(
            any("results.narrative_numbers_traceable" in item for item in audit["blockers"])
        )

        body = body.replace("0.9999", "0.1438")
        draft.write_text(body, encoding="utf-8")
        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "ready_for_human_review", audit["blockers"])

    def test_pack_binding_matches_and_mismatch_blocks(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "bound.md", result_text="无数字。")
        draft.write_text(
            ensure_pack_marker(draft.read_text(encoding="utf-8"), pack), encoding="utf-8"
        )
        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["pack_binding"], "bound")
        self.assertEqual(audit["status"], "ready_for_human_review", audit["blockers"])

        text = draft.read_text(encoding="utf-8").replace(
            pack["pack_id"], "WP-000000000000"
        )
        draft.write_text(text, encoding="utf-8")
        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["pack_binding"], "mismatch")
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(any("draft.pack_binding" in item for item in audit["blockers"]))

    def test_strict_pack_binding_blocks_unmarked_draft(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "unmarked.md", result_text="无数字。")
        audit = audit_manuscript(draft, pack=pack, strict_pack_binding=True)
        self.assertEqual(audit["pack_binding"], "unbound")
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(any("draft.pack_binding" in item for item in audit["blockers"]))

    def test_multi_ref_sentence_is_warned(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="无数字。")
        text = draft.read_text(encoding="utf-8").replace(
            "已有综述总结了学习曲线方法 [REF-01]。",
            "已有综述总结了学习曲线方法 [REF-01][REF-02]。",
        )
        draft.write_text(text, encoding="utf-8")
        audit = audit_manuscript(draft, pack=pack)
        self.assertGreaterEqual(audit["multi_ref_sentence_count"], 1)
        self.assertTrue(
            any("citations.multi_ref" in item for item in audit["warnings"])
        )

    def test_uncited_factual_claim_is_warned_and_strict_blocks(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="无数字。")
        text = draft.read_text(encoding="utf-8").replace(
            "已有综述总结了学习曲线方法 [REF-01]。",
            "研究表明学习曲线方法普遍优于所有基线。",
        )
        draft.write_text(text, encoding="utf-8")

        audit = audit_manuscript(draft, pack=pack)
        self.assertGreaterEqual(audit["uncited_factual_count"], 1)
        self.assertTrue(
            any("citations.uncited_factual" in item for item in audit["warnings"])
        )

        def judge(payload):
            return [
                {
                    "id": item["id"],
                    "status": "supported",
                    "rationale": "checked",
                    "evidence_refs": [item["evidence"][0]["ref"]],
                }
                for item in payload["items"]
            ]

        strict = audit_manuscript(
            draft, pack=pack, support_judge=judge, strict_support=True
        )
        self.assertEqual(strict["status"], "blocked")
        self.assertTrue(
            any("citations.uncited_factual" in item for item in strict["blockers"])
        )

    def test_strict_support_uses_a_qoder_ledger_without_a_judge(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="无数字。")
        draft.write_text(
            ensure_pack_marker(draft.read_text(encoding="utf-8"), pack),
            encoding="utf-8",
        )
        target = run_dir(project, RUN_ID)
        digest = hashlib.sha256(draft.read_bytes()).hexdigest()
        (target / "support-ledger.json").write_text(
            json.dumps(
                {
                    "schema_version": "support-ledger-0.1",
                    "draft_sha256": digest,
                    "status": "partial",
                    "counts": {"supported": 1, "insufficient": 1},
                    "unresolved_refs": 0,
                    "items": [],
                }
            ),
            encoding="utf-8",
        )
        audit = write_audit(
            draft,
            target,
            pack=pack,
            project=project,
            run_id=RUN_ID,
            strict_support=True,
            support_judge=None,
        )
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(any("support_ledger" in item for item in audit["blockers"]))

    def test_support_panel_gates_audit_and_rejects_stale_draft(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="无数字。")
        draft.write_text(
            ensure_pack_marker(draft.read_text(encoding="utf-8"), pack),
            encoding="utf-8",
        )
        target = run_dir(project, RUN_ID)
        panel_path = target / "support-panel.json"
        digest = hashlib.sha256(draft.read_bytes()).hexdigest()
        panel_path.write_text(
            json.dumps(
                {
                    "status": "needs_human",
                    "pending_human": ["SUP-01"],
                    "draft_sha256": digest,
                }
            ),
            encoding="utf-8",
        )
        blocked = write_audit(draft, target, pack=pack, project=project, run_id=RUN_ID)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["support_panel"]["status"], "needs_human")
        self.assertTrue(any("support_panel" in item for item in blocked["blockers"]))

        panel_path.write_text(
            json.dumps({"status": "ready", "pending_human": [], "draft_sha256": digest}),
            encoding="utf-8",
        )
        ready = write_audit(draft, target, pack=pack, project=project, run_id=RUN_ID)
        self.assertEqual(ready["status"], "ready_for_human_review", ready["blockers"])
        self.assertEqual(ready["support_panel"]["status"], "ready")
        self.assertTrue(ready["support_panel"]["draft_matches"])

        (target / "support-gold.json").write_text(
            json.dumps(
                {
                    "draft_sha256": digest,
                    "status": "complete",
                    "annotators": [{"id": "A"}, {"id": "B"}],
                    "agreement": {"mean_kappa": 0.6},
                    "panel": {"accuracy": 0.75},
                }
            ),
            encoding="utf-8",
        )
        with_gold = write_audit(draft, target, pack=pack, project=project, run_id=RUN_ID)
        self.assertEqual(with_gold["support_gold"]["annotators"], 2)
        self.assertEqual(with_gold["support_gold"]["mean_kappa"], 0.6)
        self.assertEqual(with_gold["support_gold"]["panel_accuracy"], 0.75)

        panel_path.write_text(
            json.dumps({"status": "ready", "pending_human": [], "draft_sha256": "b" * 64}),
            encoding="utf-8",
        )
        stale = write_audit(draft, target, pack=pack, project=project, run_id=RUN_ID)
        self.assertEqual(stale["status"], "blocked")
        self.assertFalse(stale["support_panel"]["draft_matches"])
        self.assertTrue(any("panel draft hash" in item for item in stale["blockers"]))

    def test_internal_ids_are_not_result_numbers(self):
        project = make_writing_project(self.root, with_run=False)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(
            self.root / "ids.md",
            result_text="TH-01 与 TH-02 表明主题之间存在张力，GAP-03 仍是缺口。",
        )
        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["result_number_count"], 0)
        self.assertEqual(audit["status"], "ready_for_human_review", audit["blockers"])

    def test_section_numbers_are_not_result_numbers(self):
        project = make_writing_project(self.root, with_run=False)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(
            self.root / "sections.md",
            result_text="按 4.2 节与 4.3 节的规则，本文只做定性综合，不报告实验数值。",
        )
        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "ready_for_human_review", audit["blockers"])
        self.assertEqual(audit["result_number_count"], 0)

    def test_unknown_citation_is_blocked(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(
            self.root / "draft.md",
            result_text="R² 均值为 0.1438。",
            citation="[REF-99]",
        )

        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(any("citations.known" in item for item in audit["blockers"]))

    def test_review_draft_needs_no_signed_claim_but_still_records_it_as_a_warning(self):
        project = make_writing_project(self.root, with_run=False)
        pack = build_writing_pack(project, RUN_ID)
        draft = write_draft(self.root / "draft.md", result_text="结果表明所提框架在多数设置下优于基线。")

        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "ready_for_human_review")
        self.assertFalse(audit["blockers"])
        claim_check = next(item for item in audit["checks"] if item["id"] == "claim.signed")
        self.assertEqual(claim_check["status"], "warn")

    def test_placeholders_and_fixture_sources_are_blocked(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)
        pack["literature"]["references"][0]["fixture"] = True
        draft = write_draft(
            self.root / "draft.md",
            result_text="R² 均值为 0.1438。待补",
        )

        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(any(item.startswith("placeholders") for item in audit["blockers"]))
        self.assertTrue(any(item.startswith("fixture") for item in audit["blockers"]))

    def test_write_audit_persists_json(self):
        project = make_writing_project(self.root, signed=True)
        draft = write_draft(self.root / "draft.md", result_text="R² 均值为 0.1438。")
        output = self.root / "audit"

        audit = write_audit(draft, output, project=project, run_id=RUN_ID)
        self.assertTrue((output / "writing-audit.json").is_file())
        persisted = json.loads((output / "writing-audit.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], audit["status"])

    def test_multi_source_pack_requires_body_diversity(self):
        project = make_writing_project(self.root, with_run=False)
        pack = build_writing_pack(project, RUN_ID)
        base = pack["literature"]["references"][0]
        pack["literature"]["references"] = [
            dict(base, ref_id="REF-%02d" % index) for index in range(1, 7)
        ]
        draft = write_draft(
            self.root / "draft.md",
            result_text="结果表明所提框架在多数设置下优于基线。",
            citation="[REF-01]",
        )
        audit = audit_manuscript(draft, pack=pack)
        self.assertEqual(audit["status"], "blocked")
        self.assertTrue(
            any(item.startswith("sources.diversity") for item in audit["blockers"])
        )

    def test_section_cross_reference_is_not_a_result_number(self):
        # A prose cross-reference used to be counted as an unsigned result number, which
        # blocked an honest results section and forced a full regeneration round.
        project = make_writing_project(self.root)
        draft = write_draft(
            self.root / "draft.md",
            result_text="本文不报告结果数字，只支撑第 3 节与第 2.1 节的控制类主张，如 §4 所述。",
        )
        audit = audit_manuscript(draft, pack=build_writing_pack(project, RUN_ID))
        self.assertFalse(
            any(item.startswith("results.numbers_without_claim") for item in audit["blockers"])
        )

    def test_real_result_numbers_still_blocked(self):
        project = make_writing_project(self.root)
        draft = write_draft(
            self.root / "draft.md",
            result_text="准确率达到 0.87，较基线提升 12%，见 15 例样本。",
        )
        audit = audit_manuscript(draft, pack=build_writing_pack(project, RUN_ID))
        self.assertTrue(
            any(item.startswith("results.numbers_without_claim") for item in audit["blockers"])
        )

    MERGED = """# 测试手稿

## 摘要

本文研究学习曲线在数据采集决策中的作用 [REF-01]。

## 引言与相关工作

数据规模决策需要可复现的评估 [REF-01]。已有综述总结了学习曲线方法 [REF-02]。

## 方法

我们采用统一协议比较不同策略 [REF-02]。

## 实验与结果

实验使用固定数据划分和多个随机种子 [REF-01]。结果表明所提框架在多数设置下优于基线 [REF-02]。

## 讨论与结论

结果仍需在更多数据集上复核 [REF-01]。本文给出可审计的评估框架 [REF-02]。

## 参考文献

[REF-01] A. 文献一
[REF-02] B. 文献二
"""

    def _audit(self, text: str):
        project = make_writing_project(self.root, with_run=False)
        draft = self.root / "draft.md"
        draft.write_text(text, encoding="utf-8")
        return audit_manuscript(draft, pack=build_writing_pack(project, RUN_ID))

    def test_merged_headings_are_named_not_counted_as_nine_sections(self):
        audit = self._audit(self.MERGED)
        # Merging sections is legitimate, so nothing may block on it.
        self.assertEqual(audit["status"], "ready_for_human_review")
        self.assertFalse(audit["blockers"])
        merged = next(item for item in audit["checks"] if item["id"] == "structure.merged_headings")
        self.assertEqual(merged["status"], "fail")
        self.assertEqual(merged["severity"], "warning")
        self.assertIn('"实验与结果" -> experiment+result', merged["detail"])
        self.assertIn('"讨论与结论" -> discussion+conclusion', merged["detail"])

    def test_absent_section_fails_its_own_structure_check(self):
        audit = self._audit(
            self.MERGED.replace("## 摘要\n\n本文研究学习曲线在数据采集决策中的作用 [REF-01]。\n\n", "")
        )
        abstract = next(item for item in audit["checks"] if item["id"] == "structure.abstract")
        self.assertEqual(abstract["status"], "fail")
        self.assertEqual(abstract["severity"], "blocker")
        self.assertTrue(
            any(item.startswith("structure.abstract") for item in audit["blockers"]),
            audit["blockers"],
        )

    def test_missing_pack_and_project_is_rejected(self):
        draft = write_draft(self.root / "draft.md", result_text="无数字。")
        with self.assertRaises(ValueError):
            audit_manuscript(draft)


if __name__ == "__main__":
    unittest.main()

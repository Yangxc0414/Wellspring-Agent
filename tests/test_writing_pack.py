import json
import tempfile
import unittest
from pathlib import Path

from research_agent.project import ProjectError
from research_agent.support_audit import audit_pack_support
from research_agent.writing_pack import (
    _selected_spans,
    bind_text_to_pack,
    build_writing_pack,
    render_writing_pack,
)
from tests.writing_support import RUN_ID, SOURCE_ID, make_writing_project


class WritingPackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_pack_selects_clean_spans_and_real_reference_fields(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID)

        references = pack["literature"]["references"]
        self.assertEqual(references[0]["ref_id"], "REF-01")
        self.assertEqual(references[0]["title"], "Learning Curves for Decision Making: A Survey")
        self.assertEqual(references[0]["authors"], ["A. Researcher", "B. Researcher"])
        self.assertEqual(references[0]["arxiv_id"], "2401.00001")
        self.assertIn("Learning curves describe model performance", references[0]["abstract"])
        self.assertIn(references[0]["ref_id"], pack["evidence_map"])

        selected = pack["literature"]["selected_spans"][SOURCE_ID]
        texts = [item["text"] for item in selected]
        self.assertTrue(any("unified framework" in text for text in texts))
        self.assertFalse(any("Instruction:" in text for text in texts))
        self.assertFalse(any("Natalia" in text for text in texts))
        self.assertFalse(any("Figure 2" in text for text in texts))
        self.assertTrue(all(item["score"] >= 4 for item in selected))
        self.assertEqual(pack["writing_contract"]["allowed_result_numbers"], [])
        self.assertEqual(pack["claim"]["status"], "draft_needs_human")
        self.assertTrue(any("claim is not signed" in item for item in pack["warnings"]))
        self.assertGreater(pack["token_estimate"], 0)

        rendered = render_writing_pack(pack)
        self.assertIn("REF-01", rendered)
        self.assertIn("draft_needs_human", rendered)
        json.dumps(pack, ensure_ascii=False)

    def test_a_short_chinese_span_is_not_dropped_as_trivial(self):
        literature = {
            "spans": [
                {
                    "span_id": "S-1",
                    "source_id": "FX-1",
                    "text": "在湿热老化条件下，只有记录完整时钝化与对照的寿命差异才可能被判定。",
                },
                {
                    "span_id": "S-2",
                    "source_id": "FX-2",
                    "text": "该数值仅用于测试流程，不是真实实验结果。",
                },
                {"span_id": "S-3", "source_id": "FX-3", "text": "太短"},
            ]
        }
        selected = _selected_spans(literature, 3)
        # A 32-CJK-char sentence and an 18-char disclaimer are both evidence; the old
        # 60-character English threshold dropped every short Chinese fixture span.
        self.assertEqual([item["span_id"] for item in selected["FX-1"]], ["S-1"])
        self.assertEqual([item["span_id"] for item in selected["FX-2"]], ["S-2"])
        self.assertNotIn("FX-3", selected)

    def test_the_research_question_lifts_on_topic_spans_above_generic_intro(self):
        literature = {
            "query_plan": {"question": "How do self-improving coding agents use archives?"},
            "spans": [
                {
                    "span_id": "S-INTRO",
                    "source_id": "FX-1",
                    "section": "1 Introduction",
                    "page": 1,
                    "text": "These insights show that scientific progress is cumulative and open-ended, with each breakthrough standing on prior work.",
                },
                {
                    "span_id": "S-ARCHIVE",
                    "source_id": "FX-1",
                    "section": "3 Method",
                    "page": 1,
                    "text": "The agent maintains an archive of generated coding agents and adds every evaluated variant to that archive over time.",
                },
            ],
        }
        # Without the question the intro sentence wins on section/page/format alone.
        plain = _selected_spans(literature, 1)
        self.assertEqual(plain["FX-1"][0]["span_id"], "S-INTRO")
        selected = _selected_spans(literature, 1, "How do self-improving coding agents use archives?")
        self.assertEqual(selected["FX-1"][0]["span_id"], "S-ARCHIVE")
        self.assertGreaterEqual(selected["FX-1"][0]["topic_hits"], 1)

    def _numeric_reference_block(self, pack):
        refs = pack["literature"]["references"]
        # Deliberately reverse the pack order: [1] is not REF-01, so index mapping would be
        # wrong; only title matching can resolve it.
        return refs, "[1] %s\n[2] %s\n" % (refs[1]["title"], refs[0]["title"]), [
            refs[1]["ref_id"], refs[0]["ref_id"]
        ]

    def test_bind_accepts_numeric_citations_from_the_generated_manuscript(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID)
        refs, block, expected = self._numeric_reference_block(pack)
        result = bind_text_to_pack(
            "# 稿\n\n钝化提高稳定性[1]，协议需要完整记录[2]。\n\n## 参考文献\n\n" + block, pack
        )
        self.assertEqual(result["numbered_refs"], [1, 2])
        self.assertEqual(result["resolved_refs"], expected)
        self.assertIn("writing-pack", result["text"])

        with self.assertRaises(ValueError):
            bind_text_to_pack("# 稿\n\n越界引用[9]。", pack)

    def test_support_items_accept_numeric_citations(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID)
        refs, block, expected = self._numeric_reference_block(pack)
        draft = self.root / "numeric-draft.md"
        draft.write_text(
            "# 稿\n\n## 摘要\n\n钝化层提高湿热稳定性[1]，但记录缺项时只能标为未判定[2]。\n\n## 参考文献\n\n"
            + block,
            encoding="utf-8",
        )
        report = audit_pack_support(draft, pack, collect_only=True)
        self.assertTrue(report["items"])
        modes = {item["citation_mode"] for item in report["items"]}
        self.assertIn("numeric_ref", modes)
        cited = {ref for item in report["items"] for ref in item["refs"]}
        self.assertEqual(cited, set(expected))
        self.assertTrue(any(item["evidence"] for item in report["items"]))

    def test_claim_plan_binds_each_claim_to_one_ref_and_span(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID)
        plan = pack["claim_plan"]
        self.assertEqual(plan["schema_version"], "claim-plan-0.1")
        self.assertTrue(plan["claims"])
        for claim in plan["claims"]:
            self.assertTrue(claim["ref_id"])
            self.assertTrue(claim["span_id"])
            self.assertGreaterEqual(len(claim["quote"]), 20)
        self.assertIn("Claim plan", render_writing_pack(pack))

    def test_signed_claim_publishes_only_traceable_numbers(self):
        project = make_writing_project(self.root, signed=True)
        pack = build_writing_pack(project, RUN_ID)

        self.assertEqual(pack["claim"]["status"], "signed")
        self.assertEqual(pack["writing_contract"]["article_type"], "reproduction")
        allowed = pack["writing_contract"]["allowed_result_numbers"]
        # Raw values plus the 4/6-decimal renderings the paper prints.
        for value in ("0.0123", "0.1438", "0.187", "0.143800", "0.187000"):
            self.assertIn(value, allowed)
        self.assertFalse(any("claim is not signed" in item for item in pack["warnings"]))

    def test_review_pack_has_no_reproduction_contract(self):
        project = make_writing_project(self.root, with_run=False)
        pack = build_writing_pack(project, RUN_ID)

        self.assertEqual(pack["writing_contract"]["article_type"], "review")
        self.assertEqual(pack["claim"]["status"], "missing")
        self.assertEqual(pack["writing_contract"]["allowed_result_numbers"], [])

    def test_unknown_run_is_rejected(self):
        project = make_writing_project(self.root)
        with self.assertRaises(ProjectError):
            build_writing_pack(project, "RUN-NOT-FOUND")

    def test_pack_is_bounded_by_max_sources_and_spans(self):
        project = make_writing_project(self.root)
        pack = build_writing_pack(project, RUN_ID, max_sources=1, max_spans_per_source=1)

        self.assertEqual(len(pack["literature"]["references"]), 1)
        self.assertEqual(len(pack["literature"]["selected_spans"][SOURCE_ID]), 1)


if __name__ == "__main__":
    unittest.main()

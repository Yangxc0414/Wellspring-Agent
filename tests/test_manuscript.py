import copy
import unittest

from research_agent.manuscript import build_manuscript, render_manuscript_markdown


def ready_fixture():
    sources = []
    spans = []
    references = []
    for index in range(1, 11):
        source_id = "SRC-%d" % index
        span_id = "SPAN-%d" % index
        sources.append(
            {
                "source_id": source_id,
                "title": "Passivation study %d" % index,
                "year": 2020 + index,
                "venue": "Journal of Test",
                "doi": "10.1000/test%d" % index,
                "full_text": True,
                "url": "https://doi.org/10.1000/test%d" % index,
            }
        )
        spans.append(
            {
                "span_id": span_id,
                "source_id": source_id,
                "text": "Passivation improves humidity stability in the tested condition.",
            }
        )
        references.append(
            {
                "title": "Passivation study %d" % index,
                "authors": ["Zhang, Jenny", "Li, Wei"],
                "year": 2020 + index,
                "venue": "Journal of Test",
                "doi": "10.1000/test%d" % index,
            }
        )
    abstract = (
        "目的：评估钝化层对钙钛矿器件湿热稳定性的影响，并明确结论所依赖的证据边界。"
        "方法：检索并读取十篇全文来源，建立可定位的句级证据链；在冻结协议下采用未钝化对照、"
        "固定数据划分、配对比较与预设停止规则，避免在看到结果后修改分析口径。"
        "结果：在预注册主指标下，钝化组的稳定性高于对照组；具体数值只来自人工签署的 claim，"
        "本工作稿不重新计算实验数值。结论：现有证据支持钝化层可能延长湿热稳定性，"
        "但该结论仍需独立重复实验、更广来源与不同器件结构的验证，不能外推为普适规律。"
    )
    paper = {
        "title": "钝化层湿热稳定性研究",
        "profile": {"language": "zh", "venue_type": "zh_core_journal"},
        "fixture_mode": False,
        "slots": [{"slot_id": "result.primary", "status": "bound_claim"}],
        "draft": [
            {"section": "摘要", "text": abstract},
            {
                "section": "引言",
                "text": "界面钝化是提升湿热稳定性的关键环节[SPAN-1]。"
                "已有研究从材料与器件层面报告了稳定性变化[SPAN-2]。",
            },
            {
                "section": "相关工作",
                "text": "已有工作分别讨论了界面缺陷[SPAN-3]、疏水性[SPAN-4]与封装工艺[SPAN-5]的作用。"
                "近期研究进一步比较了不同钝化策略[SPAN-6]。"
                "更多研究覆盖了工艺窗口[SPAN-7]、长期老化[SPAN-8]、表征方法[SPAN-9]与重复性[SPAN-10]。",
            },
            {
                "section": "方法",
                "text": "研究采用预注册的对照设计、固定数据划分与预设停止规则；seeds=3，"
                "避免在看到结果后修改分析口径。",
            },
            {
                "section": "实验设计",
                "text": "基线为未钝化对照，主指标为 T80，设置重复实验与配对比较；具体参数由冻结协议给出。",
            },
            {"section": "结果", "text": "钝化组 T80 为 0.93 [SPAN-3]，对照组为 0.81 [SPAN-3]。"},
            {
                "section": "讨论",
                "text": "该结果与已有关于界面缺陷作用的报告一致[SPAN-3]。图1 给出研究流程与证据链。",
            },
            {
                "section": "结论",
                "text": "现有证据支持钝化层可能延长湿热稳定性，但结论仍需独立重复实验与更广来源验证。",
            },
        ],
    }
    literature = {
        "fixture_mode": False,
        "hits": sources,
        "spans": spans,
        "brief": {
            "source_briefs": [
                {
                    "source_id": item["source_id"],
                    "title": item["title"],
                    "year": item["year"],
                    "venue": item["venue"],
                    "full_text": True,
                }
                for item in sources
            ]
        },
    }
    bibliography = {"entries": references}
    context = {
        "claim_statements": ["T80=0.93", "control T80=0.81"],
        "claim_signed": True,
        "run_summary": {"run_id": "RUN-TEST", "status": "completed"},
        "figure_refs": ["FIG-1"],
    }
    return paper, literature, bibliography, context


class ManuscriptTest(unittest.TestCase):
    def _build(self, paper, literature, bibliography, context):
        return build_manuscript(
            paper,
            literature,
            bibliography,
            topic="钝化层 湿热稳定性 界面工程",
            language="zh",
            venue_type="zh_core_journal",
            context=context,
        )

    def test_structure_ready_without_signed_basis_is_not_submission_ready(self):
        paper, literature, bibliography, context = ready_fixture()
        context.pop("claim_signed", None)
        context.pop("run_summary", None)
        audit = self._build(paper, literature, bibliography, context)["audit"]
        self.assertEqual(audit["status"], "attention", audit)
        self.assertFalse(audit["submission_ready"])
        self.assertEqual(audit["submission_basis"], "")
        self.assertTrue(
            any("submission.basis" in item for item in audit["warnings"]),
            audit,
        )

    def test_explicit_review_basis_requires_full_texts(self):
        paper, literature, bibliography, context = ready_fixture()
        context.pop("claim_signed", None)
        context.pop("run_summary", None)
        context["submission_basis"] = "review"
        audit = self._build(paper, literature, bibliography, context)["audit"]
        self.assertEqual(audit["submission_basis"], "review")
        self.assertTrue(audit["submission_ready"], audit)

    def test_complete_manuscript_passes_deterministic_audit(self):
        bundle = self._build(*ready_fixture())
        audit = bundle["audit"]
        self.assertEqual(audit["status"], "pass", audit)
        self.assertTrue(audit["submission_ready"])
        self.assertEqual(audit["blockers"], [])
        self.assertEqual(audit["warnings"], [])
        self.assertEqual(bundle["argument_ledger"]["summary"]["needs_evidence"], 0)
        registry = bundle["claim_registry"]
        self.assertEqual(registry["coverage"]["coverage_rate"], 1.0)
        self.assertGreater(registry["coverage"]["verified_anchor_rows"], 0)
        for entry in registry["entries"]:
            for row in entry["evidence_rows"]:
                if row["status"] == "verified_anchor":
                    self.assertEqual(len(row["span_sha256"]), 64)
                    self.assertTrue(row["quote"])

    def test_chinese_venue_audit_is_attached_without_changing_status(self):
        bundle = self._build(*ready_fixture())
        audit = bundle["audit"]
        self.assertEqual(audit["status"], "pass", audit)
        self.assertTrue(audit["submission_ready"])
        self.assertIn("venue_audit", audit)
        self.assertEqual(audit["venue_audit"]["track"], "zh_journal:zh_core_journal")
        self.assertFalse(audit["venue_audit"]["submission_ready"])

    def test_english_question_words_are_not_keywords(self):
        paper, literature, bibliography, context = ready_fixture()
        bundle = build_manuscript(
            paper,
            literature,
            bibliography,
            topic="How do self-improving coding agents use archives?",
            language="en",
            venue_type="en_conference",
            context=context,
        )
        keywords = bundle["manuscript"]["keywords"]
        # A real draft rendered "How" and "use" as keywords under its abstract.
        self.assertNotIn("How", keywords)
        self.assertNotIn("use", keywords)
        self.assertIn("archives", keywords)

    def test_numbered_citations_and_gbt7714_references(self):
        bundle = self._build(*ready_fixture())
        manuscript = bundle["manuscript"]
        self.assertGreaterEqual(len(manuscript["references"]), 10)
        self.assertIn("[1]", manuscript["sections"][1]["text"])
        self.assertIn("[J]", manuscript["references"][0]["text"])
        self.assertIn("DOI:", manuscript["references"][0]["text"])
        rendered = render_manuscript_markdown(manuscript)
        self.assertIn("**关键词：**", rendered)
        self.assertIn("## 参考文献", rendered)
        self.assertIn("[1] ZHANG J", rendered)

    def test_unresolved_citation_blocks(self):
        paper, literature, bibliography, context = ready_fixture()
        paper = copy.deepcopy(paper)
        paper["draft"][1]["text"] = paper["draft"][1]["text"].replace("[SPAN-1]", "[MISSING-9]")
        bundle = self._build(paper, literature, bibliography, context)
        self.assertEqual(bundle["audit"]["status"], "blocked")
        self.assertTrue(any("citations.unresolved" in item for item in bundle["audit"]["blockers"]))
        coverage = bundle["claim_registry"]["coverage"]
        self.assertLess(coverage["coverage_rate"], 1.0)
        self.assertGreater(coverage["needs_evidence"], 0)

    def test_unregistered_quantitative_claim_blocks(self):
        paper, literature, bibliography, context = ready_fixture()
        paper = copy.deepcopy(paper)
        paper["draft"][6]["text"] += "另外，T80 提升到 0.99。"
        bundle = self._build(paper, literature, bibliography, context)
        self.assertTrue(any("claims.registry_coverage" in item for item in bundle["audit"]["blockers"]))
        self.assertGreater(bundle["claim_registry"]["coverage"]["needs_evidence"], 0)

    def test_fixture_missing_claim_and_unverified_references_block(self):
        paper, literature, bibliography, context = ready_fixture()
        paper = copy.deepcopy(paper)
        literature = copy.deepcopy(literature)
        paper["fixture_mode"] = True
        literature["fixture_mode"] = True
        paper["slots"] = [{"slot_id": "result.primary", "status": "pending_evidence"}]
        bundle = self._build(paper, literature, {"entries": []}, context)
        blockers = " ".join(bundle["audit"]["blockers"])
        self.assertIn("evidence.fixture", blockers)
        self.assertIn("results.signed_claim", blockers)
        self.assertIn("references.verified", blockers)

    def test_numeric_mismatch_and_placeholder_block(self):
        paper, literature, bibliography, context = ready_fixture()
        paper = copy.deepcopy(paper)
        paper["draft"][5]["text"] = "钝化组 T80 为 0.99 [SPAN-3]。"
        paper["draft"][3]["text"] += " 具体流程待补。"
        bundle = self._build(paper, literature, bibliography, context)
        blockers = " ".join(bundle["audit"]["blockers"])
        self.assertIn("numeric.fidelity", blockers)
        self.assertIn("placeholders", blockers)

    def test_the_papers_rounded_observed_value_is_allowed(self):
        paper, literature, bibliography, context = ready_fixture()
        paper = copy.deepcopy(paper)
        context = copy.deepcopy(context)
        context["claim_assertions"] = [{
            "metric": "accuracy",
            "comparator": ">=",
            "value": 0.9111,
            "observed": 0.9555555555555556,
            "tolerance": 0.0,
            "status": "pass",
        }]
        paper["draft"][5]["text"] = (
            "accuracy >= 0.9111 (observed=0.955556, tolerance=0.0) [SPAN-3]。"
        )
        bundle = self._build(paper, literature, bibliography, context)
        self.assertNotIn(
            "numeric.fidelity", " ".join(bundle["audit"]["blockers"])
        )

    def test_internal_working_draft_title_is_stripped(self):
        paper, literature, bibliography, context = ready_fixture()
        paper = copy.deepcopy(paper)
        paper["title"] = "工作稿：" + paper["title"]
        bundle = self._build(paper, literature, bibliography, context)
        self.assertEqual(bundle["manuscript"]["title"], "钝化层湿热稳定性研究")
        self.assertTrue(any("title.derived" in item for item in bundle["audit"]["warnings"]))

    def test_method_parameters_do_not_require_citations(self):
        paper, literature, bibliography, context = ready_fixture()
        bundle = self._build(paper, literature, bibliography, context)
        method_entries = [
            item for item in bundle["argument_ledger"]["entries"] if item["section"] == "方法"
        ]
        self.assertEqual(method_entries, [])



class ClaimRegistryMarkerTest(unittest.TestCase):
    """The same sentence must be filtered in both languages, and a hypothesis is not a claim."""

    def _registry(self, text, language="en", label="Experimental Setup"):
        from research_agent.manuscript import _claim_registry

        return _claim_registry(
            [{"label": label, "text": text}], {}, {}, {}, language
        )

    def test_english_and_chinese_meta_sentences_are_both_skipped(self):
        english = self._registry(
            "The draft fixes its evidence boundary first: abstract-only records remain clues."
        )
        chinese = self._registry(
            "本文先固定证据边界：摘要-only 记录只作为线索。", language="zh", label="方法"
        )
        self.assertEqual(english["entries"], [])
        self.assertEqual(chinese["entries"], [])

    def test_a_hypothesis_is_a_design_statement_not_an_unsupported_claim(self):
        registry = self._registry(
            "Hypothesis (draft): retention helps only when parents are sampled broadly."
        )
        self.assertEqual(registry["entries"], [])
        chinese = self._registry("研究假设（草案）：只有广泛采样时保留才有帮助。", "zh", "方法")
        self.assertEqual(chinese["entries"], [])

    def test_empty_candidate_set_reports_an_undefined_rate(self):
        registry = self._registry("本文先固定证据边界。", "zh", "方法")
        self.assertIsNone(registry["coverage"]["coverage_rate"])
        self.assertIn("undefined", registry["coverage"]["coverage_note"])


class ReferenceTitleMatchTest(unittest.TestCase):
    """The same paper must match across a diacritic difference, or its metadata silently lapses."""

    def test_titles_fold_diacritics_before_comparison(self):
        from research_agent.manuscript import _norm_title

        self.assertEqual(
            _norm_title("Darwin Gödel Machine: Open-Ended Evolution"),
            _norm_title("Darwin Godel Machine: Open-Ended Evolution"),
        )
        self.assertNotEqual(
            _norm_title("Darwin Godel Machine"), _norm_title("A Self-Improving Coding Agent")
        )

    def test_a_diacritic_variant_still_verifies_against_the_card(self):
        from research_agent.manuscript import _source_pool

        literature = {
            "brief": {
                "source_briefs": [
                    {"source_id": "ARXIV-1", "title": "Darwin Gödel Machine", "year": 2025}
                ]
            }
        }
        card = [
            {
                "title": "Darwin Godel Machine",
                "authors": ["A. Author"],
                "year": 2025,
                "venue": "arXiv",
                "doi": "10.48550/arxiv.1",
                "url": "https://doi.org/10.48550/arxiv.1",
            }
        ]
        refs, extras, _hits = _source_pool(literature, {"entries": card})
        self.assertTrue(refs["ARXIV-1"]["verified"], refs)
        self.assertEqual(refs["ARXIV-1"]["authors"], ["A. Author"])
        self.assertEqual(extras, [])

if __name__ == "__main__":
    unittest.main()

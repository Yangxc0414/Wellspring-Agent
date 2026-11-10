import unittest

from research_agent.contracts import Span
from research_agent.modules.idea import IdeaAgent, IdeaRequest, PREDICTION_SLOTS
from research_agent.specs import SpecStore


class IdeaAgentTest(unittest.TestCase):
    def setUp(self):
        self.spec = SpecStore().load("idea")
        self.agent = IdeaAgent(self.spec)

    def _spans(self):
        return [
            Span("S-1", "FX-1", "Results", "湿热条件下钝化层的稳定性结果与配对对照。", 0, 20),
            Span("S-2", "FX-1", "Results", "湿热条件下钝化层的稳定性结果需要重复测量。", 0, 20),
            Span("S-3", "FX-1", "Limitations", "该结果只在特定湿热循环边界内成立。", 0, 20),
            Span("S-4", "FX-2", "Method", "实验方法要求记录温度、湿度、样本量与停止条件。", 0, 20),
        ]

    def test_fixture_spans_are_disclosed_as_source_mode(self):
        result = self.agent.run(IdeaRequest("湿热稳定性", self._spans(), max_candidates=3))
        markers = [w for w in result.warnings if w.startswith("source_mode=")]
        self.assertEqual(len(markers), 1)
        self.assertTrue(markers[0].startswith("source_mode=fixture:"))
        self.assertIn("not research evidence", markers[0])

    def test_non_fixture_spans_do_not_inherit_fixture_disclosure(self):
        spans = [
            Span("R-1", "SRC-1", "Results", "真实来源的结果句，需要可定位证据。", 0, 20, fixture=False),
            Span("R-2", "SRC-1", "Limitations", "该结论只在给定边界内成立。", 0, 20, fixture=False),
        ]
        result = self.agent.run(IdeaRequest("真实语料", spans, max_candidates=3))
        markers = [w for w in result.warnings if w.startswith("source_mode=")]
        self.assertEqual(len(markers), 1)
        self.assertTrue(markers[0].startswith("source_mode=real:"))

    def test_no_spans_declares_no_locatable_evidence(self):
        result = self.agent.run(IdeaRequest("无证据", [], max_candidates=3))
        self.assertTrue(any(w.startswith("source_mode=none:") for w in result.warnings))

    def test_candidates_are_clustered_with_evidence_and_falsification(self):
        result = self.agent.run(IdeaRequest("湿热稳定性", self._spans(), max_candidates=3))
        self.assertEqual(result.status, "candidates_need_human")
        self.assertLessEqual(len(result.candidates), 3)
        self.assertGreaterEqual(len(result.candidates), 2)
        self.assertTrue(all(card.falsification for card in result.candidates))
        self.assertTrue(all(card.evidence_refs for card in result.candidates))
        self.assertTrue(all(card.novelty_status == "unverified" for card in result.candidates))
        self.assertTrue(any(card.evidence_count >= 2 for card in result.candidates))
        self.assertIsNotNone(result.brief)
        self.assertEqual(result.brief.candidate_count, len(result.candidates))
        self.assertIn("novelty_unverified", result.brief.gaps)
        self.assertTrue(result.brief.summary)
        self.assertIn("候选", result.brief.summary)
        self.assertTrue(
            all(
                card.prior_art_scope in ("s1_corpus", "none")
                for card in result.candidates
            )
        )
        self.assertTrue(all(card.prior_art_delta for card in result.candidates))
        self.assertTrue(all(card.kill_criteria for card in result.candidates))
        self.assertTrue(any(card.prior_art_refs for card in result.candidates))
        self.assertTrue(any(card.contrast_refs for card in result.candidates))
        self.assertTrue(
            any("另一独立来源" in card.hypothesis for card in result.candidates)
        )
        self.assertIn("prior-art", result.brief.summary)
        self.assertIsNotNone(result.shortlist)
        self.assertEqual(result.shortlist.selection, "human_g1")
        self.assertEqual(
            len(result.shortlist.ranked), len(result.candidates)
        )
        self.assertIn("G1", result.shortlist.boundary)

    def test_shortlist_prioritizes_live_prior_art_without_auto_selection(self):
        calls = {"count": 0}

        def searcher(_query, _limit):
            calls["count"] += 1
            if calls["count"] == 1:
                return [
                    {
                        "span_id": "P-1",
                        "source_id": "SRC-9",
                        "text": "Prior work on humid stability.",
                        "title": "Prior humidity study",
                        "year": 2020,
                        "venue": "Venue",
                        "full_text": True,
                    }
                ]
            return []

        result = self.agent.run(
            IdeaRequest(
                "湿热稳定性",
                self._spans(),
                max_candidates=2,
                prior_art_searcher=searcher,
            )
        )
        self.assertIsNotNone(result.shortlist)
        self.assertEqual(result.shortlist.selection, "human_g1")
        self.assertEqual(
            result.shortlist.ranked[0]["prior_art_scope"], "live_search"
        )
        self.assertTrue(
            all("recommended_idea_id" not in item for item in result.shortlist.ranked)
        )
        self.assertEqual(
            len(result.shortlist.ranked), len(result.candidates)
        )

    def test_live_prior_art_search_annotates_candidate(self):
        def searcher(query, limit):
            self.assertIn("湿热", query)
            self.assertEqual(limit, 3)
            return [
                {
                    "span_id": "P-1",
                    "source_id": "SRC-9",
                    "text": "Prior work on humid stability.",
                    "title": "Prior humidity study",
                    "year": 2020,
                    "venue": "Venue",
                    "full_text": True,
                    "url": "https://example.org/prior",
                }
            ]

        result = self.agent.run(
            IdeaRequest(
                "湿热稳定性",
                self._spans(),
                max_candidates=2,
                prior_art_searcher=searcher,
            )
        )
        card = result.candidates[0]
        self.assertEqual(card.prior_art_scope, "live_search")
        self.assertEqual(card.prior_art_refs, ["P-1"])
        self.assertIn("Prior humidity study", card.prior_art_delta)
        self.assertTrue(result.prior_art_report)
        self.assertEqual(result.prior_art_report[0]["scope"], "live_search")
        self.assertEqual(
            result.prior_art_report[0]["hits"][0]["span_id"], "P-1"
        )

    def test_live_prior_art_filters_candidate_source(self):
        def searcher(_query, _limit):
            return [
                {
                    "span_id": "S-1",
                    "source_id": "FX-1",
                    "text": "Same-source span is not independent prior art.",
                    "title": "Same source",
                    "year": 2025,
                    "venue": "Fixture",
                    "full_text": True,
                }
            ]

        result = self.agent.run(
            IdeaRequest(
                "湿热稳定性",
                self._spans(),
                max_candidates=2,
                prior_art_searcher=searcher,
            )
        )
        card = result.candidates[0]
        self.assertNotEqual(card.prior_art_scope, "live_search")
        self.assertIn(card.prior_art_scope, ("s1_corpus", "none"))
        for hit in card.prior_art_refs:
            self.assertNotIn(hit, card.evidence_refs)

    def test_live_prior_art_failure_falls_back(self):
        def searcher(_query, _limit):
            raise RuntimeError("offline")

        result = self.agent.run(
            IdeaRequest(
                "湿热稳定性",
                self._spans(),
                max_candidates=2,
                prior_art_searcher=searcher,
            )
        )
        self.assertIn(
            result.candidates[0].prior_art_scope, ("s1_corpus", "none")
        )
        self.assertTrue(
            any(
                "prior_art_search_failed" in warning
                for warning in result.warnings
            )
        )

    def test_rule_lens_follows_section(self):
        result = self.agent.run(
            IdeaRequest("湿热稳定性", self._spans(), max_candidates=3)
        )
        lenses = {card.lens for card in result.candidates}
        self.assertIn("measurement", lenses)
        self.assertIn("boundary", lenses)
        self.assertIn("mechanism", lenses)

    def test_single_span_candidate_marks_no_prior_art(self):
        spans = [
            Span(
                "S-ONLY",
                "FX-1",
                "Results",
                "A single claim about humid stability.",
                0,
                10,
            )
        ]
        result = self.agent.run(IdeaRequest("topic", spans, max_candidates=1))
        card = result.candidates[0]
        self.assertEqual(card.prior_art_scope, "none")
        self.assertEqual(card.prior_art_refs, [])
        self.assertEqual(card.contrast_refs, [])
        self.assertIn("no_prior_art", result.brief.gaps)

    def test_no_spans_is_needs_evidence(self):
        result = self.agent.run(IdeaRequest("空主题", [], max_candidates=2))
        self.assertEqual(result.status, "needs_evidence")
        self.assertEqual(result.candidates, [])
        self.assertIsNotNone(result.brief)
        self.assertEqual(result.brief.candidate_count, 0)
        self.assertIn("no_span", result.brief.gaps)

    def test_candidate_limit_is_enforced(self):
        result = self.agent.run(IdeaRequest("湿热稳定性", self._spans(), max_candidates=1))
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.brief.candidate_count, 1)

    def test_model_candidate_must_resolve_to_input_spans(self):
        def proposer(payload):
            self.assertIn("evidence", payload)
            return [{
                "title": "边界候选",
                "hypothesis": "该效应在湿热边界外应出现可测退化。",
                "falsification": "边界外没有观察到退化。",
                "lens": "boundary",
                "evidence_refs": ["S-3"],
            }, {
                "title": "Unknown evidence",
                "hypothesis": "This references a span that was not supplied.",
                "falsification": "This candidate must be rejected.",
                "lens": "mechanism",
                "evidence_refs": ["NOT-IN-INPUT"],
            }]

        result = IdeaAgent(self.spec, proposer=proposer).run(
            IdeaRequest("湿热稳定性", self._spans(), max_candidates=3)
        )
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].title, "边界候选")
        self.assertEqual(result.candidates[0].evidence_refs, ["S-3"])
        self.assertEqual(result.candidates[0].novelty_status, "unverified")
        self.assertIn(
            result.candidates[0].prior_art_scope, ("s1_corpus", "none")
        )
        for ref in result.candidates[0].prior_art_refs:
            self.assertNotIn(ref, result.candidates[0].evidence_refs)
        self.assertTrue(any("model_proposed_candidates" in item for item in result.warnings))
        self.assertTrue(any("unknown evidence_refs" in item for item in result.warnings))

    def test_invalid_model_candidates_fall_back_to_rules(self):
        def proposer(_payload):
            return [{"title": "x", "hypothesis": "y", "falsification": "z", "evidence_refs": ["S-1"]}]

        result = IdeaAgent(self.spec, proposer=proposer).run(
            IdeaRequest("湿热稳定性", self._spans(), max_candidates=2)
        )
        self.assertGreaterEqual(len(result.candidates), 1)
        self.assertTrue(all(card.falsification for card in result.candidates))
        self.assertTrue(any("model candidates rejected" in item for item in result.warnings))



class EvidenceSpreadTest(unittest.TestCase):
    """A prompt that samples one paper cannot produce a multi-source candidate."""

    def _spans(self, sources=3, each=10):
        from research_agent.contracts import Span

        return [
            Span(
                span_id="S%d-%02d" % (source, index),
                source_id="SRC-%d" % source,
                section="1",
                text="text",
                start=index,
                end=index + 1,
            )
            for source in range(1, sources + 1)
            for index in range(each)
        ]

    def test_round_robin_reaches_every_source_before_repeating(self):
        from research_agent.modules.idea import _spread_spans

        picked = _spread_spans(self._spans(), 9)
        self.assertEqual(
            [span.source_id for span in picked],
            ["SRC-1", "SRC-2", "SRC-3"] * 3,
        )

    def test_a_prefix_would_have_stayed_in_one_source(self):
        from research_agent.modules.idea import _spread_spans

        spans = self._spans()
        self.assertEqual(len({span.source_id for span in spans[:9]}), 1)
        self.assertEqual(len({span.source_id for span in _spread_spans(spans, 9)}), 3)

    def test_the_limit_is_respected(self):
        from research_agent.modules.idea import _spread_spans

        self.assertEqual(len(_spread_spans(self._spans(), 5)), 5)

    def test_a_raw_answer_without_ids_can_be_reused(self):
        import json
        import tempfile
        from pathlib import Path

        from research_agent.modules.idea import load_idea_result

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answer.json"
            path.write_text(
                json.dumps(
                    {
                        "candidates": [
                            {"title": "T1", "hypothesis": "H1", "falsification": "F1"},
                            {"title": "T2", "hypothesis": "H2", "falsification": "F2"},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            result = load_idea_result(path, run_id="X")
            self.assertEqual([card.idea_id for card in result.candidates], ["IDEA-01", "IDEA-02"])
            self.assertEqual(result.status, "candidates_need_human")

    def test_a_candidate_with_no_content_is_rejected_not_guessed(self):
        import json
        import tempfile
        from pathlib import Path

        from research_agent.modules.idea import load_idea_result

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "answer.json"
            path.write_text(json.dumps({"candidates": [{"lens": "mechanism"}]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_idea_result(path)

class CrossSourceCandidateTest(unittest.TestCase):
    """The deterministic clusterer groups same-source spans, so a cluster alone
    can never ground a cross-source idea. The contrast span is already chosen
    from another source; v0.21.0 counts it as evidence too.
    """

    def setUp(self):
        self.spec = SpecStore().load("idea")
        self.agent = IdeaAgent(self.spec)

    @staticmethod
    def _multi_source_spans():
        # One same-source cluster (Results) plus one span in a different section
        # from a second source. The clusterer keeps the first source together and
        # cannot merge across sections, so the contrast span must be picked from
        # the other source and counted as evidence.
        return [
            Span("M-1", "SRC-A", "Results", "湿热条件下钝化层稳定性结果的重复测量。", 0, 20, fixture=False),
            Span("M-2", "SRC-A", "Results", "湿热循环中界面钝化样本量必须记录。", 0, 20, fixture=False),
            Span("M-3", "SRC-A", "Results", "湿热稳定性边界只在给定循环内成立。", 0, 20, fixture=False),
            Span("M-4", "SRC-B", "Limitations", "湿热场景的局限与其他来源的对照差异。", 0, 20, fixture=False),
        ]

    def test_rule_candidates_cite_two_independent_sources(self):
        spans = self._multi_source_spans()
        result = self.agent.run(IdeaRequest("湿热稳定性", spans, max_candidates=3))
        ids = {span.span_id for span in spans}
        self.assertEqual(result.spec_version, self.spec.version)
        self.assertGreater(len(result.candidates), 0)
        for card in result.candidates:
            self.assertGreaterEqual(card.source_count, 2)
            self.assertLessEqual(len(card.evidence_refs), 4)
            self.assertTrue(set(card.evidence_refs) <= ids)
            self.assertTrue(card.contrast_refs)
            self.assertIn(card.contrast_refs[0], card.evidence_refs)
        self.assertEqual(
            result.brief.multi_source_candidates, len(result.candidates)
        )
        self.assertNotIn("no_multi_source_candidate", result.brief.gaps)
        self.assertIn("novelty_unverified", result.brief.gaps)

    def test_candidate_breadth_is_disclosed_without_claiming_quality(self):
        result = self.agent.run(
            IdeaRequest("湿热稳定性", self._multi_source_spans(), max_candidates=3)
        )
        markers = [w for w in result.warnings if w.startswith("candidate_breadth=")]
        self.assertEqual(len(markers), 1)
        self.assertIn("input_sources:2", markers[0])
        self.assertIn("no novelty proof", markers[0])
        self.assertIn("G1 stays a human signature", markers[0])
        self.assertNotIn("cross_source_candidates:0", markers[0])

    def test_single_source_input_keeps_the_original_behaviour(self):
        spans = [
            Span("S-%d" % i, "ONLY", "Results", "湿热条件下的稳定性结果。", 0, 20)
            for i in range(1, 5)
        ]
        result = self.agent.run(IdeaRequest("湿热稳定性", spans, max_candidates=3))
        self.assertTrue(all(card.source_count == 1 for card in result.candidates))
        self.assertIn("single_source", result.brief.gaps)
        marker = [w for w in result.warnings if w.startswith("candidate_breadth=")][0]
        self.assertIn("cross_source_candidates:0", marker)


class GapRelationTest(unittest.TestCase):
    """L0: a candidate is bound to a gap only when its evidence resolves there.

    Offline S1b themes carry empty agreement/tension and mixed stances, so the
    relation type must never claim semantic synthesis.
    """

    def setUp(self):
        self.spec = SpecStore().load("idea")
        self.agent = IdeaAgent(self.spec)

    @staticmethod
    def _spans():
        return [
            Span("G-1", "SRC-A", "Results", "湿热条件下钝化层稳定性结果的重复测量。", 0, 20, fixture=False),
            Span("G-2", "SRC-A", "Results", "湿热循环中界面钝化样本量必须记录。", 0, 20, fixture=False),
            Span("G-3", "SRC-A", "Results", "湿热稳定性边界只在给定循环内成立。", 0, 20, fixture=False),
            Span("G-4", "SRC-B", "Limitations", "湿热场景的局限与其他来源的对照差异。", 0, 20, fixture=False),
        ]

    @staticmethod
    def _gap_pack(evidence=("G-1", "G-4"), tension=""):
        return {
            "gaps": [],
            "brief_gaps": ["source_cap_reached"],
            "facets": [],
            "themes": [
                {
                    "theme_id": "TH-01",
                    "source_count": 2,
                    "stances": [
                        {"source_id": "SRC-A", "evidence": evidence[0]},
                        {"source_id": "SRC-B", "evidence": evidence[1]},
                    ],
                    "agreement": "",
                    "tension": tension,
                }
            ],
        }

    def test_candidate_binds_to_theme_only_when_evidence_resolves(self):
        result = self.agent.run(
            IdeaRequest("湿热稳定性", self._spans(), max_candidates=3, gap_pack=self._gap_pack())
        )
        self.assertGreater(len(result.candidates), 0)
        self.assertTrue(
            any(card.gap_ref == "theme:TH-01" for card in result.candidates)
        )
        marker = [w for w in result.warnings if w.startswith("synthesis_breadth=")][0]
        self.assertIn("gap_pack:provided", marker)
        self.assertIn("themes:1", marker)
        self.assertNotIn("bound_candidates:0/", marker)
        self.assertIn("no_scientific_gap_in_s1", result.brief.gaps)

    def test_offline_relation_never_claims_tension_or_agreement(self):
        # Even if an upstream theme carried a tension string, the deterministic
        # path has not established it and must not label the candidate as such.
        pack = self._gap_pack(tension="A contradicts B")
        result = self.agent.run(
            IdeaRequest("湿热稳定性", self._spans(), max_candidates=3, gap_pack=pack)
        )
        allowed = {"single_source", "contrast", "theme_co_occurrence", "unclassified"}
        for card in result.candidates:
            self.assertIn(card.relation_type, allowed)
            self.assertNotIn("tension", card.relation_type)
            self.assertNotIn("agreement", card.relation_type)
        marker = [w for w in result.warnings if w.startswith("synthesis_breadth=")][0]
        self.assertIn("agreement/tension not established", marker)

    def test_gap_pack_absent_is_backward_compatible(self):
        result = self.agent.run(IdeaRequest("湿热稳定性", self._spans(), max_candidates=3))
        self.assertEqual(result.status, "candidates_need_human")
        self.assertLessEqual(len(result.candidates), 3)
        self.assertTrue(all(card.gap_ref == "none" for card in result.candidates))
        self.assertIn("gap_pack_absent", result.brief.gaps)
        marker = [w for w in result.warnings if w.startswith("synthesis_breadth=")][0]
        self.assertIn("gap_pack:absent", marker)

    def test_unresolvable_theme_evidence_is_unbound_not_fabricated(self):
        pack = self._gap_pack(evidence=("NOT-A-SPAN", "ALSO-MISSING"))
        result = self.agent.run(
            IdeaRequest("湿热稳定性", self._spans(), max_candidates=3, gap_pack=pack)
        )
        self.assertTrue(all(card.gap_ref == "unbound" for card in result.candidates))
        self.assertIn("no_gap_grounded", result.brief.gaps)


class IdeaStructureTest(unittest.TestCase):
    """0.23.0: use more of the corpus, prefer real sentences, and disclose
    that template frames are not research hypotheses.
    """

    def setUp(self):
        self.spec = SpecStore().load("idea")
        self.agent = IdeaAgent(self.spec)

    @staticmethod
    def _many_sources():
        rows = []
        for index, source in enumerate(("S-A", "S-B", "S-C", "S-D", "S-E"), 1):
            section = "Sec-%d" % index
            rows.append(
                Span("Q-%d-1" % index, source, section,
                     "湿热条件下界面钝化的稳定性结果与对照差异需要重复测量。", 0, 20, fixture=False)
            )
            rows.append(
                Span("Q-%d-2" % index, source, section,
                     "该湿热结论只在特定循环边界内成立，需进一步验证。", 0, 20, fixture=False)
            )
        return rows

    def test_contrast_evidence_comes_from_distinct_sources(self):
        spans = self._many_sources()
        by_id = {span.span_id: span for span in spans}
        result = self.agent.run(IdeaRequest("湿热稳定性", spans, max_candidates=3))
        sources = {
            by_id[card.contrast_refs[0]].source_id
            for card in result.candidates
            if card.contrast_refs
        }
        self.assertGreaterEqual(len(sources), 2)
        marker = [w for w in result.warnings if w.startswith("idea_structure=")][0]
        self.assertIn("distinct_contrast_sources:%d" % len(sources), marker)
        self.assertIn("not a research hypothesis", marker)
        self.assertIn("needs_metric:", marker)

    def test_title_prefers_a_sentence_over_a_paper_title(self):
        spans = [
            Span("T-1", "S-A", "Results", "A New Benchmark for Agent Reliability", 0, 20, fixture=False),
            Span("T-2", "S-A", "Results", "湿热条件下界面钝化层的稳定性结果需要重复测量。", 0, 20, fixture=False),
            Span("T-3", "S-B", "Limitations", "该结论只在特定湿热循环边界内成立。", 0, 20, fixture=False),
        ]
        result = self.agent.run(IdeaRequest("湿热稳定性", spans, max_candidates=2))
        self.assertGreater(len(result.candidates), 0)
        self.assertFalse(
            any("A New Benchmark for Agent Reliability" in card.title for card in result.candidates)
        )

    def test_structure_receipt_counts_template_repetition_honestly(self):
        result = self.agent.run(
            IdeaRequest("湿热稳定性", self._many_sources(), max_candidates=3)
        )
        marker = [w for w in result.warnings if w.startswith("idea_structure=")][0]
        self.assertIn(
            "unique_falsifications:%d/%d"
            % (len({c.falsification for c in result.candidates}), len(result.candidates)),
            marker,
        )
        self.assertIn("no variable, expected direction or preregistered metric", marker)


class PredictionContractTest(unittest.TestCase):
    """0.24.0: the contract keeps a structured prediction and classifies it
    purely, without inventing variables for the deterministic path.
    """

    def setUp(self):
        self.spec = SpecStore().load("idea")
        self.spans = [
            Span("X-1", "S-A", "Results", "湿热条件下钝化层稳定性结果与对照差异需要重复测量。", 0, 20, fixture=False),
            Span("X-2", "S-B", "Limitations", "该结论只在特定湿热循环边界内成立。", 0, 20, fixture=False),
        ]
        self.base = {
            "title": "Memory increases the primary metric",
            "hypothesis": "自变量 memory 开启应使主指标上升，在 gate=off 条件下。",
            "falsification": "配对区间跨零或方向反转则假设不成立，需重复种子验证。",
            "lens": "mechanism",
            "evidence_refs": ["X-1", "X-2"],
        }
        self.full = dict(
            self.base,
            variable="memory", direction="increase", condition="gate=off",
            profile="search_factorial", dataset="iris",
            metric="improvement_per_evaluation",
            controls={"memory": [False, True], "gate": [False, True]},
            seeds=[17, 18, 19],
            stopping_rule="paired CI95 crossing zero => undecidable",
            criterion="CI95 must not cross zero",
        )

    def _run(self, payload=None):
        proposer = (lambda _: [payload]) if payload is not None else None
        return IdeaAgent(self.spec, proposer=proposer).run(
            IdeaRequest("湿热稳定性", self.spans, max_candidates=2)
        )

    def test_rule_path_never_invents_a_prediction(self):
        result = self._run()
        self.assertGreater(len(result.candidates), 0)
        for card in result.candidates:
            self.assertIsNone(card.prediction)
            self.assertEqual(card.prediction_status, "not_testable_here")
            self.assertEqual(card.open_slots, list(PREDICTION_SLOTS))
        self.assertFalse(
            any("dataset" in card.title or "metric" in card.hypothesis for card in result.candidates)
        )

    def test_model_supplied_prediction_is_kept_and_classified_testable(self):
        result = self._run(self.full)
        card = result.candidates[0]
        self.assertEqual(card.prediction_status, "testable")
        self.assertEqual(set(card.prediction), set(PREDICTION_SLOTS))
        self.assertEqual(card.open_slots, [])
        self.assertEqual(card.prediction["profile"], "search_factorial")
        marker = [w for w in result.warnings if w.startswith("idea_structure=")][0]
        self.assertIn("prediction_status:testable:1", marker)

    def test_out_of_profile_prediction_is_cannot_test(self):
        outside = dict(self.full, dataset="agent reliability benchmark", metric="judge alignment")
        card = self._run(outside).candidates[0]
        self.assertEqual(card.prediction_status, "cannot_test")
        self.assertEqual(len(card.prediction), len(PREDICTION_SLOTS))
        self.assertEqual(card.open_slots, [])

    def test_partial_prediction_lists_the_missing_slots(self):
        partial = dict(self.base, variable="memory", direction="increase")
        card = self._run(partial).candidates[0]
        self.assertEqual(card.prediction_status, "cannot_test")
        self.assertEqual(len(card.open_slots), len(PREDICTION_SLOTS) - 2)
        self.assertIn("dataset", card.open_slots)

    def test_proposer_without_slots_stays_backward_compatible(self):
        result = self._run(self.base)
        self.assertEqual(result.status, "candidates_need_human")
        self.assertTrue(
            any("model_proposed_candidates" in w for w in result.warnings)
        )
        self.assertEqual(result.candidates[0].prediction_status, "not_testable_here")


if __name__ == "__main__":
    unittest.main()

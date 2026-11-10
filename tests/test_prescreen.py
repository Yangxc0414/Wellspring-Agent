import json
import unittest

from research_agent.prescreen import (
    REASON_EXCLUDED_TERM,
    REASON_MISSING_TITLE,
    REASON_NO_QUERY_TERM,
    prescreen,
    query_terms,
    rank_candidates,
    stage1_filter,
)

CANDIDATES = [
    {"paper_id": "2401.00001", "title": "Agent reliability evaluation",
     "sources": ["arxiv", "hf_daily"], "pdf_url": "https://arxiv.org/pdf/2401.00001",
     "clue_only": True, "span_eligible": False},
    {"paper_id": "2401.00002", "title": "A survey of cooking recipes",
     "sources": ["hf_daily"], "pdf_url": "", "clue_only": True},
    {"paper_id": "2401.00003", "title": "Benchmark study",
     "sources": ["hf_trending"], "pdf_url": "https://arxiv.org/pdf/2401.00003",
     "clue_only": True},
    {"paper_id": "", "title": "   ", "sources": []},
]
ABSTRACTS = {
    "2401.00003": "We measure reliability of LLM agents on public benchmarks.",
}


class QueryTermsTest(unittest.TestCase):
    def test_mixed_language_query_splits_into_stable_terms(self):
        self.assertEqual(query_terms("agent reliability"), ["agent", "reliability"])
        self.assertEqual(query_terms("钙钛矿 界面 钝化"), ["钙钛矿", "界面", "钝化"])
        self.assertEqual(query_terms(""), [])


class Stage1Test(unittest.TestCase):
    def test_irrelevant_candidates_are_rejected_with_checkable_reasons(self):
        kept, rejected, _ = stage1_filter(CANDIDATES, query="agent reliability")
        reasons = {row["paper_id"]: row["reason"] for row in rejected}
        self.assertEqual(reasons.get("2401.00002"), REASON_NO_QUERY_TERM)
        self.assertEqual(reasons.get(""), REASON_MISSING_TITLE)
        self.assertEqual([row["paper_id"] for row in kept], ["2401.00001"])

    def test_an_abstract_can_rescue_a_title_with_no_query_term(self):
        kept, _, used = stage1_filter(
            CANDIDATES, query="agent reliability", abstracts=ABSTRACTS
        )
        self.assertEqual(used, 1)
        rescued = next(row for row in kept if row["paper_id"] == "2401.00003")
        self.assertEqual(rescued["title_hits"], 0)
        self.assertGreater(rescued["abstract_hits"], 0)
        self.assertEqual(rescued["matched_terms"], ["agent", "reliability"])

    def test_the_abstract_text_is_never_echoed_or_persisted(self):
        report = prescreen(CANDIDATES, query="agent reliability", abstracts=ABSTRACTS)
        payload = json.dumps(report.to_dict())
        self.assertNotIn("We measure reliability", payload)
        for row in report.kept:
            for forbidden in ("abstract", "summary", "full_text", "spans", "text"):
                self.assertNotIn(forbidden, row)

    def test_every_rejection_names_its_reason(self):
        report = prescreen(
            CANDIDATES, query="agent reliability",
            exclude_terms=["recipe"], abstracts=ABSTRACTS,
        )
        self.assertEqual(report.by_reason[REASON_EXCLUDED_TERM], 1)
        self.assertEqual(report.by_reason[REASON_MISSING_TITLE], 1)
        for row in report.rejected:
            self.assertTrue(row["reason"])
            self.assertIsInstance(row["matched_terms"], list)

    def test_min_hits_is_a_real_threshold(self):
        single = [{"paper_id": "X", "title": "Agent systems", "sources": []}]
        self.assertEqual(len(stage1_filter(single, query="agent reliability", min_hits=1)[0]), 1)
        self.assertEqual(len(stage1_filter(single, query="agent reliability", min_hits=2)[0]), 0)

    def test_chinese_query_matches_chinese_title(self):
        rows = [
            {"paper_id": "CN-1", "title": "钙钛矿界面钝化研究", "sources": []},
            {"paper_id": "CN-2", "title": "股票市场预测", "sources": []},
        ]
        kept, rejected, _ = stage1_filter(rows, query="钙钛矿 界面 钝化", min_hits=2)
        self.assertEqual([row["paper_id"] for row in kept], ["CN-1"])
        self.assertEqual(rejected[0]["reason"], REASON_NO_QUERY_TERM)

    def test_empty_input_is_not_an_error(self):
        report = prescreen([], query="agent")
        self.assertEqual((report.input_count, report.kept_count, report.compression), (0, 0, 0.0))


class RankingTest(unittest.TestCase):
    def test_ranking_never_changes_the_kept_set(self):
        kept, _, _ = stage1_filter(
            CANDIDATES, query="agent reliability", abstracts=ABSTRACTS
        )
        before = {row["paper_id"] for row in kept}
        ranked = rank_candidates(kept)
        self.assertEqual({row["paper_id"] for row in ranked}, before)
        self.assertEqual(len(ranked), len(kept))
        self.assertEqual([row["rank_score"] for row in ranked],
                         sorted([row["rank_score"] for row in ranked], reverse=True))

    def test_the_score_is_explainable_and_marked_as_ranking_only(self):
        report = prescreen(CANDIDATES, query="agent reliability", abstracts=ABSTRACTS)
        for row in report.kept:
            self.assertEqual(row["rank_score"], sum(row["rank_signals"].values()))
            self.assertTrue(row["ranking_signal_only"])
            self.assertTrue(row["clue_only"])
            self.assertFalse(row["span_eligible"])

    def test_the_same_input_is_deterministic(self):
        first = prescreen(CANDIDATES, query="agent reliability", abstracts=ABSTRACTS).to_dict()
        second = prescreen(CANDIDATES, query="agent reliability", abstracts=ABSTRACTS).to_dict()
        self.assertEqual(first, second)


class ReportTest(unittest.TestCase):
    def test_report_carries_compression_boundary_and_next_commands(self):
        report = prescreen(CANDIDATES, query="agent reliability", abstracts=ABSTRACTS).to_dict()
        self.assertEqual(report["input_count"], 4)
        self.assertEqual(report["compression"], 0.5)
        self.assertEqual(report["abstracts_used_in_memory_only"], 1)
        self.assertIn("ranking_signal_only=true", report["boundary"])
        self.assertIn("not evidence eligible", report["boundary"])
        self.assertTrue(any("--source local" in cmd for cmd in report["next_commands"]))
        json.dumps(report)

    def test_a_report_without_query_still_advises_local_parsing(self):
        report = prescreen(CANDIDATES, query="")
        commands = report.to_dict()["next_commands"]
        self.assertEqual(len(commands), 1)
        self.assertIn("--source local", commands[0])


if __name__ == "__main__":
    unittest.main()

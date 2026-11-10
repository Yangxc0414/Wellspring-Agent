import json
import unittest
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

from research_agent.adapters import FixtureRetriever, SimpleParser
from research_agent.adapters.glm_model import GLMModel, glm_query_planner
from research_agent.adapters.openalex_retriever import OpenAlexRetriever
from research_agent.contracts import SourceHit
from research_agent.modules.literature import LiteratureAgent, LiteratureError, LiteratureRequest
from research_agent.specs import SpecStore


class OneSourcePerQueryRetriever:
    fixture_mode = True

    def __init__(self):
        self.by_query = {}

    def search(self, query, limit):
        if query not in self.by_query:
            self.by_query[query] = "S%02d" % (len(self.by_query) + 1)
        source_id = self.by_query[query]
        return [
            SourceHit(
                source_id=source_id,
                title="Source " + source_id,
                year=2025,
                venue="Fixture",
                doi=None,
                abstract="abstract",
                full_text=True,
                license="CC-BY-4.0",
                fixture=True,
            )
        ][:limit]

    def full_text(self, source_id):
        return {"sections": [{"name": "Results", "text": "This result sentence is long enough for a span."}]}


class FollowupRetriever:
    fixture_mode = True

    def __init__(self):
        self.calls = 0

    def search(self, query, limit):
        self.calls += 1
        if self.calls <= 6:
            if query == "perovskite stability":
                return [
                    SourceHit(
                        source_id="S-INITIAL",
                        title="Initial source",
                        year=2025,
                        venue="Fixture",
                        doi=None,
                        abstract="abstract",
                        full_text=True,
                        license="CC-BY-4.0",
                        fixture=True,
                    )
                ][:limit]
            return []
        return [
            SourceHit(
                source_id="S-FOLLOW-%02d" % self.calls,
                title="Followup source",
                year=2025,
                venue="Fixture",
                doi=None,
                abstract="abstract",
                full_text=True,
                license="CC-BY-4.0",
                fixture=True,
            )
        ][:limit]

    def full_text(self, source_id):
        return {
            "sections": [
                {
                    "name": "Results",
                    "text": "This followup sentence is long enough for a span.",
                }
            ]
        }


class StaticTransport:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return json.dumps(self.payload).encode("utf-8")


class LiteratureAgentTest(unittest.TestCase):
    def setUp(self):
        self.store = SpecStore()
        self.spec = self.store.load("literature")
        self.agent = LiteratureAgent(self.spec, FixtureRetriever(), SimpleParser())

    def test_fixture_run_produces_spans_not_claims(self):
        result = self.agent.run(
            LiteratureRequest(question="钙钛矿 界面 钝化 稳定性", max_sources=4, run_id="RUN-TEST-1")
        )
        data = result.to_dict()
        self.assertEqual(data["run_id"], "RUN-TEST-1")
        self.assertEqual(data["spec_version"], self.spec.version)
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["fixture_mode"])
        self.assertGreater(len(data["spans"]), 0)
        self.assertGreater(len(data["hits"]), 0)
        self.assertNotIn("claim_drafts", data)
        self.assertTrue(any("fixture_mode" in warning for warning in data["warnings"]))
        self.assertTrue(any("not claims" in warning for warning in data["warnings"]))
        self.assertTrue(any(gap["code"] == "full_text_unavailable" for gap in data["coverage"]["gaps"]))
        self.assertFalse(any(span["source_id"] == "FX-003" for span in data["spans"]))

    def test_abstract_only_never_becomes_evidence(self):
        result = self.agent.run(LiteratureRequest(question="review", max_sources=4))
        data = result.to_dict()
        self.assertEqual(data["status"], "insufficient_evidence")
        self.assertEqual(data["spans"], [])
        self.assertGreaterEqual(len(data["hits"]), 1)
        self.assertTrue(any(gap["code"] == "full_text_unavailable" for gap in data["coverage"]["gaps"]))

    def test_empty_question_is_insufficient(self):
        result = self.agent.run(LiteratureRequest(question="   "))
        data = result.to_dict()
        self.assertEqual(data["status"], "insufficient_evidence")
        self.assertEqual(data["query_plan"]["subqueries"], [])
        self.assertTrue(any(gap["code"] == "no_question" for gap in data["coverage"]["gaps"]))

    def test_revoked_spec_is_refused(self):
        revoked = replace(self.spec, status="revoked")
        agent = LiteratureAgent(revoked, FixtureRetriever(), SimpleParser())
        with self.assertRaises(LiteratureError):
            agent.run(LiteratureRequest(question="perovskite"))

    def test_coverage_brief_reports_facets_sources_and_summary(self):
        result = self.agent.run(
            LiteratureRequest(
                question="钙钛矿 界面 钝化 稳定性", max_sources=4, run_id="RUN-BRIEF", coverage_plan=True
            )
        )
        data = result.to_dict()
        brief = data["brief"]
        self.assertIsNotNone(brief)
        self.assertEqual(
            [facet["facet"] for facet in brief["facets"]],
            ["core", "survey", "method", "evaluation", "limitation", "recent"],
        )
        self.assertTrue(brief["source_briefs"])
        self.assertTrue(brief["sections"])
        self.assertTrue(brief["summary"])
        self.assertIn("共 ", brief["summary"])
        self.assertIn("摘要线索", brief["summary"])
        self.assertIn(brief["saturation"], {"saturated", "partial", "insufficient"})
        self.assertTrue(any(item["span_count"] > 0 for item in brief["source_briefs"]))
        self.assertTrue(any("coverage=" in warning for warning in data["warnings"]))
        self.assertTrue(
            "thin_domain_coverage" in [gap["code"] for gap in data["coverage"]["gaps"]]
            or brief["saturation"] == "saturated"
        )

    def test_small_budget_exposes_coverage_cap_gap(self):
        result = self.agent.run(
            LiteratureRequest(
                question="钙钛矿 界面 钝化 稳定性", max_sources=1, run_id="RUN-CAP", coverage_plan=True
            )
        )
        data = result.to_dict()
        codes = [gap["code"] for gap in data["coverage"]["gaps"]]
        self.assertIn("coverage_cap_reached", codes)
        self.assertTrue(any(gap.startswith("source_cap_reached") for gap in data["brief"]["gaps"]))
        self.assertLess(len(data["hits"]), data["brief"]["target_sources"])

    def test_followup_plan_fills_gaps_within_remaining_budget(self):
        agent = LiteratureAgent(
            self.spec, FollowupRetriever(), SimpleParser()
        )
        result = agent.run(
            LiteratureRequest(
                question="perovskite stability",
                max_sources=6,
                coverage_plan=True,
                followup_plan=True,
            )
        )
        filters = result.query_plan.filters
        self.assertTrue(filters["followup_plan"])
        self.assertTrue(filters["followup_queries"])
        self.assertGreater(filters["followup_sources_added"], 0)
        self.assertGreater(filters["followup_spans_added"], 0)
        self.assertLessEqual(len(result.hits), 6)
        self.assertEqual(
            len({hit.source_id for hit in result.hits}),
            len(result.hits),
        )
        self.assertTrue(
            any("followup_plan: added" in warning for warning in result.warnings)
        )

    def test_round_robin_covers_every_facet_before_doubling(self):
        agent = LiteratureAgent(self.spec, OneSourcePerQueryRetriever(), SimpleParser())
        result = agent.run(
            LiteratureRequest(question="perovskite stability", max_sources=7, coverage_plan=True)
        )
        self.assertEqual(len(result.hits), 6)
        self.assertTrue(all(facet.covered for facet in result.brief.facets))
        self.assertTrue(all(len(facet.source_ids) == 1 for facet in result.brief.facets))

    def test_query_planner_extends_queries_and_falls_back(self):
        planned = LiteratureAgent(
            self.spec,
            FixtureRetriever(),
            SimpleParser(),
            query_planner=lambda question: ["passivation survey", "humidity benchmark"],
        ).run(
            LiteratureRequest(question="钙钛矿 界面 钝化 稳定性", max_sources=4, coverage_plan=True)
        )
        self.assertIn("passivation survey", planned.query_plan.subqueries)
        self.assertIn("humidity benchmark", planned.query_plan.subqueries)

        fallback = LiteratureAgent(
            self.spec, FixtureRetriever(), SimpleParser(), query_planner=lambda question: None
        ).run(LiteratureRequest(question="钙钛矿 界面 钝化 稳定性", max_sources=4, coverage_plan=True))
        self.assertEqual(len(fallback.query_plan.subqueries), 6)
        self.assertTrue(any("query_planner" in warning for warning in fallback.warnings))

    def test_facet_subset_is_scoped_and_does_not_reintroduce_core(self):
        agent = LiteratureAgent(self.spec, OneSourcePerQueryRetriever(), SimpleParser())
        result = agent.run(
            LiteratureRequest(
                question="perovskite stability",
                max_sources=2,
                coverage_plan=True,
                facet_subset=["method", "evaluation"],
            )
        )
        self.assertEqual([facet.facet for facet in result.brief.facets], ["method", "evaluation"])
        self.assertEqual(len(result.hits), 2)
        self.assertEqual(result.query_plan.filters["facet_subset"], ["method", "evaluation"])

        planned = LiteratureAgent(
            self.spec,
            OneSourcePerQueryRetriever(),
            SimpleParser(),
            query_planner=lambda question: ["planned-core"],
        ).run(
            LiteratureRequest(
                question="perovskite stability",
                max_sources=1,
                coverage_plan=True,
                facet_subset=["method"],
            )
        )
        self.assertEqual(planned.query_plan.subqueries, ["perovskite stability method"])
        self.assertNotIn("core", planned.query_plan.filters["facets"])
        self.assertNotIn("planned-core", planned.query_plan.subqueries)

    def test_facet_subset_rejects_unknown_empty_or_legacy_use(self):
        with self.assertRaises(LiteratureError):
            self.agent.run(
                LiteratureRequest(question="perovskite", coverage_plan=True, facet_subset=["unknown"])
            )
        with self.assertRaises(LiteratureError):
            self.agent.run(
                LiteratureRequest(question="perovskite", coverage_plan=True, facet_subset=[])
            )
        with self.assertRaises(LiteratureError):
            self.agent.run(
                LiteratureRequest(question="perovskite", facet_subset=["method"])
            )

    def test_openalex_adapter_returns_clues_without_full_text(self):
        transport = StaticTransport(
            {
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "display_name": "Passivation study",
                        "publication_year": 2024,
                        "doi": "https://doi.org/10.1/abc",
                        "primary_location": {"source": {"display_name": "Journal"}, "license": "cc-by"},
                        "open_access": {"oa_url": "https://example.org/paper.pdf"},
                        "abstract_inverted_index": {"Hello": [0], "world": [1]},
                    }
                ]
            }
        )
        retriever = OpenAlexRetriever(mailto="lab@example.org", transport=transport)
        hits = retriever.search("perovskite passivation", 4)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].source_id, "OA:W1")
        self.assertEqual(hits[0].abstract, "Hello world")
        self.assertFalse(hits[0].full_text)
        self.assertIsNone(retriever.full_text(hits[0].source_id))
        query = parse_qs(urlparse(transport.requests[0].full_url).query)
        self.assertEqual(query["search"], ["perovskite passivation"])
        self.assertEqual(query["mailto"], ["lab@example.org"])
        self.assertNotIn("api_key", query)

    def test_openalex_api_key_is_header_only(self):
        transport = StaticTransport({"results": []})
        retriever = OpenAlexRetriever(api_key="secret-key", transport=transport)
        retriever.search("query", 1)
        request = transport.requests[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-key")
        self.assertNotIn("secret-key", request.full_url)

    def test_glm_query_planner_returns_only_search_strings(self):
        transport = StaticTransport(
            {"choices": [{"message": {"content": '{"subqueries": ["a review", "b method"]}'}}]}
        )
        planner = glm_query_planner(GLMModel(api_key="test", transport=transport))
        self.assertEqual(planner("question"), ["a review", "b method"])


class EvidenceBreadthTest(unittest.TestCase):
    """S1 must disclose whether its evidence base is review-grade.

    Measured: the default fixture corpus has 3 records (2 full text), so raising
    max_sources from 3 to 50 changes nothing; a 7-paper local CC-BY corpus with
    max_sources=12 reaches 7 sources / 56 spans / coverage 1.0 / saturated.
    Q0 returns "pass" in both cases, so the disclosure is the only signal a
    downstream S2 consumer has.
    """

    def setUp(self):
        self.store = SpecStore()
        self.spec = self.store.load("literature")

    @staticmethod
    def _breadth(result):
        markers = [w for w in result.warnings if w.startswith("evidence_breadth=")]
        return markers

    def _local_corpus_agent(self, directory):
        from pathlib import Path
        from research_agent.adapters.local_document_retriever import LocalDocumentRetriever

        base = Path(__file__).resolve().parents[1] / "modules" / "literature" / "fixtures"
        for name in ("real_corpus.json", "transfer_corpus.json"):
            payload = json.loads((base / name).read_text(encoding="utf-8"))
            for paper in payload["papers"]:
                sections = paper.get("sections") or []
                body = "\n\n".join(
                    "%s\n%s" % (section.get("heading", ""), section.get("text", ""))
                    for section in sections
                )
                if not body.strip():
                    continue
                target = Path(directory) / (paper["source_id"].replace("/", "_") + ".txt")
                target.write_text("# " + paper["title"] + "\n\n" + body, encoding="utf-8")
        return LiteratureAgent(self.spec, LocalDocumentRetriever(Path(directory)), SimpleParser())

    def test_default_fixture_is_below_review_grade_even_with_a_large_budget(self):
        agent = LiteratureAgent(self.spec, FixtureRetriever(), SimpleParser())
        result = agent.run(
            LiteratureRequest(question="钙钛矿 界面 钝化 湿热稳定性", max_sources=50, coverage_plan=True)
        )
        markers = self._breadth(result)
        self.assertEqual(len(markers), 1)
        self.assertIn("sources:3", markers[0])
        self.assertIn("spans:5", markers[0])
        self.assertIn("review_grade:no", markers[0])
        self.assertIn("--corpus-dir <dir>", markers[0])
        self.assertIn("not a literature-review conclusion", markers[0])
        # Raising the budget cannot widen a 3-record corpus.
        self.assertEqual(len(result.hits), 3)
        self.assertEqual(result.status, "ok")

    def test_local_full_text_corpus_reaches_review_grade(self):
        import tempfile
        from research_agent.flow import q0_decision

        with tempfile.TemporaryDirectory(prefix="breadth-test-") as directory:
            agent = self._local_corpus_agent(directory)
            result = agent.run(
                LiteratureRequest(question="self-improving agent", max_sources=12, coverage_plan=True)
            )
        markers = self._breadth(result)
        self.assertEqual(len(markers), 1)
        self.assertIn("sources:7", markers[0])
        self.assertIn("review_grade:yes", markers[0])
        self.assertIn("saturation:saturated", markers[0])
        self.assertNotIn("--corpus-dir", markers[0])
        self.assertEqual(q0_decision(result)["status"], "pass")

    def test_breadth_is_disclosure_only_and_q0_is_unchanged(self):
        from research_agent.flow import q0_decision

        small = LiteratureAgent(self.spec, FixtureRetriever(), SimpleParser()).run(
            LiteratureRequest(question="钙钛矿 界面 钝化 湿热稳定性", max_sources=6, coverage_plan=True)
        )
        self.assertEqual(small.status, "ok")
        self.assertEqual(q0_decision(small)["status"], "pass")
        self.assertIn(self._breadth(small)[0], small.coverage.warnings)
        # No new gap / status / claim surface was introduced by the disclosure.
        self.assertEqual(
            [gap.code for gap in small.coverage.gaps].count("evidence_breadth"), 0
        )


if __name__ == "__main__":
    unittest.main()

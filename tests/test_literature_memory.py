import json
import tempfile
import unittest
from pathlib import Path

from research_agent.literature_memory import (
    LiteratureMemoryError,
    LiteratureMemoryStore,
    topic_key,
)


class LiteratureMemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "literature_memory.json"
        self.store = LiteratureMemoryStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def _record(self, run_id: str, limitation_covered: bool = False):
        return self.store.record(
            question="How do self-improving agents use archives?",
            run_id=run_id,
            facets=[
                {"facet": "core", "queries": 2, "sources": 2, "spans": 8, "covered": True},
                {
                    "facet": "limitation",
                    "queries": 2,
                    "sources": 1 if limitation_covered else 0,
                    "spans": 4 if limitation_covered else 0,
                    "covered": limitation_covered,
                },
            ],
            totals={"sources": 2, "full_text": 2, "spans": 8, "queries": 4},
            gaps=["thin_domain_coverage"],
            saturation="partial",
            mode="fixture",
            coverage_score=0.55,
            fixture_mode=True,
        )

    def test_cold_start_uses_balanced_groups_and_full_budget(self):
        advice = self.store.advise("A new topic", 12, "fixture")
        self.assertTrue(advice["cold_start"])
        self.assertEqual(len(advice["scout_groups"]), 3)
        self.assertEqual(sum(group["budget"] for group in advice["scout_groups"]), 12)
        self.assertEqual(advice["deferred_facets"], [])
        self.assertTrue(any("cold start" in warning for warning in advice["warnings"]))

    def test_memory_is_scoped_by_source_mode(self):
        self._record("RUN-1")
        real_advice = self.store.advise("How do self-improving agents use archives?", 12, "real")
        self.assertTrue(real_advice["cold_start"])
        self.assertEqual(real_advice["observed_runs"], 0)
        self.assertTrue(any("other-mode" in warning for warning in real_advice["warnings"]))
        fixture_advice = self.store.advise("How do self-improving agents use archives?", 12, "fixture")
        self.assertFalse(fixture_advice["cold_start"])
        self.assertEqual(fixture_advice["observed_runs"], 1)

    def test_uncovered_facet_gets_priority_and_a_governed_skill_candidate(self):
        self._record("RUN-1")
        self._record("RUN-2")
        advice = self.store.advise("How do self-improving agents use archives?", 12, "fixture")
        by_facet = {item["facet"]: item for item in advice["facet_priorities"]}
        self.assertGreater(by_facet["limitation"]["priority"], by_facet["core"]["priority"])
        self.assertEqual(by_facet["limitation"]["coverage_rate"], 0.0)
        candidate = advice["skill_candidate"]
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["facet"], "limitation")
        self.assertEqual(candidate["status"], "pending_human")
        self.assertFalse(candidate["governance"]["auto_admitted"])
        self.assertIn("Claim", candidate["governance"]["immutable"])
        self.assertEqual(candidate["target"], "literature.query_planner")
        self.assertTrue(candidate["candidate_id"].startswith("LCAND-"))

    def test_repeated_budget_cap_proposes_a_process_change(self):
        for run_id in ("RUN-CAP-1", "RUN-CAP-2"):
            self.store.record(
                question="How do self-improving agents use archives?",
                run_id=run_id,
                facets=[
                    {"facet": facet, "queries": 1, "sources": 4, "spans": 8, "covered": True}
                    for facet in ("core", "survey", "method", "evaluation", "limitation", "recent")
                ],
                totals={"sources": 4, "full_text": 4, "spans": 32, "queries": 6},
                gaps=["coverage_cap_reached"],
                saturation="partial",
                mode="real",
                coverage_score=0.9,
                fixture_mode=False,
            )
        advice = self.store.advise("How do self-improving agents use archives?", 12, "real")
        candidate = advice["skill_candidate"]
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["kind"], "process")
        self.assertEqual(candidate["target"], "orchestrator.facet_budget")
        self.assertEqual(candidate["constraint"], "source_budget")
        self.assertIsNone(candidate["facet"])
        self.assertEqual(candidate["status"], "pending_human")
        self.assertFalse(candidate["governance"]["auto_admitted"])
        self.assertIn("coverage_cap_reached", candidate["rationale"])

    def test_budget_below_facet_count_defers_instead_of_pretending(self):
        advice = self.store.advise("A new topic", 2, "fixture")
        self.assertEqual(sum(group["budget"] for group in advice["scout_groups"]), 2)
        self.assertEqual(len(advice["deferred_facets"]), 4)
        self.assertTrue(any("deferred facets" in warning for warning in advice["warnings"]))

    def test_snapshot_contains_counts_not_paper_text(self):
        self._record("RUN-1")
        payload = self.store.snapshot()
        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["count"], 1)
        self.assertIn("process memory only", payload["boundary"])
        self.assertNotIn("abstract", encoded.lower())
        self.assertNotIn("excerpt", encoded.lower())
        topic = payload["topics"][0]
        self.assertEqual(topic["modes"]["fixture"]["facets"]["limitation"]["attempts"], 1)
        self.assertEqual(topic["modes"]["fixture"]["runs"], 1)

    def test_topic_key_is_normalized_and_empty_is_rejected(self):
        self.assertEqual(
            topic_key("  How  do agents use archives? "),
            topic_key("how do agents use archives?"),
        )
        with self.assertRaises(LiteratureMemoryError):
            topic_key("   ")
        with self.assertRaises(LiteratureMemoryError):
            self.store.advise("A topic", 6, "fixture", facets=["unknown"])


if __name__ == "__main__":
    unittest.main()

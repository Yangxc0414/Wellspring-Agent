"""Reviewer-side prior-art retrieval: the novelty critic must not judge against a self-chosen set.

Borrowed structure from IdeaScientist's harness, where the reviewer "does its own retrieval to
actively search for prior art that refutes the novelty delta".
"""

import json
import unittest
from dataclasses import dataclass

from research_agent.innovation_review import (
    PRIOR_ART_BOUNDARY,
    _prior_art_check,
    _review,
)


@dataclass
class Hit:
    source_id: str
    title: str
    abstract: str = ""
    fixture: bool = False


class StubRetriever:
    fixture_mode = False

    def __init__(self, hits_by_query):
        self._hits = hits_by_query
        self.queries = []

    def search(self, query, limit):
        self.queries.append((query, limit))
        return list(self._hits.get(self._key(query), []))[:limit]

    @staticmethod
    def _key(query):
        for token in ("archive", "gate"):
            if token in query:
                return token
        return "other"


class RecordingModel:
    model_id = "stub-model"

    def __init__(self, idea_ids):
        self._idea_ids = idea_ids
        self.messages = []

    def complete(self, messages, json_mode=True):
        self.messages.append(messages)
        return json.dumps(
            {
                "scores": [
                    {
                        "idea_id": idea_id,
                        "score": 6,
                        "strengths": ["ok"],
                        "weaknesses": ["weak"],
                        "must_fix": ["cite prior art"],
                    }
                    for idea_id in self._idea_ids
                ],
                "overall": "mixed",
            }
        )


IDEAS = [
    {
        "idea_id": "IDEA-01",
        "title": "archive-aware gating",
        "problem": "the archive keeps stale candidates",
        "mechanism": "gate archive additions by validation delta before they enter the pool",
        "novelty_claim": "no prior work gates an archive on measured improvement",
        "falsification": "gating changes nothing over no gating",
        "experiment_plan": {},
        "evidence_refs": ["S1"],
    }
]


class PriorArtCheckTest(unittest.TestCase):
    def test_no_retriever_is_reported_as_absent_not_silently_skipped(self):
        check = _prior_art_check(IDEAS, None, set())
        self.assertFalse(check["available"])
        self.assertIn("generator's own evidence set", check["reason"])
        self.assertEqual(check["boundary"], PRIOR_ART_BOUNDARY)

    def test_hits_are_labelled_with_overlap_and_generator_membership(self):
        retriever = StubRetriever(
            {
                "archive": [
                    Hit("W-1", "gating an archive by validation delta", "we gate additions"),
                    Hit("S1", "gate archive additions by measured improvement", ""),
                ]
            }
        )
        check = _prior_art_check(IDEAS, retriever, {"S1"}, limit=6)
        self.assertTrue(check["available"])
        self.assertTrue(check["reviewer_retrieved"])
        self.assertEqual(check["queries"], 1)
        self.assertEqual(check["sources"], 2)
        # independence must be visible, never assumed: one of the two hits was already the
        # generator's own source
        self.assertEqual(check["independent_sources"], 1)
        rows = {row["source_id"]: row for row in check["hits"]}
        self.assertTrue(rows["S1"]["also_in_generator_set"])
        self.assertFalse(rows["W-1"]["also_in_generator_set"])
        self.assertGreater(rows["W-1"]["overlap"], 0.0)
        self.assertIn("已在生成方集合=True", check["text"])
        self.assertIn("[S1]", check["text"], "the critic must be able to name the source id")
        self.assertTrue(check["independent_sources_are_upper_bound"])
        self.assertIn("prior_art_refs", check["independence_scope"])
        self.assertEqual(retriever.queries[0][1], 6)

    def test_retriever_failure_degrades_to_absent_with_the_reason(self):
        class Broken:
            fixture_mode = False

            def search(self, query, limit):
                raise RuntimeError("index missing")

        check = _prior_art_check(IDEAS, Broken(), set())
        self.assertFalse(check["available"])
        self.assertIn("index missing", check["reason"])


class ReviewPromptTest(unittest.TestCase):
    def _run(self, role, prior_art):
        model = RecordingModel([idea["idea_id"] for idea in IDEAS])
        review = _review(role, IDEAS, "context text", model, 1, prior_art=prior_art)
        sent = model.messages[0][-1]["content"]
        return review, sent

    def test_novelty_critic_receives_the_refutation_block_and_must_answer_it(self):
        prior_art = _prior_art_check(
            IDEAS,
            StubRetriever({"archive": [Hit("W-1", "gating an archive by validation delta", "")]}),
            set(),
        )
        review, sent = self._run("novelty", prior_art)
        self.assertIn("评审方独立检索到的可能反证来源", sent)
        self.assertIn("无视这些命中仍给高分，视为无效评审", sent)
        self.assertIn("W-1", sent)
        self.assertTrue(review["prior_art"]["available"])
        self.assertEqual(review["prior_art"]["sources"], 1)
        self.assertNotIn("hits", review["prior_art"], "the review carries a summary, not the rows")

    def test_other_critic_roles_do_not_get_the_novelty_block(self):
        prior_art = _prior_art_check(
            IDEAS, StubRetriever({"archive": [Hit("W-1", "gating an archive", "")]}), set()
        )
        review, sent = self._run("evidence", prior_art)
        self.assertNotIn("评审方独立检索到的可能反证来源", sent)
        self.assertNotIn("prior_art", review)

    def test_novelty_review_states_absence_instead_of_pretending_independence(self):
        review, sent = self._run("novelty", _prior_art_check(IDEAS, None, set()))
        self.assertFalse(review["prior_art"]["available"])
        self.assertIn("generator's own evidence set", review["prior_art"]["reason"])
        self.assertNotIn("评审方独立检索到的可能反证来源", sent)


if __name__ == "__main__":
    unittest.main()

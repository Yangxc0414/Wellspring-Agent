import unittest

from research_agent.idea_review import build_idea_review


def spans():
    return [
        {"span_id": "SPAN-1", "source_id": "SRC-1", "text": "Passivation improves humidity stability in the tested condition."},
        {"span_id": "SPAN-2", "source_id": "SRC-2", "text": "Humidity cycling changes interface defect density and T80."},
    ]


def card(**overrides):
    values = {
        "idea_id": "IDEA-01",
        "title": "Interface defects and humidity stability",
        "hypothesis": "Lower interface defect density will increase T80 under humidity cycling compared with the unpassivated control.",
        "falsification": "T80 does not improve beyond the preregistered minimum effect under the frozen protocol.",
        "evidence_refs": ["SPAN-1", "SPAN-2"],
        "lens": "mechanism",
    }
    values.update(overrides)
    return {"candidates": [values]}


class IdeaReviewTest(unittest.TestCase):
    def test_grounded_testable_candidate_advances(self):
        review = build_idea_review(card(), {"spans": spans()})
        item = review["reviews"][0]
        self.assertEqual(item["recommendation"], "advance")
        self.assertEqual(item["dimensions"]["source_diversity"], "multi_source")
        self.assertEqual(item["dimensions"]["novelty_heuristic"], "plausible_novel")
        self.assertEqual(review["counts"]["advance"], 1)

    def test_missing_or_unknown_refs_reject(self):
        review = build_idea_review(card(evidence_refs=["MISSING"]), {"spans": spans()})
        item = review["reviews"][0]
        self.assertEqual(item["recommendation"], "reject")
        self.assertEqual(item["dimensions"]["grounding"], "missing")
        self.assertTrue(any("evidence_ref" in reason for reason in item["reasons"]))

    def test_restatement_and_single_source_need_revision(self):
        restated = card(
            hypothesis="Passivation improves humidity stability in the tested condition.",
            evidence_refs=["SPAN-1"],
        )
        review = build_idea_review(restated, {"spans": spans()})
        item = review["reviews"][0]
        self.assertEqual(item["recommendation"], "revise")
        self.assertEqual(item["dimensions"]["novelty_heuristic"], "restates_evidence")
        self.assertEqual(item["dimensions"]["source_diversity"], "single_source")

    def test_invalid_lens_and_missing_metric_need_revision(self):
        review = build_idea_review(
            card(
                lens="unknown",
                hypothesis="An interface change may have an effect.",
                falsification="A follow-up experiment may show a difference under some conditions.",
            ),
            {"spans": spans()},
        )
        item = review["reviews"][0]
        self.assertEqual(item["recommendation"], "revise")
        self.assertEqual(item["dimensions"]["lens"], "invalid")
        self.assertIn(item["dimensions"]["testability"], ("needs_metric", "metric_signal"))


if __name__ == "__main__":
    unittest.main()

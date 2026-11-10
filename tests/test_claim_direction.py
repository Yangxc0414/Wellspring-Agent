"""The claim sentence and its assertions can disagree about direction; nothing used to notice.

Comparators are generated from the measured interval, so they are the trustworthy half. This guard
reads the prose only to warn, never to rewrite a human's claim.
"""

import unittest
from collections import namedtuple

from research_agent.study_claims import statement_direction_note

_A = namedtuple("_A", "comparator condition metric")


def _assertion(comparator, condition):
    return _A(comparator=comparator, condition=condition, metric="improvement_per_evaluation.iris.memory_on")


class StatementDirectionNoteTest(unittest.TestCase):
    def test_an_improvement_sentence_over_less_than_assertions_is_flagged(self):
        note = statement_direction_note(
            "guideline memory 提升搜索效率",
            [_assertion("<", "memory_on_gate_off vs memory_off_gate_off (decidable)")],
        )
        self.assertIn("less than zero", note)
        self.assertIn("memory_on_gate_off", note)

    def test_the_same_guard_works_in_english(self):
        note = statement_direction_note(
            "the archive improves search efficiency",
            [_assertion("<", "memory_on vs memory_off (decidable)")],
        )
        self.assertIn("improvement", note)

    def test_a_cost_sentence_over_greater_than_assertions_is_flagged_too(self):
        note = statement_direction_note(
            "the acceptance gate 降低了单位评估的改进",
            [_assertion(">", "memory_on_gate_off vs memory_off_gate_off (decidable)")],
        )
        self.assertIn("greater than zero", note)

    def test_a_consistent_sentence_gets_no_note(self):
        self.assertEqual(
            statement_direction_note(
                "guideline memory 提高最终分数", [_assertion(">", "memory_on vs memory_off (decidable)")]
            ),
            "",
        )

    def test_a_sentence_holding_both_polarities_is_left_alone(self):
        # mechanism prose legitimately says "raises X at the cost of Y"; guessing here would refuse
        # valid claims, so the note stays silent rather than picking one verb
        self.assertEqual(
            statement_direction_note(
                "memory 提高最终分数，但以降低评估效率为代价",
                [_assertion(">", "best_score (decidable)")],
            ),
            "",
        )

    def test_no_assertions_means_no_direction_to_compare(self):
        self.assertEqual(statement_direction_note("memory 提升效率", []), "")

    def test_mixed_assertion_directions_are_not_called_a_contradiction(self):
        self.assertEqual(
            statement_direction_note(
                "memory 提升表现",
                [_assertion(">", "best_score (decidable)"), _assertion("<", "efficiency (decidable)")],
            ),
            "",
        )


class ClaimWarningsReachTheCallerTest(unittest.TestCase):
    """#71: the guards wrote their notes into the file while the returned body said nothing.

    A host that drafts a claim through the CLI sees the payload, not the JSON file, so a warning
    that only lives in claim-draft.json is invisible at the moment the human is asked to sign.
    """

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_drafted_warnings_are_returned_not_only_written(self):
        import json
        from pathlib import Path

        from research_agent.search_lab import write_study_package
        from research_agent.storage import read_json
        from research_agent.study_claims import build_study_claim

        directory = Path(self.tmp.name) / "study"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 17)), budget=60)
        payload = build_study_claim(
            directory,
            "on iris, memory raises improvement per validation evaluation",
            "checked the paired intervals",
            "S5/warningtest/iris",
        )
        self.assertIn("warnings", payload, sorted(payload.keys()))
        notes = payload["warnings"]
        self.assertTrue(any("analogue" in item for item in notes), notes)
        self.assertTrue(any("exploratory" in item for item in notes), notes)
        draft = read_json(directory / "claim-draft.json") or {}
        self.assertEqual(list(draft.get("warnings") or []), list(notes))
        self.assertTrue(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()

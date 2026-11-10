"""The ideation prompt may not decide the artifact language by itself."""

import unittest

from research_agent.innovation_review import InnovationReviewError, _propose

PACK = {
    "run_id": "RUN-LANG",
    "task": {"goal": "does archive gating raise improvement per validation evaluation"},
    "literature": {
        "references": [
            {"ref_id": "REF-01", "source_id": "S1", "title": "A", "year": 2024, "venue": "arXiv"},
            {"ref_id": "REF-02", "source_id": "S2", "title": "B", "year": 2025, "venue": "arXiv"},
        ],
        "selected_spans": {
            "S1": [{"span_id": "SP-1", "text": "gating evidence", "source_id": "S1"}],
            "S2": [{"span_id": "SP-2", "text": "archive evidence", "source_id": "S2"}],
        },
    },
}


def _prompt(language):
    recorded = []

    class Recorder:
        def complete(self, messages, json_mode=False):
            recorded.append(messages[-1]["content"])
            return "not json at all"

    try:
        _propose(PACK, Recorder(), 3, language=language)
    except (InnovationReviewError, ValueError):
        pass
    assert recorded, "the proposal prompt never reached the model"
    return recorded[0]


class ProposeLanguageTest(unittest.TestCase):
    # Measured before the fix: rule 8 was hard-coded to Chinese, so 0 of 11 idea artifacts were
    # ASCII and an English venue rubric scored our S2 output at covered=0.
    def test_english_request_replaces_the_chinese_rule(self):
        prompt = _prompt("en")
        self.assertIn("in English", prompt)
        self.assertNotIn(u"8. 使用中文。", prompt)

    def test_default_request_still_asks_for_chinese(self):
        prompt = _prompt("zh")
        self.assertIn(u"8. 使用中文。", prompt)
        self.assertNotIn("Write every field you return", prompt)

    def test_an_unsupported_language_is_refused_before_the_run(self):
        from pathlib import Path

        from research_agent.innovation_review import run_innovation_review

        with self.assertRaises(InnovationReviewError) as raised:
            run_innovation_review(Path("nowhere"), "RUN-X", language="fr")
        self.assertIn("zh or en", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

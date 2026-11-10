import unittest

from research_agent.adapters.simple_parser import SimpleParser, normalize_section_text
from research_agent.contracts import SourceHit


def _source():
    return SourceHit(
        source_id="S1",
        title="A paper",
        year=2024,
        venue="arXiv",
        doi=None,
        abstract="",
        full_text=True,
        license="arXiv",
        fixture=False,
    )


class SimpleParserNormalizationTest(unittest.TestCase):
    def test_wrapped_pdf_lines_become_readable_sentences(self):
        text = (
            "We propose a unified framework for decision making with learning\n"
            "curves and show that it reduces extrapolation error across the\n"
            "evaluated settings.\n"
            "Learning in chemical reaction networks\n"
            "Chemical Reaction Networks Learn Better than Spiking Networks\n"
        )
        spans = SimpleParser(max_spans_per_source=20).spans(
            _source(), {"sections": [{"name": "Page 1", "page": 1, "text": text}]}
        )
        self.assertTrue(any("We propose a unified framework" in span.text for span in spans))
        joined = next(span.text for span in spans if span.text.startswith("We propose"))
        self.assertIn("evaluated settings.", joined)
        self.assertNotIn("\n", joined)
        self.assertTrue(any(span.text == "Learning in chemical reaction networks" for span in spans))

    def test_hyphenated_line_break_is_repaired(self):
        text = "Our frame-\nwork improves the extrapolation accuracy on the held-\nout data."
        normalized = normalize_section_text(text)
        self.assertIn("framework", normalized)
        self.assertIn("heldout", normalized)

    def test_lowercase_continuation_after_blank_line_is_joined(self):
        text = "Here we present a set of community recommendations aiming to\n\nestablish standards for validation in biology."
        normalized = normalize_section_text(text)
        self.assertFalse(any(line.startswith("establish standards") for line in normalized.split("\n")))
        self.assertIn("recommendations aiming to establish standards", normalized)

    def test_abbreviation_and_decimal_do_not_split_into_fragments(self):
        text = (
            "We compare methods such as Ridge (e.g. alpha=0.1) and report gains "
            "of 0.1438 over the baseline in the main experiment."
        )
        spans = SimpleParser(max_spans_per_source=20).spans(
            _source(), {"sections": [{"name": "Page 1", "page": 1, "text": text}]}
        )
        self.assertEqual(len(spans), 1)
        self.assertIn("0.1438", spans[0].text)

    def test_chinese_sentences_keep_full_stop_boundaries(self):
        text = "本文提出统一的评估框架。实验表明该框架降低了外推误差。"
        spans = SimpleParser(max_spans_per_source=20).spans(
            _source(), {"sections": [{"name": "摘要", "page": 1, "text": text}]}
        )
        self.assertEqual([span.text for span in spans], ["本文提出统一的评估框架。", "实验表明该框架降低了外推误差。"])

    def test_abstract_only_source_has_no_spans(self):
        source = _source()
        source.full_text = False
        spans = SimpleParser().spans(
            source, {"sections": [{"name": "Page 1", "text": "Abstract only."}]}
        )
        self.assertEqual(spans, [])


if __name__ == "__main__":
    unittest.main()

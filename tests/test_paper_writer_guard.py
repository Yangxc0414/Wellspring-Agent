"""The writer guard must reject invented results without rejecting grounded citations.

Both directions broke in practice: the number guard scanned citation ids (which carry digits) as
result numbers and rejected every grounded section, while the citation whitelist accepted refs from
spans the prompt never showed.
"""

import unittest
from types import SimpleNamespace

from research_agent.modules.paper import (
    MAX_WRITER_EVIDENCE_SPANS,
    _validate_writer_sections,
    citable_refs,
)

INTRODUCTION = (
    "Retention and gating decide which candidates are worth validating, because the loop stays "
    "expensive while every accepted change has to be scored before it is kept "
    "[ARXIV-2609.19526-S01-03]."
)


def _request(span_count=4):
    spans = [
        SimpleNamespace(
            span_id="ARXIV-2609.19526-S01-%02d" % index,
            source_id="ARXIV-2609.19526",
            section="1 Introduction",
            text="archive retention changes how many evaluations a self-improvement loop can afford",
        )
        for index in range(span_count)
    ]
    return SimpleNamespace(
        topic="archive memory and acceptance gates",
        literature_brief=None,
        spans=spans,
        design=None,
        claim_statements=[],
    )


class WriterNumberGuardTest(unittest.TestCase):
    def test_span_citations_are_not_counted_as_result_numbers(self):
        request = _request()
        refs = {span.span_id for span in request.spans}
        accepted, rejected = _validate_writer_sections(
            request, {"introduction": INTRODUCTION}, refs
        )
        self.assertEqual(rejected, [], rejected)
        self.assertIn("introduction", accepted)

    def test_an_invented_number_outside_citations_is_still_rejected(self):
        request = _request()
        refs = {span.span_id for span in request.spans}
        text = INTRODUCTION + " The harness reached 35 percent on the benchmark [ARXIV-2609.19526-S01-01]."
        accepted, rejected = _validate_writer_sections(request, {"introduction": text}, refs)
        self.assertEqual(accepted, {})
        self.assertEqual(rejected, ["introduction:ungrounded_number"])

    def test_a_citation_outside_the_shown_evidence_is_rejected(self):
        request = _request(span_count=4)
        refs = {span.span_id for span in request.spans[:3]}
        accepted, rejected = _validate_writer_sections(
            request, {"introduction": INTRODUCTION}, refs
        )
        self.assertEqual(accepted, {})
        self.assertEqual(rejected, ["introduction:unknown_citation"])

    def test_only_the_spans_presented_to_the_writer_are_citable(self):
        request = _request(span_count=MAX_WRITER_EVIDENCE_SPANS + 3)
        refs = citable_refs(request, "en")
        self.assertIn(request.spans[0].span_id, refs)
        self.assertNotIn(request.spans[-1].span_id, refs)
        self.assertEqual(len(refs), MAX_WRITER_EVIDENCE_SPANS)


if __name__ == "__main__":
    unittest.main()

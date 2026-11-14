"""Span grading: LLM classifies information type, mechanical baseline independently checks.

验收：机械基线分类正确（含数字 = quantitative_result 等）；
LLM prompt 模板合法；grading response 解析容忍格式异常；
一致率计算正确（LLM vs 机械基线）。
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.span_grades import (
    EVIDENCE_ROLES,
    SPAN_GRADES_SCHEMA,
    _mechanical_hint,
    build_grading_prompt,
    grade_spans,
    parse_grading_response,
    save_grades,
)


def _span(sid, text, source_id="SRC-1"):
    return {"span_id": sid, "text": text, "source_id": source_id, "section": "1"}


class MechanicalBaselineTest(unittest.TestCase):
    def test_quantitative_result_detected(self):
        self.assertEqual(
            _mechanical_hint("accuracy improved from 0.7 to 0.85 (p < 0.05)"),
            "quantitative_result",
        )

    def test_methodology_detected(self):
        self.assertEqual(
            _mechanical_hint("we used logistic regression with L2 regularization"),
            "methodology",
        )

    def test_causal_claim_detected(self):
        self.assertEqual(
            _mechanical_hint("this approach leads to better generalization"),
            "causal_claim",
        )

    def test_background_fallback(self):
        self.assertEqual(
            _mechanical_hint("this field has seen rapid growth"),
            "background",
        )


class GradingPromptTest(unittest.TestCase):
    def test_prompt_contains_all_span_texts(self):
        spans = [
            _span("S1", "first span text about accuracy"),
            _span("S2", "second span about methodology"),
        ]
        prompt = build_grading_prompt(spans)
        self.assertIn("first span text about accuracy", prompt)
        self.assertIn("second span about methodology", prompt)
        self.assertIn("S1", prompt)
        self.assertIn("S2", prompt)

    def test_prompt_contains_all_roles(self):
        prompt = build_grading_prompt([_span("S1", "text")])
        for role in EVIDENCE_ROLES:
            self.assertIn(role, prompt)


class ParseGradingResponseTest(unittest.TestCase):
    def test_valid_response_parsed(self):
        raw = json.dumps([
            {"span_id": "S1", "evidence_role": "quantitative_result"},
            {"span_id": "S2", "evidence_role": "methodology"},
        ])
        grades = parse_grading_response(raw, ["S1", "S2"])
        self.assertEqual(grades["S1"], "quantitative_result")
        self.assertEqual(grades["S2"], "methodology")

    def test_invalid_role_ignored(self):
        raw = json.dumps([{"span_id": "S1", "evidence_role": "made_up_role"}])
        grades = parse_grading_response(raw, ["S1"])
        self.assertNotIn("S1", grades)

    def test_malformed_json_returns_empty(self):
        grades = parse_grading_response("{not json", ["S1"])
        self.assertEqual(grades, {})

    def test_unknown_span_id_ignored(self):
        raw = json.dumps([{"span_id": "UNKNOWN", "evidence_role": "background"}])
        grades = parse_grading_response(raw, ["S1"])
        self.assertNotIn("UNKNOWN", grades)


class GradeSpansTest(unittest.TestCase):
    class _MockPort:
        def __init__(self, response):
            self._response = response
        def complete(self, messages, json_mode=False):
            return self._response

    def test_grade_spans_with_mock_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            spans = [
                _span("S1", "accuracy improved from 0.7 to 0.85 (p < 0.05)"),
                _span("S2", "we used logistic regression with L2 regularization"),
            ]
            mock_response = json.dumps([
                {"span_id": "S1", "evidence_role": "quantitative_result"},
                {"span_id": "S2", "evidence_role": "methodology"},
            ])
            port = self._MockPort(mock_response)
            result = grade_spans(spans, model_port=port, output_dir=Path(tmp))
            self.assertEqual(result["grades"]["S1"], "quantitative_result")
            self.assertEqual(result["grades"]["S2"], "methodology")
            self.assertTrue(result["agreement_rate"] is not None)

    def test_grade_spans_with_model_error(self):
        class _BrokenPort:
            def complete(self, messages, json_mode=False):
                raise RuntimeError("model unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            spans = [_span("S1", "text")]
            result = grade_spans(spans, model_port=_BrokenPort(), output_dir=Path(tmp))
            self.assertIn("error", result)

    def test_save_grades_creates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = {
                "schema_version": SPAN_GRADES_SCHEMA,
                "grades": {"S1": "quantitative_result"},
                "boundary": "test",
            }
            out = Path(tmp) / "span-grades.json"
            save_grades(out, result)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["grades"]["S1"], "quantitative_result")


if __name__ == "__main__":
    unittest.main()

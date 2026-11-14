"""Result interpretation connector: LLM 生成初步解读，人签仍由人决定。

验收：有 RunCapsule 时产出结构化解读；无 capsule 诚实报缺失；
LLM 解析失败不中断；boundary 声明不含门禁语义。
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.result_interpreter import (
    INTERPRETATION_SCHEMA,
    interpret_results,
    load_interpretation,
)


class _MockPort:
    def __init__(self, response):
        self._response = response

    def complete(self, messages, json_mode=False):
        return self._response


class _BrokenPort:
    def complete(self, messages, json_mode=False):
        raise RuntimeError("model unavailable")


def _fabricate_run(run: Path, with_metrics=True):
    run.mkdir(parents=True, exist_ok=True)
    (run / "run").mkdir(exist_ok=True)
    if with_metrics:
        (run / "run" / "run-capsule.json").write_text(
            json.dumps({
                "schema_version": "run-capsule-0.1",
                "run_id": "RUN-TEST",
                "metric_name": "accuracy",
                "dataset_id": "iris",
                "seeds": [17, 18, 19],
                "metrics_by_seed": [
                    {"seed": 17, "accuracy": 0.911},
                    {"seed": 18, "accuracy": 0.956},
                    {"seed": 19, "accuracy": 1.0},
                ],
                "mean": 0.956,
            }),
            encoding="utf-8",
        )
    (run / "experiment.json").write_text(
        json.dumps({"question": "Does X improve Y?", "primary_metric": "accuracy", "baseline": "ctrl"}),
        encoding="utf-8",
    )


class ResultInterpreterTest(unittest.TestCase):
    def test_interprets_real_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-1"
            _fabricate_run(run)
            mock = _MockPort(json.dumps({
                "metrics_reading": "seed 17 lowest, seed 19 highest",
                "notable_patterns": "monotonic increase",
                "potential_concerns": "only 3 seeds",
                "recommended_next_action": "add more seeds",
                "confidence_note": "directly supported",
            }, ensure_ascii=False))
            result = interpret_results(run, model_port=mock)
            self.assertEqual(result["status"], "interpreted")
            self.assertIn("metrics_reading", result["interpretation"])
            self.assertTrue((run / "interpretation.json").is_file())

    def test_missing_capsule_is_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-EMPTY"
            run.mkdir(parents=True)
            result = interpret_results(run, model_port=_MockPort("irrelevant"))
            self.assertEqual(result["status"], "missing_capsule")

    def test_model_failure_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-1"
            _fabricate_run(run)
            result = interpret_results(run, model_port=_BrokenPort())
            self.assertEqual(result["status"], "interpretation_failed")

    def test_boundary_does_not_claim_gate_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-1"
            _fabricate_run(run)
            result = interpret_results(run, model_port=_MockPort(json.dumps({
                "metrics_reading": "test", "notable_patterns": "test",
                "potential_concerns": "test", "recommended_next_action": "test",
                "confidence_note": "test",
            })))
            self.assertIn("NOT a claim", result["boundary"])
            self.assertIn("reading aid", result["boundary"].lower())
            self.assertNotIn("auto_sign", result["boundary"].lower())

    def test_load_interpretation_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-1"
            _fabricate_run(run)
            mock = _MockPort(json.dumps({
                "metrics_reading": "test reading", "notable_patterns": "test",
                "potential_concerns": "test", "recommended_next_action": "test",
                "confidence_note": "test",
            }))
            interpret_results(run, model_port=mock)
            loaded = load_interpretation(run)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["status"], "interpreted")


if __name__ == "__main__":
    unittest.main()

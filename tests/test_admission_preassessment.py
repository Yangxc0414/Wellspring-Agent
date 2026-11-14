"""Admission pre-assessment: LLM prepares the full evidence chain for S5b.

验收：有完整证据链时产出结构化预评估；无 signed claim 诚实报缺；
LLM 失败不 crash；boundary 声明不含门禁语义；roundtrip。
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.admission_preassessment import (
    load_preassessment,
    preassess_admission,
)


class _MockPort:
    def __init__(self, response):
        self._response = response

    def complete(self, messages, json_mode=False):
        return self._response


class _BrokenPort:
    def complete(self, messages, json_mode=False):
        raise RuntimeError("model unavailable")


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _fabricate_run(run: Path, with_claim=True):
    run.mkdir(parents=True, exist_ok=True)
    (run / "run").mkdir(exist_ok=True)
    (run / "claim").mkdir(exist_ok=True)
    _write(run / "run" / "run-capsule.json", {
        "schema_version": "run-capsule-0.1", "run_id": "RUN-TEST",
        "metric_name": "accuracy", "dataset_id": "iris", "seeds": [17, 18, 19],
        "metrics_by_seed": [
            {"seed": 17, "accuracy": 0.911}, {"seed": 18, "accuracy": 0.956}, {"seed": 19, "accuracy": 1.0},
        ], "mean": 0.956,
    })
    _write(run / "run" / "ea.json", {"run_id": "RUN-TEST", "immutable": True, "source": "run", "path": "metrics.json", "sha256": "abc"})
    if with_claim:
        _write(run / "claim" / "claim.json", {
            "claim_id": "CLM-TEST", "status": "supported", "statement": "accuracy >= 0.911",
            "assertions": [{"metric": "accuracy", "comparator": ">=", "value": 0.911, "observed": 0.956, "status": "pass"}],
        })
    _write(run / "idea.json", {"candidates": [
        {"idea_id": "IDEA-01", "title": "Test idea", "falsification": "if X then Y fails"}
    ]})
    _write(run / "experiment.json", {"question": "Does X improve Y?", "primary_metric": "accuracy"})


class AdmissionPreassessmentTest(unittest.TestCase):
    def test_preassesses_full_evidence_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-TEST"
            _fabricate_run(run)
            mock = _MockPort(json.dumps({
                "evidence_support": "strong",
                "semantic_consistency": "consistent",
                "gaps": ["only 3 seeds"],
                "focus_areas": ["check seed variance"],
                "reading_guide": "results are consistent across seeds",
            }, ensure_ascii=False))
            result = preassess_admission(run, model_port=mock)
            self.assertEqual(result["status"], "preassessed")
            self.assertEqual(result["preassessment"]["evidence_support"], "strong")
            self.assertIn("reading_guide", result["preassessment"])
            self.assertTrue((run / "admission-preassessment.json").is_file())

    def test_no_signed_claim_is_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-NO-CLAIM"
            _fabricate_run(run, with_claim=False)
            result = preassess_admission(run, model_port=_MockPort(json.dumps({
                "evidence_support": "weak", "semantic_consistency": "partial",
                "gaps": ["claim not signed"], "focus_areas": ["sign claim"],
                "reading_guide": "claim unsigned, cannot pre-assess fully",
            }, ensure_ascii=False)))
            self.assertEqual(result["status"], "no_signed_claim")

    def test_model_failure_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-1"
            _fabricate_run(run)
            result = preassess_admission(run, model_port=_BrokenPort())
            self.assertEqual(result["status"], "preassessment_failed")

    def test_boundary_does_not_claim_gate_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-1"
            _fabricate_run(run)
            mock = _MockPort(json.dumps({
                "evidence_support": "strong", "semantic_consistency": "consistent",
                "gaps": [], "focus_areas": [], "reading_guide": "test",
            }))
            result = preassess_admission(run, model_port=mock)
            b = result["boundary"].lower()
            self.assertIn("not a claim", b)
            self.assertIn("reading aid", b)
            self.assertIn("does not enter", b)

    def test_roundtrip_via_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "RUN-1"
            _fabricate_run(run)
            mock = _MockPort(json.dumps({
                "evidence_support": "strong", "semantic_consistency": "consistent",
                "gaps": [], "focus_areas": [], "reading_guide": "test",
            }))
            result = preassess_admission(run, model_port=mock)
            loaded = load_preassessment(run)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["status"], "preassessed")
            self.assertEqual(loaded["preassessment"]["evidence_support"], "strong")


if __name__ == "__main__":
    unittest.main()

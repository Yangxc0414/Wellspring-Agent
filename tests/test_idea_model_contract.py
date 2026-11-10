"""The model / host-model supply path must deliver structured predictions.

0.24.0 made IdeaCard carry `prediction`; if the prompt sent to the host still
forbids those slots, every real run stays `not_testable_here`. These tests pin
the prompt and the gateway -> IdeaCard path together.
"""

import json
import unittest

from research_agent.adapters.research_models import IDEA_SYSTEM, idea_proposer_from_model
from research_agent.contracts import Span
from research_agent.modules.idea import IdeaAgent, IdeaRequest, PREDICTION_SLOTS
from research_agent.specs import SpecStore


class FakeModelPort:
    def __init__(self, payload):
        self.payload = payload
        self.messages = None

    def complete(self, messages, json_mode=True):
        self.messages = messages
        return json.dumps(self.payload, ensure_ascii=False)


FULL_PREDICTION = {
    "variable": "memory",
    "direction": "increase",
    "condition": "gate=off",
    "profile": "search_factorial",
    "dataset": "iris",
    "metric": "improvement_per_evaluation",
    "controls": {"memory": [False, True], "gate": [False, True]},
    "seeds": [17, 18, 19],
    "stopping_rule": "paired CI95 crossing zero => undecidable",
    "criterion": "CI95 must not cross zero",
}


def _candidate(prediction=None):
    item = {
        "title": "Memory increases the primary metric",
        "hypothesis": "自变量 memory 开启应使主指标上升，在 gate=off 条件下。",
        "falsification": "配对区间跨零或方向反转则假设不成立，需重复种子验证。",
        "lens": "mechanism",
        "evidence_refs": ["X-1", "X-2"],
    }
    if prediction is not None:
        item["prediction"] = prediction
    return item


class IdeaModelContractTest(unittest.TestCase):
    def setUp(self):
        self.spec = SpecStore().load("idea")
        self.spans = [
            Span("X-1", "S-A", "Results",
                 "湿热条件下钝化层稳定性结果与对照差异需要重复测量。", 0, 20, fixture=False),
            Span("X-2", "S-B", "Limitations",
                 "该结论只在特定湿热循环边界内成立。", 0, 20, fixture=False),
        ]

    def _run(self, payload):
        port = FakeModelPort(payload)
        result = IdeaAgent(self.spec, proposer=idea_proposer_from_model(port)).run(
            IdeaRequest("湿热稳定性", self.spans, max_candidates=2)
        )
        return result, port

    def test_system_prompt_declares_all_slots_and_forbids_invention(self):
        for slot in PREDICTION_SLOTS:
            self.assertIn(slot, IDEA_SYSTEM)
        self.assertIn("省略 prediction", IDEA_SYSTEM)
        self.assertIn("禁止猜测或编造", IDEA_SYSTEM)
        self.assertIn("不在册一律判为不可测试", IDEA_SYSTEM)

    def test_gateway_delivers_prediction_to_a_testable_card(self):
        result, port = self._run({"candidates": [_candidate(FULL_PREDICTION)]})
        card = result.candidates[0]
        self.assertEqual(card.prediction_status, "testable")
        self.assertEqual(set(card.prediction or {}), set(PREDICTION_SLOTS))
        self.assertEqual(card.open_slots, [])
        self.assertEqual(port.messages[0]["content"], IDEA_SYSTEM)

    def test_host_answer_without_prediction_stays_not_testable(self):
        result, _ = self._run({"candidates": [_candidate()]})
        card = result.candidates[0]
        self.assertEqual(card.prediction_status, "not_testable_here")
        self.assertEqual(card.open_slots, list(PREDICTION_SLOTS))

    def test_out_of_profile_prediction_is_rejected_by_the_runtime(self):
        outside = dict(FULL_PREDICTION, dataset="agent reliability benchmark",
                       metric="judge alignment")
        result, _ = self._run({"candidates": [_candidate(outside)]})
        card = result.candidates[0]
        self.assertEqual(card.prediction_status, "cannot_test")
        self.assertEqual(len(card.prediction or {}), len(PREDICTION_SLOTS))


if __name__ == "__main__":
    unittest.main()

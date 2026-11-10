import json
import unittest

from research_agent.adapters.deepseek_model import DeepSeekModel, ModelConfigError
from research_agent.rsi_proposer import (
    FrozenModelProposer, ProposerError, RuleBasedProposer,
)


class FakeModel:
    model_id = "fake-frozen"

    def __init__(self, output):
        self.output = output
        self.calls = 0

    def complete(self, messages, json_mode=True):
        self.calls += 1
        return self.output


class SequenceModel(FakeModel):
    def __init__(self, outputs):
        super().__init__(outputs[0])
        self.outputs = list(outputs)

    def complete(self, messages, json_mode=True):
        self.calls += 1
        return self.outputs[min(self.calls - 1, len(self.outputs) - 1)]


class FrozenModelProposerTest(unittest.TestCase):
    def test_schema_repair_retries_with_error_feedback(self):
        valid = json.dumps({
            "kind": "process", "target": "budget",
            "patch": {"max_sources": 3, "retriever": "minilm"},
            "rationale": "cheaper retrieval", "predicted_effect": "lower cost",
        })
        model = SequenceModel(["not json", valid])
        result = FrozenModelProposer(model).propose_with_repair(
            "thin coverage", repair_attempts=1
        )
        self.assertTrue(result["repaired"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(model.calls, 2)
        self.assertIn("valid JSON", result["errors"][0])
        self.assertEqual(result["candidate"].target, "literature.retrieval.budget")


    def test_valid_candidate_is_policy_checked(self):
        model = FakeModel(json.dumps({
            "kind": "process",
            "target": "budget",
            "patch": {"max_sources": 2, "min_sources": 1},
            "rationale": "coverage observation",
            "predicted_effect": "same recall fewer sources",
        }))
        candidate = FrozenModelProposer(model).propose("thin coverage")
        self.assertEqual(candidate.target, "literature.retrieval.budget")
        self.assertEqual(json.loads(candidate.patch), {"retriever": "bm25", "max_sources": 2})
        self.assertEqual(candidate.scope, "S1/model-proposal")
        self.assertEqual(model.calls, 1)

    def test_invalid_json_is_rejected(self):
        with self.assertRaises(ProposerError):
            FrozenModelProposer(FakeModel("not json")).propose("thin coverage")

    def test_immutable_target_is_rejected(self):
        model = FakeModel(json.dumps({
            "kind": "process", "target": "claim.text", "patch": "x",
            "rationale": "x", "predicted_effect": "x",
        }))
        with self.assertRaises(ProposerError):
            FrozenModelProposer(model).propose("thin coverage")

    def test_rule_proposer_and_missing_key(self):
        candidate = RuleBasedProposer().propose("retrieval cost high")
        self.assertEqual(candidate.kind, "process")
        with self.assertRaises(ProposerError):
            RuleBasedProposer().propose("coverage gap only")
        with self.assertRaises(ModelConfigError):
            DeepSeekModel(api_key="")


if __name__ == "__main__":
    unittest.main()

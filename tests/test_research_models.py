import json
import tempfile
import unittest
from pathlib import Path

from research_agent.contracts import Span
from research_agent.models import ModelRequiredError
from research_agent.modules.experiment import ExperimentDesignAgent, ExperimentRequest
from research_agent.modules.idea import IdeaAgent, IdeaRequest
from research_agent.specs import SpecStore
from research_agent.adapters.research_models import (
    experiment_designer_from_model,
    gateway_experiment_designer,
    gateway_idea_proposer,
    idea_proposer_from_model,
)


class _FakeModel:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, messages, json_mode=True):
        self.messages = messages
        self.json_mode = json_mode
        return json.dumps(self.payload, ensure_ascii=False)


class ResearchModelAdapterTest(unittest.TestCase):
    def test_idea_proposer_parses_candidates(self):
        model = _FakeModel({"candidates": [{"title": "t", "evidence_refs": ["S-1"]}]})
        proposer = idea_proposer_from_model(model)
        result = proposer({"topic": "q", "language": "zh", "evidence": []})
        self.assertEqual(result, [{"title": "t", "evidence_refs": ["S-1"]}])
        self.assertTrue(model.json_mode)
        self.assertIn("evidence", model.messages[0]["content"])

    def test_idea_proposer_rejects_malformed_json(self):
        class BadModel:
            def complete(self, messages, json_mode=True):
                return "not json"

        self.assertIsNone(idea_proposer_from_model(BadModel())({"topic": "q"}))

    def test_experiment_designer_accepts_nested_design(self):
        model = _FakeModel({"design": {"baseline": "majority"}})
        design = experiment_designer_from_model(model)({"question": "q"})
        self.assertEqual(design, {"baseline": "majority"})

    def test_gateway_resolvers_degrade_without_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "models.json"
            idea, idea_note = gateway_idea_proposer(store_path=store_path)
            experiment, experiment_note = gateway_experiment_designer(store_path=store_path)
        self.assertIsNone(idea)
        self.assertIn("no idea model binding", idea_note)
        self.assertIsNone(experiment)
        self.assertIn("no experiment model binding", experiment_note)

    def test_strict_proposer_raises_instead_of_falling_back(self):
        class BadModel:
            def complete(self, messages, json_mode=True):
                raise RuntimeError("provider down")

        proposer = idea_proposer_from_model(BadModel(), strict=True)
        with self.assertRaises(ModelRequiredError):
            proposer({"topic": "q"})

    def test_strict_gateway_requires_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "models.json"
            with self.assertRaises(ModelRequiredError):
                gateway_idea_proposer(store_path=store_path, strict=True)
            with self.assertRaises(ModelRequiredError):
                gateway_experiment_designer(store_path=store_path, strict=True)

    def test_idea_agent_does_not_swallow_required_model_failure(self):
        class BadModel:
            def complete(self, messages, json_mode=True):
                raise RuntimeError("provider down")

        agent = IdeaAgent(
            SpecStore().load("idea"),
            proposer=idea_proposer_from_model(BadModel(), strict=True),
        )
        spans = [Span("S-1", "FX-1", "Results", "evidence text for the candidate.", 0, 20)]
        with self.assertRaises(ModelRequiredError):
            agent.run(IdeaRequest("strict topic", spans, max_candidates=1))

    def test_strict_idea_rejects_candidates_with_unknown_refs(self):
        def proposer(_payload):
            return [{
                "title": "Candidate",
                "hypothesis": "This candidate cites a span that was not supplied.",
                "falsification": "The candidate must be rejected in strict mode.",
                "lens": "mechanism",
                "evidence_refs": ["UNKNOWN"],
            }]

        agent = IdeaAgent(
            SpecStore().load("idea"), proposer=proposer, strict_model=True
        )
        spans = [Span("S-1", "FX-1", "Results", "evidence text for the candidate.", 0, 20)]
        with self.assertRaises(ModelRequiredError):
            agent.run(IdeaRequest("strict topic", spans, max_candidates=1))

    def test_strict_experiment_rejects_empty_draft(self):
        agent = ExperimentDesignAgent(
            SpecStore().load("experiment"), designer=lambda _payload: {}, strict_model=True
        )
        with self.assertRaises(ModelRequiredError):
            agent.run(ExperimentRequest("q", hypothesis="human hypothesis", seeds=3))


if __name__ == "__main__":
    unittest.main()

import unittest

from research_agent.modules.experiment import ExperimentDesignAgent, ExperimentRequest
from research_agent.specs import SpecStore


class ExperimentModelDraftTest(unittest.TestCase):
    def setUp(self):
        self.spec = SpecStore().load("experiment")
        self.agent = ExperimentDesignAgent(self.spec)

    def test_model_only_fills_missing_fields_and_stays_needs_human(self):
        seen = {}

        def designer(payload):
            seen.update(payload)
            return {
                "hypothesis": "model must not override the supplied hypothesis",
                "baseline": "majority class",
                "primary_metric": "accuracy",
                "controls": ["majority baseline", "shuffled labels"],
                "budget": "3 seeds x fixed split",
                "seeds": 99,
                "stopping_rule": "model must not set this",
            }

        agent = ExperimentDesignAgent(self.spec, designer=designer)
        design = agent.run(
            ExperimentRequest(
                "q",
                hypothesis="human-supplied hypothesis",
                seeds=3,
                evidence=[{"ref": "S-1", "section": "Results", "text": "evidence"}],
                language="en",
            )
        )
        self.assertEqual(seen["current"]["hypothesis"], "human-supplied hypothesis")
        self.assertEqual(design.hypothesis, "human-supplied hypothesis")
        self.assertEqual(design.baseline, "majority class")
        self.assertEqual(design.primary_metric, "accuracy")
        self.assertEqual(design.controls, ["majority baseline", "shuffled labels"])
        self.assertEqual(design.seeds, 3)
        self.assertNotIn("model must not set this", design.stopping_rule)
        self.assertEqual(design.status, "needs_human")
        self.assertTrue(any("model-drafted fields" in item for item in design.warnings))
        self.assertTrue(any("no automatic G2" in item for item in design.warnings))

    def test_complete_design_does_not_call_the_model(self):
        called = {"value": False}

        def designer(_payload):
            called["value"] = True
            return {"baseline": "should not be used"}

        agent = ExperimentDesignAgent(self.spec, designer=designer)
        design = agent.run(
            ExperimentRequest(
                "q",
                hypothesis="complete hypothesis",
                baseline="majority",
                primary_metric="accuracy",
                controls=["majority"],
                seeds=3,
                budget="3 seeds",
            )
        )
        self.assertFalse(called["value"])
        self.assertEqual(design.status, "ready_for_g2")

    def test_model_failure_keeps_deterministic_placeholders(self):
        def designer(_payload):
            raise RuntimeError("offline")

        agent = ExperimentDesignAgent(self.spec, designer=designer)
        design = agent.run(
            ExperimentRequest(
                "q",
                hypothesis="h",
                seeds=3,
                evidence=[{"ref": "S01-01", "section": "Intro", "text": "grounding span"}],
            )
        )
        self.assertEqual(design.baseline, "待人工补全")
        self.assertEqual(design.status, "needs_human")
        self.assertTrue(any("designer failed" in item for item in design.warnings))

    def test_designer_is_not_asked_to_design_without_span_level_evidence(self):
        called = {"value": False}

        def designer(_payload):
            called["value"] = True
            return {"baseline": "invented"}

        agent = ExperimentDesignAgent(self.spec, designer=designer)
        design = agent.run(ExperimentRequest("q", hypothesis="h", seeds=3))
        self.assertFalse(called["value"])
        self.assertEqual(design.baseline, "待人工补全")
        self.assertTrue(
            any("no span-level evidence" in item for item in design.warnings)
        )

    def test_model_cannot_mark_placeholder_as_complete(self):
        def designer(_payload):
            return {"hypothesis": "待人工补全", "baseline": "x", "controls": []}

        agent = ExperimentDesignAgent(self.spec, designer=designer)
        design = agent.run(ExperimentRequest("q", hypothesis="待人工补全", seeds=3))
        self.assertEqual(design.status, "needs_human")
        self.assertTrue(any("missing pre-registration fields" in item for item in design.warnings))


if __name__ == "__main__":
    unittest.main()

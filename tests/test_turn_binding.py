"""A recorded model turn must be attributable to the run that asked for it.

The ledger already stored prompt text and messages_sha256, but every recorded turn carried an empty
binding because no stage caller passed one, so a submission bundle could not say which prompts were
its own. These cases pin the two hops that were missing.
"""

import unittest

import research_agent.adapters.research_models as research_models
import research_agent.innovation_review as innovation_review


class BindingForwardingTest(unittest.TestCase):
    def test_default_model_for_forwards_the_binding_to_the_gateway_port(self):
        seen = {}

        def fake_gateway(module, profile_id, store_path, gateway, strict, purpose="",
                         binding=None, sink=None, wait_seconds=0):
            seen["binding"] = binding
            return object(), "host agent profile"

        original = research_models._gateway_port
        research_models._gateway_port = fake_gateway
        try:
            port, _note = research_models.default_model_for(
                "idea", purpose="S2 review", binding={"run_id": "RUN-9"}
            )
        finally:
            research_models._gateway_port = original
        self.assertIsNotNone(port)
        self.assertEqual(seen["binding"], {"run_id": "RUN-9"})

    def test_the_ideation_stage_names_the_project_and_run(self):
        captured = {}

        def fake_default(module, purpose="", binding=None, **kwargs):
            captured["module"] = module
            captured["purpose"] = purpose
            captured["binding"] = binding
            return object(), "host agent profile"

        original = research_models.default_model_for
        research_models.default_model_for = fake_default
        try:
            innovation_review._default_model("runtime_data/proj", "RUN-9")
        finally:
            research_models.default_model_for = original
        self.assertEqual(
            captured["binding"], {"project_dir": "runtime_data/proj", "run_id": "RUN-9"}
        )

    def test_no_context_yields_no_binding_rather_than_an_invented_one(self):
        captured = {}

        def fake_default(module, purpose="", binding=None, **kwargs):
            captured["binding"] = binding
            return object(), "note"

        original = research_models.default_model_for
        research_models.default_model_for = fake_default
        try:
            innovation_review._default_model()
        finally:
            research_models.default_model_for = original
        self.assertIsNone(captured["binding"])


if __name__ == "__main__":
    unittest.main()

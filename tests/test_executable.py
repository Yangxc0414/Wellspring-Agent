"""The executability registry is what stops idea-stage plans from becoming fiction."""

import unittest

from research_agent.executable import (
    BOUNDARY,
    REGISTRY_SCHEMA,
    executable_profiles,
    plan_prompt_block,
    profile_ids,
    validate_plan,
)


class ExecutableRegistryTest(unittest.TestCase):
    def test_every_profile_declares_what_it_cannot_test(self):
        profiles = executable_profiles()
        self.assertEqual(len(profiles), 3)
        for profile in profiles:
            self.assertTrue(
                profile.get("cannot_test"),
                "%s must name its own external-validity limit" % profile["id"],
            )
            self.assertTrue(profile.get("supports"))
            self.assertTrue(profile.get("datasets"))
            self.assertTrue(profile.get("metrics"))
        self.assertEqual(REGISTRY_SCHEMA, "executable-profiles-0.1")
        self.assertIn("protocol_run", profile_ids())

    def test_plan_without_a_profile_is_rejected_not_passed_with_a_warning(self):
        outcome = validate_plan(
            {"dataset": "两个公开小规模任务", "metric": "跨种子方差", "baseline": "x", "stopping_rule": "y"}
        )
        self.assertFalse(outcome["ok"])
        self.assertTrue(any("must name an executable profile" in item for item in outcome["reasons"]))

    def test_unknown_profile_is_rejected(self):
        outcome = validate_plan({"profile": "quantum_survey", "dataset": "iris", "metric": "accuracy"})
        self.assertFalse(outcome["ok"])
        self.assertTrue(any("unknown profile" in item for item in outcome["reasons"]))

    def test_dataset_and_metric_must_belong_to_the_chosen_profile(self):
        outcome = validate_plan(
            {"profile": "search_factorial", "dataset": "perovskite_passivation", "metric": "novelty_score"}
        )
        self.assertFalse(outcome["ok"])
        self.assertEqual(len(outcome["reasons"]), 2)

    def test_protocol_run_cannot_certify_a_search_claim(self):
        # The claim that motivated this registry: archive/gate hypotheses need the search
        # profile; the fixed protocol run cannot produce them.
        search = validate_plan(
            {"profile": "search_factorial", "dataset": "iris", "metric": "improvement_per_evaluation"}
        )
        protocol = validate_plan({"profile": "protocol_run", "dataset": "iris", "metric": "improvement_per_evaluation"})
        self.assertTrue(search["ok"])
        self.assertFalse(protocol["ok"])

    def test_prompt_block_lists_profiles_and_their_limits(self):
        block = plan_prompt_block()
        for profile_id in profile_ids():
            self.assertIn(profile_id, block)
        self.assertIn("不能检验", block)

    def test_boundary_is_carried_on_the_registry(self):
        self.assertIn("cannot be validated", BOUNDARY)


if __name__ == "__main__":
    unittest.main()

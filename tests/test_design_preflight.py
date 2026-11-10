"""Pre-flight must refuse designs the runner will refuse, using the runner's own rule.

Measured on a real host-answered ideation run (RUN-20261029T061502Z-45c79c): validate_plan checked
profile, dataset and metric but never the declared design, so plans with unregistered levels
(archive "on", archive_window "top2", parent_selection "diversity_biased") and a 16-cell design all
passed pre-flight with ok=True and would only fail after a round had been spent.

Payloads carry four ideas because the stage keeps an existing floor of three valid ideas; the cases
here assert on the refused fourth, not on that floor.
"""

import unittest

from research_agent.innovation_review import _normalise_ideas

REF_IDS = ("REF-01", "REF-02")
REF_SOURCES = {"REF-01": "paper-one", "REF-02": "paper-two"}
GOOD = (
    {"memory": ["on", "off"], "gate": ["on", "off"]},
    {"operators": ["all", "feature_only"]},
    {"min_delta": [0.005, 0.02]},
)


def _idea(idea_id, design):
    return {
        "idea_id": idea_id,
        "title": "Study %s" % idea_id,
        "problem": "a stated problem",
        "mechanism": "a stated mechanism",
        "novelty_claim": "a stated claim",
        "falsification": "if nothing moves, the claim is wrong",
        "risks": ["single dataset"],
        "evidence_refs": ["REF-01", "REF-02"],
        "experiment_plan": {
            "profile": "search_factorial",
            "dataset": "iris",
            "baseline": "incumbent cell",
            "metric": "improvement_per_evaluation",
            "stopping_rule": "fixed evaluation budget",
            "design": design,
        },
    }


def _payload(extra_design=None, extra_id="IDEA-04"):
    ideas = [_idea("IDEA-%02d" % (index + 1), design) for index, design in enumerate(GOOD)]
    if extra_design is not None:
        ideas.append(_idea(extra_id, extra_design))
    return {"gaps": [], "ideas": ideas}


def _run(payload):
    warnings = []
    ideas = _normalise_ideas(payload, list(REF_IDS), dict(REF_SOURCES), warnings)
    return ideas, warnings


class DesignPreFlightTest(unittest.TestCase):
    def test_a_registered_design_reports_its_cell_count(self):
        ideas, _warnings = _run(_payload())
        self.assertEqual(len(ideas), 3)
        checks = {idea["idea_id"]: idea["executable"] for idea in ideas}
        self.assertTrue(checks["IDEA-01"]["ok"], checks["IDEA-01"])
        # memory x gate is 4 cells once every unstated factor joins at its first level
        self.assertEqual(checks["IDEA-01"]["cells"], 4)

    def test_string_boolean_levels_pass_so_the_check_cannot_over_reject(self):
        # the registry stores True/False; a plan writing "on"/"off" is legitimate. A pre-flight that
        # failed those would refuse executable designs, which is as harmful as accepting bad ones
        ideas, warnings = _run(_payload(extra_design={"archive": ["off", "negative"]}))
        self.assertEqual(len(ideas), 4, warnings)
        self.assertTrue(ideas[3]["executable"]["ok"], ideas[3]["executable"])

    def test_an_unregistered_level_is_refused_before_any_round_is_spent(self):
        ideas, warnings = _run(_payload(extra_design={"archive": ["off", "on"]}))
        self.assertEqual(len(ideas), 3, "the unexecutable fourth idea must be dropped")
        self.assertNotIn("IDEA-04", [idea["idea_id"] for idea in ideas])
        self.assertTrue(
            any("unknown level 'on' for factor archive" in w for w in warnings), warnings
        )

    def test_a_design_over_the_cell_cap_is_refused_with_the_count(self):
        ideas, warnings = _run(
            _payload(
                extra_design={
                    "memory": ["on", "off"],
                    "gate": ["on", "off"],
                    "archive": ["off", "negative"],
                    "archive_window": ["all", "recent"],
                }
            )
        )
        self.assertEqual(len(ideas), 3)
        self.assertTrue(any("the limit is 12" in w for w in warnings), warnings)

    def test_a_numeric_factor_is_not_level_bound(self):
        # min_delta is a number control: 0.002 sits outside the illustrative list yet the runner
        # accepts it, so the pre-flight must not invent a membership rule the executor lacks
        ideas, warnings = _run(_payload(extra_design={"min_delta": [0.002, 0.005]}))
        self.assertEqual(len(ideas), 4, warnings)
        self.assertTrue(ideas[3]["executable"]["ok"], ideas[3]["executable"])


class PromptVocabularyTest(unittest.TestCase):
    """The pre-flight refuses invented levels; the prompt has to state them in the first place."""

    def test_the_levels_a_model_might_invent_are_named_as_invalid_by_the_prompt(self):
        from research_agent.innovation_review import plan_levels_block

        block = plan_levels_block()
        # measured inventions from the host-answered run; the prompt must now carry the real set
        self.assertIn("negative", block)
        self.assertIn("recent", block)
        self.assertIn("round_robin", block)
        self.assertNotIn("top2", block)
        self.assertNotIn("diversity_biased", block)

    def test_boolean_and_number_factors_are_described_by_how_the_runner_reads_them(self):
        from research_agent.innovation_review import plan_levels_block

        block = plan_levels_block()
        self.assertIn("memory: on | off", block)
        # min_delta is numeric: the registry list is illustrative, and saying otherwise would make
        # the prompt forbid plans the executor accepts
        self.assertIn("任意数值", block)
        self.assertIn("12", block)


if __name__ == "__main__":
    unittest.main()

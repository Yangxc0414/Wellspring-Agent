import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent import innovation_review
from tests.writing_support import RUN_ID, make_writing_project


class ReviewDestinationTest(unittest.TestCase):
    def test_output_dir_is_added_but_target_kept(self):
        from research_agent.innovation_review import _review_destinations

        target = Path('/tmp/project/runs/RUN-1')
        destinations = _review_destinations(target, Path('/tmp/project/innovation'))
        self.assertEqual(destinations, [target, Path('/tmp/project/innovation')])

    def test_same_directory_is_not_duplicated(self):
        from research_agent.innovation_review import _review_destinations

        self.assertEqual(_review_destinations('/tmp/run', '/tmp/run'), [Path('/tmp/run')])

    def test_no_output_dir_uses_target_only(self):
        from research_agent.innovation_review import _review_destinations

        self.assertEqual(_review_destinations('/tmp/run', None), [Path('/tmp/run')])


class NonSearchPlanTest(unittest.TestCase):
    def _idea(self, index):
        return {
            "title": "Idea %d" % index,
            "problem": "p",
            "mechanism": "m",
            "novelty_claim": "n",
            "falsification": "f",
            "evidence_refs": ["R1", "R2"],
            "risks": ["r"],
            "experiment_plan": {
                "profile": "local_tabular_experiment",
                "dataset": "user-provided commit CSV",
                "baseline": "b",
                "metric": "mean_diff",
                "stopping_rule": "s",
                "design": {"project": ["a", "b"]},
            },
        }

    def test_non_search_design_is_not_validated_against_search_factors(self):
        from research_agent.innovation_review import _normalise_ideas

        payload = {"ideas": [self._idea(1), self._idea(2), self._idea(3)]}
        ideas = _normalise_ideas(payload, {"R1", "R2"}, {"R1": "S1", "R2": "S2"})
        self.assertEqual(len(ideas), 3)
        self.assertTrue(all(idea["executable"].get("deferred_design") for idea in ideas))

    def test_search_profile_design_is_still_validated(self):
        from research_agent.innovation_review import InnovationReviewError, _normalise_ideas

        bad = self._idea(1)
        bad["experiment_plan"]["profile"] = "search_factorial"
        bad["experiment_plan"]["dataset"] = "iris"
        bad["experiment_plan"]["metric"] = "accuracy"
        payload = {"ideas": [bad, self._idea(2), self._idea(3)]}
        with self.assertRaises(InnovationReviewError):
            _normalise_ideas(payload, {"R1", "R2"}, {"R1": "S1", "R2": "S2"})


class InnovationReviewTest(unittest.TestCase):
    def test_design_levels_keep_their_json_scalar_types(self):
        design = innovation_review._normalise_design(
            {"gate": [False, True], "archive": ["off", "negative"], "min_delta": [0.02]}
        )
        self.assertEqual(design["gate"], [False, True])
        self.assertEqual(design["archive"], ["off", "negative"])
        self.assertEqual(design["min_delta"], [0.02])

    def test_the_run_topic_reaches_the_proposer_when_no_topic_is_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_writing_project(Path(tmp))
            run = project / "runs" / RUN_ID
            # Pipeline runs have no task goal; the topic lives in demo.json.
            (run / "task.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (run / "demo.json").write_text(
                json.dumps({"topic": "钙钛矿 界面 钝化 湿热稳定性"}), encoding="utf-8"
            )
            with mock.patch.object(
                innovation_review, "_propose", return_value=([], [], [])
            ) as propose:
                innovation_review.run_innovation_review(
                    project, RUN_ID, propose_only=True, model=object()
                )
            pack = propose.call_args[0][0]
            # A pack with task.goal=None used to make the prompt say "研究主题: 未提供".
            self.assertEqual(pack["task"]["goal"], "钙钛矿 界面 钝化 湿热稳定性")


if __name__ == "__main__":
    unittest.main()

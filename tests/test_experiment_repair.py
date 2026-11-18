"""Experiment shape-repair wrapper: one bounded retry with explicit errors."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent import cli  # noqa: E402


class ExperimentRepairTest(unittest.TestCase):
    def test_bad_shape_triggers_one_repair(self):
        calls = []

        def generator(payload):
            calls.append(dict(payload or {}))
            if len(calls) == 1:
                return {"primary_metric": "Repository task success rate measured by tests", "budget": "not specified"}
            return {"primary_metric": "success_rate", "budget": "3 seeds x 50 tasks"}

        wrapped = cli._wrap_with_experiment_repair(generator)
        draft = wrapped({"topic": "t"})
        self.assertEqual(len(calls), 2)
        self.assertEqual(draft["primary_metric"], "success_rate")
        self.assertIn("repair_errors", calls[1])
        self.assertTrue(any("primary_metric" in item for item in calls[1]["repair_errors"]))
        self.assertIn("previous_draft", calls[1])
        self.assertEqual(calls[0]["topic"], "t")

    def test_good_shape_is_not_repaired(self):
        calls = []

        def generator(payload):
            calls.append(dict(payload or {}))
            return {"primary_metric": "accuracy", "budget": "3 seeds x 1 split"}

        cli._wrap_with_experiment_repair(generator)({"topic": "t"})
        self.assertEqual(len(calls), 1)

    def test_non_dict_draft_is_returned_unchanged(self):
        wrapped = cli._wrap_with_experiment_repair(lambda payload: None)
        self.assertIsNone(wrapped({"topic": "t"}))


if __name__ == "__main__":
    unittest.main()

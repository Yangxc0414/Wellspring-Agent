"""The self-improvement loop must be able to state a number it can later be judged against.

Measured before these tests existed: `Candidate.predicted_metrics` was already in the data model,
already validated as numeric and finite, already read by the tracking layer and already serialised
into the story - but no documented command could fill it. So `rsi propose` produced episodes with
prose-only predictions, and a ledger built that way reported `calibration: uncalibrated` with the
warning "actuals recorded without numeric predictions", however many trials ran. A loop that cannot
be calibrated can accumulate rejections but cannot improve its own decision rule.

The second defect fixed here is provenance: episodes carried `simulation`, the tracking report even
computed an all-simulated flag, and the story's summary dropped both - so a reader of the headline
counts could not tell an exercised loop from an improved one. `simulation_episodes` counts them per
episode rather than all-or-nothing, because a mixed ledger is exactly where an all-or-nothing flag
would read as "real".
"""

import tempfile
import unittest
from pathlib import Path

from research_agent.cli import _predicted_metrics
from research_agent.rsi import (
    Candidate,
    RSIPolicyError,
    RSIController,
    StepLedger,
    ledger_story,
)


def candidate(metrics=None, patch="add a review subquery"):
    return Candidate(
        kind="skill", target="literature.query_planner", patch=patch,
        rationale="coverage was thin", predicted_effect="one more full-text source",
        predicted_metrics=dict(metrics or {}), parent_id="incumbent", scope="S1/zh_core_journal",
    )


class PredictedMetricParsingTest(unittest.TestCase):
    def test_repeatable_key_value_pairs_become_floats(self):
        self.assertEqual(
            _predicted_metrics(["recall=0.85", "cost=-0.02", " max_sources = 12 "]),
            {"recall": 0.85, "cost": -0.02, "max_sources": 12.0},
        )

    def test_nothing_declared_means_nothing_invented(self):
        self.assertEqual(_predicted_metrics([]), {})
        self.assertEqual(_predicted_metrics(None), {})

    def test_malformed_pairs_are_refused_with_the_offending_text(self):
        for bad in ("recall", "=0.5", "recall=", "recall=high"):
            with self.assertRaises(SystemExit, msg=bad) as ctx:
                _predicted_metrics([bad])
            self.assertIn(bad.split("=")[0] or bad, str(ctx.exception))

    def test_non_finite_predictions_are_refused(self):
        for bad in ("recall=inf", "recall=-inf", "recall=nan"):
            with self.assertRaises(SystemExit, msg=bad):
                _predicted_metrics([bad])


class NumericPredictionRoundTripTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "rsi-ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_numeric_prediction_survives_proposal_reload_and_projection(self):
        record = RSIController(StepLedger(self.path)).propose(
            candidate({"recall": 0.85, "cost": -0.02}), dry_run_ref="DRY-001"
        )
        self.assertEqual(record.candidate.predicted_metrics, {"recall": 0.85, "cost": -0.02})
        reloaded = StepLedger.load(self.path)
        self.assertEqual(
            reloaded.episodes[0].candidate.predicted_metrics, {"recall": 0.85, "cost": -0.02}
        )
        story = ledger_story(reloaded)
        episode = [e for e in story["episodes"] if e["episode_id"] == record.episode_id][0]
        self.assertEqual(episode["predicted_metrics"], {"recall": 0.85, "cost": -0.02})

    def test_the_model_itself_refuses_a_prediction_that_is_not_a_number(self):
        with self.assertRaises(RSIPolicyError):
            candidate({"recall": "high"})
        with self.assertRaises(RSIPolicyError):
            candidate({"recall": float("inf")})


class SimulationDisclosureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "rsi-ledger.json"
        self.controller = RSIController(StepLedger(self.path))

    def tearDown(self):
        self.tmp.cleanup()

    def _story(self):
        return ledger_story(StepLedger.load(self.path))

    def test_a_real_episode_is_not_labelled_simulated(self):
        self.controller.propose(candidate(), dry_run_ref="DRY-001")
        story = self._story()
        self.assertEqual(story["schema_version"], "rsi-story-0.4")
        self.assertEqual(story["summary"]["simulation_episodes"], 0)
        self.assertFalse(any("simulation=true" in w for w in story["warnings"]))

    def test_a_simulated_episode_announces_itself_in_the_summary(self):
        self.controller.propose(candidate(), dry_run_ref="DRY-001", simulation=True)
        story = self._story()
        self.assertEqual(story["summary"]["simulation_episodes"], 1)
        warning = [w for w in story["warnings"] if "simulation=true" in w]
        self.assertEqual(len(warning), 1)
        self.assertIn("not an improved one", warning[0])
        self.assertIn("capability gain", warning[0])

    def test_a_mixed_ledger_counts_rather_than_rounding_to_all_or_nothing(self):
        self.controller.propose(candidate(patch="real change"), dry_run_ref="DRY-001")
        self.controller.propose(candidate(patch="exercised change"), dry_run_ref="DRY-002",
                                simulation=True)
        story = self._story()
        self.assertEqual(story["summary"]["episodes"], 2)
        self.assertEqual(story["summary"]["simulation_episodes"], 1)


if __name__ == "__main__":
    unittest.main()

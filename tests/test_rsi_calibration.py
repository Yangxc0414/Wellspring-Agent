"""The calibration loop must be closable through documented commands, not just inside fixtures.

#96's shape: a field the audit layer reads but no documented command can write makes the evidence
permanently empty. `predicted_metrics` gained `rsi propose --predicted-metric`; `actuals` previously
was only written inside fixture/s5, so a human-proposed candidate could never be calibrated. The new
`rsi actuals` command closes that. These tests pin both the command surface and the behaviour.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_agent.rsi import Candidate, RSIController, StepLedger, ledger_story

REPO = Path(__file__).resolve().parents[1]


class CalibrationClosesTest(unittest.TestCase):
    def test_prediction_plus_actuals_on_one_episode_yields_tracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = StepLedger(Path(tmp) / "ledger.json")
            controller = RSIController(ledger)
            record = controller.propose(
                Candidate(
                    kind="skill", target="literature.query_planner", patch="p", rationale="r",
                    predicted_effect="e", predicted_metrics={"recall": 0.8},
                    parent_id="incumbent", scope="S1/zh",
                ),
                dry_run_ref="DRY-001",
            )
            controller.record_actuals(record.episode_id, {"recall": 0.7}, note="measured")
            story = ledger_story(StepLedger.load(Path(tmp) / "ledger.json"))
            tracking = story["tracking"]
            self.assertEqual(tracking["status"], "tracked")
            self.assertGreaterEqual(tracking["compared_episodes"], 1)
            self.assertNotIn(story["summary"]["calibration"], ("no_actuals", "uncalibrated"))

    def test_actuals_without_prediction_stays_uncalibrated_not_falsely_tracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = StepLedger(Path(tmp) / "ledger.json")
            controller = RSIController(ledger)
            record = controller.propose(
                Candidate(
                    kind="skill", target="x", patch="p", rationale="r", predicted_effect="e",
                    parent_id="i", scope="S1/zh",
                ),
                dry_run_ref="DRY-001",
            )
            controller.record_actuals(record.episode_id, {"recall": 0.7})
            story = ledger_story(StepLedger.load(Path(tmp) / "ledger.json"))
            self.assertEqual(story["tracking"]["status"], "uncalibrated")


class CommandSurfaceTest(unittest.TestCase):
    def _help(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "research_agent", "rsi", *args, "--help"],
            cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding="utf-8", errors="replace",
        )

    def test_propose_exposes_a_numeric_prediction_writer(self):
        proc = self._help("propose")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--predicted-metric", proc.stdout)

    def test_actuals_exposes_a_measured_outcome_writer(self):
        proc = self._help("actuals")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--metric", proc.stdout)
        self.assertIn("--episode", proc.stdout)


if __name__ == "__main__":
    unittest.main()

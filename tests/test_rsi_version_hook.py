"""Platform<->self-evolution version hook: episodes bind platform fingerprint + candidate version."""
import tempfile
import unittest
from pathlib import Path

from research_agent.paths import build_fingerprint
from research_agent.rsi import Candidate, RSIController, StepLedger


class VersionHookTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self._tmp.name) / "ledger.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_propose_binds_platform_fingerprint_and_candidate_version(self):
        ledger = StepLedger(self.ledger_path)
        controller = RSIController(ledger)
        cand = Candidate(
            kind="skill", target="literature.query_planner", patch="p", rationale="r",
            predicted_effect="e", version="v1.2.3",
        )
        record = controller.propose(cand)
        self.assertEqual(record.platform_fingerprint, build_fingerprint())
        self.assertEqual(record.candidate.version, "v1.2.3")
        self.assertTrue(ledger.verify_events()["ok"])

    def test_version_and_fingerprint_persist_across_reload(self):
        ledger = StepLedger(self.ledger_path)
        controller = RSIController(ledger)
        record = controller.propose(Candidate(
            kind="skill", target="t", patch="p", rationale="r", predicted_effect="e",
            version="v2.0",
        ))
        reloaded = StepLedger.load(self.ledger_path)
        found = reloaded.find(record.episode_id)
        self.assertEqual(found.candidate.version, "v2.0")
        self.assertEqual(found.platform_fingerprint, build_fingerprint())

    def test_default_version_empty_and_fingerprint_still_set(self):
        controller = RSIController(StepLedger(self.ledger_path))
        record = controller.propose(Candidate(
            kind="skill", target="t", patch="p", rationale="r", predicted_effect="e",
        ))
        self.assertEqual(record.candidate.version, "")
        self.assertTrue(record.platform_fingerprint)


if __name__ == "__main__":
    unittest.main()
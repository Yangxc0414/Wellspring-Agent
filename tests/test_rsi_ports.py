"""Decoupling seams: external ProposerPort/EvaluatorPort implementations must flow
through the governed control plane, and every EvalEvidence binds a code fingerprint."""
import tempfile
import unittest
from pathlib import Path

from research_agent.paths import build_fingerprint
from research_agent.ports import EvaluatorPort, ProposerPort
from research_agent.rsi import Candidate, EvalEvidence, RSIController, StepLedger


class FakeProposer:
    proposer_id = "fake-external"

    def propose(self, observation: str):
        return [Candidate(kind="skill", target="literature.query_planner", patch="p",
                          rationale=observation, predicted_effect="e", version="v9")]


class FakeEvaluator:
    evaluator_id = "fake-eval"

    def evaluate(self, candidate, split):
        return EvalEvidence(split=split, status="passed", artifact_ref="art-" + split,
                            metrics={"recall": 1.0}, evaluator=self.evaluator_id)


class PortsSeamTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "ledger.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_fake_ports_satisfy_protocols(self):
        self.assertIsInstance(FakeProposer(), ProposerPort)
        self.assertIsInstance(FakeEvaluator(), EvaluatorPort)

    def test_external_proposer_and_evaluator_flow_through_control_plane(self):
        controller = RSIController(StepLedger(self.path))
        proposer, evaluator = FakeProposer(), FakeEvaluator()
        cand = proposer.propose("thin coverage")[0]
        record = controller.propose(cand)
        self.assertEqual(record.candidate.version, "v9")
        pub = evaluator.evaluate(cand, "public")
        hid = evaluator.evaluate(cand, "hidden")
        controller.evaluate(record.episode_id, pub, hid)
        reloaded = StepLedger.load(self.path).find(record.episode_id)
        self.assertEqual(reloaded.public_eval.evaluator, "fake-eval")
        self.assertTrue(reloaded.public_eval.code_fingerprint)

    def test_eval_evidence_auto_binds_code_fingerprint(self):
        ev = EvalEvidence(split="public", status="passed", artifact_ref="a")
        self.assertEqual(ev.code_fingerprint, build_fingerprint())
        explicit = EvalEvidence(split="public", status="passed", artifact_ref="a",
                                code_fingerprint="deadbeef" * 8)
        self.assertEqual(explicit.code_fingerprint, "deadbeef" * 8)


if __name__ == "__main__":
    unittest.main()
import tempfile
import unittest
from pathlib import Path

from research_agent.model_batch import run_model_batch
from research_agent.rsi import Candidate


class ModelBatchTest(unittest.TestCase):
    def test_batch_records_eligibility_and_errors(self):
        def propose(observation):
            if "fail" in observation:
                raise ValueError("bad observation")
            return Candidate(
                kind="process",
                target="literature.retrieval.budget",
                patch='{"retriever":"minilm","max_sources":3}',
                rationale="stub",
                predicted_effect="stub",
                scope="S1/model-proposal",
            )

        def evaluate(candidate, ledger, output, approve):
            return {
                "decision": "pending_human",
                "chosen": "CAND-STUB",
                "would_accept": True,
                "candidates": [{"decision": "pending_human"}],
                "rsi_report": {"capability_claims": []},
            }

        with tempfile.TemporaryDirectory() as tmp:
            report = run_model_batch(
                None,
                ["ok observation", "fail observation"],
                Path(tmp) / "out",
                Path(tmp) / "ledgers",
                propose_fn=propose,
                evaluate_fn=evaluate,
            )
            self.assertEqual(report["observations"], 2)
            self.assertEqual(report["eligible"], 1)
            self.assertEqual(report["errors"], 1)
            self.assertTrue((Path(tmp) / "out" / "candidate-00.json").is_file())
            self.assertTrue((Path(tmp) / "out" / "model-batch.json").is_file())


if __name__ == "__main__":
    unittest.main()

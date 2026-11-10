"""The frontend gate chain must equal the backend admission timeline.

The orchestration strip used to hand-type "dry-run → public → hidden → regression → human" and
silently drop near_ood - the environment the agent-level archive says must be primary. The chain now
lives in apps/web/src/domain/rsiSemantics.ts; this test reads that constant and compares it with the
timeline the backend actually produces, so the two faces cannot drift apart again. It is a
cross-language guard on purpose: a TS-only test would let the backend change unnoticed.
"""

import re
import tempfile
import unittest
from pathlib import Path

from research_agent.rsi import Candidate, RSIController, StepLedger, ledger_story

SEMANTICS = Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "domain" / "rsiSemantics.ts"


def frontend_chain():
    text = SEMANTICS.read_text(encoding="utf-8")
    block = text.split("RSI_GATE_CHAIN = [", 1)[1].split("]", 1)[0]
    return re.findall(r'"([a-z_-]+)"', block)


class GateChainParityTest(unittest.TestCase):
    def test_the_frontend_chain_equals_the_backend_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            RSIController(StepLedger(path)).propose(
                Candidate(
                    kind="skill", target="literature.query_planner", patch="p", rationale="r",
                    predicted_effect="e", parent_id="incumbent", scope="S1/zh",
                ),
                dry_run_ref="DRY-001",
            )
            story = ledger_story(StepLedger.load(path))
        backend = [step["id"] for step in story["timeline"]
                   if step["id"] not in ("observe", "candidate")]
        self.assertEqual(frontend_chain(), backend)

    def test_the_chain_keeps_the_primary_environment(self):
        self.assertIn("near_ood", frontend_chain())


if __name__ == "__main__":
    unittest.main()

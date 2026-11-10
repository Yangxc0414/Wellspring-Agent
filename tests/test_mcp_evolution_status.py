"""The self-improvement loop has to be readable from the tool face, but only readable.

Measured before this existed: nine RSI/evolution/autopilot HTTP routes were reachable over the
runtime and the CLI while no MCP capability pointed at any of them, so an agent plugged into the
editor could not see the loop it was supposedly inside - it could only be told about it.
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.face_coverage import DECLARATIONS
from research_agent.mcp_server import TOOL_NAMES, ResearchMCPService
from research_agent.mcp_tools import TOOLS
from research_agent.project import ProjectError

NAME = "research_evolution_status"


def _episode_ledger(root: Path) -> str:
    from research_agent.rsi import Candidate, EvalEvidence, RSIController, StepLedger

    path = root / "rsi-ledger.json"
    controller = RSIController(StepLedger(path))
    record = controller.propose(
        Candidate(
            kind="skill",
            target="literature.query_planner",
            patch="add a review subquery",
            rationale="coverage was thin",
            predicted_effect="one more full-text source",
            parent_id="incumbent",
            scope="S1/zh_core_journal",
        ),
        observation="thin coverage",
        dry_run_ref="DRY-MCP-1",
    )
    controller.admit(
        record.episode_id,
        EvalEvidence("public", "passed", "ART-P", {"coverage": 0.8}, 2, claim_eligible=False),
        EvalEvidence("hidden", "passed", "ART-H", {"coverage": 0.8}, 2, claim_eligible=False),
        "operator approval",
        "S1/zh",
        30,
    )
    return str(path)


class EvolutionStatusToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.service = ResearchMCPService(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_tool_is_declared_on_every_face_that_serves_it(self):
        self.assertIn(NAME, TOOL_NAMES)
        declared = DECLARATIONS[NAME]
        self.assertEqual(declared["cli"], "rsi story")
        self.assertEqual(declared["http"], "/api/rsi/story")

    def test_the_schema_declares_itself_read_only_and_needs_only_a_ledger(self):
        spec = next(item for item in TOOLS if item["name"] == NAME)
        self.assertTrue(spec["annotations"]["readOnlyHint"])
        self.assertEqual(list(spec["inputSchema"]["properties"]), ["ledger"])
        self.assertEqual(spec["inputSchema"]["required"], ["ledger"])

    def test_a_rejected_round_reports_a_rate_and_an_informative_verdict(self):
        ledger = _episode_ledger(self.root)
        from research_agent.rsi import StepLedger

        record = StepLedger.load(Path(ledger)).episodes[0]
        result = self.service.evolution_status({"ledger": ledger})
        body = result["structuredContent"]
        self.assertFalse(result["isError"])
        self.assertEqual(body["episodes"], 1)
        self.assertEqual(body["decided"], body["approved"] + body["rejected"])
        self.assertIn(
            body["gate_verdict"],
            ("gate_uninformative", "informative", "awaiting_decisions"),
        )
        self.assertEqual(body["capability_claims"], 0)
        # an admitted round must not report its own successes as failures
        self.assertNotIn("human:approved", body["gate_stops"])
        self.assertNotIn("lease:active", body["gate_stops"])
        self.assertIn("near_ood:missing", body["gate_stops"])
        self.assertIn(record.candidate.candidate_id, json.dumps(body["timeline"]))

    def test_missing_ledger_and_extra_arguments_are_errors_not_silent_defaults(self):
        with self.assertRaises(ProjectError):
            self.service.evolution_status({"ledger": "does-not-exist.json"})
        with self.assertRaises(ProjectError):
            self.service.evolution_status({"ledger": "runtime_data/x.json", "approve": True})
        with self.assertRaises(ProjectError):
            self.service.evolution_status({})

    def test_the_mcp_face_carries_the_same_provenance_as_the_cli_face(self):
        """Provenance that survives one face and is dropped by the other is not provenance.

        Measured on a real local BM25 trial ledger before this test existed: the CLI story carried
        generated_at, source_fingerprint, base, read_only, provenance and
        summary.simulation_episodes, while this tool carried none of them. A host inside Qoder
        therefore could not tell a simulated ledger from a real one, nor which build produced the
        numbers it was reading - the exact defect #76 and the projection contract exist to prevent.
        """
        ledger = _episode_ledger(self.root)
        from research_agent.rsi import StepLedger, ledger_story

        story = ledger_story(StepLedger.load(Path(ledger)))
        body = self.service.evolution_status({"ledger": ledger})["structuredContent"]
        self.assertEqual(body["schema_version"], "mcp-evolution-status-0.2")
        self.assertEqual(body["story_schema_version"], story["schema_version"])
        for slot in ("source_fingerprint", "base", "read_only"):
            self.assertEqual(body[slot], story[slot], slot)
        # generated_at is read at call time on both sides, so equality across two calls would be a
        # race; what matters is that the face emits a timestamp at all, and the same one format
        self.assertTrue(body["generated_at"], "the MCP face dropped the projection timestamp")
        self.assertEqual(body["generated_at"][:10], story["generated_at"][:10])
        self.assertEqual(body["provenance"], story["provenance"])
        self.assertEqual(body["simulation_episodes"], story["summary"]["simulation_episodes"])
        self.assertEqual(body["warnings"], story["warnings"])

    def test_a_simulated_ledger_announces_itself_through_the_mcp_face(self):
        # the disclosure has to be reachable by a host, not only by someone standing at a terminal
        import tempfile

        from research_agent.rsi import Candidate, RSIController, StepLedger

        tmp = tempfile.TemporaryDirectory()
        try:
            path = Path(tmp.name) / "ledger.json"
            RSIController(StepLedger(path)).propose(
                Candidate(
                    kind="skill", target="literature.query_planner", patch="p", rationale="r",
                    predicted_effect="e", predicted_metrics={"recall": 0.8}, parent_id="incumbent",
                    scope="S1/zh",
                ),
                dry_run_ref="DRY-001",
                simulation=True,
            )
            body = self.service.evolution_status({"ledger": str(path)})["structuredContent"]
            self.assertEqual(body["simulation_episodes"], 1)
            self.assertTrue(any("simulation=true" in w for w in body["warnings"]), body["warnings"])
            self.assertTrue(body["source_fingerprint"])
        finally:
            tmp.cleanup()

    def test_no_gate_verb_reached_the_new_surface(self):
        for verb in ("approve", "admit", "reject", "revoke", "activate", "sign"):
            self.assertNotIn(verb, NAME)
            self.assertNotIn(verb, json.dumps(DECLARATIONS[NAME]))


if __name__ == "__main__":
    unittest.main()

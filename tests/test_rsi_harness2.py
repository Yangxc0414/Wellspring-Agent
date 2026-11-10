"""The Harness² seam: contract, mapping and the pending-only boundary.

These tests never need Harness² installed: they exercise the platform half with a
synthetic artifact whose shape matches the real one. One optional test validates the
committed artifact when a local run has produced it.
"""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research_agent import rsi_harness2
from research_agent.cli import build_parser
from research_agent.evolution_policy import EvolutionPolicyError
from research_agent.rsi import StepLedger


def _artifact():
    diff = (
        "--- a/scripts/coverage.py\n"
        "+++ b/scripts/coverage.py\n"
        "@@ -7,3 +7,4 @@\n"
        "-known = {span['span_id'] for span in spans}\n"
        "+index = {(span['claim_id'], span['span_id']): span for span in spans}\n"
    )
    return {
        "schema": "harness2-run-0.1",
        "generated_at": "2026-11-10T00:00:00Z",
        "harness2": {"root": "/opt/harness2", "method_version": 2, "package_version": "0.1.0"},
        "run": {
            "adapter": "science",
            "executor": "deterministic-science-fixture",
            "k": 2,
            "modes": ["agg", "seq"],
            "exit_code": 0,
            "wall_s": 12.0,
        },
        "tasks": [
            {"task_id": "claims-1", "domain": "claim-audit", "status": "ok"},
            {"task_id": "claims-2", "domain": "claim-audit", "status": "ok"},
        ],
        "budget": {"R": 16, "expected_R": 16, "P": 12, "expected_P": 12, "usd": 0.0},
        "fallbacks": [],
        "adopted": [
            {
                "task_id": "claims-1",
                "mode": "agg",
                "label": "agg2",
                "adopted_sha256": "a" * 64,
                "notes": "join on the pair",
                "lesson": "Join on (claim_id, span_id).",
                "changes": [{"path": "scripts/coverage.py", "diff": diff}],
            },
            {
                "task_id": "claims-2",
                "mode": "seq",
                "label": "c2",
                "adopted_sha256": "a" * 64,
                "notes": "join on the pair",
                "lesson": "Join on (claim_id, span_id).",
                "changes": [{"path": "scripts/coverage.py", "diff": diff}],
            },
        ],
        "held_out": {"n": 1, "passed": 1, "base_passed": 0, "delta": 1},
        "lessons": [
            {
                "task_id": "claims-1",
                "lesson": "Join on (claim_id, span_id).",
                "evidence": "scripts/coverage.py contrast",
            }
        ],
        "surface": {
            "components": {
                "c1 system prompt": 1,
                "c2 guardrails": 1,
                "c3 memory": 1,
                "c4 tool guidance": 1,
                "c5 subagents": 0,
                "c6 skills": 0,
                "c7 scripts": 1,
                "c8 plugins": 0,
            }
        },
        "shims": [{"name": "fcntl.flock"}],
        "classification": {"simulation": True, "claim_eligible": False},
        "task_pack_sha256": "b" * 64,
    }


class ProbeTest(unittest.TestCase):
    def test_missing_checkout_is_a_state_not_an_exception(self):
        status = rsi_harness2.probe(root=str(Path(tempfile.gettempdir()) / "no-harness2-here"))
        self.assertFalse(status["available"])
        self.assertIn("not found", status["reason"])
        self.assertEqual(status["schema"], "harness2-seam-0.1")

    def test_probe_reports_the_platform_python_it_runs_on(self):
        status = rsi_harness2.probe()
        self.assertTrue(status["platform_python"].startswith("3."))
        self.assertIn("adapters", status)


class ArtifactContractTest(unittest.TestCase):
    def test_valid_artifact_passes(self):
        self.assertEqual(rsi_harness2.validate_artifact(_artifact()), [])

    def test_schema_is_frozen(self):
        payload = _artifact()
        payload["schema"] = "harness2-run-0.2"
        self.assertTrue(any("schema" in item for item in rsi_harness2.validate_artifact(payload)))

    def test_claim_eligible_must_stay_false(self):
        payload = _artifact()
        payload["classification"]["claim_eligible"] = True
        problems = rsi_harness2.validate_artifact(payload)
        self.assertTrue(any("claim_eligible" in item for item in problems))

    def test_task_pack_hash_must_be_sha256(self):
        payload = _artifact()
        payload["task_pack_sha256"] = "short"
        self.assertTrue(any("task_pack_sha256" in item for item in rsi_harness2.validate_artifact(payload)))

    def test_surface_needs_six_components(self):
        payload = _artifact()
        payload["surface"]["components"] = {"c1": 1}
        self.assertTrue(any("surface.components" in item for item in rsi_harness2.validate_artifact(payload)))

    def test_missing_budget_is_rejected(self):
        payload = _artifact()
        del payload["budget"]["expected_P"]
        self.assertTrue(any("budget.expected_P" in item for item in rsi_harness2.validate_artifact(payload)))


class ConformanceTest(unittest.TestCase):
    def test_all_checks_pass_on_a_clean_run(self):
        checklist = rsi_harness2.conformance(_artifact())
        failed = [item for item in checklist if not item["ok"]]
        self.assertEqual(failed, [])

    def test_budget_mismatch_is_named(self):
        payload = _artifact()
        payload["budget"]["R"] = 15
        checklist = {item["id"]: item for item in rsi_harness2.conformance(payload)}
        self.assertFalse(checklist["budget"]["ok"])
        self.assertIn("R=15/16", checklist["budget"]["detail"])

    def test_fallback_and_failed_task_are_named(self):
        payload = _artifact()
        payload["fallbacks"] = ["claims-1/agg/inv1"]
        payload["tasks"][0]["status"] = "partial"
        checklist = {item["id"]: item for item in rsi_harness2.conformance(payload)}
        self.assertFalse(checklist["fallback"]["ok"])
        self.assertFalse(checklist["tasks"]["ok"])


class CandidateMappingTest(unittest.TestCase):
    def test_same_edit_on_two_runs_becomes_one_candidate(self):
        candidates, blocked = rsi_harness2.to_candidates(_artifact())
        self.assertEqual(blocked, [])
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.target, "harness2.harness/scripts/coverage.py")
        self.assertEqual(candidate.scope, "harness2.harness")
        self.assertEqual(candidate.kind, "process")
        self.assertIn("claims-1/agg", candidate.rationale)
        self.assertIn("claims-2/seq", candidate.rationale)

    def test_component_path_on_an_immutable_surface_is_blocked(self):
        payload = _artifact()
        for entry in payload["adopted"]:
            entry["changes"][0]["path"] = "skills/claim_writer/SKILL.md"
        candidates, blocked = rsi_harness2.to_candidates(payload)
        self.assertEqual(candidates, [])
        self.assertEqual(len(blocked), 1)
        self.assertIn("immutable surface", blocked[0]["reason"])

    def test_prompt_component_maps_to_prompt_kind(self):
        payload = _artifact()
        payload["adopted"][0]["changes"][0]["path"] = "systemprompt.md"
        candidates, _ = rsi_harness2.to_candidates(payload)
        self.assertEqual(candidates[0].kind, "prompt")


class EvidenceMappingTest(unittest.TestCase):
    def test_evidence_is_simulation_and_never_claimable(self):
        public, hidden = rsi_harness2.to_evidence(_artifact())
        self.assertTrue(public.simulation)
        self.assertFalse(public.claim_eligible)
        self.assertEqual(public.split, "public")
        self.assertEqual(public.status, "passed")
        self.assertTrue(hidden.simulation)
        self.assertFalse(hidden.claim_eligible)
        self.assertEqual(hidden.split, "hidden")

    def test_no_holdout_means_no_hidden_evidence(self):
        payload = _artifact()
        payload["held_out"] = {"n": 0}
        _, hidden = rsi_harness2.to_evidence(payload)
        self.assertIsNone(hidden)

    def test_failed_task_makes_public_fail(self):
        payload = _artifact()
        payload["tasks"][0]["status"] = "failed"
        public, _ = rsi_harness2.to_evidence(payload)
        self.assertEqual(public.status, "failed")


class RecordBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="harness2-seam-"))
        self.ledger = self.root / "ledger.json"
        self.policy = self.root / "policy.json"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_record_writes_pending_episodes_only(self):
        result = rsi_harness2.record_episode(
            _artifact(), self.ledger, policy_path=self.policy
        )
        self.assertEqual(len(result["episodes"]), 1)
        self.assertEqual(result["public_status"], "passed")
        self.assertTrue(result["hidden_present"])
        ledger = StepLedger.load(self.ledger)
        self.assertEqual(len(ledger.episodes), 1)
        self.assertEqual(ledger.episodes[0].decision, "pending_human")
        self.assertEqual(ledger.leases, [])
        self.assertEqual(ledger.confirmations, [])

    def test_record_refuses_a_disabled_policy(self):
        self.policy.write_text(json.dumps({"enabled": False}), encoding="utf-8")
        with self.assertRaises(EvolutionPolicyError):
            rsi_harness2.record_episode(_artifact(), self.ledger, policy_path=self.policy)
        self.assertFalse(self.ledger.exists())

    def test_record_refuses_a_partial_run(self):
        payload = _artifact()
        payload["fallbacks"] = ["claims-1/agg/inv1"]
        with self.assertRaises(rsi_harness2.Harness2Error):
            rsi_harness2.record_episode(payload, self.ledger, policy_path=self.policy)
        self.assertFalse(self.ledger.exists())


class CliSurfaceTest(unittest.TestCase):
    def test_harness2_commands_exist(self):
        parser = build_parser()
        namespace = parser.parse_args(["rsi", "harness2", "probe"])
        self.assertEqual(namespace.harness2_command, "probe")
        self.assertEqual(namespace.func.__name__, "_cmd_rsi_harness2")
        record = parser.parse_args(["rsi", "harness2", "record"])
        self.assertEqual(record.scope, "harness2.harness")

    def test_record_help_documents_the_scope_flag(self):
        parser = build_parser()
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            with self.assertRaises(SystemExit):
                parser.parse_args(["rsi", "harness2", "record", "--help"])
        text = buffer.getvalue()
        self.assertIn("--scope", text)
        self.assertIn("--ledger", text)


class CommittedArtifactTest(unittest.TestCase):
    """If a real run exists on this checkout, its contract must still hold."""

    def test_public_story_carries_no_absolute_paths(self):
        status = {
            "available": True,
            "reason": "ready",
            "root": "/opt/harness2",
            "interpreter": {"version": "3.12.10", "source": "py -3.12", "path": "/opt/py"},
            "bridge": {"path": "/repo/scripts/harness2_run.py", "exists": True},
            "package": {"version": "0.1.0"},
            "adapters": ["science"],
            "platform_python": "3.8.7",
            "shims": [],
        }
        story = rsi_harness2.public_story(_artifact(), status=status)
        text = json.dumps(story, ensure_ascii=False)
        self.assertNotIn("/opt/", text)
        self.assertNotIn("/repo/", text)
        self.assertNotIn("artifact_ref", story.get("held_out", {}))
        self.assertEqual(story["probe"]["root_name"], "harness2")

    def test_latest_artifact_matches_the_contract(self):
        path = rsi_harness2.DEFAULT_ARTIFACT_PATH
        if not path.is_file():
            self.skipTest("no local Harness² artifact")
        payload = rsi_harness2.load_artifact(path)
        self.assertEqual(rsi_harness2.validate_artifact(payload), [])
        story = rsi_harness2.summarize(payload)
        self.assertTrue(story["checklist_ok"])
        self.assertEqual(story["budget"]["R"], story["budget"]["expected_R"])


if __name__ == "__main__":
    unittest.main()

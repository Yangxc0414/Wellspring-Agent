"""Two-track version management: agent harness generations and platform generations."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research_agent import evolution_generations as gens
from research_agent.cli import build_parser
from research_agent.paths import build_fingerprint

TREE_A = "a" * 64
TREE_B = "b" * 64


class GenerationStoreTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="evolution-gen-"))
        self.path = self.root / "generations.json"

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def store(self):
        return gens.GenerationStore.load(self.path)

    def test_agent_generation_needs_a_tree_hash_when_adopted(self):
        store = self.store()
        with self.assertRaises(gens.GenerationError):
            store.open(kind="agent", label="no tree", status="adopted")
        generation = store.open(
            kind="agent", label="with tree", status="adopted", agent_tree_sha=TREE_A
        )
        self.assertEqual(generation.status, "adopted")
        self.assertEqual(generation.platform_fingerprint, build_fingerprint())

    def test_platform_snapshot_supersedes_the_previous_one(self):
        store = self.store()
        first = gens.platform_snapshot(store, "baseline", commit="abc1234", fingerprint="1" * 16)
        second = gens.platform_snapshot(store, "next", commit="def5678", fingerprint="2" * 16)
        reloaded = self.store()
        self.assertEqual(reloaded.get(first.generation_id).status, "superseded")
        self.assertEqual(reloaded.get(first.generation_id).note, "superseded by next")
        self.assertEqual(reloaded.get(second.generation_id).status, "adopted")
        self.assertEqual(reloaded.get(second.generation_id).parent_id, first.generation_id)

    def test_snapshot_of_the_same_state_is_rejected(self):
        store = self.store()
        gens.platform_snapshot(store, "baseline", fingerprint="3" * 16)
        with self.assertRaises(gens.GenerationError):
            gens.platform_snapshot(store, "again", fingerprint="3" * 16)

    def test_agent_generations_chain_by_parent(self):
        store = self.store()
        first = store.open(kind="agent", label="g1", status="adopted", agent_tree_sha=TREE_A)
        second = store.open(kind="agent", label="g2", status="adopted", agent_tree_sha=TREE_B)
        self.assertEqual(second.parent_id, first.generation_id)

    def test_compare_reports_tree_change_and_deltas(self):
        store = self.store()
        first = store.open(kind="agent", label="g1", status="adopted", agent_tree_sha=TREE_A)
        second = store.open(
            kind="agent",
            label="g2",
            status="adopted",
            agent_tree_sha=TREE_B,
            candidate_ids=["CAND-1", "CAND-2"],
            episode_ids=["EP-1"],
        )
        diff = store.compare(first.generation_id, second.generation_id)
        self.assertTrue(diff["tree_changed"])
        self.assertEqual(diff["candidates_delta"], 2)
        self.assertEqual(diff["episodes_delta"], 1)

    def test_compare_rejects_mixed_tracks(self):
        store = self.store()
        agent = store.open(kind="agent", label="g1", status="adopted", agent_tree_sha=TREE_A)
        platform = gens.platform_snapshot(store, "p1", fingerprint="4" * 16)
        with self.assertRaises(gens.GenerationError):
            store.compare(agent.generation_id, platform.generation_id)

    def test_close_superseded_needs_a_newer_adopted_generation(self):
        store = self.store()
        only = store.open(kind="agent", label="g1", status="adopted", agent_tree_sha=TREE_A)
        with self.assertRaises(gens.GenerationError):
            store.close(only.generation_id, "superseded")

    def test_revert_is_recorded_with_a_note(self):
        store = self.store()
        generation = store.open(kind="agent", label="g1", status="adopted", agent_tree_sha=TREE_A)
        store.close(generation.generation_id, "reverted", note="regressed on the held-out split")
        reloaded = self.store().get(generation.generation_id)
        self.assertEqual(reloaded.status, "reverted")
        self.assertIn("held-out", reloaded.note)
        self.assertTrue(reloaded.closed_at)


class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="evolution-verify-"))
        self.path = self.root / "generations.json"
        self.store = gens.GenerationStore.load(self.path)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_clean_ledger_reports_ok(self):
        gens.platform_snapshot(
            self.store, "baseline", commit="abc1234", fingerprint=build_fingerprint()
        )
        self.store.open(kind="agent", label="g1", status="adopted", agent_tree_sha=TREE_A)
        report = self.store.verify()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["warnings"], [])

    def test_agent_from_another_platform_is_flagged_for_revalidation(self):
        generation = self.store.open(
            kind="agent",
            label="g1",
            status="adopted",
            agent_tree_sha=TREE_A,
            platform_fingerprint="0" * 16,
        )
        report = self.store.verify(current_fingerprint="f" * 16)
        self.assertEqual(report["stale_agents"], [generation.generation_id])
        self.assertTrue(
            any("re-validate" in warning for warning in report["warnings"]),
            report["warnings"],
        )

    def test_platform_drift_is_named(self):
        gens.platform_snapshot(self.store, "baseline", fingerprint="1" * 16)
        report = self.store.verify(current_fingerprint="2" * 16)
        self.assertTrue(any("record a new platform generation" in w for w in report["warnings"]))

    def test_missing_parent_is_an_error(self):
        self.store.open(
            kind="agent", label="orphan", status="adopted", agent_tree_sha=TREE_A, parent_id="GEN-missing"
        )
        report = self.store.verify()
        self.assertFalse(report["ok"])
        self.assertTrue(any("missing parent" in error for error in report["errors"]))

    def test_event_chain_is_hash_linked(self):
        self.store.open(kind="agent", label="g1", status="adopted", agent_tree_sha=TREE_A)
        self.store.open(kind="agent", label="g2", status="adopted", agent_tree_sha=TREE_B)
        chain = self.store.verify_events()
        self.assertTrue(chain["ok"], chain)
        self.assertEqual(chain["count"], 2)


class RunToGenerationTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="evolution-run-"))
        self.store = gens.GenerationStore.load(self.root / "generations.json")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _artifact(self):
        return {
            "budget": {"R": 8, "expected_R": 8, "P": 6, "expected_P": 6},
            "tasks": [{"task_id": "claims-1", "status": "ok"}],
            "adopted": [{"task_id": "claims-1", "adopted_sha256": TREE_A, "changes": []}],
            "held_out": {"n": 1, "passed": 1, "base_passed": 0},
            "classification": {"simulation": True, "claim_eligible": False},
            "platform_fingerprint": "9" * 16,
            "run": {"adapter": "science"},
        }

    def test_run_becomes_an_agent_generation_linked_to_its_platform(self):
        artifact = self.root / "run.json"
        artifact.write_text(json.dumps(self._artifact()), encoding="utf-8")
        generation = gens.agent_generation_from_run(
            self.store, self._artifact(), "claims fixture", artifact_path=artifact, episode_ids=["EP-1"]
        )
        self.assertEqual(generation.kind, "agent")
        self.assertEqual(generation.agent_tree_sha, TREE_A)
        self.assertEqual(generation.platform_fingerprint, "9" * 16)
        self.assertEqual(generation.episode_ids, ["EP-1"])
        self.assertTrue(generation.evidence["budget_identity"])
        self.assertTrue(generation.evidence["simulation"])
        self.assertEqual(len(generation.artifact_sha256), 64)

    def test_a_run_without_an_adopted_tree_cannot_be_versioned(self):
        payload = self._artifact()
        payload["adopted"] = []
        with self.assertRaises(gens.GenerationError):
            gens.agent_generation_from_run(self.store, payload, "empty")

    def test_the_same_tree_on_a_new_platform_supersedes_the_older_record(self):
        first = self.store.open(
            kind="agent",
            label="g1",
            status="adopted",
            agent_tree_sha=TREE_A,
            platform_fingerprint="1" * 16,
        )
        payload = self._artifact()
        payload["platform_fingerprint"] = "2" * 16
        second = gens.agent_generation_from_run(self.store, payload, "g2")
        reloaded = gens.GenerationStore.load(self.store.path)
        self.assertEqual(reloaded.get(first.generation_id).status, "superseded")
        self.assertIn("re-validated on platform", reloaded.get(first.generation_id).note)
        self.assertEqual(reloaded.get(second.generation_id).status, "adopted")
        report = reloaded.verify(current_fingerprint="2" * 16)
        self.assertEqual(report["stale_agents"], [])

    def test_patch_proposal_records_whether_it_applies(self):
        patch = self.root / "change.patch"
        patch.write_text("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n", encoding="utf-8")
        generation = gens.propose_platform_patch(
            self.store, "tidy x", patch, applies=False
        )
        self.assertEqual(generation.status, "proposed")
        self.assertFalse(generation.evidence["applies_cleanly"])
        self.assertEqual(len(generation.artifact_sha256), 64)


class StoryTest(unittest.TestCase):
    def test_story_has_both_tracks_and_a_boundary(self):
        root = Path(tempfile.mkdtemp(prefix="evolution-story-"))
        try:
            store = gens.GenerationStore.load(root / "generations.json")
            gens.platform_snapshot(store, "baseline", commit="abc1234")
            store.open(kind="agent", label="g1", status="adopted", agent_tree_sha=TREE_A)
            story = store.story()
            self.assertEqual(story["schema"], "evolution-story-0.1")
            self.assertEqual(len(story["tracks"]["platform"]), 1)
            self.assertEqual(len(story["tracks"]["agent"]), 1)
            self.assertIn("never applies a patch", story["boundary"])
            self.assertEqual(story["current"]["fingerprint"], build_fingerprint())
        finally:
            shutil.rmtree(root, ignore_errors=True)


class CliSurfaceTest(unittest.TestCase):
    def test_gen_subcommands_parse(self):
        parser = build_parser()
        snapshot = parser.parse_args(["rsi", "gen", "snapshot", "--label", "x"])
        self.assertEqual(snapshot.gen_command, "snapshot")
        self.assertEqual(snapshot.func.__name__, "_cmd_rsi_gen")
        agent = parser.parse_args(["rsi", "gen", "agent", "--label", "x"])
        self.assertEqual(agent.status, "adopted")
        record = parser.parse_args(["rsi", "harness2", "record", "--generation", "run-1"])
        self.assertEqual(record.generation, "run-1")


if __name__ == "__main__":
    unittest.main()

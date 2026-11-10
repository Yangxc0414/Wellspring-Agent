import json
import tempfile
import unittest
from pathlib import Path

from research_agent.workspace import (
    AgentRegistry,
    ArchiveStore,
    CommandRegistry,
    MemoryStore,
    WorkspaceStoreError,
    export_workspace_snapshots,
)

REPO = Path(__file__).resolve().parents[1]


class WorkspaceStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_agent_registry_is_read_only_spec_projection(self):
        snapshot = AgentRegistry().snapshot()
        ids = [agent["id"] for agent in snapshot["agents"]]
        self.assertGreaterEqual(snapshot["count"], 11)
        self.assertIn("literature", ids)
        self.assertIn("idea", ids)
        self.assertIn("rsi", ids)
        self.assertEqual(snapshot["source"], "modules/*/SPEC.md")
        literature = next(agent for agent in snapshot["agents"] if agent["id"] == "literature")
        self.assertEqual(literature["status"], "pilot")
        self.assertTrue(literature["invariants"])
        self.assertTrue(literature["spec"].startswith("modules/literature/SPEC.md"))

    def test_command_catalog_keeps_human_gates(self):
        snapshot = CommandRegistry().snapshot()
        by_id = {item["id"]: item for item in snapshot["commands"]}
        self.assertEqual(by_id["run.claim"]["safety"], "human_gate")
        self.assertEqual(by_id["closure.sign"]["safety"], "human_gate")
        self.assertEqual(by_id["rsi.status"]["safety"], "read_only")
        self.assertGreaterEqual(snapshot["count"], 10)

    def test_memory_round_trip_and_boundary(self):
        store = MemoryStore(self.root / "memory.json")
        entry = store.add("只在湿热循环中比较 T80。", kind="constraint", scope="perovskite", source="user")
        self.assertTrue(entry["id"].startswith("MEM-"))
        listed = store.snapshot()
        self.assertEqual(listed["count"], 1)
        self.assertIn("not evidence", listed["boundary"])
        reopened = MemoryStore(self.root / "memory.json").snapshot()
        self.assertEqual(reopened["entries"][0]["text"], "只在湿热循环中比较 T80。")
        self.assertTrue(store.delete(entry["id"]))
        self.assertEqual(store.snapshot()["count"], 0)
        self.assertFalse(store.delete("MEM-missing"))

    def test_memory_rejects_bad_kind_and_oversize_text(self):
        store = MemoryStore(self.root / "memory.json")
        with self.assertRaises(WorkspaceStoreError):
            store.add("x", kind="claim")
        with self.assertRaises(WorkspaceStoreError):
            store.add("x" * 2001)

    def test_archive_round_trip_and_secret_rejection(self):
        store = ArchiveStore(self.root / "archive")
        meta = store.add(
            "perovskite snapshot",
            "perovskite",
            {"task_id": "perovskite", "messages": [{"role": "user", "text": "hello"}]},
            note="before archive",
        )
        self.assertTrue(meta["id"].startswith("ARC-"))
        self.assertEqual(store.snapshot()["count"], 1)
        payload = store.get(meta["id"])
        self.assertEqual(payload["payload"]["task_id"], "perovskite")
        self.assertTrue(store.delete(meta["id"]))
        self.assertEqual(store.snapshot()["count"], 0)

        with self.assertRaises(WorkspaceStoreError):
            store.add("bad", "bad", {"api_key": "should-not-be-saved"})
        with self.assertRaises(WorkspaceStoreError):
            store.get("../memory")

    def test_export_writes_snapshots_and_matches_committed_files(self):
        result = export_workspace_snapshots(self.root)
        self.assertEqual(
            sorted(result["files"]),
            [
                "agent-registry.json",
                "command-catalog.json",
                "custom-agents.json",
                "evolution-policy.json",
                "orchestration-topology.json",
            ],
        )
        agents = json.loads((self.root / "agent-registry.json").read_text(encoding="utf-8"))
        commands = json.loads((self.root / "command-catalog.json").read_text(encoding="utf-8"))
        topology = json.loads((self.root / "orchestration-topology.json").read_text(encoding="utf-8"))
        custom = json.loads((self.root / "custom-agents.json").read_text(encoding="utf-8"))
        policy = json.loads((self.root / "evolution-policy.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(agents["count"], 12)
        self.assertNotIn("waitpoints", [agent["id"] for agent in agents["agents"]])
        self.assertGreaterEqual(commands["count"], 12)
        self.assertTrue(topology["template"])
        self.assertEqual(topology["lanes"]["parallel"]["max_workers"], 3)
        self.assertIn("boundary", custom)
        self.assertIn("scopes", policy)

        committed_agents = REPO / "apps" / "web" / "public" / "agent-registry.json"
        committed_commands = REPO / "apps" / "web" / "public" / "command-catalog.json"
        if committed_agents.is_file():
            current = json.loads(committed_agents.read_text(encoding="utf-8"))
            self.assertEqual(current["agents"], AgentRegistry().snapshot()["agents"])
        if committed_commands.is_file():
            current = json.loads(committed_commands.read_text(encoding="utf-8"))
            self.assertEqual(current["commands"], CommandRegistry().snapshot()["commands"])



class CommandCatalogDriftTest(unittest.TestCase):
    """A wired CLI command must be discoverable by a host, or the plugin story is fiction."""

    def surface(self):
        from research_agent.workspace import CommandRegistry, cli_command_surface

        return CommandRegistry().snapshot(), cli_command_surface()

    def test_every_cli_command_appears_in_the_catalog(self):
        snapshot, surface = self.surface()
        ids = {item["id"] for item in snapshot["commands"]}
        missing = sorted(row["id"] for row in surface if row["id"] not in ids)
        self.assertEqual(missing, [], "commands wired into the CLI but invisible to hosts")

    def test_groups_that_were_once_invisible_are_now_listed(self):
        snapshot, _ = self.surface()
        groups = {item["group"] for item in snapshot["commands"]}
        for group in ("study", "memory", "handoff", "host-model", "closure", "benchmark"):
            self.assertIn(group, groups, sorted(groups))

    def test_derived_entries_declare_themselves_unclassified(self):
        snapshot, surface = self.surface()
        by_id = {item["id"]: item for item in snapshot["commands"]}
        derived = [row["id"] for row in surface if not row["id"].startswith("task.")]
        for ident in derived[:5]:
            entry = by_id.get(ident)
            if entry is not None and not entry.get("curated"):
                self.assertEqual(entry["safety"], "catalog_only", entry)

    def test_curated_descriptions_survive_the_derivation(self):
        from research_agent.workspace import COMMANDS

        snapshot, _ = self.surface()
        by_id = {item["id"]: item for item in snapshot["commands"]}
        for curated in COMMANDS:
            entry = by_id.get(curated["id"])
            self.assertIsNotNone(entry, curated["id"])
            self.assertEqual(entry["description"], curated["description"], curated["id"])
            self.assertTrue(entry.get("curated"), curated["id"])

if __name__ == "__main__":
    unittest.main()

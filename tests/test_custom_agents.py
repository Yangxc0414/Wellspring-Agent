import json
import tempfile
import unittest
from pathlib import Path

from research_agent.custom_agents import CustomAgentError, CustomAgentStore


class CustomAgentStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "custom_agents.json"
        self.store = CustomAgentStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_derives_safe_stage_tools_outputs_and_boundary(self):
        agent = self.store.add(
            "覆盖与引用审稿人",
            "reviewer",
            "检查全文覆盖和候选引用是否落在 span 中",
            ["citation", "coverage"],
        )
        self.assertTrue(agent["id"].startswith("CAG-"))
        self.assertEqual(agent["checks"], ["coverage", "citation"])
        self.assertEqual(agent["stages"], ["S1"])
        self.assertEqual(agent["tools"], ["coverage.inspect", "citation.inspect"])
        self.assertEqual(agent["outputs"], ["CoverageAdvisory", "CitationAdvisory"])
        self.assertTrue(agent["advisory_only"])
        self.assertEqual(agent["writes"], [])
        self.assertTrue(agent["enabled"])
        self.assertEqual(self.store.snapshot()["count"], 1)
        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn("advisory only", persisted["boundary"])

    def test_toggle_update_and_delete_round_trip(self):
        agent = self.store.add("协议审稿人", "methodologist", "检查 protocol", ["protocol"])
        updated = self.store.update(agent["id"], enabled=False, purpose="S4 protocol audit")
        self.assertFalse(updated["enabled"])
        self.assertEqual(updated["purpose"], "S4 protocol audit")
        self.assertEqual(self.store.list(enabled_only=True), [])
        self.assertTrue(self.store.delete(agent["id"]))
        self.assertFalse(self.store.delete(agent["id"]))
        self.assertEqual(self.store.snapshot()["count"], 0)

    def test_validation_rejects_unknown_empty_duplicate_and_long_fields(self):
        with self.assertRaises(CustomAgentError):
            self.store.add("x", "reviewer", "too short", ["coverage"])
        with self.assertRaises(CustomAgentError):
            self.store.add("valid", "unknown", "purpose here", ["coverage"])
        with self.assertRaises(CustomAgentError):
            self.store.add("valid", "reviewer", "purpose here", [])
        with self.assertRaises(CustomAgentError):
            self.store.add("valid", "reviewer", "purpose here", ["claim"])
        with self.assertRaises(CustomAgentError):
            self.store.add("valid", "reviewer", "purpose here", ["coverage", "unknown"])
        self.store.add("valid", "reviewer", "purpose here", ["coverage"])
        with self.assertRaises(CustomAgentError):
            self.store.add("VALID", "reviewer", "other purpose", ["citation"])
        with self.assertRaises(CustomAgentError):
            self.store.add("v" * 61, "reviewer", "purpose here", ["coverage"])

    def test_export_is_a_web_snapshot_with_checks_and_roles(self):
        self.store.add("引用审稿人", "auditor", "检查引用对齐", ["citation"])
        output = Path(self.tmp.name) / "public" / "custom-agents.json"
        result = self.store.export(output)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(result["count"], 1)
        self.assertEqual(payload["count"], 1)
        self.assertTrue(any(item["id"] == "citation" for item in payload["checks"]))
        self.assertTrue(any(item["id"] == "auditor" for item in payload["roles"]))
        self.assertIn("advisory only", payload["boundary"])


if __name__ == "__main__":
    unittest.main()

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent import paths
from research_agent.custom_agents import DEFAULT_CUSTOM_AGENTS_PATH
from research_agent.evolution_policy import DEFAULT_EVOLUTION_POLICY_PATH
from research_agent.orchestrator import DEFAULT_MEMORY_PATH
from research_agent.storage import (
    JsonStoreError,
    atomic_replace,
    now_iso,
    read_json,
    write_json_atomic,
)


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_atomic_json_round_trip_and_missing_file(self):
        path = self.root / "nested" / "state.json"
        self.assertIsNone(read_json(path))
        write_json_atomic(path, {"schema_version": "test-0.1", "items": [1, 2]})
        self.assertEqual(read_json(path), {"schema_version": "test-0.1", "items": [1, 2]})
        self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_atomic_replace_retries_a_transient_permission_error(self):
        source = self.root / "state.json.tmp"
        target = self.root / "state.json"
        source.write_text('{"ok": true}', encoding="utf-8")
        real_replace = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("sharing violation")
            return real_replace(src, dst)

        with mock.patch("research_agent.storage.os.replace", side_effect=flaky):
            atomic_replace(source, target)
        self.assertEqual(len(calls), 3)
        self.assertEqual(target.read_text(encoding="utf-8"), '{"ok": true}')

    def test_invalid_json_is_a_typed_error(self):
        path = self.root / "bad.json"
        path.write_text("{not-json", encoding="utf-8")
        with self.assertRaises(JsonStoreError):
            read_json(path)

    def test_default_paths_are_absolute_and_shared(self):
        self.assertTrue(paths.DEFAULT_CUSTOM_AGENTS_PATH.is_absolute())
        self.assertTrue(paths.DEFAULT_EVOLUTION_POLICY_PATH.is_absolute())
        self.assertTrue(paths.DEFAULT_LITERATURE_MEMORY_PATH.is_absolute())
        self.assertEqual(DEFAULT_CUSTOM_AGENTS_PATH, paths.DEFAULT_CUSTOM_AGENTS_PATH)
        self.assertEqual(DEFAULT_EVOLUTION_POLICY_PATH, paths.DEFAULT_EVOLUTION_POLICY_PATH)
        self.assertEqual(DEFAULT_MEMORY_PATH, paths.DEFAULT_LITERATURE_MEMORY_PATH)
        self.assertEqual(paths.DEFAULT_CUSTOM_AGENTS_PATH.parent, paths.RUNTIME_DATA_ROOT)
        self.assertTrue(now_iso().endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()

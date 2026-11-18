"""Memory-pack prompt injection: load failures, wrap generators, never write back."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent import cli  # noqa: E402


class MemoryPackLoaderTest(unittest.TestCase):
    def _write(self, payload, suffix=".json"):
        tmp = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8")
        json.dump(payload, tmp) if suffix == ".json" else tmp.write(payload)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink())
        return tmp.name

    def test_json_pack_extracts_failures_only(self):
        path = self._write({
            "sections": [
                {"name": "failures", "lines": ["- [failure] FA-1: leakage", "- [failure] FA-2: underpowered"]},
                {"name": "claims", "lines": ["- [claim] CLM-1: should not be injected"]},
            ]
        })
        text, meta = cli._load_memory_pack(path)
        self.assertIn("FA-1", text)
        self.assertIn("FA-2", text)
        self.assertNotIn("CLM-1", text)
        self.assertEqual(meta["chars"], len(text))

    def test_markdown_pack_is_used_verbatim(self):
        path = self._write("# failures\n- FA-9: silent fallback", suffix=".md")
        text, _meta = cli._load_memory_pack(path)
        self.assertIn("FA-9", text)

    def test_missing_pack_is_an_error(self):
        with self.assertRaises(SystemExit):
            cli._load_memory_pack("runtime_data/does-not-exist.json")

    def test_empty_pack_is_an_error(self):
        path = self._write({"sections": [{"name": "failures", "lines": []}]})
        with self.assertRaises(SystemExit):
            cli._load_memory_pack(path)

    def test_wrapper_adds_memory_and_keeps_original_payload(self):
        seen = {}

        def generator(payload):
            seen.update(payload)
            return ["candidate"]

        wrapped = cli._wrap_with_memory(generator, "FA-1: leakage")
        result = wrapped({"topic": "t"})
        self.assertEqual(result, ["candidate"])
        self.assertEqual(seen["topic"], "t")
        self.assertIn("FA-1", seen["memory_of_past_failures"])

    def test_wrapper_does_not_mutate_caller_payload(self):
        payload = {"topic": "t"}
        cli._wrap_with_memory(lambda item: item, "memory")(payload)
        self.assertNotIn("memory_of_past_failures", payload)


if __name__ == "__main__":
    unittest.main()

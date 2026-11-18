"""Bare profile ids are accepted when the gateway store declares them."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent import cli  # noqa: E402


def _store(path: Path) -> None:
    payload = {
        "schema_version": "model-gateway-0.1",
        "providers": [
            {
                "provider_id": "test-provider",
                "kind": "openai_compatible",
                "label": "test",
                "base_url": "https://example.invalid/v1",
                "api_key_env": "TEST_PROVIDER_KEY",
                "models": ["test-model"],
            }
        ],
        "profiles": [
            {
                "profile_id": "my-profile",
                "provider_id": "test-provider",
                "model": "test-model",
                "label": "test profile",
                "thinking": {"mode": "off"},
                "thinking_supported": False,
                "max_tokens": 512,
                "context_window": 8192,
                "max_output_tokens": 1024,
            }
        ],
        "bindings": {},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class BareProfileIdTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="model-store-")
        self.store = Path(self.tmp) / "model_gateway.json"
        _store(self.store)
        self._original = cli.default_store_path
        cli.default_store_path = lambda: self.store
        os.environ.setdefault("RESEARCH_AGENT_MODE", "test")
        os.environ["TEST_PROVIDER_KEY"] = "test-key-not-used"

    def tearDown(self):
        cli.default_store_path = self._original
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_bare_idea_profile_is_resolved(self):
        proposer, note = cli._resolve_idea_proposer("my-profile")
        self.assertIsNotNone(proposer)
        self.assertIn("my-profile", note)

    def test_bare_experiment_profile_is_resolved(self):
        designer, note = cli._resolve_experiment_designer("my-profile")
        self.assertIsNotNone(designer)
        self.assertIn("my-profile", note)

    def test_bare_writer_profile_is_resolved(self):
        writer, note = cli._resolve_paper_writer("my-profile")
        self.assertIsNotNone(writer)
        self.assertIn("my-profile", note)

    def test_unknown_id_still_falls_back_with_a_note(self):
        proposer, note = cli._resolve_idea_proposer("no-such-profile")
        self.assertIsNone(proposer)
        self.assertIn("no-such-profile", note)

    def test_prefixed_form_still_works(self):
        proposer, note = cli._resolve_idea_proposer("profile:my-profile")
        self.assertIsNotNone(proposer)
        self.assertIn("my-profile", note)


if __name__ == "__main__":
    unittest.main()

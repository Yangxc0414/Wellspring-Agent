"""HTTP surface for the host-agent handoff: read the queue, submit an answer, stay honest."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from research_agent.host_model import ModelTurnLedger
from research_agent.runtime.app import create_app
from research_agent.runtime.jobs import default_settings

MESSAGES = [
    {"role": "system", "content": "use only the given evidence"},
    {"role": "user", "content": '{"evidence": ["REF-01"]}'},
]


class HostModelHttpApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        settings = default_settings()
        settings.repo_root = root
        settings.jobs_root = root / "jobs"
        settings.workspace_memory_path = root / "workspace_memory.json"
        settings.workspace_archive_root = root / "archive"
        settings.literature_memory_path = root / "literature_memory.json"
        settings.custom_agents_path = root / "custom_agents.json"
        settings.evolution_policy_path = root / "evolution_policy.json"
        settings.skill_registry_path = root / "skills.json"
        settings.model_store_path = root / "model_gateway.json"
        settings.host_model_ledger_path = root / "host-model" / "turns.json"
        settings.research_api_root = root / "research-root"
        settings.research_api_root.mkdir(parents=True, exist_ok=True)
        self.ledger = ModelTurnLedger(settings.host_model_ledger_path)
        self.app = create_app(settings)

    def tearDown(self):
        self.tmp.cleanup()

    def _turn(self, **kwargs):
        return self.ledger.create(MESSAGES, "host-agent", module="idea", **kwargs)

    def test_panel_endpoint_reports_critic_supplies_without_secrets(self):
        from research_agent.models import GatewayStore, ModelProfile

        store = GatewayStore(Path(self.tmp.name) / "model_gateway.json")
        store.profiles = {}
        store.bindings = {}
        for index, provider in enumerate(("openai", "anthropic"), start=1):
            store.upsert_profile(
                ModelProfile(profile_id="p%d" % index, provider_id=provider,
                             model="model-%d" % index, json_mode=True)
            )
        store.save()
        with TestClient(self.app) as client:
            with mock.patch.dict(
                "os.environ", {"OPENAI_API_KEY": "sk-a", "ANTHROPIC_API_KEY": "sk-b"}
            ):
                response = client.get("/api/host-model/panel")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "critic-panel-0.1")
        self.assertEqual(payload["distinct_supplies"], 2)
        self.assertFalse(payload["panel_possible"], "two supplies cannot staff three roles")
        self.assertEqual(payload["missing_supplies"], 1)
        self.assertNotIn("sk-a", response.text)
        self.assertNotIn("sk-b", response.text)
        self.assertNotIn(self.tmp.name.replace("\\", "/"), response.text)

    def test_queue_returns_the_prompt_so_a_host_can_answer(self):
        turn = self._turn(purpose="S2 idea candidates")
        with TestClient(self.app) as client:
            response = client.get("/api/host-model/turns", params={"status": "pending"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["counts"]["pending"], 1)
        item = body["turns"][0]
        self.assertEqual(item["turn_id"], turn["turn_id"])
        self.assertEqual(item["request"]["system"], "use only the given evidence")
        self.assertIn("how_to_respond", body)
        self.assertNotIn("ledger_path", str(body))

    def test_submit_validates_then_binds_the_answer(self):
        turn = self._turn(expects={"json": True, "object": True})
        with TestClient(self.app) as client:
            rejected = client.post(
                "/api/host-model/respond",
                json={"turn_id": turn["turn_id"], "text": "prose not json", "host_label": "Qoder"},
            )
            self.assertEqual(rejected.status_code, 200)
            self.assertFalse(rejected.json()["accepted"])
            self.assertTrue(rejected.json()["errors"])
            self.assertEqual(self.ledger.get(turn["turn_id"])["status"], "pending")

            accepted = client.post(
                "/api/host-model/respond",
                json={"turn_id": turn["turn_id"], "text": '{"candidates": []}', "host_label": "Qoder"},
            )
            self.assertTrue(accepted.json()["accepted"])
            receipt = accepted.json()["receipt"]
            self.assertEqual(receipt["messages_sha256"], turn["messages_sha256"])
            self.assertEqual(len(receipt["text_sha256"]), 64)

            again = client.post(
                "/api/host-model/respond",
                json={"turn_id": turn["turn_id"], "text": '{"candidates": []}', "host_label": "Qoder"},
            )
            self.assertEqual(again.status_code, 400)

    def test_unknown_turn_is_rejected_not_created(self):
        with TestClient(self.app) as client:
            response = client.post(
                "/api/host-model/respond",
                json={"turn_id": "MT-doesnotexist", "text": "{}", "host_label": "Qoder"},
            )
        self.assertEqual(response.status_code, 400)

    def test_http_surface_has_no_mutating_gate_route(self):
        with TestClient(self.app) as client:
            mutating = {
                route.path
                for route in client.app.routes
                for method in (getattr(route, "methods", None) or set())
                if method in ("POST", "PUT", "PATCH", "DELETE")
            }
        offenders = [
            path
            for path in mutating
            if any(word in path.lower() for word in ("approve", "sign", "freeze", "publish", "claim"))
        ]
        self.assertEqual(offenders, [])
        self.assertIn("/api/host-model/respond", mutating)


if __name__ == "__main__":
    unittest.main()

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent.mcp_server import ResearchMCPService
from research_agent.model_catalog import critic_panel, profile_catalog
from research_agent.models import GatewayStore, ModelProfile, ProviderConfig


def _store(path: Path) -> Path:
    store = GatewayStore(path)
    store.profiles = {}
    store.profiles["judge-a"] = ModelProfile(
        profile_id="judge-a",
        provider_id="openai",
        model="gpt-test",
        label="OpenAI judge",
        json_mode=True,
    )
    store.profiles["judge-b"] = ModelProfile(
        profile_id="judge-b",
        provider_id="anthropic",
        model="claude-test",
        label="Anthropic judge",
        json_mode=True,
    )
    store.bindings = {"judge": "judge-a"}
    store.save()
    return path


class ModelCatalogTest(unittest.TestCase):
    def test_catalog_lists_profiles_and_diverse_pairs_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _store(Path(tmp) / "gateway.json")
            with mock.patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "sk-openai-secret", "ANTHROPIC_API_KEY": "sk-anthropic-secret"},
            ):
                catalog = profile_catalog(path)
            ids = [item["profile_id"] for item in catalog["profiles"]]
            self.assertEqual(ids, ["judge-a", "judge-b"])
            self.assertTrue(all(item["has_key"] for item in catalog["profiles"]))
            self.assertEqual(catalog["diverse_judge_pairs"][0], ["judge-a", "judge-b"])
            self.assertEqual(catalog["bindings"], {"judge": "judge-a"})
            serialized = json.dumps(catalog).lower()
            self.assertNotIn("sk-openai-secret", serialized)
            self.assertNotIn("sk-anthropic-secret", serialized)
            self.assertNotIn("api_key", serialized)
            self.assertNotIn("base_url", serialized)

            with mock.patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": ""},
            ):
                unavailable = profile_catalog(path)
            self.assertEqual(unavailable["available_profiles"], 0)
            self.assertEqual(unavailable["diverse_judge_pairs"], [])

    def test_host_agent_profile_is_keyless_and_never_a_diverse_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gateway.json"
            store = GatewayStore(path)
            store.upsert_provider(
                ProviderConfig(provider_id="host-agent", kind="host_agent", label="Host")
            )
            store.upsert_profile(
                ModelProfile(profile_id="host-agent", provider_id="host-agent", model="host")
            )
            store.profiles["judge-a"] = ModelProfile(
                profile_id="judge-a", provider_id="openai", model="gpt-test"
            )
            store.set_binding("idea", "host-agent")
            with mock.patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "sk-openai-secret",
                    "DEEPSEEK_API_KEY": "",
                    "ZHIPU_API_KEY": "",
                    "ANTHROPIC_API_KEY": "",
                    "OPENAI_COMPATIBLE_API_KEY": "",
                    "LOCAL_LLM_API_KEY": "",
                },
            ):
                catalog = profile_catalog(path)
            entries = {item["profile_id"]: item for item in catalog["profiles"]}
            self.assertTrue(entries["host-agent"]["keyless"])
            self.assertEqual(entries["host-agent"]["supply"], "host_agent")
            self.assertEqual(catalog["host_agent_profiles"], ["host-agent"])
            self.assertEqual(catalog["host_agent_bound_modules"], ["idea"])
            # one keyed provider + one host supply is not two independent providers
            self.assertEqual(catalog["available_profiles"], 1)
            self.assertEqual(catalog["diverse_judge_pairs"], [])

    def test_default_catalog_exposes_deepseek_when_key_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            # An explicit path that does not exist yet still loads the built-in defaults, so this
            # asserts on the shipped catalog rather than whatever the machine has persisted.
            missing = Path(tmp) / "gateway.json"
            with mock.patch.dict(
                os.environ,
                {"DEEPSEEK_API_KEY": "sk-deepseek-secret", "ZHIPU_API_KEY": ""},
            ):
                catalog = profile_catalog(missing)
        profiles = {item["profile_id"]: item for item in catalog["profiles"]}
        self.assertIn("deepseek", profiles)
        self.assertEqual(profiles["deepseek"]["provider_id"], "deepseek")
        self.assertTrue(profiles["deepseek"]["has_key"])
        self.assertNotIn("sk-deepseek-secret", json.dumps(catalog))

    def test_pathless_catalog_follows_the_configured_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _store(Path(tmp) / "gateway.json")
            with mock.patch.dict(
                os.environ,
                {
                    "RESEARCH_AGENT_MODEL_STORE": str(path),
                    "OPENAI_API_KEY": "sk-a",
                    "ANTHROPIC_API_KEY": "sk-b",
                },
            ):
                catalog = profile_catalog()
            self.assertEqual(
                [item["profile_id"] for item in catalog["profiles"]], ["judge-a", "judge-b"]
            )

    def test_critic_panel_needs_one_distinct_supply_per_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _store(Path(tmp) / "gateway.json")
            store = GatewayStore(path)
            store.upsert_profile(
                ModelProfile(profile_id="judge-c", provider_id="zhipu", model="glm-test")
            )
            store.save()
            with mock.patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "sk-a",
                    "ANTHROPIC_API_KEY": "sk-b",
                    "ZHIPU_API_KEY": "sk-c",
                    "DEEPSEEK_API_KEY": "",
                },
            ):
                panel = critic_panel(path)
            self.assertTrue(panel["panel_possible"], panel["note"])
            self.assertEqual(len(panel["suggested"]), 3)
            self.assertEqual(len(set(panel["suggested"].values())), 3)
            self.assertEqual(panel["distinct_supplies"], 3)

    def test_critic_panel_counts_two_profiles_on_the_same_model_as_one_supply(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gateway.json"
            store = GatewayStore(path)
            store.upsert_provider(
                ProviderConfig(provider_id="host-agent", kind="host_agent", label="Host")
            )
            for profile in ("host_a", "host_b", "host_c"):
                store.upsert_profile(
                    ModelProfile(profile_id=profile, provider_id="host-agent", model="same-model")
                )
            store.set_binding("idea", "host_a")
            store.save()
            with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": ""}):
                panel = critic_panel(path)
            self.assertFalse(panel["panel_possible"])
            self.assertEqual(panel["distinct_supplies"], 1)
            self.assertEqual(panel["missing_supplies"], 2)

    def test_catalog_embeds_the_critic_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _store(Path(tmp) / "gateway.json")
            with mock.patch.dict(
                os.environ, {"OPENAI_API_KEY": "sk-a", "ANTHROPIC_API_KEY": "sk-b"}
            ):
                catalog = profile_catalog(path)
            self.assertEqual(catalog["critic_panel"]["schema_version"], "critic-panel-0.1")
            self.assertIn("judge-a", catalog["critic_panel"]["usable_profiles"])

    def test_mcp_model_profiles_service_uses_the_configured_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = _store(root / "gateway.json")
            with mock.patch.dict(
                os.environ,
                {
                    "RESEARCH_AGENT_MODEL_STORE": str(path),
                    "OPENAI_API_KEY": "sk-a",
                    "ANTHROPIC_API_KEY": "sk-b",
                },
            ):
                service = ResearchMCPService(root)
                response = service.model_profiles({})
            self.assertFalse(response["isError"])
            payload = response["structuredContent"]
            self.assertEqual(payload["schema_version"], "model-profile-catalog-0.1")
            self.assertEqual(len(payload["profiles"]), 2)
            self.assertNotIn("sk-a", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()

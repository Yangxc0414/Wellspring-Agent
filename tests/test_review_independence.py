"""Independence is disclosed, not assumed; and a review verdict cannot outlive its own power."""

import json
import unittest

from research_agent.innovation_review import REVIEW_ROLES, _independence
from research_agent.manuscript_writer import _evidence_context


class FakeModel:
    model_id = "host-agent:host-agent"


def _panel(models_by_role, proposer=None, **kwargs):
    return _independence(models_by_role, proposer, list(REVIEW_ROLES), 1, **kwargs)


class IndependenceDisclosureTest(unittest.TestCase):
    def test_three_roles_one_model_are_recorded_as_one_author(self):
        model = FakeModel()
        block = _panel({role: model for role in REVIEW_ROLES})
        self.assertEqual(block["critic_calls"], 3)
        self.assertEqual(block["distinct_supplies"], 0, "no provider fingerprint is resolvable")
        self.assertTrue(block["single_author_review"])
        self.assertEqual(block["kind"], "unverifiable")
        self.assertFalse(
            block["admission_eligible"],
            "same-supply scores must never be admissible as independent evidence",
        )

    def test_one_author_state_is_liftable_by_distinct_supplies(self):
        class Supply:
            def __init__(self, provider, model):
                self.provider_id = provider
                self.provider_kind = "openai_compatible"
                self.model_name = model
                self.model_id = "%s:%s" % (provider, model)

        critics = {
            "novelty": Supply("deepseek", "deepseek-chat"),
            "evidence": Supply("moonshot", "kimi-k2"),
            "feasibility": Supply("openai", "gpt-4o-mini"),
        }
        block = _panel(critics, proposer=Supply("anthropic", "claude-sonnet"))
        self.assertTrue(block["admission_eligible"], block["reading"])
        self.assertEqual(block["kind"], "provider_and_model")
        self.assertFalse(block["single_author_review"])
        self.assertEqual(block["distinct_supplies"], 3)
        self.assertEqual(len(block["distinct_providers"]), 3)

    def test_proposer_on_the_bench_blocks_admission(self):
        class Supply:
            def __init__(self, provider, model):
                self.provider_id = provider
                self.provider_kind = "openai_compatible"
                self.model_name = model
                self.model_id = "%s:%s" % (provider, model)

        proposer = Supply("deepseek", "deepseek-chat")
        critics = {
            "novelty": proposer,
            "evidence": Supply("moonshot", "kimi-k2"),
            "feasibility": Supply("openai", "gpt-4o-mini"),
        }
        block = _panel(critics, proposer=proposer)
        self.assertFalse(block["admission_eligible"])
        self.assertTrue(block["proposer_is_critic"])
        self.assertIn("author bias", block["reading"])

    def test_two_host_profiles_on_the_same_model_are_not_two_critics(self):
        class Host:
            provider_kind = "host_agent"

            def __init__(self, provider, profile, model):
                self.provider_id = provider
                self.profile_id = profile
                self.model_name = model
                self.model_id = "host-agent:" + profile

        shared = "qoder-default"
        critics = {
            "novelty": Host("qoder", "host_a", shared),
            "evidence": Host("qoder", "host_b", shared),
            "feasibility": Host("qoder", "host_c", shared),
        }
        block = _panel(critics, proposer=Host("qoder", "host_a", shared))
        self.assertFalse(block["admission_eligible"])
        self.assertTrue(block["single_author_review"])

    def test_ledger_attributes_all_turns_to_one_host_agent(self):
        class Host:
            provider_kind = "host_agent"

            def __init__(self, profile, model):
                self.provider_id = "qoder"
                self.profile_id = profile
                self.model_name = model
                self.model_id = "host-agent:" + profile

        critics = {
            "novelty": Host("host_a", "model-a"),
            "evidence": Host("host_b", "model-b"),
            "feasibility": Host("host_c", "model-c"),
        }
        block = _panel(
            critics,
            proposer=Host("host_d", "model-d"),
            answered_by={role: ["same-laptop"] for role in REVIEW_ROLES},
        )
        self.assertFalse(
            block["admission_eligible"],
            "distinct configs answered by one named agent is still one reviewer",
        )
        self.assertIn("one host agent", block["reading"])

    def test_write_prompt_allows_structural_independence_only_when_eligible(self):
        pack = {
            "literature": {"references": [{"ref_id": "REF-01", "source_id": "S1"}]},
            "task": {"goal": "t"},
            "evidence_map": {"REF-01": ["span"]},
        }
        eligible = {
            "admission_eligible": True,
            "critic_calls": 3,
            "distinct_supplies": 3,
            "distinct_providers": ["deepseek", "moonshot", "openai"],
            "distinct_model_ids": ["a", "b", "c"],
            "kind": "provider_and_model",
        }
        text = _evidence_context(pack, {"gaps": [], "final_ideas": [], "independence": eligible})
        self.assertIn("结构化独立评审", text)
        self.assertIn("不得把它当新颖性证明", text)
        blocked = {
            "admission_eligible": False,
            "critic_calls": 3,
            "reasons": ["the model that proposed these ideas also scored them"],
        }
        text = _evidence_context(pack, {"gaps": [], "final_ideas": [], "independence": blocked})
        self.assertIn("不得把三方角色写成三位独立审稿人", text)
        self.assertIn("解除条件", text)

    def test_writer_prompt_forbids_calling_the_roles_independent_reviewers(self):
        pack = {
            "literature": {"references": [{"ref_id": "REF-01", "source_id": "S1"}]},
            "task": {"goal": "t"},
            "evidence_map": {"REF-01": ["span"]},
        }
        innovation = {
            "gaps": [{"gap_id": "GAP-01", "description": "d", "why_unresolved": "w", "evidence_refs": ["REF-01"]}],
            "final_ideas": [
                {
                    "idea_id": "IDEA-01",
                    "title": "标题",
                    "mechanism": "m",
                    "falsification": "f",
                    "evidence_refs": ["REF-01"],
                    "experiment_plan": {
                        "profile": "search_factorial",
                        "dataset": "iris",
                        "metric": "improvement_per_evaluation",
                    },
                }
            ],
            "independence": _panel({role: FakeModel() for role in REVIEW_ROLES}),
        }
        text = _evidence_context(pack, innovation)
        self.assertIn("评审独立性", text)
        self.assertIn("不得把三方角色写成三位独立审稿人", text)
        self.assertIn("profile=search_factorial", text)
        self.assertIn("improvement_per_evaluation", text)

    def test_plan_without_profile_is_shown_as_unbound_not_silently_dropped(self):
        pack = {
            "literature": {"references": [{"ref_id": "REF-01", "source_id": "S1"}]},
            "task": {"goal": "t"},
            "evidence_map": {"REF-01": ["span"]},
        }
        innovation = {
            "gaps": [],
            "final_ideas": [
                {"idea_id": "IDEA-01", "title": "x", "mechanism": "m", "falsification": "f", "evidence_refs": ["REF-01"]}
            ],
        }
        text = _evidence_context(pack, innovation)
        self.assertIn("profile=未绑定", text)
        self.assertNotIn("评审独立性", text)

    def test_feasibility_critic_is_given_the_registry_and_the_code_verdict(self):
        from research_agent.innovation_review import _review

        captured = {}

        class RecordingModel:
            model_id = "host-agent:host-agent"

            def complete(self, messages, json_mode=True):
                captured["system"] = messages[0]["content"]
                captured["user"] = messages[1]["content"]
                return json.dumps(
                    {
                        "scores": [
                            {"idea_id": "IDEA-01", "score": 9, "strengths": [], "weaknesses": [], "must_fix": []}
                        ],
                        "overall": "ok",
                    }
                )

        ideas = [
            {
                "idea_id": "IDEA-01",
                "title": "x",
                "problem": "p",
                "mechanism": "m",
                "novelty_claim": "n",
                "falsification": "f",
                "experiment_plan": {"profile": "search_factorial", "dataset": "iris", "metric": "improvement_per_evaluation"},
                "executable": {"ok": True, "reasons": [], "profile": "search_factorial"},
                "evidence_refs": ["REF-01", "REF-02"],
                "risks": [],
                "revision_notes": [],
            }
        ]
        _review("feasibility", ideas, "context", RecordingModel(), 1)
        self.assertIn("本运行时可执行的实验档位", captured["system"])
        self.assertIn("search_factorial", captured["system"])
        self.assertIn("最多给 3 分", captured["system"])
        self.assertIn("executability_check", captured["user"])
        # novelty critic must not be told about executability
        _review("novelty", ideas, "context", RecordingModel(), 1)
        self.assertNotIn("本运行时可执行的实验档位", captured["system"])


class McpCriticResolutionTest(unittest.TestCase):
    """The host agent must be able to staff the bench, or be told exactly why it cannot."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from research_agent.mcp_server import ResearchMCPService
        from research_agent.project import init_project

        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = root / "gateway.json"
        self.mock = mock
        init_project(root / "project", "critic bench")
        self.patcher = mock.patch.dict(
            "os.environ",
            {"RESEARCH_AGENT_MODEL_STORE": str(self.store), "DEEPSEEK_API_KEY": ""},
        )
        self.patcher.start()
        self.service = ResearchMCPService(root)
        self.args = {
            "project_dir": "project",
            "run_id": "RUN-MISSING",
            "rounds": 1,
        }

    def tearDown(self):
        self.patcher.stop()
        self.tmp.cleanup()

    def _call(self, extra):
        from research_agent.project import ProjectError

        args = dict(self.args)
        args.update(extra)
        with self.assertRaises(ProjectError) as caught:
            self.service.innovation_review(args)
        return str(caught.exception)

    def test_unknown_role_is_rejected(self):
        message = self._call({"critic_profiles": {"noveltyy": "p-1"}})
        self.assertIn("unknown critic role", message)
        self.assertIn("novelty, evidence, feasibility", message)

    def test_unknown_profile_is_rejected(self):
        message = self._call({"critic_profiles": {"novelty": "not-configured"}})
        self.assertIn("unknown model profile not-configured", message)
        self.assertNotIn("deterministic template", message)

    def test_independent_fails_with_the_missing_supply_count(self):
        message = self._call({"independent": True})
        self.assertIn("no independent bench is available", message)
        self.assertIn("missing 3", message)

    def test_host_profile_resolves_to_a_scoped_critic_port(self):
        from research_agent.models import GatewayStore, ModelProfile, ProviderConfig

        store = GatewayStore(self.store)
        store.upsert_provider(
            ProviderConfig(provider_id="qoder-host", kind="host_agent", label="Qoder host")
        )
        store.upsert_profile(
            ModelProfile(profile_id="critic-a", provider_id="qoder-host", model="qoder-large")
        )
        models = self.service._critic_models(
            {"critic_profiles": {"novelty": "critic-a"}}
        )
        port = models["novelty"]
        self.assertEqual(port.provider_id, "qoder-host")
        self.assertEqual(port.model_name, "qoder-large")
        self.assertEqual(port.purpose, "innovation critic: novelty")


if __name__ == "__main__":
    unittest.main()

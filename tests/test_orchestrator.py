import json
import tempfile
import unittest
from pathlib import Path

from research_agent.literature_memory import LiteratureMemoryStore
from research_agent.custom_agents import CustomAgentStore
from research_agent.evolution_policy import EvolutionPolicyStore
from research_agent.orchestrator import (
    OrchestrationError,
    collaboration_plan,
    public_snapshot,
    run_orchestration,
    topology_snapshot,
    write_orchestration_artifacts,
)

TOPIC = "钙钛矿 界面 钝化 稳定性"


class OrchestrationPlanTest(unittest.TestCase):
    def test_plan_has_fanout_fanin_typed_handoffs_and_human_gates(self):
        plan = collaboration_plan(TOPIC, 12, "fixture")
        self.assertEqual(plan["topology"], "fan-out → fan-in → sequential → human gate")
        self.assertEqual(plan["lanes"]["parallel"]["max_workers"], 3)
        self.assertEqual(len(plan["lanes"]["parallel"]["roles"]), 3)
        self.assertEqual(plan["lanes"]["fan_in"]["merge_keys"], ["source_id", "span_id"])
        contracts = {handoff["contract"] for handoff in plan["handoffs"]}
        self.assertIn("ScoutTask", contracts)
        self.assertIn("ScoutReport", contracts)
        self.assertIn("MergedEvidenceView", contracts)
        self.assertIn("SkillCandidate", contracts)
        self.assertEqual([gate["id"] for gate in plan["human_gates"]], ["G1", "G2", "S5b", "G5"])
        self.assertEqual(plan["blocked_at"], "G1")
        self.assertIn("S5 run and Claim", plan["does_not_execute"])
        orchestrator = next(role for role in plan["roles"] if role["id"] == "orchestrator")
        self.assertIn("Claim", orchestrator["forbidden"])
        self.assertIn("admission", orchestrator["forbidden"])
        self.assertEqual(
            sum(group["sources"] for group in plan["budget"]["groups"]), 12
        )

    def test_topology_snapshot_is_a_template_without_a_topic(self):
        snapshot = topology_snapshot()
        self.assertTrue(snapshot["template"])
        self.assertEqual(snapshot["topic"], "")
        self.assertEqual(len(snapshot["roles"]), 13)
        self.assertIn("Topology only", snapshot["boundary"])

    def test_invalid_source_is_rejected(self):
        with self.assertRaises(OrchestrationError):
            collaboration_plan(TOPIC, 6, "openalex")


class OrchestrationRunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.memory_path = self.root / "memory.json"
        self.custom_agents_path = self.root / "custom_agents.json"
        self.policy_path = self.root / "policy.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fixture_fanout_merges_and_stops_before_g1(self):
        result = run_orchestration(TOPIC, 12, "fixture", memory_path=self.memory_path, custom_agents_path=self.custom_agents_path, policy_path=self.policy_path)
        data = result.to_dict()
        self.assertEqual(len(data["scouts"]), 3)
        self.assertEqual(
            [scout["facets"] for scout in data["scouts"]],
            [["core", "survey"], ["method", "evaluation"], ["limitation", "recent"]],
        )
        self.assertEqual(data["merged"]["sources"], 3)
        self.assertEqual(data["merged"]["full_text"], 2)
        self.assertGreaterEqual(data["merged"]["spans_count"], 3)
        self.assertEqual(data["merged"]["planned_facets"], 6)
        self.assertTrue(data["fixture_mode"])
        self.assertEqual(data["idea"]["status"], "candidates_need_human")
        self.assertTrue(data["idea"]["candidates"])
        self.assertTrue(
            all(
                card.get("prior_art_scope")
                for card in data["idea"]["candidates"]
            )
        )
        self.assertIsNotNone(data["idea"].get("shortlist"))
        self.assertNotIn("claim_drafts", json.dumps(data))
        self.assertTrue(any("stops before G1" in warning for warning in data["warnings"]))
        self.assertTrue(self.memory_path.is_file())
        self.assertEqual(LiteratureMemoryStore(self.memory_path).snapshot()["count"], 1)

    def test_each_scout_gets_only_its_facet_subset_and_budget(self):
        result = run_orchestration(TOPIC, 12, "fixture", memory_path=self.memory_path, custom_agents_path=self.custom_agents_path, policy_path=self.policy_path)
        facets = []
        for scout in result.scouts:
            self.assertEqual(len(scout["facets"]), 2)
            self.assertEqual(scout["budget"], 4)
            self.assertEqual(scout["queries"], 2)
            facets.extend(scout["facets"])
        self.assertEqual(len(facets), len(set(facets)))

    def test_memory_derives_a_pending_skill_candidate_after_repeated_gaps(self):
        first = run_orchestration(TOPIC, 12, "fixture", memory_path=self.memory_path, custom_agents_path=self.custom_agents_path, policy_path=self.policy_path)
        second = run_orchestration(TOPIC, 12, "fixture", memory_path=self.memory_path, custom_agents_path=self.custom_agents_path, policy_path=self.policy_path)
        self.assertIsNone(first.skill_candidate)
        self.assertIsNotNone(second.skill_candidate)
        candidate = second.skill_candidate
        self.assertEqual(candidate["status"], "pending_human")
        self.assertFalse(candidate["governance"]["auto_admitted"])
        self.assertEqual(candidate["target"], "literature.query_planner")
        self.assertIn("Claim", candidate["governance"]["immutable"])
        self.assertEqual(second.memory["next_advice"]["observed_runs"], 2)

    def test_public_snapshot_strips_sources_and_spans(self):
        result = run_orchestration(TOPIC, 12, "fixture", memory_path=self.memory_path, custom_agents_path=self.custom_agents_path, policy_path=self.policy_path)
        snapshot = public_snapshot(result)
        encoded = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("span_id", encoded)
        self.assertNotIn('"hits"', encoded)
        self.assertNotIn("claim_drafts", encoded)
        self.assertEqual(snapshot["merged"]["sources"], 3)
        self.assertTrue(snapshot["scouts"][0]["facets"])
        self.assertIn("candidate", snapshot["boundary"])

    def test_artifacts_round_trip(self):
        result = run_orchestration(TOPIC, 6, "fixture", memory_path=self.memory_path, custom_agents_path=self.custom_agents_path, policy_path=self.policy_path)
        path = write_orchestration_artifacts(result, self.root / "artifacts")
        self.assertEqual(path.name, "orchestration.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["run_id"], result.run_id)
        self.assertTrue((self.root / "artifacts" / "idea-candidates.json").is_file())
        self.assertTrue((self.root / "artifacts" / "memory-advice.json").is_file())

    def test_custom_advisory_agent_runs_whitelisted_checks_only(self):
        store = CustomAgentStore(self.custom_agents_path)
        store.add(
            "覆盖与引用审稿人",
            "reviewer",
            "检查全文覆盖和候选引用是否落在 span 中",
            ["coverage", "citation"],
        )
        result = run_orchestration(
            TOPIC, 12, "fixture", memory_path=self.memory_path,
            custom_agents_path=self.custom_agents_path, policy_path=self.policy_path,
        )
        self.assertEqual(len(result.custom_agents), 1)
        self.assertTrue(result.custom_agents[0]["advisory_only"])
        self.assertEqual(result.custom_agents[0]["writes"], [])
        notes = {note["check"]: note for note in result.advisory_notes}
        self.assertEqual(set(notes), {"coverage", "citation"})
        self.assertIn(notes["coverage"]["status"], ("pass", "warn"))
        self.assertIn(notes["citation"]["status"], ("pass", "warn"))
        self.assertTrue(all("no Claim/EA/gate" in note["boundary"] for note in notes.values()))
        self.assertTrue(result.plan["lanes"]["custom_advisory"]["roles"])
        self.assertIn("AdvisoryNote[]", {item["contract"] for item in result.plan["handoffs"]})

    def test_later_stage_custom_check_is_deferred(self):
        store = CustomAgentStore(self.custom_agents_path)
        store.add(
            "协议审稿人",
            "methodologist",
            "在 S4 检查 baseline 与 seeds",
            ["protocol"],
        )
        result = run_orchestration(
            TOPIC, 12, "fixture", memory_path=self.memory_path,
            custom_agents_path=self.custom_agents_path, policy_path=self.policy_path,
        )
        self.assertEqual(result.advisory_notes[0]["check"], "protocol")
        self.assertEqual(result.advisory_notes[0]["status"], "deferred")
        custom_role = next(role for role in result.plan["roles"] if role["mode"] == "custom-advisory")
        self.assertFalse(custom_role["executes"])
        self.assertEqual(custom_role["deferred_checks"], ["protocol"])

    def test_policy_can_pause_memory_and_suppress_candidates(self):
        memory_store = LiteratureMemoryStore(self.memory_path)
        for run_id in ("RUN-1", "RUN-2"):
            memory_store.record(
                question=TOPIC,
                run_id=run_id,
                facets=[
                    {"facet": "core", "queries": 1, "sources": 3, "spans": 8, "covered": True},
                    {"facet": "limitation", "queries": 1, "sources": 0, "spans": 0, "covered": False},
                ],
                totals={"sources": 3, "full_text": 2, "spans": 8, "queries": 2},
                gaps=["thin_domain_coverage"],
                saturation="partial",
                mode="fixture",
                coverage_score=0.5,
                fixture_mode=True,
            )
        policy = EvolutionPolicyStore(self.policy_path)
        policy.update(scopes={"literature.query_planner": False})
        result = run_orchestration(
            TOPIC, 12, "fixture", memory_path=self.memory_path,
            custom_agents_path=self.custom_agents_path, policy_path=self.policy_path,
        )
        self.assertIsNone(result.skill_candidate)
        self.assertIsNotNone(result.policy["suppressed_candidate"])
        self.assertEqual(result.policy["suppressed_candidate"]["status"], "suppressed_by_policy")

        policy.update(enabled=False)
        paused = run_orchestration(
            TOPIC, 12, "fixture", memory_path=self.memory_path,
            custom_agents_path=self.custom_agents_path, policy_path=self.policy_path,
        )
        self.assertFalse(paused.memory["applied"])
        self.assertFalse(paused.plan["memory"]["applied"])
        self.assertFalse(paused.plan["evolution_policy"]["enabled"])
        self.assertIsNone(paused.skill_candidate)


if __name__ == "__main__":
    unittest.main()

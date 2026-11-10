import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent.adapters import OpenAlexError
from research_agent.task_agent import TaskAgent, TaskError, TaskRequest


class RateLimitedRetriever:
    fixture_mode = False

    def search(self, query, limit):
        raise OpenAlexError(
            "openalex request failed after retries: HTTP 429; shared free quota may be exhausted"
        )

    def full_text(self, source_id):
        return None


class TaskAgentTest(unittest.TestCase):
    def setUp(self):
        self.agent = TaskAgent()

    def test_router_picks_minimal_route(self):
        cases = {
            "帮我做一轮钙钛矿文献综述": "literature_review",
            "给我三个可证伪的研究假设": "hypothesis_design",
            "复现 Iris 协议并给出证据": "experiment_validation",
            "围绕界面钝化写一篇完整工作稿": "full_research",
        }
        for goal, expected in cases.items():
            plan = self.agent.plan(TaskRequest(goal=goal))
            self.assertEqual(plan.route, expected, goal)
        plan = self.agent.plan(
            TaskRequest("验证协议", task_type="experiment_validation", run_dataset="iris")
        )
        self.assertEqual(plan.route, "experiment_validation")

    def test_literature_task_stops_after_s1_and_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            execution = self.agent.run(
                TaskRequest(
                    goal="钙钛矿界面钝化 湿热稳定性 文献综述",
                    task_type="literature_review",
                    source="fixture",
                    max_sources=6,
                ),
                out,
            )
            self.assertEqual(execution.status, "completed")
            self.assertTrue((out / "task-report.md").is_file())
            self.assertTrue((out / "literature.json").is_file())
            self.assertFalse((out / "paper.md").exists())
            report = (out / "task-report.md").read_text(encoding="utf-8")
            self.assertIn("文献覆盖", report)
            self.assertIn("证据边界", report)
            saved = json.loads((out / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "completed")
            self.assertTrue(saved["evidence_packages"])
            self.assertEqual(saved["evidence_packages"][0]["id"], "literature")

    def test_route_decision_flags_ambiguous_and_strict_env(self):
        ambiguous = self.agent.plan(TaskRequest(goal="研究一下界面", task_type="auto"))
        self.assertEqual(ambiguous.route, "full_research")
        self.assertTrue(ambiguous.route_decision["needs_input"])
        self.assertEqual(ambiguous.route_decision["confidence"], "low")
        self.assertTrue(any("routing ambiguous" in item for item in ambiguous.warnings))
        strong = self.agent.plan(
            TaskRequest(goal="帮我做一轮钙钛矿文献综述", task_type="auto")
        )
        self.assertEqual(strong.route, "literature_review")
        self.assertFalse(strong.route_decision["needs_input"])
        self.assertIn("high", strong.route_decision["confidence"])
        with mock.patch.dict(os.environ, {"RESEARCH_AGENT_STRICT_ROUTING": "1"}):
            with self.assertRaises(TaskError):
                self.agent.plan(TaskRequest(goal="研究一下界面", task_type="auto"))
        with self.assertRaises(TaskError):
            TaskAgent(strict_routing=True).plan(
                TaskRequest(goal="研究一下界面", task_type="auto")
            )

    def test_auto_route_downgrades_openalex_to_literature_review(self):
        plan = self.agent.plan(
            TaskRequest(
                goal="围绕界面钝化写一篇完整工作稿",
                task_type="auto",
                source="openalex",
            )
        )
        self.assertEqual(plan.route, "literature_review")
        self.assertTrue(any("auto routing uses literature_review" in item for item in plan.warnings))

        explicit = self.agent.plan(
            TaskRequest(
                goal="围绕界面钝化写一篇完整工作稿",
                task_type="full_research",
                source="openalex",
            )
        )
        self.assertEqual(explicit.route, "full_research")
        self.assertFalse(any("auto routing uses literature_review" in item for item in explicit.warnings))
        self.assertTrue(any("explicit full_research with OpenAlex" in item for item in explicit.warnings))

    def test_failed_task_writes_structured_failure_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            execution = TaskAgent(retriever=RateLimitedRetriever()).run(
                TaskRequest(
                    goal="OpenAlex 检索失败诊断",
                    task_type="literature_review",
                    source="openalex",
                    max_sources=3,
                ),
                out,
            )
            self.assertEqual(execution.status, "failed")
            self.assertEqual(execution.failure["schema_version"], "task-failure-0.1")
            self.assertEqual(execution.failure["error_type"], "OpenAlexError")
            self.assertTrue(execution.failure["retryable"])
            self.assertIn("OPENALEX_API_KEY", execution.failure["suggested_action"])
            self.assertIn("failure.json", execution.artifacts)
            saved = json.loads((out / "failure.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, execution.failure)
            task = json.loads((out / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(task["status"], "failed")
            self.assertEqual(task["failure"]["error_type"], "OpenAlexError")
            self.assertIn("failure.json", task["artifacts"])

    def test_missing_local_corpus_is_not_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            execution = TaskAgent().run(
                TaskRequest(
                    goal="本地全文检索",
                    task_type="literature_review",
                    source="local",
                    corpus_dir=str(Path(tmp) / "missing-corpus"),
                ),
                Path(tmp),
            )
            self.assertEqual(execution.status, "failed")
            self.assertFalse(execution.failure["retryable"])
            self.assertIn("local corpus", execution.failure["suggested_action"])

    def test_full_task_reuses_pipeline_and_stops_at_human_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            execution = self.agent.run(
                TaskRequest(
                    goal="验证界面钝化对湿热稳定性的影响，并形成工作稿",
                    task_type="full_research",
                    source="fixture",
                ),
                out,
            )
            self.assertEqual(execution.status, "needs_human")
            self.assertIn("report.md", execution.artifacts)
            self.assertIn("paper.md", execution.artifacts)
            self.assertTrue((out / "task-report.md").is_file())
            checks = {item["name"]: item["status"] for item in execution.checks}
            self.assertEqual(checks["paper_draft"], "pass")
            self.assertEqual(checks["pipeline_status"], "pass")
            packages = {item["id"]: item for item in execution.evidence_packages}
            self.assertEqual(packages["claim"]["status"], "missing")
            self.assertEqual(packages["closure"]["status"], "blocked")
            report = (out / "task-report.md").read_text(encoding="utf-8")
            self.assertIn("证据包状态", report)

    def test_strict_hypothesis_task_stops_before_design_without_g1(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            execution = self.agent.run(
                TaskRequest(
                    goal="钙钛矿界面钝化 湿热稳定性 假设设计",
                    task_type="hypothesis_design",
                    source="fixture",
                    max_sources=4,
                    flow_mode="strict",
                ),
                out,
            )
            self.assertEqual(execution.status, "needs_human")
            self.assertEqual(execution.stopped_at, "G1")
            self.assertTrue((out / "idea.json").is_file())
            self.assertFalse((out / "experiment.json").exists())
            report = (out / "task-report.md").read_text(encoding="utf-8")
            self.assertIn("停止点：`G1`", report)

    def test_strict_full_task_stops_at_first_gate_and_keeps_resume_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            execution = self.agent.run(
                TaskRequest(
                    goal="钙钛矿 界面 钝化 稳定性",
                    task_type="full_research",
                    source="fixture",
                    max_sources=6,
                    flow_mode="strict",
                ),
                out,
            )
            self.assertEqual(execution.status, "needs_human")
            self.assertEqual(execution.stopped_at, "G1")
            self.assertTrue((out / "idea.json").is_file())
            self.assertTrue((out / "idea-review.json").is_file())
            self.assertFalse((out / "paper.md").exists())
            saved = json.loads((out / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["stopped_at"], "G1")
            self.assertTrue(saved["gates"])

            idea = json.loads((out / "idea.json").read_text(encoding="utf-8"))
            candidate = (idea.get("candidates") or [None])[0]
            self.assertIsNotNone(candidate)
            decision = out / "g1-decision.json"
            decision.write_text(
                json.dumps({
                    "status": "approved",
                    "selected_idea_id": candidate["idea_id"],
                    "human_reason": "strict resume test",
                }),
                encoding="utf-8",
            )
            resumed_out = out / "resumed"
            resumed = self.agent.run(
                TaskRequest(
                    goal="钙钛矿 界面 钝化 稳定性",
                    task_type="full_research",
                    source="fixture",
                    max_sources=6,
                    flow_mode="strict",
                    g1_decision_file=str(decision),
                ),
                resumed_out,
            )
            self.assertEqual(resumed.stopped_at, "G2")
            self.assertTrue((resumed_out / "experiment.json").is_file())
            self.assertTrue((resumed_out / "idea-review.json").is_file())
            self.assertTrue((resumed_out / "design-audit.json").is_file())

    def test_experiment_validation_requires_run_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            execution = self.agent.run(
                TaskRequest(
                    goal="复现一个本地实验",
                    task_type="experiment_validation",
                    source="fixture",
                    run_dataset="",
                ),
                out,
            )
            self.assertEqual(execution.status, "needs_input")
            self.assertTrue(any("run_dataset" in item for item in execution.warnings))
            self.assertFalse((out / "paper.md").exists())


if __name__ == "__main__":
    unittest.main()

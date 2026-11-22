"""判据 A（design/165）：同一研究内容、两个不同方法，事件流里的阶段序列必须不同。

这是"方法真正编排阶段"的可证伪门槛。事件序列相同 = 计划卡不同但执行没变 = 不算做到。
本测试在实现之前写，先红；design/173 把判据 A 提升为完成门槛。
"""

import tempfile
import unittest
from pathlib import Path

from research_agent.pipeline import PipelineRequest, PipelineRunner
from research_agent.specs import SpecStore


class CriterionATest(unittest.TestCase):
    """Same content, two methods -> different stage_start sequence."""

    @classmethod
    def setUpClass(cls):
        cls.store = SpecStore()

    def _run(self, method_id: str, topic: str = "钙钛矿 界面 钝化 稳定性"):
        events = []
        with tempfile.TemporaryDirectory() as tmp:
            result = PipelineRunner(
                self.store,
                run_output_dir=Path(tmp) / "run",
                event_sink=events.append,
            ).run(
                PipelineRequest(
                    topic=topic,
                    language="zh",
                    venue_type="zh_core_journal",
                    method_id=method_id,
                    run_id="PIPE-ORCH-%s" % method_id,
                )
            )
        return result, [e for e in events if e.get("type") == "stage_start"]

    def test_two_methods_produce_different_stage_sequences(self):
        controlled, controlled_stages = self._run("controlled-experiment")
        mining, mining_stages = self._run("repository-mining")

        controlled_ids = [e["stage"] for e in controlled_stages]
        mining_ids = [e["stage"] for e in mining_stages]

        # The plan differs: controlled-experiment covers idea/paper,
        # repository-mining covers literature/run but not idea/paper.
        self.assertNotEqual(
            controlled_ids, mining_ids,
            "判据 A 失败：两个方法的 stage_start 序列相同 = 方法没有真正编排阶段",
        )

    def test_stage_sequence_matches_composition_plan(self):
        mining, events = self._run("repository-mining")
        plan = mining.modules["composition_plan"]
        covered = set(plan["covered_stages"])

        started = [e["stage"] for e in events if e["stage"] != "composition"]
        # Every executed stage must be declared covered by the method's plan.
        # (composition itself is a planning event, not a research stage.)
        for stage in started:
            self.assertIn(
                stage, covered,
                "%s executed but not in composition plan %s" % (stage, sorted(covered)),
            )

    def test_plan_order_is_reflected_in_execution_order(self):
        controlled, events = self._run("controlled-experiment")
        plan = controlled.modules["composition_plan"]
        covered = plan["covered_stages"]

        started = [e["stage"] for e in events if e["stage"] != "composition"]
        self.assertEqual(
            set(started), set(covered),
            "executed stages must equal the composition plan's covered set",
        )

    def test_skipped_stage_gates_are_not_applicable_not_pass(self):
        """判据 B 的治理面：跳过阶段的门不得伪装成 pass。"""
        slr, _ = self._run("systematic-literature-review")
        gates = {g["gate"]: g for g in slr.gates}
        # SLR covers literature/paper; idea and experiment are skipped.
        self.assertEqual(gates["G1"]["status"], "not_applicable")
        self.assertEqual(gates["G2"]["status"], "not_applicable")
        self.assertIn("composition", gates["G1"]["reason"])

    def test_skipped_stage_artifacts_carry_no_evidence(self):
        """跳过的阶段留下显式 not_applicable，不是空绑定也不是伪证据。"""
        mining, _ = self._run("repository-mining")
        # repository-mining does not cover idea -> no candidates, explicit status.
        self.assertEqual(mining.modules["idea"]["status"], "not_applicable")
        self.assertEqual(mining.modules["idea"].get("candidates") or [], [])
        # It does not cover figure -> no figure id payload masquerading as a result.
        self.assertEqual(mining.modules["figure"]["status"], "not_applicable")


if __name__ == "__main__":
    unittest.main()

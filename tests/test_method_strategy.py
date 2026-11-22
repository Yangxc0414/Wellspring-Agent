"""design/175: 研究方法形式化建模——护栏（AI 不可改）与可优化策略空间的二分。

核心主张：此前只建模护栏，没有建模"范式允许的自由空间"，所以流程级自改进无对象。
本测试钉住：guard 只能引用真实 check id；策略点不得触碰 LOCKED_SCOPES；
每个可优化分支必须带可判定的 evidence_of_effect——否则"优化"不可验证。
"""

import copy
import unittest

from research_agent.method_strategy import (
    StrategySpaceError,
    guardrails_for,
    load_strategy_space,
    strategy_points_for,
    validate_strategy_space,
)


class StrategySpaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.space = load_strategy_space()

    def test_space_loads_and_four_methods_are_modeled(self):
        modeled = [k for k, v in self.space["methods"].items() if v["status"] == "modeled"]
        self.assertCountEqual(
            modeled,
            ["controlled-experiment", "repository-mining", "case-study", "systematic-literature-review"],
        )

    def test_every_modeled_method_has_guardrails_and_choice_points(self):
        for mid, entry in self.space["methods"].items():
            if entry["status"] != "modeled":
                continue
            self.assertTrue(entry["hard_constraints"], mid)
            self.assertTrue(entry["choice_points"], mid)
            self.assertTrue(entry["boundary"].strip(), mid)

    def test_choice_points_are_queryable_by_stage(self):
        points = strategy_points_for(self.space, "controlled-experiment", stage="S4")
        self.assertEqual([p["id"] for p in points], ["randomization.scheme"])
        self.assertTrue(guardrails_for(self.space, "case-study"))

    def test_pending_methods_do_not_claim_optimizable_space(self):
        for mid, entry in self.space["methods"].items():
            if entry["status"] == "pending":
                self.assertEqual(entry["choice_points"], [], mid)

    def test_unknown_guard_is_rejected(self):
        bad = copy.deepcopy(self.space)
        bad["methods"]["controlled-experiment"]["choice_points"][0]["guard"] = ["check_that_does_not_exist"]
        with self.assertRaises(StrategySpaceError):
            validate_strategy_space(bad)

    def test_locked_scope_as_guard_is_rejected(self):
        bad = copy.deepcopy(self.space)
        bad["methods"]["case-study"]["choice_points"][0]["guard"] = ["gate.decision"]
        with self.assertRaises(StrategySpaceError):
            validate_strategy_space(bad)

    def test_missing_evidence_of_effect_is_rejected(self):
        bad = copy.deepcopy(self.space)
        bad["methods"]["repository-mining"]["choice_points"][0]["evidence_of_effect"] = ""
        with self.assertRaises(StrategySpaceError):
            validate_strategy_space(bad)

    def test_choice_point_outside_fit_stages_is_rejected(self):
        bad = copy.deepcopy(self.space)
        bad["methods"]["systematic-literature-review"]["choice_points"][0]["stage"] = "S13-S16"
        with self.assertRaises(StrategySpaceError):
            validate_strategy_space(bad)

    def test_option_conflicting_with_cannot_support_is_rejected(self):
        bad = copy.deepcopy(self.space)
        bad["methods"]["controlled-experiment"]["choice_points"][0]["options"].append("未操控变量的因果推断")
        with self.assertRaises(StrategySpaceError):
            validate_strategy_space(bad)


if __name__ == "__main__":
    unittest.main()

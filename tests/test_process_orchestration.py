"""design/177: 元模型驱动的编排——端口依赖推导顺序，阶段是带角色的契约实例。

钉住四件事：
1. 拓扑序必须等于合法 wiring 的声明序（两个 composition 各一条）；
2. 实际 order 只含方法覆盖的要素，契约数 == fit_stages 数；
3. 人签阶段与治理门来自元模型，不由方法改写；
4. 环 / 缺失上游端口必须 fail-closed，不猜顺序。
"""

import copy
import unittest

from research_agent.method_registry import load_registry
from research_agent.process_orchestration import (
    OrchestrationError,
    orchestration_plan,
    stage_contracts,
    topological_order,
)


class TopologicalOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def test_topological_order_matches_declared_wiring(self):
        for composition in self.registry["compositions"]:
            declared = [str(step["element"]) for step in composition["wiring"]]
            derived = [str(step["element"]) for step in topological_order(composition, self.registry)]
            self.assertEqual(derived, declared, composition["id"])

    def test_cycle_is_rejected_not_guessed(self):
        broken = copy.deepcopy(self.registry["compositions"][0])
        # 把证据挪到方案之前：证据消费"判别式协议"，而方案尚未产出 -> 无上游，必须拒绝
        wiring = broken["wiring"]
        evidence_index = next(i for i, s in enumerate(wiring) if s["element"] == "证据")
        evidence = wiring.pop(evidence_index)
        wiring.insert(1, evidence)
        with self.assertRaises(OrchestrationError):
            topological_order(broken, self.registry)

    def test_missing_upstream_port_is_rejected(self):
        broken = copy.deepcopy(self.registry["compositions"][0])
        broken["wiring"][4]["consumes"] = "一个没人产出的端口"
        with self.assertRaises(OrchestrationError):
            topological_order(broken, self.registry)

    def test_empty_wiring_is_rejected(self):
        with self.assertRaises(OrchestrationError):
            topological_order({"id": "empty", "wiring": []}, self.registry)


class StageContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry()

    def test_contract_count_equals_fit_stages(self):
        for method in self.registry["methods"]:
            contracts = stage_contracts(method["id"], self.registry)
            covered = [c for c in contracts if c["covered"]]
            self.assertEqual(
                len(covered), len(method["fit_stages"]),
                "%s: %d covered contracts vs %d fit stages"
                % (method["id"], len(covered), len(method["fit_stages"])),
            )

    def test_human_stages_cannot_be_agent_owned(self):
        contracts = {c["stage"]: c for c in stage_contracts("controlled-experiment", self.registry)}
        # 元模型把假设/方案/判定/写作标为 human=true；契约不得把它降成 agent。
        for stage in ("S2-S3", "S4", "S5b", "S8-S12"):
            self.assertTrue(contracts[stage]["human"], stage)
            self.assertTrue(contracts[stage]["locked_outputs"], stage)

    def test_gates_come_from_governance_not_method(self):
        contracts = {c["stage"]: c for c in stage_contracts("controlled-experiment", self.registry)}
        self.assertEqual(contracts["S4"]["gate"], "G2")
        self.assertEqual(contracts["S5b"]["gate"], "S5b")
        self.assertEqual(contracts["S8-S12"]["gate"], "G5")
        self.assertEqual(contracts["S5"]["gate"], "")

    def test_each_check_belongs_to_exactly_one_stage(self):
        contracts = stage_contracts("controlled-experiment", self.registry)
        seen = {}
        for contract in contracts:
            for check in contract["checks"]:
                self.assertNotIn(check, seen, "%s appears in %s and %s" % (check, seen.get(check), contract["stage"]))
                seen[check] = contract["stage"]
        self.assertEqual(seen.get("experiment.power"), "S4")
        self.assertEqual(seen.get("experiment.hypothesis"), "S2-S3")

    def test_actual_order_excludes_uncovered_elements(self):
        plan = orchestration_plan("systematic-literature-review", self.registry)
        self.assertEqual(plan["order"], ["问题", "证据", "写作"])
        self.assertIn("假设", plan["full_order"])
        self.assertNotIn("假设", plan["order"])

    def test_contract_is_read_only_projection(self):
        before = copy.deepcopy(self.registry)
        orchestration_plan("repository-mining", self.registry)
        self.assertEqual(self.registry, before)


if __name__ == "__main__":
    unittest.main()

"""design/178: 阶段角色（AgentRole）与统一端口接口。

钉住四件事：
1. 每个治理阶段有且仅有一个角色，模块真实存在；
2. S5b（claim 人签）必须是 human 且无 agent —— 治理不变量，不是配置项；
3. 人签阶段不得绑定 agent，agent 阶段不得用 sign 接口；
4. 不同接口（run/execute）能被适配成统一 run，且适配后仍可寻址。
"""

import copy
import unittest

from research_agent.method_registry import load_registry
from research_agent.process_orchestration import stage_contracts
from research_agent.stage_agents import (
    StageAgentError,
    as_stage_agent,
    assert_bindable,
    binding_for,
)
from research_agent.stage_roles import (
    StageRoleError,
    load_stage_roles,
    merge_into_contracts,
    role_for,
    validate_stage_roles,
)


class _RunStyleAgent:
    module_id = "idea"

    def run(self, request):
        return "ran:" + str(request)


class _ExecuteStyleAgent:
    module_id = "run"

    def execute(self, request):
        return "executed:" + str(request)


class StageRoleDeclarationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.roles = load_stage_roles()
        cls.registry = load_registry()

    def test_every_registry_stage_has_exactly_one_role(self):
        declared = {str(s["id"]) for s in self.registry["stages"]}
        seen = [str(entry["stage"]) for entry in self.roles["roles"]]
        for stage in declared:
            self.assertEqual(seen.count(stage), 1, stage)

    def test_claim_signing_is_human_only(self):
        claim = role_for(self.roles, "S5b")
        self.assertEqual(claim["executor"], "human")
        self.assertEqual(claim["module"], "")
        self.assertEqual(claim["interface"], "sign")
        self.assertEqual(claim["human_sign"], "S5b")

    def test_agent_role_binding_a_module_must_exist(self):
        broken = copy.deepcopy(self.roles)
        next(entry for entry in broken["roles"] if entry["stage"] == "S1")["module"] = "no-such-module"
        with self.assertRaises(StageRoleError):
            validate_stage_roles(broken)

    def test_human_stage_cannot_bind_a_module(self):
        broken = copy.deepcopy(self.roles)
        claim = next(entry for entry in broken["roles"] if entry["stage"] == "S5b")
        claim["module"] = "run"
        with self.assertRaises(StageRoleError):
            validate_stage_roles(broken)

    def test_claim_signer_cannot_be_turned_into_an_agent(self):
        broken = copy.deepcopy(self.roles)
        claim = next(entry for entry in broken["roles"] if entry["stage"] == "S5b")
        claim["executor"] = "agent"
        claim["module"] = "run"
        claim["interface"] = "run"
        with self.assertRaises(StageRoleError):
            validate_stage_roles(broken)

    def test_missing_stage_declaration_is_rejected(self):
        broken = copy.deepcopy(self.roles)
        broken["roles"] = [r for r in broken["roles"] if r["stage"] != "S6"]
        with self.assertRaises(StageRoleError):
            validate_stage_roles(broken)

    def test_unknown_interface_is_rejected(self):
        broken = copy.deepcopy(self.roles)
        next(entry for entry in broken["roles"] if entry["stage"] == "S4")["interface"] = "magic"
        with self.assertRaises(StageRoleError):
            validate_stage_roles(broken)


class StageAgentAdaptersTest(unittest.TestCase):
    def test_run_style_agent_passes_through(self):
        agent = as_stage_agent(_RunStyleAgent(), "idea", "run")
        self.assertEqual(agent.run("x"), "ran:x")

    def test_execute_style_agent_is_adapted_to_run(self):
        agent = as_stage_agent(_ExecuteStyleAgent(), "run", "execute")
        self.assertEqual(agent.run("y"), "executed:y")
        self.assertEqual(agent.module_id, "run")

    def test_signing_cannot_be_delegated_to_an_agent(self):
        with self.assertRaises(StageAgentError):
            binding_for({"stage": "S5b", "executor": "agent", "module": "run", "interface": "sign"})

    def test_human_stage_refuses_an_agent(self):
        with self.assertRaises(StageAgentError):
            assert_bindable(
                {"stage": "S5b", "executor": "human", "module": "", "interface": "sign"},
                _RunStyleAgent(),
            )

    def test_agent_stage_without_module_is_rejected(self):
        with self.assertRaises(StageAgentError):
            binding_for({"stage": "S4", "executor": "agent", "module": "", "interface": "run"})


class ContractRoleMergeTest(unittest.TestCase):
    def test_contracts_carry_role_and_do_not_lose_fields(self):
        contracts = stage_contracts("controlled-experiment", load_registry())
        by_stage = {c["stage"]: c for c in contracts}
        self.assertEqual(by_stage["S4"]["role"], "experiment-designer")
        self.assertEqual(by_stage["S4"]["human_sign"], "G2")
        self.assertEqual(by_stage["S5b"]["executor"], "human")
        # 原有契约字段仍在
        for key in ("requires", "produces", "human", "gate", "tasks", "checks", "covered"):
            self.assertIn(key, by_stage["S4"])

    def test_merge_is_pure(self):
        roles = load_stage_roles()
        contracts = [{"stage": "S4", "element": "方案", "covered": True}]
        before = copy.deepcopy(contracts)
        merge_into_contracts(roles, contracts)
        self.assertEqual(contracts, before)


if __name__ == "__main__":
    unittest.main()

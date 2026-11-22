"""阶段智能体的统一寻址与端口适配（design/178）。

现状（核查所得）：
- 已有 7 个阶段 agent，但接口不统一：LiteratureAgent/IdeaAgent/... 用 `run(request)`，
  RunAgent 用 `execute(request)`；
- pipeline 用 if/else 硬编码 module id，角色不是数据；
- "谁执行"和"谁签"混在一个 human bool 里。

本模块提供两样东西，让"不同阶段不同智能体"从隐式约定变成可寻址契约：
1. `as_stage_agent(agent)`：把任意阶段 agent 适配成统一的 `run(request) -> result`；
2. `binding_for(role)`：把 (stage, role) 声明翻译成可校验的绑定描述，
   并显式拒绝"给人签阶段配 agent"这种越界。

它不构造真实 agent（那需要 SPEC 与依赖注入，仍在 PipelineRunner 里），
只保证：**契约声明的角色，必须能被统一接口寻址；人签阶段必须没有 agent。**
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable


class StageAgentError(ValueError):
    pass


@runtime_checkable
class StageAgent(Protocol):
    """所有阶段智能体的统一面：一个 module_id，一个 run(request)。"""

    module_id: str

    def run(self, request: Any) -> Any:
        ...


class AgentAdapter:
    """把 execute/check/propose 之类的专用方法适配成统一 run。"""

    def __init__(self, agent: Any, module_id: str, method: str) -> None:
        if not hasattr(agent, method):
            raise StageAgentError(
                "module %s does not implement %s()" % (module_id, method)
            )
        self._agent = agent
        self.module_id = module_id
        self.interface = method

    def run(self, request: Any) -> Any:
        return getattr(self._agent, self.interface)(request)

    def __getattr__(self, name: str) -> Any:
        # 保留原 agent 的其他能力（如 claim/execute），但统一入口仍是 run。
        return getattr(self._agent, name)


def as_stage_agent(agent: Any, module_id: Optional[str] = None, interface: str = "run") -> StageAgent:
    """把阶段 agent 适配成统一 run 接口；已实现 run 的直接返回。"""
    resolved = module_id or str(getattr(agent, "module_id", "") or "")
    if not resolved:
        raise StageAgentError("agent has no module_id; pass it explicitly")
    if interface == "run" and hasattr(agent, "run"):
        return agent
    return AgentAdapter(agent, resolved, interface)


def binding_for(role: Dict[str, Any]) -> Dict[str, str]:
    """把一条角色声明翻译成绑定描述；越界的组合直接拒绝。"""
    stage = str(role.get("stage") or "")
    executor = str(role.get("executor") or "")
    module = str(role.get("module") or "")
    interface = str(role.get("interface") or "")
    if not stage:
        raise StageAgentError("role stage required")
    if executor == "human":
        if module:
            raise StageAgentError(
                "%s: a human-owned stage must not bind agent module %s" % (stage, module)
            )
        if interface not in ("sign",):
            raise StageAgentError("%s: human-owned stage must use interface=sign" % stage)
    else:
        if not module:
            raise StageAgentError("%s: agent-owned stage needs a module" % stage)
        if interface in ("sign",):
            raise StageAgentError("%s: signing cannot be delegated to an agent" % stage)
    return {
        "stage": stage,
        "role": str(role.get("role") or ""),
        "executor": executor,
        "module": module,
        "interface": interface,
        "human_sign": str(role.get("human_sign") or ""),
    }


def assert_bindable(role: Dict[str, Any], agent: Any) -> StageAgent:
    """按角色声明校验 agent 并返回统一接口——用于将来编排器按契约寻址。"""
    binding = binding_for(role)
    if binding["executor"] == "human":
        raise StageAgentError(
            "%s is human-owned; refusing to bind an agent" % binding["stage"]
        )
    return as_stage_agent(agent, binding["module"], binding["interface"])

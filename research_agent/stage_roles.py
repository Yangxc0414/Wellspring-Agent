"""阶段角色（AgentRole）的只读声明与校验（design/178）。

老师的框架把 AgentRole 列为元元素之一；我们此前已有 7 个阶段 agent，但：
- 角色没有显式声明（pipeline 用 if/else 硬编码 module id）；
- 接口不统一（RunAgent.execute vs 其他 run）；
- "谁执行"与"谁签"混在一个 human bool 里。

本模块把 (stage, role) 声明成数据，并 fail-closed 校验：
1. 每个治理阶段必须有且仅有一个角色；
2. module 必须存在于 modules/；executor=human 时不得绑定 module；
3. interface/executor/human_sign 必须来自封闭词表；
4. **S5b 必须是 human**——agent 不得代签 claim（治理不变量，不是可配置项）。

只读：不启动 agent、不读门禁、不产生 Claim。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROLES = ROOT / "modules" / "method-registry" / "stage-roles.json"
DEFAULT_REGISTRY = ROOT / "modules" / "method-registry" / "registry.json"
MODULES_DIR = ROOT / "modules"

SCHEMA = "ese-stage-roles-0.1"
# META 不在 registry.stages 里，但它是治理阶段（经验/自改进），允许声明。
EXTRA_STAGES = {"META"}


class StageRoleError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StageRoleError(message)


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StageRoleError("cannot load %s: %s" % (path, exc))


def known_modules() -> Set[str]:
    """真实实现模块；排除 _template 与只读资料目录。"""
    return {
        path.name
        for path in MODULES_DIR.iterdir()
        if path.is_dir()
        and not path.name.startswith("_")
        and (path / "SPEC.md").is_file()
    }


def load_stage_roles(path: Path = DEFAULT_ROLES, registry_path: Path = DEFAULT_REGISTRY) -> Dict[str, Any]:
    roles = load_json(path)
    validate_stage_roles(roles, registry_path)
    return roles


def validate_stage_roles(
    roles: Dict[str, Any],
    registry_path: Path = DEFAULT_REGISTRY,
    modules: Optional[Set[str]] = None,
) -> None:
    _require(isinstance(roles, dict), "stage roles must be an object")
    _require(str(roles.get("schema") or "") == SCHEMA, "schema must be " + SCHEMA)

    interfaces = set(roles.get("interfaces") or [])
    executors = set(roles.get("executors") or [])
    sign_gates = set(roles.get("sign_gates") or [])
    _require(interfaces == {"internal", "run", "execute", "check", "sign", "propose"},
             "interfaces must be the closed set internal/run/execute/check/sign/propose")
    _require(executors == {"agent", "human", "hybrid"},
             "executors must be agent/human/hybrid")
    _require(sign_gates == {"Q0", "G1", "G2", "S5b", "G5", "lease"},
             "sign_gates must be Q0/G1/G2/S5b/G5/lease")

    registry = load_json(registry_path)
    declared_stages = [str(s.get("id") or "") for s in (registry.get("stages") or [])]
    available_modules = modules if modules is not None else known_modules()

    entries = roles.get("roles")
    _require(isinstance(entries, list) and entries, "roles must be a non-empty list")

    seen: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        _require(isinstance(entry, dict), "role entry must be an object")
        stage = str(entry.get("stage") or "")
        _require(bool(stage), "role stage required")
        _require(stage not in seen, "duplicate role for stage " + stage)
        _require(
            stage in declared_stages or stage in EXTRA_STAGES,
            "role stage not in registry: " + stage,
        )
        role = str(entry.get("role") or "")
        _require(bool(role), stage + ": role name required")
        interface = str(entry.get("interface") or "")
        _require(interface in interfaces, stage + ": unknown interface " + interface)
        executor = str(entry.get("executor") or "")
        _require(executor in executors, stage + ": unknown executor " + executor)
        module = str(entry.get("module") or "")
        human_sign = str(entry.get("human_sign") or "")
        _require(not human_sign or human_sign in sign_gates, stage + ": unknown sign gate " + human_sign)

        if executor == "human":
            _require(not module, stage + ": a human-owned stage must not bind an agent module")
        else:
            _require(bool(module), stage + ": an agent/hybrid stage must bind a module")
            _require(module in available_modules, stage + ": unknown module " + module)
        _require(bool(str(entry.get("description") or "")), stage + ": description required")
        seen[stage] = entry

    missing = [stage for stage in declared_stages if stage not in seen]
    _require(not missing, "missing role declaration for stages: " + ", ".join(missing))

    # 治理不变量：claim 签署只能由人完成，不能因为配置改成一个 agent。
    claim_role = seen.get("S5b")
    _require(claim_role is not None, "S5b must declare a role")
    _require(
        claim_role.get("executor") == "human" and not claim_role.get("module"),
        "S5b must be human-owned with no agent module; agents never sign claims",
    )


def role_for(roles: Dict[str, Any], stage: str) -> Optional[Dict[str, Any]]:
    for entry in roles.get("roles") or []:
        if str(entry.get("stage") or "") == stage:
            return dict(entry)
    return None


def merge_into_contracts(roles: Dict[str, Any], contracts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把角色并入阶段契约（不覆盖契约已有字段，只补 role/executor/interface/module/human_sign）。"""
    merged: List[Dict[str, Any]] = []
    for contract in contracts:
        item = dict(contract)
        entry = role_for(roles, str(contract.get("stage") or "")) or {}
        item["role"] = str(entry.get("role") or "")
        item["executor"] = str(entry.get("executor") or "")
        item["interface"] = str(entry.get("interface") or "")
        item["agent_module"] = str(entry.get("module") or "")
        item["human_sign"] = str(entry.get("human_sign") or "")
        item["role_description"] = str(entry.get("description") or "")
        merged.append(item)
    return merged

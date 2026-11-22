"""研究方法的形式化"策略空间"只读视图（design/175）。

导师框架：方法建模必须区分**硬性约束（护栏，AI 不可改）**与**可选策略分支（自改进空间）**。
registry.json 已经把护栏建得很扎实（checks / protocol_fields / cannot_support / iteration_rule），
但没有一等字段描述"范式允许的自由空间"——于是自改进只能改 skill，改不了流程。

本模块提供：
- `load_strategy_space()`：读 modules/method-registry/strategy-space.json；
- `validate_strategy_space(space, registry)`：fail-closed 校验：
    1. guard 必须引用真实 check id 或 LOCKED_SCOPES id；
    2. 策略点必须落在 fit_stages 内；
    3. 策略点不得触碰 LOCKED_SCOPES；
    4. 每个策略点必须有 evidence_of_effect（否则"优化"无法判定）；
    5. options 不得与 cannot_support 冲突（粗粒度关键词检查，见下同）。
- 所有输出只读，不改注册表、不读门禁、不产生 Claim。
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from .evolution_policy import LOCKED_SCOPES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPACE = ROOT / "modules" / "method-registry" / "strategy-space.json"
DEFAULT_REGISTRY = ROOT / "modules" / "method-registry" / "registry.json"

SCHEMA = "ese-method-strategy-space-0.1"


class StrategySpaceError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StrategySpaceError(message)


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StrategySpaceError("cannot load %s: %s" % (path, exc))


def load_strategy_space(path: Path = DEFAULT_SPACE) -> Dict[str, Any]:
    space = load_json(path)
    validate_strategy_space(space)
    return space


def validate_strategy_space(space: Dict[str, Any], registry: Path = DEFAULT_REGISTRY) -> None:
    """Fail closed on malformed strategy data — it is shipped data, not ad-hoc input."""
    _require(isinstance(space, dict), "strategy space must be an object")
    _require(str(space.get("schema") or "") == SCHEMA, "schema must be " + SCHEMA)
    methods = space.get("methods")
    _require(isinstance(methods, dict) and methods, "strategy space needs methods")

    reg = load_json(registry)
    reg_methods = {str(m.get("id") or ""): m for m in (reg.get("methods") or [])}
    locked = set(str(item.get("id") or "") for item in LOCKED_SCOPES)
    declared_locked = set(space.get("locked_scopes") or [])
    _require(locked == declared_locked, "locked_scopes must mirror LOCKED_SCOPES exactly")

    for mid, entry in methods.items():
        _require(mid in reg_methods, "%s: method not in registry" % mid)
        _require(isinstance(entry, dict), "%s: entry must be an object" % mid)
        status = str(entry.get("status") or "")
        _require(status in ("modeled", "pending"), "%s: unknown status %s" % (mid, status))
        points = entry.get("choice_points")
        _require(isinstance(points, list), "%s: choice_points must be a list" % mid)
        if status == "pending":
            _require(not points, "%s: pending method must not declare choice points" % mid)
            continue

        method = reg_methods[mid]
        fit = set(method.get("fit_stages") or [])
        check_ids = set(str(c.get("id") or "") for c in (method.get("checks") or []))
        allowed_guards = check_ids | locked
        cannot = [str(x) for x in (method.get("cannot_support") or [])]

        _require(bool(entry.get("hard_constraints")), "%s: modeled method needs hard_constraints" % mid)
        for guard in entry["hard_constraints"]:
            _require(guard in allowed_guards, "%s: unknown hard constraint %s" % (mid, guard))

        ids = set()
        for point in points:
            _require(isinstance(point, dict), "%s: choice point must be an object" % mid)
            pid = str(point.get("id") or "")
            _require(bool(pid) and pid not in ids, "%s: duplicate/empty choice point id" % mid)
            ids.add(pid)
            stage = str(point.get("stage") or "")
            _require(stage in fit, "%s/%s: stage %s outside fit_stages" % (mid, pid, stage))

            options = point.get("options")
            _require(isinstance(options, list) and options, "%s/%s: options required" % (mid, pid))
            guards = point.get("guard")
            _require(isinstance(guards, list) and guards, "%s/%s: guard required" % (mid, pid))
            for guard in guards:
                _require(guard in allowed_guards, "%s/%s: unknown guard %s" % (mid, pid, guard))
                _require(guard not in locked, "%s/%s: guard touches LOCKED_SCOPE %s" % (mid, pid, guard))

            _require(
                bool(str(point.get("evidence_of_effect") or "").strip()),
                "%s/%s: evidence_of_effect required (otherwise optimization is unverifiable)" % (mid, pid),
            )
            _require(
                isinstance(point.get("reversible"), bool),
                "%s/%s: reversible must be bool" % (mid, pid),
            )
            # Rule 5: option text must not claim a capability the method declares unsupported.
            for option in options:
                text = json.dumps(option, ensure_ascii=False)
                for forbidden in cannot:
                    if forbidden and forbidden in text:
                        raise StrategySpaceError(
                            "%s/%s: option %s conflicts with cannot_support %s" % (mid, pid, text, forbidden)
                        )


def strategy_points_for(space: Dict[str, Any], method_id: str, stage: str = "") -> List[Dict[str, Any]]:
    """只读查询：某方法（可指定阶段）的可优化策略点。"""
    entry = (space.get("methods") or {}).get(method_id) or {}
    points = entry.get("choice_points") or []
    return [dict(p) for p in points if not stage or p.get("stage") == stage]


def guardrails_for(space: Dict[str, Any], method_id: str) -> List[str]:
    entry = (space.get("methods") or {}).get(method_id) or {}
    return list(entry.get("hard_constraints") or [])

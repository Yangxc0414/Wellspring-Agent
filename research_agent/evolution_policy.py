"""Local self-evolution policy.

The switch is intentionally narrow. It can pause the process/skill changes that
have an implemented candidate path (memory ordering, query templates, facet
budget). It can never unlock claims, evidence, gates, rubrics, held-out data,
closure, signatures or export. Turning it off does not revoke historical leases
or confirmations; it only blocks new automatic candidates and memory ordering.
"""

from pathlib import Path
from typing import Any, Dict, Optional

from .paths import DEFAULT_EVOLUTION_POLICY_PATH
from .storage import JsonStoreError, now_iso, read_json, write_json_atomic

__all__ = [
    "DEFAULT_EVOLUTION_POLICY_PATH",
    "EVOLUTION_POLICY_SCHEMA",
    "LOCKED_SCOPES",
    "SAFE_SCOPES",
    "EvolutionPolicyError",
    "EvolutionPolicyStore",
]

EVOLUTION_POLICY_SCHEMA = "evolution-policy-0.1"

SAFE_SCOPES: Dict[str, Dict[str, str]] = {
    "literature.memory_order": {
        "label": "文献记忆调序",
        "kind": "process",
        "description": "按历史覆盖/缺口重排下一轮面向顺序与预算；关闭后使用均衡分组。",
    },
    "literature.query_planner": {
        "label": "检索模板候选",
        "kind": "skill",
        "description": "从 facet 级重复缺口生成 query-planner 候选；仍需 dry-run 与人工准入。",
    },
    "orchestrator.facet_budget": {
        "label": "面向预算候选",
        "kind": "process",
        "description": "从预算/全文约束生成预算或全文获取流程候选；不改变 full-text-only 规则。",
    },
    "literature.retrieval.budget": {
        "label": "检索预算参数",
        "kind": "process",
        "description": (
            "唯一可被 runtime 消费的检索预算参数（retriever + max_sources）。"
            "注册在此是为了让准入门管得到它：候选必须经 dry-run、四套评测与人签租约，"
            "激活后每次消费都会复查租约状态。"
        ),
    },
    "experiment.run.seeds": {
        "label": "S5 种子预算",
        "kind": "process",
        "description": (
            "S5 协议验证的种子数预算。注册在此是为了让准入门管得到它：种子只能由有效租约"
            "给出，撤销后立刻失效；它不改变任何门禁判定或签核。"
        ),
    },
    "harness2.harness": {
        "label": "Harness² 组件面",
        "kind": "process",
        "description": (
            "由 Harness²（递归 harness 改进）提出的 c1..c8 组件改动：system prompt、"
            "guardrails、memory、tool guidance、subagents、skills、scripts、plugins。"
            "注册在此是为了让准入门管得到它：候选仍须 dry-run、public/hidden 评测、人签与"
            "租约；平台不实现也不自动套用这些改动，且组件路径命中 claim/evidence/gate/"
            "closure 等不可变面时一律拒绝。"
        ),
    },
}

LOCKED_SCOPES = [
    {"id": "claim.statement", "label": "Claim 陈述", "reason": "必须由作者/PI 签署"},
    {"id": "evidence.artifact", "label": "EvidenceArtifact", "reason": "只能由运行与人签产生"},
    {"id": "gate.decision", "label": "门禁判定", "reason": "G1/G2/S5b/G5 只能人工放行"},
    {"id": "rubric", "label": "评价规则", "reason": "规则冻结，候选不得改写"},
    {"id": "heldout", "label": "Held-out 集合", "reason": "不得用于提案或调参"},
    {"id": "closure", "label": "闭包报告", "reason": "只能由闭包检查产生"},
    {"id": "signature", "label": "签名", "reason": "浏览器与编排器都不提供签核"},
    {"id": "export", "label": "导出清单", "reason": "未闭包/已过期时锁定"},
]


class EvolutionPolicyError(ValueError):
    pass


def _now() -> str:
    return now_iso()


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    write_json_atomic(path, payload)


def _default() -> Dict[str, Any]:
    return {
        "schema_version": EVOLUTION_POLICY_SCHEMA,
        "enabled": True,
        "scopes": {key: True for key in SAFE_SCOPES},
        "updated_at": "",
    }


def _read(path: Path) -> Dict[str, Any]:
    try:
        payload = read_json(path)
    except JsonStoreError as exc:
        raise EvolutionPolicyError(str(exc))
    if payload is None:
        return _default()
    if not isinstance(payload, dict):
        raise EvolutionPolicyError("evolution policy must be a JSON object")
    default = _default()
    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise EvolutionPolicyError("evolution policy enabled must be boolean")
    scopes = payload.get("scopes", {})
    if not isinstance(scopes, dict):
        raise EvolutionPolicyError("evolution policy scopes must be an object")
    normalized = {}
    for key in SAFE_SCOPES:
        value = scopes.get(key, True)
        if not isinstance(value, bool):
            raise EvolutionPolicyError("scope %s must be boolean" % key)
        normalized[key] = value
    default["enabled"] = enabled
    default["scopes"] = normalized
    default["updated_at"] = str(payload.get("updated_at", ""))
    return default


class EvolutionPolicyStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @property
    def boundary(self) -> str:
        return (
            "local visibility gate for automatic process/skill candidates; "
            "never unlocks Claim/EA/gate/rubric/held-out/closure/signature/export"
        )

    def get(self) -> Dict[str, Any]:
        return _read(self.path)

    def update(
        self,
        enabled: Optional[bool] = None,
        scopes: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        if enabled is None and not scopes:
            raise EvolutionPolicyError("provide enabled and/or at least one scope")
        if enabled is not None and not isinstance(enabled, bool):
            raise EvolutionPolicyError("enabled must be boolean")
        payload = self.get()
        if enabled is not None:
            payload["enabled"] = enabled
        if scopes:
            for key, value in scopes.items():
                if key in {item["id"] for item in LOCKED_SCOPES}:
                    raise EvolutionPolicyError("scope is immutable and cannot be toggled: " + key)
                if key not in SAFE_SCOPES:
                    raise EvolutionPolicyError("unknown or unsafe evolution scope: " + key)
                if not isinstance(value, bool):
                    raise EvolutionPolicyError("scope %s must be boolean" % key)
                payload["scopes"][key] = value
        payload["updated_at"] = _now()
        _atomic_write(
            self.path,
            {
                "schema_version": EVOLUTION_POLICY_SCHEMA,
                "enabled": payload["enabled"],
                "scopes": payload["scopes"],
                "updated_at": payload["updated_at"],
                "boundary": self.boundary,
            },
        )
        return self.get()

    def allows_memory_order(self) -> bool:
        payload = self.get()
        return bool(payload["enabled"] and payload["scopes"].get("literature.memory_order", True))

    def require_enabled(self) -> Dict[str, Any]:
        payload = self.get()
        if not payload["enabled"]:
            raise EvolutionPolicyError(
                "self-evolution policy is off; re-enable it with `rsi policy set --enabled`"
            )
        return payload

    def require_candidate(self, kind: str, target: str) -> None:
        self.require_enabled()
        if not self.allows_candidate(kind, target):
            raise EvolutionPolicyError("self-evolution policy blocks target scope: " + str(target))

    def allows_candidate(self, kind: str, target: str) -> bool:
        payload = self.get()
        if not payload["enabled"]:
            return False
        target_text = str(target or "").strip()
        if not target_text:
            return False
        for locked in LOCKED_SCOPES:
            if locked["id"] in target_text:
                return False
        if target_text.startswith("skill:"):
            return True
        for scope in SAFE_SCOPES:
            if target_text == scope or target_text.startswith(scope + ".") or target_text.startswith(
                scope + "/"
            ):
                return bool(payload["scopes"].get(scope, True))
        # Default deny: a new target namespace must be registered in SAFE_SCOPES
        # before automatic candidates can use it.
        return False

    def snapshot(self) -> Dict[str, Any]:
        payload = self.get()
        scopes = [
            {
                "id": key,
                **value,
                "enabled": bool(payload["scopes"].get(key, True)),
                "effective": bool(payload["enabled"] and payload["scopes"].get(key, True)),
                "allowed_by_master": bool(payload["enabled"]),
            }
            for key, value in SAFE_SCOPES.items()
        ]
        return {
            "schema_version": EVOLUTION_POLICY_SCHEMA,
            "generated_at": _now(),
            "enabled": bool(payload["enabled"]),
            "scopes": scopes,
            "locked": [dict(item) for item in LOCKED_SCOPES],
            "updated_at": payload.get("updated_at", ""),
            "boundary": self.boundary,
        }

    def export(self, path: Path) -> Dict[str, Any]:
        snapshot = self.snapshot()
        _atomic_write(Path(path), snapshot)
        return {"output": str(path), "enabled": snapshot["enabled"]}

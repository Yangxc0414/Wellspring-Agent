"""User-registered advisory subagents.

A custom agent is a declarative, read-only role. It cannot execute arbitrary
code, call external tools, write Claim/EA or pass a gate. Its allowed checks are
a fixed whitelist; tools and outputs are derived from those checks. The
orchestrator can therefore run the role deterministically without turning user
input into an unreviewed capability.
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .paths import DEFAULT_CUSTOM_AGENTS_PATH
from .storage import JsonStoreError, now_iso, read_json, write_json_atomic

__all__ = [
    "CHECK_ORDER",
    "CUSTOM_AGENTS_SCHEMA",
    "CUSTOM_AGENT_ROLES",
    "DEFAULT_CUSTOM_AGENTS_PATH",
    "SAFE_CHECKS",
    "CustomAgentError",
    "CustomAgentStore",
]

CUSTOM_AGENTS_SCHEMA = "custom-agents-0.1"
MAX_CUSTOM_AGENTS = 30
MAX_NAME = 60
MAX_PURPOSE = 400

CHECK_ORDER = (
    "coverage",
    "citation",
    "hypothesis",
    "protocol",
    "evidence",
    "figure",
    "closure",
)

SAFE_CHECKS: Dict[str, Dict[str, str]] = {
    "coverage": {
        "label": "覆盖审计",
        "stage": "S1",
        "tool": "coverage.inspect",
        "output": "CoverageAdvisory",
        "description": "检查全文数、面向覆盖与摘要-only 来源。",
    },
    "citation": {
        "label": "引用对齐",
        "stage": "S1",
        "tool": "citation.inspect",
        "output": "CitationAdvisory",
        "description": "检查候选帧引用的 span 是否存在于合并证据视图。",
    },
    "hypothesis": {
        "label": "假设审阅",
        "stage": "S2–S3",
        "tool": "idea.inspect",
        "output": "HypothesisAdvisory",
        "description": "检查候选的证据支持、跨来源与 lens 多样性。",
    },
    "protocol": {
        "label": "协议审阅",
        "stage": "S4",
        "tool": "protocol.inspect",
        "output": "ProtocolAdvisory",
        "description": "检查 baseline、指标、对照与 seeds；当前编排 stop point 之外。",
    },
    "evidence": {
        "label": "证据边界",
        "stage": "S5b",
        "tool": "evidence.inspect",
        "output": "EvidenceAdvisory",
        "description": "检查 claim/EA 边界；当前编排不产生 Claim，因此 deferred。",
    },
    "figure": {
        "label": "图形审阅",
        "stage": "S6",
        "tool": "figure.inspect",
        "output": "FigureAdvisory",
        "description": "检查图与 provenance；当前编排不执行 S6。",
    },
    "closure": {
        "label": "闭包审阅",
        "stage": "S13–S16",
        "tool": "closure.inspect",
        "output": "ClosureAdvisory",
        "description": "检查 closure/export；当前编排不执行 S13–S16。",
    },
}

CUSTOM_AGENT_ROLES: Dict[str, str] = {
    "reviewer": "审稿人",
    "auditor": "审计员",
    "scout": "侦察员",
    "methodologist": "方法学家",
    "writer-assistant": "写作助理",
}


class CustomAgentError(ValueError):
    pass


def _now() -> str:
    return now_iso()


def _new_id() -> str:
    return "CAG-%s-%s" % (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        uuid.uuid4().hex[:6],
    )


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    write_json_atomic(path, payload)


def _read(path: Path) -> List[Dict[str, Any]]:
    try:
        payload = read_json(path)
    except JsonStoreError as exc:
        raise CustomAgentError(str(exc))
    if payload is None:
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get("agents"), list):
        raise CustomAgentError("custom agents file must contain an agents list")
    return [item for item in payload["agents"] if isinstance(item, dict)]


def _clean(value: Any, limit: int, field: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise CustomAgentError("%s must not be empty" % field)
    if len(text) > limit:
        raise CustomAgentError("%s is longer than %d characters" % (field, limit))
    return text


def _derive(checks: Iterable[str]) -> Dict[str, Any]:
    selected = [str(item) for item in checks if str(item).strip()]
    if not selected:
        raise CustomAgentError("at least one check is required")
    unknown = sorted({item for item in selected if item not in SAFE_CHECKS})
    if unknown:
        raise CustomAgentError("unknown check(s): " + ", ".join(unknown))
    ordered = [item for item in CHECK_ORDER if item in set(selected)]
    stages: List[str] = []
    for check in ordered:
        stage = SAFE_CHECKS[check]["stage"]
        if stage not in stages:
            stages.append(stage)
    return {
        "checks": ordered,
        "check_labels": [SAFE_CHECKS[item]["label"] for item in ordered],
        "stages": stages,
        "stage": " / ".join(stages),
        "tools": list(dict.fromkeys(SAFE_CHECKS[item]["tool"] for item in ordered)),
        "outputs": list(dict.fromkeys(SAFE_CHECKS[item]["output"] for item in ordered)),
    }


class CustomAgentStore:
    """Local registry for advisory-only roles. It never runs code itself."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> List[Dict[str, Any]]:
        return _read(self.path)

    def _save(self, agents: List[Dict[str, Any]]) -> None:
        _atomic_write(
            self.path,
            {
                "schema_version": CUSTOM_AGENTS_SCHEMA,
                "updated_at": _now(),
                "count": len(agents),
                "agents": agents,
                "boundary": self.boundary,
            },
        )

    @property
    def boundary(self) -> str:
        return (
            "advisory only: whitelisted deterministic checks; no Claim/EA/gate, "
            "no arbitrary code, no external tools"
        )

    def add(
        self,
        name: str,
        role: str,
        purpose: str,
        checks: Iterable[str],
        enabled: bool = True,
    ) -> Dict[str, Any]:
        clean_name = _clean(name, MAX_NAME, "name")
        if len(clean_name) < 2:
            raise CustomAgentError("name must be at least 2 characters")
        clean_purpose = _clean(purpose, MAX_PURPOSE, "purpose")
        role = str(role or "")
        if role not in CUSTOM_AGENT_ROLES:
            raise CustomAgentError(
                "role must be one of: " + ", ".join(sorted(CUSTOM_AGENT_ROLES))
            )
        derived = _derive(checks)
        agents = self._load()
        if len(agents) >= MAX_CUSTOM_AGENTS:
            raise CustomAgentError("custom agent limit reached (%d)" % MAX_CUSTOM_AGENTS)
        if any(str(item.get("name", "")).lower() == clean_name.lower() for item in agents):
            raise CustomAgentError("custom agent name already exists: " + clean_name)
        stamp = _now()
        agent = {
            "id": _new_id(),
            "name": clean_name,
            "role": role,
            "role_label": CUSTOM_AGENT_ROLES[role],
            "purpose": clean_purpose,
            "enabled": bool(enabled),
            "advisory_only": True,
            "writes": [],
            "created_at": stamp,
            "updated_at": stamp,
            **derived,
        }
        agents.insert(0, agent)
        self._save(agents)
        return agent

    def update(
        self,
        agent_id: str,
        enabled: Optional[bool] = None,
        name: Optional[str] = None,
        purpose: Optional[str] = None,
        checks: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        agents = self._load()
        target = next((item for item in agents if item.get("id") == agent_id), None)
        if target is None:
            raise CustomAgentError("custom agent not found: " + str(agent_id))
        if name is not None:
            clean_name = _clean(name, MAX_NAME, "name")
            if len(clean_name) < 2:
                raise CustomAgentError("name must be at least 2 characters")
            if any(
                item is not target
                and str(item.get("name", "")).lower() == clean_name.lower()
                for item in agents
            ):
                raise CustomAgentError("custom agent name already exists: " + clean_name)
            target["name"] = clean_name
        if purpose is not None:
            target["purpose"] = _clean(purpose, MAX_PURPOSE, "purpose")
        if checks is not None:
            target.update(_derive(checks))
        if enabled is not None:
            target["enabled"] = bool(enabled)
        target["updated_at"] = _now()
        self._save(agents)
        return target

    def delete(self, agent_id: str) -> bool:
        agents = self._load()
        remaining = [item for item in agents if item.get("id") != agent_id]
        if len(remaining) == len(agents):
            return False
        self._save(remaining)
        return True

    def list(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        agents = sorted(self._load(), key=lambda item: str(item.get("created_at", "")), reverse=True)
        if enabled_only:
            return [item for item in agents if item.get("enabled", True)]
        return agents

    def snapshot(self) -> Dict[str, Any]:
        agents = self.list()
        return {
            "schema_version": CUSTOM_AGENTS_SCHEMA,
            "generated_at": _now(),
            "count": len(agents),
            "agents": agents,
            "checks": [
                {
                    "id": key,
                    "label": value["label"],
                    "stage": value["stage"],
                    "tool": value["tool"],
                    "output": value["output"],
                    "description": value["description"],
                }
                for key, value in SAFE_CHECKS.items()
            ],
            "roles": [{"id": key, "label": value} for key, value in CUSTOM_AGENT_ROLES.items()],
            "boundary": self.boundary,
        }

    def export(self, path: Path) -> Dict[str, Any]:
        snapshot = self.snapshot()
        _atomic_write(Path(path), snapshot)
        return {"output": str(path), "count": snapshot["count"]}

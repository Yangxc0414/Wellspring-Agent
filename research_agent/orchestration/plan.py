"""Collaboration plan, roles, handoffs and static topology."""

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..evolution_policy import LOCKED_SCOPES
from ..literature_memory import DEFAULT_SCOUT_GROUPS
from ..modules.literature import FACET_LABELS, FACET_ORDER
from . import ORCHESTRATION_SCHEMA
from .advisories import custom_agent_roles
from .common import fingerprint, now_iso
from .errors import OrchestrationError


GOVERNED_ROLES: Tuple[Dict[str, Any], ...] = (
    {
        "id": "coverage-auditor",
        "name": "覆盖审计",
        "stage": "S1",
        "module": "literature",
        "mode": "fan-in",
        "inputs": ["ScoutReport[]"],
        "outputs": ["MergedEvidenceView", "CoverageSummary"],
        "gates": ["Q0"],
        "executes": True,
    },
    {
        "id": "idea-facilitator",
        "name": "假设收敛",
        "stage": "S2–S3",
        "module": "idea",
        "mode": "sequential",
        "inputs": ["MergedEvidenceView"],
        "outputs": ["IdeaCard", "IdeaBrief"],
        "gates": ["G1"],
        "executes": True,
        "gate_owner": "human",
    },
    {
        "id": "protocol-designer",
        "name": "设计冻结",
        "stage": "S4",
        "module": "experiment",
        "mode": "gated",
        "inputs": ["IdeaCard"],
        "outputs": ["DesignCard", "ProtocolDraft"],
        "gates": ["G2"],
        "executes": False,
        "gate_owner": "human",
    },
    {
        "id": "runner",
        "name": "复现执行",
        "stage": "S5a",
        "module": "run",
        "mode": "gated",
        "inputs": ["DesignCard"],
        "outputs": ["RunCapsule"],
        "gates": ["X0–X7"],
        "executes": False,
    },
    {
        "id": "evidence-curator",
        "name": "证据判定",
        "stage": "S5b",
        "module": "run",
        "mode": "gated",
        "inputs": ["RunCapsule"],
        "outputs": ["EvidenceArtifact", "ClaimRecord"],
        "gates": ["S5"],
        "executes": False,
        "gate_owner": "human",
    },
    {
        "id": "figure-builder",
        "name": "结果图",
        "stage": "S6",
        "module": "figure",
        "mode": "gated",
        "inputs": ["ClaimRecord"],
        "outputs": ["FigureManifest"],
        "gates": [],
        "executes": False,
    },
    {
        "id": "writer",
        "name": "写作槽位",
        "stage": "S8–S12",
        "module": "paper",
        "mode": "gated",
        "inputs": ["ClaimRecord", "FigureManifest"],
        "outputs": ["PaperContract", "SectionSlots"],
        "gates": [],
        "executes": False,
    },
    {
        "id": "closure-auditor",
        "name": "闭包检查",
        "stage": "S13–S16",
        "module": "closure",
        "mode": "gated",
        "inputs": ["ClaimRecord", "SignatureRequest"],
        "outputs": ["ClosureReport", "ExportManifest"],
        "gates": ["G5"],
        "executes": False,
        "gate_owner": "human",
    },
    {
        "id": "rsi-governor",
        "name": "自进化治理",
        "stage": "META",
        "module": "rsi",
        "mode": "independent",
        "inputs": ["ProcessObservation", "SkillCandidate"],
        "outputs": ["EvalEvidence", "LeaseDecision"],
        "gates": [],
        "executes": False,
        "note": "allowed to evaluate and propose; admission/revoke stays on the human-governed RSI path",
    },
)


HANDOFFS: Tuple[Dict[str, Any], ...] = (
    {
        "from": "orchestrator",
        "to": "scout-*",
        "contract": "ScoutTask",
        "mode": "fan-out",
        "fields": ["question", "facet_subset", "budget", "source_scope"],
    },
    {
        "from": "scout-*",
        "to": "coverage-auditor",
        "contract": "ScoutReport",
        "mode": "fan-in",
        "fields": ["hits", "spans", "coverage", "brief"],
        "merge": "dedupe source_id/span_id; no scout may write a Claim",
    },
    {
        "from": "coverage-auditor",
        "to": "idea-facilitator",
        "contract": "MergedEvidenceView",
        "mode": "sequential",
        "fields": ["hits", "spans", "facet_coverage", "gaps"],
    },
    {
        "from": "idea-facilitator",
        "to": "human",
        "contract": "IdeaCard[]",
        "mode": "gate",
        "gate": "G1",
        "fields": ["candidates", "brief", "gaps"],
    },
    {
        "from": "human",
        "to": "protocol-designer",
        "contract": "G1Decision",
        "mode": "gate",
        "gate": "G2",
        "fields": ["metric", "baseline", "seeds", "controls"],
    },
    {
        "from": "evidence-curator",
        "to": "figure-builder",
        "contract": "ClaimRecord",
        "mode": "gate",
        "gate": "S5b",
        "fields": ["ea", "claim", "scope"],
    },
    {
        "from": "closure-auditor",
        "to": "human",
        "contract": "ClosureReport",
        "mode": "gate",
        "gate": "G5",
        "fields": ["report", "signature", "export_manifest"],
    },
    {
        "from": "rsi-governor",
        "to": "human",
        "contract": "SkillCandidate",
        "mode": "independent",
        "fields": ["patch", "dry_run", "public_eval", "hidden_eval", "regression"],
        "note": "orchestrator never admits; human admission is a separate gate",
    },
)


HUMAN_GATES: Tuple[Dict[str, str], ...] = (
    {"id": "G1", "after": "S2–S3", "reason": "候选假设收敛与新颖性仍需人工判断"},
    {"id": "G2", "after": "S4", "reason": "主指标、对照与 seeds 需要人工冻结"},
    {"id": "S5b", "after": "S5a", "reason": "Claim 只能由作者/PI 签署"},
    {"id": "G5", "after": "S13–S16", "reason": "闭包与导出需要人工放行"},
)


def balanced_groups(max_sources: int) -> List[Dict[str, Any]]:
    facets = list(FACET_ORDER)
    if max_sources < len(facets):
        facets = facets[:max_sources]
    budget = {facet: 1 for facet in facets}
    remaining = max(0, max_sources - len(facets))
    cursor = 0
    while remaining > 0 and facets:
        budget[facets[cursor % len(facets)]] += 1
        cursor += 1
        remaining -= 1
    groups: List[Dict[str, Any]] = []
    for index, default_group in enumerate(DEFAULT_SCOUT_GROUPS, start=1):
        members = [facet for facet in default_group if facet in budget]
        if not members:
            continue
        groups.append(
            {
                "role_id": "scout-%d" % index,
                "facets": members,
                "labels": [FACET_LABELS.get(facet, facet) for facet in members],
                "budget": sum(budget[facet] for facet in members),
                "per_facet_budget": {facet: budget[facet] for facet in members},
                "priority": 1.0,
            }
        )
    return groups


def scout_roles(groups: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    roles = []
    for group in groups:
        roles.append(
            {
                "id": str(group["role_id"]),
                "name": "文献侦察 · " + "/".join(str(label) for label in group.get("labels", [])),
                "stage": "S1",
                "module": "literature",
                "mode": "fan-out",
                "parallel_group": "s1-scouts",
                "facets": list(group.get("facets", [])),
                "inputs": ["ScoutTask"],
                "outputs": ["SourceHit[]", "Span[]", "CoverageReceipt", "LiteratureBrief"],
                "gates": ["Q0"],
                "budget": int(group.get("budget", 0)),
                "executes": True,
            }
        )
    return roles


def default_policy_summary() -> Dict[str, Any]:
    return {
        "enabled": True,
        "scopes": {
            "literature.memory_order": True,
            "literature.query_planner": True,
            "orchestrator.facet_budget": True,
        },
        "locked": [item["id"] for item in LOCKED_SCOPES],
        "boundary": "local visibility gate; never unlocks Claim/EA/gate/rubric/held-out/closure/signature/export",
    }


def summarize_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not policy:
        return default_policy_summary()
    scopes = {}
    raw_scopes = policy.get("scopes", [])
    if isinstance(raw_scopes, dict):
        scopes = {str(key): bool(value) for key, value in raw_scopes.items()}
    elif isinstance(raw_scopes, list):
        scopes = {
            str(item.get("id")): bool(item.get("enabled", True))
            for item in raw_scopes
            if isinstance(item, dict) and item.get("id")
        }
    if not scopes:
        scopes = default_policy_summary()["scopes"]
    return {
        "enabled": bool(policy.get("enabled", True)),
        "scopes": scopes,
        "locked": list(policy.get("locked") or [item["id"] for item in LOCKED_SCOPES]),
        "boundary": str(policy.get("boundary") or default_policy_summary()["boundary"]),
    }


def collaboration_plan(
    topic: str,
    max_sources: int = 6,
    source: str = "fixture",
    advice: Optional[Dict[str, Any]] = None,
    custom_agents: Optional[Sequence[Dict[str, Any]]] = None,
    evolution_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    text = " ".join((topic or "").split())
    if len(text) < 2 or len(text) > 500:
        raise OrchestrationError("topic must be 2-500 characters")
    if not 1 <= int(max_sources) <= 50:
        raise OrchestrationError("max_sources must be between 1 and 50")
    if source not in ("fixture", "real"):
        raise OrchestrationError("orchestrator source must be fixture or real; OpenAlex fan-out stays opt-in separately")
    groups = list((advice or {}).get("scout_groups") or balanced_groups(int(max_sources)))
    if not groups:
        raise OrchestrationError("no scout group can be scheduled with the current budget")
    custom_roles = custom_agent_roles(custom_agents or [])
    roles = [
        {
            "id": "orchestrator",
            "name": "研究编排器",
            "stage": "META",
            "module": "orchestrator",
            "mode": "control",
            "inputs": ["question", "budget", "memory_advice", "evolution_policy"],
            "outputs": ["ScoutTask[]", "StopDecision", "AdvisoryNote[]"],
            "gates": [],
            "executes": True,
            "forbidden": ["Claim", "EA", "gate", "signature", "admission"],
        }
    ]
    roles.extend(scout_roles(groups))
    roles.extend(custom_roles)
    roles.extend(dict(role) for role in GOVERNED_ROLES)
    policy_view = summarize_policy(evolution_policy)
    handoffs = [dict(item) for item in HANDOFFS]
    if custom_roles:
        handoffs.append(
            {
                "from": "coverage-auditor/idea-facilitator",
                "to": "custom-advisory",
                "contract": "AdvisoryNote[]",
                "mode": "custom-advisory",
                "fields": ["checks", "status", "summary", "details"],
                "note": "read-only deterministic checks; protocol/evidence/figure/closure stay deferred at this stop point",
            }
        )
    seed = {
        "topic": text,
        "source": source,
        "max_sources": int(max_sources),
        "groups": [
            {"role_id": group["role_id"], "facets": group["facets"], "budget": group["budget"]}
            for group in groups
        ],
        "custom_agents": [role["id"] for role in custom_roles],
        "policy": policy_view,
    }
    lanes: Dict[str, Any] = {
        "parallel": {
            "name": "S1 scout fan-out",
            "roles": [str(group["role_id"]) for group in groups],
            "max_workers": len(groups),
            "write_scope": "read-only retrieval; each scout returns its own facet report",
        },
        "fan_in": {
            "name": "coverage merge",
            "role": "coverage-auditor",
            "depends_on": [str(group["role_id"]) for group in groups],
            "merge_keys": ["source_id", "span_id"],
        },
        "sequential": ["idea-facilitator", "G1"],
        "independent": ["rsi-governor"],
    }
    if custom_roles:
        lanes["custom_advisory"] = {
            "name": "custom advisory checks",
            "roles": [role["id"] for role in custom_roles],
            "applies_at": "S1–S3",
            "write_scope": "advisory notes only; no Claim/EA/gate",
        }
    return {
        "schema_version": ORCHESTRATION_SCHEMA,
        "action": "collaboration-plan",
        "generated_at": now_iso(),
        "topic": text,
        "source": source,
        "fingerprint": fingerprint(seed),
        "topology": "fan-out → fan-in → sequential → human gate"
        + (" (+ advisory lane)" if custom_roles else ""),
        "roles": roles,
        "lanes": lanes,
        "handoffs": handoffs,
        "human_gates": [dict(item) for item in HUMAN_GATES],
        "budget": {
            "total_sources": int(max_sources),
            "groups": [
                {
                    "role_id": str(group["role_id"]),
                    "facets": list(group["facets"]),
                    "sources": int(group["budget"]),
                }
                for group in groups
            ],
        },
        "stop_at": "S2–S3 candidate frames",
        "blocked_at": "G1",
        "does_not_execute": [
            "G1/G2/S5b/G5 decisions",
            "S4 design freeze",
            "S5 run and Claim",
            "closure/signature/export",
            "RSI admission or revocation",
        ],
        "evolution_policy": policy_view,
        "memory": {
            "mode": (advice or {}).get("mode", source),
            "observed_runs": int((advice or {}).get("observed_runs", 0)),
            "cold_start": bool((advice or {}).get("cold_start", True)),
            "rationale": list((advice or {}).get("rationale") or []),
            "skill_candidate": (advice or {}).get("skill_candidate"),
            "applied": bool(policy_view["enabled"] and policy_view["scopes"].get("literature.memory_order", True)),
            "boundary": "memory reorders facets/budget only; it never supplies evidence",
        },
        "boundary": "Plan only: no retrieval, run, claim, gate, signature or skill admission is executed.",
    }


def topology_snapshot(
    custom_agents: Optional[Sequence[Dict[str, Any]]] = None,
    evolution_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Static role/handoff topology for the settings UI; no run is executed."""

    plan = collaboration_plan(
        "协作拓扑模板",
        6,
        "fixture",
        custom_agents=custom_agents,
        evolution_policy=evolution_policy,
    )
    plan.pop("fingerprint", None)
    plan["template"] = True
    plan["topic"] = ""
    plan["generated_at"] = now_iso()
    plan["note"] = "静态角色与 handoff 模板；具体 facet 预算由任务运行时按记忆重算"
    plan["boundary"] = "Topology only: the UI never runs scouts, claims, gates or admissions."
    return plan


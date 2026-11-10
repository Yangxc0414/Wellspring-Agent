"""Custom advisory roles and deterministic checks."""

from typing import Any, Dict, List, Sequence

from ..custom_agents import SAFE_CHECKS
from ..modules.literature import TARGET_FULL_TEXT


CURRENT_ADVISORY_CHECKS = {"coverage", "citation", "hypothesis"}


def custom_agent_roles(custom_agents: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    roles: List[Dict[str, Any]] = []
    for agent in custom_agents:
        checks = list(agent.get("checks", []))
        executable = [check for check in checks if check in CURRENT_ADVISORY_CHECKS]
        deferred = [check for check in checks if check not in CURRENT_ADVISORY_CHECKS]
        roles.append(
            {
                "id": str(agent.get("id", "")),
                "name": str(agent.get("name", "自定义子智能体")),
                "stage": str(agent.get("stage", "")),
                "module": "custom-advisory",
                "mode": "custom-advisory",
                "checks": checks,
                "check_labels": list(agent.get("check_labels", [])),
                "tools": list(agent.get("tools", [])),
                "outputs": list(agent.get("outputs", [])),
                "inputs": ["MergedEvidenceView", "IdeaCard[]"],
                "gates": [],
                "executes": bool(executable),
                "deferred_checks": deferred,
                "advisory_only": True,
                "writes": [],
                "gate_owner": "human",
            }
        )
    return roles


def advisory_notes(
    custom_agents: Sequence[Dict[str, Any]],
    merged: Dict[str, Any],
    idea: Any,
) -> List[Dict[str, Any]]:
    span_ids = {str(item.get("span_id", "")) for item in merged.get("spans", [])}
    candidates = list(getattr(idea, "candidates", []) or [])
    brief = getattr(idea, "brief", None)
    notes: List[Dict[str, Any]] = []
    for agent in custom_agents:
        for check in agent.get("checks", []):
            base = {
                "id": "ADV-%s-%s" % (agent.get("id", "custom"), check),
                "agent_id": str(agent.get("id", "")),
                "agent_name": str(agent.get("name", "")),
                "check": check,
                "check_label": SAFE_CHECKS.get(check, {}).get("label", check),
                "boundary": "advisory note only; no Claim/EA/gate",
            }
            if check == "coverage":
                full_text = int(merged.get("full_text", 0))
                covered = int(merged.get("covered_facets", 0))
                planned = max(1, int(merged.get("planned_facets", 0)))
                abstract_only = sum(1 for hit in merged.get("hits", []) if not hit.get("full_text"))
                ok = full_text >= TARGET_FULL_TEXT and covered / float(planned) >= 0.8
                if abstract_only:
                    ok = False
                notes.append(
                    {
                        **base,
                        "status": "pass" if ok else "warn",
                        "summary": "全文 %d/%d · 面向 %d/%d · 摘要-only %d"
                        % (full_text, TARGET_FULL_TEXT, covered, planned, abstract_only),
                        "details": [
                            "full_text_target=%d" % TARGET_FULL_TEXT,
                            "facet_ratio=%.2f" % (covered / float(planned)),
                            "abstract_only=%d" % abstract_only,
                        ],
                    }
                )
            elif check == "citation":
                refs = [str(ref) for card in candidates for ref in getattr(card, "evidence_refs", [])]
                missing = sorted({ref for ref in refs if ref not in span_ids})
                if not candidates:
                    status = "needs_attention"
                    summary = "没有候选帧可做引用对齐"
                elif missing:
                    status = "warn"
                    summary = "%d 个候选引用不在合并 span 中" % len(missing)
                else:
                    status = "pass"
                    summary = "%d 个候选引用全部落在合并 span 中" % len(set(refs))
                notes.append(
                    {
                        **base,
                        "status": status,
                        "summary": summary,
                        "details": ["candidates=%d" % len(candidates), "missing_refs=%d" % len(missing)],
                    }
                )
            elif check == "hypothesis":
                gaps = list(getattr(brief, "gaps", []) or [])
                if not candidates:
                    status = "needs_attention"
                    summary = "没有候选帧"
                elif "no_multi_source_candidate" in gaps or "single_source" in gaps:
                    status = "warn"
                    summary = "候选缺少跨来源支持"
                else:
                    status = "pass"
                    summary = "%d 个候选，跨来源与证据支持已检查" % len(candidates)
                notes.append(
                    {
                        **base,
                        "status": status,
                        "summary": summary,
                        "details": [
                            "candidates=%d" % len(candidates),
                            "multi_ref=%d" % int(getattr(brief, "multi_ref_candidates", 0) or 0),
                            "multi_source=%d" % int(getattr(brief, "multi_source_candidates", 0) or 0),
                            "novelty=unverified",
                        ],
                    }
                )
            else:
                stage = SAFE_CHECKS.get(check, {}).get("stage", "later stage")
                notes.append(
                    {
                        **base,
                        "status": "deferred",
                        "summary": "%s check 在当前 S1–S3 stop point 之外" % stage,
                        "details": ["not_executed=true", "stage=%s" % stage],
                    }
                )
    return notes


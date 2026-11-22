"""研究方法的认识论声明与推论判定（design/179）。

问题（design/179 诊断）：我们能按方法剪裁流程，但"什么算证据、证据怎么支撑结论"
仍是实证一元论——后端只有一种 EvidenceArtifact，claim 只认 source=run，
案例研究/SLR/DSR 的结论在系统里签不了字。

本模块补上两层只读能力：
1. `validate_epistemics()`：fail-closed 校验每个方法声明了
   evidence_form（什么算证据）/ inference_rule（允许怎么推论）/ constraints（顺序的方法论出处 + citation）。
2. `claim_support_check()`：按方法的推论规则判定"这批证据能否支撑这个 claim"，
   支持统计、模式匹配、主题综合、设计循环、描述五种规则——非统计形态不再被拒绝。

边界：只读判定，不产生、不签署 Claim；最终签署仍由人完成。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EPISTEMICS = ROOT / "modules" / "method-registry" / "epistemics.json"
DEFAULT_REGISTRY = ROOT / "modules" / "method-registry" / "registry.json"

SCHEMA = "ese-method-epistemics-0.1"
INFERENCE_RULES = frozenset(
    ("statistical", "pattern-match", "thematic-synthesis", "design-cycle", "descriptive")
)
# 要求跨来源交叉印证的规则：min_independent_sources 必须 >= 2，否则自相矛盾。
MULTI_SOURCE_RULES = frozenset(("pattern-match", "thematic-synthesis"))
# 占位文本：等同未填写。
PLACEHOLDERS = ("todo", "tbd", "待补", "待定", "xxx")


class EpistemicsError(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EpistemicsError(message)


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EpistemicsError("cannot load %s: %s" % (path, exc))


def _is_placeholder(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return not lowered or lowered in PLACEHOLDERS


def load_epistemics(
    path: Path = DEFAULT_EPISTEMICS, registry_path: Path = DEFAULT_REGISTRY
) -> Dict[str, Any]:
    payload = load_json(path)
    validate_epistemics(payload, registry_path)
    return payload


def validate_epistemics(
    payload: Dict[str, Any], registry_path: Path = DEFAULT_REGISTRY
) -> None:
    _require(isinstance(payload, dict), "epistemics must be an object")
    _require(str(payload.get("schema") or "") == SCHEMA, "schema must be " + SCHEMA)
    declared_rules = set(payload.get("inference_rules") or [])
    _require(
        declared_rules == INFERENCE_RULES,
        "inference_rules must be the closed set " + "/".join(sorted(INFERENCE_RULES)),
    )

    registry = load_json(registry_path)
    registry_methods = {str(m.get("id") or ""): m for m in (registry.get("methods") or [])}
    entries = payload.get("methods")
    _require(isinstance(entries, dict) and entries, "methods must be a non-empty object")

    missing = [mid for mid in registry_methods if mid not in entries]
    _require(not missing, "missing epistemics for methods: " + ", ".join(missing))
    unknown = [mid for mid in entries if mid not in registry_methods]
    _require(not unknown, "epistemics for unknown methods: " + ", ".join(unknown))

    for method_id, entry in entries.items():
        _require(isinstance(entry, dict), method_id + ": entry must be an object")
        status = str(entry.get("status") or "")
        _require(status in ("modeled", "partial"), method_id + ": unknown status " + status)

        form = entry.get("evidence_form")
        _require(isinstance(form, dict), method_id + ": evidence_form required")
        for key in ("id", "label", "hashable", "unit"):
            _require(
                not _is_placeholder(str(form.get(key) or "")),
                "%s: evidence_form.%s required (no placeholder)" % (method_id, key),
            )

        rule = str(entry.get("inference_rule") or "")
        _require(rule in INFERENCE_RULES, method_id + ": unknown inference_rule " + rule)
        _require(
            not _is_placeholder(str(entry.get("rule_detail") or "")),
            method_id + ": rule_detail required",
        )

        minimum = entry.get("min_independent_sources")
        _require(
            isinstance(minimum, int) and minimum >= 1,
            method_id + ": min_independent_sources must be an int >= 1",
        )
        if rule in MULTI_SOURCE_RULES:
            _require(
                minimum >= 2,
                "%s: rule %s requires >=2 independent sources (got %d); a multi-source rule "
                "with a single source is self-contradictory" % (method_id, rule, minimum),
            )

        fit = set(str(x) for x in (registry_methods[method_id].get("fit_stages") or []))
        constraints = entry.get("constraints")
        _require(
            isinstance(constraints, list) and constraints,
            method_id + ": at least one epistemic constraint required",
        )
        seen_ids: Set[str] = set()
        for constraint in constraints:
            _require(isinstance(constraint, dict), method_id + ": constraint must be an object")
            cid = str(constraint.get("id") or "")
            _require(bool(cid) and cid not in seen_ids, method_id + ": duplicate/empty constraint id")
            seen_ids.add(cid)
            _require(
                not _is_placeholder(str(constraint.get("constraint") or "")),
                "%s/%s: constraint text required" % (method_id, cid),
            )
            citation = str(constraint.get("citation") or "")
            _require(
                not _is_placeholder(citation),
                "%s/%s: citation required — an order constraint without a methodological "
                "source is just personal habit" % (method_id, cid),
            )
            stage = str(constraint.get("stage") or "")
            _require(
                stage in fit,
                "%s/%s: constraint stage %s outside fit_stages" % (method_id, cid, stage),
            )


def claim_support_check(
    method_id: str,
    *,
    evidence_items: List[Dict[str, Any]],
    assertions: Optional[List[Dict[str, Any]]] = None,
    generalises: bool = False,
    epistemics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """按方法的推论规则判定证据是否支撑 claim（只读，不签署）。

    evidence_items 每条至少要有：
      source_id（独立来源，如案例 id / 研究 id / 数据集 id）
      kind（artifact / evaluation / measurement / document / interview / observation）
      可选 pattern_id / theme_id（同一模式/主题的标识）
      可选 artifact_id（evaluation 指向的产物）
    """
    payload = epistemics or load_epistemics()
    entry = (payload.get("methods") or {}).get(method_id)
    _require(entry is not None, "unknown method " + method_id)
    rule = str(entry.get("inference_rule") or "")
    minimum = int(entry.get("min_independent_sources") or 1)
    items = list(evidence_items or [])
    blockers: List[str] = []

    if rule == "statistical":
        results = list(assertions or [])
        if not results:
            blockers.append("statistical rule needs at least one numeric assertion to recompute")
        for item in results:
            if str(item.get("status") or "") != "pass":
                blockers.append(
                    "assertion %s is %s" % (item.get("metric", "?"), item.get("status", "missing"))
                )

    elif rule in MULTI_SOURCE_RULES:
        key = "pattern_id" if rule == "pattern-match" else "theme_id"
        ids = {str(item.get(key) or "") for item in items if str(item.get(key) or "")}
        if len(ids) > 1:
            blockers.append(
                "evidence covers %d different %s values; a single claim must name one"
                % (len(ids), key)
            )
        sources = {str(item.get("source_id") or "") for item in items}
        sources.discard("")
        if len(sources) < minimum:
            blockers.append(
                "rule %s needs >=%d independent sources, got %d" % (rule, minimum, len(sources))
            )
        if rule == "pattern-match":
            types = {str(item.get("kind") or "") for item in items}
            types.discard("")
            if len(types) < 2:
                blockers.append(
                    "pattern-match needs >=2 kinds of evidence (triangulation), got %d" % len(types)
                )

    elif rule == "design-cycle":
        artifacts = {str(i.get("evidence_id") or "") for i in items if str(i.get("kind") or "") == "artifact"}
        evaluations = [i for i in items if str(i.get("kind") or "") == "evaluation"]
        if not artifacts:
            blockers.append("design-cycle needs an artifact")
        if not evaluations:
            blockers.append("design-cycle needs an evaluation for the artifact")
        for evaluation in evaluations:
            if str(evaluation.get("artifact_id") or "") not in artifacts:
                blockers.append("evaluation is not bound to a declared artifact")

    elif rule == "descriptive":
        sources = {str(item.get("source_id") or "") for item in items}
        sources.discard("")
        if len(sources) < minimum:
            blockers.append(
                "descriptive rule needs >=%d records, got %d" % (minimum, len(sources))
            )
        if generalises:
            blockers.append(
                "descriptive rule cannot generalise to a population; re-scope the claim or "
                "declare a sampling frame and non-response analysis"
            )

    return {
        "method": method_id,
        "rule": rule,
        "evidence_form": (entry.get("evidence_form") or {}).get("id", ""),
        "min_independent_sources": minimum,
        "observed_sources": len({str(i.get("source_id") or "") for i in items} - {""}),
        "supported": not blockers,
        "blockers": blockers,
        "boundary": "read-only check; it never signs a claim — a human still signs",
    }


def constraints_for(epistemics: Dict[str, Any], method_id: str, stage: str = "") -> List[Dict[str, Any]]:
    entry = (epistemics.get("methods") or {}).get(method_id) or {}
    return [
        dict(item)
        for item in (entry.get("constraints") or [])
        if not stage or str(item.get("stage") or "") == stage
    ]

"""Process-level literature memory.

This store remembers how retrieval went, not what the papers said. It records
facet coverage, query yield, gaps and saturation, then reorders the next S1
scout plan. It never stores abstracts/spans/claims, never marks a facet as
evidence, and never admits a skill. A memory-derived skill change is a
candidate that still needs dry-run, public/hidden/regression evaluation and a
human admission decision.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .modules.literature import FACET_LABELS, FACET_ORDER
from .paths import DEFAULT_LITERATURE_MEMORY_PATH
from .storage import JsonStoreError, now_iso, read_json, write_json_atomic

__all__ = [
    "DEFAULT_LITERATURE_MEMORY_PATH",
    "DEFAULT_SCOUT_GROUPS",
    "LITERATURE_MEMORY_SCHEMA",
    "LiteratureMemoryError",
    "LiteratureMemoryStore",
    "topic_key",
]

LITERATURE_MEMORY_SCHEMA = "literature-memory-0.1"
MAX_TOPICS = 100
MAX_RUNS = 40
DEFAULT_SCOUT_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("core", "survey"),
    ("method", "evaluation"),
    ("limitation", "recent"),
)


class LiteratureMemoryError(ValueError):
    pass


def _now() -> str:
    return now_iso()


def topic_key(question: str) -> str:
    normalized = " ".join((question or "").split()).lower()
    if not normalized:
        raise LiteratureMemoryError("question must not be empty")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return "TOP-" + digest


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    write_json_atomic(path, payload)


def _read(path: Path) -> Dict[str, Any]:
    try:
        payload = read_json(path)
    except JsonStoreError as exc:
        raise LiteratureMemoryError(str(exc))
    if payload is None:
        return {"schema_version": LITERATURE_MEMORY_SCHEMA, "topics": {}}
    if not isinstance(payload, dict):
        raise LiteratureMemoryError("literature memory must be a JSON object")
    if not isinstance(payload.get("topics"), dict):
        raise LiteratureMemoryError("literature memory topics must be an object")
    return payload


def _empty_facet_stats() -> Dict[str, Any]:
    return {
        "attempts": 0,
        "covered_runs": 0,
        "queries": 0,
        "sources": 0,
        "spans": 0,
        "last_covered": False,
        "last_run_id": "",
        "last_seen": "",
    }


def _empty_mode() -> Dict[str, Any]:
    return {
        "runs": 0,
        "sources": 0,
        "full_text": 0,
        "spans": 0,
        "queries": 0,
        "facets": {facet: _empty_facet_stats() for facet in FACET_ORDER},
        "gaps": {},
        "saturations": {},
        "last_run_id": "",
        "last_seen": "",
    }


def normalize_facets(facets: Optional[Iterable[str]]) -> List[str]:
    if facets is None:
        return list(FACET_ORDER)
    requested = [str(facet) for facet in facets]
    unknown = sorted({facet for facet in requested if facet not in FACET_ORDER})
    if unknown:
        raise LiteratureMemoryError("unknown facet(s): " + ", ".join(unknown))
    selected = {facet for facet in requested}
    return [facet for facet in FACET_ORDER if facet in selected]


def _priority(stats: Dict[str, Any]) -> Tuple[float, str]:
    attempts = int(stats.get("attempts", 0))
    if attempts <= 0:
        return 1.0, "尚未观测"
    covered = int(stats.get("covered_runs", 0))
    queries = max(1, int(stats.get("queries", 0)))
    spans = int(stats.get("spans", 0))
    coverage_rate = min(1.0, covered / float(attempts))
    spans_per_query = spans / float(queries)
    if coverage_rate < 1.0:
        score = 0.6 + 0.3 * (1.0 - coverage_rate) + 0.1 * min(attempts, 3) / 3.0
        return round(score, 4), "覆盖 %d/%d 次，未覆盖优先" % (covered, attempts)
    score = 0.35 + min(0.15, spans_per_query / 10.0) - min(0.1, attempts * 0.02)
    return round(score, 4), "已覆盖，按 span/query 产出给余量（%.2f）" % spans_per_query


class LiteratureMemoryStore:
    """JSON-backed facet memory with an explicit process-only boundary."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> Dict[str, Any]:
        return _read(self.path)

    def _save(self, payload: Dict[str, Any]) -> None:
        payload["schema_version"] = LITERATURE_MEMORY_SCHEMA
        payload["updated_at"] = _now()
        _atomic_write(self.path, payload)

    def _topic(self, payload: Dict[str, Any], question: str) -> Dict[str, Any]:
        key = topic_key(question)
        topic = payload["topics"].get(key)
        normalized = " ".join(question.split())
        if not isinstance(topic, dict):
            topic = {
                "topic_id": key,
                "question": normalized,
                "created_at": _now(),
                "updated_at": _now(),
                "modes": {},
                "runs": [],
            }
            payload["topics"][key] = topic
        topic["question"] = normalized
        topic.setdefault("modes", {})
        topic.setdefault("runs", [])
        return topic

    def record(
        self,
        question: str,
        run_id: str,
        facets: Sequence[Dict[str, Any]],
        totals: Dict[str, Any],
        gaps: Sequence[str],
        saturation: str,
        mode: str,
        role: str = "literature",
        coverage_score: float = 0.0,
        fixture_mode: Optional[bool] = None,
    ) -> Dict[str, Any]:
        mode = str(mode or "fixture")
        normalized_facets = normalize_facets([str(item.get("facet")) for item in facets])
        payload = self._load()
        topic = self._topic(payload, question)
        mode_state = topic["modes"].setdefault(mode, _empty_mode())
        by_facet = {str(item.get("facet")): item for item in facets}

        for facet in normalized_facets:
            item = by_facet.get(facet, {})
            stats = mode_state["facets"].setdefault(facet, _empty_facet_stats())
            stats["attempts"] = int(stats.get("attempts", 0)) + 1
            stats["covered_runs"] = int(stats.get("covered_runs", 0)) + (1 if item.get("covered") else 0)
            stats["queries"] = int(stats.get("queries", 0)) + int(item.get("queries", 0) or 0)
            stats["sources"] = int(stats.get("sources", 0)) + int(item.get("sources", 0) or 0)
            stats["spans"] = int(stats.get("spans", 0)) + int(item.get("spans", 0) or 0)
            stats["last_covered"] = bool(item.get("covered"))
            stats["last_run_id"] = run_id
            stats["last_seen"] = _now()

        mode_state["runs"] = int(mode_state.get("runs", 0)) + 1
        mode_state["sources"] = int(mode_state.get("sources", 0)) + int(totals.get("sources", 0) or 0)
        mode_state["full_text"] = int(mode_state.get("full_text", 0)) + int(totals.get("full_text", 0) or 0)
        mode_state["spans"] = int(mode_state.get("spans", 0)) + int(totals.get("spans", 0) or 0)
        mode_state["queries"] = int(mode_state.get("queries", 0)) + int(totals.get("queries", 0) or 0)
        mode_state["last_run_id"] = run_id
        mode_state["last_seen"] = _now()
        gap_counts = mode_state.setdefault("gaps", {})
        for code in sorted(set(str(code) for code in gaps)):
            gap_counts[code] = int(gap_counts.get(code, 0)) + 1
        saturations = mode_state.setdefault("saturations", {})
        saturations[saturation] = int(saturations.get(saturation, 0)) + 1

        run = {
            "run_id": run_id,
            "role": str(role),
            "mode": mode,
            "at": _now(),
            "facets": normalized_facets,
            "sources": int(totals.get("sources", 0) or 0),
            "full_text": int(totals.get("full_text", 0) or 0),
            "spans": int(totals.get("spans", 0) or 0),
            "queries": int(totals.get("queries", 0) or 0),
            "coverage_score": round(float(coverage_score or 0.0), 4),
            "saturation": saturation,
            "gaps": sorted({str(code) for code in gaps}),
            "fixture_mode": bool(fixture_mode),
        }
        topic["runs"].append(run)
        topic["runs"] = topic["runs"][-MAX_RUNS:]
        topic["updated_at"] = _now()

        if len(payload["topics"]) > MAX_TOPICS:
            ordered = sorted(
                payload["topics"].items(),
                key=lambda item: str(item[1].get("updated_at", "")),
            )
            for key, _ in ordered[: len(payload["topics"]) - MAX_TOPICS]:
                payload["topics"].pop(key, None)
        self._save(payload)
        return run

    def record_result(self, question: str, result: Any, mode: Optional[str] = None) -> Dict[str, Any]:
        mode = mode or ("fixture" if getattr(result, "fixture_mode", False) else "real")
        brief = getattr(result, "brief", None)
        facets = []
        if brief is not None:
            facets = [
                {
                    "facet": item.facet,
                    "queries": len(item.queries),
                    "sources": len(item.source_ids),
                    "spans": item.span_count,
                    "covered": item.covered,
                }
                for item in brief.facets
            ]
        coverage = getattr(result, "coverage", None)
        return self.record(
            question=question,
            run_id=str(getattr(result, "run_id", "")),
            facets=facets,
            totals={
                "sources": len(getattr(result, "hits", [])),
                "full_text": len({span.source_id for span in getattr(result, "spans", [])}),
                "spans": len(getattr(result, "spans", [])),
                "queries": int(getattr(coverage, "queries", 0) or 0),
            },
            gaps=[gap.code for gap in getattr(coverage, "gaps", [])],
            saturation=str(getattr(brief, "saturation", "unknown") if brief else "unknown"),
            mode=mode,
            role="literature",
            coverage_score=float(getattr(brief, "coverage_score", 0.0) if brief else 0.0),
            fixture_mode=bool(getattr(result, "fixture_mode", False)),
        )

    def advise(self, question: str, max_sources: int = 6, mode: str = "fixture", facets: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        if max_sources < 1:
            raise LiteratureMemoryError("max_sources must be >= 1")
        requested = normalize_facets(facets)
        payload = self._load()
        key = topic_key(question)
        topic = payload["topics"].get(key) if isinstance(payload["topics"].get(key), dict) else None
        mode_state = (topic or {}).get("modes", {}).get(mode, _empty_mode())
        other_modes = [name for name in (topic or {}).get("modes", {}) if name != mode]
        priorities: List[Dict[str, Any]] = []
        for facet in requested:
            stats = mode_state.get("facets", {}).get(facet, _empty_facet_stats())
            score, reason = _priority(stats)
            attempts = int(stats.get("attempts", 0))
            priorities.append(
                {
                    "facet": facet,
                    "label": FACET_LABELS.get(facet, facet),
                    "priority": score,
                    "reason": reason,
                    "attempts": attempts,
                    "covered_runs": int(stats.get("covered_runs", 0)),
                    "coverage_rate": round(int(stats.get("covered_runs", 0)) / float(attempts), 4) if attempts else None,
                    "spans_per_query": round(
                        int(stats.get("spans", 0)) / float(max(1, int(stats.get("queries", 0)))),
                        4,
                    ),
                }
            )
        ranked = sorted(
            priorities,
            key=lambda item: (-float(item["priority"]), FACET_ORDER.index(str(item["facet"]))),
        )

        if max_sources < len(requested):
            budget_facets = [str(item["facet"]) for item in ranked[:max_sources]]
            deferred = [str(item["facet"]) for item in ranked[max_sources:]]
        else:
            budget_facets = [str(item["facet"]) for item in ranked]
            deferred = []
        budget = {facet: 1 for facet in budget_facets}
        remaining = max(0, max_sources - len(budget_facets))
        cursor = 0
        while remaining > 0 and budget_facets:
            budget[budget_facets[cursor % len(budget_facets)]] += 1
            cursor += 1
            remaining -= 1

        groups: List[Dict[str, Any]] = []
        grouped = set()
        for group_index, default_group in enumerate(DEFAULT_SCOUT_GROUPS, start=1):
            members = [facet for facet in default_group if facet in budget]
            if not members:
                continue
            grouped.update(members)
            group_priority = max(
                float(next(item["priority"] for item in priorities if item["facet"] == facet))
                for facet in members
            )
            groups.append(
                {
                    "role_id": "scout-%d" % group_index,
                    "facets": members,
                    "labels": [FACET_LABELS.get(facet, facet) for facet in members],
                    "budget": sum(budget[facet] for facet in members),
                    "per_facet_budget": {facet: budget[facet] for facet in members},
                    "priority": round(group_priority, 4),
                }
            )
        leftover = [facet for facet in budget if facet not in grouped]
        if leftover:
            groups.append(
                {
                    "role_id": "scout-%d" % (len(groups) + 1),
                    "facets": leftover,
                    "labels": [FACET_LABELS.get(facet, facet) for facet in leftover],
                    "budget": sum(budget[facet] for facet in leftover),
                    "per_facet_budget": {facet: budget[facet] for facet in leftover},
                    "priority": max(
                        float(next(item["priority"] for item in priorities if item["facet"] == facet))
                        for facet in leftover
                    ),
                }
            )
        groups.sort(key=lambda item: -float(item["priority"]))

        observed_runs = int(mode_state.get("runs", 0))
        cold_start = observed_runs == 0
        warnings: List[str] = []
        if cold_start:
            warnings.append("cold start: no %s-mode observation for this topic; use balanced facet groups" % mode)
        if other_modes:
            warnings.append(
                "other-mode memory ignored for planning: " + ", ".join(sorted(other_modes))
            )
        if deferred:
            warnings.append(
                "budget below facet count; deferred facets: " + ", ".join(deferred)
            )
        rationale = []
        for item in ranked:
            if item["facet"] in budget:
                rationale.append(
                    "%s：%s；本次预算 %d"
                    % (item["label"], item["reason"], budget[str(item["facet"])])
                )
        candidate = _skill_candidate(question, key, mode, priorities, mode_state)
        return {
            "schema_version": LITERATURE_MEMORY_SCHEMA,
            "topic_id": key,
            "question": " ".join(question.split()),
            "mode": mode,
            "observed_runs": observed_runs,
            "cold_start": cold_start,
            "facet_priorities": priorities,
            "budget": budget,
            "deferred_facets": deferred,
            "scout_groups": groups,
            "rationale": rationale,
            "warnings": warnings,
            "skill_candidate": candidate,
            "boundary": "retrieval-process memory only; no abstract/span/claim text is stored or replayed as evidence",
        }

    def snapshot(self, limit: int = 20) -> Dict[str, Any]:
        payload = self._load()
        topics: List[Dict[str, Any]] = []
        for key, topic in payload["topics"].items():
            if not isinstance(topic, dict):
                continue
            modes = {}
            for mode, state in (topic.get("modes") or {}).items():
                if not isinstance(state, dict):
                    continue
                modes[mode] = {
                    "runs": int(state.get("runs", 0)),
                    "sources": int(state.get("sources", 0)),
                    "full_text": int(state.get("full_text", 0)),
                    "spans": int(state.get("spans", 0)),
                    "queries": int(state.get("queries", 0)),
                    "last_run_id": state.get("last_run_id", ""),
                    "last_seen": state.get("last_seen", ""),
                    "facets": {
                        facet: {
                            "attempts": int(stats.get("attempts", 0)),
                            "covered_runs": int(stats.get("covered_runs", 0)),
                            "spans": int(stats.get("spans", 0)),
                            "queries": int(stats.get("queries", 0)),
                        }
                        for facet, stats in (state.get("facets") or {}).items()
                        if isinstance(stats, dict)
                    },
                    "gaps": dict(state.get("gaps") or {}),
                    "saturations": dict(state.get("saturations") or {}),
                }
            topics.append(
                {
                    "topic_id": key,
                    "question": topic.get("question", ""),
                    "updated_at": topic.get("updated_at", ""),
                    "modes": modes,
                    "recent_runs": list(topic.get("runs") or [])[-5:],
                }
            )
        topics.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return {
            "schema_version": LITERATURE_MEMORY_SCHEMA,
            "count": len(topics),
            "topics": topics[: max(0, limit)],
            "boundary": "process memory only; it can reorder retrieval but never creates Claim/EA/gate or evidence",
            "generated_at": _now(),
        }


def _skill_candidate(
    question: str,
    key: str,
    mode: str,
    priorities: Sequence[Dict[str, Any]],
    mode_state: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    eligible = [
        item for item in priorities
        if int(item.get("attempts", 0)) >= 2
        and (
            float(item.get("coverage_rate") or 0.0) < 0.5
            or float(item.get("spans_per_query") or 0.0) < 0.5
        )
    ]
    if not eligible:
        return _budget_candidate(key, mode, mode_state)
    target = sorted(
        eligible,
        key=lambda item: (
            float(item.get("coverage_rate") or 0.0),
            float(item.get("spans_per_query") or 0.0),
            FACET_ORDER.index(str(item["facet"])),
        ),
    )[0]
    facet = str(target["facet"])
    label = FACET_LABELS.get(facet, facet)
    coverage = target.get("coverage_rate")
    yield_value = float(target.get("spans_per_query") or 0.0)
    patch = (
        "add facet-specific query variants for %s; route them to one scout and keep the "
        "round-robin budget plus full-text-only span rule" % facet
    )
    if coverage is not None and float(coverage) >= 0.5:
        patch = (
            "replace the generic %s query suffix with %s-anchored templates and a venue/benchmark "
            "filter; keep the round-robin budget plus full-text-only span rule" % (facet, label)
        )
    digest = hashlib.sha256(
        ("%s|%s|%s|%s" % (key, mode, facet, patch)).encode("utf-8")
    ).hexdigest()[:10]
    return {
        "candidate_id": "LCAND-" + digest,
        "kind": "skill",
        "target": "literature.query_planner",
        "facet": facet,
        "patch": patch,
        "rationale": (
            "%s 在 %s 模式已观测 %d 次，覆盖 %d 次，span/query=%.2f；"
            "当前查询模板对该面向产出不足。"
            % (
                label,
                mode,
                int(target.get("attempts", 0)),
                int(target.get("covered_runs", 0)),
                yield_value,
            )
        ),
        "predicted_effect": "下一次 public dry-run 至少多覆盖 1 个面向或 1 篇全文；不改变证据规则",
        "status": "pending_human",
        "scope": "S1/%s/%s" % (mode, key),
        "governance": {
            "auto_admitted": False,
            "required": ["dry_run", "public_eval", "hidden_eval", "regression", "human_admission"],
            "immutable": ["Claim", "EA", "gate", "rubric", "export", "signature"],
            "note": "memory can propose a query-planner skill change; it cannot admit it or touch evidence",
        },
    }


def _budget_candidate(
    key: str,
    mode: str,
    mode_state: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    state = mode_state or {}
    gaps = state.get("gaps") or {}
    cap_count = int(gaps.get("coverage_cap_reached", 0))
    thin_count = int(gaps.get("thin_full_text_coverage", 0))
    if cap_count < 2 and thin_count < 2:
        return None
    if cap_count >= thin_count:
        constraint = "source_budget"
        patch = (
            "when coverage_cap_reached repeats, reserve one extra source for the lowest-yield facet "
            "before adding queries; request a larger max_sources if the cap is still binding"
        )
        rationale = (
            "coverage_cap_reached 在 %s 模式的 %d 次 S1 运行中重复出现；"
            "约束在来源预算，不是查询模板。"
            % (mode, cap_count)
        )
        predicted = "下一次 public dry-run 在不改变 full-text-only 规则下达到目标来源数"
    else:
        constraint = "full_text_access"
        patch = (
            "route abstract-only hits to an explicit full-text acquisition handoff; do not add query "
            "variants until a full text is available"
        )
        rationale = (
            "thin_full_text_coverage 在 %s 模式的 %d 次 S1 运行中重复出现；"
            "证据缺口来自全文获取，不是查询覆盖。"
            % (mode, thin_count)
        )
        predicted = "下一次 public dry-run 的全文读取数提高，摘要仍不进入 span"
    digest = hashlib.sha256(
        ("%s|%s|process|%s|%s" % (key, mode, constraint, patch)).encode("utf-8")
    ).hexdigest()[:10]
    return {
        "candidate_id": "LCAND-" + digest,
        "kind": "process",
        "target": "orchestrator.facet_budget",
        "facet": None,
        "constraint": constraint,
        "patch": patch,
        "rationale": rationale,
        "predicted_effect": predicted,
        "status": "pending_human",
        "scope": "S1/%s/%s" % (mode, key),
        "governance": {
            "auto_admitted": False,
            "required": ["dry_run", "public_eval", "hidden_eval", "regression", "human_admission"],
            "immutable": ["Claim", "EA", "gate", "rubric", "export", "signature"],
            "note": "budget/full-text process proposal only; no evidence boundary changes",
        },
    }

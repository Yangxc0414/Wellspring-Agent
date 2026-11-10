"""Stable facade for typed multi-agent S1/S2/S3 orchestration.

Implementation is split into research_agent/orchestration/ so the plan,
advisory checks, merge rules and local stores stay independently testable.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .adapters import FixtureRetriever, RealCorpusRetriever, SimpleParser
from .contracts import SourceHit, Span
from .custom_agents import CustomAgentError, CustomAgentStore
from .evolution_policy import EvolutionPolicyError, EvolutionPolicyStore
from .literature_memory import LiteratureMemoryError, LiteratureMemoryStore
from .modules.idea import (
    IdeaAgent,
    IdeaRequest,
    prior_art_hits_from_literature,
)
from .modules.literature import FACET_LABELS, LiteratureAgent, LiteratureRequest
from .orchestration import ORCHESTRATION_SCHEMA
from .orchestration.advisories import advisory_notes
from .orchestration.common import new_run_id
from .orchestration.errors import OrchestrationError
from .orchestration.merge import memory_facets, merge_reports
from .orchestration.plan import (
    balanced_groups,
    collaboration_plan,
    summarize_policy,
    topology_snapshot,
)
from .paths import (
    DEFAULT_CUSTOM_AGENTS_PATH,
    DEFAULT_EVOLUTION_POLICY_PATH,
    DEFAULT_LITERATURE_MEMORY_PATH,
)
from .specs import SpecStore

DEFAULT_MEMORY_PATH = DEFAULT_LITERATURE_MEMORY_PATH

__all__ = [
    "DEFAULT_MEMORY_PATH",
    "ORCHESTRATION_SCHEMA",
    "OrchestrationError",
    "OrchestrationResult",
    "collaboration_plan",
    "public_snapshot",
    "run_orchestration",
    "topology_snapshot",
    "write_orchestration_artifacts",
]


def _make_retriever(source: str, corpus_path: Optional[Path]):
    if source == "fixture":
        return FixtureRetriever(Path(corpus_path) if corpus_path else None)
    if source == "real":
        path = Path(corpus_path) if corpus_path else (
            Path(__file__).resolve().parents[1] / "modules" / "literature" / "fixtures" / "real_corpus.json"
        )
        return RealCorpusRetriever(path)
    raise OrchestrationError("orchestrator source must be fixture or real")


def _run_scout(
    topic: str,
    source: str,
    corpus_path: Optional[Path],
    group: Dict[str, Any],
    base_run_id: str,
    spec_factory: Callable[[], Any],
) -> Tuple[Dict[str, Any], Any]:
    retriever = _make_retriever(source, corpus_path)
    agent = LiteratureAgent(spec_factory(), retriever, SimpleParser())
    result = agent.run(
        LiteratureRequest(
            question=topic,
            max_sources=max(1, int(group.get("budget", 1))),
            source_scope=[source],
            run_id="%s-%s" % (base_run_id, group["role_id"]),
            coverage_plan=True,
            facet_subset=list(group["facets"]),
        )
    )
    summary = {
        "role_id": str(group["role_id"]),
        "name": "文献侦察 · " + "/".join(
            FACET_LABELS.get(str(facet), str(facet)) for facet in group["facets"]
        ),
        "facets": list(group["facets"]),
        "budget": int(group.get("budget", 0)),
        "run_id": result.run_id,
        "status": result.status,
        "queries": result.coverage.queries,
        "sources": len(result.hits),
        "source_ids": [hit.source_id for hit in result.hits],
        "full_text": len({span.source_id for span in result.spans}),
        "spans": len(result.spans),
        "gap_codes": [gap.code for gap in result.coverage.gaps],
        "warnings": list(result.warnings),
        "saturation": result.brief.saturation if result.brief else "unknown",
        "coverage_score": result.brief.coverage_score if result.brief else 0.0,
    }
    return summary, result


@dataclass
class OrchestrationResult:
    run_id: str
    topic: str
    source: str
    plan: Dict[str, Any]
    scouts: List[Dict[str, Any]]
    merged: Dict[str, Any]
    idea: Dict[str, Any]
    memory: Dict[str, Any]
    skill_candidate: Optional[Dict[str, Any]]
    warnings: List[str]
    fixture_mode: bool
    custom_agents: List[Dict[str, Any]]
    advisory_notes: List[Dict[str, Any]]
    policy: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": ORCHESTRATION_SCHEMA,
            "run_id": self.run_id,
            "topic": self.topic,
            "source": self.source,
            "fixture_mode": self.fixture_mode,
            "plan": self.plan,
            "scouts": self.scouts,
            "merged": self.merged,
            "idea": self.idea,
            "custom_agents": self.custom_agents,
            "advisory_notes": self.advisory_notes,
            "policy": self.policy,
            "memory": self.memory,
            "skill_candidate": self.skill_candidate,
            "warnings": list(self.warnings),
            "boundary": "S1/S2/S3 orchestration only: spans and candidate frames, no Claim/EA/gate/admission.",
        }


def run_orchestration(
    topic: str,
    max_sources: int = 6,
    source: str = "fixture",
    corpus_path: Optional[Path] = None,
    memory_path: Optional[Path] = None,
    memory: Optional[LiteratureMemoryStore] = None,
    max_workers: Optional[int] = None,
    custom_agents_path: Optional[Path] = None,
    policy_path: Optional[Path] = None,
) -> OrchestrationResult:
    text = " ".join((topic or "").split())
    if len(text) < 2 or len(text) > 500:
        raise OrchestrationError("topic must be 2-500 characters")
    if not 1 <= int(max_sources) <= 50:
        raise OrchestrationError("max_sources must be between 1 and 50")
    if source not in ("fixture", "real"):
        raise OrchestrationError("orchestrator source must be fixture or real")
    store = memory or LiteratureMemoryStore(memory_path or DEFAULT_MEMORY_PATH)
    try:
        custom_store = CustomAgentStore(custom_agents_path or DEFAULT_CUSTOM_AGENTS_PATH)
        custom_agents = custom_store.list(enabled_only=True)
        policy_store = EvolutionPolicyStore(policy_path or DEFAULT_EVOLUTION_POLICY_PATH)
        policy_state = policy_store.snapshot()
    except (CustomAgentError, EvolutionPolicyError) as exc:
        raise OrchestrationError(str(exc))
    memory_allowed = policy_store.allows_memory_order()
    try:
        advice = store.advise(text, int(max_sources), source) if memory_allowed else None
    except LiteratureMemoryError as exc:
        raise OrchestrationError(str(exc))
    plan = collaboration_plan(
        text,
        int(max_sources),
        source,
        advice,
        custom_agents=custom_agents,
        evolution_policy=policy_state,
    )
    groups = list((advice or {}).get("scout_groups") or balanced_groups(int(max_sources)))
    groups = [group for group in groups if int(group.get("budget", 0)) > 0]
    if not groups:
        raise OrchestrationError("no scout group can be scheduled")
    basenew_run_id = new_run_id()
    spec_factory = lambda: SpecStore().load("literature")
    summaries: List[Dict[str, Any]] = []
    results: List[Any] = []
    workers = min(len(groups), int(max_workers or len(groups)))
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="s1-scout") as executor:
        futures = [
            (group, executor.submit(
                _run_scout, text, source, corpus_path, group, basenew_run_id, spec_factory
            ))
            for group in groups
        ]
        for group, future in futures:
            try:
                summary, result = future.result()
            except Exception as exc:
                raise OrchestrationError(
                    "scout %s failed: %s" % (group.get("role_id", "unknown"), exc)
                )
            summaries.append(summary)
            results.append(result)
    pairs = sorted(zip(summaries, results), key=lambda pair: str(pair[0]["role_id"]))
    summaries = [pair[0] for pair in pairs]
    results = [pair[1] for pair in pairs]
    merged = merge_reports(results, summaries)
    merged_hits = [SourceHit(**hit) for hit in merged["hits"]]
    merged_spans = [Span(**span) for span in merged["spans"]]
    prior_art_agent = LiteratureAgent(
        SpecStore().load("literature"),
        _make_retriever(source, corpus_path),
        SimpleParser(),
    )

    def _prior_art_search(
        query: str, limit: int
    ) -> List[Dict[str, Any]]:
        result = prior_art_agent.run(
            LiteratureRequest(
                question=query,
                max_sources=max(1, min(limit, 3)),
                source_scope=[source],
                coverage_plan=False,
            )
        )
        return prior_art_hits_from_literature(result, limit)

    idea_result = IdeaAgent(SpecStore().load("idea")).run(
        IdeaRequest(
            topic=text,
            spans=merged_spans,
            max_candidates=3,
            run_id="%s-IDEA" % basenew_run_id,
            prior_art_searcher=_prior_art_search,
        )
    )
    warnings: List[str] = []
    for warning in merged["warnings"]:
        if warning not in warnings:
            warnings.append(warning)
    warnings.append("orchestrator stops before G1; idea frames are candidates, not an admitted hypothesis")
    warnings.append("self-evolution stays in the skill/memory lane; no skill is admitted by this run")
    if not policy_state.get("enabled", True):
        warnings.append("self-evolution policy is off; memory ordering and new candidate generation are suppressed")
    else:
        policy_scopes = {
            str(item.get("id")): bool(item.get("enabled", True))
            for item in policy_state.get("scopes", [])
            if isinstance(item, dict)
        }
        if not policy_scopes.get("literature.memory_order", True):
            warnings.append("literature.memory_order scope is off; using balanced facet groups")
    if custom_agents:
        warnings.append(
            "%d custom advisory agent(s) ran read-only checks; notes are not evidence or gate decisions"
            % len(custom_agents)
        )
    unread = [hit.source_id for hit in merged_hits if not hit.full_text]
    if unread:
        warnings.append(
            "%d abstract-only source(s) were not converted to spans; fetch full texts before Q0" % len(unread)
        )

    recorded = store.record(
        question=text,
        run_id=basenew_run_id,
        facets=memory_facets(merged),
        totals={
            "sources": merged["sources"],
            "full_text": merged["full_text"],
            "spans": merged["spans_count"],
            "queries": merged["queries"],
        },
        gaps=[gap["code"] for gap in merged["gaps"]],
        saturation=merged["saturation"],
        mode=source,
        role="orchestrator/s1-fanout",
        coverage_score=merged["coverage_score"],
        fixture_mode=source == "fixture",
    )
    next_advice = store.advise(text, int(max_sources), source)
    skill_candidate = next_advice.get("skill_candidate")
    suppressed_candidate = None
    if skill_candidate and not policy_store.allows_candidate(
        str(skill_candidate.get("kind", "")), str(skill_candidate.get("target", ""))
    ):
        suppressed_candidate = {
            **skill_candidate,
            "status": "suppressed_by_policy",
            "suppressed_reason": "evolution policy disabled for target scope",
        }
        skill_candidate = None
        warnings.append(
            "candidate %s suppressed by evolution policy; no proposal was emitted"
            % suppressed_candidate.get("candidate_id", "unknown")
        )
    advisories = advisory_notes(custom_agents, merged, idea_result)
    policy_payload = {
        **policy_state,
        "memory_applied": bool(memory_allowed),
        "suppressed_candidate": suppressed_candidate,
    }
    memory_payload = {
        "advice": advice,
        "recorded": recorded,
        "next_focus": [
            {
                "facet": item["facet"],
                "priority": item["priority"],
                "reason": item["reason"],
            }
            for item in next_advice["facet_priorities"][:2]
        ],
        "next_advice": next_advice,
        "applied": bool(memory_allowed),
        "boundary": "process memory only; it reorders the next scout plan and never becomes evidence",
    }
    return OrchestrationResult(
        run_id=basenew_run_id,
        topic=text,
        source=source,
        plan=plan,
        scouts=summaries,
        merged=merged,
        idea={
            "run_id": idea_result.run_id,
            "status": idea_result.status,
            "candidates": [card.__dict__ for card in idea_result.candidates],
            "brief": idea_result.brief.__dict__ if idea_result.brief else None,
            "prior_art_report": list(idea_result.prior_art_report),
            "shortlist": (
                idea_result.shortlist.__dict__
                if idea_result.shortlist
                else None
            ),
            "warnings": list(idea_result.warnings),
        },
        memory=memory_payload,
        skill_candidate=skill_candidate,
        warnings=warnings,
        fixture_mode=source == "fixture",
        custom_agents=[
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "role": item.get("role"),
                "role_label": item.get("role_label"),
                "stage": item.get("stage"),
                "checks": list(item.get("checks", [])),
                "check_labels": list(item.get("check_labels", [])),
                "tools": list(item.get("tools", [])),
                "outputs": list(item.get("outputs", [])),
                "enabled": bool(item.get("enabled", True)),
                "advisory_only": True,
                "writes": [],
            }
            for item in custom_agents
        ],
        advisory_notes=advisories,
        policy=policy_payload,
    )


def write_orchestration_artifacts(result: OrchestrationResult, output_dir: Path) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    path = output / "orchestration.json"
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    idea_path = output / "idea-candidates.json"
    with open(str(idea_path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result.idea, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    advice_path = output / "memory-advice.json"
    with open(str(advice_path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(result.memory.get("next_advice", {}), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


def _public_idea(idea: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        {
            "idea_id": card.get("idea_id"),
            "title": card.get("title"),
            "hypothesis": card.get("hypothesis"),
            "falsification": card.get("falsification"),
            "evidence_refs": list(card.get("evidence_refs") or []),
            "status": card.get("status"),
            "lens": card.get("lens"),
            "evidence_count": card.get("evidence_count"),
            "source_count": card.get("source_count"),
            "novelty_status": card.get("novelty_status"),
            "testability": card.get("testability"),
            "prior_art_scope": card.get("prior_art_scope"),
            "has_kill_criteria": bool(card.get("kill_criteria")),
        }
        for card in idea.get("candidates") or []
        if isinstance(card, dict)
    ]
    shortlist = idea.get("shortlist") or {}
    ranked = [
        {
            key: item.get(key)
            for key in (
                "rank",
                "idea_id",
                "evidence_count",
                "source_count",
                "prior_art_scope",
                "novelty_status",
                "testability",
                "has_kill_criteria",
            )
        }
        for item in shortlist.get("ranked") or []
        if isinstance(item, dict)
    ]
    return {
        "run_id": idea.get("run_id"),
        "status": idea.get("status"),
        "candidates": candidates,
        "brief": idea.get("brief"),
        "prior_art_report": [
            {
                "idea_id": entry.get("idea_id"),
                "scope": entry.get("scope"),
                "hit_count": len(entry.get("hits") or []),
                "error": bool(entry.get("error")),
            }
            for entry in idea.get("prior_art_report") or []
            if isinstance(entry, dict)
        ],
        "shortlist": (
            {
                "ranked": ranked,
                "selection": shortlist.get("selection"),
                "criteria": list(shortlist.get("criteria") or []),
                "boundary": shortlist.get("boundary"),
            }
            if shortlist
            else None
        ),
        "warnings": list(idea.get("warnings") or []),
    }


def public_snapshot(result: OrchestrationResult) -> Dict[str, Any]:
    """Summary for the web UI: counts and frames, never source text or spans."""

    merged = result.merged
    policy_view = summarize_policy(result.policy)
    return {
        "schema_version": ORCHESTRATION_SCHEMA,
        "run_id": result.run_id,
        "topic": result.topic,
        "source": result.source,
        "fixture_mode": result.fixture_mode,
        "scouts": [
            {
                "role_id": item["role_id"],
                "name": item["name"],
                "facets": list(item["facets"]),
                "budget": int(item["budget"]),
                "status": item["status"],
                "sources": int(item["sources"]),
                "full_text": int(item["full_text"]),
                "spans": int(item["spans"]),
                "queries": int(item["queries"]),
                "saturation": item["saturation"],
                "coverage_score": item["coverage_score"],
                "gap_codes": list(item["gap_codes"]),
            }
            for item in result.scouts
        ],
        "merged": {
            "sources": int(merged["sources"]),
            "full_text": int(merged["full_text"]),
            "spans_count": int(merged["spans_count"]),
            "queries": int(merged["queries"]),
            "covered_facets": int(merged["covered_facets"]),
            "planned_facets": int(merged["planned_facets"]),
            "coverage_score": float(merged["coverage_score"]),
            "saturation": merged["saturation"],
            "facet_coverage": [
                {
                    "facet": item["facet"],
                    "label": item["label"],
                    "queries": len(item["queries"]),
                    "sources": len(item["source_ids"]),
                    "span_count": int(item["span_count"]),
                    "covered": bool(item["covered"]),
                }
                for item in merged["facet_coverage"]
            ],
            "gaps": list(merged["gaps"]),
            "scout_gaps": dict(merged["scout_gaps"]),
        },
        "idea": _public_idea(result.idea),
        "custom_agents": list(result.custom_agents),
        "advisory_notes": list(result.advisory_notes),
        "policy": {
            "enabled": bool(policy_view["enabled"]),
            "scopes": dict(policy_view["scopes"]),
            "locked": list(policy_view["locked"]),
            "memory_applied": bool(result.policy.get("memory_applied", False)),
            "suppressed_candidate": result.policy.get("suppressed_candidate"),
            "boundary": str(policy_view["boundary"]),
        },
        "memory": {
            "recorded": result.memory.get("recorded", {}),
            "next_focus": result.memory.get("next_focus", []),
            "applied": bool(result.memory.get("applied", False)),
            "boundary": result.memory.get("boundary", ""),
        },
        "skill_candidate": result.skill_candidate,
        "warnings": list(result.warnings),
        "boundary": (
            "Web summary only: no source text, span text or abstract; idea frames remain candidates and "
            "no Claim/EA/gate/admission is created."
        ),
    }


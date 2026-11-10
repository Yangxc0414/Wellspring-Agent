"""Backend actions behind workspace buttons.

The service orchestrates existing research modules; it is not an evidence
producer. Plans and skill results are recommendations and audit summaries,
never claims, EA or gate decisions.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adapters import FixtureRetriever, RealCorpusRetriever, SimpleParser
from .contracts import Span
from .modules.idea import IdeaAgent, IdeaRequest
from .modules.literature import (
    FACET_LABELS,
    FACET_ORDER,
    TARGET_FULL_TEXT,
    TARGET_SOURCES,
    TARGET_SPANS,
    LiteratureAgent,
    LiteratureRequest,
)
from .specs import SpecStore


class ActionError(ValueError):
    pass


STAGES: List[Dict[str, Any]] = [
    {
        "id": "S1",
        "label": "文献调研",
        "owner": "literature",
        "gates": ["Q0"],
        "human_gate": False,
        "outputs": ["SourceHit", "Span", "CoverageReceipt", "LiteratureBrief"],
    },
    {
        "id": "S2–S3",
        "label": "假设收敛",
        "owner": "idea",
        "gates": ["G1"],
        "human_gate": True,
        "outputs": ["IdeaCard", "IdeaBrief"],
    },
    {
        "id": "S4",
        "label": "设计冻结",
        "owner": "experiment",
        "gates": ["G2"],
        "human_gate": True,
        "outputs": ["DesignCard", "ProtocolDraft"],
    },
    {
        "id": "S5a",
        "label": "复现执行",
        "owner": "run",
        "gates": ["X0–X7"],
        "human_gate": False,
        "outputs": ["RunCapsule"],
    },
    {
        "id": "S5b",
        "label": "证据判定",
        "owner": "run",
        "gates": ["S5"],
        "human_gate": True,
        "outputs": ["EvidenceArtifact", "ClaimRecord"],
    },
    {
        "id": "S6",
        "label": "结果图",
        "owner": "figure",
        "gates": [],
        "human_gate": False,
        "outputs": ["FigureManifest"],
    },
    {
        "id": "S8–S12",
        "label": "写作槽位",
        "owner": "paper",
        "gates": [],
        "human_gate": False,
        "outputs": ["PaperContract", "SectionSlots"],
    },
    {
        "id": "S13–S16",
        "label": "闭包检查",
        "owner": "closure",
        "gates": ["G5"],
        "human_gate": True,
        "outputs": ["ClosureReport", "Signature", "ExportManifest"],
    },
    {
        "id": "META",
        "label": "自进化提案",
        "owner": "rsi",
        "gates": [],
        "human_gate": False,
        "outputs": ["Candidate", "StepLedger"],
    },
]

HUMAN_GATES: List[Dict[str, str]] = [
    {"id": "G1", "after": "S2–S3", "reason": "候选假设收敛与新颖性仍需人工判断"},
    {"id": "G2", "after": "S4", "reason": "主指标、对照与 seeds 需要人工冻结"},
    {"id": "S5b", "after": "S5a", "reason": "Claim 只能由作者/PI 签署"},
    {"id": "G5", "after": "S13–S16", "reason": "闭包与导出需要人工放行"},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fingerprint(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def automation_plan(
    topic: str,
    max_sources: int = 6,
    run_dataset: str = "",
    run_seeds: int = 3,
) -> Dict[str, Any]:
    text = " ".join((topic or "").split())
    if len(text) < 2 or len(text) > 500:
        raise ActionError("topic must be 2-500 characters")
    if not 1 <= int(max_sources) <= 50:
        raise ActionError("max_sources must be between 1 and 50")
    if not 1 <= int(run_seeds) <= 10:
        raise ActionError("run_seeds must be between 1 and 10")
    if run_dataset not in ("", "iris", "breast_cancer", "chemlab"):
        raise ActionError("unknown run_dataset")

    budget = {
        "max_sources": int(max_sources),
        "target_sources": TARGET_SOURCES,
        "target_full_text": TARGET_FULL_TEXT,
        "target_spans": TARGET_SPANS,
        "run_seeds": int(run_seeds),
        "max_candidates": 3,
        "facets": len(FACET_ORDER),
    }
    seed = {
        "topic": text,
        "max_sources": int(max_sources),
        "run_dataset": run_dataset,
        "run_seeds": int(run_seeds),
        "stages": [stage["id"] for stage in STAGES],
    }
    return {
        "schema_version": "action-0.1",
        "action": "automation-plan",
        "generated_at": _now(),
        "topic": text,
        "mode": "governed_auto",
        "fingerprint": _fingerprint(seed),
        "stages": [dict(stage) for stage in STAGES],
        "human_gates": [dict(gate) for gate in HUMAN_GATES],
        "stop_at": "S5b",
        "budget": budget,
        "adaptive_literature": {
            "strategy": "facet_round_robin_then_bounded_fill",
            "facets": [
                {"id": facet, "label": FACET_LABELS[facet], "target_sources": 1}
                for facet in FACET_ORDER
            ],
            "coverage_plan": True,
        },
        "run": {
            "dataset": run_dataset or None,
            "seeds": int(run_seeds) if run_dataset else 0,
            "available": bool(run_dataset),
        },
        "boundary": "Plan only: no retrieval, run, claim, gate or signature is executed.",
    }


def _literature_skill(payload: Dict[str, Any]) -> Dict[str, Any]:
    question = str(payload.get("question") or payload.get("topic") or "").strip()
    if not question:
        raise ActionError("literature-brief requires question or topic")
    max_sources = int(payload.get("max_sources", 6))
    if not 1 <= max_sources <= 50:
        raise ActionError("max_sources must be between 1 and 50")
    source = str(payload.get("source", "fixture"))
    repo = Path(__file__).resolve().parents[1]
    if source == "real":
        retriever = RealCorpusRetriever(repo / "modules" / "literature" / "fixtures" / "real_corpus.json")
    elif source == "fixture":
        retriever = FixtureRetriever()
    else:
        raise ActionError("source must be fixture or real")
    agent = LiteratureAgent(SpecStore().load("literature"), retriever, SimpleParser())
    result = agent.run(
        LiteratureRequest(
            question=question,
            max_sources=max_sources,
            source_scope=[source],
            coverage_plan=True,
        )
    )
    brief = asdict(result.brief) if result.brief else None
    return {
        "schema_version": "action-0.1",
        "action": "skill",
        "skill_id": "literature-brief",
        "status": result.status,
        "coverage": {
            "sources": len(result.hits),
            "spans": len(result.spans),
            "gaps": len(result.coverage.gaps),
            "saturation": result.brief.saturation if result.brief else "unknown",
        },
        "brief": brief,
        "warnings": list(result.warnings),
        "boundary": "S1 span-only: abstracts are not evidence and no Claim is created.",
    }


def _idea_skill(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_spans = payload.get("spans") or []
    if not isinstance(raw_spans, list):
        raise ActionError("spans must be a list")
    spans: List[Span] = []
    for index, item in enumerate(raw_spans):
        if not isinstance(item, dict):
            raise ActionError("each span must be a JSON object")
        text = str(item.get("text") or "").strip()
        if not text:
            raise ActionError("span text must not be empty")
        spans.append(
            Span(
                span_id=str(item.get("span_id") or "SPAN-%02d" % (index + 1)),
                source_id=str(item.get("source_id") or "UNKNOWN"),
                section=str(item.get("section") or "section"),
                text=text,
                start=int(item.get("start", 0)),
                end=int(item.get("end", len(text))),
                fixture=bool(item.get("fixture", True)),
            )
        )
    result = IdeaAgent(SpecStore().load("idea")).run(
        IdeaRequest(
            topic=str(payload.get("topic") or "workspace"),
            spans=spans,
            max_candidates=int(payload.get("max_candidates", 3)),
        )
    )
    return {
        "schema_version": "action-0.1",
        "action": "skill",
        "skill_id": "hypothesis-triage",
        "status": result.status,
        "candidates": [asdict(card) for card in result.candidates],
        "brief": asdict(result.brief) if result.brief else None,
        "warnings": list(result.warnings),
        "boundary": "Candidates only: no novelty claim and no automatic G1.",
    }


def _protocol_skill(payload: Dict[str, Any]) -> Dict[str, Any]:
    protocol = payload.get("protocol") or payload
    if not isinstance(protocol, dict):
        raise ActionError("protocol must be a JSON object")
    metric = protocol.get("primary_metric") or protocol.get("metric")
    frozen = str(protocol.get("status") or "").strip().lower() == "frozen"
    checks = [
        ("hypothesis", bool(str(protocol.get("hypothesis") or "").strip())),
        ("baseline", bool(str(protocol.get("baseline") or "").strip())),
        ("metric", bool(str(metric or "").strip())),
        ("seeds", int(protocol.get("seeds") or 0) >= 2),
        ("controls", len(protocol.get("controls") or []) >= 1),
    ]
    if frozen:
        checks.extend([
            ("human_reason", bool(str(protocol.get("human_reason") or "").strip())),
            ("limitation", bool(str(protocol.get("limitation") or "").strip())),
            ("design_sha256", bool(str(protocol.get("design_sha256") or "").strip())),
        ])
    missing = [name for name, ok in checks if not ok]
    return {
        "schema_version": "action-0.2",
        "action": "skill",
        "skill_id": "protocol-review",
        "status": "pass" if not missing else "needs_input",
        "missing": missing,
        "frozen": frozen,
        "checks": [{"id": name, "ok": ok} for name, ok in checks],
        "boundary": (
            "Pre-registration fields and freeze metadata checked; G2 freeze and "
            "claim signing remain human actions."
        ),
    }


def _evidence_skill(payload: Dict[str, Any]) -> Dict[str, Any]:
    evidence = payload.get("evidence") or []
    if not isinstance(evidence, list):
        raise ActionError("evidence must be a list")
    claims = [item for item in evidence if isinstance(item, dict) and item.get("kind") == "claim"]
    unsigned = [item for item in claims if item.get("status") != "signed"]
    no_refs = [item for item in claims if not item.get("refs")]
    gaps = [item for item in evidence if isinstance(item, dict) and item.get("kind") == "gap"]
    status = "blocked" if no_refs or unsigned else "pass"
    return {
        "schema_version": "action-0.1",
        "action": "skill",
        "skill_id": "evidence-boundary",
        "status": status,
        "counts": {
            "claims": len(claims),
            "unsigned_claims": len(unsigned),
            "claims_without_refs": len(no_refs),
            "gaps": len(gaps),
        },
        "checks": [
            {"id": "claims_signed", "ok": not unsigned},
            {"id": "claims_have_refs", "ok": not no_refs},
            {"id": "gaps_registered", "ok": bool(gaps)},
        ],
        "boundary": "Read-only audit; evidence and gates are not modified.",
    }


def _protocol_skill_v10(payload: Dict[str, Any]) -> Dict[str, Any]:
    """The pre-freeze-metadata protocol check kept for rollback evaluation."""
    protocol = payload.get("protocol") or payload
    if not isinstance(protocol, dict):
        raise ActionError("protocol must be a JSON object")
    metric = protocol.get("primary_metric") or protocol.get("metric")
    checks = [
        ("hypothesis", bool(str(protocol.get("hypothesis") or "").strip())),
        ("baseline", bool(str(protocol.get("baseline") or "").strip())),
        ("metric", bool(str(metric or "").strip())),
        ("seeds", int(protocol.get("seeds") or 0) >= 2),
        ("controls", len(protocol.get("controls") or []) >= 1),
    ]
    missing = [name for name, ok in checks if not ok]
    return {
        "schema_version": "action-0.1",
        "action": "skill",
        "skill_id": "protocol-review",
        "status": "pass" if not missing else "needs_input",
        "missing": missing,
        "checks": [{"id": name, "ok": ok} for name, ok in checks],
        "boundary": "Basic pre-registration fields only; freeze metadata is not checked in v1.0.0.",
    }


SKILL_VERSIONS: Dict[str, Dict[str, Any]] = {
    "literature-brief": {"1.1.0": _literature_skill},
    "hypothesis-triage": {"1.0.0": _idea_skill},
    "protocol-review": {
        "1.0.0": _protocol_skill_v10,
        "1.1.0": _protocol_skill,
    },
    "evidence-boundary": {"1.0.0": _evidence_skill},
}
DEFAULT_SKILL_VERSIONS = {
    "literature-brief": "1.1.0",
    "hypothesis-triage": "1.0.0",
    "protocol-review": "1.1.0",
    "evidence-boundary": "1.0.0",
}


def run_skill(
    skill_id: str,
    payload: Optional[Dict[str, Any]] = None,
    version: Optional[str] = None,
) -> Dict[str, Any]:
    versions = SKILL_VERSIONS.get(skill_id)
    if not versions:
        raise ActionError("unknown skill: " + skill_id)
    resolved = version or DEFAULT_SKILL_VERSIONS[skill_id]
    handler = versions.get(resolved)
    if handler is None:
        raise ActionError("unknown %s version: %s" % (skill_id, resolved))
    if payload is not None and not isinstance(payload, dict):
        raise ActionError("payload must be a JSON object")
    result = handler(payload or {})
    result["skill_version"] = resolved
    return result

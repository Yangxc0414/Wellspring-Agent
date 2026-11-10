"""Internal deterministic benchmark for research-flow invariants.

This is not an external quality benchmark and not a capability claim. It checks
that strict pre-registration, claim reuse, closure binding and support-audit
oracle/nop behavior remain intact. Model quality still requires a separate
held-out task suite and human review.
"""

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from .bibliography import BibliographyAgent
from .closure import ClosureAgent
from .modules.experiment import ExperimentDesignAgent
from .modules.run import RunAgent
from .pipeline import PipelineRequest, PipelineRunner, write_pipeline_artifacts
from .specs import SpecStore
from .support_audit import audit_support


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _case(case_id: str, runner: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    started = time.monotonic()
    try:
        result = runner()
        result = {"case_id": case_id, "status": "pass", **result}
    except Exception as exc:
        result = {
            "case_id": case_id,
            "status": "fail",
            "error": "%s: %s" % (type(exc).__name__, exc),
        }
    result["latency_ms"] = int((time.monotonic() - started) * 1000)
    return result


def _strict_and_closure(root: Path, store: SpecStore) -> Dict[str, Any]:
    g1_out = root / "g1"
    first = PipelineRunner(store).run(PipelineRequest(
        topic="strict flow fixture",
        language="en",
        venue_type="en_conference",
        max_sources=6,
        flow_mode="strict",
    ))
    assert first.status == "needs_g1", first.status
    assert first.stopped_at == "G1", first.stopped_at
    assert "experiment" not in first.modules
    candidates = list((first.modules.get("idea") or {}).get("candidates") or [])
    selected = str(candidates[0]["idea_id"])
    decision = g1_out / "g1-decision.json"
    _write_json(decision, {
        "status": "approved",
        "selected_idea_id": selected,
        "human_reason": "benchmark selected candidate",
    })

    g2_out = root / "g2"
    second = PipelineRunner(store).run(PipelineRequest(
        topic="strict flow fixture",
        language="en",
        venue_type="en_conference",
        max_sources=6,
        flow_mode="strict",
        g1_decision_file=str(decision),
        run_dataset="iris",
        run_seeds=3,
    ))
    assert second.status == "needs_g2", second.status
    assert second.stopped_at == "G2", second.stopped_at
    assert "run" not in second.modules
    design = second.modules.get("experiment") or {}
    frozen = ExperimentDesignAgent(store.load("experiment")).freeze_design(
        design,
        "benchmark limitation",
        "benchmark reviewed design",
        g2_out / "protocol",
    )

    run_out = root / "run"
    third = PipelineRunner(store, run_output_dir=run_out).run(PipelineRequest(
        topic="strict flow fixture",
        language="en",
        venue_type="en_conference",
        max_sources=6,
        flow_mode="strict",
        g1_decision_file=str(decision),
        protocol_file=frozen["path"],
        run_dataset="iris",
        run_seeds=3,
    ))
    assert third.status == "needs_human", third.status
    capsule = (third.modules.get("run") or {}).get("paths") or {}
    draft = (third.modules.get("run") or {}).get("claim_draft_record") or {}
    claim = RunAgent(store.load("run")).claim(
        Path(capsule["capsule"]),
        Path(capsule["ea"]),
        str(draft["statement"]),
        "benchmark reviewed EA",
        "S5/demo/iris",
        root / "claim",
    )
    bibliography = BibliographyAgent().verify(
        Path(__file__).resolve().parents[1]
        / "modules" / "literature" / "fixtures" / "bibliography.json",
        root / "bibliography",
    )

    final_out = root / "final"
    final = PipelineRunner(store, run_output_dir=final_out / "run").run(PipelineRequest(
        topic="strict flow fixture",
        language="en",
        venue_type="en_conference",
        max_sources=6,
        flow_mode="strict",
        g1_decision_file=str(decision),
        protocol_file=frozen["path"],
        run_dir=capsule["capsule"] and str(Path(capsule["capsule"]).parent),
        claim_file=claim["path"],
        bibliography_file=bibliography["path"],
    ))
    paths = write_pipeline_artifacts(
        final, final_out, claim_file=claim["path"]
    )
    closure = json.loads(Path(paths["closure"]).read_text(encoding="utf-8"))
    assert closure.get("status") == "ready", closure.get("status")
    assert not closure.get("unresolved")
    sign = ClosureAgent().sign(
        Path(paths["closure"]),
        final_out / "demo.json",
        final_out / "claim" / "claim.json",
        "benchmark reviewed closure",
        final_out / "signature",
    )
    assert Path(sign["path"]).is_file()
    return {
        "checks": [
            "strict stopped at G1",
            "strict stopped at G2 without run",
            "protocol binding reused completed run",
            "closure ready with bibliography",
            "closure signed",
        ],
        "claim_id": claim["claim"]["claim_id"],
        "closure": closure.get("status"),
    }


class _EmptyRetriever:
    fixture_mode = True

    def search(self, query: str, limit: int) -> list:
        return []

    def full_text(self, source_id: str):
        return None


def _nop_no_evidence() -> Dict[str, Any]:
    result = PipelineRunner(
        retriever=_EmptyRetriever(), source_scope=["fixture"]
    ).run(PipelineRequest(
        topic="nop empty corpus",
        language="en",
        venue_type="en_conference",
        flow_mode="strict",
    ))
    assert result.status == "blocked_q0", result.status
    assert result.stopped_at == "Q0", result.stopped_at
    assert not any(key in result.modules for key in ("idea", "experiment", "run", "paper"))
    return {
        "checks": ["empty corpus blocks Q0 before idea/experiment/paper"],
        "pipeline_status": result.status,
    }


def _support_oracle_nop() -> Dict[str, Any]:
    spans = [
        {"span_id": "S-1", "source_id": "FX-1", "text": "Passivation improved stability under damp heat."},
        {"span_id": "S-2", "source_id": "FX-2", "text": "The control also improved under damp heat."},
    ]
    paper = {
        "title": "support benchmark",
        "draft": [{
            "section": "Results",
            "text": "Passivation improved stability under damp heat [S-1]. The control also improved [S-2].",
            "evidence_refs": ["S-1", "S-2"],
        }],
    }
    gold = {
        "Passivation improved stability under damp heat [S-1].": "supported",
        "The control also improved [S-2].": "supported",
    }

    def verdict(status: str):
        def judge(payload):
            return [{
                "id": item["id"],
                "status": status,
                "rationale": "benchmark " + status,
                "evidence_refs": [item["evidence"][0]["ref"]],
            } for item in payload["items"]]
        return judge

    oracle = audit_support(paper, spans, judge=verdict("supported"))
    nop = audit_support(paper, spans, judge=verdict("insufficient"))
    heuristic = audit_support(paper, spans)
    supported_oracle = oracle["counts"]["supported"]
    supported_nop = nop["counts"]["supported"]
    supported_heuristic = heuristic["counts"]["supported"]
    assert supported_oracle == len(oracle["items"])
    assert supported_nop == 0
    assert supported_heuristic == 0
    assert oracle["method"] == "model_judge"
    assert nop["method"] == "model_judge"
    assert heuristic["method"] == "lexical_overlap_heuristic"
    return {
        "checks": [
            "oracle judge reaches all supported",
            "nop judge returns zero supported",
            "heuristic never returns supported",
            "oracle and nop are labelled model_judge",
        ],
        "oracle_supported": supported_oracle,
        "nop_supported": supported_nop,
        "heuristic_supported": supported_heuristic,
        "gold": list(gold.values()),
    }


def run_internal_benchmark(
    output_dir: Optional[Path] = None,
    include_closure: bool = True,
) -> Dict[str, Any]:
    root = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="ra-bench-"))
    root.mkdir(parents=True, exist_ok=True)
    store = SpecStore()
    started = time.monotonic()
    cases = [
        _case("support-oracle-nop", _support_oracle_nop),
        _case("nop-empty-corpus", _nop_no_evidence),
    ]
    if include_closure:
        cases.append(_case(
            "strict-pre-registration-and-closure",
            lambda: _strict_and_closure(root / "closure-case", store),
        ))
    summary = {
        "total": len(cases),
        "passed": sum(1 for item in cases if item["status"] == "pass"),
        "failed": sum(1 for item in cases if item["status"] != "pass"),
    }
    report = {
        "schema_version": "internal-benchmark-0.1",
        "boundary": (
            "deterministic internal regression only; not an external capability benchmark, "
            "not human evaluation, and not evidence for a scientific claim"
        ),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "cases": cases,
        "summary": summary,
    }
    path = root / "benchmark.json"
    _write_json(path, report)
    report["path"] = str(path)
    return report

"""Fixed-instance evaluation on a frozen, CC-BY real-text corpus.

This is still a curated retrieval probe, not a peer-review benchmark. It exists
to replace synthetic-only evidence in the S1 harness loop with real paper text.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adapters import MiniLMRetriever, RealCorpusRetriever, SimpleParser
from .modules.literature import LiteratureAgent
from .rsi import RSIPolicyError, StepLedger
from .rsi_fixture import (
    SPLITS, FixtureTask, RetrievalPolicy, _evaluate_policy, run_retrieval_trial,
)
from .specs import SpecStore

BENCHMARK = "rsi-ccby-4"
BENCHMARK_MINILM = "rsi-ccby-4-minilm-abstract"
BENCHMARK_COMPARE = "rsi-ccby-4-compare"
BENCHMARK_MODEL = "rsi-ccby-4-model"
BASELINE = RetrievalPolicy("incumbent-full", 6, "bm25")


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _policies(retriever_kind: str):
    if retriever_kind == "bm25":
        return [
            RetrievalPolicy("candidate-budget4", 4, "bm25"),
            RetrievalPolicy("candidate-budget3", 3, "bm25"),
            RetrievalPolicy("candidate-budget2", 2, "bm25"),
            RetrievalPolicy("candidate-budget1", 1, "bm25"),
        ]
    if retriever_kind == "minilm":
        return [
            RetrievalPolicy("candidate-budget4", 4, "minilm"),
            RetrievalPolicy("candidate-budget3", 3, "minilm"),
            RetrievalPolicy("candidate-budget2", 2, "minilm"),
            RetrievalPolicy("candidate-budget1", 1, "minilm"),
        ]
    if retriever_kind == "compare":
        return [
            RetrievalPolicy("candidate-bm25-budget2", 2, "bm25"),
            RetrievalPolicy("candidate-minilm-budget3", 3, "minilm"),
        ]
    raise ValueError("retriever_kind must be bm25, minilm or compare")


def resolve_active_harness(ledger_path: Path, scope: str) -> Optional[Dict[str, Any]]:
    """Resolve an active real-harness lease; reject conflicting compositions."""
    ledger = StepLedger.load(Path(ledger_path))
    episodes = {record.candidate.candidate_id: record for record in ledger.episodes}
    matches = []
    for lease in ledger.leases:
        if lease.effective_status() != "active" or lease.scope != scope:
            continue
        record = episodes.get(lease.candidate_id)
        if record is None or record.candidate.target != "literature.retrieval.budget":
            continue
        try:
            patch = json.loads(record.candidate.patch)
        except (TypeError, ValueError):
            continue
        retriever = str(patch.get("retriever", ""))
        budget = patch.get("max_sources")
        if retriever in ("bm25", "minilm") and isinstance(budget, int) and not isinstance(budget, bool) and budget >= 1:
            matches.append({
                "lease_id": lease.lease_id,
                "episode_id": record.episode_id,
                "candidate_id": lease.candidate_id,
                "retriever": retriever,
                "max_sources": budget,
                "scope": lease.scope,
            })
    if not matches:
        return None
    signatures = {(item["retriever"], item["max_sources"]) for item in matches}
    if len(signatures) > 1:
        raise RSIPolicyError("conflicting active real harness leases: %s" % sorted(signatures))
    return matches[0]


def load_real_tasks(path: Path) -> List[FixtureTask]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("fixture") is not False:
        raise ValueError("real evaluation tasks must be marked fixture: false")
    if data.get("corpus_kind") != "real":
        raise ValueError("real evaluation tasks need corpus_kind: real")
    tasks = []
    for raw in data.get("tasks", []):
        if raw["split"] not in SPLITS:
            raise ValueError("unknown task split: " + raw["split"])
        tasks.append(FixtureTask(raw["task_id"], raw["split"], raw["question"], list(raw["gold_texts"])))
    if not tasks:
        raise ValueError("real evaluation needs at least one task")
    return tasks


def run_real_trial(
    ledger_path: Path,
    output_dir: Path,
    tasks_path: Optional[Path] = None,
    corpus_path: Optional[Path] = None,
    human_approve: bool = False,
    retriever_kind: str = "bm25",
    candidate_path: Optional[Path] = None,
) -> Dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    tasks_path = tasks_path or root / "research_agent" / "rsi_fixtures" / "real_tasks.json"
    corpus_path = corpus_path or root / "modules" / "literature" / "fixtures" / "real_corpus.json"
    tasks = load_real_tasks(Path(tasks_path))
    proposal = None
    if candidate_path:
        proposal = json.loads(Path(candidate_path).read_text(encoding="utf-8"))
        patch = proposal.get("patch")
        if isinstance(patch, str):
            patch = json.loads(patch)
        if not isinstance(patch, dict):
            raise ValueError("model candidate patch must be a JSON object")
        retriever = str(patch.get("retriever", "bm25")).lower()
        budget = patch.get("max_sources")
        if retriever not in ("bm25", "minilm") or not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
            raise ValueError("model candidate needs retriever and positive max_sources")
        retriever_kind = retriever
        policies = [RetrievalPolicy(
            str(proposal.get("candidate_id", "candidate-model")), budget, retriever
        )]
        benchmark = BENCHMARK_MODEL
    else:
        policies = _policies(retriever_kind)
        if retriever_kind == "bm25":
            benchmark = BENCHMARK
        elif retriever_kind == "minilm":
            benchmark = BENCHMARK_MINILM
        else:
            benchmark = BENCHMARK_COMPARE
    agents = {"bm25": LiteratureAgent(
        SpecStore().load("literature"),
        RealCorpusRetriever(Path(corpus_path)),
        SimpleParser(max_spans_per_source=2000),
    )}
    if retriever_kind in ("minilm", "compare"):
        agents["minilm"] = LiteratureAgent(
            SpecStore().load("literature"),
            MiniLMRetriever(Path(corpus_path)),
            SimpleParser(max_spans_per_source=2000),
        )
    result = run_retrieval_trial(
        tasks,
        agents,
        Path(ledger_path),
        Path(output_dir),
        human_approve=human_approve,
        simulation=False,
        benchmark=benchmark,
        source_scope=["real"],
        claim_eligible=False,
        note="Frozen CC-BY paper text; curated retrieval probe, not a peer-review or capability benchmark.",
        policies=policies,
        baseline_policy=BASELINE,
        proposal_meta={str(proposal.get("candidate_id")): proposal} if proposal else None,
    )
    result["corpus"] = str(Path(corpus_path))
    result["retriever"] = retriever_kind
    if proposal is not None:
        result["proposal"] = proposal
    return result


def run_real_confirmation(
    ledger_path: Path,
    output_dir: Path,
    scope: str,
    tasks_path: Optional[Path] = None,
    corpus_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Post-lease sealed check on new real questions; never feeds admission."""
    root = Path(__file__).resolve().parents[1]
    tasks_path = tasks_path or root / "research_agent" / "rsi_fixtures" / "real_confirm_tasks.json"
    corpus_path = corpus_path or root / "modules" / "literature" / "fixtures" / "real_corpus.json"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "real-confirmation.json"
    active = resolve_active_harness(Path(ledger_path), scope)
    if active is None:
        result = {
            "fixture": False,
            "sealed": True,
            "used_for_admission": False,
            "status": "no_active_lease",
            "passed": False,
            "scope": scope,
            "note": "No active real harness lease for this scope; confirmation was not run.",
        }
        _write_json(receipt_path, result)
        return result

    tasks = load_real_tasks(Path(tasks_path))
    if any(task.split != "hidden" for task in tasks):
        raise ValueError("real confirmation tasks must all be hidden")
    bm25_agent = LiteratureAgent(
        SpecStore().load("literature"),
        RealCorpusRetriever(Path(corpus_path)),
        SimpleParser(max_spans_per_source=2000),
    )
    candidate_agent = bm25_agent
    if active["retriever"] == "minilm":
        candidate_agent = LiteratureAgent(
            SpecStore().load("literature"),
            MiniLMRetriever(Path(corpus_path)),
            SimpleParser(max_spans_per_source=2000),
        )
    baseline = _evaluate_policy(
        bm25_agent, tasks, BASELINE, "hidden", output_dir,
        source_scope=["real"], simulation=False, benchmark="rsi-ccby-4-confirm",
    )
    candidate = _evaluate_policy(
        candidate_agent, tasks,
        RetrievalPolicy("lease-" + active["lease_id"], active["max_sources"], active["retriever"]),
        "hidden", output_dir, source_scope=["real"], simulation=False,
        benchmark="rsi-ccby-4-confirm",
    )
    delta = {
        "gold_recall": candidate["metrics"]["gold_recall"] - baseline["metrics"]["gold_recall"],
        "cost": candidate["metrics"]["cost"] - baseline["metrics"]["cost"],
        "coverage_gaps": candidate["metrics"]["coverage_gaps"] - baseline["metrics"]["coverage_gaps"],
    }
    passed = delta["gold_recall"] >= 0 and delta["coverage_gaps"] <= 0
    result = {
        "fixture": False,
        "sealed": True,
        "used_for_admission": False,
        "status": "confirmed" if passed else "regressed",
        "scope": scope,
        "lease": active,
        "baseline": baseline["metrics"],
        "candidate": candidate["metrics"],
        "delta": delta,
        "n": candidate["n"],
        "passed": passed,
        "baseline_receipt": str(baseline["receipt"].relative_to(output_dir.parent)),
        "candidate_receipt": str(candidate["receipt"].relative_to(output_dir.parent)),
        "note": "Post-lease sealed real-text confirmation; not admission evidence and not a capability claim.",
    }
    _write_json(receipt_path, result)
    return result

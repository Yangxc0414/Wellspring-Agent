"""A local, training-free TF-RSI fixture loop.

This is a *mechanism test*, not a scientific benchmark. It evaluates several
retrieval-budget policies on a frozen synthetic corpus, splits questions into
public / hidden / near-OOD / regression, and requires explicit human approval
before a lease is issued.

The loop is intentionally small: it demonstrates archive/selection and
regularized non-inferiority checks, not research quality.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .adapters import FixtureRetriever, SimpleParser
from .modules.literature import LiteratureAgent, LiteratureRequest
from .rsi import Candidate, CandidateArchive, EvalEvidence, RSIController, RSIPolicyError, StepLedger
from .specs import SpecStore


@dataclass(frozen=True)
class FixtureTask:
    task_id: str
    split: str
    question: str
    gold_texts: List[str]


@dataclass(frozen=True)
class RetrievalPolicy:
    policy_id: str
    max_sources: int
    retriever_kind: str = "fixture"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "max_sources": self.max_sources,
            "retriever": self.retriever_kind,
        }


POLICIES = [
    RetrievalPolicy("candidate-budget4", 4),
    RetrievalPolicy("candidate-budget3", 3),
    RetrievalPolicy("candidate-budget2", 2),
    RetrievalPolicy("candidate-budget1", 1),
]
BASE_POLICY = RetrievalPolicy("incumbent-full", 6)
SPLITS = ("public", "hidden", "near_ood", "regression")
MAX_FINALISTS = 2


def load_tasks(path: Path) -> List[FixtureTask]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("fixture") is not True:
        raise ValueError("RSI fixture tasks must be marked fixture: true")
    tasks = []
    for raw in data.get("tasks", []):
        if raw["split"] not in SPLITS:
            raise ValueError("unknown task split: " + raw["split"])
        tasks.append(FixtureTask(raw["task_id"], raw["split"], raw["question"], list(raw["gold_texts"])))
    if not tasks:
        raise ValueError("RSI fixture needs at least one task")
    return tasks


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def active_literature_policy(ledger_path: Path, expected_scope: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Resolve the single active literature-budget lease, optionally scoped."""
    ledger = StepLedger.load(Path(ledger_path))
    episodes = {record.candidate.candidate_id: record for record in ledger.episodes}
    resolved: List[Dict[str, Any]] = []
    for lease in ledger.leases:
        if lease.effective_status() != "active":
            continue
        if expected_scope is not None and lease.scope != expected_scope:
            continue
        record = episodes.get(lease.candidate_id)
        if record is None or record.candidate.target != "literature.retrieval.budget":
            continue
        try:
            patch = json.loads(record.candidate.patch)
        except (TypeError, ValueError):
            continue
        budget = patch.get("max_sources")
        if isinstance(budget, int) and not isinstance(budget, bool) and 1 <= budget <= 64:
            resolved.append({
                "lease_id": lease.lease_id,
                "episode_id": record.episode_id,
                "candidate_id": lease.candidate_id,
                "max_sources": budget,
                "scope": lease.scope,
            })
    if not resolved:
        return None
    budgets = sorted({item["max_sources"] for item in resolved})
    if len(budgets) > 1:
        raise RSIPolicyError("conflicting active literature budgets: %s" % budgets)
    return resolved[0]


def _evaluate_policy(
    agent: LiteratureAgent,
    tasks: List[FixtureTask],
    policy: RetrievalPolicy,
    split: str,
    output_dir: Path,
    source_scope: Optional[List[str]] = None,
    simulation: bool = True,
    benchmark: str = "fixture",
) -> Dict[str, Any]:
    details = []
    recalls = []
    total_cost = 0
    total_gaps = 0
    for task in [t for t in tasks if t.split == split]:
        result = agent.run(
            LiteratureRequest(
                question=task.question,
                max_sources=policy.max_sources,
                source_scope=list(source_scope or ["fixture"]),
                run_id="RSI-%s-%s" % (policy.policy_id, task.task_id),
            )
        )
        span_text = "\n".join(span.text for span in result.spans)
        hits = [gold for gold in task.gold_texts if gold in span_text]
        recall = len(hits) / len(task.gold_texts) if task.gold_texts else 0.0
        cost = len(result.query_plan.subqueries) + len(result.hits)
        gaps = len(result.coverage.gaps)
        recalls.append(recall)
        total_cost += cost
        total_gaps += gaps
        details.append({
            "task_id": task.task_id,
            "recall": recall,
            "found_gold": hits,
            "sources": len(result.hits),
            "spans": len(result.spans),
            "coverage_gaps": gaps,
            "cost": cost,
            "status": result.status,
        })
    metrics = {
        "gold_recall": sum(recalls) / len(recalls) if recalls else 0.0,
        "cost": total_cost,
        "coverage_gaps": total_gaps,
    }
    receipt = {
        "fixture": simulation,
        "benchmark": benchmark,
        "policy": policy.as_dict(),
        "split": split,
        "metrics": metrics,
        "tasks": details,
        "note": (
            "Synthetic fixture task pack; not a scientific benchmark."
            if simulation else
            "Frozen real-text body corpus; curated retrieval probe, not a peer-review benchmark."
        ),
    }
    path = output_dir / ("%s-%s.json" % (policy.policy_id, split))
    _write_json(path, receipt)
    return {"split": split, "metrics": metrics, "receipt": path, "n": len(details)}


def _task_pack_sha(tasks: List[Any]) -> str:
    payload = [asdict(task) if hasattr(task, "__dataclass_fields__") else task for task in tasks]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _evidence(
    receipt: Dict[str, Any],
    output_dir: Path,
    status: str = "passed",
    simulation: bool = True,
    benchmark: str = "fixture",
    claim_eligible: bool = True,
    task_pack_sha256: str = "",
) -> EvalEvidence:
    receipt_path = Path(receipt["receipt"])
    artifact_hash = (
        hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        if receipt_path.is_file() else ""
    )
    return EvalEvidence(
        split=receipt["split"],
        status=status,
        artifact_ref=str(receipt_path.relative_to(output_dir.parent)),
        metrics=receipt["metrics"],
        n=receipt["n"],
        simulation=simulation,
        claim_eligible=claim_eligible,
        evaluator="deterministic-fixture" if simulation else "deterministic-real-corpus",
        artifact_sha256=artifact_hash,
        task_pack_sha256=task_pack_sha256,
        evaluated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        note=(
            "TF-RSI synthetic fixture; not a scientific benchmark"
            if simulation else
            "Frozen CC-BY real-text probe (%s); harness metric, not a research capability claim" % benchmark
        ),
    )


def _dry_run(policy: RetrievalPolicy, output_dir: Path, simulation: bool = True, benchmark: str = "fixture") -> Path:
    path = output_dir / ("dry-run-%s.json" % policy.policy_id)
    _write_json(path, {
        "fixture": simulation,
        "benchmark": benchmark,
        "policy": policy.as_dict(),
        "schema_check": "max_sources is a positive integer; no claim/gate mutation",
    })
    return path


def run_retrieval_trial(
    tasks: List[FixtureTask],
    agents: Dict[str, LiteratureAgent],
    ledger_path: Path,
    output_dir: Path,
    human_approve: bool = False,
    simulation: bool = True,
    benchmark: str = "fixture",
    source_scope: Optional[List[str]] = None,
    claim_eligible: bool = True,
    note: str = "",
    policies: Optional[List[RetrievalPolicy]] = None,
    baseline_policy: RetrievalPolicy = BASE_POLICY,
    proposal_meta: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    policies = list(policies or POLICIES)
    task_pack_sha = _task_pack_sha(tasks)

    baseline_agent = agents[baseline_policy.retriever_kind]
    baseline = {
        split: _evaluate_policy(
            baseline_agent, tasks, baseline_policy, split, output_dir,
            source_scope=source_scope, simulation=simulation, benchmark=benchmark,
        )
        for split in SPLITS
    }
    base_public = baseline["public"]["metrics"]
    base_hidden = baseline["hidden"]["metrics"]
    ledger = StepLedger.load(Path(ledger_path))
    controller = RSIController(ledger)
    candidate_reports: List[Dict[str, Any]] = []
    public_finalists: List[Dict[str, Any]] = []

    for policy in policies:
        scope = "S1/%s" % benchmark
        patch = json.dumps(policy.as_dict(), ensure_ascii=False)
        existing = next(
            (
                record for record in ledger.episodes
                if record.candidate.target == "literature.retrieval.budget"
                and record.candidate.patch == patch
                and record.candidate.scope == scope
            ),
            None,
        )
        if existing is not None:
            candidate_reports.append({
                "policy": policy.as_dict(),
                "episode_id": existing.episode_id,
                "decision": "skipped_" + existing.decision,
                "would_accept": False,
                "deduplicated": True,
                "note": "candidate already recorded on this benchmark; no silent retry",
            })
            continue
        meta = (proposal_meta or {}).get(policy.policy_id, {})
        candidate_id = (
            policy.policy_id
            if policy.policy_id.startswith("CAND-")
            else "%s:%s" % (benchmark, policy.policy_id)
        )
        episode = controller.propose(
            Candidate(
                kind="process",
                target="literature.retrieval.budget",
                patch=patch,
                rationale=str(meta.get("rationale") or "budget trial: reduce retrieval budget while preserving gold-span recall"),
                predicted_effect=str(meta.get("predicted_effect") or "same recall with fewer sources: %d -> %d" % (BASE_POLICY.max_sources, policy.max_sources)),
                parent_id=str(meta.get("parent_id", "")),
                scope=scope,
                candidate_id=candidate_id,
                predicted_metrics=dict(meta.get("predicted_metrics") or {}),
                proposer=str(meta.get("proposer", "human-cli")),
                proposer_model=str(meta.get("proposer_model", "")),
                prompt_sha256=str(meta.get("prompt_sha256", "")),
            ),
            observation="budget prefilter on public %s" % benchmark,
            dry_run_ref=str(_dry_run(policy, output_dir, simulation=simulation, benchmark=benchmark)),
            simulation=simulation,
        )
        if policy.max_sources < 2:
            controller.reject(episode.episode_id, "critic/pruner: max_sources below 2 is too aggressive for coverage")
            candidate_reports.append({
                "policy": policy.as_dict(), "episode_id": episode.episode_id,
                "public_ok": False, "non_inferior": False, "cheaper": False,
                "would_accept": False, "decision": "rejected", "pruned": "min_sources",
            })
            continue
        public = _evidence(
            _evaluate_policy(
                agents[policy.retriever_kind], tasks, policy, "public", output_dir,
                source_scope=source_scope, simulation=simulation, benchmark=benchmark,
            ),
            output_dir, simulation=simulation, benchmark=benchmark, claim_eligible=claim_eligible,
            task_pack_sha256=task_pack_sha,
        )
        controller.evaluate(episode.episode_id, public)  # public-only prefilter
        public_ok = public.metrics["gold_recall"] >= base_public["gold_recall"]
        report: Dict[str, Any] = {
            "policy": policy.as_dict(), "episode_id": episode.episode_id,
            "public": public.metrics, "public_ok": public_ok,
        }
        if not public_ok:
            controller.reject(episode.episode_id, "public prefilter: lower gold-span recall")
            report.update({"non_inferior": False, "cheaper": False, "would_accept": False, "decision": "rejected"})
            candidate_reports.append(report)
            continue
        public_finalists.append({"policy": policy, "episode": episode, "public": public, "report": report})
        candidate_reports.append(report)

    chosen = None
    if public_finalists:
        public_finalists.sort(key=lambda item: (item["report"]["public"]["cost"], item["policy"].policy_id))
        evaluated = set()
        for finalist in public_finalists[:MAX_FINALISTS]:
            policy = finalist["policy"]
            episode = finalist["episode"]
            public = finalist["public"]
            report = finalist["report"]
            hidden = _evidence(
                _evaluate_policy(
                    agents[policy.retriever_kind], tasks, policy, "hidden", output_dir,
                    source_scope=source_scope, simulation=simulation, benchmark=benchmark,
                ),
                output_dir, simulation=simulation, benchmark=benchmark, claim_eligible=claim_eligible,
                task_pack_sha256=task_pack_sha,
            )
            near_ood = _evidence(
                _evaluate_policy(
                    agents[policy.retriever_kind], tasks, policy, "near_ood", output_dir,
                    source_scope=source_scope, simulation=simulation, benchmark=benchmark,
                ),
                output_dir, simulation=simulation, benchmark=benchmark, claim_eligible=claim_eligible,
                task_pack_sha256=task_pack_sha,
            )
            regression = _evidence(
                _evaluate_policy(
                    agents[policy.retriever_kind], tasks, policy, "regression", output_dir,
                    source_scope=source_scope, simulation=simulation, benchmark=benchmark,
                ),
                output_dir, simulation=simulation, benchmark=benchmark, claim_eligible=claim_eligible,
                task_pack_sha256=task_pack_sha,
            )
            controller.evaluate(episode.episode_id, public, hidden, near_ood, regression)
            non_inferior = (
                hidden.metrics["gold_recall"] >= baseline["hidden"]["metrics"]["gold_recall"]
                and near_ood.metrics["gold_recall"] >= baseline["near_ood"]["metrics"]["gold_recall"]
                and regression.metrics["gold_recall"] >= baseline["regression"]["metrics"]["gold_recall"]
                and hidden.metrics["coverage_gaps"] <= baseline["hidden"]["metrics"]["coverage_gaps"]
                and near_ood.metrics["coverage_gaps"] <= baseline["near_ood"]["metrics"]["coverage_gaps"]
                and regression.metrics["coverage_gaps"] <= baseline["regression"]["metrics"]["coverage_gaps"]
            )
            cheaper = hidden.metrics["cost"] < base_hidden["cost"]
            actual = {
                "hidden_recall_delta": hidden.metrics["gold_recall"] - baseline["hidden"]["metrics"]["gold_recall"],
                "hidden_cost_delta": hidden.metrics["cost"] - baseline["hidden"]["metrics"]["cost"],
                "hidden_gap_delta": hidden.metrics["coverage_gaps"] - baseline["hidden"]["metrics"]["coverage_gaps"],
                "near_ood_recall_delta": near_ood.metrics["gold_recall"] - baseline["near_ood"]["metrics"]["gold_recall"],
                "near_ood_gap_delta": near_ood.metrics["coverage_gaps"] - baseline["near_ood"]["metrics"]["coverage_gaps"],
                "regression_recall_delta": regression.metrics["gold_recall"] - baseline["regression"]["metrics"]["gold_recall"],
                "regression_gap_delta": regression.metrics["coverage_gaps"] - baseline["regression"]["metrics"]["coverage_gaps"],
            }
            controller.record_actuals(episode.episode_id, actual, "prediction audit recorded")
            report.update({
                "hidden": hidden.metrics, "near_ood": near_ood.metrics, "regression": regression.metrics,
                "non_inferior": non_inferior, "cheaper": cheaper,
                "would_accept": non_inferior and cheaper,
            })
            evaluated.add(episode.episode_id)
            if report["would_accept"]:
                report["decision"] = "pending_human"
                chosen = report
                break
            controller.reject(episode.episode_id, "hidden/near-OOD/regression gate failed")
            report["decision"] = "rejected"
        for other in public_finalists:
            if other["episode"].episode_id in evaluated:
                continue
            controller.reject(
                other["episode"].episode_id,
                "not evaluated: finalist budget exhausted or an earlier finalist passed; hidden held out",
            )
            other["report"].update({
                "hidden_held_out": True, "non_inferior": False, "cheaper": False,
                "would_accept": False, "decision": "rejected",
            })
    if human_approve and chosen:
        selected = controller.ledger.find(chosen["episode_id"])
        controller.admit(
            selected.episode_id,
            selected.public_eval, selected.hidden_eval,
            "human-approved %s process change" % benchmark, "S1/%s" % benchmark, 30,
            near_ood_eval=selected.near_ood_eval, regression_eval=selected.regression_eval,
            strict=not simulation, approved_by="human-cli",
        )
        for report in candidate_reports:
            if report["episode_id"] != chosen["episode_id"]:
                record = controller.ledger.find(report["episode_id"])
                if record.decision == "pending_human":
                    controller.reject(report["episode_id"], "not selected; dominated by " + chosen["policy"]["policy_id"])
                report["decision"] = controller.ledger.find(report["episode_id"]).decision
        chosen["decision"] = "approved"
    elif human_approve:
        for report in candidate_reports:
            record = controller.ledger.find(report["episode_id"])
            if record.decision == "pending_human":
                controller.reject(report["episode_id"], "%s gate failed: non-inferior recall and lower cost" % benchmark)
                report["decision"] = "rejected"
    else:
        for report in candidate_reports:
            report["decision"] = controller.ledger.find(report["episode_id"]).decision

    prediction_audit = None
    if chosen:
        prediction_audit = {
            "predicted": "same recall with fewer sources",
            "actual": {
                "hidden_recall_delta": chosen["hidden"]["gold_recall"] - baseline["hidden"]["metrics"]["gold_recall"],
                "hidden_cost_delta": chosen["hidden"]["cost"] - baseline["hidden"]["metrics"]["cost"],
                "hidden_gap_delta": chosen["hidden"]["coverage_gaps"] - baseline["hidden"]["metrics"]["coverage_gaps"],
                "near_ood_recall_delta": chosen["near_ood"]["gold_recall"] - baseline["near_ood"]["metrics"]["gold_recall"],
                "near_ood_gap_delta": chosen["near_ood"]["coverage_gaps"] - baseline["near_ood"]["metrics"]["coverage_gaps"],
                "regression_recall_delta": chosen["regression"]["gold_recall"] - baseline["regression"]["metrics"]["gold_recall"],
                "regression_gap_delta": chosen["regression"]["coverage_gaps"] - baseline["regression"]["metrics"]["coverage_gaps"],
            },
            "fixture": simulation,
            "benchmark": benchmark,
        }
        controller.record_actuals(chosen["episode_id"], prediction_audit["actual"], "prediction audit recorded")
    result = {
        "fixture": simulation,
        "simulation": simulation,
        "benchmark": benchmark,
        "note": note or (
            "Mechanism test only; public/hidden fixtures are synthetic and are not research evidence."
            if simulation else
            "Frozen real-text probe; curated retrieval metric, not a research capability benchmark."
        ),
        "selection": "public cost ranks candidates; at most two finalists are gated in that pre-registered order; hidden is not used for ranking",
        "baseline": {split: baseline[split]["metrics"] for split in SPLITS},
        "candidates": candidate_reports,
        "chosen": chosen["policy"]["policy_id"] if chosen else None,
        "human_approve": human_approve,
        "would_accept": bool(chosen),
        "decision": chosen["decision"] if chosen else "no_candidate",
        "prediction_audit": prediction_audit,
        "rsi_report": controller.report(),
    }
    _write_json(output_dir / "tf-rsi-report.json", result)
    return result


def run_fixture_trial(
    ledger_path: Path,
    output_dir: Path,
    tasks_path: Optional[Path] = None,
    human_approve: bool = False,
) -> Dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    tasks_path = tasks_path or root / "research_agent" / "rsi_fixtures" / "tasks.json"
    tasks = load_tasks(Path(tasks_path))
    agent = LiteratureAgent(SpecStore().load("literature"), FixtureRetriever(), SimpleParser())
    return run_retrieval_trial(
        tasks,
        {"fixture": agent},
        ledger_path,
        output_dir,
        human_approve=human_approve,
        simulation=True,
        benchmark="fixture",
        source_scope=["fixture"],
        note="Mechanism test only; public/hidden fixtures are synthetic and are not research evidence.",
    )


def run_observation_trial(
    candidate_policy: RetrievalPolicy,
    observation: str,
    ledger_path: Path,
    output_dir: Path,
    human_approve: bool = False,
) -> Dict[str, Any]:
    """Evaluate one observation-derived policy against the fixture incumbent."""
    root = Path(__file__).resolve().parents[1]
    tasks = load_tasks(root / "research_agent" / "rsi_fixtures" / "tasks.json")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    spec = SpecStore().load("literature")
    agent = LiteratureAgent(spec, FixtureRetriever(), SimpleParser())
    task_pack_sha = _task_pack_sha(tasks)
    baseline = {split: _evaluate_policy(agent, tasks, BASE_POLICY, split, output_dir) for split in SPLITS}
    trial = {split: _evaluate_policy(agent, tasks, candidate_policy, split, output_dir) for split in SPLITS}

    controller = RSIController(StepLedger.load(Path(ledger_path)))
    parents = CandidateArchive(controller.ledger).select_parents(1)
    parent_id = parents[0] if parents else ""
    episode = controller.propose(
        Candidate(
            kind="process",
            target="literature.retrieval.budget",
            patch=json.dumps(candidate_policy.as_dict(), ensure_ascii=False),
            rationale="observation-derived fixture policy",
            predicted_effect="same recall with fewer sources: %d -> %d" % (BASE_POLICY.max_sources, candidate_policy.max_sources),
            parent_id=parent_id,
            scope="S1/fixture/zh+en",
        ),
        observation=observation,
        dry_run_ref=str(_dry_run(candidate_policy, output_dir)),
        simulation=True,
    )
    public = _evidence(trial["public"], output_dir, task_pack_sha256=task_pack_sha)
    hidden = _evidence(trial["hidden"], output_dir, task_pack_sha256=task_pack_sha)
    near_ood = _evidence(trial["near_ood"], output_dir, task_pack_sha256=task_pack_sha)
    regression = _evidence(trial["regression"], output_dir, task_pack_sha256=task_pack_sha)
    controller.evaluate(episode.episode_id, public, hidden, near_ood, regression)
    non_inferior = all(
        trial[split]["metrics"]["gold_recall"] >= baseline[split]["metrics"]["gold_recall"]
        and trial[split]["metrics"]["coverage_gaps"] <= baseline[split]["metrics"]["coverage_gaps"]
        for split in ("hidden", "near_ood", "regression")
    )
    cheaper = trial["hidden"]["metrics"]["cost"] < baseline["hidden"]["metrics"]["cost"]
    would_accept = non_inferior and cheaper
    if human_approve and would_accept:
        controller.admit(
            episode.episode_id, public, hidden, "human-approved observation-derived policy",
            "S1/fixture", 30, near_ood_eval=near_ood, regression_eval=regression,
            approved_by="human-cli",
        )
    elif human_approve and not would_accept:
        controller.reject(episode.episode_id, "fixture gate failed: non-inferior recall or lower cost")

    actual = {
        "hidden_recall_delta": trial["hidden"]["metrics"]["gold_recall"] - baseline["hidden"]["metrics"]["gold_recall"],
        "hidden_cost_delta": trial["hidden"]["metrics"]["cost"] - baseline["hidden"]["metrics"]["cost"],
        "hidden_gap_delta": trial["hidden"]["metrics"]["coverage_gaps"] - baseline["hidden"]["metrics"]["coverage_gaps"],
        "near_ood_recall_delta": trial["near_ood"]["metrics"]["gold_recall"] - baseline["near_ood"]["metrics"]["gold_recall"],
        "near_ood_gap_delta": trial["near_ood"]["metrics"]["coverage_gaps"] - baseline["near_ood"]["metrics"]["coverage_gaps"],
        "regression_recall_delta": trial["regression"]["metrics"]["gold_recall"] - baseline["regression"]["metrics"]["gold_recall"],
        "regression_gap_delta": trial["regression"]["metrics"]["coverage_gaps"] - baseline["regression"]["metrics"]["coverage_gaps"],
    }
    controller.record_actuals(episode.episode_id, actual, "prediction audit recorded")
    result = {
        "fixture": True,
        "simulation": True,
        "observation": observation,
        "candidate": candidate_policy.as_dict(),
        "parent_episode": parent_id,
        "baseline": {split: baseline[split]["metrics"] for split in SPLITS},
        "candidate_metrics": {split: trial[split]["metrics"] for split in SPLITS},
        "non_inferior": non_inferior,
        "cheaper": cheaper,
        "would_accept": would_accept,
        "human_approve": human_approve,
        "episode_id": episode.episode_id,
        "decision": controller.ledger.find(episode.episode_id).decision,
        "prediction_audit": {"predicted": "same recall with fewer sources", "actual": actual, "fixture": True},
        "rsi_report": controller.report(),
    }
    _write_json(output_dir / "observation-report.json", result)
    return result


def run_confirmation_trial(
    ledger_path: Path,
    output_dir: Path,
    tasks_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Post-lease sealed confirmation; never feeds selection or admission."""
    root = Path(__file__).resolve().parents[1]
    tasks_path = tasks_path or root / "research_agent" / "rsi_fixtures" / "tasks_confirm.json"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "lease-confirmation.json"
    active = active_literature_policy(Path(ledger_path), expected_scope="S1/fixture")
    if active is None:
        result = {
            "fixture": True,
            "sealed": True,
            "used_for_admission": False,
            "status": "no_active_lease",
            "passed": False,
            "note": "No active literature-budget lease; confirmation was not run.",
        }
        _write_json(receipt_path, result)
        return result

    tasks = load_tasks(Path(tasks_path))
    spec = SpecStore().load("literature")
    agent = LiteratureAgent(spec, FixtureRetriever(), SimpleParser())
    baseline = _evaluate_policy(agent, tasks, BASE_POLICY, "hidden", output_dir)
    policy = RetrievalPolicy("lease-" + active["lease_id"].split("-")[-1], active["max_sources"])
    candidate = _evaluate_policy(agent, tasks, policy, "hidden", output_dir)
    delta = {
        "gold_recall": candidate["metrics"]["gold_recall"] - baseline["metrics"]["gold_recall"],
        "cost": candidate["metrics"]["cost"] - baseline["metrics"]["cost"],
        "coverage_gaps": candidate["metrics"]["coverage_gaps"] - baseline["metrics"]["coverage_gaps"],
    }
    passed = delta["gold_recall"] >= 0 and delta["cost"] <= 0 and delta["coverage_gaps"] <= 0
    result = {
        "fixture": True,
        "sealed": True,
        "used_for_admission": False,
        "status": "confirmed" if passed else "regressed",
        "lease": active,
        "policy": policy.as_dict(),
        "baseline": baseline["metrics"],
        "candidate": candidate["metrics"],
        "delta": delta,
        "n": candidate["n"],
        "passed": passed,
        "receipt": str(receipt_path.relative_to(output_dir.parent)),
        "note": "Sealed fixture confirmation read only after admission; not admission evidence and not a scientific benchmark.",
    }
    _write_json(receipt_path, result)
    return result

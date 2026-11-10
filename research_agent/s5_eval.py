"""S5 seed-budget RSI evaluator: real local runs -> public/hidden gates."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .contracts import RunRequest
from .modules.run import RunAgent
from .rsi import Candidate, EvalEvidence, RSIController, RSIPolicyError, StepLedger
from .specs import SpecStore

SPLITS = ("public", "hidden", "near_ood", "regression")
TASKS = (
    {"task_id": "S5-PUB-02", "split": "public", "test_size": 0.2},
    {"task_id": "S5-PUB-03", "split": "public", "test_size": 0.3},
    {"task_id": "S5-HID-025", "split": "hidden", "test_size": 0.25},
    {"task_id": "S5-HID-035", "split": "hidden", "test_size": 0.35},
    {"task_id": "S5-OOD-015", "split": "near_ood", "test_size": 0.15},
    {"task_id": "S5-OOD-04", "split": "near_ood", "test_size": 0.4},
    {"task_id": "S5-REG-01", "split": "regression", "test_size": 0.1},
    {"task_id": "S5-REG-045", "split": "regression", "test_size": 0.45},
)
BASELINE_SEEDS = 5
CANDIDATE_SEEDS = (4, 3, 2)
MAX_FINALISTS = 2
TASK_PACK_SHA = hashlib.sha256(
    json.dumps(TASKS, sort_keys=True, ensure_ascii=False).encode("utf-8")
).hexdigest()
SCOPE = "S5/demo/iris"
DATASETS = ("iris", "breast_cancer", "chemlab")
DATASET_METRIC = {"iris": "accuracy", "breast_cancer": "accuracy", "chemlab": "r2"}
MEAN_TOLERANCE = 0.015
MIN_TOLERANCE = 0.03
CONFIRM_TASKS = (
    {"task_id": "S5-CONF-012", "split": "hidden", "test_size": 0.12},
    {"task_id": "S5-CONF-022", "split": "hidden", "test_size": 0.22},
    {"task_id": "S5-CONF-028", "split": "hidden", "test_size": 0.28},
    {"task_id": "S5-CONF-038", "split": "hidden", "test_size": 0.38},
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def resolve_s5_seed_policy(ledger_path: Path, scope: str = SCOPE) -> Optional[Dict[str, Any]]:
    ledger = StepLedger.load(Path(ledger_path))
    episodes = {record.candidate.candidate_id: record for record in ledger.episodes}
    matches = []
    for lease in ledger.leases:
        if lease.effective_status() != "active" or lease.scope != scope:
            continue
        record = episodes.get(lease.candidate_id)
        if record is None or record.candidate.target != "experiment.run.seeds":
            continue
        try:
            patch = json.loads(record.candidate.patch)
        except (TypeError, ValueError):
            continue
        seeds = patch.get("seeds")
        if isinstance(seeds, int) and not isinstance(seeds, bool) and 1 <= seeds <= 10:
            matches.append({
                "lease_id": lease.lease_id,
                "episode_id": record.episode_id,
                "candidate_id": lease.candidate_id,
                "seeds": seeds,
                "scope": lease.scope,
            })
    if not matches:
        return None
    if len({item["seeds"] for item in matches}) > 1:
        raise RSIPolicyError("conflicting active S5 seed leases")
    return matches[0]


def _evaluate(
    agent: RunAgent,
    seeds: int,
    split: str,
    output_dir: Path,
    dataset: str = "iris",
    tasks=TASKS,
    run_split: str = "demo",
) -> Dict[str, Any]:
    details = []
    means = []
    mins = []
    failed = 0
    metric_key = DATASET_METRIC[dataset]
    selected = [item for item in tasks if item["split"] == split]
    for task in selected:
        run = agent.execute(
            RunRequest(
                protocol_id="P-%s-seed-budget" % dataset,
                dataset=dataset,
                seeds=seeds,
                test_size=task["test_size"],
                run_id="RUN-%s-S%d" % (task["task_id"], seeds),
                split=run_split,
            ),
            output_dir / "runs" / ("%s-s%d" % (task["task_id"], seeds)),
        )
        capsule = run["capsule"]
        if capsule["status"] != "completed":
            failed += 1
            continue
        task_min = min(item[metric_key] for item in capsule["metrics_by_seed"])
        means.append(capsule["mean"])
        mins.append(task_min)
        details.append({
            "task_id": task["task_id"],
            "mean": capsule["mean"],
            "min": task_min,
            "capsule": run["paths"]["capsule"],
            "ea": run["paths"]["ea"],
        })
    mean_score = sum(means) / len(means) if means else 0.0
    min_score = min(mins) if mins else 0.0
    metrics = {
        "mean_score": mean_score,
        "min_score": min_score,
        "cost": seeds * len(selected),
        "failed_runs": failed,
    }
    if metric_key == "accuracy":
        metrics["mean_accuracy"] = mean_score
        metrics["min_accuracy"] = min_score
    else:
        metrics["mean_r2"] = mean_score
        metrics["min_r2"] = min_score
    receipt = output_dir / ("%s-%s-seeds%d.json" % (dataset, split, seeds))
    _write_json(receipt, {
        "fixture": False,
        "protocol": "P-%s-seed-budget" % dataset,
        "dataset": dataset,
        "metric": metric_key,
        "seeds": seeds,
        "split": split,
        "metrics": metrics,
        "tasks": details,
        "note": "Local %s protocol validation; not thesis scientific evidence." % dataset,
    })
    return {"split": split, "metrics": metrics, "receipt": receipt, "n": len(details)}


def _evidence(result: Dict[str, Any], output_dir: Path) -> EvalEvidence:
    receipt_path = Path(result["receipt"])
    return EvalEvidence(
        split=result["split"],
        status="passed",
        artifact_ref=str(receipt_path.relative_to(output_dir.parent)),
        metrics=result["metrics"],
        n=result["n"],
        simulation=False,
        claim_eligible=False,
        evaluator="deterministic-s5",
        artifact_sha256=(
            hashlib.sha256(receipt_path.read_bytes()).hexdigest()
            if receipt_path.is_file() else ""
        ),
        task_pack_sha256=TASK_PACK_SHA,
        evaluated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        note="S5 seed-budget protocol-validation metric; not a research capability claim",
    )


def run_s5_trial(
    ledger_path: Path,
    output_dir: Path,
    human_approve: bool = False,
    dataset: str = "iris",
) -> Dict[str, Any]:
    if dataset not in DATASETS:
        raise ValueError("dataset must be one of %s" % (DATASETS,))
    scope = "S5/demo/%s" % dataset
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    agent = RunAgent(SpecStore().load("run"))
    baseline = {
        split: _evaluate(agent, BASELINE_SEEDS, split, output_dir, dataset=dataset)
        for split in SPLITS
    }
    base = {split: baseline[split]["metrics"] for split in SPLITS}
    baseline_public = base["public"]
    ledger = StepLedger.load(Path(ledger_path))
    controller = RSIController(ledger)
    reports: List[Dict[str, Any]] = []
    finalists: List[Dict[str, Any]] = []
    metric_label = "R2" if dataset == "chemlab" else "accuracy"

    for seeds in CANDIDATE_SEEDS:
        predicted_cost_delta = -float(base["hidden"]["cost"]) * (BASELINE_SEEDS - seeds) / BASELINE_SEEDS
        dry_run = output_dir / ("dry-run-seeds%d.json" % seeds)
        _write_json(dry_run, {
            "fixture": False,
            "patch": {"seeds": seeds},
            "schema_check": "1 <= seeds <= 10; no claim/gate mutation",
        })
        episode = controller.propose(
            Candidate(
                kind="process",
                target="experiment.run.seeds",
                patch=json.dumps({"seeds": seeds}),
                rationale="reduce seed budget while preserving %s protocol %s" % (dataset, metric_label),
                predicted_effect="lower run cost with non-inferior mean %s" % metric_label,
                scope=scope,
                candidate_id="S5:seed-budget-%d" % seeds,
                predicted_metrics={
                    "hidden_mean_delta": 0.0,
                    "hidden_cost_delta": predicted_cost_delta,
                },
            ),
            observation="S5 seed-budget trial on %s protocol" % dataset,
            dry_run_ref=str(dry_run),
            simulation=False,
        )
        public = _evidence(_evaluate(agent, seeds, "public", output_dir, dataset=dataset), output_dir)
        controller.evaluate(episode.episode_id, public)
        public_ok = (
            public.metrics["mean_score"] >= baseline_public["mean_score"] - MEAN_TOLERANCE
            and public.metrics["min_score"] >= baseline_public["min_score"] - MIN_TOLERANCE
            and public.metrics["failed_runs"] == 0
        )
        report = {"seeds": seeds, "episode_id": episode.episode_id, "public": public.metrics, "public_ok": public_ok}
        if not public_ok:
            controller.reject(episode.episode_id, "S5 public prefilter: %s loss or failed run" % metric_label)
            report.update({"cheaper": False, "would_accept": False, "decision": "rejected"})
            reports.append(report)
            continue
        finalists.append({"seeds": seeds, "episode": episode, "public": public, "report": report})
        reports.append(report)

    chosen = None
    finalists.sort(key=lambda item: (item["seeds"], item["report"]["episode_id"]))
    evaluated = set()
    for finalist in finalists[:MAX_FINALISTS]:
        seeds = finalist["seeds"]
        episode = finalist["episode"]
        report = finalist["report"]
        hidden = _evidence(_evaluate(agent, seeds, "hidden", output_dir, dataset=dataset), output_dir)
        near = _evidence(_evaluate(agent, seeds, "near_ood", output_dir, dataset=dataset), output_dir)
        regression = _evidence(_evaluate(agent, seeds, "regression", output_dir, dataset=dataset), output_dir)
        controller.evaluate(episode.episode_id, finalist["public"], hidden, near, regression)
        non_inferior = True
        for split, ev in (("hidden", hidden), ("near_ood", near), ("regression", regression)):
            if ev.metrics["mean_score"] < base[split]["mean_score"] - MEAN_TOLERANCE:
                non_inferior = False
            if ev.metrics["min_score"] < base[split]["min_score"] - MIN_TOLERANCE:
                non_inferior = False
            if ev.metrics["failed_runs"] != 0:
                non_inferior = False
        cheaper = hidden.metrics["cost"] < base["hidden"]["cost"]
        report.update({
            "hidden": hidden.metrics, "near_ood": near.metrics, "regression": regression.metrics,
            "non_inferior": non_inferior, "cheaper": cheaper,
            "would_accept": non_inferior and cheaper,
        })
        evaluated.add(episode.episode_id)
        if report["would_accept"]:
            report["decision"] = "pending_human"
            chosen = report
            break
        controller.reject(episode.episode_id, "S5 hidden/near-OOD/regression gate failed")
        report["decision"] = "rejected"
    for finalist in finalists:
        if finalist["episode"].episode_id in evaluated:
            continue
        controller.reject(finalist["episode"].episode_id, "S5 finalist budget exhausted; gates not read")
        finalist["report"].update({
            "would_accept": False, "decision": "rejected", "hidden_held_out": True,
        })

    if human_approve and chosen:
        record = controller.ledger.find(chosen["episode_id"])
        controller.admit(
            record.episode_id, record.public_eval, record.hidden_eval,
            "human-approved S5 seed-budget change", scope, 30,
            near_ood_eval=record.near_ood_eval, regression_eval=record.regression_eval,
            strict=True, approved_by="human-cli",
        )
        chosen["decision"] = "approved"
        for report in reports:
            if report["episode_id"] != chosen["episode_id"]:
                existing = controller.ledger.find(report["episode_id"])
                if existing.decision == "pending_human":
                    controller.reject(report["episode_id"], "S5 not selected; dominated by seeds=%d" % chosen["seeds"])
                report["decision"] = controller.ledger.find(report["episode_id"]).decision
    elif human_approve:
        for report in reports:
            existing = controller.ledger.find(report["episode_id"])
            if existing.decision == "pending_human":
                controller.reject(report["episode_id"], "S5 gate failed")
                report["decision"] = "rejected"
    else:
        for report in reports:
            report["decision"] = controller.ledger.find(report["episode_id"]).decision

    audit = None
    if chosen:
        hidden = chosen["hidden"]
        audit = {
            "predicted": "lower run cost with non-inferior mean %s" % metric_label,
            "actual": {
                "hidden_mean_delta": hidden["mean_score"] - base["hidden"]["mean_score"],
                "hidden_min_delta": hidden["min_score"] - base["hidden"]["min_score"],
                "hidden_cost_delta": hidden["cost"] - base["hidden"]["cost"],
            },
            "fixture": False,
        }
        controller.record_actuals(chosen["episode_id"], audit["actual"], "S5 prediction audit")
    result = {
        "fixture": False,
        "dataset": dataset,
        "note": "S5 %s protocol validation; not thesis scientific evidence." % dataset,
        "baseline": base,
        "candidates": reports,
        "chosen": chosen["seeds"] if chosen else None,
        "decision": chosen["decision"] if chosen else "no_candidate",
        "prediction_audit": audit,
        "rsi_report": controller.report(),
    }
    _write_json(output_dir / "s5-trial.json", result)
    return result


def run_s5_confirmation(
    ledger_path: Path,
    output_dir: Path,
    dataset: str = "iris",
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    """Post-lease sealed S5 check on new protocol instances."""
    if dataset not in DATASETS:
        raise ValueError("dataset must be one of %s" % (DATASETS,))
    scope = scope or ("S5/demo/%s" % dataset)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt = output_dir / "s5-confirmation.json"
    active = resolve_s5_seed_policy(Path(ledger_path), scope)
    if active is None:
        result = {
            "fixture": False,
            "sealed": True,
            "used_for_admission": False,
            "status": "no_active_lease",
            "passed": False,
            "scope": scope,
            "note": "No active S5 seed lease for this scope; confirmation was not run.",
        }
        _write_json(receipt, result)
        return result
    agent = RunAgent(SpecStore().load("run"))
    run_split = "holdout" if dataset == "chemlab" else "demo"
    baseline = _evaluate(
        agent, BASELINE_SEEDS, "hidden", output_dir,
        dataset=dataset, tasks=CONFIRM_TASKS, run_split=run_split,
    )
    candidate = _evaluate(
        agent, active["seeds"], "hidden", output_dir,
        dataset=dataset, tasks=CONFIRM_TASKS, run_split=run_split,
    )
    delta = {
        "mean_score": candidate["metrics"]["mean_score"] - baseline["metrics"]["mean_score"],
        "min_score": candidate["metrics"]["min_score"] - baseline["metrics"]["min_score"],
        "cost": candidate["metrics"]["cost"] - baseline["metrics"]["cost"],
        "failed_runs": candidate["metrics"]["failed_runs"],
    }
    passed = (
        delta["mean_score"] >= -MEAN_TOLERANCE
        and delta["min_score"] >= -MIN_TOLERANCE
        and delta["failed_runs"] == 0
    )
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
        "dataset": dataset,
        "split": run_split,
        "note": (
            "Post-lease S5 sealed confirmation on 42 held-out reactions; protocol validation, not thesis evidence."
            if dataset == "chemlab" else
            "Post-lease S5 sealed confirmation; %s protocol validation, not thesis evidence." % dataset
        ),
    }
    controller = RSIController(StepLedger.load(Path(ledger_path)))
    result["ledger_confirmation"] = controller.record_confirmation(
        active["episode_id"], result, "S5 sealed confirmation recorded as audit only"
    )
    _write_json(receipt, result)
    return result

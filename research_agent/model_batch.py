"""Run several frozen-model proposals through the same governed evaluator."""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .adapters import LocalHFModel
from .real_eval import run_real_trial
from .rsi_proposer import FrozenModelProposer, ProposerError

ProposeFn = Callable[[str], Any]
EvaluateFn = Callable[[Path, Path, Path, bool], Dict[str, Any]]


def load_observations(path: Path) -> List[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    observations = data.get("observations") if isinstance(data, dict) else data
    if not isinstance(observations, list) or not observations:
        raise ValueError("observations must be a non-empty list")
    result = [str(item).strip() for item in observations]
    if any(not item for item in result):
        raise ValueError("observations must not be empty strings")
    return result


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def run_model_batch(
    model_path: Optional[Path],
    observations: List[str],
    output_dir: Path,
    ledger_root: Path,
    human_approve: bool = False,
    propose_fn: Optional[ProposeFn] = None,
    evaluate_fn: Optional[EvaluateFn] = None,
    repair_attempts: int = 0,
) -> Dict[str, Any]:
    output_dir = Path(output_dir)
    ledger_root = Path(ledger_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_root.mkdir(parents=True, exist_ok=True)
    proposer = None
    if propose_fn is None:
        if model_path is None:
            raise ValueError("model_path is required when propose_fn is omitted")
        proposer = FrozenModelProposer(LocalHFModel(Path(model_path)))
        if repair_attempts > 0:
            propose_fn = lambda observation: proposer.propose_with_repair(
                observation, repair_attempts=repair_attempts
            )
        else:
            propose_fn = proposer.propose
    evaluate = evaluate_fn or (
        lambda candidate, ledger, out, approve: run_real_trial(
            ledger, out, candidate_path=candidate, human_approve=approve
        )
    )
    results = []
    for index, observation in enumerate(observations):
        item: Dict[str, Any] = {"index": index, "observation": observation}
        try:
            proposed = propose_fn(observation)
            if isinstance(proposed, dict) and "candidate" in proposed:
                candidate = proposed["candidate"]
                item["proposal_audit"] = {
                    key: value for key, value in proposed.items() if key != "candidate"
                }
            else:
                candidate = proposed
            candidate_path = output_dir / ("candidate-%02d.json" % index)
            _write_json(candidate_path, candidate if isinstance(candidate, dict) else candidate.__dict__)
            trial = evaluate(candidate_path, ledger_root / ("ledger-%02d.json" % index), output_dir / ("trial-%02d" % index), human_approve)
            rejected = [c for c in trial.get("candidates", []) if c.get("decision") == "rejected"]
            item.update({
                "candidate": str(candidate_path),
                "decision": trial.get("decision"),
                "chosen": trial.get("chosen"),
                "would_accept": trial.get("would_accept"),
                "gate_failures": [
                    {
                        "policy": c.get("policy"),
                        "near_ood": c.get("near_ood"),
                        "regression": c.get("regression"),
                    }
                    for c in rejected
                ],
                "capability_claims": (trial.get("rsi_report") or {}).get("capability_claims", []),
            })
        except (ProposerError, ValueError, OSError, RuntimeError) as exc:
            item["error"] = type(exc).__name__ + ": " + str(exc)
        results.append(item)
    report = {
        "fixture": False,
        "note": "Prompt-stability audit for frozen-model proposals; not RSI evidence.",
        "observations": len(observations),
        "eligible": sum(1 for item in results if item.get("chosen")),
        "rejected": sum(1 for item in results if item.get("decision") == "no_candidate"),
        "errors": sum(1 for item in results if item.get("error")),
        "repair_attempts": repair_attempts,
        "repaired": sum(
            1 for item in results if (item.get("proposal_audit") or {}).get("repaired")
        ),
        "results": results,
    }
    _write_json(output_dir / "model-batch.json", report)
    return report

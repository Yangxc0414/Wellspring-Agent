"""S5 run contract and artifact allowlist check.

The contract binds a completed RunCapsule to the frozen protocol/dataset/seeds/
metric and an allowlist of run artifacts. It is derived after the run from the
frozen inputs; it does not execute a run or replace EA/claim gates.
"""

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

RUN_CONTRACT_SCHEMA = "run-contract-0.1"
RUN_CHECK_SCHEMA = "run-contract-check-0.1"
ALLOWED_ARTIFACTS = ("run-capsule.json", "ea.json", "metrics.json", "claim-draft.json")
BOUNDARY = (
    "contract/allowlist audit only; min_delta is not evaluated without a "
    "baseline metric; it does not create claims, EA or closure decisions"
)


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_run_contract(
    protocol: Optional[Dict[str, Any]],
    design: Optional[Dict[str, Any]],
    run_module: Dict[str, Any],
) -> Dict[str, Any]:
    capsule = run_module.get("capsule") or {}
    protocol = protocol or {}
    design = design or {}
    contract = {
        "schema_version": RUN_CONTRACT_SCHEMA,
        "protocol_id": str(protocol.get("protocol_id") or capsule.get("protocol_id") or ""),
        "design_sha256": str(protocol.get("design_sha256") or ""),
        "dataset_id": str(capsule.get("dataset_id") or ""),
        "seeds": list(capsule.get("seeds") or []),
        "metric_name": str(capsule.get("metric_name") or ""),
        "min_delta": float(protocol.get("min_delta") or 0.0),
        "allowed_artifacts": list(ALLOWED_ARTIFACTS),
        "created_at": _now(),
        "boundary": BOUNDARY,
    }
    contract["contract_sha256"] = _sha256(contract)
    return contract


def verify_run_contract(
    contract: Dict[str, Any],
    run_module: Dict[str, Any],
    run_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    capsule = run_module.get("capsule") or {}
    evidence = run_module.get("evidence") or {}
    checks: List[Dict[str, str]] = []
    blockers: List[str] = []
    warnings: List[str] = []

    def add(check_id: str, ok: bool, detail: str, blocker: bool = True) -> None:
        checks.append(
            {"id": check_id, "status": "pass" if ok else "fail", "detail": detail}
        )
        if not ok:
            (blockers if blocker else warnings).append("%s: %s" % (check_id, detail))

    add("capsule.completed", capsule.get("status") == "completed", "status=%s" % capsule.get("status"))
    add(
        "identity.protocol",
        not contract.get("protocol_id")
        or str(capsule.get("protocol_id") or "") == str(contract.get("protocol_id")),
        "capsule=%s contract=%s" % (capsule.get("protocol_id"), contract.get("protocol_id")),
    )
    add(
        "identity.dataset",
        str(capsule.get("dataset_id") or "") == str(contract.get("dataset_id") or ""),
        "capsule=%s contract=%s" % (capsule.get("dataset_id"), contract.get("dataset_id")),
    )
    add(
        "identity.seeds",
        [int(item) for item in (capsule.get("seeds") or [])]
        == [int(item) for item in (contract.get("seeds") or [])],
        "capsule=%s contract=%s" % (capsule.get("seeds"), contract.get("seeds")),
    )
    add(
        "identity.metric",
        str(capsule.get("metric_name") or "") == str(contract.get("metric_name") or ""),
        "capsule=%s contract=%s" % (capsule.get("metric_name"), contract.get("metric_name")),
    )
    finite = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in (capsule.get("mean"), capsule.get("std"))
    )
    add("metrics.finite", finite, "mean=%s std=%s" % (capsule.get("mean"), capsule.get("std")))
    evidence_path = Path(str(evidence.get("path") or ""))
    add(
        "evidence.present",
        evidence_path.is_file(),
        "evidence path=%s" % (evidence_path or "missing"),
    )
    if evidence_path.is_file() and evidence.get("sha256"):
        actual = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        add(
            "evidence.hash",
            actual == str(evidence.get("sha256")),
            "expected=%s actual=%s" % (evidence.get("sha256"), actual),
        )
    if run_dir is not None:
        run_dir = Path(run_dir)
        allowed = set(contract.get("allowed_artifacts") or ALLOWED_ARTIFACTS)
        present = {path.name for path in run_dir.rglob("*") if path.is_file()} if run_dir.is_dir() else set()
        required = {"run-capsule.json", "ea.json", "metrics.json"}
        missing = sorted(required - present)
        add("artifacts.required", not missing, "missing=%s" % missing)
        unexpected = sorted(
            name for name in present
            if name not in allowed and name not in ("run-contract.json", "run-contract-check.json")
        )
        if unexpected:
            warnings.append("artifacts.unexpected: " + ", ".join(unexpected[:10]))
    metric = str(contract.get("metric_name") or capsule.get("metric_name") or "")
    metrics_by_seed = capsule.get("metrics_by_seed") or []
    delta_values: List[float] = []
    for item in metrics_by_seed:
        if not isinstance(item, dict):
            continue
        value = item.get("delta_" + metric)
        if value is None and metric and item.get(metric) is not None and item.get("baseline_" + metric) is not None:
            value = float(item.get(metric)) - float(item.get("baseline_" + metric))
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
            delta_values.append(float(value))
    if not delta_values:
        add(
            "min_delta",
            False,
            "not_verifiable: no paired baseline metrics for metric=%s" % (metric or "unknown"),
            blocker=False,
        )
    else:
        observed = sum(delta_values) / len(delta_values)
        required = float(contract.get("min_delta") or 0.0)
        if required > 0:
            add(
                "min_delta",
                observed >= required,
                "observed=%.6f required=%.6f across %d seeds" % (observed, required, len(delta_values)),
                blocker=True,
            )
        else:
            add(
                "min_delta",
                observed > 0,
                "observed=%.6f across %d seeds; no preregistered min_delta" % (observed, len(delta_values)),
                blocker=False,
            )
    status = "blocked" if blockers else ("attention" if warnings else "pass")
    return {
        "schema_version": RUN_CHECK_SCHEMA,
        "status": status,
        "contract_sha256": contract.get("contract_sha256", ""),
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "boundary": BOUNDARY,
    }

"""Explicit local execution and evidence ingestion for generated experiments.

Only the local CLI calls the execution functions. MCP/HTTP never execute
training. The generated package writes a local receipt; this module verifies
hashes and turns it into ``experiment-evidence.json``. A human may then sign a
claim in the CLI. No EA, gate or signature is created automatically.
"""

import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import read_json, write_json_atomic

APPROVAL_SCHEMA = "experiment-approval-0.1"
EXECUTION_SCHEMA = "experiment-execution-0.1"
EVIDENCE_SCHEMA = "experiment-evidence-0.1"
CLAIM_SCHEMA = "experiment-claim-0.1"
ENV_ALLOWLIST = (
    "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "COMSPEC", "PYTHONPATH",
    "PYTHONUSERBASE", "LANG", "LC_ALL", "PYTHONIOENCODING", "PYTHONUTF8",
)


class ExperimentExecutionError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _package(project: Path, experiment_id: str) -> Path:
    root = Path(project).resolve() / "experiments" / str(experiment_id).strip()
    if not root.is_dir():
        raise ExperimentExecutionError("experiment package does not exist: " + str(root))
    return root


def _load_json(path: Path) -> Any:
    try:
        return read_json(path)
    except Exception:
        return None


def _spec_and_hashes(root: Path, project: Path) -> Dict[str, Any]:
    spec = _load_json(root / "experiment-spec.json")
    manifest = _load_json(root / "code-manifest.json")
    if not isinstance(spec, dict) or not isinstance(manifest, dict):
        raise ExperimentExecutionError("experiment-spec.json or code-manifest.json is missing")
    data_path = (Path(project).resolve() / str(spec.get("data", {}).get("path") or "")).resolve()
    if not data_path.is_file():
        raise ExperimentExecutionError("data table is missing: " + str(data_path))
    return {
        "spec": spec,
        "manifest": manifest,
        "data_path": data_path,
        "spec_sha256": _sha256_file(root / "experiment-spec.json"),
        "code_sha256": _sha256_file(root / "run_experiment.py"),
        "data_sha256": _sha256_file(data_path),
    }


def preflight_experiment(
    project: Path,
    experiment_id: str,
    *,
    python: str = "",
    timeout_sec: int = 60,
) -> Dict[str, Any]:
    """Validate a generated package with --dry-run; never trains or writes evidence."""
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    state = _spec_and_hashes(root, project)
    expected_data = str((state["spec"].get("data") or {}).get("sha256") or "")
    if expected_data and state["data_sha256"] != expected_data:
        raise ExperimentExecutionError("data table changed after package generation")
    for item in state["manifest"].get("files") or []:
        path = root / str(item.get("name") or "")
        if not path.is_file() or _sha256_file(path) != str(item.get("sha256") or ""):
            raise ExperimentExecutionError(
                "code manifest hash mismatch: " + str(item.get("name") or "unknown")
            )
    timeout = max(10, min(int(timeout_sec or 60), 300))
    python_bin = str(python or sys.executable)
    if not Path(python_bin).exists() and not python_bin.lower().endswith(".exe"):
        raise ExperimentExecutionError("python executable not found: " + python_bin)
    command = [python_bin, "run_experiment.py", "--dry-run"]
    env = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        status = "passed" if completed.returncode == 0 else "failed"
        stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as exc:
        status = "failed"
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        code = -1
    duration = round(time.time() - started, 3)
    (root / "preflight.stdout.log").write_text(stdout, encoding="utf-8")
    (root / "preflight.stderr.log").write_text(stderr, encoding="utf-8")
    result = {
        "schema_version": "experiment-preflight-0.1",
        "experiment_id": experiment_id,
        "status": status,
        "created_at": _now(),
        "command": command,
        "cwd": str(root),
        "duration_sec": duration,
        "returncode": code,
        "data_sha256": state["data_sha256"],
        "spec_sha256": state["spec_sha256"],
        "code_sha256": state["code_sha256"],
        "stdout": "preflight.stdout.log",
        "stderr": "preflight.stderr.log",
        "boundary": (
            "Preflight only: dry-run validates data/schema and imports; no model is "
            "trained, no execution/evidence/claim is created, and no human gate is signed."
        ),
    }
    write_json_atomic(root / "preflight.json", result)
    return result


def approve_experiment(
    project: Path,
    experiment_id: str,
    human_reason: str,
    *,
    timeout_sec: int = 7200,
    ridge_alpha: Optional[float] = None,
) -> Dict[str, Any]:
    if not str(human_reason or "").strip():
        raise ExperimentExecutionError("human_reason is required")
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    state = _spec_and_hashes(root, project)
    spec = state["spec"]
    if ridge_alpha is not None:
        if (
            not isinstance(ridge_alpha, (int, float))
            or isinstance(ridge_alpha, bool)
            or not math.isfinite(float(ridge_alpha))
            or float(ridge_alpha) <= 0
        ):
            raise ExperimentExecutionError("ridge_alpha must be a finite positive number")
        if "ridge" not in ((spec.get("design") or {}).get("methods") or []):
            raise ExperimentExecutionError("ridge_alpha requires the ridge method")
        ridge_alpha = float(ridge_alpha)
    for item in state["manifest"].get("files") or []:
        path = root / str(item.get("name") or "")
        if not path.is_file() or _sha256_file(path) != str(item.get("sha256") or ""):
            raise ExperimentExecutionError(
                "code manifest hash mismatch: " + str(item.get("name") or "unknown")
            )
    approval = {
        "schema_version": APPROVAL_SCHEMA,
        "experiment_id": experiment_id,
        "approved_at": _now(),
        "human_reason": str(human_reason).strip()[:1000],
        "timeout_sec": max(10, min(int(timeout_sec), 24 * 3600)),
        "command": (
            [sys.executable, "run_experiment.py"]
            + (["--ridge-alpha", str(ridge_alpha)] if ridge_alpha is not None else [])
            + ["--out", "outputs"]
        ),
        "cwd": str(root),
        "ridge_alpha": ridge_alpha,
        "data_sha256": state["data_sha256"],
        "spec_sha256": state["spec_sha256"],
        "code_sha256": state["code_sha256"],
        "design_status": (spec.get("design") or {}).get("status"),
        "boundary": "Human approval for local execution only; not a Claim, EA or gate.",
    }
    write_json_atomic(root / "execution-approval.json", approval)
    return approval


def execute_experiment(
    project: Path,
    experiment_id: str,
    *,
    allow_execute: bool = False,
    python: str = "",
    timeout_sec: int = 0,
    dry_run: bool = False,
    ridge_alpha: Optional[float] = None,
) -> Dict[str, Any]:
    if not allow_execute:
        raise ExperimentExecutionError("execution requires explicit --allow-execute")
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    approval = _load_json(root / "execution-approval.json")
    if not isinstance(approval, dict) or approval.get("schema_version") != APPROVAL_SCHEMA:
        raise ExperimentExecutionError("execution-approval.json is missing; run `experiment approve` first")
    state = _spec_and_hashes(root, project)
    for key in ("data_sha256", "spec_sha256", "code_sha256"):
        if str(approval.get(key)) != str(state[key]):
            raise ExperimentExecutionError(
                "%s changed after approval; run `experiment approve` again" % key
            )
    approved_alpha = approval.get("ridge_alpha")
    if ridge_alpha is not None and approved_alpha != ridge_alpha:
        raise ExperimentExecutionError("ridge_alpha differs from the approved value")
    if ridge_alpha is None:
        ridge_alpha = approved_alpha
    timeout = int(timeout_sec or approval.get("timeout_sec") or 7200)
    timeout = max(10, min(timeout, 24 * 3600))
    python_bin = str(python or sys.executable)
    if not Path(python_bin).exists() and not python_bin.lower().endswith(".exe"):
        raise ExperimentExecutionError("python executable not found: " + python_bin)
    command = [python_bin, "run_experiment.py"]
    if ridge_alpha is not None:
        command.extend(["--ridge-alpha", str(ridge_alpha)])
    if dry_run:
        command.append("--dry-run")
    else:
        command.extend(["--out", "outputs"])
    env = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        status = "completed" if completed.returncode == 0 else "failed"
        stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        code = -1
    duration = round(time.time() - started, 3)
    (root / "execution.stdout.log").write_text(stdout, encoding="utf-8")
    (root / "execution.stderr.log").write_text(stderr, encoding="utf-8")
    execution = {
        "schema_version": EXECUTION_SCHEMA,
        "experiment_id": experiment_id,
        "status": status,
        "created_at": _now(),
        "command": command,
        "cwd": str(root),
        "dry_run": bool(dry_run),
        "duration_sec": duration,
        "returncode": code,
        "python": python_bin,
        "platform": platform.platform(),
        "seeds": (state["spec"].get("design") or {}).get("seeds"),
        "ridge_alpha": ridge_alpha,
        "data_sha256": state["data_sha256"],
        "spec_sha256": state["spec_sha256"],
        "code_sha256": state["code_sha256"],
        "stdout": "execution.stdout.log",
        "stderr": "execution.stderr.log",
        "artifacts": {},
        "boundary": "Local execution record only; not a RunCapsule, EA, Claim or gate.",
    }
    if not dry_run and status == "completed":
        for name in ("metrics.json", "predictions.csv", "run-receipt.json", "artifact-manifest.json"):
            path = root / "outputs" / name
            if path.is_file():
                execution["artifacts"][name] = {
                    "sha256": _sha256_file(path),
                    "bytes": path.stat().st_size,
                }
    write_json_atomic(root / "execution.json", execution)
    return execution


def ingest_experiment(project: Path, experiment_id: str) -> Dict[str, Any]:
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    state = _spec_and_hashes(root, project)
    spec = state["spec"]
    execution = _load_json(root / "execution.json")
    checks: List[Dict[str, str]] = []
    blockers: List[str] = []

    def add(check_id: str, ok: bool, detail: str) -> None:
        checks.append({"id": check_id, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            blockers.append("%s: %s" % (check_id, detail))

    if not isinstance(execution, dict):
        raise ExperimentExecutionError("execution.json is missing; run `experiment run` first")
    add("execution.completed", execution.get("status") == "completed", str(execution.get("status")))
    add("execution.dry_run", not execution.get("dry_run"), "dry-run cannot become evidence")
    add("hash.data", execution.get("data_sha256") == state["data_sha256"], "data hash")
    add("hash.spec", execution.get("spec_sha256") == state["spec_sha256"], "spec hash")
    add("hash.code", execution.get("code_sha256") == state["code_sha256"], "code hash")
    receipt = _load_json(root / "outputs" / "run-receipt.json") or {}
    metrics_payload = _load_json(root / "outputs" / "metrics.json") or {}
    manifest = _load_json(root / "outputs" / "artifact-manifest.json") or {}
    add("receipt.schema", receipt.get("schema_version") == "local-experiment-receipt-0.1", "receipt schema")
    add("receipt.status", receipt.get("status") == "completed_local", str(receipt.get("status")))
    add("receipt.spec", receipt.get("spec_sha256") == state["spec_sha256"], "receipt spec hash")
    add("receipt.code", receipt.get("code_sha256") == state["code_sha256"], "receipt code hash")
    add("receipt.data", receipt.get("data_sha256") == state["data_sha256"], "receipt data hash")
    seeds = [int(item) for item in (spec.get("design") or {}).get("seeds") or []]
    add("receipt.seeds", [int(item) for item in receipt.get("seeds") or []] == seeds, "receipt seeds")
    cv_folds = int((spec.get("design") or {}).get("cv_folds") or 0)
    if cv_folds:
        add(
            "receipt.cv_folds",
            int(receipt.get("cv_folds") or 0) == cv_folds,
            "receipt cv folds",
        )
    approval = _load_json(root / "execution-approval.json") or {}
    approved_alpha = approval.get("ridge_alpha")
    if approved_alpha is not None:
        add(
            "receipt.ridge_alpha",
            receipt.get("ridge_alpha") == approved_alpha,
            "receipt ridge alpha",
        )
        add(
            "execution.ridge_alpha",
            execution.get("ridge_alpha") == approved_alpha,
            "execution ridge alpha",
        )
    for artifact in manifest.get("artifacts") or []:
        path = root / "outputs" / str(artifact.get("name") or "")
        if not path.is_file():
            add("artifact." + str(artifact.get("name")), False, "missing")
            continue
        add(
            "artifact." + str(artifact.get("name")),
            _sha256_file(path) == str(artifact.get("sha256") or ""),
            "artifact hash",
        )
    aggregate = receipt.get("metrics") or {}
    methods = (spec.get("design") or {}).get("methods") or []
    primary_method = methods[-1] if methods else ""
    primary_metric = (spec.get("design") or {}).get("metric") or ""
    primary = (aggregate.get(primary_method) or {}).get(primary_metric) or {}
    mean, std = primary.get("mean"), primary.get("std")
    finite = all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in (mean, std)
    )
    add("metrics.primary", finite, "primary method/metric missing")
    status = "verified" if not blockers else "blocked"
    evidence = {
        "schema_version": EVIDENCE_SCHEMA,
        "experiment_id": experiment_id,
        "run_id": spec.get("run_id"),
        "status": status,
        "created_at": _now(),
        "spec_sha256": state["spec_sha256"],
        "execution_sha256": _sha256_file(root / "execution.json"),
        "data_sha256": state["data_sha256"],
        "code_sha256": state["code_sha256"],
        "seeds": seeds,
        "cv_folds": cv_folds,
        "data_audit": spec.get("data_audit") or {},
        "ridge_alpha": approved_alpha,
        "primary_method": primary_method,
        "primary_metric": primary_metric,
        "mean": mean,
        "std": std,
        "metrics": metrics_payload,
        "comparison": receipt.get("comparison") or metrics_payload.get("comparison") or {},
        "results_table": (
            str(root / "outputs" / "results-table.md")
            if (root / "outputs" / "results-table.md").is_file()
            else ""
        ),
        "results_table_sha256": (
            _sha256_file(root / "outputs" / "results-table.md")
            if (root / "outputs" / "results-table.md").is_file()
            else ""
        ),
        "receipt": receipt,
        "checks": checks,
        "blockers": blockers,
        "scope": "local-experiment/" + experiment_id,
        "boundary": (
            "Verified local experiment evidence. Not a RunCapsule, EA, Claim or gate; "
            "human claim signature remains required."
        ),
    }
    write_json_atomic(root / "experiment-evidence.json", evidence)
    return evidence


def _parse_assertion(text: str, evidence: Dict[str, Any]) -> Dict[str, Any]:
    parts = [item.strip() for item in str(text or "").split(",") if item.strip()]
    values = {}
    for part in parts:
        if "=" in part:
            key, value = part.split("=", 1)
            values[key.strip().lower()] = value.strip()
    metric = values.get("metric") or evidence.get("primary_metric") or ""
    comparator = values.get("comparator") or ">="
    try:
        target = float(values.get("value", ""))
    except ValueError:
        raise ExperimentExecutionError("assertion value must be numeric")
    tolerance = float(values.get("tolerance", "0.01"))
    observed = evidence.get("mean")
    checks = {
        ">=": observed is not None and float(observed) >= target - tolerance,
        "<=": observed is not None and float(observed) <= target + tolerance,
        ">": observed is not None and float(observed) > target,
        "<": observed is not None and float(observed) < target,
        "==": observed is not None and abs(float(observed) - target) <= tolerance,
    }
    ok = bool(checks.get(comparator))
    return {
        "metric": metric,
        "comparator": comparator,
        "value": target,
        "tolerance": tolerance,
        "observed": observed,
        "status": "pass" if ok else "fail",
    }


def sign_experiment_claim(
    project: Path,
    experiment_id: str,
    statement: str,
    human_reason: str,
    assertions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if not str(statement or "").strip() or not str(human_reason or "").strip():
        raise ExperimentExecutionError("statement and human_reason are required")
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    evidence = _load_json(root / "experiment-evidence.json")
    if not isinstance(evidence, dict) or evidence.get("status") != "verified":
        raise ExperimentExecutionError("verified experiment-evidence.json is required before a claim")
    parsed = [_parse_assertion(item, evidence) for item in (assertions or [])]
    failed = [item for item in parsed if item.get("status") != "pass"]
    if failed:
        raise ExperimentExecutionError("claim assertion failed: " + json.dumps(failed, ensure_ascii=False))
    claim = {
        "schema_version": CLAIM_SCHEMA,
        "claim_id": "CLAIM-" + experiment_id,
        "experiment_id": experiment_id,
        "status": "supported",
        "statement": str(statement).strip()[:1000],
        "human_reason": str(human_reason).strip()[:1000],
        "signed_at": _now(),
        "assertions": parsed,
        "evidence_sha256": _sha256_file(root / "experiment-evidence.json"),
        "ridge_alpha": evidence.get("ridge_alpha"),
        "cv_folds": evidence.get("cv_folds"),
        "primary_method": evidence.get("primary_method"),
        "primary_metric": evidence.get("primary_metric"),
        "results_table_sha256": evidence.get("results_table_sha256") or "",
        "data_audit_status": (evidence.get("data_audit") or {}).get("status") or "",
        "scope": evidence.get("scope"),
        "boundary": "Human-signed local experiment claim; not a gate, closure or publication approval.",
    }
    write_json_atomic(root / "claim.json", claim)
    return claim


def experiment_status(project: Path, experiment_id: str) -> Dict[str, Any]:
    """Read-only lifecycle status for one generated experiment package."""
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    spec = _load_json(root / "experiment-spec.json") or {}
    if not spec or not (root / "run_experiment.py").is_file():
        return {
            "schema_version": "experiment-status-0.1",
            "closure_profile": "local_experiment",
            "experiment_id": experiment_id,
            "package": str(root),
            "stages": {"spec": "missing" if not spec else "ready", "code": "missing"},
            "next_action": "fix_or_regenerate_experiment_package",
            "boundary": "Read-only local experiment status; it never executes, signs or changes evidence.",
        }
    manifest = _load_json(root / "code-manifest.json") or {}
    approval = _load_json(root / "execution-approval.json") or {}
    preflight = _load_json(root / "preflight.json") or {}
    execution = _load_json(root / "execution.json") or {}
    evidence = _load_json(root / "experiment-evidence.json") or {}
    claim = _load_json(root / "claim.json") or {}
    closure = _load_json(root / "experiment-closure" / "closure-report.json") or {}
    signature = _load_json(root / "experiment-closure" / "signature.json") or {}
    data_path = project / str((spec.get("data") or {}).get("path") or "")
    data_ok = data_path.is_file() and _sha256_file(data_path) == str((spec.get("data") or {}).get("sha256") or "")
    code_ok = True
    for item in manifest.get("files") or []:
        path = root / str(item.get("name") or "")
        if not path.is_file() or _sha256_file(path) != str(item.get("sha256") or ""):
            code_ok = False
            break
    approval_ok = bool(approval) and all(
        approval.get(key) == value
        for key, value in (
            ("data_sha256", (spec.get("data") or {}).get("sha256")),
            ("spec_sha256", _sha256_file(root / "experiment-spec.json")),
            ("code_sha256", _sha256_file(root / "run_experiment.py")),
        )
    )
    execution_ok = (
        execution.get("status") == "completed"
        and not execution.get("dry_run")
        and execution.get("data_sha256") == (spec.get("data") or {}).get("sha256")
        and execution.get("spec_sha256") == _sha256_file(root / "experiment-spec.json")
        and execution.get("code_sha256") == _sha256_file(root / "run_experiment.py")
    )
    evidence_ok = (
        evidence.get("status") == "verified"
        and evidence.get("execution_sha256") == _sha256_file(root / "execution.json")
    )
    claim_ok = (
        claim.get("status") == "supported"
        and claim.get("evidence_sha256") == _sha256_file(root / "experiment-evidence.json")
    )
    run_id = str(spec.get("run_id") or "")
    panel_path = project / "runs" / run_id / "support-panel.json" if run_id else None
    panel = _load_json(panel_path) if panel_path is not None and panel_path.is_file() else {}
    panel_required = bool(panel_path is not None and panel_path.is_file())
    panel_status = str(panel.get("status") or ("missing" if panel_required else "not_required"))
    panel_ready = not panel_required or panel_status in ("ready", "not_applicable")
    closure_panel = closure.get("support_panel") or {}
    panel_reported = not panel_required or (
        bool(closure_panel.get("path")) and closure_panel.get("status") == panel_status
    )
    closure_ok = (
        closure.get("status") == "ready_for_human_signature"
        and bool(claim_ok)
        and panel_ready
        and panel_reported
    )
    from .experiment_figures import result_figure_manifest_path, verify_result_figure

    figure_path = result_figure_manifest_path(project, experiment_id)
    if figure_path.is_file():
        figure_status = str(verify_result_figure(figure_path, project=project).get("status") or "stale")
    else:
        figure_status = "missing"
    stages = {
        "spec": "ready" if spec else "missing",
        "data": "fresh" if data_ok else "stale_or_missing",
        "code": "fresh" if code_ok else "stale_or_missing",
        "preflight": str(preflight.get("status") or "missing"),
        "approval": "fresh" if approval_ok else ("stale" if approval else "missing"),
        "execution": "completed" if execution_ok else str(execution.get("status") or "missing"),
        "evidence": "verified" if evidence_ok else str(evidence.get("status") or "missing"),
        "claim": "signed" if claim_ok else ("present_unverified" if claim else "missing"),
        "support_panel": panel_status,
        "figure": "fresh" if figure_status == "clean" else figure_status,
        "closure": (
            "ready_for_signature"
            if closure_ok
            else "support_panel_pending"
            if panel_required and not panel_ready
            else str(closure.get("status") or "missing")
        ),
        "signature": "signed" if signature else "missing",
        "lineage": "present" if (root / "experiment-lineage" / "lineage.json").is_file() else "missing",
    }
    if not data_ok or not code_ok:
        action = "fix_or_regenerate_experiment_package"
    elif not approval_ok:
        action = "experiment approve"
    elif not execution_ok:
        action = "experiment run --allow-execute"
    elif not evidence_ok:
        action = "experiment ingest"
    elif not claim_ok:
        action = "experiment claim (human only)"
    elif panel_required and not panel_ready:
        action = "support adjudication (human only)"
    elif not closure_ok:
        action = "experiment closure"
    elif not signature:
        action = "experiment sign (human only)"
    else:
        action = "complete"
    try:
        sweep = sweep_status(project, experiment_id)
    except ExperimentExecutionError:
        sweep = {"stages": {"sweep_spec": "missing"}, "next_action": "regenerate with alpha_grid"}
    comparison = {
        str(name): {
            "mean_diff": item.get("mean_diff"),
            "ci95_low": item.get("ci95_low"),
            "ci95_high": item.get("ci95_high"),
            "bootstrap_ci95_low": item.get("bootstrap_ci95_low"),
            "bootstrap_ci95_high": item.get("bootstrap_ci95_high"),
            "wins": item.get("wins"),
            "sign_test_p": item.get("sign_test_p"),
            "n": item.get("n"),
        }
        for name, item in (evidence.get("comparison") or {}).items()
        if isinstance(item, dict)
    }
    data_audit = spec.get("data_audit") or {}
    evidence_summary = {
        "status": evidence.get("status") or "missing",
        "mean": evidence.get("mean"),
        "std": evidence.get("std"),
        "cv_folds": evidence.get("cv_folds")
        or (spec.get("design") or {}).get("cv_folds")
        or 0,
        "ridge_alpha": evidence.get("ridge_alpha"),
        "comparison": comparison,
        "results_table": evidence.get("results_table") or "",
        "data_audit_status": data_audit.get("status") or "missing",
        "data_audit_warnings": len(data_audit.get("warnings") or []),
    }
    return {
        "schema_version": "experiment-status-0.1",
        "closure_profile": "local_experiment",
        "experiment_id": experiment_id,
        "package": str(root),
        "design_status": (spec.get("design") or {}).get("status"),
        "stages": stages,
        "support_panel": {
            "status": panel_status,
            "pending_human": len(panel.get("pending_human") or []),
            "path": str(panel_path) if panel_required else "",
        },
        "sweep": sweep,
        "evidence_summary": evidence_summary,
        "next_action": action,
        "boundary": "Read-only local experiment status; it never executes, signs or changes evidence.",
    }


SWEEP_APPROVAL_SCHEMA = "experiment-sweep-approval-0.1"
SWEEP_EXECUTION_SCHEMA = "experiment-sweep-execution-0.1"
SWEEP_EVIDENCE_SCHEMA = "experiment-sweep-evidence-0.1"
SWEEP_BOUNDARY = (
    "Sweep lifecycle is exploratory: it is not a RunCapsule, EA, Claim or gate, "
    "and its results cannot be cited as a confirmed result until a single-config "
    "local run is ingested and a human signs a claim."
)


def _sweep_hashes(root: Path, project: Path) -> Dict[str, Any]:
    spec = _load_json(root / "experiment-spec.json")
    manifest = _load_json(root / "code-manifest.json")
    if not isinstance(spec, dict) or not isinstance(manifest, dict):
        raise ExperimentExecutionError("experiment-spec.json or code-manifest.json is missing")
    if not spec.get("sweep"):
        raise ExperimentExecutionError("experiment spec has no sweep plan; regenerate with alpha_grid")
    code_path = root / "run_sweep.py"
    if not code_path.is_file():
        raise ExperimentExecutionError("run_sweep.py is missing from the package")
    files = {str(item.get("name")): str(item.get("sha256")) for item in manifest.get("files") or []}
    if files.get("run_sweep.py") != _sha256_file(code_path):
        raise ExperimentExecutionError("sweep code is not hashed in code-manifest.json")
    data_path = (Path(project).resolve() / str((spec.get("data") or {}).get("path") or "")).resolve()
    if not data_path.is_file():
        raise ExperimentExecutionError("data table is missing: " + str(data_path))
    return {
        "spec": spec,
        "manifest": manifest,
        "data_path": data_path,
        "spec_sha256": _sha256_file(root / "experiment-spec.json"),
        "data_sha256": _sha256_file(data_path),
        "code_sha256": _sha256_file(code_path),
    }


def approve_sweep(
    project: Path,
    experiment_id: str,
    human_reason: str,
    *,
    timeout_sec: int = 7200,
) -> Dict[str, Any]:
    if not str(human_reason or "").strip():
        raise ExperimentExecutionError("human_reason is required")
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    state = _sweep_hashes(root, project)
    for item in state["manifest"].get("files") or []:
        path = root / str(item.get("name") or "")
        if not path.is_file() or _sha256_file(path) != str(item.get("sha256") or ""):
            raise ExperimentExecutionError(
                "code manifest hash mismatch: " + str(item.get("name") or "unknown")
            )
    approval = {
        "schema_version": SWEEP_APPROVAL_SCHEMA,
        "experiment_id": experiment_id,
        "approved_at": _now(),
        "human_reason": str(human_reason).strip()[:1000],
        "timeout_sec": max(10, min(int(timeout_sec), 24 * 3600)),
        "command": [sys.executable, "run_sweep.py", "--out", "outputs"],
        "cwd": str(root),
        "data_sha256": state["data_sha256"],
        "spec_sha256": state["spec_sha256"],
        "code_sha256": state["code_sha256"],
        "sweep": state["spec"].get("sweep"),
        "boundary": SWEEP_BOUNDARY,
    }
    write_json_atomic(root / "sweep-approval.json", approval)
    return approval


def execute_sweep(
    project: Path,
    experiment_id: str,
    *,
    allow_execute: bool = False,
    python: str = "",
    timeout_sec: int = 0,
    dry_run: bool = False,
) -> Dict[str, Any]:
    if not allow_execute:
        raise ExperimentExecutionError("sweep execution requires explicit --allow-execute")
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    approval = _load_json(root / "sweep-approval.json")
    if not isinstance(approval, dict) or approval.get("schema_version") != SWEEP_APPROVAL_SCHEMA:
        raise ExperimentExecutionError("sweep-approval.json is missing; run `experiment sweep-approve` first")
    state = _sweep_hashes(root, project)
    for key in ("data_sha256", "spec_sha256", "code_sha256"):
        if str(approval.get(key)) != str(state[key]):
            raise ExperimentExecutionError(
                "%s changed after sweep approval; approve again" % key
            )
    timeout = int(timeout_sec or approval.get("timeout_sec") or 7200)
    timeout = max(10, min(timeout, 24 * 3600))
    python_bin = str(python or sys.executable)
    if not Path(python_bin).exists() and not python_bin.lower().endswith(".exe"):
        raise ExperimentExecutionError("python executable not found: " + python_bin)
    command = [python_bin, "run_sweep.py"]
    if dry_run:
        command.append("--dry-run")
    else:
        command.extend(["--out", "outputs"])
    env = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    started = time.time()
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        status = "completed" if completed.returncode == 0 else "failed"
        stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        stdout = str(exc.stdout or "")
        stderr = str(exc.stderr or "")
        code = -1
    duration = round(time.time() - started, 3)
    (root / "sweep.stdout.log").write_text(stdout, encoding="utf-8")
    (root / "sweep.stderr.log").write_text(stderr, encoding="utf-8")
    execution = {
        "schema_version": SWEEP_EXECUTION_SCHEMA,
        "experiment_id": experiment_id,
        "status": status,
        "created_at": _now(),
        "command": command,
        "cwd": str(root),
        "dry_run": bool(dry_run),
        "duration_sec": duration,
        "returncode": code,
        "python": python_bin,
        "platform": platform.platform(),
        "data_sha256": state["data_sha256"],
        "spec_sha256": state["spec_sha256"],
        "code_sha256": state["code_sha256"],
        "stdout": "sweep.stdout.log",
        "stderr": "sweep.stderr.log",
        "artifacts": {},
        "boundary": SWEEP_BOUNDARY,
    }
    if not dry_run and status == "completed":
        for name in (
            "sweep-results.json",
            "sweep-receipt.json",
            "sweep-artifact-manifest.json",
        ):
            path = root / "outputs" / name
            if path.is_file():
                execution["artifacts"][name] = {
                    "sha256": _sha256_file(path),
                    "bytes": path.stat().st_size,
                }
    write_json_atomic(root / "sweep-execution.json", execution)
    return execution


def ingest_sweep(project: Path, experiment_id: str) -> Dict[str, Any]:
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    state = _sweep_hashes(root, project)
    execution = _load_json(root / "sweep-execution.json")
    checks: List[Dict[str, str]] = []
    blockers: List[str] = []

    def add(check_id: str, ok: bool, detail: str) -> None:
        checks.append({"id": check_id, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            blockers.append("%s: %s" % (check_id, detail))

    add(
        "execution.completed",
        isinstance(execution, dict) and execution.get("status") == "completed",
        str((execution or {}).get("status")),
    )
    add(
        "execution.not_dry_run",
        isinstance(execution, dict) and not execution.get("dry_run"),
        "dry-run cannot become sweep evidence",
    )
    for key in ("data_sha256", "spec_sha256", "code_sha256"):
        add(
            "execution." + key,
            isinstance(execution, dict) and execution.get(key) == state[key],
            "execution hash",
        )
    results_path = root / "outputs" / "sweep-results.json"
    receipt_path = root / "outputs" / "sweep-receipt.json"
    manifest_path = root / "outputs" / "sweep-artifact-manifest.json"
    results = _load_json(results_path)
    receipt = _load_json(receipt_path)
    artifact_manifest = _load_json(manifest_path)
    add("results.present", isinstance(results, dict), str(results_path))
    add("receipt.present", isinstance(receipt, dict), str(receipt_path))
    if isinstance(receipt, dict):
        add("receipt.data", receipt.get("data_sha256") == state["data_sha256"], "receipt data hash")
        add("receipt.spec", receipt.get("spec_sha256") == state["spec_sha256"], "receipt spec hash")
        add("receipt.code", receipt.get("code_sha256") == state["code_sha256"], "receipt code hash")
    if isinstance(results, dict):
        values = [str(value) for value in results.get("values") or []]
        best = str((results.get("selection") or {}).get("best_alpha"))
        add("results.best_alpha", best in values, "best_alpha=%s" % best)
        add("results.aggregate", bool(results.get("aggregate")), "aggregate is non-empty")
    if isinstance(artifact_manifest, dict):
        for item in artifact_manifest.get("artifacts") or []:
            path = root / "outputs" / str(item.get("name") or "")
            add(
                "artifact." + str(item.get("name")),
                path.is_file() and _sha256_file(path) == str(item.get("sha256") or ""),
                "sweep artifact hash",
            )
    status = "verified_exploratory" if not blockers else "blocked"
    evidence = {
        "schema_version": SWEEP_EVIDENCE_SCHEMA,
        "experiment_id": experiment_id,
        "status": status,
        "created_at": _now(),
        "data_sha256": state["data_sha256"],
        "spec_sha256": state["spec_sha256"],
        "code_sha256": state["code_sha256"],
        "parameter": (results or {}).get("parameter"),
        "values": (results or {}).get("values"),
        "seeds": (results or {}).get("seeds"),
        "cv_folds": (results or {}).get("cv_folds") or 0,
        "metric": (results or {}).get("metric"),
        "best_alpha": ((results or {}).get("selection") or {}).get("best_alpha"),
        "aggregate": (results or {}).get("aggregate"),
        "baseline": (results or {}).get("baseline"),
        "artifact_refs": [
            str(path)
            for path in (results_path, receipt_path, manifest_path)
            if path.is_file()
        ],
        "checks": checks,
        "blockers": blockers,
        "boundary": SWEEP_BOUNDARY,
    }
    write_json_atomic(root / "sweep-evidence.json", evidence)
    return evidence


def sweep_status(project: Path, experiment_id: str) -> Dict[str, Any]:
    project = Path(project).resolve()
    root = _package(project, experiment_id)
    spec = _load_json(root / "experiment-spec.json") or {}
    approval = _load_json(root / "sweep-approval.json") or {}
    execution = _load_json(root / "sweep-execution.json") or {}
    evidence = _load_json(root / "sweep-evidence.json") or {}
    stages = {
        "sweep_spec": "ready" if spec.get("sweep") else "missing",
        "sweep_approval": "present" if approval else "missing",
        "sweep_execution": str(execution.get("status") or "missing"),
        "sweep_evidence": str(evidence.get("status") or "missing"),
    }
    if stages["sweep_spec"] == "missing":
        action = "regenerate with alpha_grid"
    elif not approval:
        action = "experiment sweep-approve (human only)"
    elif execution.get("status") != "completed":
        action = "experiment sweep-run --allow-execute"
    elif evidence.get("status") != "verified_exploratory":
        action = "experiment sweep-ingest"
    else:
        action = "exploratory_only; run a single-config experiment and human claim for a confirmatory result"
    return {
        "schema_version": "experiment-sweep-status-0.1",
        "experiment_id": experiment_id,
        "package": str(root),
        "stages": stages,
        "best_alpha": evidence.get("best_alpha"),
        "next_action": action,
        "boundary": SWEEP_BOUNDARY,
    }

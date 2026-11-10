"""Governed local-command experiment execution (Codex-like, CLI-only).

Implements the ARCHITECTURE local-experiment target contract: a human registers a
command (argv), an optional environment prefix (conda/uv/docker), a cwd, expected
outputs and a timeout; approves it; then runs it with explicit --allow-execute.
The run is recorded with command, env fingerprint, git commit, stdout/stderr and
output hashes. MCP/HTTP never call these functions. The evidence is a local
execution record, not a RunCapsule/EA/Claim; a human must sign to use it as a result.
"""

import hashlib
import os
import platform
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .experiment_runner import ENV_ALLOWLIST, ExperimentExecutionError
from .storage import read_json, write_json_atomic

LOCAL_SPEC_SCHEMA = "local-exec-spec-0.1"
LOCAL_APPROVAL_SCHEMA = "local-exec-approval-0.1"
LOCAL_EXECUTION_SCHEMA = "local-exec-execution-0.1"
LOCAL_EVIDENCE_SCHEMA = "local-exec-evidence-0.1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_value(value: Any) -> str:
    import json
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return read_json(path)
    except Exception:
        return None


def _root(project: Path, experiment_id: str) -> Path:
    return Path(project).resolve() / "experiments" / str(experiment_id).strip()


def _argv(value: Any) -> List[str]:
    if isinstance(value, str):
        parts = shlex.split(value)
    elif isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        raise ExperimentExecutionError("command must be a string or argv list")
    if not parts:
        raise ExperimentExecutionError("command must not be empty")
    return parts


def init_local_experiment(
    project: Path,
    experiment_id: str,
    command: Any,
    *,
    cwd: str = "",
    env_prefix: Any = "",
    expected_outputs: Optional[List[str]] = None,
    timeout_sec: int = 3600,
) -> Dict[str, Any]:
    root = _root(project, experiment_id)
    root.mkdir(parents=True, exist_ok=True)
    prefix = _argv(env_prefix) if env_prefix else []
    outputs = [str(o) for o in (expected_outputs or [])]
    timeout = max(10, min(int(timeout_sec or 3600), 24 * 3600))
    spec = {
        "schema_version": LOCAL_SPEC_SCHEMA,
        "experiment_id": str(experiment_id),
        "command": _argv(command),
        "env_prefix": prefix,
        "cwd": str(cwd or ""),
        "expected_outputs": outputs,
        "timeout_sec": timeout,
        "created_at": _now(),
        "boundary": (
            "Human-registered local command. Execution requires approve + --allow-execute "
            "in the CLI; no shell is used, dependencies are not installed, and MCP/HTTP "
            "cannot run it."
        ),
    }
    write_json_atomic(root / "local-spec.json", spec)
    return spec


def approve_local_experiment(project: Path, experiment_id: str, human_reason: str) -> Dict[str, Any]:
    if not str(human_reason or "").strip():
        raise ExperimentExecutionError("approval requires a non-empty human reason")
    root = _root(project, experiment_id)
    spec_path = root / "local-spec.json"
    if not spec_path.is_file():
        raise ExperimentExecutionError("local-spec.json missing; run `experiment local-init` first")
    approval = {
        "schema_version": LOCAL_APPROVAL_SCHEMA,
        "experiment_id": str(experiment_id),
        "spec_sha256": _sha256_file(spec_path),
        "human_reason": str(human_reason),
        "approved_at": _now(),
    }
    write_json_atomic(root / "local-approval.json", approval)
    return approval


def _git_commit(cwd: Path) -> str:
    try:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(cwd), capture_output=True,
            text=True, timeout=5,
        )
        return done.stdout.strip() if done.returncode == 0 else ""
    except Exception:
        return ""


def run_local_experiment(
    project: Path,
    experiment_id: str,
    *,
    allow_execute: bool = False,
    timeout_sec: int = 0,
) -> Dict[str, Any]:
    if not allow_execute:
        raise ExperimentExecutionError("execution requires explicit --allow-execute")
    root = _root(project, experiment_id)
    spec = _load_json(root / "local-spec.json")
    approval = _load_json(root / "local-approval.json")
    if not isinstance(spec, dict) or spec.get("schema_version") != LOCAL_SPEC_SCHEMA:
        raise ExperimentExecutionError("local-spec.json missing; run `experiment local-init` first")
    if not isinstance(approval, dict) or approval.get("schema_version") != LOCAL_APPROVAL_SCHEMA:
        raise ExperimentExecutionError("local-approval.json missing; run `experiment local-approve` first")
    spec_sha = _sha256_file(root / "local-spec.json")
    if str(approval.get("spec_sha256")) != spec_sha:
        raise ExperimentExecutionError("local-spec changed after approval; approve again")
    cwd = (root / str(spec.get("cwd") or "")).resolve() if spec.get("cwd") else root
    if not cwd.is_dir():
        raise ExperimentExecutionError("cwd does not exist: " + str(cwd))
    argv = list(spec.get("env_prefix") or []) + list(spec.get("command") or [])
    timeout = int(timeout_sec or spec.get("timeout_sec") or 3600)
    timeout = max(10, min(timeout, 24 * 3600))
    env = {name: os.environ[name] for name in ENV_ALLOWLIST if name in os.environ}
    started = time.time()
    try:
        completed = subprocess.run(
            argv, cwd=str(cwd), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        status = "completed" if completed.returncode == 0 else "failed"
        stdout, stderr, code = completed.stdout, completed.stderr, completed.returncode
    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        stdout, stderr, code = str(exc.stdout or ""), str(exc.stderr or ""), -1
    except FileNotFoundError as exc:
        raise ExperimentExecutionError("command not found: " + str(exc))
    duration = round(time.time() - started, 3)
    (root / "local.stdout.log").write_text(stdout, encoding="utf-8")
    (root / "local.stderr.log").write_text(stderr, encoding="utf-8")
    outputs, missing = {}, []
    for name in spec.get("expected_outputs") or []:
        path = cwd / str(name)
        if path.is_file():
            outputs[str(name)] = {"sha256": _sha256_file(path), "bytes": path.stat().st_size}
        else:
            missing.append(str(name))
    execution = {
        "schema_version": LOCAL_EXECUTION_SCHEMA,
        "experiment_id": str(experiment_id),
        "status": status,
        "created_at": _now(),
        "command": list(spec.get("command") or []),
        "env_prefix": list(spec.get("env_prefix") or []),
        "argv": argv,
        "cwd": str(cwd),
        "git_commit": _git_commit(cwd),
        "platform": platform.platform(),
        "duration_sec": duration,
        "returncode": code,
        "spec_sha256": spec_sha,
        "stdout": "local.stdout.log",
        "stderr": "local.stderr.log",
        "outputs": outputs,
        "missing_outputs": missing,
        "boundary": "Local execution record only; not a RunCapsule, EA, Claim or gate.",
    }
    write_json_atomic(root / "local-execution.json", execution)
    return execution


def ingest_local_experiment(project: Path, experiment_id: str) -> Dict[str, Any]:
    root = _root(project, experiment_id)
    spec = _load_json(root / "local-spec.json")
    approval = _load_json(root / "local-approval.json")
    execution = _load_json(root / "local-execution.json")
    for obj, schema in ((spec, LOCAL_SPEC_SCHEMA), (approval, LOCAL_APPROVAL_SCHEMA), (execution, LOCAL_EXECUTION_SCHEMA)):
        if not isinstance(obj, dict) or obj.get("schema_version") != schema:
            raise ExperimentExecutionError("local lifecycle incomplete; run init/approve/run first")
    spec_sha = _sha256_file(root / "local-spec.json")
    checks = []

    def add(check_id: str, ok: bool, detail: str) -> None:
        checks.append({"id": check_id, "ok": bool(ok), "detail": detail})

    add("approval_bound", approval.get("spec_sha256") == spec_sha, "approval binds current spec")
    add("execution_bound", execution.get("spec_sha256") == spec_sha, "execution binds current spec")
    add("completed", execution.get("status") == "completed", "execution returncode 0")
    cwd = Path(str(execution.get("cwd") or root))
    outputs_ok = True
    for name, rec in (execution.get("outputs") or {}).items():
        path = cwd / name
        ok = path.is_file() and _sha256_file(path) == str(rec.get("sha256"))
        outputs_ok = outputs_ok and ok
        add("output:" + name, ok, "output hash matches execution record")
    add("no_missing", not (execution.get("missing_outputs") or []), "all expected outputs present")
    verified = all(c["ok"] for c in checks)
    evidence = {
        "schema_version": LOCAL_EVIDENCE_SCHEMA,
        "experiment_id": str(experiment_id),
        "evidence_type": "local_command",
        "status": "verified" if verified else "incomplete",
        "claim_eligible": False,
        "created_at": _now(),
        "spec_sha256": spec_sha,
        "execution_sha256": _sha256_value(execution),
        "outputs": execution.get("outputs") or {},
        "checks": checks,
        "boundary": (
            "Real local execution evidence, but not a RunCapsule/EA/Claim. A human must sign "
            "a claim to use it as a paper result; failed/incomplete runs are retained."
        ),
    }
    write_json_atomic(root / "local-evidence.json", evidence)
    return evidence
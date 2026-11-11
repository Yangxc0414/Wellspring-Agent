"""Read-only research-mandate projection over existing run artifacts.

A mandate is a human-authored delegation: an objective, an authorization scope,
a validity window and stop conditions. This module does not create or widen a
mandate; it aggregates the blockers and next actions already computed in
`runs/*/loop-capsule.json` plus the optional autopilot policy, and reports what
is triggered, what a human must approve, and what would count as verification.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project import ProjectError, open_project

SCHEMA = "research-mandate-0.1"
STATUSES = ("empty", "active", "partial", "needs_human", "stopped")
BOUNDARY = (
    "read-only projection of existing run capsules and autopilot policy; missing artifacts "
    "are not passes; this does not create evidence, claims, gates, signatures or closures, "
    "and it never executes a command"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _load(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProjectError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ProjectError("%s is not a JSON object" % path)
    return data


def _clean(value: Any, limit: int = 300) -> str:
    return str(value or "").strip()[:limit]


def _policy(project: Path, now: datetime) -> Dict[str, Any]:
    path = project / "autopilot" / "policy.json"
    if not path.is_file():
        return {"state": "missing", "path": "", "summary": {}}
    try:
        policy = _load(path)
    except ProjectError as exc:
        return {"state": "invalid", "path": _rel(path, project), "error": str(exc), "summary": {}}
    expires = _parse_time(policy.get("expires_at"))
    policy_id = _clean(policy.get("policy_id"), 80)
    max_runs = policy.get("max_runs")
    if max_runs is not None:
        try:
            max_runs = int(max_runs)
        except (TypeError, ValueError):
            max_runs = None
    used = 0
    ledger_state = "missing"
    ledger_error = ""
    ledger_path = project / "autopilot" / "ledger.json"
    if ledger_path.is_file():
        try:
            ledger = _load(ledger_path)
            runs = ledger.get("runs") or []
            used = sum(
                1 for item in runs
                if isinstance(item, dict)
                and (not policy_id or str(item.get("policy_id") or "") == policy_id)
            )
            ledger_state = "ok"
        except ProjectError as exc:
            ledger_state = "invalid"
            ledger_error = str(exc)
    if not policy.get("authorized_by"):
        state = "invalid"
    elif expires is not None and expires <= now:
        state = "expired"
    elif ledger_state == "invalid":
        state = "invalid"
    elif max_runs is not None and used >= max_runs:
        state = "exhausted"
    else:
        state = "active"
    summary = {
        "policy_id": policy_id,
        "authorized_by": _clean(policy.get("authorized_by"), 200),
        "scope": _clean(policy.get("scope"), 200),
        "datasets": [_clean(item, 80) for item in policy.get("datasets") or []],
        "min_seeds": policy.get("min_seeds"),
        "max_runs": max_runs,
        "runs_used": used,
        "remaining_runs": (max_runs - used) if max_runs is not None else None,
        "ledger_state": ledger_state,
        "expires_at": _clean(policy.get("expires_at"), 80),
    }
    return {"state": state, "path": _rel(path, project), "error": ledger_error, "summary": summary}


def _human_gates(value: Any, run_id: str) -> List[Dict[str, Any]]:
    gates: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            gates.append({**({"gate": str(key)}), "run_id": run_id, "state": _clean(item, 120)})
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                gates.append({"run_id": run_id, **item})
            elif isinstance(item, str):
                gates.append({"run_id": run_id, "gate": item})
    return gates


def build_mandate_status(
    project_path: Path,
    now: Optional[datetime] = None,
    max_runs: int = 20,
) -> Dict[str, Any]:
    project = Path(project_path)
    opened = open_project(project)
    current = now or datetime.now(timezone.utc)
    limit = max(1, min(int(max_runs), 100))
    capsule_paths = sorted((project / "runs").glob("*/loop-capsule.json"))
    selected = capsule_paths[:limit]

    runs: List[Dict[str, Any]] = []
    triggers: List[Dict[str, Any]] = []
    plan: List[Dict[str, Any]] = []
    gate_rows: List[Dict[str, Any]] = []
    blockers_all: List[str] = []
    invalid = 0

    # 判定总线交叉核验（verdict-ledger 0.2.0 roadmap 项）：capsule 是签署前快照，
    # autopilot 代签后其 CLOSURE_UNSIGNED 会变 stale。总线不重算门禁——它消费
    # closure_profiles 已经记录的判定；冲突时以总线为准并留 suppression 审计行。
    verdict_closure: Dict[str, Dict[str, Any]] = {}
    try:
        from .verdict_ledger import collect as _collect_verdicts

        verdict_closure = {
            str(row.get("subject") or ""): row
            for row in (_collect_verdicts(project, limit=limit).get("rows") or [])
            if row.get("kind") == "closure"
        }
    except (OSError, ValueError):
        verdict_closure = {}

    for path in selected:
        run_id = path.parent.name
        # 读时重算（与 research_status 对齐，第三轮证据链去脆弱化）：产物为准，
        # 快照只作重算失败时的兜底。capsule 快照是签署前状态，代签/推进后全量
        # blockers 都可能 stale——重算消掉整类漂移而不只是 CLOSURE_UNSIGNED。
        capsule_source = "snapshot"
        try:
            from .loop_capsule import build_loop_capsule

            capsule = build_loop_capsule(path.parent)
            capsule_source = "recomputed"
        except Exception as exc:
            try:
                capsule = _load(path) or {}
            except ProjectError as load_exc:
                invalid += 1
                runs.append({"run_id": run_id, "capsule": _rel(path, project), "status": "invalid",
                             "error": str(load_exc)})
                triggers.append({"kind": "invalid_capsule", "code": "INVALID_RUN_CAPSULE",
                                 "run_id": run_id, "source": _rel(path, project)})
                continue
            capsule_source = "snapshot_fallback"
            triggers.append({
                "kind": "recompute_failed", "code": "CAPSULE_RECOMPUTE_FAILED",
                "run_id": run_id, "source": _rel(path, project),
                "error": str(exc)[:160],
            })
        blockers = [str(item) for item in capsule.get("blockers") or [] if str(item).strip()]
        actions = [
            action for action in capsule.get("next_actions") or []
            if isinstance(action, dict)
        ]
        closure_row = verdict_closure.get("runs/" + run_id)
        bus_signed = bool(closure_row) and closure_row.get("status") == "signed"
        if bus_signed and "CLOSURE_UNSIGNED" in blockers:
            # 兜底路径（重算失败落到快照时）的第二道保险：总线判定优先于快照
            blockers = [code for code in blockers if code != "CLOSURE_UNSIGNED"]
            actions = [
                action for action in actions
                if "closure sign" not in str(action.get("command") or "")
            ]
            triggers.append({
                "kind": "stale_snapshot_suppressed", "code": "CLOSURE_UNSIGNED",
                "run_id": run_id, "source": _rel(path, project),
                "authority": "verdict-ledger", "recomputed": "signed",
                "source_sha256": str(closure_row.get("source_sha256") or ""),
            })
        run_status = _clean(capsule.get("task_status") or capsule.get("flow_mode") or "", 80)
        runs.append({
            "run_id": run_id,
            "capsule": _rel(path, project),
            "capsule_sha256": _sha(path),
            "capsule_source": capsule_source,
            "status": run_status,
            "route": _clean(capsule.get("route"), 120),
            "blockers": blockers,
            "next_actions": len(actions),
        })
        for code in blockers:
            if code not in blockers_all:
                blockers_all.append(code)
            triggers.append({"kind": "blocker", "code": code, "run_id": run_id,
                             "source": _rel(path, project), "authority": "human"})
        for action in actions:
            plan.append({
                "run_id": run_id,
                "owner": _clean(action.get("owner") or "human", 40),
                "gate": _clean(action.get("gate"), 40),
                "command": _clean(action.get("command"), 1000),
            })
        gate_rows.extend(_human_gates(capsule.get("human_gates"), run_id))

    policy = _policy(project, current)
    if policy["state"] == "expired":
        triggers.append({"kind": "policy_expired", "code": "AUTOPILOT_POLICY_EXPIRED",
                         "source": policy["path"], "expires_at": policy["summary"].get("expires_at")})
    elif policy["state"] == "exhausted":
        triggers.append({"kind": "policy_exhausted", "code": "AUTOPILOT_POLICY_EXHAUSTED",
                         "source": policy["path"],
                         "max_runs": policy["summary"].get("max_runs"),
                         "runs_used": policy["summary"].get("runs_used")})
    elif policy["state"] == "invalid":
        triggers.append({"kind": "policy_invalid", "code": "AUTOPILOT_POLICY_INVALID",
                         "source": policy["path"], "error": policy.get("error", "")})

    # A truncated scan must never be read as "nothing is wrong": the runs outside the
    # window are unseen, not clean.
    truncated = len(capsule_paths) > limit
    if truncated:
        triggers.append({"kind": "scope_truncated", "code": "MANDATE_SCOPE_TRUNCATED",
                         "runs_total": len(capsule_paths), "runs_scanned": len(selected)})
    substantive = bool(blockers_all or plan or any(
        item["kind"] != "scope_truncated" for item in triggers
    ))

    if policy["state"] in ("expired", "exhausted"):
        status = "stopped"
    elif substantive:
        status = "needs_human"
    elif truncated:
        status = "partial"
    elif not selected and not capsule_paths:
        status = "empty"
    else:
        status = "active"

    commands = []
    for item in plan:
        command = item["command"]
        if command and command not in commands:
            commands.append(command)

    return {
        "schema_version": SCHEMA,
        "generated_at": _now(),
        "project": str(project.resolve()),
        "status": status,
        "counts": {
            "runs": len(selected),
            "capsules_total": len(capsule_paths),
            "truncated": len(capsule_paths) > limit,
            "invalid_capsules": invalid,
            "triggers": len(triggers),
            "open_blockers": len(blockers_all),
            "next_actions": len(plan),
        },
        "stages": {
            "mandate": {
                "project_id": _clean(opened.get("project_id"), 80),
                "name": _clean(opened.get("name"), 120),
                "created_at": _clean(opened.get("created_at"), 80),
            },
            "trigger": triggers,
            "context": {
                "runs": runs,
                "policy": policy,
            },
            "plan": plan,
            "approval": {
                "policy_state": policy["state"],
                "human_gates": gate_rows,
                "delegation": (
                    "autopilot policy may cover only its declared scope; claim signatures, "
                    "closure signatures, publishing and export approval stay human-only"
                ),
            },
            "verification": {
                "rule": (
                    "a trigger is cleared only when its blocker disappears from a fresh "
                    "loop capsule and the artifact named by the human command verifies"
                ),
                "commands": commands,
                "not_evidence": True,
            },
            "obligations": blockers_all,
            "acceptance": {
                "unit": "a mandate over a time window, not a single run",
                "status": status,
                "rule": (
                    "no open blocker, a valid policy (if one is used), and every claim/closure "
                    "verification passes; this projection does not sign"
                ),
                "stop_conditions": [
                    "the autopilot policy expires or is revoked",
                    "a human stops the mandate",
                ],
            },
        },
        "boundary": BOUNDARY,
    }

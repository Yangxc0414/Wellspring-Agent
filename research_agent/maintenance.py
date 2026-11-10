"""Closed-loop maintenance: plan a change, then only auto-reclose safe cases.

The important boundary is what this module refuses to do: it never runs S5,
rewrites a slot, signs a claim, or publishes an export. It turns a change into
a plan; reclosure is allowed only when every affected node is a recheck.
"""

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .closure import ClosureAgent, ClosureError
from .lineage import LineageAgent, LineageError
from .storage import JsonStoreError, read_json, write_json_atomic

PLAN_SCHEMA = "maintenance-plan-0.1"
RECLOSURE_SCHEMA = "reclosure-report-0.1"


class MaintenanceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = read_json(Path(path))
    except JsonStoreError as exc:
        raise MaintenanceError(str(exc))
    if value is None:
        raise MaintenanceError("%s not found: %s" % (label, path))
    if not isinstance(value, dict):
        raise MaintenanceError("%s must contain a JSON object" % label)
    return value


class MaintenanceAgent:
    def plan(
        self,
        baseline_manifest: Path,
        bundle: Path,
        actor: str,
        reason: str,
        output_dir: Path,
    ) -> Dict[str, Any]:
        actor = " ".join(str(actor or "").split())
        reason = " ".join(str(reason or "").split())
        if not actor or not reason:
            raise MaintenanceError("actor and reason are required for a maintenance plan")
        try:
            impact = LineageAgent().verify(Path(baseline_manifest), Path(bundle))
        except LineageError as exc:
            raise MaintenanceError("cannot compute impact: %s" % exc)
        actions = impact.get("action_counts") or {}
        rerun_or_rewrite = bool(actions.get("rerun") or actions.get("rewrite"))
        stale = impact.get("status") == "stale"
        if not stale:
            status = "clean"
            auto_reclose_allowed = False
        elif rerun_or_rewrite:
            status = "blocked_pending_work"
            auto_reclose_allowed = False
        elif actions.get("recheck"):
            status = "ready_for_reclosure"
            auto_reclose_allowed = True
        else:
            status = "blocked_pending_work"
            auto_reclose_allowed = False
        plan = {
            "schema_version": PLAN_SCHEMA,
            "plan_id": "MNT-" + uuid.uuid4().hex[:10],
            "created_at": _now(),
            "actor": actor,
            "reason": reason,
            "baseline_manifest": str(Path(baseline_manifest).resolve()),
            "bundle_root": str(Path(bundle).resolve()),
            "status": status,
            "auto_reclose_allowed": auto_reclose_allowed,
            "requires_human_signature": stale,
            "export_allowed": bool(impact.get("export_allowed")) and not stale,
            "changes": impact.get("changed") or [],
            "stale": impact.get("stale") or [],
            "stale_ids": [str(item.get("node_id")) for item in impact.get("stale") or []],
            "dispositions": impact.get("dispositions") or [],
            "action_counts": actions,
            "next_steps": impact.get("next_steps") or [],
        }
        output_dir = Path(output_dir)
        path = output_dir / "maintenance-plan.json"
        write_json_atomic(path, plan)
        return {"plan": plan, "path": str(path)}

    def reclose(
        self,
        plan_path: Path,
        bundle: Path,
        demo: Path,
        claim: Path,
        output_dir: Path,
    ) -> Dict[str, Any]:
        plan = _read_object(Path(plan_path), "maintenance plan")
        if plan.get("schema_version") != PLAN_SCHEMA:
            raise MaintenanceError("unsupported maintenance plan")
        if not str(plan.get("actor") or "").strip() or not str(plan.get("reason") or "").strip():
            raise MaintenanceError("maintenance plan has no actor/reason")
        bundle_root = Path(bundle).resolve()
        if str(bundle_root) != str(plan.get("bundle_root")):
            raise MaintenanceError("bundle does not match the maintenance plan")
        demo_path = Path(demo).resolve()
        claim_path = Path(claim).resolve()
        for label, path in (("demo", demo_path), ("claim", claim_path)):
            try:
                path.relative_to(bundle_root)
            except ValueError:
                raise MaintenanceError("%s must live inside the maintenance bundle" % label)
        try:
            current = LineageAgent().verify(Path(str(plan["baseline_manifest"])), Path(bundle))
        except (LineageError, KeyError) as exc:
            raise MaintenanceError("cannot verify current bundle: %s" % exc)
        claim_node = next(
            (node for node in current.get("nodes") or [] if node.get("kind") == "claim"),
            None,
        )
        if claim_node and hashlib.sha256(claim_path.read_bytes()).hexdigest() != claim_node.get("sha256"):
            raise MaintenanceError("claim does not match the current lineage node")
        current_actions = current.get("action_counts") or {}
        current_stale_ids = [str(item.get("node_id")) for item in current.get("stale") or []]
        if current_stale_ids != sorted(plan.get("stale_ids") or []):
            # The plan may have been made before another edit; never reclose a
            # bundle whose impact changed underneath it.
            return {
                "status": "stale_plan",
                "plan_id": plan.get("plan_id"),
                "current_action_counts": current_actions,
                "current_stale_ids": current_stale_ids,
                "required_action": "create a new maintenance plan",
                "signed": False,
                "export_allowed": False,
            }
        if current.get("status") == "clean":
            return {
                "status": "clean",
                "plan_id": plan.get("plan_id"),
                "signed": False,
                "export_allowed": bool(current.get("export_allowed")),
                "required_action": "none",
            }
        if not plan.get("auto_reclose_allowed") or current_actions.get("rerun") or current_actions.get("rewrite"):
            return {
                "status": "blocked_pending_work",
                "plan_id": plan.get("plan_id"),
                "current_action_counts": current_actions,
                "next_steps": current.get("next_steps") or plan.get("next_steps") or [],
                "signed": False,
                "export_allowed": False,
                "required_action": "complete rerun/rewrite work, then create a new plan",
            }
        if current_actions.get("recheck") and not plan.get("auto_reclose_allowed"):
            return {
                "status": "blocked_pending_work",
                "plan_id": plan.get("plan_id"),
                "current_action_counts": current_actions,
                "signed": False,
                "export_allowed": False,
                "required_action": "create a new maintenance plan",
            }
        try:
            closure = ClosureAgent().check(Path(demo), Path(claim), Path(output_dir))
        except ClosureError as exc:
            raise MaintenanceError("cannot run closure: %s" % exc)
        closure_report = closure.get("report") or {}
        ready = closure_report.get("status") == "ready"
        result = {
            "schema_version": RECLOSURE_SCHEMA,
            "created_at": _now(),
            "plan_id": plan.get("plan_id"),
            "status": "ready_for_resign" if ready else "blocked_closure",
            "closure_report_path": str(closure.get("path", "")),
            "closure_status": closure_report.get("status"),
            "auto_reclose_allowed": True,
            "signed": False,
            "export_allowed": False,
            "required_action": "human closure sign, then closure publish" if ready else "fix closure blockers",
            "plan": plan,
        }
        output_dir = Path(output_dir)
        path = output_dir / "reclosure-report.json"
        write_json_atomic(path, result)
        return {"report": result, "path": str(path)}

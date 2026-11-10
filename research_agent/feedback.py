"""FeedbackPort: the pluggable seam where a verdict changes the next action.

71-§4.2: every loop follows observe -> propose -> gate -> apply -> record, and
the gate defaults to reject — a loop that wants to mutate anything gated stays
a proposal until its scope is explicitly registered.  V1 ships one loop,
``lineage_reverify``: it re-derives the lineage impact straight from the
artifacts (read-only) and records the receipt, which is the 回指 side of
feedback loop B (溯源/失效传播) in the strategy figure.  With no loops enabled
the port writes nothing anywhere, so 关闭全部环 = 与今日行为逐字节一致.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .storage import write_json_atomic

FEEDBACK_SCHEMA = "feedback-ledger-0.1"

_BOUNDARY = (
    "pluggable feedback loops; the gate defaults to reject, so v1 applies only "
    "read-only re-verification and records the receipt; disabled by default — "
    "with no loops enabled nothing is written and no projection changes"
)

# (loop_id) -> {"observe": fn(project, limit) -> [observation],
#               "propose": fn(observation) -> [proposal],
#               "gate": fn(proposal) -> decision,
#               "apply": fn(proposal, observation, project) -> effect}
_LOOPS: Dict[str, Dict[str, Callable[..., Any]]] = {}


def register_loop(loop_id: str, observe: Callable[..., Any], propose: Callable[..., Any],
                  gate: Callable[..., Any], apply: Callable[..., Any]) -> None:
    if loop_id in _LOOPS:
        raise ValueError("feedback loop already registered: " + loop_id)
    _LOOPS[loop_id] = {
        "observe": observe,
        "propose": propose,
        "gate": gate,
        "apply": apply,
    }


def registered_loops() -> List[str]:
    return sorted(_LOOPS)


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _observe_lineage_reverify(project: Path, limit: int = 50) -> List[Dict[str, Any]]:
    from .lineage import LineageAgent, LineageError

    root = Path(project).resolve()
    observations: List[Dict[str, Any]] = []
    runs_dir = root / "runs"
    if not runs_dir.is_dir():
        return observations
    for run in sorted(runs_dir.glob("RUN-*"))[-max(1, min(int(limit), 200)):]:
        if not run.is_dir():
            continue
        manifest = run / "lineage" / "lineage.json"
        if not manifest.is_file():
            continue
        subject = "runs/" + run.name
        try:
            impact = LineageAgent().verify(manifest, run)
        except LineageError as exc:
            observations.append(
                {
                    "loop_id": "lineage_reverify",
                    "subject": subject,
                    "state": "verify_failed",
                    "detail": str(exc),
                    "source_path": _rel(root, manifest),
                    "source_sha256": _sha256(manifest),
                }
            )
            continue
        observations.append(
            {
                "loop_id": "lineage_reverify",
                "subject": subject,
                # impact carries a wall-clock field (verified_at); the observation keeps
                # only stable verdict fields so the ledger stays deterministic
                "state": str(impact.get("status") or "unknown"),
                "changed": bool(impact.get("changed")),
                "stale_nodes": list(impact.get("stale") or []),
                "stale": len(impact.get("stale") or []),
                "requires_reclosure": bool(impact.get("requires_reclosure")),
                "requires_resign": bool(impact.get("requires_resign")),
                "export_allowed": bool(impact.get("export_allowed")),
                "source_path": _rel(root, manifest),
                "source_sha256": _sha256(manifest),
            }
        )
    return observations


def _propose_lineage_reverify(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    subject = str(observation.get("subject") or "")
    stale = int(observation.get("stale") or 0)
    needs_resign = bool(observation.get("requires_resign"))
    proposal = {
        "loop_id": "lineage_reverify",
        "kind": "record_receipt",
        "read_only": True,
        "subject": subject,
        "human_action": "",
    }
    if stale or needs_resign:
        proposal["human_action"] = (
            "lineage impact is stale on %d node(s)%s; re-run the affected closure/check "
            "and re-sign in the CLI before any further export" % (stale, " and a re-sign is required" if needs_resign else "")
        )
    return [proposal]


def _gate_lineage_reverify(proposal: Dict[str, Any]) -> Dict[str, Any]:
    # default reject: only read-only receipts may pass; anything that would touch a
    # gated artifact (claim/EA/closure/signature/export) is refused at the seam
    if proposal.get("read_only"):
        return {"decision": "auto_allowed", "reason": "read-only re-verification; writes nothing outside the feedback ledger"}
    return {"decision": "rejected", "reason": "mutating proposals need a registered scope (default reject)"}


def _apply_lineage_reverify(proposal: Dict[str, Any], observation: Dict[str, Any], project: Path) -> Dict[str, Any]:
    return {
        "effect": "recorded_receipt",
        "state": str(observation.get("state") or ""),
        "stale": int(observation.get("stale") or 0) if not isinstance(observation.get("stale"), list) else len(observation["stale"]),
        "human_action": str(proposal.get("human_action") or ""),
    }


register_loop(
    "lineage_reverify",
    _observe_lineage_reverify,
    _propose_lineage_reverify,
    _gate_lineage_reverify,
    _apply_lineage_reverify,
)


def _observe_t6b_falsification(project: Path, limit: int = 50) -> List[Dict[str, Any]]:
    """T6b 证伪/反事实（审计项 → 记录化 proposal 的第一步，71-图① 对照）。

    Observation: executed studies bind a falsification condition in
    study-origin.json; the loop reads that condition together with the study's
    claim status.  The auto-back-pointer into hypothesis GENERATION is roadmap;
    v1 records the constraint a future generation must carry.
    """
    from .storage import read_json as _read_json

    root = Path(project).resolve()
    observations: List[Dict[str, Any]] = []
    studies = root / "studies"
    if not studies.is_dir():
        return observations
    for origin_path in sorted(studies.glob("*/study-origin.json"))[-max(1, min(int(limit), 200)):]:
        try:
            origin = _read_json(origin_path)
        except (OSError, ValueError):
            origin = {}
        if not isinstance(origin, dict):
            origin = {}
        study_dir = origin_path.parent
        claim_path = study_dir / "claim.json"
        claim_status = "absent"
        if claim_path.is_file():
            try:
                claim_payload = _read_json(claim_path)
                claim_status = str((claim_payload or {}).get("status") or "absent")
            except (OSError, ValueError):
                claim_status = "unreadable"
        falsification = str(origin.get("falsification") or "")
        observations.append(
            {
                "loop_id": "t6b_falsification",
                "subject": _rel(root, study_dir),
                "state": "falsification_bound" if falsification else "no_falsification_bound",
                "falsification": falsification,
                "idea_id": str(origin.get("idea_id") or ""),
                "claim_status": claim_status,
                "source_path": _rel(root, origin_path),
                "source_sha256": _sha256(origin_path),
            }
        )
    return observations


def _propose_t6b_falsification(observation: Dict[str, Any]) -> List[Dict[str, Any]]:
    falsification = str(observation.get("falsification") or "")
    if observation.get("state") == "falsification_bound":
        constraint = "carry the executed falsification condition into new hypotheses: " + falsification[:240]
    else:
        constraint = (
            "bind a falsification condition before the next study is executed "
            "(study-origin.falsification is empty for %s)" % observation.get("subject")
        )
    return [
        {
            "loop_id": "t6b_falsification",
            "kind": "generation_constraint",
            "read_only": True,
            "subject": str(observation.get("subject") or ""),
            "constraint": constraint,
            "human_action": "",
        }
    ]


def _apply_t6b_falsification(proposal: Dict[str, Any], observation: Dict[str, Any], project: Path) -> Dict[str, Any]:
    return {
        "effect": "recorded_constraint",
        "state": str(observation.get("state") or ""),
        "constraint": str(proposal.get("constraint") or ""),
    }


register_loop(
    "t6b_falsification",
    _observe_t6b_falsification,
    _propose_t6b_falsification,
    _gate_lineage_reverify,  # same read-only-only gate discipline
    _apply_t6b_falsification,
)


def run_feedback(project: Path, loops: Optional[List[str]] = None, limit: int = 50) -> Dict[str, Any]:
    """Run the explicitly enabled loops; with none enabled, write nothing anywhere."""
    root = Path(project).resolve()
    if not root.is_dir():
        raise ValueError("project directory does not exist: %s" % root)
    if not loops:
        return {
            "schema_version": FEEDBACK_SCHEMA,
            "status": "disabled",
            "loops_run": [],
            "rows": 0,
            "registered": registered_loops(),
            "boundary": _BOUNDARY,
        }
    unknown = [loop_id for loop_id in loops if loop_id not in _LOOPS]
    if unknown:
        raise ValueError("unknown feedback loop(s): %s; registered: %s" % (", ".join(unknown), ", ".join(registered_loops())))
    rows: List[Dict[str, Any]] = []
    for loop_id in loops:
        entry = _LOOPS[loop_id]
        for observation in entry["observe"](root, limit=limit):
            for proposal in entry["propose"](observation):
                decision = entry["gate"](proposal)
                effect = None
                if decision.get("decision") == "auto_allowed":
                    effect = entry["apply"](proposal, observation, root)
                rows.append(
                    {
                        "loop_id": loop_id,
                        "subject": str(observation.get("subject") or ""),
                        "observation": observation,
                        "proposal": proposal,
                        "gate_decision": decision,
                        "effect": effect,
                    }
                )
    rows.sort(key=lambda row: (row["loop_id"], row["subject"], json.dumps(row["observation"], sort_keys=True)))
    ledger = {
        "schema_version": FEEDBACK_SCHEMA,
        "status": "ran",
        "loops": list(loops),
        "rows": rows,
        "boundary": _BOUNDARY,
    }
    write_json_atomic(str(root / "feedback-ledger.json"), ledger)
    return ledger


def read_ledger(path: Path) -> Dict[str, Any]:
    """Read a previously written feedback ledger."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


ACTION_SCHEMA = "verdict-action-0.1"

_ACTION_BOUNDARY = (
    "deterministic decision table: verdict rows -> one proposed action per subject; "
    "same-subject conflicts and invariant violations escalate to a human instead of "
    "guessing a winner; pure and wall-clock free, so the same rows always produce "
    "the same actions"
)


def _action_for(kind: str, status: str) -> str:
    if kind == "closure":
        if status == "signed":
            return "verify_bundle"
        if status == "ready":
            return "closure_sign_human"
        return "inspect_run"
    if kind == "claim":
        if status == "signed":
            return "closure_check"
        if status == "draft":
            return "claim_sign_human"
        return "complete_run_first"
    if kind == "experiment":
        if status == "signed":
            return "verify_bundle"
        if status == "ready_for_human_signature":
            return "experiment_sign_human"
        return "run_experiment_closure"
    if kind == "study":
        if status == "signed":
            return "closed_study"
        if status == "ready_for_human_signature":
            return "study_sign_human"
        return "run_study_closure"
    if kind == "snapshot_drift":
        # the drift row means the capsule snapshot is stale; the summary consumer
        # already re-derives through the bus, so the action is: trust the override,
        # never the snapshot
        return "verdict_bus_authoritative"
    return "inspect_artifacts"


def verdict_action_table(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministically propose the next action per subject from verdict rows.

    借鉴点（71-§4.2 设计输入 3）：grade-iterate 的 verdict_reader 是纯函数决策表，
    预算/状态改变建议动作；这里同型——同一 subject 的判定互相矛盾、或出现不变量
    违例（closure signed 而 claim 未签）时，升级为 escalate_conflict 交人工裁决，
    不猜哪边对。
    """
    by_subject: Dict[str, Dict[str, str]] = {}
    for row in rows:
        subject = str(row.get("subject") or "")
        kind = str(row.get("kind") or "")
        status = str(row.get("status") or "")
        if not subject or not kind:
            continue
        slot = by_subject.setdefault(subject, {})
        if kind in slot and slot[kind] != status:
            # same subject, same kind, two verdicts: the table does not guess
            slot[kind] = "__conflict__"
        else:
            slot[kind] = status
    actions = []
    for subject in sorted(by_subject):
        slot = by_subject[subject]
        conflict = any(status == "__conflict__" for status in slot.values())
        if not conflict and slot.get("closure") == "signed" and slot.get("claim") not in (None, "signed"):
            # invariant violation: a signed closure over an unsigned claim cannot be
            # acted on; escalate instead of picking a winner
            conflict = True
        if conflict:
            action, basis = "escalate_conflict", "conflicting verdicts for one subject"
        else:
            # the earliest unfinished stage wins: claim -> closure -> bundle
            claim_status = slot.get("claim")
            closure_status = slot.get("closure")
            if closure_status is not None:
                action, basis = _action_for("closure", closure_status), {"kind": "closure", "status": closure_status}
            elif claim_status is not None:
                action, basis = _action_for("claim", claim_status), {"kind": "claim", "status": claim_status}
            else:
                drift_status = slot.get("snapshot_drift")
                exp_status = slot.get("experiment")
                study_status = slot.get("study")
                if drift_status is not None:
                    action, basis = _action_for("snapshot_drift", drift_status), {"kind": "snapshot_drift", "status": drift_status}
                elif exp_status is not None:
                    action, basis = _action_for("experiment", exp_status), {"kind": "experiment", "status": exp_status}
                elif study_status is not None:
                    action, basis = _action_for("study", study_status), {"kind": "study", "status": study_status}
                else:
                    action, basis = "inspect_artifacts", {}
        actions.append({"subject": subject, "action": action, "basis": basis})
    counts: Dict[str, int] = {}
    for item in actions:
        counts[item["action"]] = counts.get(item["action"], 0) + 1
    return {
        "schema_version": ACTION_SCHEMA,
        "actions": actions,
        "counts": counts,
        "boundary": _ACTION_BOUNDARY,
    }

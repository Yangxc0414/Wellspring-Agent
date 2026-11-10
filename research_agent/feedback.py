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

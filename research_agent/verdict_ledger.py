"""Verdict ledger: one deterministic, read-only projection of the decisions a
project's artifacts already contain.

Consumers used to read decisions from snapshots (``loop-capsule.json`` blockers
and next_actions) that go stale the moment a signature lands after the snapshot
was written: an autopilot run signs closure, and the capsule still says
``CLOSURE_UNSIGNED``, so a host following next_actions volunteers to sign an
already-signed closure.  The ledger re-derives each verdict from its
single-point producer (``closure_profiles.detect_project_profiles``) and pairs
it with the snapshot claim, so the drift between the two is visible instead of
silent.

It adds no new judgment: every row names the artifact it was derived from and
carries that artifact's sha256.  Collecting twice over unchanged artifacts
yields byte-identical output (no wall-clock fields), which is what makes the
ledger auditable by replay rather than by trust.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from .closure_profiles import claim_candidates, detect_project_profiles
from .storage import write_json_atomic

VERDICT_SCHEMA = "verdict-ledger-0.1"

_BOUNDARY = (
    "read-only deterministic projection: collect twice over unchanged artifacts "
    "and the bytes are identical; adds no verdicts, writes no claims, evidence "
    "or gates; the snapshot comparison reads loop-capsule.json but never trusts it"
)


def _rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        # a stray artifact outside the project keeps its name only; the ledger
        # must never publish an absolute local path (it is HTTP-readable)
        return path.name


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _row(
    kind: str,
    subject: str,
    status: str,
    source_path: Path,
    root: Path,
    detail: str,
    **extra: Any,
) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "kind": kind,
        "subject": subject,
        "status": status,
        "verdict_source": "recomputed",
        "source_path": _rel(root, source_path),
        "source_sha256": _sha256(source_path) if source_path.is_file() else "",
        "detail": detail,
    }
    row.update(extra)
    return row


def _closure_source(run: Path) -> Path:
    # mirrors the candidate order closure_profiles uses for the canonical run;
    # keep the two lists in sync (pinned by test_verdict_ledger)
    for candidate in (run / "run" / "closure-report.json", run / "closure" / "closure-report.json"):
        if candidate.is_file():
            return candidate
    return run / "closure" / "closure-report.json"


def _claim_source(root: Path, run: Path) -> Path:
    for candidate in claim_candidates(root, run):
        if candidate.is_file():
            return candidate
    # a draft verdict derives from the draft itself, which lives outside the
    # signed-claim candidate list closure_profiles scans
    for draft in (run / "run" / "claim-draft.json", run / "claim-draft.json"):
        if draft.is_file():
            return draft
    return run / "claim" / "claim.json"


def closure_verdict_for_run(run_dir: Path) -> Dict[str, Any]:
    """Single-run closure verdict for consumers whose layout is one bare run dir
    (runtime jobs), using the same sources as collect()'s canonical row.

    Returns {status, delegated, has_signed_claim, source_path, source_sha256} —
    the same fields the canonical closure row carries, computed per run dir so
    the runtime payload can surface fresh verdicts without a project layout.
    """
    run = Path(run_dir)
    closure_path = _closure_source(run)
    closure = _read_json_safe(closure_path)
    signature_path = run / "closure-signature" / "signature.json"
    signature = _read_json_safe(signature_path)
    status = str((closure or {}).get("status") or "missing")
    if signature and status == "ready":
        status = "signed"
    claim_path = run / "claim" / "claim.json"
    claim = _read_json_safe(claim_path)
    claim_status = str((claim or {}).get("status") or "") in ("supported", "approved")
    return {
        "subject": "runs/" + run.name,
        "status": status,
        "delegated": str((signature or {}).get("human_reason") or "").startswith("[delegated:"),
        "has_signed_claim": claim_status,
        "source_path": closure_path.name and str(closure_path),
        "source_sha256": _sha256(closure_path) if closure_path.is_file() else "",
    }


def _read_json_safe(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _capsule_blockers(capsule: Path) -> List[str]:
    if not capsule.is_file():
        return []
    try:
        payload = json.loads(capsule.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["__unreadable__"]
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        return ["__unreadable__"]
    return [str(item) for item in blockers]


def _study_source(study_dir: Path) -> Path:
    for candidate in (study_dir / "closure" / "closure-report.json", study_dir / "closure-report.json"):
        if candidate.is_file():
            return candidate
    return study_dir / "closure" / "closure-report.json"


def collect(project: Path, limit: int = 50) -> Dict[str, Any]:
    """Re-derive every verdict the project's artifacts already contain."""
    root = Path(project).resolve()
    if not root.is_dir():
        raise ValueError("project directory does not exist: %s" % root)
    detection = detect_project_profiles(root, limit=limit)
    rows: List[Dict[str, Any]] = []

    for item in detection.get("canonical_run") or []:
        run_id = str(item.get("run_id") or "")
        run = root / "runs" / run_id
        subject = "runs/" + run_id
        closure_status = str(item.get("closure_status") or "missing")
        rows.append(
            _row(
                "closure",
                subject,
                closure_status,
                _closure_source(run),
                root,
                str(item.get("next") or ""),
                delegated=bool(item.get("delegated")),
                has_signed_claim=bool(item.get("has_signed_claim")),
            )
        )
        claim_status = (
            "signed" if item.get("has_signed_claim") else ("draft" if item.get("has_claim_draft") else "absent")
        )
        rows.append(
            _row(
                "claim",
                subject + "/claim",
                claim_status,
                _claim_source(root, run),
                root,
                "single-point: claim candidates shared with closure_profiles",
            )
        )
        capsule = run / "loop-capsule.json"
        blockers = _capsule_blockers(capsule)
        if blockers == ["__unreadable__"]:
            rows.append(
                {
                    "kind": "snapshot_drift",
                    "subject": subject + "/loop-capsule.json",
                    "status": "unreadable",
                    "verdict_source": "snapshot",
                    "source_path": _rel(root, capsule),
                    "source_sha256": _sha256(capsule) if capsule.is_file() else "",
                    "detail": "loop-capsule.json is not valid JSON; the snapshot side of the comparison fails visible",
                }
            )
        elif capsule.is_file():
            signed = closure_status == "signed"
            stale = "CLOSURE_UNSIGNED" in blockers
            if signed and stale:
                rows.append(
                    {
                        "kind": "snapshot_drift",
                        "subject": subject + "/loop-capsule.json",
                        "status": "stale",
                        "verdict_source": "snapshot",
                        "source_path": _rel(root, capsule),
                        "source_sha256": _sha256(capsule),
                        "snapshot": "CLOSURE_UNSIGNED",
                        "recomputed": "signed",
                        "detail": (
                            "capsule snapshot predates the signature; consumers reading blockers must "
                            "re-derive closure from closure profiles, not from this snapshot"
                        ),
                    }
                )

    for item in detection.get("local_experiment") or []:
        experiment_id = str(item.get("experiment_id") or "")
        package = root / "experiments" / experiment_id
        rows.append(
            _row(
                "experiment",
                "experiments/" + experiment_id,
                str(item.get("closure_status") or "missing"),
                package / "experiment-closure" / "closure-report.json",
                root,
                str(item.get("next") or ""),
                signed=bool(item.get("signed")),
            )
        )

    for item in detection.get("search_study") or []:
        study_dir = root / str(item.get("study_dir") or "studies/unknown")
        rows.append(
            _row(
                "study",
                str(item.get("study_dir") or "studies/unknown"),
                str(item.get("closure_status") or "missing"),
                _study_source(study_dir),
                root,
                str(item.get("next") or ""),
                signed=bool(item.get("signed")),
                underpowered=bool(item.get("underpowered")),
                dataset=str(item.get("dataset") or ""),
            )
        )

    rows.sort(key=lambda row: (row["kind"], row["subject"], row.get("status", "")))
    counts: Dict[str, Any] = {}
    for row in rows:
        bucket = counts.setdefault(row["kind"], {})
        bucket[row["status"]] = bucket.get(row["status"], 0) + 1
    counts["drift"] = sum(1 for row in rows if row["kind"] == "snapshot_drift")
    counts["rows"] = len(rows)
    return {
        "schema_version": VERDICT_SCHEMA,
        "rows": rows,
        "sources": sorted(
            {
                row["source_path"] + "  " + row["source_sha256"]
                for row in rows
                if row.get("source_sha256")
            }
        ),
        "counts": counts,
        "present_profiles": list(detection.get("present_profiles") or []),
        "boundary": _BOUNDARY,
    }


def write_ledger(path: Path, ledger: Dict[str, Any]) -> Dict[str, Any]:
    """Atomically persist a collected ledger; deterministic content, atomic write."""
    target = Path(path)
    if target.parent and not target.parent.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(str(target), ledger)
    return {
        "schema_version": ledger.get("schema_version") or VERDICT_SCHEMA,
        "path": str(target),
        "rows": len(ledger.get("rows") or []),
        "counts": ledger.get("counts") or {},
    }

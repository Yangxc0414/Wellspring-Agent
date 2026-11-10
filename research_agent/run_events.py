"""Append-only run events and gate-boundary commits.

The event list is the authority. Every JSON snapshot derived from a run
(`demo.json`, `job.json`, a report) is a projection and must never be edited
in place to change a gate conclusion. This module supplies four things:

* a SHA-256 linked, append-only event list (``append_event`` / ``verify_events``);
* an atomic boundary decision (``commit_boundary``) that refuses to advance a
  phase while any gate is blocked, pending or failed;
* a read-only replay (``replay_boundaries``) for inspecting where a run stopped;
* append-only persistence to ``events.ndjson`` (``write_events`` / ``read_events``).

It deliberately does NOT resume a run, cross a human gate, change
``submission_ready``, or write any Claim/EA/Verdict/gate/signature. A
``boundary_committed`` event is an auditable statement about gates, not a
permission to continue.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

EVENT_SCHEMA = "run-events-0.1"
COMMITTED_KIND = "boundary_committed"
REJECTED_KIND = "gate_rejected"
PASS_STATUSES = ("pass", "skipped")
EVENT_FILENAME = "events.ndjson"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _entry_hash(entry: Dict[str, Any]) -> str:
    payload = {key: value for key, value in entry.items() if key != "entry_hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def append_event(
    events: List[Dict[str, Any]],
    kind: str,
    phase: str = "",
    payload: Optional[Dict[str, Any]] = None,
    at: str = "",
) -> Dict[str, Any]:
    """Append one event. Earlier entries are never read or modified for writing."""
    previous = str(events[-1].get("entry_hash") or "") if events else ""
    entry = {
        "schema_version": EVENT_SCHEMA,
        "seq": len(events) + 1,
        "at": at or _now(),
        "kind": str(kind or "info"),
        "phase": str(phase or ""),
        "payload": dict(payload or {}),
        "prev_hash": previous,
    }
    entry["entry_hash"] = _entry_hash(entry)
    events.append(entry)
    return entry


def verify_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Recompute the chain and report every mismatch; never repair anything."""
    errors: List[str] = []
    previous = ""
    expected_seq = 1
    count = 0
    last_hash = ""
    for line_number, entry in enumerate(events or [], start=1):
        if not isinstance(entry, dict):
            errors.append("line %d is not an object" % line_number)
            continue
        count += 1
        if entry.get("seq") != expected_seq:
            errors.append("line %d seq is %r, expected %d" % (
                line_number, entry.get("seq"), expected_seq
            ))
        expected_seq += 1
        if entry.get("prev_hash") != previous:
            errors.append("line %d prev_hash mismatch" % line_number)
        if entry.get("entry_hash") != _entry_hash(entry):
            errors.append("line %d entry_hash mismatch" % line_number)
        previous = str(entry.get("entry_hash") or "")
        last_hash = previous
    return {
        "ok": not errors,
        "count": count,
        "last_hash": last_hash,
        "errors": errors,
    }


def commit_boundary(
    events: List[Dict[str, Any]],
    phase: str,
    gates: List[Dict[str, Any]],
    at: str = "",
) -> Dict[str, Any]:
    """Only emit ``boundary_committed`` when every gate is pass/skipped.

    An empty gate list is fail-closed: no evidence of a check is not a check.
    """
    checked = [dict(gate) for gate in (gates or [])]
    rejected = [
        str(gate.get("gate") or "?")
        for gate in checked
        if str(gate.get("status") or "") not in PASS_STATUSES
    ]
    if not checked:
        rejected = ["no_gates"]
    if rejected:
        append_event(
            events, REJECTED_KIND, phase=phase, at=at,
            payload={"gates_checked": len(checked), "rejected": rejected},
        )
        return {
            "ok": False, "phase": str(phase or ""), "rejected": rejected,
            "gates_checked": len(checked), "committed": False,
        }
    append_event(
        events, COMMITTED_KIND, phase=phase, at=at,
        payload={"gates_checked": len(checked)},
    )
    return {
        "ok": True, "phase": str(phase or ""), "rejected": [],
        "gates_checked": len(checked), "committed": True,
    }


def replay_boundaries(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Read-only projection of committed boundaries; a broken chain covers nothing."""
    verification = verify_events(events)
    if not verification["ok"]:
        return {
            "ok": False, "boundaries": [], "rejected": [], "last_committed": "",
            "errors": verification["errors"],
        }
    committed = [entry for entry in events if entry.get("kind") == COMMITTED_KIND]
    rejected = [entry for entry in events if entry.get("kind") == REJECTED_KIND]
    return {
        "ok": True,
        "boundaries": [str(entry.get("phase") or "") for entry in committed],
        "rejected": [dict(entry.get("payload") or {}) for entry in rejected],
        "last_committed": str(committed[-1].get("phase") or "") if committed else "",
        "errors": [],
        "note": "read-only replay; does not resume a run or cross a human gate",
    }


def read_events(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    handle_path = Path(path)
    if not handle_path.is_file():
        return rows
    for line_number, line in enumerate(
        handle_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            raise ValueError("events.ndjson line %d is not JSON" % line_number)
        if not isinstance(entry, dict):
            raise ValueError("events.ndjson line %d is not an object" % line_number)
        rows.append(entry)
    return rows


def write_events(path: Path, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Append only the new tail. Existing lines are verified, never rewritten."""
    handle_path = Path(path)
    existing = read_events(handle_path)
    verification = verify_events(existing)
    if not verification["ok"]:
        raise ValueError("existing event chain is broken: %s" % "; ".join(verification["errors"]))
    new_rows = [entry for entry in events or [] if int(entry.get("seq") or 0) > len(existing)]
    if new_rows and str(new_rows[0].get("prev_hash") or "") != verification["last_hash"]:
        raise ValueError("new events do not extend the existing chain")
    handle_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(handle_path), "a", encoding="utf-8", newline="\n") as handle:
        for entry in new_rows:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "path": handle_path.as_posix(),
        "existing": len(existing),
        "appended": len(new_rows),
        "total": len(existing) + len(new_rows),
    }


__all__ = [
    "EVENT_SCHEMA", "COMMITTED_KIND", "REJECTED_KIND", "PASS_STATUSES", "EVENT_FILENAME",
    "append_event", "verify_events", "commit_boundary", "replay_boundaries",
    "read_events", "write_events",
]

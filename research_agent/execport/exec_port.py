"""ExecPort: one registerable seam over the isolated execution faces (71-§4.4).

The platform already runs work on three real faces: deterministic local compute
on the platform interpreter (inprocess), the Harness² recursion on a separate
Python 3.12 bridge process (bridge), and model generation supplied by an
external host agent (host_agent). They exist and are authorized differently,
but there was no single object naming them, so "isolated execution units" in
the strategy figure stayed a narrative.

This module makes that boundary explicit and registerable WITHOUT rerouting
existing dispatch: callers still invoke the faces directly today (routing via
the port is roadmap). The port is the single place a new face (conda, docker,
remote) registers its kind, interpreter and authorization boundary, and the
read-only projection exposes the pool. It never starts, kills or schedules a
process and never creates Claim/EA/gate/signature.
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, List

EXEC_PORT_SCHEMA = "exec-port-0.2"

_BOUNDARY = (
    "execution-face pool with dispatch provenance: begin_dispatch gates routing "
    "through a registered face (an unregistered kind refuses to execute) and "
    "records provenance, but never starts, kills or schedules processes and "
    "creates no Claim/EA/gate/signature; execution authorization and audit "
    "semantics are unchanged"
)


class ExecPortError(RuntimeError):
    pass


@dataclass
class ExecFace:
    kind: str
    name: str
    interpreter: str
    entry: str
    isolation: str
    authorization: str


_FACES: Dict[str, ExecFace] = {}
_DISPATCH_LOG: List[Dict[str, Any]] = []
_DISPATCH_COUNTS: Dict[str, int] = {}
_DISPATCH_RING_LIMIT = 200


def register_face(face: ExecFace) -> None:
    kind = str(face.kind or "").strip()
    if not kind:
        raise ExecPortError("exec face kind must not be empty")
    if kind in _FACES:
        raise ExecPortError("exec face already registered: " + kind)
    _FACES[kind] = face


def registered_faces() -> List[str]:
    return sorted(_FACES)


def resolve(kind: str) -> ExecFace:
    if kind not in _FACES:
        raise ExecPortError(
            "unknown exec face: %s; registered: %s" % (kind, ", ".join(registered_faces()))
        )
    return _FACES[kind]


def describe() -> Dict[str, Any]:
    return {
        "schema_version": EXEC_PORT_SCHEMA,
        "faces": [asdict(_FACES[kind]) for kind in sorted(_FACES)],
        "dispatch_stats": dispatch_stats(),
        "boundary": _BOUNDARY,
    }


def begin_dispatch(kind: str, subject: str = "") -> Dict[str, Any]:
    """Gate + provenance for one dispatch onto a registered face.

    Routing through the port means an unregistered (or unknown) face refuses to
    execute — the gate is the point.  The port itself never starts, kills or
    schedules anything: callers still own the process/model lifecycle.
    """
    face = resolve(kind)
    _DISPATCH_COUNTS[kind] = _DISPATCH_COUNTS.get(kind, 0) + 1
    ticket = {
        "face": kind,
        "subject": str(subject or "")[:120],
        "entry": face.entry,
        "isolation": face.isolation,
        "status": "dispatched",
    }
    _DISPATCH_LOG.append(ticket)
    del _DISPATCH_LOG[:-_DISPATCH_RING_LIMIT]
    return dict(ticket)


def end_dispatch(ticket: Dict[str, Any], status: str = "completed") -> None:
    """Mark a dispatched ticket finished (completed/failed)."""
    if ticket:
        ticket["status"] = str(status or "completed")[:40]


def dispatch_stats() -> Dict[str, Any]:
    return {
        "counts": dict(sorted(_DISPATCH_COUNTS.items())),
        "recent": [dict(ticket) for ticket in _DISPATCH_LOG[-20:]],
    }


register_face(ExecFace(
    kind="inprocess",
    name="platform-local",
    interpreter="3.8",
    entry="research_agent/executable.py",
    isolation="same-process deterministic compute",
    authorization="local user environment; no network; no dependency install; "
                  "explicit human approval before execution",
))
register_face(ExecFace(
    kind="bridge",
    name="harness2-bridge",
    interpreter="3.12",
    entry="research_agent/rsi_harness2.py",
    isolation="separate Python 3.12 bridge process",
    authorization="Harness² (Apache-2.0) recursion; budget identity R=4k/P=3k and "
                  "10-point conformance enforced before record; platform keeps "
                  "criteria/ledger/human-sign only",
))
register_face(ExecFace(
    kind="host_agent",
    name="host-as-model",
    interpreter="host",
    entry="research_agent/host_model.py",
    isolation="external host agent process (Qoder/Claude Code/Codex/Zcode)",
    authorization="host supplies the model with zero external API key; hash-bound "
                  "one-time turns; no sign/approve/freeze/publish/export tool",
))
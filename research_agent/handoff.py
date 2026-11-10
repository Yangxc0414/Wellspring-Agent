"""File-drop transport for host-model turns, so an agent that can only read and write files can
supply model capability without speaking MCP.

``export_pending`` writes ``inbox/<turn_id>.json`` containing the request, the shape the answer must
have, and the hash the answer is bound to. ``import_answers`` reads ``outbox/<turn_id>.answer.json``
and records it through the *same* ledger path an in-process host uses, so shape validation, hash
binding, one-shot consumption and expiry are unchanged: this module adds a transport, not a second
set of rules.

The boundary is deliberate. A handoff directory can carry prose and JSON only: it cannot sign,
approve, freeze, close or export anything, and no gate decision is read from files the host wrote.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .host_model import ModelTurnLedger, STATUS_PENDING
from .storage import read_json, write_json_atomic

HANDOFF_SCHEMA = "host-handoff-0.1"
REQUEST_DIR = "inbox"
ANSWER_DIR = "outbox"
BOUNDARY = (
    "file-drop transport for model capability only: the ledger still validates shape and hash, an "
    "answer is consumed once, expiry still applies, and no claim, approval, closure or export "
    "decision can be made through a handoff directory"
)


def paths(outbox: Path) -> Dict[str, Path]:
    root = Path(outbox)
    return {
        "root": root,
        "inbox": root / REQUEST_DIR,
        "answer": root / ANSWER_DIR,
    }


def answer_filename(turn_id: str) -> str:
    return "%s.answer.json" % turn_id


def export_pending(
    ledger: ModelTurnLedger, outbox: Path, limit: int = 50
) -> Dict[str, Any]:
    """Write every pending turn into the inbox so an external agent can answer it offline."""
    dirs = paths(Path(outbox))
    dirs["inbox"].mkdir(parents=True, exist_ok=True)
    dirs["answer"].mkdir(parents=True, exist_ok=True)
    written: List[Dict[str, Any]] = []
    for turn in ledger.list_turns(status=STATUS_PENDING, limit=limit):
        target = dirs["inbox"] / ("%s.json" % turn["turn_id"])
        payload = {
            "schema_version": HANDOFF_SCHEMA,
            "turn_id": turn["turn_id"],
            "module": turn.get("module", ""),
            "purpose": turn.get("purpose", ""),
            "request": turn.get("request") or {},
            "expects": turn.get("expects") or {},
            "messages_sha256": turn.get("messages_sha256", ""),
            "expires_at": turn.get("expires_at", ""),
            "answer_file": "%s/%s" % (ANSWER_DIR, answer_filename(str(turn["turn_id"]))),
            "answer_format": (
                'write {"text": "<model output as a string>"} or '
                '{"json": <the object the schema asks for>}; nothing else is read'
            ),
            "boundary": BOUNDARY,
        }
        write_json_atomic(target, payload)
        written.append(
            {
                "turn_id": turn["turn_id"],
                "module": turn.get("module", ""),
                "request_file": str(target.relative_to(dirs["root"])),
                "answer_file": payload["answer_file"],
                "already_answered": (dirs["root"] / payload["answer_file"]).is_file(),
            }
        )
    return {
        "schema_version": HANDOFF_SCHEMA,
        "outbox": str(dirs["root"]),
        "exported": len(written),
        "turns": written,
        "next": "have the host write each answer_file, then run `handoff import --outbox %s`"
        % str(dirs["root"]),
        "boundary": BOUNDARY,
    }


def _answer_text(raw: Any) -> Optional[str]:
    """Accept a string answer or a JSON object answer, and nothing else."""
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("text"), str):
        return raw["text"]
    if "json" in raw:
        return json.dumps(raw["json"], ensure_ascii=False)
    return None


def import_answers(
    ledger: ModelTurnLedger,
    outbox: Path,
    host_label: str = "file-drop",
    project_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Record every answer file that exists, through the same ledger path an in-process host uses."""
    dirs = paths(Path(outbox))
    accepted: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    skipped: List[str] = []
    if not dirs["inbox"].is_dir():
        return {
            "schema_version": HANDOFF_SCHEMA,
            "outbox": str(dirs["root"]),
            "accepted": accepted,
            "rejected": rejected,
            "skipped": skipped,
            "error": "no %s/ directory yet; run `handoff export` first" % REQUEST_DIR,
            "boundary": BOUNDARY,
        }
    for request_file in sorted(dirs["inbox"].glob("MT-*.json")):
        turn_id = request_file.stem
        answer_file = dirs["answer"] / answer_filename(turn_id)
        if not answer_file.is_file():
            skipped.append(turn_id)
            continue
        raw = read_json(answer_file)
        text = _answer_text(raw)
        if text is None:
            rejected.append(
                {
                    "turn_id": turn_id,
                    "errors": ["answer must be {\"text\": string} or {\"json\": any}"],
                }
            )
            continue
        try:
            outcome = ledger.respond(
                turn_id, text, host_label=host_label, project_root=project_root
            )
        except Exception as exc:  # unknown, expired or already consumed turns
            rejected.append({"turn_id": turn_id, "errors": [str(exc)]})
            continue
        turn = outcome.get("turn") or {}
        if not outcome.get("accepted"):
            # the ledger owns the shape check and keeps the turn pending with a recorded rejection
            rejected.append(
                {
                    "turn_id": turn_id,
                    "errors": list(outcome.get("errors") or ["rejected by the ledger"]),
                    "reject_count": turn.get("reject_count"),
                }
            )
            continue
        accepted.append(
            {
                "turn_id": turn_id,
                "module": turn.get("module", ""),
                "status": turn.get("status", ""),
                "host_label": (turn.get("response") or {}).get("host_label", ""),
                "answer_file": str(answer_file.relative_to(dirs["root"])),
            }
        )
    return {
        "schema_version": HANDOFF_SCHEMA,
        "outbox": str(dirs["root"]),
        "accepted": accepted,
        "rejected": rejected,
        "skipped": skipped,
        "next": "re-run the deferred step: it replays recorded answers instead of asking again",
        "boundary": BOUNDARY,
    }


def handoff_status(ledger: ModelTurnLedger, outbox: Path) -> Dict[str, Any]:
    dirs = paths(Path(outbox))
    inbox = sorted(dirs["inbox"].glob("MT-*.json")) if dirs["inbox"].is_dir() else []
    answers = sorted(dirs["answer"].glob("MT-*.answer.json")) if dirs["answer"].is_dir() else []
    pending = ledger.list_turns(status=STATUS_PENDING, limit=200)
    return {
        "schema_version": HANDOFF_SCHEMA,
        "outbox": str(dirs["root"]),
        "ledger_counts": ledger.counts(),
        "pending_in_ledger": len(pending),
        "exported_requests": len(inbox),
        "answers_present": len(answers),
        "awaiting_answer": [
            str(path.stem) for path in inbox
            if not (dirs["answer"] / answer_filename(path.stem)).is_file()
        ],
        "boundary": BOUNDARY,
    }

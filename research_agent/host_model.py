"""Host-as-Model: hand a generation step to the calling agent instead of an API key.

The runtime never contacts a provider for a ``host_agent`` profile. It writes a durable
``ModelTurn`` request, raises ``ModelTurnPending`` so the caller surfaces the turn to its
host agent, and replays the stored answer when the same request is made again after the
host has responded. Submitted text is a capability output only: every downstream gate
(span-only evidence, citation whitelist, allowed result numbers, section and fixture
audit) still runs unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models.types import ModelTurnPending
from .paths import DEFAULT_HOST_MODEL_LEDGER_PATH
from .ports import ModelPort
from .project import ProjectError, _inside
from .storage import read_json, write_json_atomic

TURN_SCHEMA = "host-model-turn-0.1"
LEDGER_SCHEMA = "host-model-ledger-0.1"
DEFAULT_LEDGER_PATH = DEFAULT_HOST_MODEL_LEDGER_PATH
LEDGER_PATH_ENV = "RESEARCH_AGENT_HOST_MODEL_LEDGER"


def resolve_ledger_path(path: Optional[Path] = None) -> Path:
    """One resolver for every construction site, so writes and reads cannot split."""
    import os

    if path:
        return Path(path).expanduser()
    raw = os.environ.get(LEDGER_PATH_ENV, "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_LEDGER_PATH

STATUS_PENDING = "pending"
STATUS_RESPONDED = "responded"
STATUS_EXPIRED = "expired"
STATUS_VOIDED = "voided"

MAX_TURNS_KEPT = 300
MAX_RESPONSE_CHARS = 200_000
DEFAULT_TTL_MINUTES = 180

BOUNDARY = (
    "a host response is capability output, not evidence: it does not sign, approve, "
    "freeze, claim or publish anything, and it never bypasses manuscript audit, "
    "citation whitelists or result-number limits. host_label is self-reported and "
    "unverified."
)

_TURN_ID_RE = re.compile(r"^MT-[A-Za-z0-9]{6,40}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def canonical_messages_sha256(messages: List[Dict[str, str]]) -> str:
    payload = json.dumps(
        [
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in messages
        ],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _split_messages(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    system = "\n\n".join(
        str(m.get("content", "")) for m in messages if str(m.get("role", "")) == "system"
    ).strip()
    turns = [
        {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
        for m in messages
        if str(m.get("role", "")) != "system"
    ]
    return {"system": system, "turns": turns}


class ModelTurnLedger:
    """Durable pending/answered generation requests, keyed by request hash."""

    def __init__(self, path: Optional[Path] = None):
        self.path = resolve_ledger_path(path)

    # -- storage ---------------------------------------------------------
    def _load(self) -> Dict[str, Any]:
        payload = read_json(self.path)
        if not isinstance(payload, dict) or payload.get("schema_version") != LEDGER_SCHEMA:
            return {"schema_version": LEDGER_SCHEMA, "boundary": BOUNDARY, "turns": []}
        if not isinstance(payload.get("turns"), list):
            payload["turns"] = []
        return payload

    def _save(self, payload: Dict[str, Any]) -> None:
        payload["turns"] = payload["turns"][-MAX_TURNS_KEPT:]
        write_json_atomic(self.path, payload)

    # -- reads -----------------------------------------------------------
    def get(self, turn_id: str) -> Optional[Dict[str, Any]]:
        for turn in self._load()["turns"]:
            if turn.get("turn_id") == turn_id:
                return self._with_effective_status(turn)
        return None

    def find_by_hash(self, request_sha256: str, profile_id: str = "") -> Optional[Dict[str, Any]]:
        # Scoping by profile matters when two critic roles share one ledger: the same prompt sent
        # to two supplies must not be answered once and replayed for both.
        matches = [
            self._with_effective_status(turn)
            for turn in self._load()["turns"]
            if turn.get("messages_sha256") == request_sha256
            and (not profile_id or turn.get("profile_id") == profile_id)
        ]
        if not matches:
            return None
        for turn in reversed(matches):
            if turn.get("status") == STATUS_RESPONDED:
                return turn
        for turn in reversed(matches):
            # Only a live turn can be answered. Returning an expired one would deadlock the
            # caller: it raises pending, but submission to an expired turn is refused.
            if turn.get("status") == STATUS_PENDING:
                return turn
        return None

    def list_turns(
        self,
        status: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        turns = [
            self._with_effective_status(turn)
            for turn in self._load()["turns"]
        ]
        if status:
            turns = [turn for turn in turns if turn.get("status") == status]
        if module:
            turns = [turn for turn in turns if turn.get("module") == module]
        turns.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return turns[: max(1, min(int(limit), MAX_TURNS_KEPT))]

    def counts(self) -> Dict[str, int]:
        tally: Dict[str, int] = {}
        for turn in self._load()["turns"]:
            effective = self._with_effective_status(turn)
            tally[str(effective.get("status", "unknown"))] = tally.get(
                str(effective.get("status", "unknown")), 0
            ) + 1
        return tally

    # -- writes ----------------------------------------------------------
    def create(
        self,
        messages: List[Dict[str, str]],
        profile_id: str,
        module: str = "",
        purpose: str = "",
        expects: Optional[Dict[str, Any]] = None,
        sink: Optional[Dict[str, str]] = None,
        binding: Optional[Dict[str, str]] = None,
        ttl_minutes: int = DEFAULT_TTL_MINUTES,
    ) -> Dict[str, Any]:
        request_sha = canonical_messages_sha256(messages)
        created = _now()
        turn_id = "MT-" + uuid.uuid4().hex[:12]
        turn = {
            "turn_id": turn_id,
            "schema_version": TURN_SCHEMA,
            "status": STATUS_PENDING,
            "profile_id": str(profile_id),
            "module": str(module or ""),
            "purpose": str(purpose or ""),
            "messages_sha256": request_sha,
            "request": _split_messages(messages),
            "expects": _normalize_expects(expects),
            "sink": dict(sink or {}) or None,
            "binding": dict(binding or {}),
            "created_at": _iso(created),
            "expires_at": _iso(created + timedelta(minutes=max(1, int(ttl_minutes)))),
            "response": None,
            "receipt": None,
        }
        payload = self._load()
        payload["turns"].append(turn)
        self._save(payload)
        return dict(turn)

    def respond(
        self,
        turn_id: str,
        text: str,
        host_label: str = "",
        project_root: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Validate and record the host answer; a rejected answer leaves the turn pending."""
        if not _TURN_ID_RE.match(turn_id or ""):
            raise ValueError("invalid turn_id")
        payload = self._load()
        index = next(
            (i for i, turn in enumerate(payload["turns"]) if turn.get("turn_id") == turn_id),
            -1,
        )
        if index < 0:
            raise ValueError("unknown turn: " + turn_id)
        turn = payload["turns"][index]
        effective = self._with_effective_status(turn)
        if effective.get("status") == STATUS_EXPIRED:
            raise ValueError("turn %s expired at %s" % (turn_id, effective.get("expires_at")))
        if effective.get("status") == STATUS_RESPONDED:
            raise ValueError(
                "turn %s is already responded; host turns are consumed once" % turn_id
            )

        body = str(text or "")
        errors = self._validate(turn, body)
        if errors:
            attempts = int(turn.get("reject_count", 0)) + 1
            turn["reject_count"] = attempts
            turn["last_rejection"] = {
                "errors": errors,
                "at": _iso(_now()),
                "text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            }
            payload["turns"][index] = turn
            self._save(payload)
            return {"accepted": False, "turn": turn, "errors": errors}

        written = self._write_sink(turn, body, project_root)
        submitted_at = _iso(_now())
        turn["status"] = STATUS_RESPONDED
        turn["response"] = {
            "text": body,
            "text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "host_label": _clean_label(host_label),
            "submitted_at": submitted_at,
            "chars": len(body),
        }
        turn["receipt"] = {
            "schema_version": "host-model-receipt-0.1",
            "turn_id": turn_id,
            "module": turn.get("module", ""),
            "purpose": turn.get("purpose", ""),
            "messages_sha256": turn.get("messages_sha256", ""),
            "text_sha256": turn["response"]["text_sha256"],
            "host_label": turn["response"]["host_label"],
            "submitted_at": submitted_at,
            "sink": written,
            "boundary": BOUNDARY,
        }
        payload["turns"][index] = turn
        self._save(payload)
        return {"accepted": True, "turn": turn, "receipt": turn["receipt"], "errors": []}

    def void(self, turn_id: str, reason: str) -> Dict[str, Any]:
        """Invalidate an answered turn so the stage asks again.

        Without this, a structurally-valid but semantically wrong answer is replayed forever
        by request-hash reuse, and the only recovery is editing files by hand. Voiding is a
        demotion: it can never admit a capability, so it needs no human gate — but it does
        require a reason, and the original answer stays in the record for audit.
        """
        if not str(reason or "").strip():
            raise ValueError("voiding a turn requires a reason")
        payload = self._load()
        for index, turn in enumerate(payload["turns"]):
            if turn.get("turn_id") != turn_id:
                continue
            turn["voided"] = {
                "reason": str(reason).strip()[:400],
                "at": _iso(_now()),
                "previous_text_sha256": (turn.get("response") or {}).get("text_sha256", ""),
            }
            turn["status"] = STATUS_VOIDED
            payload["turns"][index] = turn
            self._save(payload)
            return dict(turn)
        raise ValueError("unknown turn: " + turn_id)

    def cancel(self, turn_id: str, reason: str = "") -> Dict[str, Any]:
        payload = self._load()
        for index, turn in enumerate(payload["turns"]):
            if turn.get("turn_id") != turn_id:
                continue
            if turn.get("status") == STATUS_RESPONDED:
                raise ValueError("turn %s is already responded" % turn_id)
            turn["status"] = "cancelled"
            turn["cancelled_reason"] = str(reason or "")[:300]
            payload["turns"][index] = turn
            self._save(payload)
            return dict(turn)
        raise ValueError("unknown turn: " + turn_id)

    # -- internals -------------------------------------------------------
    @staticmethod
    def _with_effective_status(turn: Dict[str, Any]) -> Dict[str, Any]:
        if turn.get("status") != STATUS_PENDING:
            return dict(turn)
        expires = _parse_iso(str(turn.get("expires_at", "")))
        if expires is not None and _now() > expires:
            stamped = dict(turn)
            stamped["status"] = STATUS_EXPIRED
            return stamped
        return dict(turn)

    @staticmethod
    def _validate(turn: Dict[str, Any], body: str) -> List[str]:
        errors: List[str] = []
        if not body.strip():
            errors.append("empty response")
        if len(body) > MAX_RESPONSE_CHARS:
            errors.append("response exceeds %d chars" % MAX_RESPONSE_CHARS)
        expects = turn.get("expects") or {}
        if expects.get("json"):
            match = re.search(r"\{.*\}|\[.*\]", body, re.DOTALL)
            value: Any = None
            try:
                value = json.loads(match.group(0)) if match else None
            except ValueError:
                value = None
            if value is None:
                errors.append("response must contain a JSON object or array")
            else:
                required = list(expects.get("require_keys") or [])
                container = value if isinstance(value, dict) else (
                    value[0] if isinstance(value, list) and value and isinstance(value[0], dict) else {}
                )
                if required and isinstance(container, dict):
                    missing = [key for key in required if key not in container]
                    if missing:
                        errors.append("missing required keys: " + ", ".join(missing))
                if expects.get("object") is True and not isinstance(value, dict):
                    errors.append("expected a JSON object")
                if expects.get("array_field"):
                    field = str(expects.get("array_field"))
                    if not isinstance(value, dict) or not isinstance(value.get(field), list):
                        errors.append("expected JSON object with array field '%s'" % field)
                    elif expects.get("min_items") and len(value[field]) < int(expects["min_items"]):
                        errors.append("field '%s' needs >= %d items" % (field, int(expects["min_items"])))
        for needle in list(expects.get("forbid_substrings") or []):
            if str(needle) and str(needle).lower() in body.lower():
                errors.append("response contains forbidden text: " + str(needle))
        return errors

    @staticmethod
    def _write_sink(
        turn: Dict[str, Any], body: str, project_root: Optional[Path]
    ) -> Optional[Dict[str, str]]:
        sink = turn.get("sink")
        if not sink or not project_root:
            return None
        relpath = str(sink.get("relpath") or "")
        if not relpath:
            return None
        try:
            target = _inside(Path(project_root), Path(project_root) / relpath)
        except ProjectError as exc:
            raise ValueError(str(exc))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        return {"relpath": relpath, "text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}


def _normalize_expects(expects: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = dict(expects or {})
    return {
        "json": bool(raw.get("json", False)),
        "object": bool(raw.get("object", False)),
        "array_field": str(raw.get("array_field") or ""),
        "min_items": int(raw.get("min_items") or 0),
        "require_keys": [str(key) for key in (raw.get("require_keys") or [])][:20],
        "forbid_substrings": [str(item) for item in (raw.get("forbid_substrings") or [])][:20],
    }


def _clean_label(value: str) -> str:
    label = re.sub(r"[\x00-\x1f]+", " ", str(value or "")).strip()
    return (label or "unspecified-host")[:80]


class HostModelPort(ModelPort):
    """A ModelPort backed by the host agent instead of a provider endpoint."""

    def __init__(
        self,
        ledger: ModelTurnLedger,
        profile_id: str,
        module: str = "",
        purpose: str = "",
        expects: Optional[Dict[str, Any]] = None,
        sink: Optional[Dict[str, str]] = None,
        binding: Optional[Dict[str, str]] = None,
        wait_seconds: int = 0,
        poll_interval: float = 2.0,
        provider_id: str = "host",
        provider_kind: str = "host_agent",
        model_name: str = "",
    ):
        self.ledger = ledger
        self.profile_id = str(profile_id)
        self.module = str(module or "")
        self.purpose = str(purpose or "")
        self.expects = dict(expects or {})
        self.sink = dict(sink or {}) or None
        self.binding = dict(binding or {})
        self.wait_seconds = max(0, int(wait_seconds))
        self.poll_interval = max(0.5, float(poll_interval))
        self.model_id = "host-agent:" + self.profile_id
        self.provider_id = str(provider_id or "host")
        self.provider_kind = str(provider_kind or "host_agent")
        # Two host profiles naming the same model are one supply wearing two configs, so the
        # panel needs the model the host actually runs, not only the profile row.
        self.model_name = str(model_name or "") or self.model_id
        self.turn_ids: List[str] = []

    def complete(self, messages: List[Dict[str, str]], json_mode: bool = True) -> str:
        request_sha = canonical_messages_sha256(messages)
        turn = self.ledger.find_by_hash(request_sha, self.profile_id)
        if turn is None:
            expects = dict(self.expects)
            expects.setdefault("json", bool(json_mode))
            turn = self.ledger.create(
                messages=messages,
                profile_id=self.profile_id,
                module=self.module,
                purpose=self.purpose,
                expects=expects,
                sink=self.sink,
                binding=self.binding,
            )
        if turn.get("status") == STATUS_RESPONDED:
            self._track(turn)
            return str((turn.get("response") or {}).get("text", ""))
        # A pending turn belongs to this role too: attribution has to know which answers are owed.
        self._track(turn)
        deadline = time.monotonic() + self.wait_seconds
        while self.wait_seconds and time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            refreshed = self.ledger.get(str(turn.get("turn_id", "")))
            if refreshed and refreshed.get("status") == STATUS_RESPONDED:
                self._track(refreshed)
                return str((refreshed.get("response") or {}).get("text", ""))
        raise ModelTurnPending(
            "awaiting host agent model output; respond to turn %s "
            "(module=%s purpose=%s) with research_model_respond, then re-run the step"
            % (turn.get("turn_id"), self.module or "?", self.purpose or "?"),
            turn_id=str(turn.get("turn_id", "")),
            messages_sha256=request_sha,
        )

    def _track(self, turn: Dict[str, Any]) -> None:
        """Remember which turns this role consumed, so answers can be attributed after the fact."""
        turn_id = str(turn.get("turn_id") or "")
        if turn_id and turn_id not in self.turn_ids:
            self.turn_ids.append(turn_id)

    def answered_by(self) -> List[str]:
        """Self-reported labels of the host agents that actually answered this role's turns."""
        labels: List[str] = []
        for turn_id in self.turn_ids:
            turn = self.ledger.get(turn_id) or {}
            label = str((turn.get("response") or {}).get("host_label") or "").strip()
            if label and label not in labels:
                labels.append(label)
        return labels


def host_turn_requests(
    ledger: ModelTurnLedger,
    status: Optional[str] = None,
    module: Optional[str] = None,
    limit: int = 10,
    include_request: bool = True,
) -> Dict[str, Any]:
    """The queue a host agent reads to answer turns, with the exact prompt to answer."""
    turns = ledger.list_turns(status=status, module=module, limit=limit)
    payload = []
    for turn in turns:
        item = {
            "turn_id": turn.get("turn_id"),
            "status": turn.get("status"),
            "module": turn.get("module"),
            "purpose": turn.get("purpose"),
            "profile_id": turn.get("profile_id"),
            "messages_sha256": turn.get("messages_sha256"),
            "expects": turn.get("expects"),
            "binding": turn.get("binding") or {},
            "created_at": turn.get("created_at"),
            "expires_at": turn.get("expires_at"),
            "reject_count": turn.get("reject_count", 0),
            "last_rejection": turn.get("last_rejection"),
            "receipt": turn.get("receipt"),
        }
        if include_request:
            item["request"] = turn.get("request")
        payload.append(item)
    return {
        "schema_version": "host-model-requests-0.1",
        "counts": ledger.counts(),
        "returned": len(payload),
        "turns": payload,
        "how_to_respond": (
            "produce the output for each pending turn with your own model, then call "
            "research_model_respond(turn_id, text, host_label). The response is validated "
            "against the turn's declared shape and bound to the request hash; it is "
            "capability output, so manuscript audit, citation whitelists and "
            "result-number limits still run. Re-run the deferred step afterwards: it "
            "replays the stored answer instead of asking again."
        ),
        "boundary": BOUNDARY,
    }


def host_model_summary(ledger: ModelTurnLedger, limit: int = 20) -> Dict[str, Any]:
    """Read-only view of the handoff queue for agents and the workbench."""
    turns = ledger.list_turns(limit=limit)
    pending = [turn for turn in turns if turn.get("status") == STATUS_PENDING]
    return {
        "schema_version": "host-model-status-0.1",
        "path": str(ledger.path),
        "counts": ledger.counts(),
        "pending": len(pending),
        "pending_turn_ids": [turn.get("turn_id") for turn in pending],
        "turns": [
            {
                "turn_id": turn.get("turn_id"),
                "status": turn.get("status"),
                "module": turn.get("module"),
                "purpose": turn.get("purpose"),
                "profile_id": turn.get("profile_id"),
                "messages_sha256": turn.get("messages_sha256"),
                "created_at": turn.get("created_at"),
                "expires_at": turn.get("expires_at"),
                "reject_count": turn.get("reject_count", 0),
                "binding": turn.get("binding") or {},
                "sink": turn.get("sink"),
                "receipt": turn.get("receipt"),
            }
            for turn in turns
        ],
        "boundary": BOUNDARY,
    }

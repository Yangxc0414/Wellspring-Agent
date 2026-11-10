"""Timestamp, run-id and deterministic fingerprint helpers."""

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id(prefix: str = "ORCH") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return "%s-%s-%s" % (prefix, stamp, uuid.uuid4().hex[:6])


def fingerprint(payload: Dict[str, Any]) -> str:
    import json

    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


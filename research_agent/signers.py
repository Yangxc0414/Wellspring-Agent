"""Local signer identities and HMAC signatures.

This is a local possession proof, not PKI and not a legally recognized
signature. A signer secret stays in a local store with restrictive permissions;
signatures bind the export manifest bytes, human reason and submission=false.
"""

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import DEFAULT_SIGNER_STORE_PATH
from .storage import JsonStoreError, read_json, write_json_atomic

SIGNER_SCHEMA = "local-signers-0.1"
SIGNATURE_SCHEME = "hmac-sha256-local"


class SignerError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canonical_payload(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")


class SignerStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or DEFAULT_SIGNER_STORE_PATH)
        self.signers: List[Dict[str, Any]] = []
        self._load()

    @property
    def boundary(self) -> str:
        return (
            "local HMAC identity only: proves possession of a local signer secret, "
            "not PKI, legal identity, or peer review; runtime exposes no signer endpoint"
        )

    def _load(self) -> None:
        try:
            payload = read_json(self.path)
        except JsonStoreError as exc:
            raise SignerError(str(exc))
        if payload is None:
            return
        if not isinstance(payload, dict) or payload.get("schema_version") != SIGNER_SCHEMA:
            raise SignerError("unsupported signer store schema")
        entries = payload.get("signers")
        if not isinstance(entries, list):
            raise SignerError("signer store must contain a signers list")
        for item in entries:
            if not isinstance(item, dict):
                continue
            if not item.get("signer_id") or not item.get("key_id") or not item.get("secret_hex"):
                raise SignerError("signer entry is missing id/key/secret")
            self.signers.append(item)

    def _save(self) -> None:
        write_json_atomic(self.path, {
            "schema_version": SIGNER_SCHEMA,
            "updated_at": _now(),
            "signers": self.signers,
            "boundary": self.boundary,
        })
        try:
            os.chmod(str(self.path), 0o600)
        except OSError:
            pass

    @staticmethod
    def _masked(item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "signer_id": item["signer_id"],
            "name": item["name"],
            "key_id": item["key_id"],
            "created_at": item["created_at"],
            "active": bool(item.get("active", True)),
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "schema_version": SIGNER_SCHEMA,
            "count": len(self.signers),
            "signers": [self._masked(item) for item in self.signers],
            "boundary": self.boundary,
        }

    def create(self, name: str) -> Dict[str, Any]:
        label = (name or "").strip()
        if not label:
            raise SignerError("signer name is required")
        item = {
            "signer_id": "SIGNER-" + uuid.uuid4().hex[:10],
            "name": label[:80],
            "key_id": "KEY-" + uuid.uuid4().hex[:10],
            "secret_hex": secrets.token_hex(32),
            "created_at": _now(),
            "active": True,
        }
        self.signers.append(item)
        self._save()
        return self._masked(item)

    def get(self, signer_id: str) -> Dict[str, Any]:
        item = next(
            (entry for entry in self.signers
             if entry.get("signer_id") == signer_id and entry.get("active", True)),
            None,
        )
        if item is None:
            raise SignerError("active signer not found: " + signer_id)
        return item

    def sign(self, signer_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        entry = self.get(signer_id)
        data = canonical_payload(payload)
        return {
            "signer_id": entry["signer_id"],
            "signer_key_id": entry["key_id"],
            "signature_scheme": SIGNATURE_SCHEME,
            "signed_payload_sha256": hashlib.sha256(data).hexdigest(),
            "signature_hmac": hmac.new(
                bytes.fromhex(entry["secret_hex"]), data, hashlib.sha256
            ).hexdigest(),
        }

    def verify(
        self,
        signer_id: str,
        key_id: str,
        payload: Dict[str, Any],
        signature_hmac: str,
    ) -> bool:
        entry = self.get(signer_id)
        if entry.get("key_id") != key_id:
            return False
        data = canonical_payload(payload)
        expected = hmac.new(
            bytes.fromhex(entry["secret_hex"]), data, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, str(signature_hmac))

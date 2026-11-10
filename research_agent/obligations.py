"""Append-only closure obligations.

A closure report is a snapshot; obligations are the durable ledger of unresolved
checks. They are never deleted: an obligation can be open, resolved, or reopened
if the same failure reappears in a later report.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import read_json, write_json_atomic

OBLIGATION_SCHEMA = "closure-obligations-0.1"
BOUNDARY = (
    "closure obligations are an audit ledger; unresolved items never auto-resolve, "
    "only explicit human resolve/waive closes them; evidence hashes prove file identity, "
    "not scientific truth"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


class ObligationLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: List[Dict[str, Any]] = []
        if self.path.is_file():
            payload = read_json(self.path)
            if isinstance(payload, dict) and isinstance(payload.get("obligations"), list):
                self.entries = [
                    item for item in payload["obligations"] if isinstance(item, dict)
                ]

    def _save(self) -> None:
        write_json_atomic(
            self.path,
            {
                "schema_version": OBLIGATION_SCHEMA,
                "updated_at": _now(),
                "summary": self.summary(),
                "obligations": self.entries,
                "boundary": BOUNDARY,
            },
        )

    def summary(self) -> Dict[str, Any]:
        open_items = [item for item in self.entries if item.get("status") == "open"]
        reopened = [item for item in self.entries if item.get("status") == "reopened"]
        unverified = [
            item for item in self.entries
            if item.get("status") == "unverified_disappearance"
        ]
        resolved = [item for item in self.entries if item.get("status") == "resolved"]
        waived = [item for item in self.entries if item.get("status") == "waived"]
        return {
            "total": len(self.entries),
            "open": len(open_items),
            "reopened": len(reopened),
            "unverified_disappearance": len(unverified),
            "resolved": len(resolved),
            "waived": len(waived),
            "status": "blocked" if open_items or reopened or unverified else "clear",
        }

    def reconcile(self, report: Dict[str, Any]) -> Dict[str, Any]:
        report_id = str(report.get("report_id") or "")
        current: Dict[str, Dict[str, str]] = {}
        for check in report.get("checks") or []:
            if not isinstance(check, dict) or check.get("status") == "pass":
                continue
            key = "check:" + str(check.get("name") or "")
            current[key] = {
                "kind": "closure_check",
                "label": str(check.get("name") or ""),
                "detail": str(check.get("detail") or ""),
            }
        for item in report.get("unresolved") or []:
            key = "unresolved:" + str(item)
            current[key] = {
                "kind": "unresolved_slot" if str(item) != "limitation" else "limitation",
                "label": str(item),
                "detail": "closure report still lists this unresolved item",
            }
        by_key = {str(item.get("key")): item for item in self.entries}
        now = _now()
        for key, payload in current.items():
            entry = by_key.get(key)
            if entry is None:
                entry = {
                    "obligation_id": "OBL-" + _sha256(key)[:10],
                    "key": key,
                    "kind": payload["kind"],
                    "label": payload["label"],
                    "detail": payload["detail"],
                    "status": "open",
                    "first_seen": now,
                    "last_seen": now,
                    "occurrences": 1,
                    "report_ids": [report_id],
                    "history": [
                        {"at": now, "report_id": report_id, "status": "open", "detail": payload["detail"]}
                    ],
                }
                self.entries.append(entry)
                by_key[key] = entry
                continue
            if entry.get("status") in ("resolved", "waived", "unverified_disappearance"):
                entry["status"] = "reopened"
                entry["reopened_at"] = now
                entry["resolved_at"] = ""
                entry["waived_at"] = ""
                entry["unverified_at"] = ""
            entry["detail"] = payload["detail"]
            entry["last_seen"] = now
            entry["occurrences"] = int(entry.get("occurrences", 0)) + 1
            reports = list(entry.get("report_ids") or [])
            if report_id and report_id not in reports:
                reports.append(report_id)
            entry["report_ids"] = reports[-30:]
            history = list(entry.get("history") or [])
            history.append(
                {
                    "at": now,
                    "report_id": report_id,
                    "status": entry["status"],
                    "detail": payload["detail"],
                }
            )
            entry["history"] = history
        for entry in self.entries:
            if str(entry.get("key")) in current:
                continue
            if entry.get("status") in ("open", "reopened"):
                entry["status"] = "unverified_disappearance"
                entry["unverified_at"] = now
                entry["unverified_by_report_id"] = report_id
                history = list(entry.get("history") or [])
                history.append(
                    {
                        "at": now,
                        "report_id": report_id,
                        "status": "unverified_disappearance",
                        "detail": (
                            "item is absent from the current report; explicit human "
                            "resolve/waive is required"
                        ),
                    }
                )
                entry["history"] = history
        self._save()
        return self.snapshot()

    def resolve(
        self,
        obligation_ref: str,
        human_reason: str,
        evidence_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        return self._close(obligation_ref, human_reason, evidence_path, "resolve")

    def waive(self, obligation_ref: str, human_reason: str) -> Dict[str, Any]:
        return self._close(obligation_ref, human_reason, None, "waive")

    def _close(
        self,
        obligation_ref: str,
        human_reason: str,
        evidence_path: Optional[Path],
        kind: str,
    ) -> Dict[str, Any]:
        reason = (human_reason or "").strip()
        if len(reason) < 8:
            raise ValueError("human_reason must be at least 8 characters")
        entry = next(
            (
                item for item in self.entries
                if obligation_ref in (item.get("obligation_id"), item.get("key"))
            ),
            None,
        )
        if entry is None:
            raise KeyError("obligation not found: %s" % obligation_ref)
        if entry.get("status") in ("resolved", "waived"):
            raise ValueError(
                "obligation is already %s: %s" % (entry.get("status"), obligation_ref)
            )
        evidence_hash = ""
        evidence_text = ""
        if kind == "resolve":
            if evidence_path is None:
                raise ValueError("resolve requires an evidence file")
            evidence = Path(evidence_path)
            if not evidence.is_file():
                raise FileNotFoundError("evidence file not found: %s" % evidence)
            evidence_text = str(evidence)
            evidence_hash = hashlib.sha256(evidence.read_bytes()).hexdigest()
        now = _now()
        entry["status"] = "resolved" if kind == "resolve" else "waived"
        entry["resolution_kind"] = kind
        entry["closed_at"] = now
        entry["closed_by"] = "human"
        entry["human_reason"] = reason
        if kind == "resolve":
            entry["resolution_evidence_path"] = evidence_text
            entry["resolution_evidence_sha256"] = evidence_hash
        else:
            entry["waived_at"] = now
            entry["resolution_evidence_path"] = ""
            entry["resolution_evidence_sha256"] = ""
        history = list(entry.get("history") or [])
        history.append(
            {
                "at": now,
                "report_id": "",
                "status": entry["status"],
                "detail": "%s: %s" % (kind, reason),
            }
        )
        entry["history"] = history
        self._save()
        return {
            "path": str(self.path),
            "obligation": dict(entry),
            "summary": self.summary(),
            "boundary": BOUNDARY,
        }

    def snapshot(self) -> Dict[str, Any]:
        return {
            "schema_version": OBLIGATION_SCHEMA,
            "path": str(self.path),
            "summary": self.summary(),
            "obligations": [dict(item) for item in self.entries],
            "boundary": BOUNDARY,
        }

"""Map local claim-registry evidence rows to a whitelisted external claim audit.

The external scientific-writing skill stays outside this repository. This
adapter only builds a temporary source manifest + claim CSV + marker manuscript
from existing local evidence rows, runs the known audit_claims.py, and returns
its structured report. It never changes claims, closure or signatures.
"""

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from .external_writing_gate import ExternalWritingGateError, _skill_root

GATE_TOOL = "scientific-writing.audit_claims"
EXTERNAL_TOOL = "audit_claims"
BOUNDARY = (
    "read-only external MIT claim audit over a temporary derived package; "
    "no claim/evidence/closure/signature mutation and no dependency installation"
)
_CLAIM_MARKER_RE = re.compile(r"\[claim:(C[0-9]{3,8})\]")
_EVIDENCE_MARKER_RE = re.compile(r"\[evidence:((?:E[0-9]{3,8})(?:\s*,\s*E[0-9]{3,8})*)\]")
_CITATION_MARKER_RE = re.compile(r"\[@(E[0-9]{3,8})\]")
_EXISTING_BRACKET_RE = re.compile(r"\[[A-Za-z0-9_.:-]+\]")
_NUMERIC_RE = re.compile(r"(?<![A-Za-z])(?:[<>]=?\s*)?[0-9]+(?:\.[0-9]+)?%?")


def _claim_hash(line: str) -> str:
    text = _CLAIM_MARKER_RE.sub("", line)
    text = _EVIDENCE_MARKER_RE.sub("", text)
    text = _CITATION_MARKER_RE.sub("", text)
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


def _span_records(
    claim_registry: Dict[str, Any], literature: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    spans = {
        str(item.get("span_id")): item
        for item in (literature.get("spans") or [])
        if isinstance(item, dict) and item.get("span_id")
    }
    records: Dict[str, Dict[str, Any]] = {}
    for entry in claim_registry.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        for row in entry.get("evidence_rows") or []:
            if not isinstance(row, dict):
                continue
            span_id = str(row.get("span_id") or "")
            quote = str(row.get("quote") or "")
            if not span_id or not quote:
                continue
            span = spans.get(span_id) or {}
            records[span_id] = {
                "span_id": span_id,
                "source_id": str(span.get("source_id") or row.get("source_id") or ""),
                "quote": quote[:800],
                "verified": str(row.get("status") or "") == "verified_anchor",
            }
    return records


def build_external_claim_package(
    claim_registry: Dict[str, Any], literature: Dict[str, Any]
) -> Dict[str, Any]:
    records = _span_records(claim_registry, literature)
    evidence_ids = {
        span_id: "E%03d" % (index + 1)
        for index, span_id in enumerate(sorted(records))
    }
    claims: List[Dict[str, str]] = []
    claim_lines: List[str] = []
    for entry in claim_registry.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        sentence = _EXISTING_BRACKET_RE.sub(
            "", str(entry.get("sentence") or "")
        ).strip()
        if not sentence:
            continue
        rows = [
            row for row in (entry.get("evidence_rows") or [])
            if isinstance(row, dict)
        ]
        ids: List[str] = []
        for row in rows:
            span_id = str(row.get("span_id") or "")
            if span_id in evidence_ids and evidence_ids[span_id] not in ids:
                ids.append(evidence_ids[span_id])
        if not ids:
            continue
        claim_id = "C%03d" % (len(claims) + 1)
        line = "%s [claim:%s] [evidence:%s]" % (sentence, claim_id, ",".join(ids))
        kind = "numeric" if _NUMERIC_RE.search(sentence) else "factual"
        verified = all(
            records.get(str(row.get("span_id") or ""), {}).get("verified")
            for row in rows
            if str(row.get("span_id") or "") in records
        )
        claims.append({
            "claim_id": claim_id,
            "section": str(entry.get("section") or "section"),
            "claim_kind": kind,
            "claim_text_sha256": _claim_hash(line),
            "evidence_ids": ";".join(ids),
            "verification_status": "verified" if verified else "unverified",
            "uncertainty": "not_estimated",
            "analysis_intent": "confirmatory",
        })
        claim_lines.append(line)
    sources = []
    for span_id, evidence_id in evidence_ids.items():
        record = records[span_id]
        sources.append({
            "authors": [],
            "confidentiality": "public",
            "evidence_id": evidence_id,
            "identifiers": {"doi": "", "isbn": "", "pmcid": "", "pmid": "", "url": ""},
            "locator": span_id,
            "source_type": "other",
            "title": record["quote"][:200],
            "verification": {
                "source_opened": bool(record["verified"]),
                "status": "verified" if record["verified"] else "unverified",
                "verified_by": "local-span-anchor",
                "verified_on": "2026-10-28",
            },
            "year": None,
        })
    return {
        "claims": claims,
        "claim_lines": claim_lines,
        "sources": sources,
        "claim_count": len(claims),
        "source_count": len(sources),
    }


def run_claim_audit(
    claim_registry: Dict[str, Any],
    literature: Dict[str, Any],
    skill_root: Optional[Path] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    root = _skill_root(skill_root)
    script = root / "skills" / "scientific-writing" / "scripts" / "audit_claims.py"
    if not script.is_file():
        raise ExternalWritingGateError(
            "whitelisted audit_claims.py not found under: " + str(root)
        )
    package = build_external_claim_package(claim_registry, literature)
    with tempfile.TemporaryDirectory(prefix="external-claim-audit-") as temp:
        temp = Path(temp)
        manuscript = temp / "claims.md"
        claims_csv = temp / "claims.csv"
        sources_json = temp / "sources.json"
        manuscript.write_text(
            "\n".join(package["claim_lines"]) + "\n", encoding="utf-8"
        )
        fields = (
            "claim_id,section,claim_kind,claim_text_sha256,evidence_ids,"
            "verification_status,uncertainty,analysis_intent"
        )
        rows = [fields]
        for item in package["claims"]:
            rows.append(",".join(
                str(item[key]) for key in (
                    "claim_id", "section", "claim_kind", "claim_text_sha256",
                    "evidence_ids", "verification_status", "uncertainty",
                    "analysis_intent",
                )
            ))
        claims_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
        sources_json.write_text(
            json.dumps(
                {"schema_version": "1.0", "sources": package["sources"]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(manuscript),
                    str(claims_csv),
                    str(sources_json),
                ],
                cwd=str(script.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=max(1, min(int(timeout), 300)),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExternalWritingGateError(
                "external claim audit failed to start: " + str(exc)
            )
        try:
            payload = json.loads(completed.stdout)
        except (TypeError, ValueError):
            raise ExternalWritingGateError(
                "external claim audit returned non-JSON output: "
                + (completed.stderr or completed.stdout or "")[:400]
            )
        if not isinstance(payload, dict) or payload.get("tool") not in (
            EXTERNAL_TOOL,
            GATE_TOOL,
        ):
            raise ExternalWritingGateError(
                "external claim audit returned an unexpected report"
            )
        issues = [
            item for item in (payload.get("issues") or [])
            if isinstance(item, dict)
        ]
        status = (
            "blocked" if payload.get("status") == "fail"
            else "attention" if issues else "ready"
        )
        return {
            "schema_version": "external-claim-audit-0.1",
            "tool": GATE_TOOL,
            "external_tool": str(payload.get("tool") or ""),
            "skill_root": str(root),
            "status": status,
            "external_status": payload.get("status"),
            "summary": payload.get("summary") or {},
            "issues": issues[:40],
            "claim_count": package["claim_count"],
            "source_count": package["source_count"],
            "exit_code": completed.returncode,
            "boundary": BOUNDARY,
        }

"""Explicit stage/gate control for review and strict research flows.

Review mode preserves the demo/review-bundle behavior. Strict mode treats
Q0/G1/G2 as execution guards: the pipeline stops before the next stage and
leaves a resumable artifact instead of running ahead and reporting gates later.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .contracts import IdeaCard, LiteratureResult

FLOW_MODES = ("review", "strict")


class FlowError(ValueError):
    pass


def validate_flow_mode(mode: str) -> str:
    value = str(mode or "review").strip().lower()
    if value not in FLOW_MODES:
        raise FlowError("flow_mode must be review or strict")
    return value


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


DESIGN_HASH_FIELDS = (
    "question",
    "hypothesis",
    "baseline",
    "primary_metric",
    "controls",
    "seeds",
    "budget",
    "stopping_rule",
    "evidence_refs",
    "idea_id",
)


def design_sha256(design: Dict[str, Any]) -> str:
    payload = {key: design.get(key) for key in DESIGN_HASH_FIELDS}
    return sha256_json(payload)


def q0_decision(literature: LiteratureResult) -> Dict[str, str]:
    hits = list(literature.hits or [])
    spans = list(literature.spans or [])
    full_text = sum(1 for hit in hits if getattr(hit, "full_text", False))
    saturation = literature.brief.saturation if literature.brief else "unknown"
    if not spans:
        return {
            "gate": "Q0",
            "status": "blocked",
            "reason": "no locatable span; abstract-only sources are clues, not evidence",
        }
    if full_text < 1:
        return {
            "gate": "Q0",
            "status": "blocked",
            "reason": "no full-text source; span-only evidence requires at least one full text",
        }
    if saturation == "insufficient":
        return {
            "gate": "Q0",
            "status": "blocked",
            "reason": "coverage is insufficient (%d full-text, %d spans); add sources before S2"
            % (full_text, len(spans)),
        }
    return {
        "gate": "Q0",
        "status": "pass",
        "reason": "%d full-text source(s), %d span(s), coverage=%s"
        % (full_text, len(spans), saturation),
    }


def load_g1_decision(path: Path, candidates: List[IdeaCard]) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FlowError("G1 decision file not found: " + str(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FlowError("G1 decision is not readable JSON: %s" % exc)
    if not isinstance(value, dict):
        raise FlowError("G1 decision must be a JSON object")
    status = str(value.get("status") or "").strip().lower()
    if status not in ("approved", "pass"):
        raise FlowError("G1 decision status must be approved")
    selected = str(value.get("selected_idea_id") or "").strip()
    if not selected:
        raise FlowError("G1 decision requires selected_idea_id")
    candidates_by_id = {card.idea_id: card for card in candidates}
    if selected not in candidates_by_id:
        raise FlowError("G1 selected_idea_id is not in the current idea candidates: " + selected)
    reason = str(value.get("human_reason") or "").strip()
    if not reason:
        raise FlowError("G1 decision requires a human reason")
    expected = sha256_json(
        {
            "idea_id": candidates_by_id[selected].idea_id,
            "title": candidates_by_id[selected].title,
            "hypothesis": candidates_by_id[selected].hypothesis,
            "falsification": candidates_by_id[selected].falsification,
            "evidence_refs": list(candidates_by_id[selected].evidence_refs),
        }
    )
    supplied = str(value.get("selected_idea_sha256") or "").strip()
    if supplied and supplied != expected:
        raise FlowError("G1 selected idea hash does not match the current candidate")
    return {
        "status": "approved",
        "selected_idea_id": selected,
        "selected_idea_sha256": expected,
        "human_reason": reason,
        "decision_id": str(value.get("decision_id") or "").strip(),
        "path": str(path),
    }


def validate_frozen_protocol(path: Path, design: Dict[str, Any]) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise FlowError("frozen protocol file not found: " + str(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FlowError("frozen protocol is not readable JSON: %s" % exc)
    if not isinstance(value, dict):
        raise FlowError("frozen protocol must be a JSON object")
    if str(design.get("status") or "") != "ready_for_g2":
        raise FlowError("design must be ready_for_g2 before S5")
    if str(value.get("status") or "") != "frozen":
        raise FlowError("protocol status must be frozen")
    if not str(value.get("human_reason") or "").strip():
        raise FlowError("frozen protocol requires a human reason")
    if not str(value.get("limitation") or "").strip():
        raise FlowError("frozen protocol requires a limitation")
    expected = design_sha256(design)
    actual = str(value.get("design_sha256") or "").strip()
    if actual != expected:
        raise FlowError(
            "protocol design_sha256 does not match the current design "
            "(expected %s, got %s)" % (expected[:12], actual[:12] or "empty")
        )
    value = dict(value)
    value["_path"] = str(path)
    value["_design_sha256"] = expected
    return value


def protocol_binding(
    protocol: Dict[str, Any],
    capsule_path: Path,
    ea_artifact_id: str,
    run_id: str,
) -> Dict[str, Any]:
    capsule_path = Path(capsule_path)
    if not capsule_path.is_file():
        raise FlowError("completed capsule file not found for protocol binding")
    return {
        "schema_version": "protocol-binding-0.1",
        "protocol_id": str(protocol.get("protocol_id") or ""),
        "design_sha256": str(protocol.get("design_sha256") or ""),
        "capsule_sha256": sha256_file(capsule_path),
        "ea_artifact_id": str(ea_artifact_id or ""),
        "run_id": str(run_id or ""),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "boundary": "binding proves this capsule was run under the frozen design; it is not a Claim or Closure",
    }

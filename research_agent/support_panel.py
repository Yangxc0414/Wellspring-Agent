"""Multi-judge support panel with a disagreement ledger and human adjudication.

Each judge audits the same draft/pack independently. The panel records per-item
verdicts, flags disagreements, computes pairwise agreement/kappa on the audited
subset, and either blocks in strict mode or asks for a human adjudication file.
It never creates Claim/EA/gate/signature and never authorizes submission.
"""

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .support_audit import STATUSES, SupportJudge, audit_pack_support
from .writing_pack import PACK_MARKER_RE

PANEL_SCHEMA = "support-panel-0.1"
ADJUDICATION_SCHEMA = "support-adjudication-0.1"
PANEL_BOUNDARY = (
    "Multi-judge support ledger only: judge ids, families and provider ids are caller-supplied "
    "configuration; distinct providers do not prove independent outputs, models or human gold. "
    "Kappa is pairwise on the audited subset, not human gold. It does not create or change "
    "Claim/EA/gate/signature and never authorizes submission."
)
_SEVERITY = {"contradicted": 4, "insufficient": 3, "partial": 2, "supported": 1, "not_required": 0}


class SupportPanelError(RuntimeError):
    pass


def _majority(statuses: List[str]) -> str:
    counts = Counter(statuses)
    return max(counts, key=lambda value: (counts[value], _SEVERITY.get(value, 0)))


def _kappa(pairs: List[Tuple[str, str]]) -> Tuple[Optional[float], Optional[float]]:
    if not pairs:
        return None, None
    total = len(pairs)
    observed = sum(1 for left, right in pairs if left == right) / total
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    expected = sum(
        (left_counts[status] / total) * (right_counts[status] / total)
        for status in STATUSES
    )
    if expected >= 1:
        kappa = 1.0 if observed >= 1 else 0.0
    else:
        kappa = (observed - expected) / (1 - expected)
    return round(observed, 4), round(kappa, 4)


def _load_adjudication(path: Optional[Path]) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    if not path:
        return {}, []
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SupportPanelError("adjudication file is unreadable: " + str(path)) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("decisions"), list):
        raise SupportPanelError("adjudication must contain a decisions list")
    decisions: Dict[str, Dict[str, str]] = {}
    warnings: List[str] = []
    for entry in payload["decisions"]:
        if not isinstance(entry, dict):
            raise SupportPanelError("adjudication decision must be an object")
        item_id = str(entry.get("id") or "").strip()
        status = str(entry.get("status") or "").strip().lower()
        reason = str(entry.get("human_reason") or "").strip()
        if not item_id:
            raise SupportPanelError("adjudication decision needs an id")
        if status not in STATUSES:
            raise SupportPanelError("invalid adjudication status: " + status)
        if not reason:
            raise SupportPanelError("adjudication decision needs human_reason: " + item_id)
        if item_id in decisions:
            raise SupportPanelError("duplicate adjudication decision: " + item_id)
        decisions[item_id] = {"status": status, "human_reason": reason[:600]}
    return decisions, warnings


def audit_support_panel(
    draft_path,
    pack: Dict[str, Any],
    judges: List[Tuple[str, SupportJudge]],
    *,
    strict: bool = False,
    max_items: int = 80,
    judge_votes: int = 1,
    cache_dir: Optional[Path] = None,
    refresh: bool = False,
    adjudication_path: Optional[Path] = None,
    judge_families: Optional[Dict[str, str]] = None,
    require_families: bool = False,
    judge_providers: Optional[Dict[str, str]] = None,
    judge_models: Optional[Dict[str, str]] = None,
    require_providers: bool = False,
) -> Dict[str, Any]:
    """Audit one draft with multiple independent judges and adjudicate disagreement."""
    if not judges:
        raise SupportPanelError("at least one judge is required")
    judge_ids = [str(item[0]) for item in judges]
    if len(set(judge_ids)) != len(judge_ids):
        raise SupportPanelError("judge profile ids must be unique")
    if strict and len(judges) < 2:
        raise SupportPanelError("strict panel requires at least two judges")
    families = {
        str(key): str(value).strip().lower()
        for key, value in (judge_families or {}).items()
        if str(value).strip()
    }
    providers = {
        str(key): str(value).strip().lower()
        for key, value in (judge_providers or {}).items()
        if str(value).strip()
    }
    models = {
        str(key): str(value).strip()
        for key, value in (judge_models or {}).items()
        if str(value).strip()
    }
    if require_families:
        missing = [judge_id for judge_id in judge_ids if not families.get(judge_id)]
        if missing:
            raise SupportPanelError(
                "family-required panel needs a family for every judge: "
                + ", ".join(missing)
            )
        if len({families[judge_id] for judge_id in judge_ids}) < 2:
            raise SupportPanelError(
                "family-required panel needs at least two distinct model families"
            )
    if require_providers:
        missing = [judge_id for judge_id in judge_ids if not providers.get(judge_id)]
        if missing:
            raise SupportPanelError(
                "provider-required panel needs a provider for every judge: "
                + ", ".join(missing)
            )
        if len({providers[judge_id] for judge_id in judge_ids}) < 2:
            raise SupportPanelError(
                "provider-required panel needs at least two distinct provider ids"
            )
    family_warning = ""
    if not require_families and len({families.get(judge_id, "") for judge_id in judge_ids}) < 2:
        family_warning = (
            "judge families are missing or not distinct; independence is unverified"
        )
    provider_warning = ""
    provider_count = len({providers.get(judge_id, "") for judge_id in judge_ids if providers.get(judge_id)})
    if not require_providers and provider_count < 2 and providers:
        provider_warning = (
            "judge provider ids are missing or not distinct; provider independence is unverified"
        )

    from .revision_io import read_draft

    pack_id = str(pack.get("pack_id") or "")
    pack_sha256 = str(pack.get("pack_sha256") or "")
    if not pack_id or not pack_sha256:
        raise SupportPanelError("writing pack has no pack_id/pack_sha256; rebuild it first")
    document = read_draft(Path(draft_path))
    full_text = "\n".join(
        block.text
        for section in document.sections
        for block in section.blocks
        if block.text
    )
    marker = PACK_MARKER_RE.search(full_text)
    if (
        not marker
        or marker.group(1) != pack_id
        or marker.group(2) != pack_sha256
    ):
        raise SupportPanelError(
            "draft is not bound to the current writing pack; rebuild the draft from this pack"
        )

    reports: List[Tuple[str, Dict[str, Any]]] = []
    for judge_id, judge in judges:
        try:
            report = audit_pack_support(
                draft_path,
                pack,
                judge=judge,
                strict=True,
                max_items=max_items,
                judge_model_id=judge_id,
                judge_votes=judge_votes,
                cache_dir=cache_dir,
                refresh=refresh,
            )
        except Exception as exc:
            if isinstance(exc, SupportPanelError):
                raise
            raise SupportPanelError(
                "judge %s failed: %s" % (judge_id, type(exc).__name__)
            )
        reports.append((judge_id, report))

    baseline = reports[0][1]
    truncated = any(bool(report.get("truncated")) for _, report in reports)
    total_cited = max(
        [int(report.get("total_cited_sentences") or 0) for _, report in reports]
        or [0]
    )
    items_by_judge = {
        judge_id: {str(item.get("id") or ""): item for item in report.get("items") or []}
        for judge_id, report in reports
    }
    items: List[Dict[str, Any]] = []
    disagreements: List[str] = []
    pending_human: List[str] = []
    for base in baseline.get("items") or []:
        item_id = str(base.get("id") or "")
        statuses: Dict[str, str] = {}
        rationales: Dict[str, str] = {}
        for judge_id, _ in judges:
            verdict = items_by_judge[judge_id].get(item_id)
            if verdict is None:
                statuses[judge_id] = "missing"
                rationales[judge_id] = "judge returned no verdict for this item"
            else:
                statuses[judge_id] = str(verdict.get("status") or "missing")
                rationales[judge_id] = str(verdict.get("rationale") or "")
        present = [status for status in statuses.values() if status != "missing"]
        majority = _majority(present) if present else "insufficient"
        unanimous = len(set(present)) <= 1 and not any(
            status == "missing" for status in statuses.values()
        )
        requires_human = not unanimous
        if requires_human:
            disagreements.append(item_id)
        items.append(
            {
                "id": item_id,
                "section": base.get("section"),
                "sentence": base.get("sentence"),
                "refs": base.get("refs") or [],
                "unresolved_refs": base.get("unresolved_refs") or [],
                "mode": base.get("mode") or "claim",
                "evidence": base.get("evidence") or [],
                "verdicts": statuses,
                "rationales": rationales,
                "majority": majority,
                "unanimous": unanimous,
                "requires_human": requires_human,
                "final_status": majority,
                "final_source": "majority",
            }
        )

    decisions, warnings = _load_adjudication(adjudication_path)
    known_ids = {item["id"] for item in items}
    for item_id in decisions:
        if item_id not in known_ids:
            warnings.append("adjudication ignored unknown item: " + item_id)
    for item in items:
        decision = decisions.get(item["id"])
        if decision:
            item["final_status"] = decision["status"]
            item["final_source"] = "human_adjudication"
            item["human_reason"] = decision["human_reason"]
        elif item["requires_human"]:
            pending_human.append(item["id"])

    counts = {status: 0 for status in STATUSES}
    for item in items:
        counts[item["final_status"]] = counts.get(item["final_status"], 0) + 1
    unresolved_refs = sum(
        1
        for item in items
        if item["unresolved_refs"] and item["mode"] != "proposal"
    )
    if not items:
        status = "not_applicable"
    elif counts.get("contradicted", 0) or unresolved_refs:
        status = "blocked"
    elif pending_human:
        status = "blocked" if strict else "needs_human"
    elif counts.get("insufficient", 0) or counts.get("partial", 0):
        status = "partial"
    elif counts.get("supported", 0) or counts.get("not_required", 0):
        status = "ready"
    else:
        status = "blocked"
    if family_warning:
        warnings.append(family_warning)
    if provider_warning:
        warnings.append(provider_warning)
    if truncated:
        warnings.append(
            "support panel truncated: audited %d/%d cited sentences; increase max_items"
            % (len(items), total_cited)
        )
        if strict:
            status = "blocked"
        elif status == "ready":
            status = "partial"

    pairs: List[Dict[str, Any]] = []
    claim_items = [item for item in items if item["mode"] != "proposal"]
    for left_index in range(len(judges)):
        for right_index in range(left_index + 1, len(judges)):
            left_id = judge_ids[left_index]
            right_id = judge_ids[right_index]
            values = [
                (item["verdicts"].get(left_id, "missing"), item["verdicts"].get(right_id, "missing"))
                for item in claim_items
                if item["verdicts"].get(left_id) not in (None, "missing")
                and item["verdicts"].get(right_id) not in (None, "missing")
            ]
            observed, kappa = _kappa(values)
            pairs.append(
                {
                    "a": left_id,
                    "b": right_id,
                    "a_family": families.get(left_id, ""),
                    "b_family": families.get(right_id, ""),
                    "a_provider": providers.get(left_id, ""),
                    "b_provider": providers.get(right_id, ""),
                    "items": len(values),
                    "observed_agreement": observed,
                    "kappa": kappa,
                }
            )
    kappas = [pair["kappa"] for pair in pairs if pair["kappa"] is not None]

    template = {
        "schema_version": ADJUDICATION_SCHEMA,
        "draft": str(Path(draft_path)),
        "decisions": [
            {
                "id": item["id"],
                "sentence": item["sentence"],
                "verdicts": item["verdicts"],
                "majority": item["majority"],
                "status": "",
                "human_reason": "",
            }
            for item in items
            if item["requires_human"] and not decisions.get(item["id"])
        ],
        "boundary": "Human adjudication only; choose a status and give a reason for every decision.",
    }
    fingerprint_source = {
        "draft_sha256": baseline.get("draft_sha256", ""),
        "pack_sha256": pack_sha256,
        "judges": judge_ids,
        "judge_families": [families.get(judge_id, "") for judge_id in judge_ids],
        "judge_providers": [providers.get(judge_id, "") for judge_id in judge_ids],
        "judge_models": [models.get(judge_id, "") for judge_id in judge_ids],
        "items": [[item["id"], item["final_status"], item["final_source"]] for item in items],
    }
    fingerprint = hashlib.sha256(
        json.dumps(fingerprint_source, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": PANEL_SCHEMA,
        "scope": "multi-judge sentence-level [REF-xx] support panel with adjudication ledger",
        "draft": str(Path(draft_path)),
        "draft_sha256": baseline.get("draft_sha256", ""),
        "pack_id": pack_id,
        "pack_sha256": pack_sha256,
        "pack_binding": "bound",
        "judges": [
            {
                "id": judge_id,
                "family": families.get(judge_id, ""),
                "provider": providers.get(judge_id, ""),
                "model": models.get(judge_id, ""),
                "method": report.get("method"),
                "counts": report.get("counts") or {},
                "status": report.get("status"),
            }
            for judge_id, report in reports
        ],
        "judge_families": dict(families),
        "judge_providers": dict(providers),
        "judge_models": dict(models),
        "family_requirement": "required" if require_families else "declared_optional",
        "provider_requirement": "required" if require_providers else "declared_optional",
        "independence": (
            "distinct_providers"
            if provider_count >= 2
            else "declared_two_family"
            if len({families.get(judge_id, "") for judge_id in judge_ids if families.get(judge_id)}) >= 2
            else "unverified"
        ),
        "independence_note": (
            "distinct provider ids are caller-declared configuration; they do not prove "
            "independent model outputs, semantic independence or human gold"
        ),
        "judge_votes": max(1, min(int(judge_votes), 5)),
        "items": items,
        "counts": counts,
        "item_limit": max(1, min(int(max_items), 500)),
        "total_cited_sentences": total_cited,
        "audited_cited_sentences": len(items),
        "truncated": truncated,
        "unresolved_refs": unresolved_refs,
        "disagreements": disagreements,
        "pending_human": pending_human,
        "adjudication": {
            "provided": bool(adjudication_path),
            "path": str(adjudication_path) if adjudication_path else "",
            "applied": sum(1 for item in items if item["final_source"] == "human_adjudication"),
        },
        "adjudication_template": template,
        "agreement": {
            "pairs": pairs,
            "mean_kappa": round(sum(kappas) / len(kappas), 4) if kappas else None,
        },
        "status": status,
        "strict": bool(strict),
        "panel_fingerprint": fingerprint,
        "warnings": warnings,
        "boundary": PANEL_BOUNDARY,
    }

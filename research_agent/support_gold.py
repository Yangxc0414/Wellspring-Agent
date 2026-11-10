"""Double-annotated human gold for sentence-level support, with panel comparison.

This is a reference label set, not an automatic judge. It computes inter-annotator
agreement (pairwise Cohen's kappa), the majority label, and optionally compares a
support panel's final verdicts with the human majority. It never creates a Claim,
EA, gate or signature and never authorizes submission.
"""

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .support_audit import STATUSES

GOLD_SCHEMA = "support-gold-0.1"
ANNOTATION_SCHEMA = "support-gold-annotations-0.1"
GOLD_BOUNDARY = (
    "Human annotation reference only: kappa measures agreement, not truth. Labels are "
    "human-supplied and are not peer review. No Claim/EA/gate/signature is created and "
    "submission is never authorized."
)
_SEVERITY = {"contradicted": 4, "insufficient": 3, "partial": 2, "supported": 1, "not_required": 0}


class SupportGoldError(RuntimeError):
    pass


def _majority(labels: List[str]) -> str:
    counts = Counter(labels)
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


def load_annotations(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SupportGoldError("annotation file is unreadable: " + str(path)) from exc
    if not isinstance(payload, dict):
        raise SupportGoldError("annotation must be an object: " + str(path))
    annotator = str(payload.get("annotator") or "").strip()
    if not annotator:
        raise SupportGoldError("annotation needs an annotator id: " + str(path))
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise SupportGoldError("annotation needs a non-empty items list: " + str(path))
    labels: Dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise SupportGoldError("annotation item must be an object: " + str(path))
        item_id = str(item.get("id") or "").strip()
        status = str(item.get("status") or "").strip().lower()
        if not item_id:
            raise SupportGoldError("annotation item needs an id: " + str(path))
        if status not in STATUSES:
            raise SupportGoldError(
                "invalid annotation status for %s: %s" % (item_id, status)
            )
        if item_id in labels:
            raise SupportGoldError("duplicate annotation item: " + item_id)
        labels[item_id] = status
    return {
        "annotator": annotator,
        "items": labels,
        "draft_sha256": str(payload.get("draft_sha256") or ""),
        "source": str(path),
    }


def panel_from_ledger(ledger: Dict[str, Any], *, source: str = "") -> Dict[str, Any]:
    """Wrap a Qoder support ledger as a panel-like object for human gold."""
    if not isinstance(ledger, dict) or not isinstance(ledger.get("items"), list):
        raise SupportGoldError("support ledger has no items")
    items: List[Dict[str, Any]] = []
    for value in ledger["items"]:
        if not isinstance(value, dict):
            continue
        item_id = str(value.get("id") or "").strip()
        status = str(value.get("status") or "").strip().lower()
        if not item_id or status not in STATUSES:
            continue
        items.append(
            {
                **value,
                "final_status": status,
                "final_source": "qoder_ledger",
            }
        )
    if not items:
        raise SupportGoldError("support ledger has no usable items")
    return {
        "schema_version": "support-panel-from-ledger-0.1",
        "draft": str(ledger.get("draft") or ""),
        "draft_sha256": str(ledger.get("draft_sha256") or ""),
        "status": str(ledger.get("status") or ""),
        "items": items,
        "judges": [
            {
                "id": str(ledger.get("judge_model") or "qoder"),
                "status": str(ledger.get("status") or ""),
            }
        ],
        "panel_fingerprint": str(ledger.get("cache_key") or ""),
        "source": source or "support_ledger",
        "judge_model": str(ledger.get("judge_model") or ""),
    }


def build_gold_templates(
    panel: Dict[str, Any],
    annotators: List[str],
    *,
    source: str = "",
) -> Dict[str, Any]:
    """Blank annotation templates from a panel; panel verdicts are deliberately omitted."""
    if not isinstance(panel, dict) or not isinstance(panel.get("items"), list):
        raise SupportGoldError("panel has no items for gold templates")
    names = [str(item).strip() for item in annotators if str(item).strip()]
    if len(names) < 2:
        raise SupportGoldError("gold templates require at least two annotators")
    if len(set(names)) != len(names):
        raise SupportGoldError("annotator ids must be unique")
    items: List[Dict[str, Any]] = []
    for value in panel["items"]:
        if not isinstance(value, dict):
            continue
        item_id = str(value.get("id") or "").strip()
        if not item_id:
            continue
        items.append(
            {
                "id": item_id,
                "section": str(value.get("section") or ""),
                "sentence": str(value.get("sentence") or ""),
                "refs": value.get("refs") or [],
                "unresolved_refs": value.get("unresolved_refs") or [],
                "mode": str(value.get("mode") or "claim"),
                "evidence": value.get("evidence") or [],
                "status": "",
                "note": "",
            }
        )
    if not items:
        raise SupportGoldError("panel has no usable items for gold templates")
    templates = [
        {
            "schema_version": ANNOTATION_SCHEMA,
            "annotator": name,
            "draft_sha256": str(panel.get("draft_sha256") or ""),
            "items": [dict(item) for item in items],
        }
        for name in names
    ]
    return {
        "schema_version": "support-gold-template-0.1",
        "source_panel": source,
        "draft_sha256": str(panel.get("draft_sha256") or ""),
        "annotators": names,
        "item_count": len(items),
        "templates": templates,
        "boundary": (
            "Blank labels only; panel verdicts and rationales are omitted to avoid anchoring. "
            "Annotators must fill status and note independently; the template is not gold."
        ),
    }


def render_gold_template_instructions(result: Dict[str, Any]) -> str:
    lines = [
        "# Support Gold Annotation Templates",
        "",
        "- panel: `%s`" % (result.get("source_panel") or ""),
        "- items: %d" % int(result.get("item_count") or 0),
        "- annotators: %s" % ", ".join(result.get("annotators") or []),
        "",
        "Fill `status` for every item with one of: supported, partial, contradicted, insufficient.",
        "Use `note` for the reason. Do not copy panel verdicts or discuss labels with the other annotator.",
        "",
        "Then run:",
        "",
        "```bash",
        "python -m research_agent writing support-gold --project <project> --run-id <RUN> \\",
        "  --annotator-file <A.json> --annotator-file <B.json> --panel <panel.json>",
        "```",
        "",
        "Boundary: " + str(result.get("boundary") or ""),
        "",
    ]
    return "\n".join(lines)


def evaluate_support_gold(
    annotations: List[Dict[str, Any]],
    *,
    panel: Optional[Dict[str, Any]] = None,
    draft_sha256: str = "",
) -> Dict[str, Any]:
    if len(annotations) < 2:
        raise SupportGoldError("human gold requires at least two annotators")
    names = [str(item["annotator"]) for item in annotations]
    if len(set(names)) != len(names):
        raise SupportGoldError("annotator ids must be unique")
    item_sets = [set(item["items"]) for item in annotations]
    if any(values != item_sets[0] for values in item_sets[1:]):
        raise SupportGoldError("annotators must label the same item ids")
    item_ids = sorted(item_sets[0])
    annotation_hashes = {
        str(item.get("draft_sha256") or "")
        for item in annotations
        if str(item.get("draft_sha256") or "")
    }
    if len(annotation_hashes) > 1:
        raise SupportGoldError("annotations disagree on draft_sha256")
    annotation_hash = next(iter(annotation_hashes), "")
    if draft_sha256 and annotation_hash and annotation_hash != draft_sha256:
        raise SupportGoldError("annotation draft_sha256 does not match the draft")
    effective_draft = draft_sha256 or annotation_hash

    items: List[Dict[str, Any]] = []
    for item_id in item_ids:
        labels = {
            str(item["annotator"]): str(item["items"][item_id])
            for item in annotations
        }
        values = list(labels.values())
        items.append(
            {
                "id": item_id,
                "labels": labels,
                "majority": _majority(values),
                "unanimous": len(set(values)) == 1,
            }
        )

    pairs: List[Dict[str, Any]] = []
    for left_index in range(len(annotations)):
        for right_index in range(left_index + 1, len(annotations)):
            left = str(annotations[left_index]["annotator"])
            right = str(annotations[right_index]["annotator"])
            values = [
                (item["labels"][left], item["labels"][right])
                for item in items
            ]
            observed, kappa = _kappa(values)
            pairs.append(
                {
                    "a": left,
                    "b": right,
                    "items": len(values),
                    "observed_agreement": observed,
                    "kappa": kappa,
                }
            )
    kappas = [pair["kappa"] for pair in pairs if pair["kappa"] is not None]
    counts = {status: 0 for status in STATUSES}
    for item in items:
        counts[item["majority"]] += 1

    panel_summary: Dict[str, Any] = {"present": False}
    status = "complete"
    if panel is not None:
        if not isinstance(panel, dict):
            raise SupportGoldError("panel must be an object")
        panel_hash = str(panel.get("draft_sha256") or "")
        if effective_draft and panel_hash and panel_hash != effective_draft:
            raise SupportGoldError("panel draft_sha256 does not match the gold draft")
        panel_items = {
            str(item.get("id") or ""): str(
                item.get("final_status") or item.get("majority") or "missing"
            )
            for item in (panel.get("items") or [])
            if isinstance(item, dict)
        }
        missing = [item_id for item_id in item_ids if item_id not in panel_items]
        confusion: Dict[str, Dict[str, int]] = {}
        disagreements: List[Dict[str, str]] = []
        matches = 0
        for item in items:
            panel_status = panel_items.get(item["id"], "missing")
            confusion.setdefault(item["majority"], {})
            confusion[item["majority"]][panel_status] = (
                confusion[item["majority"]].get(panel_status, 0) + 1
            )
            item["panel_status"] = panel_status
            if panel_status == item["majority"]:
                matches += 1
            else:
                disagreements.append(
                    {
                        "id": item["id"],
                        "gold": item["majority"],
                        "panel": panel_status,
                    }
                )
        if missing:
            status = "incomplete"
        panel_summary = {
            "present": True,
            "status": str(panel.get("status") or ""),
            "items": len(panel_items),
            "missing": missing,
            "accuracy": round(matches / len(items), 4) if items else None,
            "confusion": confusion,
            "disagreements": disagreements,
            "panel_fingerprint": str(panel.get("panel_fingerprint") or ""),
            "judge_model": str(panel.get("judge_model") or ""),
            "source": str(panel.get("source") or ""),
        }
    return {
        "schema_version": GOLD_SCHEMA,
        "draft": str((panel or {}).get("draft") or ""),
        "draft_sha256": effective_draft,
        "annotators": [
            {"id": str(item["annotator"]), "source": str(item.get("source") or "")}
            for item in annotations
        ],
        "items": items,
        "counts": counts,
        "unanimous_items": sum(1 for item in items if item["unanimous"]),
        "agreement": {
            "pairs": pairs,
            "mean_kappa": round(sum(kappas) / len(kappas), 4) if kappas else None,
        },
        "panel": panel_summary,
        "status": status,
        "boundary": GOLD_BOUNDARY,
    }


def render_support_gold(report: Dict[str, Any]) -> str:
    lines = [
        "# Support Gold",
        "",
        "- draft: `%s`" % (report.get("draft") or ""),
        "- status: **%s**" % report.get("status"),
        "- annotators: %s"
        % ", ".join(item["id"] for item in report.get("annotators") or []),
        "",
        "## Agreement",
        "",
    ]
    for pair in (report.get("agreement") or {}).get("pairs") or []:
        lines.append(
            "- %s vs %s: observed=%s kappa=%s"
            % (pair["a"], pair["b"], pair["observed_agreement"], pair["kappa"])
        )
    lines.extend(["", "## Majority labels", ""])
    for status, count in (report.get("counts") or {}).items():
        if count:
            lines.append("- %s: %d" % (status, count))
    panel = report.get("panel") or {}
    if panel.get("present"):
        lines.extend(
            [
                "",
                "## Panel vs human majority",
                "",
                "- accuracy: %s" % panel.get("accuracy"),
                "- panel status: %s" % panel.get("status"),
                "- disagreements: %d" % len(panel.get("disagreements") or []),
            ]
        )
        for item in panel.get("disagreements") or []:
            lines.append(
                "- %s: gold=%s panel=%s"
                % (item["id"], item["gold"], item["panel"])
            )
    lines.extend(["", "Boundary: " + str(report.get("boundary") or ""), ""])
    return "\n".join(lines)

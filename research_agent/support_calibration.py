"""Calibration harness for the sentence-level support judge.

The case set is a project-authored regression set, not independent human gold.
It exists to detect judge drift, compare vote counts, and make support-ledger
behavior measurable before changing prompts or models.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .support_audit import (
    STATUSES,
    _claim_mode,
    _majority_verdicts,
    _validate_verdicts,
)

CALIBRATION_SCHEMA = "support-calibration-report-0.1"
DEFAULT_CASES = Path(__file__).resolve().parent / "fixtures" / "support_calibration.json"
BOUNDARY = (
    "Curated regression set, not independent human gold and not peer review; "
    "scores measure judge behavior, not manuscript quality or submission readiness."
)


class SupportCalibrationError(ValueError):
    pass


def load_cases(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    source = Path(path) if path else DEFAULT_CASES
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SupportCalibrationError("cannot read calibration cases: %s" % exc)
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list) or not cases:
        raise SupportCalibrationError("calibration file must contain a non-empty cases list")
    normalized = []
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("id") or "CAL-%02d" % (index + 1))
        expected = str(case.get("expected") or "").lower()
        if expected not in STATUSES:
            raise SupportCalibrationError("invalid expected status in " + case_id)
        normalized.append(
            {
                "id": case_id,
                "section": str(case.get("section") or "Methods"),
                "sentence": str(case.get("sentence") or ""),
                "evidence": [str(item) for item in case.get("evidence") or [] if str(item)],
                "expected": expected,
                "mode": str(case.get("mode") or "claim"),
                "note": str(case.get("note") or ""),
            }
        )
    return normalized


def _case_payload(case: Dict[str, Any]) -> Dict[str, Any]:
    evidence = [
        {"ref": "EV-%02d" % (index + 1), "text": text}
        for index, text in enumerate(case["evidence"])
    ]
    return {
        "paper_title": "support calibration",
        "items": [
            {
                "id": case["id"],
                "section": case["section"],
                "sentence": case["sentence"],
                "citation_mode": "explicit_ref",
                "evidence": evidence,
            }
        ],
    }


def evaluate_support_cases(
    cases: List[Dict[str, Any]],
    judge: Optional[Callable[[Dict[str, Any]], Optional[List[Dict[str, Any]]]]],
    *,
    votes: int = 1,
    model_id: str = "",
) -> Dict[str, Any]:
    votes = max(1, min(int(votes), 5))
    confusion = {expected: {actual: 0 for actual in STATUSES} for expected in STATUSES}
    results = []
    for case in cases:
        if case["mode"] != "claim":
            actual = (
                "not_required"
                if _claim_mode(case["sentence"], case["section"]) == "proposal"
                else "insufficient"
            )
            method = "claim_mode"
        else:
            item = {
                "id": case["id"],
                "section": case["section"],
                "sentence": case["sentence"],
                "citation_mode": "explicit_ref",
                "evidence": [
                    {"ref": "EV-%02d" % (index + 1), "text": text}
                    for index, text in enumerate(case["evidence"])
                ],
            }
            actual = "insufficient"
            method = "no_judge"
            if judge is not None:
                runs = []
                payload = _case_payload(case)
                for _ in range(votes):
                    try:
                        raw = judge(payload)
                    except Exception:
                        raw = None
                    verdicts = _validate_verdicts(raw or [], [item]) if raw else []
                    if verdicts:
                        runs.append(verdicts)
                if runs:
                    merged = (
                        _majority_verdicts(runs, [item])
                        if len(runs) > 1
                        else runs[0]
                    )
                    if merged:
                        actual = str(merged[0].get("status") or "insufficient")
                        method = "model_judge_majority" if len(runs) > 1 else "model_judge"
        expected = case["expected"]
        passed = expected == actual
        confusion[expected][actual] += 1
        results.append(
            {
                "id": case["id"],
                "section": case["section"],
                "sentence": case["sentence"],
                "expected": expected,
                "actual": actual,
                "passed": passed,
                "method": method,
                "note": case["note"],
            }
        )

    total = len(results)
    correct = sum(1 for item in results if item["passed"])
    per_status = {}
    for status in STATUSES:
        true_positive = confusion[status][status]
        expected_count = sum(confusion[status].values())
        predicted_count = sum(confusion[other][status] for other in STATUSES)
        precision = true_positive / predicted_count if predicted_count else 0.0
        recall = true_positive / expected_count if expected_count else 0.0
        per_status[status] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "support": expected_count,
        }
    return {
        "schema_version": CALIBRATION_SCHEMA,
        "model": model_id,
        "votes": votes,
        "case_count": total,
        "correct": correct,
        "accuracy": round(correct / total, 3) if total else 0.0,
        "per_status": per_status,
        "confusion": confusion,
        "results": results,
        "failures": [item for item in results if not item["passed"]],
        "boundary": BOUNDARY,
    }


def render_support_calibration(report: Dict[str, Any]) -> str:
    lines = [
        "# Support Judge Calibration",
        "",
        "- model: `%s`" % report.get("model"),
        "- votes: %s" % report.get("votes"),
        "- cases: %s; correct: %s; accuracy: %.3f"
        % (report.get("case_count"), report.get("correct"), report.get("accuracy") or 0.0),
        "",
        "## Per status",
        "",
        "| status | precision | recall | support |",
        "| --- | --- | --- | --- |",
    ]
    for status, item in (report.get("per_status") or {}).items():
        lines.append(
            "| %s | %.3f | %.3f | %d |"
            % (status, item["precision"], item["recall"], item["support"])
        )
    lines += ["", "## Failures", ""]
    for item in report.get("failures") or []:
        lines.append(
            "- `%s` expected **%s**, got **%s**: %s"
            % (item["id"], item["expected"], item["actual"], item["sentence"][:180])
        )
    lines += ["", report.get("boundary") or BOUNDARY, ""]
    return "\n".join(lines)

"""Heuristic tabular-data audit for generated experiments.

This is a pre-run warning layer, not a leakage proof and not a substitute for
human G2 review. It uses only the standard library so it can run anywhere the
code generator runs.
"""

import csv
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

AUDIT_SCHEMA = "experiment-data-audit-0.1"
AUDIT_BOUNDARY = (
    "Heuristic data audit only: it flags possible missingness, duplicates, "
    "constant/ID-like columns, class imbalance and near-perfect feature-target "
    "correlation; it does not prove absence of leakage or replace human review."
)
ID_NAME_RE = re.compile(r"(^id$|_id$|uuid|guid|编号|序号|样本号)", re.I)


def _number(value: Any) -> Optional[float]:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _correlation(pairs: List[tuple]) -> Optional[float]:
    if len(pairs) < 3:
        return None
    xs = [item[0] for item in pairs]
    ys = [item[1] for item in pairs]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    var_x = sum((value - mean_x) ** 2 for value in xs)
    var_y = sum((value - mean_y) ** 2 for value in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    return covariance / math.sqrt(var_x * var_y)


def audit_tabular_data(
    path: Path,
    target: str,
    features: List[str],
    task: str = "regression",
    *,
    max_rows: int = 5000,
) -> Dict[str, Any]:
    source = Path(path)
    checks: List[Dict[str, str]] = []
    warnings: List[str] = []
    try:
        with open(str(source), "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            header = list(reader.fieldnames or [])
            rows = []
            for index, row in enumerate(reader):
                if index >= max_rows:
                    break
                rows.append(row)
    except OSError as exc:
        return {
            "schema_version": AUDIT_SCHEMA,
            "status": "error",
            "checks": [],
            "warnings": ["cannot read data table: %s" % exc],
            "rows": 0,
            "boundary": AUDIT_BOUNDARY,
        }

    def add(check_id: str, ok: bool, detail: str) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "pass" if ok else "warn",
                "detail": detail,
            }
        )
        if not ok:
            warnings.append("%s: %s" % (check_id, detail))

    add("rows.present", bool(rows), "rows sampled=%d" % len(rows))
    if len(rows) < 30:
        add("rows.small", False, "only %d rows; variance/CI will be weak" % len(rows))
    else:
        add("rows.small", True, "%d rows" % len(rows))

    selected = [column for column in features + [target] if column in header]
    missing_counts = {
        column: sum(1 for row in rows if not str(row.get(column) or "").strip())
        for column in selected
    }
    missing_total = sum(missing_counts.values())
    add(
        "missing.values",
        missing_total == 0,
        "missing cells=%s" % {k: v for k, v in missing_counts.items() if v},
    )

    duplicates = len(rows) - len({tuple(str(row.get(column) or "") for column in selected) for row in rows})
    add("duplicates.rows", duplicates == 0, "duplicate rows=%d" % duplicates)

    constant = [
        column
        for column in features
        if column in header
        and len({str(row.get(column) or "").strip() for row in rows}) <= 1
    ]
    add("features.constant", not constant, "constant features=%s" % constant)

    id_like = []
    for column in features:
        values = [str(row.get(column) or "").strip() for row in rows]
        if not values:
            continue
        unique_ratio = len(set(values)) / len(values)
        numeric_ratio = sum(1 for value in values if _number(value) is not None) / len(values)
        name_match = bool(ID_NAME_RE.search(column))
        if name_match or (
            len(values) >= 20 and unique_ratio >= 0.98 and numeric_ratio < 0.8
        ):
            id_like.append(column)
    add("features.id_like", not id_like, "ID-like features=%s" % id_like)

    target_values = [str(row.get(target) or "").strip() for row in rows]
    target_copies = [
        column
        for column in features
        if column in header
        and target_values
        and all(
            str(row.get(column) or "").strip() == value
            for row, value in zip(rows, target_values)
        )
    ]
    add("target.copy", not target_copies, "features identical to target=%s" % target_copies)
    if task == "classification" and target_values:
        counts: Dict[str, int] = {}
        for value in target_values:
            counts[value] = counts.get(value, 0) + 1
        share = max(counts.values()) / len(target_values)
        add(
            "target.class_balance",
            share <= 0.8,
            "largest class share=%.2f" % share,
        )
    if task == "regression":
        pairs = []
        for row in rows:
            y = _number(row.get(target))
            if y is None:
                continue
            pairs.append((row, y))
        suspicious = []
        for column in features:
            feature_pairs = []
            for row, y in pairs:
                x = _number(row.get(column))
                if x is not None:
                    feature_pairs.append((x, y))
            correlation = _correlation(feature_pairs)
            if correlation is not None and abs(correlation) >= 0.98:
                suspicious.append({"feature": column, "correlation": round(correlation, 4)})
        add(
            "features.target_correlation",
            not suspicious,
            "near-perfect feature-target correlation=%s" % suspicious,
        )
    status = "warn" if warnings else "ok"
    return {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "rows_sampled": len(rows),
        "checks": checks,
        "warnings": warnings,
        "boundary": AUDIT_BOUNDARY,
    }

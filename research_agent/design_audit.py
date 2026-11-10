"""Deterministic S4 design/statistics checklist.

This is not statistical validation and not a G2 decision. It reports which
required design fields and statistical-plan elements are missing so a human can
decide whether to freeze the protocol.
"""

import re
from typing import Any, Dict, List

DESIGN_AUDIT_SCHEMA = "design-audit-0.1"
BOUNDARY = (
    "design checklist only; not statistical validation and not a G2 decision; "
    "missing statistics are warnings, not silent approvals"
)
STAT_PATTERNS = {
    "effect_size": r"效应量|最小可检测|最小效应|effect\s*size|MDE",
    "power_or_sample": r"功效|检验效能|样本量|power|sample\s*size",
    "randomization": r"随机|randomi[sz]",
    "multiple_comparisons": r"多重比较|multiple\s*comparison|FDR|Bonferroni|校正",
    "confidence_interval": r"置信区间|confidence\s*interval|\bCI\b",
    "missing_data": r"缺失|missing\s*data|排除|exclude",
    "robustness": r"稳健|robust|敏感性|sensitivity",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _present(value: Any) -> bool:
    text = _text(value)
    return bool(text) and text not in ("待人工补全", "待补全", "TODO", "TBD")


def audit_design(design: Dict[str, Any]) -> Dict[str, Any]:
    checks: List[Dict[str, str]] = []
    warnings: List[str] = []
    blockers: List[str] = []

    def add(check_id: str, status: str, detail: str, severity: str = "warning") -> None:
        checks.append({"id": check_id, "status": status, "detail": detail, "severity": severity})
        if status == "fail" and severity == "blocker":
            blockers.append("%s: %s" % (check_id, detail))
        elif status in ("warn", "fail"):
            warnings.append("%s: %s" % (check_id, detail))

    required = {
        "hypothesis": "研究假设",
        "baseline": "基线/对照",
        "primary_metric": "主指标",
        "budget": "预算",
        "stopping_rule": "停止规则",
    }
    missing = [label for key, label in required.items() if not _present(design.get(key))]
    if missing:
        add("design.required", "fail", "缺少：" + "、".join(missing), "blocker")
    else:
        add("design.required", "pass", "hypothesis / baseline / metric / budget / stopping rule present")

    controls = [item for item in (design.get("controls") or []) if _text(item)]
    if controls:
        add("design.controls", "pass", "%d control(s)" % len(controls))
    else:
        add("design.controls", "fail", "no control condition", "blocker")

    seeds = design.get("seeds")
    if not isinstance(seeds, int) or isinstance(seeds, bool):
        add("design.seeds", "fail", "seeds must be an integer", "blocker")
    elif seeds < 2:
        add("design.seeds", "fail", "seeds=%d; repeated runs are required" % seeds, "blocker")
    elif seeds < 3:
        add("design.seeds", "warn", "seeds=%d; use at least 3 when feasible" % seeds)
    else:
        add("design.seeds", "pass", "seeds=%d" % seeds)

    corpus = " ".join(
        [
            _text(design.get("hypothesis")),
            _text(design.get("baseline")),
            _text(design.get("primary_metric")),
            _text(design.get("budget")),
            _text(design.get("stopping_rule")),
            " ".join(_text(item) for item in controls),
        ]
    )
    missing_stats = [
        name for name, pattern in STAT_PATTERNS.items()
        if not re.search(pattern, corpus, re.IGNORECASE)
    ]
    if missing_stats:
        add(
            "design.statistics",
            "warn",
            "未明确：" + "、".join(missing_stats),
            "warning",
        )
    else:
        add("design.statistics", "pass", "statistical plan elements are present")

    status = "incomplete" if blockers else "attention" if warnings else "ready_for_g2"
    return {
        "schema_version": DESIGN_AUDIT_SCHEMA,
        "status": status,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "boundary": BOUNDARY,
    }

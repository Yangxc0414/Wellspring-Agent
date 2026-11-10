"""Metric-headroom audit for search studies.

``improvement_per_evaluation`` counts improvement events per evaluation. When the underlying
score is bounded (accuracy in [0, 1]), a run that reaches the ceiling early stops producing
events, so a raw count difference can be a right-censoring artifact rather than an efficiency
difference. This module only reports that risk from the recorded run traces; it never recomputes,
normalizes or rewrites the registered metric.
"""

from typing import Any, Dict, List, Optional

METRIC_CEILING = 1.0
WARN_SHARE = 0.10
MIN_DECISION_SEEDS = 4


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def saturation_report(study: Dict[str, Any]) -> Dict[str, Any]:
    runs: List[Dict[str, Any]] = []
    bounded = True
    for cell in study.get("cells") or []:
        if not isinstance(cell, dict):
            continue
        for run in cell.get("runs") or []:
            if not isinstance(run, dict):
                continue
            best = run.get("best_score")
            root = run.get("root_score")
            if not _number(best) or not _number(root):
                continue
            if not (0.0 <= best <= 1.0 and 0.0 <= root <= 1.0):
                bounded = False
            runs.append({"cell": str(cell.get("cell_id") or ""), "best": float(best), "root": float(root)})
    if not runs:
        return {"available": False, "saturated": False, "reason": "study has no scored runs"}
    if not bounded:
        return {
            "available": False,
            "saturated": False,
            "reason": "scores are not bounded to [0, 1]; ceiling semantics are unknown for this metric",
        }
    ceiling = [run for run in runs if run["best"] >= METRIC_CEILING - 1e-9]
    root_ceiling = [run for run in runs if run["root"] >= METRIC_CEILING - 1e-9]
    share = len(ceiling) / float(len(runs))
    by_cell: Dict[str, Dict[str, int]] = {}
    for run in runs:
        bucket = by_cell.setdefault(run["cell"], {"runs": 0, "ceiling": 0})
        bucket["runs"] += 1
        if run["best"] >= METRIC_CEILING - 1e-9:
            bucket["ceiling"] += 1
    saturated = share >= WARN_SHARE
    if saturated:
        detail = (
            "%d/%d runs (%.1f%%) reach the metric ceiling %.1f; %d start there; "
            "improvement counts are right-censored, so report a headroom-normalized anytime "
            "curve before reading an efficiency difference"
            % (len(ceiling), len(runs), 100.0 * share, METRIC_CEILING, len(root_ceiling))
        )
    else:
        detail = "no run reaches a bounded metric ceiling"
    return {
        "available": True,
        "saturated": saturated,
        "runs": len(runs),
        "ceiling_runs": len(ceiling),
        "ceiling_share": round(share, 6),
        "root_ceiling_runs": len(root_ceiling),
        "by_cell": by_cell,
        "detail": detail,
        "boundary": (
            "disclosure only: this reads recorded traces and does not re-run, normalize or "
            "replace the registered metric"
        ),
    }


def normalized_run(run: Dict[str, Any], include_curve: bool = False) -> Optional[Dict[str, Any]]:
    """Headroom-normalized best-so-far curve for one run, or None when undefined.

    ``include_curve`` adds the curve points themselves.  It is off by default so the
    stored and displayed summaries keep their shape; a figure needs the per-evaluation
    series, nothing else does.
    """
    nodes = sorted(
        (node for node in run.get("nodes") or [] if isinstance(node, dict)),
        key=lambda node: node.get("evaluations") or 0,
    )
    if not nodes:
        return None
    scores = [node.get("score") for node in nodes]
    if not all(_number(score) and 0.0 <= float(score) <= 1.0 for score in scores):
        return None
    root = float(scores[0])
    headroom = METRIC_CEILING - root
    if headroom <= 1e-6:
        return None
    best = root
    curve: List[float] = []
    points: List[Dict[str, Any]] = []
    first_ceiling = None
    for node, score in zip(nodes, scores):
        best = max(best, float(score))
        curve.append(best)
        points.append({"evaluations": node.get("evaluations"), "best": best})
        if first_ceiling is None and best >= METRIC_CEILING - 1e-9:
            first_ceiling = node.get("evaluations")
    after = curve[1:]
    auc = sum((value - root) / headroom for value in after) / len(after) if after else 0.0
    gain = min(1.0, max(0.0, (curve[-1] - root) / headroom))
    summary = {
        "auc": auc,
        "gain": gain,
        "first_ceiling": first_ceiling,
        "evals_after_ceiling": 0 if first_ceiling is None else len(curve) - int(first_ceiling),
    }
    if include_curve:
        summary["root"] = root
        summary["ceiling"] = METRIC_CEILING
        summary["curve"] = points
    return summary


def _paired_summary(contrasts: List[float], name: str) -> Dict[str, Any]:
    n = len(contrasts)
    if not n:
        return {"available": False, "name": name, "reason": "no complete-case seeds"}
    mean = sum(contrasts) / n
    base: Dict[str, Any] = {
        "available": True,
        "name": name,
        "mean_interaction": round(mean, 6),
        "n": n,
    }
    if n < MIN_DECISION_SEEDS:
        base.update({
            "ci95_low": None,
            "ci95_high": None,
            "underpowered": True,
            "decidable": False,
            "reason": "needs >= %d seeds before an interval is interpreted" % MIN_DECISION_SEEDS,
        })
        return base
    variance = sum((value - mean) ** 2 for value in contrasts) / (n - 1)
    standard_error = variance ** 0.5 / (n ** 0.5)
    try:
        from scipy.stats import t

        critical = float(t.ppf(0.975, n - 1))
    except Exception:
        critical = 2.0
    low = mean - critical * standard_error
    high = mean + critical * standard_error
    base.update({
        "ci95_low": round(low, 6),
        "ci95_high": round(high, 6),
        "underpowered": False,
        "decidable": low > 0 or high < 0,
    })
    return base


def interaction_sensitivity(study: Dict[str, Any]) -> Dict[str, Any]:
    """Raw event-count interaction beside a headroom-normalized one for a 2x2 design."""
    cells_list = [cell for cell in study.get("cells") or [] if isinstance(cell, dict)]
    if not cells_list:
        return {"available": False, "reason": "study has no cells"}
    windows = {str(cell.get("archive_window") or "") for cell in cells_list}
    gates = {bool(cell.get("gate")) for cell in cells_list}
    if len(windows) > 1 or len(gates) > 1:
        return {
            "available": False,
            "reason": (
                "study varies archive_window or gate; slice it to one 2x2 memory x archive "
                "design before reading a paired interaction"
            ),
        }
    by_cell: Dict[tuple, List[Dict[str, Any]]] = {}
    for cell in cells_list:
        key = (bool(cell.get("memory")), str(cell.get("archive") or ""))
        by_cell[key] = [run for run in cell.get("runs") or [] if isinstance(run, dict)]
    needed = [(False, "off"), (False, "negative"), (True, "off"), (True, "negative")]
    if set(by_cell) != set(needed):
        return {
            "available": False,
            "reason": "needs exactly the 2x2 memory (off/on) x archive (off/negative) cells",
        }
    by_seed: Dict[tuple, Dict[int, Dict[str, Any]]] = {}
    for key in needed:
        by_seed[key] = {int(run.get("seed") or 0): run for run in by_cell[key]}
    seeds = set(by_seed[needed[0]])
    for key in needed[1:]:
        seeds &= set(by_seed[key])
    seeds = sorted(seed for seed in seeds if seed)
    if not seeds:
        return {"available": False, "reason": "no seed is present in all four cells"}

    def contrast(metric) -> List[float]:
        values = []
        for seed in seeds:
            a, b, c, d = (metric(by_seed[key][seed]) for key in needed)
            values.append((d - c) - (b - a))
        return values

    raw = contrast(lambda run: float(run.get("improvement_per_evaluation") or 0.0))
    auc_values, gain_values = [], []
    for seed in seeds:
        norms = [normalized_run(by_seed[key][seed]) for key in needed]
        if any(item is None for item in norms):
            continue
        a, b, c, d = norms
        auc_values.append((d["auc"] - c["auc"]) - (b["auc"] - a["auc"]))
        gain_values.append((d["gain"] - c["gain"]) - (b["gain"] - a["gain"]))
    return {
        "available": True,
        "topic": "post-hoc ceiling sensitivity, not pre-registered evidence",
        "raw": _paired_summary(raw, "raw_improvement_per_evaluation"),
        "normalized_auc": _paired_summary(auc_values, "headroom_normalized_auc"),
        "normalized_gain": _paired_summary(gain_values, "headroom_normalized_gain"),
        "complete_case_seeds": len(auc_values),
        "boundary": (
            "the normalized summaries are a different estimand and are reported after the "
            "registered run; they can expose a ceiling artifact but cannot replace or sign "
            "the registered metric"
        ),
    }

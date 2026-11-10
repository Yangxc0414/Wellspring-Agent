"""Data-backed result figures for generated local experiments.

The figure is rendered only from verified experiment evidence, and its manifest
binds the image bytes to the experiment spec, execution, evidence and claim
hashes. This is not a schematic and not a new result: it visualizes the same
verified metrics that the signed claim is checked against.
"""

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project import project_output_path
from .storage import read_json, write_json_atomic

FIGURE_SCHEMA = "experiment-figure-manifest-0.1"
FIGURE_BOUNDARY = (
    "Data-backed result figure from verified local experiment evidence; not a "
    "schematic, not a claim, not peer review and not submission approval."
)


class ExperimentFigureError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha_text(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = read_json(path)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _metric_values(evidence: Dict[str, Any], metric: str) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in (evidence.get("metrics") or {}).get("by_seed") or []:
        if not isinstance(row, dict):
            continue
        method = str(row.get("method") or "")
        value = (row.get("metrics") or {}).get(metric)
        if not method or not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        grouped.setdefault(method, []).append(
            {"seed": row.get("seed"), "value": float(value)}
        )
    return grouped


def result_figure_manifest_path(project: Path, experiment_id: str) -> Path:
    project = Path(project).resolve()
    spec = _load(project / "experiments" / str(experiment_id).strip() / "experiment-spec.json")
    return (
        project
        / "runs"
        / str(spec.get("run_id") or "")
        / "figures"
        / "empirical-result"
        / "figure-manifest.json"
    )


def build_result_figure(
    project: Path,
    experiment_id: str,
    *,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    root = project / "experiments" / str(experiment_id).strip()
    spec_path = root / "experiment-spec.json"
    execution_path = root / "execution.json"
    evidence_path = root / "experiment-evidence.json"
    claim_path = root / "claim.json"
    spec = _load(spec_path)
    execution = _load(execution_path)
    evidence = _load(evidence_path)
    claim = _load(claim_path)
    if not spec:
        raise ExperimentFigureError("experiment spec does not exist: " + str(spec_path))
    if evidence.get("status") != "verified":
        raise ExperimentFigureError("experiment evidence is not verified; run experiment ingest first")
    if execution.get("status") != "completed" or execution.get("dry_run"):
        raise ExperimentFigureError("a completed non-dry-run execution is required for a result figure")
    if evidence.get("spec_sha256") != _sha(spec_path):
        raise ExperimentFigureError("evidence is not bound to the current experiment spec")
    if evidence.get("execution_sha256") != _sha(execution_path):
        raise ExperimentFigureError("evidence is not bound to the current execution")
    data_path = project / str((spec.get("data") or {}).get("path") or "")
    if not data_path.is_file() or evidence.get("data_sha256") != _sha(data_path):
        raise ExperimentFigureError("evidence is not bound to the current data file")
    metric = str(evidence.get("primary_metric") or "")
    grouped = _metric_values(evidence, metric)
    if len(grouped) < 2:
        raise ExperimentFigureError("at least two methods with numeric metrics are required")
    methods = [
        str(item) for item in ((spec.get("design") or {}).get("methods") or [])
        if str(item) in grouped
    ]
    if not methods:
        methods = list(grouped.keys())
    seeds = sorted({item.get("seed") for values in grouped.values() for item in values if item.get("seed") is not None})
    rows = [
        {"method": method, "seed": item.get("seed"), metric: item["value"]}
        for method in methods
        for item in grouped[method]
    ]
    means: List[float] = []
    stds: List[float] = []
    for method in methods:
        values = [item["value"] for item in grouped[method]]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        means.append(mean)
        stds.append(variance ** 0.5)
    output_root = (
        result_figure_manifest_path(project, experiment_id).parent
        if not output_dir
        else Path(output_dir)
    )
    output_root = project_output_path(project, str(output_root), "figure output")
    output_root.mkdir(parents=True, exist_ok=True)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axis = plt.subplots(figsize=(6.4, 4.0))
    positions = list(range(len(methods)))
    axis.bar(positions, means, yerr=stds, capsize=5, color="#4C78A8", width=0.55)
    axis.set_xticks(positions)
    axis.set_xticklabels(methods)
    axis.set_xlabel("method")
    axis.set_ylabel(metric)
    axis.set_title("%s by method (mean +/- std, %d seeds)" % (metric, len(seeds)))
    axis.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    figure_id = "FIG-%s-%s" % (
        re.sub(r"[^A-Za-z0-9._-]+", "-", str(experiment_id))[:60] or "EXP",
        re.sub(r"[^A-Za-z0-9._-]+", "-", metric)[:30] or "metric",
    )
    png = output_root / (figure_id + ".png")
    svg = output_root / (figure_id + ".svg")
    figure.savefig(str(png), dpi=300)
    figure.savefig(str(svg))
    plt.close(figure)
    caption = (
        "图 1 在 %d 个随机种子上，%s 的 %s 均值与标准差（误差线）；"
        "数据来自本地实验 %s，证据 SHA-256 为 %s。"
        % (
            len(seeds),
            "、".join(methods),
            metric,
            experiment_id,
            str(evidence.get("execution_sha256") or "")[:12],
        )
    )
    manifest = {
        "schema_version": FIGURE_SCHEMA,
        "figure_id": figure_id,
        "figure_number": 1,
        "experiment_id": experiment_id,
        "run_id": spec.get("run_id"),
        "metric": metric,
        "methods": methods,
        "seeds": seeds,
        "rows": rows,
        "data_sha256": _sha_text(rows),
        "caption": caption,
        "insert_after_heading": "结果",
        "spec_path": str(spec_path),
        "spec_sha256": _sha(spec_path),
        "execution_path": str(execution_path),
        "execution_sha256": _sha(execution_path),
        "evidence_path": str(evidence_path),
        "evidence_sha256": _sha(evidence_path),
        "claim_path": str(claim_path) if claim_path.is_file() else "",
        "claim_sha256": _sha(claim_path) if claim_path.is_file() else "",
        "claim_status": claim.get("status") or "missing",
        "png": str(png),
        "svg": str(svg),
        "output_sha256": _sha(png),
        "svg_sha256": _sha(svg),
        "schematic": False,
        "kind": "data_result_plot",
        "renderer": "matplotlib",
        "astradraw": False,
        "workflow": "verified_evidence_result_plot",
        "created_at": _now(),
        "boundary": FIGURE_BOUNDARY,
    }
    manifest_path = output_root / "figure-manifest.json"
    write_json_atomic(manifest_path, manifest)
    (output_root / "figure-caption.md").write_text(
        "%s\n\n- PNG: `%s`\n- SVG: `%s`\n- evidence: `%s`\n\n%s\n"
        % (caption, png, svg, evidence_path, FIGURE_BOUNDARY),
        encoding="utf-8",
    )
    return {**manifest, "manifest": str(manifest_path)}


def verify_result_figure(
    manifest_path: Path,
    *,
    project: Optional[Path] = None,
) -> Dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    manifest = _load(manifest_path)
    errors: List[str] = []
    if not manifest or manifest.get("schema_version") != FIGURE_SCHEMA:
        return {"status": "stale", "errors": ["missing or unsupported figure manifest"]}
    if manifest.get("schematic") is not False:
        errors.append("result figure must be schematic=false")
    if manifest.get("kind") != "data_result_plot":
        errors.append("result figure must be kind=data_result_plot")
    if manifest.get("astradraw") is not False:
        errors.append("AstraDraw schematics cannot be verified as result figures")
    root = Path(project).resolve() if project else None
    for path_key, hash_key in (
        ("spec_path", "spec_sha256"),
        ("execution_path", "execution_sha256"),
        ("evidence_path", "evidence_sha256"),
        ("claim_path", "claim_sha256"),
        ("png", "output_sha256"),
        ("svg", "svg_sha256"),
    ):
        raw = str(manifest.get(path_key) or "")
        expected = str(manifest.get(hash_key) or "")
        if not raw:
            if path_key == "claim_path":
                continue
            errors.append("missing " + path_key)
            continue
        path = Path(raw)
        if root is not None:
            try:
                path.resolve().relative_to(root)
            except ValueError:
                errors.append(path_key + " escapes the project")
                continue
        if not path.is_file():
            errors.append(path_key + " does not exist")
            continue
        if _sha(path) != expected:
            errors.append(path_key + " hash mismatch")
    if manifest.get("data_sha256") != _sha_text(manifest.get("rows") or []):
        errors.append("figure rows hash mismatch")
    return {
        "schema_version": FIGURE_SCHEMA,
        "figure_id": manifest.get("figure_id"),
        "status": "clean" if not errors else "stale",
        "errors": errors,
        "manifest": str(manifest_path),
        "boundary": FIGURE_BOUNDARY,
    }

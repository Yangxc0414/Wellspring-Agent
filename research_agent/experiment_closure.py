"""Closure and lineage profile for generated local experiments.

This is not the canonical RunCapsule/EA closure. It binds the experiment spec,
data, code, approval, execution, metrics, evidence and human claim into a
separate local-experiment closure report. A human signature is still required.
"""

import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .closure_profiles import LOCAL_EXPERIMENT
from .experiment_figures import result_figure_manifest_path, verify_result_figure
from .storage import read_json, write_json_atomic

CLOSURE_SCHEMA = "experiment-closure-0.1"
SIGNATURE_SCHEMA = "experiment-signature-0.1"
LINEAGE_SCHEMA = "experiment-lineage-0.1"
LOCAL_CLOSURE_BOUNDARY = (
    "Local experiment closure profile: not a RunCapsule/EA, not peer review, "
    "not legal signature, no auto-submission."
)


class ExperimentClosureError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    try:
        return read_json(path)
    except Exception:
        return None


def _root(project: Path, experiment_id: str) -> Path:
    root = Path(project).resolve() / "experiments" / str(experiment_id).strip()
    if not root.is_dir():
        raise ExperimentClosureError("experiment package does not exist: " + str(root))
    return root


def _assertion_ok(item: Dict[str, Any], observed: Any) -> bool:
    if not isinstance(observed, (int, float)) or isinstance(observed, bool):
        return False
    try:
        target = float(item.get("value"))
        tolerance = float(item.get("tolerance", 0.01))
        comparator = str(item.get("comparator") or ">=")
    except (TypeError, ValueError):
        return False
    if comparator == ">=":
        return float(observed) >= target - tolerance
    if comparator == "<=":
        return float(observed) <= target + tolerance
    if comparator == ">":
        return float(observed) > target
    if comparator == "<":
        return float(observed) < target
    if comparator == "==":
        return abs(float(observed) - target) <= tolerance
    return False


def check_experiment_closure(
    project: Path,
    experiment_id: str,
    *,
    manuscript: Optional[Path] = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    root = _root(project, experiment_id)
    spec = _load(root / "experiment-spec.json") or {}
    manifest = _load(root / "code-manifest.json") or {}
    approval = _load(root / "execution-approval.json") or {}
    execution = _load(root / "execution.json") or {}
    evidence = _load(root / "experiment-evidence.json") or {}
    claim = _load(root / "claim.json") or {}
    checks: List[Dict[str, str]] = []
    blockers: List[str] = []
    warnings: List[str] = []

    def add(check_id: str, ok: bool, detail: str) -> None:
        checks.append({"id": check_id, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            blockers.append("%s: %s" % (check_id, detail))

    data_path = project / str((spec.get("data") or {}).get("path") or "")
    add("spec.present", bool(spec), "experiment-spec.json")
    add("data.present", data_path.is_file(), str(data_path))
    if data_path.is_file():
        add(
            "data.hash",
            _sha(data_path) == str((spec.get("data") or {}).get("sha256") or ""),
            "spec data hash",
        )
    for item in manifest.get("files") or []:
        path = root / str(item.get("name") or "")
        add(
            "code." + str(item.get("name")),
            path.is_file() and _sha(path) == str(item.get("sha256") or ""),
            "code manifest hash",
        )
    add("approval.present", bool(approval), "execution-approval.json")
    add("approval.data", approval.get("data_sha256") == (spec.get("data") or {}).get("sha256"), "approval data hash")
    add("approval.spec", approval.get("spec_sha256") == _sha(root / "experiment-spec.json"), "approval spec hash")
    add("approval.code", approval.get("code_sha256") == _sha(root / "run_experiment.py"), "approval code hash")
    add("execution.completed", execution.get("status") == "completed", str(execution.get("status")))
    add("execution.not_dry_run", not execution.get("dry_run"), "dry-run cannot close")
    add("evidence.verified", evidence.get("status") == "verified", str(evidence.get("status")))
    add("evidence.execution", evidence.get("execution_sha256") == _sha(root / "execution.json"), "evidence execution hash")
    add("claim.supported", claim.get("status") == "supported", str(claim.get("status")))
    add("claim.evidence", claim.get("evidence_sha256") == _sha(root / "experiment-evidence.json"), "claim evidence hash")
    if evidence.get("ridge_alpha") is not None or claim.get("ridge_alpha") is not None:
        add(
            "claim.ridge_alpha",
            claim.get("ridge_alpha") == evidence.get("ridge_alpha"),
            "claim alpha=%s evidence alpha=%s"
            % (claim.get("ridge_alpha"), evidence.get("ridge_alpha")),
        )
    if evidence.get("cv_folds"):
        add(
            "claim.cv_folds",
            int(claim.get("cv_folds") or 0) == int(evidence.get("cv_folds") or 0),
            "claim cv_folds=%s evidence cv_folds=%s"
            % (claim.get("cv_folds"), evidence.get("cv_folds")),
        )
    results_table = Path(str(evidence.get("results_table") or ""))
    if str(evidence.get("results_table") or ""):
        add(
            "results_table.present",
            results_table.is_file(),
            str(results_table),
        )
        if results_table.is_file():
            add(
                "results_table.hash",
                _sha(results_table) == str(evidence.get("results_table_sha256") or ""),
                "results table hash",
            )
        add(
            "claim.results_table",
            str(claim.get("results_table_sha256") or "")
            == str(evidence.get("results_table_sha256") or ""),
            "claim results table hash",
        )
    assertions = claim.get("assertions") or []
    if assertions:
        failed = [
            item for item in assertions
            if not _assertion_ok(item, evidence.get("mean"))
        ]
        add("claim.assertions", not failed, "failed assertions=%s" % len(failed))
    else:
        warnings.append("claim has no structured assertions; numeric support not re-verified")
    figure_path = result_figure_manifest_path(project, experiment_id)
    figure_manifest = {}
    figure_status = "missing"
    if figure_path.is_file():
        verification = verify_result_figure(figure_path, project=project)
        figure_status = str(verification.get("status") or "stale")
        add(
            "figure.binding",
            figure_status == "clean",
            "; ".join(verification.get("errors") or []),
        )
        figure_manifest = _load(figure_path) or {}
        add(
            "figure.not_schematic",
            figure_manifest.get("schematic") is False,
            "schematic=%s" % figure_manifest.get("schematic"),
        )
        add(
            "figure.data_result_plot",
            figure_manifest.get("kind") == "data_result_plot"
            and figure_manifest.get("astradraw") is False,
            "kind=%s astradraw=%s"
            % (figure_manifest.get("kind"), figure_manifest.get("astradraw")),
        )
    else:
        warnings.append("no data-backed result figure; closure has no figure binding")
    method_info = (
        _load(project / "runs" / str(spec.get("run_id") or "") / "figures" / "method-figure.json")
        if spec.get("run_id")
        else {}
    ) or {}
    method_manifest = (
        _load(Path(str(method_info.get("manifest") or ""))) if method_info else {}
    ) or {}
    method_svg = Path(str((method_manifest.get("files") or {}).get("svg") or ""))
    if method_info and method_manifest:
        schematic_ok = (
            method_manifest.get("kind") == "astradraw_scene"
            and method_manifest.get("schematic") is True
        )
        checks.append(
            {
                "id": "method_figure.schematic",
                "status": "pass" if schematic_ok else "fail",
                "detail": "kind=%s schematic=%s"
                % (method_manifest.get("kind"), method_manifest.get("schematic")),
                "severity": "warning",
            }
        )
        if not schematic_ok:
            warnings.append("method figure is not a labeled AstraDraw schematic")
        svg_ok = (
            method_svg.is_file()
            and _sha(method_svg) == str(method_manifest.get("svg_sha256") or "")
        )
        checks.append(
            {
                "id": "method_figure.svg",
                "status": "pass" if svg_ok else "fail",
                "detail": "method schematic SVG hash",
                "severity": "warning",
            }
        )
        if not svg_ok:
            warnings.append("method schematic SVG is missing or stale")
    artifact_refs = []
    if data_path.is_file():
        artifact_refs.append(str(data_path))
    for name in (
        "experiment-spec.json", "run_experiment.py", "code-manifest.json",
        "execution-approval.json", "execution.json", "experiment-evidence.json", "claim.json",
    ):
        path = root / name
        if path.is_file():
            artifact_refs.append(str(path))
    outs = root / "outputs"
    for name in ("metrics.json", "predictions.csv", "run-receipt.json", "artifact-manifest.json"):
        path = outs / name
        if path.is_file():
            artifact_refs.append(str(path))
    for path in (
        figure_path,
        Path(str(figure_manifest.get("png") or "")),
        Path(str(figure_manifest.get("svg") or "")),
        Path(str(method_info.get("manifest") or "")),
        method_svg,
        results_table,
    ):
        if str(path) and path.is_file() and str(path) not in artifact_refs:
            artifact_refs.append(str(path))
    manifest_file = outs / "artifact-manifest.json"
    if manifest_file.is_file():
        output_manifest = _load(manifest_file) or {}
        for item in output_manifest.get("artifacts") or []:
            path = outs / str(item.get("name") or "")
            add(
                "output." + str(item.get("name")),
                path.is_file() and _sha(path) == str(item.get("sha256") or ""),
                "output artifact hash",
            )
    if manuscript is not None:
        manuscript = Path(manuscript)
        add("manuscript.present", manuscript.is_file(), str(manuscript))
        if manuscript.is_file():
            from .writing_audit import audit_manuscript

            audit = audit_manuscript(
                manuscript, project=project, run_id=str(spec.get("run_id") or ""),
                experiment_id=experiment_id,
            )
            add("manuscript.audit", audit.get("status") == "ready_for_human_review", audit.get("status"))
            add("manuscript.not_submission_ready", audit.get("submission_ready") is False, "submission_ready")
            artifact_refs.append(str(manuscript))
    run_id = str(spec.get("run_id") or "")
    support_panel_path = project / "runs" / run_id / "support-panel.json" if run_id else None
    support_panel: Dict[str, Any] = {}
    if support_panel_path is not None and support_panel_path.is_file():
        support_panel = _load(support_panel_path) or {}
        panel_status = str(support_panel.get("status") or "missing")
        add(
            "support_panel.ready",
            panel_status in ("ready", "not_applicable"),
            "status=%s pending_human=%d"
            % (panel_status, len(support_panel.get("pending_human") or [])),
        )
        if manuscript is not None and Path(manuscript).is_file():
            add(
                "support_panel.manuscript",
                str(support_panel.get("draft_sha256") or "") == _sha(Path(manuscript)),
                "panel draft must match the final manuscript",
            )
        artifact_refs.append(str(support_panel_path))
    status = "ready_for_human_signature" if not blockers else "blocked"
    report = {
        "schema_version": CLOSURE_SCHEMA,
        "closure_profile": LOCAL_EXPERIMENT,
        "report_id": "EXP-CLR-" + experiment_id,
        "experiment_id": experiment_id,
        "run_id": spec.get("run_id"),
        "status": status,
        "created_at": _now(),
        "spec_sha256": _sha(root / "experiment-spec.json"),
        "execution_sha256": _sha(root / "execution.json") if (root / "execution.json").is_file() else "",
        "evidence_sha256": _sha(root / "experiment-evidence.json") if (root / "experiment-evidence.json").is_file() else "",
        "claim_sha256": _sha(root / "claim.json") if (root / "claim.json").is_file() else "",
        "support_panel": {
            "path": str(support_panel_path) if support_panel_path and support_panel_path.is_file() else "",
            "status": str(support_panel.get("status") or "missing"),
            "fingerprint": str(support_panel.get("panel_fingerprint") or ""),
            "pending_human": len(support_panel.get("pending_human") or []),
        },
        "figure": {
            "manifest": str(figure_path) if figure_path.is_file() else "",
            "status": figure_status,
            "figure_id": figure_manifest.get("figure_id"),
        },
        "method_figure": {
            "manifest": str(method_info.get("manifest") or ""),
            "figure_id": method_manifest.get("figure_id"),
            "schematic": bool(method_manifest.get("schematic")),
        },
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "artifact_refs": artifact_refs,
        "boundary": LOCAL_CLOSURE_BOUNDARY,
    }
    destination = Path(output_dir) if output_dir else root / "experiment-closure"
    destination.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination / "closure-report.json", report)
    lines = [
        "# Experiment Closure",
        "",
        "- experiment: `%s`" % experiment_id,
        "- status: **%s**" % status,
        "",
        "## Checks",
        "",
    ]
    for item in checks:
        lines.append("- %s: %s — %s" % (item["id"], item["status"], item["detail"]))
    lines += ["", "## Blockers", ""]
    for item in blockers:
        lines.append("- " + item)
    lines += ["", LOCAL_CLOSURE_BOUNDARY, ""]
    (destination / "closure-report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def sign_experiment_closure(
    project: Path,
    experiment_id: str,
    report_path: Path,
    human_reason: str,
    *,
    signer_store: Any = None,
    signer_id: str = "",
    output_dir: Optional[Path] = None,
    manuscript: Optional[Path] = None,
) -> Dict[str, Any]:
    if not str(human_reason or "").strip():
        raise ExperimentClosureError("human_reason is required")
    project = Path(project).resolve()
    root = _root(project, experiment_id)
    report = _load(Path(report_path))
    if not isinstance(report, dict) or report.get("status") != "ready_for_human_signature":
        raise ExperimentClosureError("closure report is not ready_for_human_signature")
    with tempfile.TemporaryDirectory(prefix="exp-closure-") as temp:
        fresh = check_experiment_closure(
            project,
            experiment_id,
            manuscript=manuscript,
            output_dir=Path(temp),
        )
    if fresh.get("status") != "ready_for_human_signature":
        raise ExperimentClosureError("closure is no longer ready for the current experiment")
    if report.get("checks") != fresh.get("checks"):
        raise ExperimentClosureError("submitted report checks do not match current experiment; re-run closure")
    destination = Path(output_dir) if output_dir else root / "experiment-closure"
    destination.mkdir(parents=True, exist_ok=True)
    files = {}
    for value in [*fresh.get("artifact_refs", []), str(report_path)]:
        path = Path(value).resolve()
        if path.is_file():
            files[str(path)] = _sha(path)
    manifest = {
        "schema_version": "experiment-export-manifest-0.1",
        "closure_profile": LOCAL_EXPERIMENT,
        "report_id": report.get("report_id"),
        "checks_sha256": hashlib.sha256(
            json.dumps(fresh.get("checks"), ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "files": files,
        "submission": False,
        "created_at": _now(),
    }
    manifest_path = destination / "export-manifest.json"
    write_json_atomic(manifest_path, manifest)
    payload = {
        "schema_version": SIGNATURE_SCHEMA,
        "closure_profile": LOCAL_EXPERIMENT,
        "report_id": report.get("report_id"),
        "export_manifest_sha256": _sha(manifest_path),
        "human_reason": str(human_reason).strip()[:1000],
        "submission": False,
    }
    signature_fields = {}
    if signer_store is not None:
        if not signer_id:
            raise ExperimentClosureError("signer_id is required with signer_store")
        signature_fields = signer_store.sign(signer_id, payload)
    signature = {
        **payload,
        "created_at": _now(),
        "artifact_refs": [str(report_path), str(manifest_path)],
        "boundary": LOCAL_CLOSURE_BOUNDARY,
        **signature_fields,
    }
    signature_path = destination / "signature.json"
    write_json_atomic(signature_path, signature)
    return {
        "signature": signature,
        "signature_path": str(signature_path),
        "manifest": str(manifest_path),
        "boundary": LOCAL_CLOSURE_BOUNDARY,
    }


def build_experiment_lineage(
    project: Path,
    experiment_id: str,
    *,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    root = _root(project, experiment_id)
    spec = _load(root / "experiment-spec.json") or {}
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, str]] = []

    def node(node_id: str, path: Path, upstream: Optional[str] = None) -> None:
        if not path.is_file():
            return
        nodes.append({
            "node_id": node_id,
            "path": str(path),
            "sha256": _sha(path),
            "upstream": upstream or "",
        })
        if upstream:
            edges.append({"from": upstream, "to": node_id})

    node("spec", root / "experiment-spec.json")
    data_path = project / str((spec.get("data") or {}).get("path") or "")
    node("data", data_path, "spec")
    node("code", root / "run_experiment.py", "spec")
    node("approval", root / "execution-approval.json", "spec")
    node("execution", root / "execution.json", "approval")
    node("metrics", root / "outputs" / "metrics.json", "execution")
    node("receipt", root / "outputs" / "run-receipt.json", "execution")
    node("evidence", root / "experiment-evidence.json", "metrics")
    evidence = _load(root / "experiment-evidence.json") or {}
    results_table = Path(str(evidence.get("results_table") or ""))
    node("results_table", results_table, "evidence")
    node("claim", root / "claim.json", "evidence")
    run_id = str(spec.get("run_id") or "")
    support_panel_path = project / "runs" / run_id / "support-panel.json" if run_id else None
    if support_panel_path is not None:
        node("support_panel", support_panel_path, "claim")
    figure_manifest_path = result_figure_manifest_path(project, experiment_id)
    if figure_manifest_path.is_file():
        figure = _load(figure_manifest_path) or {}
        node("figure_manifest", figure_manifest_path, "evidence")
        node("figure_png", Path(str(figure.get("png") or "")), "figure_manifest")
        node("figure_svg", Path(str(figure.get("svg") or "")), "figure_manifest")
    node("closure", root / "experiment-closure" / "closure-report.json", "claim")
    result = {
        "schema_version": LINEAGE_SCHEMA,
        "experiment_id": experiment_id,
        "created_at": _now(),
        "nodes": nodes,
        "edges": edges,
        "boundary": LOCAL_CLOSURE_BOUNDARY,
    }
    destination = Path(output_dir) if output_dir else root / "experiment-lineage"
    destination.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination / "lineage.json", result)
    return result


def verify_experiment_lineage(
    project: Path,
    experiment_id: str,
    *,
    lineage_path: Optional[Path] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    root = _root(project, experiment_id)
    path = Path(lineage_path) if lineage_path else root / "experiment-lineage" / "lineage.json"
    lineage = _load(path)
    if not isinstance(lineage, dict):
        raise ExperimentClosureError("experiment lineage is missing")
    checks = []
    stale = []
    for item in lineage.get("nodes") or []:
        node_path = Path(str(item.get("path") or ""))
        ok = node_path.is_file() and _sha(node_path) == str(item.get("sha256") or "")
        checks.append({"node_id": item.get("node_id"), "status": "fresh" if ok else "stale"})
        if not ok:
            stale.append(item.get("node_id"))
    return {
        "status": "fresh" if not stale else "stale",
        "checks": checks,
        "stale": stale,
        "lineage": str(path),
        "boundary": LOCAL_CLOSURE_BOUNDARY,
    }

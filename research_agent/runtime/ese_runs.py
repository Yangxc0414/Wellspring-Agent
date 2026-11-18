"""Read-only scan of local ESE study directories for the runtime front page.

The runtime previously served a bare HTML placeholder while every real ESE run lived only in
runtime_data/. This module turns those directories into a small, honest view: study id, commit
count, pooled rate, adjusted difference, capsule digest and the artifact paths. It reads files
only and never touches gates or claims.
"""

import hashlib
import json
from pathlib import Path

SCHEMA = "runtime-ese-runs-0.1"
BOUNDARY = (
    "read-only local view; exploratory repository-mining results; no Claim/EA/signature and no "
    "gate decision is produced or changed"
)


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return ""


def scan_ese_runs(root):
    """Return one summary per directory that has result.json (optionally a run capsule)."""
    base = Path(root)
    if not base.is_dir():
        return []
    runs = []
    for directory in sorted(base.iterdir()):
        if not directory.is_dir():
            continue
        result_path = directory / "result.json"
        if not result_path.is_file():
            continue
        result = _read_json(result_path)
        pooled = result.get("pooled") or {}
        stratified = result.get("stratified") or {}
        capsule_path = directory / "run" / "run-capsule.json"
        capsule = _read_json(capsule_path)
        runs.append({
            "study_id": str(result.get("study_id") or directory.name),
            "directory": directory.name,
            "commits": pooled.get("commits"),
            "rate": pooled.get("rate"),
            "ci": pooled.get("ci"),
            "adjusted_difference": stratified.get("adjusted_difference"),
            "bugfix_difference": pooled.get("difference"),
            "capsule": str(capsule_path) if capsule_path.is_file() else "",
            "capsule_sha256": _sha256(capsule_path) if capsule_path.is_file() else "",
            "status": str(capsule.get("status") or "no-capsule"),
            "result_mtime": result_path.stat().st_mtime,
        })
    runs.sort(key=lambda item: item.get("result_mtime") or 0, reverse=True)
    for item in runs:
        item.pop("result_mtime", None)
    return runs


def summary(root):
    runs = scan_ese_runs(root)
    return {"schema": SCHEMA, "count": len(runs), "runs": runs, "boundary": BOUNDARY}

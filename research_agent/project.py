"""Bounded research project folders for CLI and MCP integrations.

A project is a plain directory with a manifest and fixed subfolders. It is not
an evidence store: runs still use the same TaskAgent/Claim/Closure boundaries.
MCP callers may only create, run and read inside an allowed project root.
"""

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import JsonStoreError, read_json, write_json_atomic

PROJECT_SCHEMA = "research-project-0.1"
RUN_INDEX_SCHEMA = "research-run-index-0.1"
PROJECT_DIRS = (
    "inputs",
    "runs",
    "protocols",
    "claims",
    "closure",
    "studies",
    "memory",
    "notes",
)
RUN_ID_RE = re.compile(r"^RUN-[A-Za-z0-9-]+$")
TEXT_SUFFIXES = {
    ".json", ".jsonl", ".md", ".txt", ".csv", ".tsv", ".yaml", ".yml",
    ".svg", ".log", ".tex", ".bib", ".py", ".toml", ".html",
}
MAX_LISTED_FILES = 500
MAX_READ_CHARS = 400_000
PROJECT_BOUNDARY = (
    "project folders hold run artifacts only; G1/G2/S5b/G3/G5 claim, closure, "
    "signature and export decisions remain human-only"
)


class ProjectError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_name(name: str, fallback: str) -> str:
    value = re.sub(r"[\x00-\x1f]+", " ", str(name or "")).strip()
    value = re.sub(r"\s+", " ", value)
    return (value or fallback)[:120]


def _inside(root: Path, target: Path, allow_root: bool = False) -> Path:
    root = Path(root).resolve()
    target = Path(target).expanduser().resolve()
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise ProjectError("path must stay inside the allowed root: %s" % root)
    if not allow_root and not str(relative):
        raise ProjectError("path must point below the allowed root")
    return target


def resolve_root(root: Optional[str] = None) -> Path:
    raw = (root or os.environ.get("RESEARCH_AGENT_MCP_ROOT") or os.getcwd()).strip()
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise ProjectError("allowed root is not a directory: %s" % path)
    return path


def resolve_project(root: Path, project_dir: Optional[str] = None) -> Path:
    root = resolve_root(str(root))
    raw = (project_dir or "research-project").strip()
    target = Path(raw).expanduser()
    if not target.is_absolute():
        target = root / target
    return _inside(root, target, allow_root=True)


def _manifest(path: Path) -> Dict[str, Any]:
    payload = read_json(path / "project.json")
    if not isinstance(payload, dict):
        raise ProjectError("project.json is missing or invalid: %s" % (path / "project.json"))
    if payload.get("schema_version") != PROJECT_SCHEMA:
        raise ProjectError("unsupported project schema: %s" % payload.get("schema_version"))
    return payload


def init_project(path: Path, name: str = "") -> Dict[str, Any]:
    """Create or return a project. Never overwrites an existing manifest."""
    target = Path(path).expanduser().resolve()
    if target.exists() and not target.is_dir():
        raise ProjectError("project path is not a directory: %s" % target)
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / "project.json"
    if manifest_path.is_file():
        payload = _manifest(target)
        for folder in PROJECT_DIRS:
            (target / folder).mkdir(exist_ok=True)
        return {"created": False, "project": payload, "path": str(target)}
    for folder in PROJECT_DIRS:
        (target / folder).mkdir(exist_ok=True)
    created_at = _now()
    project_id = "PRJ-" + hashlib.sha256(
        (str(target) + created_at).encode("utf-8")
    ).hexdigest()[:10]
    payload = {
        "schema_version": PROJECT_SCHEMA,
        "project_id": project_id,
        "name": _clean_name(name, target.name or "research-project"),
        "created_at": created_at,
        "paths": {folder: folder for folder in PROJECT_DIRS},
        "boundary": PROJECT_BOUNDARY,
    }
    write_json_atomic(manifest_path, payload)
    return {"created": True, "project": payload, "path": str(target)}


def open_project(path: Path) -> Dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.is_dir():
        raise ProjectError("project directory does not exist: %s" % target)
    return {"project": _manifest(target), "path": str(target)}


def new_run_dir(project: Path) -> Path:
    manifest = _manifest(project)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "RUN-%s-%s" % (stamp, uuid.uuid4().hex[:6])
    target = Path(project).resolve() / "runs" / run_id
    target.mkdir(parents=True, exist_ok=False)
    write_json_atomic(
        target / "run-context.json",
        {
            "schema_version": "research-run-context-0.1",
            "run_id": run_id,
            "project_id": manifest.get("project_id", ""),
            "created_at": _now(),
            "boundary": PROJECT_BOUNDARY,
        },
    )
    return target


def update_run_index(project: Path, entry: Dict[str, Any]) -> None:
    index_path = Path(project).resolve() / "runs" / "index.json"
    try:
        current = read_json(index_path)
    except JsonStoreError as exc:
        raise ProjectError(str(exc))
    if not isinstance(current, dict) or not isinstance(current.get("runs"), list):
        current = {"schema_version": RUN_INDEX_SCHEMA, "runs": []}
    runs = [item for item in current["runs"] if isinstance(item, dict)]
    run_id = str(entry.get("run_id", ""))
    runs = [item for item in runs if item.get("run_id") != run_id]
    runs.insert(0, dict(entry))
    write_json_atomic(
        index_path,
        {
            "schema_version": RUN_INDEX_SCHEMA,
            "updated_at": _now(),
            "runs": runs[:200],
        },
    )


def run_dir(project: Path, run_id: str) -> Path:
    value = str(run_id or "").strip()
    if not RUN_ID_RE.match(value):
        raise ProjectError("invalid run_id: %s" % value)
    target = (Path(project).resolve() / "runs" / value).resolve()
    return _inside(Path(project).resolve() / "runs", target)


def project_file(project: Path, relative: str, label: str = "file") -> Path:
    value = str(relative or "").strip()
    if not value:
        raise ProjectError("%s path is empty" % label)
    target = Path(value).expanduser()
    if not target.is_absolute():
        target = Path(project).resolve() / target
    target = _inside(Path(project).resolve(), target)
    if not target.is_file():
        raise ProjectError("%s does not exist inside project: %s" % (label, value))
    return target


def project_output_path(project: Path, relative: str, label: str = "output") -> Path:
    value = str(relative or "").strip()
    if not value:
        raise ProjectError("%s path is empty" % label)
    target = Path(value).expanduser()
    if not target.is_absolute():
        target = Path(project).resolve() / target
    return _inside(Path(project).resolve(), target)


def _optional_json(path: Path) -> Dict[str, Any]:
    try:
        value = read_json(path)
    except JsonStoreError:
        return {}
    return value if isinstance(value, dict) else {}


def _run_governance(target: Path) -> Dict[str, Any]:
    governance: Dict[str, Any] = {}
    panel = _optional_json(target / "support-panel.json")
    if panel:
        governance["support_panel"] = {
            "status": str(panel.get("status") or "missing"),
            "pending_human": len(panel.get("pending_human") or []),
        }
    gold = _optional_json(target / "support-gold.json")
    if gold:
        governance["support_gold"] = {
            "status": str(gold.get("status") or "missing"),
            "annotators": len(gold.get("annotators") or []),
            "mean_kappa": (gold.get("agreement") or {}).get("mean_kappa"),
            "panel_accuracy": (gold.get("panel") or {}).get("accuracy"),
        }
    audit = _optional_json(target / "writing-audit.json")
    if audit:
        governance["writing_audit"] = {"status": str(audit.get("status") or "missing")}
    return governance


def project_status(project: Path, limit: int = 20) -> Dict[str, Any]:
    opened = open_project(project)
    root = Path(project).resolve()
    entries: List[Dict[str, Any]] = []
    try:
        index = read_json(root / "runs" / "index.json")
    except JsonStoreError:
        index = None
    if isinstance(index, dict) and isinstance(index.get("runs"), list):
        entries = [item for item in index["runs"] if isinstance(item, dict)]
    if not entries:
        for path in sorted((root / "runs").glob("RUN-*"), reverse=True):
            if path.is_dir():
                entries.append({"run_id": path.name})
    runs: List[Dict[str, Any]] = []
    for entry in entries[:max(1, min(int(limit), 100))]:
        run_id = str(entry.get("run_id", ""))
        try:
            target = run_dir(root, run_id)
        except ProjectError:
            continue
        task: Dict[str, Any] = {}
        try:
            loaded = read_json(target / "task.json")
            task = loaded if isinstance(loaded, dict) else {}
        except JsonStoreError:
            task = {}
        row = {
            "run_id": run_id,
            "status": task.get("status", entry.get("status", "unknown")),
            "route": (task.get("plan") or {}).get("route", entry.get("route", "")),
            "stopped_at": task.get("stopped_at", entry.get("stopped_at", "")),
            "failure": task.get("failure", {}),
            "goal": entry.get("goal", ""),
            "created_at": entry.get("created_at", ""),
            "path": str(target),
        }
        governance = _run_governance(target)
        if governance:
            row["governance"] = governance
        runs.append(row)
    from .closure_profiles import detect_project_profiles

    return {
        "project": opened["project"],
        "project_dir": opened["path"],
        "runs": runs,
        "closure_profiles": detect_project_profiles(root, limit=limit),
        "boundary": PROJECT_BOUNDARY,
    }


def list_artifacts(project: Path, run_id: str) -> Dict[str, Any]:
    target = run_dir(project, run_id)
    files: List[Dict[str, Any]] = []
    for path in sorted(target.rglob("*")):
        if len(files) >= MAX_LISTED_FILES:
            break
        if not path.is_file() or path.is_symlink():
            continue
        try:
            resolved = path.resolve()
            _inside(target, resolved)
        except ProjectError:
            continue
        files.append(
            {
                "path": resolved.relative_to(target).as_posix(),
                "size": resolved.stat().st_size,
                "suffix": resolved.suffix.lower(),
            }
        )
    return {
        "run_id": run_id,
        "run_dir": str(target),
        "artifacts": files,
        "truncated": len(files) >= MAX_LISTED_FILES,
    }


def read_artifact(
    project: Path, run_id: str, relative: str, max_chars: int = 120_000
) -> Dict[str, Any]:
    target = run_dir(project, run_id)
    value = str(relative or "").strip()
    if not value:
        raise ProjectError("artifact path is empty")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = target / path
    path = _inside(target, path)
    if not path.is_file():
        raise ProjectError("artifact not found: %s" % value)
    suffix = path.suffix.lower()
    if suffix and suffix not in TEXT_SUFFIXES:
        raise ProjectError("artifact is not text-readable: %s" % suffix)
    limit = max(1_000, min(int(max_chars), MAX_READ_CHARS))
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > limit
    return {
        "run_id": run_id,
        "path": path.relative_to(target).as_posix(),
        "size": path.stat().st_size,
        "truncated": truncated,
        "text": text[:limit] + ("\n...[truncated]" if truncated else ""),
    }


PROJECT_INVENTORY_SCHEMA = "research-project-inventory-0.1"
EXPERIMENT_INVENTORY_SCHEMA = "project-experiment-inventory-0.1"
EXPERIMENT_ID_RE = re.compile(r"^EXP-[A-Za-z0-9._-]{1,80}$")
PROJECT_SCAN_SKIP = {
    "runtime_data", "oss", "cortex-agent", "claude-code-main", "template_refs",
    ".git", "__pycache__",
}


def _experiment_package_count(project: Path) -> int:
    root = Path(project).resolve() / "experiments"
    if not root.is_dir():
        return 0
    count = 0
    for child in root.iterdir():
        if child.is_dir() and EXPERIMENT_ID_RE.match(child.name):
            if (child / "experiment-spec.json").is_file():
                count += 1
    return count


def list_projects(root: Optional[str] = None) -> Dict[str, Any]:
    """List research projects under the allowed root, read-only."""
    root_path = resolve_root(str(root) if root else None)
    candidates: List[Path] = []
    for child in sorted(root_path.iterdir()):
        if child.name.startswith(".") or child.name in PROJECT_SCAN_SKIP:
            continue
        if child.is_dir() and (child / "project.json").is_file():
            candidates.append(child)
    runtime_root = root_path / "runtime_data"
    if runtime_root.is_dir():
        for child in sorted(runtime_root.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_dir() and (child / "project.json").is_file():
                candidates.append(child)
    projects: List[Dict[str, Any]] = []
    for path in candidates[:100]:
        try:
            manifest = _manifest(path)
        except ProjectError:
            continue
        projects.append(
            {
                "project_id": str(manifest.get("project_id") or ""),
                "name": str(manifest.get("name") or path.name),
                "project_dir": path.relative_to(root_path).as_posix(),
                "experiment_count": _experiment_package_count(path),
            }
        )
    projects.sort(key=lambda item: (item["project_dir"] != "runtime_data", item["name"]))
    return {
        "schema_version": PROJECT_INVENTORY_SCHEMA,
        "count": len(projects),
        "projects": projects,
        "boundary": "Read-only project inventory; it does not execute, sign or change evidence.",
    }


def list_project_experiments(project: Path, limit: int = 100) -> Dict[str, Any]:
    """List local experiment packages with their real read-only lifecycle stages."""
    project = Path(project).resolve()
    manifest = _manifest(project)
    root = project / "experiments"
    items: List[Dict[str, Any]] = []
    if root.is_dir():
        for child in sorted(root.iterdir()):
            if not child.is_dir() or not EXPERIMENT_ID_RE.match(child.name):
                continue
            if not (child / "experiment-spec.json").is_file():
                continue
            spec = _optional_json(child / "experiment-spec.json")
            try:
                from .experiment_runner import experiment_status

                status = experiment_status(project, child.name)
                stages = dict(status.get("stages") or {})
                next_action = str(status.get("next_action") or "")
                evidence_summary = status.get("evidence_summary") or {}
            except Exception as exc:
                stages = {}
                next_action = "status_unavailable"
                evidence_summary = {}
                status = {"error": type(exc).__name__}
            items.append(
                {
                    "experiment_id": child.name,
                    "idea_id": str(spec.get("idea_id") or ""),
                    "run_id": str(spec.get("run_id") or ""),
                    "design_status": str((spec.get("design") or {}).get("status") or ""),
                    "package": child.relative_to(project).as_posix(),
                    "stages": stages,
                    "next_action": next_action,
                    "evidence_summary": {
                        "status": evidence_summary.get("status"),
                        "mean": evidence_summary.get("mean"),
                        "std": evidence_summary.get("std"),
                        "cv_folds": evidence_summary.get("cv_folds"),
                    },
                    "error": str(status.get("error") or ""),
                }
            )
            if len(items) >= max(1, min(int(limit), 200)):
                break
    return {
        "schema_version": EXPERIMENT_INVENTORY_SCHEMA,
        "project_id": str(manifest.get("project_id") or ""),
        "name": str(manifest.get("name") or project.name),
        "count": len(items),
        "experiments": items,
        "boundary": (
            "Read-only project experiment inventory; execution, claims, closure and "
            "signatures remain local CLI/human operations."
        ),
    }

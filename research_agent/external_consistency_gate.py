"""Run a whitelisted external scientific-writing consistency check.

The external skill stays outside this repository. Only the known
`scientific-writing/scripts/check_consistency.py` entry is executed with the
current Python interpreter and an explicit skill root. It reads a caller-supplied
JSON registry, never modifies it, and never creates evidence or signatures.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

GATE_TOOL = "scientific-writing.check_consistency"
BOUNDARY = (
    "read-only external MIT skill consistency gate; caller-selected registry and skill root; "
    "current interpreter; no dependency installation, registry modification, evidence/claim/"
    "closure or signature"
)


class ExternalConsistencyGateError(ValueError):
    pass


def _skill_root(value: Optional[Path] = None) -> Path:
    raw = str(value or os.environ.get("RESEARCH_AGENT_EXTERNAL_SKILLS") or "").strip()
    if not raw:
        raise ExternalConsistencyGateError(
            "external skill root is required; pass --skill-root or set "
            "RESEARCH_AGENT_EXTERNAL_SKILLS"
        )
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ExternalConsistencyGateError("external skill root does not exist: " + str(root))
    return root


def run_consistency_check(
    registry_path: Path,
    skill_root: Optional[Path] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    root = _skill_root(skill_root)
    script = root / "skills" / "scientific-writing" / "scripts" / "check_consistency.py"
    if not script.is_file():
        raise ExternalConsistencyGateError(
            "whitelisted check_consistency.py not found under: " + str(root)
        )
    registry = Path(registry_path)
    if not registry.is_file():
        raise ExternalConsistencyGateError("consistency registry does not exist: " + str(registry))
    if registry.suffix.lower() != ".json":
        raise ExternalConsistencyGateError("consistency registry must be a .json file")
    try:
        completed = subprocess.run(
            [sys.executable, str(script), str(registry)],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max(1, min(int(timeout), 300)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalConsistencyGateError(
            "external consistency check failed to start: " + str(exc)
        )
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        raise ExternalConsistencyGateError(
            "external consistency check returned non-JSON output: "
            + (completed.stderr or completed.stdout or "")[:400]
        )
    if not isinstance(payload, dict) or payload.get("tool") not in (
        "check_consistency",
        GATE_TOOL,
    ):
        raise ExternalConsistencyGateError(
            "external consistency check returned an unexpected report"
        )
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    issues = [item for item in (payload.get("issues") or []) if isinstance(item, dict)]
    status = "blocked" if payload.get("status") == "fail" else "attention" if issues else "ready"
    return {
        "schema_version": "external-consistency-gate-0.1",
        "tool": GATE_TOOL,
        "external_tool": str(payload.get("tool") or ""),
        "skill_root": str(root),
        "registry": str(registry),
        "status": status,
        "external_status": payload.get("status"),
        "summary": summary,
        "issues": issues[:40],
        "exit_code": completed.returncode,
        "boundary": BOUNDARY,
    }

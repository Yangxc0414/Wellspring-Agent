"""Run a whitelisted external scientific-writing lint as a read-only gate.

The external skill stays outside this repository. Only the known
`scientific-writing/scripts/lint_manuscript.py` entry is executed with the
current Python interpreter and an explicit skill root. It never installs
dependencies, modifies the draft, creates evidence or signs anything.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

GATE_TOOL = "scientific-writing.lint_manuscript"
BOUNDARY = (
    "read-only external MIT skill lint; caller-selected root and current interpreter; "
    "no dependency installation, draft modification, evidence/claim/closure or signature"
)


class ExternalWritingGateError(ValueError):
    pass


def _skill_root(value: Optional[Path] = None) -> Path:
    raw = str(value or os.environ.get("RESEARCH_AGENT_EXTERNAL_SKILLS") or "").strip()
    if not raw:
        raise ExternalWritingGateError(
            "external skill root is required; pass --skill-root or set "
            "RESEARCH_AGENT_EXTERNAL_SKILLS"
        )
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ExternalWritingGateError("external skill root does not exist: " + str(root))
    return root


def run_writing_lint(
    draft_path: Path,
    skill_root: Optional[Path] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    root = _skill_root(skill_root)
    script = root / "skills" / "scientific-writing" / "scripts" / "lint_manuscript.py"
    if not script.is_file():
        raise ExternalWritingGateError(
            "whitelisted lint_manuscript.py not found under: " + str(root)
        )
    draft = Path(draft_path)
    if not draft.is_file():
        raise ExternalWritingGateError("draft does not exist: " + str(draft))
    try:
        completed = subprocess.run(
            [sys.executable, str(script), str(draft)],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=max(1, min(int(timeout), 300)),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExternalWritingGateError("external lint failed to start: " + str(exc))
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        raise ExternalWritingGateError(
            "external lint returned non-JSON output: "
            + (completed.stderr or completed.stdout or "")[:400]
        )
    if not isinstance(payload, dict) or payload.get("tool") not in (
        "lint_manuscript",
        GATE_TOOL,
    ):
        raise ExternalWritingGateError("external lint returned an unexpected report")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    issues = [item for item in (payload.get("issues") or []) if isinstance(item, dict)]
    status = "blocked" if payload.get("status") == "fail" else "attention" if issues else "ready"
    return {
        "schema_version": "external-writing-gate-0.1",
        "tool": GATE_TOOL,
        "external_tool": str(payload.get("tool") or ""),
        "skill_root": str(root),
        "draft": str(draft),
        "status": status,
        "external_status": payload.get("status"),
        "summary": summary,
        "issues": issues[:40],
        "exit_code": completed.returncode,
        "boundary": BOUNDARY,
    }

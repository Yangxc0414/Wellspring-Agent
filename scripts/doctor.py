#!/usr/bin/env python3
"""Diagnose the local research-agent environment without network calls.

The doctor never prints API key values. It reports presence only, checks the
MCP launcher, web workspace and optional external skill entry points, and
suggests the next command for each missing piece.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

KEY_ENV_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "ZHIPU_API_KEY",
    "OPENAI_COMPATIBLE_API_KEY",
    "LOCAL_LLM_API_KEY",
)
OPTIONAL_MODULES = ("numpy", "pandas", "sklearn", "matplotlib", "fastapi", "pydantic")
EXTERNAL_SCRIPTS = ("lint_manuscript.py", "audit_claims.py", "check_consistency.py")


def _node_version() -> str:
    node = shutil.which("node")
    if not node:
        return ""
    try:
        result = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
        return (result.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def check_environment(
    root: Path,
    skill_root: Optional[Path] = None,
) -> Dict[str, Any]:
    root = Path(root).resolve()
    checks: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    python_ok = sys.version_info >= (3, 8)
    checks.append(
        {
            "id": "python",
            "status": "ok" if python_ok else "blocked",
            "detail": platform.python_version(),
            "next": "" if python_ok else "install Python 3.8+",
        }
    )

    launcher = root / "scripts" / "research_mcp_server.py"
    checks.append(
        {
            "id": "mcp_launcher",
            "status": "ok" if launcher.is_file() else "blocked",
            "detail": str(launcher),
            "next": "" if launcher.is_file() else "restore scripts/research_mcp_server.py",
        }
    )

    web_package = root / "apps" / "web" / "package.json"
    node_version = _node_version()
    checks.append(
        {
            "id": "web_workspace",
            "status": "ok" if web_package.is_file() and node_version else "warn",
            "detail": "package.json=%s node=%s" % (web_package.is_file(), node_version or "missing"),
            "next": "install Node 20+ and run cd apps/web && npm ci" if not node_version else "",
        }
    )

    modules = {
        name: importlib.util.find_spec(name) is not None
        for name in OPTIONAL_MODULES
    }
    modules_ok = all(modules.values())
    checks.append(
        {
            "id": "optional_modules",
            "status": "ok" if modules_ok else "warn",
            "detail": modules,
            "next": "" if modules_ok else "pip install -r requirements-dev.txt (local environment only)",
        }
    )

    env_presence = {name: bool(os.environ.get(name, "").strip()) for name in KEY_ENV_NAMES}
    keys_present = any(env_presence.values())
    host_bound = {}
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from research_agent.models import GatewayStore
        from research_agent.models.store import default_store_path

        store = GatewayStore(default_store_path())
        for module, profile_id in sorted(store.bindings.items()):
            profile = store.profiles.get(profile_id)
            provider = store.providers.get(profile.provider_id) if profile else None
            host_bound[module] = bool(provider and provider.kind == "host_agent")
    except Exception as exc:
        host_bound = {"error": "%s: %s" % (type(exc).__name__, exc)}
    host_ready = bool(host_bound) and not host_bound.get("error") and any(host_bound.values())
    checks.append(
        {
            "id": "model_supply",
            "status": "ok" if keys_present or host_ready else "warn",
            "detail": {
                "provider_keys": env_presence,
                "host_agent_bound_modules": sorted(
                    key for key, value in host_bound.items() if value is True
                ),
            },
            "next": (
                ""
                if keys_present or host_ready
                else "set a provider key in the environment, or bind a keyless host-agent "
                     "profile with `python -m research_agent host-model bind`; test mode stays keyless"
            ),
        }
    )

    mcp_json = root / ".mcp.json"
    checks.append(
        {
            "id": "mcp_json",
            "status": "ok" if mcp_json.is_file() else "warn",
            "detail": "present" if mcp_json.is_file() else "missing (gitignored local config)",
            "next": "" if mcp_json.is_file() else "python scripts/setup_mcp.py",
        }
    )

    raw_skill_root = str(skill_root or os.environ.get("RESEARCH_AGENT_EXTERNAL_SKILLS") or "").strip()
    if raw_skill_root:
        external = Path(raw_skill_root).expanduser().resolve()
        scripts = {
            name: (external / "skills" / "scientific-writing" / "scripts" / name).is_file()
            for name in EXTERNAL_SCRIPTS
        }
        status = "ok" if all(scripts.values()) else "warn"
        detail = {"root": str(external), "scripts": scripts}
        next_action = "" if status == "ok" else "point --skill-root at a scientific-writing skill root"
    else:
        status = "warn"
        detail = {"root": "", "scripts": {}}
        next_action = "optional: set RESEARCH_AGENT_EXTERNAL_SKILLS or pass --skill-root"
    checks.append(
        {"id": "external_skills", "status": status, "detail": detail, "next": next_action}
    )

    blockers = [item for item in checks if item["status"] == "blocked"]
    warnings.extend(item for item in checks if item["status"] == "warn")
    return {
        "schema_version": "research-agent-doctor-0.1",
        "root": str(root),
        "platform": platform.platform(),
        "status": "blocked" if blockers else "ok",
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "boundary": (
            "local environment check only; it never reads key values, installs "
            "dependencies, calls models or changes claims/signatures"
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--skill-root", default="")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on warnings")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    report = check_environment(
        Path(args.root),
        Path(args.skill_root) if args.skill_root else None,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("doctor: %s" % report["status"])
        for item in report["checks"]:
            print("%-7s %-18s %s" % (item["status"].upper(), item["id"], item["detail"]))
            if item.get("next"):
                print("        next: %s" % item["next"])
    if report["status"] == "blocked":
        return 1
    if args.strict and report["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

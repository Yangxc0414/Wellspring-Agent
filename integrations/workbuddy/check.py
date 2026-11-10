"""Read-only preflight for the WorkBuddy MCP entry point.

Never starts the server, never writes a file, never changes a gate.
Works from the repository root or from the Wellspring-Agent distribution:
both place this file at <root>/integrations/workbuddy/check.py.

    python integrations/workbuddy/check.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("approve", "sign", "freeze", "publish", "export")


def main():
    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})
        return bool(ok)

    add(
        "python>=3.8",
        sys.version_info >= (3, 8),
        "%d.%d" % (sys.version_info[0], sys.version_info[1]),
    )
    launcher = ROOT / "scripts" / "research_mcp_server.py"
    add("launcher", launcher.is_file(), launcher.name)
    package = ROOT / "research_agent" / "mcp_server.py"
    add("mcp_server", package.is_file(), package.name)
    specs = sorted((ROOT / "modules").glob("*/SPEC.md"))
    add("module_specs", len(specs) > 0, "%d specs" % len(specs))

    tool_count = 0
    forbidden = []
    import_error = ""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from research_agent.mcp_server import TOOL_NAMES

        tool_count = len(TOOL_NAMES)
        forbidden = sorted(
            name for name in TOOL_NAMES if any(word in name for word in FORBIDDEN)
        )
    except Exception as exc:  # a missing dependency must be reported, not hidden
        import_error = "%s: %s" % (type(exc).__name__, exc)

    add(
        "tool_table",
        tool_count > 0 and not import_error,
        import_error or "%d tools" % tool_count,
    )
    add(
        "human_gates_closed",
        not forbidden,
        ", ".join(forbidden) or "no gate tools exposed",
    )

    # A fresh distribution has no project directory. Every project-scoped MCP tool
    # rejects its first call until research_project_init creates one. Report this as
    # guidance, not as a failed check: it is an expected first step, not a broken install.
    project_dir = ROOT / "research-project"
    project_present = project_dir.is_dir()

    report = {
        "root": ROOT.name,
        "checks": checks,
        "ok": all(item["ok"] for item in checks),
        "project_dir": "research-project",
        "project_dir_present": project_present,
        "first_call": (
            "run research_project_init with project_dir=research-project, "
            "or pass your custom project_dir to every project-scoped tool"
            if not project_present
            else "project directory exists; project-scoped tools can run"
        ),
        "read_only": True,
        "boundary": "preflight only; does not start the MCP server or change any state",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

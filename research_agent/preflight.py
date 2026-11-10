"""Governance preflight: which link of the spec->export->bundle chain is stale, in seconds.

A killed command chain leaves a partially updated repository, and the only existing detector
was the full test suite, which costs minutes. This module answers the same question directly:
is every SPEC self-consistent, is the exported registry current, and do the tool surfaces agree.
It reports facts and never repairs anything, and a green preflight is not a substitute for the
suite: it checks bookkeeping, not behaviour.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _spec_files(modules_dir: Optional[Path] = None) -> List[Path]:
    modules = Path(modules_dir) if modules_dir else REPO / "modules"
    if not modules.is_dir():
        return []
    return sorted(p for p in modules.glob("*/SPEC.md"))


def spec_self_consistency(modules_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Every SPEC's frontmatter version must appear in its own Changelog entry."""
    stale: List[Dict[str, str]] = []
    checked = 0
    for path in _spec_files(modules_dir):
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        version = ""
        for line in lines[:40]:
            if line.startswith("version:"):
                version = line.split(":", 1)[1].strip()
                break
        if not version:
            stale.append({"spec": _display(path), "problem": "no version field"})
            continue
        checked += 1
        marker = "v%s" % version
        if not any(marker in line for line in lines):
            stale.append(
                {
                    "spec": _display(path),
                    "problem": "version %s has no Changelog entry" % version,
                }
            )
    return {"checked": checked, "stale": stale}


def registry_freshness(target_path: Optional[Path] = None) -> Dict[str, Any]:
    """The committed agent registry must match what the SPECs project right now."""
    target = Path(target_path) if target_path else REPO / "apps" / "web" / "public" / "agent-registry.json"
    if not target.is_file():
        return {"status": "missing", "path": _display(target)}
    from .workspace import AgentRegistry

    committed = json.loads(target.read_text(encoding="utf-8"))
    live = AgentRegistry().snapshot()
    def index(snapshot: Dict[str, Any]) -> Dict[str, str]:
        return {
            str(item.get("id")): str(item.get("version"))
            for item in snapshot.get("agents") or []
        }

    before, after = index(committed), index(live)
    changed = [
        {"id": key, "exported": before.get(key), "live": after.get(key)}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    ]
    return {
        "status": "fresh" if not changed else "stale",
        "agents_exported": len(before),
        "agents_live": len(after),
        "changed": changed,
    }


def tool_surface_parity() -> Dict[str, Any]:
    """MCP TOOLS, the server's TOOL_NAMES and the integration SPEC tools list must agree."""
    from .mcp_server import TOOL_NAMES
    from .mcp_tools import TOOLS

    names = [str(item.get("name")) for item in TOOLS]
    problems: List[str] = []
    if names != list(TOOL_NAMES):
        problems.append("mcp_tools.TOOLS order differs from mcp_server.TOOL_NAMES")
    missing_in_spec = sorted(set(TOOL_NAMES) - _spec_tools())
    extra_in_spec = sorted(_spec_tools() - set(TOOL_NAMES))
    if missing_in_spec:
        problems.append("tools missing from the integration SPEC: %s" % ", ".join(missing_in_spec))
    if extra_in_spec:
        problems.append("SPEC lists tools that the server does not expose: %s" % ", ".join(extra_in_spec))
    return {
        "status": "fresh" if not problems else "stale",
        "tools": len(TOOL_NAMES),
        "problems": problems,
    }


def _spec_tools() -> set:
    path = REPO / "modules" / "integration" / "SPEC.md"
    if not path.is_file():
        return set()
    tools = set()
    inside = False
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.startswith("tools:"):
            inside = True
            continue
        if inside:
            if not line.startswith("  - "):
                break
            tools.add(line[4:].strip())
    return tools


def face_counts(http_tools: Optional[int] = None) -> Dict[str, Any]:
    """How many capabilities each face advertises.

    `http_tools` must be counted by the serving process: guessing it from the MCP list would
    turn an unmeasured face into a copy of a measured one, which is exactly the proxy signal
    this module exists to catch.
    """
    from .mcp_server import TOOL_NAMES
    from .workspace import CommandRegistry

    return {
        "mcp_tools": len(TOOL_NAMES),
        "http_tools": http_tools,
        "cli_commands": int(CommandRegistry().snapshot()["count"]),
    }


def build_preflight(http_tools: Optional[int] = None) -> Dict[str, Any]:
    specs = spec_self_consistency()
    registry = registry_freshness()
    tools = tool_surface_parity()
    if http_tools is None:
        blockers_hint = None
    blockers: List[str] = []
    if specs["stale"]:
        blockers.append("%d SPEC(s) lack a Changelog entry for their own version" % len(specs["stale"]))
    if registry.get("status") != "fresh":
        blockers.append("exported agent registry does not match the SPECs; run workspace export")
    if tools["status"] != "fresh":
        blockers.append("tool surfaces disagree: " + "; ".join(tools["problems"]))
    report = {
        "schema_version": "preflight-0.1",
        "faces": face_counts(http_tools),
        "checks": {"spec_self_consistency": specs, "registry": registry, "tool_surfaces": tools},
        "status": "stale" if blockers else "fresh",
        "blockers": blockers,
        "boundary": (
            "bookkeeping only: a fresh preflight means the spec/export/tool surfaces agree, "
            "not that behaviour is correct; run the test suite for that"
        ),
    }
    if http_tools is None:
        report["faces"]["http_tools_note"] = (
            "not measured from this process; the runtime route fills it with the count it serves"
        )
    return report

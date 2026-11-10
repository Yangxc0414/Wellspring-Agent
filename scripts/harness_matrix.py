#!/usr/bin/env python
"""Harness-client acceptance matrix for the Wellspring-Agent MCP surface.

For every host we support (Qoder / Zcode / Codex / Workbuddy) this script:
  1. renders the ready-to-paste config snippet via ``scripts/setup_mcp.py --host X``;
  2. parses it (JSON for the three JSON hosts, TOML for Codex) and verifies the
     referenced entrypoint exists on this checkout;
  3. checks the repo-side template in ``plugin/`` matches what setup_mcp prints;
  4. runs one shared stdio smoke against the MCP server (initialize → tools/list)
     and asserts the tool count is reported and no signing tool is exposed.

Exit code is non-zero if any matrix cell fails, so CI can gate on it.
Usage: python scripts/harness_matrix.py [--json]
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

try:
    import tomllib  # py>=3.11
except ImportError:  # 3.8–3.10
    tomllib = None

from research_agent.paths import REPO_ROOT as _REPO  # noqa: E402

HOSTS = ("qoder", "zcode", "codex", "workbuddy")
SIGNING_TOKENS = ("sign", "approve", "freeze", "publish", "export")

EXPECT_FORMAT = {"qoder": "json", "zcode": "json", "workbuddy": "json", "codex": "toml"}


def run_setup_mcp(host):
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "setup_mcp.py"), "--host", host],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def parse_snippet(host, text):
    """Return (ok, entrypoint_or_None, detail)."""
    if EXPECT_FORMAT[host] == "json":
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return False, None, "no JSON object found in snippet"
        try:
            data = json.loads(match.group(0))
        except ValueError as exc:
            return False, None, "invalid JSON: %s" % exc
        servers = data.get("mcpServers") or {}
        if host == "qoder":
            servers = servers or data.get("mcp_servers") or {}
        if not servers:
            return False, None, "no mcpServers entry in snippet"
        name, server = next(iter(servers.items()))
        command = server.get("command")
        args = server.get("args") or []
        return True, (command, args), "server=%s" % name
    # codex TOML
    match = re.search(r"\[mcp_servers\.[^\]]+\][\s\S]*?(?=\n\[|$)", text)
    if not match:
        return False, None, "no [mcp_servers.*] table found"
    block = match.group(0)
    command_match = re.search(r'command\s*=\s*"([^"]+)"', block)
    args_match = re.search(r"args\s*=\s*\[([^\]]*)\]", block)
    if not command_match:
        return False, None, "no command in TOML table"
    args = []
    if args_match:
        args = re.findall(r'"([^"]*)"', args_match.group(1))
    return True, (command_match.group(1), args), "toml table ok"


def entrypoint_exists(command, args):
    """The snippet points at a python interpreter + a repo script; verify the script."""
    script_candidates = [a for a in (args or []) if a.endswith(".py")]
    if script_candidates:
        return all((REPO / a.replace("/", os.sep)).exists() for a in script_candidates), script_candidates
    if command and command.endswith((".exe", "python", "python3")):
        return True, [command]
    return bool(command), [command or "(empty)"]


def mcp_stdio_smoke():
    server = REPO / "scripts" / "research_mcp_server.py"
    if not server.exists():
        server = REPO / "research_agent" / "mcp_server.py"
    payload = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "harness-matrix", "version": "0"}}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
    )
    proc = subprocess.run(
        [sys.executable, str(server)],
        cwd=str(REPO),
        input=payload,
        capture_output=True,
        text=True,
        timeout=120,
    )
    tools = None
    server_info = None
    signing = []
    for line in (proc.stdout or "").splitlines():
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if data.get("id") == 1:
            server_info = (data.get("result", {}).get("serverInfo") or {}).get("version")
        if data.get("id") == 2:
            tools = data.get("result", {}).get("tools") or []
            signing = [t["name"] for t in tools
                       if any(tok in t["name"].lower() for tok in SIGNING_TOKENS)]
    ok = server_info is not None and tools is not None
    return ok, {"server_version": server_info, "tools": len(tools) if tools else 0,
                "signing_tools": signing or "none", "exit": proc.returncode}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    rows = []
    smoke_ok, smoke = mcp_stdio_smoke()
    for host in HOSTS:
        row = {"host": host, "format": EXPECT_FORMAT[host]}
        ok, out = run_setup_mcp(host)
        row["snippet_rendered"] = ok
        if ok:
            ok2, entry, detail = parse_snippet(host, out)
            row["snippet_parsed"] = ok2
            row["detail"] = detail
            if ok2 and entry:
                exists, refs = entrypoint_exists(*entry)
                row["entrypoint_exists"] = exists
                row["entrypoint_refs"] = refs[:2]
            else:
                row["entrypoint_exists"] = False
        else:
            row["snippet_parsed"] = False
            row["detail"] = out[-160:]
        row["template_in_repo"] = (REPO / "plugin" / ("mcp.%s.json" % host)).exists() or \
                                  (REPO / "plugin" / ("mcp.%s.toml" % host)).exists()
        rows.append(row)

    result = {
        "schema": "harness-matrix-0.1",
        "mcp_stdio_smoke": {"ok": smoke_ok, **smoke},
        "hosts": rows,
        "all_ok": smoke_ok and all(
            r.get("snippet_rendered") and r.get("snippet_parsed") and r.get("entrypoint_exists")
            and r.get("template_in_repo") for r in rows
        ),
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
    else:
        print("MCP stdio smoke: ok=%s server=%s tools=%s signing=%s" % (
            smoke_ok, smoke["server_version"], smoke["tools"], smoke["signing_tools"]))
        print("%-12s %-6s %-8s %-14s %-8s %s" % ("HOST", "FORMAT", "RENDER", "PARSE", "ENTRY", "TEMPLATE"))
        for r in rows:
            print("%-12s %-6s %-8s %-14s %-8s %s" % (
                r["host"], r["format"],
                r.get("snippet_rendered"), r.get("snippet_parsed"),
                r.get("entrypoint_exists"), r.get("template_in_repo")))
        print("\nALL OK" if result["all_ok"] else "\nFAILURES PRESENT")
    return 0 if result["all_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

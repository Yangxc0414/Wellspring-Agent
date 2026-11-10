"""Generate the plugin bundle a host installs, from the runtime that is actually checked out.

Hand-written install fragments drift the moment a tool or path changes — the same failure mode that
made the command catalog invisible to hosts. So every file here is derived: the entrypoints come from
the real server script, the counts from the live registries, and the human-only list from the module
that enforces it. `plugin verify` re-derives and compares, which turns "the plugin README is out of
date" into a failing test.

The bundle carries no build fingerprint on purpose: that value changes with every source edit, so
pinning it here would force a re-export ritual with no safety benefit. A host reads it live from
`handoff contract`.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PLUGIN_SCHEMA = "research-agent-plugin-0.1"
ROOT_PLACEHOLDER = "<RESEARCH_AGENT_ROOT>"
HOSTS = ("qoder", "codex", "zcode", "workbuddy")
BOUNDARY = (
    "the plugin is a transport and a description of entrypoints only: it contains no research logic "
    "and no gate authority; claim signatures, gate decisions, protocol freeze, closure signatures, "
    "publishing and export approval stay CLI operations, run by a human or by a human-authored "
    "autopilot policy that the plugin may invoke but never create or widen"
)


def _server_paths(root_token: str) -> Dict[str, Any]:
    return {
        "command": "python",
        "args": [root_token + "/scripts/research_mcp_server.py", "--root", root_token],
        "env": {"PYTHONPATH": root_token},
    }


def _write(path: Path, text: str) -> None:
    """Python 3.8 has no write_text(newline=...); LF keeps the bundle byte-stable."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def files(root_token: str) -> Dict[str, str]:
    """Every file in the bundle, keyed by relative path."""
    from .host_contract import GATE_VERBS
    from .host_model import DEFAULT_TTL_MINUTES
    from .mcp_server import HUMAN_ONLY, PROMPTS, SERVER_NAME, TOOL_NAMES
    from .workspace import CommandRegistry

    commands = CommandRegistry().snapshot()["count"]
    server = _server_paths(root_token)
    manifest = {
        "schema_version": PLUGIN_SCHEMA,
        "name": SERVER_NAME,
        "root": root_token,
        "entrypoints": {
            "mcp_stdio": server,
            "http_runtime": {"command": "python", "args": ["-m", "research_agent.runtime"]},
            "cli": "python -m research_agent",
            "file_drop": {
                "contract": "python -m research_agent handoff contract --capabilities <claims>",
                "export": "python -m research_agent handoff export --outbox <dir>",
                "import": "python -m research_agent handoff import --outbox <dir>",
            },
        },
        "tools": len(TOOL_NAMES),
        "tool_names": list(TOOL_NAMES),
        "cli_commands": commands,
        "prompts": [prompt["name"] for prompt in PROMPTS],
        "turn_ttl_minutes": DEFAULT_TTL_MINUTES,
        "human_only": list(GATE_VERBS),
        "human_only_statement": HUMAN_ONLY,
        # Two supply modes, decided by where the plugin runs, not by a config flag.
        "model_supply": {
            "host_supplied_no_api_key": {
                "where": "a platform host whose agent has its own model (Qoder and similar)",
                "how": (
                    "generation stages return a pending ModelTurn; the host answers it with "
                    "research_model_respond (or handoff export/import) and re-runs the step"
                ),
                "api_key_required": False,
                "detect": "handoff contract --capabilities can_call_tools,can_serve_model",
            },
            "client_configured_key": {
                "where": "a plain CLI client with no agent to answer turns",
                "how": "bind a keyed profile once, then every stage calls it directly",
                "api_key_required": True,
                "detect": "handoff contract without can_serve_model",
            },
            "if_neither": (
                "the run stops with blocked=model_stages_suspend_without_a_host_model instead of "
                "silently producing a weaker draft"
            ),
        },
        "boundary": BOUNDARY,
    }
    toml = "\n".join(
        [
            "# Codex registers MCP servers in ~/.codex/config.toml",
            "[mcp_servers.research-agent]",
            'command = "python"',
            "args = [%s]" % ", ".join('"%s"' % item for item in server["args"]),
            "",
            "[mcp_servers.research-agent.env]",
            'PYTHONPATH = "%s"' % root_token,
            "",
        ]
    )
    return {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        "mcp.qoder.json": json.dumps(
            {"mcpServers": {"research-agent": dict(server, type="stdio")}},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "mcp.zcode.json": json.dumps(
            {"mcpServers": {"research-agent": dict(server, type="stdio")}},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "mcp.codex.toml": toml,
        "mcp.workbuddy.json": json.dumps(
            {"mcpServers": {"research-agent": dict(server, type="stdio")}},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "SKILL.md": _skill(root_token),
        "README.md": _readme(root_token, len(TOOL_NAMES), commands),
    }


def _skill(root_token: str) -> str:
    return (
        "# research-agent plugin skill\n\n"
        "Drive the runtime over whichever transport this host actually has. Follow these steps in "
        "order and stop where it says to stop.\n\n"
        "1. Negotiate first: `python -m research_agent handoff contract --capabilities "
        "<can_call_tools,can_write_files,can_serve_model>` (or the `research_host_contract` "
        "equivalent over MCP). Read `blocked` and `next_commands` before starting a run.\n"
        "2. Choose a transport. Tools available -> MCP. Files only -> `handoff export`, answer "
        "`outbox/MT-*.answer.json`, `handoff import`, then re-run the deferred step; it replays "
        "recorded answers instead of asking again.\n"
        "3. Run the research task with a project directory inside the user's workspace. Every "
        "artifact stays in that directory.\n"
        "4. Who supplies the model. On a platform host like Qoder, you do: answer each pending "
        "turn with your own model, and no API key is needed anywhere. On a plain CLI client "
        "with no agent to answer, bind a keyed profile once instead. An answer is capability "
        "output: it still passes shape validation, citation whitelists and result-number "
        "limits.\n"
        "5. Stop at the gate. Claim signature, G1/G2 decisions, protocol freeze, closure signature, "
        "publishing and export approval are not offered to any transport. Show the CLI command and "
        "let the human run it. For a specific run the exact command is "
        "`research_status` -> `closure_profiles.canonical_run[].claim_draft.command` "
        "(project-relative, already carrying the proposed `--assertion`); it disappears once the "
        "run is signed.\n"
        "6. Only if the human already wrote an autopilot policy, you may run "
        "`python -m research_agent autopilot research --project <dir> --topic <topic> --policy "
        "<policy.json>` to go from a topic to a sealed bundle, or `autopilot run --project <dir> "
        "--run-id <RUN-ID> --policy <policy.json>` to finish an existing run. It can never create "
        "or widen a policy, and it refuses out-of-scope runs. Never write a policy on the human's "
        "behalf.\n\n"
        "The runtime root for this bundle is `%s`. Verify the bundle after any change with "
        "`python -m research_agent plugin verify`.\n" % root_token
    )


def _readme(root_token: str, tools: int, commands: int) -> str:
    return (
        "# research-agent plugin bundle\n\n"
        "Generated by `python -m research_agent plugin export`; do not edit by hand.\n\n"
        "This bundle lets an agent host drive the research runtime. It is a transport plus a "
        "description of entrypoints: %d MCP tools, %d CLI commands, and one file-drop path for "
        "hosts that cannot call tools.\n\n"
        "## Install per host\n\n"
        "- **Qoder**: merge `mcp.qoder.json` into the app's MCP server settings, then reload the "
        "connector.\n"
        "- **Codex**: append `mcp.codex.toml` to `~/.codex/config.toml`.\n"
        "- **Zcode / WorkBuddy / other MCP clients**: use `mcp.zcode.json` / `mcp.workbuddy.json`.\n"
        "- **No tool calling at all**: keep the CLI on disk and exchange files through "
        "`handoff export|import`.\n\n"
        "Replace `%s` with the checkout root, or regenerate with "
        "`plugin export --root <path>`.\n\n"
        "## Model supply: no API key on a platform host\n\n"
        "On Qoder and similar platform hosts the agent you are talking to **is** the model: it "
        "answers pending turns, and no API key is configured anywhere. On a plain CLI client with "
        "no agent to answer turns, bind a keyed profile once instead "
        "(`python -m research_agent host-model bind ...`). If neither holds, the run stops with "
        "`blocked=model_stages_suspend_without_a_host_model` rather than drafting something weaker. "
        "`manifest.json` records both modes under `model_supply`.\n\n"
        "## First thing to run\n\n"
        "    python -m research_agent handoff contract --capabilities can_call_tools,can_write_files\n\n"
        "It reports which transports are live, which stages will suspend waiting for the host model, "
        "and what stays human-only.\n\n"
        "## What this bundle cannot do\n\n"
        "%s\n" % (tools, commands, root_token, BOUNDARY)
    )


def export(output: Path, root: Optional[str] = None) -> Dict[str, Any]:
    target = Path(output)
    token = str(root).rstrip("/\\") if root else ROOT_PLACEHOLDER
    written: List[str] = []
    payload = files(token)
    target.mkdir(parents=True, exist_ok=True)
    for name, text in sorted(payload.items()):
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        _write(path, text)
        written.append(name)
    return {
        "schema_version": PLUGIN_SCHEMA,
        "output_dir": str(target),
        "root": token,
        "files": written,
        "next": "reload the host connector, then run `handoff contract` from the host",
        "boundary": BOUNDARY,
    }


def verify(output: Path, root: Optional[str] = None) -> Dict[str, Any]:
    """Re-derive the bundle and compare it against what is committed on disk."""
    target = Path(output)
    token = str(root).rstrip("/\\") if root else ROOT_PLACEHOLDER
    expected = files(token)
    missing: List[str] = []
    stale: List[str] = []
    for name, text in sorted(expected.items()):
        path = target / name
        if not path.is_file():
            missing.append(name)
        elif path.read_text(encoding="utf-8") != text:
            stale.append(name)
    extra = sorted(
        str(path.relative_to(target))
        for path in target.rglob("*")
        if path.is_file() and str(path.relative_to(target)) not in expected
    ) if target.is_dir() else []
    return {
        "schema_version": PLUGIN_SCHEMA,
        "output_dir": str(target),
        "in_sync": not missing and not stale and not extra,
        "missing": missing,
        "stale": stale,
        "unexpected": extra,
        "next": "run `python -m research_agent plugin export` to regenerate"
        if (missing or stale or extra)
        else "",
        "boundary": BOUNDARY,
    }

"""Which faces actually serve each capability, checked against live enumerations.

The project has long claimed that the CLI, MCP and HTTP faces answer the same request the same way,
but nothing recorded *which* face serves *which* capability: audits had to match names by eye, and
name matching conflates a rename with an absence (measured: pairing by name pairs only 24 of 45 MCP
tools, and a regex scan finds 52 HTTP routes where the app itself exposes 59). This module states the
mapping explicitly and verifies every declared target against the live CLI tree and the live route
list, so a typo or an invented command fails rather than quietly reporting a face as missing.

Anything not yet audited is reported as ``unaudited``. That is deliberate: an honest matrix with
visible holes beats a complete-looking one built from guesses, and the hole count is part of the
output so it cannot be read as coverage.
"""

import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

MATRIX_SCHEMA = "face-matrix-0.2"

# capability -> the exact CLI command path and/or HTTP route that serves it.
# Absence needs a reason; a wrong target is caught by the guard test, not trusted.
DECLARATIONS: Dict[str, Dict[str, str]] = {
    "research_project_init": {"cli": "project init"},
    "research_conference_fetch": {"cli": "conference fetch"},
    "research_literature_fetch": {"cli": "literature fetch"},
    "research_literature_synthesis": {"cli": "literature synthesize"},
    "research_innovation_review": {"cli": "innovation review"},
    "research_figure_render": {"cli": "figure render"},
    "research_figure_templates": {"cli": "figure templates"},
    "research_grant_template": {"cli": "grant template"},
    "research_venue_audit": {"cli": "venue audit"},
    "research_skill_packs": {"cli": "skill coverage"},
    "research_skill_list": {"cli": "skill list"},
    "research_skill_invoke": {"cli": "skill invoke"},
    "research_skill_distill": {"cli": "skill distill"},
    "research_writing_pack": {"cli": "writing pack"},
    "research_manuscript_audit": {"cli": "writing audit"},
    "research_manuscript_bind": {"cli": "writing bind"},
    "research_manuscript_draft": {"cli": "manuscript draft"},
    "research_manuscript_review": {"cli": "manuscript review"},
    "research_manuscript_ab_review": {"cli": "revision ab-review"},
    "research_number_provenance": {"cli": "manuscript provenance"},
    "research_experiment_status": {"cli": "experiment status"},
    "research_experiment_codegen": {"cli": "experiment scaffold"},
    "research_empirical_status": {"cli": "empirical check"},
    "research_mandate_status": {"cli": "mandate status"},
    "research_model_turns": {"cli": "host-model turns", "http": "/api/host-model/turns"},
    "research_model_respond": {"cli": "host-model respond", "http": "/api/host-model/respond"},
    "research_model_void": {"cli": "host-model void", "http": "/api/host-model/void"},
    "research_model_profiles": {"http": "/api/models/profiles"},
    "research_host_contract": {"cli": "handoff contract", "http": "/api/research/capabilities"},
    "research_read_artifact": {"http": "/api/runs/{job_id}/artifacts/{artifact_path:path}"},
    "research_list_artifacts": {"http": "/api/runs/{job_id}/artifacts"},
    "research_status": {"http": "/api/runs/{job_id}"},
    "research_closure_status": {"cli": "loop status"},
    "research_evolution_status": {"cli": "rsi story", "http": "/api/rsi/story"},
    "research_lineage_status": {"cli": "lineage build"},
    "research_bootstrap": {"cli": "workspace export"},
    "research_next_actions": {"cli": "action automation-plan"},
    "research_plan": {"cli": "orchestrate plan"},
    # Traced through the handler, not the name. ``research_run`` builds a TaskRequest and runs the
    # task agent, which is CLI ``task run``; CLI ``research run`` is the ResearchRunner batch and
    # serves nothing here. Pairing by name would have declared the wrong target and passed.
    "research_run": {"cli": "task run"},
    "research_manuscript_revise": {"cli": "revision run"},
    "research_study_baseline": {"cli": "study baseline"},
    "research_support_panel": {"cli": "writing support-panel"},
}

# Capabilities that must never appear outside the CLI: a human gate is not transportable.
HUMAN_ONLY_MCP_ABSENT = (
    "approve",
    "claim",
    "sign",
    "freeze",
    "publish",
    "export approval",
    "ingest",
)

# A surface the MCP face does not reach is only excused when the reason is written down here.
# Silence is not a reason: the matrix is keyed by MCP tool name, so it cannot see a CLI command or
# an HTTP route that no tool points at, and an unrecorded absence reads as "nothing is missing".
REVERSE_REASONS: Dict[str, str] = {
    "cli:study brief": "not_exposed_yet: the signing brief is a human read; a host that sees it may "
    "also want to answer it, so it stays CLI-only until someone decides the read-only half is safe",
    "cli:experiment preflight": "not_exposed_yet: /api/research/preflight already answers the same "
    "question over HTTP, so the gap is MCP-specific and the blocker commands must be checked before "
    "an agent face is handed a list of commands to run",
    "cli:workspace preflight": "not_exposed_yet: same reason as experiment preflight",
}

GATE_TOKENS = ("approve", "claim", "sign", "freeze", "publish", "ingest", "confirm", "execute")

BOUNDARY_TAIL = (
    "; it is not a claim that the faces behave identically, only that they are reachable here, and "
    "unaudited capabilities are counted and reported rather than assumed absent or present. Human "
    "gates stay CLI-only by design, and no face here can sign, approve, freeze, publish or export"
)

# The verification clause has to match the enumeration that actually ran: a caller that skips the
# app import must not receive a boundary asserting a checked route list, or an unverified HTTP
# column reads as verified.
MATRIX_BOUNDARY = (
    "this matrix records which face serves which capability and was verified against the live "
    "argparse command tree and the live FastAPI route list, so every declared target exists"
    + BOUNDARY_TAIL
)
MATRIX_BOUNDARY_HTTP_UNVERIFIED = (
    "this matrix records which face serves which capability. CLI targets were verified against the "
    "live argparse command tree; HTTP targets were NOT verified because the route list was not "
    "enumerated for this call, so the http column is a declaration awaiting a check" + BOUNDARY_TAIL
)


def matrix_boundary(http_targets_verified: bool) -> str:
    return MATRIX_BOUNDARY if http_targets_verified else MATRIX_BOUNDARY_HTTP_UNVERIFIED


UNREACHED_LIST_CAP = 40


def _classify(surface: str, kind: str) -> Optional[Dict[str, str]]:
    """Return the reason a face does not reach this surface, or None when nobody wrote one down."""
    key = "%s:%s" % (kind, surface)
    if key in REVERSE_REASONS:
        return {"class": "reasoned", "reason": REVERSE_REASONS[key]}
    tokens = [t for t in str(surface).replace("/", " ").split() if t != "api"]
    if any(token in tokens for token in GATE_TOKENS):
        return {"class": "human_gate_by_design", "reason": "a gate verb is not transportable to a tool face"}
    return None


def reverse_coverage(
    entries: List[Dict[str, Any]],
    commands: List[str],
    routes: List[str],
    http_scanned: bool = True,
) -> Dict[str, Any]:
    """The direction the MCP-keyed matrix cannot see: surfaces that no capability points at."""
    reached = {
        "cli": {str(entry.get("cli") or "") for entry in entries if entry.get("cli")},
        "http": {str(entry.get("http") or "") for entry in entries if entry.get("http")},
    }
    rows: List[Dict[str, Any]] = []
    counts: Dict[str, int] = {"human_gate_by_design": 0, "reasoned": 0, "unexplained": 0}
    # only surfaces no capability reaches are classified: counting a reached route as "unexplained"
    # inflates the hole list with the very rows the forward matrix already proves reachable
    for kind, surfaces in (("cli", sorted(set(commands))), ("http", sorted(set(routes)))):
        for surface in surfaces:
            if not surface or surface in reached[kind]:
                continue
            found = _classify(surface, kind)
            label = "unexplained" if found is None else found["class"]
            counts[label] += 1
            rows.append(
                {
                    "surface": surface,
                    "face": kind,
                    "class": label,
                    "reason": "" if found is None else found["reason"],
                }
            )
    unexplained = [row for row in rows if row["class"] == "unexplained"]
    # the family counts are taken over every unexplained row: the capped list below is an
    # alphabetical prefix, so grouping it produced a distribution skewed to whatever sorts first
    # (measured: closure/agent/autopilot from the first 40 against rsi/skill over all 241)
    families: Dict[str, int] = {}
    for row in unexplained:
        head = str(row["surface"]).split()[0] if row["face"] == "cli" else "http-route"
        families[head] = families.get(head, 0) + 1
    ranked = sorted(families.items(), key=lambda kv: (-kv[1], kv[0]))
    scan_note = (
        ""
        if http_scanned
        else "; the HTTP route list was not enumerated for this call, so http rows are absent "
        "because nothing was scanned and not because nothing is missing"
    )
    return {
        "schema_version": "face-reverse-0.1",
        "surfaces": len(rows),
        "http_scanned": bool(http_scanned),
        "summary": counts,
        "unlisted": max(0, len(unexplained) - UNREACHED_LIST_CAP),
        "truncated": len(unexplained) > UNREACHED_LIST_CAP,
        "unexplained_families": dict(ranked[:12]),
        "unexplained_families_scanned": len(unexplained),
        "unexplained_examples": [
            {"surface": row["surface"], "face": row["face"]} for row in unexplained[:UNREACHED_LIST_CAP]
        ],
        "examples_order": (
            "alphabetical prefix of the unexplained rows, not a random or stratified sample: "
            "derive no distribution from it, use unexplained_families which counts every row"
        ),
        "boundary": (
            "this is the reverse of the face matrix: it lists CLI commands and HTTP routes that no "
            "MCP capability declares, and it only excuses an absence that carries a written reason. "
            "%d of %d unreached surface(s) have no reason recorded, and a count of zero here is the "
            "goal, not a claim that the MCP face should serve everything: many of these are "
            "plumbing, human gates, or deliberately CLI-only. The list is capped at %d rows and "
            "truncation is reported rather than hidden%s"
            % (counts["unexplained"], len(rows), UNREACHED_LIST_CAP, scan_note)
        ),
    }


def cli_command_paths() -> List[str]:
    """Every executable command path the CLI parser accepts, walked rather than grepped.

    Only leaves count: a parser that still owns subparsers is a namespace, not a command, and
    including the 42 group paths inflated the unreached-surface count with things no face can serve.
    """
    from .cli import build_parser

    paths: List[str] = []

    def has_subcommands(parser: Any) -> bool:
        for action in getattr(parser, "_actions", []):
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict) and any(
                hasattr(sub, "_actions") for sub in choices.values()
            ):
                return True
        return False

    def walk(parser: Any, prefix: List[str]) -> None:
        for action in getattr(parser, "_actions", []):
            choices = getattr(action, "choices", None)
            if not isinstance(choices, dict):
                continue
            for name, sub in sorted(choices.items()):
                if not hasattr(sub, "_actions"):
                    continue
                path = prefix + [name]
                if not has_subcommands(sub):
                    paths.append(" ".join(path))
                walk(sub, path)

    walk(build_parser(), [])
    return sorted(set(paths))


def http_route_paths() -> List[str]:
    """Every route the runtime app actually registers, or [] when the app cannot be imported."""
    try:
        from .runtime.app import create_app

        app = create_app()
    except Exception:
        return []
    return sorted({str(getattr(route, "path", "")) for route in app.routes if getattr(route, "path", "")})


def face_matrix(tool_names: Optional[List[str]] = None, include_http: bool = True) -> Dict[str, Any]:
    """Build the matrix and fail loudly on a declared target that does not exist."""
    from .mcp_server import TOOL_NAMES

    tools = sorted(tool_names or TOOL_NAMES)
    commands = set(cli_command_paths())
    # importing the runtime app to list routes is not free and some callers only need the mapping,
    # so those must say so rather than receive an unverified HTTP column that looks checked
    routes = set(http_route_paths()) if include_http else set()
    entries: List[Dict[str, Any]] = []
    problems: List[str] = []
    unaudited: List[str] = []
    for tool in tools:
        declared = dict(DECLARATIONS.get(tool) or {})
        cli = str(declared.get("cli") or "")
        http = str(declared.get("http") or "")
        if cli and cli not in commands:
            problems.append("declared CLI command does not exist: %s -> %s" % (tool, cli))
        if http and include_http and not routes:
            problems.append("HTTP routes could not be enumerated; %s is unverified" % tool)
        if http and routes and http not in routes:
            problems.append("declared HTTP route does not exist: %s -> %s" % (tool, http))
        status = "declared" if (cli or http) else "unaudited"
        if status == "unaudited":
            unaudited.append(tool)
        entries.append(
            {
                "capability": tool,
                "mcp": True,
                "cli": cli,
                "http": http,
                "status": status,
            }
        )
    return {
        "schema_version": MATRIX_SCHEMA,
        "faces": {
            "cli_commands": len(commands),
            "mcp_tools": len(tools),
            "http_routes": len(routes),
            "http_routes_enumerable": bool(routes),
            "http_targets_verified": bool(routes),
        },
        "entries": entries,
        "summary": {
            "declared": len(entries) - len(unaudited),
            "unaudited": len(unaudited),
            "mcp_absent_by_design": list(HUMAN_ONLY_MCP_ABSENT),
        },
        "unaudited_capabilities": unaudited,
        "declaration_problems": problems,
        "reverse": reverse_coverage(entries, sorted(commands), sorted(routes), bool(routes)),
        "boundary": matrix_boundary(bool(routes)),
    }

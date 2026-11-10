"""Host-facing CLI families: the plugin bundle and the file-drop / negotiation transport.

These two families are the surface a host agent touches first, so they live away from the
five-thousand-line main CLI. Moving them also keeps the import graph one-way: this module never
imports ``cli``, and ``cli`` borrows only ``print_json`` and ``add_host_parsers`` from here.
"""

import argparse
import json
from pathlib import Path
from typing import List


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def cmd_plugin(args: argparse.Namespace) -> int:
    """Generate or check the host plugin bundle; it is derived, never hand-written."""
    from .plugin_bundle import export, verify

    output = Path(args.output_dir)
    root = getattr(args, "root", "") or None
    if args.plugin_command == "export":
        print_json(export(output, root=root))
        return 0
    report = verify(output, root=root)
    print_json(report)
    return 0 if report["in_sync"] else 1


def cmd_handoff(args: argparse.Namespace) -> int:
    """File-drop transport for host turns: no MCP, no long-lived process, files only."""
    from .handoff import export_pending, handoff_status, import_answers
    from .host_contract import host_contract
    from .host_model import ModelTurnLedger

    if args.handoff_command == "contract":
        capabilities: List[str] = [
            item.strip()
            for item in str(args.capabilities or "").split(",")
            if item.strip()
        ]
        print_json(
            host_contract(
                declared=capabilities,
                outbox=Path(args.outbox) if args.outbox else None,
            )
        )
        return 0
    ledger = ModelTurnLedger(Path(args.ledger) if args.ledger else None)
    outbox = Path(args.outbox)
    if args.handoff_command == "export":
        print_json(export_pending(ledger, outbox))
    elif args.handoff_command == "import":
        print_json(
            import_answers(
                ledger,
                outbox,
                host_label=args.host_label,
                project_root=Path(args.project) if args.project else None,
            )
        )
    else:
        print_json(handoff_status(ledger, outbox))
    return 0


def add_host_parsers(sub: argparse._SubParsersAction) -> None:
    """Register the plugin and handoff families on the top-level subparsers."""
    plugin_parser = sub.add_parser(
        "plugin",
        help="generate/verify the host plugin bundle (Qoder, Codex, Zcode, or files only)",
    )
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_command", required=True)
    for name, help_text in (
        ("export", "write the bundle from the live registries"),
        ("verify", "re-derive and compare against the committed bundle"),
    ):
        plugin_sub_parser = plugin_sub.add_parser(name, help=help_text)
        plugin_sub_parser.add_argument(
            "--output-dir", default="plugin", help="bundle directory"
        )
        plugin_sub_parser.add_argument(
            "--root", default="", help="materialize this runtime root instead of a placeholder"
        )
        plugin_sub_parser.set_defaults(func=cmd_plugin)

    handoff_parser = sub.add_parser(
        "handoff",
        help="file-drop transport for host-model turns (no MCP, no long-lived server)",
    )
    handoff_sub = handoff_parser.add_subparsers(dest="handoff_command", required=True)
    for name, help_text in (
        ("export", "write pending turns into inbox/ for an external agent"),
        ("import", "record answer files from outbox/ through the turn ledger"),
        ("status", "read-only: what is exported, answered or still awaiting an answer"),
        (
            "contract",
            "read-only host negotiation: what this host can do, what will suspend, what stays human",
        ),
    ):
        sub_parser = handoff_sub.add_parser(name, help=help_text)
        sub_parser.add_argument(
            "--outbox",
            required=name in ("export", "import"),
            help="handoff directory",
        )
        if name == "contract":
            sub_parser.add_argument(
                "--capabilities",
                default="",
                help="comma-separated host claims: can_call_tools,can_write_files,"
                "can_serve_model,long_sessions",
            )
        sub_parser.add_argument(
            "--ledger", default="", help="turn ledger path (default: env/store)"
        )
        if name == "import":
            sub_parser.add_argument(
                "--host-label", default="file-drop", help="who supplied the answers"
            )
            sub_parser.add_argument("--project", default="", help="project root for sink writes")
        sub_parser.set_defaults(func=cmd_handoff)
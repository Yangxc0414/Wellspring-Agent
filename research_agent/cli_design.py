"""CLI for the CCF-A study-design audit.

One direction of imports: cli.py imports this module, never the other way around.
"""

import argparse
import json
from pathlib import Path

from .ccfa_audit import audit_file, study_design_template
from .design_draft import DesignDraftError, request_study_design
from .storage import write_json_atomic


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _cmd_design_audit(args: argparse.Namespace) -> int:
    try:
        result = audit_file(Path(args.design), venue=args.venue)
    except ValueError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    if args.strict and result["status"] != "ready_for_g2":
        return 2
    return 0


def _cmd_design_draft(args: argparse.Namespace) -> int:
    try:
        result = request_study_design(
            Path(args.project),
            args.run_id,
            ledger_path=Path(args.ledger) if args.ledger else None,
            profile_id=args.profile,
            force=args.force,
        )
    except DesignDraftError as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    if result.get("status") == "pending":
        return 3
    if args.strict and result.get("status") != "ready_for_g2":
        return 2
    return 0


def _cmd_design_template(args: argparse.Namespace) -> int:
    path = Path(args.output)
    if path.exists():
        raise SystemExit("template already exists; refusing to overwrite: %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, study_design_template())
    _print_json(
        {
            "path": str(path),
            "schema_version": study_design_template()["schema_version"],
            "note": "fill every TODO; the audit is a disclosure checklist, not a venue decision",
        }
    )
    return 0


def add_design_parsers(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "design",
        help="CCF-A study-design disclosure audit (separate from the local run design)",
    )
    commands = parser.add_subparsers(dest="design_command", required=True)

    audit = commands.add_parser("audit", help="check a study-design.json against the venue skills")
    audit.add_argument("--design", required=True)
    audit.add_argument("--venue", default="neurips")
    audit.add_argument("--strict", action="store_true", help="exit 2 unless ready_for_g2")
    audit.set_defaults(func=_cmd_design_audit)

    draft = commands.add_parser(
        "draft", help="ask the bound host model for a study design, then audit it"
    )
    draft.add_argument("--project", required=True)
    draft.add_argument("--run-id", required=True)
    draft.add_argument("--ledger", default="")
    draft.add_argument("--profile", default="host-agent")
    draft.add_argument("--force", action="store_true")
    draft.add_argument("--strict", action="store_true", help="exit 2 unless ready_for_g2")
    draft.set_defaults(func=_cmd_design_draft)

    template = commands.add_parser("template", help="write a study-design skeleton")
    template.add_argument("--output", required=True)
    template.set_defaults(func=_cmd_design_template)

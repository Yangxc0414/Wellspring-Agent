"""CLI surface for the policy-bounded autopilot.

Kept out of cli.py for the same reason cli_host.py was split out: the command tree is
already large, and this surface has one direction of imports (cli imports this, never the
other way around).
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from .autopilot import (
    AutopilotError,
    autopilot_status,
    build_policy,
    load_policy,
    run_autopilot,
    run_autopilot_research,
)
from .paths import DEFAULT_SIGNER_STORE_PATH, REPO_ROOT
from .signers import SignerError, SignerStore
from .storage import write_json_atomic


def _print_json(value: Dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _cmd_policy_init(args: argparse.Namespace) -> int:
    try:
        signers = SignerStore(Path(args.signers_path))
        signer = signers.get(args.signer)
    except SignerError as exc:
        raise SystemExit(str(exc))
    project = Path(args.project)
    if not project.is_dir():
        raise SystemExit("project directory does not exist: %s" % project)
    policy = build_policy(
        scope=args.scope,
        authorized_by=args.authorized_by,
        signer_id=args.signer,
        datasets=args.dataset or None,
        min_seeds=args.min_seeds,
        max_runs=args.max_runs,
        expires_hours=args.expires_hours,
        endpoint=args.endpoint,
        limitation=args.limitation,
        bibliography_source=args.bibliography_source,
        allow_revise_idea=args.allow_revise_idea,
        note=args.note,
    )
    path = Path(args.output) if args.output else project / "autopilot" / "policy.json"
    # Policies are immutable: overwriting one would let a later, wider authorization replace the
    # original without a trace. A human can write a new file with --output instead.
    if path.exists():
        raise SystemExit("policy already exists; write a new file with --output: %s" % path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(path, policy)
    _print_json(
        {
            "policy": policy,
            "path": str(path),
            "signer": {"signer_id": signer.get("signer_id"), "name": signer.get("name")},
            "note": (
                "this file is the human authorization; autopilot never creates or widens one; "
                "the signer id is the delegated identity, not the authorizer"
            ),
        }
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        policy = load_policy(Path(args.policy))
        result = run_autopilot(
            Path(args.project),
            args.run_id,
            Path(args.policy),
            Path(args.signers_path) if args.signers_path else None,
            REPO_ROOT,
        )
    except (AutopilotError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0 if result.get("status") == "completed" else 2


def _cmd_research(args: argparse.Namespace) -> int:
    try:
        result = run_autopilot_research(
            Path(args.project),
            args.topic,
            Path(args.policy),
            language=args.language,
            venue=args.venue,
            max_sources=args.max_sources,
            run_id=args.run_id,
            corpus_dir=Path(args.corpus_dir) if args.corpus_dir else None,
            study_design_file=Path(args.study_design_file) if args.study_design_file else None,
            signers_path=Path(args.signers_path) if args.signers_path else None,
            repo_root=REPO_ROOT,
        )
    except (AutopilotError, OSError, ValueError) as exc:
        raise SystemExit(str(exc))
    _print_json(result)
    return 0 if result.get("status") == "completed" else 2


def _cmd_status(args: argparse.Namespace) -> int:
    _print_json(autopilot_status(Path(args.project)))
    return 0


def add_autopilot_parsers(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "autopilot",
        help="policy-bounded delegated gates: G1/G2/S5b/G5, publish and lineage",
    )
    commands = parser.add_subparsers(dest="autopilot_command", required=True)

    policy = commands.add_parser("policy", help="inspect or create the human authorization")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    init = policy_sub.add_parser("init", help="write a policy file (human action; never automatic)")
    init.add_argument("--project", required=True)
    init.add_argument("--scope", required=True)
    init.add_argument("--authorized-by", required=True)
    init.add_argument("--signer", required=True, help="local signer id used for the delegated signature")
    init.add_argument("--dataset", action="append", default=[], help="allowed dataset substring; repeatable")
    init.add_argument("--min-seeds", type=int, default=3)
    init.add_argument("--max-runs", type=int, default=1)
    init.add_argument("--expires-hours", type=int, default=24)
    init.add_argument("--endpoint", choices=["bundle", "lineage"], default="bundle")
    init.add_argument("--limitation", default="")
    init.add_argument("--bibliography-source", default="")
    init.add_argument("--allow-revise-idea", action="store_true")
    init.add_argument("--note", default="")
    init.add_argument("--output", default="")
    init.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    init.set_defaults(func=_cmd_policy_init)

    research = commands.add_parser(
        "research", help="one command from topic to sealed bundle, inside one policy"
    )
    research.add_argument("--project", required=True)
    research.add_argument("--topic", required=True)
    research.add_argument("--policy", required=True)
    research.add_argument("--language", choices=["zh", "en"], default="en")
    research.add_argument("--venue", default="en_conference")
    research.add_argument("--max-sources", type=int, default=4)
    research.add_argument("--run-id", default="")
    research.add_argument("--corpus-dir", default="", help="local PDF/TXT/MD corpus instead of fixtures")
    research.add_argument("--study-design-file", default="", help="pre-registered study-design.json")
    research.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    research.set_defaults(func=_cmd_research)

    run = commands.add_parser("run", help="execute the delegated tail of one completed run")
    run.add_argument("--project", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--policy", required=True)
    run.add_argument("--signers-path", default=str(DEFAULT_SIGNER_STORE_PATH))
    run.set_defaults(func=_cmd_run)

    status = commands.add_parser("status", help="read the autopilot ledger and latest report")
    status.add_argument("--project", required=True)
    status.set_defaults(func=_cmd_status)

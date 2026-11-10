"""Run the localhost research runtime: python -m research_agent.runtime."""

import argparse
from pathlib import Path

import uvicorn

from .app import create_app, remote_bind_problem
from .jobs import RuntimeSettings, default_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Research Agent local runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--jobs-root", default="")
    parser.add_argument("--rsi-root", action="append", default=[])
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    settings: RuntimeSettings = default_settings()
    refusal = remote_bind_problem(args.host, args.allow_remote, settings.research_api_token)
    if refusal:
        parser.error(refusal)
    if args.jobs_root:
        settings.jobs_root = Path(args.jobs_root)
        settings.workspace_memory_path = settings.jobs_root.parent / "workspace_memory.json"
        settings.workspace_archive_root = settings.jobs_root.parent / "workspace_archive"
        settings.literature_memory_path = settings.jobs_root.parent / "literature_memory.json"
        settings.custom_agents_path = settings.jobs_root.parent / "custom_agents.json"
        settings.evolution_policy_path = settings.jobs_root.parent / "evolution_policy.json"
        settings.skill_registry_path = settings.jobs_root.parent / "skills.json"
    if args.rsi_root:
        settings.allowed_rsi_roots = [Path(item) for item in args.rsi_root]

    uvicorn.run(
        create_app(settings),
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()

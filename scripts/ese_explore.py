"""Agent-driven ESE exploration driver: S1-S4 pipeline, then protocol, execution, note."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.ese_explore import EseExploreError, run_exploration  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="run an agent-driven ESE exploration")
    parser.add_argument("--question", required=True)
    parser.add_argument("--corpus-dir", default="")
    parser.add_argument("--repos", required=True, help="comma-separated local repository paths")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--pipeline-dir", default="", help="reuse an existing pipeline run dir")
    parser.add_argument("--profile", default="deepseek-v41")
    parser.add_argument("--max-sources", type=int, default=8)
    parser.add_argument("--study-id", default="")
    args = parser.parse_args(argv)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    repos = [item.strip() for item in args.repos.split(",") if item.strip()]
    for repo in repos:
        if not Path(repo).is_dir():
            print("missing repository: " + repo)
            return 2
    pipeline_dir = Path(args.pipeline_dir) if args.pipeline_dir else out / "pipeline"

    if not args.pipeline_dir:
        command = [
            sys.executable, "-m", "research_agent", "pipeline", "run",
            "--topic", args.question,
            "--language", "en",
            "--venue", "en_conference",
            "--max-sources", str(args.max_sources),
            "--idea-model", args.profile,
            "--experiment-model", args.profile,
            "--writer", "off",
            "--ese-method", "repository-mining",
            "--output-dir", str(pipeline_dir),
        ]
        if args.corpus_dir:
            command.extend(["--corpus-dir", args.corpus_dir])
        print("step 1/3: pipeline S1-S4 on SE corpus ...")
        completed = subprocess.run(command, cwd=str(ROOT))
        if completed.returncode != 0:
            print("pipeline failed with exit " + str(completed.returncode))
            return completed.returncode

    print("step 2/3: draft protocol and execute repository mining ...")
    try:
        study_id = args.study_id or ("ESE-EX-" + out.name.replace("ese-explore-", ""))
        summary = run_exploration(args.question, pipeline_dir, repos, out, study_id)
    except EseExploreError as exc:
        print(str(exc))
        return 2
    print("step 3/3: note written")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

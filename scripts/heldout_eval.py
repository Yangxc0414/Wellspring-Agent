"""Evaluate one pipeline run against the frozen held-out rubric (read-only).

Usage:
    python scripts/heldout_eval.py --run-dir runtime_data/model-eval-deepseek8
    python scripts/heldout_eval.py --run-dir P --task-id HO-20261118-A --out report.md
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from research_agent.heldout_eval import (  # noqa: E402
    HeldoutEvalError,
    evaluate_run,
    render_markdown,
)

DEFAULT_TASKS = os.path.join(ROOT, "research_agent", "eval", "heldout_tasks.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description="held-out rubric evaluation (read-only)")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--task-file", default=DEFAULT_TASKS)
    parser.add_argument("--task-id", default="")
    parser.add_argument("--out", default="", help="optional markdown report path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = evaluate_run(args.run_dir, args.task_file, args.task_id)
    except HeldoutEvalError as exc:
        print(str(exc))
        return 2
    if args.out:
        out = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_markdown(report))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())

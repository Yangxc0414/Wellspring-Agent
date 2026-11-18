"""Run a frozen repository-mining ESE protocol on local clones (read-only)."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.ese_exec import EseExecError, emit_run_artifacts, run_study  # noqa: E402

DEFAULT_PROTOCOL = ROOT / "research_agent" / "eval" / "ese_protocols" / "msr-cochange.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description="execute a repository-mining ESE study")
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    parser.add_argument("--corpus-dir", default="runtime_data/msr-corpus")
    parser.add_argument("--out", default="runtime_data/ese-ms-20261118-01")
    parser.add_argument(
        "--emit-run-artifacts",
        action="store_true",
        help="also write run-capsule/ea/metrics/run-contract for the human S5b step",
    )
    args = parser.parse_args(argv)

    protocol_path = Path(args.protocol)
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    corpus = Path(args.corpus_dir)
    repo_paths = {}
    for entry in protocol["sampling_frame"]["repos"]:
        name = entry["name"] if isinstance(entry, dict) else str(entry)
        candidate = corpus / name
        if not candidate.is_dir():
            print("missing clone: %s (expected %s)" % (name, candidate))
            return 2
        repo_paths[name] = candidate
    try:
        result = run_study(protocol_path, repo_paths, args.out)
    except EseExecError as exc:
        print(str(exc))
        return 2
    print("study: %s | repos: %d | commits: %d" % (
        result["study_id"], len(result["repos"]), result["pooled"]["commits"]))
    print("pooled test co-change: %d/%d = %.3f, 95%% CI [%.3f, %.3f]" % (
        result["pooled"]["test_cochange"], result["pooled"]["commits"],
        result["pooled"]["rate"], result["pooled"]["ci"][0], result["pooled"]["ci"][1]))
    print("bugfix vs other: %+.3f (p=%.4f, n_perm=%d)" % (
        result["pooled"]["difference"],
        result["pooled"]["permutation"]["p_value_two_sided"],
        result["pooled"]["permutation"]["n"]))
    if args.emit_run_artifacts:
        artifacts = emit_run_artifacts(protocol_path, result, args.out)
        check = artifacts["check"]
        print("run artifacts: {0} (blockers={1}, warnings={2})".format(
            artifacts["run_dir"], len(check.get("blockers") or []), len(check.get("warnings") or [])))
        for blocker in check.get("blockers") or []:
            print("  blocker: " + blocker)
        for warning in check.get("warnings") or []:
            print("  warning: " + warning)
    print("wrote: " + str(Path(args.out) / "result.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

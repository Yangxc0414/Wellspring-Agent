"""Summarise a paired ablation over held-out rubric scores (read-only).

Usage:
    python scripts/ablation_summary.py \
        --task-id HO-20261118-B \
        --arm baseline=runtime_data/ho-b-base-1,runtime_data/ho-b-base-2,runtime_data/ho-b-base-3 \
        --arm r1=runtime_data/ho-b-r1-1,runtime_data/ho-b-r1-2,runtime_data/ho-b-r1-3

The summary reports per-run totals, per-arm means and the paired difference between the
first two arms. With n < 4 it says underpowered and does not call a direction.
"""

import argparse
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from research_agent.heldout_eval import evaluate_run, HeldoutEvalError  # noqa: E402

TASKS = os.path.join(ROOT, "research_agent", "eval", "heldout_tasks.json")
MIN_PAIRS = 4
# Two-sided 95% t critical values for small df; beyond the table we use 1.96 (large-n approx).
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}


def paired_interval(differences):
    """Mean paired difference with a 95% t interval and an exact two-sided sign test."""
    values = [float(item) for item in differences]
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "ci_low": None, "ci_high": None, "sign_test_two_sided_p": None}
    mean = sum(values) / float(n)
    if n == 1:
        return {"mean": round(mean, 3), "ci_low": None, "ci_high": None, "sign_test_two_sided_p": 1.0}
    variance = sum((value - mean) ** 2 for value in values) / float(n - 1)
    std = variance ** 0.5
    se = std / (n ** 0.5)
    critical = T95.get(n - 1, 1.96)
    positives = sum(1 for value in values if value > 0)
    negatives = sum(1 for value in values if value < 0)
    tail = min(positives, negatives)
    sign_p = min(1.0, 2.0 * sum(math.comb(n, k) for k in range(0, tail + 1)) / (2.0 ** n))
    return {
        "mean": round(mean, 3),
        "ci_low": round(mean - critical * se, 3),
        "ci_high": round(mean + critical * se, 3),
        "sign_test_two_sided_p": round(sign_p, 4),
    }



def parse_arm(value):
    if "=" not in value:
        raise SystemExit("--arm must be name=dir1,dir2,...")
    name, raw = value.split("=", 1)
    dirs = [item.strip() for item in raw.split(",") if item.strip()]
    if not dirs:
        raise SystemExit("--arm needs at least one run dir: " + name)
    return name, dirs


def main(argv=None):
    parser = argparse.ArgumentParser(description="paired held-out ablation summary")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-file", default=TASKS)
    parser.add_argument("--arm", action="append", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    arms = []
    for value in args.arm:
        name, dirs = parse_arm(value)
        runs = []
        for run_dir in dirs:
            try:
                report = evaluate_run(run_dir, args.task_file, args.task_id)
            except HeldoutEvalError as exc:
                raise SystemExit(str(exc))
            axes = {axis["axis"]: axis for axis in report["axes"]}
            runs.append({
                "run_dir": run_dir,
                "total": report["summary"]["passed"],
                "denominator": report["summary"]["total"],
                "idea": axes.get("idea", {}).get("passed", 0),
                "experiment": axes.get("experiment", {}).get("passed", 0),
                "paper": axes.get("paper", {}).get("passed", 0),
            })
        arms.append({"name": name, "runs": runs})

    summary = {"task_id": args.task_id, "arms": []}
    for arm in arms:
        totals = [run["total"] for run in arm["runs"]]
        summary["arms"].append({
            "name": arm["name"],
            "n": len(totals),
            "scores": totals,
            "mean": round(sum(totals) / float(len(totals)), 3) if totals else 0.0,
            "idea_mean": round(sum(run["idea"] for run in arm["runs"]) / float(len(arm["runs"])), 3),
            "experiment_mean": round(sum(run["experiment"] for run in arm["runs"]) / float(len(arm["runs"])), 3),
            "paper_mean": round(sum(run["paper"] for run in arm["runs"]) / float(len(arm["runs"])), 3),
        })

    paired = None
    if len(arms) >= 2 and len(arms[0]["runs"]) == len(arms[1]["runs"]):
        diffs = [b["total"] - a["total"] for a, b in zip(arms[0]["runs"], arms[1]["runs"])]
        n = len(diffs)
        paired = {
            "left": arms[0]["name"],
            "right": arms[1]["name"],
            "differences": diffs,
            "mean": round(sum(diffs) / float(n), 3) if n else 0.0,
            "n": n,
            "underpowered": n < MIN_PAIRS,
            "interval": paired_interval(diffs),
            "direction": "none" if n < MIN_PAIRS else ("positive" if sum(diffs) > 0 else ("negative" if sum(diffs) < 0 else "none")),
        }
    summary["paired"] = paired
    summary["boundary"] = (
        "rubric conformance scores; n below %d is underpowered and must not be read as a direction" % MIN_PAIRS
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print("# Ablation: " + summary["task_id"])
        print("")
        for arm in summary["arms"]:
            print("- {0}: n={1} scores={2} mean={3} (idea {4} / experiment {5} / paper {6})".format(
                arm["name"], arm["n"], arm["scores"], arm["mean"],
                arm["idea_mean"], arm["experiment_mean"], arm["paper_mean"],
            ))
        if paired:
            print("")
            interval = paired.get("interval") or {}
            print("paired {0} -> {1}: diffs={2} mean={3} n={4} underpowered={5}".format(
                paired["left"], paired["right"], paired["differences"],
                paired["mean"], paired["n"], paired["underpowered"],
            ))
            print("  95% t interval: [{0}, {1}] | sign test p={2}".format(
                interval.get("ci_low"), interval.get("ci_high"),
                interval.get("sign_test_two_sided_p")))
        print("")
        print("> " + summary["boundary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

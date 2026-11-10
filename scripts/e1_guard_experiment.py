"""E1: score the replication guard as a classifier, against data it never saw.

The pilot in `57-` section 3.8 compared two arms on three packages that all blocked the *same*
comparison, and its arbiter was the same pool the guard reads. This experiment removes both
weaknesses:

* three **independent designs** (memory x gate, memory x parent_selection, gate x operators), so a
  blocked comparison in one design is not a re-run of another;
* three **disjoint seed ranges** — offer (1-12), arbiter (13-48), held-out (49-96) — so the truth
  label comes from seeds that influenced neither the low-power verdict nor the guard's decision.

The guard's decision is recomputed exactly as `study_replication._overturned` does it (a lower-power
verdict that the higher-power package leaves undecidable, or reverses, stops being signable), but
only over the offer+arbiter pair. The held-out package is then read as ground truth: an assertion is
"real" when the held-out interval decides it with the same sign.

    python scripts/e1_guard_experiment.py run       # executes missing packages, resumable
    python scripts/e1_guard_experiment.py analyze   # writes runtime_data/e1-result.json

Layout matters: held-out packages live under `eval/`, not `studies/`, so the runtime's sibling scan
cannot pick them up and the guard cannot see them by construction.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_agent.search_lab import write_study_package  # noqa: E402
from research_agent.study_claims import comparison_verdicts  # noqa: E402
from research_agent.storage import read_json, write_json_atomic  # noqa: E402

BUDGET = 60
MIN_DELTA = 0.005
OFFER = list(range(1, 13))
ARBITER = list(range(13, 49))
HOLDOUT = list(range(49, 97))
DATASETS = ("iris", "wine")
DESIGNS = {
    "D1_memory_gate": [
        "--factors memory=off,on",
        "--factors gate=off,on",
    ],
    "D2_memory_parent": [
        "--factors memory=off,on",
        "--factors gate=off",
        "--factors parent_selection=uniform,best",
    ],
    "D3_gate_operators": [
        "--factors memory=off",
        "--factors gate=off,on",
        "--factors operators=all,feature_only",
    ],
}
POWERS = {"L": OFFER, "M": ARBITER, "H": HOLDOUT}
GUARD_ROOT = ROOT / "runtime_data" / "e1-guard" / "studies"
HOLD_ROOT = ROOT / "runtime_data" / "e1-holdout" / "eval"
DECIDED = ("positive", "negative")


def design_levels(spec):
    design = {}
    for item in spec:
        factor, _, levels = item.split(" ", 1)[1].partition("=")
        design[factor.strip()] = [
            part.strip() for part in levels.split(",") if part.strip()
        ]
    return design


def package_path(name, dataset, power):
    root = HOLD_ROOT if power == "H" else GUARD_ROOT
    return root / ("%s-%s-%s" % (name, dataset, power))


def run_packages():
    for name, spec in DESIGNS.items():
        design = design_levels(spec)
        for dataset in DATASETS:
            for power, seeds in POWERS.items():
                target = package_path(name, dataset, power)
                if (target / "study-evidence.json").is_file():
                    print("skip", target.name)
                    continue
                started = time.time()
                write_study_package(target, dataset=dataset, seeds=seeds, budget=BUDGET,
                                    min_delta=MIN_DELTA, design=design)
                print("ran %-28s %5.1fs" % (target.name, time.time() - started), flush=True)


def states(directory):
    evidence = read_json(directory / "study-evidence.json")
    if not isinstance(evidence, dict):
        return {}
    return {
        row["comparison"]: row
        for row in comparison_verdicts(evidence)
    }


def analyze():
    rows = []
    for name in DESIGNS:
        for dataset in DATASETS:
            low = states(package_path(name, dataset, "L"))
            mid = states(package_path(name, dataset, "M"))
            high = states(package_path(name, dataset, "H"))
            for comparison, offer in low.items():
                if comparison not in mid or comparison not in high:
                    continue
                if offer["state"] not in DECIDED:
                    continue  # nothing was offered: no verdict to guard
                arbiter = mid[comparison]
                truth = high[comparison]
                blocked = arbiter["state"] != offer["state"]
                real = truth["state"] == offer["state"]
                if blocked and not real:
                    label = "true_positive"
                elif blocked and real:
                    label = "false_positive"
                elif not blocked and not real:
                    label = "false_negative"
                else:
                    label = "true_negative"
                rows.append({
                    "design": name,
                    "dataset": dataset,
                    "comparison": comparison,
                    "offer": {"state": offer["state"], "mean_diff": offer["mean_diff"], "ci95": offer["ci95"]},
                    "arbiter": {"state": arbiter["state"], "mean_diff": arbiter["mean_diff"], "ci95": arbiter["ci95"]},
                    "heldout": {"state": truth["state"], "mean_diff": truth["mean_diff"], "ci95": truth["ci95"]},
                    "guard_blocked": blocked,
                    "heldout_agrees": real,
                    "label": label,
                })
    counts = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    offered = len(rows)
    blocked = counts.get("true_positive", 0) + counts.get("false_positive", 0)
    passed = offered - blocked
    summary = {
        "schema_version": "e1-guard-experiment-0.1",
        "designs": sorted(DESIGNS),
        "datasets": list(DATASETS),
        "seeds": {"offer": [OFFER[0], OFFER[-1]], "arbiter": [ARBITER[0], ARBITER[-1]],
                  "heldout": [HOLDOUT[0], HOLDOUT[-1]]},
        "budget": BUDGET,
        "min_delta": MIN_DELTA,
        "offered_assertions": offered,
        "guard_blocked": blocked,
        "guard_passed": passed,
        "counts": counts,
        "block_precision": round(counts.get("true_positive", 0) / blocked, 4) if blocked else None,
        "miss_rate_among_passed": round(counts.get("false_negative", 0) / passed, 4) if passed else None,
        "rows": rows,
        "boundary": (
            "ground truth here is a third disjoint seed range on the same analogue loop, not an "
            "external standard: a held-out disagreement means 'not reproduced at 48 seeds', not "
            "'false in the world'. Nothing is signed, and no published system is reproduced."
        ),
    }
    write_json_atomic(ROOT / "runtime_data" / "e1-result.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, ensure_ascii=False, indent=2))
    for row in rows:
        print("%-18s %-13s %-46s %-16s blocked=%-5s heldout_agrees=%-5s %s" % (
            row["design"], row["dataset"], row["comparison"], row["offer"]["state"],
            row["guard_blocked"], row["heldout_agrees"], row["label"]))
    return summary


if __name__ == "__main__":
    stage = (sys.argv[1] if len(sys.argv) > 1 else "both").strip().lower()
    if stage in ("run", "both"):
        run_packages()
    if stage in ("analyze", "both"):
        analyze()

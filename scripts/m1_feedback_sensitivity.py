"""M1: does the next action actually track the quality of the feedback?

Q2 (71-§5 步 3; 图① 反馈环口径): the FeedbackPort claims a verdict changes the
next action.  Falsifiable form: five feedback classes over the SAME project —
real / shuffled / stale / noisy / contradictory — go through the same
deterministic decision table (feedback.verdict_action_table).  The 切口 stands
only if the real class reproduces its own actions while every degraded class
discriminates (match rate materially below the real rate, and the contradictory
class escalates to a human).  If degraded classes match at ≈ the real rate,
反馈敏感性与信息价值一致 → 切口不成立 — recorded as such, not argued away.

Honest boundary: this measures the discriminative power of the seam's decision
table on one project snapshot.  The action table is not yet wired into
next_actions consumers, so this is not an end-to-end behavior-change
measurement; it is the precondition for that wiring.
"""

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.feedback import verdict_action_table  # noqa: E402
from research_agent.verdict_ledger import collect  # noqa: E402

RESULT_SCHEMA = "m1-feedback-sensitivity-0.1"
SEED = 20261111

KIND_STATUSES = {
    "closure": ["signed", "ready", "missing"],
    "claim": ["signed", "draft", "absent"],
    "experiment": ["signed", "ready_for_human_signature", "missing"],
    "study": ["signed", "ready_for_human_signature", "missing"],
}
_OPPOSITE = {
    "signed": "missing",
    "ready": "missing",
    "ready_for_human_signature": "missing",
    "draft": "signed",
    "missing": "signed",
}


def _rewind_signatures(rows):
    """The stale class: what a pre-signature snapshot claimed, verbatim."""
    out = []
    for row in rows:
        row = dict(row)
        if row.get("kind") == "closure" and row.get("status") == "signed":
            row["status"] = "ready"
        if row.get("kind") == "claim" and row.get("status") == "signed":
            row["status"] = "draft"
        out.append(row)
    return out


def _shuffle(rows):
    """The shuffled class: verdicts attached to the wrong subjects (rotate by one)."""
    by_kind = {}
    for row in rows:
        by_kind.setdefault(str(row.get("kind") or ""), []).append(dict(row))
    out = []
    for kind, items in by_kind.items():
        items.sort(key=lambda r: r.get("subject", ""))
        statuses = [str(r.get("status") or "") for r in items]
        rotated = statuses[1:] + statuses[:1]
        for row, status in zip(items, rotated):
            row = dict(row)
            row["status"] = status
            out.append(row)
    return out


def _noisy(rows, seed=SEED):
    """The noisy class: seeded perturbation of statuses and hash bindings."""
    rng = random.Random(seed)
    out = []
    for row in rows:
        row = dict(row)
        kind = str(row.get("kind") or "")
        choices = [s for s in KIND_STATUSES.get(kind, []) if s != row.get("status")]
        if choices and rng.random() < 0.5:
            row["status"] = rng.choice(choices)
        row["source_sha256"] = "0" * 64
        out.append(row)
    return out


def _contradictory(rows):
    """The contradictory class: every verdict gets a twin that says the opposite."""
    out = []
    for row in rows:
        out.append(dict(row))
        twin = dict(row)
        status = str(row.get("status") or "")
        twin["status"] = _OPPOSITE.get(status, "missing")
        out.append(twin)
    return out


def _action_map(rows):
    table = verdict_action_table(rows)
    return {item["subject"]: item["action"] for item in table["actions"]}


def _match_rate(real_map, other_map):
    if not real_map:
        return 0.0, []
    subjects = sorted(real_map)
    mismatches = [s for s in subjects if other_map.get(s) != real_map[s]]
    return round(1.0 - len(mismatches) / len(subjects), 4), mismatches


def run(project: Path, limit: int = 50) -> dict:
    real_rows = collect(Path(project), limit=limit)["rows"]
    classes = {
        "real": real_rows,
        "stale": _rewind_signatures(real_rows),
        "shuffled": _shuffle(real_rows),
        "noisy": _noisy(real_rows),
        "contradictory": _contradictory(real_rows),
    }
    real_map = _action_map(real_rows)
    per_class = {}
    for name, rows in classes.items():
        table = verdict_action_table(rows)
        match_rate, mismatches = _match_rate(real_map, {i["subject"]: i["action"] for i in table["actions"]})
        per_class[name] = {
            "rows": len(rows),
            "subjects": len(table["actions"]),
            "action_counts": table["counts"],
            "match_rate_vs_real": match_rate,
            "mismatched_subjects": mismatches[:10],
            "escalations": table["counts"].get("escalate_conflict", 0),
        }
    # determinism of the real class: the same rows must yield the same actions
    per_class["real"]["deterministic"] = verdict_action_table(real_rows)["actions"] == verdict_action_table(real_rows)["actions"]

    degraded = [per_class[name]["match_rate_vs_real"] for name in ("stale", "shuffled", "noisy")]
    mean_degraded = round(sum(degraded) / len(degraded), 4)
    real_rate = per_class["real"]["match_rate_vs_real"]
    escalations = per_class["contradictory"]["escalations"]
    supported = (
        per_class["real"].get("deterministic") is True
        and real_rate == 1.0
        and mean_degraded < 0.9
        and escalations >= 1
    )
    return {
        "schema_version": RESULT_SCHEMA,
        "project": str(Path(project).resolve()),
        "per_class": per_class,
        "metrics": {
            "real_match_rate": real_rate,
            "mean_degraded_match_rate": mean_degraded,
            "contradictory_escalations": escalations,
        },
        "criterion": (
            "切口成立 = 真实类自复现 (rate 1.0) 且退化类平均判别 (match < 0.9) 且矛盾类升级人工；"
            "否则 反馈敏感性与信息价值一致 → 切口不成立"
        ),
        "verdict": "supported" if supported else "not_supported",
        "boundary": (
            "one project snapshot; measures the discriminative power of the seam's decision "
            "table, not end-to-end behavior change — the action table is not yet wired into "
            "next_actions consumers (verdict-ledger SPEC roadmap)"
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    result = run(Path(args.project), limit=args.limit)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

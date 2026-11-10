"""Re-score the E1 blocks against the claim as stated, not just its sign.

`analyze` in scripts/e1_guard_experiment.py labels a block correct only when the held-out interval
disagrees in *direction*. A signed assertion also carries a magnitude, and the new
`overturn_kind` field makes the two separable: an arbiter whose interval excludes the claimed effect
is evidence the claim overstates, not an absence of evidence. This re-reads the stored rows and
reports both scores.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_agent.study_replication import overturn_kind  # noqa: E402

result = json.loads((ROOT / "runtime_data" / "e1-result.json").read_text(encoding="utf-8"))
direction = {"correct": 0, "wrong": 0}
magnitude = {"correct": 0, "wrong": 0}
misses = []
for row in result["rows"]:
    claimed = row["offer"]["mean_diff"]
    held_low, held_high = row["heldout"]["ci95"]
    reproduces_size = held_low <= claimed <= held_high
    if row["guard_blocked"]:
        kind = overturn_kind(
            row["offer"]["state"], claimed, row["arbiter"]["state"], row["arbiter"]["ci95"]
        )
        right_direction = not row["heldout_agrees"]
        direction["correct" if right_direction else "wrong"] += 1
        right_claim = not reproduces_size
        magnitude["correct" if right_claim else "wrong"] += 1
        print("blocked %-18s %-5s %-46s kind=%-22s claimed %+0.4f heldout [%+0.4f, %+0.4f] "
              "direction_ok=%s claim_ok=%s"
              % (row["design"], row["dataset"], row["comparison"], kind, claimed,
                 held_low, held_high, right_direction, right_claim))
    elif not reproduces_size:
        misses.append(row)

blocked = sum(direction.values())
print()
print("blocks scored:", blocked)
print("correct on direction      :", direction, "precision=%s" % round(direction["correct"] / blocked, 3))
print("correct on claim as stated:", magnitude, "precision=%s" % round(magnitude["correct"] / blocked, 3))
print("passed assertions whose claimed size the held-out interval excludes:", len(misses),
      "of", result["guard_passed"])
for row in misses:
    print("   missed %-18s %-5s %-46s claimed %+0.4f heldout [%+0.4f, %+0.4f]"
          % (row["design"], row["dataset"], row["comparison"], row["offer"]["mean_diff"],
             row["heldout"]["ci95"][0], row["heldout"]["ci95"][1]))

"""M2: the same candidate pool through the four memory admission strategies.

71-§4.3 / M2 四存储策略对照的准入半程: one candidate pool (replayable source /
missing source / independently verified / bare) runs through store_all,
store_none, replay_then_store and independent_verify_then_store.  The measured
object is the ADMISSION DECISION SET per strategy — the downstream cross-task
benefit measurement needs multi-session / multi-supply answering and is
explicitly out of scope here (fact-baseline 边界).

Criterion (pre-registered): the four strategies must produce pairwise distinct
admission sets ordered by strictness (store_all ⊇ replay ⊇ independent_verify ⊇
store_none) — otherwise the strategies are not actually discriminating and the
M2 experiment design fails before it starts.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.memory_port import admit  # noqa: E402

RESULT_SCHEMA = "m2-memory-strategies-0.1"


def _candidate_pool(project: Path) -> list:
    """A pool covering every admission-relevant shape, bound to real project files."""
    import hashlib

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    good_source = project / "inputs" / "protocol.txt"
    good_source.parent.mkdir(parents=True, exist_ok=True)
    if not good_source.is_file():
        good_source.write_text("preregistered protocol: temperature, humidity, sample size, stopping rule\n", encoding="utf-8")
    receipt = project / "inputs" / "verification.json"
    if not receipt.is_file():
        receipt.write_text(json.dumps({"verified_by": "independent session", "item": "protocol"}), encoding="utf-8")

    return [
        {
            "text": "missing temperature field -> rerun the protocol audit -> fix before S5",
            "sources": ["inputs/protocol.txt"],
        },
        {
            "text": "unverified lore says humidity does not matter -> ignore humidity checks",
            "sources": ["inputs/missing-source.txt"],
        },
        {
            "text": "independently verified: stopping rule fires on sample size, not wall clock",
            "sources": ["inputs/protocol.txt"],
            "verification": {"source": "inputs/verification.json", "sha256": sha(receipt)},
        },
        {
            "text": "bare claim with no binding at all -> treat any metric as fine",
            "sources": [],
        },
    ]


def run(project: Path, output_dir: Path = None) -> dict:
    pool = _candidate_pool(Path(project))
    per_strategy = {}
    for strategy in ("store_all", "store_none", "replay_then_store", "independent_verify_then_store"):
        report = admit(pool, strategy=strategy, project=Path(project))
        per_strategy[strategy] = {
            "admitted_texts": [str(item.get("text") or "")[:80] for item in report["admitted"]],
            "counts": report["counts"],
            "rows": report["rows"],
        }

    def key(strategy: str):
        return frozenset(per_strategy[strategy]["admitted_texts"])

    k_all, k_none = key("store_all"), key("store_none")
    k_replay, k_indep = key("replay_then_store"), key("independent_verify_then_store")
    strictness = {
        "store_all_admits_everything": len(per_strategy["store_all"]["admitted_texts"]) == len(pool),
        "store_none_admits_nothing": len(per_strategy["store_none"]["admitted_texts"]) == 0,
        "replay_between_extremes": k_replay != k_all and k_replay != k_none,
        "independent_between_extremes": k_indep != k_all and k_indep != k_none,
        "pairwise_distinct": len({k_all, k_none, k_replay, k_indep}) == 4,
    }
    supported = all(strictness.values())
    return {
        "schema_version": RESULT_SCHEMA,
        "project": str(Path(project).resolve()),
        "pool_size": len(pool),
        "per_strategy": per_strategy,
        "strictness": strictness,
        "criterion": (
            "M2 准入半程成立 = 四策略两两互异且严格度有序（store_all ⊇ replay ⊇ "
            "independent_verify ⊇ store_none）；否则策略不判别，M2 实验设计失败"
        ),
        "verdict": "supported" if supported else "not_supported",
        "boundary": (
            "measures the admission decision sets only; downstream cross-task benefit "
            "needs multi-session / multi-supply answering (fact-baseline 边界) and is "
            "out of scope here"
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args(argv)
    result = run(Path(args.project))
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

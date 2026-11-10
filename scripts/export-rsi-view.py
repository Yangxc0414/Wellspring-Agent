"""Export an RSI ledger + status report as a static workbench fixture.

Reads a StepLedger produced by the local RSI control plane (no API) and
writes research_agent/web/data/rsi.json for the workbench "自进化" view.
Read-only: it never mutates the ledger.

Usage:
    python scripts/export-rsi-view.py \
        --ledger research_agent/web/data/rsi-chemlab-v2/ledger.json \
        --output research_agent/web/data/rsi.json
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from research_agent.paths import build_info
from research_agent.rsi import RSIController, StepLedger


def main() -> int:
    parser = argparse.ArgumentParser(description="export RSI ledger view fixture")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--output", default="research_agent/web/data/rsi.json")
    args = parser.parse_args()

    ledger_path = Path(args.ledger)
    ledger = StepLedger.load(ledger_path)
    report = RSIController(ledger).report()

    view = {
        "schema_version": "rsi-view-0.2",
        "static": True,
        "api_connected": False,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_fingerprint": str(build_info().get("fingerprint") or ""),
        "simulation_episodes": sum(1 for episode in ledger.episodes if episode.simulation),
        "source": {
            "ledger": str(ledger_path),
            "command": "python -m research_agent rsi status --ledger " + str(ledger_path),
            "note": (
                "静态快照：本地 RSI 控制面产出的真实台账（本地评测、无 API）。"
                "harness-only / claim_eligible=false 的证据不构成能力主张。"
            ),
        },
        "ledger": ledger.to_dict(),
        "report": report,
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(str(out), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(view, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("wrote " + str(out) + " (episodes=%d)" % len(ledger.episodes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

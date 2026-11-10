"""Walk the documented RSI demo chain end-to-end, offline, and assert every artifact lands.

AGENTS.md lists `rsi fixture`, `rsi real-trial`, `rsi story` as separate copy-paste commands, but
nothing checked that the chain actually runs from a clean directory - which is how #81's readback
acceptance got blocked by a ledger that no documented step had produced. This script is the
executable version of that documentation: it runs the chain in a temporary directory, asserts each
producer wrote its artifact, and prints the gate verdict so a human can see what the loop concluded.

It never signs, admits, or publishes; it only runs read/proposal/evaluation commands that are safe
offline. Usage:
    python scripts/demo_walkthrough.py [--work-dir DIR]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "research_agent", *args],
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="walk the offline RSI demo chain")
    parser.add_argument("--work-dir", default="")
    args = parser.parse_args()
    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="rsi-demo-"))
    work.mkdir(parents=True, exist_ok=True)

    ledger = work / "ledger.json"
    steps = [
        ("fixture", ["rsi", "fixture", "--ledger", str(ledger), "--output-dir", str(work / "fixture")]),
        ("real-trial", ["rsi", "real-trial", "--ledger", str(work / "real-ledger.json"),
                        "--output-dir", str(work / "real")]),
        ("story", ["rsi", "story", "--ledger", str(work / "real-ledger.json"),
                   "--output", str(work / "story.json")]),
    ]
    for name, cmd in steps:
        proc = run(*cmd)
        if proc.returncode != 0:
            print("FAIL %s (rc=%d)\n%s" % (name, proc.returncode, proc.stdout[-800:]))
            return 1
        print("ok   %s" % name)

    story_path = work / "story.json"
    if not story_path.is_file():
        print("FAIL story artifact missing")
        return 1
    story = json.loads(story_path.read_text(encoding="utf-8"))
    summary = story.get("summary", {})
    print("gate_verdict=%s episodes=%s decided=%s rejected=%s simulation_episodes=%s" % (
        summary.get("gate_verdict"), summary.get("episodes"), summary.get("decided"),
        summary.get("rejected"), (story.get("provenance") or {}).get("simulation_episodes"),
    ))
    print("work dir: %s" % work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

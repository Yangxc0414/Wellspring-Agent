"""Run the full suite and record the verdict against the code fingerprint.

    python scripts/record_test_verdict.py            # run and record
    python scripts/record_test_verdict.py --show     # what does the newest verdict cover?

The exit code comes from the parsed runner summary, not from a shell chain: a `grep` at the end of
`python -m unittest ... ; grep ...` reports grep's success, and this session actually received
"completed (exit code 0)" for a suite that printed FAILED.
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from research_agent.paths import build_info  # noqa: E402
from research_agent.storage import read_json, write_json_atomic  # noqa: E402
from research_agent.verdicts import (  # noqa: E402
    VERDICT_FILENAME,
    parse_unittest_output,
    verdict_record,
    verdict_status,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record the suite verdict with its fingerprint")
    parser.add_argument("--show", action="store_true", help="print the newest verdict's coverage")
    parser.add_argument(
        "--output", default=str(REPO / "runtime_data" / VERDICT_FILENAME),
        help="where to write the verdict record",
    )
    args = parser.parse_args()
    out = Path(args.output)
    current = str(build_info().get("fingerprint") or "")

    if args.show:
        record = read_json(out) if out.is_file() else None
        status = verdict_status(record, current)
        print(
            "%s | tests %s | current %s | %s"
            % (
                status["state"],
                (record or {}).get("tests_run"),
                current,
                status["detail"],
            )
        )
        return 0 if status["covers_current_source"] else 1

    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace",
    )
    parsed = parse_unittest_output(proc.stdout or "")
    record = verdict_record(
        fingerprint=current,
        tests_run=parsed["tests_run"],
        seconds=parsed["seconds"],
        ok=parsed["ok"],
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source="scripts/record_test_verdict.py",
        truncated=not parsed["found"],
        failures=parsed.get("failures", 0),
        errors=parsed.get("errors", 0),
        summary=parsed["summary"],
    )
    write_json_atomic(out, record)
    print("%s\nrecorded: %s -> %s" % (parsed["summary"], parsed["summary"], out))
    # the verdict line decides the exit code, never the shell chain
    return 0 if parsed["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

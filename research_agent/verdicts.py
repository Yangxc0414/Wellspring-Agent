"""A test verdict must say which code it is a verdict about.

Three times this session a green suite was quoted against code it did not cover: a background
run interrupted mid-flight (exit 1073807364, a log with no `Ran` line that a naive reader would
call "still running" and a careless one would call "passed"); source edited while a run was in
flight, which voids the verdict by this project's own rule; and a completion notification reporting
`exit code 0` for a suite that in fact printed `FAILED (failures=1)`, because the shell chain ended
in a `grep` that succeeded. The MCP face already solved this shape for live servers - every error
names the build that served it, so staleness is one comparison (#76). The same idea belongs on the
verdict.

These functions are pure: they never run a test, never decide whether the suite passed, and never
infer anything from a shell exit code. The runner is `scripts/record_test_verdict.py`, and it parses
the runner's own output, so "green" always arrives with a code fingerprint attached.
"""

from typing import Any, Dict, Optional
import re

VERDICT_FILENAME = "test-verdict.json"
VERDICT_SCHEMA = "test-verdict-0.1"
RAN_LINE = "Ran "
OK_WORD = "OK"
FAILED_WORD = "FAILED"
# "Ran 1207 tests in 352.457s". The first version of this parser indexed the split result by hand
# and read position 3, which is the word "in": float() raised, the except swallowed it, and the
# record was written with seconds=0.0 while still reporting a green verdict. A summary we cannot
# read is now fail-closed rather than defaulted.
RAN_RE = re.compile(r"^Ran (\d+) tests? in ([0-9.]+)s")
# "FAILED (failures=39, errors=115)" / "FAILED (errors=58)". The counts are
# part of the runner's own verdict and must reach the structured record; a
# previous version left errors=0 in the JSON while summary_line said 58.
COUNT_RE = re.compile(r"(failures|errors)=(\d+)")


def _failure_counts(verdict_line: str) -> Dict[str, int]:
    counts = {"failures": 0, "errors": 0}
    for key, value in COUNT_RE.findall(str(verdict_line or "")):
        counts[key] = int(value)
    return counts


def parse_unittest_output(text: str) -> Dict[str, Any]:
    """Read the runner's own summary out of its output.

    Returns `found=False` when no readable summary line exists - which is the interrupted-run case,
    and the whole reason this module exists. A missing verdict is reported as missing, never as
    success, and an unreadable one is reported as unreadable rather than parsed into zeros.
    """
    lines = [line.strip() for line in str(text or "").splitlines()]
    ran = next((line for line in reversed(lines) if line.startswith(RAN_LINE)), "")
    tail = next(
        (line for line in reversed(lines) if line in (OK_WORD,) or line.startswith(FAILED_WORD)),
        "",
    )
    if not ran:
        return {"found": False, "tests_run": 0, "seconds": 0.0, "ok": False, "summary": "",
                "failures": 0, "errors": 0,
                "why": "no 'Ran N tests' line: the run did not finish, so it says nothing"}
    match = RAN_RE.search(ran)
    if match is None:
        return {
            "found": False,
            "tests_run": 0,
            "seconds": 0.0,
            "ok": False,
            "summary": ran,
            "failures": 0,
            "errors": 0,
            "why": "summary line present but unreadable, so it is not counted as a verdict: %s" % ran,
        }
    counts = _failure_counts(tail)
    return {
        "found": True,
        "tests_run": int(match.group(1)),
        "seconds": float(match.group(2)),
        "ok": tail == OK_WORD,
        "summary": "%s / %s" % (ran, tail or "(no verdict line)"),
        "verdict_line": tail,
        "failures": counts["failures"],
        "errors": counts["errors"],
        "failures_reported": tail.startswith(FAILED_WORD) if tail else False,
    }


def verdict_record(
    fingerprint: str,
    tests_run: int,
    seconds: float,
    ok: bool,
    finished_at: str,
    source: str = "",
    truncated: bool = False,
    failures: int = 0,
    errors: int = 0,
    summary: str = "",
) -> Dict[str, Any]:
    """What a green run actually was: the code it covered, how many tests, and what it said."""
    return {
        "schema_version": VERDICT_SCHEMA,
        "source_fingerprint": str(fingerprint or ""),
        "tests_run": int(tests_run),
        "failures": int(failures),
        "errors": int(errors),
        "seconds": round(float(seconds), 3),
        "ok": bool(ok),
        "truncated": bool(truncated),
        "finished_at": str(finished_at or ""),
        "produced_by": str(source or ""),
        # the runner's own words, so a reader can check the record against a log instead of trusting it
        "summary_line": str(summary or ""),
        "read_only": True,
        "base": "%d test(s) against fingerprint %s"
        % (int(tests_run), str(fingerprint or "unknown")),
        "boundary": (
            "a statement about one code version, not a status: this record covers exactly "
            "source_fingerprint and nothing else, and it is written by the test runner parsing its "
            "own output, never from a shell exit code (a chained command's exit code is the last "
            "command's, not the suite's). ok=False or truncated=True is still a valid record: an "
            "interrupted run has to be recorded, because the absence of a verdict is the thing "
            "people later misread as success"
        ),
    }


def verdict_status(record: Optional[Dict[str, Any]], current_fingerprint: str) -> Dict[str, Any]:
    """Does the newest recorded verdict describe the code on disk right now?"""
    if not record:
        return {
            "state": "absent",
            "covers_current_source": False,
            "detail": "no verdict record exists: the current source has no full-suite verdict",
        }
    if record.get("truncated"):
        return {
            "state": "truncated",
            "covers_current_source": False,
            "detail": "the newest record is from a run that did not finish (%s)"
            % record.get("base", ""),
        }
    same = str(record.get("source_fingerprint") or "") == str(current_fingerprint or "")
    return {
        "state": "current" if (same and record.get("ok"))
        else ("stale" if not same else "failed"),
        "covers_current_source": bool(same and record.get("ok")),
        "recorded_for": str(record.get("source_fingerprint") or ""),
        "current_source": str(current_fingerprint or ""),
        "tests_run": record.get("tests_run"),
        "detail": (
            "the newest verdict covers %s for %d test(s); current source is %s"
            % (record.get("source_fingerprint") or "unknown",
               int(record.get("tests_run") or 0),
               current_fingerprint or "unknown")
        ),
    }


__all__ = [
    "VERDICT_FILENAME",
    "VERDICT_SCHEMA",
    "parse_unittest_output",
    "verdict_record",
    "verdict_status",
]

"""Check the curated ESE history against the real runtime artifacts.

`apps/web/public/ese-history.json` is curated prose plus a small `verify` block per
entry. The prose can be edited, but the numbers must keep matching `runtime_data/`.
This script is the guard: it re-reads the original result/demo JSON and fails on drift.

Usage:
    python scripts/build_web_ese_history.py --check
    python scripts/build_web_ese_history.py           # check only; copy is done by vite
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY = ROOT / "apps" / "web" / "public" / "ese-history.json"

Q0_PATTERN = re.compile(r"(\d+)\s+full-text source\(s\),\s*(\d+)\s+span\(s\)")

RESULT_FIELDS = {
    "commits": ("pooled", "commits"),
    "rate": ("pooled", "rate"),
    "bugfix_difference": ("pooled", "difference"),
    "adjusted_difference": ("stratified", "adjusted_difference"),
}


class HistoryError(ValueError):
    """历史条目与原产物不一致。"""


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _close(actual, expected):
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(actual) - float(expected)) <= 1e-6
    return actual == expected


def _check_result(entry, path):
    payload = _read_json(path)
    problems = []
    for key, expected in entry["verify"]["expect"].items():
        section, field = RESULT_FIELDS[key]
        actual = (payload.get(section) or {}).get(field)
        if not _close(actual, expected):
            problems.append(
                "{0}: {1}={2!r}, 但 {3} 里是 {4!r}".format(
                    entry["id"], key, expected, path.name, actual
                )
            )
    return problems


def _check_demo(entry, path):
    payload = _read_json(path)
    gates = payload.get("gates") or []
    q0 = ""
    for gate in gates:
        if isinstance(gate, dict) and str(gate.get("gate") or "") == "Q0":
            q0 = str(gate.get("reason") or "")
            break
    match = Q0_PATTERN.search(q0)
    if not match:
        return ["{0}: {1} 里找不到 Q0 的 sources/spans 读数".format(entry["id"], path.name)]

    sources, spans = int(match.group(1)), int(match.group(2))
    problems = []
    expect = entry["verify"]["expect"]
    if not _close(sources, expect["q0_sources"]):
        problems.append(
            "{0}: q0_sources={1}, 但产物里是 {2}".format(
                entry["id"], expect["q0_sources"], sources
            )
        )
    if not _close(spans, expect["q0_spans"]):
        problems.append(
            "{0}: q0_spans={1}, 但产物里是 {2}".format(
                entry["id"], expect["q0_spans"], spans
            )
        )
    return problems


def validate(history_path=DEFAULT_HISTORY, root=ROOT):
    """Return (ok, problems). Never raises for content drift."""
    history_path = Path(history_path)
    payload = _read_json(history_path)
    entries = payload.get("entries") or []
    problems = []

    if payload.get("count") != len(entries):
        problems.append(
            "count={0}, 但 entries 有 {1} 条".format(payload.get("count"), len(entries))
        )

    seen = set()
    for entry in entries:
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            problems.append("存在没有 id 的条目")
            continue
        if entry_id in seen:
            problems.append("{0}: id 重复".format(entry_id))
        seen.add(entry_id)

        verify = entry.get("verify") or {}
        kind = str(verify.get("kind") or "")
        rel = str(verify.get("path") or "")
        if kind not in ("result", "demo") or not rel:
            problems.append("{0}: verify 必须是 result/demo 且带 path".format(entry_id))
            continue

        target = Path(root) / rel
        if not target.is_file():
            problems.append("{0}: 原产物不存在 {1}".format(entry_id, rel))
            continue

        try:
            if kind == "result":
                problems.extend(_check_result(entry, target))
            else:
                problems.extend(_check_demo(entry, target))
        except (KeyError, ValueError, TypeError) as error:
            problems.append("{0}: 校验失败 {1}".format(entry_id, error))

    return not problems, problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="check curated ESE history")
    parser.add_argument("--history", default=str(DEFAULT_HISTORY))
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--check", action="store_true", help="only validate (default)")
    args = parser.parse_args(argv)

    ok, problems = validate(args.history, args.root)
    if not ok:
        print("ese history: FAILED")
        for problem in problems:
            print("  - " + problem)
        return 1
    payload = _read_json(args.history)
    print("ese history: OK ({0} entries match runtime_data)".format(len(payload["entries"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())

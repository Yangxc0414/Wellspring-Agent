"""Verify innovation claims against repository facts.

Reads research_agent/web/data/innovations.json (the machine-readable mirror
of the innovation-ledger design doc) and checks every enforcement pointer
against the actual repository: `exists` checks require the file to be present,
`contains` checks require the text to appear in the file. Writes a static
report for the workbench and exits non-zero when any check fails, so the
ledger can never silently drift from the code ("claim must bind evidence"
applied to our own claims).

Usage:
    python scripts/verify-innovation-claims.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research_agent" / "web" / "data" / "innovations.json"
REPORT = ROOT / "research_agent" / "web" / "data" / "innovations-report.json"


def run_check(check: dict) -> bool:
    path = ROOT / check["path"]
    if check["type"] == "exists":
        return path.is_file()
    if check["type"] == "contains":
        if not path.is_file():
            return False
        return check["text"] in path.read_text(encoding="utf-8")
    raise ValueError("unknown check type: " + str(check.get("type")))


def main() -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    results = []
    failures = 0
    for pillar in data.get("pillars", []):
        for check in pillar.get("checks", []):
            ok = run_check(check)
            if not ok:
                failures += 1
            results.append({
                "pillar": pillar.get("id", ""),
                "pillar_title": pillar.get("title", ""),
                "label": check.get("label", ""),
                "type": check.get("type", ""),
                "path": check.get("path", ""),
                "ok": ok,
            })
    report = {
        "schema_version": "innovations-report-0.1",
        "static": True,
        "source": "scripts/verify-innovation-claims.py",
        "total": len(results),
        "passed": len(results) - failures,
        "failed": failures,
        "results": results,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with open(str(REPORT), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    for row in results:
        print("%s  %-28s %s" % ("PASS" if row["ok"] else "FAIL", row["pillar"], row["label"]))
    print("%d/%d checks passed -> %s" % (report["passed"], report["total"], REPORT))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

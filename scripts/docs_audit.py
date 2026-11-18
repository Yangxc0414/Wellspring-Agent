"""Audit the design archive: duplicate numbers, index links, count claims.

The design folder is append-only history. Two independent failures are invisible in normal
reading: two documents claiming the same number (we shipped a duplicate 81 once), and an index
that points at a renamed file. Both are cheap to check and expensive to discover later.

Read-only. Exit code 1 means at least one blocker.
"""

import argparse
import json
import re
from pathlib import Path

NUMBERED = re.compile(r"^(\d+)-.+\.md$")
LINK = re.compile(r"\]\(([^)]+\.md)\)")
COUNT = re.compile(r"00–(\d+)\s*共\s*(\d+)\s*份")
INDEX_COUNT = re.compile(r"编号 00–(\d+)（(\d+) 份")


def audit(root):
    base = Path(root)
    design = base / "design"
    blockers = []
    warnings = []
    if not design.is_dir():
        return {"status": "blocked", "blockers": [{"kind": "design_dir_missing"}], "warnings": []}
    numbered = {}
    for path in sorted(design.glob("*.md")):
        match = NUMBERED.match(path.name)
        if match:
            numbered.setdefault(int(match.group(1)), []).append(path.name)
    for number, names in sorted(numbered.items()):
        if len(names) > 1:
            blockers.append({"kind": "duplicate_number", "number": number, "files": names})
    actual_max = max(numbered) if numbered else 0
    actual_count = sum(len(names) for names in numbered.values())

    index = design / "README.md"
    if index.is_file():
        text = index.read_text(encoding="utf-8")
        for target in LINK.findall(text):
            if target.startswith("http"):
                continue
            if not (design / target).is_file():
                blockers.append({"kind": "index_missing_target", "target": target})
        match = INDEX_COUNT.search(text)
        if match:
            if int(match.group(1)) != actual_max or int(match.group(2)) != actual_count:
                blockers.append({
                    "kind": "index_count_mismatch", "claimed_max": int(match.group(1)),
                    "claimed_count": int(match.group(2)), "actual_max": actual_max,
                    "actual_count": actual_count,
                })
        else:
            warnings.append("design/README.md has no '编号 00–N（M 份' count marker")
    else:
        blockers.append({"kind": "index_missing"})

    readme = base / "README.md"
    if readme.is_file():
        match = COUNT.search(readme.read_text(encoding="utf-8"))
        if match:
            if int(match.group(1)) != actual_max or int(match.group(2)) != actual_count:
                blockers.append({
                    "kind": "readme_count_mismatch", "claimed_max": int(match.group(1)),
                    "claimed_count": int(match.group(2)), "actual_max": actual_max,
                    "actual_count": actual_count,
                })
        else:
            warnings.append("root README.md has no '00–N 共 M 份' count marker")
    return {
        "status": "blocked" if blockers else "ok",
        "max_number": actual_max,
        "count": actual_count,
        "blockers": blockers,
        "warnings": warnings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="audit design numbering and index links")
    parser.add_argument("--root", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = audit(args.root)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("design archive: " + report["status"])
        print("  numbered docs: {0} (max {1})".format(report["count"], report["max_number"]))
        for blocker in report["blockers"]:
            print("  BLOCK {0}: {1}".format(blocker.get("kind"), json.dumps(blocker, ensure_ascii=False)))
        for warning in report["warnings"]:
            print("  warn  " + warning)
    return 1 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

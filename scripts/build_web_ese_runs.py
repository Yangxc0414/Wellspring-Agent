"""Build the workbench's bundled ESE runs snapshot from runtime_data.

The React workbench fetches /api/ese/runs when a local runtime is up and falls back to
/ese-runs.json otherwise. This script keeps the fallback honest: it is generated from the
same scanner the runtime uses, not hand-written.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.runtime.ese_runs import summary  # noqa: E402


def build(scan_root, out_path):
    payload = summary(scan_root)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="build apps/web/public/ese-runs.json")
    parser.add_argument("--scan-root", default="runtime_data")
    parser.add_argument("--out", default="apps/web/public/ese-runs.json")
    args = parser.parse_args(argv)
    payload = build(args.scan_root, args.out)
    print("ese runs snapshot: {0} run(s) -> {1}".format(payload["count"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

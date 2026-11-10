"""Ask the connector's own server, in a fresh process, which build it is running.

A long-lived MCP process keeps the modules it imported at start-up, so edits to
`research_agent/` are invisible to the host until the connector reloads. This probe answers the
two questions separately: what does a *fresh* server say (its `build.fingerprint`, the replication
pool size and the design keys), so the value can be compared against whatever the host returns.

    python scripts/mcp_build_probe.py [--project runtime_data/power-ladder]

If the host's `research_status` has no `build` field, or its fingerprint differs from this output,
the connector is stale and must be reloaded — nothing else about "tested through the host" is
trustworthy until then.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from research_mcp_demo import MCPClient  # noqa: E402


def probe(root: Path, project: str) -> dict:
    client = MCPClient(root, {"PYTHONIOENCODING": "utf-8"})
    try:
        payload = client.call("research_status", {"project_dir": str(root / project)})
    finally:
        client.close()
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    replication = (body.get("closure_profiles") or {}).get("replication") or {}
    return {
        "local_fingerprint": _local_fingerprint(),
        "build": body.get("build") or payload.get("build"),
        "replication_packages": replication.get("packages"),
        "overturned_design_keys": sorted(
            {item.get("design_key") for item in replication.get("overturned") or []}
        ),
        "strongest_used": sorted(
            {
                (item.get("at_higher_power") or {}).get("directory")
                for item in replication.get("overturned") or []
            }
        ),
    }


def _local_fingerprint() -> str:
    from research_agent.paths import build_fingerprint

    return build_fingerprint()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default="runtime_data/power-ladder")
    args = parser.parse_args()
    print(json.dumps(probe(ROOT, args.project), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

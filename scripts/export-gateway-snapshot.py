"""Export a static model-gateway snapshot for the workbench.

Mirrors the runtime GET /api/models response (providers with key-presence
status only, profiles, module bindings, wiring notes, security statement)
into research_agent/web/data/gateway.json. Never writes key values; the
workbench uses this offline snapshot when the local runtime is not running.

Usage:
    python scripts/export-gateway-snapshot.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_agent.models import GatewayStore, ModelRegistryService  # noqa: E402

OUT = ROOT / "research_agent" / "web" / "data" / "gateway.json"


def main() -> int:
    store_path = ROOT / "research_agent" / "web" / "data" / "model_gateway.json"
    store = GatewayStore(store_path if store_path.is_file() else None)
    service = ModelRegistryService(store)
    snapshot = service.snapshot()
    snapshot["static"] = True
    snapshot["api_connected"] = False
    snapshot["source"] = "scripts/export-gateway-snapshot.py（离线快照；启动本地 runtime 后前端可探测 /api/models 实时状态）"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(str(OUT), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(snapshot, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    providers = ", ".join("%s(%s)" % (item["provider_id"], "key✓" if item["configured"] else "key—") for item in snapshot["providers"])
    print("wrote %s" % OUT)
    print("providers: " + providers)
    print("bindings: " + json.dumps(snapshot["bindings"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Live literature + real ChemLab experiment through the Qoder MCP server.

Reproduction/protocol validation only. The claim remains a draft; no human
signature is fabricated. The literature fetch is real arXiv PDF acquisition.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for entry in (str(ROOT), str(SCRIPTS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from research_mcp_demo import MCPClient


QUERY = "machine learning molecular fingerprints chemical reaction prediction"
GOAL = "Reproduce a Morgan-fingerprint Ridge baseline for chemical reaction conversion prediction."


def json_artifact(client, project, run_id, name):
    try:
        text = client.call(
            "research_read_artifact",
            {"project_dir": project, "run_id": run_id, "path": name, "max_chars": 200000},
        ).get("text") or ""
    except RuntimeError as exc:
        if "artifact not found" in str(exc):
            return None
        raise
    try:
        return json.loads(text)
    except ValueError:
        return None


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = ROOT / "runtime_data" / "qoder-live-experiment" / stamp
    project = "runtime_data/qoder-live-experiment/%s/project" % stamp
    base.mkdir(parents=True, exist_ok=True)
    client = MCPClient(ROOT, {"RESEARCH_AGENT_MODE": "test", "RESEARCH_AGENT_MODEL_STORE": str(base / "model_gateway.json")})
    summary = {
        "schema_version": "qoder-live-experiment-0.1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": QUERY,
        "goal": GOAL,
        "project": project,
        "checks": [],
        "boundary": "reproduction/protocol validation; real ChemLab data; claim is a draft, not signed",
    }

    def check(name, ok, detail=""):
        summary["checks"].append({"name": name, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            raise AssertionError("%s: %s" % (name, detail))

    try:
        client.request("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "qoder-live-experiment", "version": "0.1"}, "capabilities": {}})
        client.notify("notifications/initialized")
        created = client.call("research_project_init", {"project_dir": project, "name": "Qoder Live Experiment"})
        check("project.init", created.get("created") is True)
        fetch = client.call(
            "research_literature_fetch",
            {"project_dir": project, "query": QUERY, "max_results": 4, "allow_network": True},
        )
        check("fetch.downloaded", len(fetch.get("downloaded") or []) >= 3, str(len(fetch.get("downloaded") or [])))
        summary["downloaded"] = [
            {"arxiv_id": item.get("arxiv_id"), "title": item.get("title"), "pdf": item.get("pdf")}
            for item in (fetch.get("downloaded") or [])
        ]

        run = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": GOAL,
                "task_type": "experiment_validation",
                "source": "local",
                "max_sources": 4,
                "language": "en",
                "venue_type": "en_conference",
                "flow_mode": "review",
                "run_dataset": "chemlab",
                "run_seeds": 3,
            },
        )
        summary["run"] = {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "route": run.get("route"),
            "stopped_at": run.get("stopped_at"),
            "fixture_mode": run.get("fixture_mode"),
            "artifacts": run.get("artifacts") or [],
            "run_dir": run.get("run_dir"),
        }
        run_dir = Path(run.get("run_dir") or "")
        literature = json_artifact(client, project, run.get("run_id"), "literature-ledger.json") or {}
        experiment = json_artifact(client, project, run.get("run_id"), "experiment.json") or {}
        claim_draft = json_artifact(client, project, run.get("run_id"), "run/claim-draft.json")
        summary["literature"] = {
            "sources": len(literature.get("sources") or []),
            "counts": literature.get("counts") or {},
        }
        summary["experiment"] = {
            "status": experiment.get("status"),
            "baseline": experiment.get("baseline"),
            "primary_metric": experiment.get("primary_metric"),
            "seeds": experiment.get("seeds"),
        }
        summary["claim_draft"] = {
            "status": (claim_draft or {}).get("status"),
            "statement": (claim_draft or {}).get("statement"),
            "capsule": (claim_draft or {}).get("capsule"),
            "ea": (claim_draft or {}).get("ea"),
        }
        summary["checks"].append(
            {"name": "run.status", "status": "pass" if run.get("status") in ("completed", "needs_human") else "fail", "detail": str(run.get("status"))}
        )
        summary["checks"].append(
            {"name": "experiment.chemLab", "status": "pass" if experiment.get("primary_metric") == "delta_r2" else "fail", "detail": str(experiment.get("primary_metric"))}
        )
        summary["checks"].append(
            {"name": "claim.draft_only", "status": "pass" if (claim_draft or {}).get("status") == "draft_needs_human" else "fail", "detail": str((claim_draft or {}).get("status"))}
        )
        for name in ("run/run-capsule.json", "run/ea.json", "run/metrics.json", "run/claim-draft.json", "paper.md", "manuscript.md"):
            if (run_dir / name).is_file():
                summary.setdefault("artifacts", {})[name] = str(run_dir / name)
        summary["artifacts"]["run_dir"] = str(run_dir)
        summary["artifacts"]["literature_ledger"] = str(run_dir / "literature-ledger.json")
        summary["result"] = "pass" if all(item["status"] == "pass" for item in summary["checks"]) else "fail"
    finally:
        client.close()

    (base / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Qoder Live Experiment",
        "",
        "- Query: `%s`" % QUERY,
        "- Goal: %s" % GOAL,
        "- Project: `%s`" % project,
        "- Result: `%s`" % summary.get("result"),
        "",
        "## Evidence",
        "",
        "- literature sources: %s" % summary.get("literature", {}).get("sources"),
        "- full text: %s" % (summary.get("literature", {}).get("counts") or {}).get("included_full_text"),
        "- experiment baseline/metric: `%s` / `%s`"
        % (summary.get("experiment", {}).get("baseline"), summary.get("experiment", {}).get("primary_metric")),
        "- claim draft: `%s`" % summary.get("claim_draft", {}).get("status"),
        "",
        "## Artifacts",
        "",
    ]
    for key, value in sorted((summary.get("artifacts") or {}).items()):
        lines.append("- %s: `%s`" % (key, value))
    lines += [
        "",
        "## Human next step",
        "",
        "Inspect RunCapsule/EA, then sign the claim with `python -m research_agent run claim ...`; this demo deliberately did not sign it.",
        "",
        "Boundary: ChemLab is a public protocol-validation dataset; this is a reproduction, not a novel scientific claim or a paper-ready result.",
        "",
    ]
    (base / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"result": summary.get("result"), "summary": str(base / "summary.md"), "project": summary.get("artifacts", {}).get("run_dir")}, ensure_ascii=False, indent=2))
    return 0 if summary.get("result") == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

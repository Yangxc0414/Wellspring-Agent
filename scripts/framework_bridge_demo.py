"""Prove a non-MCP framework can call the research agent over HTTP JSON.

Starts an isolated local runtime, uses ResearchAgentClient (the same client a
LangGraph/CrewAI/AutoGen wrapper would use), runs a fixture literature review
through the HTTP tool bridge, and saves the transcript.
"""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.client import ResearchAgentClient


def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def main() -> int:
    output = ROOT / "runtime_data" / "integrations" / "framework-bridge-demo"
    output.mkdir(parents=True, exist_ok=True)
    jobs_root = output / "jobs"
    project = "runtime_data/integrations/framework-demo-project"
    token = "framework-demo-token"
    port = free_port()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["RESEARCH_AGENT_API_TOKEN"] = token
    env["RESEARCH_AGENT_API_ROOT"] = str(ROOT)
    env["RESEARCH_AGENT_MODE"] = "test"
    log_path = output / "runtime-stderr.log"
    log = open(str(log_path), "w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "research_agent.runtime",
            "--port", str(port), "--jobs-root", str(jobs_root),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=log,
    )
    client = ResearchAgentClient("http://127.0.0.1:%d" % port, token=token, timeout=180)
    summary = {
        "schema_version": "framework-bridge-demo-0.1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": client.base_url,
        "project": project,
        "token_used": True,
        "calls": [],
    }
    try:
        for _ in range(80):
            try:
                health = client.health()
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("runtime did not become healthy; see " + str(log_path))
        summary["health"] = health
        capabilities = client.capabilities()
        summary["capability_count"] = len(capabilities.get("tools") or [])
        summary["openai_tool_count"] = len(capabilities.get("openai_tools") or [])
        summary["calls"].append("GET /api/research/capabilities")

        created = client.init_project(project, "Framework Bridge Demo")
        summary["project_created"] = created.get("created")
        summary["calls"].append("research_project_init")

        plan = client.plan(
            project_dir=project,
            goal="钙钛矿界面钝化 湿热稳定性 文献综述",
            task_type="literature_review",
            source="fixture",
            max_sources=3,
            language="zh",
            flow_mode="review",
        )
        summary["planned_route"] = (plan.get("plan") or {}).get("route")
        summary["calls"].append("research_plan")

        run = client.run(
            project_dir=project,
            goal="钙钛矿界面钝化 湿热稳定性 文献综述",
            task_type="literature_review",
            source="fixture",
            max_sources=3,
            language="zh",
            flow_mode="review",
        )
        summary["run"] = {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "route": run.get("route"),
            "stopped_at": run.get("stopped_at"),
            "run_dir": run.get("run_dir"),
            "artifacts": run.get("artifacts") or [],
            "fixture_mode": run.get("fixture_mode"),
        }
        summary["calls"].append("research_run")

        status = client.status(project, limit=5)
        summary["status_runs"] = len(status.get("runs") or [])
        summary["calls"].append("research_status")

        read = client.call_tool(
            "research_read_artifact",
            {
                "project_dir": project,
                "run_id": run.get("run_id"),
                "path": "task-report.md",
                "max_chars": 2000,
            },
        )
        summary["report_excerpt"] = str(read.get("text") or "")[:1000]
        summary["calls"].append("research_read_artifact")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()

    summary["boundary"] = (
        "HTTP JSON adapter uses the same 11 tools as MCP; it stops at human gates and "
        "does not expose sign/approve/freeze/publish"
    )
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Framework Bridge Demo",
        "",
        "- base_url: `%s`" % summary["base_url"],
        "- tools: %s / OpenAI schemas: %s" % (
            summary.get("capability_count"), summary.get("openai_tool_count")
        ),
        "- project: `%s`" % project,
        "- planned route: `%s`" % summary.get("planned_route"),
        "- run: `%s` status=`%s` stopped_at=`%s`" % (
            (summary.get("run") or {}).get("run_id"),
            (summary.get("run") or {}).get("status"),
            (summary.get("run") or {}).get("stopped_at") or "-",
        ),
        "- calls: %s" % " → ".join(summary["calls"]),
        "- report: `%s`" % (
            (summary.get("run") or {}).get("run_dir", "") + "/task-report.md"
        ),
        "",
        "This is the same `ResearchAgentClient` a LangGraph/CrewAI/AutoGen adapter would use.",
        "Fixture output is workflow-only and not citable evidence.",
        "",
    ]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nSaved:", output / "summary.json")
    return 0 if (summary.get("run") or {}).get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

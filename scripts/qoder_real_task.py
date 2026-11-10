"""Run a real CC-BY literature task through the Qoder MCP server.

The task uses the frozen 4-paper real corpus (not fixture), stops at G1,
performs a human-style G1 decision via the CLI, resumes to S4, and captures
every stage artifact in one new project directory.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for entry in (str(ROOT), str(SCRIPTS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from research_mcp_demo import MCPClient


GOAL = "基于 4 篇 CC-BY 全文，分析自改进智能体的证据、评测与失败归因缺口，提出可证伪假设与实验设计。"


def read_json_artifact(client, project, run_id, name):
    try:
        response = client.call(
            "research_read_artifact",
            {"project_dir": project, "run_id": run_id, "path": name, "max_chars": 120000},
        )
    except RuntimeError as exc:
        if "artifact not found" in str(exc):
            return None
        raise
    text = response.get("text") or ""
    try:
        return json.loads(text)
    except ValueError:
        return None


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = ROOT / "runtime_data" / "qoder-real-task" / stamp
    project = "runtime_data/qoder-real-task/%s/project" % stamp
    base.mkdir(parents=True, exist_ok=True)
    env = {
        "RESEARCH_AGENT_MODE": "test",
        "RESEARCH_AGENT_MODEL_STORE": str(base / "model_gateway.json"),
    }
    client = MCPClient(ROOT, env)
    summary = {
        "schema_version": "qoder-real-task-0.1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "goal": GOAL,
        "source": "real (frozen CC-BY corpus)",
        "project": project,
        "stages": [],
        "artifacts": {},
        "boundary": "real literature text, frozen CC-BY corpus; no claim/closure signature, no fabricated run",
    }
    try:
        client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "qoder-real-task", "version": "0.1"},
                "capabilities": {},
            },
        )
        client.notify("notifications/initialized")
        tools = client.request("tools/list").get("tools", [])
        summary["tools"] = len(tools)

        created = client.call("research_project_init", {"project_dir": project, "name": "Qoder Real Task"})
        project_path = Path(created.get("path") or "")
        summary["project_path"] = str(project_path)
        (base / "README.md").write_text(
            "# Qoder Real Task\n\n"
            "Build: `python scripts/qoder_real_task.py`\n\n"
            "Source: frozen real CC-BY corpus (4 papers), not fixture.\n\n"
            "This run stops at G1; a CLI G1 decision is recorded, then the strict\n"
            "full_research run resumes and stops at G2. No claim or closure was signed.\n",
            encoding="utf-8",
        )

        plan = client.call(
            "research_plan",
            {
                "project_dir": project,
                "goal": GOAL,
                "task_type": "full_research",
                "source": "real",
                "max_sources": 4,
                "language": "zh",
                "venue_type": "zh_core_journal",
                "flow_mode": "strict",
            },
        )
        summary["plan"] = plan.get("plan") or {}
        summary["stages"].append({"stage": "plan", "status": "completed"})

        first = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": GOAL,
                "task_type": "full_research",
                "source": "real",
                "max_sources": 4,
                "language": "zh",
                "venue_type": "zh_core_journal",
                "flow_mode": "strict",
            },
        )
        first_id = first.get("run_id")
        first_dir = Path(first.get("run_dir") or "")
        summary["first_run"] = {
            "run_id": first_id,
            "status": first.get("status"),
            "route": first.get("route"),
            "stopped_at": first.get("stopped_at"),
            "fixture_mode": first.get("fixture_mode"),
            "artifacts": first.get("artifacts") or [],
            "run_dir": str(first_dir),
        }
        summary["stages"].append(
            {"stage": "S1+S2-S3+S4(partial)", "status": first.get("status"), "stopped_at": first.get("stopped_at")}
        )
        ledger = read_json_artifact(client, project, first_id, "literature-ledger.json") or {}
        idea = read_json_artifact(client, project, first_id, "idea.json") or {}
        design = read_json_artifact(client, project, first_id, "experiment.json") or {}
        design_audit = read_json_artifact(client, project, first_id, "design-audit.json") or {}
        task = read_json_artifact(client, project, first_id, "task.json") or {}
        counts = ledger.get("counts") if isinstance(ledger.get("counts"), dict) else {}
        summary["literature"] = {
            "sources": len(ledger.get("sources") or []),
            "counts": counts,
            "coverage": ledger.get("coverage") or {},
            "source_scope": ledger.get("source_scope") or [],
        }
        summary["ideas"] = [
            {"idea_id": item.get("idea_id"), "title": item.get("title")}
            for item in (idea.get("candidates") or [])
        ]
        summary["design_status"] = design.get("status")
        summary["design_audit"] = design_audit.get("status")
        summary["first_gates"] = [
            {"gate": g.get("gate"), "status": g.get("status")}
            for g in (task.get("gates") or [])
        ]
        summary["artifacts"]["stage1"] = str(first_dir)
        for name, key in (
            ("literature-ledger.json", "literature_ledger"),
            ("idea-review.json", "idea_review"),
            ("design-audit.json", "design_audit"),
        ):
            path = first_dir / name
            if path.is_file():
                summary["artifacts"][key] = str(path)

        candidate = (idea.get("candidates") or [None])[0]
        if not candidate:
            raise RuntimeError("real task produced no idea candidate")
        g1_path = first_dir / "g1-decision.json"
        cli = subprocess.run(
            [
                sys.executable, "-m", "research_agent", "flow", "g1",
                "--idea-file", str(first_dir / "idea.json"),
                "--idea-id", str(candidate.get("idea_id")),
                "--human-reason", "Qoder real-task demo selection; human gate simulation",
                "--output-dir", str(first_dir),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        if cli.returncode != 0 or not g1_path.is_file():
            raise RuntimeError("G1 CLI failed: " + (cli.stderr or cli.stdout))
        summary["stages"].append({"stage": "G1 decision", "status": "completed", "file": str(g1_path)})

        resumed = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": GOAL,
                "task_type": "full_research",
                "source": "real",
                "max_sources": 4,
                "language": "zh",
                "venue_type": "zh_core_journal",
                "flow_mode": "strict",
                "g1_decision_file": "runs/%s/g1-decision.json" % first_id,
            },
        )
        resumed_id = resumed.get("run_id")
        resumed_dir = Path(resumed.get("run_dir") or "")
        summary["resumed_run"] = {
            "run_id": resumed_id,
            "status": resumed.get("status"),
            "route": resumed.get("route"),
            "stopped_at": resumed.get("stopped_at"),
            "fixture_mode": resumed.get("fixture_mode"),
            "artifacts": resumed.get("artifacts") or [],
            "run_dir": str(resumed_dir),
        }
        summary["stages"].append(
            {"stage": "S4 design", "status": resumed.get("status"), "stopped_at": resumed.get("stopped_at")}
        )
        resumed_design = read_json_artifact(client, project, resumed_id, "experiment.json") or {}
        resumed_audit = read_json_artifact(client, project, resumed_id, "design-audit.json") or {}
        summary["resumed_design_status"] = resumed_design.get("status")
        summary["resumed_design_audit"] = resumed_audit.get("status")
        summary["artifacts"]["stage2"] = str(resumed_dir)
        for name, key in (
            ("experiment.json", "resumed_experiment"),
            ("idea-review.json", "resumed_idea_review"),
            ("design-audit.json", "resumed_design_audit"),
        ):
            path = resumed_dir / name
            if path.is_file():
                summary["artifacts"][key] = str(path)
        actions = client.call("research_next_actions", {"project_dir": project, "run_id": resumed_id})
        summary["next_actions"] = actions.get("next_actions") or []
    finally:
        client.close()

    summary["result"] = (
        "pass"
        if summary.get("first_run", {}).get("stopped_at") == "G1"
        and summary.get("resumed_run", {}).get("stopped_at") == "G2"
        and not summary.get("first_run", {}).get("fixture_mode")
        else "fail"
    )
    (base / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Qoder Real Task",
        "",
        "- Goal: " + GOAL,
        "- Source: frozen **real CC-BY** corpus (4 papers), fixture_mode=`%s`"
        % summary.get("first_run", {}).get("fixture_mode"),
        "- Project: `%s`" % project,
        "- Result: `%s`" % summary["result"],
        "",
        "## Stage artifacts",
        "",
    ]
    for key, value in sorted(summary.get("artifacts", {}).items()):
        lines.append("- %s: `%s`" % (key, value))
    lines += [
        "",
        "## Runs",
        "",
        "- strict first run: `%s` status=%s stopped_at=%s"
        % (
            summary.get("first_run", {}).get("run_id"),
            summary.get("first_run", {}).get("status"),
            summary.get("first_run", {}).get("stopped_at"),
        ),
        "- G1 decision: `g1-decision.json` created by CLI",
        "- resumed run: `%s` status=%s stopped_at=%s"
        % (
            summary.get("resumed_run", {}).get("run_id"),
            summary.get("resumed_run", {}).get("status"),
            summary.get("resumed_run", {}).get("stopped_at"),
        ),
        "",
        "## Ideas",
        "",
    ]
    for idea in summary.get("ideas", []):
        lines.append("- `%s` %s" % (idea.get("idea_id"), idea.get("title")))
    lines += [
        "",
        "## Boundary",
        "",
        "Real full text from the frozen CC-BY corpus; this is not a claim, not a signed result, and not a publication. G2 protocol freeze / S5 run / claim are still human actions.",
        "",
    ]
    (base / "stage-report.md").write_text("\n".join(lines), encoding="utf-8")

    index_lines = [
        "# Artifact Index",
        "",
        "## Project",
        "",
        "- `%s`" % project,
        "- source: real CC-BY corpus (4 papers), fixture_mode=false",
        "",
    ]
    for label, run in (
        ("Stage 1 / G1 run", summary.get("first_run") or {}),
        ("Stage 2 / G2 run", summary.get("resumed_run") or {}),
    ):
        run_dir = Path(run.get("run_dir") or "")
        index_lines += [
            "## " + label,
            "",
            "- run_id: `%s`" % run.get("run_id"),
            "- status: `%s` stopped_at: `%s`" % (run.get("status"), run.get("stopped_at") or "-"),
            "",
            "| File | Bytes |",
            "| --- | ---: |",
        ]
        for path in sorted(run_dir.glob("*")):
            if path.is_file():
                index_lines.append("| `%s` | %d |" % (path.name, path.stat().st_size))
        index_lines.append("")
    index_lines += [
        "## Human next action",
        "",
    ]
    for action in summary.get("next_actions") or []:
        if action.get("kind") == "human_gate":
            index_lines += [
                "- gate: `%s`" % action.get("gate"),
                "- %s" % action.get("message"),
                "",
                "```bash",
                str(action.get("cli") or ""),
                "```",
                "",
            ]
    index_lines += [
        "## Boundary",
        "",
        "Real CC-BY full text; no Claim/EA/Closure signature; design is incomplete until baseline/metric/budget are supplied and G2 is frozen by a human.",
        "",
    ]
    (base / "artifact-index.md").write_text("\n".join(index_lines), encoding="utf-8")
    print(json.dumps({
        "result": summary["result"],
        "stage_report": str(base / "stage-report.md"),
        "artifact_index": str(base / "artifact-index.md"),
        "project": summary.get("project_path"),
    }, ensure_ascii=False, indent=2))
    return 0 if summary["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

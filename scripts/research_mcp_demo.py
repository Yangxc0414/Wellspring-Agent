"""Drive the research-agent MCP server over stdio and save a demo transcript.

Usage:
    python scripts/research_mcp_demo.py --project runtime_data/integrations/mcp-demo-project
"""

import argparse
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class MCPClient:
    def __init__(self, root: Path, env_overrides=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["RESEARCH_AGENT_MCP_ROOT"] = str(root)
        env.update(env_overrides or {})
        self.stderr_lines = []
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "scripts" / "research_mcp_server.py"),
                "--root",
                str(root),
            ],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.next_id = 1
        self.transcript = []
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self):
        assert self.proc.stderr is not None
        for raw in iter(self.proc.stderr.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self.stderr_lines.append(line)

    def _send(self, payload):
        assert self.proc.stdin is not None
        self.proc.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def request(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)
        assert self.proc.stdout is not None
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("MCP server closed stdout; stderr:\n" + "\n".join(self.stderr_lines[-20:]))
        response = json.loads(line.decode("utf-8"))
        self.transcript.append({"request": payload, "response": response})
        if "error" in response:
            raise RuntimeError("MCP error: %s" % response["error"])
        return response["result"]

    def notify(self, method, params=None):
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)
        self.transcript.append({"request": payload, "response": None})

    def call(self, name, arguments):
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError((result.get("structuredContent") or {}).get("error", "tool failed"))
        return result.get("structuredContent") or {}

    def close(self):
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()
        self._stderr_thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--project", default="runtime_data/integrations/mcp-demo-project")
    parser.add_argument("--output", default="runtime_data/integrations/mcp-demo")
    parser.add_argument("--source", default="fixture")
    parser.add_argument("--max-sources", type=int, default=6)
    args = parser.parse_args()

    root = Path(args.root).resolve()
    project = args.project
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    skill_demo = output / "skill-demo"
    skill_demo.mkdir(parents=True, exist_ok=True)
    skill_registry = skill_demo / "skills.json"
    skill_usage = skill_demo / "usage.json"

    from research_agent.skill_registry import SkillRegistryStore, manifest_from_payload

    registry = SkillRegistryStore(skill_registry)
    demo_manifest, _ = registry.register(
        manifest_from_payload(
            {
                "name": "demo-evidence-check",
                "description": "Use when a draft needs an evidence checklist.",
                "instructions": "Check every result sentence against a locatable source span.",
                "version": "0.1.0",
                "license": "MIT",
                "source": "imported",
                "enabled": False,
            }
        )
    )
    registry.set_enabled(demo_manifest["id"], True)

    client = MCPClient(
        root,
        {
            "RESEARCH_AGENT_SKILL_REGISTRY": str(skill_registry),
            "RESEARCH_AGENT_SKILL_USAGE": str(skill_usage),
        },
    )
    summary = {
        "schema_version": "mcp-integration-demo-0.1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "project_dir": project,
        "client": "",
        "server": "",
        "tools": [],
        "runs": [],
        "transcript": "",
        "stderr": "",
        "boundary": (
            "MCP never signs claims, freezes protocols or approves closure/export; "
            "distillation creates a disabled candidate and does not execute scripts; "
            "manuscript revision is project-bounded and never reports submission_ready=true"
        ),
    }
    try:
        init = client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "research-agent-demo-client", "version": "0.1.0"},
                "capabilities": {},
            },
        )
        summary["server"] = init.get("serverInfo", {})
        summary["protocol"] = init.get("protocolVersion", "")
        client.notify("notifications/initialized")
        tools = client.request("tools/list").get("tools", [])
        summary["tools"] = [item.get("name") for item in tools]

        before = client.call("research_skill_list", {})
        summary["skill_list_before"] = before
        distilled = client.call(
            "research_skill_distill",
            {
                "skill_id": demo_manifest["id"],
                "project_dir": project,
                "human_reason": "Demo: keep the evidence checklist for local reuse",
            },
        )
        summary["skill_distill"] = {
            "created": distilled.get("created"),
            "candidate": distilled.get("candidate"),
            "path": distilled.get("path"),
            "boundary": distilled.get("boundary"),
        }
        summary["skill_list_after"] = client.call("research_skill_list", {})

        created = client.call(
            "research_project_init",
            {"project_dir": project, "name": "MCP Integration Demo"},
        )
        summary["project_created"] = created.get("created")
        summary["project_path"] = created.get("path")

        project_root = Path(created.get("path") or "")
        revision_input = project_root / "notes" / "manuscript-demo"
        revision_input.mkdir(parents=True, exist_ok=True)
        (revision_input / "paper.md").write_text(
            "# Demo manuscript revision\n\n"
            "## 结果\n\n方法 A 的平均准确率为 0.9000，引用 [1]。\n\n"
            "## 参考文献\n\n[1] Demo reference.\n",
            encoding="utf-8",
        )
        (revision_input / "data.csv").write_text(
            "method,accuracy\nA,0.90\nA,0.92\n", encoding="utf-8"
        )
        (revision_input / "metrics.json").write_text(
            json.dumps(
                {"metrics": [
                    {"name": "mean_a", "table": "data", "column": "accuracy",
                     "op": "mean", "digits": 4, "replace": "0.9000"}
                ]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        revision = client.call(
            "research_manuscript_revise",
            {
                "project_dir": project,
                "draft": "notes/manuscript-demo/paper.md",
                "data": ["notes/manuscript-demo/data.csv"],
                "metrics_file": "notes/manuscript-demo/metrics.json",
                "formats": ["md", "docx"],
            },
        )
        summary["manuscript_revision"] = {
            "status": revision.get("status"),
            "writer_mode": revision.get("writer_mode"),
            "output_dir": revision.get("output_dir"),
            "export": (revision.get("files") or {}).get("export"),
        }
        templates = client.call("research_figure_templates", {})
        figure_name = "framework-demo-" + datetime.now(timezone.utc).strftime("%H%M%S")
        figure = client.call(
            "research_figure_render",
            {
                "project_dir": project,
                "template_id": "framework-example",
                "name": figure_name,
                "title": "AstraDraw Framework Demo",
                "description": "Bundled AstraDraw scene rendered through the research-agent MCP.",
                "formats": ["svg", "png"],
            },
        )
        summary["figure"] = {
            "template_count": len(templates.get("templates") or []),
            "figure_id": figure.get("figure_id"),
            "output_dir": figure.get("output_dir"),
            "files": figure.get("files"),
            "audit_status": figure.get("audit_status"),
        }

        plan = client.call(
            "research_plan",
            {
                "project_dir": project,
                "goal": "钙钛矿界面钝化 湿热稳定性 文献综述",
                "task_type": "literature_review",
                "source": args.source,
                "max_sources": args.max_sources,
                "language": "zh",
            },
        )
        summary["planned_route"] = (plan.get("plan") or {}).get("route", "")

        first = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": "钙钛矿界面钝化 湿热稳定性 文献综述",
                "task_type": "literature_review",
                "source": args.source,
                "max_sources": args.max_sources,
                "language": "zh",
                "flow_mode": "review",
            },
        )
        summary["runs"].append(
            {
                "run_id": first.get("run_id"),
                "status": first.get("status"),
                "route": first.get("route"),
                "stopped_at": first.get("stopped_at"),
                "run_dir": first.get("run_dir"),
                "artifacts": first.get("artifacts", []),
                "warnings": first.get("warnings", []),
                "next_actions": first.get("next_actions", []),
            }
        )

        second = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": "湿热条件下钝化层稳定性 研究假设",
                "task_type": "hypothesis_design",
                "source": args.source,
                "max_sources": args.max_sources,
                "language": "zh",
                "flow_mode": "strict",
            },
        )
        summary["runs"].append(
            {
                "run_id": second.get("run_id"),
                "status": second.get("status"),
                "route": second.get("route"),
                "stopped_at": second.get("stopped_at"),
                "run_dir": second.get("run_dir"),
                "artifacts": second.get("artifacts", []),
                "warnings": second.get("warnings", []),
                "next_actions": second.get("next_actions", []),
            }
        )

        status = client.call("research_status", {"project_dir": project, "limit": 10})
        summary["status_runs"] = status.get("runs", [])

        run_id = first.get("run_id")
        listed = client.call(
            "research_list_artifacts",
            {"project_dir": project, "run_id": run_id},
        )
        summary["artifact_count"] = len(listed.get("artifacts", []))

        report = client.call(
            "research_read_artifact",
            {
                "project_dir": project,
                "run_id": run_id,
                "path": "task-report.md",
                "max_chars": 4000,
            },
        )
        summary["report_excerpt"] = report.get("text", "")[:2000]

        pack = client.call(
            "research_writing_pack",
            {
                "project_dir": project,
                "run_id": run_id,
                "language": "zh",
                "max_sources": args.max_sources,
                "max_spans_per_source": 2,
            },
        )
        summary["writing_pack"] = {
            "token_estimate": pack.get("token_estimate"),
            "references": len((pack.get("literature") or {}).get("references") or []),
            "claim_status": (pack.get("claim") or {}).get("status"),
            "files": pack.get("files"),
        }
        drafts = project_root / "drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        (drafts / "demo-review.md").write_text(
            "# Demo review\n\n## 摘要\n\n本文综述钝化稳定性 %s。\n\n## 引言\n\n稳定性是关键 %s。\n\n"
            "## 相关工作\n\n已有多种策略 %s。\n\n## 方法\n\n本文比较已报道设置 %s。\n\n"
            "## 实验\n\n本文比较文献中的实验设置 %s。\n\n## 结果\n\n文献结果显示钝化改善稳定性 %s。\n\n"
            "## 讨论\n\n不同来源仍有差异 %s。\n\n## 结论\n\n需要统一评价协议 %s。\n\n"
            "## 参考文献\n\n[REF-01] Demo reference. %s\n" % (("[REF-01]",) * 9),
            encoding="utf-8",
        )
        audit = client.call(
            "research_manuscript_audit",
            {"project_dir": project, "run_id": run_id, "draft": "drafts/demo-review.md"},
        )
        summary["writing_audit"] = {
            "status": audit.get("status"),
            "submission_ready": audit.get("submission_ready"),
            "blockers": audit.get("blockers"),
            "warnings": audit.get("warnings"),
        }
    finally:
        client.close()

    transcript_path = output / "transcript.json"
    stderr_path = output / "stderr.log"
    summary["transcript"] = str(transcript_path)
    summary["stderr"] = str(stderr_path)
    summary_path = output / "summary.json"
    transcript_path.write_text(
        json.dumps(client.transcript, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    stderr_path.write_text("\n".join(client.stderr_lines), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown = [
        "# Research-Agent MCP 接入演示",
        "",
        "- protocol: `%s`" % summary.get("protocol", ""),
        "- project: `%s`" % summary.get("project_path", ""),
        "- transcript: `transcript.json`",
        "- stderr: `stderr.log`",
        "- tools: %s" % ", ".join("`%s`" % name for name in summary["tools"]),
        "",
        "| Run | Route | Status | Stopped | Artifacts |",
        "| --- | --- | --- | --- | --- |",
    ]
    for run in summary["runs"]:
        markdown.append(
            "| `%s` | %s | `%s` | %s | %s |"
            % (
                run.get("run_id", ""),
                run.get("route", ""),
                run.get("status", ""),
                run.get("stopped_at") or "-",
                ", ".join("`%s`" % item for item in run.get("artifacts", [])),
            )
        )
    markdown += [
        "",
        "## AstraDraw Figure",
        "",
        "- templates: %s" % (summary.get("figure") or {}).get("template_count"),
        "- figure: `%s`" % (summary.get("figure") or {}).get("figure_id"),
        "- output: `%s`" % (summary.get("figure") or {}).get("output_dir"),
        "- audit: `%s`" % (summary.get("figure") or {}).get("audit_status"),
        "",
        "## Manuscript Revision",
        "",
        "- status: `%s`" % (summary.get("manuscript_revision") or {}).get("status"),
        "- writer_mode: `%s`" % (summary.get("manuscript_revision") or {}).get("writer_mode"),
        "- output: `%s`" % (summary.get("manuscript_revision") or {}).get("output_dir"),
        "- export: %s" % ", ".join(
            "`%s`" % value
            for value in (((summary.get("manuscript_revision") or {}).get("export") or {}).values())
        ),
        "",
        "## Writing Pack",
        "",
        "- tokens: %s" % (summary.get("writing_pack") or {}).get("token_estimate"),
        "- references: %s" % (summary.get("writing_pack") or {}).get("references"),
        "- claim: `%s`" % (summary.get("writing_pack") or {}).get("claim_status"),
        "- pack: `%s`" % (((summary.get("writing_pack") or {}).get("files") or {}).get("json")),
        "- audit: `%s` (submission_ready=%s)"
        % (
            (summary.get("writing_audit") or {}).get("status"),
            (summary.get("writing_audit") or {}).get("submission_ready"),
        ),
        "- blockers: %s" % "; ".join((summary.get("writing_audit") or {}).get("blockers") or []),
        "",
        "## External Skill",
        "",
        "- registry: `%s`" % skill_registry,
        "- before: %s skill(s)" % (summary.get("skill_list_before") or {}).get("count", 0),
        "- distilled: `%s` (created=%s, disabled=%s)"
        % (
            (summary.get("skill_distill") or {}).get("path", ""),
            (summary.get("skill_distill") or {}).get("created"),
            not ((summary.get("skill_distill") or {}).get("candidate") or {}).get("enabled", True),
        ),
        "- after: %s skill(s)" % (summary.get("skill_list_after") or {}).get("count", 0),
        "- MCP does not execute external scripts; trusted scripts are local CLI opt-in only.",
        "",
        "Boundary: " + summary["boundary"] + ".",
        "Fixture output is workflow-only and is not citable evidence.",
        "",
    ]
    (output / "summary.md").write_text("\n".join(markdown), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nSaved:", summary_path)
    return 0 if all(run.get("status") not in ("failed",) for run in summary["runs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

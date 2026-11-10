"""End-to-end top-conference research workflow through the MCP server.

Corpus (already fetched) -> local S1 -> writing pack -> innovation review ->
first draft -> rubric review/revision/re-review -> audit -> DOCX/PDF export.

This script requires DEEPSEEK_API_KEY in the environment. It never signs a
claim or claims submission readiness.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = Path(__file__).resolve().parent
for entry in (str(ROOT), str(SCRIPTS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from research_mcp_demo import MCPClient


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="runtime_data/topconf-research-2026")
    parser.add_argument(
        "--goal",
        default="Auditable self-improving LLM research agents: failure experience, role decomposition, memory, and evaluation protocols",
    )
    parser.add_argument("--max-sources", type=int, default=24)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--threshold", type=float, default=7.0)
    parser.add_argument("--draft", default="drafts/topconf-review.zh.md")
    args = parser.parse_args()

    project = args.project
    project_path = (ROOT / project).resolve()
    corpus_manifest = project_path / "inputs" / "conference-corpus.json"
    if not corpus_manifest.is_file():
        raise SystemExit("conference corpus not found: " + str(corpus_manifest))
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY is required for innovation/writing/review loops")
    started = time.time()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = {
        "schema_version": "topconf-article-run-0.1",
        "created_at": stamp,
        "project": project,
        "goal": args.goal,
        "checks": [],
        "boundary": (
            "MCP-driven review/position article. The corpus is a bounded set of arXiv versions "
            "with accepted-venue comments; acceptance is not independently verified. "
            "No claim, EA, gate or signature is created."
        ),
    }

    def check(name, ok, detail=""):
        summary["checks"].append(
            {"name": name, "status": "pass" if ok else "fail", "detail": detail}
        )
        if not ok:
            raise AssertionError("%s: %s" % (name, detail))

    client = MCPClient(
        ROOT,
        {
            "RESEARCH_AGENT_MODE": "test",
            "RESEARCH_AGENT_MODEL_STORE": str(project_path / "model_gateway.json"),
        },
    )
    try:
        client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "topconf-article", "version": "0.1"},
                "capabilities": {},
            },
        )
        client.notify("notifications/initialized")
        tools = [item.get("name") for item in client.request("tools/list").get("tools", [])]
        summary["tool_count"] = len(tools)
        check("mcp.tools", len(tools) == 20, str(len(tools)))

        created = client.call(
            "research_project_init",
            {"project_dir": project, "name": "TopConf Research 2026"},
        )
        summary["project_path"] = created.get("path")

        run = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": args.goal,
                "task_type": "literature_review",
                "source": "local",
                "max_sources": args.max_sources,
                "language": "zh",
                "flow_mode": "review",
            },
        )
        check("s1.completed", run.get("status") == "completed", str(run.get("status")))
        run_id = run.get("run_id")
        summary["run_id"] = run_id
        summary["run_dir"] = run.get("run_dir")
        ledger = json.loads(
            client.call(
                "research_read_artifact",
                {
                    "project_dir": project,
                    "run_id": run_id,
                    "path": "literature-ledger.json",
                    "max_chars": 400000,
                },
            ).get("text")
            or "{}"
        )
        counts = ledger.get("counts") or {}
        summary["corpus"] = {
            "sources": len(ledger.get("sources") or []),
            "counts": counts,
            "source_types": ledger.get("source_types") or {},
        }
        check(
            "s1.full_text",
            int(counts.get("included_full_text") or 0) >= 3,
            str(counts),
        )
        check(
            "s1.span",
            int(counts.get("with_locatable_span") or 0) >= 3,
            str(counts),
        )

        pack = client.call(
            "research_writing_pack",
            {
                "project_dir": project,
                "run_id": run_id,
                "language": "zh",
                "max_sources": min(16, args.max_sources),
                "max_spans_per_source": 3,
            },
        )
        summary["writing_pack"] = {
            "tokens": pack.get("token_estimate"),
            "references": len((pack.get("literature") or {}).get("references") or []),
            "corpus": (pack.get("literature") or {}).get("corpus") or {},
            "files": pack.get("files"),
        }
        check(
            "writing_pack.refs",
            len((pack.get("literature") or {}).get("references") or []) >= 3,
            str(summary["writing_pack"]["references"]),
        )

        synthesis = client.call(
            "research_literature_synthesis",
            {"project_dir": project, "run_id": run_id, "max_themes": 7},
        )
        summary["synthesis"] = {
            "source_count": synthesis.get("source_count"),
            "theme_count": synthesis.get("theme_count"),
            "themes": [
                {
                    "theme_id": item.get("theme_id"),
                    "name": item.get("name"),
                    "source_count": item.get("source_count"),
                    "confidence": item.get("confidence"),
                    "tension": item.get("tension"),
                }
                for item in synthesis.get("themes") or []
            ],
            "unused_sources": synthesis.get("unused_sources") or [],
        }
        check("synthesis.multi_source", int(synthesis.get("theme_count") or 0) >= 3)
        (project_path / "synthesis-summary.json").write_text(
            json.dumps(synthesis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        innovation = client.call(
            "research_innovation_review",
            {
                "project_dir": project,
                "run_id": run_id,
                "topic": args.goal,
                "direction": (
                    "以‘可审计自我改进运行时’为统一方向：交互经验带 provenance 进入证据门，"
                    "经过反事实复核与可撤销的能力更新；避免 benchmark A+B 拼接。"
                ),
                "rounds": args.rounds,
                "max_ideas": 5,
                "threshold": args.threshold,
            },
        )
        summary["innovation"] = {
            "status": innovation.get("status"),
            "rounds_completed": innovation.get("rounds_completed"),
            "gaps": innovation.get("gaps") or [],
            "ranking": innovation.get("ranking") or [],
            "score_progression": [
                item.get("overall") for item in innovation.get("iterations") or []
            ],
            "selected": [
                {
                    "idea_id": item.get("idea_id"),
                    "title": item.get("title"),
                    "falsification": item.get("falsification"),
                    "evidence_refs": item.get("evidence_refs"),
                }
                for item in innovation.get("selected_ideas") or []
            ],
        }
        check("innovation.selected", len(innovation.get("selected_ideas") or []) >= 1)
        (project_path / "innovation-summary.json").write_text(
            json.dumps(innovation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        draft = client.call(
            "research_manuscript_draft",
            {
                "project_dir": project,
                "run_id": run_id,
                "output": args.draft,
                "overwrite": True,
            },
        )
        summary["initial_draft"] = {
            "draft": draft.get("draft"),
            "status": draft.get("status"),
            "audit": {
                "status": (draft.get("audit") or {}).get("status"),
                "blockers": (draft.get("audit") or {}).get("blockers"),
                "citation_count": (draft.get("audit") or {}).get("citation_count"),
                "reference_count": (draft.get("audit") or {}).get("reference_count"),
            },
            "repair_attempts": draft.get("repair_attempts"),
        }
        check("draft.generated", draft.get("status") == "generated", str(draft.get("status")))

        review = client.call(
            "research_manuscript_review",
            {
                "project_dir": project,
                "run_id": run_id,
                "draft": args.draft,
                "rounds": args.rounds,
                "threshold": args.threshold,
            },
        )
        summary["review"] = {
            "status": review.get("status"),
            "rounds_completed": review.get("rounds_completed"),
            "accepted_revisions": review.get("accepted_revisions"),
            "score_progression": review.get("score_progression"),
            "best_score": review.get("best_score"),
            "improved": review.get("improved"),
            "baseline_audit": {
                "status": (review.get("baseline_audit") or {}).get("status"),
                "blockers": (review.get("baseline_audit") or {}).get("blockers"),
            },
            "final_audit": {
                "status": (review.get("final_audit") or {}).get("status"),
                "blockers": (review.get("final_audit") or {}).get("blockers"),
                "citation_count": (review.get("final_audit") or {}).get("citation_count"),
            },
            "final_draft": review.get("final_draft"),
            "submission_ready": review.get("submission_ready"),
        }
        check("review.final_audit", (review.get("final_audit") or {}).get("status") == "ready_for_human_review")
        check("review.not_submission_ready", review.get("submission_ready") is False)
        (project_path / "review-summary.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

        final_relative = str(Path(review["final_draft"]).relative_to(project_path)).replace("\\", "/")
        final_audit = client.call(
            "research_manuscript_audit",
            {"project_dir": project, "run_id": run_id, "draft": final_relative},
        )
        summary["final_audit"] = {
            "status": final_audit.get("status"),
            "blockers": final_audit.get("blockers"),
            "warnings": final_audit.get("warnings"),
            "citation_count": final_audit.get("citation_count"),
            "reference_count": final_audit.get("reference_count"),
            "result_number_count": final_audit.get("result_number_count"),
        }

        export = client.call(
            "research_manuscript_revise",
            {
                "project_dir": project,
                "draft": final_relative,
                "venue": "zh_core_journal",
                "formats": ["md", "docx", "pdf"],
            },
        )
        summary["export"] = {
            "status": export.get("status"),
            "output_dir": export.get("output_dir"),
            "files": (export.get("files") or {}).get("export"),
        }
        summary["result"] = "pass"
    except Exception as exc:
        summary["result"] = "fail"
        summary["error"] = "%s: %s" % (type(exc).__name__, exc)
        raise
    finally:
        summary["elapsed_seconds"] = round(time.time() - started, 1)
        client.close()
        (project_path / "run-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    lines = [
        "# Top-Conference Research Run",
        "",
        "- project: `%s`" % project,
        "- run: `%s`" % summary.get("run_id"),
        "- tools: %s" % summary.get("tool_count"),
        "- corpus sources: %s" % (summary.get("corpus") or {}).get("sources"),
        "- full text: %s" % ((summary.get("corpus") or {}).get("counts") or {}).get("included_full_text"),
        "- writing pack refs: %s" % (summary.get("writing_pack") or {}).get("references"),
        "- synthesis themes: %s" % (summary.get("synthesis") or {}).get("theme_count"),
        "- innovation rounds: %s" % (summary.get("innovation") or {}).get("rounds_completed"),
        "- innovation status: `%s`" % (summary.get("innovation") or {}).get("status"),
        "- draft audit: `%s`" % ((summary.get("initial_draft") or {}).get("audit") or {}).get("status"),
        "- review scores: %s" % (summary.get("review") or {}).get("score_progression"),
        "- final audit: `%s`" % ((summary.get("final_audit") or {}).get("status")),
        "- submission_ready: false",
        "- export: `%s`" % ((summary.get("export") or {}).get("files") or {}).get("pdf"),
        "- elapsed: %ss" % summary.get("elapsed_seconds"),
        "",
        "## Innovation ranking",
        "",
    ]
    for row in (summary.get("innovation") or {}).get("ranking") or []:
        lines.append("- %s %.2f %s" % (row.get("idea_id"), row.get("average_score", 0), row.get("title")))
    lines += [
        "",
        "## Boundary",
        "",
        summary["boundary"],
        "",
    ]
    (project_path / "run-summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"result": summary["result"], "summary": str(project_path / "run-summary.md"), "run_id": summary.get("run_id")}, ensure_ascii=False, indent=2))
    return 0 if summary["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

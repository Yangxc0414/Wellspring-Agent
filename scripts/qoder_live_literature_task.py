"""Live Qoder MCP trajectory: arXiv search -> PDF download -> local S1 review."""

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


QUERY = "self-improving agent large language model"
GOAL = "How do self-improving LLM agents use failure trajectories, memory, and context updates?"


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = ROOT / "runtime_data" / "qoder-live-literature" / stamp
    project = "runtime_data/qoder-live-literature/%s/project" % stamp
    base.mkdir(parents=True, exist_ok=True)
    client = MCPClient(ROOT, {"RESEARCH_AGENT_MODE": "test", "RESEARCH_AGENT_MODEL_STORE": str(base / "model_gateway.json")})
    summary = {
        "schema_version": "qoder-live-literature-0.1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": QUERY,
        "goal": GOAL,
        "project": project,
        "checks": [],
        "boundary": "live arXiv PDFs are read only through local PDF parsing; no claim/closure was signed",
    }

    def check(name, ok, detail=""):
        summary["checks"].append({"name": name, "status": "pass" if ok else "fail", "detail": detail})
        if not ok:
            raise AssertionError("%s: %s" % (name, detail))

    try:
        client.request("initialize", {"protocolVersion": "2024-11-05", "clientInfo": {"name": "qoder-live-literature", "version": "0.1"}, "capabilities": {}})
        client.notify("notifications/initialized")
        created = client.call("research_project_init", {"project_dir": project, "name": "Qoder Live Literature"})
        check("project.init", created.get("created") is True)

        fetch = client.call(
            "research_literature_fetch",
            {
                "project_dir": project,
                "query": QUERY,
                "max_results": 4,
                "allow_network": True,
            },
        )
        summary["fetch"] = {
            "found": fetch.get("found"),
            "downloaded": [
                {
                    "arxiv_id": item.get("arxiv_id"),
                    "title": item.get("title"),
                    "pdf": item.get("pdf"),
                    "sha256": item.get("sha256"),
                }
                for item in (fetch.get("downloaded") or [])
            ],
            "skipped": fetch.get("skipped") or [],
        }
        check("fetch.downloaded", len(summary["fetch"]["downloaded"]) == 4, str(len(summary["fetch"]["downloaded"])))

        plan = client.call(
            "research_plan",
            {
                "project_dir": project,
                "goal": GOAL,
                "task_type": "literature_review",
                "source": "local",
                "max_sources": 4,
                "language": "zh",
                "flow_mode": "review",
            },
        )
        check("plan.route", (plan.get("plan") or {}).get("route") == "literature_review")
        run = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": GOAL,
                "task_type": "literature_review",
                "source": "local",
                "max_sources": 4,
                "language": "zh",
                "flow_mode": "review",
            },
        )
        summary["run"] = {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "route": run.get("route"),
            "fixture_mode": run.get("fixture_mode"),
            "artifacts": run.get("artifacts") or [],
            "run_dir": run.get("run_dir"),
        }
        check("run.completed", run.get("status") == "completed", str(run.get("status")))
        check("run.not_fixture", run.get("fixture_mode") is False)
        ledger = json.loads(
            client.call(
                "research_read_artifact",
                {"project_dir": project, "run_id": run.get("run_id"), "path": "literature-ledger.json", "max_chars": 120000},
            ).get("text") or "{}"
        )
        task_payload = json.loads(
            client.call(
                "research_read_artifact",
                {"project_dir": project, "run_id": run.get("run_id"), "path": "task.json", "max_chars": 400000},
            ).get("text") or "{}"
        )
        span_check = next(
            (item for item in (task_payload.get("checks") or []) if item.get("name") == "locatable_spans"),
            {},
        )
        summary["literature"] = {
            "sources": len(ledger.get("sources") or []),
            "counts": ledger.get("counts") or {},
            "coverage": ledger.get("coverage") or {},
            "spans": span_check.get("detail") or "",
        }
        check("s1.full_text", int((ledger.get("counts") or {}).get("included_full_text") or 0) >= 3, str(ledger.get("counts")))
        check("s1.source_is_pdf", int((ledger.get("counts") or {}).get("abstract_only") or 0) == 0, str(ledger.get("counts")))
        check("s1.span_total", "spans" in str(span_check.get("detail") or ""), str(span_check))
        report = client.call(
            "research_read_artifact",
            {"project_dir": project, "run_id": run.get("run_id"), "path": "task-report.md", "max_chars": 12000},
        ).get("text") or ""
        check("report.read", "文献覆盖" in report or "Literature" in report)
        pack = client.call(
            "research_writing_pack",
            {
                "project_dir": project,
                "run_id": run.get("run_id"),
                "language": "zh",
                "max_sources": 4,
                "max_spans_per_source": 4,
            },
        )
        references = (pack.get("literature") or {}).get("references") or []
        check("writing.references", len(references) >= 3, str(len(references)))
        check("writing.no_result_numbers", (pack.get("writing_contract") or {}).get("allowed_result_numbers") == [])
        summary["writing"] = {
            "pack": (pack.get("files") or {}).get("json"),
            "tokens": pack.get("token_estimate"),
            "references": [
                {"ref_id": item.get("ref_id"), "title": item.get("title"), "year": item.get("year")}
                for item in references
            ],
            "claim_status": (pack.get("claim") or {}).get("status"),
            "warnings": pack.get("warnings") or [],
        }
        summary["artifacts"] = {
            "project": created.get("path"),
            "run_dir": run.get("run_dir"),
            "ledger": str(Path(run.get("run_dir")) / "literature-ledger.json"),
            "report": str(Path(run.get("run_dir")) / "task-report.md"),
            "writing_pack": summary["writing"].get("pack"),
        }
        summary["result"] = "pass"
    except Exception as exc:
        summary["result"] = "fail"
        summary["error"] = "%s: %s" % (type(exc).__name__, exc)
        raise
    finally:
        client.close()

    (base / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Qoder Live Literature Task",
        "",
        "- Query: `%s`" % QUERY,
        "- Goal: %s" % GOAL,
        "- Project: `%s`" % project,
        "- Result: `%s`" % summary["result"],
        "",
        "## Downloaded arXiv PDFs",
        "",
    ]
    for item in summary["fetch"].get("downloaded", []):
        lines.append("- `%s` [%s](https://arxiv.org/abs/%s)" % (item["arxiv_id"], item["title"], item["arxiv_id"]))
        lines.append("  - PDF: `%s`" % item["pdf"])
    lines += [
        "",
        "## S1",
        "",
        "- sources: %s" % summary.get("literature", {}).get("sources"),
        "- full text: %s" % (summary.get("literature", {}).get("counts") or {}).get("included_full_text"),
        "- spans: %s" % summary.get("literature", {}).get("spans"),
        "- report: `%s`" % summary.get("artifacts", {}).get("report"),
        "",
        "## Writing Pack",
        "",
        "- refs: %s" % len(summary.get("writing", {}).get("references") or []),
        "- tokens: %s" % summary.get("writing", {}).get("tokens"),
        "- claim: %s" % summary.get("writing", {}).get("claim_status"),
        "- pack: `%s`" % summary.get("writing", {}).get("pack"),
        "",
        "Use the writing pack to draft a project-local manuscript, then call `research_manuscript_audit`.",
        "",
        "## Boundary",
        "",
        "Downloaded arXiv PDFs are not evidence by themselves; S1 reads local PDF text and records spans. This task is a literature review, not an experiment, claim or paper.",
        "",
    ]
    (base / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"result": summary["result"], "summary": str(base / "summary.md"), "project": summary.get("artifacts", {}).get("project")}, ensure_ascii=False, indent=2))
    return 0 if summary["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

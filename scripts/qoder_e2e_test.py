"""End-to-end test through the same stdio MCP server Qoder calls.

This intentionally uses the MCP transport, not direct Python functions. It
verifies tool discovery, literature review, strict G1 stop + CLI resume,
writing pack/audit boundaries, manuscript revision, AstraDraw rendering and
path traversal rejection.
"""

import json
import os
import shutil
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


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime_data" / "qoder-e2e" / stamp
    project = "runtime_data/qoder-e2e/%s/project" % stamp
    output.mkdir(parents=True, exist_ok=True)
    env = {
        "RESEARCH_AGENT_MODE": "test",
        "RESEARCH_AGENT_MODEL_STORE": str(output / "model_gateway.json"),
    }
    client = MCPClient(ROOT, env)
    summary = {
        "schema_version": "qoder-e2e-0.1",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "project": project,
        "checks": [],
        "artifacts": {},
        "boundary": "MCP only; no claim/closure signature was created",
    }

    def check(name, passed, detail=""):
        summary["checks"].append({"name": name, "status": "pass" if passed else "fail", "detail": detail})
        if not passed:
            raise AssertionError("%s failed: %s" % (name, detail))

    try:
        client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "qoder-e2e", "version": "0.1"},
                "capabilities": {},
            },
        )
        client.notify("notifications/initialized")
        tools = client.request("tools/list").get("tools", [])
        names = [item.get("name") for item in tools]
        summary["tools"] = names
        # Compare against the dispatch layer's own registry so this check cannot go stale
        # when a tool is added.
        from research_agent.mcp_server import TOOL_NAMES as EXPECTED_TOOLS

        check(
            "tools.count",
            sorted(names) == sorted(EXPECTED_TOOLS),
            "got %d, expected %d; missing %s"
            % (
                len(names),
                len(EXPECTED_TOOLS),
                sorted(set(EXPECTED_TOOLS) - set(names))[:5],
            ),
        )
        check("tools.host_model", "research_model_turns" in names and "research_model_respond" in names)
        check(
            "tools.no_signing_verbs",
            not [
                name
                for name in names
                if any(word in name for word in ("sign", "approve", "freeze", "publish"))
            ],
        )
        check("tools.revision", "research_manuscript_revise" in names)
        check("tools.astradraw", "research_figure_render" in names)
        check("tools.writing", "research_writing_pack" in names and "research_manuscript_audit" in names)
        check("tools.support_panel", "research_support_panel" in names)
        check("tools.support_items", "research_support_items" in names)
        check("tools.support_verdicts", "research_support_verdicts" in names)
        check("tools.section_edit", "research_manuscript_section_edit" in names)
        check("tools.manuscript_bind", "research_manuscript_bind" in names)
        check("tools.skill_instructions", "research_skill_instructions" in names)
        check("tools.bootstrap", "research_bootstrap" in names)
        check("tools.host_contract", "research_host_contract" in names)
        # A plugin host negotiates before it runs anything: with the host serving the model there
        # must be no API-key blocker, and the answer must carry the schema a host can branch on.
        contract = client.call(
            "research_host_contract",
            {"capabilities": ["can_call_tools", "can_serve_model"]},
        )
        body = (
            contract.get("payload")
            if isinstance(contract.get("payload"), dict)
            else contract
        )
        body = body if isinstance(body, dict) else {}
        # the schema pin is deliberate and rides the contract version (host-contract-0.3):
        # bump it together with handoff.py, same discipline as tests/test_handoff
        check(
            "host_contract.no_api_key",
            body.get("schema_version") == "host-contract-0.3" and not body.get("blocked"),
            "schema=%s blocked=%s" % (body.get("schema_version"), body.get("blocked")),
        )
        check(
            "host_contract.human_only",
            len(body.get("human_only_for_every_transport") or []) >= 5,
            "gates=%d" % len(body.get("human_only_for_every_transport") or []),
        )
        check("tools.model_profiles", "research_model_profiles" in names)

        prompts = client.request("prompts/list").get("prompts", [])
        check(
            "prompts.list",
            any(item.get("name") == "start-research" for item in prompts),
            str([item.get("name") for item in prompts]),
        )
        prompt = client.request(
            "prompts/get",
            {
                "name": "start-research",
                "arguments": {
                    "project_dir": project,
                    "goal": "启动科研智能体 E2E",
                    "source": "fixture",
                },
            },
        )
        prompt_text = (
            ((prompt.get("messages") or [{}])[0].get("content") or {}).get("text") or ""
        )
        check(
            "prompts.start_research",
            "research_bootstrap" in prompt_text
            and "reuse=true" in prompt_text
            and "run_now: true" in prompt_text,
            prompt_text[:120],
        )
        review_prompt = client.request(
            "prompts/get",
            {
                "name": "review-draft",
                "arguments": {
                    "project_dir": project,
                    "run_id": "RUN-E2E",
                    "draft": "drafts/e2e-review.md",
                },
            },
        )
        review_text = (
            (
                (review_prompt.get("messages") or [{}])[0].get("content") or {}
            ).get("text")
            or ""
        )
        check(
            "prompts.review_draft",
            "research_manuscript_bind" in review_text
            and "reuse=true" in review_text,
            review_text[:120],
        )
        idea_prompt = client.request(
            "prompts/get",
            {
                "name": "review-idea",
                "arguments": {
                    "project_dir": project,
                    "run_id": "RUN-E2E",
                },
            },
        )
        idea_text = (
            (
                (idea_prompt.get("messages") or [{}])[0].get("content") or {}
            ).get("text")
            or ""
        )
        check(
            "prompts.review_idea",
            "flow g1" in idea_text
            and "novelty_status=unverified" in idea_text,
            idea_text[:120],
        )

        profiles = client.call("research_model_profiles", {})
        check(
            "models.catalog",
            profiles.get("schema_version") == "model-profile-catalog-0.1"
            and isinstance(profiles.get("profiles"), list),
        )
        check(
            "models.no_secrets",
            "api_key" not in json.dumps(profiles).lower()
            and "base_url" not in json.dumps(profiles).lower(),
        )
        check(
            "tools.topconf_review",
            all(
                name in names
                for name in (
                    "research_conference_fetch",
                    "research_literature_synthesis",
                    "research_innovation_review",
                    "research_manuscript_draft",
                    "research_manuscript_review",
                    "research_experiment_codegen",
                )
            ),
        )

        created = client.call("research_project_init", {"project_dir": project, "name": "Qoder E2E"})
        check("project.init", created.get("created") is True)
        project_path = Path(created.get("path") or "")
        check("project.inside_root", str(project_path).startswith(str(ROOT)))

        closure = client.call("research_closure_status", {"project_dir": project})
        inventory = closure.get("inventory") or {}
        check("closure.inventory", closure.get("schema_version") == "closure-status-0.2")
        check("closure.read_only", "never signs" in str(closure.get("boundary") or ""))
        check("closure.profiles", isinstance(inventory.get("canonical_run"), list) and isinstance(inventory.get("local_experiment"), list))

        lineage = client.call(
            "research_lineage_status",
            {"project_dir": project, "experiment_id": "EXP-NOT-YET"},
        )
        check("lineage.missing", lineage.get("status") == "missing")
        check("lineage.read_only", "Nothing is rebuilt" in str(lineage.get("boundary") or ""))

        plan = client.call(
            "research_plan",
            {
                "project_dir": project,
                "goal": "钙钛矿界面钝化 湿热稳定性 文献综述",
                "task_type": "literature_review",
                "source": "fixture",
                "max_sources": 3,
                "language": "zh",
                "flow_mode": "review",
            },
        )
        check("plan.route", (plan.get("plan") or {}).get("route") == "literature_review")

        run = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": "钙钛矿界面钝化 湿热稳定性 文献综述",
                "task_type": "literature_review",
                "source": "fixture",
                "max_sources": 3,
                "language": "zh",
                "flow_mode": "review",
            },
        )
        check("review.status", run.get("status") == "completed", str(run.get("status")))
        check("review.report", "task-report.md" in (run.get("artifacts") or []))
        summary["artifacts"]["review_run"] = run.get("run_dir")
        report = client.call(
            "research_read_artifact",
            {
                "project_dir": project,
                "run_id": run.get("run_id"),
                "path": "task-report.md",
                "max_chars": 4000,
            },
        )
        check("review.read", "任务完成报告" in str(report.get("text") or ""))
        summary["artifacts"]["review_report"] = (run.get("run_dir") or "") + "/task-report.md"

        pack = client.call(
            "research_writing_pack",
            {
                "project_dir": project,
                "run_id": run.get("run_id"),
                "language": "zh",
                "max_sources": 3,
                "max_spans_per_source": 2,
            },
        )
        check("writing.references", len((pack.get("literature") or {}).get("references") or []) > 0)
        check("writing.claim_status", (pack.get("claim") or {}).get("status") == "missing")
        check("writing.pack_file", Path((pack.get("files") or {}).get("json") or "").is_file())
        summary["artifacts"]["writing_pack"] = (pack.get("files") or {}).get("json")

        drafts = project_path / "drafts"
        drafts.mkdir(parents=True, exist_ok=True)
        (drafts / "e2e-review.md").write_text(
            "# E2E 综述草稿\n\n## 摘要\n\n本文综述钝化稳定性 %s。\n\n## 引言\n\n稳定性是关键 %s。\n\n"
            "## 相关工作\n\n已有多种策略 %s。\n\n## 方法\n\n本文比较已报道设置 %s。\n\n"
            "## 实验\n\n本文比较文献中的实验设置 %s。\n\n## 结果\n\n文献结果显示钝化改善稳定性 %s。\n\n"
            "## 讨论\n\n不同来源仍有差异 %s。\n\n## 结论\n\n需要统一评价协议 %s。\n\n"
            "## 参考文献\n\n[REF-01] Fixture reference. %s\n" % (("[REF-01]",) * 9),
            encoding="utf-8",
        )
        audit = client.call(
            "research_manuscript_audit",
            {
                "project_dir": project,
                "run_id": run.get("run_id"),
                "draft": "drafts/e2e-review.md",
            },
        )
        check("writing.audit_blocked_by_fixture", audit.get("status") == "blocked", str(audit.get("status")))
        check("writing.not_submission_ready", audit.get("submission_ready") is False)
        check("writing.audit_file", (Path(run.get("run_dir")) / "writing-audit.json").is_file())
        summary["artifacts"]["writing_audit"] = str(Path(run.get("run_dir")) / "writing-audit.json")

        real_run = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": "How do self-improving coding agents use archives?",
                "task_type": "literature_review",
                "source": "real",
                "max_sources": 2,
                "language": "en",
                "flow_mode": "review",
            },
        )
        check("support.real_run", real_run.get("status") == "completed", str(real_run.get("status")))
        real_pack = client.call(
            "research_writing_pack",
            {
                "project_dir": project,
                "run_id": real_run.get("run_id"),
                "language": "en",
                "max_sources": 2,
                "max_spans_per_source": 2,
            },
        )
        check(
            "support.pack_spans",
            any((real_pack.get("evidence_map") or {}).values()),
            str({key: len(value) for key, value in (real_pack.get("evidence_map") or {}).items()}),
        )
        source_draft = project_path / "drafts" / "e2e-support-source.md"
        source_draft.write_text(
            "# E2E Support\n\n## 摘要\n\n该文研究安全地自动搜索更优 AI 的可能性[REF-01]。"
            "\n\n## 引言\n\n自我改进编码智能体可以修改自身代码以提升性能[REF-02]。\n",
            encoding="utf-8",
        )
        bind = client.call(
            "research_manuscript_bind",
            {
                "project_dir": project,
                "run_id": real_run.get("run_id"),
                "draft": "drafts/e2e-support-source.md",
                "output": "drafts/e2e-support.md",
            },
        )
        check(
            "support.bind",
            bool(bind.get("marker"))
            and Path(bind.get("new_draft") or "").is_file(),
            str(bind.get("unresolved_refs")),
        )
        support_items = client.call(
            "research_support_items",
            {
                "project_dir": project,
                "run_id": real_run.get("run_id"),
                "draft": "drafts/e2e-support.md",
            },
        )
        judgeable = support_items.get("judgeable_ids") or []
        check("support.items", len(judgeable) >= 2, str(judgeable))
        by_id = {item["id"]: item for item in support_items.get("items") or []}
        verdicts = [
            {
                "id": item_id,
                "status": "supported",
                "rationale": "e2e support check",
                "evidence_refs": [by_id[item_id]["evidence"][0]["ref"]],
            }
            for item_id in judgeable
        ]
        first_ledger = client.call(
            "research_support_verdicts",
            {
                "project_dir": project,
                "run_id": real_run.get("run_id"),
                "draft": "drafts/e2e-support.md",
                "judge_id": "qoder-e2e",
                "verdicts": verdicts,
            },
        )
        check("support.ledger", first_ledger.get("status") == "ready", str(first_ledger.get("status")))
        edit = client.call(
            "research_manuscript_section_edit",
            {
                "project_dir": project,
                "run_id": real_run.get("run_id"),
                "draft": "drafts/e2e-support.md",
                "section": "引言",
                "replacement": "自我改进编码智能体能够编辑自身代码库，以在成本、速度与基准性能上改进自身[REF-02]。",
                "output": "drafts/e2e-support-v2.md",
            },
        )
        check("support.section_edit", Path(edit.get("new_draft") or "").is_file())
        second_items = client.call(
            "research_support_items",
            {
                "project_dir": project,
                "run_id": real_run.get("run_id"),
                "draft": "drafts/e2e-support-v2.md",
            },
        )
        changed = [
            item
            for item in second_items.get("items") or []
            if "编辑自身代码库" in item.get("sentence", "")
        ]
        check("support.changed_item", len(changed) == 1, str(len(changed)))
        reused = client.call(
            "research_support_verdicts",
            {
                "project_dir": project,
                "run_id": real_run.get("run_id"),
                "draft": "drafts/e2e-support-v2.md",
                "judge_id": "qoder-e2e",
                "reuse": True,
                "verdicts": [
                    {
                        "id": changed[0]["id"],
                        "status": "supported",
                        "rationale": "e2e changed sentence",
                        "evidence_refs": [changed[0]["evidence"][0]["ref"]],
                    }
                ],
            },
        )
        check(
            "support.reuse",
            reused.get("reused_count") == len(judgeable) - 1,
            str(reused.get("reused_count")),
        )
        archived = reused.get("archived_ledger") or ""
        check(
            "support.archive",
            bool(archived) and (Path(real_run.get("run_dir") or "") / archived).is_file(),
            archived,
        )
        next_actions = client.call(
            "research_next_actions",
            {"project_dir": project, "run_id": real_run.get("run_id")},
        )
        kinds = [
            action.get("kind")
            for action in next_actions.get("next_actions") or []
        ]
        check("support.next_human_gold", "human_gold" in kinds, str(kinds))
        status = client.call(
            "research_status", {"project_dir": project, "limit": 20}
        )
        status_row = next(
            (
                item
                for item in status.get("runs") or []
                if item.get("run_id") == real_run.get("run_id")
            ),
            {},
        )
        check(
            "support.status_visible",
            (status_row.get("support") or {}).get("status") == "ready",
            str(status_row.get("support")),
        )
        support_run_dir = Path(real_run.get("run_dir") or "")
        gold_template_cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent",
                "writing",
                "support-gold-template",
                "--project",
                str(project_path),
                "--run-id",
                str(real_run.get("run_id")),
                "--ledger",
                "runs/%s/support-ledger.json" % real_run.get("run_id"),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        check(
            "gold.template_cli",
            gold_template_cli.returncode == 0
            and (support_run_dir / "support-gold-template.json").is_file(),
            gold_template_cli.stderr[-200:],
        )
        for name in ("A", "B"):
            annotation_path = support_run_dir / (
                "support-gold-annotations-%s.json" % name
            )
            annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
            for item in annotation.get("items") or []:
                item["status"] = "supported"
                item["note"] = "E2E simulated label; not human gold"
            annotation_path.write_text(
                json.dumps(annotation, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        gold_cli = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_agent",
                "writing",
                "support-gold",
                "--project",
                str(project_path),
                "--run-id",
                str(real_run.get("run_id")),
                "--annotator-file",
                "runs/%s/support-gold-annotations-A.json" % real_run.get("run_id"),
                "--annotator-file",
                "runs/%s/support-gold-annotations-B.json" % real_run.get("run_id"),
                "--ledger",
                "runs/%s/support-ledger.json" % real_run.get("run_id"),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        gold_payload = json.loads(gold_cli.stdout or "{}")
        check(
            "gold.compare_cli",
            gold_cli.returncode == 0
            and gold_payload.get("status") == "complete"
            and (gold_payload.get("panel") or {}).get("accuracy") == 1.0,
            gold_cli.stderr[-200:],
        )
        summary["artifacts"]["support_ledger"] = str(
            support_run_dir / "support-ledger.json"
        )
        summary["artifacts"]["support_gold"] = str(
            support_run_dir / "support-gold.json"
        )

        strict = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": "湿热条件下钝化层稳定性 研究假设",
                "task_type": "hypothesis_design",
                "source": "fixture",
                "max_sources": 3,
                "language": "zh",
                "flow_mode": "strict",
            },
        )
        check("strict.g1", strict.get("stopped_at") == "G1", str(strict.get("stopped_at")))
        check("strict.human", strict.get("status") == "needs_human", str(strict.get("status")))
        actions = client.call(
            "research_next_actions",
            {"project_dir": project, "run_id": strict.get("run_id")},
        )
        g1 = next((item for item in actions.get("next_actions", []) if item.get("gate") == "G1"), None)
        check("strict.next_action", bool(g1 and g1.get("cli")))
        summary["artifacts"]["strict_run"] = strict.get("run_dir")

        idea_text = client.call(
            "research_read_artifact",
            {
                "project_dir": project,
                "run_id": strict.get("run_id"),
                "path": "idea.json",
                "max_chars": 20000,
            },
        ).get("text") or ""
        idea = json.loads(idea_text)
        candidate = (idea.get("candidates") or [None])[0]
        check("strict.idea", isinstance(candidate, dict) and bool(candidate.get("idea_id")))
        g1_path = Path(strict.get("run_dir")) / "g1-decision.json"
        cli = subprocess.run(
            [
                sys.executable, "-m", "research_agent", "flow", "g1",
                "--idea-file", str(Path(strict.get("run_dir")) / "idea.json"),
                "--idea-id", str(candidate.get("idea_id")),
                "--human-reason", "E2E test selection; not a claim signature",
                "--output-dir", str(Path(strict.get("run_dir"))),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ, PYTHONIOENCODING="utf-8"),
        )
        check("strict.g1_cli", cli.returncode == 0 and g1_path.is_file(), cli.stderr)
        strict_status = client.call(
            "research_status", {"project_dir": project, "limit": 20}
        )
        strict_row = next(
            (
                item
                for item in strict_status.get("runs") or []
                if item.get("run_id") == strict.get("run_id")
            ),
            {},
        )
        strict_idea = strict_row.get("idea") or {}
        check(
            "idea.status_visible",
            strict_idea.get("candidate_count", 0) > 0
            and strict_idea.get("shortlist_selection") == "human_g1",
            str(strict_idea)[:200],
        )
        g1_actions = client.call(
            "research_next_actions",
            {"project_dir": project, "run_id": strict.get("run_id")},
        )
        g1_action = next(
            (
                item
                for item in g1_actions.get("next_actions") or []
                if item.get("gate") == "G1"
            ),
            {},
        )
        check(
            "idea.g1_action",
            (g1_action.get("idea") or {}).get("candidate_count", 0) > 0
            and bool(g1_action.get("idea_ids")),
            str(g1_action.get("idea_ids")),
        )
        resumed = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": "湿热条件下钝化层稳定性 研究假设",
                "task_type": "hypothesis_design",
                "source": "fixture",
                "max_sources": 3,
                "language": "zh",
                "flow_mode": "strict",
                "g1_decision_file": "runs/%s/g1-decision.json" % strict.get("run_id"),
            },
        )
        check("strict.resume_status", resumed.get("status") in ("completed", "needs_human"), str(resumed.get("status")))
        check("strict.resume_experiment", "experiment.json" in (resumed.get("artifacts") or []))
        summary["artifacts"]["resumed_run"] = resumed.get("run_dir")

        data_path = project_path / "inputs" / "e2e-data.csv"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        rows = ["x1,x2,y"]
        for index in range(1, 13):
            rows.append("%d,%d,%d" % (index, index * 2, index * 3 + 1))
        data_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        codegen = client.call(
            "research_experiment_codegen",
            {
                "project_dir": project,
                "run_id": resumed.get("run_id"),
                "data": "inputs/e2e-data.csv",
                "target": "y",
                "features": ["x1", "x2"],
                "task": "regression",
                "methods": ["dummy", "ridge"],
                "seeds": 3,
            },
        )
        check(
            "experiment.codegen",
            codegen.get("status") == "generated"
            and bool(codegen.get("experiment_id")),
            str(codegen.get("status")),
        )
        manifest = Path(codegen.get("output_dir") or "") / "code-manifest.json"
        check(
            "experiment.not_executed",
            codegen.get("execution") == "not_run" and manifest.is_file(),
            str(codegen.get("execution")),
        )
        summary["artifacts"]["experiment_package"] = str(
            Path(codegen.get("output_dir") or "")
        )
        experiment_status = client.call(
            "research_experiment_status",
            {
                "project_dir": project,
                "experiment_id": codegen.get("experiment_id"),
            },
        )
        stages = experiment_status.get("stages") or {}
        check(
            "experiment.awaiting_human_approval",
            stages.get("approval") == "missing"
            and stages.get("execution") == "missing"
            and "approve" in str(experiment_status.get("next_action") or "").lower(),
            str(experiment_status.get("next_action")),
        )
        experiment_actions = client.call(
            "research_next_actions",
            {"project_dir": project, "run_id": resumed.get("run_id")},
        )
        experiment_kinds = [
            action.get("kind")
            for action in experiment_actions.get("next_actions") or []
        ]
        check(
            "experiment.next_approval_action",
            "experiment_approval" in experiment_kinds,
            str(experiment_kinds),
        )
        status_body = client.call(
            "research_status", {"project_dir": project, "limit": 20}
        )
        experiment_status_row = next(
            (
                item
                for item in status_body.get("runs") or []
                if item.get("run_id") == resumed.get("run_id")
            ),
            {},
        )
        visible_experiments = experiment_status_row.get("experiments") or []
        check(
            "experiment.status_visible",
            any(
                item.get("experiment_id") == codegen.get("experiment_id")
                and (item.get("stages") or {}).get("approval") == "missing"
                for item in visible_experiments
            ),
            str(visible_experiments)[:200],
        )
        inventory = status_body.get("experiment_inventory") or {}
        check(
            "experiment.inventory_visible",
            any(
                item.get("experiment_id") == codegen.get("experiment_id")
                for item in inventory.get("experiments") or []
            ),
            str(inventory.get("experiments") or [])[:200],
        )

        full = client.call(
            "research_run",
            {
                "project_dir": project,
                "goal": "湿热条件下钝化层稳定性 完整研究",
                "task_type": "full_research",
                "source": "fixture",
                "max_sources": 3,
                "language": "zh",
                "flow_mode": "strict",
                "g1_decision_file": "runs/%s/g1-decision.json" % strict.get("run_id"),
            },
        )
        check("full.g2_stop", full.get("stopped_at") == "G2", str(full.get("stopped_at")))
        summary["artifacts"]["full_research_run"] = full.get("run_dir")

        templates = client.call("research_figure_templates", {})
        template_ids = [item.get("id") for item in templates.get("templates", [])]
        check("figure.templates", "survey-framework" in template_ids)
        figure = client.call(
            "research_figure_render",
            {
                "project_dir": project,
                "template_id": "survey-framework",
                "name": "survey-framework",
                "title": "Qoder E2E Survey Framework",
                "description": "AstraDraw scene rendered through Qoder MCP",
                "formats": ["svg", "png"],
            },
        )
        check("figure.audit", figure.get("audit_status") == "pass", str(figure.get("audit_status")))
        check("figure.svg", Path((figure.get("files") or {}).get("svg") or "").is_file())
        check("figure.png", Path((figure.get("files") or {}).get("png") or "").is_file())
        summary["artifacts"]["figure"] = figure.get("output_dir")

        input_dir = project_path / "notes" / "revision"
        input_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "runtime_data/revision-demo-input/paper.md", input_dir / "paper.md")
        shutil.copyfile(ROOT / "runtime_data/revision-demo-input/results.csv", input_dir / "results.csv")
        shutil.copyfile(ROOT / "runtime_data/revision-demo-input/metrics.json", input_dir / "metrics.json")
        shutil.copyfile(ROOT / "runtime_data/revision-demo-input/figures.json", input_dir / "figures.json")
        revision = client.call(
            "research_manuscript_revise",
            {
                "project_dir": project,
                "draft": "notes/revision/paper.md",
                "data": ["notes/revision/results.csv"],
                "metrics_file": "notes/revision/metrics.json",
                "figures_file": "notes/revision/figures.json",
                "venue": "software_journal",
                "formats": ["md", "docx", "pdf"],
            },
        )
        check("revision.copy_mode", revision.get("writer_mode") == "copy", str(revision.get("writer_mode")))
        check("revision.not_submission_ready", revision.get("submission_ready") is False)
        check("revision.export", Path((revision.get("files") or {}).get("export", {}).get("docx") or "").is_file())
        summary["artifacts"]["revision"] = revision.get("output_dir")

        traversal = client.request(
            "tools/call",
            {
                "name": "research_read_artifact",
                "arguments": {
                    "project_dir": project,
                    "run_id": run.get("run_id"),
                    "path": "../../project.json",
                },
            },
        )
        check("path.traversal_rejected", traversal.get("isError") is True, str(traversal.get("structuredContent") or {}))
    finally:
        client.close()

    summary["result"] = "pass" if all(item["status"] == "pass" for item in summary["checks"]) else "fail"
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Qoder MCP E2E",
        "",
        "- project: `%s`" % project,
        "- tools: %d" % len(summary.get("tools") or []),
        "- result: `%s`" % summary["result"],
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for item in summary["checks"]:
        lines.append("| %s | %s | %s |" % (item["name"], item["status"], item["detail"]))
    lines += [
        "",
        "## Artifacts",
        "",
    ]
    for key, value in sorted((summary.get("artifacts") or {}).items()):
        lines.append("- %s: `%s`" % (key, value))
    lines += [
        "",
        "Boundary: this test used MCP; it did not sign a claim, freeze a protocol, sign closure or publish a bundle.",
        "",
    ]
    (output / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"result": summary["result"], "summary": str(output / "summary.md"), "tools": len(summary["tools"])}, ensure_ascii=False, indent=2))
    return 0 if summary["result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

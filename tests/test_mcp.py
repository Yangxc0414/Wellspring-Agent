import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent.mcp_server import MCPServer, ResearchMCPService, TOOL_NAMES, Transport
from research_agent.mcp_tools import TOOLS
from research_agent.project import ProjectError
from research_agent.skill_registry import SkillRegistryStore, manifest_from_payload
from research_agent.specs import SpecStore


def _ndjson(messages):
    return b"".join(
        (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        for message in messages
    )


def _parse_ndjson(payload):
    return [
        json.loads(line.decode("utf-8"))
        for line in payload.splitlines()
        if line.strip()
    ]


def _lsp(message):
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    return b"Content-Length: %d\r\n\r\n" % len(body) + body


def _parse_lsp(payload):
    header, body = payload.split(b"\r\n\r\n", 1)
    length = int(header.decode("ascii").split(":", 1)[1].strip())
    return json.loads(body[:length].decode("utf-8"))


class MCPIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.project = "demo-project"
        self.env = mock.patch.dict(
            os.environ,
            {
                "RESEARCH_AGENT_MODE": "test",
                "RESEARCH_AGENT_MODEL_STORE": str(self.root / "model_gateway.json"),
                "RESEARCH_AGENT_SKILL_REGISTRY": str(self.root / "skills.json"),
                "RESEARCH_AGENT_SKILL_USAGE": str(self.root / "skill_usage.json"),
            },
        )
        self.env.start()
        self.log_patch = mock.patch("research_agent.mcp_server._log", lambda _message: None)
        self.log_patch.start()

    def tearDown(self):
        self.log_patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def _serve(self, messages):
        reader = io.BytesIO(_ndjson(messages))
        writer = io.BytesIO()
        server = MCPServer(ResearchMCPService(self.root), Transport(reader, writer))
        server.serve()
        return _parse_ndjson(writer.getvalue())

    def test_venue_audit_over_mcp_carries_the_same_pack_rubric_as_the_cli(self):
        # the CLI could attach a journal pack rubric to a venue audit while the host-facing
        # tool silently lacked those arguments, so the two faces could not be compared
        import json as _json

        from research_agent.project import init_project

        project = self.root / "venue-project"
        init_project(project, name="venue")
        draft = {
            "title": "归档与门控对搜索效率的影响",
            "abstract": "本文研究记忆归档与门控组合对搜索效率的影响，采用配对种子设计。" * 3,
            "keywords": ["搜索智能体", "记忆", "消融"],
            "sections": [{"heading": "方法", "text": "配对种子 32 个，报告均值与区间。"}],
            "references": [{"title": "A survey of self-improving agents", "raw": "REF-01"}],
        }
        (project / "draft.json").write_text(
            _json.dumps(draft, ensure_ascii=False), encoding="utf-8"
        )
        pack = self.root / "venue-pack"
        (pack / "skills" / "demo").mkdir(parents=True)
        (pack / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (pack / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo-journal\n---\n\n# Demo\n\n## 实验要求\n\n"
            "- 多次运行报告均值±方差\n- 每个设计选择做去除或替换对照\n",
            encoding="utf-8",
        )
        result = ResearchMCPService(self.root).venue_audit({
            "project_dir": "venue-project",
            "file": "draft.json",
            "kind": "zh_journal",
            "skill_pack": "venue-pack",
        })
        self.assertFalse(result["isError"])
        payload = result["structuredContent"]
        attached = payload.get("skill_pack") or {}
        coverage = attached.get("coverage") or {}
        self.assertEqual(attached.get("pack"), "venue-pack")
        self.assertIn("pack_scope", coverage)
        # items + context_skipped is about extraction, not about the actionability heuristic,
        # so this asserts the pack really travelled to the host face without depending on tone
        self.assertGreaterEqual(coverage.get("items", 0) + coverage.get("context_skipped", 0), 1)
        self.assertEqual(
            coverage["pack_scope"]["checklist_total"],
            attached["checklist_total"],
        )
        self.assertTrue(
            any("advisory checklist" in w for w in payload.get("warnings") or []),
            payload.get("warnings"),
        )
        # the same pack arguments must be declared in the tool schema, or a host cannot find them
        schema = next(
            spec["inputSchema"]["properties"]
            for spec in TOOLS
            if spec["name"] == "research_venue_audit"
        )
        for key in ("skill_pack", "skill_pack_root", "venue", "skill_stage", "skill_profile"):
            self.assertIn(key, schema)

    def test_skill_pack_coverage_and_mandate_tools_are_usable_by_a_host(self):
        service = ResearchMCPService(self.root)
        pack = self.root / "pack"
        (pack / "skills" / "demo").mkdir(parents=True)
        (pack / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (pack / "skills" / "demo" / "SKILL.md").write_text(
            "---\nname: demo\n---\n\n# Demo\n\n## Experiment requirements\n\n"
            "- report mean and variance over seeds\n- explain the missing baseline\n",
            encoding="utf-8",
        )
        (self.root / "design.json").write_text(
            '{"question": "does variance help", "statistics": {"seeds": 32}}', encoding="utf-8"
        )
        result = service.skill_packs(
            {"action": "coverage", "pack_dir": "pack", "artifact": "design.json"}
        )
        self.assertFalse(result["isError"])
        scope = result["structuredContent"]["pack_scope"]
        self.assertGreaterEqual(scope["checklist_total"], 1)
        self.assertEqual(scope["checklist_items"], scope["checklist_total"])
        with self.assertRaises(ProjectError):
            service.skill_packs(
                {"action": "coverage", "pack_dir": "pack", "artifact": "design.json",
                 "stage": "design", "profile": "design"}
            )
        with self.assertRaises(ProjectError):
            service.mandate_status({"project_dir": "does-not-exist"})

    def test_handshake_tool_whitelist_and_fixture_run(self):
        first = self._serve(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": "unit-test", "version": "0.1"},
                        "capabilities": {},
                    },
                },
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": self.project, "name": "Demo"},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "research_plan",
                        "arguments": {
                            "project_dir": self.project,
                            "goal": "钙钛矿界面钝化 湿热稳定性 文献综述",
                            "task_type": "literature_review",
                            "source": "fixture",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "research_run",
                        "arguments": {
                            "project_dir": self.project,
                            "goal": "钙钛矿界面钝化 湿热稳定性 文献综述",
                            "task_type": "literature_review",
                            "source": "fixture",
                            "max_sources": 6,
                            "language": "zh",
                            "flow_mode": "review",
                        },
                    },
                },
            ]
        )
        self.assertGreaterEqual(len(first), 5)
        init = first[0]["result"]
        self.assertEqual(init["protocolVersion"], "2024-11-05")
        self.assertEqual(init["serverInfo"]["name"], "research-agent")
        self.assertEqual(init["serverInfo"]["version"], SpecStore().load("integration").version)
        tools = [item["name"] for item in first[1]["result"]["tools"]]
        self.assertEqual(tuple(tools), TOOL_NAMES)
        self.assertFalse(
            any(word in name for name in tools for word in ("sign", "approve", "publish", "freeze"))
        )

        created = first[2]["result"]["structuredContent"]
        self.assertTrue(created["created"])
        self.assertTrue((self.root / self.project / "project.json").is_file())
        self.assertTrue((self.root / self.project / "inputs").is_dir())

        plan = first[3]["result"]["structuredContent"]
        self.assertEqual(plan["plan"]["route"], "literature_review")

        run = first[4]["result"]["structuredContent"]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["route"], "literature_review")
        self.assertIn("task.json", run["artifacts"])
        self.assertIn("task-report.md", run["artifacts"])
        run_dir = Path(run["run_dir"])
        self.assertTrue(str(run_dir).startswith(str(self.root)))
        self.assertTrue((run_dir / "task.json").is_file())
        self.assertTrue((run_dir / "task-report.md").is_file())
        self.assertEqual(run["next_actions"][0]["kind"], "read")

        run_id = run["run_id"]
        second = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_list_artifacts",
                        "arguments": {"project_dir": self.project, "run_id": run_id},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_read_artifact",
                        "arguments": {
                            "project_dir": self.project,
                            "run_id": run_id,
                            "path": "task-report.md",
                            "max_chars": 2000,
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "research_read_artifact",
                        "arguments": {
                            "project_dir": self.project,
                            "run_id": run_id,
                            "path": "../../project.json",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "research_status",
                        "arguments": {"project_dir": self.project},
                    },
                },
            ]
        )
        listed = second[1]["result"]["structuredContent"]
        paths = {item["path"] for item in listed["artifacts"]}
        self.assertIn("task.json", paths)
        self.assertIn("run-context.json", paths)
        report = second[2]["result"]["structuredContent"]
        self.assertIn("task-report.md", report["path"])
        self.assertTrue(report["text"].startswith("#"))
        escaped = second[3]["result"]
        self.assertTrue(escaped["isError"])
        self.assertIn("inside", escaped["structuredContent"]["error"])
        status = second[4]["result"]["structuredContent"]
        self.assertEqual(status["runs"][0]["run_id"], run_id)
        self.assertEqual(status["runs"][0]["status"], "completed")

    def test_skill_invoke_requires_enabled_external_skill_and_profile(self):
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_skill_invoke",
                        "arguments": {"skill_id": "missing-skill", "input": "review this"},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_skill_invoke",
                        "arguments": {
                            "skill_id": "missing-skill",
                            "input": "review this",
                            "trusted_scripts": True,
                        },
                    },
                },
            ]
        )
        response = responses[1]["result"]
        self.assertTrue(response["isError"])
        self.assertIn("profile_id", response["structuredContent"]["error"])
        refused = responses[2]["result"]
        self.assertTrue(refused["isError"])
        self.assertIn("trusted_scripts", refused["structuredContent"]["error"])

    def test_bootstrap_initializes_project_plans_and_lists_skills(self):
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_bootstrap",
                        "arguments": {
                            "project_dir": self.project,
                            "goal": "钙钛矿界面钝化 湿热稳定性 文献综述",
                            "source": "fixture",
                            "task_type": "literature_review",
                            "run_now": True,
                        },
                    },
                },
            ]
        )
        payload = responses[1]["result"]["structuredContent"]
        self.assertEqual(payload["schema_version"], "research-bootstrap-0.2")
        self.assertTrue((self.root / self.project / "project.json").is_file())
        self.assertEqual(payload["plan"]["route"], "literature_review")
        self.assertIn("available_skills", payload)
        self.assertIn("journal_profiles", payload)
        self.assertEqual(payload["run"]["status"], "completed")
        self.assertIn("bounded research_run", payload["boundary"])

    def test_skill_instructions_are_read_only_and_never_execute_scripts(self):
        store = SkillRegistryStore(self.root / "skills.json")
        manifest = manifest_from_payload(
            {
                "name": "mcp-instructions",
                "description": "Review a manuscript with an external checklist.",
                "instructions": "Check every claim against a selected span.",
                "license": "MIT",
                "source": "imported",
                "has_scripts": True,
                "enabled": True,
            }
        )
        record, _ = store.register(manifest)
        store.set_enabled(record["id"], True)
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_skill_instructions",
                        "arguments": {"skill_id": record["id"]},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_skill_instructions",
                        "arguments": {"skill_id": "missing-skill"},
                    },
                },
            ]
        )
        payload = responses[1]["result"]["structuredContent"]
        self.assertIn("selected span", payload["instructions"])
        self.assertTrue(payload["has_scripts"])
        self.assertIn("no script execution", payload["boundary"])
        self.assertTrue(responses[2]["result"]["isError"])

    def test_skill_list_and_distill_are_project_bounded(self):
        store = SkillRegistryStore(self.root / "skills.json")
        manifest = manifest_from_payload(
            {
                "name": "mcp-review",
                "description": "Review a manuscript.",
                "instructions": "Check every claim against a span.",
                "license": "MIT",
                "source": "imported",
                "enabled": True,
            }
        )
        record, _ = store.register(manifest)
        store.set_enabled(record["id"], True)
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": self.project},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "research_skill_list", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "research_skill_distill",
                        "arguments": {
                            "skill_id": record["id"],
                            "project_dir": self.project,
                            "human_reason": "Reuse the review checklist locally",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {"name": "research_skill_list", "arguments": {}},
                },
            ]
        )
        listed = responses[2]["result"]["structuredContent"]
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["skills"][0]["id"], record["id"])
        self.assertNotIn("instructions", listed["skills"][0])
        self.assertNotIn("origin", listed["skills"][0])
        distilled = responses[3]["result"]["structuredContent"]
        self.assertTrue(distilled["created"])
        self.assertFalse(distilled["candidate"]["enabled"])
        self.assertTrue(
            distilled["path"].startswith(str(self.root / self.project / "notes" / "skill-library"))
        )
        local = store.list()
        local_candidate = next(item for item in local if item.get("id") == distilled["candidate"]["registered_skill_id"])
        self.assertFalse(local_candidate["enabled"])
        listed_again = responses[4]["result"]["structuredContent"]
        self.assertEqual(listed_again["count"], 2)
        self.assertEqual(
            sum(1 for item in listed_again["skills"] if not item["enabled"]), 1
        )
        self.assertTrue(
            (self.root / self.project / "notes" / "skill-distillations").is_dir()
        )

    def test_literature_fetch_requires_explicit_network_opt_in(self):
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": self.project},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_literature_fetch",
                        "arguments": {
                            "project_dir": self.project,
                            "query": "self-improving agents",
                            "allow_network": False,
                        },
                    },
                },
            ]
        )
        result = responses[2]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("allow_network", result["structuredContent"]["error"])

    def test_figure_templates_and_render_are_project_bounded(self):
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "research_figure_templates", "arguments": {}},
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": self.project},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "research_figure_render",
                        "arguments": {
                            "project_dir": self.project,
                            "template_id": "framework-example",
                            "name": "framework-demo",
                            "formats": ["svg"],
                        },
                    },
                },
            ]
        )
        catalog = responses[1]["result"]["structuredContent"]
        self.assertTrue(any(item["id"] == "framework-example" for item in catalog["templates"]))
        rendered = responses[3]["result"]["structuredContent"]
        self.assertEqual(rendered["status"], "rendered")
        self.assertTrue(Path(rendered["files"]["svg"]).is_file())
        self.assertTrue(
            str(rendered["output_dir"]).startswith(str(self.root / self.project / "figures"))
        )

    def test_manuscript_revise_is_project_bounded(self):
        project_path = self.root / self.project
        project_path.mkdir(parents=True)
        (project_path / "paper.md").write_text(
            "# MCP revision test\n\n## 结果\n\n方法 A 的准确率为 0.9000，引用 [1]。\n\n"
            "## 参考文献\n\n[1] Test reference.\n",
            encoding="utf-8",
        )
        (project_path / "data.csv").write_text(
            "method,accuracy\nA,0.90\nA,0.92\n", encoding="utf-8"
        )
        (project_path / "metrics.json").write_text(
            json.dumps(
                {"metrics": [
                    {"name": "mean_a", "table": "data", "column": "accuracy",
                     "op": "mean", "digits": 4, "replace": "0.9000"}
                ]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": self.project},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_manuscript_revise",
                        "arguments": {
                            "project_dir": self.project,
                            "draft": "paper.md",
                            "data": ["data.csv"],
                            "metrics_file": "metrics.json",
                            "formats": ["md", "docx"],
                        },
                    },
                },
            ]
        )
        result = responses[2]["result"]
        self.assertFalse(result["isError"], result)
        summary = result["structuredContent"]
        self.assertEqual(summary["status"], "copy_only")
        self.assertFalse(summary["submission_ready"])
        self.assertTrue(summary["output_dir"].startswith(str(project_path / "revisions")))
        self.assertTrue(Path(summary["files"]["export"]["docx"]).is_file())
        self.assertTrue((Path(summary["output_dir"]) / "revision-audit.json").is_file())

    def test_writing_pack_and_audit_write_inside_run(self):
        goal = "钙钛矿界面钝化 湿热稳定性 文献综述"
        first = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": self.project},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_run",
                        "arguments": {
                            "project_dir": self.project,
                            "goal": goal,
                            "task_type": "literature_review",
                            "source": "fixture",
                            "max_sources": 4,
                            "language": "zh",
                            "flow_mode": "review",
                        },
                    },
                },
            ]
        )
        run = first[2]["result"]["structuredContent"]
        run_id = run["run_id"]
        run_path = Path(run["run_dir"])
        self.assertTrue((run_path / "loop-capsule.json").is_file())

        status_response = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_status",
                        "arguments": {"project_dir": self.project},
                    },
                },
            ]
        )
        status_run = status_response[1]["result"]["structuredContent"]["runs"][0]
        self.assertIn("loop_capsule", status_run)
        self.assertIn("S1", status_run["loop_capsule"]["nodes"])

        next_response = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_next_actions",
                        "arguments": {"project_dir": self.project, "run_id": run_id},
                    },
                },
            ]
        )
        next_payload = next_response[1]["result"]["structuredContent"]
        self.assertTrue(next_payload["loop_capsule"])
        self.assertIn("boundary", next_payload["loop_capsule"])

        second = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_writing_pack",
                        "arguments": {
                            "project_dir": self.project,
                            "run_id": run_id,
                            "max_sources": 4,
                        },
                    },
                },
            ]
        )
        pack = second[1]["result"]["structuredContent"]
        self.assertGreater(len(pack["literature"]["references"]), 0)
        self.assertEqual(pack["claim"]["status"], "missing")
        self.assertTrue((run_path / "writing-pack.json").is_file())
        self.assertTrue((run_path / "writing-pack.md").is_file())

        draft = run_path / "draft.md"
        draft.write_text(
            "# 综述草稿\n\n## 摘要\n\n本文综述界面钝化 %s。\n\n## 引言\n\n稳定性是关键问题 %s。\n\n"
            "## 相关工作\n\n已有研究覆盖多种钝化策略 %s。\n\n## 方法\n\n本文采用文献比较方法 %s。\n\n"
            "## 实验\n\n本文比较已报道的实验设置 %s。\n\n## 结果\n\n文献结果表明钝化可以改善稳定性 %s。\n\n"
            "## 讨论\n\n不同来源之间仍存在差异 %s。\n\n## 结论\n\n需要统一评价协议 %s。\n\n"
            "## 参考文献\n\n[REF-01] Fixture reference. %s\n"
            % (("[REF-01]",) * 9),
            encoding="utf-8",
        )
        third = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_manuscript_audit",
                        "arguments": {
                            "project_dir": self.project,
                            "run_id": run_id,
                            "draft": "runs/" + run_id + "/draft.md",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_next_actions",
                        "arguments": {"project_dir": self.project, "run_id": run_id},
                    },
                },
            ]
        )
        audit = third[1]["result"]["structuredContent"]
        self.assertFalse(third[1]["result"]["isError"], third[1]["result"])
        self.assertEqual(audit["status"], "blocked")
        self.assertFalse(audit["submission_ready"])
        self.assertTrue(any(item.startswith("fixture") for item in audit["blockers"]))
        self.assertTrue((run_path / "writing-audit.json").is_file())
        next_actions = third[2]["result"]["structuredContent"]["next_actions"]
        self.assertTrue(
            any(item.get("tool") == "research_manuscript_audit" for item in next_actions),
            next_actions,
        )
        with mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": ""}):
            fourth = self._serve(
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "research_innovation_review",
                            "arguments": {"project_dir": self.project, "run_id": run_id, "rounds": 1},
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "research_manuscript_review",
                            "arguments": {
                                "project_dir": self.project,
                                "run_id": run_id,
                                "draft": "runs/" + run_id + "/draft.md",
                                "rounds": 1,
                            },
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "research_manuscript_draft",
                            "arguments": {
                                "project_dir": self.project,
                                "run_id": run_id,
                                "output": "drafts/generated.md",
                            },
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 5,
                        "method": "tools/call",
                        "params": {
                            "name": "research_literature_synthesis",
                            "arguments": {"project_dir": self.project, "run_id": run_id},
                        },
                    },
                ]
            )
        for response in (
            fourth[1]["result"],
            fourth[2]["result"],
            fourth[3]["result"],
            fourth[4]["result"],
        ):
            self.assertTrue(response["isError"])
            self.assertIn("DEEPSEEK", response["structuredContent"]["error"])

    def test_content_length_framing(self):
        payload = _lsp(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05"},
            }
        )
        reader = io.BytesIO(payload)
        writer = io.BytesIO()
        MCPServer(ResearchMCPService(self.root), Transport(reader, writer)).serve()
        response = _parse_lsp(writer.getvalue())
        self.assertEqual(response["result"]["serverInfo"]["name"], "research-agent")

    def test_outside_root_and_unknown_method_are_rejected(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": str(Path(outside.name).resolve())},
                    },
                },
                {"jsonrpc": "2.0", "id": 3, "method": "unknown/method", "params": {}},
            ]
        )
        init = responses[1]["result"]
        self.assertTrue(init["isError"])
        self.assertIn("allowed root", init["structuredContent"]["error"])
        self.assertFalse((Path(outside.name) / "project.json").exists())
        self.assertEqual(responses[2]["error"]["code"], -32601)

    def test_local_source_requires_inputs(self):
        self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": self.project},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_run",
                        "arguments": {
                            "project_dir": self.project,
                            "goal": "本地全文证据综述",
                            "task_type": "literature_review",
                            "source": "local",
                        },
                    },
                },
            ]
        )
        run_dirs = list((self.root / self.project / "runs").glob("RUN-*"))
        self.assertEqual(run_dirs, [])
        result = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_run",
                        "arguments": {
                            "project_dir": self.project,
                            "goal": "本地全文证据综述",
                            "task_type": "literature_review",
                            "source": "local",
                        },
                    },
                },
            ]
        )[1]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("PDF/TXT/MD", result["structuredContent"]["error"])

    def test_strict_g1_resume_path_is_project_relative(self):
        responses = self._serve(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "research_project_init",
                        "arguments": {"project_dir": self.project},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "research_run",
                        "arguments": {
                            "project_dir": self.project,
                            "goal": "湿热条件下钝化层稳定性 研究假设",
                            "task_type": "hypothesis_design",
                            "source": "fixture",
                            "flow_mode": "strict",
                        },
                    },
                },
            ]
        )
        run = responses[2]["result"]["structuredContent"]
        self.assertEqual(run["status"], "needs_human")
        self.assertEqual(run["stopped_at"], "G1")
        resume = run["next_actions"][0]["resume"]["g1_decision_file"]
        self.assertEqual(resume, "runs/%s/g1-decision.json" % run["run_id"])
        self.assertFalse(resume.startswith("/"))

    def test_production_fails_closed_without_model_key(self):
        with mock.patch.dict(os.environ, {"RESEARCH_AGENT_MODE": "production"}):
            responses = self._serve(
                [
                    {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                    {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {
                            "name": "research_project_init",
                            "arguments": {"project_dir": self.project},
                        },
                    },
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "research_run",
                            "arguments": {
                                "project_dir": self.project,
                                "goal": "production mode must fail closed",
                                "task_type": "literature_review",
                                "source": "fixture",
                            },
                        },
                    },
                ]
            )
        result = responses[2]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("model", result["structuredContent"]["error"].lower())
        run_dirs = list((self.root / self.project / "runs").glob("RUN-*"))
        self.assertEqual(len(run_dirs), 1)
        error = json.loads((run_dirs[0] / "startup-error.json").read_text(encoding="utf-8"))
        self.assertEqual(error["status"], "failed")
        self.assertFalse((run_dirs[0] / "task.json").exists())


    def test_prompts_list_and_start_research_prompt(self):
        responses = self._serve(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": "unit-test", "version": "0.1"},
                        "capabilities": {},
                    },
                },
                {"jsonrpc": "2.0", "id": 2, "method": "prompts/list"},
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "prompts/get",
                    "params": {
                        "name": "start-research",
                        "arguments": {
                            "project_dir": self.project,
                            "goal": "启动科研智能体测试",
                            "source": "local",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "prompts/get",
                    "params": {"name": "missing", "arguments": {}},
                },
            ]
        )
        self.assertEqual(
            responses[0]["result"]["capabilities"]["prompts"],
            {"listChanged": False},
        )
        prompts = responses[1]["result"]["prompts"]
        self.assertEqual(
            [item["name"] for item in prompts],
            ["start-research", "review-draft", "review-idea"],
        )
        self.assertEqual(prompts[0]["arguments"][0]["name"], "project_dir")
        text = responses[2]["result"]["messages"][0]["content"]["text"]
        self.assertIn("research_bootstrap", text)
        self.assertIn("reuse=true", text)
        self.assertIn("不要通过 MCP 签署", text)
        self.assertEqual(responses[3]["error"]["code"], -32602)

    def test_prompts_review_draft_requires_bind_and_reuse(self):
        responses = self._serve(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": "unit-test", "version": "0.1"},
                        "capabilities": {},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "prompts/get",
                    "params": {
                        "name": "review-draft",
                        "arguments": {
                            "project_dir": self.project,
                            "run_id": "RUN-TEST",
                            "draft": "drafts/paper.md",
                        },
                    },
                },
            ]
        )
        text = responses[1]["result"]["messages"][0]["content"]["text"]
        self.assertIn("research_manuscript_bind", text)
        self.assertIn("reuse=true", text)
        self.assertIn("不得代填 gold", text)
        self.assertIn("drafts/paper-bound.md", text)

    def test_prompts_review_idea_stops_before_g1(self):
        responses = self._serve(
            [
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": "unit-test", "version": "0.1"},
                        "capabilities": {},
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "prompts/get",
                    "params": {
                        "name": "review-idea",
                        "arguments": {
                            "project_dir": self.project,
                            "run_id": "RUN-TEST",
                        },
                    },
                },
            ]
        )
        text = responses[1]["result"]["messages"][0]["content"]["text"]
        self.assertIn("research_status", text)
        self.assertIn("flow g1", text)
        self.assertIn("不要通过 MCP 写 g1-decision", text)
        self.assertIn("novelty_status=unverified", text)
        self.assertIn("不得给单一推荐", text)


if __name__ == "__main__":
    unittest.main()

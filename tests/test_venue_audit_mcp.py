"""The venue audit is exposed to Qoder as a read-only MCP tool."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent.mcp_server import (
    ResearchMCPService,
    TOOL_NAMES,
    TOOLS,
    dispatch_tool,
)


def _manuscript():
    return {
        "abstract": "本文研究科研智能体的证据审计方法。" * 20,
        "keywords": ["科研智能体", "证据审计", "复现", "实验设计", "写作"],
        "sections": [
            {"label": label, "text": "内容。" * 40}
            for label in ["引言", "相关工作", "方法", "实验", "结果", "讨论"]
        ] + [{
            "label": "结论",
            "text": "结论。基金项目：示例基金。创新点：证据审计。数据可用：代码已公开。" * 5,
        }],
        "references": [
            {"title": "中文文献%d" % index if index < 4 else "English %d" % index,
             "text": "", "verified": True}
            for index in range(8)
        ],
    }


class VenueAuditMCPTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
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
        self.service = ResearchMCPService(self.root)
        self.service.init({"project_dir": "probe", "name": "venue audit"})
        self.project = self.root / "probe"

    def tearDown(self):
        self.log_patch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_tool_is_declared_read_only(self):
        self.assertIn("research_venue_audit", TOOL_NAMES)
        tool = next(item for item in TOOLS if item["name"] == "research_venue_audit")
        self.assertTrue(tool["annotations"]["readOnlyHint"])
        properties = tool["inputSchema"]["properties"]
        for forbidden in ("sign", "approve", "publish", "submit"):
            self.assertNotIn(forbidden, properties)

    def test_chinese_manuscript_is_audited_through_dispatch(self):
        (self.project / "manuscript.json").write_text(
            json.dumps(_manuscript(), ensure_ascii=False), encoding="utf-8"
        )
        result = dispatch_tool(
            self.service,
            "research_venue_audit",
            {"project_dir": "probe", "file": "manuscript.json", "kind": "zh_journal"},
        )
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["status"], "ready_for_human")

    def test_grant_is_audited_and_nssfc_anonymity_is_enforced(self):
        sections = {module: "研究内容与依据。" * 30 for module in
                    ["选题说明", "选题依据", "研究内容", "创新之处", "研究基础", "经费概算", "活页匿名"]}
        (self.project / "grant.json").write_text(
            json.dumps({"sections": sections, "evidence_refs": ["prior"]}, ensure_ascii=False),
            encoding="utf-8",
        )
        args = {"project_dir": "probe", "file": "grant.json", "kind": "grant", "scheme": "nssfc",
                "ai_statement": True}
        blocked = dispatch_tool(self.service, "research_venue_audit", args)
        self.assertEqual(blocked["structuredContent"]["status"], "blocked")
        args.update({"anonymous": True, "identity_removed": True})
        ready = dispatch_tool(self.service, "research_venue_audit", args)
        self.assertEqual(ready["structuredContent"]["status"], "ready_for_human")

    def test_a_path_outside_the_project_is_refused(self):
        from research_agent.project import ProjectError

        with self.assertRaises(ProjectError):
            dispatch_tool(
                self.service,
                "research_venue_audit",
                {"project_dir": "probe", "file": "../outside.json", "kind": "zh_journal"},
            )


if __name__ == "__main__":
    unittest.main()

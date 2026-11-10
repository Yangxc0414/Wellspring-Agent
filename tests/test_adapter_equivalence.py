"""The platform and the plugin must produce the same research artifacts.

"一个平台 + 一个即插即用插件，效果一样" is only a claim until the same task is run through both
access surfaces and the produced artifacts are compared. This test does exactly that: the identical
`research_project_init` / `research_plan` / `research_run` sequence runs once in-process (the
platform path) and once over the real stdio MCP server (the path a Qoder/Codex/Zcode plugin uses),
and every JSON artifact plus the status payload must agree after stripping only instance identity
(run ids, project ids, timestamps, absolute paths).
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

GOAL = "钙钛矿界面钝化 湿热稳定性 文献综述"
RUN_ARGUMENTS = {
    "goal": GOAL,
    "task_type": "literature_review",
    "source": "fixture",
    "max_sources": 6,
    "language": "zh",
    "flow_mode": "review",
}
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+\d{2}:\d{2})?")
ID_RES = [
    (re.compile(r"RUN-\d{8}T\d{6}Z-[0-9a-f]+"), "RUN-*"),
    (re.compile(r"PRJ-[0-9a-f]{8,}"), "PRJ-*"),
    (re.compile(r"STUDY-[A-Za-z0-9-]*\d{8}T\d{6}Z-[0-9a-f]+"), "STUDY-*"),
    (re.compile(r"TASK-[0-9a-f]{8,}"), "TASK-*"),
    (re.compile(r"EXP-[A-Z0-9-]+"), "EXP-*"),
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"), "UUID-*"),
]


def _scrub(value, project=None):
    text = str(value)
    if project:
        text = text.replace(str(project), "<PROJECT>")
        text = text.replace(str(project).replace("\\", "/"), "<PROJECT>")
    text = TIMESTAMP_RE.sub("<TS>", text)
    for pattern, replacement in ID_RES:
        text = pattern.sub(replacement, text)
    return text


def normalize(node, project=None):
    """Strip instance identity, keep everything that carries research meaning."""
    if isinstance(node, dict):
        return {str(key): normalize(node[key], project) for key in sorted(node)}
    if isinstance(node, list):
        return [normalize(item, project) for item in node]
    if isinstance(node, str):
        return _scrub(node, project)
    return node


def _collect(project: Path) -> dict:
    """Every JSON artifact in the project, keyed by a path that survives run-id scrubbing."""
    out = {}
    for path in sorted(project.rglob("*.json")):
        relative = _scrub(str(path.relative_to(project)))
        try:
            out[relative] = normalize(json.loads(path.read_text(encoding="utf-8")), project)
        except ValueError:
            out[relative] = "unparseable"
    return out


class AdapterEquivalenceTest(unittest.TestCase):
    def _via_platform(self, root: Path, project: Path) -> dict:
        from research_agent.client import LocalResearchAgent

        Path(root).mkdir(parents=True, exist_ok=True)
        agent = LocalResearchAgent(root)
        agent.call_tool("research_project_init", {"project_dir": str(project), "name": "Equiv"})
        agent.call_tool("research_plan", dict(RUN_ARGUMENTS, project_dir=str(project)))
        agent.call_tool("research_run", dict(RUN_ARGUMENTS, project_dir=str(project)))
        status = agent.call_tool("research_status", {"project_dir": str(project)})
        return {"artifacts": _collect(project), "status": normalize(status, project)}

    def _via_plugin(self, root: Path, project: Path) -> dict:
        from research_mcp_demo import MCPClient

        Path(root).mkdir(parents=True, exist_ok=True)
        client = MCPClient(root, {"PYTHONIOENCODING": "utf-8"})
        try:
            client.call("research_project_init", {"project_dir": str(project), "name": "Equiv"})
            client.call("research_plan", dict(RUN_ARGUMENTS, project_dir=str(project)))
            client.call("research_run", dict(RUN_ARGUMENTS, project_dir=str(project)))
            status = client.call("research_status", {"project_dir": str(project)})
        finally:
            client.close()
        return {"artifacts": _collect(project), "status": normalize(status, project)}

    def test_platform_and_plugin_produce_the_same_artifacts(self):
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            platform = self._via_platform(base / "platform", base / "platform" / "project")
            plugin = self._via_plugin(base / "plugin", base / "plugin" / "project")

        self.assertTrue(platform["artifacts"], "the platform run produced no artifacts")
        self.assertEqual(
            sorted(platform["artifacts"]), sorted(plugin["artifacts"]),
            "the two transports wrote different files",
        )
        differing = [
            name for name in platform["artifacts"]
            if platform["artifacts"][name] != plugin["artifacts"][name]
        ]
        self.assertEqual(differing, [], "artifacts differ beyond instance identity: %s" % differing)

    def test_the_research_result_itself_is_non_empty_on_both_sides(self):
        # an equivalence test over two empty runs would pass for the wrong reason
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            platform = self._via_platform(base / "platform", base / "platform" / "project")
            plugin = self._via_plugin(base / "plugin", base / "plugin" / "project")
        for label, result in (("platform", platform), ("plugin", plugin)):
            ledgers = [
                name for name in result["artifacts"] if name.endswith("literature-ledger.json")
            ]
            self.assertTrue(ledgers, (label, sorted(result["artifacts"])))
            payload = json.dumps(result["artifacts"][ledgers[0]])
            self.assertIn("source", payload.lower(), ledgers)
            self.assertGreater(len(payload), 200, label)


    def test_the_third_transport_records_the_same_answer_as_the_first_two(self):
        """A file-drop answer and an MCP answer for the same request must be indistinguishable."""
        import os
        import subprocess

        from research_agent.handoff import ANSWER_DIR, answer_filename, export_pending, import_answers
        from research_agent.host_model import ModelTurnLedger

        messages = [
            {"role": "system", "content": "produce candidates"},
            {"role": "user", "content": json.dumps({"topic": "archives"}, ensure_ascii=False)},
        ]
        answer = json.dumps({"candidates": [{"title": "T", "hypothesis": "H"}]}, ensure_ascii=False)

        ledgers = {}
        for label in ("via-mcp", "via-file"):
            directory = self.root / label
            directory.mkdir(parents=True)
            ledger = ModelTurnLedger(directory / "turns.json")
            turn = ledger.create(messages=messages, profile_id="host-agent", module="idea")
            ledgers[label] = (ledger, turn, directory)

        mcp_ledger, mcp_turn, _ = ledgers["via-mcp"]
        drop_ledger, drop_turn, drop_dir = ledgers["via-file"]
        self.assertEqual(mcp_turn["messages_sha256"], drop_turn["messages_sha256"])

        from research_mcp_demo import MCPClient

        client = MCPClient(
            self.root,
            {
                "PYTHONIOENCODING": "utf-8",
                # the server must answer against this test's ledger, not the machine default
                "RESEARCH_AGENT_HOST_MODEL_LEDGER": str(self.root / "via-mcp" / "turns.json"),
            },
        )
        try:
            client.call(
                "research_model_respond",
                {"turn_id": mcp_turn["turn_id"], "text": answer, "host_label": "qoder-desktop"},
            )
        finally:
            client.close()

        export_pending(drop_ledger, drop_dir / "handoff")
        (drop_dir / "handoff" / ANSWER_DIR / answer_filename(drop_turn["turn_id"])).write_text(
            json.dumps({"text": answer}, ensure_ascii=False), encoding="utf-8"
        )
        import_answers(drop_ledger, drop_dir / "handoff", host_label="file-drop")

        stored_mcp = mcp_ledger.get(mcp_turn["turn_id"])["response"]
        stored_drop = drop_ledger.get(drop_turn["turn_id"])["response"]
        self.assertEqual(stored_mcp["text_sha256"], stored_drop["text_sha256"])
        self.assertEqual(stored_mcp["text"], stored_drop["text"])
        self.assertNotEqual(stored_mcp["host_label"], stored_drop["host_label"])

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

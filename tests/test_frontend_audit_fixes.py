"""Pins for the front-end / skill audit in design/127.

Source-level guards: these UI fixes have no backend contract to test against,
so we pin the exact source constructs that make the behaviour real. A regression
that reintroduces a dead-end or a stale-tab bug must turn a test red.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"

PANEL = (WEB / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
STORE = (WEB / "state" / "workspaceStore.ts").read_text(encoding="utf-8")
DRAWER = (WEB / "components" / "SkillsDrawer.tsx").read_text(encoding="utf-8")
WELCOME = (WEB / "components" / "WelcomeHome.tsx").read_text(encoding="utf-8")
CSS = (WEB / "styles" / "components.css").read_text(encoding="utf-8")
DOC = ROOT / "design" / "127-前端demo与skill框架的系统性反思和改进.md"


class FrontendAuditFixesTest(unittest.TestCase):
    def test_all_tabs_carry_task_key(self):
        for marker in (
            '<FlowDemo key={task.id} />',
            '<div className="context-stack" key={task.id}>',
            '<EseRunsPanel key={task.id} />',
        ):
            self.assertIn(marker, PANEL)

    def test_stage_action_accepts_and_passes_title(self):
        self.assertIn("title?: string;", PANEL)
        self.assertIn("title={title}", PANEL)
        self.assertIn("G2 是人工门", PANEL)

    def test_run_experiment_guides_static_demo_users(self):
        self.assertIn("演示请用「全自动推进」", STORE)
        self.assertIn("完整闭环」会话——它已预置冻结协议与 EA", STORE)
        # the gate itself must remain: no silent auto-freeze was introduced
        self.assertIn("if (!task.protocolFrozen)", STORE)

    def test_skill_panel_states_loading_is_only_a_check_card(self):
        self.assertIn("skill-honesty-note", DRAWER)
        self.assertIn("不会把 instructions 当作指令喂给模型执行", DRAWER)
        self.assertIn("/api/skills/", DRAWER)
        self.assertIn(".skills-drawer .skill-honesty-note", CSS)

    def test_welcome_prompts_admit_they_only_fill(self):
        self.assertIn("点击填入输入框，再按发送（不会自动执行）", WELCOME)

    def test_reflection_doc_exists_and_counts_are_updated(self):
        self.assertTrue(DOC.is_file())
        text = DOC.read_text(encoding="utf-8")
        self.assertIn("纯 UI 幻觉", text)
        self.assertIn("前后端 skill 清单漂移", text)
        index = (ROOT / "design" / "README.md").read_text(encoding="utf-8")
        # Do not pin an exact document count: every new design doc would turn this
        # red for no reason. Require the count marker to exist and the entry to be
        # indexed; docs_audit already checks the number against the real maximum.
        self.assertRegex(index, r"编号 00–\d+（\d+ 份")
        self.assertIn("127-前端demo与skill框架的系统性反思和改进", index)


if __name__ == "__main__":
    unittest.main()

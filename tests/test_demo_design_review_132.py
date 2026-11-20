"""Pins for the 132 design review: home hierarchy, sidebar gate state,
six-stage evidence chain, FlowDemo advance, and Pages demo subpage integrity.

Each rule here came from a concrete defect found by walking the UI, not from a
style preference. Keep them so the same regression cannot silently return.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
HOME = (WEB / "components" / "WelcomeHome.tsx").read_text(encoding="utf-8")
SIDEBAR = (WEB / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
PANEL = (WEB / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
FLOW = (WEB / "components" / "FlowDemo.tsx").read_text(encoding="utf-8")
LAYOUT = (WEB / "styles" / "layout.css").read_text(encoding="utf-8")
COMPCSS = (WEB / "styles" / "components.css").read_text(encoding="utf-8")
LEGIB = (ROOT / "site" / "assets" / "demo-legibility.js").read_text(encoding="utf-8")
FRONTIER = (ROOT / "demo" / "frontier" / "index.html").read_text(encoding="utf-8")
STUDY = (ROOT / "demo" / "ese-ms-03" / "index.html").read_text(encoding="utf-8")
CHAIN_SCRIPT = (ROOT / "scripts" / "build_ese_chain_page.py").read_text(encoding="utf-8")
STUDY_SCRIPT = (ROOT / "scripts" / "build_ese_study_page.py").read_text(encoding="utf-8")


class DemoDesignReviewTest(unittest.TestCase):
    # --- Home ---
    def test_home_states_product_before_greeting(self):
        self.assertIn("<h1>科研智能体工作台</h1>", HOME)
        self.assertIn("WELLSPRING AGENT · {greeting}", HOME)
        self.assertIn("welcome-prompts-hint", HOME)
        # the fill-in behaviour is visible, not hover-only
        self.assertIn("<small>填入</small>", HOME)
        self.assertIn(".welcome-prompts button small", LAYOUT)

    def test_home_prompts_are_complete_questions(self):
        # a prompt that ends in a colon gives the user a half question to send
        self.assertNotIn('text: "帮我做一轮文献调研，先盘点来源、可定位 span 与证据缺口："', HOME)
        self.assertIn("主题是：界面钝化与湿热稳定性", HOME)

    # --- Sidebar ---
    def test_blocked_demo_label_is_not_swallowed(self):
        self.assertIn('task.status === "blocked" && !demo.label.includes("待签")', SIDEBAR)
        self.assertIn("`${demo.label} · 待签`", SIDEBAR)

    # --- Evidence chain ---
    def test_chain_is_one_canonical_six_stage_vocabulary(self):
        for label in ("来源", "片段", "运行记录", "证据制品", "断言", "闭合"):
            self.assertIn(f'label: "{label}"', PANEL)
        # the guide must not fall back to the old five-stage wording
        self.assertIn("六段的含义与人工签署时点", PANEL)
        self.assertNotIn("五段的含义与人工签署时点", PANEL)
        self.assertIn("闭合", PANEL)

    def test_chain_has_status_legend_and_direction(self):
        self.assertIn("chain-legend", PANEL)
        self.assertIn("已就绪", PANEL)
        self.assertIn("待人工", PANEL)
        self.assertIn("未产出", PANEL)
        self.assertIn(".chain-link::after", COMPCSS)

    # --- FlowDemo ---
    def test_advance_opens_the_stage_entered_not_the_one_completed(self):
        self.assertIn("const next = step + 1;", FLOW)
        self.assertIn("setOpen(Math.min(next, STAGES.length - 1))", FLOW)
        self.assertNotIn("setOpen(Math.min(step, STAGES.length - 1))", FLOW)

    def test_only_one_human_gate_marker(self):
        self.assertNotIn('className="flow-stage-human"', FLOW)

    # --- Pages demo subpages ---
    def test_legibility_guide_reads_page_marker_from_main(self):
        # the marker lives on <main>, not <body>; reading body only meant the
        # guide never mounted at all
        self.assertIn('main.getAttribute("data-dl-page")', LEGIB)
        self.assertIn("MODE_TEXT_REPLAY", LEGIB)
        self.assertIn("isRealReplay()", LEGIB)
        self.assertIn("fixture_mode:\\s*false", LEGIB)

    def test_frontier_paths_are_not_one_level_too_shallow(self):
        self.assertIn('href="../../assets/demo-legibility.css"', FRONTIER)
        self.assertIn('src="../../assets/demo-legibility.js"', FRONTIER)
        self.assertIn('href="../../app/"', FRONTIER)
        self.assertNotIn('src="../assets/demo-legibility.js"', FRONTIER)

    def test_demo_titles_carry_brand(self):
        self.assertIn("· Research Agent", (ROOT / "demo" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("· Research Agent", (ROOT / "demo" / "run" / "index.html").read_text(encoding="utf-8"))
        self.assertIn("· Research Agent", FRONTIER)
        self.assertIn("· Research Agent", STUDY)
        self.assertIn("· Research Agent", CHAIN_SCRIPT)
        self.assertIn("· Research Agent", STUDY_SCRIPT)

    def test_ese_boundary_no_longer_contradicts_the_stage_table(self):
        self.assertIn("两者不矛盾", STUDY)
        self.assertIn("本页只读回放、不会新建或签署证据", STUDY)
        self.assertNotIn("D:/Program Files", STUDY)

    def test_cli_copy_matches_quoted_interpreter(self):
        self.assertIn("-m\\s+research_agent", LEGIB)


if __name__ == "__main__":
    unittest.main()

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
SEED = (WEB / "domain" / "seed.ts").read_text(encoding="utf-8")
SIDEBAR = (WEB / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
LAYOUT = (WEB / "styles" / "layout.css").read_text(encoding="utf-8")


class SidebarDemoLabelsTest(unittest.TestCase):
    def test_every_seeded_session_has_a_role_label(self):
        for key in (
            '"full-chain-demo"',
            '"ese-ms-20261118-03"',
            "perovskite:",
            "archives:",
            '"evidence-writing"',
            '"proposal-review"',
        ):
            self.assertIn(key, SEED)

    def test_ese_label_marks_it_as_a_real_signed_pending_study(self):
        # the ESE session is real data, still awaiting signature — the label must say so
        self.assertIn('label: "真实研究·待签"', SEED)
        self.assertIn("ESE-MS-20261118-03", SEED)
        self.assertIn("5132 提交", SEED)
        self.assertIn("click 方向反转", SEED)
        self.assertIn("仍待人签", SEED)

    def test_labels_are_shown_in_sidebar_not_raw_dates(self):
        self.assertIn("DEMO_LABELS", SIDEBAR)
        self.assertIn("const demo = DEMO_LABELS[task.id]", SIDEBAR)
        self.assertIn("if (demo) return demo.label", SIDEBAR)
        self.assertIn("demo.hint", SIDEBAR)
        self.assertIn('data-demo={demo ? "1" : undefined}', SIDEBAR)
        self.assertIn("data-demo-tone={demo?.tone}", SIDEBAR)

    def test_tones_distinguish_demo_from_pending_from_example(self):
        self.assertIn('tone: "demo"', SEED)
        self.assertIn('tone: "pending"', SEED)
        self.assertIn('tone: "example"', SEED)
        self.assertIn('.task-row[data-demo-tone="demo"] .task-row-time', LAYOUT)
        self.assertIn('.task-row[data-demo-tone="pending"] .task-row-time', LAYOUT)

    def test_badge_style_present(self):
        self.assertIn('.task-row[data-demo="1"] .task-row-time', LAYOUT)

    def test_export_is_importable(self):
        self.assertIn("export const DEMO_LABELS", SEED)


if __name__ == "__main__":
    unittest.main()

"""Pins for the demo-narrative audit (design/127 §6).

A demo's first impression is a separate concern from whether its buttons work:
the stage label must agree with progress, a recorded replay must open at its
first message, and the two demo surfaces must explain why their counters differ.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
CONV = (WEB / "components" / "Conversation.tsx").read_text(encoding="utf-8")
FLOW = (WEB / "components" / "FlowDemo.tsx").read_text(encoding="utf-8")
CSS = (WEB / "styles" / "components.css").read_text(encoding="utf-8")
DOC = (ROOT / "design" / "127-前端demo与skill框架的系统性反思和改进.md").read_text(
    encoding="utf-8"
)


class DemoNarrativeFixesTest(unittest.TestCase):
    def test_stage_kicker_reflects_real_progress(self):
        self.assertIn("currentStage = task.autoStages[", CONV)
        self.assertIn("completedCount > 1 && currentStage", CONV)
        self.assertIn("stageKicker}", CONV)
        # the fixed mode kicker must no longer be rendered directly
        self.assertNotIn("<span>{meta.kicker}</span>", CONV)

    def test_static_replay_opens_at_the_top(self):
        self.assertIn('item.text.startsWith("STATIC ")', CONV)
        self.assertIn("replayInitialCount", CONV)
        self.assertIn('scrollTo({ top: 0, behavior: "auto" })', CONV)
        # new messages from demo actions still scroll to newest
        self.assertIn("top: threadRef.current.scrollHeight", CONV)

    def test_flow_banner_explains_the_two_demo_surfaces(self):
        self.assertIn("flow-banner-hint", FLOW)
        self.assertIn("已走完整场", FLOW)
        self.assertIn("从第 0 步亲手推一遍", FLOW)
        self.assertIn(".flow-banner .flow-banner-hint", CSS)

    def test_reflection_doc_covers_the_second_audit(self):
        self.assertIn("## 6. 补充反思：以", DOC)
        self.assertIn("演示动线", DOC)


if __name__ == "__main__":
    unittest.main()

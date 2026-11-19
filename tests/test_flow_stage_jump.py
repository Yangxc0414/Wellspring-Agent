"""Pins for RESEARCH FLOW node -> conversation message jump.

A presenter clicks a stage in the right panel; the thread must scroll to and
highlight the message tagged with that stage. Every flow stage needs a tagged
message, otherwise the click silently does nothing.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
TYPES = (WEB / "domain" / "types.ts").read_text(encoding="utf-8")
SEED = (WEB / "domain" / "seed.ts").read_text(encoding="utf-8")
FLOW = (WEB / "components" / "FlowDemo.tsx").read_text(encoding="utf-8")
CONV = (WEB / "components" / "Conversation.tsx").read_text(encoding="utf-8")
CSS = (WEB / "styles" / "components.css").read_text(encoding="utf-8")
LAYOUT = (WEB / "styles" / "layout.css").read_text(encoding="utf-8")

# The nine stages shown in FlowDemo.
STAGES = ["S1", "S2–S3", "S4", "S5a", "S5b", "S6", "S8–S12", "S13–S16", "META"]


class FlowStageJumpTest(unittest.TestCase):
    def test_message_and_ui_carry_stage(self):
        self.assertIn("stage?: string;", TYPES)
        self.assertIn("focusStage: { id: string; tick: number } | null;", TYPES)
        self.assertIn("focusStage: null", (WEB / "state" / "workspaceStore.ts").read_text(encoding="utf-8"))

    def test_every_flow_stage_has_a_tagged_message(self):
        for stage in STAGES:
            self.assertIn(f'), "{stage}"),', SEED, f"stage {stage} has no tagged message")

    def test_flow_node_click_focuses_stage(self):
        self.assertIn("const focusInThread = (stageId: string)", FLOW)
        self.assertIn("focusStage: { id: stageId, tick: Date.now() }", FLOW)
        self.assertIn("focusInThread(stage.id)", FLOW)
        self.assertIn("flow-stage-jump", FLOW)
        self.assertIn("event.stopPropagation()", FLOW)

    def test_no_stage_message_gives_honest_feedback(self):
        self.assertIn("当前会话没有", FLOW)
        self.assertIn("切到「完整闭环」会话", FLOW)

    def test_conversation_scrolls_and_highlights_target(self):
        self.assertIn("data-stage={item.stage}", CONV)
        self.assertIn('[data-stage="${focusStage.id}"]', CONV)
        self.assertIn("scrollIntoView({ block: \"center\"", CONV)
        self.assertIn('classList.add("is-stage-focused")', CONV)

    def test_highlight_and_jump_styles_present(self):
        self.assertIn(".message.is-stage-focused .bubble", LAYOUT)
        self.assertIn(".flow-stage-jump", CSS)

    def test_delta_is_rounded_for_display(self):
        card = (WEB / "components" / "ArtifactCard.tsx").read_text(encoding="utf-8")
        self.assertIn("toFixed(4)", card)
        self.assertNotIn("const delta = card.mean - card.baseline;", card)


if __name__ == "__main__":
    unittest.main()

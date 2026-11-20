"""Pins for the end-to-end walkthrough: two progress streams must declare
their own metric, and a blocked task must not claim a stage it never cleared.

Also pins the ESE bundled-snapshot paths — those JSONs sat beside index.html
but were fetched from the site root, so ESE data had never loaded in the demo.
"""

import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
CONV = (WEB / "components" / "Conversation.tsx").read_text(encoding="utf-8")
FLOW = (WEB / "components" / "FlowDemo.tsx").read_text(encoding="utf-8")
ESE = (WEB / "components" / "EseRunsPanel.tsx").read_text(encoding="utf-8")


class FlowNarrativeTest(unittest.TestCase):
    def test_two_progress_streams_declare_their_own_metric(self):
        self.assertIn("回放 {completedCount}/9 stages", CONV)
        self.assertIn("这是已录完的回放进度", CONV)
        self.assertIn("教学重演 · 待签 · 第 ${step}/${STAGES.length} 步", FLOW)
        self.assertIn("REPLAY · 教学重演", FLOW)

    def test_blocked_task_does_not_claim_a_stage_it_never_cleared(self):
        self.assertIn('task.status === "blocked"', CONV)
        self.assertIn("`${kickerRoot} · 人签门待人签`", CONV)
        # the old META claim path is now gated behind non-blocked only
        self.assertIn(": completedCount > 1 && currentStage", CONV)

    def test_demo_sign_stays_honest(self):
        self.assertIn('signed ? "已签 · DEMO"', FLOW)
        self.assertNotIn('signed ? "已签"', FLOW)

    def test_ese_bundled_snapshots_use_relative_paths(self):
        for name in ("ese-runs.json", "ese-history.json", "ese-studies.json"):
            self.assertIn(f'fetch("./{name}', ESE)
            self.assertNotIn(f'fetch("/{name}', ESE)

    def test_static_build_skips_the_ese_runtime_call(self):
        self.assertIn("if (runtimeAvailable) {", ESE)
        self.assertIn("domain/capabilities", ESE)


if __name__ == "__main__":
    unittest.main()

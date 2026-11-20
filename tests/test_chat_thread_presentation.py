"""Pins for the chat-thread / history presentation review.

Findings were measured in a real browser, not guessed:
  * bodyW == bubbleW == cardW for every agent message (no alignment bug) — so
    this file deliberately does NOT pin any bubble-width change;
  * the user identity showed twice ("YOU" avatar + "你" header);
  * the 88-char boundary disclaimer was 10px faint, reading as a watermark;
  * 3 of 6 sidebar titles were truncated, the two most important ones worst,
    because status pills took 59-93px.
"""

import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
CONV = (WEB / "components" / "Conversation.tsx").read_text(encoding="utf-8")
SIDEBAR = (WEB / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
SEED = (WEB / "domain" / "seed.ts").read_text(encoding="utf-8")
LAYOUT = (WEB / "styles" / "layout.css").read_text(encoding="utf-8")


class ChatThreadPresentationTest(unittest.TestCase):
    def test_user_identity_not_shown_twice(self):
        self.assertIn("{!isUser && <b>Wellspring Agent</b>}", CONV)
        # the old duplicated "你" next to a "YOU" avatar is gone
        self.assertNotIn('<b>{isUser ? "你" : "Wellspring Agent"}</b>', CONV)

    def test_boundary_disclaimer_has_visual_weight(self):
        block = LAYOUT.split(".system-line {", 1)[1].split("}", 1)[0]
        self.assertIn("font-size: calc(11px", block)
        self.assertIn("color: var(--muted)", block)
        self.assertIn("border: 1px dashed var(--line)", block)
        self.assertIn("padding: 6px 12px", block)
        self.assertNotIn("color: var(--faint)", block)

    def test_demo_labels_have_compact_short_form(self):
        self.assertIn("short: string;", SEED)
        self.assertIn('short: "演示·待签"', SEED)
        self.assertIn('short: "回放·待签"', SEED)
        # sidebar renders the short form, tooltip keeps the full label + hint
        self.assertIn("demo.short", SIDEBAR)
        self.assertIn("`${task.name}\\n\\n${demo.hint}`", SIDEBAR)

    def test_status_pills_do_not_outshine_titles(self):
        block = LAYOUT.split('.task-row[data-demo="1"] .task-row-time {', 1)[1].split("}", 1)[0]
        self.assertIn("background: transparent", block)
        self.assertIn("border: 0", block)
        self.assertIn("color: var(--faint)", block)
        # title returns to full-strength text colour
        self.assertIn(".task-row[data-demo=\"1\"] .task-row-title {\n  color: var(--text);", LAYOUT)

    def test_blocked_short_label_still_signalled(self):
        self.assertIn('!demo.short.includes("待签")', SIDEBAR)


if __name__ == "__main__":
    unittest.main()

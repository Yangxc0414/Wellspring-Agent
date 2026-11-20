"""Pins for the end-to-end closed-loop replay seeded into the workbench.

This task carries a real executed run (runtime_data/e2e-closed-loop,
PIPE-20261110T163849Z-e2bd4a). Two facts must never be blurred:
  * the corpus is fixture data, so it demonstrates mechanism, not science;
  * the G5 signature on disk is `[delegated:autopilot]` with submission=false,
    which is NOT a human signature.

If a future edit lets a delegated signature render as "已人工签署" or be counted
in SIGNED CLAIMS, the demo would be lying. These tests exist to stop that.
"""

import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "apps" / "web" / "src"
SEED = (WEB / "domain" / "seed.ts").read_text(encoding="utf-8")
SIG = (WEB / "domain" / "claimSignature.ts").read_text(encoding="utf-8")
TYPES = (WEB / "domain" / "types.ts").read_text(encoding="utf-8")
PANEL = (WEB / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
GATE = (WEB / "components" / "ClaimGateDialog.tsx").read_text(encoding="utf-8")


class E2EClosedLoopSeedTest(unittest.TestCase):
    def test_task_is_registered_and_complete(self):
        self.assertIn("export function seedE2EClosedLoop()", SEED)
        self.assertIn("seedE2EClosedLoop(),", SEED)
        self.assertIn('id: "e2e-closed-loop"', SEED)
        # eight of nine stages done, META left waiting; G5 blocks the task
        self.assertIn("completedStages: [0, 1, 2, 3, 4, 5, 6, 7]", SEED)
        self.assertIn('status: "blocked"', SEED)

    def test_real_readings_are_carried_from_the_run(self):
        for reading in (
            "RUN-20261110T163848Z-f84f16",
            "EA-bf9f4eeca1d7",
            "sklearn:iris:150x4",
            "0.956",
            "PIPE-20261110T163849Z-e2bd4a",
        ):
            self.assertIn(reading, SEED, f"missing real reading: {reading}")

    def test_fixture_caveat_is_stated_in_the_ui(self):
        self.assertIn("语料是 fixture", SEED)
        self.assertIn("数据不得当作科学结论", SEED)
        self.assertIn("fixture 证据不可引用", SEED)

    def test_delegated_signature_is_never_a_human_signature(self):
        self.assertIn('origin: "delegated"', SEED)
        self.assertIn('"delegated"', TYPES)
        self.assertIn('"signed-delegated"', SIG)
        self.assertIn("委托签 · 非人签", SIG)
        self.assertIn("委托签署（非人签）", SIG)
        self.assertIn("不是作者人签", SIG)
        # the delegated branch must come before the legacy "signed-cli" fallthrough
        self.assertLess(SIG.index('claim.origin === "delegated"'), SIG.index("state: \"signed-cli\""))

    def test_delegated_is_not_counted_as_a_signed_claim(self):
        # SIGNED CLAIMS must only count human/CLI-import signatures
        block = PANEL.split("SIGNED CLAIMS", 1)[0]
        tail = block.rsplit("<div><b>", 1)[-1]
        self.assertNotIn("signed-delegated", tail)
        self.assertIn('claimLabel.state === "signed-cli" || claimLabel.state === "signed-import"', tail)

    def test_brief_and_gate_explain_the_delegated_state(self):
        self.assertIn("委托签署（autopilot 按策略代签，submission=false）", PANEL)
        self.assertIn('claim.origin === "delegated"', GATE)

    def test_sidebar_label_does_not_double_the_pending_suffix(self):
        # short label already ends at the gate truth; the blocked suffix must not stack
        self.assertIn('short: "闭环·待签"', SEED)
        self.assertNotIn('short: "闭环·委托签"', SEED)


if __name__ == "__main__":
    unittest.main()

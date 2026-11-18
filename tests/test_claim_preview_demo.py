"""Guard the static-demo 'preview signed state' button.

It used to be disabled on every seeded session: previewDemoClaim required an
existing unsigned claim, but the full-chain / ESE / example sessions only carry
gap and hypothesis evidence. The button therefore looked clickable but did
nothing. These source-level pins keep the fix and its safety boundary intact.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = (ROOT / "apps" / "web" / "src" / "state" / "workspaceStore.ts").read_text(
    encoding="utf-8"
)
DIALOG = (ROOT / "apps" / "web" / "src" / "components" / "ClaimGateDialog.tsx").read_text(
    encoding="utf-8"
)
PALETTE = (ROOT / "apps" / "web" / "src" / "components" / "CommandPalette.tsx").read_text(
    encoding="utf-8"
)


class ClaimPreviewDemoTest(unittest.TestCase):
    def test_preview_creates_a_demo_claim_when_none_exists(self):
        # The fallback materialises a clearly-labelled demo claim instead of bailing out.
        self.assertIn('id: uid("clm-demo")', STORE)
        self.assertIn('kind: "claim"', STORE)
        self.assertIn('status: "unsigned"', STORE)
        self.assertIn("if (!claim) {", STORE)
        self.assertNotIn("没有待签署的 claim；先运行 pipeline", STORE)

    def test_created_claim_is_demo_origin_and_never_a_signature(self):
        self.assertIn('origin: "demo" as const', STORE)
        self.assertIn("演示态预览：浏览器未产生签名", STORE)
        # G5 must stay blocked through the whole preview.
        self.assertIn('gate(item.gates, "G5", "blocked", "演示态预览', STORE)

    def test_reset_removes_a_preview_created_claim_cleanly(self):
        self.assertIn('previewCreated = demo.id.startsWith("clm-demo-")', STORE)
        self.assertIn("item.evidence.filter((entry) => entry.id !== demo.id)", STORE)

    def test_button_enabled_in_static_demo_even_without_a_claim(self):
        self.assertIn("const pending = __STATIC_ONLY__", DIALOG)
        self.assertIn('label.state !== "signed-demo"', DIALOG)
        self.assertIn("disabled={!pending}", DIALOG)
        self.assertIn("onClick={actions.previewDemoClaim}", DIALOG)

    def test_preview_is_still_gated_to_static_only(self):
        self.assertIn("if (!__STATIC_ONLY__)", STORE)
        self.assertIn("演示态预览只在静态 demo 构建可用", STORE)

    def test_gate_opener_is_reachable_without_a_claim_in_static_demo(self):
        # The palette previously hid the gate command when there was no unsigned
        # claim, so sessions with only gap/hypothesis evidence had no way in.
        self.assertIn("const canOpenClaimGate = unsignedClaim || __STATIC_ONLY__", PALETTE)
        self.assertIn("...(canOpenClaimGate ?", PALETTE)
        self.assertIn("run: actions.signClaim", PALETTE)


if __name__ == "__main__":
    unittest.main()

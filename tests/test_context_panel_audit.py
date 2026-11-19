"""Pins for the right-hand context panel audit.

Two classes of defect this guards against:
  * one fact told three ways — a demo claim must never read as a CLI signature;
  * a read-only control that mutates run state — "view where it was signed"
    must not pause an autopilot run or roll G5 back.
Plus two reachability/honesty fixes: eight tabs must stay clickable on a narrow
panel, and a static build must not tell the user to start a service.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web" / "src"
PANEL = (WEB / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
STORE = (WEB / "state" / "workspaceStore.ts").read_text(encoding="utf-8")
GOV = (WEB / "components" / "GovernancePanel.tsx").read_text(encoding="utf-8")
ESE = (WEB / "components" / "EseRunsPanel.tsx").read_text(encoding="utf-8")
LAYOUT = (WEB / "styles" / "layout.css").read_text(encoding="utf-8")


class ContextPanelAuditTest(unittest.TestCase):
    def test_demo_claim_is_never_shown_as_a_real_signature(self):
        # BRIEF and EVIDENCE must consult origin via claimSignatureLabel, not
        # the bare status field (RUN already did).
        self.assertIn('claimLabel.state === "signed-demo"', PANEL)
        self.assertIn("演示态预览：未产生真实签名", PANEL)
        self.assertIn("claim ? claimLabel.short : \"none\"", PANEL)
        # the old status-only wording must be gone
        self.assertNotIn('claim?.status === "signed" ? "已签署（证据来自 CLI）', PANEL)
        self.assertNotIn('claim?.status === "signed" ? 1 : 0', PANEL)

    def test_signed_claim_count_excludes_demo(self):
        self.assertIn(
            'claimLabel.state === "signed-cli" || claimLabel.state === "signed-import" ? 1 : 0',
            PANEL,
        )

    def test_view_only_entry_does_not_mutate_run_state(self):
        # a dedicated read-only opener exists and does not touch paused/gate
        self.assertIn("openClaimGate: () => void;", STORE)
        self.assertIn("openClaimGate: () => {", STORE)
        # the panel must route "查看" to it instead of signClaim
        self.assertIn("? actions.signClaim", PANEL)
        self.assertIn(": actions.openClaimGate", PANEL)

    def test_split_is_real_in_the_store(self):
        block = STORE.split("openClaimGate: () => {", 1)[1].split("},", 1)[0]
        self.assertNotIn("paused", block)
        self.assertNotIn("gate(item.gates", block)

    def test_all_tabs_wrap_instead_of_clipping(self):
        self.assertIn("flex-wrap: wrap;", LAYOUT)
        self.assertIn("Eight tabs overflow a narrow context panel", LAYOUT)

    def test_static_build_does_not_blame_a_missing_service(self):
        self.assertIn("静态演示构建：runtime 在构建时已禁用", GOV)
        self.assertIn("静态演示构建：runtime 在构建时已禁用且没有 ESE 快照", ESE)
        self.assertIn("静态演示构建：runtime 在构建时已禁用，这里没有 observation 数据", PANEL)
        self.assertIn("runtimeAvailable", GOV)
        self.assertIn("runtimeAvailable", ESE)

    def test_empty_projects_tab_explains_itself(self):
        self.assertNotIn("if (!projects.length && !loading && !error) return null;", PANEL)
        self.assertIn("还没有登记项目实验链", PANEL)


if __name__ == "__main__":
    unittest.main()

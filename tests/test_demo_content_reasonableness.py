"""Content reasonableness of the demo, as opposed to its structure.

137 checked that every session *can* be opened and that numbers agree. This one
checks whether what the panels *say* is true of the task in front of the viewer.
The trigger was BRIEF's NEXT line, which assumed every task was still doing a
literature review:

  - the ESE repository study had already run 5132 commits and sealed an EA, yet
    BRIEF said "先跑文献调研，至少拿到可定位的 span";
  - an autopilot delegation printed CLAIM=signed and NEXT="claim 已签";
  - a writing task at S8-S12 was told to go back to retrieval;
  - a blocked task's STAGE read "自进化提案" because it used task.stage (where the
    task would go next) instead of the last stage it actually cleared.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL = (ROOT / "apps" / "web" / "src" / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
CLAIM = (ROOT / "apps" / "web" / "src" / "domain" / "claimSignature.ts").read_text(encoding="utf-8")


class BriefNextMatchesTaskState(unittest.TestCase):
    def setUp(self):
        start = PANEL.index("function briefNext")
        end = PANEL.index("function briefMarkdown")
        self.body = PANEL[start:end]

    def test_run_outranks_retrieval(self):
        # A completed run means the next human step is the claim, not more search.
        self.assertIn("if (task.run)", self.body)
        self.assertIn("RunCapsule 与 EA 已就位", self.body)

    def test_delegated_signature_is_not_reported_as_signed(self):
        self.assertIn('label.state === "signed-delegated"', self.body)
        self.assertIn("委托签，不是人签", self.body)

    def test_writing_task_does_not_go_back_to_retrieval(self):
        self.assertIn('task.mode === "writing"', self.body)
        self.assertIn("写作槽位 locked", self.body)

    def test_g1_is_stated_as_convergence_not_claim_signing(self):
        self.assertIn("G1 人工收敛", self.body)
        # The old line conflated the two gates: "G1 收敛与 claim 人工签署".
        self.assertNotIn("G1 收敛与 claim 人工签署", self.body)

    def test_the_old_span_only_branch_is_gone(self):
        self.assertNotIn("return task.coverage.spans > 0\n      ? \"证据已到 span 层", self.body)


class BriefStageDoesNotClaimUnreachedStages(unittest.TestCase):
    def test_blocked_tasks_use_the_last_cleared_stage(self):
        start = PANEL.index("function briefStage")
        end = PANEL.index("function briefBlockers")
        body = PANEL[start:end]
        self.assertIn('task.status === "blocked"', body)
        self.assertIn("task.completedStages", body)
        self.assertIn("sort((a, b) => b - a)[0]", body)


class ClaimKpiSeparatesHumanFromDelegated(unittest.TestCase):
    def test_label_exposes_a_kpi_word(self):
        self.assertIn('kpi: "none" | "unsigned" | "signed" | "delegated" | "demo"', CLAIM)
        self.assertEqual(CLAIM.count("kpi:"), 7, "one type + six return branches")

    def test_brief_uses_the_kpi_not_the_raw_status(self):
        self.assertIn("{claimLabel.kpi}", PANEL)
        self.assertIn("claimSignatureLabel(claim).kpi", PANEL)
        self.assertNotIn('`- claim: ${claim?.status ?? "none"}`', PANEL)


class BlockersIncludeNonGateBlockers(unittest.TestCase):
    def test_run_contract_is_a_reported_blocker(self):
        self.assertIn("function briefBlockers", PANEL)
        self.assertIn("RUN CONTRACT", PANEL)
        self.assertIn("/blocked/i.test(task.run.status)", PANEL)

    def test_both_brief_surfaces_use_one_helper(self):
        # JSX and the copied Markdown must not compute blockers twice.
        self.assertEqual(PANEL.count("const blockers = briefBlockers(task);"), 2)


class EvalEmptinessIsExplained(unittest.TestCase):
    def test_all_dash_baseline_has_a_reason(self):
        self.assertIn("const hasBaseline", PANEL)
        self.assertIn("还没有登记论文基线", PANEL)


class ProtocolRowDoesNotCallRealRunsDemo(unittest.TestCase):
    def test_replay_basis_is_consulted(self):
        start = PANEL.index("<b>G2 协议</b>")
        body = PANEL[start:start + 700]
        self.assertIn('task.replay?.basis === "real"', body)
        self.assertIn("run-capsule 绑定 protocol sha256", body)


class TaskSwitchShowsThatTasksOwnBrief(unittest.TestCase):
    def test_generic_flow_is_not_carried_across_tasks(self):
        store = (ROOT / "apps" / "web" / "src" / "state" / "workspaceStore.ts").read_text(encoding="utf-8")
        # Opening ESE must not leave the generic full-chain replay as the first
        # panel; an explicit tab choice must survive the switch. The selector was
        # later split across lines, so compare on collapsed whitespace instead of
        # assuming one line (the behaviour pinned here is unchanged).
        compact = " ".join(store.split())
        self.assertIn(
            'contextTab: task.messages.some((m) => m.stage) ? "flow" : state.ui.contextTab === "flow" ? "brief" : state.ui.contextTab',
            compact,
        )


if __name__ == "__main__":
    unittest.main()

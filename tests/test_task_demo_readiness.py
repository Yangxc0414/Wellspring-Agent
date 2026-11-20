"""Every seeded session must be demonstrable *and* internally consistent.

This pass started from one question: can each task in the sidebar actually be
walked through in a meeting? Probing the live DOM showed three kinds of failure
that reading the code alone had not caught:

  1. the ESE task's structured record said "not run / not sealed" while its S5
     gate said "EA immutable" and the transcript cited EA-65d32e114229;
  2. the run card was hard-coded for the perovskite T80 experiment, so any other
     task would have rendered its metric under a "MEAN T80 / h" heading;
  3. the two thesis examples ended on an agent fragment with no gate, so a
     presenter had nothing to point at.

These tests pin the fixes. They assert source-level contracts because the demo is
a static bundle; the browser checks for the same facts live in the review notes.
"""

import io
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = (ROOT / "apps" / "web" / "src" / "domain" / "seed.ts").read_text(encoding="utf-8")
CARD = (ROOT / "apps" / "web" / "src" / "components" / "ArtifactCard.tsx").read_text(encoding="utf-8")
PANEL = (ROOT / "apps" / "web" / "src" / "components" / "ContextPanel.tsx").read_text(encoding="utf-8")
FLOW = (ROOT / "apps" / "web" / "src" / "components" / "FlowDemo.tsx").read_text(encoding="utf-8")
TYPES = (ROOT / "apps" / "web" / "src" / "domain" / "types.ts").read_text(encoding="utf-8")


def block(start: str, end: str) -> str:
    i = SEED.index(start)
    j = SEED.index(end, i)
    return SEED[i:j]


class EseTaskIsDemonstrable(unittest.TestCase):
    """The ESE replay must not contradict itself on one screen."""

    def setUp(self):
        self.ese = block("export function seedEseStudy", "export function seedE2EClosedLoop")

    def test_run_record_matches_the_capsule_the_transcript_cites(self):
        # The transcript and the S5 gate both cite this capsule and EA. Leaving
        # `run: null` made EVIDENCE print "not run / not sealed" beside them.
        self.assertIn('id: "ESE-MS-20261118-03"', self.ese)
        self.assertIn('ea: "EA-65d32e114229"', self.ese)
        self.assertNotIn("run: null", self.ese)
        self.assertIn('metric: "test_cochange_rate"', self.ese)
        self.assertIn("mean: 0.3749", self.ese)

    def test_gates_are_monotonic(self):
        # A run cannot execute before G1/G2 are approved. Marking them
        # needs_human while S5 passed produced an impossible sequence and made
        # RUN display "WAIT G1" next to a sealed EA.
        self.assertIn('{ id: "G1", status: "pass"', self.ese)
        self.assertIn('{ id: "G2", status: "pass"', self.ese)
        self.assertIn('{ id: "S5", status: "pass"', self.ese)
        self.assertNotIn('{ id: "G1", status: "needs_human"', self.ese)
        self.assertNotIn('{ id: "G2", status: "needs_human"', self.ese)

    def test_claim_is_unsigned_not_invented_as_signed(self):
        self.assertIn('id: "CLM-ESE-01"', self.ese)
        self.assertIn('status: "unsigned"', self.ese)
        self.assertNotIn('status: "signed"', self.ese)

    def test_declares_a_real_replay_basis(self):
        self.assertIn('replay: { basis: "real", source: "runtime_data/ese-ms-20261118-03" }', self.ese)


class RunCardIsMetricDriven(unittest.TestCase):
    """The card must render whatever was measured, not assume T80 hours."""

    def test_headline_uses_the_recorded_metric(self):
        self.assertIn("MEAN · {card.metric}", CARD)
        self.assertNotIn("MEAN T80", CARD)

    def test_unit_is_opt_in(self):
        self.assertIn("card.unit ?", CARD)
        self.assertIn('Unit suffix ("h" for T80 hours)', TYPES)
        self.assertIn("unit?: string;", TYPES)

    def test_null_baseline_never_renders_a_delta(self):
        self.assertIn('card.baseline == null ? "—"', CARD)
        self.assertIn("delta == null", CARD)
        # The old implementation defaulted a missing baseline to 0, inventing a
        # delta for a run whose contract is blocked on min_delta.
        self.assertNotIn("card.baseline ?? 0", CARD)

    def test_note_is_per_run_so_real_readings_are_not_called_demo_data(self):
        self.assertIn("card.note ??", CARD)
        self.assertIn("note?: string;", TYPES)


class E2EHasNoFakeBaseline(unittest.TestCase):
    def test_blocked_contract_has_no_baseline_number(self):
        e2e = block("export function seedE2EClosedLoop", "export function seedFullChainDemo")
        self.assertIn("baseline: null", e2e)
        self.assertIn("min_delta", e2e)
        self.assertNotIn("baseline: 0,", e2e)

    def test_declares_fixture_basis(self):
        e2e = block("export function seedE2EClosedLoop", "export function seedFullChainDemo")
        self.assertIn('replay: { basis: "fixture"', e2e)


class ReplayBadgeIsDataDriven(unittest.TestCase):
    def test_panel_reads_the_declared_basis(self):
        self.assertIn('task.replay?.basis === "real"', PANEL)
        self.assertIn('"真实回放"', PANEL)
        self.assertIn('task.replay?.basis === "fixture"', PANEL)
        self.assertIn("FIXTURE · 真实执行", PANEL)

    def test_type_allows_the_three_bases(self):
        self.assertIn('basis: "real" | "fixture" | "demo"', TYPES)


class TeachingPanelNamesItsScope(unittest.TestCase):
    def test_generic_replay_is_announced_on_other_tasks(self):
        # Otherwise selecting the ESE task and opening 演示流程 narrates the
        # full-chain/self-improvement story as if it belonged to ESE.
        self.assertIn("isGenericReplay", FLOW)
        self.assertIn("全流程演示 · 通用模板（非当前任务）", FLOW)
        self.assertIn("不是这条任务的流程", FLOW)


class ThesisExamplesEndOnAGate(unittest.TestCase):
    """A demo fragment is not a demo: each example must stop at a gate."""

    def setUp(self):
        self.thesis = block("function seedThesisTask", "export function seedEseStudy")

    def test_writing_example_shows_locked_slots(self):
        self.assertIn("写作槽位保持 locked", self.thesis)
        self.assertIn('gate: "S8–S12"', self.thesis)

    def test_proposal_example_shows_the_g1_gate(self):
        self.assertIn("候选假设待人工收敛", self.thesis)
        self.assertIn('gate: "G1"', self.thesis)

    def test_examples_ask_a_question_first(self):
        self.assertIn("能不能直接开始", self.thesis)
        self.assertIn("怎么收敛", self.thesis)

    def test_writing_task_stage_progress_matches_its_header(self):
        # stage=6 with all stages pending made RUN say "NEXT S1" while the
        # header claimed S8–S12.
        self.assertIn('mode === "writing" && index < 6', self.thesis)


if __name__ == "__main__":
    unittest.main()

"""A claim may not be about a factor the package never varied."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from research_agent.search_lab import write_study_package
from research_agent.storage import read_json
from research_agent.study_claims import (
    build_study_claim,
    statement_arm_disclosure,
    statement_subject_check,
)

DESIGN = {
    "gate": [False, True],
    "memory": [False, True],
    "operators": ["all"],
    "min_delta": [0.005],
    "parent_selection": ["uniform"],
}
ASSERTIONS = [
    SimpleNamespace(metric="improvement_per_evaluation.iris.memory_on_gate_off"),
    SimpleNamespace(metric="improvement_per_evaluation.iris.memory_x_gate_interaction"),
]


class StatementSubjectUnitTest(unittest.TestCase):
    def _both(self, statement, design=DESIGN, assertions=ASSERTIONS):
        return statement_subject_check(statement, design, assertions)

    def test_a_fixed_factor_in_the_statement_is_refused(self):
        refusal, warning = self._both("在 iris 上，收窄变异算子空间降低了单位验证算力的改进率")
        self.assertIn("about operators", refusal)
        self.assertIn("single level", refusal)
        self.assertIn("gate, memory", refusal)
        self.assertEqual(warning, "")

    def test_an_english_statement_is_refused_the_same_way(self):
        refusal, _ = self._both("narrowing the operator space lowered improvement per evaluation")
        self.assertIn("operators", refusal)

    def test_a_varied_and_asserted_factor_passes(self):
        refusal, warning = self._both("在 iris 上，开启接受门控提高了单位验证算力的改进率")
        self.assertEqual(refusal, "")
        self.assertEqual(warning, "")

    def test_archive_window_is_not_misread_as_archive(self):
        refusal, warning = self._both(
            "在 iris 上，档案窗口越窄改进率越高",
            {"archive_window": [1, 2, 4], "gate": [False, True]},
            [SimpleNamespace(metric="improvement_per_evaluation.iris.archive_window_1_gate_on")],
        )
        self.assertEqual((refusal, warning), ("", ""))

    def test_a_named_factor_with_no_decidable_comparison_is_refused(self):
        refusal, _ = self._both(
            "在 iris 上，记忆改变了单位验证算力的改进率",
            DESIGN,
            [SimpleNamespace(metric="improvement_per_evaluation.iris.gate_main_effect")],
        )
        self.assertIn("no decidable comparison", refusal)

    def test_naming_nothing_warns_instead_of_passing_silently(self):
        refusal, warning = self._both("本研究表明搜索效率整体提升")
        self.assertEqual(refusal, "")
        self.assertIn("names none of the factors", warning)


class ClaimDraftEnforcementTest(unittest.TestCase):
    """The guard must fire on the command path, not only in the unit.

    Order matters and is deliberate: "this package decided nothing" is a strictly prior condition,
    so a package with no decidable comparison is refused by that check before the subject is read.
    These tests therefore use a configuration that does decide something (16 paired seeds), the
    same shape as the package where the defect was found.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _decidable_package(self, name: str) -> Path:
        directory = self.root / name
        write_study_package(directory, dataset="iris", seeds=list(range(1, 17)), budget=60)
        self.assertTrue(
            (directory / "study-evidence.json").is_file(), "the fixture package did not run"
        )
        return directory

    def test_a_claim_about_an_unexecuted_control_is_refused_on_the_command_path(self):
        directory = self._decidable_package("study")
        spec = json.loads((directory / "study-spec.json").read_text(encoding="utf-8"))
        # a default run records the whole normalized design, and operators sits in it at one level
        self.assertEqual(spec["design"]["operators"], ["all"])
        self.assertEqual(len(spec["design"]["gate"]), 2)
        with self.assertRaises(ValueError) as raised:
            build_study_claim(
                directory,
                "在 iris 上，收窄变异算子空间降低了单位验证算力的改进率",
                "read the paired intervals",
                "S5/guard/iris",
            )
        self.assertIn("operators", str(raised.exception))
        self.assertFalse(
            (directory / "claim-draft.json").is_file(),
            "a refused statement must not leave a draft behind",
        )

    def test_a_statement_about_a_varied_factor_still_drafts(self):
        directory = self._decidable_package("study-ok")
        result = build_study_claim(
            directory,
            "在 iris 上，开启接受门控提高了单位验证算力的改进率",
            "read the paired intervals and the lineage log",
            "S5/guard/iris",
        )
        self.assertEqual(result["status"], "draft")
        self.assertGreaterEqual(result["signable_assertions"], 1)
        draft = json.loads((directory / "claim-draft.json").read_text(encoding="utf-8"))
        self.assertFalse(
            any("names none of the factors" in item for item in draft["warnings"]),
            "a statement that names a varied factor must not be warned about its subject",
        )


if __name__ == "__main__":
    unittest.main()


class StatementArmDisclosureTest(unittest.TestCase):
    """Factor coverage is not arm coverage: the memory-alone arm and memory-plus-gate differ."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    VERDICTS = [
        {"comparison": "memory_on_gate_on", "state": "negative"},
        {"comparison": "memory_x_gate_interaction", "state": "negative"},
        {"comparison": "memory_on_gate_off", "state": "undecidable"},
        {"comparison": "memory_off_gate_on", "state": "undecidable"},
    ]

    def test_a_decided_arm_does_not_cover_an_undecided_arm_of_the_same_factor(self):
        note = statement_arm_disclosure(
            "on wine, memory alone raises improvement per validation evaluation", self.VERDICTS
        )
        self.assertIn("memory: decided in memory_on_gate_on", note)
        self.assertIn("memory_on_gate_off", note)
        self.assertIn("not covered by a decision about another arm", note)

    def test_a_statement_without_a_named_factor_gets_no_arm_note(self):
        self.assertEqual(statement_arm_disclosure("the protocol behaves as designed", self.VERDICTS), "")

    def test_a_fully_decided_factor_gets_no_arm_note(self):
        verdicts = [
            {"comparison": "memory_on_gate_on", "state": "negative"},
            {"comparison": "memory_on_gate_off", "state": "positive"},
        ]
        self.assertEqual(statement_arm_disclosure("memory changes the rate", verdicts), "")

    def test_the_claim_carries_the_arm_note_as_a_warning(self):
        directory = self.root / "study-arm"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 17)), budget=60)
        claim = build_study_claim(
            directory,
            "on iris, memory alone raises improvement per validation evaluation",
            "checked the paired intervals",
            "S5/armtest/iris",
        )
        draft = read_json(directory / "claim-draft.json") or {}
        notes = [w for w in draft.get("warnings") or [] if "not covered by a decision" in w]
        self.assertEqual(len(notes), 1, draft.get("warnings"))
        self.assertIn("memory: decided in", notes[0])

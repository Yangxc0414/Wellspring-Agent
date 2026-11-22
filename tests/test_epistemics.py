"""design/179: 认识论声明与推论判定。

钉住三件事：
1. 每个方法必须声明 evidence_form / inference_rule / 带 citation 的约束；
   "多来源"规则若只要求 1 个来源，是自相矛盾，必须拒绝。
2. 非统计形态（模式匹配/主题综合/设计循环/描述）能真正判定，
   case-study 的两个案例可以支撑 claim，且不需要 RunCapsule。
3. 判定是只读的：不签署、不改输入。
"""

import copy
import unittest

from research_agent.epistemics import (
    EpistemicsError,
    claim_support_check,
    constraints_for,
    load_epistemics,
    validate_epistemics,
)


class EpistemicsDeclarationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.epistemics = load_epistemics()

    def test_every_method_declares_evidence_form_and_rule(self):
        for method_id, entry in self.epistemics["methods"].items():
            self.assertTrue(entry["evidence_form"]["hashable"], method_id)
            self.assertTrue(entry["rule_detail"], method_id)
            self.assertGreaterEqual(entry["min_independent_sources"], 1, method_id)
            self.assertTrue(entry["constraints"], method_id)

    def test_every_constraint_carries_a_citation(self):
        for method_id, entry in self.epistemics["methods"].items():
            for constraint in entry["constraints"]:
                self.assertTrue(
                    constraint["citation"].strip(),
                    "%s/%s has no methodological source" % (method_id, constraint["id"]),
                )

    def test_placeholder_citation_is_rejected(self):
        broken = copy.deepcopy(self.epistemics)
        broken["methods"]["case-study"]["constraints"][0]["citation"] = "TODO"
        with self.assertRaises(EpistemicsError):
            validate_epistemics(broken)

    def test_multi_source_rule_with_one_source_is_rejected(self):
        broken = copy.deepcopy(self.epistemics)
        broken["methods"]["case-study"]["min_independent_sources"] = 1
        with self.assertRaises(EpistemicsError):
            validate_epistemics(broken)

    def test_constraint_on_uncovered_stage_is_rejected(self):
        broken = copy.deepcopy(self.epistemics)
        broken["methods"]["case-study"]["constraints"][0]["stage"] = "S2-S3"
        with self.assertRaises(EpistemicsError):
            validate_epistemics(broken)

    def test_missing_method_is_rejected(self):
        broken = copy.deepcopy(self.epistemics)
        broken["methods"].pop("survey")
        with self.assertRaises(EpistemicsError):
            validate_epistemics(broken)

    def test_constraints_are_queryable_by_stage(self):
        found = constraints_for(self.epistemics, "case-study", stage="S5")
        self.assertTrue(found)
        self.assertTrue(all(item["stage"] == "S5" for item in found))


class ClaimSupportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.epistemics = load_epistemics()

    def _case_evidence(self):
        return [
            {"evidence_id": "E1", "source_id": "case-A", "kind": "interview", "pattern_id": "p1"},
            {"evidence_id": "E2", "source_id": "case-A", "kind": "document", "pattern_id": "p1"},
            {"evidence_id": "E3", "source_id": "case-B", "kind": "interview", "pattern_id": "p1"},
        ]

    def test_case_study_supports_a_pattern_claim_without_a_run_capsule(self):
        result = claim_support_check(
            "case-study", evidence_items=self._case_evidence(), epistemics=self.epistemics
        )
        self.assertTrue(result["supported"])
        self.assertEqual(result["rule"], "pattern-match")
        self.assertEqual(result["evidence_form"], "case-corpus")
        self.assertEqual(result["observed_sources"], 2)

    def test_single_case_cannot_support_a_pattern_claim(self):
        one = [item for item in self._case_evidence() if item["source_id"] == "case-A"]
        result = claim_support_check("case-study", evidence_items=one, epistemics=self.epistemics)
        self.assertFalse(result["supported"])
        self.assertIn(">=2 independent sources", result["blockers"][0])

    def test_pattern_claim_needs_two_kinds_of_evidence(self):
        only_interviews = [
            {"source_id": "case-A", "kind": "interview", "pattern_id": "p1"},
            {"source_id": "case-B", "kind": "interview", "pattern_id": "p1"},
        ]
        result = claim_support_check(
            "case-study", evidence_items=only_interviews, epistemics=self.epistemics
        )
        self.assertFalse(result["supported"])
        self.assertTrue(any("triangulation" in item for item in result["blockers"]))

    def test_mixing_two_patterns_in_one_claim_is_rejected(self):
        mixed = self._case_evidence() + [
            {"source_id": "case-C", "kind": "document", "pattern_id": "p2"}
        ]
        result = claim_support_check("case-study", evidence_items=mixed, epistemics=self.epistemics)
        self.assertFalse(result["supported"])
        self.assertTrue(any("pattern_id" in item for item in result["blockers"]))

    def test_statistical_rule_requires_passing_assertions(self):
        empty = claim_support_check(
            "controlled-experiment", evidence_items=[], assertions=[], epistemics=self.epistemics
        )
        self.assertFalse(empty["supported"])
        passing = claim_support_check(
            "controlled-experiment",
            evidence_items=[],
            assertions=[{"metric": "accuracy", "status": "pass"}],
            epistemics=self.epistemics,
        )
        self.assertTrue(passing["supported"])
        failing = claim_support_check(
            "controlled-experiment",
            evidence_items=[],
            assertions=[{"metric": "accuracy", "status": "fail"}],
            epistemics=self.epistemics,
        )
        self.assertFalse(failing["supported"])

    def test_thematic_synthesis_counts_independent_studies(self):
        two = [
            {"evidence_id": "S1", "source_id": "study-1", "kind": "document", "theme_id": "t1"},
            {"evidence_id": "S2", "source_id": "study-2", "kind": "document", "theme_id": "t1"},
        ]
        self.assertTrue(
            claim_support_check(
                "systematic-literature-review", evidence_items=two, epistemics=self.epistemics
            )["supported"]
        )
        one = two[:1]
        self.assertFalse(
            claim_support_check(
                "systematic-literature-review", evidence_items=one, epistemics=self.epistemics
            )["supported"]
        )

    def test_design_cycle_requires_a_bound_evaluation(self):
        no_eval = [
            {"evidence_id": "A1", "source_id": "proj", "kind": "artifact"}
        ]
        self.assertFalse(
            claim_support_check("design-science", evidence_items=no_eval, epistemics=self.epistemics)[
                "supported"
            ]
        )
        bound = no_eval + [
            {"evidence_id": "V1", "source_id": "proj", "kind": "evaluation", "artifact_id": "A1"}
        ]
        self.assertTrue(
            claim_support_check("design-science", evidence_items=bound, epistemics=self.epistemics)[
                "supported"
            ]
        )
        unbound = no_eval + [
            {"evidence_id": "V2", "source_id": "proj", "kind": "evaluation", "artifact_id": "A9"}
        ]
        self.assertFalse(
            claim_support_check("design-science", evidence_items=unbound, epistemics=self.epistemics)[
                "supported"
            ]
        )

    def test_descriptive_rule_refuses_to_generalise(self):
        items = [{"source_id": "r1", "kind": "measurement"}]
        self.assertTrue(
            claim_support_check("survey", evidence_items=items, epistemics=self.epistemics)["supported"]
        )
        generalised = claim_support_check(
            "survey", evidence_items=items, generalises=True, epistemics=self.epistemics
        )
        self.assertFalse(generalised["supported"])
        self.assertTrue(any("generalise" in item for item in generalised["blockers"]))

    def test_check_is_read_only(self):
        items = self._case_evidence()
        before = copy.deepcopy(items)
        claim_support_check("case-study", evidence_items=items, epistemics=self.epistemics)
        self.assertEqual(items, before)


if __name__ == "__main__":
    unittest.main()

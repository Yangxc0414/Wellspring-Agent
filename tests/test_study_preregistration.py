import json
import tempfile
import unittest
from pathlib import Path

from research_agent.storage import read_json, write_json_atomic
from research_agent.study_preregistration import (
    PREREG_SCHEMA,
    PreregistrationError,
    assert_matches_run,
    bind_sidecar,
    check_preregistration,
    load_preregistration,
)

PREREG = {
    "schema_version": PREREG_SCHEMA,
    "question": "Does the archive help?",
    "hypothesis": "It helps only with memory off.",
    "analysis": "paired interaction interval",
    "decision_rule": "claim only if the interval excludes zero",
    "design": {"archive": ["off", "negative"]},
    "seeds": [1, 2, 3, 4],
    "budget": 60,
    "dataset": "iris",
}


class StudyPreregistrationTest(unittest.TestCase):
    def test_a_declared_plan_binds_to_a_study_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json_atomic(root / "prereg.json", PREREG)
            prereg = load_preregistration(root / "prereg.json")
            self.assertEqual(prereg["dataset"], "iris")
            study = {
                "study_sha256": "study-hash",
                "design": {"archive": ["off", "negative"], "gate": [True]},
            }
            bind_sidecar(root, prereg, study)
            self.assertTrue(check_preregistration(root, study)["bound"])

            sidecar = read_json(root / "study-preregistration.json")
            sidecar["study_sha256"] = "other"
            write_json_atomic(root / "study-preregistration.json", sidecar)
            check = check_preregistration(root, study)
            self.assertFalse(check["bound"])
            self.assertIn("study hash", check["reason"])

    def test_a_plan_that_does_not_match_the_run_is_refused(self):
        with self.assertRaises(PreregistrationError):
            assert_matches_run(
                PREREG, design={"archive": ["off"]}, seeds=[1, 2, 3, 4], budget=60,
                dataset="iris",
            )
        with self.assertRaises(PreregistrationError):
            assert_matches_run(
                PREREG, design={"archive": ["off", "negative"]}, seeds=[1, 2, 3],
                budget=60, dataset="iris",
            )
        with self.assertRaises(PreregistrationError):
            assert_matches_run(
                PREREG, design={"archive": ["off", "negative"]}, seeds=[1, 2, 3, 4],
                budget=30, dataset="iris",
            )

    def test_missing_fields_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            bad = dict(PREREG)
            bad.pop("decision_rule")
            write_json_atomic(path, bad)
            with self.assertRaises(PreregistrationError):
                load_preregistration(path)

    def test_absent_sidecar_is_not_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            check = check_preregistration(Path(tmp), {"study_sha256": "x", "design": {}})
            self.assertFalse(check["present"])
            self.assertIn("no study-preregistration.json", check["reason"])


if __name__ == "__main__":
    unittest.main()


class ScaffoldTest(unittest.TestCase):
    """A form is not a pre-registration, and the loader has to tell the two apart."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _scaffold(self):
        from research_agent.study_preregistration import scaffold, unfilled_fields

        plan = scaffold({"gate": [False, True]}, [1, 2, 3, 4], 40, "iris")
        return plan, unfilled_fields(plan)

    def test_the_scaffold_fills_facts_and_leaves_the_promises_blank(self):
        plan, unfilled = self._scaffold()
        self.assertEqual(plan["schema_version"], PREREG_SCHEMA)
        self.assertEqual(plan["dataset"], "iris")
        self.assertEqual(plan["seeds"], [1, 2, 3, 4])
        self.assertEqual(plan["budget"], 40)
        self.assertEqual(plan["design"]["gate"], [False, True])
        self.assertEqual(
            unfilled, ["question", "hypothesis", "analysis", "decision_rule", "baseline.why"]
        )

    def test_an_untouched_scaffold_is_refused_and_names_every_placeholder(self):
        plan, _ = self._scaffold()
        path = self.root / "untouched.json"
        write_json_atomic(path, plan)
        with self.assertRaises(PreregistrationError) as raised:
            load_preregistration(path)
        message = str(raised.exception)
        self.assertIn("scaffolded and never written", message)
        for field in ("question", "hypothesis", "analysis", "decision_rule", "baseline.why"):
            self.assertIn(field, message)

    def test_a_written_scaffold_loads_and_still_matches_the_run_it_declares(self):
        plan, _ = self._scaffold()
        for field in ("question", "hypothesis", "analysis", "decision_rule"):
            plan[field] = "declared before the run: %s" % field
        plan["baseline"]["why"] = "grid-tuned cross-validation spent real fitting budget"
        path = self.root / "written.json"
        write_json_atomic(path, plan)
        loaded = load_preregistration(path)
        assert_matches_run(
            loaded, design=plan["design"], seeds=[1, 2, 3, 4], budget=40, dataset="iris"
        )
        self.assertEqual(loaded["dataset"], "iris")

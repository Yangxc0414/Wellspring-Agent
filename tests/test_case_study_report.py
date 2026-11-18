"""Case-study codings: coverage, enum validation and descriptive counts."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.case_study_report as report  # noqa: E402

ATLAS = ROOT / "research_agent" / "failures" / "atlas.json"
CODINGS = ROOT / "research_agent" / "eval" / "case_study_codings.json"


class CaseStudyValidationTest(unittest.TestCase):
    def test_repository_codings_cover_the_atlas(self):
        atlas, codings = report.load_codings(ATLAS, CODINGS)
        self.assertEqual(len(atlas["entries"]), len(codings["cases"]))
        summary = report.summarise(atlas, codings)
        self.assertEqual(summary["n"], 6)
        self.assertEqual(summary["regression_rate"], 0.833)

    def _write(self, tmp, name, payload):
        path = tmp / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _fixture(self, tmp, cases):
        atlas = self._write(tmp, "atlas.json", {"schema": "failure-atlas-0.1", "entries": [
            {"failure_id": "F1", "kind": "leakage", "scope": "s", "observed": "o", "diagnosis": "d", "retry_condition": "r"},
            {"failure_id": "F2", "kind": "underpowered", "scope": "s", "observed": "o", "diagnosis": "d", "retry_condition": "r"},
        ]})
        codings = self._write(tmp, "codings.json", {
            "schema": "case-study-codings-0.1",
            "study_id": "CS-T",
            "protocol": {"research_questions": ["rq"], "case_selection": "all", "data_sources": ["atlas"], "ethics": "none"},
            "cases": cases,
        })
        return atlas, codings

    def test_missing_coding_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            atlas, codings = self._fixture(Path(tmp), [{
                "failure_id": "F1", "detection_mechanism": "real_model_run",
                "fix_type": "code", "regression_test": "yes",
            }])
            with self.assertRaises(report.CaseStudyError):
                report.load_codings(atlas, codings)

    def test_unknown_failure_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            atlas, codings = self._fixture(Path(tmp), [
                {"failure_id": "F1", "detection_mechanism": "real_model_run", "fix_type": "code", "regression_test": "yes"},
                {"failure_id": "F3", "detection_mechanism": "real_model_run", "fix_type": "code", "regression_test": "yes"},
            ])
            with self.assertRaises(report.CaseStudyError):
                report.load_codings(atlas, codings)

    def test_bad_enum_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            atlas, codings = self._fixture(Path(tmp), [
                {"failure_id": "F1", "detection_mechanism": "vibes", "fix_type": "code", "regression_test": "yes"},
                {"failure_id": "F2", "detection_mechanism": "real_model_run", "fix_type": "code", "regression_test": "yes"},
            ])
            with self.assertRaises(report.CaseStudyError):
                report.load_codings(atlas, codings)

    def test_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            atlas, codings = self._fixture(Path(tmp), [
                {"failure_id": "F1", "stage": "S1", "detection_mechanism": "real_model_run", "fix_type": "code", "regression_test": "yes"},
                {"failure_id": "F2", "stage": "S4", "detection_mechanism": "heldout_rubric", "fix_type": "docs", "regression_test": "no"},
            ])
            summary = report.summarise(*report.load_codings(atlas, codings))
        self.assertEqual(summary["detection"], {"heldout_rubric": 1, "real_model_run": 1})
        self.assertEqual(summary["fix_type"], {"code": 1, "docs": 1})
        self.assertEqual(summary["regression_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()

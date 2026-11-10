"""A rubric mixes requirements on files with instructions for the submission act.

Measured on the ACL submission profile over a full-chain study package: 14 of 38 items covered, but
10 of the 24 missing rows were OpenReview forms, page limits and archive naming, which no artifact
on disk can satisfy. The split is reported next to the head ratio, never instead of it.
"""

import tempfile
import unittest
from pathlib import Path

from research_agent.pack_audit import coverage_input
from research_agent.skill_packs import coverage_report

STAGE = "submission"


def _rows(report):
    return {row["id"]: row for row in report["rows"]}


class ProceduralSplitTest(unittest.TestCase):
    ITEMS = [
        {"id": "budget", "text": "report the compute budget", "stage": STAGE},
        {"id": "baseline", "text": "name the tuned baseline", "stage": STAGE},
        {"id": "rule", "text": "state the stopping rule", "stage": STAGE},
        {
            "id": "pii",
            "text": "describe the scanning and anonymization steps actually performed",
            "stage": STAGE,
        },
        {
            "id": "form",
            "text": "upload the supplement as a .zip through the OpenReview form",
            "stage": STAGE,
        },
    ]

    def test_the_split_partitions_without_removing_any_item(self):
        report = coverage_report(self.ITEMS, "we report the compute budget", STAGE)
        self.assertEqual(report["items"], 5)
        self.assertEqual(
            report["items"], report["artifact_items"] + report["procedural_items"]
        )
        self.assertEqual(
            report["covered"], report["artifact_covered"] + report["procedural_covered"]
        )
        self.assertEqual(
            report["missing"], report["artifact_missing"] + report["procedural_missing"]
        )

    def test_an_artifact_requirement_about_anonymization_is_not_reclassified(self):
        # The flattering failure mode is a classifier wide enough to rebrand a real gap as paperwork.
        report = coverage_report(self.ITEMS, "nothing at all here", STAGE)
        rows = _rows(report)
        self.assertFalse(rows["pii"]["procedural_like"])
        self.assertTrue(rows["form"]["procedural_like"])
        self.assertEqual(rows["form"]["status"], "missing")

    def test_the_warning_names_the_split_the_head_ratio_hides(self):
        report = coverage_report(
            self.ITEMS,
            "report the compute budget name the tuned baseline state the stopping rule",
            STAGE,
        )
        self.assertEqual(report["artifact_items"], 4)
        self.assertEqual(report["artifact_covered"], 3)
        self.assertAlmostEqual(report["artifact_ratio"], 0.75)
        notes = [w for w in report["warnings"] if "mixed denominator" in w]
        self.assertEqual(len(notes), 1)
        self.assertIn("understates", notes[0])

    def test_matching_a_submission_instruction_is_reported_as_overstatement(self):
        report = coverage_report(
            self.ITEMS, "we zip the supplement and upload it on openreview", STAGE
        )
        self.assertTrue(_rows(report)["form"]["covered"])
        notes = [w for w in report["warnings"] if "mixed denominator" in w]
        self.assertEqual(len(notes), 1)
        self.assertIn("overstates", notes[0])


class RatioGranularityTest(unittest.TestCase):
    """A seven-item rubric makes one item worth fourteen headline points."""

    ITEMS = [
        {"id": str(index), "text": "requirement %d about reporting variance" % index, "stage": "design"}
        for index in range(7)
    ]

    def test_a_small_but_not_thin_rubric_reports_what_one_item_is_worth(self):
        report = coverage_report(self.ITEMS, "reporting variance", "design")
        self.assertEqual(report["items"], 7)
        self.assertFalse(report["thin_denominator"])
        self.assertAlmostEqual(report["ratio_granularity_points"], 14.3)
        notes = [w for w in report["warnings"] if "ratio granularity" in w]
        self.assertEqual(len(notes), 1)

    def test_a_fine_grained_rubric_is_not_flagged(self):
        items = [
            {"id": str(index), "text": "requirement %d names the compute budget" % index,
             "stage": "design"}
            for index in range(25)
        ]
        report = coverage_report(items, "nothing at all here", "design")
        self.assertEqual(report["ratio_granularity_points"], 4.0)
        self.assertFalse([w for w in report["warnings"] if "ratio granularity" in w])


class ReleasedDataDisclosureTest(unittest.TestCase):
    """Released outputs are data: named in the manifest of the scored input, never scored, never
    silently dropped. A rubric item asks whether they exist, so absence of mention would be a lie."""

    def test_a_csv_is_listed_without_its_numbers_entering_the_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("we report the compute budget", encoding="utf-8")
            (root / "outputs-per-seed.csv").write_text("seed,score\n1,0.5\n2,0.6\n", encoding="utf-8")
            text, meta = coverage_input(root)
        bundle = meta["bundle"]
        self.assertNotIn("0.5", text)
        self.assertEqual([row["path"] for row in bundle["data_files"]], ["outputs-per-seed.csv"])
        self.assertEqual(bundle["data_files"][0]["lines"], 3)
        self.assertEqual(bundle["skipped_unsupported_suffix"], 0)


if __name__ == "__main__":
    unittest.main()

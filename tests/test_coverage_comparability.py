"""A coverage ratio must carry its base, and `covered` must not hide a partial match.

Both were measured defects, not hypothetical ones: the AAAI/design item "Report uncertainty,
variance, and statistical tests when small differences matter" was reported covered on the
strength of report/uncertainty/variance while we deliberately run no statistical test; and the
same study design scored 0/14 or 8/14 depending on which build printed its README and whether the
bundle mixed scripts, so two quoted numbers were not comparable. These tests pin the disclosure.
They must not change any score: `covered`, `overlap` and the thresholds stay exactly as they were.
"""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.pack_audit import artifact_base, coverage_input
from research_agent.skill_packs import coverage_report, demand_phrases


def item(text, stage="design"):
    return {"text": text, "stage": stage, "actionable": True, "source": "s", "heading": "h"}


class DemandPhraseTest(unittest.TestCase):
    def test_a_conjoined_sentence_splits_into_its_demands(self):
        phrases = demand_phrases(
            "Report uncertainty, variance, and statistical tests when small differences matter"
        )
        self.assertEqual(len(phrases), 3)
        self.assertTrue(any("statistical" in phrase for phrase in phrases), phrases)

    def test_semicolons_split_too_and_empties_are_dropped(self):
        self.assertEqual(
            len(demand_phrases("Freeze contribution; baselines; ablations")), 3
        )
        self.assertEqual(demand_phrases(""), [])
        self.assertEqual(demand_phrases("and or , ;"), [])


class PartialMatchDisclosureTest(unittest.TestCase):
    def test_a_covered_row_says_which_demand_it_never_met(self):
        report = coverage_report(
            [item("Report uncertainty, variance, and statistical tests")],
            "we report uncertainty and variance across seeds",
            stage="design",
        )
        row = report["rows"][0]
        self.assertTrue(row["covered"], "the fixture no longer reproduces the measured case")
        self.assertEqual(row["demands"], 3)
        self.assertEqual(row["matched_demands"], 2)
        self.assertEqual(row["unmet_demand_phrases"], ["statistical tests"])
        self.assertEqual(report["comparability"]["partial_matches"], 1)

    def test_a_missing_row_can_still_have_matched_most_of_its_demands(self):
        # the longer sentence sits at overlap 0.333 against a 0.34 threshold, so it reads as
        # missing while two of its three demands are present: the demand split is the only thing
        # that shows the reader how close to the line the item is, and that the line is arbitrary
        report = coverage_report(
            [item("Report uncertainty, variance, and statistical tests when small differences matter")],
            "we report uncertainty and variance across seeds",
            stage="design",
        )
        row = report["rows"][0]
        self.assertFalse(row["covered"])
        self.assertEqual(row["overlap"], 0.333)
        self.assertEqual(row["demands"], 3)
        self.assertEqual(row["matched_demands"], 2)
        self.assertEqual(report["comparability"]["partial_matches"], 0)

    def test_a_fully_matched_row_reports_no_unmet_phrase(self):
        report = coverage_report(
            [item("Report uncertainty, variance, and statistical tests")],
            "we report uncertainty, variance and statistical tests",
            stage="design",
        )
        row = report["rows"][0]
        self.assertEqual(row["matched_demands"], row["demands"])
        self.assertEqual(row["unmet_demand_phrases"], [])
        self.assertEqual(report["comparability"]["partial_matches"], 0)

    def test_every_row_carries_the_demand_keys_including_unmatched_ones(self):
        report = coverage_report(
            [item("Report uncertainty and variance"), item("and or the")],
            "we report uncertainty and variance",
            stage="design",
        )
        self.assertEqual(report["rows"][1]["status"], "unmatched")
        for row in report["rows"]:
            for key in ("demands", "matched_demands", "unmet_demand_phrases"):
                self.assertIn(key, row)

    def test_the_disclosure_does_not_move_any_score(self):
        text = "we report uncertainty and variance across seeds"
        items = [item("Report uncertainty, variance, and statistical tests when small differences matter")]
        with_base = coverage_report(items, text, stage="design", artifact={"path": "p"})
        without = coverage_report(items, text, stage="design")
        for key in ("covered", "missing", "items", "threshold", "artifact_ratio", "overlap"):
            if key == "overlap":
                self.assertEqual(with_base["rows"][0][key], without["rows"][0][key])
            else:
                self.assertEqual(with_base[key], without[key], key)


class ComparabilityBaseTest(unittest.TestCase):
    def test_slots_the_caller_cannot_fill_are_named_unknown_not_dropped(self):
        report = coverage_report([item("Report uncertainty")], "uncertainty", stage="design")
        base = report["comparability"]
        self.assertEqual(base["artifact_fingerprint"], "unknown")
        self.assertEqual(base["artifact_path"], "unknown")
        self.assertEqual(base["artifact_generated_at"], "unknown")
        self.assertIn("scored items 1 of 1 scanned", base["denominator"])

    def test_a_supplied_base_is_carried_through(self):
        report = coverage_report(
            [item("Report uncertainty")], "uncertainty", stage="design",
            artifact={"path": "pkg", "fingerprint": "abc123", "generated_at": "2026-11-05",
                      "language": "monolingual"},
        )
        base = report["comparability"]
        self.assertEqual(base["artifact_fingerprint"], "abc123")
        self.assertEqual(base["artifact_generated_at"], "2026-11-05")
        self.assertEqual(report["schema_version"], "skill-pack-coverage-0.4")

    def test_quote_as_carries_the_ratio_and_its_base_in_one_line(self):
        report = coverage_report(
            [item("Report uncertainty"), item("Report variance")],
            "uncertainty", stage="design", artifact={"path": "pkg", "fingerprint": "abc123"},
        )
        quoted = report["quote_as"]
        for fragment in ("coverage 1/2", "threshold", "confidence=", "pkg", "abc123"):
            self.assertIn(fragment, quoted)


class ArtifactBaseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _manifest(self, **fields):
        payload = {"schema_version": "study-package-manifest-0.2"}
        payload.update(fields)
        (self.root / "MANIFEST.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_the_generating_build_and_the_current_one_are_both_read(self):
        self._manifest(code_fingerprint_recorded="old111", code_fingerprint_now="new222")
        base = artifact_base(self.root)
        self.assertEqual(base["fingerprint"], "old111")
        self.assertEqual(base["fingerprint_now"], "new222")
        self.assertEqual(base["language"], "monolingual")

    def test_a_bundle_that_quotes_another_script_says_so(self):
        self._manifest(code_fingerprint_recorded="old111", foreign_script_fields=["baseline.why"])
        base = artifact_base(self.root)
        self.assertEqual(base["foreign_script_fields"], 1)
        self.assertEqual(base["language"], "mixed-script")

    def test_no_manifest_means_empty_slots_rather_than_invented_ones(self):
        base = artifact_base(self.root)
        self.assertEqual(base["fingerprint"], "")
        self.assertEqual(base["language"], "")

    def test_a_broken_manifest_is_not_fatal(self):
        (self.root / "MANIFEST.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(artifact_base(self.root)["fingerprint"], "")

    def test_coverage_input_attaches_the_base_for_a_bundle_only(self):
        self._manifest(code_fingerprint_recorded="old111")
        (self.root / "README.md").write_text("uncertainty", encoding="utf-8")
        _, fields = coverage_input(self.root)
        self.assertEqual(fields["artifact_base"]["fingerprint"], "old111")
        # a single file is not a bundle and must not start carrying bundle metadata; its path is
        # already reported by every caller as `input`
        _, single = coverage_input(self.root / "README.md")
        self.assertEqual(single, {})


if __name__ == "__main__":
    unittest.main()

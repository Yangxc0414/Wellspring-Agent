"""Number provenance: trace decimals byte-identically, refuse to certify counts by presence."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.cli import main
from research_agent.number_provenance import (
    build_provenance,
    draft_numbers,
    provenance_for_draft,
)


class NumberProvenanceTest(unittest.TestCase):
    def test_full_precision_token_is_never_split(self):
        # the ad-hoc version of this check truncated "-0.502872" to "0.5028" and invented
        # seventeen "unsourced" numbers; one token per number, sign and all decimals
        classes = draft_numbers("iris -0.406510 [-0.502872,-0.310149] 和 +0.074262 共 107 个")
        self.assertIn("-0.502872", classes["decimals"])
        self.assertIn("+0.074262", classes["decimals"])
        self.assertNotIn("0.5028", classes["decimals"])
        self.assertIn("107", classes["counts"])

    def test_decimal_is_traced_and_count_is_never_certified(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            (corpus / "studies").mkdir(parents=True)
            (corpus / "studies" / "study.json").write_text(
                json.dumps({"auc": -0.40651, "low_power": 107}), encoding="utf-8"
            )
            result = build_provenance(
                "raw 交互判定为负：iris -0.40651；107 个低功效判定", corpus
            )
            self.assertEqual(result["decimals_traced"], 1)
            self.assertEqual(result["decimals_untraced"], [])
            self.assertEqual(result["counts_certified"], 0)
            self.assertGreaterEqual(result["counts_total"], 1)
            self.assertIn("re-running the recorded command", result["boundary"])

    def test_a_value_absent_from_the_corpus_reports_a_missing_trace_not_a_fabrication(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            corpus.mkdir()
            (corpus / "a.json").write_text(json.dumps({"x": 0.1}), encoding="utf-8")
            result = build_provenance("we report -0.987654", corpus)
            self.assertEqual(result["decimals_untraced"], ["-0.987654"])
            self.assertTrue(any("missing trace" in w for w in result["warnings"]))

    def test_scan_budget_is_part_of_the_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            corpus.mkdir()
            for index in range(4):
                (corpus / ("f%d.json" % index)).write_text(
                    json.dumps({"v": 0.5 + index}), encoding="utf-8"
                )
            result = build_provenance("we report 3.5", corpus, max_files=2)
            self.assertEqual(result["files_scanned"], 2)
            self.assertEqual(result["files_over_budget"], 2)
            self.assertTrue(
                any("--max-files" in w for w in result["warnings"]),
                "a truncated corpus must not read as a full sweep",
            )

    def test_a_value_whose_only_home_is_the_draft_folder_is_not_counted_as_sourced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "paper"
            paper.mkdir()
            study = root / "studies"
            study.mkdir()
            (study / "study.json").write_text(
                json.dumps({"auc": -0.40651}), encoding="utf-8"
            )
            # an audit card echoing the draft is a derived copy, not a source
            (paper / "manuscript-audit.json").write_text(
                json.dumps({"numbers": [-0.111111]}), encoding="utf-8"
            )
            draft = paper / "manuscript.json"
            draft.write_text(
                json.dumps({"text": "iris -0.40651 and self-echoed -0.111111"}), encoding="utf-8"
            )
            result = provenance_for_draft(draft, root)
            self.assertEqual(result["decimals_traced"], 2)
            self.assertEqual(result["decimals_only_in_draft_folder"], ["-0.111111"])
            self.assertTrue(any("draft itself" in w for w in result["warnings"]))

    def test_rendering_more_decimals_than_the_artifact_stores_is_called_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "studies").mkdir()
            (root / "studies" / "study.json").write_text(
                json.dumps({"ci_low": -0.03307}), encoding="utf-8"
            )
            result = build_provenance(
                "breast_cancer +0.074262 [-0.033070,+0.181594]",
                root,
                draft_dir="",
            )
            row = result["decimals_rounded_match"][0]
            self.assertEqual(row["draft_value"], "-0.033070")
            self.assertEqual(row["stored_value"], "-0.03307")
            self.assertTrue(row["over_precision"])
            self.assertEqual(result["decimals_over_precision"], ["-0.033070"])
            self.assertTrue(
                any("MORE decimals" in w for w in result["warnings"]),
                "implied precision must be reported, not silently accepted",
            )

    def test_scan_budget_is_part_of_the_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            corpus.mkdir()
            for index in range(4):
                (corpus / ("f%d.json" % index)).write_text(
                    json.dumps({"v": 0.5 + index}), encoding="utf-8"
                )
            result = build_provenance("we report 3.5", corpus, max_files=2)
            self.assertEqual(result["files_scanned"], 2)
            self.assertEqual(result["files_over_budget"], 2)
            self.assertTrue(
                any("--max-files" in w for w in result["warnings"]),
                "a truncated corpus must not read as a full sweep",
            )

    def test_a_value_whose_only_home_is_the_draft_folder_is_not_counted_as_sourced(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "paper"
            paper.mkdir()
            study = root / "studies"
            study.mkdir()
            (study / "study.json").write_text(
                json.dumps({"auc": -0.40651}), encoding="utf-8"
            )
            # an audit card echoing the draft is a derived copy, not a source
            (paper / "manuscript-audit.json").write_text(
                json.dumps({"numbers": [-0.111111]}), encoding="utf-8"
            )
            draft = paper / "manuscript.json"
            draft.write_text(
                json.dumps({"text": "iris -0.40651 and self-echoed -0.111111"}), encoding="utf-8"
            )
            result = provenance_for_draft(draft, root)
            self.assertEqual(result["decimals_traced"], 2)
            self.assertEqual(result["decimals_only_in_draft_folder"], ["-0.111111"])
            self.assertTrue(any("draft itself" in w for w in result["warnings"]))

    def test_cli_writes_the_provenance_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = root / "corpus"
            corpus.mkdir()
            (corpus / "s.json").write_text(json.dumps({"auc": 0.123456}), encoding="utf-8")
            draft = root / "draft.md"
            draft.write_text("AUC 0.123456 across 8 arms\n", encoding="utf-8")
            out = root / "prov.json"
            code = main(
                [
                    "manuscript", "provenance",
                    "--draft", str(draft),
                    "--corpus", str(corpus),
                    "--output", str(out),
                ]
            )
            self.assertEqual(code, 0)
            saved = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(saved["decimals_traced"], 1)
            self.assertEqual(saved["counts_certified"], 0)


if __name__ == "__main__":
    unittest.main()

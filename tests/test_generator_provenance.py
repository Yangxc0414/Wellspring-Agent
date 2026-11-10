"""Nothing in the evidence chain records who wrote a stage's prose, and the bundle must say so.

Measured on the four full-chain demo packages: study-origin.json records source=innovation_review,
which names the stage that raised the idea and not whether a person or a model wrote it, and no
artefact in the chain carries a generator field at all. The README therefore reports the absence
instead of implying that the venue's AI-use question has been answered somewhere.
"""

import io
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.study_package import (
    OUTPUTS_FILENAME,
    PER_SEED_COLUMNS,
    PROMPTS_FILENAME,
    _write_outputs,
    build_study_package,
    generator_provenance,
    per_seed_outputs,
    released_prompts,
)

from tests.test_study_package import fixture_package




class PortableStudyDirTest(unittest.TestCase):
    """A closure report must not hand a venue the machine that produced it."""

    def test_a_study_inside_the_repo_is_recorded_relative(self):
        from research_agent.paths import REPO_ROOT
        from research_agent.study_closure import portable_study_dir

        inside = REPO_ROOT / "runtime_data" / "x" / "studies" / "pkg"
        recorded = portable_study_dir(inside)
        self.assertEqual(recorded, "runtime_data/x/studies/pkg")
        self.assertNotIn("Users", recorded)

    def test_a_study_outside_the_repo_keeps_only_its_name(self):
        import tempfile

        from research_agent.study_closure import portable_study_dir

        with tempfile.TemporaryDirectory() as tmp:
            recorded = portable_study_dir(Path(tmp) / "elsewhere")
        self.assertEqual(recorded, "elsewhere")
        self.assertNotIn(tmp.replace("\\", "/"), recorded)
        self.assertNotIn("\\", recorded)


class AnonymityScanTest(unittest.TestCase):
    """The check that should live with the deliverable, not in a one-off script."""

    def setUp(self):
        import tempfile

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_absolute_paths_in_shippable_files_are_counted_per_file(self):
        from research_agent.study_package import anonymity_scan

        (self.root / "README.md").write_text("see C:/somewhere/outputs", encoding="utf-8")
        (self.root / "MANIFEST.json").write_text('{"study_dir": "/home/alice/x"}', encoding="utf-8")
        (self.root / "notes.pdf").write_text("binary-ish", encoding="utf-8")
        scan = anonymity_scan(self.root)
        self.assertEqual(scan["files_scanned"], 2)
        self.assertFalse(scan["clean"])
        self.assertEqual(scan["files_with_absolute_paths"], 2)
        self.assertEqual([item["file"] for item in scan["offending_files"]], ["MANIFEST.json", "README.md"])
        self.assertIn("not a guarantee of anonymity", scan["boundary"])

    def test_repo_relative_paths_pass(self):
        from research_agent.study_package import anonymity_scan

        (self.root / "README.md").write_text("runtime_data/studies/x/README.md", encoding="utf-8")
        (self.root / "MANIFEST.json").write_text('{"chain_files": ["study.json"]}', encoding="utf-8")
        scan = anonymity_scan(self.root)
        self.assertTrue(scan["clean"], scan)
        self.assertEqual(scan["absolute_path_hits"], 0)
        self.assertEqual(scan["offending_files"], [])
class GeneratorProvenanceTest(unittest.TestCase):
    def test_absent_generator_fields_are_reported_as_absent(self):
        got = generator_provenance({"statement": "s"}, {"source": "innovation_review"}, {}, {})
        self.assertEqual(got["recorded"], [])
        self.assertEqual(len(got["unrecorded"]), 4)
        self.assertEqual(got["origin_source_field"], "innovation_review")
        self.assertEqual(got["delegated_to_autopilot"], [])

    def test_a_human_reason_is_recorded_and_delegation_is_named_separately(self):
        got = generator_provenance({"human_reason": "[delegated:autopilot] policy sha deadbeef"}, {}, {}, {})
        self.assertEqual([row["artifact"] for row in got["recorded"]], ["claim"])
        self.assertEqual(got["delegated_to_autopilot"], ["claim"])

    def test_the_readme_states_what_the_package_cannot_know(self):
        import io
        import json as _json

        with tempfile.TemporaryDirectory() as tmp:
            result = build_study_package(fixture_package(), output=Path(tmp) / "reader", language="en")
            document = (Path(tmp) / "reader" / "README.md").read_text(encoding="utf-8")
            manifest = _json.loads(io.open(result["manifest"], encoding="utf-8").read())
        provenance = manifest["generator_provenance"]
        self.assertEqual(provenance["schema_version"], "study-generator-0.1")
        # a recorded human act is reported as recorded, so the section is not blanket pessimism
        self.assertEqual(
            [row["artifact"] for row in provenance["recorded"]],
            ["claim"],
            provenance["recorded"],
        )
        self.assertIn(
            "study-spec: carries no generator field",
            provenance["unrecorded"],
            provenance["unrecorded"],
        )
        self.assertIn("Who produced what", document)
        self.assertIn("AI-use", document)
        self.assertIn("study-spec: carries no generator field", document)


class ReleasedOutputsTableTest(unittest.TestCase):
    """The released per-seed table must be a copy of the records, not a re-derivation of them.

    A hand-assembled table once produced a header that did not match its columns, so the width and
    the verbatim values are what these cases pin.
    """

    STUDY = {
        "cells": [
            {
                "cell_id": "memory_off_gate_off",
                "runs": [
                    {"seed": 1, "best_score": 0.922222, "operators": ["a", "b"], "nodes": [0] * 60,
                     "improvement_per_evaluation": 0.283333, "evaluations": 60, "memory": False},
                    {"seed": 2, "best_score": None, "operators": ["a"], "nodes": [0] * 30},
                ],
            },
            {
                "cell_id": "memory_on_gate_on",
                "runs": [{"seed": 1, "best_score": 0.5, "operators": [], "nodes": []}],
            },
        ]
    }

    def test_the_table_copies_records_and_counts_what_is_absent(self):
        table = per_seed_outputs(self.STUDY)
        self.assertEqual(len(table["rows"]), 3)
        self.assertEqual(table["columns"], list(PER_SEED_COLUMNS))
        first = dict(zip(table["columns"], table["rows"][0]))
        self.assertEqual(first["cell_id"], "memory_off_gate_off")
        self.assertEqual(first["operators"], "a|b")
        self.assertEqual(first["best_score"], "0.922222")
        self.assertEqual(table["empty_fields"], sum(1 for r in table["rows"] for v in r if v == ""))
        self.assertEqual(table["trace_steps"], [0, 60])

    def test_the_written_csv_has_one_width_and_verbatim_numbers(self):
        import csv

        with tempfile.TemporaryDirectory() as tmp:
            path = _write_outputs(Path(tmp) / OUTPUTS_FILENAME, per_seed_outputs(self.STUDY))
            rows = list(csv.reader(io.open(path, encoding="utf-8", newline="")))
        widths = set(len(row) for row in rows)
        self.assertEqual(widths, {len(PER_SEED_COLUMNS)})
        self.assertEqual(rows[1][rows[0].index("best_score")], "0.922222")
        self.assertEqual(rows[3][rows[0].index("cell_id")], "memory_on_gate_on")


class ReleasedPromptsTest(unittest.TestCase):
    """A shared ledger holds many runs' prompts; a package may only release its own."""

    ORIGIN = {"project_dir": "D:/proj", "run_id": "RUN-1"}

    def _ledger(self, root, bindings):
        turns = []
        for index, binding in enumerate(bindings):
            turns.append(
                {
                    "turn_id": "MT-%d" % index,
                    "module": "idea",
                    "status": "responded",
                    "messages_sha256": "sha%d" % index,
                    "binding": binding,
                    "request": {"system": ["sys"], "turns": [{"role": "user", "content": "ask %d" % index}]},
                    "response": {"text": "answer %d" % index},
                }
            )
        path = Path(root) / "turns.json"
        path.write_text(json.dumps({"turns": turns}), encoding="utf-8")
        return path

    def test_only_the_run_own_turns_are_released(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._ledger(
                tmp,
                [
                    {"project_dir": "D:/proj", "run_id": "RUN-1"},
                    {"project_dir": "D:/proj", "run_id": "RUN-OTHER"},
                    {"project_dir": "D:/elsewhere", "run_id": "RUN-1"},
                    {},
                ],
            )
            got = released_prompts(self.ORIGIN, path)
        self.assertEqual(got["status"], "released")
        self.assertEqual([item["turn_id"] for item in got["items"]], ["MT-0"])
        self.assertEqual(got["turns_in_ledger"], 4)
        self.assertEqual(got["unattributed_turns"], 1)

    def test_an_empty_key_is_never_a_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._ledger(tmp, [{}, {}, {"project_dir": "", "run_id": ""}])
            got = released_prompts({"project_dir": "", "run_id": ""}, path)
            self.assertEqual(got["status"], "no_run_identity")
            self.assertEqual(got["items"], [])
            other = released_prompts(self.ORIGIN, path)
        self.assertEqual(other["status"], "no_matching_turns")
        self.assertEqual(other["turns_in_ledger"], 3)

    def test_a_missing_ledger_says_the_run_asked_no_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            got = released_prompts(self.ORIGIN, Path(tmp) / "absent.json")
        self.assertEqual(got["status"], "no_ledger")

    def test_the_bundle_writes_the_release_and_states_its_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_study_package(fixture_package(), output=Path(tmp) / "reader", language="en")
            document = (Path(tmp) / "reader" / "README.md").read_text(encoding="utf-8")
            manifest = json.loads(io.open(result["manifest"], encoding="utf-8").read())
            release = (Path(tmp) / "reader" / PROMPTS_FILENAME).read_text(encoding="utf-8")
        self.assertEqual(manifest["released_prompts"]["schema_version"], "study-released-prompts-0.1")
        # the fixture has no origin, so the honest answer is that nothing can be attributed
        self.assertEqual(manifest["released_prompts"]["status"], "no_run_identity")
        self.assertEqual(manifest["released_prompts"]["released_items"], 0)
        self.assertIn("prompts-released.jsonl", document)
        self.assertIn("no_run_identity", release.split("\n")[0])


if __name__ == "__main__":
    unittest.main()

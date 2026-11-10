"""Chain integrity separates "can this still be verified" from "is the code still the same"."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.project import init_project
from research_agent.search_lab import write_study_package
from research_agent.closure_profiles import detect_project_profiles
from research_agent.study_integrity import integrity_layers, package_integrity


def _write(path: Path, payload) -> None:
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True)


class PackageIntegrityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        write_study_package(cls.root / "good", dataset="iris", seeds=list(range(1, 17)), budget=60)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def copy(self, name: str) -> Path:
        import shutil

        target = self.root / name
        shutil.copytree(str(self.root / "good"), str(target))
        return target

    def test_a_fresh_package_re_derives_and_matches_the_code_on_disk(self):
        integrity = package_integrity(self.root / "good")
        self.assertEqual(integrity["state"], "derivable")
        self.assertEqual(integrity["failures"], [])
        self.assertEqual(integrity["code_fingerprint"], "match")
        self.assertFalse(integrity["artifacts"]["origin"])
        self.assertFalse(integrity["artifacts"]["claim"])

    def test_a_recorded_hash_that_nothing_reproduces_is_unverifiable_not_just_stale(self):
        """The pre-timing-fix failure mode: the bytes are intact, the recorded hash is a lie."""
        directory = self.copy("pre-fix")
        study = json.loads((directory / "study.json").read_text(encoding="utf-8"))
        study["study_sha256"] = "f" * 64
        _write(directory / "study.json", study)
        integrity = package_integrity(directory)
        self.assertEqual(integrity["state"], "non_derivable")
        self.assertIn("study.self_hash", integrity["failures"])
        # The two bindings that quote the study hash fail alongside it, which is correct: an
        # unverifiable package is unverifiable in several places at once.
        self.assertIn("spec.binds_study", integrity["failures"])
        # The code axis stays independent: nothing about the search code changed here.
        self.assertEqual(integrity["code_fingerprint"], "match")

    def test_a_missing_artifact_is_reported_as_incomplete_rather_than_wrong(self):
        directory = self.copy("partial")
        (directory / "study-evidence.json").unlink()
        integrity = package_integrity(directory)
        self.assertEqual(integrity["state"], "incomplete")
        self.assertEqual(integrity["missing"], ["study-evidence.json"])

    def test_changed_search_code_stales_the_fingerprint_without_unverifying_the_package(self):
        integrity = package_integrity(self.root / "good", current_fingerprint="0" * 64)
        self.assertEqual(integrity["state"], "derivable")
        self.assertEqual(integrity["code_fingerprint"], "stale")

    def test_absent_fingerprint_is_recorded_as_absent_not_as_stale(self):
        directory = self.copy("legacy")
        spec = json.loads((directory / "study-spec.json").read_text(encoding="utf-8"))
        spec.pop("code_fingerprint", None)
        _write(directory / "study-spec.json", spec)
        integrity = package_integrity(directory)
        # Dropping the field changes the canonical spec hash, so the evidence no longer binds it.
        self.assertIn("evidence.binds_spec", integrity["failures"])
        self.assertEqual(integrity["artifacts"]["code_fingerprint"], False)


def entry(state, **artifacts):
    flags = {"origin": False, "preregistration": False, "baseline": False, "claim": False,
             "environment": False, "code_fingerprint": False}
    flags.update(artifacts)
    return {"integrity": {"state": state, "artifacts": flags}}


class IntegrityLayerTest(unittest.TestCase):
    def test_every_artifact_reports_both_the_mixed_and_the_verifiable_denominator(self):
        summary = integrity_layers([
            entry("derivable", origin=True, environment=True),
            entry("derivable", environment=True),
            entry("non_derivable", origin=True),
        ])
        self.assertEqual(summary["layers"], {
            "derivable": 2, "non_derivable": 1, "incomplete": 0, "unknown": 0,
        })
        origin = summary["artifacts"]["origin"]
        self.assertEqual((origin["present"], origin["denominator"], origin["ratio"]), (2, 3, 0.6667))
        self.assertEqual(origin["derivable_present"], 1)
        self.assertEqual(origin["derivable_denominator"], 2)
        self.assertEqual(origin["derivable_ratio"], 0.5)
        self.assertIn("derivable_ratio", summary["rule"])

    def test_packages_without_integrity_data_are_counted_as_unknown_not_quietly_dropped(self):
        summary = integrity_layers([entry("derivable", claim=True), {"directory": "hand-built"}])
        self.assertEqual(summary["layers"]["unknown"], 1)
        self.assertEqual(summary["packages"], 2)
        self.assertEqual(summary["with_integrity_data"], 1)

    def test_an_all_unverifiable_inventory_reports_no_ratio_instead_of_a_fake_zero(self):
        summary = integrity_layers([entry("non_derivable")])
        self.assertIsNone(summary["artifacts"]["origin"]["derivable_ratio"])
        self.assertEqual(summary["artifacts"]["origin"]["ratio"], 0.0)


class SidecarFlagTest(unittest.TestCase):
    def test_artifact_flags_name_what_the_package_actually_carries(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name) / "pkg"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 17)), budget=60)
        _write(directory / "study-origin.json", {"idea_id": "IDEA-01"})
        flags = package_integrity(directory)["artifacts"]
        self.assertTrue(flags["origin"])
        self.assertFalse(flags["preregistration"])
        self.assertTrue(flags["environment"])
        self.assertTrue(flags["code_fingerprint"])


class InventoryIntegrityLayerTest(unittest.TestCase):
    def test_rows_and_layers_project_one_integrity_answer_for_the_inventory(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        project = Path(tmp.name) / "project"
        init_project(project, "integrity inventory")
        write_study_package(
            project / "studies" / "iris", dataset="iris", seeds=list(range(1, 17)), budget=60
        )
        inventory = detect_project_profiles(project)
        row = inventory["search_study"][0]
        self.assertEqual(row["integrity"]["state"], "derivable")
        layers = inventory["study_integrity_layers"]
        self.assertEqual(layers["layers"]["derivable"], 1)
        self.assertEqual(layers["artifacts"]["origin"]["present"], 0)
        self.assertEqual(layers["artifacts"]["origin"]["derivable_present"], 0)
        self.assertEqual(layers["artifacts"]["environment"]["derivable_ratio"], 1.0)

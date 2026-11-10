"""`study package` is a projection: it may not invent a number, and must not claim readiness."""

import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from research_agent.search_lab import code_fingerprint, spec_sha256_of
from research_agent.study_claims import build_study_claim
from research_agent.search_lab import write_study_package
from research_agent.study_package import _environment_lines, build_study_package, foreign_text_fields


_FIXTURE = {}


def fixture_package():
    """One shared 16-seed package for the whole module, built once and removed at exit.

    A per-class fixture looked tempting until the second class depended on the first one's
    directory and the run order decided whether the test could see it.
    """
    if not _FIXTURE:
        import atexit
        import shutil

        root = Path(tempfile.mkdtemp())
        package = root / "study"
        write_study_package(package, dataset="iris", seeds=list(range(1, 17)), budget=60)
        try:
            build_study_claim(
                package,
                "on iris, turning the acceptance gate on raises improvement per validation evaluation",
                "read the paired intervals and the power ladder",
                "S5/pkgtest/iris",
            )
        except ValueError:
            # a study that decides nothing must still package: the README records
            # "(no claim drafted)" rather than inventing a claim to make a test pass
            pass
        _FIXTURE["root"] = root
        _FIXTURE["package"] = package
        atexit.register(shutil.rmtree, str(root), True)
    return _FIXTURE["package"]


def _decimals(text):
    return set(re.findall(r"[-+]?\d+\.\d+", text))


class StudyPackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = fixture_package()
        cls.root = cls.directory.parent

    def test_readme_invents_no_numbers(self):
        result = build_study_package(self.directory, language="en")
        readme = Path(result["readme"]).read_text(encoding="utf-8")
        source = " ".join(
            (self.directory / name).read_text(encoding="utf-8")
            for name in ("study.json", "study-evidence.json", "study-spec.json", "claim-draft.json")
            if (self.directory / name).is_file()
        )
        invented = _decimals(readme) - _decimals(source)
        self.assertEqual(invented, set(), "the README carried numbers the package does not contain")
        self.assertIn("How to re-run", readme)
        self.assertIn("study search", readme)

    def test_manifest_hashes_match_the_bytes_on_disk(self):
        result = build_study_package(self.directory, output=self.root / "out", language="en")
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        rows = manifest["chain_files"] + manifest["extra_files"]
        self.assertTrue(rows, "the manifest listed no files")
        for row in rows:
            handle = self.directory / row["file"]
            self.assertEqual(
                row["sha256"],
                hashlib.sha256(handle.read_bytes()).hexdigest(),
                "manifest hash does not match " + row["file"],
            )
            self.assertEqual(row["bytes"], handle.stat().st_size)
        names = {row["file"] for row in manifest["chain_files"]}
        self.assertIn("study-spec.json", names)
        self.assertIn("claim-draft.json", names)

    def test_the_recorded_spec_binding_is_recomputable(self):
        # guards #59 on the new surface: the spec hash the evidence records must be derivable
        # from the stored spec under the current rule, or the chain binding is fiction.
        spec = json.loads((self.directory / "study-spec.json").read_text(encoding="utf-8"))
        evidence = json.loads((self.directory / "study-evidence.json").read_text(encoding="utf-8"))
        self.assertEqual(evidence["study_spec_sha256"], spec_sha256_of(spec))
        result = build_study_package(self.directory, language="en")
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["code_fingerprint_now"], code_fingerprint())
        self.assertFalse(manifest["submission_ready"])

    def test_a_package_without_recorded_environment_says_so(self):
        lines = _environment_lines({})
        self.assertEqual(len(lines), 1)
        self.assertIn("NOT RECORDED", lines[0])
        self.assertIn("re-run", lines[0])

    def test_a_non_package_directory_is_refused(self):
        with self.assertRaises(ValueError) as raised:
            build_study_package(self.root / "not-a-study")
        self.assertIn("not a study package", str(raised.exception))


class ScriptDisclosureTest(unittest.TestCase):
    """An English bundle that quotes a non-Latin sentence says so; it never translates it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _copy_with_statement(self, statement):
        target = self.root / "bundle"
        target.mkdir(parents=True, exist_ok=True)
        for handle in fixture_package().glob("*"):
            if handle.is_file():
                (target / handle.name).write_bytes(handle.read_bytes())
        claim = json.loads((target / "claim-draft.json").read_text(encoding="utf-8"))
        claim["statement"] = statement
        (target / "claim-draft.json").write_text(json.dumps(claim, ensure_ascii=False), encoding="utf-8")
        return target

    def test_the_pure_function_names_only_the_foreign_fields(self):
        fields = foreign_text_fields(
            {"statement": "在 iris 上，门控提高了改进率"},
            {"question": "does gating pay for itself", "baseline": {"why": "no external opponent"}},
            {"boundary": "a deterministic search study", "metric_caveats": ["起点不同的格子不可直接比较"]},
        )
        self.assertEqual(fields, ["claim.statement", "study-evidence.metric_caveats"])

    def test_an_all_english_package_has_no_disclosure(self):
        result = build_study_package(fixture_package(), output=self.root / "en", language="en")
        readme = Path(result["readme"]).read_text(encoding="utf-8")
        self.assertEqual(result["foreign_script_fields"], [])
        self.assertNotIn("Script disclosure", readme)

    def test_a_chinese_statement_is_disclosed_and_kept_verbatim(self):
        statement = "在 iris 上，开启接受门控提高了单位验证算力的改进率"
        target = self._copy_with_statement(statement)
        result = build_study_package(target, output=self.root / "zh", language="en")
        self.assertEqual(result["foreign_script_fields"], ["claim.statement"])
        readme = Path(result["readme"]).read_text(encoding="utf-8")
        self.assertIn("## Script disclosure", readme)
        self.assertIn("will not translate", readme)
        self.assertIn(statement, readme, "the author's sentence must stay verbatim")
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["foreign_script_fields"], ["claim.statement"])
        self.assertFalse(manifest["submission_ready"])


if __name__ == "__main__":
    unittest.main()


class GridShapedBaselineReadoutTest(unittest.TestCase):
    """A grid-over-environments baseline has its own keys; the README must read them, not None."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_readout_names_real_numbers_and_the_actually_varied_factors(self):
        from research_agent.study_claims import build_study_claim

        directory = self.root / "study"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 17)), budget=60)
        report = directory / "grid-baseline.json"
        report.write_text(
            json.dumps(
                {
                    "schema_version": "tuned-baseline-0.1",
                    "datasets": ["iris"],
                    "folds": 3,
                    "seeds": list(range(1, 17)),
                    "per_dataset": {
                        "iris": {"seeds": 16, "held_out_mean": 0.956667, "evaluations_spent": 912}
                    },
                    "trivial_baselines": {
                        "iris": {
                            "seeds": 16,
                            "values": {
                                "majority_class": {"mean": 0.333333},
                                "random_label": {"mean": 0.337778},
                            },
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        build_study_claim(
            directory,
            "on iris, turning the acceptance gate on changes improvement per validation evaluation",
            "checked the intervals",
            "S5/pkgtest/iris",
            baseline_file=str(report),
        )
        result = build_study_package(directory, output=directory / "reader", language="en")
        readme = (Path(result["readme"])).read_text(encoding="utf-8")
        baseline_row = [row for row in readme.split("\n") if "baseline tuned with" in row][0]
        self.assertIn("folds 3", baseline_row)
        self.assertIn("0.956667", baseline_row)
        self.assertNotIn("None", baseline_row)
        trivial_row = [row for row in readme.split("\n") if "trivial baselines" in row][0]
        self.assertIn("0.333333", trivial_row)
        self.assertNotIn("are not in the bound reference", readme)
        ablation_row = [row for row in readme.split("\n") if "ablation rows" in row][0]
        self.assertIn("gate, memory", ablation_row)
        self.assertNotIn("operators", ablation_row)


class RefusedPowerDisclosureTest(unittest.TestCase):
    """A refused comparison must say how far from decidable it is, not just that it covers zero."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self) -> Path:
        from research_agent.study_claims import build_study_claim

        directory = self.root / "study"
        write_study_package(directory, dataset="wine", seeds=list(range(1, 17)), budget=60)
        try:
            build_study_claim(
                directory,
                "on wine, memory alone raises improvement per validation evaluation",
                "read the intervals",
                "S5/pkgtest/wine",
            )
        except ValueError:
            pass
        return directory

    def test_a_far_from_decidable_refusal_states_its_seed_distance_and_its_ceiling(self):
        directory = self._package()
        result = build_study_package(directory, output=directory / "reader", language="en")
        readme = Path(result["readme"]).read_text(encoding="utf-8")
        block = [row for row in readme.split("\n") if row.startswith("- `") and "not signable" in row]
        self.assertTrue(block, readme[:400])
        far = [row for row in block if "practical ceiling" in row]
        for row in far:
            self.assertIn("paired seeds would be needed", row)
            self.assertIn("mechanism check, not a confirmable direction", row)
            self.assertIn("winner's curse", row)
        # every refused row must either state a distance or state nothing: no bare "0" is allowed
        self.assertFalse([row for row in block if "(0, past" in row or "needed at this observed effect size (0" in row])

    def test_a_comparison_with_no_planning_estimate_gets_no_invented_number(self):
        directory = self.root / "noestimate"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 17)), budget=60)
        evidence = json.loads((directory / "study-evidence.json").read_text(encoding="utf-8"))
        stripped = {
            name: {key: value for key, value in row.items() if key != "seeds_for_80pct"}
            for name, row in (evidence.get("comparison") or {}).items()
        }
        evidence["comparison"] = stripped
        with open(str(directory / "study-evidence.json"), "w", encoding="utf-8") as handle:
            json.dump(evidence, handle)
        result = build_study_package(directory, output=directory / "reader", language="en")
        readme = Path(result["readme"]).read_text(encoding="utf-8")
        self.assertNotIn("paired seeds would be needed", readme)
        self.assertNotIn("None paired seeds", readme)

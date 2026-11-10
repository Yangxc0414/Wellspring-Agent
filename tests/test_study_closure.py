"""Search-study closure: human-signed, hash-bound, and it goes stale on purpose."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.closure_profiles import PROFILE_IDS, SEARCH_STUDY, describe_profiles
from research_agent.search_lab import write_study_package
from research_agent.study_claims import build_study_claim
from research_agent.storage import write_json_atomic
from research_agent.study_closure import (
    build_study_lineage,
    check_study_closure,
    sign_study_closure,
    verify_study_lineage,
)


def _ready_study(tmp: Path) -> Path:
    directory = tmp / "iris"
    write_study_package(directory, dataset="iris", seeds=list(range(1, 9)), budget=60)
    build_study_claim(
        directory,
        "接受门控提高了单位验证算力的改进率",
        "checked the paired interval and the lineage log",
        "S5/search/iris",
        sign=True,
    )
    return directory


class StudyClosureProfileTest(unittest.TestCase):
    def test_search_study_is_a_third_distinct_profile(self):
        self.assertEqual(
            PROFILE_IDS, ("canonical_run", "local_experiment", "search_study")
        )
        ids = [item["id"] for item in describe_profiles()["profiles"]]
        self.assertEqual(len(set(ids)), 3)
        entry = next(item for item in describe_profiles()["profiles"] if item["id"] == SEARCH_STUDY)
        self.assertIn("study closure", entry["entrypoint"])
        self.assertIn("human only", entry["signature"])
        self.assertFalse(describe_profiles()["submission_ready"])


class StudyClosureCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_records_undecidable_tracks_the_evidence_not_the_claim_shape(self):
        from research_agent.study_claims import comparison_verdicts
        from research_agent.storage import read_json, write_json_atomic

        directory = self.root / "ops"
        write_study_package(
            directory,
            dataset="wine",
            seeds=list(range(1, 17)),
            budget=40,
            design={"gate": [True], "operators": ["all", "feature_only", "knob_only"]},
        )
        evidence = read_json(directory / "study-evidence.json") or {}
        refused = [
            row["comparison"]
            for row in comparison_verdicts(evidence)
            if row["state"] in ("undecidable", "unavailable")
        ]
        build_study_claim(
            directory, "算子空间限制改变了单位算力改进率", "reason", "S5/search/wine-ops", sign=False
        )
        report = check_study_closure(directory)
        self.assertFalse(
            any(item.startswith("claim.records_undecidable") for item in report["warnings"]),
            "a claim that records its refusals must not be warned about them",
        )
        claim = read_json(directory / "claim-draft.json")
        claim["verification"] = dict(claim.get("verification") or {}, not_signable=[])
        write_json_atomic(directory / "claim-draft.json", claim)
        after = check_study_closure(directory)
        self.assertEqual(
            any(item.startswith("claim.records_undecidable") for item in after["warnings"]),
            bool(refused),
            "the warning belongs to studies that actually had undecidable comparisons",
        )

    def test_ceiling_saturation_is_a_warning_not_a_blocker(self):
        directory = self.root / "sat"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 9)), budget=60)
        study = json.loads((directory / "study.json").read_text(encoding="utf-8"))
        for cell in study["cells"]:
            for run in cell["runs"][:4]:
                run["best_score"] = 1.0
        (directory / "study.json").write_text(
            json.dumps(study, ensure_ascii=False), encoding="utf-8"
        )
        report = check_study_closure(directory)
        self.assertTrue(
            any(item.startswith("metric.headroom") for item in report["warnings"]),
            "ceiling-capped runs must surface as a metric-validity warning",
        )
        self.assertFalse(
            any(item.startswith("metric.headroom") for item in report["unresolved"]),
            "a post-hoc headroom warning must not block a pre-registered study",
        )

    def test_draft_claim_blocks_closure_until_a_human_signs(self):
        directory = self.root / "study"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 9)), budget=60)
        build_study_claim(
            directory, "接受门控提高单位算力改进率", "reason", "S5/search/iris", sign=False
        )
        report = check_study_closure(directory)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(any(item.startswith("claim.signed") for item in report["unresolved"]))

    def test_full_chain_closes_and_stays_not_submission_ready(self):
        directory = _ready_study(self.root)
        report = check_study_closure(directory)
        self.assertEqual(report["status"], "ready_for_human_signature", report["unresolved"])
        self.assertFalse(report["submission_ready"])
        self.assertEqual(report["closure_profile"], SEARCH_STUDY)
        signature = sign_study_closure(directory, human_reason="reviewed the interval")
        self.assertEqual(signature["report_id"], report["report_id"])
        self.assertTrue((directory / "signature.json").is_file())

    def test_passing_checks_do_not_carry_failure_details(self):
        directory = _ready_study(self.root)
        report = check_study_closure(directory)
        checks = {item["id"]: item for item in report["checks"]}
        self.assertEqual(checks["code.unchanged"]["status"], "pass")
        self.assertNotIn("changed", checks["code.unchanged"]["detail"].lower())
        self.assertEqual(checks["evidence.self_hash"]["status"], "pass")
        self.assertNotIn("does not match", checks["evidence.self_hash"]["detail"])
        self.assertEqual(checks["power.sufficient"]["status"], "pass")
        self.assertNotIn("underpowered", checks["power.sufficient"]["detail"].lower())
        self.assertEqual(checks["claim.signed"]["status"], "pass")
        self.assertNotIn("draft", checks["claim.signed"]["detail"].lower())

    def test_underpowered_study_is_refused_at_both_layers(self):
        directory = self.root / "weak"
        write_study_package(directory, dataset="wine", seeds=[1, 2], budget=20)
        # Layer 1: no claim can even be drafted from an undecidable study.
        with self.assertRaises(ValueError) as raised:
            build_study_claim(directory, "某个方向", "reason", "S5/search/wine", sign=True)
        self.assertIn("nothing is signable", str(raised.exception))
        # Layer 2: closure does not trust the claim layer; it refuses independently.
        report = check_study_closure(directory)
        self.assertEqual(report["status"], "blocked")
        failed = " ".join(report["unresolved"])
        self.assertIn("power.sufficient", failed)
        self.assertIn("has_decidable_comparison", failed)
        with self.assertRaises(ValueError):
            sign_study_closure(directory, human_reason="trying anyway")

    def test_editing_the_spec_hash_breaks_the_binding(self):
        directory = _ready_study(self.root)
        self.assertEqual(check_study_closure(directory)["status"], "ready_for_human_signature")
        spec_path = directory / "study-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["budget"] = 999
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        report = check_study_closure(directory)
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(
            any(item.startswith("evidence.bound_to_spec") for item in report["unresolved"])
        )

    def test_changed_search_code_blocks_citing_an_old_study(self):
        directory = _ready_study(self.root)
        spec_path = directory / "study-spec.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["code_fingerprint"] = "0" * 64
        spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        report = check_study_closure(directory)
        self.assertTrue(
            any(item.startswith("code.unchanged") for item in report["unresolved"]),
            "editing the study code must not leave a prior finding citable",
        )

    def test_provenance_sidecar_is_a_tracked_lineage_node(self):
        directory = _ready_study(self.root)
        write_json_atomic(
            directory / "study-origin.json",
            {"schema_version": "study-origin-0.1", "idea_id": "IDEA-01", "source": "unit_test"},
        )
        check_study_closure(directory)
        lineage = build_study_lineage(directory)
        nodes = [item["node_id"] for item in lineage["nodes"]]
        self.assertIn("study-origin", nodes)
        self.assertEqual(verify_study_lineage(directory)["status"], "fresh")
        self.assertEqual(nodes.index("study-origin"), nodes.index("study-evidence") + 1)

        # Editing only the idea binding must not stay invisible to the chain.
        write_json_atomic(
            directory / "study-origin.json",
            {"schema_version": "study-origin-0.1", "idea_id": "IDEA-99", "source": "retrofit"},
        )
        verify = verify_study_lineage(directory)
        self.assertEqual(verify["status"], "stale")
        self.assertEqual(verify["stale"], ["study-origin"])

    def test_package_without_a_sidecar_keeps_the_old_chain(self):
        directory = _ready_study(self.root)
        check_study_closure(directory)
        lineage = build_study_lineage(directory)
        self.assertNotIn(
            "study-origin", [item["node_id"] for item in lineage["nodes"]]
        )
        self.assertEqual(verify_study_lineage(directory)["status"], "fresh")

    def test_lineage_reports_stale_nodes_and_signing_refuses_a_blocked_report(self):
        directory = _ready_study(self.root)
        check_study_closure(directory)
        build_study_lineage(directory)
        self.assertEqual(verify_study_lineage(directory)["status"], "fresh")
        (directory / "study.json").write_text('{"study_sha256": "tampered"}', encoding="utf-8")
        verify = verify_study_lineage(directory)
        self.assertEqual(verify["status"], "stale")
        self.assertIn("study", verify["stale"])
        with self.assertRaises(ValueError):
            sign_study_closure(directory, human_reason="trying to sign over stale evidence")


class BoundBaselineClosureTest(unittest.TestCase):
    """A bound tuned opponent is verified at byte level, and goes stale with the study."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _bound(self) -> Path:
        directory = self.root / "bound"
        write_study_package(directory, dataset="iris", seeds=list(range(1, 9)), budget=60)
        report = self.root / "tuned.json"
        report.write_text(
            json.dumps(
                {
                    "schema_version": "tuned-baseline-comparison-0.1",
                    "dataset": "iris",
                    "study_budget": 60,
                    "folds": 3,
                    "grid_size": 19,
                    "baseline_fits_per_seed": 57,
                    "budget_matched": True,
                    "seeds": list(range(1, 9)),
                    "cells": [{"cell_id": "memory_on_gate_on", "mean_delta": 0.02}],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        build_study_claim(
            directory,
            "接受门控在预算对齐的调优基线之前仍然提高单位验证算力改进率",
            "checked the paired interval and bound the tuned reference",
            "S5/search/iris",
            sign=True,
            baseline_file=str(report),
        )
        return directory

    def test_bound_baseline_passes_closure_until_its_bytes_change(self):
        directory = self._bound()
        clean = check_study_closure(directory)
        self.assertFalse(
            any(item.startswith("baseline.bound") for item in clean["unresolved"]),
            clean["unresolved"],
        )
        self.assertIn("tuned-baseline.json", clean["artifact_refs"])
        build_study_lineage(directory)
        self.assertEqual(verify_study_lineage(directory)["status"], "fresh")
        (directory / "tuned-baseline.json").write_text(
            json.dumps({"dataset": "iris", "cells": []}), encoding="utf-8"
        )
        stale = check_study_closure(directory)
        self.assertTrue(
            any(item.startswith("baseline.bound") for item in stale["unresolved"]),
            stale["unresolved"],
        )
        verify = verify_study_lineage(directory)
        self.assertEqual(verify["status"], "stale")
        self.assertIn("tuned-baseline", verify["stale"])

    def test_claim_without_a_bound_baseline_warns_instead_of_blocking(self):
        directory = _ready_study(self.root)
        report = check_study_closure(directory)
        self.assertTrue(
            any(item.startswith("baseline.bound") for item in report["warnings"]),
            report["warnings"],
        )
        self.assertFalse(
            any(item.startswith("baseline.bound") for item in report["unresolved"]),
            report["unresolved"],
        )


class EnvironmentDisclosureTest(unittest.TestCase):
    """Compute disclosure travels with the package, and its absence is never a blocker."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self) -> Path:
        directory = self.root / "env"
        write_study_package(directory, dataset="iris", seeds=[1, 2, 3, 4], budget=24)
        return directory

    def test_fresh_package_reports_versions_and_positive_wall_clock(self):
        from research_agent.storage import read_json

        directory = self._package()
        spec = read_json(directory / "study-spec.json")
        environment = spec.get("environment") or {}
        self.assertTrue(environment.get("python"))
        self.assertTrue(environment.get("sklearn"))
        self.assertGreater(int(environment.get("cpu_logical") or 0), 0)
        self.assertGreater(float(environment.get("study_wall_seconds") or 0), 0.0)
        self.assertIn("contention", str(environment.get("boundary") or ""))
        for cell in read_json(directory / "study.json").get("cells") or []:
            self.assertGreater(float(cell.get("elapsed_seconds") or 0), 0.0)
        report = check_study_closure(directory)
        self.assertFalse(
            any(item.startswith("environment.recorded") for item in report["unresolved"]),
            report["unresolved"],
        )

    def test_legacy_package_without_disclosure_warns_instead_of_blocking(self):
        from research_agent.search_lab import evidence_sha256_of, spec_sha256_of
        from research_agent.storage import read_json, write_json_atomic

        directory = self._package()
        # simulate a package written before the field existed: drop it and rehash both files
        # the way the framework does (spec has no self-hash field; the evidence helper blanks
        # its own hash before digesting), so only the disclosure check can react
        spec = read_json(directory / "study-spec.json")
        spec.pop("environment", None)
        evidence = read_json(directory / "study-evidence.json")
        evidence["study_spec_sha256"] = spec_sha256_of(spec)
        evidence["evidence_sha256"] = evidence_sha256_of(evidence)
        write_json_atomic(directory / "study-spec.json", spec)
        write_json_atomic(directory / "study-evidence.json", evidence)

        report = check_study_closure(directory)
        warned = [item for item in report["warnings"] if item.startswith("environment.recorded")]
        self.assertTrue(warned, report["warnings"])
        self.assertFalse(
            any(item.startswith("environment.recorded") for item in report["unresolved"])
        )
        self.assertFalse(
            any(item.startswith("evidence.bound_to_spec") for item in report["unresolved"]),
            "rehashing must stay consistent, or this test would be hiding a real blocker",
        )


class DeclaredBaselineTest(unittest.TestCase):
    """The opponent is chosen before the results exist; declaration and binding must agree."""

    @classmethod
    def setUpClass(cls):
        cls._seed_dir = Path(tempfile.mkdtemp(prefix="declared-baseline-seed-"))
        write_study_package(
            cls._seed_dir / "study", dataset="iris", seeds=list(range(1, 9)), budget=60
        )

    @classmethod
    def tearDownClass(cls):
        import shutil

        shutil.rmtree(cls._seed_dir, ignore_errors=True)

    def setUp(self):
        import shutil

        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.directory = self.root / "study"
        shutil.copytree(self._seed_dir / "study", self.directory)
        self.report = self.root / "tuned.json"
        self.report.write_text(
            json.dumps(
                {
                    "schema_version": "tuned-baseline-comparison-0.1",
                    "dataset": "iris",
                    "study_budget": 60,
                    "folds": 3,
                    "grid_size": 19,
                    "baseline_fits_per_seed": 57,
                    "budget_matched": True,
                    "seeds": list(range(1, 9)),
                    "cells": [{"cell_id": "memory_on_gate_on", "mean_delta": 0.02}],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _prereg(self, baseline):
        from research_agent.study_preregistration import bind_sidecar

        plan = {
            "schema_version": "study-preregistration-0.1",
            "question": "does an archive of accepted configurations help?",
            "hypothesis": "acceptance gating raises improvement per evaluation",
            "analysis": "paired per-seed contrasts against the reference cell",
            "decision_rule": "sign only intervals excluding zero",
            "design": {"memory": [False, True], "gate": [False, True]},
            "seeds": list(range(1, 9)),
            "budget": 60,
            "dataset": "iris",
        }
        if baseline is not None:
            plan["baseline"] = baseline
        study = json.loads((self.directory / "study.json").read_text(encoding="utf-8"))
        bind_sidecar(self.directory, plan, study)

    def _closure_blockers(self):
        report = check_study_closure(self.directory)
        return [item for item in report["unresolved"] if item.startswith("baseline.declared")], [
            item for item in report["warnings"] if item.startswith("baseline.declared")
        ]

    def test_declared_and_bound_opponents_agree(self):
        build_study_claim(
            self.directory,
            "接受门控在预算对齐的调优基线之前仍然提高单位验证算力改进率",
            "checked the declared plan and the paired interval",
            "S5/search/iris",
            sign=True,
            baseline_file=str(self.report),
        )
        self._prereg(
            {"kind": "tuned_cv", "file": "tuned-baseline.json", "why": "budget-matched reference"}
        )
        blockers, warnings = self._closure_blockers()
        self.assertEqual(blockers, [], blockers)
        self.assertEqual(warnings, [], warnings)

    def test_an_opponent_that_appears_after_the_results_is_a_blocker(self):
        build_study_claim(
            self.directory,
            "接受门控提高了单位验证算力的改进率",
            "checked the paired interval",
            "S5/search/iris",
            sign=True,
            baseline_file=str(self.report),
        )
        self._prereg({"kind": "none", "why": "internal comparison only"})
        blockers, _ = self._closure_blockers()
        self.assertTrue(blockers, "a post-hoc opponent must block closure")
        self.assertIn("cannot appear for the first time", blockers[0])

    def test_binding_a_different_file_than_declared_is_a_blocker(self):
        build_study_claim(
            self.directory,
            "接受门控在预算对齐的调优基线之前仍然提高单位验证算力改进率",
            "checked the declared plan",
            "S5/search/iris",
            sign=True,
            baseline_file=str(self.report),
        )
        self._prereg(
            {"kind": "external_file", "file": "another-baseline.json", "why": "declared earlier"}
        )
        blockers, _ = self._closure_blockers()
        self.assertTrue(blockers, blockers)
        self.assertIn("bind the declared file", blockers[0])

    def test_no_declaration_is_a_warning_not_a_verdict(self):
        build_study_claim(
            self.directory,
            "接受门控提高了单位验证算力的改进率",
            "checked the paired interval",
            "S5/search/iris",
            sign=True,
        )
        self._prereg(None)
        blockers, warnings = self._closure_blockers()
        self.assertEqual(blockers, [], blockers)
        self.assertTrue(warnings, "a missing declaration must still be visible")

    def test_a_declared_opponent_cannot_be_an_empty_claim(self):
        from research_agent.study_preregistration import (
            PreregistrationError,
            load_preregistration,
        )

        path = self.root / "plan.json"
        base = {
            "schema_version": "study-preregistration-0.1",
            "question": "q",
            "hypothesis": "h",
            "analysis": "a",
            "decision_rule": "d",
            "design": {},
            "seeds": [1],
            "budget": 60,
            "dataset": "iris",
        }
        path.write_text(json.dumps(dict(base, baseline={"kind": "tuned_cv"})), encoding="utf-8")
        with self.assertRaises(PreregistrationError) as raised:
            load_preregistration(path)
        self.assertIn("requires baseline.file", str(raised.exception))
        path.write_text(
            json.dumps(dict(base, baseline={"kind": "invented"})), encoding="utf-8"
        )
        with self.assertRaises(PreregistrationError) as raised:
            load_preregistration(path)
        self.assertIn("before results exist", str(raised.exception))


if __name__ == "__main__":
    unittest.main()


class PreregistrationOnChainTest(unittest.TestCase):
    """A declared plan that is not on the chain is a declared plan anyone can rewrite."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _package(self, name: str = "study") -> Path:
        from research_agent.storage import read_json, write_json_atomic
        from research_agent.study_preregistration import SIDECAR, bind_sidecar

        directory = self.root / name
        write_study_package(directory, dataset="iris", seeds=list(range(1, 17)), budget=60)
        study = read_json(directory / "study.json")
        bind_sidecar(
            directory,
            {
                "schema_version": "study-preregistration-0.1",
                "question": "does the gate change improvement per evaluation",
                "hypothesis": "the gate stops the budget being spent on worse candidates",
                "analysis": "paired per-seed differences against the reference cell",
                "decision_rule": "only an interval excluding zero is quoted as a direction",
                "design": study["design"],
                "seeds": study["seeds"],
                "budget": study["budget"],
                "dataset": study["dataset"],
            },
            study,
        )
        self.sidecar = directory / SIDECAR
        return directory

    def test_the_closure_report_lists_the_declared_plan_as_chain_material(self):
        directory = self._package()
        report = check_study_closure(directory, output_dir=self.root / "out")
        self.assertIn("study-preregistration.json", report["artifact_refs"])

    def test_rewriting_the_declared_question_stales_the_lineage(self):
        from research_agent.storage import read_json, write_json_atomic
        from research_agent.study_closure import build_study_lineage, verify_study_lineage

        directory = self._package("tampered")
        build_study_lineage(directory)
        payload = read_json(self.sidecar)
        self.assertIn("study-preregistration", [node["node_id"] for node in (read_json(directory / "lineage.json") or {}).get("nodes") or []])
        payload["question"] = "a different question written after the results were seen"
        write_json_atomic(self.sidecar, payload)
        verified = verify_study_lineage(directory)
        self.assertEqual(verified["status"], "stale")
        self.assertIn("study-preregistration", verified["stale"])

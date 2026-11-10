import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_agent.autopilot import (
    AutopilotError,
    autopilot_status,
    build_policy,
    inspect_run,
    load_policy,
    parse_assertion,
    policy_fingerprint,
    run_autopilot,
    worst_seed_floor,
)
from research_agent.pipeline import PipelineRequest, PipelineRunner, write_pipeline_artifacts
from research_agent.project import init_project
from research_agent.signers import SignerStore

ASSERTION = "metric=accuracy,value=0.9000,comparator=>=,tolerance=0.0"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _capsule(**overrides):
    value = {
        "run_id": "RUN-AUTO",
        "status": "completed",
        "dataset_id": "sklearn:iris:150x4",
        "metric_name": "accuracy",
        "seeds": [1, 2, 3],
        "metrics_by_seed": [
            {"seed": 1, "accuracy": 0.95},
            {"seed": 2, "accuracy": 0.92},
            {"seed": 3, "accuracy": 0.90},
        ],
    }
    value.update(overrides)
    return value


def _draft(**overrides):
    value = {
        "status": "draft_needs_human",
        "statement": "On the local iris protocol, mean accuracy is 0.923 over seeds [1, 2, 3].",
        "scope": "S5/demo/iris",
        "assertion_proposal": {"assertion_argument": ASSERTION},
    }
    value.update(overrides)
    return value


class PolicyFileTest(unittest.TestCase):
    def test_a_policy_round_trips_and_a_hand_edit_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            policy = build_policy(
                scope="S5/demo/iris",
                authorized_by="project owner",
                signer_id="SIGNER-TEST",
                min_seeds=3,
                max_runs=2,
                limitation="single fixture dataset",
                bibliography_source="modules/literature/fixtures/bibliography.json",
            )
            _write(path, policy)
            loaded = load_policy(path)
            self.assertEqual(loaded["policy_sha256"], policy_fingerprint(loaded))
            self.assertTrue(loaded["auto_g1"]["require_review_advance"])
            self.assertEqual(loaded["endpoint"], "bundle")

            edited = dict(policy)
            edited["max_runs"] = 99
            _write(path, edited)
            with self.assertRaises(AutopilotError):
                load_policy(path)

    def test_an_unattributed_policy_is_not_a_delegation(self):
        with self.assertRaises(AutopilotError):
            build_policy(scope="S5/demo/iris", authorized_by=" ", signer_id="SIGNER-TEST")


class PolicyCliTest(unittest.TestCase):
    def test_policy_init_refuses_to_overwrite_an_authorization(self):
        import argparse
        from research_agent.cli_autopilot import _cmd_policy_init

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "policy cli")
            signers = SignerStore(Path(tmp) / "signers.json")
            signer = signers.create("autopilot")
            args = argparse.Namespace(
                project=str(project),
                scope="S5/demo/iris",
                authorized_by="project owner",
                signer=signer["signer_id"],
                dataset=["iris"],
                min_seeds=3,
                max_runs=1,
                expires_hours=1,
                endpoint="bundle",
                limitation="single fixture dataset",
                bibliography_source="",
                allow_revise_idea=False,
                note="",
                output="",
                signers_path=str(Path(tmp) / "signers.json"),
            )
            self.assertEqual(_cmd_policy_init(args), 0)
            with self.assertRaises(SystemExit):
                _cmd_policy_init(args)


class AssertionRulesTest(unittest.TestCase):
    def test_the_floor_is_the_worst_seed(self):
        metric, floor = worst_seed_floor(_capsule())
        self.assertEqual(metric, "accuracy")
        self.assertEqual(floor, 0.9)

    def test_parse_assertion_keeps_the_comparator(self):
        parsed = parse_assertion(ASSERTION)
        self.assertEqual(parsed["comparator"], ">=")
        self.assertEqual(parsed["value"], 0.9)
        self.assertEqual(parsed["tolerance"], 0.0)


class InspectRunTest(unittest.TestCase):
    def _project(self, tmp, capsule=None, draft=None, claim=None):
        project = Path(tmp) / "project"
        init_project(project, "autopilot inspect")
        run = project / "runs" / "RUN-AUTO"
        (run / "run").mkdir(parents=True)
        _write(run / "run" / "run-capsule.json", capsule or _capsule())
        _write(run / "run" / "ea.json", {"artifact_id": "EA-1", "scope": "S5/demo/iris"})
        _write(run / "run" / "claim-draft.json", draft or _draft())
        if claim:
            claim_dir = run / "claim"
            claim_dir.mkdir()
            _write(claim_dir / "claim.json", claim)
        return project, run

    def _policy(self, **overrides):
        policy = build_policy(
            scope="S5/demo/iris",
            authorized_by="project owner",
            signer_id="SIGNER-TEST",
            datasets=["iris"],
            min_seeds=3,
        )
        policy.update(overrides)
        policy["policy_sha256"] = policy_fingerprint(policy)
        return policy

    def _ledger(self, runs=None):
        return {"schema_version": "autopilot-ledger-0.1", "runs": list(runs or [])}

    def test_a_compliant_run_has_no_reasons_to_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _ = self._project(tmp)
            checked = inspect_run(project, "RUN-AUTO", self._policy(), self._ledger())
            self.assertTrue(checked["ok"], checked["reasons"])
            self.assertEqual(checked["floor"], 0.9)

    def test_a_weaker_assertion_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft = _draft(
                assertion_proposal={
                    "assertion_argument": "metric=accuracy,value=0.5000,comparator=>=,tolerance=0.0"
                }
            )
            project, _ = self._project(tmp, draft=draft)
            checked = inspect_run(project, "RUN-AUTO", self._policy(), self._ledger())
            self.assertFalse(checked["ok"])
            self.assertTrue(any("not the worst seed" in item for item in checked["reasons"]))

    def test_scope_seeds_and_expiry_are_bounds_not_suggestions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _ = self._project(tmp, capsule=_capsule(seeds=[1], metrics_by_seed=[{"seed": 1, "accuracy": 0.9}]))
            policy = self._policy(min_seeds=3, scope="S5/demo/wine")
            checked = inspect_run(project, "RUN-AUTO", policy, self._ledger())
            reasons = " | ".join(checked["reasons"])
            self.assertIn("outside policy scope", reasons)
            self.assertIn("policy requires at least 3", reasons)

            expired = self._policy(expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat())
            checked = inspect_run(project, "RUN-AUTO", expired, self._ledger())
            self.assertIn("policy expired", " | ".join(checked["reasons"]))

    def test_an_incomplete_study_design_blocks_claim_signing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, run = self._project(tmp)
            _write(run / "demo.json", {
                "modules": {
                    "study_design": {
                        "audit": {"status": "incomplete", "ccfa": {"level": "disclosure_incomplete"}}
                    }
                }
            })
            checked = inspect_run(project, "RUN-AUTO", self._policy(), self._ledger())
            self.assertFalse(checked["ok"])
            self.assertIn("G2 is blocked", " | ".join(checked["reasons"]))

    def test_an_existing_claim_or_a_used_budget_stops_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            project, _ = self._project(tmp, claim={"status": "supported", "claim_id": "CLM-1"})
            checked = inspect_run(project, "RUN-AUTO", self._policy(), self._ledger())
            self.assertIn("already has a claim", " | ".join(checked["reasons"]))

            project2, _ = self._project(Path(tmp) / "second")
            # build_policy generates a policy id from the creation time; reusing one instance
            # is required or the ledger entry belongs to a different policy.
            policy = self._policy(max_runs=1)
            ledger = self._ledger(
                [{"policy_id": policy["policy_id"], "claim_id": "CLM-1"}]
            )
            checked = inspect_run(project2, "RUN-AUTO", policy, ledger)
            self.assertIn("max_runs=1", " | ".join(checked["reasons"]))


class SnapshotTest(unittest.TestCase):
    def test_the_page_projection_drops_absolute_paths(self):
        from research_agent.autopilot import autopilot_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "snapshot")
            _write(project / "autopilot" / "ledger.json", {
                "schema_version": "autopilot-ledger-0.1",
                "runs": [{
                    "policy_id": "AUTO-1",
                    "run_id": "RUN-1",
                    "status": "completed",
                    "claim_id": "CLM-1",
                    "signature_id": "SIG-1",
                    "bundle": str(project / "bundles" / "RUN-1"),
                }],
            })
            _write(project / "autopilot" / "RUN-1" / "autopilot-report.json", {
                "run_id": "RUN-1",
                "status": "completed",
                "created_at": "2026-10-30T00:00:00+00:00",
                "policy": {"policy_id": "AUTO-1", "authorized_by": "owner"},
                "steps": [{"step": "G1", "status": "delegated", "detail": "x", "path": str(project)}],
                "artifacts": {
                    "claim": {"claim_id": "CLM-1", "path": str(project / "claim.json")},
                    "closure": {"signature_id": "SIG-1", "signature_path": str(project)},
                    "bundle": {"path": str(project / "bundles" / "RUN-1"), "verified": True},
                },
                "delegation": {"not_a_human_signature": True},
            })
            snap = autopilot_snapshot(project)
            text = json.dumps(snap, ensure_ascii=False)
            self.assertNotIn(str(project), text)
            self.assertEqual(snap["claim"]["claim_id"], "CLM-1")
            self.assertEqual(snap["bundle"]["path"], "bundles/RUN-1")
            self.assertEqual(snap["steps"][0]["step"], "G1")


class ResearchTest(unittest.TestCase):
    def test_one_command_goes_from_topic_to_a_sealed_bundle(self):
        from research_agent.autopilot import run_autopilot_research

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "autopilot research")
            signers = SignerStore(Path(tmp) / "signers.json")
            signer = signers.create("autopilot")
            policy = build_policy(
                scope="S5/demo/iris",
                authorized_by="project owner",
                signer_id=signer["signer_id"],
                datasets=["iris"],
                min_seeds=3,
                max_runs=1,
                limitation="single fixture dataset; protocol validation only",
                bibliography_source=str(
                    Path(__file__).resolve().parents[1]
                    / "modules/literature/fixtures/bibliography.json"
                ),
                allow_revise_idea=True,
            )
            policy_path = project / "autopilot" / "policy.json"
            _write(policy_path, policy)
            result = run_autopilot_research(
                project,
                "One command from topic to sealed evidence",
                policy_path,
                signers_path=Path(tmp) / "signers.json",
                repo_root=Path(__file__).resolve().parents[1],
            )
            self.assertEqual(result["status"], "completed", result["autopilot"].get("reasons"))
            self.assertEqual(result["pipeline"]["status"], "needs_human")
            report = result["autopilot"]
            self.assertTrue(Path(report["artifacts"]["claim"]["path"]).is_file())
            self.assertTrue(Path(report["artifacts"]["bundle"]["path"]).is_dir())
            self.assertEqual(report["artifacts"]["lineage"]["verify"], "clean")


class FullChainTest(unittest.TestCase):
    """A real fixture run through the delegated tail: claim, closure, bundle, lineage."""

    def test_the_delegated_tail_reaches_a_sealed_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "autopilot chain")
            out = project / "runs" / "RUN-AUTO"
            runner = PipelineRunner(run_output_dir=out / "run")
            result = runner.run(
                PipelineRequest(
                    topic="Policy-bounded autopilot closes the loop",
                    language="en",
                    venue_type="en_conference",
                    run_dataset="iris",
                    run_seeds=3,
                )
            )
            write_pipeline_artifacts(result, out)

            signers = SignerStore(Path(tmp) / "signers.json")
            signer = signers.create("autopilot")
            policy = build_policy(
                scope="S5/demo/iris",
                authorized_by="project owner",
                signer_id=signer["signer_id"],
                datasets=["iris"],
                min_seeds=3,
                max_runs=1,
                limitation="single fixture dataset; protocol validation only",
                bibliography_source=str(
                    Path(__file__).resolve().parents[1]
                    / "modules/literature/fixtures/bibliography.json"
                ),
                allow_revise_idea=True,
            )
            policy_path = project / "autopilot" / "policy.json"
            _write(policy_path, policy)

            # A host model wrote this section; binding the claim must not replace it with the
            # deterministic template.
            paper_path = out / "paper.json"
            paper = json.loads(paper_path.read_text(encoding="utf-8"))
            for item in paper.get("draft") or []:
                if "Abstract" in str(item.get("section") or ""):
                    item["status"] = "model_draft"
                    item["text"] = (
                        "MODEL MARKER kept through claim binding. This sentence is deliberately "
                        "long enough to pass the section length guard and invents no numbers."
                    )
            _write(paper_path, paper)

            report = run_autopilot(
                project,
                "RUN-AUTO",
                policy_path,
                Path(tmp) / "signers.json",
                Path(__file__).resolve().parents[1],
            )
            self.assertEqual(report["status"], "completed", report.get("reasons"))
            self.assertTrue(report["delegation"]["not_a_human_signature"])
            claim = json.loads(Path(report["artifacts"]["claim"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(claim["status"], "supported")
            self.assertIn("[delegated:autopilot]", claim["human_reason"])
            self.assertIn(policy["policy_sha256"], claim["human_reason"])
            self.assertTrue(Path(report["artifacts"]["closure"]["signature_path"]).is_file())
            bundle = Path(report["artifacts"]["bundle"]["path"])
            self.assertTrue((bundle / "bundle-manifest.json").is_file())
            self.assertEqual(report["artifacts"]["lineage"]["verify"], "clean")
            final_paper = json.loads(paper_path.read_text(encoding="utf-8"))
            final_text = " ".join(
                str(item.get("text") or "") for item in final_paper.get("draft") or []
            )
            self.assertIn("MODEL MARKER", final_text)
            status = autopilot_status(project)
            self.assertEqual(status["runs"][0]["status"], "completed")
            self.assertEqual(status["runs"][0]["claim_id"], claim["claim_id"])

            # The budget is spent: a second attempt refuses instead of signing again.
            again = run_autopilot(
                project,
                "RUN-AUTO",
                policy_path,
                Path(tmp) / "signers.json",
                Path(__file__).resolve().parents[1],
            )
            self.assertEqual(again["status"], "stopped")
            self.assertIn("already has a claim", " | ".join(again["reasons"]))


if __name__ == "__main__":
    unittest.main()

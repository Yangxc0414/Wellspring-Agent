import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from research_agent.closure_profiles import (
    CANONICAL_RUN,
    LOCAL_EXPERIMENT,
    SEARCH_STUDY,
    closure_status,
    describe_profiles,
    detect_project_profiles,
    lineage_status,
)
from research_agent.project import init_project, project_status


class ClosureProfilesTest(unittest.TestCase):
    def test_registry_names_all_profiles_and_never_submits(self):
        described = describe_profiles()
        ids = [item["id"] for item in described["profiles"]]
        self.assertEqual(ids, [CANONICAL_RUN, LOCAL_EXPERIMENT, SEARCH_STUDY])
        self.assertFalse(described["submission_ready"])
        for item in described["profiles"]:
            self.assertFalse(item.get("submission_ready", False))
            self.assertIn("human", item["signature"])
        # profiles are distinguishable, so a report cannot be passed off as another one's
        schemas = [item["report_schema"] for item in described["profiles"]]
        self.assertEqual(len(set(schemas)), len(schemas), "report schemas must not collide")
        artifacts = [item["artifacts"] for item in described["profiles"]]
        self.assertEqual(len(set(artifacts)), len(artifacts))
        self.assertIn("all three", described["rule"])

    def test_inventory_survives_a_malformed_evidence_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "broken-project"
            init_project(project, "broken inventory")
            study = project / "studies" / "broken"
            study.mkdir(parents=True)
            (study / "study-spec.json").write_text(
                json.dumps({"dataset": "broken"}), encoding="utf-8"
            )
            (study / "study-evidence.json").write_text(
                json.dumps(
                    {
                        "comparison": {"memory_on_gate_on": "not-a-dict"},
                        "interaction_inference": ["also", "not", "a", "dict"],
                    }
                ),
                encoding="utf-8",
            )
            row = detect_project_profiles(project)["search_study"][0]
            self.assertTrue(row["verdict"]["available"])
            self.assertEqual(
                [item["state"] for item in row["verdict"]["comparisons"]], ["unavailable"]
            )

    def test_inventory_verdict_splits_decidable_from_undecidable(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "verdict-project"
            init_project(project, "verdict inventory")
            study = project / "studies" / "wine"
            study.mkdir(parents=True)
            (study / "study-spec.json").write_text(
                json.dumps({"dataset": "wine", "seeds": [1, 2, 3, 4, 5, 6, 7, 8]}),
                encoding="utf-8",
            )
            (study / "study-evidence.json").write_text(
                json.dumps(
                    {
                        "primary_metric": "improvement_per_evaluation",
                        "underpowered": False,
                        "comparison": {
                            "memory_on_gate_on": {
                                "mean_diff": 0.05,
                                "ci95_low": -0.01,
                                "ci95_high": 0.12,
                                "comparator": "baseline",
                            },
                            "memory_on_gate_off": {
                                "mean_diff": -0.09,
                                "ci95_low": -0.14,
                                "ci95_high": -0.04,
                                "comparator": "baseline",
                            },
                            "memory_off_gate_on": {"mean_diff": 0.02},
                        },
                        "interaction_inference": {
                            "available": True,
                            "mean_interaction": -0.16,
                            "ci95_low": -0.23,
                            "ci95_high": -0.09,
                        },
                    }
                ),
                encoding="utf-8",
            )
            verdict = detect_project_profiles(project)["search_study"][0]["verdict"]
            states = {row["comparison"]: row["state"] for row in verdict["comparisons"]}
            self.assertEqual(
                states,
                {
                    "memory_on_gate_on": "undecidable",
                    "memory_on_gate_off": "negative",
                    "memory_off_gate_on": "unavailable",
                    "memory_x_gate_interaction": "negative",
                },
            )
            self.assertEqual(verdict["decidable"], 2)
            self.assertEqual(verdict["undecidable"], 1)
            # A positive point estimate whose interval covers zero is never shown as a win.
            cross_zero = [
                row for row in verdict["comparisons"] if row["comparison"] == "memory_on_gate_on"
            ][0]
            self.assertGreater(cross_zero["mean_diff"], 0)
            self.assertEqual(cross_zero["state"], "undecidable")

    def test_inventory_reports_which_idea_a_study_was_run_for(self):
        from research_agent.search_lab import spec_sha256_of
        from research_agent.storage import write_json_atomic

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "origin-project"
            init_project(project, "origin inventory")
            study = project / "studies" / "STUDY-IDEA-09"
            study.mkdir(parents=True)
            spec = {"dataset": "wine", "seeds": [1, 2, 3, 4]}
            write_json_atomic(study / "study-spec.json", spec)
            write_json_atomic(study / "study-evidence.json", {"comparison": {}})
            row = detect_project_profiles(project)["search_study"][0]
            self.assertEqual(row["origin"], "absent")
            # Before a closure report exists the spec is the truthful dataset source.
            self.assertEqual(row["dataset"], "wine")

            write_json_atomic(
                study / "study-origin.json",
                {"idea_id": "IDEA-09", "study_spec_sha256": spec_sha256_of(spec)},
            )
            row = detect_project_profiles(project)["search_study"][0]
            self.assertEqual(row["origin"], "bound")
            self.assertEqual(row["idea_id"], "IDEA-09")

            write_json_atomic(study / "study-spec.json", dict(spec, seeds=[1, 2, 3, 4, 5]))
            after = detect_project_profiles(project)["search_study"][0]
            self.assertEqual(
                after["origin"], "stale", "re-running a study must break the origin binding"
            )

    def test_inventory_lists_a_search_study_package_as_its_own_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "study-project"
            init_project(project, "study inventory")
            study = project / "studies" / "iris"
            study.mkdir(parents=True)
            (study / "study-spec.json").write_text(
                json.dumps({"dataset": "iris", "seeds": [1, 2, 3, 4]}), encoding="utf-8"
            )
            (study / "study-evidence.json").write_text(
                json.dumps({"underpowered": False}), encoding="utf-8"
            )
            found = detect_project_profiles(project)
            self.assertIn(SEARCH_STUDY, found["present_profiles"])
            entry = found["search_study"][0]
            self.assertEqual(entry["dataset"], "iris")
            self.assertEqual(entry["next"], "study closure")
            self.assertEqual(
                entry["study_dir"], "studies/iris", "the inventory must not leak absolute paths"
            )

            (study / "study-evidence.json").write_text(
                json.dumps({"underpowered": True}), encoding="utf-8"
            )
            underpowered = detect_project_profiles(project)["search_study"][0]
            self.assertIn("not closable", underpowered["next"])
            self.assertNotIn(SEARCH_STUDY, found["canonical_run"] + found["local_experiment"])

    def test_detect_inventories_runs_and_experiments(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "closure profiles")
            run_dir = project / "runs" / "RUN-20261027T000000Z-abcdef" / "run"
            run_dir.mkdir(parents=True)
            (run_dir / "run-capsule.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (run_dir / "ea.json").write_text("{}", encoding="utf-8")
            (run_dir / "closure-report.json").write_text(
                json.dumps({"status": "ready"}), encoding="utf-8"
            )
            package = project / "experiments" / "EXP-DEMO"
            (package / "experiment-closure").mkdir(parents=True)
            (package / "experiment-spec.json").write_text("{}", encoding="utf-8")
            (package / "experiment-closure" / "closure-report.json").write_text(
                json.dumps({"status": "ready_for_human_signature"}), encoding="utf-8"
            )
            detected = detect_project_profiles(project)
            self.assertEqual(detected["present_profiles"], [CANONICAL_RUN, LOCAL_EXPERIMENT])
            self.assertEqual(detected["canonical_run"][0]["run_id"], "RUN-20261027T000000Z-abcdef")
            self.assertEqual(detected["canonical_run"][0]["next"], "claim sign (human only)")
            self.assertEqual(detected["local_experiment"][0]["experiment_id"], "EXP-DEMO")
            self.assertEqual(
                detected["local_experiment"][0]["next"], "experiment sign (human only)"
            )
            self.assertFalse(detected["submission_ready"])

    def test_inventory_shows_the_claim_draft_the_human_would_sign(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "claim draft inventory")
            run = project / "runs" / "RUN-20261030T000000Z-abcdef"
            run_dir = run / "run"
            run_dir.mkdir(parents=True)
            (run_dir / "run-capsule.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (run_dir / "ea.json").write_text("{}", encoding="utf-8")
            (run_dir / "claim-draft.json").write_text(
                json.dumps(
                    {
                        "status": "draft_needs_human",
                        "statement": "On the local iris protocol, mean accuracy is 0.956.",
                        "scope": "S5/demo/iris",
                        "assertion_proposal": {
                            "status": "proposed_for_human",
                            "reading": "the proposed value is the worst seed",
                            "assertion_argument": "metric=accuracy,value=0.9111,comparator=>=,tolerance=0.0",
                        },
                    }
                ),
                encoding="utf-8",
            )
            item = detect_project_profiles(project)["canonical_run"][0]
            draft = item["claim_draft"]
            self.assertEqual(draft["status"], "draft_needs_human")
            self.assertIn("mean accuracy is 0.956", draft["statement"])
            self.assertEqual(
                draft["assertion"], "metric=accuracy,value=0.9111,comparator=>=,tolerance=0.0"
            )
            # Paths stay project-relative: this inventory also travels over HTTP.
            self.assertNotIn(str(project), draft["command"])
            self.assertIn("runs/RUN-20261030T000000Z-abcdef/run/run-capsule.json", draft["command"])
            self.assertIn("--scope S5/demo/iris", draft["command"])
            self.assertIn('--assertion "metric=accuracy', draft["command"])
            self.assertIn("--output-dir runs/RUN-20261030T000000Z-abcdef/run/claim", draft["command"])
            self.assertIn("signs nothing", draft["boundary"])

            # A signed claim makes "what you would sign" stale, so the inventory drops it.
            claim_dir = run / "claim"
            claim_dir.mkdir()
            (claim_dir / "claim.json").write_text(
                json.dumps({"status": "supported"}), encoding="utf-8"
            )
            signed_item = detect_project_profiles(project)["canonical_run"][0]
            self.assertTrue(signed_item["has_signed_claim"])
            self.assertIsNone(signed_item["claim_draft"])

    def test_inventory_surfaces_the_study_design_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "study design inventory")
            run = project / "runs" / "RUN-DESIGN"
            (run / "run").mkdir(parents=True)
            (run / "run" / "run-capsule.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (run / "run" / "ea.json").write_text("{}", encoding="utf-8")
            (run / "demo.json").write_text(
                json.dumps(
                    {
                        "modules": {
                            "study_design": {
                                "audit": {
                                    "status": "incomplete",
                                    "ccfa": {"level": "disclosure_incomplete"},
                                    "blockers": ["claims.present: 0 claim(s)"],
                                }
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            row = detect_project_profiles(project)["canonical_run"][0]
            self.assertEqual(row["study_design"]["status"], "incomplete")
            self.assertEqual(row["study_design"]["ccfa_level"], "disclosure_incomplete")
            self.assertIn("claims.present", row["study_design"]["blockers"][0])
            self.assertEqual(row["next"], "fix study design; G2 is blocked")

    def test_a_signed_closure_is_not_still_asking_for_a_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "signed closure inventory")
            run = project / "runs" / "RUN-SIGNED"
            (run / "run").mkdir(parents=True)
            (run / "run" / "run-capsule.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (run / "run" / "ea.json").write_text("{}", encoding="utf-8")
            (run / "closure").mkdir()
            (run / "closure" / "closure-report.json").write_text(
                json.dumps({"status": "ready"}), encoding="utf-8"
            )
            (run / "closure-signature").mkdir()
            (run / "closure-signature" / "signature.json").write_text(
                json.dumps(
                    {
                        "signature_id": "SIG-1",
                        "human_reason": "[delegated:autopilot] G5 closure signature under policy AUTO-1",
                    }
                ),
                encoding="utf-8",
            )
            (run / "claim").mkdir()
            (run / "claim" / "claim.json").write_text(
                json.dumps({"status": "supported", "claim_id": "CLM-1"}), encoding="utf-8"
            )
            row = detect_project_profiles(project)["canonical_run"][0]
            self.assertTrue(row["has_signature"])
            self.assertTrue(row["delegated"])
            self.assertEqual(row["closure_status"], "signed")
            self.assertEqual(row["next"], "signature present; publish a local bundle")
            self.assertIsNone(row["claim_draft"])

            (project / "bundles" / "RUN-SIGNED").mkdir(parents=True)
            row = detect_project_profiles(project)["canonical_run"][0]
            self.assertEqual(row["next"], "closed locally; verify the sealed bundle")

    def test_closure_status_reports_local_and_canonical_next_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "closure status")
            package = project / "experiments" / "EXP-STATUS" / "experiment-closure"
            package.mkdir(parents=True)
            (package / "closure-report.json").write_text(
                json.dumps({"status": "ready_for_human_signature", "checks": [], "blockers": []}),
                encoding="utf-8",
            )
            local = closure_status(project, experiment_id="EXP-STATUS")
            self.assertEqual(local["profile"], LOCAL_EXPERIMENT)
            self.assertEqual(local["next_action"], "experiment sign (human only)")
            self.assertFalse(local["signed"])
            self.assertFalse(local["submission_ready"])
            self.assertFalse(local["chain_complete"])
            local_roles = [item["role"] for item in local["chain"]]
            self.assertIn("execution_approval", local_roles)
            self.assertIn("experiment_evidence", local_roles)
            self.assertEqual(len(local["chain_fingerprint"]), 64)

            package.parent.joinpath("experiment-spec.json").write_text(
                json.dumps({"run_id": "RUN-LOCAL"}), encoding="utf-8"
            )
            panel_path = project / "runs" / "RUN-LOCAL" / "support-panel.json"
            panel_path.parent.mkdir(parents=True)
            panel_path.write_text(
                json.dumps({"status": "needs_human", "pending_human": ["SUP-01"]}),
                encoding="utf-8",
            )
            pending_panel = closure_status(project, experiment_id="EXP-STATUS")
            self.assertEqual(pending_panel["support_panel_status"], "needs_human")
            self.assertEqual(
                pending_panel["next_action"], "support adjudication (human only)"
            )
            panel_path.write_text(
                json.dumps({"status": "ready", "pending_human": []}),
                encoding="utf-8",
            )
            resolved_panel = closure_status(project, experiment_id="EXP-STATUS")
            self.assertEqual(
                resolved_panel["next_action"], "experiment sign (human only)"
            )
            resolved_roles = {
                item["role"]: item for item in resolved_panel["chain"]
            }
            self.assertTrue(resolved_roles["support_panel"]["present"])

            run = project / "runs" / "RUN-CLOSURE"
            (run / "run").mkdir(parents=True)
            (run / "run" / "run-capsule.json").write_text("{}", encoding="utf-8")
            (run / "run" / "closure-report.json").write_text(
                json.dumps({"status": "ready", "checks": [], "blockers": []}),
                encoding="utf-8",
            )
            canonical = closure_status(project, run_id="RUN-CLOSURE")
            self.assertEqual(canonical["profile"], CANONICAL_RUN)
            self.assertEqual(canonical["next_action"], "claim sign (human only)")
            self.assertEqual(canonical["claim_status"], "missing")
            self.assertFalse(canonical["claim_signed"])
            self.assertFalse(canonical["signed"])
            self.assertFalse(canonical["chain_complete"])
            canonical_roles = {item["role"]: item for item in canonical["chain"]}
            self.assertTrue(canonical_roles["run_capsule"]["present"])
            self.assertTrue(canonical_roles["closure_report"]["present"])
            self.assertIn("support_panel", canonical_roles)
            self.assertFalse(canonical_roles["support_panel"]["present"])
            self.assertFalse(canonical_roles["claim"]["present"])
            self.assertFalse(canonical_roles["closure_signature"]["present"])
            self.assertEqual(
                canonical_roles["closure_report"]["sha256"],
                hashlib.sha256(
                    (run / "run" / "closure-report.json").read_bytes()
                ).hexdigest(),
            )

            claim_path = run / "claim" / "claim.json"
            claim_path.parent.mkdir(parents=True)
            claim_path.write_text(
                json.dumps({"status": "supported"}), encoding="utf-8"
            )
            signed_claim = closure_status(project, run_id="RUN-CLOSURE")
            self.assertEqual(signed_claim["claim_status"], "supported")
            self.assertTrue(signed_claim["claim_signed"])
            self.assertEqual(signed_claim["next_action"], "closure sign (human only)")
            signed_roles = {item["role"]: item for item in signed_claim["chain"]}
            self.assertTrue(signed_roles["claim"]["present"])

            panel_path = run / "support-panel.json"
            panel_path.write_text(
                json.dumps({"status": "needs_human", "pending_human": ["SUP-02"]}),
                encoding="utf-8",
            )
            pending_panel = closure_status(project, run_id="RUN-CLOSURE")
            self.assertEqual(pending_panel["support_panel_status"], "needs_human")
            self.assertEqual(pending_panel["support_panel_pending_human"], 1)
            self.assertEqual(
                pending_panel["next_action"], "support adjudication (human only)"
            )
            panel_path.write_text(
                json.dumps(
                    {
                        "status": "ready",
                        "pending_human": [],
                        "panel_fingerprint": "b" * 64,
                    }
                ),
                encoding="utf-8",
            )
            resolved_panel = closure_status(project, run_id="RUN-CLOSURE")
            self.assertEqual(resolved_panel["next_action"], "closure sign (human only)")
            resolved_roles = {item["role"]: item for item in resolved_panel["chain"]}
            self.assertTrue(resolved_roles["support_panel"]["present"])
            self.assertEqual(
                resolved_roles["support_panel"]["meta"]["panel_fingerprint"], "b" * 64
            )

    def test_chain_fingerprint_is_stable_until_an_artifact_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "closure chain")
            package = project / "experiments" / "EXP-FP"
            (package / "outputs").mkdir(parents=True)
            (package / "experiment-closure").mkdir()
            (package / "experiment-spec.json").write_text("{}", encoding="utf-8")
            (package / "execution-approval.json").write_text("{}", encoding="utf-8")
            (package / "execution.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (package / "experiment-evidence.json").write_text(
                json.dumps({"status": "verified"}), encoding="utf-8"
            )
            (package / "claim.json").write_text(
                json.dumps({"status": "signed"}), encoding="utf-8"
            )
            table = package / "outputs" / "results-table.csv"
            table.write_text("metric,mean\naccuracy,0.9\n", encoding="utf-8")
            (package / "experiment-closure" / "closure-report.json").write_text(
                json.dumps({"status": "ready_for_human_signature"}), encoding="utf-8"
            )
            (package / "experiment-closure" / "signature.json").write_text(
                "{}", encoding="utf-8"
            )
            first = closure_status(project, experiment_id="EXP-FP")
            self.assertTrue(first["chain_complete"])
            again = closure_status(project, experiment_id="EXP-FP")
            self.assertEqual(again["chain_fingerprint"], first["chain_fingerprint"])
            table.write_text("metric,mean\naccuracy,0.8\n", encoding="utf-8")
            changed = closure_status(project, experiment_id="EXP-FP")
            self.assertNotEqual(changed["chain_fingerprint"], first["chain_fingerprint"])
            roles = {item["role"]: item for item in changed["chain"]}
            self.assertEqual(roles["results_table"]["sha256"], hashlib.sha256(table.read_bytes()).hexdigest())

    def test_lineage_status_rehashes_nodes_and_never_rebuilds(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "lineage status")
            missing = lineage_status(project, experiment_id="EXP-LIN")
            self.assertEqual(missing["status"], "missing")
            self.assertIn("experiment lineage", missing["next_action"])
            self.assertFalse(missing["submission_ready"])

            package = project / "experiments" / "EXP-LIN"
            (package / "outputs").mkdir(parents=True)
            metrics = package / "outputs" / "metrics.json"
            metrics.write_text('{"accuracy": 0.9}', encoding="utf-8")
            claim = package / "claim.json"
            claim.write_text('{"status": "signed"}', encoding="utf-8")
            lineage_dir = package / "experiment-lineage"
            lineage_dir.mkdir()
            manifest = lineage_dir / "lineage.json"
            manifest.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "node_id": "metrics",
                                "path": str(metrics),
                                "sha256": hashlib.sha256(metrics.read_bytes()).hexdigest(),
                            },
                            {
                                "node_id": "claim",
                                "path": str(claim),
                                "sha256": hashlib.sha256(claim.read_bytes()).hexdigest(),
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            fresh = lineage_status(project, experiment_id="EXP-LIN")
            self.assertEqual(fresh["status"], "fresh")
            self.assertEqual(fresh["stale"], [])
            self.assertEqual(fresh["node_count"], 2)
            self.assertIn("none", fresh["next_action"])

            metrics.write_text('{"accuracy": 0.8}', encoding="utf-8")
            stale = lineage_status(project, experiment_id="EXP-LIN")
            self.assertEqual(stale["status"], "stale")
            self.assertEqual(stale["stale"], ["metrics"])
            checks = {item["node_id"]: item for item in stale["checks"]}
            self.assertEqual(checks["metrics"]["reason"], "sha256 mismatch")
            self.assertEqual(checks["claim"]["status"], "fresh")
            self.assertIn("experiment closure", stale["next_action"])

            outside = Path(tmp) / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            manifest.write_text(
                json.dumps(
                    {
                        "nodes": [
                            {
                                "node_id": "outside",
                                "path": str(outside),
                                "sha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            guarded = lineage_status(project, experiment_id="EXP-LIN")
            self.assertEqual(guarded["status"], "stale")
            self.assertEqual(guarded["checks"][0]["reason"], "outside project")

    def test_project_status_surfaces_panel_gold_and_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "governance status")
            run = project / "runs" / "RUN-GOV"
            run.mkdir(parents=True)
            (run / "task.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (run / "support-panel.json").write_text(
                json.dumps({"status": "needs_human", "pending_human": ["SUP-01"]}),
                encoding="utf-8",
            )
            (run / "support-gold.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "annotators": [{"id": "A"}, {"id": "B"}],
                        "agreement": {"mean_kappa": 0.6},
                        "panel": {"accuracy": 0.8},
                    }
                ),
                encoding="utf-8",
            )
            (run / "writing-audit.json").write_text(
                json.dumps({"status": "blocked"}), encoding="utf-8"
            )
            status = project_status(project)
            governance = status["runs"][0]["governance"]
            self.assertEqual(governance["support_panel"]["status"], "needs_human")
            self.assertEqual(governance["support_panel"]["pending_human"], 1)
            self.assertEqual(governance["support_gold"]["annotators"], 2)
            self.assertEqual(governance["support_gold"]["mean_kappa"], 0.6)
            self.assertEqual(governance["support_gold"]["panel_accuracy"], 0.8)
            self.assertEqual(governance["writing_audit"]["status"], "blocked")

    def test_next_actions_surface_panel_adjudication(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "next actions")
            run = project / "runs" / "RUN-NEXT"
            run.mkdir(parents=True)
            (run / "task.json").write_text(
                json.dumps({"status": "completed", "stopped_at": "", "artifacts": {}}),
                encoding="utf-8",
            )
            (run / "support-panel.json").write_text(
                json.dumps(
                    {
                        "status": "needs_human",
                        "draft": str(project / "draft.md"),
                        "judges": [{"id": "a"}, {"id": "b"}],
                    }
                ),
                encoding="utf-8",
            )
            from research_agent.mcp_server import _next_actions

            actions = _next_actions(project, "RUN-NEXT")
            self.assertEqual(actions[0]["kind"], "human_adjudication")
            self.assertIn("writing support-panel", actions[0]["cli"])
            self.assertIn("--strict-support", actions[0]["cli"])
            self.assertEqual(
                actions[0]["artifact"], "support-adjudication-template.json"
            )

    def test_project_status_exposes_profile_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "closure profiles")
            status = project_status(project)
            self.assertEqual(status["closure_profiles"]["present_profiles"], [])
            self.assertIn("guidance", status["closure_profiles"])



class PlanningHintTest(unittest.TestCase):
    """An undecidable verdict must carry the next step, not only the refusal."""

    def test_seeds_for_80pct_survives_into_the_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "hint-project"
            init_project(project, "hint inventory")
            study = project / "studies" / "iris"
            study.mkdir(parents=True)
            (study / "study-spec.json").write_text(
                json.dumps({"dataset": "iris", "seeds": [1, 2, 3, 4]}), encoding="utf-8"
            )
            (study / "study-evidence.json").write_text(
                json.dumps(
                    {
                        "primary_metric": "improvement_per_evaluation",
                        "underpowered": False,
                        "comparison": {
                            "memory_on_gate_off": {
                                "mean_diff": 0.10,
                                "ci95_low": -0.05,
                                "ci95_high": 0.25,
                                "seeds_for_80pct": 25,
                            }
                        },
                        "interaction_inference": {},
                    }
                ),
                encoding="utf-8",
            )
            row = detect_project_profiles(project)["search_study"][0]
            comparison = row["verdict"]["comparisons"][0]
            self.assertEqual(comparison["state"], "undecidable")
            self.assertEqual(comparison["seeds_for_80pct"], 25)

    def test_a_study_without_the_hint_reports_null_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "no-hint-project"
            init_project(project, "no hint")
            study = project / "studies" / "iris"
            study.mkdir(parents=True)
            (study / "study-spec.json").write_text(
                json.dumps({"dataset": "iris", "seeds": [1, 2, 3, 4]}), encoding="utf-8"
            )
            (study / "study-evidence.json").write_text(
                json.dumps(
                    {
                        "primary_metric": "improvement_per_evaluation",
                        "underpowered": False,
                        "comparison": {
                            "memory_on_gate_off": {
                                "mean_diff": 0.10,
                                "ci95_low": -0.05,
                                "ci95_high": 0.25,
                            }
                        },
                        "interaction_inference": {},
                    }
                ),
                encoding="utf-8",
            )
            comparison = detect_project_profiles(project)["search_study"][0]["verdict"]["comparisons"][0]
            self.assertIsNone(comparison["seeds_for_80pct"])

if __name__ == "__main__":
    unittest.main()

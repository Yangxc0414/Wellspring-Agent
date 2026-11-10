import json
import tempfile
import unittest
from pathlib import Path

from research_agent.loop_capsule import (
    build_loop_capsule,
    update_loop_capsule_meta,
    write_loop_capsule,
)


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class LoopCapsuleTest(unittest.TestCase):
    def test_a_run_level_design_audit_reaches_the_workbench(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            root = project / "runs" / "RUN-1"
            root.mkdir(parents=True)
            _write(root / "study-design.json", {"schema_version": "study-design-0.1"})
            _write(root / "study-design-audit.json", {
                "status": "attention",
                "ccfa": {"level": "evidence_ready"},
                "blockers": ["replication.partial_claim"],
            })
            capsule = build_loop_capsule(root)
            node = {item["id"]: item for item in capsule["nodes"]}["S4"]
            self.assertEqual(node["study_design_status"], "attention")
            self.assertEqual(node["ccfa_level"], "evidence_ready")
            self.assertEqual(
                node["study_design_blockers"], ["replication.partial_claim"]
            )

    def test_a_decidable_study_surfaces_the_human_claim_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            root = project / "runs" / "RUN-1"
            root.mkdir(parents=True)
            study = project / "studies" / "STUDY-IDEA-01"
            _write(study / "study-origin.json", {"idea_id": "IDEA-01"})
            _write(study / "closure-report.json", {
                "status": "blocked",
                "checks": [
                    {"id": "has_decidable_comparison", "status": "pass"},
                    {"id": "claim.present", "status": "fail"},
                ],
            })
            second = project / "studies" / "STUDY-IDEA-03"
            _write(second / "study-origin.json", {"idea_id": "IDEA-03"})
            _write(second / "closure-report.json", {
                "status": "blocked",
                "checks": [
                    {"id": "has_decidable_comparison", "status": "pass"},
                    {"id": "claim.present", "status": "fail"},
                ],
            })
            capsule = build_loop_capsule(root)
            actions = [
                item for item in capsule["next_actions"] if "study claim" in item["command"]
            ]
            self.assertEqual(len(actions), 2)
            self.assertEqual({item["gate"] for item in actions}, {"S5b"})
            self.assertTrue(any("STUDY-IDEA-01" in item["command"] for item in actions))
            self.assertTrue(any("STUDY-IDEA-03" in item["command"] for item in actions))
            self.assertTrue(any("RUN-1/IDEA-03" in item["command"] for item in actions))

    def test_capsule_reports_real_nodes_blockers_and_next_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "task.json", {
                "task_id": "TASK-1",
                "status": "needs_human",
                "plan": {"route": "full_research"},
            })
            _write(root / "demo.json", {
                "run_id": "RUN-1",
                "fixture_mode": False,
                "flow_mode": "review",
                "stopped_at": "G2",
                "gates": [
                    {"gate": "G1", "status": "needs_human", "reason": "idea"},
                    {"gate": "G2", "status": "needs_human", "reason": "protocol"},
                    {"gate": "G5", "status": "blocked", "reason": "no closure"},
                ],
                "modules": {},
            })
            _write(root / "literature.json", {
                "spans": [{"span_id": "SPAN-1"}],
                "coverage": {"sources_found": 2, "gaps": [{"code": "thin"}]},
            })
            _write(root / "idea.json", {
                "status": "candidates_need_human",
                "candidates": [{"idea_id": "IDEA-01", "title": "candidate"}],
                "shortlist": {"selection": "human_g1"},
            })
            _write(root / "experiment.json", {
                "status": "needs_human",
                "idea_id": "IDEA-01",
                "baseline": "待人工补全",
                "primary_metric": "",
                "budget": "",
            })
            _write(root / "paper.json", {
                "status": "needs_evidence",
                "slots": [
                    {"slot_id": "result.primary", "status": "pending_evidence"},
                    {"slot_id": "limitation", "status": "pending_evidence"},
                ],
            })
            _write(root / "figure.manifest.json", {
                "kind": "module_graph",
                "schematic": True,
            })
            _write(root / "claim-registry.json", {
                "entries": [{"claim_id": "CLM-1"}],
                "coverage": {"coverage_rate": 1.0},
            })

            capsule = build_loop_capsule(root)
            self.assertEqual(capsule["schema_version"], "research-loop-capsule-0.1")
            nodes = {item["id"]: item for item in capsule["nodes"]}
            self.assertEqual(nodes["S2-S3"]["status"], "needs_human")
            self.assertEqual(nodes["S4"]["status"], "needs_human")
            self.assertEqual(nodes["S5"]["status"], "missing")
            self.assertEqual(nodes["S6"]["status"], "partial")
            self.assertEqual(nodes["S8-S12"]["status"], "needs_human")
            self.assertEqual(nodes["S13"]["status"], "missing")
            self.assertIn("G1_IDEA_SELECTION_REQUIRED", capsule["blockers"])
            self.assertIn("G2_PROTOCOL_FREEZE_REQUIRED", capsule["blockers"])
            self.assertIn("S5_NOT_RUN", capsule["blockers"])
            self.assertIn("CLOSURE_NOT_RUN", capsule["blockers"])
            gates = {item["gate"] for item in capsule["next_actions"]}
            self.assertTrue({"G1", "G2", "S5", "G5"}.issubset(gates))
            self.assertEqual(capsule["claim_registry"]["entries"], 1)
            self.assertIn("read-only projection", capsule["boundary"])

            path = write_loop_capsule(root)
            self.assertTrue(path.is_file())
            update_loop_capsule_meta(root, "OBS-1", "ACT-1")
            updated = json.loads(path.read_text(encoding="utf-8"))
            meta = next(item for item in updated["nodes"] if item["id"] == "META")
            self.assertEqual(meta["status"], "partial")
            self.assertEqual(meta["observation_id"], "OBS-1")
            self.assertEqual(meta["active_policy_id"], "ACT-1")

    def test_writing_audit_projects_to_s8(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "task.json", {"task_id": "TASK-3", "status": "needs_human"})
            _write(root / "demo.json", {"run_id": "RUN-3", "fixture_mode": False, "gates": []})
            _write(root / "paper.json", {
                "status": "needs_evidence",
                "slots": [{"slot_id": "result.primary", "status": "pending_evidence"}],
            })
            _write(root / "manuscript-audit.json", {
                "status": "blocked",
                "submission_ready": False,
                "blockers": ["results.signed_claim: pending"],
                "external_lint": {"status": "blocked", "issues": [{"code": "PLACEHOLDER_FOUND"}]},
                "external_consistency": {"status": "attention", "issues": []},
            })
            capsule = build_loop_capsule(root)
            nodes = {item["id"]: item for item in capsule["nodes"]}
            self.assertEqual(nodes["S8-S12"]["status"], "blocked")
            self.assertEqual(nodes["S8-S12"]["writing_status"], "blocked")
            self.assertEqual(capsule["writing"]["status"], "blocked")
            self.assertEqual(
                capsule["writing"]["external_gates"]["external_lint"]["status"],
                "blocked",
            )
            self.assertEqual(
                capsule["writing"]["external_gates"]["external_consistency"]["status"],
                "attention",
            )
            self.assertIn("WRITING_AUDIT_BLOCKED", capsule["blockers"])
            commands = [
                item for item in capsule["next_actions"]
                if item.get("gate") == "S8-S12"
            ]
            self.assertTrue(commands)
            self.assertNotIn("--project", commands[0]["command"])
            self.assertIn("runtime job", commands[0]["command"])

    def test_capsule_claim_command_carries_the_proposed_assertion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "task.json", {"task_id": "TASK-3", "status": "completed"})
            _write(root / "demo.json", {
                "run_id": "RUN-3",
                "fixture_mode": False,
                "gates": [],
                "modules": {
                    "run": {
                        "status": "completed",
                        "capsule": {"status": "completed"},
                        "claim_draft_record": {
                            "scope": "S5/demo/iris",
                            "assertion_proposal": {
                                "assertion_argument": (
                                    "metric=accuracy,value=0.9111,comparator=>=,tolerance=0.0"
                                )
                            },
                        },
                    }
                },
            })
            capsule = build_loop_capsule(root)
            self.assertIn("CLAIM_UNSIGNED", capsule["blockers"])
            action = next(item for item in capsule["next_actions"] if item["gate"] == "S5b")
            # The host copies this string; it must not be weaker than the draft it just read.
            self.assertIn("--scope S5/demo/iris", action["command"])
            self.assertIn('--assertion "metric=accuracy,value=0.9111', action["command"])
            self.assertNotIn('--scope "..."', action["command"])

    def test_an_incomplete_study_design_blocks_s4(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "task.json", {"task_id": "TASK-5", "status": "completed"})
            _write(root / "demo.json", {
                "run_id": "RUN-5",
                "fixture_mode": False,
                "gates": [],
                "modules": {
                    "experiment": {"status": "ready_for_g2"},
                    "study_design": {
                        "audit": {
                            "status": "incomplete",
                            "blockers": ["claims.present: 0 claim(s)"],
                            "ccfa": {"level": "disclosure_incomplete"},
                        }
                    },
                },
            })
            capsule = build_loop_capsule(root)
            self.assertIn("STUDY_DESIGN_INCOMPLETE", capsule["blockers"])
            nodes = {item["id"]: item for item in capsule["nodes"]}
            self.assertEqual(nodes["S4"]["status"], "blocked")
            self.assertEqual(nodes["S4"]["ccfa_level"], "disclosure_incomplete")
            self.assertTrue(
                any(item["gate"] == "G2" for item in capsule["next_actions"])
            )

    def test_a_signed_closure_is_done_not_still_waiting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "task.json", {"task_id": "TASK-4", "status": "completed"})
            _write(root / "demo.json", {
                "run_id": "RUN-4",
                "fixture_mode": False,
                "gates": [{"gate": "G5", "status": "blocked", "reason": "no signature"}],
                "modules": {
                    "run": {
                        "status": "completed",
                        "capsule": {"status": "completed"},
                        "claim_draft_record": {"scope": "S5/demo/iris"},
                    }
                },
            })
            _write(root / "claim" / "claim.json", {"status": "supported", "claim_id": "CLM-4"})
            _write(root / "closure" / "closure-report.json", {"status": "ready"})

            unsigned = build_loop_capsule(root)
            self.assertIn("CLOSURE_UNSIGNED", unsigned["blockers"])
            nodes = {item["id"]: item for item in unsigned["nodes"]}
            self.assertEqual(nodes["S13"]["status"], "ready")

            _write(root / "closure-signature" / "signature.json", {
                "signature_id": "SIG-4",
                "human_reason": "[delegated:autopilot] G5 closure signature",
            })
            signed = build_loop_capsule(root)
            self.assertNotIn("CLOSURE_UNSIGNED", signed["blockers"])
            self.assertNotIn("CLOSURE_NOT_RUN", signed["blockers"])
            gates = {item["gate"]: item for item in signed["human_gates"]}
            self.assertEqual(gates["G5"]["status"], "pass")
            self.assertIn("delegated", gates["G5"]["reason"])
            nodes = {item["id"]: item for item in signed["nodes"]}
            self.assertEqual(nodes["S13"]["status"], "done")
            self.assertEqual(nodes["S5"]["claim_status"], "signed")

    def test_capsule_never_invents_s5_claim_or_closure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "task.json", {"task_id": "TASK-2", "status": "completed"})
            _write(root / "demo.json", {"run_id": "RUN-2", "fixture_mode": False, "gates": []})
            capsule = build_loop_capsule(root)
            nodes = {item["id"]: item for item in capsule["nodes"]}
            self.assertEqual(nodes["S5"]["status"], "missing")
            self.assertEqual(nodes["S13"]["status"], "missing")
            self.assertIn("S5_NOT_RUN", capsule["blockers"])
            self.assertIn("CLOSURE_NOT_RUN", capsule["blockers"])
            self.assertEqual(capsule["claim_registry"]["entries"], 0)


if __name__ == "__main__":
    unittest.main()

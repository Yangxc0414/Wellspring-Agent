import json
import tempfile
import unittest
from pathlib import Path

from research_agent.flow import (
    FlowError,
    design_sha256,
    load_g1_decision,
    validate_frozen_protocol,
)
from research_agent.modules.experiment import ExperimentDesignAgent
from research_agent.modules.run import RunAgent
from research_agent.pipeline import PipelineRequest, PipelineRunner, write_pipeline_artifacts
from research_agent.specs import SpecStore


class ExplicitFlowTest(unittest.TestCase):
    def setUp(self):
        self.store = SpecStore()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_design_hash_ignores_transient_id_and_warnings(self):
        design = {
            "design_id": "D-1",
            "question": "q",
            "hypothesis": "h",
            "baseline": "b",
            "primary_metric": "m",
            "controls": ["c"],
            "seeds": 3,
            "budget": "3 seeds",
            "stopping_rule": "fixed",
            "evidence_refs": ["S-1"],
            "status": "ready_for_g2",
            "warnings": ["one"],
            "idea_id": "IDEA-1",
        }
        changed = dict(design, design_id="D-2", warnings=["two"], status="needs_human")
        self.assertEqual(design_sha256(design), design_sha256(changed))

    def test_strict_flow_stops_at_g1_g2_then_binds_protocol(self):
        out1 = self.root / "g1-stop"
        first = PipelineRunner(self.store).run(
            PipelineRequest(
                topic="strict flow fixture",
                language="en",
                venue_type="en_conference",
                flow_mode="strict",
            )
        )
        self.assertEqual(first.status, "needs_g1")
        self.assertEqual(first.stopped_at, "G1")
        self.assertNotIn("experiment", first.modules)
        paths1 = write_pipeline_artifacts(first, out1)
        idea = json.loads(Path(paths1["idea"]).read_text(encoding="utf-8"))
        selected = idea["candidates"][0]["idea_id"]
        decision_path = out1 / "g1-decision.json"
        decision_path.write_text(
            json.dumps({
                "status": "approved",
                "selected_idea_id": selected,
                "human_reason": "selected for strict-flow test",
            }),
            encoding="utf-8",
        )

        out2 = self.root / "g2-stop"
        second = PipelineRunner(self.store).run(
            PipelineRequest(
                topic="strict flow fixture",
                language="en",
                venue_type="en_conference",
                flow_mode="strict",
                g1_decision_file=str(decision_path),
                run_dataset="iris",
                run_seeds=3,
            )
        )
        self.assertEqual(second.status, "needs_g2")
        self.assertEqual(second.stopped_at, "G2")
        self.assertNotIn("run", second.modules)
        paths2 = write_pipeline_artifacts(second, out2)
        design = json.loads(Path(paths2["experiment"]).read_text(encoding="utf-8"))
        agent = ExperimentDesignAgent(self.store.load("experiment"))
        frozen = agent.freeze_design(
            design, "fixture only", "reviewed design", out2
        )

        out3 = self.root / "run"
        third = PipelineRunner(self.store, run_output_dir=out3 / "run").run(
            PipelineRequest(
                topic="strict flow fixture",
                language="en",
                venue_type="en_conference",
                flow_mode="strict",
                g1_decision_file=str(decision_path),
                protocol_file=frozen["path"],
                run_dataset="iris",
                run_seeds=3,
            )
        )
        self.assertEqual(third.status, "needs_human")
        self.assertEqual(third.stopped_at, "")
        self.assertEqual(third.modules["run"]["capsule"]["status"], "completed")
        self.assertEqual(
            third.modules["run"]["capsule"]["protocol_sha256"],
            frozen["protocol"]["design_sha256"],
        )
        self.assertTrue(third.modules.get("protocol_binding"))
        self.assertEqual(
            third.modules["protocol_binding"]["design_sha256"],
            frozen["protocol"]["design_sha256"],
        )
        paths3 = write_pipeline_artifacts(third, out3)
        self.assertTrue(Path(paths3["protocol_binding"]).is_file())
        self.assertTrue(Path(paths3["demo"]).is_file())

        draft = third.modules["run"]["claim_draft_record"]
        claim = RunAgent(self.store.load("run")).claim(
            Path(third.modules["run"]["paths"]["capsule"]),
            Path(third.modules["run"]["paths"]["ea"]),
            draft["statement"],
            "human signed after reviewing EA",
            "S5/demo/iris",
            self.root / "signed-claim",
        )
        out4 = self.root / "signed"
        fourth = PipelineRunner(self.store, run_output_dir=out4 / "run").run(
            PipelineRequest(
                topic="strict flow fixture",
                language="en",
                venue_type="en_conference",
                flow_mode="strict",
                g1_decision_file=str(decision_path),
                protocol_file=frozen["path"],
                run_dataset="iris",
                run_dir=str(Path(third.modules["run"]["paths"]["capsule"]).parent),
                claim_file=claim["path"],
            )
        )
        self.assertEqual(fourth.status, "needs_human")
        self.assertEqual(fourth.modules["paper"]["claims"], [claim["claim"]["claim_id"]])
        s5 = next(gate for gate in fourth.gates if gate["gate"] == "S5")
        self.assertEqual(s5["status"], "pass")
        self.assertIn("signed supported claim", s5["reason"])
        paths4 = write_pipeline_artifacts(
            fourth, out4, claim_file=claim["path"]
        )
        self.assertTrue(Path(paths4["postprocess"]).is_file())
        self.assertTrue(Path(paths4["closure"]).is_file())
        self.assertTrue(Path(paths4["lineage"]).is_file())
        postprocess = json.loads(Path(paths4["postprocess"]).read_text(encoding="utf-8"))
        self.assertIn(postprocess["closure"]["status"], ("ready", "blocked"))
        self.assertIn(postprocess["lineage"]["status"], ("complete", "partial"))
        closure_report = json.loads(
            Path(paths4["closure"]).read_text(encoding="utf-8")
        )
        closure_checks = {
            item["name"]: item["status"] for item in closure_report.get("checks", [])
        }
        self.assertEqual(closure_checks.get("protocol_frozen"), "pass")

        from research_agent.bibliography import BibliographyAgent

        bibliography = BibliographyAgent().verify(
            Path(__file__).resolve().parents[1]
            / "modules" / "literature" / "fixtures" / "bibliography.json",
            self.root / "bibliography",
        )
        out5 = self.root / "closed"
        fifth = PipelineRunner(self.store, run_output_dir=out5 / "run").run(
            PipelineRequest(
                topic="strict flow fixture",
                language="en",
                venue_type="en_conference",
                flow_mode="strict",
                g1_decision_file=str(decision_path),
                protocol_file=frozen["path"],
                run_dir=str(Path(third.modules["run"]["paths"]["capsule"]).parent),
                claim_file=claim["path"],
                bibliography_file=bibliography["path"],
            )
        )
        def support_judge(payload):
            return [{
                "id": item["id"],
                "status": "supported",
                "rationale": "fixture judge",
                "evidence_refs": [item["evidence"][0]["ref"]],
            } for item in payload["items"]]

        paths5 = write_pipeline_artifacts(
            fifth,
            out5,
            claim_file=claim["path"],
            support_judge=support_judge,
        )
        support = json.loads(Path(paths5["support_audit"]).read_text(encoding="utf-8"))
        self.assertEqual(support["method"], "model_judge")
        self.assertEqual(support["status"], "ready")
        self.assertEqual(support["counts"]["supported"], len(support["items"]))
        gates = {gate["gate"]: gate for gate in fifth.gates}
        self.assertEqual(gates["G3"]["status"], "pass")
        self.assertEqual(gates["G5"]["status"], "needs_human")
        closure5 = json.loads(Path(paths5["closure"]).read_text(encoding="utf-8"))
        self.assertEqual(closure5["status"], "ready")
        self.assertEqual(closure5["unresolved"], [])
        from research_agent.closure import ClosureAgent
        from research_agent.signers import SignerStore

        signers = SignerStore(self.root / "signers.json")
        signer = signers.create("flow-test-signer")
        signature = ClosureAgent().sign(
            Path(paths5["closure"]),
            out5 / "demo.json",
            out5 / "claim" / "claim.json",
            "reviewed closure for flow test",
            out5 / "signature",
            signer_store=signers,
            signer_id=signer["signer_id"],
        )
        self.assertEqual(signature["scheme"], "hmac-sha256-local")
        self.assertEqual(signature["signature"]["signer_id"], signer["signer_id"])
        self.assertTrue(Path(signature["path"]).is_file())
        self.assertTrue(Path(signature["manifest"]).is_file())
        published = ClosureAgent().publish(
            Path(signature["manifest"]),
            out5 / "publish",
            signature_path=Path(signature["path"]),
            bundle_name="flow-bundle",
            signer_store=signers,
        )
        verification = ClosureAgent().verify_bundle(
            Path(published["bundle"]), signer_store=signers
        )
        self.assertEqual(verification["status"], "clean")
        self.assertTrue(verification["signed"])
        self.assertTrue(verification["signature_verified"])
        self.assertEqual(verification["errors"], [])

    def test_g1_decision_must_select_a_current_candidate(self):
        from research_agent.contracts import IdeaCard

        path = self.root / "bad-g1.json"
        path.write_text(
            json.dumps({
                "status": "approved",
                "selected_idea_id": "IDEA-OTHER",
                "human_reason": "test",
            }),
            encoding="utf-8",
        )
        card = IdeaCard("IDEA-1", "t", "h", "f", ["S-1"])
        with self.assertRaises(FlowError):
            load_g1_decision(path, [card])

    def test_protocol_mismatch_is_rejected(self):
        design = {
            "question": "q",
            "hypothesis": "h",
            "baseline": "b",
            "primary_metric": "m",
            "controls": ["c"],
            "seeds": 3,
            "budget": "3 seeds",
            "stopping_rule": "fixed",
            "evidence_refs": ["S-1"],
            "status": "ready_for_g2",
            "idea_id": "IDEA-1",
        }
        agent = ExperimentDesignAgent(self.store.load("experiment"))
        frozen = agent.freeze_design(design, "limit", "reason", self.root)
        changed = dict(design, primary_metric="another_metric")
        with self.assertRaises(FlowError):
            validate_frozen_protocol(Path(frozen["path"]), changed)


if __name__ == "__main__":
    unittest.main()

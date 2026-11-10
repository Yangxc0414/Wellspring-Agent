import json
import shutil
import tempfile
import unittest
from pathlib import Path

from research_agent.closure import ClosureAgent
from research_agent.maintenance import MaintenanceAgent, MaintenanceError

REPO = Path(__file__).resolve().parents[1]
CLOSED = REPO / "research_agent" / "web" / "data" / "closed-loop"
CHANGED = REPO / "research_agent" / "web" / "data" / "closed-loop-changed"


class MaintenanceTest(unittest.TestCase):
    def test_planned_data_change_blocks_reclosure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            agent = MaintenanceAgent()
            planned = agent.plan(
                CLOSED / "lineage" / "lineage.json",
                CHANGED,
                actor="author",
                reason="dataset snapshot changed",
                output_dir=root / "plan",
            )
            plan = planned["plan"]
            self.assertEqual(plan["status"], "blocked_pending_work")
            self.assertFalse(plan["auto_reclose_allowed"])
            self.assertFalse(plan["export_allowed"])
            self.assertGreaterEqual(plan["action_counts"].get("rerun", 0), 1)
            self.assertGreaterEqual(plan["action_counts"].get("rewrite", 0), 1)
            result = agent.reclose(
                Path(planned["path"]),
                CHANGED,
                CHANGED / "bound" / "demo.json",
                CHANGED / "claim" / "claim.json",
                root / "reclose",
            )
            self.assertEqual(result["status"], "blocked_pending_work")
            self.assertFalse(result["signed"])
            self.assertFalse((root / "reclose" / "closure-report.json").exists())

    def test_recheck_only_reclosure_then_human_sign_and_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundle = root / "bundle"
            shutil.copytree(CLOSED, bundle)
            signature_path = bundle / "signature" / "signature.json"
            signature = json.loads(signature_path.read_text(encoding="utf-8"))
            signature["human_reason"] = "simulated metadata-only change"
            signature_path.write_text(json.dumps(signature), encoding="utf-8")
            demo = bundle / "bound" / "demo.json"
            claim = bundle / "claim" / "claim.json"
            agent = MaintenanceAgent()
            planned = agent.plan(
                CLOSED / "lineage" / "lineage.json",
                bundle,
                actor="author",
                reason="signature metadata changed",
                output_dir=root / "plan",
            )
            self.assertEqual(planned["plan"]["status"], "ready_for_reclosure")
            self.assertTrue(planned["plan"]["auto_reclose_allowed"])
            self.assertFalse(planned["plan"]["export_allowed"])
            with self.assertRaises(MaintenanceError):
                agent.reclose(
                    Path(planned["path"]), bundle,
                    CLOSED / "bound" / "demo.json", claim, root / "bad-reclose",
                )
            reclosure = agent.reclose(
                Path(planned["path"]), bundle, demo, claim, root / "reclose",
            )
            self.assertEqual(reclosure["report"]["status"], "ready_for_resign")
            self.assertFalse(reclosure["report"]["signed"])
            self.assertFalse((root / "reclose" / "signature.json").exists())
            signed = ClosureAgent().sign(
                Path(reclosure["report"]["closure_report_path"]),
                demo,
                claim,
                "maintenance re-sign after metadata change",
                root / "signed",
            )
            published = ClosureAgent().publish(Path(signed["manifest"]), root / "published")
            self.assertTrue(published["signed"])
            self.assertEqual(ClosureAgent().verify_bundle(Path(published["bundle"]))["status"], "clean")

    def test_plan_requires_actor_and_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(MaintenanceError):
                MaintenanceAgent().plan(
                    CLOSED / "lineage" / "lineage.json", CLOSED,
                    actor="", reason="", output_dir=Path(tmp),
                )


if __name__ == "__main__":
    unittest.main()

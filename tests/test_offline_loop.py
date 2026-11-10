import json
import tempfile
import unittest
from pathlib import Path

from research_agent.empirical_loop import run_empirical_paper
from research_agent.experiment_codegen import generate_experiment_code
from research_agent.experiment_closure import sign_experiment_closure
from research_agent.experiment_runner import (
    approve_experiment,
    execute_experiment,
    ingest_experiment,
    sign_experiment_claim,
)
from research_agent.loop_capsule import write_loop_capsule
from research_agent.signers import SignerStore
from research_agent.storage import write_json_atomic
from tests.writing_support import RUN_ID, make_writing_project


class OfflineLoopTest(unittest.TestCase):
    def test_offline_draft_reaches_closure_and_capsule(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            run = project / "runs" / RUN_ID
            design = json.loads((run / "experiment.json").read_text(encoding="utf-8"))
            design["idea_id"] = "IDEA-01"
            write_json_atomic(run / "experiment.json", design)
            write_json_atomic(run / "innovation-review.json", {
                "status": "reviewed",
                "final_ideas": [{"idea_id": "IDEA-01", "title": "offline loop"}],
            })
            data = project / "data.csv"
            rows = ["x1,x2,y"]
            for index in range(48):
                rows.append("%d,%d,%d" % (index, index % 5, index * 2 + (index % 4)))
            data.write_text("\n".join(rows) + "\n", encoding="utf-8")

            generate_experiment_code(
                project,
                RUN_ID,
                data_path="data.csv",
                target="y",
                features=["x1", "x2"],
                task="regression",
                methods=["dummy", "ridge"],
                seeds=2,
                experiment_id="EXP-OFFLINE",
            )
            approve_experiment(project, "EXP-OFFLINE", "offline test approval")
            execution = execute_experiment(
                project, "EXP-OFFLINE", allow_execute=True
            )
            self.assertEqual(execution["status"], "completed", execution)
            ingest_experiment(project, "EXP-OFFLINE")
            sign_experiment_claim(
                project,
                "EXP-OFFLINE",
                "Ridge is compared with the dummy baseline under the local protocol.",
                "checked synthetic protocol",
                ["metric=r2,value=0.0,comparator=>=,tolerance=0.01"],
            )

            result = run_empirical_paper(
                project,
                RUN_ID,
                "EXP-OFFLINE",
                project / "drafts" / "offline-empirical.md",
                review_rounds=0,
                offline_draft=True,
            )
            self.assertEqual(result["status"], "ready_for_human_review", result)
            self.assertEqual(
                result["final_audit"]["status"], "ready_for_human_review"
            )
            self.assertEqual(
                result["closure"]["status"], "ready_for_human_signature"
            )
            draft = Path(result["draft"]["path"]).read_text(encoding="utf-8")
            self.assertIn("[REF-", draft)
            self.assertIn("## 参考文献", draft)
            self.assertNotIn("TODO", draft)
            self.assertNotIn("待补", draft)

            capsule_path = write_loop_capsule(run)
            capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
            nodes = {item["id"]: item for item in capsule["nodes"]}
            self.assertEqual(nodes["S8-S12"]["status"], "needs_human")
            self.assertEqual(nodes["S13"]["status"], "ready")
            self.assertEqual(capsule["writing"]["status"], "ready_for_human_review")
            self.assertFalse(capsule["writing"]["submission_ready"])

            signers = SignerStore(root / "signers.json")
            signer = signers.create("offline-loop-test")
            signed = sign_experiment_closure(
                project,
                "EXP-OFFLINE",
                project
                / "experiments"
                / "EXP-OFFLINE"
                / "experiment-closure"
                / "closure-report.json",
                "test-only local HMAC signature for capsule transition",
                signer_store=signers,
                signer_id=signer["signer_id"],
                manuscript=Path(result["draft"]["path"]),
            )
            self.assertTrue(Path(signed["signature_path"]).is_file())
            signed_capsule = json.loads(
                write_loop_capsule(run).read_text(encoding="utf-8")
            )
            signed_nodes = {item["id"]: item for item in signed_capsule["nodes"]}
            self.assertEqual(signed_nodes["S13"]["status"], "done")
            self.assertNotIn("EXPERIMENT_CLOSURE_UNSIGNED", signed_capsule["blockers"])


if __name__ == "__main__":
    unittest.main()

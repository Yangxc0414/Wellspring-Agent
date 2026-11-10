import json
import tempfile
import unittest
from pathlib import Path

from research_agent.experiment_codegen import generate_experiment_code
from research_agent.experiment_closure import check_experiment_closure
from research_agent.experiment_runner import (
    approve_experiment,
    execute_experiment,
    ingest_experiment,
    sign_experiment_claim,
)
from research_agent.pipeline import (
    PipelineRequest,
    PipelineRunner,
    write_pipeline_artifacts,
)
from research_agent.loop_capsule import write_loop_capsule
from research_agent.project import init_project
from research_agent.specs import SpecStore
from research_agent.writing_pack import build_writing_pack


class ResearchLoopE2ETest(unittest.TestCase):
    def test_pipeline_design_feeds_experiment_and_writing_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            init_project(project, "loop-e2e")
            run_id = "RUN-LOOP-E2E"
            result = PipelineRunner(SpecStore()).run(
                PipelineRequest(
                    topic="钙钛矿 界面 钝化 湿热稳定性 实证闭环",
                    language="zh",
                    venue_type="zh_core_journal",
                    run_id=run_id,
                    max_sources=4,
                )
            )
            run = project / "runs" / run_id
            run.mkdir(parents=True, exist_ok=True)
            paths = write_pipeline_artifacts(result, run)
            self.assertTrue(Path(paths["loop_capsule"]).is_file())
            experiment = result.modules.get("experiment") or {}
            idea_id = str(experiment.get("idea_id") or "")
            self.assertIn(idea_id, {"IDEA-01", "IDEA-02", "IDEA-03"}, experiment)

            data = project / "data.csv"
            rows = ["x1,x2,y"]
            for index in range(40):
                rows.append("%d,%d,%d" % (index, index % 5, index * 2 + (index % 4)))
            data.write_text("\n".join(rows) + "\n", encoding="utf-8")

            generated = generate_experiment_code(
                project,
                run_id,
                data_path="data.csv",
                target="y",
                features=["x1", "x2"],
                task="regression",
                methods=["dummy", "ridge"],
                seeds=2,
                experiment_id="EXP-LOOP-E2E",
            )
            self.assertEqual(generated["spec"]["run_id"], run_id)
            self.assertEqual(generated["spec"]["idea_id"], idea_id)

            approve_experiment(project, "EXP-LOOP-E2E", "checked design and data")
            execution = execute_experiment(
                project, "EXP-LOOP-E2E", allow_execute=True
            )
            self.assertEqual(execution["status"], "completed", execution)
            ingest_experiment(project, "EXP-LOOP-E2E")
            claim = sign_experiment_claim(
                project,
                "EXP-LOOP-E2E",
                "Ridge is compared with the dummy baseline under the local protocol.",
                "checked synthetic protocol",
                ["metric=r2,value=0.0,comparator=>=,tolerance=0.01"],
            )
            self.assertEqual(claim["status"], "supported")
            self.assertEqual(len(claim["evidence_sha256"]), 64)

            pack = build_writing_pack(
                project, run_id, experiment_id="EXP-LOOP-E2E"
            )
            self.assertEqual(pack["claim"]["status"], "signed")
            self.assertTrue(pack["run"]["ea"]["hash_bound"])
            self.assertEqual(
                pack["run"]["ea"]["bound_claim_id"], "CLAIM-EXP-LOOP-E2E"
            )
            self.assertTrue(pack["writing_contract"]["allowed_result_numbers"])
            self.assertEqual(
                pack["experiment_design"]["idea_id"],
                idea_id,
            )

            closure = check_experiment_closure(project, "EXP-LOOP-E2E")
            self.assertEqual(closure["status"], "ready_for_human_signature", closure)
            capsule_path = write_loop_capsule(run)
            capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
            nodes = {item["id"]: item for item in capsule["nodes"]}
            self.assertEqual(nodes["S5"]["status"], "done")
            self.assertEqual(nodes["S5"]["experiment_id"], "EXP-LOOP-E2E")
            self.assertEqual(nodes["S13"]["status"], "ready")
            self.assertIn("EXPERIMENT_CLOSURE_UNSIGNED", capsule["blockers"])
            self.assertEqual(capsule["experiments"][0]["experiment_id"], "EXP-LOOP-E2E")


if __name__ == "__main__":
    unittest.main()

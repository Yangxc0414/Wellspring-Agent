import json
import tempfile
import unittest
from pathlib import Path

from research_agent.empirical_loop import check_empirical_loop
from research_agent.experiment_closure import (
    build_experiment_lineage,
    check_experiment_closure,
    verify_experiment_lineage,
)
from research_agent.experiment_codegen import generate_experiment_code
from research_agent.experiment_figures import build_result_figure
from research_agent.loop_capsule import write_loop_capsule
from research_agent.experiment_runner import (
    approve_experiment,
    approve_sweep,
    execute_experiment,
    execute_sweep,
    ingest_experiment,
    ingest_sweep,
    sign_experiment_claim,
)
from research_agent.manuscript_writer import generate_manuscript
from research_agent.storage import write_json_atomic
from research_agent.writing_pack import build_writing_pack, render_writing_pack
from tests.writing_support import RUN_ID, make_writing_project, write_draft

EXPERIMENT_ID = "EXP-E2E"


class _FakeWriter:
    model_id = "fake:e2e-writer"

    def __init__(self, text):
        self.text = text

    def complete(self, messages, json_mode=True):
        return self.text


def _innovation() -> dict:
    return {
        "status": "reviewed",
        "gaps": [
            {
                "gap_id": "GAP-01",
                "description": "学习曲线评估缺少统一协议",
                "why_unresolved": "现有工作各自定义指标",
                "observable": "跨种子方差",
                "evidence_refs": ["REF-01", "REF-02"],
            }
        ],
        "final_ideas": [
            {
                "idea_id": "IDEA-01",
                "title": "统一学习曲线评估",
                "mechanism": "证据账本约束评估协议",
                "falsification": "若跨数据集方差无下降则否证",
                "evidence_refs": ["REF-01", "REF-02"],
            }
        ],
    }


class EmpiricalEndToEndTest(unittest.TestCase):
    def test_sweep_confirm_figure_table_writing_closure_lineage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_writing_project(root)
            data = project / "data.csv"
            rows = ["x1,x2,y"]
            for index in range(48):
                rows.append(
                    "%d,%d,%d" % (index, index % 5, index * 2 + (index % 4))
                )
            data.write_text("\n".join(rows) + "\n", encoding="utf-8")
            run = project / "runs" / RUN_ID
            design = json.loads((run / "experiment.json").read_text(encoding="utf-8"))
            design["idea_id"] = "IDEA-01"
            write_json_atomic(run / "experiment.json", design)
            write_json_atomic(run / "innovation-review.json", _innovation())

            generated = generate_experiment_code(
                project,
                RUN_ID,
                data_path="data.csv",
                target="y",
                features=["x1", "x2"],
                task="regression",
                methods=["dummy", "ridge"],
                seeds=2,
                cv_folds=3,
                alpha_grid=[0.1, 1, 10],
                experiment_id=EXPERIMENT_ID,
            )
            package = Path(generated["output_dir"])

            approve_sweep(project, EXPERIMENT_ID, "checked sweep plan")
            sweep_execution = execute_sweep(
                project, EXPERIMENT_ID, allow_execute=True
            )
            self.assertEqual(sweep_execution["status"], "completed", sweep_execution)
            sweep_evidence = ingest_sweep(project, EXPERIMENT_ID)
            self.assertEqual(
                sweep_evidence["status"], "verified_exploratory", sweep_evidence
            )
            best_alpha = sweep_evidence["best_alpha"]
            self.assertIsNotNone(best_alpha)

            approve_experiment(
                project,
                EXPERIMENT_ID,
                "confirmed sweep alpha",
                ridge_alpha=best_alpha,
            )
            execution = execute_experiment(
                project,
                EXPERIMENT_ID,
                allow_execute=True,
                ridge_alpha=best_alpha,
            )
            self.assertEqual(execution["status"], "completed", execution)
            evidence = ingest_experiment(project, EXPERIMENT_ID)
            self.assertEqual(evidence["status"], "verified", evidence["blockers"])
            self.assertEqual(evidence["ridge_alpha"], best_alpha)
            claim = sign_experiment_claim(
                project,
                EXPERIMENT_ID,
                "The selected alpha reproduces the sweep choice under the local protocol.",
                "checked sweep, CV, metrics and hashes",
                ["metric=r2,value=-1.0,comparator=>=,tolerance=0.01"],
            )
            self.assertEqual(claim["status"], "supported")
            self.assertEqual(claim["ridge_alpha"], best_alpha)

            figure = build_result_figure(project, EXPERIMENT_ID)
            self.assertEqual(figure["kind"], "data_result_plot")
            self.assertTrue(Path(figure["png"]).is_file())
            self.assertTrue((package / "outputs" / "results-table.md").is_file())

            preflight = check_empirical_loop(project, RUN_ID, EXPERIMENT_ID)
            self.assertEqual(preflight["status"], "ready_for_writing", preflight)

            pack = build_writing_pack(
                project, RUN_ID, experiment_id=EXPERIMENT_ID
            )
            write_json_atomic(run / "writing-pack.json", pack)
            (run / "writing-pack.md").write_text(
                render_writing_pack(pack), encoding="utf-8"
            )
            self.assertEqual(pack["claim"]["status"], "signed")
            self.assertIsNotNone(pack["experiment_package"]["figure"])
            self.assertTrue(pack["experiment_package"]["results_table"])

            draft_text = write_draft(
                root / "seed.md",
                result_text="图 1 和表 1 展示了不同方法的均值、标准差与配对差异。",
            ).read_text(encoding="utf-8")
            output = project / "drafts" / "empirical.md"
            written = generate_manuscript(
                project,
                RUN_ID,
                output,
                model=_FakeWriter(draft_text),
                innovation=_innovation(),
            )
            self.assertEqual(written["status"], "generated", written)
            self.assertEqual(
                written["audit"]["status"], "ready_for_human_review", written
            )

            closure = check_experiment_closure(
                project, EXPERIMENT_ID, manuscript=output
            )
            self.assertEqual(
                closure["status"], "ready_for_human_signature", closure["blockers"]
            )
            checks = {item["id"]: item for item in closure["checks"]}
            self.assertEqual(checks["claim.ridge_alpha"]["status"], "pass")
            self.assertEqual(checks["results_table.hash"]["status"], "pass")
            self.assertEqual(checks["claim.results_table"]["status"], "pass")

            capsule_path = write_loop_capsule(run)
            capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
            nodes = {item["id"]: item for item in capsule["nodes"]}
            self.assertEqual(nodes["S5"]["status"], "done", capsule)
            self.assertEqual(nodes["S5"]["experiment_id"], EXPERIMENT_ID)
            self.assertEqual(nodes["S13"]["status"], "ready", capsule)
            self.assertIn("EXPERIMENT_CLOSURE_UNSIGNED", capsule["blockers"])
            self.assertEqual(capsule["experiments"][0]["experiment_id"], EXPERIMENT_ID)

            build_experiment_lineage(project, EXPERIMENT_ID)
            verified = verify_experiment_lineage(project, EXPERIMENT_ID)
            self.assertEqual(verified["status"], "fresh", verified)
            self.assertIn("results_table", [item["node_id"] for item in verified["checks"]])


if __name__ == "__main__":
    unittest.main()

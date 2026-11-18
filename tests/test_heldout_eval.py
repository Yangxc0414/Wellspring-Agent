"""Held-out rubric evaluator: deterministic checks, fail-closed on missing artifacts."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent.heldout_eval import (  # noqa: E402
    HeldoutEvalError,
    evaluate_run,
    load_tasks,
)

TASKS = ROOT / "research_agent" / "eval" / "heldout_tasks.json"
SECTIONS = (
    "Abstract", "Introduction", "Related Work", "Method",
    "Experimental Setup", "Results", "Discussion", "Conclusion",
)


def _idea(candidates=3):
    items = []
    for index in range(candidates):
        items.append({
            "idea_id": "IDEA-{0}".format(index + 1),
            "title": "t",
            "hypothesis": "h",
            "falsification": "f",
            "evidence_refs": ["S-1-S01-01"],
            "lens": "mechanism" if index % 2 == 0 else "boundary",
        })
    return {"candidates": items}


def _experiment(metric="accuracy", budget="3 seeds x 1 split", controls=2, seeds=3):
    return {
        "hypothesis": "h",
        "baseline": "b",
        "primary_metric": metric,
        "budget": budget,
        "controls": ["c{0}".format(i) for i in range(controls)],
        "seeds": seeds,
        "stopping_rule": "stop at n",
    }


def _paper(results_status="pending_evidence"):
    draft = []
    for name in SECTIONS:
        text = "text [S-1-S01-0{0}]".format(1 + len(draft) % 4)
        draft.append({"section": name, "text": text, "status": results_status if name == "Results" else "draft_evidence"})
    return {"sections": list(SECTIONS), "draft": draft}


class HeldoutEvalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="heldout-"))
        (self.tmp / "literature.json").write_text(json.dumps({"spans": [{"span_id": "S-1-S01-01"}]}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name, payload):
        (self.tmp / name).write_text(json.dumps(payload), encoding="utf-8")

    def test_complete_run_scores_full(self):
        self._write("idea.json", _idea())
        self._write("experiment.json", _experiment())
        self._write("paper.json", _paper())
        report = evaluate_run(self.tmp, TASKS)
        self.assertEqual(report["summary"]["passed"], 14)
        self.assertEqual(report["summary"]["total"], 14)

    def test_sentence_metric_and_vague_budget_fail(self):
        self._write("idea.json", _idea())
        self._write("experiment.json", _experiment(metric="Repository-level task success rate, measured by tests", budget="Not specified"))
        self._write("paper.json", _paper())
        report = evaluate_run(self.tmp, TASKS)
        experiment = [axis for axis in report["axes"] if axis["axis"] == "experiment"][0]
        failed = [check["id"] for check in experiment["checks"] if not check["passed"]]
        self.assertIn("experiment.metric_shape", failed)
        self.assertIn("experiment.budget", failed)

    def test_missing_artifact_is_not_run_not_pass(self):
        self._write("idea.json", _idea())
        report = evaluate_run(self.tmp, TASKS)
        axes = {axis["axis"]: axis for axis in report["axes"]}
        self.assertEqual(axes["experiment"]["status"], "not_run")
        self.assertEqual(axes["paper"]["status"], "not_run")
        self.assertEqual(report["summary"]["total"], 4)

    def test_results_with_number_fails_pending_check(self):
        self._write("idea.json", _idea())
        self._write("experiment.json", _experiment())
        self._write("paper.json", _paper(results_status="bound_claim"))
        report = evaluate_run(self.tmp, TASKS)
        paper = [axis for axis in report["axes"] if axis["axis"] == "paper"][0]
        self.assertFalse([check for check in paper["checks"] if check["id"] == "paper.results_pending"][0]["passed"])

    def test_unknown_task_id_is_rejected(self):
        with self.assertRaises(HeldoutEvalError):
            evaluate_run(self.tmp, TASKS, task_id="NO-SUCH-TASK")

    def test_task_file_schema_is_checked(self):
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"schema": "wrong"}), encoding="utf-8")
        with self.assertRaises(HeldoutEvalError):
            load_tasks(bad)


if __name__ == "__main__":
    unittest.main()

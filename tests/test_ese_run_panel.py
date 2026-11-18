"""Run panel generator: summary from demo.json, generated panel injection."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.build_ese_run_panel as panel  # noqa: E402


class DownstreamTest(unittest.TestCase):
    def test_downstream_reads_review_and_audit(self):
        import tempfile
        from pathlib import Path as P

        with tempfile.TemporaryDirectory() as tmp:
            review_dir = P(tmp) / 'manuscript-review'
            review_dir.mkdir()
            (review_dir / 'manuscript-review.json').write_text(json.dumps({
                'status': 'needs_more_work',
                'rounds_completed': 1,
                'iterations': [{'accepted': True}],
            }), encoding='utf-8')
            (review_dir / 'final-audit.json').write_text(json.dumps({
                'status': 'ready_for_human_review',
                'citation_count': 73,
                'han_character_count': 9401,
                'submission_ready': False,
            }), encoding='utf-8')
            summary = panel.downstream_summary(P(tmp) / 'run', review_dir)
        self.assertEqual(summary['manuscript_review']['status'], 'needs_more_work')
        self.assertTrue(summary['manuscript_review']['accepted'])
        self.assertEqual(summary['final_audit']['citation_count'], 73)
        self.assertFalse(summary['final_audit']['submission_ready'])

    def test_missing_downstream_is_empty(self):
        self.assertEqual(panel.downstream_summary('/tmp/nothing', '/tmp/nothing'), {})


class EseRunPanelTest(unittest.TestCase):
    def _run(self, tmp, stages, gates):
        run = Path(tmp) / "run"
        run.mkdir()
        (run / "demo.json").write_text(json.dumps({
            "run_id": "PIPE-TEST",
            "fixture_mode": False,
            "status": "needs_human",
            "modules": {key: {"status": value, "warnings": []} for key, value in stages.items()},
            "gates": [{"gate": g, "status": s, "reason": "r"} for g, s in gates],
        }), encoding="utf-8")
        return run

    def test_summary_keeps_stage_and_gate_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(tmp, {"literature": "ok", "paper": "needs_evidence"}, [("G1", "needs_human")])
            summary = panel.build_summary(run)
        self.assertEqual(summary["run_id"], "PIPE-TEST")
        self.assertEqual([item["status"] for item in summary["stages"]], ["ok", "needs_evidence"])
        self.assertEqual(summary["gates"][0]["gate"], "G1")
        self.assertFalse(summary["fixture_mode"])

    def test_panel_renders_boundary_and_gates(self):
        summary = {
            "run_id": "PIPE-TEST",
            "stages": [{"stage": "paper", "status": "needs_evidence", "warnings": 2}],
            "gates": [{"gate": "G5", "status": "blocked", "reason": "r"}],
            "boundary": "static mirror of one real local run",
        }
        html = panel.render_panel(summary)
        self.assertIn("PIPE-TEST", html)
        self.assertIn("needs_evidence", html)
        self.assertIn("G5=blocked", html)
        self.assertIn("static mirror", html)

    def test_missing_demo_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                panel.build_summary(tmp)


if __name__ == "__main__":
    unittest.main()

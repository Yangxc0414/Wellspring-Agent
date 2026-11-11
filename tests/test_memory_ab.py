import json
import tempfile
import unittest
from pathlib import Path

from research_agent.memory_ab import (
    MEMORY_AB_BOUNDARY,
    analysis,
    compare,
    record,
    score_arm,
)

LITERATURE = {
    "spans": [
        {"span_id": "SP-1", "source_id": "A"},
        {"span_id": "SP-2", "source_id": "B"},
    ]
}


def _good(index=0):
    return {
        "title": "可判定交互 %d" % index,
        "evidence_refs": ["SP-1", "SP-2"],
        "falsification": "在两个以上数据集上交互区间都覆盖零则该说法被否证",
        "experiment_plan": {
            "profile": "search_factorial",
            "dataset": "iris",
            "baseline": "memory_off_gate_off",
            "metric": "improvement_per_evaluation",
            "stopping_rule": "16 paired seeds",
        },
    }


def _weak():
    return {"title": "拼接想法", "evidence_refs": ["SP-1"], "falsification": "也许有效", "experiment_plan": {"profile": ""}}


class ScoreTests(unittest.TestCase):
    def test_rates_count_the_three_deterministic_checks(self):
        scored = score_arm([_good(0), _weak()], LITERATURE)
        self.assertEqual(scored["n"], 2)
        self.assertEqual(scored["rates"]["grounded_rate"], 0.5)
        self.assertEqual(scored["rates"]["executable_plan_rate"], 0.5)
        self.assertEqual(scored["per_idea"][0]["score"], 3)
        self.assertEqual(scored["per_idea"][1]["score"], 0)

    def test_empty_arm_has_no_rates(self):
        scored = score_arm([], LITERATURE)
        self.assertEqual(scored["n"], 0)
        self.assertIsNone(scored["rates"]["grounded_rate"])


class CompareTests(unittest.TestCase):
    def test_few_pairs_refuses_to_report_a_direction(self):
        with_arm = score_arm([_good(0), _good(1), _good(2)], LITERATURE)
        without_arm = score_arm([_weak(), _weak(), _weak()], LITERATURE)
        verdict = compare(with_arm, without_arm)
        self.assertTrue(verdict["underpowered"])
        self.assertEqual(verdict["direction"], "")
        self.assertIn("too few", verdict["reading"])

    def test_four_pairs_of_improvement_read_as_with_memory_better(self):
        with_arm = score_arm([_good(i) for i in range(4)], LITERATURE)
        without_arm = score_arm([_weak() for _ in range(4)], LITERATURE)
        verdict = compare(with_arm, without_arm)
        self.assertFalse(verdict["underpowered"])
        self.assertEqual(verdict["direction"], "with_memory_better")
        self.assertEqual(verdict["sign_counts"]["better"], 4)
        self.assertEqual(verdict["rates"]["delta"]["executable_plan_rate"], 1.0)
        self.assertIn("not a discovery claim", verdict["reading"])

    def test_identical_arms_read_as_no_difference(self):
        arm = score_arm([_good(i) for i in range(4)], LITERATURE)
        verdict = compare(arm, arm)
        self.assertEqual(verdict["direction"], "no_difference")
        self.assertEqual(verdict["sign_counts"]["tie"], 4)


class StoreTests(unittest.TestCase):
    def test_record_both_arms_then_analyse(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "memory").mkdir()
            self.assertEqual(analysis(project)["status"], "incomplete")
            record(project, run_id="RUN-1", arm="with", ideas=[_good(i) for i in range(4)],
                   literature=LITERATURE, guidance="## 本 run 已确认的做法")
            record(project, run_id="RUN-1", arm="without", ideas=[_weak() for _ in range(4)],
                   literature=LITERATURE, guidance="")
            result = analysis(project)
            self.assertEqual(result["status"], "compared")
            self.assertEqual(result["comparison"]["direction"], "with_memory_better")
            self.assertEqual(result["boundary"], MEMORY_AB_BOUNDARY)
            stored = (project / "memory" / "ab.json").read_text(encoding="utf-8")
            self.assertIn("guidance_chars", stored)


class CLITests(unittest.TestCase):
    def test_plan_record_compare_via_cli(self):
        import json
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "proj"
            (project / "memory").mkdir(parents=True)
            ideas = root / "ideas.json"
            literature = root / "lit.json"
            ideas.write_text(json.dumps({"selected_ideas": [_good(i) for i in range(4)]}), encoding="utf-8")
            literature.write_text(json.dumps(LITERATURE), encoding="utf-8")

            def run(*args):
                return subprocess.run(
                    [sys.executable, "-m", "research_agent", *args],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )

            planned = run("memory", "ab", "plan", "--project", str(project), "--run-id", "RUN-1")
            self.assertEqual(planned.returncode, 0, planned.stderr[-300:])
            self.assertIn("--no-guidance", planned.stdout)
            for arm in ("with", "without"):
                recorded = run(
                    "memory", "ab", "record", "--project", str(project), "--run-id", "RUN-1",
                    "--arm", arm, "--ideas-file", str(ideas), "--literature-file", str(literature),
                )
                self.assertEqual(recorded.returncode, 0, recorded.stderr[-300:])
            compared = run("memory", "ab", "compare", "--project", str(project))
            payload = json.loads(compared.stdout[compared.stdout.index("{"):])
            self.assertEqual(payload["comparison"]["direction"], "no_difference")


class SessionModeTest(unittest.TestCase):
    """M1/M2 收尾：单会话/多会话可选——multi 强制 host_label 分离，single 带同源偏差边界。"""

    def _arm(self, label=None):
        arm = {
            "n": 4,
            "rates": {"grounded_rate": 1.0, "falsifiable_rate": 1.0, "executable_plan_rate": 1.0,
                      "distinct_sources_mean": 2.0, "power_aware_stopping_rate": 1.0, "risk_noted_rate": 0.5},
            "per_idea": [
                {"score_wide": 3 + i, "score": 2 + i} for i in range(4)
            ],
        }
        if label is not None:
            arm["session"] = {"session_id": "s-" + label, "host_label": label}
        return arm

    def test_schema_bumped_to_0_2(self):
        from research_agent.memory_ab import MEMORY_AB_SCHEMA

        self.assertEqual(MEMORY_AB_SCHEMA, "memory-ab-0.2")

    def test_multi_mode_blocks_same_host_label(self):
        verdict = compare(self._arm("Zcode-1"), self._arm("Zcode-1"), session_mode="multi")
        self.assertEqual(verdict["session_check"]["status"], "blocked")
        self.assertEqual(verdict["direction"], "")
        self.assertIn("distinct sessions", verdict["reading"])

    def test_multi_mode_blocks_missing_session_metadata(self):
        verdict = compare(self._arm(None), self._arm("Qoder-1"), session_mode="multi")
        self.assertEqual(verdict["session_check"]["status"], "blocked")
        self.assertIn("--session-host-label", verdict["reading"])

    def test_multi_mode_passes_with_distinct_labels(self):
        verdict = compare(self._arm("Zcode-1"), self._arm("Qoder-1"), session_mode="multi")
        self.assertEqual(verdict["session_check"]["status"], "ok")
        self.assertEqual(verdict["session_check"]["with_host_label"], "Zcode-1")

    def test_single_mode_carries_same_source_boundary(self):
        verdict = compare(self._arm("Zcode-1"), self._arm("Zcode-1"), session_mode="single")
        self.assertIn("same-source bias", verdict["reading"])

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            compare(self._arm("A"), self._arm("B"), session_mode="both")

    def test_record_stores_session_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            literature = {"spans": [{"span_id": "SP-1", "source_id": "A"}, {"span_id": "SP-2", "source_id": "B"}]}
            record(project, run_id="RUN-1", arm="with", ideas=[_good()], literature=literature,
                   session={"session_id": "s-1", "host_label": "Zcode-1"})
            store = json.loads((project / "memory" / "ab.json").read_text(encoding="utf-8"))
            self.assertEqual(store["schema_version"], "memory-ab-0.2")
            self.assertEqual(store["arms"]["with"]["session"]["host_label"], "Zcode-1")

    def test_analysis_passes_session_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            literature = {"spans": [{"span_id": "SP-1", "source_id": "A"}, {"span_id": "SP-2", "source_id": "B"}]}
            record(project, run_id="RUN-1", arm="with", ideas=[_good(index=1) for _ in range(4)], literature=literature,
                   session={"session_id": "s-1", "host_label": "Zcode-1"})
            record(project, run_id="RUN-1", arm="without", ideas=[_good(index=5) for _ in range(4)], literature=literature,
                   session={"session_id": "s-2", "host_label": "Qoder-1"})
            result = analysis(project, session_mode="multi")
            self.assertEqual(result["comparison"]["session_check"]["status"], "ok")
            self.assertEqual(result["comparison"]["session_mode"], "multi")


if __name__ == "__main__":
    unittest.main()

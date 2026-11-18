"""Contract tests for the ESE stage x method registry."""

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent import method_registry  # noqa: E402
from research_agent import cli  # noqa: E402


class RegistryIntegrityTest(unittest.TestCase):
    def setUp(self):
        self.registry = method_registry.load_registry()

    def test_every_method_declares_guidelines_and_boundaries(self):
        for method in self.registry["methods"]:
            self.assertGreaterEqual(len(method["guidelines"]), 2, method["id"])
            self.assertTrue(method["cannot_support"], method["id"])
            self.assertTrue(method["protocol_fields"], method["id"])
            self.assertTrue(method["checks"], method["id"])
            self.assertTrue(method.get("reporting_sections"), method["id"])

    def test_every_method_stage_task_is_inside_fit_stages(self):
        for method in self.registry["methods"]:
            for stage in method["stage_tasks"]:
                self.assertIn(stage, method["fit_stages"], method["id"])

    def test_registry_rejects_duplicate_method_ids(self):
        payload = json.loads(json.dumps(self.registry))
        payload["methods"].append(dict(payload["methods"][0]))
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.validate(payload)

    def test_registry_rejects_unknown_stage(self):
        payload = json.loads(json.dumps(self.registry))
        payload["methods"][0]["fit_stages"].append("S99")
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.validate(payload)

    def test_registry_rejects_bad_severity(self):
        payload = json.loads(json.dumps(self.registry))
        payload["methods"][0]["checks"][0]["severity"] = "info"
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.validate(payload)


class ProjectionTest(unittest.TestCase):
    def setUp(self):
        self.registry = method_registry.load_registry()

    def test_list_methods_is_stable_and_complete(self):
        methods = method_registry.list_methods(self.registry)
        ids = [item["id"] for item in methods]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("controlled-experiment", ids)
        self.assertIn("case-study", ids)
        self.assertIn("systematic-literature-review", ids)

    def test_unknown_method_lists_known_ids(self):
        with self.assertRaises(method_registry.MethodRegistryError) as context:
            method_registry.get_method("no-such-method", self.registry)
        self.assertIn("controlled-experiment", str(context.exception))

    def test_stage_matrix_has_tasks(self):
        result = method_registry.matrix(self.registry, "S4")
        cells = result["rows"][0]["cells"]
        self.assertGreaterEqual(len(cells), 5)
        for cell in cells:
            self.assertTrue(cell["task"], cell["method"])

    def test_unknown_stage_is_rejected(self):
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.matrix(self.registry, "S99")

    def test_task_card_carries_guidelines_and_checks(self):
        card = method_registry.task_card("S4", "controlled-experiment", self.registry)
        self.assertTrue(card["applicable"])
        self.assertIn("power_analysis", card["protocol_fields"])
        keys = [item["key"] for item in card["guidelines"]]
        self.assertIn("wohlin2012", keys)
        self.assertIn("advisory only", card["boundary"])

    def test_task_card_marks_non_applicable_stage(self):
        card = method_registry.task_card("S6", "controlled-experiment", self.registry)
        self.assertFalse(card["applicable"])
        self.assertEqual(card["task"], "")


COMPLETE_EXPERIMENT = {
    "hypothesis": "factor A improves metric M",
    "factors": ["A"],
    "levels": [0, 1],
    "primary_metric": "M",
    "sample_size": 64,
    "power_analysis": "80% at d=0.5",
    "analysis_plan": "paired t + CI",
    "stopping_rule": "stop at n=64",
    "randomization": "seeded shuffle",
}


class AdvisoryCheckTest(unittest.TestCase):
    def setUp(self):
        self.registry = method_registry.load_registry()

    def test_empty_payload_reports_blockers(self):
        report = method_registry.check("controlled-experiment", {}, self.registry)
        self.assertEqual(report["status"], "advisory_missing")
        missing = [item["check"] for item in report["findings"] if item["status"] == "missing"]
        self.assertIn("experiment.power", missing)

    def test_complete_payload_passes(self):
        report = method_registry.check("controlled-experiment", COMPLETE_EXPERIMENT, self.registry)
        self.assertEqual(report["status"], "advisory_ok")
        self.assertTrue(all(item["status"] == "pass" for item in report["findings"]))

    def test_dotted_paths_are_supported(self):
        payload = {"design": {"baseline": {"kind": "tuned_cv"}}}
        self.assertTrue(method_registry._present(method_registry._lookup(payload, "design.baseline.kind")))
        self.assertFalse(method_registry._present(method_registry._lookup(payload, "design.baseline.file")))

    def test_placeholder_text_counts_as_missing(self):
        payload = dict(COMPLETE_EXPERIMENT)
        payload["power_analysis"] = "TODO(calc)"
        report = method_registry.check("controlled-experiment", payload, self.registry)
        power = [item for item in report["findings"] if item["check"] == "experiment.power"][0]
        self.assertEqual(power["status"], "missing")

    def test_mining_requires_analysis_plan(self):
        payload = {
            "sampling_frame": "three repos",
            "project_selection": "criteria",
            "time_window": "2000..2026",
            "time_split": "median date",
            "dedup_policy": "merge commits excluded",
            "label_source": "path heuristics",
            "license_check": "checked",
            "extraction_script": "scripts/run_ese_study.py",
        }
        report = method_registry.check("repository-mining", payload, self.registry)
        analysis = [item for item in report["findings"] if item["check"] == "mining.analysis"][0]
        self.assertEqual(analysis["status"], "missing")
        self.assertIn("analysis.stratification", analysis["missing"])

    def test_shipped_protocol_passes_all_checks(self):
        import json
        from pathlib import Path as _Path

        path = _Path(__file__).resolve().parents[1] / "research_agent" / "eval" / "ese_protocols" / "msr-cochange-v3.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        report = method_registry.check("repository-mining", payload, self.registry)
        self.assertEqual(report["status"], "advisory_ok")
        self.assertTrue(all(item["status"] == "pass" for item in report["findings"]))

    def test_mining_requires_time_split(self):
        report = method_registry.check("repository-mining", {"sampling_frame": "x", "project_selection": "y"}, self.registry)
        mining = [item for item in report["findings"] if item["check"] == "mining.time_split"][0]
        self.assertEqual(mining["status"], "missing")
        self.assertIn("time_split", mining["missing"])


class CliTest(unittest.TestCase):
    def test_list_command_prints_methods(self):
        args = cli.argparse.Namespace(method_command="list")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli._cmd_method_list(args)
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["methods"])

    def test_unknown_method_returns_nonzero(self):
        args = cli.argparse.Namespace(method_id="no-such-method")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli._cmd_method_show(args)
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

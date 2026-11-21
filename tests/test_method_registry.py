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

    def test_every_method_declares_the_three_model_dimensions(self):
        # design/153: inputs / evidence_sources / evaluation_dimensions must be
        # declared per method and each evaluation dimension carries a literature
        # basis — the reference model is theory-grounded, not intuition.
        for method in self.registry["methods"]:
            self.assertGreaterEqual(len(method["inputs"]), 2, method["id"])
            self.assertTrue(method["evidence_sources"], method["id"])
            self.assertGreaterEqual(len(method["evaluation_dimensions"]), 3, method["id"])
            for dim in method["evaluation_dimensions"]:
                self.assertTrue(dim["dimension"], method["id"])
                self.assertTrue(dim["basis"], method["id"] + ": dimension needs a basis")

    def test_registry_rejects_method_without_dimensions(self):
        payload = json.loads(json.dumps(self.registry))
        del payload["methods"][0]["evaluation_dimensions"]
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.validate(payload)

    def test_every_method_declares_vocabulary_tags(self):
        # design/155: the 标签化梳理 todo — tags are the reproducible form of
        # "提炼共性与差异", so they must come from the shared vocabulary.
        vocabulary = {entry["tag"] for entry in self.registry["tag_vocabulary"]}
        for method in self.registry["methods"]:
            self.assertTrue(method["tags"], method["id"])
            unknown = [tag for tag in method["tags"] if tag not in vocabulary]
            self.assertEqual(unknown, [], method["id"])

    def test_vocabulary_entries_carry_definition_and_basis(self):
        for entry in self.registry["tag_vocabulary"]:
            self.assertTrue(entry["definition"], entry["tag"])
            self.assertTrue(entry["basis"], entry["tag"])

    def test_tag_layer_extracts_commonality_and_difference(self):
        # The advisor's extraction, made reproducible: tags held by >=3 methods
        # are commonalities; single-method tags are the essential differences.
        from collections import Counter

        counter = Counter()
        for method in self.registry["methods"]:
            counter.update(method["tags"])
        common = sorted(tag for tag, count in counter.items() if count >= 3)
        difference = sorted(tag for tag, count in counter.items() if count == 1)
        # 预注册协议 / 伦理审查 cross methods (governance commonalities);
        # 随机化 (experiment) and 三角验证 (case study) are essential
        # differences — the two examples the advisor gave verbatim.
        self.assertIn("预注册协议", common)
        self.assertIn("伦理审查", common)
        self.assertIn("随机化", difference)
        self.assertIn("三角验证", difference)

    def test_registry_rejects_tag_outside_vocabulary(self):
        payload = json.loads(json.dumps(self.registry))
        payload["methods"][0]["tags"].append("不存在于词表的标签")
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.validate(payload)


class ElementCompositionTest(unittest.TestCase):
    """design/156: the meta-model (elements with typed ports) and reference
    wirings are registry data, fail-closed at load."""

    def setUp(self):
        self.registry = method_registry.load_registry()

    def test_reference_compositions_are_legal_wirings(self):
        for composition in self.registry["compositions"]:
            method_registry.validate(self.registry)  # loader-level port matching
        wiring_ids = [
            (c["id"], [step["element"] for step in c["wiring"]])
            for c in self.registry["compositions"]
        ]
        confirmatory = dict(wiring_ids)["confirmatory"]
        self.assertIn("假设", confirmatory)
        self.assertIn("方案", confirmatory)

    def test_registry_rejects_illegal_wiring(self):
        # 探索式组合里让方案消费假设：假设在该接线上尚未产出 → 数据层拒绝。
        payload = json.loads(json.dumps(self.registry))
        exploratory = [c for c in payload["compositions"] if c["id"] == "exploratory"][0]
        exploratory["wiring"].insert(
            2, {"element": "方案", "consumes": "候选假设（可判别）"}
        )
        with self.assertRaises(method_registry.MethodRegistryError) as context:
            method_registry.validate(payload)
        self.assertIn("has not been produced upstream", str(context.exception))

    def test_registry_rejects_unknown_port(self):
        payload = json.loads(json.dumps(self.registry))
        payload["elements"][0]["outputs"][0]["produces"] = "不属于词表的端口"
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.validate(payload)

    def test_get_composition_round_trip(self):
        composition = method_registry.get_composition("confirmatory", self.registry)
        self.assertEqual(composition["id"], "confirmatory")
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.get_composition("no-such-composition", self.registry)

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


class PipelineStagePlanTest(unittest.TestCase):
    """The advisory projection from a method's composition to pipeline stages."""

    def setUp(self):
        self.registry = method_registry.load_registry()

    def test_confirmatory_slr_does_not_cover_experiment_stages(self):
        plan = method_registry.pipeline_stage_plan("systematic-literature-review", self.registry)
        self.assertEqual(plan["composition"], "confirmatory")
        self.assertIn("literature", plan["covered_stages"])
        self.assertIn("paper", plan["covered_stages"])
        self.assertNotIn("experiment", plan["covered_stages"])
        self.assertNotIn("run", plan["covered_stages"])

    def test_exploratory_mining_covers_execution_but_not_writing(self):
        plan = method_registry.pipeline_stage_plan("repository-mining", self.registry)
        self.assertEqual(plan["composition"], "exploratory")
        self.assertIn("literature", plan["covered_stages"])
        self.assertIn("run", plan["covered_stages"])
        self.assertNotIn("paper", plan["covered_stages"])

    def test_plan_walks_each_slot_once(self):
        plan = method_registry.pipeline_stage_plan("repository-mining", self.registry)
        self.assertTrue(plan["plan"])
        slots = [step["slot"] for step in plan["plan"]]
        self.assertEqual(len(slots), len(set(slots)), "a slot must not be walked twice")

    def test_uncovered_fit_slot_is_marked_not_dropped(self):
        # No current method leaves a fit slot outside its composition; verify the
        # extension seam with a synthetic wiring that drops one slot.
        import copy
        registry = copy.deepcopy(self.registry)
        method = next(m for m in registry["methods"] if m["id"] == "repository-mining")
        dropped = method["fit_stages"][-1]
        for composition in registry["compositions"]:
            if composition["id"] == method["composition_id"]:
                for slots in composition["slot_map"].values():
                    if dropped in slots:
                        slots.remove(dropped)
        plan = method_registry.stage_plan("repository-mining", registry)
        marked = [step["slot"] for step in plan["stages"] if step.get("uncovered")]
        self.assertIn(dropped, marked, "fit slots outside the wiring must be marked, not dropped")

    def test_unknown_method_is_rejected(self):
        with self.assertRaises(method_registry.MethodRegistryError):
            method_registry.pipeline_stage_plan("no-such-method", self.registry)


if __name__ == "__main__":
    unittest.main()

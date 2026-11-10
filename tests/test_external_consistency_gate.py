import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from research_agent.cli import main
from research_agent.external_consistency_gate import (
    ExternalConsistencyGateError,
    run_consistency_check,
)

EXTERNAL_ROOT = Path("D:/Users/20691/Downloads/Research Skill调研/scientific-agent-skills-main")


def _registry(path: Path, *, broken: bool = False) -> Path:
    payload = {
        "schema_version": "1.0",
        "numeric_facts": [
            {
                "fact_id": "N001",
                "concept": "r2",
                "section": "results",
                "value": 0.5,
                "unit": "unitless",
                "numerator": None,
                "denominator": None,
                "sample_size": 48,
                "analysis_set": "training",
                "evidence_ids": ["E001"],
            }
        ],
        "methods": [
            {
                "method_id": "M001",
                "name": "ridge",
                "analysis_intent": "confirmatory",
                "protocol_status": "prespecified",
                "outcome_ids": ["O001"],
            }
        ],
        "results": [
            {
                "result_id": "R001",
                "method_id": "M001",
                "outcome_id": "O001",
                "analysis_intent": "confirmatory",
                "sample_size": 48,
                "evidence_ids": ["E001"],
                "reported_sections": ["results"],
            }
        ],
    }
    if broken:
        payload["results"][0]["evidence_ids"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _fake_root(tmp: Path, status: str, issues) -> Path:
    root = tmp / "external"
    script = root / "skills" / "scientific-writing" / "scripts" / "check_consistency.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "import json\n"
        "print(json.dumps({'tool': 'check_consistency', 'status': %r, "
        "'summary': {'errors': %d, 'warnings': 0, 'numeric_facts': 1, "
        "'methods': 1, 'results': 1}, 'issues': %r}))\n"
        % (status, 1 if status == "fail" else 0, issues),
        encoding="utf-8",
    )
    return root


class ExternalConsistencyGateTest(unittest.TestCase):
    def test_whitelisted_check_is_read_only_and_maps_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_root = _fake_root(
                root,
                "pass",
                [{"severity": "warning", "code": "DUPLICATE_NUMERIC_VALUE"}],
            )
            registry = _registry(root / "registry.json")
            before = registry.read_bytes()
            result = run_consistency_check(registry, skill_root)
            self.assertEqual(result["status"], "attention")
            self.assertEqual(result["external_status"], "pass")
            self.assertEqual(result["tool"], "scientific-writing.check_consistency")
            self.assertEqual(result["summary"]["numeric_facts"], 1)
            self.assertIn("read-only", result["boundary"])
            self.assertEqual(registry.read_bytes(), before)

    def test_external_error_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_root = _fake_root(
                root,
                "fail",
                [{"severity": "error", "code": "RESULT_WITHOUT_EVIDENCE"}],
            )
            result = run_consistency_check(
                _registry(root / "registry.json", broken=True), skill_root
            )
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["issues"][0]["code"], "RESULT_WITHOUT_EVIDENCE")

    def test_missing_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = _registry(Path(tmp) / "registry.json")
            with self.assertRaises(ExternalConsistencyGateError):
                run_consistency_check(registry, Path(tmp) / "missing")

    @unittest.skipUnless(EXTERNAL_ROOT.is_dir(), "external skill root not installed")
    def test_actual_external_skill_passes_valid_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_consistency_check(_registry(Path(tmp) / "registry.json"), EXTERNAL_ROOT)
        self.assertEqual(result["status"], "ready", result)
        self.assertEqual(result["summary"]["errors"], 0)

    @unittest.skipUnless(EXTERNAL_ROOT.is_dir(), "external skill root not installed")
    def test_actual_external_skill_blocks_result_without_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_consistency_check(
                _registry(Path(tmp) / "registry.json", broken=True), EXTERNAL_ROOT
            )
        self.assertEqual(result["status"], "blocked", result)
        codes = {item.get("code") for item in result["issues"]}
        self.assertIn("RESULT_WITHOUT_EVIDENCE", codes)

    def test_cli_wiring_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "project"
            project.mkdir()
            _registry(project / "registry.json")
            skill_root = _fake_root(root, "pass", [])
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(
                    [
                        "writing",
                        "external-consistency",
                        "--project",
                        str(project),
                        "--registry",
                        "registry.json",
                        "--skill-root",
                        str(skill_root),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(buffer.getvalue())["status"], "ready")


if __name__ == "__main__":
    unittest.main()

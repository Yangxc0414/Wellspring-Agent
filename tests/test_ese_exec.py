"""Repository-mining ESE executor: extraction, intervals, permutation, protocol checks."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_agent import ese_exec  # noqa: E402


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def _commit(repo, message, files):
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)


def _repo(tmp, name="r1"):
    repo = Path(tmp) / name
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    return repo


class EseExecTest(unittest.TestCase):
    def test_wilson_interval_bounds(self):
        low, high = ese_exec.wilson_interval(5, 10)
        self.assertLess(low, 0.5)
        self.assertGreater(high, 0.5)
        self.assertEqual(ese_exec.wilson_interval(0, 0), (0.0, 0.0))

    def test_extraction_filters_and_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            _commit(repo, "add module", {"src/a.py": "x = 1\n"})
            _commit(repo, "add tests", {"src/a.py": "x = 2\n", "tests/test_a.py": "def test(): pass\n"})
            _commit(repo, "fix bug in parser", {"src/b.py": "y = 1\n", "tests/test_b.py": "def test(): pass\n"})
            commits = ese_exec.extract_commits(repo)
            self.assertEqual(len(commits), 3)
            self.assertEqual(sum(1 for c in commits if c["touches_test"]), 2)
            self.assertEqual(sum(1 for c in commits if c["is_bugfix"]), 1)

    def test_analysis_and_result_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            _commit(repo, "add module", {"src/a.py": "x = 1\n"})
            _commit(repo, "add tests", {"src/a.py": "x = 2\n", "tests/test_a.py": "def test(): pass\n"})
            protocol_path = Path(tmp) / "protocol.json"
            protocol = {
                "schema": "ese-study-protocol-0.1",
                "study_id": "T-1",
                "method": "repository-mining",
                "research_questions": ["rq"],
                "sampling_frame": {"repos": [{"name": "r1"}]},
                "time_window": {"start": "2000-01-01", "end": "2026-11-18"},
                "dedup_policy": "merge commits excluded",
                "label_source": {"unit": "py", "outcome": "tests"},
                "analysis": {"metric": "rate", "unit": "commit", "ci_level": 0.95,
                              "permutation": {"n": 200, "seed": 7}},
            }
            protocol_path.write_text(json.dumps(protocol), encoding="utf-8")
            result = ese_exec.run_study(protocol_path, {"r1": repo}, Path(tmp) / "out")
            self.assertEqual(result["pooled"]["commits"], 2)
            self.assertEqual(result["pooled"]["test_cochange"], 1)
            self.assertIn("stratified", result)
            self.assertIn("adjusted_difference", result["stratified"])
            self.assertTrue(result["stratified"]["strata"])
            self.assertTrue((Path(tmp) / "out" / "result.json").is_file())
            self.assertTrue((Path(tmp) / "out" / "result.md").is_file())

    def test_wrong_method_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps({"schema": "ese-study-protocol-0.1", "method": "case-study"}), encoding="utf-8")
            with self.assertRaises(ese_exec.EseExecError):
                ese_exec.load_protocol(path)

    def test_missing_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps({
                "schema": "ese-study-protocol-0.1",
                "study_id": "x",
                "method": "repository-mining",
            }), encoding="utf-8")
            with self.assertRaises(ese_exec.EseExecError):
                ese_exec.load_protocol(path)


class EseRunArtifactTest(unittest.TestCase):
    def test_emit_run_artifacts_writes_capsule_and_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = _repo(tmp)
            _commit(repo, "add module", {"src/a.py": "x = 1\n"})
            _commit(repo, "fix bug", {"src/a.py": "x = 2\n", "tests/test_a.py": "def test(): pass\n"})
            protocol_path = Path(tmp) / "protocol.json"
            protocol_path.write_text(json.dumps({
                "schema": "ese-study-protocol-0.1",
                "study_id": "T-RUN-1",
                "method": "repository-mining",
                "research_questions": ["rq"],
                "sampling_frame": {"repos": [{"name": "r1"}]},
                "time_window": {"start": "2000-01-01", "end": "2026-11-18"},
                "dedup_policy": "merge commits excluded",
                "label_source": {"unit": "py", "outcome": "tests"},
                "analysis": {"metric": "rate", "unit": "commit", "ci_level": 0.95,
                              "permutation": {"n": 200, "seed": 7}},
            }), encoding="utf-8")
            result = ese_exec.run_study(protocol_path, {"r1": repo}, Path(tmp) / "out")
            artifacts = ese_exec.emit_run_artifacts(protocol_path, result, Path(tmp) / "out")
            self.assertTrue((Path(artifacts["run_dir"]) / "run-capsule.json").is_file())
            self.assertTrue((Path(artifacts["run_dir"]) / "ea.json").is_file())
            self.assertTrue((Path(artifacts["run_dir"]) / "run-contract.json").is_file())
            self.assertEqual(artifacts["check"]["blockers"], [])
            from research_agent.modules.run import verify_claim_assertions
            capsule = json.loads((Path(artifacts["run_dir"]) / "run-capsule.json").read_text(encoding="utf-8"))
            metrics = json.loads((Path(artifacts["run_dir"]) / "metrics.json").read_text(encoding="utf-8"))
            checked = verify_claim_assertions(
                capsule, metrics,
                [{"metric": "test_cochange_rate", "value": result["pooled"]["rate"],
                  "comparator": "==", "tolerance": 0.001}],
            )
            self.assertEqual(checked[0]["status"], "pass")
            wrong = verify_claim_assertions(
                capsule, metrics,
                [{"metric": "test_cochange_rate", "value": 0.99, "comparator": "==", "tolerance": 0.001}],
            )
            self.assertEqual(wrong[0]["status"], "fail")


if __name__ == "__main__":
    unittest.main()

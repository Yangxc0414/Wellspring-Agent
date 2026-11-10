"""Governed local-command execution (Codex-like) must stay CLI-only and approval-bound."""
import sys
import tempfile
import unittest
from pathlib import Path

from research_agent.local_exec import (
    _argv,
    approve_local_experiment,
    ingest_local_experiment,
    init_local_experiment,
    run_local_experiment,
)
from research_agent.experiment_runner import ExperimentExecutionError


class LocalExecTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.eid = "EXP-LOCAL"

    def tearDown(self):
        self._tmp.cleanup()

    def _init(self, command=None, expect=None):
        return init_local_experiment(
            self.project, self.eid,
            command or [sys.executable, "-c", "from pathlib import Path; Path('out.txt').write_text('ok', encoding='utf-8')"],
            expected_outputs=expect if expect is not None else ["out.txt"],
        )

    def test_init_parses_string_to_argv_without_shell(self):
        spec = self._init(command="echo a && echo b")
        self.assertIsInstance(spec["command"], list)
        self.assertIn("&&", spec["command"])  # kept as one argv token, not a shell operator
        self.assertEqual(len(spec["command"]), 5)
        self.assertEqual(_argv("echo hello"), ["echo", "hello"])

    def test_run_requires_allow_execute(self):
        self._init()
        approve_local_experiment(self.project, self.eid, "checked command")
        with self.assertRaises(ExperimentExecutionError):
            run_local_experiment(self.project, self.eid, allow_execute=False)

    def test_run_requires_approval(self):
        self._init()
        with self.assertRaises(ExperimentExecutionError):
            run_local_experiment(self.project, self.eid, allow_execute=True)

    def test_spec_change_after_approval_rejected(self):
        self._init()
        approve_local_experiment(self.project, self.eid, "checked command")
        self._init(command=[sys.executable, "-c", "print('changed')"])
        with self.assertRaises(ExperimentExecutionError):
            run_local_experiment(self.project, self.eid, allow_execute=True)

    def test_run_and_ingest_verified_but_not_claim_eligible(self):
        self._init()
        approve_local_experiment(self.project, self.eid, "checked command and outputs")
        execution = run_local_experiment(self.project, self.eid, allow_execute=True)
        self.assertEqual(execution["status"], "completed")
        self.assertIn("out.txt", execution["outputs"])
        self.assertEqual(execution["missing_outputs"], [])
        self.assertTrue(execution["argv"])
        evidence = ingest_local_experiment(self.project, self.eid)
        self.assertEqual(evidence["status"], "verified")
        self.assertFalse(evidence["claim_eligible"])
        self.assertEqual(evidence["evidence_type"], "local_command")

    def test_failed_run_retained_incomplete(self):
        self._init(command=[sys.executable, "-c", "import sys; sys.exit(3)"], expect=[])
        approve_local_experiment(self.project, self.eid, "expect failure")
        execution = run_local_experiment(self.project, self.eid, allow_execute=True)
        self.assertEqual(execution["status"], "failed")
        evidence = ingest_local_experiment(self.project, self.eid)
        self.assertEqual(evidence["status"], "incomplete")

    def test_missing_expected_output_incomplete(self):
        self._init(expect=["nope.txt"])
        approve_local_experiment(self.project, self.eid, "output will be missing")
        execution = run_local_experiment(self.project, self.eid, allow_execute=True)
        self.assertEqual(execution["status"], "completed")
        self.assertEqual(execution["missing_outputs"], ["nope.txt"])
        evidence = ingest_local_experiment(self.project, self.eid)
        self.assertEqual(evidence["status"], "incomplete")


if __name__ == "__main__":
    unittest.main()
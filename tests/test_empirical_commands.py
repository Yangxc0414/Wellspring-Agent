"""Empirical preflight must answer a blocker with the command it already knows how to name."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.empirical_loop import _empirical_command, check_empirical_loop


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))


class EmpiricalCommandsTest(unittest.TestCase):
    def test_every_named_blocker_maps_to_a_command(self):
        cases = {
            "literature ledger has no sources": "literature run",
            "multi-source synthesis matrix is missing; run literature synthesize": "literature synthesize",
            "innovation review is missing; run innovation review before writing": "innovation review",
            "experiment package does not exist: EXP-1": "experiment scaffold",
            "experiment evidence is not verified; run experiment ingest": "experiment ingest",
            "experiment claim is not human-signed; human must run experiment claim": "experiment claim",
        }
        for blocker, needle in cases.items():
            command = _empirical_command(blocker, "proj", "RUN-1", "EXP-1", "why memory helps", "accuracy")
            self.assertIn(needle, command, blocker)
            self.assertTrue(command.startswith("python -m research_agent"), blocker)
        self.assertEqual(_empirical_command("experiment hypothesis is missing", "p", "r", "e", "q", "m"), "")

    def test_preflight_uses_the_run_goal_instead_of_a_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            target = project / "runs" / "RUN-1"
            _write(target / "run-context.json", {"request": {"goal": "memory x archive interaction"}})
            _write(target / "literature-ledger.json", {"sources": []})
            result = check_empirical_loop(project, "RUN-1", "EXP-MISSING")
            self.assertEqual(result["status"], "blocked")
            commands = [item["command"] for item in result["blocker_actions"]]
            self.assertTrue(any("memory x archive interaction" in c for c in commands), commands)
            self.assertTrue(all(c for c in commands), commands)
            self.assertNotIn("resolve blockers in order; human gates stay in CLI", result["next_actions"])


if __name__ == "__main__":
    unittest.main()

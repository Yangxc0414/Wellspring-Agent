"""A task-less run must not give weaker advice than its own capsule supports."""

import json
import tempfile
import unittest
from pathlib import Path

from research_agent.mcp_server import _next_actions
from research_agent.project import init_project


def _run_dir(project: Path, run_id: str, capsule=None) -> Path:
    target = project / "runs" / run_id
    target.mkdir(parents=True)
    if capsule is not None:
        with open(str(target / "loop-capsule.json"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(capsule, ensure_ascii=False))
    return target


class NextActionsFallbackTest(unittest.TestCase):
    def test_capsule_commands_survive_a_missing_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            init_project(project, "Fallback")
            _run_dir(
                project,
                "RUN-CAPSULE",
                {
                    "schema_version": "loop-capsule-0.1",
                    "run_id": "RUN-CAPSULE",
                    "blockers": ["CLAIM_UNSIGNED"],
                    "next_actions": [
                        {
                            "owner": "human",
                            "gate": "S5b",
                            "command": "python -m research_agent run claim --capsule x.json",
                        }
                    ],
                },
            )
            actions = _next_actions(project, "RUN-CAPSULE")
            self.assertEqual(actions[0]["gate"], "S5b")
            self.assertIn("run claim", actions[0]["command"])
            self.assertNotEqual(actions[0].get("kind"), "inspect")

    def test_no_capsule_still_falls_back_to_inspect(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            init_project(project, "Fallback")
            _run_dir(project, "RUN-EMPTY")
            _run_dir(
                project,
                "RUN-NOARGS",
                {"schema_version": "loop-capsule-0.1", "run_id": "RUN-NOARGS", "next_actions": []},
            )
            for run_id in ("RUN-EMPTY", "RUN-NOARGS"):
                actions = _next_actions(project, run_id)
                self.assertEqual(actions[0]["kind"], "inspect", run_id)


if __name__ == "__main__":
    unittest.main()

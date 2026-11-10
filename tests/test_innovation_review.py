import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from research_agent import innovation_review
from tests.writing_support import RUN_ID, make_writing_project


class InnovationReviewTest(unittest.TestCase):
    def test_design_levels_keep_their_json_scalar_types(self):
        design = innovation_review._normalise_design(
            {"gate": [False, True], "archive": ["off", "negative"], "min_delta": [0.02]}
        )
        self.assertEqual(design["gate"], [False, True])
        self.assertEqual(design["archive"], ["off", "negative"])
        self.assertEqual(design["min_delta"], [0.02])

    def test_the_run_topic_reaches_the_proposer_when_no_topic_is_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = make_writing_project(Path(tmp))
            run = project / "runs" / RUN_ID
            # Pipeline runs have no task goal; the topic lives in demo.json.
            (run / "task.json").write_text(
                json.dumps({"status": "completed"}), encoding="utf-8"
            )
            (run / "demo.json").write_text(
                json.dumps({"topic": "钙钛矿 界面 钝化 湿热稳定性"}), encoding="utf-8"
            )
            with mock.patch.object(
                innovation_review, "_propose", return_value=([], [], [])
            ) as propose:
                innovation_review.run_innovation_review(
                    project, RUN_ID, propose_only=True, model=object()
                )
            pack = propose.call_args[0][0]
            # A pack with task.goal=None used to make the prompt say "研究主题: 未提供".
            self.assertEqual(pack["task"]["goal"], "钙钛矿 界面 钝化 湿热稳定性")


if __name__ == "__main__":
    unittest.main()

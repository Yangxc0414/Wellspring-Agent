import tempfile
import unittest
from pathlib import Path

from research_agent.guideline_memory import (
    GUIDELINE_BOUNDARY,
    block_for,
    merge,
    parse_entry,
    render_block,
    save,
    load,
    overlap,
)


class ParseTests(unittest.TestCase):
    def test_only_the_three_part_form_is_accepted(self):
        good = parse_entry("closure blocked on origin absent -> 记录 idea 溯源 -> 先跑 from-idea 再签")
        self.assertEqual(good["mechanism"], "记录 idea 溯源")
        self.assertIsNone(parse_entry("多读文献总是有帮助"))
        self.assertIsNone(parse_entry("a -> b"))

    def test_overlap_is_token_jaccard_not_substring(self):
        self.assertGreater(overlap("gate on 让搜索变差 -> 加种子", "gate on 使搜索变差 -> 加种子"), 0.5)
        self.assertLess(overlap("gate  hurts", "memory helps"), 0.5)


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name)
        (self.project / "memory").mkdir(parents=True)
        (self.project / "studies").mkdir()
        (self.project / "studies" / "STUDY-A").mkdir()
        (self.project / "studies" / "STUDY-A" / "study-evidence.json").write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _propose(self, action="先跑 from-idea 再签", step=1):
        return {
            "text": "closure 因 origin 缺失告警 -> 记录想法溯源 -> %s" % action,
            "sources": ["studies/STUDY-A/study-evidence.json"],
        }

    def test_repeated_lesson_reaffirms_instead_of_duplicating(self):
        first = merge([], [self._propose()], step=1, project=self.project)
        self.assertEqual(len(first["entries"]), 1)
        second = merge(first["entries"], [self._propose()], step=2, project=self.project)
        self.assertEqual(len(second["entries"]), 1)
        self.assertEqual(second["entries"][0]["seen"], 2)
        self.assertTrue(second["accepted"][0]["reaffirmed"])

    def test_a_lesson_without_a_real_artifact_is_rejected(self):
        # This is where we deliberately diverge from TTME: free-floating prose is not evidence.
        proposed = {"text": self._propose()["text"], "sources": ["studies/NOPE/study-evidence.json"]}
        result = merge([], [proposed], step=1, project=self.project)
        self.assertEqual(result["entries"], [])
        self.assertEqual(result["rejected"][0]["reason"], "sources missing or outside the project")

    def test_escaping_the_project_is_not_enough_to_smuggle_a_citation(self):
        proposed = {"text": self._propose()["text"], "sources": ["../outside.txt"]}
        (Path(self.tmp.name) / "outside.txt").write_text("x", encoding="utf-8")
        result = merge([], [proposed], step=1, project=self.project)
        self.assertEqual(result["entries"], [])

    def test_stale_lessons_expire_instead_of_persisting(self):
        seeded = merge([], [self._propose()], step=1, project=self.project)["entries"]
        aged = merge(seeded, [], step=25, project=self.project)
        self.assertEqual(aged["entries"], [])
        self.assertEqual(len(aged["expired"]), 1)

    def test_at_most_three_lessons_land_in_one_step(self):
        batch = [self._propose("动作%d" % index) for index in range(5)]
        result = merge([], batch, step=1, project=self.project)
        self.assertLessEqual(len(result["entries"]), 3)
        self.assertTrue(any("over-cap-per-step" in item["reason"] for item in result["rejected"]))

    def test_round_trip_and_render_respect_the_budget(self):
        entries = merge([], [self._propose()], step=1, project=self.project)["entries"]
        save(self.project, entries, step=1)
        reloaded = load(self.project)
        self.assertEqual(len(reloaded), 1)
        block = render_block(reloaded, step=1)
        self.assertIn(" -> ", block)
        self.assertIn("studies/STUDY-A/study-evidence.json", block)
        self.assertIn("非结论", block)
        self.assertEqual(render_block([], step=1), "")

    def test_boundary_is_carried_in_the_store(self):
        path = save(self.project, merge([], [self._propose()], step=1, project=self.project)["entries"], 1)
        import json

        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["boundary"], GUIDELINE_BOUNDARY)
        self.assertIn("cannot create or change a Claim", stored["boundary"])


class ConsumptionTests(unittest.TestCase):
    """The store only matters if it reaches the prompt that proposes the next ideas."""

    def test_guidance_reaches_the_proposal_prompt(self):
        # _propose validates after the model call, so an empty payload still proves what was sent.
        from research_agent.innovation_review import InnovationReviewError, _propose

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "studies" / "S").mkdir(parents=True)
            (project / "studies" / "S" / "study-evidence.json").write_text("{}", encoding="utf-8")
            entries = merge(
                [],
                [
                    {
                        "text": "closure 报 origin 缺失 -> 想法与数字必须同链 -> 先跑 from-idea 再签",
                        "sources": ["studies/S/study-evidence.json"],
                    }
                ],
                step=1,
                project=project,
            )["entries"]
            save(project, entries, step=1)
            recorded = {}

            class _Recorder:
                """Records the first prompt only: a failed parse adds a repair turn on top."""

                def complete(self, messages, json_mode=True):
                    if "user" not in recorded:
                        recorded["user"] = messages[-1]["content"]
                    return '{"gaps": [], "ideas": []}'

            with self.assertRaises(InnovationReviewError):
                _propose(
                    {"literature": {"references": []}},
                    _Recorder(),
                    3,
                    "",
                    {},
                    guidance=block_for(project),
                )
        self.assertIn("先跑 from-idea 再签", recorded["user"])
        self.assertIn("studies/S/study-evidence.json", recorded["user"])

    def test_empty_store_adds_no_advice(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(block_for(Path(tmp)), "")


if __name__ == "__main__":
    unittest.main()

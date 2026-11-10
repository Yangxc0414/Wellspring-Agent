import unittest

from research_agent.literature_synthesis import synthesize_sources_deterministic
from research_agent.cli import _resume_pipeline_inputs


def _sources():
    return [
        {
            "source_id": "FX-001",
            "ref_id": "REF-01",
            "title": "Paper A",
            "full_text": True,
            "spans": [
                {"span_id": "FX-001-S01-01", "text": "Interface passivation improves humidity stability."},
            ],
        },
        {
            "source_id": "FX-002",
            "ref_id": "REF-02",
            "title": "Paper B",
            "full_text": True,
            "spans": [
                {"span_id": "FX-002-S01-01", "text": "Passivation protocols affect stability reproducibility."},
            ],
        },
        {
            "source_id": "FX-003",
            "ref_id": "REF-03",
            "title": "Paper C",
            "full_text": False,
            "spans": [],
        },
    ]


class DeterministicSynthesisTest(unittest.TestCase):
    def test_themes_require_two_sources(self):
        result = synthesize_sources_deterministic(_sources())
        self.assertEqual(result["schema_version"], "literature-synthesis-deterministic-0.1")
        self.assertTrue(result["themes"])
        for theme in result["themes"]:
            self.assertGreaterEqual(theme["source_count"], 2)
            evidence = [stance["evidence"] for stance in theme["stances"]]
            self.assertTrue(all(evidence))
            self.assertTrue(all(stance["stance"] == "mixed" for stance in theme["stances"]))
        self.assertEqual(result["unused_sources"], [])
        self.assertIn("FX-003", result["excluded_sources"])
        self.assertTrue(any("FX-003" in warning for warning in result["warnings"]))
        self.assertIn("not semantic synthesis", result["boundary"])

    def test_single_full_text_source_yields_no_themes(self):
        only = [item for item in _sources() if item["source_id"] != "FX-002"]
        result = synthesize_sources_deterministic(only)
        self.assertEqual(result["theme_count"], 0)
        self.assertEqual(len(result["excluded_sources"]), 1)


class PaperSynthesisConsumptionTest(unittest.TestCase):
    def test_related_work_lists_cross_source_themes(self):
        from research_agent.contracts import (
            LiteratureBrief,
            SectionBrief,
            SourceBrief,
            Span,
        )
        from research_agent.modules.paper import PROFILES, PaperRequest, _deterministic_draft

        request = PaperRequest(
            topic="passivation stability",
            language="en",
            venue_type="en_conference",
            synthesis=synthesize_sources_deterministic(_sources()),
            spans=[
                Span(span_id="FX-001-S01-01", source_id="FX-001", section="Results", text="passivation improves stability", start=0, end=10),
                Span(span_id="FX-002-S01-01", source_id="FX-002", section="Results", text="stability reproducibility", start=0, end=10),
            ],
            literature_brief=LiteratureBrief(
                coverage_score=1.0,
                saturation="saturated",
                target_sources=2,
                target_full_text=2,
                facets=[],
                source_briefs=[
                    SourceBrief(
                        source_id="FX-001", title="Paper A", year=2025, venue="V",
                        full_text=True, span_count=1, sections=["Results"], excerpt="passivation",
                    ),
                    SourceBrief(
                        source_id="FX-002", title="Paper B", year=2024, venue="V",
                        full_text=True, span_count=1, sections=["Results"], excerpt="stability",
                    ),
                ],
                sections=[SectionBrief(section="Results", source_ids=["FX-001", "FX-002"], span_count=2, excerpts=["passivation"])],
                highlights=[],
                summary="two full-text sources",
            ),
        )
        draft = _deterministic_draft(request, PROFILES["en_conference"])
        related = next(item for item in draft if item.section == "Related Work")
        self.assertIn("Cross-source themes", related.text)
        self.assertIn("[FX-001-S01-01]", related.text)
        self.assertIn("[FX-002-S01-01]", related.text)
        self.assertIn("not semantic synthesis", related.text)

    def test_related_work_without_synthesis_is_unchanged(self):
        from research_agent.contracts import (
            LiteratureBrief,
            SectionBrief,
            SourceBrief,
            Span,
        )
        from research_agent.modules.paper import PROFILES, PaperRequest, _deterministic_draft

        brief = LiteratureBrief(
            coverage_score=1.0,
            saturation="saturated",
            target_sources=2,
            target_full_text=2,
            facets=[],
            source_briefs=[
                SourceBrief(
                    source_id="FX-001", title="Paper A", year=2025, venue="V",
                    full_text=True, span_count=1, sections=["Results"], excerpt="passivation",
                ),
            ],
            sections=[SectionBrief(section="Results", source_ids=["FX-001"], span_count=1, excerpts=["passivation"])],
            highlights=[],
            summary="one full-text source",
        )
        spans = [
            Span(span_id="FX-001-S01-01", source_id="FX-001", section="Results", text="passivation", start=0, end=10),
        ]
        plain = PaperRequest(topic="t", language="en", venue_type="en_conference", spans=list(spans), literature_brief=brief)
        with_empty = PaperRequest(topic="t", language="en", venue_type="en_conference", spans=list(spans), literature_brief=brief, synthesis={"themes": []})
        plain_draft = _deterministic_draft(plain, PROFILES["en_conference"])
        empty_draft = _deterministic_draft(with_empty, PROFILES["en_conference"])
        self.assertEqual(
            next(item for item in plain_draft if item.section == "Related Work").text,
            next(item for item in empty_draft if item.section == "Related Work").text,
        )


class ResumeDirTest(unittest.TestCase):
    def test_resume_inputs_pick_up_gate_artifacts(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "flow").mkdir()
            (run_dir / "protocol").mkdir()
            (run_dir / "run").mkdir()
            (run_dir / "flow" / "g1-decision.json").write_text("{}", encoding="utf-8")
            (run_dir / "protocol" / "protocol-card.json").write_text("{}", encoding="utf-8")
            (run_dir / "run" / "run-capsule.json").write_text("{}", encoding="utf-8")
            (run_dir / "run" / "ea.json").write_text("{}", encoding="utf-8")
            found = _resume_pipeline_inputs(run_dir)
            self.assertEqual(
                found["g1_decision"], str(run_dir / "flow" / "g1-decision.json")
            )
            self.assertEqual(
                found["protocol_file"], str(run_dir / "protocol" / "protocol-card.json")
            )
            self.assertEqual(found["run_dir"], str(run_dir / "run"))
            self.assertNotIn("claim_file", found)

    def test_resume_inputs_prefers_top_level_g1(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "g1-decision.json").write_text("{}", encoding="utf-8")
            found = _resume_pipeline_inputs(run_dir)
            self.assertEqual(found["g1_decision"], str(run_dir / "g1-decision.json"))

    def test_empty_dir_yields_nothing(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_resume_pipeline_inputs(Path(tmp)), {})


if __name__ == "__main__":
    unittest.main()

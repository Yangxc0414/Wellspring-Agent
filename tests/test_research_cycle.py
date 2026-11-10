import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from research_agent.research_cycle import (
    CONVERGED_KIND,
    EXHAUSTED_KIND,
    EXPANDED_KIND,
    HUMAN_BLOCK_NOTE,
    OBSERVED_KIND,
    CycleReport,
    decide_next_cycle,
    observe,
    run_literature_cycle,
)
from research_agent.run_events import verify_events

FIXTURES = Path("modules/literature/fixtures")


def _fake_result(sources, spans, score, saturation, gaps=0, grade="no"):
    brief = SimpleNamespace(coverage_score=score, saturation=saturation, gaps=[])
    return SimpleNamespace(
        hits=[SimpleNamespace(full_text=True) for _ in range(sources)],
        spans=[object()] * spans,
        brief=brief,
        coverage=SimpleNamespace(gaps=[object()] * gaps),
        warnings=["evidence_breadth=sources:%d ... review_grade:%s" % (sources, grade)],
        fixture_mode=False,
    )


class _ScriptedAgent:
    def __init__(self, results):
        self.results = list(results)
        self.budgets = []

    def run(self, request):
        self.budgets.append(request.max_sources)
        return self.results.pop(0)


def _local_corpus(destination):
    """Export the repository's CC-BY full texts as a local corpus (no invented text)."""
    written = 0
    for name in ("real_corpus.json", "transfer_corpus.json"):
        payload = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
        for paper in payload["papers"]:
            body = "\n\n".join(
                "%s\n%s" % (section.get("heading", ""), section.get("text", ""))
                for section in (paper.get("sections") or [])
            )
            if not body.strip():
                continue
            (destination / (paper["source_id"].replace("/", "_") + ".txt")).write_text(
                "# " + paper["title"] + "\n\n" + body, encoding="utf-8"
            )
            written += 1
    return written


class ObserveTest(unittest.TestCase):
    def test_observe_reads_the_verdict_without_mutating_it(self):
        result = _fake_result(3, 24, 0.675, "partial", gaps=2)
        before = len(result.warnings)
        row = observe(result)
        self.assertEqual(row["sources"], 3)
        self.assertEqual(row["spans"], 24)
        self.assertEqual(row["coverage_score"], 0.675)
        self.assertEqual(row["saturation"], "partial")
        self.assertEqual(row["gaps"], 2)
        self.assertEqual(row["review_grade"], "no")
        self.assertEqual(len(result.warnings), before)

    def test_review_grade_is_taken_from_the_existing_receipt(self):
        self.assertEqual(
            observe(_fake_result(6, 48, 1.0, "saturated", grade="yes"))["review_grade"],
            "yes",
        )


class DecisionTest(unittest.TestCase):
    def test_partial_coverage_widens_the_next_budget(self):
        decision = decide_next_cycle(
            {"saturation": "partial", "coverage_score": 0.675, "gaps": 2},
            budget=3, cycles_used=0,
        )
        self.assertEqual(decision["action"], "widen")
        self.assertEqual(decision["next_budget"], 6)
        self.assertEqual(decision["blocked_by_human"], [])

    def test_saturation_stops_the_loop_immediately(self):
        decision = decide_next_cycle(
            {"saturation": "saturated", "review_grade": "yes"},
            budget=24, cycles_used=0,
        )
        self.assertEqual((decision["action"], decision["status"]), ("stop", "converged"))
        self.assertEqual(decision["next_budget"], 24)

    def test_both_budgets_are_bounded_and_name_the_human_action(self):
        by_cycles = decide_next_cycle(
            {"saturation": "partial"}, budget=24, cycles_used=2, max_cycles=3
        )
        by_cap = decide_next_cycle(
            {"saturation": "partial"}, budget=30, cycles_used=0, budget_cap=30
        )
        for decision in (by_cycles, by_cap):
            self.assertEqual(decision["action"], "stop")
            self.assertEqual(decision["status"], "exhausted")
            self.assertIn(HUMAN_BLOCK_NOTE, decision["blocked_by_human"])

    def test_a_decision_never_contains_a_gate_or_signature_action(self):
        decision = decide_next_cycle(
            {"saturation": "insufficient", "coverage_score": 0.0, "gaps": 5},
            budget=3, cycles_used=0,
        )
        self.assertEqual(decision["action"], "widen")
        self.assertNotIn("approve", json.dumps(decision).lower())
        self.assertNotIn("sign", json.dumps(decision).lower())
        self.assertEqual(decision["blocked_by_human"], [])

    def test_widening_is_capped(self):
        decision = decide_next_cycle(
            {"saturation": "partial"}, budget=25, cycles_used=0, budget_cap=30
        )
        self.assertEqual(decision["next_budget"], 30)


class LoopControlTest(unittest.TestCase):
    def test_the_verdict_changes_the_next_runs_parameter(self):
        agent = _ScriptedAgent([
            _fake_result(3, 24, 0.675, "partial", gaps=2),
            _fake_result(6, 48, 1.0, "saturated", grade="yes"),
        ])
        events = []
        report = run_literature_cycle(
            agent, "topic", initial_budget=3, max_cycles=3, events=events
        )
        self.assertEqual(agent.budgets, [3, 6], "the verdict must change the next call")
        self.assertTrue(report.converged)
        self.assertEqual((report.initial_budget, report.final_budget), (3, 6))
        self.assertEqual([row["sources"] for row in report.rounds], [3, 6])
        self.assertTrue(verify_events(events)["ok"])
        self.assertEqual(
            [entry["kind"] for entry in events],
            [OBSERVED_KIND, EXPANDED_KIND, OBSERVED_KIND, CONVERGED_KIND],
        )

    def test_exhaustion_does_not_pretend_to_converge_and_names_the_human(self):
        agent = _ScriptedAgent([
            _fake_result(3, 5, 0.454, "partial", gaps=4)
            for _ in range(3)
        ])
        events = []
        report = run_literature_cycle(
            agent, "topic", initial_budget=3, max_cycles=3, events=events
        )
        self.assertFalse(report.converged)
        self.assertEqual(report.status, "exhausted")
        self.assertEqual(len(report.rounds), 3)
        self.assertTrue(any(entry["kind"] == EXHAUSTED_KIND for entry in events))
        self.assertTrue(any(
            entry["payload"].get("blocked_by_human")
            for entry in events if entry["kind"] == EXHAUSTED_KIND
        ))
        self.assertTrue(verify_events(events)["ok"])

    def test_report_is_json_safe_and_the_warning_carries_the_effect(self):
        agent = _ScriptedAgent([
            _fake_result(3, 24, 0.675, "partial", gaps=2),
            _fake_result(6, 48, 1.0, "saturated", grade="yes"),
        ])
        report = run_literature_cycle(agent, "topic", initial_budget=3, max_cycles=3)
        payload = report.to_dict()
        json.dumps(payload)
        self.assertIn("retrieval budget only", payload["boundary"])
        self.assertIn("sources:3->6", report.warning())
        self.assertIn("coverage:0.675->1.0", report.warning())
        self.assertIsInstance(report, CycleReport)


class RealCorpusLoopTest(unittest.TestCase):
    def test_a_real_local_corpus_converges_by_widening_the_budget(self):
        from research_agent.adapters.local_document_retriever import LocalDocumentRetriever
        from research_agent.adapters.simple_parser import SimpleParser
        from research_agent.modules.literature import LiteratureAgent
        from research_agent.specs import SpecStore

        with tempfile.TemporaryDirectory() as tmp:
            written = _local_corpus(Path(tmp))
            self.assertGreaterEqual(written, 6)
            agent = LiteratureAgent(
                SpecStore().load("literature"),
                LocalDocumentRetriever(Path(tmp)),
                SimpleParser(),
            )
            events = []
            report = run_literature_cycle(
                agent, "self-improving agent", initial_budget=3,
                max_cycles=3, budget_cap=12, source_scope=["local"], events=events,
            )
            self.assertTrue(report.converged, report.stop_reason)
            self.assertEqual([row["budget"] for row in report.rounds], [3, 6])
            first, last = report.rounds[0], report.rounds[-1]
            self.assertLess(first["coverage_score"], last["coverage_score"])
            self.assertGreater(last["sources"], first["sources"])
            self.assertEqual(last["saturation"], "saturated")
            self.assertEqual(last["gaps"], 0)
            self.assertTrue(verify_events(events)["ok"])


class PipelineIntegrationTest(unittest.TestCase):
    def test_default_pipeline_behaviour_is_unchanged(self):
        from research_agent.pipeline import PipelineRequest, PipelineRunner
        from research_agent.specs import SpecStore

        result = PipelineRunner(SpecStore()).run(
            PipelineRequest(topic="钙钛矿 界面 钝化 稳定性", language="zh", run_id="NO-LOOP")
        )
        self.assertNotIn("adaptive_cycle", result.modules)
        self.assertFalse(any(w.startswith("adaptive_cycle=") for w in result.warnings))
        self.assertTrue(result.fixture_mode)

    def test_adaptive_pipeline_writes_the_cycle_projection_and_a_receipt(self):
        from research_agent.adapters.local_document_retriever import LocalDocumentRetriever
        from research_agent.adapters.simple_parser import SimpleParser
        from research_agent.pipeline import PipelineRequest, PipelineRunner
        from research_agent.specs import SpecStore

        with tempfile.TemporaryDirectory() as tmp:
            _local_corpus(Path(tmp))
            result = PipelineRunner(
                SpecStore(),
                retriever=LocalDocumentRetriever(Path(tmp)),
                parser=SimpleParser(),
                source_scope=["local"],
            ).run(
                PipelineRequest(
                    topic="self-improving agent", language="zh", max_sources=3,
                    adaptive_retrieval=True, run_id="WITH-LOOP",
                )
            )
            cycle = result.modules["adaptive_cycle"]
            self.assertEqual(cycle["status"], "converged")
            self.assertEqual(len(cycle["rounds"]), 2)
            self.assertGreater(
                len(result.modules["literature"]["spans"]),
                len(result.modules["literature"]["hits"]) * 4,
            )
            self.assertTrue(any(w.startswith("adaptive_cycle=") for w in result.warnings))
            self.assertTrue(verify_events(result.events)["ok"])
            self.assertTrue(any(
                entry["kind"] == CONVERGED_KIND for entry in result.events
            ))


if __name__ == "__main__":
    unittest.main()

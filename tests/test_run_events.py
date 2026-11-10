import json
import tempfile
import unittest
from pathlib import Path

from research_agent.pipeline import evaluate_g3_g5
from research_agent.run_events import (
    COMMITTED_KIND,
    EVENT_FILENAME,
    REJECTED_KIND,
    append_event,
    commit_boundary,
    read_events,
    replay_boundaries,
    verify_events,
    write_events,
)
from research_agent.verdicts import parse_unittest_output, verdict_record


class EventChainTest(unittest.TestCase):
    def test_a_clean_chain_verifies_and_reports_its_last_hash(self):
        events = []
        append_event(events, "stage_start", phase="S1", at="2026-11-07T00:00:00+00:00")
        append_event(events, "stage_start", phase="S2", at="2026-11-07T00:00:01+00:00")
        report = verify_events(events)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["count"], 2)
        self.assertEqual(report["last_hash"], events[-1]["entry_hash"])
        self.assertEqual(events[1]["prev_hash"], events[0]["entry_hash"])

    def test_editing_an_earlier_entry_is_detected_not_repaired(self):
        events = []
        append_event(events, "stage_start", phase="S1", at="t1")
        append_event(events, "stage_start", phase="S2", at="t2")
        events[0]["payload"]["message"] = "rewritten after the fact"
        report = verify_events(events)
        self.assertFalse(report["ok"])
        self.assertTrue(any("entry_hash mismatch" in error for error in report["errors"]))
        # The audit never rewrites the list to make it green again.
        self.assertEqual(events[0]["payload"]["message"], "rewritten after the fact")

    def test_a_broken_seq_or_prev_hash_is_reported(self):
        events = []
        append_event(events, "a", at="t1")
        append_event(events, "b", at="t2")
        events[1]["seq"] = 9
        report = verify_events(events)
        self.assertFalse(report["ok"])
        self.assertTrue(any("seq is 9" in error for error in report["errors"]))
        events[1]["seq"] = 2
        events[1]["prev_hash"] = "deadbeef"
        self.assertTrue(any("prev_hash mismatch" in error for error in verify_events(events)["errors"]))


class BoundaryCommitTest(unittest.TestCase):
    def test_a_pending_human_gate_refuses_to_commit(self):
        events = []
        decision = commit_boundary(
            events, "pipeline",
            [{"gate": "G1", "status": "pass"}, {"gate": "G2", "status": "needs_human"}],
        )
        self.assertFalse(decision["ok"])
        self.assertFalse(decision["committed"])
        self.assertEqual(decision["rejected"], ["G2"])
        self.assertEqual(events[-1]["kind"], REJECTED_KIND)
        replay = replay_boundaries(events)
        self.assertEqual(replay["boundaries"], [])
        self.assertEqual(replay["last_committed"], "")

    def test_all_passing_gates_commit_exactly_once(self):
        events = []
        decision = commit_boundary(
            events, "S4",
            [{"gate": "G1", "status": "pass"}, {"gate": "G2", "status": "skipped"}],
        )
        self.assertTrue(decision["ok"])
        self.assertTrue(decision["committed"])
        self.assertEqual(events[-1]["kind"], COMMITTED_KIND)
        self.assertEqual(replay_boundaries(events)["boundaries"], ["S4"])

    def test_an_empty_gate_list_is_fail_closed(self):
        events = []
        decision = commit_boundary(events, "pipeline", [])
        self.assertFalse(decision["ok"])
        self.assertEqual(decision["rejected"], ["no_gates"])

    def test_a_broken_chain_covers_nothing_on_replay(self):
        events = []
        append_event(events, COMMITTED_KIND, phase="S4", at="t1")
        events[0]["payload"]["gates_checked"] = 99
        replay = replay_boundaries(events)
        self.assertFalse(replay["ok"])
        self.assertEqual(replay["boundaries"], [])
        self.assertTrue(replay["errors"])


class EventPersistenceTest(unittest.TestCase):
    def test_write_events_appends_only_and_is_idempotent(self):
        events = []
        append_event(events, "run_start", at="t1")
        append_event(events, "stage_start", phase="S1", at="t2")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / EVENT_FILENAME
            first = write_events(path, events)
            self.assertEqual((first["existing"], first["appended"]), (0, 2))
            head = path.read_text(encoding="utf-8").splitlines()
            append_event(events, "run_complete", at="t3")
            second = write_events(path, events)
            self.assertEqual((second["existing"], second["appended"]), (2, 1))
            self.assertEqual(path.read_text(encoding="utf-8").splitlines()[:2], head)
            self.assertTrue(verify_events(read_events(path))["ok"])
            third = write_events(path, events)
            self.assertEqual(third["appended"], 0)

    def test_a_corrupted_existing_file_is_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / EVENT_FILENAME
            events = []
            append_event(events, "run_start", at="t1")
            write_events(path, events)
            rows = path.read_text(encoding="utf-8").splitlines()
            broken = json.loads(rows[0])
            broken["payload"]["message"] = "tampered"
            path.write_text(json.dumps(broken, ensure_ascii=False) + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                write_events(path, events)


class SingleGateAuthorityTest(unittest.TestCase):
    def test_g3_g5_statuses_have_one_pure_source(self):
        self.assertEqual(
            [(g["gate"], g["status"]) for g in evaluate_g3_g5()],
            [("G3", "blocked"), ("G5", "blocked")],
        )
        self.assertEqual(
            [(g["gate"], g["status"]) for g in evaluate_g3_g5("ready")],
            [("G3", "pass"), ("G5", "needs_human")],
        )
        self.assertEqual(
            [(g["gate"], g["status"]) for g in evaluate_g3_g5("blocked")],
            [("G3", "blocked"), ("G5", "blocked")],
        )
        self.assertIn("EA exists", evaluate_g3_g5(has_ea=True)[1]["reason"])
        self.assertIn(
            "unresolved checks",
            evaluate_g3_g5("blocked")[1]["reason"],
        )

    def test_the_same_function_drives_runner_and_postprocess(self):
        # The runner sees no closure report; the artifact writer sees "ready".
        # Both must agree with evaluate_g3_g5, and no dict may be mutated in place.
        before = evaluate_g3_g5(has_ea=True)
        after = evaluate_g3_g5("ready")
        self.assertNotEqual(before[0]["status"], after[0]["status"])
        self.assertEqual(before[0]["status"], "blocked")  # original list untouched


class VerdictCountTest(unittest.TestCase):
    def test_failure_counts_reach_the_structured_record(self):
        parsed = parse_unittest_output(
            "Ran 1256 tests in 1917.124s\n\nFAILED (failures=39, errors=115)\n"
        )
        self.assertEqual((parsed["failures"], parsed["errors"]), (39, 115))
        self.assertFalse(parsed["ok"])
        record = verdict_record(
            fingerprint="abc", tests_run=parsed["tests_run"], seconds=parsed["seconds"],
            ok=parsed["ok"], finished_at="t", summary=parsed["summary"],
            failures=parsed["failures"], errors=parsed["errors"],
        )
        self.assertEqual((record["failures"], record["errors"]), (39, 115))
        self.assertIn("errors=115", record["summary_line"])

    def test_a_green_run_reports_zero_counts_and_an_interrupted_run_is_not_zeroed(self):
        green = parse_unittest_output("Ran 10 tests in 1.0s\n\nOK\n")
        self.assertEqual((green["failures"], green["errors"]), (0, 0))
        interrupted = parse_unittest_output("no verdict line at all")
        self.assertFalse(interrupted["found"])
        self.assertFalse(interrupted["ok"])
        self.assertEqual(interrupted["why"].split(":")[0],
                         "no 'Ran N tests' line")


if __name__ == "__main__":
    unittest.main()

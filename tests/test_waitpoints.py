import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research_agent.waitpoints import (
    WaitpointError,
    WaitpointStore,
    mark_delegation_acted,
    pending_delegation_events,
    record_delegation_events,
    triage_notices,
)


class WaitpointTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = WaitpointStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_secret_is_hashed_and_progress_does_not_fire(self):
        created = self.store.create(
            label="nightly training",
            intent="compare loss after the run",
            owner="S5/demo/iris",
        )
        waitpoint_id = created["waitpoint"]["waitpoint_id"]
        secret = created["secret"]
        self.assertNotIn(secret, created["how_to_signal"]["cli"])
        raw = (self.root / (waitpoint_id + ".json")).read_text(encoding="utf-8")
        self.assertNotIn(secret, raw)
        self.assertNotIn('"secret"', raw)
        with self.assertRaises(WaitpointError):
            self.store.signal(waitpoint_id, "wrong-secret")
        progress = self.store.signal(
            waitpoint_id, secret, status="progress", message="still running"
        )
        self.assertTrue(progress["accepted"])
        self.assertFalse(progress["fired"])
        self.assertEqual(self.store.status(waitpoint_id)["state"], "armed")
        fired = self.store.signal(
            waitpoint_id, secret, status="ok", message="loss 0.42", data="stdout tail"
        )
        self.assertTrue(fired["fired"])
        self.assertEqual(self.store.status(waitpoint_id)["state"], "fired")
        notice = self.store.inbox("S5/demo/iris")[0]
        self.assertTrue(notice["data_is_untrusted"])
        self.assertEqual(notice["signals"][-1]["message"], "loss 0.42")

    def test_members_quorum_and_dedupe(self):
        created = self.store.create(
            label="three arms",
            intent="wait for both arms",
            owner="S5/demo/iris",
            members=["arm2", "arm6"],
            quorum=2,
            fail_fast=False,
        )
        waitpoint_id = created["waitpoint"]["waitpoint_id"]
        secret = created["secret"]
        with self.assertRaises(WaitpointError):
            self.store.signal(waitpoint_id, secret, status="ok")
        first = self.store.signal(waitpoint_id, secret, member="arm2", dedupe_key="arm2-1")
        self.assertFalse(first["fired"])
        duplicate = self.store.signal(waitpoint_id, secret, member="arm2", dedupe_key="arm2-1")
        self.assertTrue(duplicate["duplicate"])
        progress = self.store.signal(waitpoint_id, secret, member="arm6", status="progress")
        self.assertFalse(progress["fired"])
        second = self.store.signal(waitpoint_id, secret, member="arm6")
        self.assertTrue(second["fired"])
        self.assertEqual(self.store.status(waitpoint_id)["state"], "fired")

    def test_concurrent_signals_produce_one_wake(self):
        created = self.store.create(
            label="race",
            intent="one terminal wake",
            owner="S5/demo/iris",
        )
        waitpoint_id = created["waitpoint"]["waitpoint_id"]
        secret = created["secret"]
        barrier = threading.Barrier(8)

        def send(index):
            barrier.wait()
            try:
                return self.store.signal(waitpoint_id, secret, message="signal-%d" % index)
            except WaitpointError as exc:
                return {"error": str(exc)}

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(send, range(8)))
        self.assertFalse(any("error" in item for item in results))
        status = self.store.status(waitpoint_id)
        self.assertEqual(status["state"], "fired")
        self.assertEqual(len(status["wakes"]), 1)
        self.assertEqual(len(self.store.consume("S5/demo/iris")), 1)
        self.assertEqual(self.store.consume("S5/demo/iris"), [])

    def test_expire_and_owner_scoping(self):
        one = self.store.create(label="one", intent="expire", owner="owner-a", ttl_seconds=1)
        two = self.store.create(label="two", intent="other", owner="owner-b")
        one_id = one["waitpoint"]["waitpoint_id"]
        record_path = self.root / (one_id + ".json")
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["expires_at"] = "2000-01-01T00:00:00+00:00"
        record_path.write_text(json.dumps(record), encoding="utf-8")
        expired = self.store.expire()
        self.assertEqual([item["waitpoint_id"] for item in expired], [one_id])
        self.assertEqual(self.store.status(one_id)["state"], "expired")
        self.assertEqual(self.store.inbox("owner-b"), [])
        self.assertEqual(len(self.store.inbox("owner-a")), 1)
        self.assertEqual(len(self.store.consume("owner-a")), 1)
        self.assertEqual(self.store.consume("owner-a"), [])
        self.assertEqual(self.store.status(two["waitpoint"]["waitpoint_id"])["state"], "armed")

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(WaitpointError):
            self.store.create(label="", intent="x", owner="o")
        with self.assertRaises(WaitpointError):
            self.store.create(label="x", intent="x", owner="o", ttl_seconds=0)
        with self.assertRaises(WaitpointError):
            self.store.create(label="x", intent="x", owner="o", max_signals=0)
        with self.assertRaises(WaitpointError):
            self.store.create(label="x", intent="x", owner="o", members=["a", "a"])
        with self.assertRaises(WaitpointError):
            self.store.create(label="x", intent="x", owner="o", members=["a"], quorum=2)


class DelegationTriageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _notice(self, wake_id="WK-1", label="iris training finished"):
        return {
            "wake_id": wake_id,
            "waitpoint_id": "WP-1",
            "label": label,
            "intent": "compare loss",
            "fired_at": "2026-11-11T00:00:00+00:00",
            "signals": [{"message": "loss 0.42"}],
        }

    def test_no_scope_defaults_to_reject(self):
        triage = triage_notices([self._notice()], None)
        self.assertEqual(triage["relevant"], [])
        self.assertEqual(len(triage["discarded"]), 1)
        self.assertIn("default reject", triage["discarded"][0]["reason"])

    def test_scope_match_is_relevant(self):
        triage = triage_notices([self._notice()], ["iris"])
        self.assertEqual(len(triage["relevant"]), 1)
        self.assertEqual(triage["relevant"][0]["matched_terms"], ["iris"])
        self.assertEqual(triage["discarded"], [])

    def test_ledger_append_only_idempotent_and_acted(self):
        notices = [self._notice(), self._notice("WK-2", "unrelated job")]
        first = record_delegation_events(self.project, notices, ["iris"])
        self.assertEqual(first["added"], 2)
        second = record_delegation_events(self.project, notices, ["iris"])
        self.assertEqual(second["added"], 0)
        pending = pending_delegation_events(self.project)
        self.assertEqual([e["wake_id"] for e in pending], ["WK-1"])
        self.assertEqual(mark_delegation_acted(self.project, ["WK-1"]), 1)
        self.assertEqual(pending_delegation_events(self.project), [])
        ledger = json.loads(
            (self.project / "delegation-events.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(ledger["events"]), 2)
        self.assertTrue(all(e["data_is_untrusted"] for e in ledger["events"]))
        self.assertEqual(
            [e["relevance"] for e in ledger["events"]], ["relevant", "discarded"]
        )


if __name__ == "__main__":
    unittest.main()

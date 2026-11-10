"""A host that can only exchange files must be able to supply model capability, and must not be
able to reach any gate through that channel."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for entry in (str(ROOT), str(ROOT / "research_agent")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from research_agent.handoff import (  # noqa: E402
    ANSWER_DIR,
    REQUEST_DIR,
    answer_filename,
    export_pending,
    handoff_status,
    import_answers,
)
from research_agent.host_model import ModelTurnLedger  # noqa: E402

EXPERTS = {
    "json": True,
    "object": False,
    "array_field": "candidates",
    "min_items": 1,
    "require_keys": ["candidates"],
    "forbid_substrings": ["TODO"],
}


class HandoffCycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = ModelTurnLedger(self.root / "turns.json")
        self.outbox = self.root / "handoff"
        self.turn = self.ledger.create(
            messages=[
                {"role": "system", "content": "produce candidates"},
                {"role": "user", "content": json.dumps({"topic": "archives"})},
            ],
            profile_id="host-agent",
            module="idea",
            purpose="S2 idea candidates",
            expects=EXPERTS,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _answer(self, payload):
        (self.outbox / ANSWER_DIR / answer_filename(self.turn["turn_id"])).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

    def test_export_then_import_completes_the_turn(self):
        report = export_pending(self.ledger, self.outbox)
        self.assertEqual(report["exported"], 1)
        request = report["turns"][0]
        self.assertTrue((self.outbox / request["request_file"]).is_file())
        self.assertFalse(request["already_answered"])
        exported = json.loads(
            (self.outbox / request["request_file"]).read_text(encoding="utf-8")
        )
        self.assertEqual(exported["module"], "idea")
        self.assertEqual(exported["messages_sha256"], self.turn["messages_sha256"])
        self.assertEqual(exported["expects"], EXPERTS)

        self._answer({"json": {"candidates": [{"title": "T", "hypothesis": "H"}]}})
        outcome = import_answers(self.ledger, self.outbox, host_label="zcode-offline")
        self.assertEqual(
            [item["turn_id"] for item in outcome["accepted"]], [self.turn["turn_id"]]
        )
        self.assertEqual(outcome["rejected"], [])
        stored = self.ledger.get(self.turn["turn_id"])
        self.assertEqual(stored["status"], "responded")
        self.assertEqual(stored["response"]["host_label"], "zcode-offline")
        # the answer is consumed once: a second import is refused, not replayed
        again = import_answers(self.ledger, self.outbox)
        self.assertEqual(again["accepted"], [])
        self.assertIn("already responded", again["rejected"][0]["errors"][0])

    def test_a_bad_shape_is_rejected_by_the_ledger_and_stays_pending(self):
        export_pending(self.ledger, self.outbox)
        # an empty candidate list violates the turn's own declared shape
        self._answer({"json": {"candidates": []}})
        outcome = import_answers(self.ledger, self.outbox)
        self.assertEqual(outcome["accepted"], [])
        self.assertTrue(outcome["rejected"][0]["errors"])
        self.assertEqual(self.ledger.get(self.turn["turn_id"])["status"], "pending")
        self.assertEqual(self.ledger.get(self.turn["turn_id"])["reject_count"], 1)

    def test_an_unreadable_answer_file_is_rejected_without_touching_the_ledger(self):
        export_pending(self.ledger, self.outbox)
        self._answer({"text": 12345})
        outcome = import_answers(self.ledger, self.outbox)
        self.assertEqual(outcome["accepted"], [])
        self.assertIn("text", outcome["rejected"][0]["errors"][0])
        self.assertEqual(self.ledger.get(self.turn["turn_id"])["status"], "pending")

    def test_status_reports_what_is_still_waiting(self):
        export_pending(self.ledger, self.outbox)
        first = handoff_status(self.ledger, self.outbox)
        self.assertEqual(first["exported_requests"], 1)
        self.assertEqual(first["awaiting_answer"], [self.turn["turn_id"]])
        self._answer({"text": json.dumps({"candidates": [{"title": "T", "hypothesis": "H"}]})})
        second = handoff_status(self.ledger, self.outbox)
        self.assertEqual(second["answers_present"], 1)
        self.assertEqual(second["awaiting_answer"], [])

    def test_import_without_export_is_an_error_not_a_silent_success(self):
        outcome = import_answers(self.ledger, self.root / "nothing-here")
        self.assertIn("error", outcome)
        self.assertEqual(outcome["accepted"], [])

    def test_the_channel_carries_no_gate_authority(self):
        report = export_pending(self.ledger, self.outbox)
        payload = json.dumps(report).lower()
        for verb in ("sign", "approve", "freeze", "publish", "claim_file"):
            self.assertNotIn(verb, payload, report)
        self.assertIn(
            "no claim, approval, closure or export decision can be made",
            report["boundary"],
        )
        # only the two agreed directories exist
        self.assertEqual(
            sorted(path.name for path in self.outbox.iterdir()),
            sorted([ANSWER_DIR, REQUEST_DIR]),
        )


class HandoffCliTest(unittest.TestCase):
    def test_cli_round_trip_through_files(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            ledger_path = root / "turns.json"
            outbox = root / "handoff"
            env = dict(os.environ)
            env["PYTHONIOENCODING"] = "utf-8"
            env["RESEARCH_AGENT_HOST_MODEL_LEDGER"] = str(ledger_path)
            ledger = ModelTurnLedger(ledger_path)
            turn = ledger.create(
                messages=[{"role": "user", "content": "hi"}],
                profile_id="host-agent",
                module="idea",
                purpose="S2 idea candidates",
                expects=EXPERTS,
            )
            exported = json.loads(
                subprocess.run(
                    [sys.executable, "-m", "research_agent", "handoff", "export",
                     "--outbox", str(outbox)],
                    capture_output=True, text=True, env=env, cwd=str(ROOT), encoding="utf-8",
                ).stdout
            )
            self.assertEqual(exported["exported"], 1)
            (outbox / ANSWER_DIR / answer_filename(turn["turn_id"])).write_text(
                json.dumps({"json": {"candidates": [{"title": "T", "hypothesis": "H"}]}}),
                encoding="utf-8",
            )
            imported = json.loads(
                subprocess.run(
                    [sys.executable, "-m", "research_agent", "handoff", "import",
                     "--outbox", str(outbox), "--host-label", "cli-file-drop"],
                    capture_output=True, text=True, env=env, cwd=str(ROOT), encoding="utf-8",
                ).stdout
            )
            self.assertEqual(
                [item["turn_id"] for item in imported["accepted"]], [turn["turn_id"]]
            )
            self.assertEqual(imported["accepted"][0]["host_label"], "cli-file-drop")


if __name__ == "__main__":
    unittest.main()


class HostContractTest(unittest.TestCase):
    """A plugin host must learn what will stop it before it starts a run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _contract(self, declared, outbox=None):
        from research_agent.host_contract import host_contract

        return host_contract(declared=declared, outbox=outbox or self.root / "handoff")

    def test_declaring_a_host_model_clears_the_model_block(self):
        without = self._contract(["can_call_tools", "can_write_files"])
        self.assertIn("model_stages_suspend_without_a_host_model", without["blocked"])
        with_model = self._contract(
            ["can_call_tools", "can_write_files", "can_serve_model"]
        )
        self.assertNotIn(
            "model_stages_suspend_without_a_host_model", with_model["blocked"]
        )
        self.assertTrue(with_model["model_supply"]["stages_suspended_for_host_answer"])

    def test_an_unknown_capability_is_reported_not_silently_accepted(self):
        report = self._contract(["can_teleport"])
        self.assertEqual(report["unknown_capabilities"], ["can_teleport"])
        self.assertEqual(report["declared_capabilities"], ["can_teleport"])

    def test_gates_stay_human_only_for_every_combination(self):
        from research_agent.host_contract import GATE_VERBS

        seen = []
        for declared in (
            [],
            ["can_call_tools"],
            ["can_call_tools", "can_write_files", "can_serve_model", "long_sessions"],
        ):
            report = self._contract(declared)
            # the gate list must not shrink, grow or reorder because a host claims more power
            self.assertEqual(list(GATE_VERBS), report["human_only_for_every_transport"], declared)
            seen.append(report["human_only_for_every_transport"])
            text = json.dumps(report, ensure_ascii=False).lower()
            for gate in GATE_VERBS:
                self.assertNotIn("available_" + gate.split(" ")[0].lower(), text, declared)
        self.assertEqual(1, len({json.dumps(item) for item in seen}), seen)

    def test_the_file_drop_probe_reports_a_real_failure(self):
        blocker = self.root / "not-a-directory"
        blocker.write_text("x", encoding="utf-8")
        # a host with no tool path depends on files, so an unwritable directory is a blocker
        files_only = self._contract([], outbox=blocker / "sub")
        self.assertFalse(files_only["transports"]["file_drop"])
        self.assertIn("no_writable_handoff_directory", files_only["blocked"])
        # a tool-capable host is not blocked by a directory it never uses
        tool_host = self._contract(["can_call_tools"], outbox=blocker / "sub")
        self.assertNotIn("no_writable_handoff_directory", tool_host["blocked"])

    def test_the_contract_names_the_running_build(self):
        from research_agent.paths import build_fingerprint

        report = self._contract([])
        self.assertEqual(report["build"]["fingerprint"], build_fingerprint())

    def test_cli_exposes_the_contract(self):
        import os
        import subprocess

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [
                sys.executable, "-m", "research_agent", "handoff", "contract",
                "--capabilities", "can_call_tools,can_serve_model",
                "--outbox", str(self.root / "handoff"),
            ],
            capture_output=True, text=True, env=env, cwd=str(ROOT), encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr[-300:])
        payload = json.loads(result.stdout)
        self.assertIn("can_serve_model", payload["declared_capabilities"])
        self.assertEqual(payload["schema_version"], "host-contract-0.3")

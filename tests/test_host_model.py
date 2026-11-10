"""Host-as-Model: the generation step is handed to the calling agent, not an API key."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from research_agent.adapters.research_models import _complete_json, _gateway_port
from research_agent.host_model import (
    STATUS_PENDING,
    STATUS_RESPONDED,
    HostModelPort,
    ModelTurnLedger,
    host_model_summary,
)
from research_agent.models import (
    GatewayStore,
    ModelGateway,
    ModelProfile,
    ModelRequiredError,
    ModelTurnPending,
    ProviderConfig,
)
from research_agent.models.store import SessionKeyStore

MESSAGES = [
    {"role": "system", "content": "only use the given evidence"},
    {"role": "user", "content": json.dumps({"evidence": ["REF-01"]})},
]


def _gateway(tmp: Path) -> ModelGateway:
    store = GatewayStore(tmp / "model_gateway.json")
    store.upsert_provider(
        ProviderConfig(provider_id="qoder-host", kind="host_agent", label="Qoder host")
    )
    store.upsert_profile(
        ModelProfile(profile_id="host-qoder", provider_id="qoder-host", model="host-agent")
    )
    store.set_binding("idea", "host-qoder")
    return ModelGateway(
        store, SessionKeyStore(), host_ledger_path=tmp / "host-model-turns.json"
    )


class HostAgentProviderTests(unittest.TestCase):
    def test_keyless_provider_needs_no_key_and_no_url(self):
        provider = ProviderConfig(provider_id="host", kind="host_agent", label="Host")
        self.assertEqual(provider.base_url, "")
        self.assertFalse(provider.allow_private_network)
        store = GatewayStore(Path(tempfile.mkdtemp()) / "gw.json")
        store.upsert_provider(provider)
        status = SessionKeyStore().status(provider)
        self.assertTrue(status["configured"])
        self.assertEqual(status["key_source"], "not_required")
        self.assertEqual(status["masked_key"], "")

    def test_gateway_completes_from_responded_turn(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            gateway = _gateway(tmp)
            ledger = ModelTurnLedger(tmp / "turns.json")
            gateway._host_ledger = ledger
            with self.assertRaises(ModelTurnPending) as raised:
                gateway.complete("host-qoder", MESSAGES, json_mode_override=True)
            turn_id = raised.exception.turn_id
            self.assertTrue(turn_id.startswith("MT-"))
            self.assertEqual(ledger.get(turn_id)["status"], STATUS_PENDING)
            ledger.respond(turn_id, '{"candidates":[{"title":"t"}]}', host_label="Qoder")
            response = gateway.complete("host-qoder", MESSAGES, json_mode_override=True)
            self.assertEqual(response.finish_reason, "host_turn")
            self.assertEqual(response.usage, {})
            self.assertIn("candidates", response.text)


class ModelTurnLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ledger = ModelTurnLedger(self.tmp / "turns.json")

    def test_turn_binds_request_hash_and_is_consumed_once(self):
        turn = self.ledger.create(MESSAGES, "host-qoder", module="idea", purpose="S2")
        self.assertEqual(turn["status"], STATUS_PENDING)
        self.assertEqual(len(turn["messages_sha256"]), 64)
        accepted = self.ledger.respond(
            turn["turn_id"], '{"ok": true}', host_label="Qoder Desktop"
        )
        self.assertTrue(accepted["accepted"])
        self.assertEqual(accepted["turn"]["status"], STATUS_RESPONDED)
        with self.assertRaises(ValueError):
            self.ledger.respond(turn["turn_id"], '{"ok": false}')

    def test_rejected_answer_leaves_turn_pending_and_is_not_half_written(self):
        turn = self.ledger.create(
            MESSAGES, "host-qoder", module="paper", expects={"json": True, "object": True}
        )
        rejected = self.ledger.respond(turn["turn_id"], "prose, not json")
        self.assertFalse(rejected["accepted"])
        self.assertTrue(rejected["errors"])
        reread = self.ledger.get(turn["turn_id"])
        self.assertEqual(reread["status"], STATUS_PENDING)
        self.assertEqual(reread["reject_count"], 1)
        self.assertIsNone(reread["response"])
        accepted = self.ledger.respond(turn["turn_id"], '{"sections": {}}')
        self.assertTrue(accepted["accepted"])

    def test_expired_turn_cannot_be_responded(self):
        turn = self.ledger.create(MESSAGES, "host-qoder", ttl_minutes=1)
        payload = self.ledger._load()
        for item in payload["turns"]:
            if item["turn_id"] == turn["turn_id"]:
                item["expires_at"] = (
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ).isoformat(timespec="seconds")
        self.ledger._save(payload)
        self.assertEqual(self.ledger.get(turn["turn_id"])["status"], "expired")
        with self.assertRaises(ValueError):
            self.ledger.respond(turn["turn_id"], "{}")

    def test_sink_writes_only_inside_the_project_root(self):
        project = self.tmp / "project"
        project.mkdir()
        turn = self.ledger.create(
            MESSAGES, "host-qoder", sink={"relpath": "runs/draft.md"}
        )
        accepted = self.ledger.respond(turn["turn_id"], "# draft", project_root=project)
        self.assertEqual(
            (project / "runs" / "draft.md").read_text(encoding="utf-8"), "# draft"
        )
        self.assertEqual(accepted["receipt"]["sink"]["relpath"], "runs/draft.md")
        escape = self.ledger.create(
            MESSAGES, "host-qoder", sink={"relpath": "../outside.md"}
        )
        with self.assertRaises(ValueError):
            self.ledger.respond(escape["turn_id"], "x", project_root=project)
        self.assertEqual(self.ledger.get(escape["turn_id"])["status"], STATUS_PENDING)

    def test_summary_is_read_only_and_lists_pending_ids(self):
        self.ledger.create(MESSAGES, "host-qoder", module="idea")
        summary = host_model_summary(self.ledger)
        self.assertEqual(summary["pending"], 1)
        self.assertEqual(len(summary["pending_turn_ids"]), 1)
        self.assertNotIn("text", json.dumps(summary["turns"][0]))


class HostModelPortTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ledger = ModelTurnLedger(self.tmp / "turns.json")

    def _port(self, **kwargs):
        return HostModelPort(self.ledger, "host-qoder", module="idea", **kwargs)

    def test_first_call_pends_and_replay_returns_the_answer(self):
        port = self._port()
        with self.assertRaises(ModelTurnPending) as raised:
            port.complete(MESSAGES)
        turn_id = raised.exception.turn_id
        self.assertEqual(self.ledger.get(turn_id)["module"], "idea")
        with self.assertRaises(ModelTurnPending) as again:
            self._port().complete(MESSAGES)
        self.assertEqual(again.exception.turn_id, turn_id)
        self.ledger.respond(turn_id, '{"candidates": []}')
        self.assertEqual(self._port().complete(MESSAGES), '{"candidates": []}')

    def test_different_prompt_is_a_different_turn(self):
        with self.assertRaises(ModelTurnPending) as first:
            self._port().complete(MESSAGES)
        with self.assertRaises(ModelTurnPending) as second:
            self._port().complete([{"role": "user", "content": "other"}])
        self.assertNotEqual(first.exception.turn_id, second.exception.turn_id)

    def test_void_reopens_a_sticky_answer_without_granting_anything(self):
        port = self._port()
        with self.assertRaises(ModelTurnPending) as raised:
            port.complete(MESSAGES)
        turn_id = raised.exception.turn_id
        self.ledger.respond(turn_id, '{"wrong_shape": true}')
        self.assertEqual(port.complete(MESSAGES), '{"wrong_shape": true}')

        with self.assertRaises(ValueError):
            self.ledger.void(turn_id, "")
        voided = self.ledger.void(turn_id, "valid JSON but the module needs scores")
        self.assertEqual(voided["status"], "voided")
        self.assertEqual(len(voided["voided"]["previous_text_sha256"]), 64)
        with self.assertRaises(ModelTurnPending) as again:
            self._port().complete(MESSAGES)
        self.assertNotEqual(again.exception.turn_id, turn_id)
        self.assertEqual(len(self.ledger.list_turns(status="voided")), 1)

    def test_expired_turn_is_replaced_by_a_fresh_answerable_turn(self):
        port = self._port()
        with self.assertRaises(ModelTurnPending) as raised:
            port.complete(MESSAGES)
        stale_id = raised.exception.turn_id
        payload = self.ledger._load()
        for item in payload["turns"]:
            if item["turn_id"] == stale_id:
                item["expires_at"] = (
                    datetime.now(timezone.utc) - timedelta(minutes=1)
                ).isoformat(timespec="seconds")
        self.ledger._save(payload)
        with self.assertRaises(ModelTurnPending) as second:
            self._port().complete(MESSAGES)
        fresh_id = second.exception.turn_id
        self.assertNotEqual(fresh_id, stale_id)
        self.assertEqual(self.ledger.get(fresh_id)["status"], STATUS_PENDING)
        accepted = self.ledger.respond(fresh_id, '{"candidates": []}')
        self.assertTrue(accepted["accepted"])
        self.assertEqual(self._port().complete(MESSAGES), '{"candidates": []}')

    def test_expects_json_shape_is_declared_on_the_turn(self):
        port = HostModelPort(
            self.ledger, "host-qoder", module="idea", expects={"json": True, "object": True}
        )
        with self.assertRaises(ModelTurnPending) as raised:
            port.complete(MESSAGES)
        turn = self.ledger.get(raised.exception.turn_id)
        self.assertTrue(turn["expects"]["json"])
        self.assertTrue(turn["expects"]["object"])
        self.assertIn("system", turn["request"])


class GatewayPortRoutingTests(unittest.TestCase):
    def test_host_profile_resolves_without_any_key(self):
        with tempfile.TemporaryDirectory() as raw:
            gateway = _gateway(Path(raw))
            port, note = _gateway_port("idea", None, None, gateway, strict=False)
            self.assertIsInstance(port, HostModelPort)
            self.assertIn("host agent", note)

    def test_pending_turn_is_not_degraded_to_a_template(self):
        with tempfile.TemporaryDirectory() as raw:
            gateway = _gateway(Path(raw))
            port, _note = _gateway_port("idea", None, None, gateway, strict=False)
            with self.assertRaises(ModelTurnPending):
                _complete_json(port, "system", {"evidence": []}, strict=False)


class SupplyAttributionTests(unittest.TestCase):
    """A host answer must be attributable, or config-level independence means nothing."""

    def _port(self, tmp: Path, model_name: str) -> HostModelPort:
        ledger = ModelTurnLedger(tmp / "host-model-ledger.json")
        return HostModelPort(
            ledger,
            "host-qoder",
            module="idea",
            purpose="innovation critic: novelty",
            provider_id="qoder-host",
            provider_kind="host_agent",
            model_name=model_name,
        )

    def test_gateway_port_carries_the_supply_fingerprint(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            gateway = _gateway(tmp)
            port, _note = _gateway_port("idea", None, None, gateway, strict=False)
            self.assertEqual(port.provider_id, "qoder-host")
            self.assertEqual(port.provider_kind, "host_agent")
            self.assertEqual(port.model_name, "host-agent")

    def test_answered_by_reports_the_label_from_the_ledger(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            port = self._port(tmp, "qoder-large")
            self.assertEqual(port.answered_by(), [])
            with self.assertRaises(ModelTurnPending) as caught:
                port.complete(MESSAGES, json_mode=True)
            self.assertEqual(port.turn_ids, [caught.exception.turn_id])
            self.assertEqual(port.answered_by(), [], "a pending turn has no answering agent yet")
            outcome = port.ledger.respond(
                caught.exception.turn_id, '{"ok": true}', host_label="Qoder Desktop"
            )
            self.assertTrue(outcome["accepted"], outcome)
            self.assertEqual(port.complete(MESSAGES, json_mode=True), '{"ok": true}')
            self.assertEqual(port.answered_by(), ["Qoder Desktop"])
            self.assertEqual(len(port.turn_ids), 1, "replayed answers must not duplicate turns")

    def test_two_ports_on_one_host_share_the_attribution_that_blocks_admission(self):
        from research_agent.independence import evaluate_panel

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            first = self._port(tmp, "model-a")
            second = HostModelPort(
                first.ledger,
                "host-qoder-2",
                module="idea",
                purpose="innovation critic: evidence",
                provider_id="qoder-host",
                provider_kind="host_agent",
                model_name="model-b",
            )
            pending = []
            for port in (first, second):
                with self.assertRaises(ModelTurnPending) as caught:
                    port.complete(MESSAGES, json_mode=True)
                pending.append((port, caught.exception.turn_id))
            for port, turn_id in pending:
                port.ledger.respond(turn_id, '{"ok": true}', host_label="Qoder Desktop")
            block = evaluate_panel(
                ["novelty", "evidence"],
                {"novelty": first, "evidence": second},
                rounds=1,
                answered_by={
                    "novelty": first.answered_by(),
                    "evidence": second.answered_by(),
                },
            )
            self.assertEqual(block["distinct_supplies"], 2)
            self.assertFalse(
                block["admission_eligible"],
                "two configs answered by one host agent is still one reviewer",
            )


if __name__ == "__main__":
    unittest.main()

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile

from research_agent.models import (
    GatewayStore,
    ModelGateway,
    ModelProfile,
    ModelRegistryService,
    ProviderConfig,
    SessionKeyStore,
    ThinkingConfig,
    ModelCallError,
    ModelConfigError,
)
from research_agent.models.types import validate_base_url


class _Handler(BaseHTTPRequestHandler):
    calls = []
    fail_status = 0
    fail_message = ""

    def log_message(self, *args):
        return

    def _record(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        type(self).calls.append({
            "method": self.command,
            "path": self.path,
            "headers": {str(key).lower(): value for key, value in self.headers.items()},
            "body": json.loads(body) if body else None,
        })
        return body

    def _send(self, status, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._record()
        if self.path.endswith("/models"):
            self._send(200, {"data": [{"id": "model-b"}, {"id": "model-a"}]})
            return
        self._send(404, {"error": {"message": "not found"}})

    def do_POST(self):
        self._record()
        if type(self).fail_status:
            self._send(type(self).fail_status, {
                "error": {"message": type(self).fail_message}
            })
            return
        if self.path.endswith("/chat/completions"):
            self._send(200, {
                "id": "req-openai",
                "choices": [{"message": {"content": "{\"ok\": true}"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            })
            return
        if self.path.endswith("/messages"):
            self._send(200, {
                "id": "req-anthropic",
                "content": [{"type": "thinking", "thinking": "private"}, {"type": "text", "text": "{\"ok\": true}"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 9, "output_tokens": 4},
            })
            return
        self._send(404, {"error": {"message": "not found"}})


class ModelGatewayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d/v1" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.calls = []
        _Handler.fail_status = 0
        _Handler.fail_message = ""
        self.tmp = tempfile.TemporaryDirectory()
        self.store = GatewayStore(Path(self.tmp.name) / "models.json")
        self.keys = SessionKeyStore()
        self.gateway = ModelGateway(self.store, self.keys, timeout=10, max_retries=0)

    def tearDown(self):
        self.tmp.cleanup()

    def _provider(self, kind, provider_id="test", **kwargs):
        provider = ProviderConfig(
            provider_id=provider_id,
            kind=kind,
            base_url=self.base,
            api_key_env="TEST_API_KEY",
            allow_private_network=True,
            **kwargs,
        )
        self.store.upsert_provider(provider)
        self.keys.set(provider_id, "sk-test-secret-123456")
        return provider

    def _profile(self, provider_id="test", profile_id="p1", **kwargs):
        profile = ModelProfile(
            profile_id=profile_id,
            provider_id=provider_id,
            model="test-model",
            **kwargs,
        )
        self.store.upsert_profile(profile)
        return profile

    def test_openai_thinking_translation_and_response(self):
        self._provider("openai")
        self._profile(thinking=ThinkingConfig(mode="effort", effort="high"), max_tokens=1024, json_mode=True)
        response = self.gateway.complete("p1", [{"role": "user", "content": "hi"}])
        self.assertTrue(response.text.startswith('{"ok"'))
        self.assertEqual(response.thinking_applied["effort"], "high")
        request = _Handler.calls[-1]
        body = request["body"]
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["max_completion_tokens"], 1024)
        self.assertNotIn("temperature", body)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertTrue(request["headers"]["authorization"].startswith("Bearer sk-test"))
        self.assertEqual(response.usage["prompt_tokens"], 11)

    def test_anthropic_thinking_budget_and_system(self):
        self._provider("anthropic")
        self._profile(
            thinking=ThinkingConfig(mode="budget", budget_tokens=2048),
            max_tokens=1024,
            temperature=0.2,
        )
        response = self.gateway.complete(
            "p1",
            [
                {"role": "system", "content": "system prompt"},
                {"role": "user", "content": "hello"},
            ],
        )
        self.assertEqual(response.text, '{"ok": true}')
        request = _Handler.calls[-1]
        body = request["body"]
        self.assertEqual(body["thinking"], {"type": "enabled", "budget_tokens": 2048})
        self.assertGreaterEqual(body["max_tokens"], 3072)
        self.assertNotIn("temperature", body)
        self.assertEqual(body["system"], "system prompt")
        self.assertEqual(body["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(request["headers"]["x-api-key"], "sk-test-secret-123456")
        self.assertEqual(request["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(response.usage["input_tokens"], 9)
        self.assertNotIn("private", response.text)

    def test_custom_budget_requires_extra_body(self):
        self._provider("openai_compatible")
        with self.assertRaises(ModelConfigError):
            self._profile(thinking=ThinkingConfig(mode="budget", budget_tokens=2048))

    def test_custom_budget_with_extra_body(self):
        self._provider("openai_compatible")
        self._profile(
            thinking=ThinkingConfig(mode="budget", budget_tokens=2048),
            extra_body={"enable_thinking": True, "thinking_budget": 2048},
        )
        self.gateway.complete("p1", [{"role": "user", "content": "hi"}])
        body = _Handler.calls[-1]["body"]
        self.assertTrue(body["enable_thinking"])
        self.assertEqual(body["thinking_budget"], 2048)

    def test_profile_declares_context_and_thinking_limits(self):
        self._provider("openai")
        with self.assertRaises(ModelConfigError):
            ModelProfile(profile_id="bad-budget", provider_id="test", model="m", max_tokens=2000, max_output_tokens=1000)
        with self.assertRaises(ModelConfigError):
            ModelProfile(profile_id="bad-context", provider_id="test", model="m", context_window=1000, max_output_tokens=1000)
        with self.assertRaises(ModelConfigError):
            ModelProfile(
                profile_id="no-thinking", provider_id="test", model="m",
                thinking=ThinkingConfig(mode="effort", effort="high"),
                thinking_supported=False,
            )

    def test_list_models_and_error_redaction(self):
        self._provider("openai")
        self._profile()
        models = self.gateway.list_models("test")
        self.assertEqual(models, ["model-a", "model-b"])
        _Handler.fail_status = 401
        _Handler.fail_message = "bad key sk-test-secret-123456"
        with self.assertRaises(ModelCallError) as context:
            self.gateway.complete("p1", [{"role": "user", "content": "hi"}])
        self.assertNotIn("sk-test-secret-123456", str(context.exception))
        self.assertIn("[redacted]", str(context.exception))

    def test_service_snapshot_never_returns_keys_and_call_log_has_no_prompt(self):
        self._provider("openai")
        self._profile()
        service = ModelRegistryService(self.store, self.keys, self.gateway)
        snapshot = service.snapshot()
        raw = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("sk-test-secret-123456", raw)
        provider = next(item for item in snapshot["providers"] if item["provider_id"] == "test")
        self.assertTrue(provider["configured"])
        self.assertEqual(provider["key_source"], "session")
        result = service.probe("p1", "very private prompt", system="private system")
        self.assertEqual(result["response"]["text"], '{"ok": true}')
        call = service.calls()[0]
        call_raw = json.dumps(call, ensure_ascii=False)
        self.assertNotIn("very private prompt", call_raw)
        self.assertNotIn("private system", call_raw)
        self.assertNotIn("sk-test-secret-123456", call_raw)

    def test_service_records_direct_gateway_calls(self):
        self._provider("openai")
        self._profile()
        service = ModelRegistryService(self.store, self.keys, self.gateway)
        sentinel = "private-prompt-sentinel-xyz"
        service.gateway.complete("p1", [{"role": "user", "content": sentinel}])
        calls = service.calls()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["ok"])
        self.assertEqual(calls[0]["profile_id"], "p1")
        self.assertNotIn(sentinel, json.dumps(calls, ensure_ascii=False))

    def test_store_does_not_persist_session_key(self):
        self._provider("openai")
        self._profile()
        raw = (Path(self.tmp.name) / "models.json").read_text(encoding="utf-8")
        self.assertNotIn("sk-test-secret-123456", raw)


class UrlPolicyTest(unittest.TestCase):
    def test_cleartext_only_local(self):
        with self.assertRaises(ModelConfigError):
            validate_base_url("http://example.com/v1")
        self.assertEqual(validate_base_url("http://127.0.0.1:11434/v1"), "http://127.0.0.1:11434/v1")

    def test_private_network_requires_opt_in(self):
        with self.assertRaises(ModelConfigError):
            validate_base_url("https://10.0.0.8/v1")
        self.assertEqual(
            validate_base_url("https://10.0.0.8/v1", allow_private_network=True),
            "https://10.0.0.8/v1",
        )
        with self.assertRaises(ModelConfigError):
            validate_base_url("https://metadata.google.internal/v1")


if __name__ == "__main__":
    unittest.main()

"""OpenAI 兼容 shim：外部框架的 LLM 调用路由到宿主作答（Zcode 额度）。

验收：已应答的 turn 直接返回 ChatCompletion JSON；未应答的 turn 在 wait 窗口内
被后台应答后返回；错误路径显式（401/400），永不静默降级为本地模板。
"""

import json
import tempfile
import threading
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.host_model import ModelTurnLedger
from research_agent.runtime.openai_compat import build_shim_app


def _project(tmp: Path) -> Path:
    root = Path(tmp) / "project"
    root.mkdir(parents=True)
    return root


class OpenAiCompatShimTest(unittest.TestCase):
    def _client(self, tmp: Path, token: str = ""):
        ledger_path = Path(tmp) / "host-model" / "turns.json"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = ModelTurnLedger(ledger_path)
        app = build_shim_app(
            ledger_path,
            profile_id="host-agent",
            module="flashrsi",
            wait_seconds=3,
            poll_interval=0.5,
            api_token=token,
        )
        return TestClient(app), ledger

    def _headers(self, token: str = ""):
        headers = {"Authorization": "Bearer " + token} if token else {}
        return headers

    def test_answered_turn_returns_openai_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ledger = self._client(Path(tmp))
            messages = [
                {"role": "system", "content": "你是严谨的科研评审。"},
                {"role": "user", "content": "提出 3 个候选创新点。"},
            ]
            # 预先把答案写进账本（模拟宿主已作答）：同 messages 哈希
            import hashlib

            from research_agent.host_model import canonical_messages_sha256

            sha = canonical_messages_sha256(messages)
            ledger.create(messages=messages, profile_id="host-agent", module="flashrsi",
                          purpose="external framework model call")
            turn_id = None
            store = json.loads(ledger.path.read_text(encoding="utf-8"))
            for t in store.get("turns") or []:
                if t.get("messages_sha256") == sha:
                    turn_id = t["turn_id"]
            ledger.respond(turn_id, json.dumps({"ideas": [{"title": "候选一"}]}, ensure_ascii=False),
                           host_label="Zcode-self")
            resp = client.post(
                "/v1/chat/completions",
                json={"model": "flashrsi", "messages": messages},
                headers=self._headers(""),
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["object"], "chat.completion")
            self.assertEqual(body["choices"][0]["message"]["role"], "assistant")
            self.assertIn("候选一", body["choices"][0]["message"]["content"])
            self.assertIn("turn_id", body["research_agent"])

    def test_pending_turn_is_answered_while_request_is_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, ledger = self._client(Path(tmp))
            messages = [{"role": "user", "content": "score the candidates"}]

            def _answer_later():
                import time

                store = None
                for _ in range(20):
                    time.sleep(0.3)
                    try:
                        store = json.loads(ledger.path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    for t in store.get("turns") or []:
                        if t.get("status") == "pending":
                            ledger.respond(t["turn_id"], {"text": "scored: 7/10"}, host_label="Zcode-self")
                            return

            worker = threading.Thread(target=_answer_later, daemon=True)
            worker.start()
            resp = client.post(
                "/v1/chat/completions",
                json={"model": "flashrsi", "messages": messages},
                headers=self._headers(""),
            )
            worker.join(timeout=5)
            self.assertEqual(resp.status_code, 200)
            self.assertIn("scored", resp.json()["choices"][0]["message"]["content"])

    def test_bad_token_is_401(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self._client(Path(tmp), token="secret")
            resp = client.post(
                "/v1/chat/completions",
                json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
                headers={"Authorization": "Bearer wrong"},
            )
            self.assertEqual(resp.status_code, 401)

    def test_empty_messages_is_400(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self._client(Path(tmp))
            resp = client.post("/v1/chat/completions", json={"model": "m", "messages": []})
            self.assertEqual(resp.status_code, 400)

    def test_models_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            client, _ = self._client(Path(tmp))
            resp = client.get("/v1/models")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("host-agent", resp.json()["data"][0]["id"])


if __name__ == "__main__":
    unittest.main()

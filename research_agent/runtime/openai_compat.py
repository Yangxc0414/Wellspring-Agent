"""OpenAI-compatible shim: route external frameworks' LLM calls to the Zcode host.

FlashRSI 的 MiniAgent runtime 是薄 AsyncOpenAI 封装（base_url 一等配置）。把它的
base_url 指到本 shim（http://127.0.0.1:8788/v1），LLM 调用就变成一条 pending
ModelTurn：宿主（Zcode 会话）用 research_model_respond 作答后，本端点把答案包装成
OpenAI ChatCompletion 返回——外部框架代码零改动，模型额度全部来自宿主会话。

边界：shim 只做协议转换与等待，不产生证据资格；每次调用的答案经 host-model 账本
的哈希绑定与形状校验（与 Host-as-Model 同一纪律）；Bearer 共享密钥防止本机之外
的进程消耗宿主额度。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request

from ..host_model import HostModelPort, ModelTurnLedger
from ..models.types import ModelTurnPending


def build_shim_app(
    ledger_path: Path,
    profile_id: str = "host-agent",
    *,
    module: str = "flashrsi",
    purpose: str = "external framework model call",
    wait_seconds: float = 600.0,
    poll_interval: float = 2.0,
    api_token: str = "",
    binding: Optional[Dict[str, Any]] = None,
) -> FastAPI:
    """Build a FastAPI app serving /v1/chat/completions via the host-model ledger.

    The ledger is file-backed, so this shim can run as a separate process from the
    main runtime and still share turns with research_model_respond.
    """
    app = FastAPI(title="research-agent openai-compat shim", docs_url=None, redoc_url=None)
    port = HostModelPort(
        ModelTurnLedger(Path(ledger_path)),
        profile_id,
        module=module,
        purpose=purpose,
        wait_seconds=wait_seconds,
        poll_interval=poll_interval,
        binding=binding or {},
    )

    def _check_auth(request: Request) -> None:
        if not api_token:
            return
        header = request.headers.get("authorization") or ""
        if header != "Bearer " + api_token:
            raise HTTPException(status_code=401, detail="invalid bearer token")

    @app.post("/v1/chat/completions")
    def chat_completions(request: Request, body: Dict[str, Any]) -> Dict[str, Any]:
        _check_auth(request)
        messages = body.get("messages") or []
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="messages must be a non-empty list")
        json_mode = (body.get("response_format") or {}).get("type") == "json_object"
        started = time.time()
        # complete() blocks on the ledger poll loop: the host answers the pending
        # turn (research_model_respond) while this request is held open.
        text = port.complete(
            messages,
            json_mode=json_mode,
        )
        latency_ms = int((time.time() - started) * 1000)
        turn_id = port.turn_ids[-1] if port.turn_ids else ""
        return {
            "id": "chatcmpl-" + turn_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": body.get("model") or profile_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "research_agent": {
                "turn_id": turn_id,
                "host_label_source": "answered via research_model_respond",
                "latency_ms": latency_ms,
                "boundary": (
                    "capability output via Host-as-Model: hash-bound turn, shape-checked; "
                    "no claim/gate/signature; host_label is self-reported"
                ),
            },
        }

    @app.get("/v1/models")
    def list_models(request: Request) -> Dict[str, Any]:
        _check_auth(request)
        return {"object": "list", "data": [{"id": profile_id, "object": "model", "owned_by": "research-agent"}]}

    return app


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default="runtime_data/host-model/turns.json")
    parser.add_argument("--profile", default="host-agent")
    parser.add_argument("--module", default="flashrsi")
    parser.add_argument("--purpose", default="external framework model call")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--wait-seconds", type=float, default=600.0)
    parser.add_argument("--api-token", default="", help="shared secret; empty = no auth (localhost only)")
    parser.add_argument("--binding", default="", help="JSON binding recorded on every turn")
    args = parser.parse_args(argv)

    binding = None
    if args.binding:
        binding = json.loads(args.binding)
    app = build_shim_app(
        Path(args.ledger),
        args.profile,
        module=args.module,
        purpose=args.purpose,
        wait_seconds=args.wait_seconds,
        api_token=args.api_token,
        binding=binding,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

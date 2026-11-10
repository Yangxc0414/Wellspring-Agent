"""Minimal frozen DeepSeek chat adapter.

This module is not exercised by the offline tests. It is the swap-in point for
the future frozen-model proposer: keys stay server-side, calls are bounded, and
no training/fine-tuning happens here.
"""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional


class ModelConfigError(RuntimeError):
    pass


class DeepSeekModel:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: int = 120,
        max_retries: int = 2,
        max_tokens: int = 4096,
    ):
        if not api_key:
            raise ModelConfigError("DeepSeek API key is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max(256, min(int(max_tokens), 16384))
        self.model_id = model
        self.provider_id = "deepseek"
        self.provider_kind = "openai_compatible"
        self.model_name = model
        self.profile_id = ""

    @classmethod
    def from_env(cls) -> "DeepSeekModel":
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not key:
            raise ModelConfigError("DEEPSEEK_API_KEY is not set")
        return cls(
            api_key=key,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    def complete(self, messages: List[Dict[str, str]], json_mode: bool = True) -> str:
        body: Dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=payload,
                method="POST",
                headers={
                    "Authorization": "Bearer " + self.api_key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                choices = data.get("choices") or []
                if not choices or not choices[0].get("message", {}).get("content"):
                    raise RuntimeError("model returned no message content")
                return str(choices[0]["message"]["content"])
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, RuntimeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
        raise RuntimeError("DeepSeek call failed: %s" % type(last_error).__name__)

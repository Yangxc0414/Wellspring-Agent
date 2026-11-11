"""Provider adapters and the provider-neutral model gateway."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..ports import ModelPort
from .store import GatewayStore, SessionKeyStore
from .types import (
    KEYLESS_PROVIDER_KINDS,
    ModelCallError,
    ModelConfigError,
    ModelProfile,
    ModelResponse,
    ProviderConfig,
    redact_text,
)

ANTHROPIC_VERSION = "2023-06-01"
EFFORT_BUDGET = {"minimal": 1024, "low": 1024, "medium": 4096, "high": 8192, "max": 16384}


def _messages_for_anthropic(messages: List[Dict[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
    system_parts: List[str] = []
    kept: List[Dict[str, str]] = []
    for message in messages:
        role = str(message.get("role", "user"))
        content = str(message.get("content", ""))
        if role == "system":
            if content.strip():
                system_parts.append(content)
            continue
        if role not in ("user", "assistant"):
            raise ModelConfigError("unsupported message role: " + role)
        kept.append({"role": role, "content": content})
    if not kept:
        raise ModelConfigError("at least one user message is required")
    return "\n\n".join(system_parts), kept


def _extract_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict) and item.get("type") in (None, "text", "output_text"):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
        return "".join(parts)
    return ""


def _usage_ints(raw: Any) -> Dict[str, int]:
    usage: Dict[str, int] = {}
    if not isinstance(raw, dict):
        return usage
    for key, value in raw.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            usage[str(key)] = int(value)
        elif isinstance(value, dict):
            nested = _usage_ints(value)
            for nested_key, nested_value in nested.items():
                usage[str(key) + "." + nested_key] = nested_value
    return usage


class ModelGateway:
    def __init__(
        self,
        store: GatewayStore,
        keys: Optional[SessionKeyStore] = None,
        timeout: int = 120,
        max_retries: int = 2,
        host_ledger_path: Optional[Any] = None,
    ):
        self.store = store
        self.keys = keys or SessionKeyStore()
        self.timeout = max(5, min(int(timeout), 600))
        self.max_retries = max(0, min(int(max_retries), 5))
        self.host_ledger_path = host_ledger_path
        self.on_call: Optional[Callable[[str, Any, bool, str], None]] = None
        self._host_ledger = None

    def _resolve(self, profile_id: str) -> Tuple[ModelProfile, ProviderConfig, str]:
        profile = self.store.profile(profile_id)
        provider = self.store.provider(profile.provider_id)
        key, _ = self.keys.resolve(provider)
        if not key:
            raise ModelConfigError(
                "provider %s has no API key; set %s or a session key"
                % (provider.provider_id, provider.api_key_env)
            )
        return profile, provider, key

    def host_ledger(self):
        """Durable queue used by keyless host-agent profiles."""
        if getattr(self, "_host_ledger", None) is None:
            from ..host_model import ModelTurnLedger

            self._host_ledger = ModelTurnLedger(self.host_ledger_path)
        return self._host_ledger

    def _url(self, provider: ProviderConfig, path: str) -> str:
        url = provider.base_url.rstrip("/") + path
        if provider.kind == "azure_openai" and provider.api_version:
            separator = "&" if "?" in url else "?"
            url += separator + urllib.parse.urlencode({"api-version": provider.api_version})
        return url

    def _headers(self, provider: ProviderConfig, key: str) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "research-agent-model-gateway/1.0",
        }
        if provider.kind == "anthropic":
            headers["x-api-key"] = key
            headers["anthropic-version"] = ANTHROPIC_VERSION
        elif provider.kind == "azure_openai":
            headers["api-key"] = key
        else:
            headers["Authorization"] = "Bearer " + key
        return headers

    def _build_body(
        self,
        profile: ModelProfile,
        provider: ProviderConfig,
        messages: List[Dict[str, str]],
        max_tokens_override: Optional[int],
        json_mode_override: Optional[bool],
    ) -> Tuple[Dict[str, Any], Dict[str, Any], bool]:
        thinking = profile.thinking
        if thinking.mode != "off" and not profile.thinking_supported:
            raise ModelConfigError(
                "profile declares no thinking support; switch thinking.mode to off"
            )
        thinking.validate_for(provider.kind)
        body: Dict[str, Any] = dict(profile.extra_body or {})
        for key in ("model", "messages", "stream"):
            body.pop(key, None)
        body["model"] = profile.model
        body["stream"] = False
        requested_tokens = (
            profile.max_tokens if max_tokens_override is None
            else max(16, min(int(max_tokens_override), profile.max_tokens))
        )
        applied: Dict[str, Any] = {"mode": thinking.mode}
        json_mode = profile.json_mode if json_mode_override is None else bool(json_mode_override)

        if provider.kind == "anthropic":
            system, kept = _messages_for_anthropic(messages)
            body["messages"] = kept
            if system:
                body["system"] = system
        else:
            body["messages"] = [
                {"role": str(item.get("role", "user")), "content": str(item.get("content", ""))}
                for item in messages
            ]

        if thinking.mode == "off":
            for key in ("reasoning_effort", "thinking"):
                body.pop(key, None)
            body["max_tokens"] = requested_tokens
            if profile.temperature is not None:
                body["temperature"] = profile.temperature
            else:
                body.pop("temperature", None)
            if profile.top_p is not None:
                body["top_p"] = profile.top_p
            else:
                body.pop("top_p", None)
        elif provider.kind == "anthropic":
            budget = (
                thinking.budget_tokens
                if thinking.mode == "budget"
                else EFFORT_BUDGET.get(thinking.effort, 4096)
            )
            if budget is None or budget < 1024:
                raise ModelConfigError("Anthropic thinking budget must be >= 1024")
            body["thinking"] = {"type": "enabled", "budget_tokens": int(budget)}
            body["max_tokens"] = min(64000, max(requested_tokens, int(budget) + 1024))
            body.pop("temperature", None)
            body.pop("top_p", None)
            applied.update({"budget_tokens": int(budget), "provider": "anthropic"})
        elif provider.kind in ("openai", "azure_openai"):
            body["reasoning_effort"] = thinking.effort
            body["max_completion_tokens"] = requested_tokens
            body.pop("max_tokens", None)
            body.pop("temperature", None)
            body.pop("top_p", None)
            applied.update({"effort": thinking.effort, "provider": provider.kind})
        else:
            # OpenAI-compatible providers are not standardized. Effort is
            # passed through; budget requires an explicit extra_body field.
            if thinking.mode == "effort":
                body["reasoning_effort"] = thinking.effort
                applied.update({"effort": thinking.effort, "provider": "openai_compatible"})
            elif thinking.mode == "budget":
                keys = set(profile.extra_body or {})
                if not keys & {"thinking", "enable_thinking", "thinking_budget", "reasoning"}:
                    raise ModelConfigError(
                        "custom provider budget thinking requires extra_body "
                        "(thinking/enable_thinking/thinking_budget)"
                    )
                applied.update({"budget_tokens": thinking.budget_tokens, "provider": "openai_compatible"})
            body["max_tokens"] = requested_tokens
            body.pop("temperature", None)
            body.pop("top_p", None)

        if json_mode:
            if provider.kind == "anthropic":
                return body, applied, False
            body["response_format"] = {"type": "json_object"}
            return body, applied, True
        body.pop("response_format", None)
        return body, applied, False

    def _request_json(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        payload: Optional[Dict[str, Any]],
        provider_id: str,
        secret: str,
    ) -> Dict[str, Any]:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last: Optional[ModelCallError] = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ModelCallError("provider returned a non-object JSON response", provider=provider_id)
                return value
            except urllib.error.HTTPError as exc:
                raw = exc.read(4096).decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(raw)
                except ValueError:
                    parsed = {}
                message = (
                    (parsed.get("error") or {}).get("message")
                    if isinstance(parsed.get("error"), dict) else ""
                ) or parsed.get("message") or parsed.get("detail") or raw or str(exc)
                error = ModelCallError(
                    redact_text(str(message), secret),
                    status=int(exc.code),
                    provider=provider_id,
                    request_id=str(exc.headers.get("request-id", "")) if exc.headers else "",
                    retryable=int(exc.code) in (429, 500, 502, 503, 504),
                )
                last = error
                if error.retryable and attempt < self.max_retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise error
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                error = ModelCallError(
                    "network error: " + redact_text(type(exc).__name__, secret),
                    provider=provider_id,
                    retryable=True,
                )
                last = error
                if attempt < self.max_retries:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                raise error
            except ValueError as exc:
                raise ModelCallError(
                    "provider returned invalid JSON: " + redact_text(str(exc), secret),
                    provider=provider_id,
                )
        raise last or ModelCallError("provider request failed", provider=provider_id)

    def complete(
        self,
        profile_id: str,
        messages: List[Dict[str, str]],
        max_tokens_override: Optional[int] = None,
        json_mode_override: Optional[bool] = None,
        host_module: str = "",
        host_purpose: str = "",
    ) -> ModelResponse:
        try:
            response = self._complete(
                profile_id,
                messages,
                max_tokens_override,
                json_mode_override,
                host_module,
                host_purpose,
            )
        except Exception as exc:
            self._notify_call(profile_id, None, False, str(exc))
            raise
        self._notify_call(profile_id, response, True)
        return response

    def _notify_call(self, profile_id: str, response: Any, ok: bool, error: str = "") -> None:
        if self.on_call is None:
            return
        try:
            self.on_call(profile_id, response, ok, error)
        except Exception:
            # Call metadata must never change a model result.
            pass

    def _complete(
        self,
        profile_id: str,
        messages: List[Dict[str, str]],
        max_tokens_override: Optional[int] = None,
        json_mode_override: Optional[bool] = None,
        host_module: str = "",
        host_purpose: str = "",
    ) -> ModelResponse:
        if not messages:
            raise ModelConfigError("messages must not be empty")
        profile, provider, key = self._resolve(profile_id)
        if provider.kind in KEYLESS_PROVIDER_KINDS:
            return self._complete_host(
                profile,
                provider,
                messages,
                json_mode_override,
                host_module,
                host_purpose,
            )
        body, thinking_applied, json_mode_applied = self._build_body(
            profile, provider, messages, max_tokens_override, json_mode_override
        )
        path = "/messages" if provider.kind == "anthropic" else "/chat/completions"
        started = time.monotonic()
        data = self._request_json(
            "POST",
            self._url(provider, path),
            self._headers(provider, key),
            body,
            provider.provider_id,
            key,
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        if provider.kind == "anthropic":
            text = "".join(
                str(block.get("text", ""))
                for block in (data.get("content") or [])
                if isinstance(block, dict) and block.get("type") == "text"
            )
            finish = str(data.get("stop_reason", ""))
            request_id = str(data.get("id", ""))
        else:
            choices = data.get("choices") or []
            message = (choices[0].get("message") or {}) if choices else {}
            text = _extract_text(message.get("content"))
            finish = str(choices[0].get("finish_reason", "")) if choices else ""
            request_id = str(data.get("id", ""))
        if not text:
            raise ModelCallError("provider returned no text content", provider=provider.provider_id)
        return ModelResponse(
            text=text,
            provider_id=provider.provider_id,
            model=profile.model,
            thinking_applied=thinking_applied,
            usage=_usage_ints(data.get("usage")),
            latency_ms=latency_ms,
            request_id=request_id,
            finish_reason=finish,
            json_mode_applied=json_mode_applied,
        )

    def _complete_host(
        self,
        profile: ModelProfile,
        provider: ProviderConfig,
        messages: List[Dict[str, str]],
        json_mode_override: Optional[bool],
        host_module: str = "",
        host_purpose: str = "",
    ) -> ModelResponse:
        """Keyless path: the calling agent is the model, so no request leaves the host."""
        from ..host_model import HostModelPort

        started = time.monotonic()
        # A pending turn that names no stage forces the host to dump the prompt to learn what is
        # waiting; the caller always knows, so carry it through.
        port = HostModelPort(
            self.host_ledger(),
            profile.profile_id,
            module=host_module,
            purpose=host_purpose,
        )
        # ExecPort 路由分派（71-§5 步 5 收口）：host_agent 面的生成经端口门禁 + 溯源。
        try:
            from ..execport.exec_port import begin_dispatch, end_dispatch

            _exec_ticket = begin_dispatch("host_agent", subject="%s/%s" % (host_module, host_purpose))
        except Exception:
            _exec_ticket = None
            end_dispatch = None
        text = port.complete(
            messages, json_mode=bool(profile.json_mode if json_mode_override is None else json_mode_override)
        )
        return ModelResponse(
            text=text,
            provider_id=provider.provider_id,
            model=profile.model,
            thinking_applied={"mode": "host_agent", "provider": "host_agent"},
            usage={},
            latency_ms=int((time.monotonic() - started) * 1000),
            request_id="",
            finish_reason="host_turn",
            json_mode_applied=False,
        )
        if _exec_ticket and end_dispatch:
            end_dispatch(_exec_ticket, "completed")

    def list_models(self, provider_id: str) -> List[str]:
        provider = self.store.provider(provider_id)
        if provider.kind in KEYLESS_PROVIDER_KINDS:
            return list(provider.models)
        key, _ = self.keys.resolve(provider)
        if not key:
            raise ModelConfigError(
                "provider %s has no API key; set %s or a session key"
                % (provider.provider_id, provider.api_key_env)
            )
        if provider.kind == "azure_openai":
            raise ModelConfigError("Azure OpenAI does not expose a model list; enter deployment names manually")
        data = self._request_json(
            "GET",
            self._url(provider, "/models"),
            self._headers(provider, key),
            None,
            provider.provider_id,
            key,
        )
        raw = data.get("data") if isinstance(data.get("data"), list) else data.get("models")
        if not isinstance(raw, list):
            return []
        models = []
        for item in raw:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict):
                model_id = item.get("id") or item.get("name") or item.get("model")
                if model_id:
                    models.append(str(model_id))
        return sorted(set(models))[:500]


class GatewayModelPort(ModelPort):
    """ModelPort adapter for FrozenModelProposer and other consumers."""

    def __init__(self, gateway: ModelGateway, profile_id: str):
        self.gateway = gateway
        self.profile_id = profile_id
        profile = gateway.store.profile(profile_id)
        self.model_id = "%s:%s" % (profile.provider_id, profile.model)
        self.provider_id = str(profile.provider_id)
        self.provider_kind = str(gateway.store.provider(profile.provider_id).kind)
        self.model_name = str(profile.model)

    def complete(self, messages: List[Dict[str, str]], json_mode: bool = True) -> str:
        return self.gateway.complete(
            self.profile_id, messages, json_mode_override=bool(json_mode)
        ).text

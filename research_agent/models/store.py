"""Non-secret configuration store and in-memory key store."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..storage import atomic_replace
from .types import (
    KEYLESS_PROVIDER_KINDS,
    KEYLESS_SENTINEL,
    MODULE_IDS,
    ModelConfigError,
    ModelProfile,
    ProviderConfig,
    ThinkingConfig,
    mask_secret,
)

SCHEMA_VERSION = "model-gateway-0.1"
SECRET_FIELDS = {"api_key", "apikey", "key", "secret", "token", "authorization"}


def default_store_path() -> Path:
    """One store for every entry point: env override first, then the repository default.

    GatewayStore(None) is intentionally ephemeral, so a binding made through a pathless
    store would report success and persist nothing.
    """
    from ..paths import DEFAULT_MODEL_STORE_PATH

    raw = os.environ.get("RESEARCH_AGENT_MODEL_STORE", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_MODEL_STORE_PATH


def _default_providers() -> List[ProviderConfig]:
    return [
        ProviderConfig(
            provider_id="host-agent",
            kind="host_agent",
            label="宿主 Agent（Qoder / Claude Code / Codex / Zcode）",
            models=["host-agent"],
        ),
        ProviderConfig(
            provider_id="openai",
            kind="openai",
            label="OpenAI",
            api_key_env="OPENAI_API_KEY",
        ),
        ProviderConfig(
            provider_id="zhipu",
            kind="openai_compatible",
            label="智谱 GLM（OpenAI 兼容）",
            base_url="https://open.bigmodel.cn/api/paas/v4",
            api_key_env="ZHIPU_API_KEY",
            models=["glm-5.3-flash", "glm-5.3", "glm-5.3-air"],
        ),
        ProviderConfig(
            provider_id="anthropic",
            kind="anthropic",
            label="Anthropic",
            api_key_env="ANTHROPIC_API_KEY",
        ),
        ProviderConfig(
            provider_id="deepseek",
            kind="openai_compatible",
            label="DeepSeek",
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
            models=["deepseek-chat"],
        ),
        ProviderConfig(
            provider_id="local-openai",
            kind="openai_compatible",
            label="本地 OpenAI 兼容网关",
            base_url="http://127.0.0.1:11434/v1",
            api_key_env="LOCAL_LLM_API_KEY",
            allow_private_network=True,
        ),
    ]


def _find_secret_fields(value: Any, path: str = "") -> List[str]:
    found: List[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SECRET_FIELDS:
                found.append(path + "." + str(key) if path else str(key))
            found.extend(_find_secret_fields(child, path + "." + str(key) if path else str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_secret_fields(child, "%s[%d]" % (path, index)))
    return found


class GatewayStore:
    """Persisted provider/profile/binding configuration without secrets."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self.providers: Dict[str, ProviderConfig] = {}
        self.profiles: Dict[str, ModelProfile] = {}
        self.bindings: Dict[str, str] = {}
        self.warning = ""
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            self._use_defaults()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema_version") != SCHEMA_VERSION:
                raise ModelConfigError("unsupported model gateway schema")
            secrets = _find_secret_fields(data)
            if secrets:
                raise ModelConfigError(
                    "model gateway config must not contain secrets: " + ", ".join(secrets)
                )
            providers = [ProviderConfig.from_dict(item) for item in data.get("providers", [])]
            profiles = [ModelProfile.from_dict(item) for item in data.get("profiles", [])]
            bindings = {str(key): str(value) for key, value in (data.get("bindings") or {}).items()}
            self.providers = {item.provider_id: item for item in providers}
            self.profiles = {item.profile_id: item for item in profiles}
            self.bindings = {key: value for key, value in bindings.items() if key in MODULE_IDS}
            for profile in self.profiles.values():
                if profile.provider_id not in self.providers:
                    raise ModelConfigError("profile references missing provider: " + profile.profile_id)
            for module, profile_id in self.bindings.items():
                if profile_id and profile_id not in self.profiles:
                    raise ModelConfigError("binding references missing profile: " + profile_id)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.warning = "model gateway config ignored: " + str(exc)
            self._use_defaults()

    def _use_defaults(self) -> None:
        self.providers = {item.provider_id: item for item in _default_providers()}
        # 默认画像与模块绑定：调研智能体（literature）规划器用 GLM-5.3-Flash；
        # 其余模块默认无模型（规则模板）。密钥永不落盘，只走 env / session。
        self.profiles = {}
        try:
            self.profiles["glm-flash"] = ModelProfile(
                profile_id="glm-flash",
                provider_id="zhipu",
                model="glm-5.3-flash",
                label="GLM-5.3-Flash · 调研规划器",
                thinking=ThinkingConfig(mode="off"),
                max_tokens=1024,
                context_window=128000,
                max_output_tokens=8192,
                temperature=0.2,
                json_mode=True,
            )
        except ModelConfigError:
            self.profiles = {}
        try:
            self.profiles["deepseek"] = ModelProfile(
                profile_id="deepseek",
                provider_id="deepseek",
                model="deepseek-chat",
                label="DeepSeek · 评审/写作",
                thinking=ThinkingConfig(mode="off"),
                max_tokens=2048,
                context_window=128000,
                max_output_tokens=8192,
                temperature=0.2,
                json_mode=True,
            )
        except ModelConfigError:
            pass
        self.bindings = {"literature": "glm-flash"} if "glm-flash" in self.profiles else {}

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        data = self.to_dict()
        secrets = _find_secret_fields(data)
        if secrets:
            raise ModelConfigError("refusing to persist secret fields")
        with open(str(tmp), "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        atomic_replace(tmp, self.path)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "providers": [item.to_dict() for item in sorted(self.providers.values(), key=lambda x: x.provider_id)],
            "profiles": [item.to_dict() for item in sorted(self.profiles.values(), key=lambda x: x.profile_id)],
            "bindings": dict(sorted(self.bindings.items())),
        }

    def provider(self, provider_id: str) -> ProviderConfig:
        try:
            return self.providers[provider_id]
        except KeyError:
            raise ModelConfigError("unknown provider: " + provider_id)

    def profile(self, profile_id: str) -> ModelProfile:
        try:
            return self.profiles[profile_id]
        except KeyError:
            raise ModelConfigError("unknown profile: " + profile_id)

    def upsert_provider(self, provider: ProviderConfig) -> ProviderConfig:
        existing = self.providers.get(provider.provider_id)
        if existing is not None and not provider.models:
            provider.models = list(existing.models)
        self.providers[provider.provider_id] = provider
        for profile in self.profiles.values():
            if profile.provider_id == provider.provider_id:
                profile.thinking.validate_for(provider.kind)
        self.save()
        return provider

    def update_models(self, provider_id: str, models: List[str]) -> ProviderConfig:
        provider = self.provider(provider_id)
        provider.models = sorted({str(item).strip() for item in models if str(item).strip()})[:500]
        self.save()
        return provider

    def upsert_profile(self, profile: ModelProfile) -> ModelProfile:
        provider = self.provider(profile.provider_id)
        profile.thinking.validate_for(provider.kind)
        if profile.thinking.mode == "budget" and provider.kind == "openai_compatible":
            keys = set(profile.extra_body)
            if not keys & {"thinking", "enable_thinking", "thinking_budget", "reasoning"}:
                raise ModelConfigError(
                    "custom provider budget thinking requires a provider-specific "
                    "extra_body field (thinking/enable_thinking/thinking_budget)"
                )
        self.profiles[profile.profile_id] = profile
        self.save()
        return profile

    def set_binding(self, module: str, profile_id: str) -> Dict[str, str]:
        if module not in MODULE_IDS:
            raise ModelConfigError("unknown module: " + module)
        if profile_id:
            self.profile(profile_id)
            self.bindings[module] = profile_id
        else:
            self.bindings.pop(module, None)
        self.save()
        return dict(self.bindings)


class SessionKeyStore:
    """Process-local keys; never written to disk or returned by the API."""

    def __init__(self):
        self._keys: Dict[str, str] = {}
        self._lock = threading.Lock()

    def set(self, provider_id: str, key: str) -> None:
        value = (key or "").strip()
        if not value:
            raise ModelConfigError("api_key must not be empty")
        if len(value) > 4096:
            raise ModelConfigError("api_key is too long")
        with self._lock:
            self._keys[provider_id] = value

    def clear(self, provider_id: str) -> None:
        with self._lock:
            self._keys.pop(provider_id, None)

    def get(self, provider_id: str) -> str:
        with self._lock:
            return self._keys.get(provider_id, "")

    def resolve(self, provider: ProviderConfig) -> Tuple[str, str]:
        if provider.kind in KEYLESS_PROVIDER_KINDS:
            return KEYLESS_SENTINEL, "not_required"
        session = self.get(provider.provider_id)
        if session:
            return session, "session"
        env_value = os.environ.get(provider.api_key_env, "").strip()
        if env_value:
            return env_value, "env:" + provider.api_key_env
        return "", "missing"

    def status(self, provider: ProviderConfig) -> Dict[str, Any]:
        if provider.kind in KEYLESS_PROVIDER_KINDS:
            return {
                "configured": True,
                "key_source": "not_required",
                "masked_key": "",
                "note": "host-agent profile: the calling agent supplies the model",
            }
        key, source = self.resolve(provider)
        return {
            "configured": bool(key),
            "key_source": source,
            "masked_key": mask_secret(key),
        }

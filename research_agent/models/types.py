"""Typed configuration and response objects for the local model gateway."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


PROVIDER_KINDS = ("openai", "openai_compatible", "azure_openai", "anthropic", "host_agent")
# host_agent providers never reach the network: they hand the turn to the calling agent.
KEYLESS_PROVIDER_KINDS = ("host_agent",)
# Sentinels keep every existing "provider has no key" gate honest without a network call.
KEYLESS_SENTINEL = "host-agent-no-key-required"
THINKING_MODES = ("off", "effort", "budget")
EFFORTS = ("minimal", "low", "medium", "high", "max")
MODULE_IDS = ("literature", "idea", "experiment", "paper", "judge", "rsi")
DEFAULT_ENV = {
    "openai": "OPENAI_API_KEY",
    "azure_openai": "AZURE_OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai_compatible": "OPENAI_COMPATIBLE_API_KEY",
    "host_agent": "RESEARCH_HOST_AGENT_LABEL",
}
DEFAULT_BASE_URL = {
    "openai": "https://api.openai.com/v1",
    "azure_openai": "",
    "anthropic": "https://api.anthropic.com/v1",
    "openai_compatible": "",
}
RESERVED_EXTRA_KEYS = ("model", "messages", "stream")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
_METADATA_HOSTS = {"metadata.google.internal", "metadata.azure.internal"}


class ModelConfigError(ValueError):
    """Configuration or key-source error; never contains the key value."""


class ModelRequiredError(RuntimeError):
    """Production required a model call but it was unavailable or invalid."""


class ModelTurnPending(ModelRequiredError):
    """A host-agent profile deferred the turn; the host must respond, then re-run.

    This is a suspension signal, not an availability failure. Callers must surface the
    turn id instead of degrading to a deterministic template.
    """

    def __init__(self, message: str, turn_id: str = "", messages_sha256: str = ""):
        super().__init__(message)
        self.turn_id = turn_id
        self.messages_sha256 = messages_sha256


class ModelCallError(RuntimeError):
    """Provider call failure with a sanitized message."""

    def __init__(
        self,
        message: str,
        status: int = 0,
        provider: str = "",
        request_id: str = "",
        retryable: bool = False,
    ):
        super().__init__(message)
        self.status = status
        self.provider = provider
        self.request_id = request_id
        self.retryable = retryable


def _is_loopback(host: str) -> bool:
    return host in ("localhost", "127.0.0.1", "::1")


def validate_base_url(url: str, allow_private_network: bool = False) -> str:
    """Reject cleartext public URLs and obvious metadata endpoints.

    Private-network endpoints are allowed only when explicitly enabled by the
    provider configuration. DNS rebinding remains a residual risk; the local
    runtime is not intended to be exposed to untrusted networks.
    """
    value = (url or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ModelConfigError("base_url must be an http(s) URL with a host")
    host = parsed.hostname.lower()
    if host in _METADATA_HOSTS:
        raise ModelConfigError("metadata endpoints are not allowed")
    if parsed.scheme == "http" and not _is_loopback(host):
        raise ModelConfigError(
            "cleartext http is only allowed for localhost/127.0.0.1; use https "
            "or explicitly run a local gateway"
        )
    if not allow_private_network and not _is_loopback(host):
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved
        ):
            raise ModelConfigError(
                "private-network base_url requires allow_private_network=true"
            )
    if parsed.username or parsed.password:
        raise ModelConfigError("base_url must not contain credentials")
    return value


def normalize_base_url(kind: str, url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if not value:
        value = DEFAULT_BASE_URL.get(kind, "")
    if kind in ("openai", "anthropic") and value:
        path = urlparse(value).path.rstrip("/")
        if path in ("", "/"):
            value = value + "/v1"
    return value.rstrip("/")


@dataclass
class ThinkingConfig:
    mode: str = "off"
    effort: str = "medium"
    budget_tokens: Optional[int] = None

    def __post_init__(self) -> None:
        if self.mode not in THINKING_MODES:
            raise ModelConfigError("thinking.mode must be one of %s" % (THINKING_MODES,))
        if self.effort not in EFFORTS:
            raise ModelConfigError("thinking.effort must be one of %s" % (EFFORTS,))
        if self.budget_tokens is not None:
            if isinstance(self.budget_tokens, bool) or not isinstance(self.budget_tokens, int):
                raise ModelConfigError("thinking.budget_tokens must be an integer")
            if not 1024 <= self.budget_tokens <= 32000:
                raise ModelConfigError("thinking.budget_tokens must be in 1024..32000")

    def validate_for(self, provider_kind: str) -> None:
        if self.mode == "budget":
            if provider_kind in ("openai", "azure_openai"):
                raise ModelConfigError(
                    "OpenAI/Azure use reasoning_effort, not token budget; "
                    "choose mode=effort or provide provider-specific extra_body"
                )
            if self.budget_tokens is None:
                raise ModelConfigError("mode=budget requires budget_tokens")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ThinkingConfig":
        raw = dict(data or {})
        return cls(
            mode=str(raw.get("mode", "off")),
            effort=str(raw.get("effort", "medium")),
            budget_tokens=raw.get("budget_tokens"),
        )


@dataclass
class ProviderConfig:
    provider_id: str
    kind: str
    label: str = ""
    base_url: str = ""
    api_key_env: str = ""
    api_version: str = ""
    allow_private_network: bool = False
    models: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not _ID_RE.match(self.provider_id or ""):
            raise ModelConfigError(
                "provider_id must be 1-40 chars of letters, digits, _ or -"
            )
        if self.kind not in PROVIDER_KINDS:
            raise ModelConfigError("kind must be one of %s" % (PROVIDER_KINDS,))
        self.label = (self.label or self.provider_id).strip()
        self.base_url = normalize_base_url(self.kind, self.base_url)
        self.api_key_env = (self.api_key_env or DEFAULT_ENV[self.kind]).strip()
        if not _ENV_RE.match(self.api_key_env):
            raise ModelConfigError("api_key_env must look like an environment variable")
        if self.kind in ("openai_compatible", "azure_openai") and not self.base_url:
            raise ModelConfigError("base_url is required for " + self.kind)
        if self.kind not in KEYLESS_PROVIDER_KINDS:
            self.base_url = validate_base_url(self.base_url, self.allow_private_network)
        else:
            self.base_url = ""
            self.allow_private_network = False
        self.models = sorted({str(item).strip() for item in self.models if str(item).strip()})

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderConfig":
        allowed = {
            "provider_id", "kind", "label", "base_url", "api_key_env",
            "api_version", "allow_private_network", "models",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ModelConfigError("unknown provider fields: " + ", ".join(sorted(unknown)))
        return cls(**{key: data[key] for key in allowed if key in data})


@dataclass
class ModelProfile:
    profile_id: str
    provider_id: str
    model: str
    label: str = ""
    thinking: ThinkingConfig = field(default_factory=ThinkingConfig)
    max_tokens: int = 2048
    context_window: int = 128000
    max_output_tokens: int = 16384
    thinking_supported: bool = True
    temperature: Optional[float] = 0.2
    top_p: Optional[float] = None
    json_mode: bool = False
    extra_body: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ID_RE.match(self.profile_id or ""):
            raise ModelConfigError(
                "profile_id must be 1-40 chars of letters, digits, _ or -"
            )
        if not _ID_RE.match(self.provider_id or ""):
            raise ModelConfigError("provider_id is invalid")
        if not (self.model or "").strip() or len(self.model) > 200:
            raise ModelConfigError("model must be a non-empty string up to 200 chars")
        self.model = self.model.strip()
        self.label = (self.label or self.model).strip()
        if isinstance(self.max_tokens, bool) or not isinstance(self.max_tokens, int):
            raise ModelConfigError("max_tokens must be an integer")
        if not 16 <= self.max_tokens <= 128000:
            raise ModelConfigError("max_tokens must be in 16..128000")
        if isinstance(self.context_window, bool) or not isinstance(self.context_window, int):
            raise ModelConfigError("context_window must be an integer")
        if not 8192 <= self.context_window <= 2000000:
            raise ModelConfigError("context_window must be in 8192..2000000")
        if isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int):
            raise ModelConfigError("max_output_tokens must be an integer")
        if not 16 <= self.max_output_tokens <= 1000000:
            raise ModelConfigError("max_output_tokens must be in 16..1000000")
        if self.max_output_tokens > self.context_window:
            raise ModelConfigError("max_output_tokens must not exceed context_window")
        if self.max_tokens > self.max_output_tokens:
            raise ModelConfigError("max_tokens must not exceed max_output_tokens")
        if not isinstance(self.thinking_supported, bool):
            raise ModelConfigError("thinking_supported must be boolean")
        if not self.thinking_supported and self.thinking.mode != "off":
            raise ModelConfigError(
                "profile declares no thinking support but thinking.mode is not off"
            )
        if self.temperature is not None:
            if not 0 <= float(self.temperature) <= 2:
                raise ModelConfigError("temperature must be in 0..2")
            self.temperature = float(self.temperature)
        if self.top_p is not None:
            if not 0 <= float(self.top_p) <= 1:
                raise ModelConfigError("top_p must be in 0..1")
            self.top_p = float(self.top_p)
        if not isinstance(self.extra_body, dict):
            raise ModelConfigError("extra_body must be an object")
        forbidden = set(self.extra_body) & set(RESERVED_EXTRA_KEYS)
        if forbidden:
            raise ModelConfigError(
                "extra_body may not override: " + ", ".join(sorted(forbidden))
            )
        self.thinking = (
            self.thinking if isinstance(self.thinking, ThinkingConfig)
            else ThinkingConfig.from_dict(self.thinking)
        )

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["thinking"] = self.thinking.to_dict()
        return value

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelProfile":
        allowed = {
            "profile_id", "provider_id", "model", "label", "thinking",
            "max_tokens", "context_window", "max_output_tokens", "thinking_supported",
            "temperature", "top_p", "json_mode", "extra_body",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ModelConfigError("unknown profile fields: " + ", ".join(sorted(unknown)))
        raw = {key: data[key] for key in allowed if key in data}
        if "thinking" in raw:
            raw["thinking"] = ThinkingConfig.from_dict(raw["thinking"])
        return cls(**raw)


@dataclass
class ModelResponse:
    text: str
    provider_id: str
    model: str
    thinking_applied: Dict[str, Any]
    usage: Dict[str, int]
    latency_ms: int
    request_id: str = ""
    finish_reason: str = ""
    json_mode_applied: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return value[:4] + "…" + value[-4:]


def redact_text(text: str, secret: str = "") -> str:
    value = str(text or "")
    if secret:
        value = value.replace(secret, "[redacted]")
    value = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-[redacted]", value)
    return value[:600]

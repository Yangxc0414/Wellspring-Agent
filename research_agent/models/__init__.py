"""Local model gateway: OpenAI, Anthropic and OpenAI-compatible providers.

Keys are never part of the persisted configuration. They come from an
environment variable or an in-memory session key managed by the local runtime.
"""

from .types import (
    KEYLESS_PROVIDER_KINDS,
    ModelCallError,
    ModelConfigError,
    ModelProfile,
    ModelRequiredError,
    ModelResponse,
    ModelTurnPending,
    ProviderConfig,
    ThinkingConfig,
)
from .store import GatewayStore, SessionKeyStore
from .gateway import GatewayModelPort, ModelGateway
from .service import ModelRegistryService

__all__ = [
    "GatewayModelPort",
    "GatewayStore",
    "KEYLESS_PROVIDER_KINDS",
    "ModelCallError",
    "ModelConfigError",
    "ModelGateway",
    "ModelProfile",
    "ModelRegistryService",
    "ModelRequiredError",
    "ModelResponse",
    "ModelTurnPending",
    "ProviderConfig",
    "SessionKeyStore",
    "ThinkingConfig",
]

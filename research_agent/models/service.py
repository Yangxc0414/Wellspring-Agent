"""Runtime-facing model registry service (no secret leaves this layer)."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .gateway import ModelGateway
from .store import GatewayStore, SessionKeyStore
from .types import MODULE_IDS, ModelConfigError, ModelProfile, ProviderConfig

WIRED = {
    "rsi": {
        "wired": True,
        "consumer": "CLI: python -m research_agent rsi propose-model --profile <id>",
        "note": "提案仍是不可信输入；必须走同一 public/hidden gate 与人签准入。",
    },
    "literature": {
        "wired": True,
        "consumer": "CLI/runtime：literature run / pipeline run --planner gateway → gateway_query_planner（默认 glm-flash）",
        "note": "只生成检索子查询；不得创建 Span/Claim；无 key 自动回退规则模板。",
    },
    "idea": {
        "wired": True,
        "consumer": "pipeline/task/runtime：S2–S3 可选 proposer（idea binding）；无 key 回退规则聚类",
        "note": "模型只能基于输入 span 提候选；引用必须解析，仍受 G1 与 novelty_unverified 约束。",
    },
    "experiment": {
        "wired": True,
        "consumer": "pipeline/task/runtime：S4 可选 designer（experiment binding）；无 key 回退确定性草稿",
        "note": "只补缺失字段；模型补全后仍为 needs_human，不得执行或冻结 protocol。",
    },
    "paper": {
        "wired": True,
        "consumer": "pipeline/runtime：非结果章节可选 writer（paper binding）；无 key 回退确定性草稿",
        "note": "模型不能写 Results；引用/数字通过校验才收，槽位与门禁仍由 claim/EA/Closure 控制。",
    },
    "judge": {
        "wired": True,
        "consumer": "pipeline/runtime：已签 claim 后可选 support judge（judge binding）；判定句子级证据支持",
        "note": "只产 advisory support audit；不创建/修改 Claim、gate、paper slot 或签名；无 key 的 test 模式明确标为 lexical heuristic。",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModelRegistryService:
    def __init__(
        self,
        store: GatewayStore,
        keys: Optional[SessionKeyStore] = None,
        gateway: Optional[ModelGateway] = None,
    ):
        self.store = store
        self.keys = keys or SessionKeyStore()
        self.gateway = gateway or ModelGateway(store, self.keys)
        self.gateway.on_call = self._record_call
        self._calls: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def snapshot(self) -> Dict[str, Any]:
        providers = []
        for provider in sorted(self.store.providers.values(), key=lambda item: item.provider_id):
            status = self.keys.status(provider)
            providers.append({
                **provider.to_dict(),
                "configured": status["configured"],
                "key_source": status["key_source"],
                "masked_key": status["masked_key"],
            })
        return {
            "schema_version": "model-gateway-view-0.1",
            "static": False,
            "api_connected": True,
            "store_warning": self.store.warning,
            "providers": providers,
            "profiles": [item.to_dict() for item in sorted(
                self.store.profiles.values(), key=lambda item: item.profile_id
            )],
            "bindings": dict(sorted(self.store.bindings.items())),
            "wired": {module: dict(WIRED.get(module, {"wired": False})) for module in MODULE_IDS},
            "readiness": self.readiness(),
            "security": {
                "keys_persisted": False,
                "key_sources": ["env", "session-memory"],
                "prompts_logged": False,
                "local_runtime_only": True,
            },
        }

    def readiness(self) -> Dict[str, Any]:
        required = ("literature", "idea", "experiment", "paper", "judge")
        modules: Dict[str, Any] = {}
        blocking: List[str] = []
        for module in required:
            info = WIRED.get(module, {})
            wired = bool(info.get("wired"))
            profile_id = self.store.bindings.get(module, "")
            profile = self.store.profiles.get(profile_id) if profile_id else None
            provider = self.store.providers.get(profile.provider_id) if profile else None
            key_configured = bool(provider and self.keys.status(provider)["configured"])
            if not wired:
                blocking.append("%s: model path is not wired (rule template only)" % module)
            elif not profile:
                blocking.append("%s: no model profile binding" % module)
            elif not key_configured:
                blocking.append("%s: provider %s has no key (%s)" % (
                    module, provider.provider_id, provider.api_key_env,
                ))
            modules[module] = {
                "wired": wired,
                "bound_profile": profile_id,
                "provider": provider.provider_id if provider else "",
                "key_configured": key_configured,
                "consumer": info.get("consumer", ""),
            }
        warnings: List[str] = []
        judge_profile = self.store.bindings.get("judge", "")
        shared_with = [
            module
            for module in ("literature", "idea", "experiment", "paper")
            if judge_profile and self.store.bindings.get(module, "") == judge_profile
        ]
        if shared_with:
            warnings.append(
                "judge shares profile '%s' with %s; support verdicts are less independent "
                "(same base model)" % (judge_profile, ", ".join(shared_with))
            )
        return {
            "required_modules": list(required),
            "modules": modules,
            "production_ready": not blocking,
            "blocking": blocking,
            "warnings": warnings,
            "boundary": "production requires every required module to be model-wired, bound and callable (provider key or a keyless host-agent profile); evidence gates remain deterministic",
        }

    def upsert_provider(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        raw = dict(payload)
        api_key = str(raw.pop("api_key", "") or "").strip()
        provider = ProviderConfig.from_dict(raw)
        self.store.upsert_provider(provider)
        if api_key:
            self.keys.set(provider.provider_id, api_key)
        return self.snapshot()

    def set_key(self, provider_id: str, api_key: str) -> Dict[str, Any]:
        self.store.provider(provider_id)
        self.keys.set(provider_id, api_key)
        return self.snapshot()

    def clear_key(self, provider_id: str) -> Dict[str, Any]:
        self.store.provider(provider_id)
        self.keys.clear(provider_id)
        return self.snapshot()

    def refresh_models(self, provider_id: str) -> Dict[str, Any]:
        models = self.gateway.list_models(provider_id)
        self.store.update_models(provider_id, models)
        return {"provider_id": provider_id, "models": models, "snapshot": self.snapshot()}

    def upsert_profile(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        profile = ModelProfile.from_dict(payload)
        self.store.upsert_profile(profile)
        return self.snapshot()

    def set_binding(self, module: str, profile_id: str) -> Dict[str, Any]:
        self.store.set_binding(module, profile_id)
        return self.snapshot()

    def probe(
        self,
        profile_id: str,
        prompt: str,
        system: str = "",
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not (prompt or "").strip():
            raise ModelConfigError("prompt must not be empty")
        messages = []
        if (system or "").strip():
            messages.append({"role": "system", "content": system.strip()})
        messages.append({"role": "user", "content": prompt.strip()})
        response = self.gateway.complete(
            profile_id, messages, max_tokens_override=max_tokens
        )
        return {
            "response": response.to_dict(),
            "call": self._calls[-1] if self._calls else {},
        }

    def _record_call(self, profile_id: str, response: Any, ok: bool, error: str = "") -> None:
        profile = self.store.profiles.get(profile_id)
        entry = {
            "at": _now(),
            "profile_id": profile_id,
            "provider_id": profile.provider_id if profile else "",
            "model": profile.model if profile else "",
            "thinking": profile.thinking.to_dict() if profile else {},
            "ok": ok,
            "latency_ms": response.latency_ms if response else 0,
            "usage": response.usage if response else {},
            "request_id": response.request_id if response else "",
            "error": error,
        }
        with self._lock:
            self._calls.append(entry)
            del self._calls[:-100]

    def calls(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in reversed(self._calls)]

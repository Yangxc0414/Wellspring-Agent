"""Optional model-backed prose writer for non-result paper sections.

The writer is an accelerator, not an evidence source. It receives only
selected span text and explicit rules, returns section prose, and is rejected
when it invents citations or numbers. Results, method commitments, claims,
gates and export remain deterministic and human-controlled.
"""

import json
import re
from typing import Any, Callable, Dict, Optional, Tuple

WRITER_SYSTEM = (
    "你是科研论文的写作助手，只能根据给定的证据片段写非结果章节。"
    "禁止编造来源、引用、数字、claim 或实验结论；禁止写 Results 或任何指标数值。"
    "引用只能使用给定 allowed_evidence 中的 ref，格式为 [ref]。"
    "避免未经证据支持的“首次/突破/显著/最优”等断言，避免“值得注意的是/综上所述”等套话。"
    "若 payload 提供 journal_style，遵循其中的目标期刊规范，但不得为此编造内容。"
    "中文摘要使用“目的/方法/结果/结论”四段式；摘要的结果只能复述已给出的 claim 结论，不能新增数值。"
    "只返回 JSON 对象，键必须是 sections 中给出的 key；值为段落文本，不要 Markdown 标题。"
)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def gateway_paper_writer(
    profile_id: Optional[str] = None,
    store_path=None,
    gateway=None,
    strict: bool = False,
) -> Tuple[Optional[Callable[[Dict[str, Any]], Optional[Dict[str, str]]]], str]:
    """Resolve the optional paper writer through the local gateway.

    Missing binding, missing provider key, or an unreadable store degrades to
    ``(None, note)``. A configured profile gives ``(writer, note)``; model or
    JSON failures inside ``writer`` return ``None`` so PaperAgent keeps the
    deterministic draft.
    """
    try:
        from ..models import KEYLESS_PROVIDER_KINDS, GatewayStore, ModelGateway

        if gateway is None:
            store = GatewayStore(store_path) if store_path else GatewayStore()
            gateway = ModelGateway(store)
        store = gateway.store
        profile = profile_id or store.bindings.get("paper", "")
        if not profile or profile not in store.profiles:
            note = "paper writer: no paper binding; using deterministic draft"
            if strict:
                from ..models import ModelRequiredError

                raise ModelRequiredError(note)
            return None, note
        provider = store.profiles[profile].provider_id
        provider_config = store.provider(provider)
        host_agent = provider_config.kind in KEYLESS_PROVIDER_KINDS
        key, _source = gateway.keys.resolve(provider_config)
        if not key:
            note = (
                "paper writer: provider %s key not set (%s); using deterministic draft"
                % (provider, provider_config.api_key_env)
            )
            if strict:
                from ..models import ModelRequiredError

                raise ModelRequiredError(note)
            return None, note

        def write(payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
            from ..models import ModelRequiredError, ModelTurnPending

            body = json.dumps(payload, ensure_ascii=False, indent=2)
            try:
                response = gateway.complete(
                    profile,
                    [
                        {"role": "system", "content": WRITER_SYSTEM},
                        {"role": "user", "content": body},
                    ],
                    json_mode_override=True,
                    host_module="paper",
                    host_purpose="S8 non-result sections",
                )
            except ModelTurnPending:
                # Deferred host turn: surface it with its turn id, never keep a silent draft.
                raise
            except Exception as exc:
                if strict:
                    raise ModelRequiredError(
                        "paper writer model failed: %s" % type(exc).__name__
                    )
                return None
            match = _JSON_OBJECT_RE.search(response.text)
            if not match:
                if strict:
                    raise ModelRequiredError("paper writer returned no JSON object")
                return None
            try:
                value = json.loads(match.group(0))
            except ValueError:
                if strict:
                    raise ModelRequiredError("paper writer returned invalid JSON")
                return None
            if not isinstance(value, dict):
                if strict:
                    raise ModelRequiredError("paper writer returned a non-object")
                return None
            return {str(key): str(item) for key, item in value.items() if isinstance(item, str)}

        return write, "paper writer: %s profile %s (%s)" % (
            "host-agent" if host_agent else "gateway",
            profile,
            store.profiles[profile].model,
        )
    except Exception as exc:
        from ..models import ModelRequiredError

        if isinstance(exc, ModelRequiredError):
            raise
        if strict:
            raise ModelRequiredError(
                "paper writer unavailable: %s" % type(exc).__name__
            )
        return None, "paper writer unavailable (%s); using deterministic draft" % type(exc).__name__

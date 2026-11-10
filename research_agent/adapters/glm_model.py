"""GLM (Zhipu) chat adapter + literature query planner.

The survey agent's designated model is GLM-5.3-Flash (registered in
modules/literature/SPEC.md v0.2.0). The endpoint is OpenAI-compatible:

- key: env ``ZHIPU_API_KEY`` or ``GLM_API_KEY`` (server-side only, never
  committed); ``GLM_MODEL`` (default ``glm-5.3-flash``) and
  ``GLM_BASE_URL`` (default ``https://open.bigmodel.cn/api/paas/v4``)
  can be overridden;
- bounded retries with backoff, 60s timeout, explicit error on exhaustion;
- ``glm_query_planner`` turns a research question into 4-6 subqueries and
  is the ONLY wiring into the research pipeline: the model output is a
  list of search strings, never evidence, never a claim. Any failure
  returns None so LiteratureAgent falls back to its rule template.

A ``transport`` callable can be injected for offline tests.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-5.3-flash"


class ModelConfigError(RuntimeError):
    pass


def _default_transport(request: urllib.request.Request) -> bytes:
    with urllib.request.urlopen(request, timeout=request.timeout) as response:
        return response.read()


class GLMModel:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 60,
        max_retries: int = 2,
        transport: Optional[Callable[[urllib.request.Request], bytes]] = None,
    ):
        if not api_key:
            raise ModelConfigError("GLM API key is required (set ZHIPU_API_KEY or GLM_API_KEY)")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.model_id = model
        self._transport = transport or _default_transport

    @classmethod
    def from_env(cls, transport=None) -> "GLMModel":
        key = (os.environ.get("ZHIPU_API_KEY") or os.environ.get("GLM_API_KEY") or "").strip()
        if not key:
            raise ModelConfigError("ZHIPU_API_KEY / GLM_API_KEY is not set")
        return cls(
            api_key=key,
            model=os.environ.get("GLM_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("GLM_BASE_URL", DEFAULT_BASE_URL),
            transport=transport,
        )

    def complete(self, messages, json_mode: bool = True) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
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
            request.timeout = self.timeout
            try:
                data = json.loads(self._transport(request).decode("utf-8"))
                choices = data.get("choices") or []
                content = choices[0].get("message", {}).get("content") if choices else None
                if not content:
                    raise RuntimeError("glm returned no message content")
                return str(content)
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, RuntimeError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                break
        raise RuntimeError("GLM call failed: %s" % type(last_error).__name__)


PLANNER_SYSTEM = (
    "你是科研文献检索规划器。给定一个研究问题，产出 4-6 条互补的检索子查询："
    "覆盖综述视角、方法视角与中英双语（按问题语言决定主语言）。"
    '只返回 JSON：{"subqueries": ["...", "..."]}，不要输出其它内容。'
)

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def glm_query_planner(model, strict: bool = False) -> Callable[[str], Optional[List[str]]]:
    """Build a LiteratureAgent query planner over ANY ModelPort-like object.

    Works with ``GLMModel`` (direct env key) or ``GatewayModelPort`` (any
    configured gateway provider: OpenAI / Anthropic / GLM / custom). Returns
    a function question -> Optional[list[str]]; None on any failure so the
    caller falls back to the rule template instead of failing the run.
    """

    def plan(question: str) -> Optional[List[str]]:
        text = (question or "").strip()
        if not text:
            return None
        try:
            raw = model.complete(
                [
                    {"role": "system", "content": PLANNER_SYSTEM},
                    {"role": "user", "content": "研究问题：" + text},
                ],
                json_mode=True,
            )
            match = _JSON_OBJECT_RE.search(raw)
            if not match:
                return None
            data = json.loads(match.group(0))
            queries = data.get("subqueries")
            if not isinstance(queries, list):
                return None
            cleaned: List[str] = []
            seen = set()
            for item in queries:
                query = str(item).strip()
                if not query or len(query) > 160 or query.lower() in seen:
                    continue
                seen.add(query.lower())
                cleaned.append(query)
            if not cleaned:
                return None
            return cleaned[:6]
        except Exception as exc:
            if strict:
                from ..models import ModelRequiredError

                raise ModelRequiredError(
                    "query planner model failed: %s" % type(exc).__name__
                )
            return None

    return plan


def gateway_query_planner(
    profile_id: Optional[str] = None,
    store_path=None,
    gateway=None,
    strict: bool = False,
):
    """Resolve a planner through the local model gateway.

    ``profile_id`` defaults to the module binding for ``literature``
    (default profile ``glm-flash`` -> zhipu/glm-5.3-flash). Any configured
    OpenAI / Anthropic / OpenAI-compatible profile works. Returns
    ``(planner_or_None, note)``; missing key or missing profile degrade to
    ``(None, note)`` instead of raising, so runs never hard-fail on models.
    """
    from ..models import GatewayStore, ModelGateway, ModelConfigError as GWConfigError

    try:
        if gateway is None:
            store = GatewayStore(store_path) if store_path else GatewayStore()
            gateway = ModelGateway(store)
        store = gateway.store
        profile = profile_id or store.bindings.get("literature", "")
        if not profile or profile not in store.profiles:
            note = "gateway has no literature binding; using rule-based queries"
            if strict:
                from ..models import ModelRequiredError

                raise ModelRequiredError(note)
            return None, note
        provider = store.profiles[profile].provider_id
        provider_config = store.provider(provider)
        key, _source = gateway.keys.resolve(provider_config)
        if not key:
            note = (
                "provider %s key not set (%s); using rule-based queries"
                % (provider, provider_config.api_key_env)
            )
            if strict:
                from ..models import ModelRequiredError

                raise ModelRequiredError(note)
            return None, note
        port = _GatewayPortShim(gateway, profile)
        return glm_query_planner(port, strict=strict), "query planner: gateway profile %s (%s)" % (
            profile, port.model_id,
        )
    except GWConfigError as error:
        if strict:
            from ..models import ModelRequiredError

            raise ModelRequiredError("gateway planner unavailable: %s" % error)
        return None, "gateway planner unavailable (%s); using rule-based queries" % error


class _GatewayPortShim:
    """Minimal ModelPort façade over ModelGateway.complete for the planner."""

    def __init__(self, gateway, profile_id: str):
        profile = gateway.store.profile(profile_id)
        self.model_id = "%s:%s" % (profile.provider_id, profile.model)
        self._gateway = gateway
        self._profile = profile_id

    def complete(self, messages, json_mode: bool = True) -> str:
        return self._gateway.complete(
            self._profile, messages, json_mode_override=bool(json_mode)
        ).text

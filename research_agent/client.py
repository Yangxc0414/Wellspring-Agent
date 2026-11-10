"""Small framework-agnostic HTTP client for other agent runtimes."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .framework_api import ResearchAgentAPI, ResearchAgentAPIError

DEFAULT_BASE_URL = "http://127.0.0.1:8787"


class ResearchAgentClientError(RuntimeError):
    pass


class ResearchAgentClient:
    """HTTP JSON client usable from LangGraph, CrewAI, AutoGen, n8n, etc."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        token: Optional[str] = None,
        timeout: int = 120,
    ):
        self.base_url = str(base_url or DEFAULT_BASE_URL).rstrip("/")
        self.token = token if token is not None else os.environ.get("RESEARCH_AGENT_API_TOKEN", "")
        self.timeout = max(5, min(int(timeout), 600))

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        return headers

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=self._headers(),
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ResearchAgentClientError("HTTP %d: %s" % (exc.code, detail[:500]))
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ResearchAgentClientError("research agent request failed: %s" % exc)

    def capabilities(self) -> Dict[str, Any]:
        return self._request("GET", "/api/research/capabilities")

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/api/research/health")

    def openai_tools(self) -> List[Dict[str, Any]]:
        return list(self.capabilities().get("openai_tools") or [])

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(arguments, dict):
            raise ResearchAgentClientError("tool arguments must be an object")
        payload = self._request("POST", "/api/research/tools/" + str(name), arguments)
        return payload.get("result") or {}

    def init_project(self, project_dir: str, name: str = "") -> Dict[str, Any]:
        return self.call_tool("research_project_init", {"project_dir": project_dir, "name": name})

    def plan(self, **kwargs: Any) -> Dict[str, Any]:
        return self.call_tool("research_plan", kwargs)

    def run(self, **kwargs: Any) -> Dict[str, Any]:
        return self.call_tool("research_run", kwargs)

    def status(self, project_dir: str, limit: int = 20) -> Dict[str, Any]:
        return self.call_tool("research_status", {"project_dir": project_dir, "limit": limit})

    def revise(self, **kwargs: Any) -> Dict[str, Any]:
        return self.call_tool("research_manuscript_revise", kwargs)


class LocalResearchAgent:
    """In-process client for Python frameworks without an HTTP hop."""

    def __init__(self, root: Path):
        self.api = ResearchAgentAPI(root)

    def capabilities(self) -> Dict[str, Any]:
        return self.api.capabilities()

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return self.api.call_tool(name, arguments)["result"]


__all__ = [
    "DEFAULT_BASE_URL",
    "LocalResearchAgent",
    "ResearchAgentAPIError",
    "ResearchAgentClient",
    "ResearchAgentClientError",
]

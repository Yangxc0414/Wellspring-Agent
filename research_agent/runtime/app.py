"""Localhost FastAPI surface for the research runtime.

The runtime executes the same PipelineRunner used by the CLI. It is read-only
for RSI: status/trace can be inspected, but admission, claims and signatures
must stay in the CLI/human workflow until identity and audit storage exist.
"""

import hmac
import json
import os
from asyncio import sleep
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..models import (
    GatewayStore,
    ModelCallError,
    ModelConfigError,
    ModelRegistryService,
)
from ..actions import ActionError, automation_plan, run_skill
from ..custom_agents import CustomAgentError, CustomAgentStore
from ..evolution_policy import EvolutionPolicyError, EvolutionPolicyStore
from ..framework_api import ResearchAgentAPI, ResearchAgentAPIError
from ..literature_memory import LiteratureMemoryError, LiteratureMemoryStore
from ..orchestrator import OrchestrationError, collaboration_plan, topology_snapshot
from ..project import ProjectError, list_project_experiments, list_projects
from ..rsi import RSIController, StepLedger, ledger_story, trace_research
from ..skill_registry import SkillError, SkillRegistryStore, manifest_from_payload
from ..skill_lab import SkillUsageStore, SkillVersionStore
from ..signers import SignerStore
from ..workspace import (
    AgentRegistry,
    ArchiveStore,
    CommandRegistry,
    MemoryStore,
    WorkspaceStoreError,
)
from .jobs import (
    ArtifactPathError,
    JobManager,
    QueueLimitError,
    RuntimeSettings,
    default_settings,
    is_relative_to,
)


LOOPBACK_CLIENTS = ("127.0.0.1", "localhost", "::1", "testclient")
MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")
WRITE_GUARD_BOUNDARY = (
    "every mutating route on this runtime needs the same credential as the research API: a "
    "Bearer token when RESEARCH_AGENT_API_TOKEN is set, otherwise a loopback client. Reads stay "
    "open because the localhost UI polls them. No route here can sign, approve, freeze, publish "
    "or export, and the generic tool dispatcher only reaches the MCP tool list"
)


def credential_problem(
    client_host: str, token: str, authorization: str
) -> Optional[Tuple[int, str]]:
    """Return ``(status, detail)`` when the caller must be refused, else ``None``.

    Pure so the rule can be tested without a socket, and so the middleware and the per-route
    research guard cannot drift apart. It replaces a guard that was applied by hand in 4 of 59
    routes, which left the most sensitive writes (model keys, model bindings, host-model
    answers) unauthenticated on a non-loopback bind.
    """
    expected = str(token or "").strip()
    if expected:
        if not hmac.compare_digest(str(authorization or ""), "Bearer " + expected):
            return 401, "invalid research API token"
        return None
    if str(client_host or "") not in LOOPBACK_CLIENTS:
        return (
            403,
            "research API is loopback-only; set RESEARCH_AGENT_API_TOKEN for remote access",
        )
    return None


def remote_bind_problem(host: str, allow_remote: bool, token: str) -> str:
    """Return a refusal reason for a runtime bind, or ``""`` when it is acceptable."""
    if str(host or "") in ("127.0.0.1", "localhost", "::1"):
        return ""
    if not allow_remote:
        return "refusing non-loopback bind without --allow-remote"
    if not str(token or "").strip():
        return (
            "refusing --allow-remote without RESEARCH_AGENT_API_TOKEN: off-loopback every "
            "mutating route would be reachable with no credential, and those routes write model "
            "keys, model bindings and host-model answers"
        )
    return ""


class RunCreate(BaseModel):
    topic: str = Field(min_length=2, max_length=500)
    task_type: Literal[
        "", "auto", "literature_review", "hypothesis_design",
        "experiment_validation", "full_research"
    ] = ""
    deliverable: str = Field(default="", max_length=80)
    language: Literal["", "zh", "en"] = ""
    venue_type: Literal[
        "zh_core_journal", "en_conference", "en_journal", "zh_thesis"
    ] = "zh_core_journal"
    grant_scheme: Literal["", "nsfc", "nssfc", "generic"] = ""
    figure_style: Literal["comic", "roman", "modern"] = "modern"
    max_sources: int = Field(default=6, ge=1, le=12)
    real_corpus: bool = False
    local_corpus: bool = False
    openalex: bool = False
    mailto: str = Field(default="", max_length=120)
    planner: str = Field(default="gateway", max_length=60)
    run_dataset: Literal["", "iris", "breast_cancer", "chemlab"] = ""
    run_seeds: int = Field(default=3, ge=1, le=10)
    flow_mode: Literal["", "review", "strict"] = ""
    g1_decision_file: str = Field(default="", max_length=1000)
    protocol_file: str = Field(default="", max_length=1000)
    claim_file: str = Field(default="", max_length=1000)
    bibliography_file: str = Field(default="", max_length=1000)
    run_dir: str = Field(default="", max_length=1000)


class ProviderPayload(BaseModel):
    provider_id: str = Field(min_length=1, max_length=40)
    kind: Literal["openai", "openai_compatible", "azure_openai", "anthropic"]
    label: str = Field(default="", max_length=80)
    base_url: str = Field(default="", max_length=500)
    api_key_env: str = Field(default="", max_length=80)
    api_version: str = Field(default="", max_length=40)
    allow_private_network: bool = False
    models: List[str] = Field(default_factory=list)
    api_key: str = Field(default="", max_length=4096)


class KeyPayload(BaseModel):
    api_key: str = Field(min_length=1, max_length=4096)


class ThinkingPayload(BaseModel):
    mode: Literal["off", "effort", "budget"] = "off"
    effort: Literal["minimal", "low", "medium", "high"] = "medium"
    budget_tokens: Optional[int] = Field(default=None, ge=1024, le=32000)


class ProfilePayload(BaseModel):
    profile_id: str = Field(min_length=1, max_length=40)
    provider_id: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=120)
    thinking: ThinkingPayload = Field(default_factory=ThinkingPayload)
    max_tokens: int = Field(default=2048, ge=16, le=128000)
    context_window: int = Field(default=128000, ge=8192, le=2000000)
    max_output_tokens: int = Field(default=16384, ge=16, le=1000000)
    thinking_supported: bool = True
    temperature: Optional[float] = Field(default=0.2, ge=0, le=2)
    top_p: Optional[float] = Field(default=None, ge=0, le=1)
    json_mode: bool = False
    extra_body: Dict[str, Any] = Field(default_factory=dict)


class BindingPayload(BaseModel):
    module: str = Field(min_length=1, max_length=40)
    profile_id: str = Field(default="", max_length=40)


class HostModelRespondPayload(BaseModel):
    turn_id: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=200000)
    host_label: str = Field(default="", max_length=80)


class HostModelVoidPayload(BaseModel):
    turn_id: str = Field(min_length=1, max_length=60)
    reason: str = Field(min_length=1, max_length=400)


class ProbePayload(BaseModel):
    profile_id: str = Field(min_length=1, max_length=40)
    prompt: str = Field(min_length=1, max_length=20000)
    system: str = Field(default="", max_length=20000)
    max_tokens: Optional[int] = Field(default=None, ge=16, le=4096)


class MemoryCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    kind: Literal["decision", "preference", "constraint", "note"] = "note"
    scope: str = Field(default="workspace", min_length=1, max_length=120)
    source: str = Field(default="user", min_length=1, max_length=120)


class ArchiveCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    task_id: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)
    payload: Dict[str, Any]


class AutomationPlanAction(BaseModel):
    topic: str = Field(min_length=2, max_length=500)
    max_sources: int = Field(default=6, ge=1, le=50)
    run_dataset: Literal["", "iris", "breast_cancer", "chemlab"] = ""
    run_seeds: int = Field(default=3, ge=1, le=10)


class SkillAction(BaseModel):
    skill_id: Literal[
        "literature-brief", "hypothesis-triage", "protocol-review", "evidence-boundary"
    ]
    payload: Dict[str, Any] = Field(default_factory=dict)


class SkillRunPayload(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    task_id: str = Field(default="", max_length=120)


class CustomAgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    role: Literal["reviewer", "auditor", "scout", "methodologist", "writer-assistant"]
    purpose: str = Field(min_length=4, max_length=400)
    checks: List[str] = Field(min_length=1, max_length=7)
    enabled: bool = True


class CustomAgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=60)
    purpose: Optional[str] = Field(default=None, min_length=4, max_length=400)
    checks: Optional[List[str]] = Field(default=None, min_length=1, max_length=7)
    enabled: Optional[bool] = None


class EvolutionPolicyUpdate(BaseModel):
    enabled: Optional[bool] = None
    scopes: Dict[str, bool] = Field(default_factory=dict)


class SkillManifestPayload(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400)
    instructions: str = Field(min_length=1, max_length=8000)
    tools: List[str] = Field(default_factory=list, max_length=20)
    version: str = Field(default="0.1.0", max_length=40)
    license: str = Field(default="", max_length=80)
    origin: str = Field(default="", max_length=500)
    source: Literal["imported", "custom"] = "imported"
    enabled: bool = False


class SkillImportPayload(BaseModel):
    skills: List[SkillManifestPayload] = Field(min_length=1, max_length=50)


class SkillTogglePayload(BaseModel):
    enabled: bool


def _relative(path: Optional[Path], root: Path) -> Optional[str]:
    if path is None:
        return None
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()


def create_app(settings: Optional[RuntimeSettings] = None) -> FastAPI:
    settings = settings or default_settings()
    model_store_path = settings.model_store_path or (settings.jobs_root.parent / "model_gateway.json")
    model_service = ModelRegistryService(GatewayStore(Path(model_store_path)))
    from ..evolution_active import ActivePolicyStore
    from ..evolution_observations import EvolutionObservationStore

    evolution_observations = EvolutionObservationStore(
        settings.evolution_observations_path
        or (settings.jobs_root.parent / "evolution_observations.json")
    )
    evolution_active = ActivePolicyStore(
        settings.evolution_active_path
        or (settings.jobs_root.parent / "evolution_active.json")
    )
    manager = JobManager(
        settings,
        model_gateway=model_service.gateway,
        observation_store=evolution_observations,
        active_policy_store=evolution_active,
    )
    memory_path = settings.workspace_memory_path or (settings.jobs_root.parent / "workspace_memory.json")
    archive_root = settings.workspace_archive_root or (settings.jobs_root.parent / "workspace_archive")
    memory_store = MemoryStore(Path(memory_path))
    archive_store = ArchiveStore(Path(archive_root))
    literature_memory_path = settings.literature_memory_path or (
        settings.jobs_root.parent / "literature_memory.json"
    )
    literature_memory = LiteratureMemoryStore(Path(literature_memory_path))
    custom_agents_path = settings.custom_agents_path or (
        settings.jobs_root.parent / "custom_agents.json"
    )
    custom_agents = CustomAgentStore(Path(custom_agents_path))
    evolution_policy_path = settings.evolution_policy_path or (
        settings.jobs_root.parent / "evolution_policy.json"
    )
    evolution_policy = EvolutionPolicyStore(Path(evolution_policy_path))
    skill_registry_path = settings.skill_registry_path or (
        settings.jobs_root.parent / "skills.json"
    )
    skill_registry = SkillRegistryStore(Path(skill_registry_path))
    skill_usage_path = settings.skill_usage_path or (settings.jobs_root.parent / "skill_usage.json")
    skill_usage = SkillUsageStore(Path(skill_usage_path))
    skill_versions_path = settings.skill_versions_path or (settings.jobs_root.parent / "skill_versions.json")
    skill_versions = SkillVersionStore(Path(skill_versions_path))
    signer_store_path = settings.signer_store_path or (settings.jobs_root.parent / "signers.json")
    signers = SignerStore(Path(signer_store_path))
    agent_registry = AgentRegistry()
    command_registry = CommandRegistry()

    bridged_env: Dict[str, Optional[str]] = {}

    def _bridge_env(key: str, value: Optional[object]) -> None:
        if value and key not in os.environ:
            bridged_env[key] = None
            os.environ[key] = str(value)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            manager.shutdown()
            for key in bridged_env:
                os.environ.pop(key, None)

    app = FastAPI(
        title="Research Agent Local Runtime",
        version="0.1.0",
        description="Localhost-only pipeline + read-only RSI audit surface.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.manager = manager
    app.state.model_service = model_service
    app.state.memory_store = memory_store
    app.state.archive_store = archive_store
    app.state.literature_memory = literature_memory
    app.state.custom_agents = custom_agents
    app.state.evolution_policy = evolution_policy
    app.state.evolution_observations = evolution_observations
    app.state.evolution_active = evolution_active
    app.state.skill_registry = skill_registry
    app.state.skill_usage = skill_usage
    app.state.skill_versions = skill_versions
    app.state.signers = signers
    # The shared MCP/framework tool layer reads these env paths on every call.
    _bridge_env("RESEARCH_AGENT_MODE", settings.research_mode)
    _bridge_env("RESEARCH_AGENT_MODEL_STORE", settings.model_store_path)
    _bridge_env("RESEARCH_AGENT_SKILL_REGISTRY", settings.skill_registry_path)
    _bridge_env("RESEARCH_AGENT_SKILL_USAGE", settings.skill_usage_path)
    research_api = ResearchAgentAPI(Path(settings.research_api_root or settings.repo_root))
    app.state.research_api = research_api

    def _require_research_api(request: Request) -> None:
        problem = credential_problem(
            request.client.host if request.client else "",
            settings.research_api_token,
            request.headers.get("authorization", ""),
        )
        if problem:
            raise HTTPException(status_code=problem[0], detail=problem[1])

    @app.middleware("http")
    async def guard_mutating_routes(request: Request, call_next):
        # Default-deny, so a route added later is guarded without anyone remembering to guard
        # it. An HTTPException raised here would escape the exception middleware (user
        # middleware sits outside it), so the refusal is returned as a response instead.
        if request.method in MUTATING_METHODS:
            problem = credential_problem(
                request.client.host if request.client else "",
                settings.research_api_token,
                request.headers.get("authorization", ""),
            )
            if problem:
                return JSONResponse(
                    status_code=problem[0],
                    content={
                        "detail": problem[1],
                        "method": request.method,
                        "route": request.url.path,
                        "boundary": WRITE_GUARD_BOUNDARY,
                    },
                )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (
            "<h1>Research Agent Local Runtime</h1>"
            "<p>Localhost-only. <a href='/docs'>OpenAPI docs</a> · "
            "<a href='/api/health'>health</a></p>"
        )

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        pending = sum(
            1 for job in manager.list(limit=200)
            if job["status"] not in ("completed", "failed")
        )
        readiness = model_service.readiness()
        return {
            "status": "ok",
            "service": "research-agent-runtime",
            "mode": "local",
            "research_mode": settings.research_mode,
            "production_ready": readiness["production_ready"],
            "model_readiness": readiness,
            "version": app.version,
            "human_sign": False,
            "rsi_read_only": True,
            "queue": {"pending": pending, "max_pending": settings.max_pending},
            "real_corpus": bool(
                settings.real_corpus_path and Path(settings.real_corpus_path).is_file()
            ),
            "local_corpus": bool(
                settings.local_corpus_dir and Path(settings.local_corpus_dir).is_dir()
            ),
            "default_rsi_ledger": _relative(settings.default_rsi_ledger, settings.repo_root),
            "model_gateway": True,
            "model_store": _relative(model_store_path, settings.repo_root),
            "cors_origins": list(settings.allowed_origins),
        }

    @app.get("/api/research/capabilities")
    def research_capabilities(request: Request) -> Dict[str, Any]:
        _require_research_api(request)
        return research_api.capabilities()

    @app.get("/api/research/health")
    def research_health(request: Request) -> Dict[str, Any]:
        _require_research_api(request)
        return research_api.health()

    @app.get("/api/research/preflight")
    def research_preflight(request: Request) -> Dict[str, Any]:
        """Which link of the spec/export/tool chain is stale, plus the three tool surfaces."""
        _require_research_api(request)
        from ..preflight import build_preflight
        from ..mcp_server import TOOL_NAMES
        from ..workspace import CommandRegistry

        report = build_preflight(
            http_tools=len((research_api.capabilities() or {}).get("tools") or [])
        )
        report["boundary"] += (
            "; the web app reads this to show governance state and cannot run any command "
            "through it"
        )
        return report

    def _project_path(raw: str) -> Path:
        value = str(raw or "").strip()
        if not value or Path(value).is_absolute() or ".." in Path(value).parts:
            raise HTTPException(
                status_code=400, detail="project_dir must be a relative project path"
            )
        root = Path(settings.repo_root).resolve()
        candidate = (root / value).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=403, detail="project_dir is outside the repository")
        if not (candidate / "project.json").is_file():
            raise HTTPException(status_code=404, detail="research project not found")
        return candidate

    @app.get("/api/projects")
    def project_inventory() -> Dict[str, Any]:
        try:
            return list_projects(str(settings.repo_root))
        except (ProjectError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/project-experiments")
    def project_experiment_inventory(
        project_dir: str = Query(..., min_length=1, max_length=500)
    ) -> Dict[str, Any]:
        target = _project_path(project_dir)
        try:
            return list_project_experiments(target)
        except (ProjectError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/project-closures")
    def project_closure_inventory(
        project_dir: str = Query(..., min_length=1, max_length=500)
    ) -> Dict[str, Any]:
        """Read-only closure inventory across all three profiles, including search studies."""
        from ..closure_profiles import detect_project_profiles

        target = _project_path(project_dir)
        try:
            return detect_project_profiles(target)
        except (ProjectError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/autopilot-status")
    def autopilot_status_endpoint(
        project_dir: str = Query(..., min_length=1, max_length=500)
    ) -> Dict[str, Any]:
        """Read-only snapshot of the policy-bounded autopilot; it can never trigger one."""
        from ..autopilot import autopilot_snapshot

        target = _project_path(project_dir)
        try:
            return autopilot_snapshot(target)
        except (ProjectError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/research/tools/{tool_name}")
    def research_tool(tool_name: str, payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
        _require_research_api(request)
        try:
            return research_api.call_tool(tool_name, payload)
        except ResearchAgentAPIError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/models")
    def model_snapshot() -> Dict[str, Any]:
        return model_service.snapshot()

    @app.post("/api/models/providers")
    def upsert_model_provider(payload: ProviderPayload) -> Dict[str, Any]:
        try:
            return model_service.upsert_provider(payload.model_dump())
        except ModelConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/models/providers/{provider_id}/key")
    def set_model_key(provider_id: str, payload: KeyPayload) -> Dict[str, Any]:
        try:
            return model_service.set_key(provider_id, payload.api_key)
        except ModelConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.delete("/api/models/providers/{provider_id}/key")
    def clear_model_key(provider_id: str) -> Dict[str, Any]:
        try:
            return model_service.clear_key(provider_id)
        except ModelConfigError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/api/models/providers/{provider_id}/refresh")
    def refresh_provider_models(provider_id: str) -> Dict[str, Any]:
        try:
            return model_service.refresh_models(provider_id)
        except ModelConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except ModelCallError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/api/models/profiles")
    def upsert_model_profile(payload: ProfilePayload) -> Dict[str, Any]:
        try:
            return model_service.upsert_profile(payload.model_dump())
        except ModelConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/models/bindings")
    def upsert_model_binding(payload: BindingPayload) -> Dict[str, Any]:
        try:
            return model_service.set_binding(payload.module, payload.profile_id)
        except ModelConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/models/probe")
    def probe_model(payload: ProbePayload) -> Dict[str, Any]:
        try:
            return model_service.probe(
                payload.profile_id,
                payload.prompt,
                system=payload.system,
                max_tokens=payload.max_tokens,
            )
        except ModelConfigError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except ModelCallError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.get("/api/models/calls")
    def model_calls() -> Dict[str, Any]:
        return {"calls": model_service.calls()}

    @app.get("/api/host-model/panel")
    def host_model_panel() -> Dict[str, Any]:
        """Read-only critic bench availability: which supplies exist and what is still missing."""
        from ..model_catalog import critic_panel

        try:
            return critic_panel(settings.model_store_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/host-model/turns")
    def host_model_turns(
        status: str = Query(default="", max_length=20),
        module: str = Query(default="", max_length=40),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> Dict[str, Any]:
        from ..host_model import ModelTurnLedger, host_turn_requests

        return host_turn_requests(
            ModelTurnLedger(settings.host_model_ledger_path),
            status=status or None,
            module=module or None,
            limit=limit,
            include_request=True,
        )

    @app.post("/api/host-model/respond")
    def host_model_respond(payload: HostModelRespondPayload) -> Dict[str, Any]:
        """Record a host-agent answer for a deferred model turn; it is capability output, not a gate."""
        from ..host_model import ModelTurnLedger

        try:
            outcome = ModelTurnLedger(settings.host_model_ledger_path).respond(
                payload.turn_id,
                payload.text,
                host_label=payload.host_label,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not outcome.get("accepted"):
            return {
                "accepted": False,
                "errors": outcome.get("errors", []),
                "note": "the turn stays pending; correct the output and respond again",
            }
        return {"accepted": True, "receipt": outcome.get("receipt", {})}

    @app.post("/api/host-model/void")
    def host_model_void(payload: HostModelVoidPayload) -> Dict[str, Any]:
        from ..host_model import ModelTurnLedger

        try:
            turn = ModelTurnLedger(settings.host_model_ledger_path).void(
                payload.turn_id, payload.reason
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"voided": True, "turn_id": turn.get("turn_id"), "status": turn.get("status")}

    @app.get("/api/workspace/agents")
    def workspace_agents() -> Dict[str, Any]:
        return agent_registry.snapshot()

    @app.get("/api/literature/memory")
    def literature_memory_snapshot(limit: int = Query(default=20, ge=1, le=100)) -> Dict[str, Any]:
        return literature_memory.snapshot(limit=limit)

    @app.get("/api/agents/custom")
    def custom_agent_snapshot() -> Dict[str, Any]:
        return custom_agents.snapshot()

    @app.post("/api/agents/custom")
    def create_custom_agent(payload: CustomAgentCreate) -> Dict[str, Any]:
        try:
            return custom_agents.add(
                payload.name, payload.role, payload.purpose, payload.checks, enabled=payload.enabled
            )
        except CustomAgentError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.patch("/api/agents/custom/{agent_id}")
    def update_custom_agent(agent_id: str, payload: CustomAgentUpdate) -> Dict[str, Any]:
        try:
            return custom_agents.update(
                agent_id,
                enabled=payload.enabled,
                name=payload.name,
                purpose=payload.purpose,
                checks=payload.checks,
            )
        except CustomAgentError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.delete("/api/agents/custom/{agent_id}")
    def delete_custom_agent(agent_id: str) -> Dict[str, Any]:
        if not custom_agents.delete(agent_id):
            raise HTTPException(status_code=404, detail="custom agent not found")
        return {"deleted": True, "id": agent_id}

    @app.get("/api/evolution/policy")
    def evolution_policy_snapshot() -> Dict[str, Any]:
        return evolution_policy.snapshot()

    @app.post("/api/evolution/policy")
    def update_evolution_policy(payload: EvolutionPolicyUpdate) -> Dict[str, Any]:
        try:
            evolution_policy.update(
                enabled=payload.enabled,
                scopes=payload.scopes or None,
            )
            return evolution_policy.snapshot()
        except EvolutionPolicyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/evolution/observations")
    def evolution_observations_snapshot(limit: int = Query(default=20, ge=1, le=100)) -> Dict[str, Any]:
        return {
            "summary": evolution_observations.summary(),
            "observations": evolution_observations.list(limit=limit),
            "boundary": evolution_observations.boundary,
        }

    @app.get("/api/evolution/active")
    def evolution_active_snapshot() -> Dict[str, Any]:
        return evolution_active.snapshot()

    @app.get("/api/skills")
    def skill_snapshot() -> Dict[str, Any]:
        return skill_registry.snapshot()

    @app.get("/api/skills/usage")
    def skill_usage_snapshot() -> Dict[str, Any]:
        return skill_usage.summary()

    @app.get("/api/skills/versions")
    def skill_versions_snapshot() -> Dict[str, Any]:
        return skill_versions.snapshot()

    @app.get("/api/signers")
    def signer_snapshot() -> Dict[str, Any]:
        return signers.snapshot()

    @app.post("/api/skills/{skill_id}/run")
    def run_builtin_skill(skill_id: str, payload: SkillRunPayload) -> Dict[str, Any]:
        if skill_id not in ("literature-brief", "hypothesis-triage", "protocol-review", "evidence-boundary"):
            raise HTTPException(status_code=404, detail="only built-in read-only skills can run")
        try:
            active_version = skill_versions.active_version(skill_id)
            result = run_skill(skill_id, payload.payload, version=active_version)
        except (ActionError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        raw_status = str(result.get("status") or "")
        status = (
            "needs_input" if raw_status == "needs_input" else
            "blocked" if raw_status in ("blocked", "insufficient_evidence") else
            "pass" if raw_status in ("pass", "ok") else "warn"
        )
        usage = skill_usage.record(
            skill_id=skill_id,
            version=active_version,
            task_id=payload.task_id,
            status=status,
            checks=list(result.get("checks") or []),
            note="built-in read-only skill run via runtime",
        )
        return {
            "result": result,
            "usage": usage,
            "active_version": active_version,
            "boundary": "built-in read-only execution; no scripts, no custom skill execution, no Claim/EA",
        }

    @app.post("/api/skills/import")
    def import_skills(payload: SkillImportPayload) -> Dict[str, Any]:
        try:
            manifests = [
                manifest_from_payload(item.model_dump()) for item in payload.skills
            ]
        except SkillError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        result = skill_registry.register_many(manifests)
        return {
            "accepted": len(result["accepted"]),
            "rejected": result["rejected"],
            "snapshot": result["snapshot"],
        }

    @app.patch("/api/skills/{skill_id}")
    def toggle_skill(skill_id: str, payload: SkillTogglePayload) -> Dict[str, Any]:
        try:
            return skill_registry.set_enabled(skill_id, payload.enabled)
        except SkillError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.delete("/api/skills/{skill_id}")
    def delete_skill(skill_id: str) -> Dict[str, Any]:
        if not skill_registry.delete(skill_id):
            raise HTTPException(status_code=404, detail="skill not found")
        return {"deleted": True, "id": skill_id}

    @app.get("/api/orchestrator/topology")
    def orchestrator_topology() -> Dict[str, Any]:
        return topology_snapshot()

    @app.get("/api/orchestrator/plan")
    def orchestrator_plan(
        topic: str = Query(min_length=2, max_length=500),
        max_sources: int = Query(default=12, ge=1, le=50),
        source: Literal["fixture", "real"] = "fixture",
    ) -> Dict[str, Any]:
        try:
            policy = evolution_policy.snapshot()
            advice = (
                literature_memory.advise(topic, max_sources, source)
                if evolution_policy.allows_memory_order()
                else None
            )
            return collaboration_plan(
                topic,
                max_sources,
                source,
                advice,
                custom_agents=custom_agents.list(enabled_only=True),
                evolution_policy=policy,
            )
        except (LiteratureMemoryError, CustomAgentError, EvolutionPolicyError, OrchestrationError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/workspace/commands")
    def workspace_commands() -> Dict[str, Any]:
        return command_registry.snapshot()

    @app.get("/api/workspace/memory")
    def workspace_memory() -> Dict[str, Any]:
        return memory_store.snapshot()

    @app.post("/api/workspace/memory")
    def create_workspace_memory(payload: MemoryCreate) -> Dict[str, Any]:
        try:
            return memory_store.add(payload.text, payload.kind, payload.scope, payload.source)
        except WorkspaceStoreError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.delete("/api/workspace/memory/{entry_id}")
    def delete_workspace_memory(entry_id: str) -> Dict[str, Any]:
        if not memory_store.delete(entry_id):
            raise HTTPException(status_code=404, detail="memory entry not found")
        return {"deleted": True, "id": entry_id}

    @app.get("/api/workspace/archive")
    def workspace_archive() -> Dict[str, Any]:
        return archive_store.snapshot()

    @app.post("/api/workspace/archive")
    def create_workspace_archive(payload: ArchiveCreate) -> Dict[str, Any]:
        try:
            return archive_store.add(
                payload.title, payload.task_id, payload.payload, note=payload.note
            )
        except WorkspaceStoreError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/workspace/archive/{archive_id}")
    def get_workspace_archive(archive_id: str) -> Dict[str, Any]:
        try:
            return archive_store.get(archive_id)
        except WorkspaceStoreError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.delete("/api/workspace/archive/{archive_id}")
    def delete_workspace_archive(archive_id: str) -> Dict[str, Any]:
        try:
            deleted = archive_store.delete(archive_id)
        except WorkspaceStoreError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not deleted:
            raise HTTPException(status_code=404, detail="archive not found")
        return {"deleted": True, "id": archive_id}

    @app.post("/api/workspace/actions/automation-plan")
    def workspace_automation_plan(payload: AutomationPlanAction) -> Dict[str, Any]:
        try:
            return automation_plan(
                payload.topic, payload.max_sources, payload.run_dataset, payload.run_seeds
            )
        except ActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/api/workspace/actions/skill")
    def workspace_skill(payload: SkillAction) -> Dict[str, Any]:
        try:
            return run_skill(payload.skill_id, payload.payload)
        except ActionError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/runs")
    def list_runs(limit: int = Query(default=20, ge=1, le=100)) -> Dict[str, Any]:
        return {"jobs": manager.list(limit=limit)}

    @app.post("/api/runs", status_code=202)
    def create_run(payload: RunCreate) -> JSONResponse:
        if settings.research_mode == "production":
            readiness = model_service.readiness()
            if not readiness["production_ready"]:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "message": "production mode requires model-wired, bound and keyed modules",
                        "readiness": readiness,
                    },
                )
        request = payload.model_dump()
        try:
            job = manager.submit(request)
        except QueueLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc))
        body = job.public(include_result=False)
        body["status"] = "queued"
        return JSONResponse(status_code=202, content=body)

    @app.get("/api/runs/{job_id}")
    def get_run(job_id: str) -> Dict[str, Any]:
        try:
            payload = manager.get(job_id).public()
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        # 判定总线到 workbench 的载荷增补（ContextPanel 数据流对接）：单 run 闭包
        # 判定经 verdict-ledger 单点；失败不打断 run 状态本身。
        try:
            from ..verdict_ledger import closure_verdict_for_run

            job = manager.get(job_id)
            payload["verdict_bus"] = {
                "closure": closure_verdict_for_run(job.output_dir),
                "boundary": "closure verdict re-derived from artifacts (verdict-ledger); prompt-side only, never a gate",
            }
        except Exception:
            payload["verdict_bus"] = {"closure": None, "error": "verdict bus unavailable"}
        return payload

    @app.get("/api/runs/{job_id}/events")
    def get_events(job_id: str, after: int = Query(default=0, ge=0)) -> Dict[str, Any]:
        try:
            job = manager.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        return {
            "job_id": job_id,
            "status": job.status,
            "terminal": job.status in ("completed", "failed"),
            "events": manager.events_after(job, after),
        }

    @app.get("/api/runs/{job_id}/events/stream")
    async def stream_events(
        job_id: str, request: Request, after: int = Query(default=0, ge=0)
    ) -> StreamingResponse:
        try:
            manager.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")

        async def event_stream():
            last = after
            idle = 0
            while True:
                if await request.is_disconnected():
                    break
                job = manager.get(job_id)
                events = manager.events_after(job, last)
                for event in events:
                    last = int(event["seq"])
                    yield "id: %d\ndata: %s\n\n" % (
                        last, json.dumps(event, ensure_ascii=False)
                    )
                if events:
                    idle = 0
                if job.status in ("completed", "failed") and not events:
                    break
                await sleep(0.25)
                idle += 1
                if idle and idle % 40 == 0:
                    yield ": keep-alive\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/runs/{job_id}/artifacts")
    def list_artifacts(job_id: str) -> Dict[str, Any]:
        try:
            job = manager.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        return {"job_id": job_id, "artifacts": manager.artifacts(job)}

    @app.get("/api/runs/{job_id}/artifacts/{artifact_path:path}")
    def get_artifact(job_id: str, artifact_path: str) -> FileResponse:
        try:
            job = manager.get(job_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="job not found")
        try:
            path = manager.read_artifact(job, artifact_path)
        except ArtifactPathError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(str(path))

    def resolve_json_path(raw: str) -> Path:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = settings.repo_root / raw
        candidate = candidate.resolve()
        if not any(is_relative_to(candidate, root) for root in settings.allowed_rsi_roots):
            raise HTTPException(status_code=403, detail="path is outside allowed RSI roots")
        if candidate.suffix.lower() != ".json" or not candidate.is_file():
            raise HTTPException(status_code=404, detail="JSON artifact not found")
        return candidate

    @app.get("/api/rsi/ledgers")
    def list_ledgers() -> Dict[str, Any]:
        found: List[Dict[str, Any]] = []
        for root in settings.allowed_rsi_roots:
            if len(found) >= 50:
                break
            root = Path(root)
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*.json")):
                if len(found) >= 50:
                    break
                try:
                    if path.stat().st_size > 5 * 1024 * 1024:
                        continue
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(data, dict) or data.get("schema_version") != "rsi-0.1":
                    continue
                found.append({
                    "path": _relative(path, settings.repo_root),
                    "episodes": len(data.get("episodes", [])),
                    "leases": len(data.get("leases", [])),
                    "confirmations": len(data.get("confirmations", [])),
                })
        return {"ledgers": found}

    @app.get("/api/rsi/status")
    def rsi_status(ledger: str = Query(default="")) -> Dict[str, Any]:
        if ledger:
            path = resolve_json_path(ledger)
        elif settings.default_rsi_ledger and Path(settings.default_rsi_ledger).is_file():
            path = resolve_json_path(str(settings.default_rsi_ledger))
        else:
            raise HTTPException(status_code=404, detail="no RSI ledger configured")
        report = RSIController(StepLedger.load(path)).report()
        report["ledger_path"] = _relative(path, settings.repo_root)
        report["read_only"] = True
        return report

    @app.get("/api/rsi/story")
    def rsi_story(ledger: str = Query(default="")) -> Dict[str, Any]:
        if ledger:
            path = resolve_json_path(ledger)
        elif settings.default_rsi_ledger and Path(settings.default_rsi_ledger).is_file():
            path = resolve_json_path(str(settings.default_rsi_ledger))
        else:
            raise HTTPException(status_code=404, detail="no RSI ledger configured")
        story = ledger_story(StepLedger.load(path))
        story["ledger_path"] = _relative(path, settings.repo_root)
        return story

    @app.get("/api/rsi/generations")
    def rsi_generations(
        path: str = Query(default=""), kind: str = Query(default="")
    ) -> Dict[str, Any]:
        """Read-only two-track lineage: adopted agent harness generations and platform code."""
        from .. import evolution_generations as generations

        try:
            store = generations.GenerationStore.load(path or "")
        except generations.GenerationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        story = store.story()
        if kind:
            story["tracks"] = {kind: story["tracks"].get(kind, [])}
        story["read_only"] = True
        return story

    @app.get("/api/rsi/harness2")
    def rsi_harness2(
        artifact: str = Query(default=""), record: bool = Query(default=False)
    ) -> Dict[str, Any]:
        """Read-only Harness² projection; ``record`` never admits, only lists what would be written."""
        from .. import rsi_harness2 as harness2_seam

        try:
            payload = harness2_seam.load_artifact(artifact or "")
        except harness2_seam.Harness2Error as exc:
            return JSONResponse(
                status_code=404,
                content={"error": str(exc), "probe": harness2_seam.probe()},
            )
        story = harness2_seam.summarize(payload)
        story["probe"] = harness2_seam.probe()
        story["read_only"] = True
        if record:
            candidates, blocked = harness2_seam.to_candidates(payload)
            story["would_record"] = [
                {
                    "kind": candidate.kind,
                    "target": candidate.target,
                    "scope": candidate.scope,
                    "patch_chars": len(candidate.patch),
                    "rationale": candidate.rationale[:400],
                }
                for candidate in candidates
            ]
            story["blocked"] = blocked
        return story

    @app.get("/api/rsi/trace")
    def rsi_trace(
        ledger: str = Query(...),
        scope: str = Query(...),
        capsule: str = Query(...),
        confirmation: str = Query(default=""),
    ) -> Dict[str, Any]:
        ledger_path = resolve_json_path(ledger)
        capsule_path = resolve_json_path(capsule)
        confirmation_path = resolve_json_path(confirmation) if confirmation else None
        result = trace_research(
            ledger_path, scope, capsule_path, confirmation_path
        )
        result["ledger_path"] = _relative(ledger_path, settings.repo_root)
        return result

    return app


app = create_app()

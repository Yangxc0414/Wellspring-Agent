"""Threaded pipeline jobs for the local runtime.

One worker is intentional: the pipeline is CPU/IO heavy, and serial execution
keeps artifact directories and logs easy to audit. Each job persists its
status, events and result summary to ``<job>/job.json`` so completed runs can
be listed and read after a runtime restart; interrupted runs are marked failed
instead of being resumed silently.
"""

import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..adapters import FixtureRetriever, LocalDocumentRetriever, RealCorpusRetriever, SimpleParser
from ..paths import (
    DEFAULT_CUSTOM_AGENTS_PATH,
    DEFAULT_EVOLUTION_ACTIVE_PATH,
    DEFAULT_EVOLUTION_OBSERVATIONS_PATH,
    DEFAULT_EVOLUTION_POLICY_PATH,
    DEFAULT_JOBS_ROOT,
    DEFAULT_LITERATURE_MEMORY_PATH,
    DEFAULT_LOCAL_CORPUS_DIR,
    DEFAULT_MODEL_STORE_PATH,
    DEFAULT_HOST_MODEL_LEDGER_PATH,
    DEFAULT_REAL_CORPUS_PATH,
    DEFAULT_RSI_CHEMLAB_LEDGER_PATH,
    DEFAULT_SIGNER_STORE_PATH,
    DEFAULT_SKILL_REGISTRY_PATH,
    DEFAULT_SKILL_USAGE_PATH,
    DEFAULT_SKILL_VERSIONS_PATH,
    DEFAULT_WORKSPACE_ARCHIVE_ROOT,
    DEFAULT_WORKSPACE_MEMORY_PATH,
    REPO_ROOT,
    RUNTIME_DATA_ROOT,
    WEB_DATA_ROOT,
)
from ..pipeline import (
    PipelineError,
    PipelineRequest,
    PipelineRunner,
    write_pipeline_artifacts,
)
from ..storage import write_json_atomic

LOGGER = logging.getLogger(__name__)
TERMINAL_STATUSES = ("completed", "failed")
JOB_SCHEMA = "runtime-job/1"


class QueueLimitError(RuntimeError):
    pass


class ArtifactPathError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class RuntimeSettings:
    repo_root: Path
    jobs_root: Path
    allowed_rsi_roots: List[Path]
    default_rsi_ledger: Optional[Path] = None
    real_corpus_path: Optional[Path] = None
    model_store_path: Optional[Path] = None
    host_model_ledger_path: Optional[Path] = None
    workspace_memory_path: Optional[Path] = None
    workspace_archive_root: Optional[Path] = None
    literature_memory_path: Optional[Path] = None
    custom_agents_path: Optional[Path] = None
    evolution_policy_path: Optional[Path] = None
    evolution_observations_path: Optional[Path] = None
    evolution_active_path: Optional[Path] = None
    skill_registry_path: Optional[Path] = None
    skill_usage_path: Optional[Path] = None
    skill_versions_path: Optional[Path] = None
    signer_store_path: Optional[Path] = None
    local_corpus_dir: Optional[Path] = None
    research_api_root: Optional[Path] = None
    research_api_token: str = ""
    research_mode: str = "test"
    allowed_origins: List[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:8010",
        "http://127.0.0.1:8010",
        "http://localhost:8017",
        "http://127.0.0.1:8017",
        "https://yangxc0414.github.io",
        "null",
    ])
    max_pending: int = 2
    max_artifact_bytes: int = 20 * 1024 * 1024


def default_settings() -> RuntimeSettings:
    mode = (os.environ.get("RESEARCH_AGENT_MODE") or "test").strip().lower()
    if mode not in ("test", "production"):
        mode = "test"
    return RuntimeSettings(
        research_mode=mode,
        repo_root=REPO_ROOT,
        jobs_root=DEFAULT_JOBS_ROOT,
        allowed_rsi_roots=[WEB_DATA_ROOT, RUNTIME_DATA_ROOT],
        default_rsi_ledger=(
            DEFAULT_RSI_CHEMLAB_LEDGER_PATH
            if DEFAULT_RSI_CHEMLAB_LEDGER_PATH.is_file()
            else None
        ),
        real_corpus_path=DEFAULT_REAL_CORPUS_PATH,
        model_store_path=DEFAULT_MODEL_STORE_PATH,
        host_model_ledger_path=DEFAULT_HOST_MODEL_LEDGER_PATH,
        research_api_root=Path(
            os.environ.get("RESEARCH_AGENT_API_ROOT") or REPO_ROOT
        ).resolve(),
        research_api_token=os.environ.get("RESEARCH_AGENT_API_TOKEN", ""),
        workspace_memory_path=DEFAULT_WORKSPACE_MEMORY_PATH,
        workspace_archive_root=DEFAULT_WORKSPACE_ARCHIVE_ROOT,
        literature_memory_path=DEFAULT_LITERATURE_MEMORY_PATH,
        custom_agents_path=DEFAULT_CUSTOM_AGENTS_PATH,
        evolution_policy_path=DEFAULT_EVOLUTION_POLICY_PATH,
        evolution_observations_path=DEFAULT_EVOLUTION_OBSERVATIONS_PATH,
        evolution_active_path=DEFAULT_EVOLUTION_ACTIVE_PATH,
        skill_registry_path=DEFAULT_SKILL_REGISTRY_PATH,
        skill_usage_path=DEFAULT_SKILL_USAGE_PATH,
        skill_versions_path=DEFAULT_SKILL_VERSIONS_PATH,
        signer_store_path=DEFAULT_SIGNER_STORE_PATH,
        local_corpus_dir=DEFAULT_LOCAL_CORPUS_DIR,
    )


@dataclass
class Job:
    job_id: str
    request: Dict[str, Any]
    output_dir: Path
    status: str = "queued"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    events: List[Dict[str, Any]] = field(default_factory=list)
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def to_record(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "schema_version": JOB_SCHEMA,
                "job_id": self.job_id,
                "request": dict(self.request),
                "status": self.status,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "events": [dict(event) for event in self.events],
                "result": dict(self.result),
                "error": self.error,
            }

    @classmethod
    def from_record(cls, record: Dict[str, Any], output_dir: Path) -> "Job":
        if record.get("schema_version") != JOB_SCHEMA:
            raise ValueError("unsupported job schema")
        status = str(record.get("status") or "failed")
        if status not in ("queued", "running", "completed", "failed"):
            raise ValueError("invalid job status")
        return cls(
            job_id=str(record["job_id"]),
            request=dict(record.get("request") or {}),
            output_dir=output_dir,
            status=status,
            created_at=str(record.get("created_at") or _now()),
            updated_at=str(record.get("updated_at") or _now()),
            events=[item for item in record.get("events") or [] if isinstance(item, dict)],
            result=dict(record.get("result") or {}),
            error=str(record.get("error") or ""),
        )

    def public(self, include_result: bool = True) -> Dict[str, Any]:
        with self.lock:
            payload = {
                "job_id": self.job_id,
                "status": self.status,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "request": dict(self.request),
                "events_count": len(self.events),
                "error": self.error,
                "events_url": "/api/runs/%s/events" % self.job_id,
                "stream_url": "/api/runs/%s/events/stream" % self.job_id,
                "artifacts_url": "/api/runs/%s/artifacts" % self.job_id,
            }
            if include_result:
                payload["result"] = dict(self.result)
            return payload


class JobManager:
    def __init__(
        self,
        settings: RuntimeSettings,
        model_gateway=None,
        observation_store=None,
        active_policy_store=None,
    ):
        self.settings = settings
        self.model_gateway = model_gateway
        self.observation_store = observation_store
        self.active_policy_store = active_policy_store
        self.settings.jobs_root.mkdir(parents=True, exist_ok=True)
        self._jobs: Dict[str, Job] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-agent")
        self._load_jobs()

    def _load_jobs(self) -> None:
        interrupted: List[Job] = []
        root = Path(self.settings.jobs_root)
        if not root.is_dir():
            return
        for job_file in sorted(root.glob("*/job.json")):
            try:
                record = json.loads(job_file.read_text(encoding="utf-8"))
                job = Job.from_record(record, job_file.parent)
            except (OSError, ValueError, KeyError):
                continue
            if job.status in ("queued", "running"):
                job.status = "failed"
                job.error = "interrupted by runtime restart; artifacts may be partial"
                job.updated_at = _now()
                interrupted.append(job)
            with self._lock:
                self._jobs[job.job_id] = job
                self._order.append(job.job_id)
        self._order.sort(key=lambda job_id: self._jobs[job_id].created_at)
        for job in interrupted:
            self._emit(
                job,
                {
                    "type": "error",
                    "stage": None,
                    "message": job.error,
                    "data": {"recovered": True},
                },
            )

    def _persist(self, job: Job) -> None:
        try:
            write_json_atomic(job.output_dir / "job.json", job.to_record())
        except (OSError, ValueError):
            LOGGER.exception("cannot persist runtime job %s", job.job_id)

    def submit(self, request: Dict[str, Any]) -> Job:
        with self._lock:
            pending = sum(
                1 for job in self._jobs.values()
                if job.status not in TERMINAL_STATUSES
            )
            if pending >= self.settings.max_pending:
                raise QueueLimitError(
                    "runtime queue is full (%d pending); wait for a run to finish"
                    % self.settings.max_pending
                )
            token = uuid.uuid4().hex[:10]
            job_id = "JOB-%s-%s" % (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"), token)
            job = Job(job_id=job_id, request=dict(request), output_dir=self.settings.jobs_root / job_id)
            job.output_dir.mkdir(parents=True, exist_ok=True)
            self._jobs[job_id] = job
            self._order.append(job_id)
            self._emit(job, {"type": "queued", "stage": None, "message": "job accepted by local runtime"})
            self._executor.submit(self._run, job)
            return job

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def list(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            job_ids = list(reversed(self._order[-limit:]))
        return [self.get(job_id).public(include_result=False) for job_id in job_ids]

    def events_after(self, job: Job, after: int) -> List[Dict[str, Any]]:
        with job.lock:
            return [dict(event) for event in job.events if event.get("seq", 0) > after]

    def artifacts(self, job: Job) -> List[Dict[str, Any]]:
        root = job.output_dir.resolve()
        items: List[Dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith(".tmp") or path.name == "job.json":
                continue
            try:
                resolved = path.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            rel = resolved.relative_to(root).as_posix()
            suffix = resolved.suffix.lower()
            try:
                size = resolved.stat().st_size
            except OSError:
                # the artifact disappeared between is_file() and stat(): a listing must
                # not fail because one entry raced, it just stops describing that entry
                continue
            kind = (
                "figure" if suffix == ".svg" else
                "data" if suffix == ".json" else
                "text" if suffix in (".md", ".txt") else
                "file"
            )
            items.append({
                "path": rel,
                "size": size,
                "kind": kind,
                "url": "/api/runs/%s/artifacts/%s" % (job.job_id, rel),
            })
            if len(items) >= 200:
                break
        return items

    def read_artifact(self, job: Job, relative_path: str) -> Path:
        if not relative_path or relative_path.startswith("/") or ".." in Path(relative_path).parts:
            raise ArtifactPathError("artifact path must be relative and stay inside the job")
        root = job.output_dir.resolve()
        candidate = (root / relative_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise ArtifactPathError("artifact path escapes the job directory")
        if not candidate.is_file():
            raise FileNotFoundError(relative_path)
        if candidate.stat().st_size > self.settings.max_artifact_bytes:
            raise ArtifactPathError("artifact exceeds the runtime size limit")
        return candidate

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)

    # -- worker -----------------------------------------------------------

    def _input_path(self, value, label: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        path = Path(raw).resolve()
        roots = [Path(self.settings.repo_root).resolve(), Path(self.settings.jobs_root).resolve()]
        if not any(is_relative_to(path, root) for root in roots):
            raise ValueError("%s must stay inside the repository or runtime data" % label)
        if not path.is_file():
            raise ValueError("%s file not found: %s" % (label, path))
        return str(path)

    def _input_dir(self, value, label: str) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        path = Path(raw).resolve()
        roots = [Path(self.settings.repo_root).resolve(), Path(self.settings.jobs_root).resolve()]
        if not any(is_relative_to(path, root) for root in roots):
            raise ValueError("%s must stay inside the repository or runtime data" % label)
        if not path.is_dir():
            raise ValueError("%s directory not found: %s" % (label, path))
        return str(path)

    def _flow_mode(self, request: Dict[str, Any]) -> str:
        if self.settings.research_mode == "production":
            return "strict"
        explicit = str(request.get("flow_mode") or "").strip().lower()
        return explicit if explicit in ("review", "strict") else "review"

    def _support_audit_summary(self, job: Job) -> Dict[str, Any]:
        path = job.output_dir / "support-audit.json"
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {
            "status": str(payload.get("status") or ""),
            "method": str(payload.get("method") or ""),
            "counts": dict(payload.get("counts") or {}),
            "citation_modes": dict(payload.get("citation_modes") or {}),
            "path": str(path.relative_to(job.output_dir)),
        }

    def _job_dir_label(self, job: Job) -> str:
        try:
            return job.output_dir.resolve().relative_to(
                Path(self.settings.repo_root).resolve()
            ).as_posix()
        except ValueError:
            return job.output_dir.as_posix()

    def _record_observation(self, job: Job, summary: Dict[str, Any], q0_status: str) -> None:
        if self.observation_store is None:
            return
        try:
            observation = self.observation_store.record({
                "source": "runtime/task" if summary.get("route") else "runtime/pipeline",
                "run_id": summary.get("run_id", ""),
                "task_id": summary.get("task_id", ""),
                "topic": str(job.request.get("topic") or ""),
                "route": summary.get("route", "pipeline"),
                "status": summary.get("status", ""),
                "stopped_at": summary.get("stopped_at", ""),
                "flow_mode": summary.get("flow_mode", ""),
                "fixture_mode": bool(summary.get("fixture_mode")),
                "max_sources": summary.get("max_sources", 0),
                "q0_status": q0_status,
                "packages": [
                    {"id": item.get("id"), "status": item.get("status")}
                    for item in (summary.get("evidence_packages") or [])
                    if isinstance(item, dict)
                ],
                "warnings": list(summary.get("warnings") or [])[:8],
            })
            summary["observation_id"] = observation["observation_id"]
        except Exception as exc:
            summary["observation_error"] = "%s: %s" % (type(exc).__name__, exc)

    def _model_tools(self):
        from ..adapters.glm_model import gateway_query_planner
        from ..adapters.paper_writer import gateway_paper_writer
        from ..adapters.research_models import (
            gateway_experiment_designer,
            gateway_idea_proposer,
        )
        from ..adapters.support_judge import gateway_support_judge

        strict = self.settings.research_mode == "production"
        gateway = self.model_gateway
        planner, planner_note = gateway_query_planner(gateway=gateway, strict=strict)
        writer, writer_note = gateway_paper_writer(gateway=gateway, strict=strict)
        idea, idea_note = gateway_idea_proposer(gateway=gateway, strict=strict)
        experiment, experiment_note = gateway_experiment_designer(
            gateway=gateway, strict=strict
        )
        judge, judge_note = gateway_support_judge(gateway=gateway, strict=strict)
        notes = [
            note for note in (
                planner_note, writer_note, idea_note, experiment_note, judge_note
            ) if note
        ]
        return {
            "planner": planner,
            "writer": writer,
            "idea": idea,
            "experiment": experiment,
            "judge": judge,
        }, notes

    def _run(self, job: Job) -> None:
        with job.lock:
            job.status = "running"
            job.updated_at = _now()
        self._persist(job)
        self._emit(job, {"type": "info", "stage": None, "message": "worker started"})
        try:
            venue_type = str(job.request.get("venue_type") or "zh_core_journal")
            language = str(job.request.get("language") or "")
            if not language:
                language = "en" if venue_type.startswith("en_") else "zh"
            task_type = str(job.request.get("task_type") or "")
            flow_mode = self._flow_mode(job.request)
            g1_decision_file = self._input_path(job.request.get("g1_decision_file"), "g1_decision_file")
            protocol_file = self._input_path(job.request.get("protocol_file"), "protocol_file")
            claim_file = self._input_path(job.request.get("claim_file"), "claim_file")
            bibliography_file = self._input_path(
                job.request.get("bibliography_file"), "bibliography_file"
            )
            run_dir = self._input_dir(job.request.get("run_dir"), "run_dir")
            active_policy = None
            if self.active_policy_store is not None:
                try:
                    active_policy = self.active_policy_store.resolve(
                        "literature.retrieval.budget"
                    )
                except Exception as exc:
                    self._emit(
                        job,
                        {
                            "type": "info",
                            "stage": "evolution",
                            "message": "active policy ignored: %s" % type(exc).__name__,
                        },
                    )
            requested_max_sources = int(job.request.get("max_sources") or 6)
            effective_max_sources = requested_max_sources
            if active_policy:
                effective_max_sources = int(
                    (active_policy.get("patch") or {}).get("max_sources")
                    or requested_max_sources
                )
                self._emit(
                    job,
                    {
                        "type": "info",
                        "stage": "evolution",
                        "message": "active evolution policy %s: max_sources %s -> %s"
                        % (
                            active_policy.get("policy_id", ""),
                            requested_max_sources,
                            effective_max_sources,
                        ),
                    },
                )
            requested_run_seeds = int(job.request.get("run_seeds") or 3)
            effective_run_seeds = requested_run_seeds
            run_dataset = str(job.request.get("run_dataset") or "")
            active_s5_lease = None
            if run_dataset and self.settings.default_rsi_ledger:
                ledger_path = Path(self.settings.default_rsi_ledger)
                if ledger_path.is_file():
                    try:
                        from ..s5_eval import resolve_s5_seed_policy

                        active_s5_lease = resolve_s5_seed_policy(
                            ledger_path, "S5/demo/%s" % run_dataset
                        )
                        if active_s5_lease:
                            effective_run_seeds = int(active_s5_lease["seeds"])
                            self._emit(
                                job,
                                {
                                    "type": "info",
                                    "stage": "evolution",
                                    "message": (
                                        "active S5 seed lease %s: run_seeds %s -> %s"
                                        % (
                                            active_s5_lease.get("lease_id", ""),
                                            requested_run_seeds,
                                            effective_run_seeds,
                                        )
                                    ),
                                },
                            )
                        else:
                            self._emit(
                                job,
                                {
                                    "type": "info",
                                    "stage": "evolution",
                                    "message": (
                                        "no active S5 seed lease for S5/demo/%s; "
                                        "using requested run_seeds=%s"
                                        % (run_dataset, requested_run_seeds)
                                    ),
                                },
                            )
                    except Exception as exc:
                        self._emit(
                            job,
                            {
                                "type": "info",
                                "stage": "evolution",
                                "message": "S5 seed lease ignored: %s: %s"
                                % (type(exc).__name__, exc),
                            },
                        )
            if task_type:
                from ..task_agent import TaskAgent, TaskRequest

                source = (
                    "openalex" if job.request.get("openalex")
                    else "local" if job.request.get("local_corpus")
                    else "real" if job.request.get("real_corpus")
                    else "fixture"
                )
                tools, model_notes = self._model_tools()
                for note in model_notes:
                    self._emit(job, {"type": "info", "stage": "models", "message": note})
                execution = TaskAgent(
                    query_planner=tools["planner"],
                    section_writer=tools["writer"],
                    idea_proposer=tools["idea"],
                    experiment_designer=tools["experiment"],
                    support_judge=tools["judge"],
                    strict_models=self.settings.research_mode == "production",
                    strict_routing=self.settings.research_mode == "production",
                ).run(
                    TaskRequest(
                        goal=str(job.request["topic"]),
                        task_type=task_type,
                        deliverable=str(job.request.get("deliverable") or ""),
                        language=language,
                        venue_type=venue_type,
                        source=source,
                        max_sources=effective_max_sources,
                        run_dataset=str(job.request.get("run_dataset") or ""),
                        run_dir=run_dir,
                        run_seeds=effective_run_seeds,
                        corpus_dir=(
                            str(self.settings.local_corpus_dir)
                            if source == "local" and self.settings.local_corpus_dir else ""
                        ),
                        flow_mode=flow_mode,
                        g1_decision_file=g1_decision_file,
                        protocol_file=protocol_file,
                        claim_file=claim_file,
                        bibliography_file=bibliography_file,
                    ),
                    job.output_dir,
                    event_sink=lambda event: self._emit(job, event),
                )
                summary = {
                    "task_id": execution.task_id,
                    "run_id": execution.task_id,
                    "job_dir": self._job_dir_label(job),
                    "status": execution.status,
                    "route": execution.plan.route,
                    "deliverable": execution.plan.deliverable,
                    "fixture_mode": source == "fixture",
                    "max_sources": effective_max_sources,
                    "requested_run_seeds": requested_run_seeds,
                    "run_seeds": effective_run_seeds,
                    "active_s5_lease": active_s5_lease,
                    "flow_mode": execution.plan.flow_mode,
                    "stopped_at": execution.stopped_at,
                    "active_policy": active_policy,
                    "warnings": list(execution.warnings),
                    "gates": list(execution.gates) or [
                        {"gate": gate, "status": "needs_human", "reason": "task route gate"}
                        for gate in execution.plan.human_gates
                    ],
                    "checks": list(execution.checks),
                    "modules": {},
                    "artifacts": dict(execution.artifacts),
                    "evidence_packages": list(execution.evidence_packages),
                    "support_audit": self._support_audit_summary(job),
                    "error": execution.error,
                    "failure": dict(execution.failure),
                }
            else:
                runner = self._build_runner(job)
                request = PipelineRequest(
                    topic=str(job.request["topic"]),
                    language=language,
                    venue_type=venue_type,
                    grant_scheme=str(job.request.get("grant_scheme") or ""),
                    figure_style=str(job.request.get("figure_style") or "modern"),
                    max_sources=effective_max_sources,
                    run_dataset=str(job.request.get("run_dataset") or ""),
                    run_dir=run_dir,
                    run_seeds=effective_run_seeds,
                    run_id="",
                    flow_mode=flow_mode,
                    g1_decision_file=g1_decision_file,
                    protocol_file=protocol_file,
                    claim_file=claim_file,
                    bibliography_file=bibliography_file,
                )
                result = runner.run(request)
                extra = {
                    "runtime": {
                        "job_id": job.job_id,
                        "mode": (
                        "openalex" if job.request.get("openalex")
                        else "real_corpus" if job.request.get("real_corpus")
                        else "fixture"
                    ),
                    }
                }
                tools, _ = self._model_tools()
                paths = write_pipeline_artifacts(
                    result,
                    job.output_dir,
                    extra=extra,
                    claim_file=claim_file,
                    support_judge=tools["judge"],
                    strict_support=self.settings.research_mode == "production",
                )
                relative_paths: Dict[str, str] = {}
                for key, value in paths.items():
                    if not value:
                        relative_paths[key] = ""
                        continue
                    try:
                        relative_paths[key] = str(Path(value).relative_to(job.output_dir))
                    except ValueError:
                        relative_paths[key] = Path(value).name
                summary = {
                    "run_id": result.run_id,
                    "job_dir": self._job_dir_label(job),
                    "status": result.status,
                    "fixture_mode": result.fixture_mode,
                    "max_sources": effective_max_sources,
                    "requested_run_seeds": requested_run_seeds,
                    "run_seeds": effective_run_seeds,
                    "active_s5_lease": active_s5_lease,
                    "flow_mode": result.flow_mode,
                    "stopped_at": result.stopped_at,
                    "active_policy": active_policy,
                    "warnings": list(result.warnings),
                    "gates": list(result.gates),
                    "spec_versions": dict(result.spec_versions),
                    "modules": {
                        key: (value.get("status") if isinstance(value, dict) else None)
                        for key, value in result.modules.items()
                    },
                    "artifacts": relative_paths,
                    "evidence_packages": list(result.evidence_packages),
                    "support_audit": self._support_audit_summary(job),
                }
            q0_status = next(
                (
                    str(item.get("status") or "unknown")
                    for item in (summary.get("gates") or [])
                    if item.get("gate") == "Q0"
                ),
                "unknown",
            )
            self._record_observation(job, summary, q0_status)
            try:
                from ..loop_capsule import update_loop_capsule_meta

                update_loop_capsule_meta(
                    job.output_dir,
                    summary.get("observation_id", ""),
                    (active_policy or {}).get("policy_id", ""),
                )
            except Exception as exc:
                summary["loop_capsule_error"] = "%s: %s" % (type(exc).__name__, exc)
            if summary.get("observation_id"):
                self._emit(
                    job,
                    {
                        "type": "info",
                        "stage": "evolution",
                        "message": "observation %s recorded; not evidence"
                        % summary["observation_id"],
                    },
                )
            with job.lock:
                job.result = summary
                job.status = "completed"
                job.updated_at = _now()
            self._persist(job)
            self._emit(
                job,
                {
                    "type": "done",
                    "stage": None,
                    "message": "%s %s" % ("task" if task_type else "pipeline", summary["status"]),
                    "data": {"status": summary["status"], "run_id": summary.get("run_id", "")},
                },
            )
        except Exception as exc:
            LOGGER.exception("runtime job %s failed", job.job_id)
            with job.lock:
                job.status = "failed"
                job.error = "%s: %s" % (type(exc).__name__, exc)
                job.updated_at = _now()
            self._persist(job)
            self._emit(
                job,
                {
                    "type": "error",
                    "stage": None,
                    "message": job.error,
                    "data": {"error_type": type(exc).__name__},
                },
            )

    def _build_runner(self, job: Job) -> PipelineRunner:
        from ..adapters.openalex_retriever import OpenAlexRetriever

        run_dir = job.output_dir / "run"
        tools, model_notes = self._model_tools()
        strict_models = self.settings.research_mode == "production"
        for note in model_notes:
            self._emit(job, {"type": "info", "stage": "models", "message": note})
        emit = lambda event: self._emit(job, event)  # noqa: E731
        if job.request.get("openalex"):
            return PipelineRunner(
                retriever=OpenAlexRetriever(mailto=str(job.request.get("mailto") or "") or None),
                parser=SimpleParser(),
                source_scope=["openalex"],
                run_output_dir=run_dir,
                event_sink=emit,
                query_planner=tools["planner"],
                section_writer=tools["writer"],
                idea_proposer=tools["idea"],
                experiment_designer=tools["experiment"],
                strict_models=strict_models,
            )
        if job.request.get("local_corpus"):
            corpus_dir = self.settings.local_corpus_dir
            if corpus_dir is None or not Path(corpus_dir).is_dir():
                raise PipelineError("local corpus directory is not configured")
            return PipelineRunner(
                retriever=LocalDocumentRetriever(Path(corpus_dir)),
                parser=SimpleParser(max_spans_per_source=4000),
                source_scope=["local"],
                run_output_dir=run_dir,
                event_sink=emit,
                query_planner=tools["planner"],
                section_writer=tools["writer"],
                idea_proposer=tools["idea"],
                experiment_designer=tools["experiment"],
                strict_models=strict_models,
            )
        if job.request.get("real_corpus"):
            corpus = self.settings.real_corpus_path
            if corpus is None or not Path(corpus).is_file():
                raise PipelineError("real corpus fixture is not configured")
            return PipelineRunner(
                retriever=RealCorpusRetriever(Path(corpus)),
                parser=SimpleParser(max_spans_per_source=2000),
                source_scope=["real"],
                run_output_dir=run_dir,
                event_sink=emit,
                query_planner=tools["planner"],
                section_writer=tools["writer"],
                idea_proposer=tools["idea"],
                experiment_designer=tools["experiment"],
                strict_models=strict_models,
            )
        return PipelineRunner(
            retriever=FixtureRetriever(),
            parser=SimpleParser(),
            source_scope=["fixture"],
            run_output_dir=run_dir,
            event_sink=emit,
            query_planner=tools["planner"],
            section_writer=tools["writer"],
            idea_proposer=tools["idea"],
            experiment_designer=tools["experiment"],
            strict_models=strict_models,
        )

    def _emit(self, job: Job, event: Dict[str, Any]) -> None:
        with job.lock:
            seq = len(job.events) + 1
            entry = {
                "seq": seq,
                "ts": _now(),
                "type": str(event.get("type") or "info"),
                "stage": event.get("stage"),
                "message": str(event.get("message") or ""),
            }
            if event.get("data") is not None:
                entry["data"] = event["data"]
            job.events.append(entry)
            job.updated_at = entry["ts"]
        self._persist(job)


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False

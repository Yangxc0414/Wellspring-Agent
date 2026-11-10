"""Task-level agent layer: route a research request to the minimal useful stages.

This is not a general ReAct loop. It is the first honest task-execution layer:
classify the requested deliverable, pick a bounded research route, execute only
the stages that route needs, record checkpoints, and report what is still
blocked by evidence or human gates.
"""

import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .adapters import (
    FixtureRetriever,
    LocalDocumentRetriever,
    OpenAlexRetriever,
    RealCorpusRetriever,
    SimpleParser,
)
from .contracts import ExperimentDesign, IdeaCard, LiteratureResult
from .evidence_packages import summarize_evidence_packages
from .flow import FlowError, load_g1_decision, q0_decision, validate_flow_mode
from .models.types import ModelTurnPending
from .modules.experiment import ExperimentDesignAgent, ExperimentRequest
from .modules.idea import IdeaAgent, IdeaRequest, prior_art_hits_from_literature
from .modules.literature import LiteratureAgent, LiteratureRequest
from .pipeline import PipelineRequest, PipelineRunner, write_pipeline_artifacts
from .ports import ParserPort, RetrieverPort
from .specs import SpecStore
from .storage import write_json_atomic


class TaskError(RuntimeError):
    pass


TASK_TYPES = (
    "auto",
    "literature_review",
    "hypothesis_design",
    "experiment_validation",
    "full_research",
)
SOURCE_SCOPES = ("fixture", "real", "openalex", "local")


@dataclass
class TaskRequest:
    goal: str
    task_type: str = "auto"
    deliverable: str = ""
    language: str = "zh"
    venue_type: str = "zh_core_journal"
    source: str = "fixture"
    max_sources: int = 6
    run_dataset: str = ""
    run_dir: str = ""
    run_seeds: int = 3
    corpus_dir: str = ""
    constraints: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    flow_mode: str = "review"
    g1_decision_file: str = ""
    protocol_file: str = ""
    claim_file: str = ""
    bibliography_file: str = ""


@dataclass
class TaskStep:
    step_id: str
    label: str
    kind: str
    gate: str = ""
    status: str = "pending"
    detail: str = ""


@dataclass
class TaskPlan:
    task_id: str
    goal: str
    route: str
    deliverable: str
    source: str
    language: str
    venue_type: str
    flow_mode: str
    steps: List[TaskStep]
    human_gates: List[str]
    success_criteria: List[str]
    budget: Dict[str, Any]
    stop_at: str
    blocking_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    route_decision: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RouteDecision:
    route: str
    confidence: str
    signals: List[str] = field(default_factory=list)
    needs_input: bool = False
    question: str = ""
    candidates: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskExecution:
    task_id: str
    plan: TaskPlan
    status: str
    steps: List[TaskStep]
    artifacts: Dict[str, str]
    checks: List[Dict[str, str]]
    warnings: List[str]
    started_at: str
    finished_at: str
    evidence_packages: List[Dict[str, Any]] = field(default_factory=list)
    stopped_at: str = ""
    gates: List[Dict[str, str]] = field(default_factory=list)
    error: str = ""
    failure: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


_TRANSIENT_MARKERS = (
    "429",
    "timeout",
    "timed out",
    "urlerror",
    "connection reset",
    "connection refused",
    "temporarily unavailable",
    "http 500",
    "http 502",
    "http 503",
    "http 504",
)


def _failure_advice(error_type: str, message: str) -> Tuple[bool, str]:
    text = (error_type + " " + message).lower()
    if "openalex" in text and "429" in text:
        return True, (
            "OpenAlex quota/network limit: set OPENALEX_API_KEY and/or OPENALEX_EMAIL, "
            "retry later, or switch to source=local/real; do not pass fixture off as real."
        )
    if "modelrequirederror" in text or "no key" in text or "no model profile binding" in text:
        return False, (
            "Configure the required runtime model profile and API key in Settings "
            "(or environment variables), then rerun; this is a configuration error."
        )
    if "supportauditerror" in text or "contradicted" in text:
        return False, (
            "Support audit failed: inspect sentence-level citations in support-audit.json, "
            "fix the evidence or conclusion, and do not sign the current claim."
        )
    if "local corpus" in text or "local_corpus" in text or "corpus_dir" in text:
        return False, (
            "Configure the local corpus directory or choose another source; "
            "no span or evidence is fabricated without full text."
        )
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return True, (
            "Transient retrieval/network failure: check connectivity and retry; for OpenAlex "
            "set OPENALEX_API_KEY / OPENALEX_EMAIL, or switch to another source."
        )
    return False, (
        "Inspect task-error.txt and the last running step, fix the reported input or "
        "environment, then rerun."
    )


def _failure_record(
    plan: "TaskPlan", error: str, warnings: List[str]
) -> Dict[str, Any]:
    error_type, _, message = error.partition(":")
    error_type = error_type.strip() or "TaskError"
    message = message.strip()
    retryable, action = _failure_advice(error_type, message)
    return {
        "schema_version": "task-failure-0.1",
        "task_id": plan.task_id,
        "route": plan.route,
        "status": "failed",
        "error_type": error_type,
        "error": message or error,
        "retryable": retryable,
        "suggested_action": action,
        "warnings": list(warnings),
        "boundary": (
            "diagnostic only; no automatic retry; never changes claims, gates, or signatures"
        ),
    }


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


class TaskRouter:
    """Deterministic router with explicit signal accounting and clarification."""

    SIGNALS = {
        "literature_review": (
            "文献综述", "文献调研", "综述", "literature review", "review paper", "survey",
        ),
        "hypothesis_design": (
            "假设", "选题", "研究想法", "hypothesis", "idea", "可证伪", "否证",
        ),
        "experiment_validation": (
            "复现", "reproduce", "实验验证", "跑实验", "experiment",
        ),
        "full_research": (
            "完整研究", "工作稿", "写一篇", "论文", "paper", "full research",
        ),
    }
    STRONG = {
        "literature_review": ("文献综述", "literature review", "review paper"),
        "hypothesis_design": ("研究假设", "可证伪", "hypothesis"),
        "experiment_validation": ("实验验证", "复现", "reproduce"),
        "full_research": ("完整研究", "完整工作稿", "写一篇", "full research"),
    }

    def decide(self, request: TaskRequest) -> RouteDecision:
        if request.task_type != "auto":
            if request.task_type not in TASK_TYPES:
                raise TaskError("unknown task_type: " + request.task_type)
            return RouteDecision(
                route=request.task_type,
                confidence="explicit",
                signals=["explicit_task_type"],
            )
        text = _normalized(request.goal)
        if request.run_dataset:
            return RouteDecision(
                route="experiment_validation",
                confidence="high",
                signals=["run_dataset:" + request.run_dataset],
            )
        hits = {
            route: [word for word in words if word in text]
            for route, words in self.SIGNALS.items()
        }
        strong = {
            route: [phrase for phrase in phrases if phrase in text]
            for route, phrases in self.STRONG.items()
        }
        ranked = sorted(
            hits,
            key=lambda route: (len(strong[route]) > 0, len(hits[route])),
            reverse=True,
        )
        best = ranked[0]
        best_hits = hits[best]
        best_strong = strong[best]
        signals = ["%s:%s" % (best, item) for item in best_hits]
        needs_input = not best_strong and len(best_hits) < 2
        candidates = [route for route in ranked if hits[route]]
        route = best if best_hits else "full_research"
        if request.source == "openalex" and route in ("hypothesis_design", "full_research"):
            route = "literature_review"
        return RouteDecision(
            route=route,
            confidence="high" if best_strong else ("medium" if len(best_hits) >= 2 else "low"),
            signals=signals,
            needs_input=needs_input,
            question=(
                "任务类型不明确；请选择文献综述 / 假设设计 / 实验验证 / 完整研究。"
                if needs_input else ""
            ),
            candidates=candidates,
        )

    def route(self, request: TaskRequest) -> str:
        decision = self.decide(request)
        if request.source == "openalex" and decision.route in ("hypothesis_design", "full_research"):
            return "literature_review"
        return decision.route


class TaskAgent:
    module_id = "task-agent"

    def __init__(
        self,
        store: Optional[SpecStore] = None,
        retriever: Optional[RetrieverPort] = None,
        parser: Optional[ParserPort] = None,
        query_planner: Optional[Callable[[str], Optional[List[str]]]] = None,
        section_writer: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, str]]]] = None,
        idea_proposer: Optional[Callable[[Dict[str, Any]], Optional[List[Dict[str, Any]]]]] = None,
        experiment_designer: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
        support_judge: Optional[Callable[[Dict[str, Any]], Optional[list]]] = None,
        strict_models: bool = False,
        strict_routing: bool = False,
        module_overrides: Optional[Dict[str, Any]] = None,
    ):
        self.store = store or SpecStore()
        self.retriever = retriever
        self.parser = parser
        self.query_planner = query_planner
        self.section_writer = section_writer
        self.idea_proposer = idea_proposer
        self.experiment_designer = experiment_designer
        self.support_judge = support_judge
        self.strict_models = strict_models
        self.strict_routing = strict_routing
        self.module_overrides = dict(module_overrides or {})
        self.router = TaskRouter()

    def plan(self, request: TaskRequest) -> TaskPlan:
        goal = " ".join((request.goal or "").split())
        if len(goal) < 2 or len(goal) > 500:
            raise TaskError("goal must be 2-500 characters")
        if request.source not in SOURCE_SCOPES:
            raise TaskError("source must be fixture, real, openalex, or local")
        if request.source == "local" and not request.corpus_dir:
            raise TaskError("source=local requires corpus_dir")
        if request.language not in ("zh", "en"):
            raise TaskError("language must be zh or en")
        try:
            flow_mode = validate_flow_mode(request.flow_mode)
        except FlowError as exc:
            raise TaskError(str(exc))
        decision = self.router.decide(request)
        if decision.needs_input and (
            self.strict_routing
            or os.environ.get("RESEARCH_AGENT_STRICT_ROUTING", "").strip().lower()
            in ("1", "true", "production")
        ):
            raise TaskError(
                "routing is ambiguous; specify task_type. " + decision.question
            )
        route = decision.route
        deliverable = request.deliverable.strip() or {
            "literature_review": "literature_review",
            "hypothesis_design": "hypothesis_design",
            "experiment_validation": "experiment_evidence",
            "full_research": "working_paper",
        }[route]
        if route == "literature_review":
            steps = [
                TaskStep("S1", "检索、全文阅读与 span 定位", "literature", gate="Q0"),
                TaskStep("REPORT", "生成任务报告与覆盖缺口", "report"),
            ]
            gates = ["Q0"]
        elif route == "hypothesis_design":
            steps = [
                TaskStep("S1", "检索、全文阅读与 span 定位", "literature", gate="Q0"),
                TaskStep("S2-S3", "证据聚类与候选假设", "idea", gate="G1"),
                TaskStep("S4", "实验设计草案", "experiment", gate="G2"),
                TaskStep("REPORT", "生成任务报告与候选/设计检查", "report"),
            ]
            gates = ["Q0", "G1", "G2"]
        elif route == "experiment_validation":
            steps = [
                TaskStep("S1", "检索、全文阅读与 span 定位", "literature", gate="Q0"),
                TaskStep("S2-S3", "证据聚类与候选假设", "idea", gate="G1"),
                TaskStep("S4", "实验设计草案", "experiment", gate="G2"),
                TaskStep("S5", "本地运行、EA 与 claim draft", "run", gate="S5b"),
                TaskStep("REPORT", "生成任务报告与证据包", "report"),
            ]
            gates = ["Q0", "G1", "G2", "S5b"]
        else:
            steps = [
                TaskStep("S1", "检索、全文阅读与 span 定位", "literature", gate="Q0"),
                TaskStep("S2-S3", "证据聚类与候选假设", "idea", gate="G1"),
                TaskStep("S4", "实验设计草案", "experiment", gate="G2"),
                TaskStep("S5", "可选本地运行与 EA", "run", gate="S5b"),
                TaskStep("S6", "科研图表", "figure"),
                TaskStep("S8-S12", "工作稿与报告", "paper", gate="G3"),
                TaskStep("REPORT", "生成任务报告", "report"),
            ]
            gates = ["Q0", "G1", "G2", "S5b", "G3"]
        criteria = list(request.success_criteria) or self._default_criteria(route)
        blocking: List[str] = []
        warnings: List[str] = []
        if route == "experiment_validation" and not (request.run_dataset or request.run_dir):
            blocking.append(
                "experiment_validation requires run_dataset (iris/breast_cancer/chemlab) "
                "or an existing run_dir"
            )
        if decision.needs_input:
            warnings.append(
                "routing ambiguous; specify task_type to avoid the %s fallback" % route
            )
        if request.source == "openalex":
            warnings.append("OpenAlex returns abstract clues only; no full text means no span and no evidence")
            if request.task_type == "auto":
                warnings.append(
                    "auto routing uses literature_review for OpenAlex; hypothesis/full research require full text"
                )
            elif request.task_type in ("hypothesis_design", "full_research"):
                warnings.append(
                    "explicit %s with OpenAlex: abstract-only cannot produce spans; expect evidence failure"
                    % request.task_type
                )
        if request.source == "fixture":
            warnings.append("fixture source is for workflow validation only; it is not citable evidence")
        return TaskPlan(
            task_id="TASK-" + uuid.uuid4().hex[:10],
            goal=goal,
            route=route,
            deliverable=deliverable,
            source=request.source,
            language=request.language,
            venue_type=request.venue_type,
            flow_mode=flow_mode,
            steps=steps,
            human_gates=gates,
            success_criteria=criteria,
            route_decision=decision.to_dict(),
            budget={
                "max_sources": int(request.max_sources),
                "run_dataset": request.run_dataset,
                "run_seeds": int(request.run_seeds),
            },
            stop_at="human_gate" if route in ("experiment_validation", "full_research") else "deliverable",
            blocking_issues=blocking,
            warnings=warnings,
        )

    @staticmethod
    def _default_criteria(route: str) -> List[str]:
        if route == "literature_review":
            return ["至少一个全文来源", "至少一个可定位 span", "报告包含 coverage 与 gap"]
        if route == "hypothesis_design":
            return ["至少一个候选假设", "每个候选有否证条件", "设计草案列出 baseline/指标/seeds"]
        if route == "experiment_validation":
            return ["RunCapsule completed", "EA immutable 且可哈希", "claim draft 未签且绑定 EA"]
        return ["报告与工作稿生成", "结果槽不早于 claim", "门禁与人工动作明确"]

    def _retriever(self, source: str, corpus_dir: str = "") -> RetrieverPort:
        if self.retriever is not None:
            return self.retriever
        if source == "fixture":
            return FixtureRetriever()
        if source == "real":
            return RealCorpusRetriever(
                Path(__file__).resolve().parents[1] / "modules" / "literature" / "fixtures" / "real_corpus.json"
            )
        if source == "local":
            if not corpus_dir:
                raise TaskError("source=local requires corpus_dir")
            return LocalDocumentRetriever(Path(corpus_dir))
        return OpenAlexRetriever()

    def _parser(self) -> ParserPort:
        return self.parser or SimpleParser(max_spans_per_source=2000)

    def run(
        self,
        request: TaskRequest,
        output_dir: Path,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> TaskExecution:
        plan = self.plan(request)
        started = _now()
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        artifacts: Dict[str, str] = {}
        warnings = list(plan.warnings)
        checks: List[Dict[str, str]] = []
        evidence_packages: List[Dict[str, Any]] = []
        stopped_at = ""
        gates: List[Dict[str, str]] = []
        steps = [TaskStep(**asdict(step)) for step in plan.steps]

        def emit(event_type: str, message: str, stage: Optional[str] = None) -> None:
            if event_sink is not None:
                try:
                    event_sink({"type": event_type, "stage": stage, "message": message})
                except Exception:
                    pass

        def write(name: str, value: Any) -> None:
            path = out / name
            write_json_atomic(path, value)
            artifacts[name] = name

        write("task-plan.json", plan.to_dict())
        emit("task_start", "task %s routed to %s" % (plan.task_id, plan.route))

        if plan.blocking_issues:
            for step in steps:
                step.status = "blocked" if step.step_id == "S5" else "skipped"
            return self._finish(
                out, plan, steps, "needs_input", artifacts, checks,
                warnings + plan.blocking_issues, started,
            )

        literature: Optional[LiteratureResult] = None
        idea_result = None
        idea_cards: List[IdeaCard] = []
        design: Optional[ExperimentDesign] = None
        pipeline_result = None

        try:
            if plan.route in ("literature_review", "hypothesis_design"):
                step = steps[0]
                step.status = "running"
                emit("step_start", step.label, step.step_id)
                literature_agent = self.module_overrides.get("literature") or LiteratureAgent(
                    self.store.load("literature"),
                    self._retriever(request.source, request.corpus_dir),
                    self._parser(),
                    query_planner=self.query_planner,
                )
                literature = literature_agent.run(
                    LiteratureRequest(
                        question=request.goal,
                        max_sources=request.max_sources,
                        source_scope=[request.source],
                        language=request.language,
                        coverage_plan=True,
                        followup_plan=True,
                    )
                )
                write("literature.json", literature.to_dict())
                from .literature_ledger import build_source_ledger

                write(
                    "literature-ledger.json",
                    build_source_ledger(
                        literature.to_dict(), request.goal, [request.source]
                    ),
                )
                step.status = "done" if literature.spans else "needs_evidence"
                step.detail = "%d sources / %d spans / %d gaps" % (
                    len(literature.hits), len(literature.spans), len(literature.coverage.gaps)
                )
                emit("step_end", step.detail, step.step_id)
                q0 = q0_decision(literature)
                write("q0.json", q0)
                if (
                    plan.route == "literature_review"
                    and request.flow_mode == "strict"
                    and q0["status"] != "pass"
                ):
                    stopped_at = "Q0"
                    warnings.append("Q0 blocked: " + q0["reason"])

                if plan.route == "hypothesis_design":
                    if request.flow_mode == "strict" and q0["status"] != "pass":
                        steps[1].status = "blocked"
                        steps[1].detail = q0["reason"]
                        steps[2].status = "skipped"
                        steps[2].detail = "not reached; Q0 blocked"
                        stopped_at = "Q0"
                        warnings.append("Q0 blocked: " + q0["reason"])
                    else:
                        step = steps[1]
                        step.status = "running"
                        emit("step_start", step.label, step.step_id)

                        def _prior_art_search(
                            query: str, limit: int
                        ) -> List[Dict[str, Any]]:
                            result = literature_agent.run(
                                LiteratureRequest(
                                    question=query,
                                    max_sources=max(1, min(limit, 3)),
                                    source_scope=[request.source],
                                    language=request.language,
                                    coverage_plan=False,
                                )
                            )
                            return prior_art_hits_from_literature(result, limit)

                        idea_agent = self.module_overrides.get("idea") or IdeaAgent(
                            self.store.load("idea"),
                            proposer=self.idea_proposer,
                            strict_model=self.strict_models,
                        )
                        idea = idea_agent.run(
                            IdeaRequest(
                                topic=request.goal,
                                spans=literature.spans,
                                max_candidates=3,
                                language=request.language,
                                prior_art_searcher=_prior_art_search,
                            )
                        )
                        idea_result = idea
                        idea_cards = list(idea.candidates)
                        write("idea.json", asdict(idea))
                        from .idea_review import build_idea_review

                        write(
                            "idea-review.json",
                            build_idea_review(asdict(idea), literature.to_dict()),
                        )
                        step.status = "done" if idea_cards else "needs_evidence"
                        step.detail = "%d candidates; G1 required" % len(idea_cards)
                        emit("step_end", step.detail, step.step_id)

                        g1_decision = None
                        if request.g1_decision_file:
                            try:
                                g1_decision = load_g1_decision(
                                    Path(request.g1_decision_file), idea_cards
                                )
                                write("g1-decision.json", g1_decision)
                            except FlowError as exc:
                                warnings.append("G1 decision rejected: " + str(exc))
                        if request.flow_mode == "strict" and g1_decision is None:
                            steps[2].status = "blocked"
                            steps[2].detail = (
                                "G1 requires a selected idea decision"
                                if idea_cards else "no candidate hypothesis"
                            )
                            stopped_at = "G1"
                        else:
                            selected_id = (
                                g1_decision["selected_idea_id"]
                                if g1_decision
                                else (idea_cards[0].idea_id if idea_cards else "")
                            )
                            selected = next(
                                (card for card in idea_cards if card.idea_id == selected_id),
                                idea_cards[0] if idea_cards else None,
                            )
                            step = steps[2]
                            step.status = "running"
                            emit("step_start", step.label, step.step_id)
                            hypothesis = selected.hypothesis if selected else "待人工补全"
                            experiment_agent = self.module_overrides.get("experiment") or ExperimentDesignAgent(
                                self.store.load("experiment"),
                                designer=self.experiment_designer,
                                strict_model=self.strict_models,
                            )
                            design = experiment_agent.run(
                                ExperimentRequest(
                                    question=request.goal,
                                    hypothesis=hypothesis,
                                    baseline="待人工补全",
                                    primary_metric="",
                                    controls=[],
                                    seeds=request.run_seeds,
                                    budget="",
                                    evidence_refs=[span.span_id for span in literature.spans[:4]],
                                    evidence=[
                                        {"ref": span.span_id, "section": span.section, "text": span.text[:500]}
                                        for span in literature.spans[:12]
                                    ],
                                    language=request.language,
                                    idea_id=selected_id,
                                )
                            )
                            write("experiment.json", asdict(design))
                            from .design_audit import audit_design

                            write("design-audit.json", audit_design(asdict(design)))
                            step.status = "needs_human"
                            step.detail = "design status=%s; G2 requires human freeze" % design.status
                            emit("step_end", step.detail, step.step_id)

            else:
                runner = PipelineRunner(
                    store=self.store,
                    retriever=self._retriever(request.source, request.corpus_dir),
                    parser=self._parser(),
                    source_scope=[request.source],
                    run_output_dir=out / "run",
                    event_sink=event_sink,
                    query_planner=self.query_planner,
                    section_writer=self.section_writer,
                    idea_proposer=self.idea_proposer,
                    experiment_designer=self.experiment_designer,
                    strict_models=self.strict_models,
                    module_overrides=self.module_overrides,
                )
                pipeline_result = runner.run(
                    PipelineRequest(
                        topic=request.goal,
                        language=request.language,
                        venue_type=request.venue_type,
                        max_sources=request.max_sources,
                        run_dataset=request.run_dataset,
                        run_dir=request.run_dir,
                        run_seeds=request.run_seeds,
                        flow_mode=request.flow_mode,
                        g1_decision_file=request.g1_decision_file,
                        protocol_file=request.protocol_file,
                        claim_file=request.claim_file,
                        bibliography_file=request.bibliography_file,
                    )
                )
                pipeline_paths = write_pipeline_artifacts(
                    pipeline_result,
                    out,
                    claim_file=request.claim_file,
                    support_judge=self.support_judge,
                    strict_support=self.strict_models,
                )
                for key, value in pipeline_paths.items():
                    if not value:
                        continue
                    try:
                        relative = Path(value).resolve().relative_to(out.resolve()).as_posix()
                    except ValueError:
                        relative = Path(value).name
                    artifacts[relative] = relative
                stopped_at = pipeline_result.stopped_at
                gates = list(pipeline_result.gates)
                module_done = {
                    name: bool((pipeline_result.modules or {}).get(name))
                    for name in ("literature", "idea", "experiment", "run", "figure", "paper")
                }
                for step in steps:
                    if step.kind in module_done:
                        step.status = "done" if module_done[step.kind] else "skipped"
                        if step.status == "skipped":
                            step.detail = "not reached; stopped at %s" % (stopped_at or "gate")
                        elif step.gate:
                            step.detail = "gate %s requires human review" % step.gate
                    if step.kind == "run" and not request.run_dataset:
                        step.status = "skipped"
                        step.detail = "no run_dataset supplied; S5b not reached"

            checks = self._checks(plan.route, literature, idea_cards, design, pipeline_result)
            status = self._status(
                plan.route, literature, idea_cards, pipeline_result, checks, stopped_at
            )
            if pipeline_result is not None:
                evidence_packages = list(pipeline_result.evidence_packages)
            else:
                modules: Dict[str, Any] = {}
                if literature is not None:
                    modules["literature"] = literature.to_dict()
                if idea_result is not None:
                    modules["idea"] = asdict(idea_result)
                if design is not None:
                    modules["experiment"] = asdict(design)
                evidence_packages = summarize_evidence_packages(modules)
            for step in steps:
                if step.kind == "report":
                    step.status = "done"
                    step.detail = "task-report.md"
            artifacts["task-report.md"] = "task-report.md"
            artifacts["task.json"] = "task.json"
            report = self._report(
                plan, steps, literature, idea_cards, design, pipeline_result,
                checks, artifacts, evidence_packages, stopped_at,
            )
            with open(str(out / "task-report.md"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(report)
            return self._finish(
                out, plan, steps, status, artifacts, checks, warnings, started,
                evidence_packages=evidence_packages,
                stopped_at=stopped_at,
                gates=gates,
            )

        except ModelTurnPending as exc:
            # A keyless host-agent profile deferred this step. That is a handoff, not a
            # failure: the caller answers the turn and re-runs, and the step replays it.
            warnings.append("awaiting host model: %s" % exc)
            for step in steps:
                if step.status == "running":
                    step.status = "blocked"
            handoff = {
                "schema_version": "host-model-handoff-0.1",
                "status": "awaiting_host_model",
                "turn_id": exc.turn_id,
                "messages_sha256": exc.messages_sha256,
                "task_id": plan.task_id,
                "goal": plan.goal,
                "resume": (
                    "answer turn %s (research_model_respond or host-model respond), "
                    "then re-run this task" % exc.turn_id
                ),
                "boundary": (
                    "a host answer is capability output, not evidence: gates, audits and "
                    "signature rules are unchanged"
                ),
            }
            write_json_atomic(out / "awaiting-host-model.json", handoff)
            artifacts["awaiting-host-model.json"] = "awaiting-host-model.json"
            return self._finish(
                out, plan, steps, "awaiting_host_model", artifacts, checks, warnings, started,
                evidence_packages=evidence_packages,
                stopped_at="host_model",
                gates=gates,
            )

        except Exception as exc:
            warnings.append("%s: %s" % (type(exc).__name__, exc))
            for step in steps:
                if step.status == "running":
                    step.status = "failed"
            return self._finish(
                out, plan, steps, "failed", artifacts, checks, warnings, started,
                error="%s: %s" % (type(exc).__name__, exc),
                evidence_packages=evidence_packages,
                stopped_at=stopped_at,
                gates=gates,
            )

    def _checks(
        self,
        route: str,
        literature: Optional[LiteratureResult],
        idea_cards: List[IdeaCard],
        design: Optional[ExperimentDesign],
        pipeline_result: Any,
    ) -> List[Dict[str, str]]:
        checks: List[Dict[str, str]] = []

        def add(name: str, status: str, detail: str) -> None:
            checks.append({"name": name, "status": status, "detail": detail})

        if literature is not None:
            add(
                "sources",
                "pass" if literature.hits else "fail",
                "%d sources" % len(literature.hits),
            )
            add(
                "locatable_spans",
                "pass" if literature.spans else "fail",
                "%d spans" % len(literature.spans),
            )
            add(
                "coverage",
                "pass" if literature.brief and literature.brief.saturation != "insufficient" else "warn",
                literature.brief.saturation if literature.brief else "unknown",
            )
        if route == "hypothesis_design":
            add(
                "falsifiable_candidates",
                "pass" if idea_cards and all(card.falsification for card in idea_cards) else "fail",
                "%d candidates" % len(idea_cards),
            )
            add(
                "design_draft",
                "pass" if design and design.status == "ready_for_g2" else "warn",
                design.status if design else "missing",
            )
        if pipeline_result is not None:
            modules = pipeline_result.modules
            run_module = modules.get("run") or {}
            add(
                "pipeline_status",
                "pass" if pipeline_result.status in ("needs_human", "draft_ready") else "warn",
                pipeline_result.status,
            )
            add(
                "run_capsule",
                "pass" if (run_module.get("capsule") or {}).get("status") == "completed" else "warn",
                str((run_module.get("capsule") or {}).get("status") or "not run"),
            )
            add(
                "paper_draft",
                "pass" if (modules.get("paper") or {}).get("draft") else "warn",
                "%d sections" % len((modules.get("paper") or {}).get("draft") or []),
            )
        return checks

    @staticmethod
    def _status(
        route: str,
        literature: Optional[LiteratureResult],
        idea_cards: List[IdeaCard],
        pipeline_result: Any,
        checks: List[Dict[str, str]],
        stopped_at: str = "",
    ) -> str:
        if any(item["status"] == "fail" for item in checks):
            return "needs_evidence"
        if stopped_at == "Q0":
            return "needs_evidence"
        if stopped_at in ("G1", "G2"):
            return "needs_human"
        if pipeline_result is not None:
            if pipeline_result.status == "needs_human":
                return "needs_human"
            if pipeline_result.status.startswith("blocked"):
                return "needs_evidence" if pipeline_result.status == "blocked_q0" else "needs_human"
            return "completed"
        if route == "literature_review":
            return "completed" if literature and literature.spans else "needs_evidence"
        if route == "hypothesis_design":
            return "completed" if idea_cards else "needs_evidence"
        return "completed"

    def _report(
        self,
        plan: TaskPlan,
        steps: List[TaskStep],
        literature: Optional[LiteratureResult],
        idea_cards: List[IdeaCard],
        design: Optional[ExperimentDesign],
        pipeline_result: Any,
        checks: List[Dict[str, str]],
        artifacts: Dict[str, str],
        evidence_packages: Optional[List[Dict[str, Any]]] = None,
        stopped_at: str = "",
    ) -> str:
        lines = [
            "# 任务完成报告",
            "",
            "- 任务：%s" % plan.goal,
            "- Task：`%s`" % plan.task_id,
            "- 路由：`%s`" % plan.route,
            "- 交付物：`%s`" % plan.deliverable,
            "- 来源：`%s`" % plan.source,
            "- 流程模式：`%s`" % plan.flow_mode,
            "- 停止点：`%s`" % (stopped_at or "none"),
            "",
            "## 执行计划与检查点",
            "",
        ]
        for step in steps:
            lines.append("- [%s] %s · %s%s" % (
                step.status.upper(), step.step_id, step.label,
                (" · " + step.detail) if step.detail else "",
            ))
        if literature is not None:
            lines += ["", "## 文献覆盖", ""]
            if literature.brief:
                lines.append(literature.brief.summary.split("\n")[0])
            lines.append("")
            for hit in literature.hits[:8]:
                lines.append(
                    "- `%s` · %s · %s"
                    % (hit.source_id, hit.title, "全文" if hit.full_text else "摘要线索，不进入证据")
                )
            if literature.coverage.gaps:
                lines += ["", "### Gap", ""]
                for gap in literature.coverage.gaps[:8]:
                    lines.append("- `%s` · %s" % (gap.code, gap.message))
        if idea_cards:
            lines += ["", "## 候选假设", ""]
            for card in idea_cards:
                lines.append(
                    "- **%s** %s\n  - 证据：%s\n  - 否证：%s"
                    % (card.idea_id, card.title, "、".join(card.evidence_refs), card.falsification)
                )
        if design is not None:
            lines += [
                "", "## 实验设计草案", "",
                "- status：`%s`" % design.status,
                "- baseline：%s" % design.baseline,
                "- metric：%s" % (design.primary_metric or "待人工补全"),
                "- seeds：%d" % design.seeds,
                "- G2：需要人工冻结 ProtocolCard",
            ]
        if pipeline_result is not None:
            lines += ["", "## Pipeline 产物", ""]
            for key, value in (pipeline_result.modules or {}).items():
                status = value.get("status") if isinstance(value, dict) else None
                lines.append("- `%s` · %s" % (key, status or "—"))
            lines += ["", "完整报告见 `report.md`；工作稿见 `paper.md`。"]
        if evidence_packages:
            lines += ["", "## 证据包状态", ""]
            for package in evidence_packages:
                lines.append(
                    "- `%s` · %s · **%s** · %s"
                    % (
                        package.get("stage", ""),
                        package.get("label", ""),
                        package.get("status", ""),
                        package.get("detail", ""),
                    )
                )
        lines += ["", "## 质量检查", ""]
        for check in checks:
            lines.append("- `%s` · %s · %s" % (check["name"], check["status"], check["detail"]))
        claim_bound = bool(
            pipeline_result
            and (pipeline_result.modules.get("paper") or {}).get("claims")
        )
        if pipeline_result is not None:
            pending_gates = [
                str(gate.get("gate"))
                for gate in pipeline_result.gates
                if gate.get("status") not in ("pass", "ready")
            ]
        else:
            pending_gates = list(plan.human_gates)
        lines += [
            "",
            "## 人工门与下一步",
            "",
            "- 本任务没有自动签署任何 Claim、Closure 或导出。",
            "- 需要人工处理：" + ("、".join(pending_gates) if pending_gates else "无未通过门禁；导出仍需要人工签核"),
            (
                "- 已绑定人签 claim；接下来检查 closure report，完成人工导出签核。"
                if claim_bound else
                "- 若后续要进入论文结果，必须先完成 claim 人签并复用原 run 重新绑定。"
            ),
            "",
            "## 产物",
            "",
        ]
        for name in sorted(artifacts):
            lines.append("- `%s`" % name)
        lines += [
            "",
            "## 证据边界",
            "",
            "本报告是任务执行记录，不是论文结论；fixture 不可引用，摘要不能当全文证据，结果数字必须来自人签 claim。",
        ]
        return "\n".join(lines).rstrip() + "\n"

    def _finish(
        self,
        out: Path,
        plan: TaskPlan,
        steps: List[TaskStep],
        status: str,
        artifacts: Dict[str, str],
        checks: List[Dict[str, str]],
        warnings: List[str],
        started: str,
        error: str = "",
        evidence_packages: Optional[List[Dict[str, Any]]] = None,
        stopped_at: str = "",
        gates: Optional[List[Dict[str, str]]] = None,
    ) -> TaskExecution:
        failure: Dict[str, Any] = {}
        if error:
            artifacts = dict(artifacts)
            failure = _failure_record(plan, error, warnings)
            artifacts["failure.json"] = "failure.json"
        execution = TaskExecution(
            task_id=plan.task_id,
            plan=plan,
            status=status,
            steps=steps,
            artifacts=dict(artifacts),
            checks=list(checks),
            warnings=list(warnings),
            started_at=started,
            finished_at=_now(),
            evidence_packages=list(evidence_packages or []),
            stopped_at=stopped_at,
            gates=list(gates or []),
            error=error,
            failure=failure,
        )
        write_json_atomic(out / "task.json", execution.to_dict())
        try:
            from .loop_capsule import write_loop_capsule

            write_loop_capsule(out)
            execution.artifacts["loop-capsule.json"] = "loop-capsule.json"
            write_json_atomic(out / "task.json", execution.to_dict())
        except Exception as exc:
            execution.warnings.append(
                "loop_capsule: %s: %s" % (type(exc).__name__, exc)
            )
            write_json_atomic(out / "task.json", execution.to_dict())
        if error:
            with open(str(out / "task-error.txt"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(error + "\n")
            if failure:
                write_json_atomic(out / "failure.json", failure)
        return execution

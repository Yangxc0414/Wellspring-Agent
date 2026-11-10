"""Compose the S1→S6→S8–S12 (and optional grant) vertical slice.

The default is deterministic and fixture-backed; optional model boundaries may
be injected. S5 only runs local protocol-validation datasets and writes an
unsigned claim draft. The pipeline never signs claims, passes human gates, or
closes evidence; it exposes where those actions are still required.
"""

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .adapters.fixture_retriever import FixtureRetriever
from .adapters.simple_parser import SimpleParser
from .contracts import ExperimentDesign, FigureEdge, FigureNode, RunRequest
from .evidence_packages import summarize_evidence_packages
from .storage import read_json
from .flow import (
    FlowError,
    load_g1_decision,
    protocol_binding,
    q0_decision,
    validate_flow_mode,
    validate_frozen_protocol,
)
from .modules.experiment import ExperimentDesignAgent, ExperimentRequest
from .modules.figure import FigureAgent, FigureRequest, build_result_figure
from .modules.grant import GrantAgent, GrantRequest
from .modules.idea import (
    IdeaAgent,
    IdeaRequest,
    load_idea_result,
    prior_art_hits_from_literature,
)
from .modules.literature import LiteratureAgent, LiteratureRequest
from .modules.paper import PaperAgent, PaperRequest, render_paper_markdown
from .manuscript import build_manuscript, render_manuscript_markdown
from .modules.run import RunAgent
from .literature_ledger import build_source_ledger
from .literature_synthesis import synthesize_sources_deterministic
from .design_audit import audit_design
from .idea_review import build_idea_review
from .run_contract import build_run_contract, verify_run_contract
from .ports import ParserPort, RetrieverPort
from .run_events import (
    COMMITTED_KIND,
    EVENT_FILENAME,
    REJECTED_KIND,
    append_event,
    commit_boundary,
    verify_events,
    write_events,
)
from .specs import SpecStore


class PipelineError(RuntimeError):
    pass


def evaluate_g3_g5(
    closure_status: str = "",
    *,
    closure_unresolved: Optional[List[str]] = None,
    has_ea: bool = False,
    has_signed_claim: bool = False,
) -> List[Dict[str, str]]:
    """The single authority for the G3/G5 rows in ``PipelineResult.gates``.

    ``closure_status`` is only known after ``write_pipeline_artifacts`` has read
    the closure report, so both the runner and the artifact writer call this
    function instead of one of them editing the other's dicts in place. An
    unknown closure is fail-closed: G3 provisional, G5 export closed.
    """
    detail = ", ".join(str(item) for item in (closure_unresolved or [])) or "unresolved checks"
    if closure_status == "ready":
        return [
            {
                "gate": "G3", "status": "pass",
                "reason": "paper contract and slots are bound; closure is ready",
            },
            {
                "gate": "G5", "status": "needs_human",
                "reason": "closure ready; export still requires a human signature",
            },
        ]
    if closure_status == "blocked":
        return [
            {
                "gate": "G3", "status": "blocked",
                "reason": "paper contract/figure are provisional",
            },
            {
                "gate": "G5", "status": "blocked",
                "reason": "closure blocked: %s" % detail,
            },
        ]
    g5_reason = (
        "EA exists but no Claim/Closure; export is closed"
        if has_ea and not has_signed_claim
        else "no EA/Closure; export is closed"
    )
    return [
        {"gate": "G3", "status": "blocked", "reason": "paper contract/figure are provisional"},
        {"gate": "G5", "status": "blocked", "reason": g5_reason},
    ]


@dataclass
class PipelineRequest:
    topic: str
    language: str = "zh"
    venue_type: str = "zh_core_journal"
    grant_scheme: str = ""
    figure_style: str = "modern"
    max_sources: int = 6
    primary_metric: str = ""
    controls: List[str] = field(default_factory=list)
    budget: str = ""
    claim_refs: List[str] = field(default_factory=list)
    claim_statements: List[str] = field(default_factory=list)
    claim_assertions: List[Dict[str, Any]] = field(default_factory=list)
    run_dataset: str = ""
    run_dir: str = ""
    run_seeds: int = 3
    run_protocol_id: str = "P-pipeline-s5"
    run_harness: Dict[str, Any] = field(default_factory=dict)
    protocol_file: str = ""
    bibliography_file: str = ""
    run_id: str = ""
    flow_mode: str = "review"
    g1_decision_file: str = ""
    idea_file: str = ""
    design_file: str = ""
    study_design_file: str = ""
    claim_file: str = ""
    synthesis_enabled: bool = True
    study_dataset: str = ""
    study_seeds: int = 0
    study_budget: int = 60
    study_root: str = ""
    adaptive_retrieval: bool = False


@dataclass
class PipelineResult:
    run_id: str
    topic: str
    status: str
    fixture_mode: bool
    modules: Dict[str, Any]
    gates: List[Dict[str, str]]
    warnings: List[str]
    spec_versions: Dict[str, str]
    evidence_packages: List[Dict[str, Any]] = field(default_factory=list)
    flow_mode: str = "review"
    stopped_at: str = ""
    manuscript: Optional[Dict[str, Any]] = None
    manuscript_audit: Optional[Dict[str, Any]] = None
    argument_ledger: Optional[Dict[str, Any]] = None
    claim_registry: Optional[Dict[str, Any]] = None
    literature_ledger: Optional[Dict[str, Any]] = None
    design_audit: Optional[Dict[str, Any]] = None
    idea_review: Optional[Dict[str, Any]] = None
    run_contract: Optional[Dict[str, Any]] = None
    run_contract_check: Optional[Dict[str, Any]] = None
    study: Optional[Dict[str, Any]] = None
    events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PipelineRunner:
    MODULES = ("literature", "idea", "experiment", "figure", "paper", "grant")

    def __init__(
        self,
        store: Optional[SpecStore] = None,
        retriever: Optional[RetrieverPort] = None,
        parser: Optional[ParserPort] = None,
        source_scope: Optional[List[str]] = None,
        run_output_dir: Optional[Path] = None,
        event_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        query_planner: Optional[Callable[[str], Optional[List[str]]]] = None,
        section_writer: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, str]]]] = None,
        idea_proposer: Optional[Callable[[Dict[str, Any]], Optional[List[Dict[str, Any]]]]] = None,
        experiment_designer: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
        strict_models: bool = False,
        module_overrides: Optional[Dict[str, Any]] = None,
        module_factories: Optional[Dict[str, Callable[[Any], Any]]] = None,
    ):
        self._events: List[Dict[str, Any]] = []
        self.store = store or SpecStore()
        self.specs = {module_id: self.store.load(module_id) for module_id in self.MODULES}
        self.retriever = retriever
        self.parser = parser
        self.source_scope = list(source_scope) if source_scope else ["fixture"]
        self.run_output_dir = Path(run_output_dir) if run_output_dir else None
        self.event_sink = event_sink
        self.query_planner = query_planner
        self.section_writer = section_writer
        self.idea_proposer = idea_proposer
        self.experiment_designer = experiment_designer
        self.strict_models = strict_models
        self.module_overrides = dict(module_overrides or {})
        self.module_factories = {
            "literature": lambda spec: LiteratureAgent(
                spec,
                self.retriever or FixtureRetriever(),
                self.parser or SimpleParser(),
                query_planner=self.query_planner,
            ),
            "idea": lambda spec: IdeaAgent(
                spec, proposer=self.idea_proposer, strict_model=self.strict_models
            ),
            "experiment": lambda spec: ExperimentDesignAgent(
                spec, designer=self.experiment_designer, strict_model=self.strict_models
            ),
            "figure": lambda spec: FigureAgent(spec),
            "paper": lambda spec: PaperAgent(spec, section_writer=self.section_writer),
            "grant": lambda spec: GrantAgent(spec),
            "run": lambda spec: RunAgent(spec),
        }
        self.module_factories.update(module_factories or {})

    def _agent(self, module_id: str):
        if module_id in self.module_overrides:
            return self.module_overrides[module_id]
        if module_id == "run":
            spec = self.store.load("run")
        else:
            spec = self.specs[module_id]
        factory = self.module_factories.get(module_id)
        if factory is None:
            raise PipelineError("no module factory for: " + module_id)
        return factory(spec)

    def _emit(
        self,
        event_type: str,
        stage: Optional[str],
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        # The append-only chain is the authority. It is written even when no
        # event_sink is attached, so a run always has an auditable trace.
        payload: Dict[str, Any] = {"message": message}
        if data:
            payload["data"] = data
        try:
            append_event(self._events, event_type, phase=stage or "", payload=payload)
        except Exception:
            # Observability must never change research execution.
            pass
        if self.event_sink is None:
            return
        event: Dict[str, Any] = {"type": event_type, "stage": stage, "message": message}
        if data:
            event["data"] = data
        try:
            self.event_sink(event)
        except Exception:
            # Observability must never change research execution.
            pass

    def _run_id(self, provided: str) -> str:
        if provided:
            return provided
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return "PIPE-%s-%s" % (stamp, uuid.uuid4().hex[:6])

    def run(self, request: PipelineRequest) -> PipelineResult:
        if not request.topic.strip():
            raise PipelineError("topic is required")
        if request.language not in ("zh", "en"):
            raise PipelineError("language must be zh or en")
        flow_mode = validate_flow_mode(request.flow_mode)
        self._events = []  # one run = one chain; a reused runner must not splice two runs
        claim_refs = list(request.claim_refs)
        claim_statements = list(request.claim_statements)
        claim_assertions = list(request.claim_assertions)
        claim_signed = False
        if request.claim_file:
            claim_path = Path(request.claim_file)
            if not claim_path.is_file():
                raise PipelineError("claim file not found: " + str(claim_path))
            claim = json.loads(claim_path.read_text(encoding="utf-8"))
            if claim.get("status") != "supported" or not claim.get("evidence_refs"):
                raise PipelineError("claim file must be supported and reference at least one EA")
            claim_signed = bool(str(claim.get("human_reason") or "").strip())
            claim_id = str(claim.get("claim_id") or "").strip()
            claim_refs = [claim_id] if claim_id else claim_refs
            statement = str(claim.get("statement") or "").strip()
            if statement:
                claim_statements = [statement]
            claim_assertions = list(claim.get("assertions") or claim_assertions)
        run_id = self._run_id(request.run_id)
        run_dataset = request.run_dataset
        if not run_dataset and request.run_dir:
            capsule_path = Path(request.run_dir) / "run-capsule.json"
            if capsule_path.is_file():
                try:
                    capsule_payload = json.loads(capsule_path.read_text(encoding="utf-8"))
                    dataset_id = str(capsule_payload.get("dataset_id") or "").lower()
                    if "chemlab" in dataset_id:
                        run_dataset = "chemlab"
                    elif "breast" in dataset_id:
                        run_dataset = "breast_cancer"
                    elif "iris" in dataset_id:
                        run_dataset = "iris"
                except (OSError, ValueError):
                    run_dataset = ""
        retriever = self.retriever or FixtureRetriever()
        fixture_mode = bool(getattr(retriever, "fixture_mode", False))
        has_local_run = bool(run_dataset or request.run_dir)
        openalex_live = "openalex" in self.source_scope
        warnings: List[str] = [
            (
                "fixture retrieval; S5 local run is a separate evidence arm; no API/claims"
                if has_local_run else
                "fixture pipeline; no real retrieval, no API, no experiment"
            )
            if fixture_mode else
            (
                "openalex live retrieval; abstracts are SourceHit clues only; OA full texts are fetched by humans; no claims"
                if openalex_live else
                "real-text pipeline; S1 reads frozen CC-BY body text; no API/run/EA/claims"
            )
        ]
        if flow_mode == "review":
            warnings.append(
                "review mode reports gates after stages; use flow_mode=strict for "
                "pre-registration and claim-bound runs"
            )
        modules: Dict[str, Any] = {}
        manuscript_bundle: Optional[Dict[str, Any]] = None
        source_ledger: Optional[Dict[str, Any]] = None
        design_audit_result: Optional[Dict[str, Any]] = None
        idea_review_result: Optional[Dict[str, Any]] = None
        run_contract_result: Optional[Dict[str, Any]] = None
        run_contract_check_result: Optional[Dict[str, Any]] = None

        def finish_early(
            status: str, stopped_at: str, gates: List[Dict[str, str]]
        ) -> PipelineResult:
            deduped: List[str] = []
            for warning in warnings:
                if warning not in deduped:
                    deduped.append(warning)
            spec_versions = {key: spec.version for key, spec in self.specs.items()}
            packages = summarize_evidence_packages(modules, gates)
            self._emit(
                "run_complete", None, "pipeline stopped at %s" % stopped_at,
                {"status": status, "stopped_at": stopped_at, "gates": gates, "warnings": deduped},
            )
            return PipelineResult(
                run_id=run_id,
                topic=request.topic,
                status=status,
                fixture_mode=fixture_mode,
                modules=modules,
                gates=gates,
                warnings=deduped,
                spec_versions=spec_versions,
                evidence_packages=packages,
                flow_mode=flow_mode,
                stopped_at=stopped_at,
                literature_ledger=source_ledger,
                design_audit=design_audit_result,
                idea_review=idea_review_result,
                run_contract=run_contract_result,
                run_contract_check=run_contract_check_result,
                events=list(self._events),
            )

        self._emit(
            "run_start", None, "pipeline started",
            {
                "run_id": run_id,
                "topic": request.topic,
                "fixture_mode": fixture_mode,
                "stages": [s for s in ("literature", "idea", "experiment", "run", "figure", "paper", "grant")
                           if s != "grant" or bool(request.grant_scheme)],
            },
        )

        self._emit("stage_start", "literature", "检索与阅读")
        if request.adaptive_retrieval:
            # The first real loopback in this runtime: the S1 coverage verdict
            # decides the next run's retrieval budget. It never crosses a gate.
            from .research_cycle import run_literature_cycle

            cycle = run_literature_cycle(
                self._agent("literature"),
                request.topic,
                initial_budget=request.max_sources,
                source_scope=list(self.source_scope),
                run_id=run_id + "-lit",
                events=self._events,
            )
            literature = cycle.final
            modules["adaptive_cycle"] = cycle.to_dict()
            warnings.append(cycle.warning())
        else:
            literature = self._agent("literature").run(
                LiteratureRequest(
                    question=request.topic,
                    max_sources=request.max_sources,
                    source_scope=list(self.source_scope),
                    run_id=run_id + "-lit",
                    coverage_plan=True,
                    followup_plan=True,
                )
            )
        modules["literature"] = literature.to_dict()
        source_ledger = build_source_ledger(
            modules["literature"], request.topic, list(self.source_scope)
        )
        warnings.extend(literature.warnings)
        self._emit(
            "stage_end", "literature",
            "%d sources / %d spans · %s (%d%%)"
            % (
                len(literature.hits),
                len(literature.spans),
                literature.brief.saturation if literature.brief else "unknown",
                round((literature.brief.coverage_score if literature.brief else 0) * 100),
            ),
            {
                "sources": len(literature.hits),
                "spans": len(literature.spans),
                "fixture_mode": literature.fixture_mode,
                "status": literature.status,
                "coverage_score": literature.brief.coverage_score if literature.brief else None,
                "saturation": literature.brief.saturation if literature.brief else None,
                "facets_covered": len([f for f in literature.brief.facets if f.covered]) if literature.brief else 0,
            },
        )
        q0 = q0_decision(literature)
        modules["q0"] = q0
        synthesis_matrix: Dict[str, Any] = {}
        if request.synthesis_enabled:
            sources_for_synthesis: Dict[str, Dict[str, Any]] = {}
            for hit in literature.hits:
                sources_for_synthesis.setdefault(
                    hit.source_id,
                    {
                        "source_id": hit.source_id,
                        "ref_id": hit.source_id,
                        "title": hit.title,
                        "full_text": bool(hit.full_text),
                        "spans": [],
                    },
                )
            for span in literature.spans:
                entry = sources_for_synthesis.setdefault(
                    span.source_id,
                    {
                        "source_id": span.source_id,
                        "ref_id": span.source_id,
                        "title": span.source_id,
                        "full_text": True,
                        "spans": [],
                    },
                )
                entry["spans"].append({"span_id": span.span_id, "text": span.text})
            synthesis_matrix = synthesize_sources_deterministic(
                list(sources_for_synthesis.values())
            )
            if synthesis_matrix["themes"]:
                modules["synthesis"] = synthesis_matrix
                self._emit(
                    "stage_end", "literature",
                    "S1b deterministic synthesis: %d themes / %d sources"
                    % (synthesis_matrix["theme_count"], synthesis_matrix["source_count"]),
                    {
                        "themes": synthesis_matrix["theme_count"],
                        "sources": synthesis_matrix["source_count"],
                        "unused_sources": len(synthesis_matrix["unused_sources"]),
                        "model": synthesis_matrix["model"],
                    },
                )
        if q0["status"] != "pass":
            warnings.append("Q0 blocked: " + q0["reason"])
            if flow_mode == "strict":
                return finish_early(
                    "blocked_q0", "Q0",
                    [
                        q0,
                        {"gate": "G1", "status": "not_started", "reason": "not reached; Q0 blocked"},
                        {"gate": "G2", "status": "not_started", "reason": "not reached; Q0 blocked"},
                        {"gate": "G3", "status": "not_started", "reason": "not reached; Q0 blocked"},
                        {"gate": "G5", "status": "not_started", "reason": "not reached; Q0 blocked"},
                    ],
                )

        self._emit("stage_start", "idea", "假设收敛")
        prior_art_agent = self._agent("literature")

        def _prior_art_search(
            query: str, limit: int
        ) -> List[Dict[str, Any]]:
            result = prior_art_agent.run(
                LiteratureRequest(
                    question=query,
                    max_sources=max(1, min(limit, 3)),
                    source_scope=self.source_scope[:1] or ["fixture"],
                    language=request.language,
                    coverage_plan=False,
                )
            )
            return prior_art_hits_from_literature(result, limit)

        # S1/S1b already computed the structured receipts; pass them to S2 so a
        # candidate can be bound to a cross-source theme it actually cites,
        # instead of S2 re-clustering raw sentences with no notion of a gap.
        gap_pack = {
            "gaps": [asdict(gap) for gap in literature.coverage.gaps],
            "brief_gaps": list(literature.brief.gaps) if literature.brief else [],
            "facets": [
                {
                    "facet": facet.facet,
                    "source_ids": list(facet.source_ids),
                    "span_count": facet.span_count,
                    "covered": facet.covered,
                }
                for facet in (literature.brief.facets if literature.brief else [])
            ],
            "themes": list((synthesis_matrix or {}).get("themes") or []),
        }
        if request.idea_file:
            idea = load_idea_result(request.idea_file, run_id=run_id + "-idea")
            warnings.append(
                "idea set reused from %s: this run does not regenerate candidates, because a G1 "
                "decision binds to the exact cards it approved" % request.idea_file
            )
        else:
            idea = self._agent("idea").run(
                IdeaRequest(
                    topic=request.topic,
                    spans=literature.spans,
                    max_candidates=3,
                    run_id=run_id + "-idea",
                    language=request.language,
                    prior_art_searcher=_prior_art_search,
                    gap_pack=gap_pack,
                )
            )
        modules["idea"] = asdict(idea)
        idea_review_result = build_idea_review(modules["idea"], modules.get("literature") or {})
        warnings.extend(idea.warnings)
        self._emit(
            "stage_end", "idea",
            "%d candidate hypotheses · %d multi-ref · %d lenses"
            % (
                len(idea.candidates),
                idea.brief.multi_ref_candidates if idea.brief else 0,
                len(idea.brief.lenses) if idea.brief else 0,
            ),
            {
                "candidates": len(idea.candidates),
                "status": idea.status,
                "multi_ref_candidates": idea.brief.multi_ref_candidates if idea.brief else 0,
                "multi_source_candidates": idea.brief.multi_source_candidates if idea.brief else 0,
                "lenses": idea.brief.lenses if idea.brief else {},
            },
        )

        g1_decision = None
        if request.g1_decision_file:
            try:
                g1_decision = load_g1_decision(
                    Path(request.g1_decision_file), idea.candidates
                )
                modules["g1_decision"] = g1_decision
                # The idea artifact must stop asking for a G1 decision once one was applied,
                # otherwise the closure capsule keeps reporting G1_IDEA_SELECTION_REQUIRED while
                # the gate ledger says pass.
                chosen = str(g1_decision.get("selected_idea_id") or "")
                modules["idea"]["status"] = "selected"
                for card in modules["idea"].get("candidates") or []:
                    if str(card.get("idea_id")) == chosen:
                        card["status"] = "selected"
            except FlowError as exc:
                warnings.append("G1 decision rejected: " + str(exc))
                if flow_mode == "strict":
                    return finish_early(
                        "blocked_g1", "G1",
                        [
                            q0,
                            {"gate": "G1", "status": "blocked", "reason": str(exc)},
                            {"gate": "G2", "status": "not_started", "reason": "not reached; G1 blocked"},
                            {"gate": "G3", "status": "not_started", "reason": "not reached; G1 blocked"},
                            {"gate": "G5", "status": "not_started", "reason": "not reached; G1 blocked"},
                        ],
                    )
        if flow_mode == "strict" and g1_decision is None:
            reason = (
                "human-selected idea required; provide a G1 decision file"
                if idea.candidates
                else "no candidate hypothesis; cannot enter S4"
            )
            return finish_early(
                "needs_g1", "G1",
                [
                    q0,
                    {"gate": "G1", "status": "needs_human" if idea.candidates else "blocked", "reason": reason},
                    {"gate": "G2", "status": "not_started", "reason": "not reached; G1 pending"},
                    {"gate": "G3", "status": "not_started", "reason": "not reached; G1 pending"},
                    {"gate": "G5", "status": "not_started", "reason": "not reached; G1 pending"},
                ],
            )
        selected_idea_id = (
            g1_decision["selected_idea_id"]
            if g1_decision
            else (idea.candidates[0].idea_id if idea.candidates else "")
        )

        selected_card = next(
            (card for card in idea.candidates if card.idea_id == selected_idea_id),
            idea.candidates[0] if idea.candidates else None,
        )
        hypothesis = selected_card.hypothesis if selected_card else "待人工补全"
        baseline = "待人工补全"
        primary_metric = request.primary_metric
        controls = list(request.controls)
        seeds = 3
        budget = request.budget
        if run_dataset == "chemlab":
            hypothesis = (
                "Ridge on B/C Morgan fingerprints predicts LCAP conversion better than a mean baseline."
            )
            baseline = "mean predictor (DummyRegressor)"
            primary_metric = request.primary_metric or "delta_r2"
            controls = list(request.controls) or ["mean baseline"]
            seeds = request.run_seeds
            budget = request.budget or "%d seeds x 418 train / 22 test" % request.run_seeds
        elif run_dataset in ("iris", "breast_cancer"):
            hypothesis = (
                "StandardScaler + logistic regression exceeds the majority-class baseline "
                "on the fixed protocol."
            )
            baseline = "majority class"
            primary_metric = request.primary_metric or "accuracy"
            controls = list(request.controls) or ["majority baseline"]
            seeds = request.run_seeds
            budget = request.budget or "%d seeds x stratified split" % request.run_seeds
        self._emit("stage_start", "experiment", "实验设计草稿")
        if request.design_file:
            payload = read_json(Path(request.design_file))
            if not isinstance(payload, dict):
                raise PipelineError(
                    "design file is not a JSON object: " + request.design_file
                )
            design = ExperimentDesign(
                **{
                    key: payload[key]
                    for key in ExperimentDesign.__dataclass_fields__
                    if key in payload
                }
            )
            warnings.append(
                "design reused from %s: a frozen protocol binds to this design, so it is not "
                "regenerated in this run" % request.design_file
            )
        else:
            design = self._agent("experiment").run(
                ExperimentRequest(
                    question=request.topic,
                    hypothesis=hypothesis,
                    baseline=baseline,
                    primary_metric=primary_metric,
                    controls=controls,
                    seeds=seeds,
                    budget=budget,
                    evidence_refs=[span.span_id for span in literature.spans[:4]],
                    evidence=[
                        {"ref": span.span_id, "section": span.section, "text": span.text[:500]}
                        for span in literature.spans[:12]
                    ],
                    language=request.language,
                    idea_id=selected_idea_id,
                    run_id=run_id + "-design",
                )
            )
        modules["experiment"] = asdict(design)
        design_audit_result = audit_design(modules["experiment"])
        warnings.extend(design.warnings)
        self._emit(
            "stage_end", "experiment", "design status: %s" % design.status,
            {"status": design.status, "metric": design.primary_metric, "seeds": design.seeds},
        )

        study_result = None
        if request.study_dataset:
            # The search arm is an evidence arm of its own: it executes the memory x gate
            # design rather than the single fixed fit S5 performs, and it never impersonates a
            # run capsule. A plan that does not belong to this arm fails loudly, because
            # silently continuing would put prose where a result should be.
            from .study_from_idea import StudyFromIdeaError, execute_study_plan, plan_from_design

            study_root = Path(request.study_root) if request.study_root else (
                Path(self.run_output_dir or Path("pipeline-study")).parent / "studies"
            )
            if not (study_root.parent / "project.json").is_file():
                warnings.append(
                    "study package will land outside a research project, so `closure profiles "
                    "--project` and research_status cannot inventory it; pass --study-project "
                    "<project>/studies to keep it visible, or run study closure --study-dir "
                    "directly"
                )

            try:
                plan = plan_from_design(
                    modules["experiment"], request.study_dataset, request.study_seeds
                )
                study_result = execute_study_plan(
                    study_root / ("STUDY-%s" % run_id),
                    plan,
                    provenance={
                        "run_id": run_id,
                        "idea_id": selected_idea_id or "PIPELINE",
                        "idea_title": request.topic,
                        "hypothesis": design.hypothesis,
                        "falsification": str(
                            getattr(selected_card, "falsification", "") or ""
                        ),
                        "source": "pipeline_design",
                    },
                    seeds=(
                        list(range(1, request.study_seeds + 1))
                        if request.study_seeds
                        else None
                    ),
                    budget=request.study_budget,
                )
            except (StudyFromIdeaError, ValueError) as exc:
                raise PipelineError("study arm refused: %s" % exc)
            modules["study"] = study_result
            # Two designs coexist here: the arm's declared factorial and the S4 draft, which may
            # still be incomplete and waiting for a human. Saying so prevents a reader from taking
            # the executed numbers as evidence for the draft.
            audit_blockers = list((design_audit_result or {}).get("blockers") or [])
            if audit_blockers:
                warnings.append(
                    "study arm executed the design it declares on %s, not the S4 draft: the design "
                    "audit still reports %d blocker(s) for that draft (%s), so the executed study "
                    "is not evidence for it"
                    % (
                        request.study_dataset,
                        len(audit_blockers),
                        "; ".join(str(item) for item in audit_blockers[:2]),
                    )
                )
            decided = len(study_result.get("directional_supported") or [])
            undecided = len(study_result.get("interval_covers_zero") or [])
            planning = sorted(
                {
                    int(item["seeds_for_80pct"])
                    for item in (study_result.get("comparison") or {}).values()
                    if isinstance(item, dict) and item.get("seeds_for_80pct")
                }
            )
            hint = (
                "; at the observed effect sizes the cheapest comparison would need about %d seeds "
                "to have a chance of deciding" % planning[0]
                if planning
                else ""
            )
            warnings.append(
                "study arm executed; %d comparison(s) decide a direction, %d remain undecidable%s; "
                "claim and closure stay human-signed" % (decided, undecided, hint)
            )
            self._emit(
                "stage_end", "study", "search study executed: %s" % study_result["study_dir"],
                {
                    "directional_supported": study_result.get("directional_supported") or [],
                    "interval_covers_zero": study_result.get("interval_covers_zero") or [],
                    "underpowered": study_result.get("underpowered"),
                },
            )

        protocol = None
        if request.protocol_file:
            try:
                protocol = validate_frozen_protocol(
                    Path(request.protocol_file), asdict(design)
                )
                modules["protocol"] = {
                    key: value for key, value in protocol.items()
                    if not key.startswith("_")
                }
            except FlowError as exc:
                warnings.append("G2 protocol rejected: " + str(exc))
                if flow_mode == "strict":
                    return finish_early(
                        "blocked_g2", "G2",
                        [
                            q0,
                            {"gate": "G1", "status": "pass", "reason": "human-selected idea supplied"},
                            {"gate": "G2", "status": "blocked", "reason": str(exc)},
                            {"gate": "G3", "status": "not_started", "reason": "not reached; G2 blocked"},
                            {"gate": "G5", "status": "not_started", "reason": "not reached; G2 blocked"},
                        ],
                    )
                raise PipelineError("frozen protocol rejected: " + str(exc))
        if flow_mode == "strict" and protocol is None:
            reason = "S5 requires a frozen ProtocolCard matching the current design"
            return finish_early(
                "needs_g2", "G2",
                [
                    q0,
                    {"gate": "G1", "status": "pass", "reason": "human-selected idea supplied"},
                    {"gate": "G2", "status": "needs_human", "reason": reason},
                    {"gate": "G3", "status": "not_started", "reason": "not reached; G2 pending"},
                    {"gate": "G5", "status": "not_started", "reason": "not reached; G2 pending"},
                ],
            )

        self._emit("stage_start", "run", "复现执行")
        bibliography = None
        if request.bibliography_file:
            bibliography = json.loads(Path(request.bibliography_file).read_text(encoding="utf-8"))
            if bibliography.get("status") != "verified_datacite_snapshot" or bibliography.get("entry_count", 0) < 2:
                raise PipelineError("bibliography card must be verified_datacite_snapshot with >=2 entries")
            modules["bibliography"] = bibliography
        run_module = None
        if request.run_dir:
            run_dir = Path(request.run_dir)
            capsule_path = run_dir / "run-capsule.json"
            ea_path = run_dir / "ea.json"
            if not capsule_path.is_file() or not ea_path.is_file():
                raise PipelineError("run_dir must contain run-capsule.json and ea.json")
            capsule = json.loads(capsule_path.read_text(encoding="utf-8"))
            evidence = json.loads(ea_path.read_text(encoding="utf-8"))
            claim_draft_path = run_dir / "claim-draft.json"
            run_module = {
                "capsule": capsule,
                "evidence": evidence,
                "paths": {
                    "capsule": str(capsule_path),
                    "metrics": evidence.get("path", ""),
                    "ea": str(ea_path),
                },
                "status": capsule.get("status", "failed"),
                "claim_draft": str(claim_draft_path) if claim_draft_path.is_file() else "",
                "claim_draft_record": (
                    json.loads(claim_draft_path.read_text(encoding="utf-8"))
                    if claim_draft_path.is_file() else None
                ),
                "active_harness": request.run_harness,
            }
            fig_manifest = run_dir / "result-figure.manifest.json"
            if fig_manifest.is_file():
                run_module["result_figure"] = {
                    "figure_id": json.loads(fig_manifest.read_text(encoding="utf-8")).get("figure_id", ""),
                    "manifest": json.loads(fig_manifest.read_text(encoding="utf-8")),
                    "paths": {"svg": str(run_dir / "result-figure.svg"), "manifest": str(fig_manifest)},
                }
            modules["run"] = run_module
            warnings.append("reused existing RunCapsule/EA from run_dir; no new run executed")
        elif run_dataset:
            if self.run_output_dir is None:
                raise PipelineError("run_dataset requires run_output_dir")
            run_result = self._agent("run").execute(
                RunRequest(
                    protocol_id=(
                        str(protocol.get("protocol_id") or request.run_protocol_id)
                        if protocol else request.run_protocol_id
                    ),
                    protocol_sha256=(
                        str(protocol.get("design_sha256") or "") if protocol else ""
                    ),
                    dataset=run_dataset,
                    seeds=request.run_seeds,
                ),
                self.run_output_dir,
            )
            capsule = run_result["capsule"]
            draft_path = self.run_output_dir / "claim-draft.json"
            if run_dataset == "chemlab":
                deltas = [item["delta_r2"] for item in capsule["metrics_by_seed"]]
                statement = (
                    "On the local ChemLab protocol, Ridge improves R2 over a mean baseline "
                    "by %.3f on average over seeds %s." % (sum(deltas) / len(deltas), capsule["seeds"])
                )
            else:
                statement = (
                    "On the local %s protocol, mean %s is %.3f over seeds %s."
                    % (run_dataset, capsule["metric_name"], capsule["mean"], capsule["seeds"])
                )
            draft = {
                "status": "draft_needs_human",
                "statement": statement,
                "evidence_refs": [run_result["evidence"]["artifact_id"]],
                "scope": "S5/demo/%s" % run_dataset,
                "capsule": run_result["paths"]["capsule"],
                "ea": run_result["paths"]["ea"],
                "note": (
                    "Draft only; run claim with a human reason before binding to paper. "
                    "assertion_proposal is a suggestion for the human to confirm or replace."
                ),
                "assertion_proposal": _assertion_proposal(capsule, run_dataset),
            }
            with open(str(draft_path), "w", encoding="utf-8", newline="\n") as handle:
                json.dump(draft, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            run_module = {
                **run_result,
                "status": capsule["status"],
                "claim_draft": str(draft_path),
                "claim_draft_record": draft,
                "active_harness": request.run_harness,
            }
            result_figure = build_result_figure(
                capsule, self.run_output_dir, [run_result["evidence"]["artifact_id"]],
                figure_id=run_id + "-result",
            )
            run_module["result_figure"] = result_figure
            modules["run"] = run_module
            warnings.append(
                "S5 run completed; claim draft requires human signature; result slot stays pending"
            )

        if run_module:
            run_contract_result = build_run_contract(
                protocol,
                modules.get("experiment") or {},
                run_module,
            )
            capsule_path = Path(str((run_module.get("paths") or {}).get("capsule") or ""))
            run_contract_check_result = verify_run_contract(
                run_contract_result,
                run_module,
                run_dir=capsule_path.parent if capsule_path.is_file() else None,
            )
            if run_contract_check_result["status"] == "blocked":
                warnings.append(
                    "run contract blocked: "
                    + "; ".join(run_contract_check_result["blockers"][:3])
                )

        if (
            run_module
            and protocol
            and (run_module.get("capsule") or {}).get("status") == "completed"
        ):
            capsule_path = Path(str((run_module.get("paths") or {}).get("capsule") or ""))
            if capsule_path.is_file():
                binding = protocol_binding(
                    protocol,
                    capsule_path,
                    str((run_module.get("evidence") or {}).get("artifact_id") or ""),
                    str((run_module.get("capsule") or {}).get("run_id") or ""),
                )
                binding_path = capsule_path.parent / "protocol-binding.json"
                _write_json(binding_path, binding)
                binding["path"] = str(binding_path)
                modules["protocol_binding"] = binding
            else:
                warnings.append("protocol binding skipped: completed capsule file is missing")

        if run_module:
            run_capsule = run_module.get("capsule") or {}
            self._emit(
                "stage_end", "run",
                "run %s: %s" % (run_capsule.get("run_id", "reused"), run_module.get("status", "")),
                {
                    "run_id": run_capsule.get("run_id", ""),
                    "dataset": run_capsule.get("dataset_id", run_dataset),
                    "seeds": run_capsule.get("seeds", []),
                    "metric": run_capsule.get("metric_name", ""),
                    "status": run_module.get("status", ""),
                    "reused": bool(request.run_dir),
                },
            )
        else:
            self._emit("stage_skip", "run", "no run_dataset or run_dir; result slot stays pending")

        self._emit("stage_start", "figure", "科研绘图")
        nodes = [
            FigureNode("lit", "文献调研\n%d spans" % len(literature.spans), "literature", 0),
            FigureNode("idea", "假设收敛\n%d candidates" % len(idea.candidates), "idea", 1),
            FigureNode("design", "实验设计\n%s" % design.status, "experiment", 2),
            FigureNode("figure", "科研绘图\nSVG + manifest", "figure", 3),
            FigureNode("paper", "论文契约\nslots pending", "paper", 4),
        ]
        edges = [
            FigureEdge("lit", "idea", "spans"),
            FigureEdge("idea", "design", "G1"),
            FigureEdge("design", "figure", "schematic"),
            FigureEdge("figure", "paper", "figure_ref"),
        ]
        if request.grant_scheme:
            nodes.append(FigureNode("grant", "基金申报\n%s" % request.grant_scheme.upper(), "grant", 4))
            edges.append(FigureEdge("design", "grant", "evidence map", dashed=True))
        figure = self._agent("figure").run(
            FigureRequest(
                title="研究运行时：从证据到稿件",
                description="模块关系示意图；不是实验结果",
                nodes=nodes,
                edges=edges,
                style=request.figure_style,
                evidence_refs=[span.span_id for span in literature.spans[:4]],
                run_id=run_id + "-figure",
            )
        )
        modules["figure"] = {**asdict(figure), "status": "schematic_ready"}
        warnings.append("figure is schematic; do not bind it to result.figure without run data")
        schematic_note = "SVG + manifest ready"
        if not figure.svg:
            modules["figure"]["status"] = "scene_only"
            schematic_note = "scene JSON only: the vendored schematic renderer is absent"
            warnings.append(schematic_note)
        self._emit(
            "stage_end", "figure", schematic_note,
            {"figure_id": figure.figure_id, "schematic": True, "svg": bool(figure.svg)},
        )

        study_design = None
        study_design_audit = None
        if request.study_design_file:
            design_path = Path(request.study_design_file)
            if not design_path.is_file():
                raise PipelineError("study design file not found: " + str(design_path))
            study_design = read_json(design_path)
            if not isinstance(study_design, dict):
                raise PipelineError("study design must be a JSON object")
            from .ccfa_audit import audit_study_design

            study_design_audit = audit_study_design(study_design)
            modules["study_design"] = {
                "design": study_design,
                "audit": study_design_audit,
            }
            warnings.append(
                "study design audit: %s (%s)"
                % (
                    study_design_audit.get("status"),
                    (study_design_audit.get("ccfa") or {}).get("level"),
                )
            )
            if study_design_audit.get("status") == "incomplete":
                warnings.append(
                    "study design has disclosure blockers: "
                    + "; ".join(study_design_audit.get("blockers") or [])[:400]
                )
        self._emit("stage_start", "paper", "写作与槽位绑定")
        paper = self._agent("paper").run(
            PaperRequest(
                topic=request.topic,
                language=request.language,
                venue_type=request.venue_type,
                evidence_refs=[span.span_id for span in literature.spans[:4]],
                figure_refs=[figure.figure_id],
                claim_refs=claim_refs,
                claim_statements=claim_statements,
                claim_assertions=claim_assertions,
                study_design=study_design,
                study_design_audit=study_design_audit,
                protocol_refs=[protocol["protocol_id"]] if protocol else [],
                bibliography_refs=[bibliography["card_id"]] if bibliography else [],
                result_figure_refs=(
                    [run_module["result_figure"]["figure_id"]]
                    if run_module and run_module.get("result_figure") else []
                ),
                spans=list(literature.spans),
                literature_brief=literature.brief,
                synthesis=synthesis_matrix or None,
                idea_candidates=list(idea.candidates),
                design=design,
                run_summary=(
                    {
                        "status": run_module.get("status", ""),
                        "run_id": (run_module.get("capsule") or {}).get("run_id", ""),
                        "dataset": (run_module.get("capsule") or {}).get("dataset_id", ""),
                        "metric": (run_module.get("capsule") or {}).get("metric_name", ""),
                        "reused": bool(request.run_dir),
                    }
                    if run_module else None
                ),
                fixture_mode=fixture_mode,
            )
        )
        modules["paper"] = asdict(paper)
        warnings.extend(paper.warnings)
        manuscript_bundle = build_manuscript(
            paper=modules["paper"],
            literature=modules.get("literature") or {},
            bibliography=modules.get("bibliography"),
            topic=request.topic,
            language=request.language,
            venue_type=request.venue_type,
            context={
                "claim_statements": claim_statements,
                "claim_assertions": claim_assertions,
                "claim_signed": claim_signed,
                "design": asdict(design) if design else {},
                "run_summary": (
                    {
                        "status": run_module.get("status", ""),
                        "run_id": (run_module.get("capsule") or {}).get("run_id", ""),
                        "dataset": (run_module.get("capsule") or {}).get("dataset_id", ""),
                        "metric": (run_module.get("capsule") or {}).get("metric_name", ""),
                    }
                    if run_module else {}
                ),
                "figure_refs": [figure.figure_id] if figure else [],
            },
        )
        warnings.append(
            "manuscript readiness: %s (%d blockers, %d warnings)"
            % (
                manuscript_bundle["audit"]["status"],
                manuscript_bundle["audit"]["summary"]["blockers"],
                manuscript_bundle["audit"]["summary"]["warnings"],
            )
        )
        self._emit(
            "stage_end", "paper", "paper status: %s" % paper.status,
            {
                "status": paper.status,
                "slots": len(paper.slots),
                "manuscript_status": manuscript_bundle["audit"]["status"],
            },
        )

        grant = None
        if request.grant_scheme:
            self._emit("stage_start", "grant", "基金申报骨架")
            grant = self._agent("grant").run(
                GrantRequest(
                    topic=request.topic,
                    scheme=request.grant_scheme,
                    evidence_refs=[span.span_id for span in literature.spans[:4]],
                )
            )
            modules["grant"] = asdict(grant)
            warnings.extend(grant.warnings)
            self._emit(
                "stage_end", "grant", "grant scaffold: %s" % grant.status,
                {"status": grant.status, "scheme": grant.scheme},
            )
        else:
            modules["grant"] = None
            self._emit("stage_skip", "grant", "no grant_scheme requested")

        deduped: List[str] = []
        for warning in warnings:
            if warning not in deduped:
                deduped.append(warning)

        study_design_incomplete = bool(study_design) and str(
            (study_design_audit or {}).get("status") or ""
        ) == "incomplete"
        gates = [
            q0,
            {
                "gate": "G1",
                "status": "pass" if g1_decision else "needs_human",
                "reason": (
                    "human-selected idea: " + g1_decision["selected_idea_id"]
                    if g1_decision else
                    "idea candidates require human convergence"
                ),
            },
            {
                "gate": "G2",
                "status": (
                    "blocked" if study_design_incomplete
                    else "pass" if protocol else "needs_human"
                ),
                "reason": (
                    "study design audit is incomplete: "
                    + "; ".join((study_design_audit or {}).get("blockers") or [])[:300]
                    if study_design_incomplete else
                    "frozen ProtocolCard matches the current design"
                    if protocol else
                    "design is %s; G2 requires a human-frozen ProtocolCard" % design.status
                ),
            },
            *evaluate_g3_g5(
                has_ea=bool(run_module),
                has_signed_claim=bool(request.claim_file and claim_refs),
            ),
        ]
        if run_module:
            signed_claim_bound = bool(request.claim_file and claim_refs)
            gates.insert(4, {
                "gate": "S5",
                "status": "pass" if signed_claim_bound else "needs_human",
                "reason": (
                    "run capsule/EA exist; signed supported claim is bound"
                    if signed_claim_bound else
                    "run capsule/EA exist; claim draft needs human signature"
                ),
            })
        status = "needs_human" if (
            design.status != "ready_for_g2" or paper.status != "ready" or study_design_incomplete
        ) else "draft_ready"

        spec_versions = {key: spec.version for key, spec in self.specs.items()}
        if run_module:
            spec_versions["run"] = self.store.load("run").version
        evidence_packages = summarize_evidence_packages(modules, gates)
        self._emit(
            "run_complete", None, "pipeline %s" % status,
            {
                "status": status,
                "fixture_mode": fixture_mode,
                "gates": gates,
                "warnings": deduped,
                "spec_versions": spec_versions,
            },
        )
        return PipelineResult(
            run_id=run_id,
            topic=request.topic,
            status=status,
            fixture_mode=fixture_mode,
            modules=modules,
            gates=gates,
            warnings=deduped,
            spec_versions=spec_versions,
            evidence_packages=evidence_packages,
            flow_mode=flow_mode,
            stopped_at="",
            manuscript=manuscript_bundle["manuscript"] if manuscript_bundle else None,
            manuscript_audit=manuscript_bundle["audit"] if manuscript_bundle else None,
            argument_ledger=manuscript_bundle["argument_ledger"] if manuscript_bundle else None,
            claim_registry=manuscript_bundle["claim_registry"] if manuscript_bundle else None,
            literature_ledger=source_ledger,
            design_audit=design_audit_result,
            idea_review=idea_review_result,
            study=study_result,
            run_contract=run_contract_result,
            run_contract_check=run_contract_check_result,
            events=list(self._events),
        )


def render_report_markdown(result: PipelineResult) -> str:
    modules = result.modules
    literature = modules.get("literature") or {}
    brief = literature.get("brief") or {}
    coverage = literature.get("coverage") or {}
    hits = literature.get("hits") or []
    spans = literature.get("spans") or []
    idea = modules.get("idea") or {}
    design = modules.get("experiment") or {}
    run = modules.get("run") or {}
    paper = modules.get("paper") or {}
    lines: List[str] = [
        "# 科研任务运行报告",
        "",
        "- 主题：%s" % result.topic,
        "- Run：`%s`" % result.run_id,
        "- 状态：`%s`" % result.status,
        "- 数据模式：%s" % ("fixture / 演示数据" if result.fixture_mode else "真实文本或本地运行"),
        "",
        "## 结论边界",
        "",
    ]
    if result.fixture_mode:
        lines.append(
            "本次运行使用 fixture 数据，只能验证流程与证据边界，不能作为科学结论或论文引用。"
        )
    elif "openalex" in (literature.get("query_plan") or {}).get("source_scope", []):
        lines.append(
            "本次运行使用 OpenAlex 检索。摘要只作为来源线索，未取得全文的来源不会生成 span，也不进入 claim。"
        )
    else:
        lines.append(
            "本次运行使用冻结真实文本或本地协议验证。只有可定位 span、RunCapsule/EA 与人签 claim 才能进入结果表达。"
        )
    lines.extend([
        "",
        "## S1 文献与证据覆盖",
        "",
        "- 来源命中：%s；读取全文：%s；可定位 span：%s；gap：%s"
        % (
            coverage.get("sources_found", len(hits)),
            coverage.get("sources_read", 0),
            coverage.get("spans_extracted", len(spans)),
            len(coverage.get("gaps") or []),
        ),
        "- 覆盖率：%s；饱和度：%s"
        % (
            round(float(brief.get("coverage_score") or 0) * 100),
            brief.get("saturation", "unknown"),
        ),
        "",
    ])
    if result.literature_ledger:
        ledger = result.literature_ledger
        counts = ledger.get("counts") or {}
        lines.extend([
            "- 来源账本：%s；全文纳入 %s；摘要-only %s；重复 %s；DOI 覆盖 %s"
            % (
                ledger.get("status", ""),
                counts.get("included_full_text", 0),
                counts.get("abstract_only", 0),
                counts.get("duplicates", 0),
                ledger.get("metadata", {}).get("doi_coverage", 0),
            ),
            "",
        ])
    if brief.get("summary"):
        lines.append(str(brief["summary"]))
        lines.append("")
    if hits:
        lines.append("### 来源")
        lines.append("")
        for hit in hits[:8]:
            marker = "全文" if hit.get("full_text") else "摘要线索"
            lines.append(
                "- `%s` · %s (%s) · %s · %s"
                % (hit.get("source_id"), hit.get("title"), hit.get("year") or "n.d.", marker, hit.get("venue"))
            )
        lines.append("")
    gaps = (coverage.get("gaps") or []) + list(brief.get("gaps") or [])
    if gaps:
        lines.append("### 缺口")
        lines.append("")
        for gap in gaps[:12]:
            if isinstance(gap, dict):
                lines.append("- `%s` · %s" % (gap.get("code", ""), gap.get("message", "")))
            else:
                lines.append("- %s" % gap)
        lines.append("")

    lines.extend(["## S2–S3 候选假设", ""])
    candidates = idea.get("candidates") or []
    if candidates:
        for candidate in candidates[:5]:
            lines.append(
                "- **%s** %s\n  - 证据：%s\n  - 否证：%s"
                % (
                    candidate.get("idea_id", ""),
                    candidate.get("title", ""),
                    "、".join(candidate.get("evidence_refs") or []) or "无",
                    candidate.get("falsification", ""),
                )
            )
        lines.append("")
    else:
        lines.extend(["没有形成候选假设；需要先补齐可定位证据。", ""])
    if result.idea_review:
        counts = result.idea_review.get("counts") or {}
        lines.extend([
            "- 独立预审：advance=%s / revise=%s / reject=%s；词法新颖性不等于文献新颖性，G1 仍需人工。"
            % (counts.get("advance", 0), counts.get("revise", 0), counts.get("reject", 0)),
            "",
        ])

    lines.extend(["## S4 实验设计", ""])
    if design:
        lines.append(
            "- hypothesis：%s\n- baseline：%s\n- primary metric：%s\n- controls：%s\n- seeds：%s\n- status：%s"
            % (
                design.get("hypothesis", ""),
                design.get("baseline", ""),
                design.get("primary_metric", ""),
                "、".join(design.get("controls") or []),
                design.get("seeds", ""),
                design.get("status", ""),
            )
        )
        if design.get("budget"):
            lines.append("- budget：%s" % design["budget"])
    else:
        lines.append("未生成实验设计。")
    if result.design_audit:
        audit = result.design_audit
        lines.append("")
        lines.append("- 设计审计：`%s`（blockers=%d, warnings=%d）" % (
            audit.get("status", ""),
            len(audit.get("blockers") or []),
            len(audit.get("warnings") or []),
        ))
        for warning in (audit.get("blockers") or [])[:4]:
            lines.append("  - %s" % warning)
    lines.append("")

    study = modules.get("study") or {}
    if study:
        lines.extend(["## 搜索研究臂（S5 study arm）", ""])
        lines.append(
            "- 研究包：`%s` · dataset=%s · seeds=%s · budget=%s"
            % (study.get("study_dir", ""), study.get("dataset", ""),
               len(study.get("seeds") or []), study.get("budget", ""))
        )
        lines.append("- 声明设计：%s" % json.dumps(study.get("design") or {}, ensure_ascii=False))
        for name, item in (study.get("comparison") or {}).items():
            low, high = item.get("ci95_low"), item.get("ci95_high")
            state = (
                "不可判定"
                if low is None or high is None or low <= 0 <= high
                else ("正向" if low > 0 else "负向")
            )
            lines.append(
                "- `%s`：%s · 点估计 %s · 95%% 区间 [%s, %s]"
                % (name, state, item.get("mean_diff"), low, high)
            )
        if not study.get("directional_supported"):
            lines.append(
                "- 本轮没有任何比较的区间排除零：**这是非结果**。加种子/预算是改变功效的设计决定，"
                "不是把同一个设计重跑到绿灯。"
            )
        lines.append(
            "- 下一步仍是人工：`study claim`（人签）→ `study closure`；报告不写入未签结果数值。"
        )
        lines.append("")

    lines.extend(["## S5 运行与证据", ""])
    capsule = run.get("capsule") or {}
    if capsule:
        lines.append(
            "- RunCapsule：`%s` · status=%s · dataset=%s · metric=%s"
            % (
                capsule.get("run_id", ""),
                capsule.get("status", ""),
                capsule.get("dataset_id", ""),
                capsule.get("metric_name", ""),
            )
        )
        lines.append("- 数值仍锁在 EA/Claim 之内；报告正文不写入未签结果。")
        if result.run_contract_check:
            check = result.run_contract_check
            min_delta = next(
                (
                    item for item in (check.get("checks") or [])
                    if item.get("id") == "min_delta"
                ),
                None,
            )
            lines.append(
                "- Run contract：`%s`（blockers=%d, warnings=%d；min_delta=%s）"
                % (
                    check.get("status", ""),
                    len(check.get("blockers") or []),
                    len(check.get("warnings") or []),
                    (min_delta or {}).get("detail", "not run"),
                )
            )
            for blocker in (check.get("blockers") or [])[:4]:
                lines.append("  - %s" % blocker)
    else:
        lines.append("本次没有执行 S5；结果槽保持 pending_evidence。")
    lines.append("")

    lines.extend(["## S8–S12 工作稿", ""])
    draft = paper.get("draft") or []
    if draft:
        lines.append("完整稿见 `paper.md`；以下为章节摘要。")
        lines.append("")
        for section in draft:
            text = " ".join(str(section.get("text", "")).split())
            if len(text) > 360:
                text = text[:360] + "…"
            lines.append("- **%s**（%s）：%s" % (
                section.get("section", ""), section.get("status", ""), text,
            ))
    else:
        lines.append("未生成正文草稿。")
    lines.append("")

    if result.manuscript:
        audit = result.manuscript_audit or {}
        lines.extend(["## 中文投稿工作稿", ""])
        lines.append("- 工作稿：`manuscript.md`")
        lines.append("- 审计：`manuscript-audit.json`")
        lines.append("- 论证台账：`argument-ledger.json`")
        lines.append("- 状态：`%s`（submission_ready=%s）" % (
            audit.get("status", ""), audit.get("submission_ready", False),
        ))
        blockers = audit.get("blockers") or []
        if blockers:
            lines.append("- 阻断项：")
            for item in blockers[:8]:
                lines.append("  - %s" % item)
        lines.append("")

    lines.extend(["## 门禁与下一步", ""])
    for gate in result.gates:
        lines.append("- `%s` · %s · %s" % (gate.get("gate"), gate.get("status"), gate.get("reason")))
    lines.extend([
        "",
        "人工下一步：",
        "",
        "1. 检查 S1 来源与 span，确认摘要-only 没有被当作证据；",
        "2. 在 G1 收敛候选假设，补齐机制、指标与最小效应；",
        "3. 冻结协议后执行 S5，签署 Claim，再重新运行 pipeline 绑定结果槽；",
        "4. Closure 通过前不导出、不投稿。",
        "",
        "## 警告",
        "",
    ])
    for warning in result.warnings:
        lines.append("- %s" % warning)
    return "\n".join(lines).rstrip() + "\n"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _assertion_proposal(capsule: Dict[str, Any], run_dataset: str) -> Dict[str, Any]:
    """Propose a conservative assertion for the human to confirm, never to auto-sign.

    The draft used to state a mean and leave the quantitative assertion entirely to the reader.
    Proposing the *worst seed* as a floor is auditable without any distributional assumption, and
    the human still types the final --assertion, so nothing becomes signable by accident.
    """
    if run_dataset == "chemlab":
        metric = "delta_r2"
        values = [float(item["delta_r2"]) for item in capsule.get("metrics_by_seed") or []]
        comparator = ">="
    else:
        metric = str(capsule.get("metric_name") or "accuracy")
        values = [
            float(item[metric])
            for item in capsule.get("metrics_by_seed") or []
            if metric in item
        ]
        comparator = ">="
    if not values:
        return {
            "status": "unavailable",
            "reason": "no per-seed metric values in the capsule; the human must supply the assertion",
            "boundary": "a proposal is a draft for a human; it is not a claim and cannot be signed",
        }
    value = min(values)
    return {
        "status": "proposed_for_human",
        "metric": metric,
        "comparator": comparator,
        "value": round(value, 4),
        "tolerance": 0.0,
        "basis": {
            "mean": round(sum(values) / len(values), 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "seeds": list(capsule.get("seeds") or []),
        },
        "reading": (
            "the proposed value is the worst seed, a floor that needs no distributional "
            "assumption; confirm or replace it before run claim"
        ),
        "assertion_argument": "metric=%s,value=%.4f,comparator=%s,tolerance=0.0"
        % (metric, round(value, 4), comparator),
        "boundary": "a proposal is a draft for a human; it is not a claim and cannot be signed",
    }


def write_pipeline_artifacts(
    result: PipelineResult,
    output_dir: Path,
    extra: Optional[Dict[str, Any]] = None,
    claim_file: str = "",
    support_judge: Optional[Callable[[Dict[str, Any]], Optional[List[Dict[str, Any]]]]] = None,
    strict_support: bool = False,
) -> Dict[str, str]:
    """Persist the shared pipeline artifact set; CLI and runtime use this."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    modules = result.modules
    run_module = modules.get("run") or {}
    run_paths = run_module.get("paths") or {}
    run_out = out / "run"
    for key in ("capsule", "ea", "metrics"):
        source = Path(str(run_paths.get(key) or ""))
        if source.is_file():
            run_out.mkdir(parents=True, exist_ok=True)
            target = run_out / source.name
            if source.resolve() != target.resolve():
                shutil.copyfile(str(source), str(target))
    claim_draft = Path(str(run_module.get("claim_draft") or ""))
    if claim_draft.is_file():
        run_out.mkdir(parents=True, exist_ok=True)
        target = run_out / "claim-draft.json"
        if claim_draft.resolve() != target.resolve():
            shutil.copyfile(str(claim_draft), str(target))
    result_figure = run_module.get("result_figure") or {}
    for key in ("manifest", "svg"):
        source = Path(str((result_figure.get("paths") or {}).get(key) or ""))
        if source.is_file():
            run_out.mkdir(parents=True, exist_ok=True)
            target = run_out / source.name
            if source.resolve() != target.resolve():
                shutil.copyfile(str(source), str(target))
    figure = modules.get("figure")
    if figure and figure.get("svg"):
        with open(str(out / "figure.svg"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(figure["svg"])
        _write_json(out / "figure.scene.json", figure.get("scene") or {})
        _write_json(out / "figure.manifest.json", figure.get("manifest") or {})
    for name in ("literature", "idea", "experiment", "q0"):
        if modules.get(name):
            _write_json(out / (name + ".json"), modules[name])
    if modules.get("synthesis"):
        _write_json(out / "synthesis-matrix.json", modules["synthesis"])
    if result.literature_ledger:
        _write_json(out / "literature-ledger.json", result.literature_ledger)
    if result.design_audit:
        _write_json(out / "design-audit.json", result.design_audit)
    if result.idea_review:
        _write_json(out / "idea-review.json", result.idea_review)
    if result.run_contract:
        _write_json(out / "run-contract.json", result.run_contract)
    if result.run_contract_check:
        _write_json(out / "run-contract-check.json", result.run_contract_check)
    if modules.get("g1_decision"):
        _write_json(out / "g1-decision.json", modules["g1_decision"])
    _write_json(out / "evidence-packages.json", result.evidence_packages)
    if modules.get("bibliography"):
        _write_json(out / "bibliography.json", modules["bibliography"])
    if modules.get("protocol"):
        _write_json(out / "protocol.json", modules["protocol"])
    if modules.get("protocol_binding"):
        _write_json(out / "protocol-binding.json", modules["protocol_binding"])
    if modules.get("paper"):
        _write_json(out / "paper.json", modules["paper"])
        paper_md = render_paper_markdown(modules["paper"])
        with open(str(out / "paper.md"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(paper_md)
    if result.manuscript:
        _write_json(out / "manuscript.json", result.manuscript)
        with open(str(out / "manuscript.md"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_manuscript_markdown(result.manuscript))
        _write_json(out / "manuscript-audit.json", result.manuscript_audit or {})
        _write_json(out / "argument-ledger.json", result.argument_ledger or {})
        _write_json(out / "claim-registry.json", result.claim_registry or {})
    report_md = render_report_markdown(result)
    with open(str(out / "report.md"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(report_md)
    if modules.get("grant"):
        _write_json(out / "grant.json", modules["grant"])
    specs = []
    for module_id in result.spec_versions:
        spec_data = SpecStore().load(module_id).to_dict()
        spec_data.pop("path", None)
        specs.append(spec_data)
    _write_json(out / "specs.json", specs)
    demo = result.to_dict()
    demo_figure = demo.get("modules", {}).get("figure")
    if isinstance(demo_figure, dict):
        demo_figure.pop("svg", None)
    demo["figure_uri"] = "data/figure.svg" if figure and figure.get("svg") else ""
    demo["paper_uri"] = "paper.md" if modules.get("paper") else ""
    demo["literature_ledger_uri"] = "literature-ledger.json" if result.literature_ledger else ""
    demo["design_audit_uri"] = "design-audit.json" if result.design_audit else ""
    demo["idea_review_uri"] = "idea-review.json" if result.idea_review else ""
    demo["run_contract_uri"] = "run-contract.json" if result.run_contract else ""
    demo["run_contract_check_uri"] = "run-contract-check.json" if result.run_contract_check else ""
    demo["manuscript_uri"] = "manuscript.md" if result.manuscript else ""
    demo["manuscript_audit_uri"] = "manuscript-audit.json" if result.manuscript else ""
    demo["claim_registry_uri"] = "claim-registry.json" if result.claim_registry else ""
    demo["report_uri"] = "report.md"
    literature_scope = (modules.get("literature") or {}).get("query_plan", {}).get("source_scope", [])
    if not result.fixture_mode and "openalex" in literature_scope:
        demo["source"] = "openalex live retrieval; abstracts are clues; OA full texts fetched by humans; no claims"
    else:
        demo["source"] = (
            "fixture pipeline; no API, no real experiment"
            if result.fixture_mode else
            "real-text pipeline; frozen CC-BY body text, no API/run/EA/claims"
        )
    if extra:
        demo.update(extra)
    demo_path = out / "demo.json"
    _write_json(demo_path, demo)
    postprocess = None
    if claim_file:
        from .postprocess import run_claim_postprocess

        try:
            postprocess = run_claim_postprocess(
                demo_path,
                Path(claim_file),
                out,
                support_judge=support_judge,
                strict_support=strict_support,
            )
            closure = postprocess.get("closure") or {}
            closure_status = str(closure.get("status") or "")
            for package in result.evidence_packages:
                if package.get("id") != "closure":
                    continue
                if closure_status == "ready":
                    package.update({
                        "status": "ready",
                        "detail": "closure report ready; export still requires a human signature.",
                        "refs": [str(closure.get("path") or "")],
                    })
                elif closure_status == "blocked":
                    package.update({
                        "status": "blocked",
                        "detail": "closure blocked: %s" % (
                            ", ".join(closure.get("unresolved") or []) or "unresolved checks"
                        ),
                        "refs": [str(closure.get("path") or "")],
                    })
            # G3/G5 have exactly one authority. Postprocessing used to mutate
            # the runner's gate dicts in place, so two places could disagree.
            refreshed = {
                item["gate"]: item
                for item in evaluate_g3_g5(
                    closure_status,
                    closure_unresolved=list(closure.get("unresolved") or []),
                    has_ea=bool(run_module),
                )
            }
            result.gates = [
                refreshed.get(str(gate.get("gate") or ""), gate)
                for gate in result.gates
            ]
            demo["gates"] = result.gates
            demo["evidence_packages"] = result.evidence_packages
            demo["postprocess"] = postprocess
            _write_json(demo_path, demo)
            _write_json(out / "evidence-packages.json", result.evidence_packages)
            report_md = render_report_markdown(result)
            with open(str(out / "report.md"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(report_md)
        except Exception as exc:
            from .models import ModelRequiredError
            from .support_audit import SupportAuditError

            if isinstance(exc, (ModelRequiredError, SupportAuditError)):
                raise
            demo["postprocess"] = {
                "status": "error",
                "error": "%s: %s" % (type(exc).__name__, exc),
            }
            _write_json(demo_path, demo)
    # The event chain is the authority; every file written above is a projection.
    # Commit the boundary once, with the final gate rows (postprocessing may have
    # refreshed G3/G5 through the same pure function), and persist append-only.
    events_written = False
    events = list(getattr(result, "events", None) or [])
    if not any(
        entry.get("kind") in (COMMITTED_KIND, REJECTED_KIND) for entry in events
    ):
        commit_boundary(events, "pipeline", result.gates)
        result.events = events
    try:
        verification = verify_events(result.events)
        if verification["ok"]:
            write_events(out / EVENT_FILENAME, result.events)
            events_written = True
        else:
            result.warnings.append(
                "run event chain is broken: %s" % "; ".join(verification["errors"])
            )
    except (OSError, ValueError) as exc:
        # Observability must never break artifact delivery; report it instead.
        result.warnings.append("run event log not written: %s" % exc)

    from .loop_capsule import write_loop_capsule

    loop_capsule = write_loop_capsule(out)
    return {
        "demo": str(out / "demo.json"),
        "figure_svg": str(out / "figure.svg") if figure and figure.get("svg") else "",
        "figure_scene": str(out / "figure.scene.json") if figure and figure.get("svg") else "",
        "figure_manifest": str(out / "figure.manifest.json") if figure and figure.get("svg") else "",
        "literature": str(out / "literature.json") if modules.get("literature") else "",
        "literature_ledger": str(out / "literature-ledger.json") if result.literature_ledger else "",
        "design_audit": str(out / "design-audit.json") if result.design_audit else "",
        "idea_review": str(out / "idea-review.json") if result.idea_review else "",
        "run_contract": str(out / "run-contract.json") if result.run_contract else "",
        "run_contract_check": str(out / "run-contract-check.json") if result.run_contract_check else "",
        "idea": str(out / "idea.json") if modules.get("idea") else "",
        "q0": str(out / "q0.json") if modules.get("q0") else "",
        "g1_decision": str(out / "g1-decision.json") if modules.get("g1_decision") else "",
        "experiment": str(out / "experiment.json") if modules.get("experiment") else "",
        "evidence_packages": str(out / "evidence-packages.json"),
        "paper": str(out / "paper.json") if modules.get("paper") else "",
        "paper_markdown": str(out / "paper.md") if modules.get("paper") else "",
        "manuscript": str(out / "manuscript.json") if result.manuscript else "",
        "manuscript_markdown": str(out / "manuscript.md") if result.manuscript else "",
        "manuscript_audit": str(out / "manuscript-audit.json") if result.manuscript else "",
        "argument_ledger": str(out / "argument-ledger.json") if result.manuscript else "",
        "claim_registry": str(out / "claim-registry.json") if result.claim_registry else "",
        "report_markdown": str(out / "report.md"),
        "specs": str(out / "specs.json"),
        "bibliography": str(out / "bibliography.json") if modules.get("bibliography") else "",
        "protocol": str(out / "protocol.json") if modules.get("protocol") else "",
        "protocol_binding": str(out / "protocol-binding.json") if modules.get("protocol_binding") else "",
        "grant": str(out / "grant.json") if modules.get("grant") else "",
        "postprocess": postprocess.get("path", "") if postprocess else "",
        "closure": ((postprocess or {}).get("closure") or {}).get("path", "") if postprocess else "",
        "closure_obligations": ((postprocess or {}).get("closure") or {}).get("obligations", "") if postprocess else "",
        "lineage": ((postprocess or {}).get("lineage") or {}).get("path", "") if postprocess else "",
        "support_audit": ((postprocess or {}).get("support_audit") or {}).get("path", "") if postprocess else "",
        "loop_capsule": str(loop_capsule),
        "events": str(out / EVENT_FILENAME) if events_written else "",
    }

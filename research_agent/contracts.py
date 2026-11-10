"""模块间数据契约：只放跨模块共享的不可变语义对象。"""

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def seed_count(value: Any) -> int:
    """A design may carry a seed count or the seed list itself; consumers must not diverge on this.

    The pipeline writes the list it actually ran in some paths and a count in others, so every
    reader normalises through here instead of calling int() on whatever it finds.
    """
    if isinstance(value, bool):
        raise ValueError("seeds must be a count or a list of seeds")
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        return len(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ValueError("seeds must be a count or a list of seeds")


@dataclass
class QueryPlan:
    question: str
    subqueries: List[str]
    source_scope: List[str]
    filters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceHit:
    source_id: str
    title: str
    year: Optional[int]
    venue: str
    doi: Optional[str]
    abstract: str
    full_text: bool
    license: str
    fixture: bool = True
    url: Optional[str] = None  # provenance/OA 链接（如 OpenAlex open_access.oa_url），供人取全文


@dataclass
class Span:
    span_id: str
    source_id: str
    section: str
    text: str
    start: int
    end: int
    fixture: bool = True
    page: Optional[int] = None


@dataclass
class Gap:
    code: str
    message: str


@dataclass
class CoverageReceipt:
    queries: int
    sources_found: int
    sources_read: int
    spans_extracted: int
    gaps: List[Gap]
    warnings: List[str]
    source_scope: List[str]


@dataclass
class CoverageFacet:
    facet: str
    queries: List[str]
    source_ids: List[str]
    span_count: int
    covered: bool


@dataclass
class SourceBrief:
    source_id: str
    title: str
    year: Optional[int]
    venue: str
    full_text: bool
    span_count: int
    sections: List[str]
    excerpt: str
    url: Optional[str] = None


@dataclass
class SectionBrief:
    section: str
    source_ids: List[str]
    span_count: int
    excerpts: List[str]


@dataclass
class LiteratureBrief:
    coverage_score: float
    saturation: str
    target_sources: int
    target_full_text: int
    facets: List[CoverageFacet]
    source_briefs: List[SourceBrief]
    sections: List[SectionBrief]
    highlights: List[str]
    summary: str
    gaps: List[str] = field(default_factory=list)


@dataclass
class LiteratureResult:
    run_id: str
    module: str
    spec_version: str
    status: str
    query_plan: QueryPlan
    hits: List[SourceHit]
    spans: List[Span]
    coverage: CoverageReceipt
    warnings: List[str]
    fixture_mode: bool = True
    brief: Optional[LiteratureBrief] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IdeaCard:
    idea_id: str
    title: str
    hypothesis: str
    falsification: str
    evidence_refs: List[str]
    status: str = "candidate"
    lens: str = "mechanism"
    evidence_count: int = 0
    source_count: int = 0
    novelty_status: str = "unverified"
    testability: str = "needs_metric"
    prior_art_refs: List[str] = field(default_factory=list)
    prior_art_scope: str = "none"
    prior_art_delta: str = ""
    kill_criteria: str = ""
    contrast_refs: List[str] = field(default_factory=list)
    contrast_note: str = ""
    gap_ref: str = "none"
    relation_type: str = "unclassified"
    prediction: Optional[Dict[str, Any]] = None
    prediction_status: str = "not_testable_here"
    open_slots: List[str] = field(default_factory=list)


@dataclass
class IdeaBrief:
    candidate_count: int
    source_count: int
    multi_ref_candidates: int
    multi_source_candidates: int
    lenses: Dict[str, int]
    gaps: List[str]
    summary: str


@dataclass
class IdeaShortlist:
    ranked: List[Dict[str, Any]]
    selection: str = "human_g1"
    criteria: List[str] = field(default_factory=list)
    boundary: str = ""


@dataclass
class IdeaResult:
    run_id: str
    module: str
    spec_version: str
    status: str
    candidates: List[IdeaCard]
    warnings: List[str]
    brief: Optional[IdeaBrief] = None
    prior_art_report: List[Dict[str, Any]] = field(default_factory=list)
    shortlist: Optional[IdeaShortlist] = None


@dataclass
class ExperimentDesign:
    design_id: str
    question: str
    hypothesis: str
    baseline: str
    primary_metric: str
    controls: List[str]
    seeds: int
    budget: str
    stopping_rule: str
    evidence_refs: List[str]
    status: str
    warnings: List[str]
    idea_id: str = ""


@dataclass
class FigureNode:
    node_id: str
    label: str
    kind: str
    level: int
    evidence_refs: List[str] = field(default_factory=list)


@dataclass
class FigureEdge:
    source: str
    target: str
    label: str = ""
    dashed: bool = False


@dataclass
class FigureArtifact:
    figure_id: str
    scene: Dict[str, Any]
    svg: str
    manifest: Dict[str, Any]
    audit: Dict[str, Any]


@dataclass
class WritingProfile:
    language: str
    venue_type: str
    citation_style: str
    sections: List[str]


@dataclass
class PaperSlot:
    slot_id: str
    section: str
    required_evidence: str
    status: str = "pending_evidence"


@dataclass
class DraftSection:
    section: str
    text: str
    status: str = "draft"
    evidence_refs: List[str] = field(default_factory=list)


@dataclass
class PaperContract:
    title: str
    profile: WritingProfile
    sections: List[str]
    slots: List[PaperSlot]
    claims: List[Any]
    status: str
    warnings: List[str]
    draft: List[DraftSection] = field(default_factory=list)
    writer_mode: str = "deterministic"


@dataclass
class GrantPlan:
    title: str
    scheme: str
    modules: List[str]
    compliance: List[str]
    evidence_refs: List[str]
    status: str
    warnings: List[str]



@dataclass
class RunRequest:
    protocol_id: str
    dataset: str = "iris"
    model: str = "logistic_regression"
    seeds: int = 3
    test_size: float = 0.3
    metric: str = "accuracy"
    run_id: str = ""
    split: str = "demo"
    protocol_sha256: str = ""


@dataclass
class RunCapsule:
    run_id: str
    protocol_id: str
    protocol_sha256: str
    dataset_id: str
    dataset_sha256: str
    code_sha256: str
    model: str
    seeds: List[int]
    test_size: float
    metric_name: str
    metrics_by_seed: List[Dict[str, Any]]
    mean: float
    std: float
    environment: Dict[str, str]
    status: str
    artifacts: Dict[str, str]
    created_at: str
    warnings: List[str]


@dataclass
class EvidenceArtifact:
    artifact_id: str
    kind: str
    run_id: str
    path: str
    sha256: str
    source: str
    captured_at: str
    immutable: bool
    scope: str


@dataclass
class ClaimAssertion:
    claim_type: str = "numerical"
    metric: str = ""
    comparator: str = ">="
    value: Optional[float] = None
    tolerance: float = 0.0
    observed: Optional[float] = None
    status: str = "unverified"
    condition: str = ""


@dataclass
class ClaimRecord:
    claim_id: str
    statement: str
    evidence_refs: List[str]
    scope: str
    status: str
    human_reason: str
    created_at: str
    warnings: List[str]
    claim_type: str = "conclusion"
    assertions: List[ClaimAssertion] = field(default_factory=list)
    verification: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClosureCheck:
    name: str
    status: str
    detail: str


@dataclass
class ClosureReport:
    report_id: str
    status: str
    checks: List[ClosureCheck]
    unresolved: List[str]
    artifact_refs: List[str]
    created_at: str
    warnings: List[str]
    closure_profile: str = "canonical_run"


@dataclass
class SignatureRecord:
    signature_id: str
    report_id: str
    human_reason: str
    created_at: str
    artifact_refs: List[str]
    export_manifest: str
    submission: bool
    signer_id: str = ""
    signer_key_id: str = ""
    signature_scheme: str = "legacy-unsigned"
    signed_payload_sha256: str = ""
    signature_hmac: str = ""


@dataclass
class ProtocolCard:
    protocol_id: str
    design_sha256: str
    capsule_sha256: str
    hypothesis: str
    baseline: str
    primary_metric: str
    controls: List[str]
    seeds: int
    limitation: str
    human_reason: str
    status: str
    created_at: str

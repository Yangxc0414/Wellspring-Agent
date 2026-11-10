"""S1 literature subagent: retrieve, read, locate spans, report coverage."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

from ..contracts import (
    CoverageFacet,
    CoverageReceipt,
    Gap,
    LiteratureBrief,
    LiteratureResult,
    QueryPlan,
    SectionBrief,
    SourceBrief,
    SourceHit,
    Span,
)
from ..ports import ParserPort, RetrieverPort
from ..specs import ModuleSpec

TARGET_SOURCES = 6
TARGET_FULL_TEXT = 3
TARGET_SPANS = 12
FACET_ORDER = ("core", "survey", "method", "evaluation", "limitation", "recent")
FACET_LABELS = {
    "core": "核心问题",
    "survey": "综述",
    "method": "方法",
    "evaluation": "评测/基准",
    "limitation": "局限/失败",
    "recent": "近期进展",
}


class LiteratureError(RuntimeError):
    pass


@dataclass
class LiteratureRequest:
    question: str
    max_sources: int = 8
    source_scope: List[str] = field(default_factory=lambda: ["fixture"])
    language: str = "auto"
    run_id: Optional[str] = None
    coverage_plan: bool = False
    facet_subset: Optional[List[str]] = None
    followup_plan: bool = False


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _facet_queries(question: str) -> Dict[str, List[str]]:
    base = question.strip()
    if not base:
        return {}
    cjk = _has_cjk(base)
    suffixes = {
        "survey": " 综述" if cjk else " review",
        "method": " 方法" if cjk else " method",
        "evaluation": " 评测" if cjk else " benchmark",
        "limitation": " 局限" if cjk else " limitation",
        "recent": " 最新进展" if cjk else " recent advances",
    }
    plan: Dict[str, List[str]] = {"core": [base]}
    for facet in FACET_ORDER[1:]:
        plan[facet] = [base + suffixes[facet]]
    return plan


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


class LiteratureAgent:
    module_id = "literature"

    def __init__(
        self,
        spec: ModuleSpec,
        retriever: RetrieverPort,
        parser: ParserPort,
        query_planner: Optional[Callable[[str], Optional[List[str]]]] = None,
    ):
        if spec.id != self.module_id:
            raise LiteratureError("spec id must be 'literature', got '%s'" % spec.id)
        self.spec = spec
        self.retriever = retriever
        self.parser = parser
        self.query_planner = query_planner

    def _new_run_id(self) -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return "RUN-%s-%s" % (stamp, uuid.uuid4().hex[:6])

    def _legacy_facet_queries(self, question: str) -> Dict[str, List[str]]:
        base = question.strip()
        if not base:
            return {}
        queries = [base, base + " review", base + " method"]
        if any("一" <= char <= "鿿" for char in base):
            queries.extend([base + " 综述", base + " 方法"])
        return {"core": [base], "survey": [base + " review"], "method": [base + " method"], "_extra": queries}

    def _legacy_subqueries(self, question: str) -> List[str]:
        base = question.strip()
        if not base:
            return []
        candidates = [base, base + " review", base + " method"]
        if any("一" <= char <= "鿿" for char in base):
            candidates.extend([base + " 综述", base + " 方法"])
        seen = set()
        result: List[str] = []
        for query in candidates:
            key = query.lower()
            if key not in seen:
                seen.add(key)
                result.append(query)
        return result

    def _planned_queries(self, question: str) -> Tuple[List[str], List[str]]:
        if self.query_planner is None:
            return [], []
        try:
            planned = self.query_planner(question)
        except Exception as exc:
            from ..models import ModelRequiredError

            if isinstance(exc, ModelRequiredError):
                raise
            planned = None
        if not planned:
            return [], ["query_planner failed or returned nothing; using rule-based queries"]
        cleaned: List[str] = []
        seen = set()
        for item in planned:
            query = " ".join(str(item).split())
            key = query.lower()
            if not query or len(query) > 160 or key in seen:
                continue
            seen.add(key)
            cleaned.append(query)
        if not cleaned:
            return [], ["query_planner returned no usable strings; using rule-based queries"]
        return cleaned[:8], []

    def _subqueries(self, question: str) -> List[str]:
        return self._legacy_subqueries(question)

    def _retrieve_legacy(
        self, subqueries: List[str], max_sources: int
    ) -> Tuple[List[SourceHit], Dict[str, List[str]], bool]:
        hits: List[SourceHit] = []
        seen_sources = set()
        facet_sources: Dict[str, List[str]] = {}
        cap = max(1, min(int(max_sources), 50))
        cap_reached = False
        for query in subqueries:
            for hit in self.retriever.search(query, cap):
                if hit.source_id in seen_sources:
                    continue
                if len(hits) >= cap:
                    cap_reached = True
                    break
                seen_sources.add(hit.source_id)
                hits.append(hit)
                facet = "core"
                lowered = query.lower()
                if "review" in lowered or "综述" in query:
                    facet = "survey"
                elif "method" in lowered or "方法" in query:
                    facet = "method"
                facet_sources.setdefault(facet, []).append(hit.source_id)
            if len(hits) >= cap:
                cap_reached = True
                break
        return hits, facet_sources, cap_reached

    def _retrieve(
        self, facet_queries: Dict[str, List[str]], max_sources: int
    ) -> Tuple[List[SourceHit], Dict[str, List[str]], bool]:
        hits: List[SourceHit] = []
        seen_sources = set()
        facet_sources: Dict[str, List[str]] = {facet: [] for facet in facet_queries}
        cap = max(1, min(int(max_sources), 50))
        cap_reached = False
        pending = {facet: list(queries) for facet, queries in facet_queries.items()}
        buffers: Dict[str, List[SourceHit]] = {}

        # Round-robin so every facet gets a first source before any facet
        # receives a second one; planner/extra queries only fill the slack.
        while len(hits) < cap and any(pending.values()):
            progressed = False
            for facet in facet_queries:
                if not pending[facet]:
                    continue
                query = pending[facet][0]
                if query not in buffers:
                    buffers[query] = list(self.retriever.search(query, cap))
                hit: Optional[SourceHit] = None
                while buffers[query]:
                    candidate = buffers[query].pop(0)
                    if candidate.source_id not in seen_sources:
                        hit = candidate
                        break
                if hit is None:
                    pending[facet].pop(0)
                    continue
                seen_sources.add(hit.source_id)
                hits.append(hit)
                facet_sources[facet].append(hit.source_id)
                progressed = True
                if len(hits) >= cap:
                    cap_reached = True
                    break
            if not progressed:
                break

        return hits, facet_sources, cap_reached

    def _brief(
        self,
        hits: List[SourceHit],
        spans: List[Span],
        sources_read: int,
        facet_queries: Dict[str, List[str]],
        facet_sources: Dict[str, List[str]],
        cap_reached: bool,
    ) -> LiteratureBrief:
        span_by_source: Dict[str, List[Span]] = {}
        for span in spans:
            span_by_source.setdefault(span.source_id, []).append(span)

        facets: List[CoverageFacet] = []
        missing: List[str] = []
        reported_facets = [facet for facet in FACET_ORDER if facet in facet_queries]
        for facet in reported_facets:
            source_ids = list(dict.fromkeys(facet_sources.get(facet, [])))
            span_count = sum(len(span_by_source.get(source_id, [])) for source_id in source_ids)
            covered = bool(source_ids) and span_count > 0
            facets.append(
                CoverageFacet(
                    facet=facet,
                    queries=list(facet_queries.get(facet, [])),
                    source_ids=source_ids,
                    span_count=span_count,
                    covered=covered,
                )
            )
            if not covered:
                missing.append(facet)
        covered_facets = len([facet for facet in facets if facet.covered])
        facet_ratio = covered_facets / len(facets) if facets else 0.0

        source_briefs: List[SourceBrief] = []
        for hit in hits:
            source_spans = span_by_source.get(hit.source_id, [])
            sections = list(dict.fromkeys(span.section for span in source_spans))
            excerpt = ""
            if source_spans:
                preferred = next(
                    (
                        span
                        for span in source_spans
                        if any(token in span.section.lower() for token in ("result", "conclusion", "abstract"))
                    ),
                    source_spans[0],
                )
                excerpt = _clip(preferred.text, 150)
            elif hit.abstract:
                excerpt = _clip(hit.abstract, 150)
            source_briefs.append(
                SourceBrief(
                    source_id=hit.source_id,
                    title=hit.title,
                    year=hit.year,
                    venue=hit.venue,
                    full_text=bool(hit.full_text),
                    span_count=len(source_spans),
                    sections=sections,
                    excerpt=excerpt,
                    url=hit.url,
                )
            )
        source_briefs.sort(key=lambda item: (not item.full_text, -item.span_count, item.source_id))

        section_groups: Dict[str, List[Span]] = {}
        for span in spans:
            section_groups.setdefault(span.section, []).append(span)
        sections_brief: List[SectionBrief] = []
        for section, section_spans in sorted(
            section_groups.items(), key=lambda item: (-len(item[1]), item[0])
        )[:6]:
            excerpts: List[str] = []
            for span in section_spans:
                clipped = _clip(span.text, 130)
                if clipped not in excerpts:
                    excerpts.append(clipped)
                if len(excerpts) >= 2:
                    break
            sections_brief.append(
                SectionBrief(
                    section=section,
                    source_ids=sorted({span.source_id for span in section_spans}),
                    span_count=len(section_spans),
                    excerpts=excerpts,
                )
            )

        source_ratio = min(len(hits) / TARGET_SOURCES, 1.0)
        full_ratio = min(sources_read / TARGET_FULL_TEXT, 1.0)
        span_ratio = min(len(spans) / TARGET_SPANS, 1.0)
        coverage_score = round(
            0.4 * facet_ratio + 0.25 * source_ratio + 0.2 * full_ratio + 0.15 * span_ratio,
            3,
        )
        if facet_ratio >= 0.8 and source_ratio >= 1 and full_ratio >= 1 and span_ratio >= 1:
            saturation = "saturated"
        elif spans:
            saturation = "partial"
        else:
            saturation = "insufficient"

        brief_gaps: List[str] = []
        if missing:
            brief_gaps.append("missing_facets:" + ",".join(missing))
        if cap_reached:
            brief_gaps.append("source_cap_reached")
        if len(hits) < TARGET_SOURCES:
            brief_gaps.append("thin_source_count")
        if sources_read < TARGET_FULL_TEXT:
            brief_gaps.append("thin_full_text")
        if len(spans) < TARGET_SPANS:
            brief_gaps.append("thin_span_count")

        covered_labels = [FACET_LABELS[facet] for facet in reported_facets if facet not in missing]
        missing_labels = [FACET_LABELS[facet] for facet in missing]
        abstract_only = sum(1 for hit in hits if not hit.full_text)
        summary_lines = [
            "共 %d 篇来源（全文 %d / 摘要-only %d），%d 个可定位 span，%d 个 gap。"
            % (len(hits), sources_read, abstract_only, len(spans), len(brief_gaps)),
            "覆盖 %d/%d 个检索面向：%s%s。"
            % (
                covered_facets,
                len(facets),
                "、".join(covered_labels) if covered_labels else "无",
                ("；缺 " + "、".join(missing_labels)) if missing_labels else "",
            ),
            "饱和度 %s；建议目标 ≥%d 篇来源 / ≥%d 篇全文 / ≥%d 个 span。"
            % (saturation, TARGET_SOURCES, TARGET_FULL_TEXT, TARGET_SPANS),
        ]
        representatives = [item for item in source_briefs if item.full_text][:3]
        if representatives:
            summary_lines.append(
                "代表全文："
                + "；".join(
                    "%s (%s, %s) — %s"
                    % (item.title, item.year or "n.d.", item.venue, item.excerpt)
                    for item in representatives
                )
            )
        abstract_reps = [item for item in source_briefs if not item.full_text][:3]
        if abstract_reps:
            summary_lines.append(
                "摘要线索："
                + "；".join(
                    "%s (%s) — %s" % (item.title, item.year or "n.d.", item.excerpt)
                    for item in abstract_reps
                )
            )
        if any(not item.full_text for item in source_briefs):
            summary_lines.append("摘要-only 来源只作线索，不生成 span，也不进入 claim。")

        highlights = [
            "%s：%d sources / %d spans"
            % (FACET_LABELS[item.facet], len(item.source_ids), item.span_count)
            for item in facets
        ]
        highlights.append(
            "coverage %.0f%% · %s · %d/%d targets"
            % (coverage_score * 100, saturation, len(hits), TARGET_SOURCES)
        )
        return LiteratureBrief(
            coverage_score=coverage_score,
            saturation=saturation,
            target_sources=TARGET_SOURCES,
            target_full_text=TARGET_FULL_TEXT,
            facets=facets,
            source_briefs=source_briefs,
            sections=sections_brief,
            highlights=highlights,
            summary="\n".join(summary_lines),
            gaps=brief_gaps,
        )

    def run(self, request: LiteratureRequest) -> LiteratureResult:
        if self.spec.status in ("revoked", "deprecated"):
            raise LiteratureError("module spec status is %s; refusing to run" % self.spec.status)
        if request.max_sources < 1:
            raise LiteratureError("max_sources must be >= 1")
        facet_subset: Optional[List[str]] = None
        if request.facet_subset is not None:
            if not request.coverage_plan:
                raise LiteratureError("facet_subset requires coverage_plan=True")
            requested_facets = [str(facet) for facet in request.facet_subset]
            unknown = [facet for facet in requested_facets if facet not in FACET_ORDER]
            if unknown:
                raise LiteratureError("unknown facet(s): " + ", ".join(sorted(set(unknown))))
            facet_subset = [facet for facet in FACET_ORDER if facet in set(requested_facets)]
            if not facet_subset:
                raise LiteratureError("facet_subset must not be empty")
        run_id = request.run_id or self._new_run_id()
        warnings: List[str] = []
        planned: List[str] = []
        if request.question.strip():
            planned, plan_warnings = self._planned_queries(request.question)
            warnings.extend(plan_warnings)
        if request.coverage_plan:
            facet_queries = _facet_queries(request.question)
            if facet_subset:
                facet_queries = {
                    facet: queries for facet, queries in facet_queries.items() if facet in facet_subset
                }
            if planned and "core" in facet_queries:
                merged: List[str] = []
                seen_queries = set()
                for query in facet_queries["core"] + planned:
                    if query.lower() not in seen_queries:
                        seen_queries.add(query.lower())
                        merged.append(query)
                facet_queries["core"] = merged
            subqueries = []
            seen_queries = set()
            for queries in facet_queries.values():
                for query in queries:
                    if query.lower() not in seen_queries:
                        seen_queries.add(query.lower())
                        subqueries.append(query)
        else:
            facet_queries = self._legacy_facet_queries(request.question)
            if planned:
                subqueries = []
                seen_queries = set()
                for query in [request.question.strip()] + planned:
                    if query.lower() not in seen_queries:
                        seen_queries.add(query.lower())
                        subqueries.append(query)
            else:
                subqueries = self._subqueries(request.question)
        gaps: List[Gap] = []
        hits: List[SourceHit] = []
        spans: List[Span] = []
        sources_read = 0
        cap_reached = False
        facet_sources: Dict[str, List[str]] = {facet: [] for facet in facet_queries}
        followup_queries: List[str] = []
        followup_sources_added = 0
        followup_spans_added = 0
        followup_budget = 0

        if not subqueries:
            gaps.append(Gap("no_question", "question is empty; no retrieval was attempted"))
        else:
            if request.coverage_plan:
                hits, facet_sources, cap_reached = self._retrieve(facet_queries, request.max_sources)
            else:
                hits, facet_sources, cap_reached = self._retrieve_legacy(subqueries, request.max_sources)
            for hit in hits:
                if not hit.full_text:
                    gaps.append(Gap("full_text_unavailable", "%s has no full text; abstract is not evidence" % hit.source_id))
                    continue
                document = self.retriever.full_text(hit.source_id)
                if not document:
                    gaps.append(Gap("full_text_unavailable", "%s declared full text but returned none" % hit.source_id))
                    continue
                sources_read += 1
                spans.extend(self.parser.spans(hit, document))

            if request.followup_plan and len(hits) < request.max_sources:
                followup_queries = self._followup_queries(
                    request.question,
                    facet_queries,
                    facet_sources,
                    spans,
                    hits,
                    sources_read,
                    subqueries,
                )
                followup_budget = min(2, request.max_sources - len(hits))
                if followup_queries and followup_budget > 0:
                    new_hits, new_facet_sources, _ = self._retrieve_legacy(
                        followup_queries, followup_budget
                    )
                    seen_sources = {hit.source_id for hit in hits}
                    for hit in new_hits:
                        if hit.source_id in seen_sources:
                            continue
                        seen_sources.add(hit.source_id)
                        hits.append(hit)
                        followup_sources_added += 1
                        if not hit.full_text:
                            continue
                        document = self.retriever.full_text(hit.source_id)
                        if not document:
                            continue
                        sources_read += 1
                        extracted = self.parser.spans(hit, document)
                        spans.extend(extracted)
                        followup_spans_added += len(extracted)
                    for facet, ids in new_facet_sources.items():
                        facet_sources.setdefault(facet, []).extend(ids)
                    subqueries.extend(followup_queries)
                    warnings.append(
                        "followup_plan: added %d sources / %d spans"
                        % (followup_sources_added, followup_spans_added)
                    )
                else:
                    warnings.append(
                        "followup_plan: no additional queries within remaining budget"
                    )

            if not hits:
                gaps.append(Gap("no_source_hit", "no source matched the query"))
            elif not sources_read:
                gaps.append(Gap("no_full_text", "hits were found, but none had a readable full text"))
            elif not spans:
                gaps.append(Gap("no_span", "full texts were read, but no sentence-level span was extracted"))
            if len(hits) >= 3 and sources_read < 3:
                gaps.append(Gap("thin_full_text_coverage", "fewer than 3 full texts were read"))

            covered_facets = self._covered_facets(facet_sources, spans)
            if request.coverage_plan and cap_reached and (len(hits) < TARGET_SOURCES or covered_facets < len(facet_queries)):
                gaps.append(Gap(
                    "coverage_cap_reached",
                    "max_sources=%d reached before all facets were covered; raise the budget or narrow the question"
                    % request.max_sources,
                ))
            if request.coverage_plan and (covered_facets < len(facet_queries) or sources_read < TARGET_FULL_TEXT):
                gaps.append(Gap(
                    "thin_domain_coverage",
                    "covered %d/%d facets, read %d/%d full texts; add sources before claim-level conclusions"
                    % (covered_facets, len(facet_queries), sources_read, TARGET_FULL_TEXT),
                ))

        if getattr(self.retriever, "fixture_mode", False):
            warnings.append("fixture_mode: synthetic data for pipeline tests only; not real evidence")
        warnings.append("S1 outputs spans, not claims; spans must pass Q0/Claim Curator before use")
        if self.spec.status != "active":
            warnings.append("spec status=%s; this run is development-only" % self.spec.status)
        if not subqueries:
            warnings.append("empty question; result is insufficient_evidence")

        brief = self._brief(hits, spans, sources_read, facet_queries, facet_sources, cap_reached)
        if brief.saturation != "saturated":
            warnings.append(
                "coverage=%s; %d sources / %d full texts / %d spans; see brief.gaps"
                % (brief.saturation, len(hits), sources_read, len(spans))
            )

        # Q0 returns the same "pass" reason for 3 synthetic fixture sources and
        # for a review-sized full-text corpus, and neither S1 nor S2 declares a
        # minimum source count. Downstream consumers of the idea output therefore
        # cannot tell whether candidates rest on a literature-review-grade base.
        # Record the breadth explicitly. This is disclosure only: it does not
        # change status, Q0, the gaps, or any gate/Claim/EA invariant.
        distinct_sources = len({hit.source_id for hit in hits})
        review_grade = (
            distinct_sources >= TARGET_SOURCES
            and sources_read >= TARGET_FULL_TEXT
            and len(spans) >= TARGET_SPANS
            and brief.saturation == "saturated"
        )
        breadth = (
            "evidence_breadth=sources:%d full_text:%d spans:%d coverage:%.3f "
            "saturation:%s review_grade:%s"
            % (
                distinct_sources,
                sources_read,
                len(spans),
                brief.coverage_score,
                brief.saturation,
                "yes" if review_grade else "no",
            )
        )
        if not review_grade:
            breadth += (
                " | below review-grade evidence; S2 idea candidates are workflow "
                "demonstrations, not a literature-review conclusion. To widen: "
                "literature run --source local --corpus-dir <dir> --max-sources 12 "
                "(or pipeline run --corpus-dir <dir> --max-sources 12)"
            )
        warnings.append(breadth)

        query_plan = QueryPlan(
            question=request.question,
            subqueries=subqueries,
            source_scope=list(request.source_scope),
            filters={
                "full_text_only": True,
                "spec_version": self.spec.version,
                "facets": facet_queries,
                "facet_subset": facet_subset,
                "coverage_plan": request.coverage_plan,
                "followup_plan": request.followup_plan,
                "followup_queries": followup_queries,
                "followup_sources_added": followup_sources_added,
                "followup_spans_added": followup_spans_added,
                "followup_budget": followup_budget,
                "target_sources": TARGET_SOURCES,
                "target_full_text": TARGET_FULL_TEXT,
            },
        )
        coverage = CoverageReceipt(
            queries=len(subqueries),
            sources_found=len(hits),
            sources_read=sources_read,
            spans_extracted=len(spans),
            gaps=gaps,
            warnings=list(warnings),
            source_scope=list(request.source_scope),
        )
        status = "ok" if spans else "insufficient_evidence"
        return LiteratureResult(
            run_id=run_id,
            module=self.module_id,
            spec_version=self.spec.version,
            status=status,
            query_plan=query_plan,
            hits=hits,
            spans=spans,
            coverage=coverage,
            warnings=warnings,
            fixture_mode=bool(getattr(self.retriever, "fixture_mode", False)),
            brief=brief,
        )

    @staticmethod
    def _covered_facet_names(
        facet_sources: Dict[str, List[str]], spans: List[Span]
    ) -> set:
        source_ids = {span.source_id for span in spans}
        return {
            facet
            for facet, ids in facet_sources.items()
            if facet != "_extra" and set(ids) & source_ids
        }

    def _followup_queries(
        self,
        question: str,
        facet_queries: Dict[str, List[str]],
        facet_sources: Dict[str, List[str]],
        spans: List[Span],
        hits: List[SourceHit],
        sources_read: int,
        subqueries: List[str],
    ) -> List[str]:
        covered = self._covered_facet_names(facet_sources, spans)
        base = question.strip()
        cjk = _has_cjk(base)
        queries: List[str] = []
        for facet, values in facet_queries.items():
            if facet == "_extra" or facet in covered:
                continue
            for value in values[:1]:
                first = value.strip()
                if not first:
                    continue
                queries.append(first + (" 全文" if cjk else " full text"))
                queries.append(first + (" PDF" if cjk else " pdf"))
        if base and len(hits) >= 3 and sources_read < TARGET_FULL_TEXT:
            queries.extend(
                [base + (" 全文" if cjk else " full text"), base + (" PDF" if cjk else " pdf")]
            )
        if base and not spans:
            queries.extend(
                [base + (" 方法" if cjk else " method"), base + (" 实验" if cjk else " experiment")]
            )
        seen = {value.lower() for value in subqueries}
        result: List[str] = []
        for value in queries:
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
            if len(result) >= 4:
                break
        return result

    @staticmethod
    def _covered_facets(facet_sources: Dict[str, List[str]], spans: List[Span]) -> int:
        source_ids = {span.source_id for span in spans}
        return sum(
            1
            for ids in facet_sources.values()
            if ids and any(source_id in source_ids for source_id in ids)
        )

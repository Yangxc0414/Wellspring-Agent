"""Merge scout reports into one read-only evidence view."""

from typing import Any, Dict, List, Sequence

from ..contracts import Gap, SourceHit, Span
from ..modules.literature import FACET_LABELS, TARGET_FULL_TEXT, TARGET_SOURCES, TARGET_SPANS


def merge_reports(results: Sequence[Any], scout_summaries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    hits_by_id: Dict[str, SourceHit] = {}
    spans_by_id: Dict[str, Span] = {}
    facet_coverage: Dict[str, Dict[str, Any]] = {}
    all_warnings: List[str] = []
    scout_gaps: Dict[str, List[str]] = {}
    query_count = 0

    for summary, result in zip(scout_summaries, results):
        scout_gaps[summary["role_id"]] = list(summary.get("gap_codes") or [])
        query_count += int(result.coverage.queries)
        for hit in result.hits:
            previous = hits_by_id.get(hit.source_id)
            if previous is None or (hit.full_text and not previous.full_text):
                hits_by_id[hit.source_id] = hit
        for span in result.spans:
            spans_by_id.setdefault(span.span_id, span)
        for warning in result.warnings:
            if warning not in all_warnings:
                all_warnings.append(warning)
        brief = result.brief
        if brief is None:
            continue
        for facet in brief.facets:
            state = facet_coverage.setdefault(
                facet.facet,
                {
                    "facet": facet.facet,
                    "label": FACET_LABELS.get(facet.facet, facet.facet),
                    "queries": [],
                    "source_ids": [],
                    "span_count": 0,
                    "covered": False,
                },
            )
            for query in facet.queries:
                if query not in state["queries"]:
                    state["queries"].append(query)
            for source_id in facet.source_ids:
                if source_id not in state["source_ids"]:
                    state["source_ids"].append(source_id)
            state["span_count"] = int(state["span_count"]) + int(facet.span_count)
            state["covered"] = bool(state["covered"] or facet.covered)

    hits = list(hits_by_id.values())
    spans = list(spans_by_id.values())
    readable_sources = {span.source_id for span in spans}
    covered_facets = sum(1 for item in facet_coverage.values() if item["covered"])
    planned_facets = max(1, len(facet_coverage))
    gaps = merged_gaps(hits, spans, facet_coverage, scout_gaps)
    facet_ratio = covered_facets / float(planned_facets)
    source_ratio = min(1.0, len(hits) / float(TARGET_SOURCES))
    full_ratio = min(1.0, len(readable_sources) / float(TARGET_FULL_TEXT))
    span_ratio = min(1.0, len(spans) / float(TARGET_SPANS))
    coverage_score = round(0.55 * facet_ratio + 0.20 * source_ratio + 0.15 * full_ratio + 0.10 * span_ratio, 4)
    if (
        facet_ratio >= 0.8
        and len(hits) >= TARGET_SOURCES
        and len(readable_sources) >= TARGET_FULL_TEXT
        and len(spans) >= TARGET_SPANS
    ):
        saturation = "saturated"
    elif covered_facets >= 2 and (readable_sources or hits):
        saturation = "partial"
    else:
        saturation = "insufficient"
    return {
        "hits": [hit.__dict__ for hit in hits],
        "spans": [span.__dict__ for span in spans],
        "facet_coverage": list(facet_coverage.values()),
        "sources": len(hits),
        "full_text": len(readable_sources),
        "spans_count": len(spans),
        "queries": query_count,
        "covered_facets": covered_facets,
        "planned_facets": planned_facets,
        "coverage_score": coverage_score,
        "saturation": saturation,
        "gaps": [gap.__dict__ for gap in gaps],
        "scout_gaps": scout_gaps,
        "warnings": all_warnings,
    }


def merged_gaps(
    hits: Sequence[SourceHit],
    spans: Sequence[Span],
    facet_coverage: Dict[str, Dict[str, Any]],
    scout_gaps: Dict[str, List[str]],
) -> List[Gap]:
    gaps: List[Gap] = []
    readable = {span.source_id for span in spans}
    if not hits:
        gaps.append(Gap("no_source_hit", "no scout returned a source"))
    elif not readable:
        gaps.append(Gap("no_full_text", "hits were found, but no scout read a full text"))
    elif not spans:
        gaps.append(Gap("no_span", "full texts were read, but no sentence-level span was extracted"))
    if len(hits) >= 3 and len(readable) < 3:
        gaps.append(Gap("thin_full_text_coverage", "fewer than 3 unique full texts were read"))
    unavailable = [hit.source_id for hit in hits if not hit.full_text]
    if unavailable:
        gaps.append(
            Gap(
                "full_text_unavailable",
                "%d source(s) are abstract-only and were not turned into spans: %s"
                % (len(unavailable), ", ".join(unavailable[:5])),
            )
        )
    uncovered = [item["facet"] for item in facet_coverage.values() if not item["covered"]]
    if uncovered:
        gaps.append(
            Gap(
                "thin_domain_coverage",
                "covered %d/%d facets; uncovered: %s"
                % (len(facet_coverage) - len(uncovered), len(facet_coverage), ", ".join(sorted(uncovered))),
            )
        )
    if any("coverage_cap_reached" in codes for codes in scout_gaps.values()):
        gaps.append(
            Gap(
                "coverage_cap_reached",
                "at least one scout exhausted its budget before its facets were covered",
            )
        )
    return gaps


def memory_facets(merged: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "facet": item["facet"],
            "queries": len(item["queries"]),
            "sources": len(item["source_ids"]),
            "spans": int(item["span_count"]),
            "covered": bool(item["covered"]),
        }
        for item in merged["facet_coverage"]
    ]


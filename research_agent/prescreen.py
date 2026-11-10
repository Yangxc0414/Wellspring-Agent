"""Deterministic Stage1 pre-screening of clue-only paper candidates.

This sits BETWEEN the information-source layer (``paper_discovery``) and the
evidence layer (S1 full-text parsing). Its job is cheap: reject obviously
irrelevant candidates before anyone spends time downloading full text.

Two stages, with a strict division of authority:

* Stage1 = hard filter. Structural completeness + lexical query-term hits in
  the title and (optionally) an abstract. Every rejection carries a checkable
  reason, so filtering is never a black box.
* Stage2 = ranking only. An explainable weighted score orders what survived;
  it NEVER changes the kept set, never decides novelty/quality, and never
  crosses a gate.

The abstract is a *filter input*, not evidence. It is supplied separately by
the caller, used in memory for lexical matching, and is never echoed, written
to the report, or turned into a span / SourceHit / Claim / EA / gate.
Passing Stage1 means "worth downloading", not "evidence eligible".
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

PRESCREEN_SCHEMA = "paper-prescreen-0.1"
REASON_MISSING_TITLE = "missing_title"
REASON_NO_QUERY_TERM = "no_query_term"
REASON_EXCLUDED_TERM = "excluded_term"

_SPLIT_RE = re.compile(r"[\s,;:、，；/]+")


def query_terms(query: str) -> List[str]:
    """Split a mixed zh/en query into stable lowercase match terms."""
    parts = [item.strip().lower() for item in _SPLIT_RE.split(str(query or ""))]
    return [item for item in parts if len(item) >= 2]


def _hits(text: str, terms: Sequence[str]) -> List[str]:
    lowered = str(text or "").lower()
    return [term for term in terms if term and term in lowered]


def _public_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Copy a candidate while dropping anything that could be read as evidence."""
    return {
        key: value
        for key, value in row.items()
        if key not in ("abstract", "summary", "full_text", "spans", "text")
    }


@dataclass
class PrescreenReport:
    query: str = ""
    kept: List[Dict[str, Any]] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    by_reason: Dict[str, int] = field(default_factory=dict)
    input_count: int = 0
    min_hits: int = 1
    abstracts_used: int = 0

    @property
    def kept_count(self) -> int:
        return len(self.kept)

    @property
    def compression(self) -> float:
        return round(1.0 - (len(self.kept) / self.input_count), 3) if self.input_count else 0.0

    def to_dict(self) -> Dict[str, Any]:
        scores = [int(row.get("rank_score") or 0) for row in self.kept]
        return {
            "schema_version": PRESCREEN_SCHEMA,
            "query": self.query,
            "min_hits": self.min_hits,
            "input_count": self.input_count,
            "kept_count": self.kept_count,
            "rejected_count": len(self.rejected),
            "compression": self.compression,
            "by_reason": dict(self.by_reason),
            "abstracts_used_in_memory_only": self.abstracts_used,
            "score_range": [min(scores), max(scores)] if scores else [],
            "kept": [dict(row) for row in self.kept],
            "rejected": [dict(row) for row in self.rejected],
            "boundary": (
                "ranking_signal_only=true: the Stage2 score orders downloads, it is not "
                "novelty, quality, or a gate decision. Abstracts are in-memory filter "
                "inputs only and are never echoed or persisted. No span, SourceHit, "
                "Claim/EA/gate/signature is produced; Q0 and S1 semantics are unchanged. "
                "Passing Stage1 means worth downloading full text, not evidence eligible."
            ),
            "next_commands": (
                [
                    'python -m research_agent literature fetch --query "%s" '
                    '--target-dir <corpus-dir> --allow-network' % self.query,
                ] if self.query else []
            ) + [
                'python -m research_agent literature run --question "<问题>" '
                '--source local --corpus-dir <corpus-dir> --max-sources 12',
            ],
        }


def stage1_filter(
    candidates: Sequence[Dict[str, Any]],
    *,
    query: str,
    abstracts: Optional[Dict[str, str]] = None,
    min_hits: int = 1,
    exclude_terms: Sequence[str] = (),
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int]:
    """Pure hard filter. Returns (kept, rejected, abstracts_used)."""
    terms = query_terms(query)
    excluded = [str(item).strip().lower() for item in exclude_terms if str(item).strip()]
    abstract_map = abstracts or {}
    kept: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    used = 0
    for row in candidates or []:
        item = dict(row or {})
        title = str(item.get("title") or "").strip()
        paper_id = str(item.get("paper_id") or "")
        abstract = str(abstract_map.get(paper_id) or "")
        if abstract:
            used += 1
        if not title:
            rejected.append({
                "paper_id": paper_id, "title": title, "reason": REASON_MISSING_TITLE,
                "matched_terms": [],
            })
            continue
        title_hits = _hits(title, terms)
        abstract_hits = _hits(abstract, terms) if abstract else []
        matched = sorted(set(title_hits) | set(abstract_hits))
        haystack = (title + " " + abstract).lower()
        blocked = [term for term in excluded if term and term in haystack]
        if blocked:
            rejected.append({
                "paper_id": paper_id, "title": title, "reason": REASON_EXCLUDED_TERM,
                "matched_terms": matched, "excluded": blocked,
            })
            continue
        if len(matched) < max(1, int(min_hits)):
            rejected.append({
                "paper_id": paper_id, "title": title, "reason": REASON_NO_QUERY_TERM,
                "matched_terms": matched,
            })
            continue
        public = _public_row(item)
        public.update({
            "matched_terms": matched,
            "title_hits": len(title_hits),
            "abstract_hits": len(abstract_hits),
            "prescreen_stage": "stage1_pass",
            "clue_only": True,
            "span_eligible": False,
        })
        kept.append(public)
    return kept, rejected, used


def rank_candidates(kept: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pure ordering pass; it must never add or remove a candidate."""
    ranked: List[Dict[str, Any]] = []
    for row in kept:
        item = dict(row)
        signals = {
            "title_hits": int(item.get("title_hits") or 0) * 3,
            "abstract_hits": int(item.get("abstract_hits") or 0),
            "multi_source": 1 if len(item.get("sources") or []) > 1 else 0,
            "has_pdf": 1 if item.get("pdf_url") else 0,
        }
        item["rank_signals"] = signals
        item["rank_score"] = sum(signals.values())
        item["ranking_signal_only"] = True
        ranked.append(item)
    return sorted(
        ranked, key=lambda item: (-int(item["rank_score"]), str(item.get("paper_id") or ""))
    )


def prescreen(
    candidates: Sequence[Dict[str, Any]],
    *,
    query: str,
    abstracts: Optional[Dict[str, str]] = None,
    min_hits: int = 1,
    exclude_terms: Sequence[str] = (),
) -> PrescreenReport:
    """Stage1 filter -> Stage2 ordering. No I/O, no model, no network."""
    rows = [dict(row or {}) for row in (candidates or [])]
    report = PrescreenReport(query=str(query or ""), input_count=len(rows), min_hits=int(min_hits))
    kept, rejected, used = stage1_filter(
        rows, query=query, abstracts=abstracts,
        min_hits=min_hits, exclude_terms=exclude_terms,
    )
    report.abstracts_used = used
    report.rejected = rejected
    for row in rejected:
        reason = str(row.get("reason") or "unknown")
        report.by_reason[reason] = report.by_reason.get(reason, 0) + 1
    # Stage2 only orders; the kept set is never truncated or expanded here.
    report.kept = rank_candidates(kept)
    return report


__all__ = [
    "PRESCREEN_SCHEMA", "REASON_MISSING_TITLE", "REASON_NO_QUERY_TERM",
    "REASON_EXCLUDED_TERM", "PrescreenReport", "query_terms", "stage1_filter",
    "rank_candidates", "prescreen",
]

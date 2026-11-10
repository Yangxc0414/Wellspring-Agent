"""Deterministic S2-S3 idea review.

This is a lexical pre-review, not a literature-novelty search and not G1.
It checks whether each candidate is grounded in supplied spans, falsifiable,
specific/testable, and not merely a restatement of one evidence sentence.
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Set

IDEA_REVIEW_SCHEMA = "idea-review-0.1"
BOUNDARY = (
    "lexical pre-review only; novelty against the literature is not established; "
    "G1 remains a human decision and candidate status is not a claim"
)
STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "and", "or", "for", "on", "with",
    "by", "from", "is", "are", "was", "were", "be", "been", "this", "that",
    "these", "those", "using", "use", "into", "as", "at", "we", "our", "it",
    "本文", "研究", "方法", "结果", "候选", "假设", "可能",
}
TESTABILITY_RE = re.compile(
    r"(指标|度量|比较|差异|提升|降低|优于|劣于|相关|回归|分类|误差|"
    r"metric|measure|compare|difference|increase|decrease|improve|accuracy|"
    r"t80|r2|precision|recall|auc|error|p\s*[<=>])",
    re.IGNORECASE,
)
LENSES = {"mechanism", "boundary", "measurement"}


def _tokens(text: Any) -> Set[str]:
    lowered = str(text or "").lower().replace("–", " ").replace("—", " ").replace("-", " ")
    terms = re.findall(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", lowered)
    return {term for term in terms if term not in STOPWORDS}


def _overlap(candidate: str, evidence: str) -> float:
    left = _tokens(candidate)
    right = _tokens(evidence)
    if not left:
        return 0.0
    return len(left & right) / len(left)


def build_idea_review(idea: Dict[str, Any], literature: Dict[str, Any]) -> Dict[str, Any]:
    cards = [item for item in (idea.get("candidates") or []) if isinstance(item, dict)]
    spans = [item for item in (literature.get("spans") or []) if isinstance(item, dict)]
    span_by_id = {str(item.get("span_id") or ""): item for item in spans}
    reviews: List[Dict[str, Any]] = []
    for card in cards:
        refs = [str(item) for item in (card.get("evidence_refs") or [])]
        valid_refs = [ref for ref in refs if ref in span_by_id]
        sources = {str(span_by_id[ref].get("source_id") or "") for ref in valid_refs}
        falsification = str(card.get("falsification") or "").strip()
        hypothesis = str(card.get("hypothesis") or "").strip()
        title = str(card.get("title") or "").strip()
        reasons: List[str] = []
        dimensions: Dict[str, str] = {}
        if valid_refs:
            dimensions["grounding"] = "grounded"
        else:
            dimensions["grounding"] = "missing"
            reasons.append("no evidence_ref resolves to a supplied span")
        if len(sources) >= 2:
            dimensions["source_diversity"] = "multi_source"
        elif len(sources) == 1:
            dimensions["source_diversity"] = "single_source"
            reasons.append(
                "candidate relies on a single source: ground it in a second source, or let a model "
                "propose cross-source candidates (the deterministic clusterer groups spans by "
                "source and cannot do this on its own)"
            )
        else:
            dimensions["source_diversity"] = "none"
        if len(falsification) >= 20:
            dimensions["falsifiability"] = "falsifiable_draft"
        else:
            dimensions["falsifiability"] = "missing_or_thin"
            reasons.append("falsification condition is missing or too thin")
        max_overlap = 0.0
        for ref in valid_refs:
            max_overlap = max(max_overlap, _overlap(hypothesis, span_by_id[ref].get("text", "")))
        if max_overlap > 0.85:
            dimensions["novelty_heuristic"] = "restates_evidence"
            reasons.append("hypothesis mostly restates a cited span; lexical novelty is low")
        elif max_overlap >= 0.55:
            dimensions["novelty_heuristic"] = "incremental"
            reasons.append("hypothesis closely overlaps a cited span")
        else:
            dimensions["novelty_heuristic"] = "plausible_novel"
        if TESTABILITY_RE.search(hypothesis) or TESTABILITY_RE.search(falsification):
            dimensions["testability"] = "metric_signal"
        else:
            dimensions["testability"] = "needs_metric"
            reasons.append("no metric/comparison signal in hypothesis or falsification")
        lens = str(card.get("lens") or "")
        if lens not in LENSES:
            dimensions["lens"] = "invalid"
            reasons.append("lens is not mechanism/boundary/measurement")
        else:
            dimensions["lens"] = lens
        if dimensions["grounding"] == "missing" or dimensions["falsifiability"] == "missing_or_thin":
            recommendation = "reject"
        elif dimensions["novelty_heuristic"] == "restates_evidence":
            recommendation = "revise"
        elif any(
            value in ("single_source", "incremental", "needs_metric", "invalid")
            for value in dimensions.values()
        ):
            recommendation = "revise"
        else:
            recommendation = "advance"
        reviews.append(
            {
                "idea_id": str(card.get("idea_id") or ""),
                "title": title,
                "recommendation": recommendation,
                "dimensions": dimensions,
                "max_evidence_overlap": round(max_overlap, 4),
                "reasons": reasons,
            }
        )
    counts = {
        "advance": sum(1 for item in reviews if item["recommendation"] == "advance"),
        "revise": sum(1 for item in reviews if item["recommendation"] == "revise"),
        "reject": sum(1 for item in reviews if item["recommendation"] == "reject"),
    }
    review_id = "IDREV-" + hashlib.sha256(
        json.dumps(reviews, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:10]
    return {
        "schema_version": IDEA_REVIEW_SCHEMA,
        "review_id": review_id,
        "counts": counts,
        "reviews": reviews,
        "boundary": BOUNDARY,
    }

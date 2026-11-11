"""S2/S3 idea facilitator: turn spans into falsifiable candidate frames.

This is deliberately not an autonomous novelty machine. It produces candidate
frames with an explicit falsification condition and marks them for human G1.
"""

import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..contracts import IdeaBrief, IdeaCard, IdeaResult, IdeaShortlist, Span
from ..models import ModelRequiredError
from ..specs import ModuleSpec


IdeaProposer = Callable[[Dict[str, Any]], Optional[List[Dict[str, Any]]]]

_T6B_CARRY_PREFIX = "carry the executed falsification condition into new hypotheses: "


def _belief_title(constraint: str) -> str:
    marker = "revise or drop '"
    start = constraint.find(marker)
    if start < 0:
        return ""
    rest = constraint[start + len(marker):]
    end = rest.find("'")
    return rest[:end] if end >= 0 else ""


def _constraint_kind(entry: Dict[str, Any]) -> str:
    """Typed consumption: kind first, prose parsing only for legacy rows."""
    kind = str(entry.get("constraint_kind") or "").strip()
    if kind:
        return kind
    loop = str(entry.get("loop_id") or "")
    text = str(entry.get("constraint") or "")
    if loop == "homogeneity":
        return "require_lens_diversity"
    if loop == "belief_revision":
        return "demote_candidate" if text.startswith("next generation: revise or drop") else "carry_forward"
    if loop == "t6b_falsification":
        return "carry_falsification" if text.startswith(_T6B_CARRY_PREFIX) else "require_falsification_binding"
    return ""


def _constraint_payload(entry: Dict[str, Any], kind: str) -> Dict[str, Any]:
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    if kind == "demote_candidate" and not payload.get("title"):
        return {"title": _belief_title(str(entry.get("constraint") or ""))}
    if kind == "carry_falsification" and not payload.get("falsification"):
        text = str(entry.get("constraint") or "")
        if text.startswith(_T6B_CARRY_PREFIX):
            return {"falsification": text[len(_T6B_CARRY_PREFIX):]}
    return payload


def _constraint_provenance(entry: Dict[str, Any], kind: str, effect: str) -> Dict[str, Any]:
    return {
        "loop_id": str(entry.get("loop_id") or ""),
        "constraint_kind": kind,
        "subject": str(entry.get("subject") or ""),
        "source_path": str(entry.get("source_path") or ""),
        "source_sha256": str(entry.get("source_sha256") or ""),
        "constraint": str(entry.get("constraint") or ""),
        "effect": effect,
    }

# Slots a falsifiable prediction must declare before it can be called testable.
PREDICTION_SLOTS = (
    "variable", "direction", "condition", "profile", "dataset",
    "metric", "controls", "seeds", "stopping_rule", "criterion",
)


class IdeaError(RuntimeError):
    pass


def prior_art_hits_from_literature(result: Any, limit: int) -> List[Dict[str, Any]]:
    """Project a LiteratureResult into bounded prior-art hit dicts."""
    source_hits = list(getattr(result, "hits", []) or [])
    by_source = {hit.source_id: hit for hit in source_hits}
    hits: List[Dict[str, Any]] = []
    for span in getattr(result, "spans", []) or []:
        hit = by_source.get(span.source_id)
        hits.append(
            {
                "span_id": span.span_id,
                "source_id": span.source_id,
                "text": span.text[:500],
                "title": hit.title if hit else "",
                "year": hit.year if hit else None,
                "venue": hit.venue if hit else "",
                "full_text": True,
                "url": (hit.url or "") if hit else "",
            }
        )
        if len(hits) >= limit:
            break
    if not hits:
        for hit in source_hits[:limit]:
            hits.append(
                {
                    "span_id": "",
                    "source_id": hit.source_id,
                    "text": (hit.abstract or "")[:400],
                    "title": hit.title,
                    "year": hit.year,
                    "venue": hit.venue,
                    "full_text": False,
                    "url": hit.url or "",
                }
            )
    return hits


def load_idea_result(path: Any, run_id: str = "") -> IdeaResult:
    """Reuse an approved idea set so a G1 decision can survive into a later run.

    The gate binds to the exact candidate content, so "resume after approval" has to reuse these
    cards instead of regenerating them: a model-generated set will never hash-match a second time.
    """
    import json
    from pathlib import Path as _Path

    payload = json.loads(_Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("idea file must be a JSON object")
    cards: List[IdeaCard] = []
    for index, item in enumerate(payload.get("candidates") or []):
        if not isinstance(item, dict):
            continue
        fields = {key: item[key] for key in IdeaCard.__dataclass_fields__ if key in item}
        # A host answer carries no idea_id: ids are assigned here in order, so a G1 decision taken
        # against this set still matches after reuse.
        fields.setdefault("idea_id", "IDEA-%02d" % (index + 1))
        fields.setdefault("title", str(fields.get("hypothesis") or "")[:80])
        fields.setdefault("hypothesis", "")
        fields.setdefault("falsification", "")
        fields.setdefault("evidence_refs", [])
        if not fields["hypothesis"] and not fields["title"]:
            raise ValueError("idea candidate %d has neither a title nor a hypothesis" % (index + 1))
        if not fields.get("prediction"):
            fields.setdefault("prediction_status", "not_testable_here")
            fields.setdefault("open_slots", list(PREDICTION_SLOTS))
        cards.append(IdeaCard(**fields))
    brief_payload = payload.get("brief")
    brief = None
    if isinstance(brief_payload, dict):
        brief = IdeaBrief(
            **{
                key: brief_payload[key]
                for key in IdeaBrief.__dataclass_fields__
                if key in brief_payload
            }
        )
    return IdeaResult(
        run_id=run_id or str(payload.get("run_id") or ""),
        module=str(payload.get("module") or "idea"),
        spec_version=str(payload.get("spec_version") or ""),
        status=str(payload.get("status") or "candidates_need_human"),
        candidates=cards,
        warnings=list(payload.get("warnings") or []),
        brief=brief,
        prior_art_report=list(payload.get("prior_art_report") or []),
        shortlist=None,
        feedback_constraints_applied=list(payload.get("feedback_constraints_applied") or []),
    )


@dataclass
class IdeaRequest:
    topic: str
    spans: List[Span]
    max_candidates: int = 3
    run_id: str = ""
    language: str = "zh"
    prior_art_searcher: Optional[
        Callable[[str, int], List[Dict[str, Any]]]
    ] = None
    gap_pack: Optional[Dict[str, Any]] = None
    generation_constraints: Optional[List[Dict[str, Any]]] = None


def _spread_spans(spans: List[Span], limit: int) -> List[Span]:
    """Round-robin across sources instead of taking a prefix.

    Spans arrive grouped by source, so a prefix of the first 24 is usually one paper. A candidate
    grounded in that payload can never cite two sources, and the pre-review then tells every idea
    to "revise" for relying on a single source — a verdict the payload made unavoidable.
    """
    by_source: Dict[str, List[Span]] = {}
    for span in spans:
        by_source.setdefault(str(span.source_id), []).append(span)
    queues = [by_source[key] for key in sorted(by_source)]
    picked: List[Span] = []
    index = 0
    while len(picked) < limit and any(index < len(queue) for queue in queues):
        for queue in queues:
            if index < len(queue) and len(picked) < limit:
                picked.append(queue[index])
        index += 1
    return picked


class IdeaAgent:
    module_id = "idea"

    def __init__(
        self,
        spec: ModuleSpec,
        proposer: Optional[IdeaProposer] = None,
        strict_model: bool = False,
    ):
        if spec.id != self.module_id:
            raise IdeaError("spec id must be 'idea'")
        self.spec = spec
        self.proposer = proposer
        self.strict_model = strict_model

    def _run_id(self, provided: str) -> str:
        if provided:
            return provided
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return "IDEA-%s-%s" % (stamp, uuid.uuid4().hex[:6])

    _STOPWORDS = {
        "the", "a", "an", "of", "to", "in", "and", "or", "for", "on", "with",
        "by", "from", "is", "are", "was", "were", "be", "been", "this", "that",
        "these", "those", "using", "use", "into", "as", "at", "we", "our", "it",
    }
    _LENSES = ("mechanism", "boundary", "measurement")
    _LENS_LABELS = {"mechanism": "机制", "boundary": "边界", "measurement": "测量"}
    _LENS_LABELS_EN = {"mechanism": "Mechanism", "boundary": "Boundary", "measurement": "Measurement"}

    def _tokens(self, text: str) -> Set[str]:
        lowered = text.lower().replace("–", " ").replace("—", " ").replace("-", " ")
        terms = re.findall(r"[a-z0-9_]+|[一-鿿]{2,}", lowered)
        return {term for term in terms if term not in self._STOPWORDS}

    def _prior_tokens(self, text: str) -> Set[str]:
        tokens = self._tokens(text)
        for run in re.findall(r"[一-鿿]+", text):
            for size in (2, 3):
                for index in range(len(run) - size + 1):
                    tokens.add(run[index : index + size])
        return tokens

    def _section(self, span: Span) -> str:
        return (span.section or "section").strip().lower()

    def _clusters(self, spans: List[Span], max_candidates: int) -> List[List[Span]]:
        groups: List[List[Span]] = []
        group_tokens: List[Set[str]] = []
        first_index: List[int] = []
        for index, span in enumerate(spans):
            tokens = self._tokens(span.text)
            best = None
            best_similarity = 0.0
            for group_index, group in enumerate(groups):
                if self._section(group[0]) != self._section(span):
                    continue
                if group[0].source_id == span.source_id:
                    similarity = 1.0
                else:
                    union = group_tokens[group_index] | tokens
                    similarity = len(group_tokens[group_index] & tokens) / len(union) if union else 0.0
                if similarity > best_similarity:
                    best = group_index
                    best_similarity = similarity
            if best is not None and best_similarity >= 0.15:
                groups[best].append(span)
                group_tokens[best] |= tokens
            else:
                groups.append([span])
                group_tokens.append(set(tokens))
                first_index.append(index)
        if len(groups) <= max_candidates:
            return groups
        ranked = sorted(range(len(groups)), key=lambda i: (-len(groups[i]), first_index[i]))
        keep = sorted(ranked[:max_candidates], key=lambda i: first_index[i])
        return [groups[i] for i in keep]

    def _excerpt(self, span: Span, limit: int = 90) -> str:
        excerpt = span.text.strip()
        return excerpt if len(excerpt) <= limit else excerpt[:limit] + "…"

    def _hypothesis(
        self,
        lens: str,
        excerpt: str,
        language: str = "zh",
        contrast: Optional[str] = None,
    ) -> str:
        if language == "en":
            if contrast:
                if lens == "boundary":
                    return (
                        "Evidence A reports \"%s\" while a different source reports \"%s\"; "
                        "if the effect holds only inside A's boundary, moving to B's condition "
                        "should show measurable degradation. Boundary and minimum effect still "
                        "need human input." % (excerpt, contrast)
                    )
                if lens == "measurement":
                    return (
                        "Evidence A reports \"%s\" while a different source reports \"%s\"; "
                        "if the difference comes from measurement/protocol, unifying the "
                        "protocol should shrink or make the contrast measurable. Measurement "
                        "and seeds still need human input." % (excerpt, contrast)
                    )
                return (
                    "Evidence A reports \"%s\" while a different source reports \"%s\"; "
                    "if a mechanism explains the gap, changing that mechanism under a fixed "
                    "protocol should move the primary metric toward B. Mechanism and metric "
                    "still need human input." % (excerpt, contrast)
                )
            if lens == "boundary":
                return (
                    "If the effect implied by \"%s\" holds only inside a specific data/condition boundary, "
                    "cross-condition replication should show measurable degradation; the boundary and minimum "
                    "effect still need human input." % excerpt
                )
            if lens == "measurement":
                return (
                    "If \"%s\" is turned into a repeatable contrast/measurement, the primary metric should be "
                    "distinguishable under the same evaluation protocol; the measurement definition and seeds "
                    "still need human input." % excerpt
                )
            return (
                "If the mechanism or key condition described by \"%s\" changes, the primary metric should show "
                "a measurable change under a fixed protocol, baseline, and budget; the mechanism and metric "
                "still need human input." % excerpt
            )
        if contrast:
            if lens == "boundary":
                return (
                    "证据 A 报告「%s」，另一独立来源报告「%s」；若 A 的效应只在特定边界内成立，"
                    "跨到 B 的条件应出现可测退化。边界与最小效应需人工补全。"
                    % (excerpt, contrast)
                )
            if lens == "measurement":
                return (
                    "证据 A 报告「%s」，另一独立来源报告「%s」；若差异来自测量/协议，"
                    "统一口径后差异应缩小或可区分。测量口径与 seeds 需人工补全。"
                    % (excerpt, contrast)
                )
            return (
                "证据 A 报告「%s」，另一独立来源报告「%s」；若某个机制能解释这一差异，"
                "在固定协议下改变该机制应使主指标向 B 移动。机制与指标需人工补全。"
                % (excerpt, contrast)
            )
        if lens == "boundary":
            return (
                "若「%s」所暗示的效应只在特定数据/条件边界内成立，则跨条件复现时应出现可测退化；"
                "边界与最小效应需人工补全。" % excerpt
            )
        if lens == "measurement":
            return (
                "若把「%s」改造成可重复的对照/测量，则在同一评价协议下主指标应可区分；"
                "测量口径与 seeds 需人工补全。" % excerpt
            )
        return (
            "若改变「%s」所描述的机制或关键条件，则在固定协议、同 baseline、同预算下，"
            "主指标应出现可测变化；机制与指标需人工补全。" % excerpt
        )

    def _proposer_payload(self, request: IdeaRequest) -> Dict[str, Any]:
        payload = {
            "topic": request.topic,
            "language": request.language,
            "max_candidates": request.max_candidates,
            "evidence": [
                {
                    "ref": span.span_id,
                    "source": span.source_id,
                    "section": span.section,
                    "text": span.text.strip()[:500],
                }
                for span in _spread_spans(request.spans, 24)
            ],
        }
        constraints = []
        for item in request.generation_constraints or []:
            if not isinstance(item, dict) or not item.get("constraint"):
                continue
            entry = {
                "loop_id": str(item.get("loop_id") or ""),
                "constraint": str(item.get("constraint") or ""),
            }
            if item.get("constraint_kind"):
                entry["constraint_kind"] = str(item.get("constraint_kind"))
            if isinstance(item.get("payload"), dict):
                entry["payload"] = item["payload"]
            constraints.append(entry)
        if constraints:
            payload["generation_constraints"] = constraints
        return payload

    def _model_cards(
        self, raw: List[Dict[str, Any]], request: IdeaRequest
    ) -> Tuple[List[IdeaCard], List[str]]:
        span_by_id = {span.span_id: span for span in request.spans}
        cards: List[IdeaCard] = []
        rejected: List[str] = []
        for index, item in enumerate(raw[: request.max_candidates], start=1):
            title = str(item.get("title") or "").strip()
            hypothesis = str(item.get("hypothesis") or "").strip()
            falsification = str(item.get("falsification") or "").strip()
            if not (3 <= len(title) <= 240):
                rejected.append("candidate %d: title" % index)
                continue
            if not (10 <= len(hypothesis) <= 1200):
                rejected.append("candidate %d: hypothesis" % index)
                continue
            if not (10 <= len(falsification) <= 1200):
                rejected.append("candidate %d: falsification" % index)
                continue
            raw_refs = item.get("evidence_refs")
            if not isinstance(raw_refs, list):
                rejected.append("candidate %d: evidence_refs" % index)
                continue
            refs: List[str] = []
            for value in raw_refs:
                ref = str(value).strip()
                if ref in span_by_id and ref not in refs:
                    refs.append(ref)
                if len(refs) >= 4:
                    break
            if not refs:
                rejected.append("candidate %d: unknown evidence_refs" % index)
                continue
            lens = str(item.get("lens") or "").strip().lower()
            if lens not in self._LENSES:
                lens = self._LENSES[(index - 1) % len(self._LENSES)]
            sources = {span_by_id[ref].source_id for ref in refs}
            # Keep the proposer's structured prediction verbatim. IDEA_SYSTEM
            # asks for a nested `prediction` object; flat top-level slots are
            # still accepted for older/host answers. Dropping these slots used
            # to turn a model-supplied testable prediction into free text with
            # a hardcoded `needs_metric` marker.
            supplied = item.get("prediction")
            source = supplied if isinstance(supplied, dict) else item
            prediction = {
                key: source[key]
                for key in PREDICTION_SLOTS
                if source.get(key) not in (None, "", [], {})
            }
            cards.append(
                IdeaCard(
                    idea_id="IDEA-%02d" % (len(cards) + 1),
                    title=title,
                    hypothesis=hypothesis,
                    falsification=falsification,
                    evidence_refs=refs,
                    lens=lens,
                    evidence_count=len(refs),
                    source_count=len(sources),
                    novelty_status="unverified",
                    testability="needs_metric",
                    prediction=prediction or None,
                )
            )
        return cards, rejected

    def _kill_criteria(self, language: str) -> str:
        if language == "en":
            return (
                "Drop or reshape if the nearest prior work already covers this "
                "mechanism/boundary/measurement, or if the primary metric shows no "
                "measurable difference under the fixed protocol."
            )
        return (
            "若最近 prior work 已覆盖该机制/边界/测量，或在固定协议下主指标"
            "无可测差异，则放弃或改写。"
        )

    def _s1_prior_art(
        self, card: IdeaCard, spans: List[Span]
    ) -> Tuple[List[str], Optional[Span]]:
        own = set(card.evidence_refs)
        own_sources = {
            span.source_id for span in spans if span.span_id in own
        }
        query_tokens = self._prior_tokens(card.title + " " + card.hypothesis)
        scored: List[Tuple[float, Span]] = []
        for span in spans:
            if span.span_id in own or span.source_id in own_sources:
                continue
            tokens = self._prior_tokens(span.text)
            overlap = len(query_tokens & tokens)
            if overlap <= 0:
                continue
            union = len(query_tokens | tokens) or 1
            scored.append((overlap / union, span))
        scored.sort(key=lambda pair: (-pair[0], pair[1].span_id))
        chosen: List[Span] = []
        for _, span in scored:
            if chosen and span.source_id in {item.source_id for item in chosen}:
                continue
            chosen.append(span)
            if len(chosen) >= 2:
                break
        return [span.span_id for span in chosen], (chosen[0] if chosen else None)

    def _s1_delta(self, nearest: Optional[Span], language: str) -> str:
        if language == "en":
            if nearest:
                return (
                    "Nearest S1 evidence \"%s\" is prior-art context, not a novelty "
                    "check; state what this candidate changes relative to it. A live "
                    "prior-art search is still required."
                    % self._excerpt(nearest, 70)
                )
            return (
                "No other S1 span matched this candidate; novelty remains "
                "unverified and a live prior-art search is required."
            )
        if nearest:
            return (
                "最近 S1 证据「%s」仅作 prior-art 上下文，不是新颖性核验；"
                "需说明本候选相对它改变了什么，仍须做实时 prior-art 检索。"
                % self._excerpt(nearest, 70)
            )
        return (
            "S1 中没有其他 span 与该候选匹配；novelty 仍未核验，"
            "须做实时 prior-art 检索。"
        )

    def _annotate_prior_art(
        self, cards: List[IdeaCard], request: IdeaRequest
    ) -> List[Dict[str, Any]]:
        report: List[Dict[str, Any]] = []
        for card in cards:
            entry: Dict[str, Any] = {
                "idea_id": card.idea_id,
                "query": "",
                "scope": "none",
                "hits": [],
            }
            used_live = False
            if request.prior_art_searcher is not None:
                query = (card.title + " " + card.hypothesis).strip()[:500]
                entry["query"] = query
                try:
                    raw_hits = request.prior_art_searcher(query, 3)
                except Exception as exc:
                    entry["error"] = "%s: %s" % (type(exc).__name__, exc)
                    raw_hits = []
                evidence_span_ids = set(card.evidence_refs)
                evidence_source_ids = {
                    span.source_id
                    for span in request.spans
                    if span.span_id in evidence_span_ids
                }
                hits: List[Dict[str, Any]] = []
                for hit in raw_hits or []:
                    if not isinstance(hit, dict):
                        continue
                    text = str(hit.get("text") or "").strip()
                    span_id = str(hit.get("span_id") or "").strip()
                    source_id = str(hit.get("source_id") or "").strip()
                    if not text and not span_id:
                        continue
                    if span_id and span_id in evidence_span_ids:
                        continue
                    if source_id and source_id in evidence_source_ids:
                        continue
                    hits.append(
                        {
                            "span_id": span_id,
                            "source_id": str(hit.get("source_id") or ""),
                            "title": str(hit.get("title") or ""),
                            "year": hit.get("year"),
                            "venue": str(hit.get("venue") or ""),
                            "text": text[:400],
                            "full_text": bool(hit.get("full_text")),
                            "url": str(hit.get("url") or ""),
                        }
                    )
                    if len(hits) >= 3:
                        break
                if hits:
                    full = [
                        hit
                        for hit in hits
                        if hit["full_text"] and hit["span_id"]
                    ]
                    card.prior_art_refs = [hit["span_id"] for hit in full[:2]]
                    card.prior_art_scope = (
                        "live_search" if full else "live_abstract"
                    )
                    nearest = hits[0]
                    label = (
                        nearest["title"]
                        or nearest["source_id"]
                        or "live hit"
                    )
                    if request.language == "en":
                        card.prior_art_delta = (
                            "Live prior-art hit \"%s\": %s. This is a search clue, "
                            "not a novelty result; state what the candidate changes "
                            "relative to it."
                            % (label, nearest["text"] or "(metadata only)")
                        )
                    else:
                        card.prior_art_delta = (
                            "实时 prior-art 命中「%s」：%s。这是检索线索，"
                            "不是新颖性结论；需说明候选相对它改变了什么。"
                            % (label, nearest["text"] or "（仅元数据）")
                        )
                    card.kill_criteria = self._kill_criteria(request.language)
                    entry["scope"] = card.prior_art_scope
                    entry["hits"] = hits
                    report.append(entry)
                    used_live = True
            if used_live:
                continue
            refs, nearest = self._s1_prior_art(card, request.spans)
            card.prior_art_refs = refs
            card.prior_art_scope = "s1_corpus" if refs else "none"
            card.prior_art_delta = self._s1_delta(nearest, request.language)
            card.kill_criteria = self._kill_criteria(request.language)
            entry["scope"] = card.prior_art_scope
            if nearest is not None:
                entry["hits"] = [
                    {
                        "span_id": nearest.span_id,
                        "source_id": nearest.source_id,
                        "title": "",
                        "year": None,
                        "venue": "",
                        "text": nearest.text[:400],
                        "full_text": True,
                        "url": "",
                    }
                ]
            report.append(entry)
        return report

    def _shortlist(
        self, cards: List[IdeaCard], language: str,
        demoted: Optional[Set[str]] = None,
    ) -> IdeaShortlist:
        prior_weight = {
            "live_search": 3,
            "live_abstract": 2,
            "s1_corpus": 1,
            "none": 0,
        }
        demoted_ids = demoted or set()

        def score(card: IdeaCard) -> Tuple[int, int, int, int, int, int]:
            return (
                0 if card.idea_id in demoted_ids else 1,
                prior_weight.get(card.prior_art_scope, 0),
                1 if card.contrast_refs else 0,
                1 if card.evidence_count >= 2 else 0,
                1 if card.source_count >= 2 else 0,
                1 if card.kill_criteria else 0,
            )

        ranked_cards = sorted(
            cards,
            key=lambda card: (
                score(card),
                card.evidence_count,
                card.source_count,
                card.idea_id,
            ),
            reverse=True,
        )
        ranked = [
            {
                "rank": rank,
                "idea_id": card.idea_id,
                "title": card.title,
                "evidence_count": card.evidence_count,
                "source_count": card.source_count,
                "prior_art_scope": card.prior_art_scope,
                "novelty_status": card.novelty_status,
                "testability": card.testability,
                "has_kill_criteria": bool(card.kill_criteria),
                "has_contrast": bool(card.contrast_refs),
            }
            for rank, card in enumerate(ranked_cards, start=1)
        ]
        if demoted_ids:
            for entry, card in zip(ranked, ranked_cards):
                entry["feedback_demoted"] = card.idea_id in demoted_ids
        if language == "en":
            criteria = [
                "prior-art scope",
                "cross-source contrast",
                "evidence count",
                "cross-source support",
                "kill criteria",
            ]
            if demoted_ids:
                criteria.insert(0, "feedback demotion (prior review verdicts)")
            boundary = (
                "Advisory comparison only; no novelty score and no automatic G1 "
                "selection. Human G1 must choose."
            )
        else:
            criteria = [
                "prior-art 范围",
                "跨来源对照",
                "证据数量",
                "跨来源支持",
                "kill criteria",
            ]
            if demoted_ids:
                criteria.insert(0, "反馈降权（先前评审判定）")
            boundary = (
                "仅作对比参考；不评分 novelty、不自动选短名单；G1 必须由人选择。"
            )
        return IdeaShortlist(
            ranked=ranked,
            selection="human_g1",
            criteria=criteria,
            boundary=boundary,
        )

    def _lens_for_section(self, section: str, fallback_index: int) -> str:
        value = (section or "").strip().lower()
        if any(
            term in value
            for term in ("limitation", "discussion", "局限", "讨论", "威胁")
        ):
            return "boundary"
        if any(
            term in value
            for term in (
                "evaluation",
                "benchmark",
                "result",
                "评测",
                "基准",
                "结果",
                "实验",
            )
        ):
            return "measurement"
        if any(term in value for term in ("method", "approach", "方法")):
            return "mechanism"
        return self._LENSES[(fallback_index - 1) % len(self._LENSES)]

    _CONTRAST_SECTIONS = (
        "limitation",
        "discussion",
        "evaluation",
        "benchmark",
        "局限",
        "讨论",
        "评测",
    )

    def _contrast_for_group(
        self,
        group: List[Span],
        spans: List[Span],
        topic_tokens: Set[str],
        exclude: Optional[Set[str]] = None,
        used_sources: Optional[Set[str]] = None,
    ) -> Optional[Span]:
        evidence_sources = {span.source_id for span in group}
        excluded = exclude or set()
        used = used_sources or set()
        candidates = [
            span
            for span in spans
            if span.source_id not in evidence_sources and span.span_id not in excluded
        ]
        if not candidates:
            return None

        def score(span: Span) -> Tuple[int, int, int, int]:
            section = (span.section or "").lower()
            bonus = 2 if any(
                term in section for term in self._CONTRAST_SECTIONS
            ) else 0
            overlap = len(self._prior_tokens(span.text) & topic_tokens)
            fresh = 0 if span.source_id in used else 1
            return (fresh, bonus, overlap, len(span.text.strip()))

        ranked = sorted(candidates, key=score, reverse=True)
        best = ranked[0]
        if score(best)[2] == 0:
            return None
        return best

    def _annotate_contrast(
        self, cards: List[IdeaCard], request: IdeaRequest
    ) -> None:
        topic_tokens = self._prior_tokens(request.topic)
        for card in cards:
            if card.contrast_refs:
                continue
            group = [
                span
                for span in request.spans
                if span.span_id in card.evidence_refs
            ]
            contrast = self._contrast_for_group(
                group, request.spans, topic_tokens
            )
            if contrast is not None:
                card.contrast_refs = [contrast.span_id]
                card.contrast_note = self._excerpt(contrast, 90)

    @staticmethod
    def _classify_prediction(
        prediction: Optional[Dict[str, Any]],
    ) -> Tuple[str, List[str]]:
        """Pure: decide whether a candidate carries a testable prediction.

        No lexical guessing about the research object. The executable registry
        is the only authority on whether a plan can be run here, so a plan whose
        dataset/metric/profile are not listed is rejected rather than waved through.
        """
        if not isinstance(prediction, dict) or not prediction:
            return "not_testable_here", list(PREDICTION_SLOTS)
        missing = [key for key in PREDICTION_SLOTS if not prediction.get(key)]
        if missing:
            return "cannot_test", missing
        from ..executable import validate_plan

        verdict = validate_plan(
            {
                "profile": prediction.get("profile"),
                "dataset": prediction.get("dataset"),
                "metric": prediction.get("metric"),
            }
        )
        if not verdict.get("ok"):
            return "cannot_test", []
        return "testable", []

    @staticmethod
    def _gap_pack_index(
        gap_pack: Optional[Dict[str, Any]],
    ) -> Tuple[Dict[str, str], List[str], List[str]]:
        """Index S1b cross-source themes by the span ids they actually cite.

        Pure projection of S1/S1b receipts: it never invents a gap, a theme or
        a relation. Returns (span_id -> theme_id, cross-source theme ids,
        structured gap refs). A theme whose evidence cannot be resolved to an
        input span is simply never bound to a candidate.
        """
        if not isinstance(gap_pack, dict):
            return {}, [], []
        themes: List[Dict[str, Any]] = []
        for theme in gap_pack.get("themes") or []:
            if not isinstance(theme, dict):
                continue
            try:
                count = int(theme.get("source_count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count >= 2 or len(theme.get("stances") or []) >= 2:
                themes.append(theme)
        index: Dict[str, str] = {}
        theme_ids: List[str] = []
        for theme in themes:
            theme_id = str(theme.get("theme_id") or theme.get("name") or "").strip()
            if not theme_id or theme_id in theme_ids:
                continue
            theme_ids.append(theme_id)
            for stance in theme.get("stances") or []:
                if not isinstance(stance, dict):
                    continue
                # `evidence` is a span id; `ref_id` is a source id and must not
                # be used here or it would fabricate a binding.
                span_id = str(stance.get("evidence") or "").strip()
                if span_id and span_id not in index:
                    index[span_id] = theme_id
        targets: List[str] = []
        for item in gap_pack.get("brief_gaps") or []:
            text = str(item)
            if text.startswith("missing_facets:"):
                for facet in text.split(":", 1)[1].split(","):
                    if facet.strip():
                        targets.append("facet:" + facet.strip())
        for item in gap_pack.get("gaps") or []:
            code = str(item.get("code") or "").strip() if isinstance(item, dict) else str(item).strip()
            if code:
                targets.append("gap:" + code)
        targets.extend("theme:" + theme_id for theme_id in theme_ids)
        return index, theme_ids, targets

    @staticmethod
    def _annotate_gap_relation(
        cards: List[IdeaCard],
        theme_index: Dict[str, str],
        theme_ids: List[str],
        targets: List[str],
    ) -> int:
        """Bind a candidate to a gap only when its evidence really resolves there."""
        bound = 0
        for card in cards:
            hit = next(
                (theme_index[ref] for ref in (card.evidence_refs or []) if ref in theme_index),
                None,
            )
            if hit:
                card.gap_ref = "theme:" + hit
                bound += 1
            elif theme_ids or targets:
                card.gap_ref = "unbound"
            else:
                card.gap_ref = "none"
            if card.source_count < 2:
                card.relation_type = "single_source"
            elif hit:
                card.relation_type = "theme_co_occurrence"
            elif card.contrast_refs:
                card.relation_type = "contrast"
            else:
                card.relation_type = "unclassified"
        return bound

    _BOILERPLATE_RE = re.compile(r"@|©|copyright|arxiv\s*:|author of", re.IGNORECASE)
    _SENTENCE_END_RE = re.compile(r"[.!?。！？;；]")
    _NAME_RE = re.compile(r"[A-Z][a-z]+(?: [A-Z][a-z]+){0,3}")

    def _looks_like_boilerplate(self, text: str) -> bool:
        """Title / author / affiliation lines are not locatable evidence.

        Deliberately a ranking penalty, not a filter: S1 keeps its spans and
        S2 simply prefers a real sentence as each candidate's representative.
        """
        body = (text or "").strip()
        if not body or len(body) < 15:
            return True
        if self._BOILERPLATE_RE.search(body):
            return True
        if self._NAME_RE.fullmatch(body):
            return True
        return not self._SENTENCE_END_RE.search(body)

    def _rule_cards(
        self, request: IdeaRequest, force_diversity: bool = False
    ) -> Tuple[List[IdeaCard], bool]:
        cards: List[IdeaCard] = []
        diversity_enforced = False
        topic_tokens = self._prior_tokens(request.topic)
        used_contrasts: Set[str] = set()
        used_contrast_sources: Set[str] = set()
        for index, group in enumerate(self._clusters(request.spans, request.max_candidates), start=1):
            ranked_group = sorted(
                group,
                key=lambda span: (
                    self._looks_like_boilerplate(span.text),
                    -len(self._prior_tokens(span.text) & topic_tokens),
                    -len(span.text.strip()),
                    span.span_id,
                ),
            )
            refs: List[str] = []
            for span in ranked_group:
                if span.span_id not in refs:
                    refs.append(span.span_id)
                if len(refs) >= 3:
                    break  # keep one slot for cross-source contrast evidence
            representative = ranked_group[0] if ranked_group else group[0]
            excerpt = self._excerpt(representative)
            lens = self._lens_for_section(
                representative.section or "", index
            )
            if (
                force_diversity
                and cards
                and len({card.lens for card in cards}) == 1
                and lens == cards[0].lens
            ):
                # homogeneity feedback: the next generation must not collapse
                # into a single lens; rotate this card to the next one
                lens = self._LENSES[
                    (self._LENSES.index(lens) + 1) % len(self._LENSES)
                ]
                diversity_enforced = True
            contrast = self._contrast_for_group(
                group,
                request.spans,
                topic_tokens,
                exclude=used_contrasts,
                used_sources=used_contrast_sources,
            )
            if contrast is not None:
                used_contrasts.add(contrast.span_id)
                used_contrast_sources.add(contrast.source_id)
            contrast_excerpt = (
                self._excerpt(contrast, 90) if contrast is not None else None
            )
            # The deterministic clusterer groups spans from the same source, so a
            # cluster alone can never ground a cross-source idea. The contrast span
            # is already picked from a different source and already shapes the
            # falsification text; count it as evidence too (still at most 4 refs),
            # while contrast_refs/contrast_note keep its role explicit.
            if contrast is not None and contrast.span_id not in refs and len(refs) < 4:
                refs.append(contrast.span_id)
            span_by_id = {span.span_id: span for span in request.spans}
            sources = {
                span_by_id[ref].source_id for ref in refs if ref in span_by_id
            }
            if request.language == "en":
                title = "[%s] Candidate %02d: around \"%s\"" % (
                    self._LENS_LABELS_EN[lens], index, excerpt,
                )
                falsification = (
                    "Under the preregistered protocol, the primary metric does not "
                    "change or reverses, the A/B gap does not replicate, or the effect "
                    "does not exceed the preregistered minimum effect."
                    if contrast_excerpt
                    else (
                        "Under the preregistered protocol, the primary metric does not "
                        "improve or reverses, or the effect does not exceed the "
                        "preregistered minimum effect."
                    )
                )
            else:
                title = "【%s】候选 %02d：围绕「%s」" % (self._LENS_LABELS[lens], index, excerpt)
                falsification = (
                    "预注册协议下主指标无变化或反向，A/B 差异无法复现，"
                    "或效应不超出预注册最小效应。"
                    if contrast_excerpt
                    else "预注册协议下主指标无改善或反向，或效应不超出预注册最小效应。"
                )
            cards.append(
                IdeaCard(
                    idea_id="IDEA-%02d" % index,
                    title=title,
                    hypothesis=self._hypothesis(
                        lens, excerpt, request.language, contrast_excerpt
                    ),
                    falsification=falsification,
                    evidence_refs=refs,
                    lens=lens,
                    evidence_count=len(refs),
                    source_count=len(sources),
                    novelty_status="unverified",
                    testability="needs_metric",
                    contrast_refs=(
                        [contrast.span_id] if contrast is not None else []
                    ),
                    contrast_note=contrast_excerpt or "",
                )
            )
        return cards, diversity_enforced

    def run(self, request: IdeaRequest) -> IdeaResult:
        if self.spec.status in ("revoked", "deprecated"):
            raise IdeaError("module spec status is %s; refusing to run" % self.spec.status)
        if request.max_candidates < 1:
            raise IdeaError("max_candidates must be >= 1")
        if request.language not in ("zh", "en"):
            raise IdeaError("language must be zh or en")
        candidates: List[IdeaCard] = []
        warnings = [
            "candidate frames only; no novelty ranking, no Claim, no automatic G1",
            "mechanism and metric must be filled by a human before design freeze",
        ]

        if self.strict_model and self.proposer is None and request.spans:
            raise ModelRequiredError("strict idea mode requires a model proposer")
        if self.proposer is not None and request.spans:
            try:
                raw = self.proposer(self._proposer_payload(request))
            except Exception as exc:
                if isinstance(exc, ModelRequiredError):
                    raise
                if self.strict_model:
                    raise ModelRequiredError(
                        "idea proposer failed: %s" % type(exc).__name__
                    )
                raw = None
                warnings.append("idea proposer failed: %s" % type(exc).__name__)
            if raw is not None:
                candidates, rejected = self._model_cards(raw, request)
                if candidates:
                    warnings.append(
                        "model_proposed_candidates: %d accepted; novelty_unverified; G1 required"
                        % len(candidates)
                    )
                if rejected:
                    warnings.append("model candidates rejected: " + "; ".join(rejected[:4]))
                if self.strict_model and not candidates:
                    raise ModelRequiredError("idea model produced no valid candidates")
            elif self.strict_model:
                raise ModelRequiredError("idea model returned no usable output")
        parsed_constraints = []
        for item in request.generation_constraints or []:
            if not isinstance(item, dict) or not item.get("constraint"):
                continue
            kind = _constraint_kind(item)
            if not kind:
                continue
            parsed_constraints.append((item, kind, _constraint_payload(item, kind)))
        homogeneity = [p for p in parsed_constraints if p[1] == "require_lens_diversity"]
        belief = [p for p in parsed_constraints if p[1] == "demote_candidate"]
        t6b = [p for p in parsed_constraints if p[1] == "carry_falsification"]
        pass_through = [
            p for p in parsed_constraints
            if p[1] in ("carry_forward", "require_falsification_binding")
        ]
        applied: List[Dict[str, Any]] = []
        diversity_enforced = False
        if not candidates:
            candidates, diversity_enforced = self._rule_cards(
                request, force_diversity=bool(homogeneity)
            )
        elif (
            homogeneity
            and len(candidates) > 1
            and len({card.lens for card in candidates}) == 1
        ):
            last = candidates[-1]
            last.lens = self._LENSES[
                (self._LENSES.index(last.lens) + 1) % len(self._LENSES)
            ]
            diversity_enforced = True
        for entry, kind, payload in homogeneity:
            applied.append(
                _constraint_provenance(
                    entry,
                    kind,
                    "lens_diversity_enforced" if diversity_enforced else "no_change_needed",
                )
            )
        demoted: Set[str] = set()
        for entry, kind, payload in belief:
            title = str(payload.get("title") or "")
            matched = [
                card.idea_id for card in candidates
                if title and card.title[:120] == title
            ]
            demoted.update(matched)
            provenance = _constraint_provenance(
                entry, kind, "shortlist_demoted" if matched else "no_matching_candidate"
            )
            if matched:
                provenance["idea_ids"] = matched
            applied.append(provenance)
        for entry, kind, payload in t6b:
            condition = str(payload.get("falsification") or "")
            if not condition:
                continue
            for card in candidates:
                card.falsification += (
                    " Carried executed-study falsification (feedback): " + condition
                    if request.language == "en"
                    else " 反馈携带的已执行否证条件：" + condition
                )
            applied.append(_constraint_provenance(entry, kind, "falsification_carried"))
        for entry, kind, payload in pass_through:
            applied.append(
                _constraint_provenance(
                    entry,
                    kind,
                    "no_change_needed" if kind == "carry_forward"
                    else "not_applicable_to_generation",
                )
            )
        self._annotate_contrast(candidates, request)
        theme_index, theme_ids, gap_targets = self._gap_pack_index(request.gap_pack)
        bound = self._annotate_gap_relation(
            candidates, theme_index, theme_ids, gap_targets
        )
        for card in candidates:
            status, slots = self._classify_prediction(card.prediction)
            card.prediction_status = status
            card.open_slots = slots
        prior_art_report = (
            self._annotate_prior_art(candidates, request) if candidates else []
        )
        for entry in prior_art_report:
            if entry.get("error"):
                warnings.append("prior_art_search_failed: %s" % entry["idea_id"])
            elif entry.get("scope") == "live_abstract":
                warnings.append("prior_art_abstract_only: %s" % entry["idea_id"])

        # S1 marks its provenance with fixture_mode, but that flag used to stop at
        # the S1/S2 boundary: IdeaResult had no marker at all, so a candidate built
        # from synthetic spans looked identical to one built from real evidence.
        # Carry the flag forward as an explicit, machine-readable warning.
        input_spans = list(request.spans or [])
        fixture_spans = sum(1 for span in input_spans if getattr(span, "fixture", False))
        if not input_spans:
            warnings.append("source_mode=none: no locatable input span; candidates are not evidence")
        elif fixture_spans:
            warnings.append(
                "source_mode=fixture: %d/%d input spans are synthetic S1 fixtures; "
                "candidate frames are for workflow testing, not research evidence or a claim"
                % (fixture_spans, len(input_spans))
            )
        else:
            warnings.append(
                "source_mode=real: input spans are not marked fixture; "
                "provenance still requires Q0/Claim Curator"
            )

        # Breadth is observable; quality is not. There is no held-out evaluation
        # or human novelty rating in this repository, so the only honest signal
        # is how many independent sources the candidates actually cite.
        input_sources = {span.source_id for span in input_spans}
        cross_source = sum(1 for card in candidates if card.source_count >= 2)
        warnings.append(
            "candidate_breadth=input_sources:%d candidates:%d "
            "cross_source_candidates:%d | structural signal only: no novelty "
            "proof, no held-out eval or human rating, G1 stays a human signature"
            % (len(input_sources), len(candidates), cross_source)
        )
        relations = Counter(card.relation_type for card in candidates)
        warnings.append(
            "synthesis_breadth=gap_pack:%s themes:%d bound_candidates:%d/%d "
            "relations:%s | offline deterministic: agreement/tension not established; "
            "theme_co_occurrence is lexical co-occurrence, not semantic synthesis"
            % (
                "provided" if request.gap_pack is not None else "absent",
                len(theme_ids),
                bound,
                len(candidates),
                ",".join("%s:%d" % (key, value) for key, value in sorted(relations.items())),
            )
        )
        span_by_id = {span.span_id: span for span in input_spans}
        contrast_sources = {
            span_by_id[ref].source_id
            for card in candidates
            for ref in (card.contrast_refs or [])
            if ref in span_by_id
        }
        warnings.append(
            "idea_structure=distinct_contrast_sources:%d unique_falsifications:%d/%d "
            "unique_kill_criteria:%d/%d needs_metric:%d/%d | template frames have no "
            "variable, expected direction or preregistered metric; these are structural "
            "counts, not a research hypothesis or a quality judgement "
            "| prediction_status:%s"
            % (
                len(contrast_sources),
                len({card.falsification for card in candidates}),
                len(candidates),
                len({card.kill_criteria for card in candidates}),
                len(candidates),
                sum(1 for card in candidates if card.testability == "needs_metric"),
                len(candidates),
                ",".join(
                    "%s:%d" % (key, value)
                    for key, value in sorted(
                        Counter(card.prediction_status for card in candidates).items()
                    )
                ),
            )
        )

        if parsed_constraints:
            warnings.append(
                "feedback_constraints_applied=%d loops:%s | prior verdicts shaped this "
                "generation; provenance in feedback_constraints_applied; G1 stays human"
                % (
                    len(applied),
                    ",".join(
                        sorted({str(item[0].get("loop_id") or "") for item in parsed_constraints})
                    ),
                )
            )
        if demoted:
            warnings.append(
                "feedback_belief_revision: demoted %d candidate(s) per prior review verdicts"
                % len(demoted)
            )

        if not request.spans:
            warnings.append("no span supplied; status=needs_evidence")
        if self.spec.status != "active":
            warnings.append("spec status=%s; development-only" % self.spec.status)

        all_sources = {span.source_id for span in request.spans}
        lenses = Counter(card.lens for card in candidates)
        gaps: List[str] = []
        if not request.spans:
            gaps.append("no_span")
        if candidates and any(card.evidence_count < 2 for card in candidates):
            gaps.append("low_evidence_support")
        if candidates and len(all_sources) < 2:
            gaps.append("single_source")
        if candidates and len(all_sources) >= 2 and not any(card.source_count >= 2 for card in candidates):
            gaps.append("no_multi_source_candidate")
        if len(candidates) > 1 and len(lenses) == 1:
            gaps.append("lens_collapse")
        if candidates and any(
            card.prior_art_scope == "none" for card in candidates
        ):
            gaps.append("no_prior_art")
        gaps.append("novelty_unverified")
        if request.gap_pack is None:
            gaps.append("gap_pack_absent")
        elif not [target for target in gap_targets if not target.startswith("theme:")]:
            # S1 coverage gaps are retrieval receipts (missing full text, facet
            # coverage), not scientific gaps. A lexical co-occurrence theme is
            # not a scientific gap either. Say so instead of implying synthesis.
            gaps.append("no_scientific_gap_in_s1")
        if theme_ids and candidates and bound == 0:
            gaps.append("no_gap_grounded")

        if candidates:
            if request.language == "en":
                summary = (
                    "Clustered %d spans from %d sources into %d candidates; %d cite at least two evidence "
                    "items and %d cross sources. Lenses: %s; G1 still needs human convergence and novelty "
                    "remains unverified."
                    % (
                        len(request.spans),
                        len(all_sources),
                        len(candidates),
                        sum(1 for card in candidates if card.evidence_count >= 2),
                        sum(1 for card in candidates if card.source_count >= 2),
                        " / ".join(sorted(lenses)),
                    )
                ) + (
                    " Prior-art is S1 nearest evidence or live search clues, "
                    "not a novelty result."
                )
            else:
                summary = (
                    "从 %d 个 span / %d 个来源聚成 %d 个候选；%d 个引用 ≥2 条证据、%d 个跨来源；"
                    "候选轴：%s；G1 仍需人工收敛，novelty 未核验。"
                    "prior-art 来自 S1 最近证据或实时检索线索，不是新颖性结论。"
                    % (
                        len(request.spans),
                        len(all_sources),
                        len(candidates),
                        sum(1 for card in candidates if card.evidence_count >= 2),
                        sum(1 for card in candidates if card.source_count >= 2),
                        " / ".join(sorted(lenses)),
                    )
                )
        elif request.language == "en":
            summary = "No clusterable span; finish S1 and keep locatable evidence before hypothesis convergence."
        else:
            summary = "没有可聚类的 span；先完成 S1 并保留可定位证据，再进入假设收敛。"

        brief = IdeaBrief(
            candidate_count=len(candidates),
            source_count=len(all_sources),
            multi_ref_candidates=sum(1 for card in candidates if card.evidence_count >= 2),
            multi_source_candidates=sum(1 for card in candidates if card.source_count >= 2),
            lenses=dict(lenses),
            gaps=gaps,
            summary=summary,
        )
        warnings.append("idea_brief: " + summary)
        for gap in gaps:
            if gap != "novelty_unverified":
                warnings.append("idea_coverage_gap: " + gap)

        status = "candidates_need_human" if candidates else "needs_evidence"
        shortlist = (
            self._shortlist(candidates, request.language, demoted=demoted or None)
            if candidates
            else None
        )
        if shortlist is not None:
            warnings.append(
                "idea_shortlist: advisory comparison only; no novelty score; human G1"
            )
        return IdeaResult(
            run_id=self._run_id(request.run_id),
            module=self.module_id,
            spec_version=self.spec.version,
            status=status,
            candidates=candidates,
            warnings=warnings,
            brief=brief,
            prior_art_report=prior_art_report,
            shortlist=shortlist,
            feedback_constraints_applied=applied,
        )

"""Section/sentence-level support audit for a signed claim and paper draft.

This is an advisory audit, not a gate: it never creates or modifies a Claim,
never changes paper slots, and never signs. A model judge is optional; without
one, the audit records a clearly labelled lexical-overlap heuristic instead of
pretending to have semantic entailment.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

SupportJudge = Callable[[Dict[str, Any]], Optional[List[Dict[str, Any]]]]

SUPPORT_LEDGER_VERSION = "0.6"
STATUSES = ("supported", "partial", "contradicted", "insufficient", "not_required")
PROPOSAL_CUES = (
    "本文提出", "我们提出", "我们计划", "本文计划", "拟", "未来工作", "后续实验",
    "研究议程", "实验计划", "可证伪", "待验证", "下一步", "将会",
    "we plan", "future work", "next step", "we propose",
)
FACTUAL_CUES = (
    "已有研究", "研究表明", "结果显示", "实验表明", "文献", "发现", "证明", "显示", "报告",
    "prior work", "studies show", "results show",
)
_SENTENCE_RE = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+")
_CITATION_RE = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9_.:-]*)\]")
_NUMBER_RE = re.compile(r"(?<![\w.])(\d+\.\d+|\d+(?:\.\d+)?%)(?![\w.])")


class SupportAuditError(RuntimeError):
    pass


def _sentences(text: str) -> List[str]:
    parts = [part.strip() for part in _SENTENCE_RE.split(text or "")]
    return [part for part in parts if part]


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", (text or "").lower()))


def _allowed_result_numbers(pack: Dict[str, Any]) -> set:
    contract = pack.get("writing_contract") or {}
    values = set(str(item) for item in (contract.get("allowed_result_numbers") or []))
    signed = (pack.get("claim") or {}).get("signed_claim") or {}
    for assertion in signed.get("assertions") or []:
        for key in ("observed", "value", "target"):
            value = assertion.get(key) if isinstance(assertion, dict) else None
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.add(str(value))
                values.add("%.4f" % float(value))
    statement = str(signed.get("statement") or "")
    values.update(_NUMBER_RE.findall(statement))
    return values


def _precheck_missing(
    sentence: str,
    evidence: List[Dict[str, str]],
    allowed: set,
) -> List[str]:
    numbers = list(dict.fromkeys(_NUMBER_RE.findall(sentence)))
    texts = " ".join(str(item.get("text") or "") for item in evidence)
    return [
        number for number in numbers
        if number not in allowed and number not in texts
    ]


def _lexical_verdict(sentence: str, evidence: List[Dict[str, str]]) -> Dict[str, Any]:
    sentence_tokens = _tokens(sentence)
    evidence_tokens = set()
    for item in evidence:
        evidence_tokens |= _tokens(str(item.get("text") or ""))
    overlap = (
        len(sentence_tokens & evidence_tokens) / len(sentence_tokens)
        if sentence_tokens else 0.0
    )
    if not evidence:
        status = "insufficient"
    elif overlap >= 0.55:
        status = "partial"
    else:
        status = "insufficient"
    return {
        "status": status,
        "rationale": (
            "lexical overlap %.2f; heuristic only, not semantic entailment" % overlap
            if status == "partial" else
            "lexical overlap %.2f; no semantic judge available" % overlap
        ),
        "method": "lexical_overlap_heuristic",
    }


def _validate_verdicts(
    raw: List[Dict[str, Any]],
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_id = {item["id"]: item for item in items}
    accepted: List[Dict[str, Any]] = []
    for value in raw:
        if not isinstance(value, dict):
            continue
        item_id = str(value.get("id") or "").strip()
        item = by_id.get(item_id)
        if item is None:
            continue
        status = str(value.get("status") or "").strip().lower()
        if status not in STATUSES:
            continue
        rationale = str(value.get("rationale") or "").strip()[:600]
        refs = [
            str(ref)
            for ref in (value.get("evidence_refs") or [])
            if str(ref) in {entry["ref"] for entry in item["evidence"]}
        ]
        accepted.append({
            "id": item_id,
            "section": item["section"],
            "sentence": item["sentence"],
            "citation_mode": item["citation_mode"],
            "status": status,
            "rationale": rationale,
            "evidence_refs": refs or [entry["ref"] for entry in item["evidence"]],
            "method": "model_judge",
        })
    return accepted


def audit_support(
    paper: Dict[str, Any],
    spans: List[Dict[str, Any]],
    claim: Optional[Dict[str, Any]] = None,
    judge: Optional[SupportJudge] = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """Audit draft sentences against the evidence refs attached to their section."""
    span_by_id = {
        str(item.get("span_id") or ""): str(item.get("text") or "")
        for item in spans
        if isinstance(item, dict) and item.get("span_id")
    }
    spans_by_source: Dict[str, List[str]] = {}
    for item in spans:
        if not isinstance(item, dict) or not item.get("span_id"):
            continue
        spans_by_source.setdefault(str(item.get("source_id") or ""), []).append(
            str(item["span_id"])
        )
    items: List[Dict[str, Any]] = []
    mode_counts: Dict[str, int] = {}
    for section in paper.get("draft") or []:
        if not isinstance(section, dict):
            continue
        section_refs = [
            str(ref) for ref in (section.get("evidence_refs") or [])
            if str(ref) in span_by_id
        ][:5]
        for sentence in _sentences(str(section.get("text") or "")):
            if len(sentence) < 24:
                continue
            explicit = _CITATION_RE.findall(sentence)
            refs: List[str] = []
            mode = ""
            if explicit:
                refs = [ref for ref in explicit if ref in span_by_id]
                mode = "explicit_span"
                if not refs:
                    for source_id in explicit:
                        refs.extend(spans_by_source.get(source_id) or [])
                    mode = "explicit_source" if refs else "unresolved_explicit"
                refs = list(dict.fromkeys(refs))[:5]
            if not refs and not explicit:
                refs = section_refs
                mode = "section_fallback"
            evidence = [{"ref": ref, "text": span_by_id[ref][:800]} for ref in refs]
            if not evidence and mode != "unresolved_explicit":
                continue
            items.append({
                "id": "SUP-%02d" % (len(items) + 1),
                "section": str(section.get("section") or "section"),
                "sentence": sentence[:800],
                "citation_mode": mode,
                "evidence": evidence,
            })
            mode_counts[mode] = mode_counts.get(mode, 0) + 1
            if len(items) >= 40:
                break
        if len(items) >= 40:
            break

    report: Dict[str, Any] = {
        "schema_version": "support-audit-0.1",
        "scope": "section/sentence-level support audit; advisory only",
        "items": [],
        "counts": {status: 0 for status in STATUSES},
        "method": "none",
        "citation_modes": dict(mode_counts),
        "claim": {
            "claim_id": str((claim or {}).get("claim_id") or ""),
            "status": str((claim or {}).get("status") or ""),
            "assertions": len((claim or {}).get("assertions") or []),
        },
        "boundary": (
            "No Claim/EA/gate/signature is created or changed; a model verdict is not a "
            "substitute for human review; heuristic mode is not semantic entailment. "
            "In production strict mode a contradicted verdict blocks the job; partial/insufficient remain advisory."
        ),
        "warnings": [],
    }
    if not items:
        report["status"] = "not_applicable"
        report["warnings"].append("no draft sentence had resolvable evidence refs")
        return report

    if strict and judge is None:
        from .models import ModelRequiredError

        raise ModelRequiredError("strict support audit requires a model judge")

    verdicts: List[Dict[str, Any]] = []
    if judge is not None:
        try:
            raw = judge({
                "paper_title": str(paper.get("title") or ""),
                "items": items,
            })
        except Exception as exc:
            from .models import ModelRequiredError

            if isinstance(exc, ModelRequiredError):
                raise
            if strict:
                raise
            report["warnings"].append("support judge failed: %s" % type(exc).__name__)
            raw = None
        if raw:
            verdicts = _validate_verdicts(raw, items)
            if verdicts:
                report["method"] = "model_judge"
            elif strict:
                from .models import ModelRequiredError

                raise ModelRequiredError("support judge returned no valid verdicts")
            else:
                report["warnings"].append("support judge verdicts rejected")
        elif strict:
            from .models import ModelRequiredError

            raise ModelRequiredError("support judge returned no verdicts")

    if not verdicts:
        verdicts = [
            {
                "id": item["id"],
                "section": item["section"],
                "sentence": item["sentence"],
                "citation_mode": item["citation_mode"],
                "evidence_refs": [entry["ref"] for entry in item["evidence"]],
                **_lexical_verdict(item["sentence"], item["evidence"]),
            }
            for item in items
        ]
        report["method"] = "lexical_overlap_heuristic"
        report["warnings"].append(
            "no semantic judge; verdicts are lexical-overlap heuristics and cannot be called supported"
        )

    report["items"] = verdicts
    for verdict in verdicts:
        report["counts"][verdict["status"]] += 1
    if report["counts"]["contradicted"]:
        report["status"] = "attention"
    elif report["counts"]["insufficient"]:
        report["status"] = "partial"
    else:
        report["status"] = "ready"
    return report


_REF_CITATION_RE = re.compile(r"\[(REF-[0-9]{2,})\]")


def _span_maps(pack: Dict[str, Any]) -> tuple:
    references = {
        str(ref.get("ref_id") or ""): str(ref.get("source_id") or "")
        for ref in (((pack.get("literature") or {}).get("references")) or [])
        if isinstance(ref, dict)
    }
    selected = (pack.get("literature") or {}).get("selected_spans") or {}
    span_by_id: Dict[str, Dict[str, str]] = {}
    for source_id, spans in selected.items():
        for span in spans or []:
            if not isinstance(span, dict):
                continue
            span_id = str(span.get("span_id") or "")
            if span_id:
                span_by_id[span_id] = {
                    "source_id": str(source_id),
                    "text": str(span.get("text") or ""),
                }
    evidence_map = {
        str(ref_id): [str(value) for value in values or [] if str(value)]
        for ref_id, values in (pack.get("evidence_map") or {}).items()
    }
    return references, evidence_map, span_by_id


METHOD_CUES = (
    "协议", "步骤", "流程", "方案", "设计", "标注规则", "评分者", "核查", "审计设计",
    "protocol", "procedure", "pipeline", "annotation", "rubric",
)
METHOD_SECTIONS = ("方法", "method", "实验设计", "研究设计")


def _claim_mode(sentence: str, section: str = "") -> str:
    lowered = sentence.lower()
    if any(cue in lowered for cue in FACTUAL_CUES):
        return "claim"
    if any(cue in lowered for cue in PROPOSAL_CUES):
        return "proposal"
    heading = section.lower()
    if any(cue in heading for cue in METHOD_SECTIONS) and any(
        cue in lowered for cue in METHOD_CUES
    ):
        return "proposal"
    return "claim"


def _majority_verdicts(
    runs: List[List[Dict[str, Any]]], items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    severity = {"contradicted": 4, "insufficient": 3, "partial": 2, "supported": 1}
    by_item: Dict[str, List[Dict[str, Any]]] = {}
    for run in runs:
        for verdict in run:
            by_item.setdefault(str(verdict.get("id") or ""), []).append(verdict)
    merged: List[Dict[str, Any]] = []
    for item in items:
        votes = by_item.get(item["id"]) or []
        if not votes:
            continue
        counts: Dict[str, int] = {}
        for verdict in votes:
            status = str(verdict.get("status") or "insufficient")
            counts[status] = counts.get(status, 0) + 1
        status = max(
            counts,
            key=lambda value: (counts[value], severity.get(value, 0)),
        )
        chosen = next(
            (verdict for verdict in votes if verdict.get("status") == status), votes[0]
        )
        merged.append({**chosen, "status": status, "votes": dict(counts)})
    return merged


def summarize_support(report: Dict[str, Any]) -> Dict[str, Any]:
    sections: Dict[str, Dict[str, Any]] = {}
    for item in report.get("items") or []:
        section = str(item.get("section") or "section")
        status = str(item.get("status") or "missing")
        entry = sections.setdefault(
            section,
            {"total": 0, "counts": {value: 0 for value in STATUSES}, "weak_items": []},
        )
        entry["total"] += 1
        entry["counts"][status] = entry["counts"].get(status, 0) + 1
        if status in ("contradicted", "insufficient", "partial"):
            entry["weak_items"].append(
                {
                    "id": item.get("id"),
                    "sentence": str(item.get("sentence") or "")[:240],
                    "status": status,
                    "rationale": str(item.get("rationale") or "")[:240],
                    "refs": item.get("refs") or [],
                }
            )
    weak_sections = []
    for section, entry in sections.items():
        bad = (
            entry["counts"].get("contradicted", 0)
            + entry["counts"].get("insufficient", 0)
            + entry["counts"].get("partial", 0)
        )
        entry["weak"] = bad
        if bad:
            weak_sections.append(
                {"section": section, "weak": bad, "total": entry["total"]}
            )
    weak_sections.sort(key=lambda item: (-item["weak"], item["section"]))
    return {
        "sections": sections,
        "weak_sections": weak_sections,
        "boundary": (
            "Section summary is a read-only prioritization aid over the submitted "
            "support verdicts; it is not a truth or peer-review judgment."
        ),
    }


def _write_support_cache(report: Dict[str, Any], cache_path: Optional[Path]) -> None:
    if not cache_path:
        return
    from .storage import write_json_atomic

    target = Path(cache_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(target, report)


def audit_pack_support(
    draft_path,
    pack: Dict[str, Any],
    judge: Optional[SupportJudge] = None,
    strict: bool = False,
    max_items: int = 80,
    judge_model_id: str = "",
    judge_votes: int = 1,
    judge_batch_size: int = 8,
    cache_path: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
    refresh: bool = False,
    collect_only: bool = False,
) -> Dict[str, Any]:
    """Sentence-level support ledger for a writing pack.

    Every sentence that cites [REF-xx] is resolved to selected spans from the
    pack. A model judge gives supported/partial/contradicted/insufficient
    verdicts; unresolved refs are deterministically insufficient. This is
    stricter and more reference-aware than the legacy section-fallback audit.
    """
    from pathlib import Path

    from .revision_io import read_draft, sha256_file

    limit = max(1, min(int(max_items), 500))
    path = Path(draft_path)
    document = read_draft(path)
    from .writing_pack import numeric_reference_map

    draft_text = "\n".join(
        str(block.text or "")
        for section in document.sections
        for block in section.blocks
    )
    reference_rows = ((pack.get("literature") or {}).get("references")) or []
    numeric_map = numeric_reference_map(draft_text, reference_rows)
    draft_digest = sha256_file(path)
    pack_digest = str(pack.get("pack_sha256") or "") or hashlib.sha256(
        json.dumps(pack, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    cache_key = hashlib.sha256(
        json.dumps(
            {
                "version": SUPPORT_LEDGER_VERSION,
                "draft_sha256": draft_digest,
                "pack_sha256": pack_digest,
                "judge_model": judge_model_id,
                "judge_votes": max(1, min(int(judge_votes), 5)),
                "judge_batch_size": max(1, min(int(judge_batch_size), 20)),
                "max_items": limit,
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    if cache_path is None and cache_dir:
        cache_path = Path(cache_dir) / (cache_key + ".json")
    if cache_path and not refresh:
        try:
            cached = json.loads(Path(cache_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
        if isinstance(cached, dict) and cached.get("cache_key") == cache_key:
            cached["cached"] = True
            return cached
    references, evidence_map, span_by_id = _span_maps(pack)
    collected: List[Dict[str, Any]] = []
    skipped_short_cited = 0
    for section in document.sections:
        heading = str(section.heading or "").lower()
        if "参考文献" in heading or "reference" in heading:
            continue
        for block in section.blocks:
            for sentence in _sentences(str(block.text or "")):
                ref_ids = list(dict.fromkeys(_REF_CITATION_RE.findall(sentence)))
                citation_mode = "explicit_ref"
                if not ref_ids:
                    # The rendered manuscript cites [1], [2]; map those indexes to the pack's
                    # reference order instead of declaring the draft unsupported.
                    numeric = [
                        int(token)
                        for token in re.findall(
                            r"(?<![\d,])\[(\d{1,3})\](?![\d,])", sentence
                        )
                    ]
                    mapped = [
                        numeric_map[index]
                        for index in numeric
                        if index in numeric_map
                    ]
                    if mapped:
                        ref_ids = list(dict.fromkeys(mapped))
                        citation_mode = "numeric_ref"
                if not ref_ids:
                    continue
                if len(sentence) < 8:
                    skipped_short_cited += 1
                    continue
                evidence: List[Dict[str, str]] = []
                unresolved: List[str] = []
                for ref_id in ref_ids:
                    span_ids = evidence_map.get(ref_id) or []
                    if not span_ids:
                        source_id = references.get(ref_id, "")
                        span_ids = [
                            str(span.get("span_id"))
                            for span in ((pack.get("literature") or {}).get("selected_spans") or {}).get(source_id, [])
                            if isinstance(span, dict) and span.get("span_id")
                        ]
                    if not span_ids:
                        unresolved.append(ref_id)
                        continue
                    for span_id in span_ids[:4]:
                        info = span_by_id.get(span_id)
                        if not info:
                            unresolved.append(ref_id)
                            continue
                        evidence.append(
                            {
                                "ref": span_id,
                                "ref_id": ref_id,
                                "source_id": info["source_id"],
                                "text": info["text"][:800],
                            }
                        )
                collected.append(
                    {
                        "id": "SUP-%02d" % (len(collected) + 1),
                        "section": str(section.heading or "section"),
                        "sentence": sentence[:800],
                        "refs": ref_ids,
                        "unresolved_refs": sorted(set(unresolved)),
                        "citation_mode": citation_mode if evidence else "unresolved_ref",
                        "mode": _claim_mode(sentence, str(section.heading or "")),
                        "evidence": evidence,
                        "precheck_missing": _precheck_missing(
                            sentence, evidence, _allowed_result_numbers(pack)
                        ),
                    }
                )

    total_cited = len(collected)
    items = collected[:limit]
    report: Dict[str, Any] = {
        "schema_version": "support-ledger-0.1",
        "scope": "sentence-level [REF-xx] support ledger; evidence limited to selected spans",
        "draft": str(path),
        "draft_sha256": draft_digest,
        "pack_scope": str((pack.get("writing_contract") or {}).get("article_type") or ""),
        "items": [],
        "counts": {status: 0 for status in STATUSES},
        "unresolved_refs": 0,
        "method": "none",
        "judge_model": judge_model_id,
        "judge_votes": max(1, min(int(judge_votes), 5)),
        "judge_batch_size": max(1, min(int(judge_batch_size), 20)),
        "item_limit": limit,
        "total_cited_sentences": total_cited,
        "audited_cited_sentences": len(items),
        "skipped_short_cited": skipped_short_cited,
        "truncated": total_cited > len(items),
        "precheck_failed": 0,
        "cache_key": cache_key,
        "cached": False,
        "strict": bool(strict),
        "status": "not_applicable",
        "warnings": [],
        "boundary": (
            "Support ledger only: it does not create or change Claim/EA/gate/signature, "
            "does not prove semantic entailment in heuristic mode, and never authorizes submission."
        ),
    }
    if skipped_short_cited:
        report["warnings"].append(
            "%d cited sentence(s) shorter than 8 characters were skipped"
            % skipped_short_cited
        )
    if collect_only:
        report["items"] = items
        report["status"] = "collected"
        report["warnings"].append(
            "collect_only: no verdicts; items are for an external/Qoder judge"
        )
        return report
    if not items:
        report["warnings"].append(
            "no sentence cited [REF-xx] or [n]; support audit not applicable"
        )
        _write_support_cache(report, cache_path)
        return report
    if strict and judge is None:
        from .models import ModelRequiredError

        raise ModelRequiredError("strict support ledger requires a model judge")

    judge_items = [
        item for item in items if item["evidence"] and item["mode"] != "proposal"
    ]
    verdicts: List[Dict[str, Any]] = []
    if judge is not None and judge_items:
        batch_size = max(1, min(int(judge_batch_size), 20))
        batches = [
            judge_items[index : index + batch_size]
            for index in range(0, len(judge_items), batch_size)
        ]
        vote_count = max(1, min(int(judge_votes), 5))
        runs: List[List[Dict[str, Any]]] = []
        for _ in range(vote_count):
            vote_verdicts: List[Dict[str, Any]] = []
            for batch in batches:
                payload = {
                    "paper_title": "",
                    "items": [
                        {
                            "id": item["id"],
                            "section": item["section"],
                            "sentence": item["sentence"],
                            "citation_mode": item["citation_mode"],
                            "evidence": item["evidence"],
                        }
                        for item in batch
                    ],
                }
                try:
                    raw = judge(payload)
                except Exception as exc:
                    from .models import ModelRequiredError

                    if isinstance(exc, ModelRequiredError):
                        raise
                    if strict:
                        raise
                    report["warnings"].append(
                        "support judge failed: %s" % type(exc).__name__
                    )
                    raw = None
                if raw:
                    validated = _validate_verdicts(raw, batch)
                    if validated:
                        vote_verdicts.extend(validated)
                    elif strict:
                        from .models import ModelRequiredError

                        raise ModelRequiredError("support judge returned no valid verdicts")
                    else:
                        report["warnings"].append("support judge verdicts rejected")
            if vote_verdicts:
                runs.append(vote_verdicts)
        if runs:
            if len(runs) == 1:
                verdicts = runs[0]
                report["method"] = "model_judge"
            else:
                verdicts = _majority_verdicts(runs, judge_items)
                report["method"] = "model_judge_majority"
            if not verdicts and strict:
                from .models import ModelRequiredError

                raise ModelRequiredError("support judge returned no usable verdicts")

    if not verdicts and judge is None:
        verdicts = [
            {
                "id": item["id"],
                "section": item["section"],
                "sentence": item["sentence"],
                "citation_mode": item["citation_mode"],
                "evidence_refs": [entry["ref"] for entry in item["evidence"]],
                **_lexical_verdict(item["sentence"], item["evidence"]),
            }
            for item in items
        ]
        report["method"] = "lexical_overlap_heuristic"
        report["warnings"].append(
            "no semantic judge; verdicts are lexical-overlap heuristics and cannot be called supported"
        )

    final: List[Dict[str, Any]] = []
    verdict_by_id = {verdict["id"]: verdict for verdict in verdicts}
    for item in items:
        if item["mode"] == "proposal":
            verdict = {
                "id": item["id"],
                "section": item["section"],
                "sentence": item["sentence"],
                "citation_mode": item["citation_mode"],
                "mode": "proposal",
                "status": "not_required",
                "rationale": "proposal/future-work sentence; citations are motivational, not evidential",
                "evidence_refs": [entry["ref"] for entry in item["evidence"]],
                "method": "claim_mode_proposal",
            }
        elif item["unresolved_refs"] and not item["evidence"]:
            verdict = {
                "id": item["id"],
                "section": item["section"],
                "sentence": item["sentence"],
                "citation_mode": item["citation_mode"],
                "status": "insufficient",
                "rationale": "no selected span for cited REF: " + ", ".join(item["unresolved_refs"]),
                "evidence_refs": [],
                "mode": item["mode"],
                "method": "deterministic_no_span",
            }
        else:
            verdict = verdict_by_id.get(item["id"])
            if not verdict:
                verdict = {
                    "id": item["id"],
                    "section": item["section"],
                    "sentence": item["sentence"],
                    "citation_mode": item["citation_mode"],
                    "status": "insufficient",
                    "rationale": "no support verdict returned",
                    "evidence_refs": [entry["ref"] for entry in item["evidence"]],
                    "mode": item["mode"],
                    "method": "missing_verdict",
                }
        missing_numbers = item.get("precheck_missing") or []
        if missing_numbers and verdict.get("status") != "contradicted":
            verdict = {
                "id": item["id"],
                "section": item["section"],
                "sentence": item["sentence"],
                "citation_mode": item["citation_mode"],
                "status": "insufficient",
                "rationale": (
                    "number(s) not found in cited span: "
                    + ", ".join(missing_numbers[:6])
                ),
                "evidence_refs": [entry["ref"] for entry in item["evidence"]],
                "mode": item["mode"],
                "method": "deterministic_evidence_precheck",
                "precheck_missing": missing_numbers,
            }
        verdict["refs"] = item["refs"]
        verdict["unresolved_refs"] = item["unresolved_refs"]
        verdict["evidence"] = item["evidence"]
        verdict["precheck_missing"] = missing_numbers
        verdict.setdefault("mode", item["mode"])
        final.append(verdict)
    report["items"] = final
    for verdict in final:
        report["counts"][verdict["status"]] += 1
        if verdict.get("unresolved_refs") and verdict.get("mode") != "proposal":
            report["unresolved_refs"] += 1
        if verdict.get("precheck_missing") and verdict.get("mode") != "proposal":
            report["precheck_failed"] += 1
    if report["counts"]["contradicted"] or report["unresolved_refs"]:
        report["status"] = "blocked"
    elif report["counts"]["insufficient"] or report["counts"]["partial"]:
        report["status"] = "partial"
    elif report["counts"]["supported"] or report["counts"]["not_required"]:
        report["status"] = "ready"
    if report["truncated"]:
        report["warnings"].append(
            "support ledger truncated: audited %d/%d cited sentences; increase max_items"
            % (report["audited_cited_sentences"], report["total_cited_sentences"])
        )
        if strict:
            report["status"] = "blocked"
        elif report["status"] == "ready":
            report["status"] = "partial"
    report["section_summary"] = summarize_support(report)
    _write_support_cache(report, cache_path)
    return report

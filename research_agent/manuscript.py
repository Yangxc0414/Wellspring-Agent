"""Deterministic Chinese-journal manuscript assembly and audit.

This layer does not create evidence or results. It converts the evidence-bound
working draft into a journal-shaped manuscript, builds numbered citations and a
GB/T 7714-style reference list, and emits a deterministic readiness audit.
"""

import hashlib
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

CITATION_RE = re.compile(r"\[([A-Za-z0-9_.:-]+)\]")
NUMBER_RE = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")
IDENTIFIER_RE = re.compile(r"\b[A-Za-z]{1,}[A-Za-z0-9]*[-_]?\d+[A-Za-z0-9_-]*\b")
FIGURE_REF_RE = re.compile(r"(图|表|Figure|Table|Fig\.?)\s*\d+", re.IGNORECASE)
SENTENCE_RE = re.compile(r"[^。！？!?\n]+[。！？!?]?")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}|[\u4e00-\u9fff]{2,}")
PLACEHOLDER_RE = re.compile(
    r"(TODO|TBD|DATA_NEEDED|待人工补全|待补|\[待补|\.\.\.待|AUTHOR_INPUT_NEEDED)"
)
OVERCLAIM_ZH = ("首次", "突破", "领先", "显著优于", "最优", "完全解决", "填补空白", "毫无疑问")
OVERCLAIM_EN = (
    "first",
    "breakthrough",
    "proves",
    "proven",
    "state-of-the-art",
    "outperforms",
    "unprecedented",
)
AI_PHRASES = (
    "值得注意的是",
    "综上所述",
    "众所周知",
    "不难发现",
    "随着",
    "近年来",
    "赋能",
    "范式",
    "显著提升",
    "有效改善",
)
KEYWORD_STOP = {
    "研究", "文献综述", "综述", "本文", "分析", "方法", "结果", "讨论", "结论",
    "进展", "现状", "应用", "影响", "问题", "study", "review", "research",
    "analysis", "method", "results", "paper",
    # English question and function words leaked into real keywords: the topic
    # "How do self-improving coding agents use archives?" rendered "How" and "use".
    "how", "what", "why", "when", "where", "which", "who", "whom", "whose",
    "does", "did", "the", "and", "not", "for", "with", "from", "into", "about",
    "use", "uses", "used", "using", "are", "was", "were", "been", "being",
    "can", "could", "should", "would", "may", "might", "will", "shall",
    "this", "that", "these", "those", "its", "their", "our", "they",
    "has", "have", "had",
}
META_MARKERS = (
    "本次", "本稿", "本文", "证据边界", "覆盖缺口", "演示数据", "fixture",
    "槽位", "待补", "人工门", "检索", "读取", "candidate", "span", "claim",
    # The deterministic template is bilingual, so the markers must be too: a Chinese-only list
    # let the English copy of the same boundary sentence through as an unsupported claim.
    "evidence boundary", "coverage gap", "demo data", "human gate", "this draft",
    "the draft", "pending until",
)
# A hypothesis or a design field is what the study tests, not a claim that needs a citation.
DESIGN_STATEMENT_MARKERS = (
    "hypothesis (draft)", "research hypothesis", "研究假设（草案）", "假设（草案）",
    "baseline:", "primary metric:", "controls:", "seeds:", "budget:", "stopping rule:",
    "对照：", "主指标：",
)
REQUIRED_KINDS = {
    "zh_core_journal": (
        "abstract", "introduction", "related_work", "method", "setup",
        "results", "discussion", "conclusion",
    ),
    "zh_thesis": (
        "abstract", "introduction", "related_work", "method", "setup",
        "results", "discussion", "conclusion",
    ),
    "en_conference": (
        "abstract", "introduction", "related_work", "method", "setup",
        "results", "discussion", "conclusion",
    ),
    "en_journal": (
        "abstract", "introduction", "related_work", "method", "results",
        "discussion", "limitation", "conclusion",
    ),
}
SECTION_LABELS = {
    "abstract": ("摘要", "Abstract"),
    "introduction": ("引言", "绪论", "Introduction"),
    "related_work": ("相关工作", "Related Work"),
    "method": ("方法", "Method"),
    "setup": ("实验设计", "实验", "Experimental Setup"),
    "results": ("结果", "Results"),
    "discussion": ("讨论", "Discussion"),
    "limitation": ("局限", "Limitations"),
    "conclusion": ("结论", "Conclusion"),
}


class ManuscriptError(ValueError):
    pass


def _norm_title(value: Any) -> str:
    """Fold case and diacritics before dropping punctuation.

    A bibliography card that writes "Darwin Godel" and a corpus card that writes "Darwin Gödel"
    name the same paper; stripping the umlaut instead of folding it made them different strings,
    which silently failed reference verification for that one entry.
    """
    text = unicodedata.normalize("NFKD", str(value or "")).lower()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", text)


def _norm_doi(value: Any) -> str:
    text = str(value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _section_kind(label: str) -> str:
    lowered = str(label or "").lower()
    if "摘要" in label or "abstract" in lowered:
        return "abstract"
    if "引言" in label or "绪论" in label or "introduction" in lowered:
        return "introduction"
    if "相关工作" in label or "related" in lowered:
        return "related_work"
    if "实验设计" in label or "experimental setup" in lowered:
        return "setup"
    if "方法" in label or "method" in lowered:
        return "method"
    if "实验" in label or "experimental" in lowered:
        return "setup"
    if "结果" in label or "result" in lowered:
        return "results"
    if "讨论" in label or "discussion" in lowered:
        return "discussion"
    if "局限" in label or "limitation" in lowered:
        return "limitation"
    if "结论" in label or "conclusion" in lowered:
        return "conclusion"
    if "参考文献" in label or "reference" in lowered:
        return "references"
    return "other"


def _numbers(text: Any) -> List[str]:
    cleaned = IDENTIFIER_RE.sub(" ", str(text or ""))
    cleaned = FIGURE_REF_RE.sub(" ", cleaned)
    return NUMBER_RE.findall(cleaned)


def _draft_sections(paper: Dict[str, Any]) -> List[Dict[str, str]]:
    draft = paper.get("draft") or []
    sections = []
    for item in draft:
        if not isinstance(item, dict):
            continue
        sections.append(
            {
                "label": str(item.get("section", "")),
                "text": str(item.get("text", "")),
            }
        )
    return sections


def _norm_language(paper: Dict[str, Any], language: str = "") -> str:
    if language:
        return language
    profile = paper.get("profile") or {}
    return str(profile.get("language") or "zh")


def _norm_venue(paper: Dict[str, Any], venue_type: str = "") -> str:
    if venue_type:
        return venue_type
    profile = paper.get("profile") or {}
    return str(profile.get("venue_type") or "zh_core_journal")


def _source_pool(
    literature: Dict[str, Any],
    bibliography: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    hits = [item for item in (literature.get("hits") or []) if isinstance(item, dict)]
    brief = literature.get("brief") or {}
    brief_sources = [
        item for item in (brief.get("source_briefs") or []) if isinstance(item, dict)
    ]
    bib_entries = [
        item for item in ((bibliography or {}).get("entries") or []) if isinstance(item, dict)
    ]
    by_doi: Dict[str, Dict[str, Any]] = {}
    by_title: Dict[str, Dict[str, Any]] = {}
    for entry in bib_entries:
        doi = _norm_doi(entry.get("doi"))
        title = _norm_title(entry.get("title"))
        if doi:
            by_doi[doi] = entry
        if title:
            by_title[title] = entry
    meta: Dict[str, Dict[str, Any]] = {}
    for item in brief_sources:
        meta[str(item.get("source_id", ""))] = dict(item)
    for item in hits:
        meta[str(item.get("source_id", ""))] = {**meta.get(str(item.get("source_id", "")), {}), **item}
    refs: Dict[str, Dict[str, Any]] = {}
    matched_bib: set = set()
    for source_id, item in meta.items():
        if not source_id:
            continue
        doi = _norm_doi(item.get("doi"))
        title = _norm_title(item.get("title"))
        entry = by_doi.get(doi) or by_title.get(title)
        if entry is not None:
            matched_bib.add(id(entry))
        refs[source_id] = {
            "source_id": source_id,
            "title": str((entry or {}).get("title") or item.get("title") or ""),
            "authors": list((entry or {}).get("authors") or []),
            "year": (entry or {}).get("year") or item.get("year"),
            "venue": str((entry or {}).get("venue") or item.get("venue") or ""),
            "doi": str((entry or {}).get("doi") or item.get("doi") or ""),
            "url": str((entry or {}).get("url") or item.get("url") or ""),
            "verified": entry is not None,
        }
    extras = []
    for entry in bib_entries:
        if id(entry) in matched_bib:
            continue
        extras.append(
            {
                "source_id": "",
                "title": str(entry.get("title") or ""),
                "authors": list(entry.get("authors") or []),
                "year": entry.get("year"),
                "venue": str(entry.get("venue") or ""),
                "doi": str(entry.get("doi") or ""),
                "url": str(entry.get("url") or ""),
                "verified": True,
            }
        )
    return refs, extras, hits


def _initials(first: str) -> str:
    parts = re.split(r"[\s-]+", first.strip())
    return " ".join(part[0].upper() for part in parts if part)


def _author_text(authors: List[Any], language: str) -> str:
    if not authors:
        return "..."
    rendered: List[str] = []
    for author in authors[:3]:
        text = str(author).strip()
        if not text:
            continue
        if "," in text:
            last, first = text.split(",", 1)
            rendered.append("%s %s" % (last.strip().upper(), _initials(first)))
        else:
            rendered.append(text)
    if len(authors) > 3:
        rendered.append("等" if language == "zh" else "et al.")
    return ", ".join(rendered) + "."


def _entry_type(ref: Dict[str, Any]) -> str:
    if ref.get("venue"):
        return "J"
    return "EB/OL"


def format_gbt7714(ref: Dict[str, Any], number: int, language: str = "zh") -> str:
    authors = _author_text(list(ref.get("authors") or []), language)
    title = str(ref.get("title") or "...").strip().rstrip("。.")
    year = str(ref.get("year") or "...")
    venue = str(ref.get("venue") or "").strip()
    doi = str(ref.get("doi") or "").strip()
    url = str(ref.get("url") or "").strip()
    kind = _entry_type(ref)
    if kind == "J":
        text = "%s %s[J]. %s, %s." % (authors, title, venue or "...", year)
    else:
        link = url or (("https://doi.org/" + doi) if doi else "")
        text = "%s %s[EB/OL]. (%s). %s." % (authors, title, year, link or "...")
    if doi and kind == "J":
        text += " DOI: %s." % doi
    return "[%d] %s" % (number, text)


def _keywords(topic: str, brief: Optional[Dict[str, Any]], language: str) -> List[str]:
    pieces = re.split(r"[\s,，、;；:：/|()（）\[\]【】]+", str(topic or ""))
    words: List[str] = []
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        for token in TOKEN_RE.findall(piece):
            lowered = token.lower()
            if lowered in KEYWORD_STOP or token in KEYWORD_STOP:
                continue
            if len(token) < 2:
                continue
            if token not in words:
                words.append(token)
    return words[:5]


def _manuscript_title(title: Any, topic: str) -> str:
    value = str(title or "").strip()
    for prefix in ("工作稿：", "工作稿:", "Working draft:", "Working draft："):
        if value.startswith(prefix):
            value = value[len(prefix):].strip()
            break
    return value or str(topic or "").strip() or "Untitled manuscript"


def _span_source_map(literature: Dict[str, Any]) -> Dict[str, str]:
    mapping = {}
    for span in literature.get("spans") or []:
        if not isinstance(span, dict):
            continue
        span_id = str(span.get("span_id") or "")
        source_id = str(span.get("source_id") or "")
        if span_id and source_id:
            mapping[span_id] = source_id
    return mapping


def _resolve_token(
    token: str,
    refs: Dict[str, Dict[str, Any]],
    span_source: Dict[str, str],
) -> Tuple[str, bool]:
    if token in refs:
        return token, True
    source_id = span_source.get(token, "")
    if source_id and source_id in refs:
        return source_id, True
    return "", False


def _convert_text(
    text: str,
    refs: Dict[str, Dict[str, Any]],
    span_source: Dict[str, str],
    number_by_source: Dict[str, int],
    ordered_sources: List[str],
    citations: List[Dict[str, Any]],
    unresolved: List[str],
    section: str,
) -> str:
    def replace(match: re.Match) -> str:
        token = match.group(1)
        source_id, ok = _resolve_token(token, refs, span_source)
        if not ok:
            if token not in unresolved:
                unresolved.append(token)
            citations.append(
                {
                    "section": section,
                    "token": token,
                    "status": "unresolved",
                    "reference": "",
                    "number": None,
                    "verified": False,
                }
            )
            return "[待补文献:%s]" % token
        if source_id not in number_by_source:
            ordered_sources.append(source_id)
            number_by_source[source_id] = len(ordered_sources)
        ref = refs[source_id]
        citations.append(
            {
                "section": section,
                "token": token,
                "status": "resolved",
                "reference": source_id,
                "number": number_by_source[source_id],
                "verified": bool(ref.get("verified")),
            }
        )
        return "[%d]" % number_by_source[source_id]

    return CITATION_RE.sub(replace, text)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _span_meta(literature: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    meta: Dict[str, Dict[str, Any]] = {}
    for span in literature.get("spans") or []:
        if not isinstance(span, dict):
            continue
        span_id = str(span.get("span_id") or "")
        text = str(span.get("text") or "")
        if not span_id:
            continue
        meta[span_id] = {
            "source_id": str(span.get("source_id") or ""),
            "quote": text[:500],
            "span_sha256": _sha256_text(text),
            "page": span.get("page"),
        }
    return meta


def _claim_registry(
    sections: List[Dict[str, str]],
    refs: Dict[str, Dict[str, Any]],
    span_source: Dict[str, str],
    span_meta: Dict[str, Dict[str, Any]],
    language: str,
) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    unresolved_all: List[str] = []
    overclaims = OVERCLAIM_ZH if language == "zh" else OVERCLAIM_EN
    for section in sections:
        kind = _section_kind(section["label"])
        if kind in ("abstract", "references", "other"):
            continue
        for sentence in SENTENCE_RE.findall(section["text"]):
            sentence = sentence.strip()
            if not sentence:
                continue
            meta_text = CITATION_RE.sub("", sentence).lower()
            if any(marker in meta_text for marker in META_MARKERS):
                continue
            if meta_text.lstrip().startswith(DESIGN_STATEMENT_MARKERS):
                continue
            tokens = CITATION_RE.findall(sentence)
            numbers = _numbers(sentence)
            has_overclaim = any(word.lower() in sentence.lower() for word in overclaims)
            kinds: List[str] = []
            if tokens:
                kinds.append("citation_bearing")
            if numbers and kind not in ("method", "setup"):
                kinds.append("quantitative")
            if has_overclaim:
                kinds.append("scope_wording")
            if kind == "results":
                kinds.append("result_sentence")
            if not kinds:
                continue
            rows: List[Dict[str, Any]] = []
            resolved_sources: List[str] = []
            unresolved: List[str] = []
            for token in tokens:
                if token in span_meta:
                    meta = span_meta[token]
                    source_id = meta.get("source_id") or span_source.get(token, "")
                    rows.append(
                        {
                            "ref": token,
                            "anchor": "span",
                            "source_id": source_id,
                            "span_id": token,
                            "quote": meta.get("quote", ""),
                            "span_sha256": meta.get("span_sha256", ""),
                            "status": "verified_anchor",
                        }
                    )
                    if source_id and source_id not in resolved_sources:
                        resolved_sources.append(source_id)
                    continue
                source_id, ok = _resolve_token(token, refs, span_source)
                if ok:
                    rows.append(
                        {
                            "ref": token,
                            "anchor": "source_level",
                            "source_id": source_id,
                            "span_id": "",
                            "quote": "",
                            "span_sha256": "",
                            "status": "source_level",
                        }
                    )
                    if source_id not in resolved_sources:
                        resolved_sources.append(source_id)
                    continue
                unresolved.append(token)
                if token not in unresolved_all:
                    unresolved_all.append(token)
            if rows and any(row["status"] == "verified_anchor" for row in rows):
                status = "supported"
                reason = "explicit span anchor with quote hash"
            elif rows:
                status = "source_only"
                reason = "source-level citation has no exact span anchor"
            else:
                status = "needs_evidence"
                reason = "quantitative/scope/result claim has no resolved citation"
            entries.append(
                {
                    "claim_id": "CLM-" + _sha256_text(section["label"] + "\n" + sentence)[:10],
                    "section": section["label"],
                    "sentence": sentence[:500],
                    "claim_text_sha256": _sha256_text(sentence),
                    "candidate_kinds": kinds,
                    "refs": resolved_sources,
                    "numbers": numbers,
                    "evidence_rows": rows,
                    "unresolved_tokens": unresolved,
                    "status": status,
                    "reason": reason,
                }
            )
            if len(entries) >= 200:
                break
        if len(entries) >= 200:
            break
    supported = sum(1 for item in entries if item["status"] == "supported")
    source_only = sum(1 for item in entries if item["status"] == "source_only")
    needs = sum(1 for item in entries if item["status"] == "needs_evidence")
    verified_rows = sum(
        1 for item in entries for row in item["evidence_rows"]
        if row["status"] == "verified_anchor"
    )
    source_rows = sum(
        1 for item in entries for row in item["evidence_rows"]
        if row["status"] == "source_level"
    )
    total = len(entries)
    return {
        "schema_version": "claim-registry-0.1",
        "entries": entries,
        "coverage": {
            "candidates": total,
            "supported": supported,
            "source_only": source_only,
            "needs_evidence": needs,
            # No candidates means the rate is undefined, not perfect: 1.0 here would be a green
            # number produced by an empty set, the failure mode this project keeps auditing.
            "coverage_rate": round((supported + source_only) / total, 4) if total else None,
            "coverage_note": (
                "no candidate sentences were found; the coverage rate is undefined"
                if not total
                else ""
            ),
            "evidence_rows": verified_rows + source_rows,
            "verified_anchor_rows": verified_rows,
            "source_level_rows": source_rows,
            "unresolved_tokens": unresolved_all,
            "semantic_completeness": "unknown",
            "detector": "lexical_citation_quantitative_scope",
        },
        "boundary": (
            "lexical candidate detection; semantic completeness is unknown; "
            "verified anchor means quote/hash provenance, not claim truth"
        ),
    }
def _audit(
    manuscript: Dict[str, Any],
    paper: Dict[str, Any],
    literature: Dict[str, Any],
    ledger: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
    registry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context = context or {}
    registry = registry or {"coverage": {}}
    language = manuscript["language"]
    venue = manuscript["venue_type"]
    checks: List[Dict[str, str]] = []
    blockers: List[str] = []
    warnings: List[str] = []

    def add(check_id: str, status: str, detail: str, severity: str = "warning") -> None:
        checks.append({"id": check_id, "status": status, "detail": detail, "severity": severity})
        if status == "fail" and severity == "blocker":
            blockers.append("%s: %s" % (check_id, detail))
        elif status in ("warn", "fail"):
            warnings.append("%s: %s" % (check_id, detail))

    draft = _draft_sections(paper)
    kinds = {_section_kind(item["label"]) for item in draft}
    raw_title = str(paper.get("title") or "")
    title_internal = raw_title.startswith("工作稿：") or raw_title.lower().startswith("working draft:")
    add(
        "title.derived",
        "warn" if title_internal else "pass",
        "title was derived from the working draft; human polish required"
        if title_internal else "title is author-supplied",
        "warning",
    )
    required = REQUIRED_KINDS.get(venue, REQUIRED_KINDS["zh_core_journal"])
    missing = [kind for kind in required if kind not in kinds]
    add(
        "structure.sections",
        "fail" if missing else "pass",
        "missing: %s" % ", ".join(missing) if missing else "all required sections present",
        "blocker",
    )

    abstract = manuscript.get("abstract") or ""
    if language == "zh":
        labels = ("目的", "方法", "结果", "结论")
        missing_labels = [label for label in labels if label not in abstract]
        add(
            "abstract.structure",
            "warn" if missing_labels else "pass",
            "missing labels: %s" % "、".join(missing_labels) if missing_labels else "structured abstract",
            "warning",
        )
        min_length, max_length = (200, 600) if venue == "zh_core_journal" else (180, 900)
        if not (min_length <= len(abstract) <= max_length):
            add(
                "abstract.length",
                "warn",
                "abstract is %d characters (expected %d-%d)" % (len(abstract), min_length, max_length),
                "warning",
            )
    else:
        if len(abstract) < 120:
            add("abstract.length", "warn", "abstract is %d characters" % len(abstract), "warning")

    keywords = manuscript.get("keywords") or []
    keyword_range = (3, 5) if language == "zh" else (3, 6)
    if not keyword_range[0] <= len(keywords) <= keyword_range[1]:
        add(
            "keywords.count",
            "warn",
            "%d keywords: %s" % (len(keywords), "；".join(keywords) or "none"),
            "warning",
        )
    else:
        add("keywords.count", "pass", "%d keywords" % len(keywords))

    references = manuscript.get("references") or []
    if not references:
        add("references.present", "fail", "no references generated", "blocker")
    else:
        add("references.present", "pass", "%d numbered references" % len(references))
    min_references = 8 if venue == "zh_core_journal" else 5
    if references and len(references) < min_references:
        add(
            "references.coverage",
            "warn",
            "only %d references (target >= %d)" % (len(references), min_references),
            "warning",
        )
    unverified = [ref for ref in references if not ref.get("verified")]
    if unverified:
        add(
            "references.verified",
            "fail",
            "%d cited references lack verified bibliography metadata" % len(unverified),
            "blocker",
        )
    else:
        add("references.verified", "pass", "all cited references have verified metadata")

    unresolved = manuscript.get("unresolved_citations") or []
    add(
        "citations.unresolved",
        "fail" if unresolved else "pass",
        "%d unresolved citation tokens" % len(unresolved) if unresolved else "all citations resolved",
        "blocker",
    )
    if not manuscript.get("citations"):
        add("citations.present", "fail", "no in-text citations", "blocker")
    else:
        add("citations.present", "pass", "%d in-text citations" % len(manuscript["citations"]))

    uncited = manuscript.get("uncited_bibliography") or []
    if uncited:
        add(
            "citations.orphan",
            "warn",
            "%d bibliography entries are not cited" % len(uncited),
            "warning",
        )
    else:
        add("citations.orphan", "pass", "no uncited bibliography entries")

    needs = [item for item in ledger if item.get("status") == "needs_evidence"]
    if needs:
        hard = any(
            item.get("numbers")
            or "result_sentence" in (item.get("candidate_kinds") or [])
            or "scope_wording" in (item.get("candidate_kinds") or [])
            for item in needs
        )
        add(
            "claims.evidence_ledger",
            "fail" if hard else "warn",
            "%d sentences need evidence" % len(needs),
            "blocker" if hard else "warning",
        )
    else:
        add("claims.evidence_ledger", "pass", "all candidate sentences have evidence")
    coverage = registry.get("coverage") or {}
    if coverage.get("candidates"):
        if needs:
            hard = any(
                "quantitative" in (item.get("candidate_kinds") or [])
                or "result_sentence" in (item.get("candidate_kinds") or [])
                or "scope_wording" in (item.get("candidate_kinds") or [])
                for item in needs
            )
            add(
                "claims.registry_coverage",
                "fail" if hard else "warn",
                "%d/%d candidates registered; %d need evidence; semantic completeness unknown"
                % (
                    coverage.get("supported", 0) + coverage.get("source_only", 0),
                    coverage.get("candidates", 0),
                    coverage.get("needs_evidence", 0),
                ),
                "blocker" if hard else "warning",
            )
        elif coverage.get("source_only"):
            add(
                "claims.registry_coverage",
                "warn",
                "%d source-level citation(s) lack exact span anchors"
                % coverage.get("source_only"),
                "warning",
            )
        else:
            add(
                "claims.registry_coverage",
                "pass",
                "%d/%d candidates have verified span anchors"
                % (coverage.get("supported", 0), coverage.get("candidates", 0)),
            )
    else:
        add("claims.registry_coverage", "pass", "no candidate claim sentences")

    text = "\n".join(item["text"] for item in draft)
    results_text = "\n".join(
        item["text"] for item in draft if _section_kind(item["label"]) == "results"
    )
    allowed = _allowed_numbers(context, literature)
    results_numbers = set(_numbers(CITATION_RE.sub("", results_text)))
    unknown = sorted(results_numbers - allowed)
    add(
        "numeric.fidelity",
        "fail" if unknown else "pass",
        (
            "%d result number(s) are outside the allowed set, which is policy rather than "
            "sourcing (the set comes from signed claim statements/assertions, span text and "
            "design fields): %s — run manuscript provenance to see where each value was read "
            "from" % (len(unknown), ", ".join(unknown))
        ) if unknown else "no result numbers outside the allowed set",
        "blocker",
    )
    discussion_text = "\n".join(
        sentence
        for item in draft
        if _section_kind(item["label"]) in ("introduction", "discussion", "conclusion")
        for sentence in SENTENCE_RE.findall(item["text"])
        if not any(marker in CITATION_RE.sub("", sentence).lower() for marker in META_MARKERS)
    )
    scoped_numbers = set(_numbers(CITATION_RE.sub("", discussion_text)))
    scoped_numbers = {number for number in scoped_numbers if not re.fullmatch(r"20\d{2}", number)}
    other_unknown = sorted(scoped_numbers - allowed)
    if other_unknown:
        add(
            "numeric.non_results",
            "warn",
            "numbers outside result evidence: %s" % ", ".join(other_unknown[:10]),
            "warning",
        )

    if PLACEHOLDER_RE.search(text):
        add("placeholders", "fail", "TODO/DATA_NEEDED/待补 marker remains", "blocker")
    else:
        add("placeholders", "pass", "no unresolved placeholders")

    if paper.get("fixture_mode") or literature.get("fixture_mode"):
        add("evidence.fixture", "fail", "fixture evidence is not citable", "blocker")
    else:
        add("evidence.fixture", "pass", "not fixture mode")

    slots = [item for item in (paper.get("slots") or []) if isinstance(item, dict)]
    primary = next((item for item in slots if item.get("slot_id") == "result.primary"), None)
    if primary and primary.get("status") not in ("bound_claim", "bound", "ready"):
        add(
            "results.signed_claim",
            "fail",
            "result.primary is `%s`, not bound to a signed claim" % primary.get("status"),
            "blocker",
        )
    else:
        add("results.signed_claim", "pass", "result slot is bound or not applicable")

    overclaims = OVERCLAIM_ZH if language == "zh" else OVERCLAIM_EN
    over_hits = sorted({word for word in overclaims if word.lower() in text.lower()})
    if over_hits:
        add("style.overclaim", "warn", "scope words: %s" % ", ".join(over_hits), "warning")
    else:
        add("style.overclaim", "pass", "no overclaim vocabulary")

    ai_hits = [phrase for phrase in AI_PHRASES if phrase in text]
    if len(ai_hits) >= 2:
        add("style.ai_phrases", "warn", "boilerplate: %s" % "、".join(ai_hits), "warning")
    else:
        add("style.ai_phrases", "pass", "no excessive boilerplate")

    long_sentences = [
        sentence for sentence in SENTENCE_RE.findall(text)
        if len(re.findall(r"[\u4e00-\u9fff]", sentence)) > 80
    ] if language == "zh" else [
        sentence for sentence in SENTENCE_RE.findall(text)
        if len(sentence.split()) > 45
    ]
    if long_sentences:
        add("readability.sentence", "warn", "%d long sentences" % len(long_sentences), "warning")
    else:
        add("readability.sentence", "pass", "sentence lengths are bounded")

    figure_refs = context.get("figure_refs") or paper.get("figure_refs") or []
    if not figure_refs:
        add("figures.present", "warn", "no figure reference in the paper contract", "warning")
    elif not re.search(r"(图\s*\d|Figure\s*\d|表\s*\d|Table\s*\d)", text):
        add("figures.mentioned", "warn", "figure exists but is not referenced in prose", "warning")
    else:
        add("figures.mentioned", "pass", "figure/table references found")

    claim_signed = bool(context.get("claim_signed"))
    run_summary = context.get("run_summary") or {}
    run_id = str(run_summary.get("run_id") or "") if isinstance(run_summary, dict) else ""
    basis = str(
        context.get("submission_basis")
        or ("empirical" if claim_signed and run_id else "")
    )
    if basis == "empirical":
        add(
            "submission.claim_signed",
            "pass" if claim_signed else "warn",
            "signed claim context present" if claim_signed else "no signed claim context",
            "warning",
        )
        add(
            "submission.run_context",
            "pass" if run_id else "warn",
            "run_id=%s" % run_id if run_id else "no completed run/experiment context",
            "warning",
        )
    elif basis == "review":
        full_texts = sum(
            1
            for hit in (literature.get("hits") or [])
            if isinstance(hit, dict) and hit.get("full_text")
        )
        add(
            "submission.review_full_text",
            "pass" if full_texts >= 3 else "warn",
            "full-text sources=%d" % full_texts,
            "warning",
        )
    else:
        add(
            "submission.basis",
            "warn",
            "no explicit submission_basis; pass claim_signed+run_summary or review basis",
            "warning",
        )

    venue_audit = None
    if str(venue) in ("zh_core_journal", "software_journal", "computer_journal"):
        from .venue_audit import audit_chinese_journal

        venue_audit = audit_chinese_journal(manuscript, profile_name=str(venue))

    status = "blocked" if blockers else "attention" if warnings else "pass"
    return {
        "schema_version": "manuscript-audit-0.1",
        "venue_audit": venue_audit,
        "status": status,
        "submission_ready": status == "pass",
        "submission_basis": basis,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "summary": {
            "blockers": len(blockers),
            "warnings": len(warnings),
            "references": len(references),
            "citations": len(manuscript.get("citations") or []),
            "ledger_needs_evidence": len(needs),
            "claim_registry_candidates": coverage.get("candidates", 0),
            "claim_registry_coverage": coverage.get("coverage_rate", 0),
            "verified_anchor_rows": coverage.get("verified_anchor_rows", 0),
        },
        "boundary": (
            "deterministic structural/evidence audit; not peer review, not a guarantee of "
            "journal acceptance, and not a substitute for real experiments or human writing"
        ),
    }


def _allowed_numbers(
    context: Dict[str, Any],
    literature: Dict[str, Any],
) -> set:
    parts: List[str] = []
    for span in literature.get("spans") or []:
        if isinstance(span, dict):
            parts.append(str(span.get("text") or ""))
    for claim in context.get("claim_statements") or []:
        parts.append(str(claim))
    for assertion in context.get("claim_assertions") or []:
        if isinstance(assertion, dict):
            for key in ("value", "observed", "target", "tolerance"):
                value = assertion.get(key)
                if value is None:
                    continue
                parts.append(str(value))
                # The paper renders observed values rounded to 4/6 decimals; without those
                # forms the audit rejects the paper's own rendering as an unsupported number.
                if isinstance(value, (int, float)):
                    parts.append("%.4f" % value)
                    parts.append("%.6f" % value)
    design = context.get("design") or {}
    if isinstance(design, dict):
        for key in ("seeds", "primary_metric", "budget", "stopping_rule"):
            if design.get(key) is not None:
                parts.append(str(design.get(key)))
        for control in design.get("controls") or []:
            parts.append(str(control))
    run_summary = context.get("run_summary") or {}
    if isinstance(run_summary, dict):
        for value in run_summary.values():
            if value is not None:
                parts.append(str(value))
    return set(_numbers("\n".join(parts)))


def build_manuscript(
    paper: Dict[str, Any],
    literature: Dict[str, Any],
    bibliography: Optional[Dict[str, Any]] = None,
    topic: str = "",
    language: str = "",
    venue_type: str = "",
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    context = context or {}
    language = _norm_language(paper, language)
    venue = _norm_venue(paper, venue_type)
    refs, extras, _hits = _source_pool(literature, bibliography)
    span_source = _span_source_map(literature)
    draft = _draft_sections(paper)
    number_by_source: Dict[str, int] = {}
    ordered_sources: List[str] = []
    citations: List[Dict[str, Any]] = []
    unresolved: List[str] = []
    converted_sections = []
    for section in draft:
        kind = _section_kind(section["label"])
        if kind == "references":
            continue
        text = _convert_text(
            section["text"], refs, span_source, number_by_source, ordered_sources,
            citations, unresolved, section["label"],
        )
        converted_sections.append({"label": section["label"], "text": text})
    abstract_section = next(
        (item for item in converted_sections if _section_kind(item["label"]) == "abstract"), None
    )
    abstract = abstract_section["text"] if abstract_section else ""
    keywords = _keywords(topic or str(paper.get("title") or ""), literature.get("brief"), language)
    references = []
    for source_id in ordered_sources:
        ref = refs[source_id]
        number = number_by_source[source_id]
        references.append(
            {
                "number": number,
                "source_id": source_id,
                "title": ref.get("title", ""),
                "doi": ref.get("doi", ""),
                "verified": bool(ref.get("verified")),
                "text": format_gbt7714(ref, number, language),
            }
        )
    uncited_bibliography = [
        {"title": item.get("title", ""), "doi": item.get("doi", "")}
        for item in extras
    ]
    manuscript = {
        "schema_version": "manuscript-0.1",
        "title": _manuscript_title(paper.get("title"), topic),
        "language": language,
        "venue_type": venue,
        "abstract": abstract,
        "keywords": keywords,
        "sections": converted_sections,
        "references": references,
        "citations": citations,
        "unresolved_citations": sorted(set(unresolved)),
        "uncited_bibliography": uncited_bibliography,
        "boundary": (
            "manuscript assembly is deterministic; citations are mapped to source metadata; "
            "it does not create evidence, numbers or claims"
        ),
    }
    span_meta = _span_meta(literature)
    registry = _claim_registry(draft, refs, span_source, span_meta, language)
    ledger = registry["entries"]
    manuscript["claim_registry_summary"] = registry["coverage"]
    audit = _audit(manuscript, paper, literature, ledger, context=context, registry=registry)
    manuscript["audit_status"] = audit["status"]
    return {
        "manuscript": manuscript,
        "audit": audit,
        "claim_registry": registry,
        "argument_ledger": {
            "schema_version": "argument-ledger-0.1",
            "entries": ledger,
            "summary": {
                "entries": len(ledger),
                "supported": sum(1 for item in ledger if item["status"] == "supported"),
                "needs_evidence": sum(1 for item in ledger if item["status"] == "needs_evidence"),
            },
            "boundary": "ledger is an audit view, not a claim or a gate",
        },
    }


def render_manuscript_markdown(manuscript: Dict[str, Any]) -> str:
    language = str(manuscript.get("language") or "zh")
    title = str(manuscript.get("title") or "")
    abstract = str(manuscript.get("abstract") or "")
    keywords = manuscript.get("keywords") or []
    lines = ["# %s" % title, ""]
    if abstract:
        # A heading, not a bold paragraph: the strict writing audit locates the abstract by
        # section heading, and a bold prefix made every generated draft fail structure.abstract.
        lines += ["## %s" % ("摘要" if language == "zh" else "Abstract"), "", abstract, ""]
    if keywords:
        lines += [
            "**%s%s** %s" % (
                "关键词" if language == "zh" else "Keywords",
                "：" if language == "zh" else ":",
                "；".join(keywords) if language == "zh" else ", ".join(keywords),
            ),
            "",
        ]
    for section in manuscript.get("sections") or []:
        kind = _section_kind(str(section.get("label", "")))
        if kind in ("abstract", "references"):
            continue
        lines += ["## %s" % section.get("label", ""), "", str(section.get("text") or ""), ""]
    references = manuscript.get("references") or []
    if references:
        lines += ["## %s" % ("参考文献" if language == "zh" else "References"), ""]
        for item in references:
            lines.append(str(item.get("text") or ""))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"

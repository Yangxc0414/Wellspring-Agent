"""Audit a Qoder-authored Chinese manuscript against a writing pack.

This is a pre-submission audit, not peer review. It checks citation keys,
result-number policy, claim status, structure and placeholders. It never signs
a claim or reports the draft as submission-ready.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .journal_skill_audit import audit_journal_style
from .revision_io import read_draft, sha256_file
from .storage import write_json_atomic
from .writing_pack import PACK_MARKER_RE, build_writing_pack, load_writing_pack

AUDIT_SCHEMA = "writing-audit-0.1"
CITATION_RE = re.compile(r"\[(REF-[0-9]{2,}|[0-9]{1,3})\]")
BARE_REF_RE = re.compile(r"(?<!\[)REF-[0-9]{2,}(?!\])")
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9])[-+]?[0-9]+(?:\.[0-9]+)?%?(?![A-Za-z0-9])")
_FACTUAL_CUES = (
    "研究表明", "已有研究", "文献表明", "文献报告", "研究显示",
    "研究发现", "学者们", "研究证实",
    "prior work", "studies show", "research shows",
)
_SELF_MARKERS = ("本文", "我们", "本研究", "本实验", "our study", "we ")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？])|(?<=[.!?])\s+")
URL_RE = re.compile(r"https?://\S+")
SECTION_HEADING_RE = re.compile(r"(?m)^\s*#{1,6}\s*[0-9]+(?:\.[0-9]+)*")
SECTION_REF_RE = re.compile(
    # Two structural forms, and nothing more:
    #   1. prefix + dotted number ("如 4.3 所示") — the original rule;
    #   2. prefix + integer + section noun ("第 3 节") — an integer cross-reference is not a
    #      metric, while a bare "见 15 例" still counts as a number.
    r"(?:第|按|见|与|如|section|§)\s*[0-9]{1,2}(?:\.[0-9]{1,2})+"
    r"|(?:第|见|如|按)\s*[0-9]{1,2}\s*(?:节|章|条|款|段|部分|小节|附录|图|表)"
    r"|§\s*[0-9]{1,2}(?:\.[0-9]{1,2})*"
    r"|(?:section\s*)[0-9]{1,2}(?:\.[0-9]{1,2})*",
    re.I,
)
IDENTIFIER_RE = re.compile(
    r"\b(?:GAP|IDEA|REF|RUN|EA|TH|CP|SUP|CLM|EXP|PROT|BIB|SPAN)-[0-9A-Za-z-]+\b"
)
REQUIRED_SECTIONS = (
    ("abstract", ("摘要", "abstract")),
    ("introduction", ("引言", "introduction")),
    ("related_work", ("相关工作", "related work")),
    ("method", ("方法", "method")),
    ("experiment", ("实验", "experiment")),
    ("result", ("结果", "result")),
    ("discussion", ("讨论", "discussion")),
    ("conclusion", ("结论", "conclusion")),
    ("references", ("参考文献", "references")),
)
PLACEHOLDERS = ("TODO", "TBD", "DATA_NEEDED", "待补", "待填")
MIN_DIVERSITY_REFS = 5
MAX_SINGLE_SOURCE_SHARE = 0.6


class WritingAuditError(ValueError):
    pass


def _section_text(document: Any, aliases: Sequence[str]) -> str:
    chunks = []
    for section in document.sections:
        heading = str(section.heading or "").lower()
        if any(alias.lower() in heading for alias in aliases):
            chunks.extend(block.text for block in section.blocks if block.text)
    return "\n".join(chunks)


def _body_text(document: Any) -> str:
    chunks = []
    for section in document.sections:
        heading = str(section.heading or "").lower()
        if "参考文献" in heading or "reference" in heading:
            continue
        chunks.extend(block.text for block in section.blocks if block.text)
    return "\n".join(chunks)


def _all_text(document: Any) -> str:
    return "\n".join(
        block.text
        for section in document.sections
        for block in section.blocks
        if block.text
    )


def _multi_ref_sentences(document: Any) -> List[str]:
    found: List[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(_body_text(document)):
        text = sentence.strip()
        if len(text) < 12:
            continue
        refs = set(CITATION_RE.findall(text))
        if len(refs) > 1:
            found.append(text[:300])
    return found


def _uncited_factual_sentences(document: Any) -> List[str]:
    found: List[str] = []
    for sentence in _SENTENCE_SPLIT_RE.split(_body_text(document)):
        text = sentence.strip()
        if len(text) < 12 or CITATION_RE.search(text):
            continue
        lowered = text.lower()
        if any(marker in lowered for marker in _SELF_MARKERS):
            continue
        if any(cue in lowered for cue in _FACTUAL_CUES):
            found.append(text[:300])
    return found


def _citation_tokens(text: str) -> List[str]:
    return CITATION_RE.findall(text or "") + BARE_REF_RE.findall(text or "")


def _clean_numbers(text: str) -> List[str]:
    value = CITATION_RE.sub(" ", text or "")
    value = BARE_REF_RE.sub(" ", value)
    value = IDENTIFIER_RE.sub(" ", value)
    value = URL_RE.sub(" ", value)
    value = SECTION_HEADING_RE.sub(" ", value)
    value = SECTION_REF_RE.sub(" ", value)
    return [match.group(0) for match in NUMBER_RE.finditer(value)]


def _number_matches(value: str, allowed: Sequence[float], tolerance: float = 0.01) -> bool:
    try:
        number = float(value.replace("%", ""))
    except ValueError:
        return False
    return any(abs(number - target) <= tolerance for target in allowed)


def _parse_numbers(values: Any) -> List[float]:
    parsed = []
    for value in values or []:
        try:
            parsed.append(float(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _allowed_numbers(pack: Dict[str, Any]) -> List[float]:
    return _parse_numbers((pack.get("writing_contract") or {}).get("allowed_result_numbers"))


def _allowed_design_numbers(pack: Dict[str, Any]) -> List[float]:
    return _parse_numbers((pack.get("writing_contract") or {}).get("allowed_design_numbers"))


def _citation_key(token: str, references: Sequence[Dict[str, Any]]) -> str:
    if token.startswith("REF-"):
        return token
    try:
        index = int(token) - 1
    except ValueError:
        return ""
    if 0 <= index < len(references):
        return str(references[index].get("ref_id") or "")
    return ""


def audit_manuscript(
    draft_path: Path,
    pack: Optional[Dict[str, Any]] = None,
    project: Optional[Path] = None,
    run_id: str = "",
    language: str = "zh",
    venue: str = "zh_core_journal",
    experiment_id: str = "",
    support_judge: Any = None,
    strict_support: bool = False,
    judge_model_id: str = "",
    strict_pack_binding: bool = False,
    support_votes: int = 1,
    support_max_items: int = 80,
    support_cache_path: Optional[Path] = None,
    refresh_support: bool = False,
) -> Dict[str, Any]:
    if pack is None:
        if project is None or not run_id:
            raise WritingAuditError("either pack or project+run_id is required")
        pack = load_writing_pack(project, run_id) or build_writing_pack(
            project, run_id, language=language, venue=venue, experiment_id=experiment_id
        )
    document = read_draft(Path(draft_path))
    references = list((pack.get("literature") or {}).get("references") or [])
    reference_ids = {str(ref.get("ref_id")) for ref in references}
    full_text = _all_text(document)
    body_text = _body_text(document)
    citations = _citation_tokens(full_text)
    body_citations = _citation_tokens(body_text)
    mapped = [_citation_key(token, references) for token in citations]
    blockers: List[str] = []
    warnings: List[str] = []
    checks: List[Dict[str, str]] = []

    def add(item_id: str, ok: bool, detail: str, severity: str = "blocker") -> None:
        checks.append(
            {
                "id": item_id,
                "status": "pass" if ok else "fail",
                "detail": detail,
                "severity": severity,
            }
        )
        if not ok:
            (blockers if severity == "blocker" else warnings).append("%s: %s" % (item_id, detail))

    if not citations:
        add("citations.present", False, "no [REF-01]/[1] citation markers")
    else:
        unknown = sorted({token for token, key in zip(citations, mapped) if not key or key not in reference_ids})
        add("citations.present", True, "%d citations" % len(citations))
        add("citations.known", not unknown, "unknown citations: " + ", ".join(unknown[:10]))
    multi_ref = _multi_ref_sentences(document)
    add(
        "citations.multi_ref",
        not multi_ref,
        "multi-REF sentences: %d; split synthesis into single-REF sentences when possible"
        % len(multi_ref),
        severity="warning",
    )
    uncited_factual = _uncited_factual_sentences(document)
    add(
        "citations.uncited_factual",
        not uncited_factual,
        "uncited factual sentences: %d" % len(uncited_factual),
        severity="blocker" if strict_support else "warning",
    )

    known_refs = [key for key in mapped if key in reference_ids]
    distinct_refs = sorted(set(known_refs))
    body_mapped = [_citation_key(token, references) for token in body_citations]
    body_known = [key for key in body_mapped if key in reference_ids]
    body_distinct = sorted(set(body_known))
    if len(references) >= MIN_DIVERSITY_REFS:
        required = min(MIN_DIVERSITY_REFS, len(references))
        add(
            "sources.diversity",
            len(body_distinct) >= required,
            "distinct refs in body: %d; required: %d" % (len(body_distinct), required),
        )
        if body_known:
            from collections import Counter
            top_share = max(Counter(body_known).values()) / len(body_known)
            add(
                "sources.balance",
                top_share <= MAX_SINGLE_SOURCE_SHARE,
                "top source share: %.2f (max %.2f)" % (top_share, MAX_SINGLE_SOURCE_SHARE),
            )
    else:
        # Not silently skipped: the check is recorded as unassessable so a reviewer can see
        # that the diversity guarantee did not apply to this draft.
        add(
            "sources.diversity",
            True,
            "not_assessable: only %d references available, fewer than %d required"
            % (len(references), MIN_DIVERSITY_REFS),
        )
        warnings.append(
            "sources.diversity not_assessable: %d references < %d; the multi-source "
            "guarantee did not apply to this draft"
            % (len(references), MIN_DIVERSITY_REFS)
        )

    han_count = len(re.findall(r"[一-鿿]", body_text or ""))
    target = (pack or {}).get("writing_contract", {}).get("length_target") or {}
    low = int(target.get("min") or 0)
    if low:
        within_range = low <= han_count <= int(target.get("max") or low)
        # Length is a venue convention, not an evidence-integrity rule: it is always
        # reported, and it only blocks when the contract explicitly asks for strict length.
        severity = "blocker" if target.get("strict") else "warning"
        add(
            "length.chinese_characters",
            within_range,
            "han characters: %d; contract target: %s-%s (strict=%s)"
            % (han_count, low, target.get("max"), bool(target.get("strict"))),
            severity=severity,
        )
    else:
        add("length.chinese_characters", True, "no target declared; count only: %d" % han_count)

    # Script leakage is a presentation defect, not an evidence-integrity one, so it warns.
    # The two directions are deliberately asymmetric: Latin punctuation is legal inside
    # Chinese prose (numbers, URLs, untranslated terms), so the only defensible zh signal is
    # a half-width mark sandwiched between two Han characters, while an en draft must carry no
    # CJK mark at all. Both sides report their denominator so a clean line is never confused
    # with an unmeasured one.
    script = str((pack or {}).get("language") or "").strip().lower()
    cjk_marks = re.findall(r"[，。；：？！（）【】《》、“”‘’…—～　]", body_text or "")
    if script == "zh":
        between_han = re.findall(r"(?<=[一-鿿])[,.;:?!](?=[一-鿿])", body_text or "")
        add(
            "script.punctuation",
            not between_han,
            "half-width marks between Han characters: %d; CJK marks: %d; han characters: %d"
            % (len(between_han), len(cjk_marks), han_count),
            severity="warning",
        )
    elif script == "en":
        add(
            "script.punctuation",
            not cjk_marks and not han_count,
            "CJK punctuation: %d; han characters: %d in a draft whose contract language is en"
            % (len(cjk_marks), han_count),
            severity="warning",
        )
    else:
        add(
            "script.punctuation",
            True,
            "not_assessable: the pack declares no language; CJK marks: %d, han characters: %d"
            % (len(cjk_marks), han_count),
        )
        warnings.append(
            "script.punctuation not_assessable: contract language missing, so no script was "
            "expected and leakage could not be judged"
        )

    satisfied_by: Dict[str, List[str]] = {}
    for section_id, aliases in REQUIRED_SECTIONS:
        matched = [
            str(section.heading or "").strip()
            for section in document.sections
            if any(alias.lower() in str(section.heading or "").lower() for alias in aliases)
        ]
        add("structure." + section_id, bool(matched), "section " + "/".join(aliases))
        for heading in matched:
            satisfied_by.setdefault(heading, []).append(section_id)
    # One heading can satisfy several required sections ("实验与结果"). Merging is normal
    # publishing practice, so it never blocks — but nine green structure checks must not read as
    # "nine distinct sections exist", so the merge is named in the panel.
    merged = {heading: ids for heading, ids in satisfied_by.items() if len(ids) > 1}
    add(
        "structure.merged_headings",
        not merged,
        "%d required sections satisfied by %d shared heading(s): %s"
        % (
            sum(len(ids) for ids in merged.values()),
            len(merged),
            "; ".join(
                '"%s" -> %s' % (heading, "+".join(ids))
                for heading, ids in sorted(merged.items())
            )
            or "each required section has its own heading",
        ),
        severity="warning",
    )

    claim = pack.get("claim") or {}
    article_type = (pack.get("writing_contract") or {}).get("article_type")
    claim_status = str(claim.get("status") or "missing")
    signed = claim_status == "signed"
    if article_type == "reproduction":
        package = pack.get("experiment_package") or {}
        figure = package.get("figure") or {}
        method_figure = package.get("method_figure") or {}
        own_text = "\n".join(
            _section_text(document, aliases)
            for aliases in (("摘要", "abstract"), ("结果", "result"), ("讨论", "discussion"), ("结论", "conclusion"))
        )
        result_section = _section_text(document, ("结果", "result"))
        method_section = _section_text(document, ("方法", "method"))
        figure_refs = sorted(
            {
                int(value)
                for value in re.findall(r"(?:图|Figure|Fig\.?)\s*([0-9]+)", own_text, re.I)
            }
        )
        result_figure_refs = {
            int(value)
            for value in re.findall(r"(?:图|Figure|Fig\.?)\s*([0-9]+)", result_section, re.I)
        }
        allowed_figures = set()
        if figure:
            allowed_figures.add(int(figure.get("figure_number") or 1))
        if method_figure:
            allowed_figures.add(int(method_figure.get("figure_number") or 2))
        unbound = [value for value in figure_refs if value not in allowed_figures]
        add(
            "figure.bound",
            not unbound,
            "figure references without a verified manifest: "
            + ", ".join(str(value) for value in unbound),
        )
        if figure:
            result_number = int(figure.get("figure_number") or 1)
            if result_number not in figure_refs:
                add(
                    "figure.referenced",
                    False,
                    "verified result figure exists but the manuscript does not reference it",
                )
        if method_figure:
            method_number = int(method_figure.get("figure_number") or 2)
            add(
                "method_figure.schematic",
                method_figure.get("schematic") is True
                and method_figure.get("kind") == "astradraw_scene",
                "method figure must be an AstraDraw schematic",
            )
            if method_number in result_figure_refs:
                add(
                    "method_figure.not_result",
                    False,
                    "AstraDraw method schematic is referenced as a result",
                )
            method_refs = {
                int(value)
                for value in re.findall(r"(?:图|Figure|Fig\.?)\s*([0-9]+)", method_section, re.I)
            }
            if method_number not in method_refs and method_number not in figure_refs:
                add(
                    "method_figure.referenced",
                    False,
                    "method schematic exists but the manuscript does not reference it",
                    severity="warning",
                )
        if package.get("method_figure_error"):
            add(
                "method_figure.available",
                False,
                str(package.get("method_figure_error")),
                severity="warning",
            )
        results_table = package.get("results_table") or ""
        table_refs = bool(re.search(r"表\s*1|Table\s*1", result_section, re.I))
        if results_table and not table_refs:
            add(
                "table.referenced",
                False,
                "verified results table exists but the Results section does not reference 表 1",
                severity="warning",
            )
        if table_refs and not results_table:
            add(
                "table.bound",
                False,
                "manuscript references 表 1 but the pack has no verified results table",
                severity="warning",
            )
        add("claim.signed", signed, "claim status=" + claim_status)
    else:
        warnings.append("review manuscript: no result claim is required, but claims still need human review")
        checks.append(
            {
                "id": "claim.signed",
                "status": "warn",
                "detail": "review manuscript; claim status=" + claim_status,
                "severity": "warning",
            }
        )

    result_text = _section_text(document, ("结果", "result"))
    result_numbers = _clean_numbers(result_text)
    if result_numbers and not signed:
        add(
            "results.numbers_without_claim",
            False,
            "result numbers are not allowed before a signed claim: " + ", ".join(result_numbers[:10]),
        )
    else:
        add("results.numbers_without_claim", True, "signed claim or no result numbers")
    if signed and result_numbers:
        allowed = _allowed_numbers(pack)
        design_allowed = _allowed_design_numbers(pack)
        bad = [
            value for value in result_numbers
            if not (
                _number_matches(value, allowed)
                or _number_matches(value, design_allowed, tolerance=1e-9)
            )
        ]
        add("results.numbers_traceable", not bad, "untraceable result numbers: " + ", ".join(bad[:10]))
        add("results.numbers_present", True, "%d numeric tokens" % len(result_numbers))
    elif article_type == "reproduction" and signed:
        add(
            "results.numbers_present",
            False,
            "signed reproduction has no result numbers in the Results section",
            severity="warning",
        )

    if article_type == "reproduction":
        narrative_text = "\n".join(
            _section_text(document, aliases)
            for aliases in (("摘要", "abstract"), ("讨论", "discussion"), ("结论", "conclusion"))
        )
        narrative_numbers = [
            value for value in _clean_numbers(narrative_text)
            if "." in value or "%" in value
        ]
        if narrative_numbers:
            allowed = _allowed_numbers(pack)
            design_allowed = _allowed_design_numbers(pack)
            bad = [
                value for value in narrative_numbers
                if not (
                    _number_matches(value, allowed)
                    or _number_matches(value, design_allowed, tolerance=1e-9)
                )
            ]
            add(
                "results.narrative_numbers_traceable",
                signed and not bad,
                "untraceable numbers in abstract/discussion: " + ", ".join(bad[:10]),
            )

    for marker in PLACEHOLDERS:
        if marker in full_text:
            add("placeholders", False, "contains " + marker)
    if not any(marker in full_text for marker in PLACEHOLDERS):
        add("placeholders", True, "no TODO/待补 markers")

    if any(bool(ref.get("fixture")) for ref in references):
        add("fixture", False, "fixture sources cannot be submitted")
    elif "fixture" in full_text.lower():
        warnings.append("draft mentions fixture; verify it is not used as evidence")

    missing_urls = [ref.get("ref_id") for ref in references if not ref.get("url")]
    if missing_urls:
        warnings.append("references without public URL: " + ", ".join(map(str, missing_urls[:10])))
    if any(str(ref.get("peer_reviewed")) == "unknown" for ref in references):
        warnings.append("some references are preprints with peer_reviewed=unknown")

    pack_id = str(pack.get("pack_id") or "")
    pack_sha256 = str(pack.get("pack_sha256") or "")
    marker = PACK_MARKER_RE.search(full_text)
    draft_pack_id = marker.group(1) if marker else ""
    draft_pack_sha256 = marker.group(2) if marker else ""
    if pack_id and marker:
        bound = draft_pack_id == pack_id and draft_pack_sha256 == pack_sha256
        pack_binding = "bound" if bound else "mismatch"
        add(
            "draft.pack_binding",
            bound,
            "draft pack %s != current pack %s" % (draft_pack_id, pack_id),
        )
    elif pack_id:
        pack_binding = "unbound"
        if strict_pack_binding:
            add(
                "draft.pack_binding",
                False,
                "draft has no writing-pack marker; rebuild it from this pack",
            )
        else:
            warnings.append(
                "draft has no writing-pack marker; it cannot be proven to use the current pack"
            )
    else:
        pack_binding = "pack_unversioned"
        warnings.append("writing pack has no pack_id; rebuild it before a bound audit")
    status = "blocked" if blockers else "ready_for_human_review"
    result = {
        "schema_version": AUDIT_SCHEMA,
        "status": status,
        "submission_ready": False,
        "article_type": article_type,
        "claim_status": claim_status,
        "draft": str(Path(draft_path)),
        "draft_sha256": sha256_file(Path(draft_path)),
        "run_id": pack.get("run_id") or run_id,
        "citation_count": len(citations),
        "han_character_count": han_count,
        "body_citation_count": len(body_citations),
        "distinct_reference_count": len(distinct_refs),
        "reference_count": len(references),
        "result_number_count": len(result_numbers),
        "result_numbers": result_numbers,
        "uncited_factual_count": len(uncited_factual),
        "uncited_factual_samples": uncited_factual[:5],
        "multi_ref_sentence_count": len(multi_ref),
        "multi_ref_sentence_samples": multi_ref[:5],
        "pack_id": pack_id,
        "pack_sha256": pack_sha256,
        "draft_pack_id": draft_pack_id,
        "draft_pack_sha256": draft_pack_sha256,
        "pack_binding": pack_binding,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "boundary": (
            "pre-submission audit only; it checks citation keys, result-number policy, "
            "claim status, structure and placeholders; optional support ledger is "
            "model-assisted and neither is peer review or a submission approval"
        ),
    }
    # A Qoder verdict ledger is a support review already: strict mode must consume it instead
    # of demanding an external judge profile and failing with "support judge call failed".
    ledger_candidate = (
        Path(project) / "runs" / run_id / "support-ledger.json"
        if project is not None and run_id
        else None
    )
    has_support_ledger = bool(ledger_candidate and ledger_candidate.is_file())
    if support_judge is not None or (strict_support and not has_support_ledger):
        from .support_audit import audit_pack_support

        support = audit_pack_support(
            draft_path,
            pack,
            judge=support_judge,
            strict=strict_support,
            judge_model_id=judge_model_id,
            judge_votes=support_votes,
            max_items=support_max_items,
            cache_path=support_cache_path,
            refresh=refresh_support,
        )
        result["support"] = support
        support_counts = support.get("counts") or {}
        if strict_support and (
            support.get("status") == "blocked"
            or int(support_counts.get("insufficient") or 0) > 0
            or int(support.get("unresolved_refs") or 0) > 0
        ):
            result["status"] = "blocked"
            result["blockers"].append(
                "semantic_support: status=%s; contradicted/unresolved/insufficient citations must be fixed"
                % support.get("status")
            )
        elif support.get("status") == "blocked":
            result["warnings"].append(
                "semantic_support: contradicted or unresolved citations found"
            )
    journal_style = audit_journal_style(document, venue)
    if journal_style:
        result["journal_style"] = journal_style
        for check in journal_style.get("checks") or []:
            if check.get("status") in ("fail", "warn"):
                result["warnings"].append(
                    "journal_style.%s: %s" % (check.get("id"), check.get("detail"))
                )
    if str(venue) in ("zh_core_journal", "software_journal", "computer_journal"):
        from .venue_audit import audit_chinese_journal, manuscript_from_draft

        venue_view = manuscript_from_draft(document, references, language=language)
        venue_report = audit_chinese_journal(venue_view, profile_name=str(venue))
        result["venue_audit"] = venue_report
        for item in list(venue_report.get("blockers") or []) + list(
            venue_report.get("warnings") or []
        ):
            result["warnings"].append("venue_audit." + item)
    return result


def write_audit(
    draft_path: Path,
    output_dir: Path,
    pack: Optional[Dict[str, Any]] = None,
    project: Optional[Path] = None,
    run_id: str = "",
    language: str = "zh",
    venue: str = "zh_core_journal",
    experiment_id: str = "",
    support_judge: Any = None,
    strict_support: bool = False,
    judge_model_id: str = "",
    strict_pack_binding: bool = False,
    support_votes: int = 1,
    support_max_items: int = 80,
    support_cache_path: Optional[Path] = None,
    refresh_support: bool = False,
) -> Dict[str, Any]:
    audit = audit_manuscript(
        draft_path=draft_path,
        pack=pack,
        project=project,
        run_id=run_id,
        language=language,
        venue=venue,
        experiment_id=experiment_id,
        support_judge=support_judge,
        strict_support=strict_support,
        judge_model_id=judge_model_id,
        strict_pack_binding=strict_pack_binding,
        support_votes=support_votes,
        support_max_items=support_max_items,
        support_cache_path=(
            support_cache_path
            if support_cache_path is not None
            else (Path(output_dir) / "support-ledger.json")
        ),
        refresh_support=refresh_support,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ledger_path = output / "support-ledger.json"
    if not audit.get("support") and ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
            if not isinstance(ledger, dict):
                raise ValueError("support-ledger.json is not an object")
            if str(ledger.get("draft_sha256") or "") == str(
                audit.get("draft_sha256") or ""
            ):
                from .support_audit import summarize_support

                ledger.setdefault("section_summary", summarize_support(ledger))
                audit["support"] = ledger
                counts = ledger.get("counts") or {}
                if strict_support and (
                    ledger.get("status") == "blocked"
                    or int(counts.get("insufficient") or 0) > 0
                    or int(ledger.get("unresolved_refs") or 0) > 0
                ):
                    audit["status"] = "blocked"
                    audit["blockers"].append(
                        "support_ledger: status=%s; contradicted/unresolved/insufficient "
                        "citations must be fixed" % ledger.get("status")
                    )
                elif ledger.get("status") in ("blocked", "partial"):
                    audit["warnings"].append(
                        "support_ledger: status=%s" % ledger.get("status")
                    )
            else:
                audit["warnings"].append(
                    "support_ledger: draft hash differs; rerun support review"
                )
        except (OSError, ValueError) as exc:
            audit["warnings"].append("support_ledger: unreadable (%s)" % exc)
    panel_path = output / "support-panel.json"
    if panel_path.is_file():
        try:
            panel = json.loads(panel_path.read_text(encoding="utf-8"))
            if not isinstance(panel, dict):
                raise ValueError("support-panel.json is not an object")
            panel_status = str(panel.get("status") or "missing")
            draft_matches = str(panel.get("draft_sha256") or "") == str(
                audit.get("draft_sha256") or ""
            )
            audit["support_panel"] = {
                "path": str(panel_path),
                "status": panel_status,
                "pending_human": len(panel.get("pending_human") or []),
                "panel_fingerprint": str(panel.get("panel_fingerprint") or ""),
                "draft_matches": draft_matches,
            }
            if not draft_matches:
                message = (
                    "support_panel: panel draft hash differs from the audited draft; rerun the panel"
                )
                audit["status"] = "blocked"
                audit["blockers"].append(message)
                audit["checks"].append(
                    {
                        "id": "support_panel.draft",
                        "status": "fail",
                        "detail": message,
                        "severity": "blocker",
                    }
                )
            elif panel_status not in ("ready", "not_applicable"):
                message = "support_panel: status=%s pending_human=%d" % (
                    panel_status,
                    len(panel.get("pending_human") or []),
                )
                audit["status"] = "blocked"
                audit["blockers"].append(message)
                audit["checks"].append(
                    {
                        "id": "support_panel.ready",
                        "status": "fail",
                        "detail": message,
                        "severity": "blocker",
                    }
                )
            else:
                audit["checks"].append(
                    {
                        "id": "support_panel.ready",
                        "status": "pass",
                        "detail": "status=%s" % panel_status,
                        "severity": "blocker",
                    }
                )
        except (OSError, ValueError) as exc:
            message = "support_panel: unreadable (%s)" % exc
            audit["status"] = "blocked"
            audit["blockers"].append(message)
    gold_path = output / "support-gold.json"
    if gold_path.is_file():
        try:
            gold = json.loads(gold_path.read_text(encoding="utf-8"))
            if not isinstance(gold, dict):
                raise ValueError("support-gold.json is not an object")
            if str(gold.get("draft_sha256") or "") != str(
                audit.get("draft_sha256") or ""
            ):
                audit["warnings"].append(
                    "support_gold: draft hash differs from the audited draft; rerun human gold"
                )
            else:
                audit["support_gold"] = {
                    "path": str(gold_path),
                    "status": str(gold.get("status") or "missing"),
                    "annotators": len(gold.get("annotators") or []),
                    "mean_kappa": (gold.get("agreement") or {}).get("mean_kappa"),
                    "panel_accuracy": (gold.get("panel") or {}).get("accuracy"),
                }
        except (OSError, ValueError) as exc:
            audit["warnings"].append("support_gold: unreadable (%s)" % exc)
    write_json_atomic(output / "writing-audit.json", audit)
    if audit.get("support"):
        write_json_atomic(output / "support-ledger.json", audit["support"])
    return audit

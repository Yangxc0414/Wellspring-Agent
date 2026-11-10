"""Deterministic submission audits for Chinese journals and grant applications.

CCF-A design disclosure lives in ``ccfa_audit.py``. This module covers the other two
submission tracks with structural checks only: it never invents policy, never writes text,
never signs and never submits. Official templates and current calls always win.
"""

import re
from typing import Any, Dict, List, Optional

from .modules.grant import SCHEMES
from .revision_templates import get_venue_profile

CJK = re.compile(r"[\u4e00-\u9fff]")


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _length(text: str) -> int:
    return len(CJK.findall(text)) or len(text.strip())


def _sections_text(manuscript: Dict[str, Any]) -> str:
    parts = [_text(manuscript.get("abstract"))]
    for section in manuscript.get("sections") or []:
        if isinstance(section, dict):
            parts.append(_text(section.get("text")))
    return "\n".join(parts)


def _add(checks: List[Dict[str, str]], blockers: List[str], warnings: List[str],
         check_id: str, ok: bool, detail: str, severity: str = "blocker") -> None:
    checks.append({"id": check_id, "status": "pass" if ok else "fail",
                   "detail": detail, "severity": severity})
    if ok:
        return
    (blockers if severity == "blocker" else warnings).append("%s: %s" % (check_id, detail))


def _result(track: str, checks: List[Dict[str, str]], blockers: List[str],
            warnings: List[str], boundary: str) -> Dict[str, Any]:
    return {
        "schema_version": "venue-audit-0.1",
        "track": track,
        "status": "blocked" if blockers else ("needs_revision" if warnings else "ready_for_human"),
        "submission_ready": False,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "boundary": boundary,
    }


def manuscript_from_draft(document, references, language: str = "zh") -> Dict[str, Any]:
    """Adapt a parsed DraftDocument + pack references to the manuscript audit view."""
    sections: List[Dict[str, str]] = []
    abstract = ""
    keywords: List[str] = []
    for section in getattr(document, "sections", []) or []:
        heading = str(getattr(section, "heading", "") or "")
        text = "\n".join(
            str(getattr(block, "text", "") or "")
            for block in getattr(section, "blocks", []) or []
            if getattr(block, "text", "")
        )
        if not text.strip():
            continue
        sections.append({"label": heading, "text": text})
        low = heading.lower()
        if not abstract and ("摘要" in heading or "abstract" in low):
            abstract = text
        if not keywords:
            match = re.search(r"关键词\s*[:：]\s*(.+)", text)
            if match:
                keywords = [
                    item.strip()
                    for item in re.split(r"[，,；;、\s]+", match.group(1))
                    if item.strip()
                ]
    if not abstract and sections:
        abstract = sections[0]["text"]
    adapted = []
    for reference in references or []:
        if isinstance(reference, dict):
            adapted.append({
                "title": str(reference.get("title") or ""),
                "text": str(reference.get("text") or ""),
                "verified": bool(reference.get("verified")),
            })
    return {
        "abstract": abstract,
        "keywords": keywords,
        "sections": sections,
        "references": adapted,
        "language": language,
    }


def audit_chinese_journal(manuscript: Dict[str, Any], profile_name: str = "zh_core_journal") -> Dict[str, Any]:
    """Check a manuscript JSON against a Chinese-journal working profile."""
    profile = get_venue_profile(profile_name)
    if str(profile.get("language") or "") != "zh":
        raise ValueError("profile %s is not a Chinese-language journal profile" % profile_name)
    checks: List[Dict[str, str]] = []
    blockers: List[str] = []
    warnings: List[str] = []
    sections = [item for item in manuscript.get("sections") or [] if isinstance(item, dict)]
    labels = [_text(item.get("label")) for item in sections]
    body = _sections_text(manuscript)

    abstract = _text(manuscript.get("abstract"))
    abstract_len = _length(abstract)
    _add(checks, blockers, warnings, "abstract.chinese",
         bool(CJK.search(abstract)) and abstract_len >= 50,
         "Chinese abstract is missing or shorter than 50 characters")
    if abstract_len < 150:
        _add(checks, blockers, warnings, "abstract.length", False,
             "Chinese abstract is %d characters (working target >= 150)" % abstract_len,
             severity="warning")

    keywords = [str(item) for item in manuscript.get("keywords") or [] if str(item).strip()]
    _add(checks, blockers, warnings, "keywords.count", 3 <= len(keywords) <= 8,
         "%d Chinese keywords (working range 3-8)" % len(keywords))

    for group in profile.get("required_sections") or []:
        tokens = [str(item).lower() for item in group]
        if any(token in ("摘要", "abstract") for token in tokens) and abstract:
            continue
        present = any(token in label.lower() for token in tokens for label in labels)
        _add(checks, blockers, warnings, "section.%s" % tokens[0], present,
             "required section missing: %s (accepted labels: %s)" % (tokens[0], ", ".join(tokens)))

    references = [item for item in manuscript.get("references") or [] if isinstance(item, dict)]
    _add(checks, blockers, warnings, "references.minimum", len(references) >= 8,
         "only %d references (working target >= 8)" % len(references),
         severity="blocker" if len(references) < 5 else "warning")
    chinese_refs = sum(1 for item in references if CJK.search(_text(item.get("title")) + _text(item.get("text"))))
    if references and chinese_refs == 0:
        _add(checks, blockers, warnings, "references.chinese", False,
             "no Chinese-language reference found; domestic positioning may be thin",
             severity="warning")
    unverified = sum(1 for item in references if not item.get("verified"))
    if unverified:
        _add(checks, blockers, warnings, "references.verified", False,
             "%d references lack verified metadata (DOI/arXiv snapshot)" % unverified,
             severity="warning")

    if not re.search(r"基金|资助|项目", body):
        _add(checks, blockers, warnings, "funding.declared", False,
             "no funding/acknowledgement text found; add it if the target journal requires it",
             severity="warning")
    if not re.search(r"创新|贡献", body):
        _add(checks, blockers, warnings, "contribution.stated", False,
             "no explicit innovation/contribution statement found",
             severity="warning")
    if not re.search(r"数据可用|数据获取|代码|复现|开源", body):
        _add(checks, blockers, warnings, "data.availability", False,
             "no data/code availability statement found",
             severity="warning")

    boundary = (
        "structural Chinese-journal checklist against a working profile, not an official "
        "template, not peer review, not a submission; verify the target journal's current "
        "requirements and page limits by hand"
    )
    return _result("zh_journal:%s" % profile.get("id"), checks, blockers, warnings, boundary)


def audit_grant(sections: Dict[str, str], scheme: str = "nsfc",
                evidence_refs: Optional[List[str]] = None,
                anonymous: bool = False, identity_removed: bool = False,
                ai_statement: bool = False) -> Dict[str, Any]:
    """Check a grant draft's section skeleton against NSFC/NSSFC/generic schemes."""
    config = SCHEMES.get(scheme)
    if config is None:
        raise ValueError("unknown grant scheme: %s (choose %s)" % (scheme, ", ".join(sorted(SCHEMES))))
    if not isinstance(sections, dict):
        raise ValueError("sections must be a mapping of module name to text")
    checks: List[Dict[str, str]] = []
    blockers: List[str] = []
    warnings: List[str] = []
    normalized = {str(key).strip(): _text(value) for key, value in sections.items()}

    def find(module: str) -> str:
        for key, value in normalized.items():
            if module in key or key in module:
                return value
        return ""

    for module in config["modules"]:
        text = find(module)
        _add(checks, blockers, warnings, "module.%s" % module, bool(text.strip()),
             "required module is missing or empty: %s" % module)
        if text.strip() and _length(text) < 80:
            _add(checks, blockers, warnings, "module.%s.length" % module, False,
                 "module %s has %d characters (working target >= 80)" % (module, _length(text)),
                 severity="warning")

    innovation = find("创新") or find("创新点") or find("创新之处")
    _add(checks, blockers, warnings, "innovation.stated", bool(innovation.strip()),
         "innovation section is missing; the applicant must state it, the tool cannot")
    if not evidence_refs:
        _add(checks, blockers, warnings, "evidence.present", False,
             "no evidence_refs supplied; map claims to prior work or preliminary results",
             severity="warning")
    if scheme == "nssfc" and not (anonymous and identity_removed):
        _add(checks, blockers, warnings, "anonymity.confirmed", False,
             "NSSFC anonymous review requires anonymous=true and identity_removed=true")
    if not ai_statement:
        _add(checks, blockers, warnings, "ai.statement", False,
             "AI-assistance declaration not confirmed; check the current call",
             severity="warning")

    boundary = (
        "structure/compliance checklist only: no scientific ideas, no budget numbers, no "
        "official template policy, no submission; current call and official template win"
    )
    return _result("grant:%s" % scheme, checks, blockers, warnings, boundary)

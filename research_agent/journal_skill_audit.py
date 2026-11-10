"""Deterministic journal-style checks derived from external writing skills.

The checks below are a small, auditable projection of the public MIT-licensed
Journal-of-Software-Skills and Chinese-Journal-of-Computers-Skills Skill packs.
They are not the official journal templates and do not replace human editing.
No external file is read at runtime; source provenance is recorded per profile.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "journal-skill-audit-0.1"
PROFILES_PATH = Path(__file__).resolve().parent / "fixtures" / "journal_skill_profiles.json"
BOUNDARY = (
    "Deterministic checklist derived from public writing skills; not an official "
    "journal template, not a language proof, and not peer review."
)

def load_profiles(path: Optional[Path] = None) -> Dict[str, Any]:
    source = Path(path) if path else PROFILES_PATH
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("journal skill profiles are unreadable: " + str(source)) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), dict):
        raise ValueError("journal skill profiles need a profiles object")
    return payload


def _profile(venue: str) -> Optional[Dict[str, Any]]:
    payload = load_profiles()
    profile = payload["profiles"].get(str(venue or "").strip().lower())
    return dict(profile) if isinstance(profile, dict) else None


def verify_journal_profiles(pack_root, path: Optional[Path] = None) -> Dict[str, Any]:
    root = Path(pack_root).resolve()
    payload = load_profiles(path)
    checks: List[Dict[str, str]] = []
    for venue, profile in payload["profiles"].items():
        license_path = profile.get("license_path") or ""
        license_file = (root / str(license_path)).resolve()
        inside = str(license_file).startswith(str(root))
        ok = inside and license_file.is_file() and hashlib.sha256(license_file.read_bytes()).hexdigest() == str(profile.get("license_sha256") or "")
        checks.append({"venue": venue, "artifact": "LICENSE", "status": "fresh" if ok else "stale", "path": str(license_path)})
        for source in profile.get("sources") or []:
            source_file = (root / str(source.get("path") or "")).resolve()
            inside = str(source_file).startswith(str(root))
            ok = inside and source_file.is_file() and hashlib.sha256(source_file.read_bytes()).hexdigest() == str(source.get("sha256") or "")
            checks.append({"venue": venue, "artifact": str(source.get("skill") or "SKILL.md"), "status": "fresh" if ok else "stale", "path": str(source.get("path") or "")})
    stale = [item for item in checks if item["status"] != "fresh"]
    return {
        "schema_version": "journal-skill-profiles-verify-0.1",
        "pack_root": str(root),
        "status": "verified" if not stale else "stale",
        "checks": checks,
        "stale": stale,
        "boundary": "Verifies source/license bytes against the profile; does not approve skill behavior or journal compliance.",
    }


_ABSTRACT_PARTS = {
    "purpose": ("目的", "问题", "针对", "旨在"),
    "method": ("方法", "提出", "采用", "构建"),
    "result": ("结果", "实验", "发现", "表明", "显示"),
    "conclusion": ("结论", "意义", "启示", "说明"),
}
_REFERENCE_TYPE_RE = re.compile(r"\[(J|C|M|D|EB/OL|S|P|R)\]")
_FIGURE_CAPTION_RE = re.compile(r"(?m)^\s*(图|表)\s*[0-9]+")
_FIGURE_REF_RE = re.compile(r"(图|表)\s*[0-9]+")


def _section(document: Any, aliases: tuple) -> str:
    chunks = []
    for section in document.sections:
        heading = str(section.heading or "").lower()
        if any(alias.lower() in heading for alias in aliases):
            chunks.extend(block.text for block in section.blocks if block.text)
    return "\n".join(chunks)


def _headings(document: Any) -> List[str]:
    return [str(section.heading or "") for section in document.sections]


def _all_text(document: Any) -> str:
    return "\n".join(
        block.text
        for section in document.sections
        for block in section.blocks
        if block.text
    )


def _keyword_count(text: str) -> int:
    match = re.search(r"(?:关键词|关键字|Key\s*words?)\s*[:：]\s*(.+)", text, re.I)
    if not match:
        return 0
    parts = [item.strip() for item in re.split(r"[;；,，、]", match.group(1)) if item.strip()]
    return len(parts)


def _check(checks: List[Dict[str, str]], item_id: str, ok: bool, detail: str, severity: str = "warn") -> None:
    checks.append(
        {
            "id": item_id,
            "status": "pass" if ok else severity,
            "detail": detail,
        }
    )


def journal_style_brief(venue: str) -> str:
    profile = _profile(venue)
    return str((profile or {}).get("brief") or "")


def audit_journal_style(document: Any, venue: str) -> Optional[Dict[str, Any]]:
    profile = _profile(venue)
    if profile is None:
        return None
    text = _all_text(document)
    headings = _headings(document)
    abstract = _section(document, ("摘要", "abstract"))
    references = _section(document, ("参考文献", "references"))
    checks: List[Dict[str, str]] = []
    _check(
        checks,
        "abstract.present",
        bool(abstract.strip()),
        "abstract section found",
        severity="fail",
    )
    if abstract:
        length = len(re.sub(r"\s+", "", abstract))
        _check(
            checks,
            "abstract.length",
            120 <= length <= 900,
            "abstract chars=%d; target roughly 120-900" % length,
        )
        parts = [name for name, cues in _ABSTRACT_PARTS.items() if any(cue in abstract for cue in cues)]
        _check(
            checks,
            "abstract.four_parts",
            len(parts) >= 3,
            "detected parts: " + ", ".join(parts),
        )
        no_citation = not re.search(r"\[(?:REF-)?[0-9]{1,3}\]", abstract)
        _check(checks, "abstract.no_citations", no_citation, "abstract must not cite")
    _check(
        checks,
        "english_abstract.present",
        any("abstract" in heading.lower() for heading in headings) or "abstract" in text.lower(),
        "English Abstract section",
        severity="fail",
    )
    plain_text = text.replace("*", "")
    keyword_count = _keyword_count(plain_text)
    _check(
        checks,
        "keywords.count",
        profile["keywords_min"] <= keyword_count <= profile["keywords_max"],
        "keywords=%d; expected %d-%d"
        % (keyword_count, profile["keywords_min"], profile["keywords_max"]),
        severity="fail",
    )
    _check(
        checks,
        "classification.present",
        bool(re.search(r"中图分类号\s*[:：]?\s*TP", plain_text)),
        "中图分类号 TP",
        severity="fail",
    )
    ref_lines = [
        line for line in references.splitlines()
        if re.search(r"\[\s*\d+\s*\]", line) or _REFERENCE_TYPE_RE.search(line)
    ]
    typed = [line for line in ref_lines if _REFERENCE_TYPE_RE.search(line)]
    ratio = len(typed) / len(ref_lines) if ref_lines else 0.0
    _check(
        checks,
        "references.gb7714",
        len(ref_lines) > 0 and ratio >= profile["gb7714_min_ratio"],
        "typed reference lines=%d/%d (need >=%.0f%%)"
        % (len(typed), len(ref_lines), profile["gb7714_min_ratio"] * 100),
        severity="fail",
    )
    has_caption = bool(_FIGURE_CAPTION_RE.search(text))
    has_ref = bool(_FIGURE_REF_RE.search(text))
    _check(
        checks,
        "figures.captions",
        (not has_ref) or has_caption,
        "figure/table references require numbered captions",
    )
    if profile["requires_threats"]:
        has_threats = any(
            ("威胁" in heading) or ("validity" in heading.lower())
            for heading in headings
        )
        _check(checks, "threats.present", has_threats, "threats-to-validity section")
    intro = _section(document, ("引言", "introduction"))
    intro_cues = sum(
        1 for cue in ("问题", "不足", "贡献", "证据", "局限")
        if cue in intro
    )
    _check(
        checks,
        "introduction.arc",
        intro_cues >= 3,
        "introduction cue count=%d/5" % intro_cues,
    )
    failed = [item for item in checks if item["status"] == "fail"]
    warned = [item for item in checks if item["status"] == "warn"]
    status = "needs_revision" if failed else ("warn" if warned else "pass")
    return {
        "schema_version": SCHEMA,
        "venue_id": profile["venue_id"],
        "label": profile["label"],
        "status": status,
        "checks": checks,
        "failed": [item["id"] for item in failed],
        "warnings": [item["id"] for item in warned],
        "sources": profile["sources"],
        "boundary": BOUNDARY,
    }

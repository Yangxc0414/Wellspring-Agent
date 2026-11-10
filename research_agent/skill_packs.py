"""Skill-pack scanner: turn a local SKILL pack into auditable rubric data.

A pack is a directory of SKILL.md files plus resources (checklists, templates,
source maps). This module extracts provenance, license, resource hashes and
stage-routed checklist items. It never executes scripts, never reads the
network, and never turns a checklist into evidence, a claim or a gate.
"""

import csv
import difflib
import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .skill_registry import SkillError, parse_skill_markdown

SCHEMA = "skill-pack-0.1"
MAX_FILES = 60
MAX_BYTES = 256_000
MAX_ITEMS = 300
# one default for every face: a score whose denominator depends on whether the caller used the
# CLI or the MCP tool is not the same answer to the same question
DEFAULT_MAX_ITEMS = 200
MAX_ITEM_CHARS = 400
STAGES = ("idea", "design", "writing", "submission", "review", "reproducibility", "general")
STAGE_PROFILES = {
    "design": ("idea", "design"),
    "draft": ("idea", "design", "writing", "reproducibility"),
    "submission": ("writing", "submission", "reproducibility"),
    "revision": ("writing", "submission", "review", "reproducibility"),
}
SCRIPT_SUFFIXES = (".py", ".sh", ".cmd", ".bat", ".js", ".ts", ".ps1")
BOUNDARY = (
    "Advisory rubric extraction only: scripts are never executed, no network is used, "
    "and checklist items are not evidence, claims, gates or official journal templates. "
    "The current call/official template wins."
)
_STAGE_TERMS = {
    "idea": ("选题", "创新", "假设", "研究问题", "novelty", "gap", "motivation"),
    "design": ("实验设计", "基线", "消融", "统计", "功效", "样本", "数据划分", "baseline", "ablation", "experiment"),
    "writing": ("摘要", "关键词", "参考文献", "引言", "图表", "语言", "格式", "abstract", "reference", "citation", "writing"),
    "submission": ("投稿", "匿名", "作者承诺", "查重", "署名", "版权", "提交", "submission", "anonym", "cover letter"),
    "review": ("审稿", "回复", "退修", "rebuttal", "reviewer", "response"),
    "reproducibility": ("复现", "代码", "数据可用", "环境", "种子", "reproduc", "artifact", "code"),
}
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(?:\[[ xX]\]\s*)?(.+?)\s*$")
_NUMBERED_RE = re.compile(r"^\s*[0-9]+[.)]\s+(.+?)\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_HEADER_RE = re.compile(r"检查|要求|项目|内容|位置|清单|checklist|requirement|item", re.I)
_CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s+(.+?)\s*$")
_GENERIC_VENUE_TERMS = {
    "venue", "journal", "conference", "research", "paper", "study",
    "academic", "international", "china", "chinese",
}
_CONTEXT_HEADINGS = (
    "现状", "背景", "为什么", "为何", "常见问题", "政策", "概览", "说明",
    "原因", "动机", "引言", "介绍", "目的", "意义", "优势", "特点",
    "background", "why", "overview", "rationale", "motivation", "policy", "faq",
)
_CONTEXT_STARTS = (
    "让", "体现", "便于", "有助于", "目的是", "为了", "旨在", "可降低", "可提升",
    "增强", "提升", "说明", "例如", "比如", "这是因为",
)
_ACTION_CUES = (
    "须", "需", "应", "请", "提交", "提供", "避免", "不得", "确保", "使用",
    "标注", "引用", "删除", "补充", "补齐", "补全", "附上", "写明", "列出",
    "保持", "采用", "核对", "检查", "统一", "注明", "公开", "上传", "填写",
    "确认", "建议", "要求", "务必", "禁止", "最好", "固定", "报告",
    "must", "should", "submit", "provide", "avoid", "ensure", "use", "include",
    "list", "remove", "state", "report", "check", "verify", "upload", "write",
    "cite", "fix", "follow", "keep", "do not", "never",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raw = raw[:MAX_BYTES]
    return raw.decode("utf-8", errors="replace")


_REVIEW_HEADINGS = ("答复", "回复", "审稿", "退修", "回应", "rebuttal", "response", "reviewer")


def _stage_for(text: str, heading: str = "") -> str:
    heading_text = (heading or "").lower()
    if any(term in heading_text for term in _REVIEW_HEADINGS):
        return "review"
    haystack = (heading + "\n" + text).lower()
    best = "general"
    best_score = 0
    for stage, terms in _STAGE_TERMS.items():
        score = 0
        for term in terms:
            if term.lower() in haystack:
                score += 1
                if term.lower() in heading.lower():
                    score += 1
        if score > best_score:
            best = stage
            best_score = score
    return best


def _has_scripts(directory: Path) -> bool:
    scripts = directory / "scripts"
    if scripts.is_dir():
        return any(
            path.is_file() and path.suffix.lower() in SCRIPT_SUFFIXES
            for path in scripts.rglob("*")
        )
    try:
        return any(
            path.is_file() and path.suffix.lower() in SCRIPT_SUFFIXES
            for path in directory.iterdir()
        )
    except OSError:
        return False


def _license(root: Path) -> Dict[str, Any]:
    candidates = [root / "LICENSE", root / "LICENSE.md", root / "COPYING"]
    for path in candidates:
        if path.is_file():
            text = _read_text(path)
            declared = "unknown"
            for name in ("MIT", "Apache", "BSD", "CC BY", "Creative Commons", "GPL"):
                if name.lower() in text.lower():
                    declared = name
                    break
            return {
                "id": declared,
                "path": _rel(path, root),
                "sha256": _sha(path),
                "verified_file": True,
            }
    readme = root / "README.md"
    if readme.is_file():
        text = _read_text(readme)[:4000]
        for name in ("MIT", "Apache", "BSD", "CC BY", "Creative Commons", "GPL"):
            if name.lower() in text.lower():
                return {"id": name, "path": "", "sha256": "", "verified_file": False}
    return {"id": "unknown", "path": "", "sha256": "", "verified_file": False}


def _skill_manifests(root: Path) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    skills: List[Dict[str, Any]] = []
    skipped: List[Dict[str, str]] = []
    candidates = sorted(root.glob("skills/*/SKILL.md")) + sorted(root.glob("SKILL.md"))
    for path in candidates[:MAX_FILES]:
        try:
            manifest = parse_skill_markdown(
                _read_text(path),
                origin=_rel(path, root),
                fallback_name=path.parent.name,
                has_scripts=_has_scripts(path.parent),
            )
        except (SkillError, OSError) as exc:
            skipped.append({"path": _rel(path, root), "reason": str(exc)})
            continue
        skills.append(
            {
                "id": manifest.id,
                "name": manifest.name,
                "description": manifest.description[:300],
                "origin": manifest.origin,
                "content_hash": manifest.content_hash,
                "has_scripts": manifest.has_scripts,
                "risk_flags": list(manifest.risk_flags),
            }
        )
    return skills, skipped


def _actionable(text: str, heading: str = "", from_table: bool = False) -> bool:
    if from_table:
        return True
    heading_text = (heading or "").lower()
    if any(marker in heading_text for marker in _CONTEXT_HEADINGS):
        return False
    stripped = (text or "").strip().lower()
    if any(stripped.startswith(marker) for marker in _CONTEXT_STARTS):
        return False
    haystack = ((text or "") + " " + (heading or "")).lower()
    return any(cue in haystack for cue in _ACTION_CUES)


def _table_items(lines: List[str], heading: str, source: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    block: List[str] = []
    for line in lines + [""]:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            block.append(stripped)
            continue
        if block:
            if len(block) >= 2 and _TABLE_HEADER_RE.search(block[0]):
                for row in block[1:]:
                    if re.match(r"^\|[\s:|-]+\|$", row):
                        continue
                    cells = [cell.strip() for cell in row.strip("|").split("|")]
                    cells = [cell for cell in cells if cell and not re.match(r"^[-: ]+$", cell)]
                    if cells:
                        text = " · ".join(cells)[:MAX_ITEM_CHARS]
                        if len(text) >= 6:
                            items.append({"text": text, "source": source, "heading": heading,
                                          "stage": _stage_for(text, heading), "actionable": True})
            block = []
    return items


def _markdown_items(path: Path, root: Path) -> List[Dict[str, Any]]:
    source = _rel(path, root)
    text = _read_text(path)
    lines: List[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        lines.append(line)
    items: List[Dict[str, Any]] = []
    heading = ""
    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            heading = match.group(2).strip()
            continue
        bullet = _BULLET_RE.match(line) or _NUMBERED_RE.match(line)
        if bullet:
            item = bullet.group(1).strip().strip("-*+ ")
            if 6 <= len(item) <= MAX_ITEM_CHARS:
                items.append({"text": item, "source": source, "heading": heading,
                              "stage": _stage_for(item, heading),
                              "actionable": _actionable(item, heading)})
    items.extend(_table_items(lines, heading, source))
    return items


def _resource_files(root: Path) -> List[Path]:
    files: List[Path] = []
    resources = root / "resources"
    if resources.is_dir():
        files.extend(sorted(resources.rglob("*.md")))
    return files[:MAX_FILES]


def _dedupe(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = re.sub(r"\s+", " ", item["text"].strip().lower())
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


VENUE_INDEX = "shared-resources/journal-selection/venue-index.tsv"


def _norm(value: str) -> str:
    return re.sub(r"[\s_\-./:;，；、（）()\[\]]+", "", str(value or "").lower())


def find_venue(pack_root: Path, venue: str, limit: int = 5) -> Dict[str, Any]:
    """Route a venue name/id to a pack using the shared venue-index.tsv.

    Lexical routing only: the index is a navigation aid, not an official venue
    classification or a guarantee that the pack matches the current call.
    """
    root = Path(pack_root).resolve()
    index = root / VENUE_INDEX
    if not index.is_file():
        raise ValueError("venue index not found: " + str(index))
    query = str(venue or "").strip()
    if not query:
        raise ValueError("venue is required")
    q_norm = _norm(query)
    q_words = _word_terms(query)
    scored: List[Dict[str, Any]] = []
    with index.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="	"):
            venue_id = str(row.get("venue_id") or "")
            display = str(row.get("display_name") or "")
            keywords = str(row.get("scope_keywords") or "").lower()
            score = 0
            if q_norm and q_norm in (_norm(venue_id), _norm(display)):
                score = 100
            elif q_norm and (q_norm in _norm(venue_id) or q_norm in _norm(display)):
                score = 80
            else:
                keyword_terms = list(dict.fromkeys(
                    item for item in re.split(r"[;\s]+", keywords)
                    if len(item) >= 2 and item not in _GENERIC_VENUE_TERMS
                ))
                matched_terms = [
                    item for item in keyword_terms
                    if _keyword_matches(item, q_norm, q_words)
                ]
                if matched_terms:
                    if any(_norm(item) == q_norm for item in matched_terms):
                        score = 85
                    else:
                        cjk_longest = max([len(item) for item in matched_terms if _CJK_RUN.search(item)] or [0])
                        ascii_longest = max([len(item) for item in matched_terms if not _CJK_RUN.search(item)] or [0])
                        score = min(
                            20 + 10 * min(cjk_longest, 8)
                            + 6 * min(ascii_longest, 8) + 2 * min(len(matched_terms), 5),
                            75,
                        )
                if score > 0:
                    score = min(score + _type_bonus(query, row), 95)
            if score <= 0:
                continue
            pack_dir = str(row.get("pack_dir") or "")
            pack_path = (root / pack_dir).resolve() if pack_dir else None
            inside = bool(pack_path and (str(pack_path) == str(root) or str(pack_path).startswith(str(root) + os.sep)))
            scored.append(
                {
                    "venue_id": venue_id,
                    "display_name": display,
                    "score": score,
                    "pack_dir": pack_dir,
                    "pack_root": str(pack_path) if pack_path and inside else "",
                    "pack_exists": bool(pack_path and inside and pack_path.is_dir()),
                    "profile_path": str(row.get("profile_path") or ""),
                    "source_map": str(row.get("source_map") or ""),
                }
            )
    scored.sort(key=lambda item: (-item["score"], item["display_name"]))
    best = scored[0] if scored else None
    confidence = "none"
    if best:
        confidence = "high" if best["score"] >= 80 else ("medium" if best["score"] >= 40 else "low")
    suggestions = []
    if best is None:
        names = {}
        with index.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="	"):
                names[str(row.get("display_name") or "")] = str(row.get("venue_id") or "")
        suggestions = [
            {"display_name": name, "venue_id": names[name]}
            for name in difflib.get_close_matches(query, list(names), n=limit, cutoff=0.6)
        ]
    return {
        "schema_version": "skill-venue-route-0.1",
        "query": query,
        "index": str(index),
        "best": best,
        "confidence": confidence,
        "matches": scored[:limit],
        "suggestions": suggestions,
        "boundary": (
            "lexical routing from a shared index; not an official venue classification, "
            "not a pack quality check, and the current call/official template wins. "
            "Low confidence means the pack must be checked manually before use."
        ),
    }


_STOP_TERMS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "must", "should",
    "have", "has", "are", "was", "were", "will", "can", "may", "not", "use", "using",
    "check", "checklist", "requirement", "requirements", "item", "items", "also",
}
_CJK_STOP = {
    "实验", "研究", "方法", "结果", "论文", "工作", "数据", "系统", "问题", "内容",
    "要求", "需要", "是否", "进行", "相关", "以及", "可以", "必须", "提供", "说明",
    "明确", "完整", "一致", "版本", "使用", "一个", "我们", "本文", "其中", "通过",
    "对于", "如果", "没有", "不是", "可能", "应该", "已经", "这些", "那些", "这种",
    "方面", "情况", "部分", "主要", "重要", "一般", "具体", "时间", "阶段", "过程",
}
_CJK_RUN = re.compile(r"[一-鿿]+")
_WORD = re.compile(r"[a-zA-Z0-9]{2,}")
_VENUE_TYPE = (
    ("journal", ("journal", "学报", "期刊", "杂志")),
    ("conference", ("conference", "会议", "symposium", "workshop")),
)


def _word_terms(text: str) -> set:
    return set(re.findall(r"[a-z0-9]{2,}", str(text or "").lower()))


def _keyword_matches(term: str, q_norm: str, q_words: set) -> bool:
    if _CJK_RUN.search(term):
        return term in q_norm
    words = _word_terms(term)
    return bool(words) and words.issubset(q_words)


def _type_bonus(query: str, row: Dict[str, Any]) -> int:
    query_text = str(query or "").lower()
    venue_text = (str(row.get("venue_id") or "") + " " + str(row.get("display_name") or "")).lower()
    for _, terms in _VENUE_TYPE:
        if any(term in query_text for term in terms) and any(term in venue_text for term in terms):
            return 5
    return 0


def _coverage_tokens(text: str) -> set:
    tokens = set()
    for word in _WORD.findall(text.lower()):
        if len(word) >= 3 and word not in _STOP_TERMS:
            tokens.add(word)
    for run in _CJK_RUN.findall(text):
        if len(run) <= 2:
            tokens.add(run)
            continue
        for size in (2, 3):
            for index in range(0, len(run) - size + 1):
                token = run[index:index + size]
                if token not in _CJK_STOP:
                    tokens.add(token)
    return tokens


_DEMAND_SPLIT = re.compile(r"\s*(?:,|;|\band\b|\bor\b)\s*", re.I)


def demand_phrases(text: str) -> List[str]:
    """Split one rubric item into candidate sub-demands, lexically.

    A comma/semicolon/and/or split is not semantics. "Report uncertainty, variance, and
    statistical tests when small differences matter" becomes three phrases and an artifact can
    share the vocabulary of two - which is exactly what `covered` hides, because it is one flag
    over the whole sentence. The phrase list is therefore a hint about *where* the match came
    from, never a score, and the boundary says so.
    """
    parts = [part.strip(" .:-*") for part in _DEMAND_SPLIT.split(str(text or ""))]
    return [part for part in parts if _coverage_tokens(part)]


# a pack folder also carries scope statements and "verified facts" prose; those read like
# requirements to a heuristic but a human dismisses them, so the row says what it looks like
_SCOPE_LIKE = re.compile(r"official-source-map|已核验事实|现状说明|学科范围|背景", re.I)


# A venue pack mixes requirements on the artifact with instructions for the submission act (which
# form to open, how many pages, what to name the archive). Only the first kind can be covered by
# text already on disk, so scoring the two together makes a package look worse than it is and does
# not say which side to fix. Phrase-anchored on purpose: bare words like "anonymize" or "checklist"
# also appear in real artifact requirements ("describe the scanning steps actually performed"), and
# mis-flagging those would hide a gap instead of exposing it.
_PROCEDURAL_LIKE = re.compile(
    r"openreview|desk[ _-]?reject|dual submission|resubmission|anonymity period|"
    r"content pages|page limit|style files?|submission form|\.t?gz\b|\.zip\b|"
    r"author names?|author order|bibtex|theme track|"
    r"投稿系统|桌拒|双投|转投|匿名期|页数限制|排版模板",
    re.I,
)


def _cjk_token_share(text: str) -> float:
    """How much of what the scorer will actually match on is CJK.

    Character share is the wrong yardstick: a document of dense Chinese headings plus long ASCII
    tables reads as ~6% Chinese by characters and ~69% by tokens, and the mismatch guard built on
    characters went silent exactly when cross-script scoring was useless.
    """
    tokens = _coverage_tokens(text or "")
    if not tokens:
        return 0.0
    cjk = sum(1 for token in tokens if _CJK_RUN.search(token))
    return round(cjk / float(len(tokens)), 4)


def _dominant_script(share: float) -> str:
    if share >= 0.5:
        return "zh"
    if share <= 0.1:
        return "latin"
    return "mixed"


MIN_SCORABLE_ITEMS = 5
# Above this, one item can flip the headline by a visible amount. Measured across two venue packs
# over identical full-chain packages: the design profile contributes 7 scored items from ACL and 7
# from NeurIPS, and the same artifact reads 3/7 (0.43) against 6/7 (0.86) purely because the two
# packs word the checklist differently. A five-item floor does not protect a quoted ratio.
RATIO_GRANULARITY_POINTS = 5.0


def coverage_report(
    items: List[Dict[str, Any]],
    text: str,
    stage: str = "",
    threshold: float = 0.34,
    stages: Optional[List[str]] = None,
    artifact: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Lexical coverage of pack checklist items by a draft.

    Coverage means the draft contains related terms; it is not a compliance
    verdict, not a pass/fail check, and not evidence.  ``stages`` narrows the
    rubric to a stage profile; ``stage`` remains the single-stage option.
    ``artifact`` carries the base a quoted ratio needs (path, the code
    fingerprint of whatever generated it, when it was generated, its language);
    slots the caller cannot fill are reported as ``unknown`` rather than dropped,
    because an absent base is what made the same study read as 0/14 or 8/14.
    """
    selected = list(stages or ())
    if not selected and stage:
        selected = [stage]
    expected_all = [
        item for item in items
        if not selected or item.get("stage") in selected
    ]
    expected = [item for item in expected_all if item.get("actionable", True)]
    context_skipped = len(expected_all) - len(expected)
    haystack = _coverage_tokens(text or "")
    rows: List[Dict[str, Any]] = []
    for item in expected:
        item = dict(item)
        item["scope_like"] = bool(
            _SCOPE_LIKE.search(str(item.get("source") or ""))
            or _SCOPE_LIKE.search(str(item.get("heading") or ""))
            or _SCOPE_LIKE.search(str(item.get("text") or ""))
        )
        item["procedural_like"] = bool(
            _PROCEDURAL_LIKE.search(str(item.get("heading") or ""))
            or _PROCEDURAL_LIKE.search(str(item.get("text") or ""))
        )
        tokens = _coverage_tokens(str(item.get("text") or ""))
        if not tokens:
            rows.append({**item, "covered": False, "overlap": 0.0, "matched_terms": [],
                         "demands": 0, "matched_demands": 0, "unmet_demand_phrases": [],
                         "status": "unmatched"})
            continue
        matched = sorted(tokens & haystack)
        overlap = len(matched) / float(len(tokens))
        phrase = next((token for token in matched if len(token) >= 3 and _CJK_RUN.fullmatch(token)), "")
        covered = bool(phrase) or ((len(matched) >= 1) if len(tokens) <= 2 else (overlap >= threshold and len(matched) >= 2))
        near_miss = bool(not covered and len(matched) >= 2 and overlap >= 0.25)
        phrases = demand_phrases(str(item.get("text") or ""))
        unmet = [part for part in phrases if not (_coverage_tokens(part) & haystack)]
        rows.append(
            {
                **item,
                "covered": covered,
                "overlap": round(overlap, 3),
                "matched_terms": matched[:8],
                "matched_phrase": phrase,
                "near_miss": near_miss,
                # a covered flag over a three-part sentence does not say which parts matched; this
                # does, and `unmet_demand_phrases` keeps the reader from quoting coverage as
                # compliance when the artifact never mentions one of the demanded things
                "demands": len(phrases),
                "matched_demands": len(phrases) - len(unmet),
                "unmet_demand_phrases": unmet[:4],
                "status": "covered" if covered else "missing",
            }
        )
    covered = sum(1 for row in rows if row["status"] == "covered")
    missing = sum(1 for row in rows if row["status"] == "missing")
    unmatched = sum(1 for row in rows if row["status"] == "unmatched")
    near = sum(1 for row in rows if row.get("near_miss"))
    scope_like = sum(1 for row in rows if row.get("scope_like"))
    # A second, orthogonal denominator: which of the scored items are requirements on files at all.
    procedural_rows = [row for row in rows if row.get("procedural_like")]
    artifact_rows = [row for row in rows if not row.get("procedural_like")]
    procedural_covered = sum(1 for row in procedural_rows if row["status"] == "covered")
    artifact_covered = sum(1 for row in artifact_rows if row["status"] == "covered")
    procedural_missing = len(procedural_rows) - procedural_covered
    artifact_missing = len(artifact_rows) - artifact_covered
    rubric_text = " ".join(str(row.get("text") or "") for row in rows)
    script_share = {
        "artifact_cjk_token_share": _cjk_token_share(text or ""),
        "rubric_cjk_token_share": _cjk_token_share(rubric_text),
    }
    dominant_scripts = {
        "artifact": _dominant_script(script_share["artifact_cjk_token_share"]),
        "rubric": _dominant_script(script_share["rubric_cjk_token_share"]),
    }
    mismatch = bool(rows) and (
        dominant_scripts["artifact"] != dominant_scripts["rubric"]
        or "mixed" in (dominant_scripts["artifact"], dominant_scripts["rubric"])
    )
    warnings: List[str] = []
    if not rows:
        warnings.append(
            "no rubric item was scored, so covered=0 of items=0 describes nothing about the "
            "artifact; check the pack path and the stage/profile filter"
        )
    if mismatch:
        reason = (
            "the rubric and the artifact are written in different scripts"
            if dominant_scripts["artifact"] != dominant_scripts["rubric"]
            else "at least one side is mixed-script, so some requirement terms are written in a "
            "script the other side never uses"
        )
        warnings.append(
            "coverage: %s (artifact %s at %.2f CJK tokens, rubric %s at %.2f); %d of %d items "
            "matched only through shared tokens, overlap under-reports the rest, so these counts "
            "are a rough punch list and not a score"
            % (
                reason,
                dominant_scripts["artifact"],
                script_share["artifact_cjk_token_share"],
                dominant_scripts["rubric"],
                script_share["rubric_cjk_token_share"],
                covered,
                len(rows),
            )
        )
    # A one-item denominator is not a verdict about the stage: measured across the same pack
    # root, ACL-Skills yields 1 checklist item for the ideation stage while it yields 19 for
    # design and 43 for submission, so "covered 0 of 1" says more about the pack's routing than
    # about the artifact. Report the thin denominator instead of letting the ratio stand alone.
    thin_denominator = 0 < len(rows) < MIN_SCORABLE_ITEMS
    if thin_denominator:
        warnings.append(
            "thin denominator: the pack yields only %d actionable item(s) for stage=%s, so this "
            "coverage number is not a verdict about the stage; scan the same stage across other "
            "venues in the pack root (they differ by up to 7x) before quoting a ratio"
            % (len(rows), stage or "all")
        )
    # Warn when the split changes the quoted number, not merely when it exists: if the procedural
    # rows were mostly covered the head ratio is already honest. Measured on the ACL submission
    # profile over a full-chain study package: 14/38 head against 14/28 artifact-side, where all
    # 10 reclassified rows were submission-act instructions and none was ever covered.
    head_ratio = covered / float(len(rows)) if rows else 0.0
    artifact_headroom = (artifact_covered / float(len(artifact_rows)) if artifact_rows else 0.0)
    if missing and abs(artifact_headroom - head_ratio) >= 0.1:
        # Both directions mean something different: leaving out covered submission instructions
        # overstates the artifact, leaving in uncovered ones understates it.
        direction = "understates the artifact" if artifact_headroom > head_ratio else (
            "overstates the artifact, because the text matched submission-act instructions it does "
            "not satisfy"
        )
        warnings.append(
            "mixed denominator: %d of %d missing item(s) read like instructions for the submission "
            "act (which form, how many pages, what to name the archive) rather than requirements on "
            "files, so the head ratio of %d/%d (%.2f) %s; the actionable split "
            "is %d/%d (%.2f). procedural_like is a lexical heuristic and never removes an item from "
            "the denominator: a human must confirm each flagged row before using it to dismiss a "
            "requirement"
            % (
                procedural_missing,
                missing,
                covered,
                len(rows),
                head_ratio,
                direction,
                artifact_covered,
                len(artifact_rows),
                artifact_headroom,
            )
        )
    granularity = 100.0 / len(rows) if rows else 0.0
    if granularity > RATIO_GRANULARITY_POINTS:
        warnings.append(
            "ratio granularity: this pack contributes %d scored item(s), so one item moves the "
            "headline by %.1f points and the ratio is as much a property of the pack as of the "
            "artifact; quote the missing items instead of the number (measured on identical "
            "packages: the design profile yields 3/7 from ACL against 6/7 from NeurIPS)"
            % (len(rows), granularity)
        )
    artifact_info = dict(artifact or {})
    confidence = "unusable" if not rows else ("degraded" if mismatch else "ok")
    stage_label = stage or (",".join(selected) if selected else "all-stages")
    # The base of the ratio, in words, with every slot the caller could not fill named as unknown:
    # coverage of the same study measured 0/14 and 8/14 depending on which build printed its README
    # and whether the bundle mixed scripts, so a number quoted without these is not comparable.
    comparability = {
        "denominator": "scored items %d of %d scanned (%d narrative/context bullets skipped)"
        % (len(rows), len(items), context_skipped),
        "artifact_denominator": "artifact-requirement items %d of %d scored (%d read as instructions for the submission act)"
        % (len(artifact_rows), len(rows), len(procedural_rows)),
        "stage_label": stage_label,
        "threshold": threshold,
        "granularity_points": round(granularity, 1),
        "script": "%s artifact vs %s rubric (cjk token share %.3f vs %.3f), coverage_confidence=%s"
        % (
            dominant_scripts.get("artifact") or "unknown",
            dominant_scripts.get("rubric") or "unknown",
            float(script_share.get("artifact_cjk_token_share") or 0.0),
            float(script_share.get("rubric_cjk_token_share") or 0.0),
            confidence,
        ),
        "artifact_path": str(artifact_info.get("path") or "unknown"),
        "artifact_fingerprint": str(artifact_info.get("fingerprint") or "unknown"),
        "artifact_generated_at": str(artifact_info.get("generated_at") or "unknown"),
        "artifact_language": str(artifact_info.get("language") or "unknown"),
        "partial_matches": sum(
            1 for row in rows
            if row["status"] == "covered" and row.get("demands", 0) > row.get("matched_demands", 0)
        ),
        "boundary": (
            "the base of the ratio, not a second score: demands/matched_demands per row come from "
            "splitting the rubric sentence on commas, semicolons, 'and' and 'or', which is a lexical "
            "guess about where the match came from and never a judgement about how many requirements "
            "are satisfied; partial_matches counts covered rows whose sentence has an unmet phrase, "
            "so a reader can see that covered does not mean fully covered; artifact_fingerprint is "
            "the code that printed the artifact, and 'unknown' means the caller could not supply it "
            "- which is itself the reason two packages can score differently for reasons that are "
            "not about the study"
        ),
    }
    quote_as = (
        "%s coverage %d/%d scored items (of %d scanned; artifact-only %d/%d) at threshold %.2f, "
        "granularity %.1f points, script %s/%s confidence=%s, artifact %s fingerprint %s, "
        "%d covered row(s) with an unmet phrase"
        % (
            stage_label, covered, len(rows), len(items), artifact_covered, len(artifact_rows),
            threshold, round(granularity, 1),
            dominant_scripts.get("artifact") or "?", dominant_scripts.get("rubric") or "?",
            confidence, comparability["artifact_path"], comparability["artifact_fingerprint"],
            comparability["partial_matches"],
        )
    )
    by_stage: Dict[str, Dict[str, int]] = {}
    for row in rows:
        bucket = by_stage.setdefault(str(row.get("stage") or "general"), {})
        bucket["items"] = bucket.get("items", 0) + 1
        key = "covered" if row["status"] == "covered" else "missing"
        bucket[key] = bucket.get(key, 0) + 1
    from datetime import datetime, timezone

    from .paths import build_info

    return {
        "schema_version": "skill-pack-coverage-0.4",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_fingerprint": str(build_info().get("fingerprint") or ""),
        "read_only": True,
        "base": "%s; %s" % (comparability["denominator"], comparability["artifact_denominator"]),
        "provenance": {
            "artifact_path": comparability["artifact_path"],
            "artifact_fingerprint": comparability["artifact_fingerprint"],
            "artifact_generated_at": comparability["artifact_generated_at"],
            "artifact_language": comparability["artifact_language"],
            "script": comparability["script"],
        },
        # one truth per field: an empty value means unfiltered, and "all" is never invented
        "stage": stage,
        "stages": list(selected),
        "threshold": threshold,
        "items": len(rows),
        # scored vs scanned: 19 design bullets filter down to 6 actionable ones, and a 6/6 read as
        # perfection would hide that thirteen requirements were never scored at all
        "items_scanned": len(items),
        "covered": covered,
        "missing": missing,
        "unmatched": unmatched,
        "near_miss": near,
        "scope_like": scope_like,
        # the head ratio above scores the whole pack; this partition says how much of that pack is
        # a requirement on files at all, and it is reported next to the head ratio, never instead
        "procedural_items": len(procedural_rows),
        "procedural_covered": procedural_covered,
        "procedural_missing": procedural_missing,
        "artifact_items": len(artifact_rows),
        "artifact_covered": artifact_covered,
        "artifact_missing": artifact_missing,
        "artifact_ratio": (
            round(artifact_covered / float(len(artifact_rows)), 3) if artifact_rows else 0.0
        ),
        "ratio_granularity_points": round(granularity, 1),
        "context_skipped": context_skipped,
        # one number over a mixed profile hides where the gap actually is
        "by_stage": by_stage,
        "language_mismatch": mismatch,
        "thin_denominator": thin_denominator,
        "items_required_for_verdict": MIN_SCORABLE_ITEMS,
        # the guard's own evidence travels with the verdict, or the reader cannot check it
        "script_share": script_share,
        "dominant_scripts": dominant_scripts,
        "coverage_confidence": (
            "unusable" if not rows else ("degraded" if mismatch else "ok")
        ),
        "warnings": warnings,
        "rows": rows,
        "comparability": comparability,
        "quote_as": quote_as,
        "boundary": (
            "lexical coverage only: a covered item means related terms appear, not that the "
            "requirement is satisfied; near_miss lists items that share terms but fall under the "
            "threshold; cross-script and mixed-script pairs under-report, which is reported as "
            "script_share/dominant_scripts/coverage_confidence over the same token set the score "
            "uses rather than over character counts; narrative/context "
            "bullets are skipped by a heuristic actionability flag, scope_like marks scored items "
            "that read like scope or verified-fact statements a human should dismiss, "
            "procedural_like marks scored items that read like instructions for the submission act "
            "(which form, how many pages, what to name the archive) rather than requirements on "
            "files, and the artifact_* counts partition the same scored items without removing any "
            "of them, because a heuristic that can inflate a score by reclassifying a gap is not a "
            "guard; and this never changes a status or creates evidence"
        ),
    }


_NAVIGATION_WORDS = re.compile(
    r"\b(use|see|refer to|refer|check|follow|and|or)\b|见|详见|参见|参考|使用|请|的",
    re.I,
)


def _navigation_only(text: str, names: List[str]) -> bool:
    lowered = text.lower()
    if not any(name in lowered for name in names):
        return False
    tail = re.split(r"[:：]", text, 1)[-1]
    residue = re.sub(r"`[^`]*`", " ", tail)
    residue = _NAVIGATION_WORDS.sub(" ", residue)
    residue = re.sub(r"[\s,，、.。;；:：!！?？()（）\-*_/]+", " ", residue).strip()
    return len(residue) <= 1


def scan_pack(
    root: Path,
    stage: str = "",
    max_items: int = 200,
    stages: Optional[List[str]] = None,
) -> Dict[str, Any]:
    base = Path(root).resolve()
    if not base.is_dir():
        raise ValueError("skill pack root is not a directory: " + str(root))
    if stage and stage not in STAGES:
        raise ValueError("unknown stage: %s (choose %s)" % (stage, ", ".join(STAGES)))
    profile = [str(name) for name in (stages or ()) if name]
    for name in profile:
        if name not in STAGES:
            raise ValueError("unknown stage: %s (choose %s)" % (name, ", ".join(STAGES)))
    limit = max(1, min(int(max_items), MAX_ITEMS))
    clamped = limit < int(max_items)
    licence = _license(base)
    skills, skipped = _skill_manifests(base)
    resources: List[Dict[str, Any]] = []
    checklist: List[Dict[str, Any]] = []
    for path in sorted(base.glob("skills/*/SKILL.md"))[:MAX_FILES]:
        checklist.extend(_markdown_items(path, base))
    for path in _resource_files(base):
        resources.append(
            {
                "path": _rel(path, base),
                "sha256": _sha(path),
                "kind": _resource_kind(path),
            }
        )
        checklist.extend(_markdown_items(path, base))
    checklist = _dedupe(checklist)
    skill_names = [
        str(name).lower()
        for name in ([item["id"] for item in skills] + [item["name"] for item in skills])
        # only slug-like identifiers: a plain word such as "Submission" would match half the pack
        if len(str(name)) >= 4 and ("-" in str(name) or "_" in str(name))
    ]
    for item in checklist:
        item["navigation"] = _navigation_only(item["text"], skill_names)
        if item["navigation"]:
            item["actionable"] = False
    if stage:
        checklist = [item for item in checklist if item["stage"] == stage]
    if profile:
        # narrowing must happen before the window, otherwise a small --max-items on a big
        # pack silently drops the stage the caller asked for instead of the rest
        checklist = [item for item in checklist if item["stage"] in profile]
    checklist_total = len(checklist)
    truncated = checklist_total > limit
    checklist = checklist[:limit]
    counts: Dict[str, int] = {}
    actionable_counts: Dict[str, int] = {}
    for item in checklist:
        counts[item["stage"]] = counts.get(item["stage"], 0) + 1
        if item.get("actionable", True):
            actionable_counts[item["stage"]] = actionable_counts.get(item["stage"], 0) + 1
    warnings: List[str] = []
    if clamped:
        warnings.append(
            "requested %d items but the pack window is capped at %d; use --stage or "
            "--profile to narrow the rubric instead of raising the cap"
            % (int(max_items), limit)
        )
    if licence["id"] == "unknown":
        warnings.append("no license file or declared license found; do not redistribute")
    if not licence["verified_file"] and licence["id"] != "unknown":
        warnings.append("license is declared in README but no LICENSE file was verified")
    if truncated:
        warnings.append(
            "checklist truncated to %d of %d items" % (limit, checklist_total)
        )
    if skipped:
        warnings.append("%d SKILL.md file(s) skipped" % len(skipped))
    if checklist_total == 0:
        warnings.append(
            "the pack exposes 0 rubric items under this stage/profile filter; a 0-of-0 report "
            "means nothing was checked, not that the artifact passes"
        )
    return {
        "schema_version": SCHEMA,
        "pack": base.name,
        "root": str(base),
        "license": licence,
        "skills": skills,
        "resources": resources,
        "checklist": checklist,
        "checklist_total": checklist_total,
        "limit_applied": limit,
        "profile_stages": profile,
        "stage_counts": counts,
        "actionable_counts": actionable_counts,
        "truncated": truncated,
        "skipped": skipped,
        "warnings": warnings,
        "boundary": BOUNDARY,
    }


def _resource_kind(path: Path) -> str:
    name = path.name.lower()
    if "checklist" in name or "rubric" in name:
        return "checklist"
    if "template" in name:
        return "template"
    if "exemplar" in name or "example" in name:
        return "exemplar"
    if "source" in name or "official" in name:
        return "source_map"
    return "resource"

"""Revise an existing manuscript against user data and a venue profile.

This module does not invent a new research project. It preserves the original
sections, experimental narrative, citations and numbers, optionally rewrites
paragraphs with a model, recomputes declared data metrics, generates data-backed
figures, audits the result, and exports a working submission package.
"""

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .paths import DEFAULT_MODEL_STORE_PATH
from .revision_figures import generate_figures, load_figure_specs
from .revision_io import (
    RevisionIOError,
    apply_metric_replacements,
    compute_metrics,
    export_document,
    extract_numbers,
    load_data_tables,
    load_metric_specs,
    profile_tables,
    read_draft,
    render_markdown,
)
from .revision_templates import (
    get_venue_profile,
    missing_required_sections,
    profile_summary,
)
from .revision_types import Block, DraftDocument, MetricResult, Section
from .storage import write_json_atomic

REVISION_SCHEMA = "manuscript-revision-0.1"
REVISION_AUDIT_SCHEMA = "revision-audit-0.1"
BOUNDARY = (
    "revision preserves the user's research narrative and cites; it does not invent data, "
    "claims, peer review or journal acceptance; submission_ready is always false"
)
SKIP_REWRITE_HEADINGS = (
    "参考文献", "references", "bibliography", "致谢", "acknowledg", "附录", "appendix",
    "作者", "author", "基金", "funding", "声明", "declaration",
)
PROTECTED_HEADINGS = (
    "方法", "实验", "结果", "讨论", "method", "experiment", "result", "discussion",
)
CITATION_PATTERNS = (
    r"\[\[@[^\]]+\]\]",
    r"\[@[^\]]+\]",
    r"\[\d+(?:\s*[-,]\s*\d+)*\]",
    r"（[^（）]{0,40}\d{4}[a-z]?）",
    r"\([A-Za-z][^()]{0,60}\d{4}[a-z]?\)",
)
FIGURE_REF_RE = re.compile(r"(图|表|figure|table|fig\.?)\s*([0-9一二三四五六七八九十]+)", re.I)
URL_RE = re.compile(r"https?://\S+|www\.\S+")
SYSTEM_PROMPT = (
    "You are revising an existing research manuscript, not writing a new paper. "
    "Improve clarity, logical flow, concision and venue-appropriate academic style. You may "
    "restructure sentences and merge redundancy, but preserve every fact, experimental "
    "condition, method detail, limitation, numeric value, citation token, figure/table "
    "reference and section order. Do not add citations, numbers, claims, experiments, data, "
    "authors or acknowledgements. Do not remove experimental narrative. Do not return the "
    "original unchanged unless it already meets the goal; if unchanged, explain why in "
    "change_summary. Rewrite only the supplied paragraph; never include the section heading, "
    "neighboring paragraphs or the whole section. Return only JSON: "
    "{\"text\":\"...\",\"change_summary\":[\"short change\"]}."
)


class RevisionError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _strip_citations(text: str) -> str:
    result = str(text or "")
    for pattern in CITATION_PATTERNS:
        result = re.sub(pattern, " ", result)
    return URL_RE.sub(" ", result)


def extract_citations(text: str) -> List[str]:
    values: List[str] = []
    for pattern in CITATION_PATTERNS:
        values.extend(re.findall(pattern, str(text or "")))
    return sorted(set(item.strip() for item in values if item.strip()))


def protected_numbers(text: str) -> List[str]:
    return extract_numbers(_strip_citations(text))


def _figure_refs(text: str) -> List[str]:
    refs = set()
    for label, number in FIGURE_REF_RE.findall(text or ""):
        kind = "figure" if label.lower().startswith(("图", "fig")) else "table"
        refs.add("%s:%s" % (kind, number))
    return sorted(refs)


def _section_is_protected(heading: str) -> bool:
    lowered = str(heading or "").lower()
    return any(marker in lowered for marker in PROTECTED_HEADINGS)


def _skip_section(heading: str) -> bool:
    lowered = str(heading or "").strip().lower()
    if not lowered:
        return True
    return any(marker in lowered for marker in SKIP_REWRITE_HEADINGS)


def _gateway_model(profile_id: str, store_path: Optional[str]) -> Any:
    from .models import GatewayModelPort, GatewayStore, ModelGateway

    store = GatewayStore(Path(store_path or DEFAULT_MODEL_STORE_PATH))
    if profile_id not in store.profiles:
        raise RevisionError("unknown model profile: " + profile_id)
    profile = store.profiles[profile_id]
    provider = store.provider(profile.provider_id)
    gateway = ModelGateway(store)
    key, _ = gateway.keys.resolve(provider)
    if not key:
        raise RevisionError(
            "model provider %s has no key (%s)" % (provider.provider_id, provider.api_key_env)
        )
    return GatewayModelPort(gateway, profile_id)


def _parse_model_json(raw: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", str(raw or ""), re.DOTALL)
    if not match:
        raise RevisionError("model returned no JSON object")
    try:
        value = json.loads(match.group(0))
    except ValueError:
        raise RevisionError("model returned invalid JSON")
    if not isinstance(value, dict):
        raise RevisionError("model returned a non-object")
    for _ in range(3):
        text = str(value.get("text") or "").strip()
        if text.startswith("{") and text.endswith("}"):
            try:
                nested = json.loads(text)
            except ValueError:
                break
            if isinstance(nested, dict) and nested.get("text"):
                value = nested
                continue
        break
    text = str(value.get("text") or "").strip()
    if not text:
        raise RevisionError("model returned empty text")
    summary = value.get("change_summary")
    if not isinstance(summary, list):
        summary = []
    return {
        "text": text,
        "change_summary": [str(item).strip()[:240] for item in summary if str(item).strip()][:10],
    }


def _validate_rewrite(
    original: str,
    revised: str,
    protected: bool,
) -> Tuple[List[str], List[str]]:
    blockers: List[str] = []
    warnings: List[str] = []
    original_citations = set(extract_citations(original))
    revised_citations = set(extract_citations(revised))
    if original_citations != revised_citations:
        missing = sorted(original_citations - revised_citations)
        added = sorted(revised_citations - original_citations)
        blockers.append("citation set changed (missing=%s added=%s)" % (missing, added))
    original_numbers = set(protected_numbers(original))
    revised_numbers = set(protected_numbers(revised))
    added_numbers = sorted(revised_numbers - original_numbers)
    missing_numbers = sorted(original_numbers - revised_numbers)
    if added_numbers:
        blockers.append("new numbers added: " + ", ".join(added_numbers[:8]))
    if missing_numbers and protected:
        blockers.append("protected numbers missing: " + ", ".join(missing_numbers[:8]))
    elif missing_numbers:
        warnings.append("numbers not retained: " + ", ".join(missing_numbers[:8]))
    original_refs = set(_figure_refs(original))
    revised_refs = set(_figure_refs(revised))
    if original_refs - revised_refs:
        blockers.append("figure/table references removed: " + ", ".join(sorted(original_refs - revised_refs)))
    if revised_refs - original_refs:
        blockers.append("figure/table references added: " + ", ".join(sorted(revised_refs - original_refs)))
    for marker in ("TODO", "TBD", "DATA_NEEDED", "待补"):
        if marker in revised and marker not in original:
            blockers.append("new placeholder introduced: " + marker)
    if "\n\n" not in original and "\n\n" in revised:
        blockers.append("rewrite changed paragraph scope: original is one paragraph but revised has multiple paragraphs")
    ratio = len(revised) / max(1, len(original))
    if ratio < 0.5:
        blockers.append("rewrite too short: %.2f of original" % ratio)
    elif ratio > 1.8:
        blockers.append("rewrite too long: %.2f of original" % ratio)
    return blockers, warnings


def _insert_figures(document: DraftDocument, manifest: Dict[str, Any]) -> None:
    for item in manifest.get("figures") or []:
        heading = str(item.get("insert_after_heading") or "")
        block = Block(
            kind="figure",
            image=str(item.get("png") or ""),
            caption=str(item.get("caption") or item.get("title") or ""),
            meta={"figure_id": item.get("figure_id"), "manifest": item},
        )
        target = None
        if heading:
            target = next(
                (section for section in document.sections if heading.lower() in section.heading.lower()),
                None,
            )
        if target is None:
            target = next(
                (
                    section for section in document.sections
                    if any(marker in section.heading.lower() for marker in ("结果", "result", "实验", "experiment"))
                ),
                None,
            )
        if target is None:
            target = document.sections[-1] if document.sections else Section(heading="", level=0)
            if not document.sections:
                document.sections.append(target)
        target.blocks.append(block)


def load_review_comments(path: Path) -> List[str]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()][:20]
    if not isinstance(value, dict):
        return []
    for key in ("must_fix", "review_comments"):
        items = value.get(key)
        if isinstance(items, list):
            return [str(item).strip() for item in items if str(item).strip()][:20]
    iterations = value.get("iterations")
    if isinstance(iterations, list):
        for item in reversed(iterations):
            review = item.get("review") if isinstance(item, dict) else None
            if isinstance(review, dict) and isinstance(review.get("must_fix"), list):
                return [str(fix).strip() for fix in review["must_fix"] if str(fix).strip()][:20]
    return []


def _strip_section_heading(text: str, heading: str) -> str:
    value = str(text or "").strip()
    target = str(heading or "").strip()
    if not value or not target:
        return value
    lines = value.splitlines()
    first = lines[0].strip().lstrip("#").strip()
    if first == target:
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines.pop(0)
        return "\n".join(lines).strip()
    if value.startswith(target + " "):
        return value[len(target):].strip()
    return value


def _rewrite_document(
    document: DraftDocument,
    model: Any,
    sections: Sequence[str],
    venue: Dict[str, Any],
    metrics: Sequence[MetricResult],
    goal: str = "",
    review_comments: Optional[Sequence[str]] = None,
    plan: Optional[Dict[str, Any]] = None,
    auto_plan: bool = False,
) -> Dict[str, Any]:
    wanted = [item.strip().lower() for item in sections if str(item).strip()]
    plan_actions: Dict[tuple, Dict[str, Any]] = {}
    plan_sections: Dict[str, Dict[str, Any]] = {}
    for plan_section in (plan or {}).get("sections") or []:
        heading = str(plan_section.get("heading") or "")
        plan_sections[heading] = plan_section
        for action in plan_section.get("paragraph_actions") or []:
            plan_actions[(heading, int(action.get("block_index", -1)))] = action
    records: List[Dict[str, Any]] = []
    blockers: List[str] = []
    warnings: List[str] = []
    changed = 0
    for section in document.sections:
        if _skip_section(section.heading):
            continue
        if wanted and not any(item in section.heading.lower() for item in wanted):
            continue
        protected = _section_is_protected(section.heading)
        section_text = "\n".join(block.text for block in section.blocks if block.text)[:4000]
        for index, block in enumerate(section.blocks):
            if block.kind not in ("paragraph", "bullet"):
                continue
            original = block.text.strip()
            if len(original) < 40:
                continue
            payload = {
                "venue": profile_summary(venue),
                "document_title": document.title,
                "section": section.heading,
                "paragraph_context_before": (
                    section.blocks[index - 1].text[-260:]
                    if index > 0 and section.blocks[index - 1].text else ""
                ),
                "paragraph_context_after": (
                    section.blocks[index + 1].text[:260]
                    if index + 1 < len(section.blocks) and section.blocks[index + 1].text else ""
                ),
                "output_scope": "Rewrite only original_text; do not output headings or neighboring paragraphs.",
                "rewrite_goal": goal or "improve clarity and logical flow without changing facts",
                "review_comments": list(review_comments or [])[:12],
                "plan_section_role": (plan_sections.get(section.heading) or {}).get("role", ""),
                "plan_issues": (plan_sections.get(section.heading) or {}).get("issues", []),
                "plan_action": (plan_actions.get((section.heading, index)) or {}).get("action", ""),
                "original_text": original,
                "data_metrics": [
                    {"name": metric.name, "value": metric.formatted, "op": metric.op}
                    for metric in metrics if metric.formatted
                ],
                "protected_numbers": protected_numbers(original),
                "protected_citations": extract_citations(original),
                "requirements": [
                    "Preserve all facts and experimental narrative.",
                    "Do not invent citations, numbers, data or claims.",
                    "Keep citation tokens and figure/table references unchanged.",
                ],
            }
            try:
                raw = model.complete(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                    json_mode=True,
                )
                parsed = _parse_model_json(raw)
                parsed["text"] = _strip_section_heading(parsed["text"], section.heading)
                section_blockers, section_warnings = _validate_rewrite(
                    original, parsed["text"], protected=protected
                )
            except Exception as exc:
                section_blockers = ["model or parse failure: %s" % type(exc).__name__]
                section_warnings = []
                parsed = {"text": original, "change_summary": []}
            unchanged = not section_blockers and parsed.get("text", "").strip() == original
            record = {
                "section": section.heading,
                "block_index": index,
                "protected": protected,
                "status": (
                    "unchanged" if unchanged else
                    "accepted" if not section_blockers else "rejected"
                ),
                "blockers": section_blockers,
                "warnings": section_warnings,
                "change_summary": parsed.get("change_summary", []),
                "original_text": original,
                "revised_text": parsed.get("text", original),
            }
            records.append(record)
            if section_blockers:
                blockers.extend(
                    "%s / block %d: %s" % (section.heading, index, item)
                    for item in section_blockers
                )
            elif unchanged:
                warnings.append("%s / block %d: model returned unchanged text" % (section.heading, index))
            else:
                warnings.extend(
                    "%s / block %d: %s" % (section.heading, index, item)
                    for item in section_warnings
                )
                block.text = parsed["text"]
                changed += 1
    return {
        "records": records,
        "blockers": blockers,
        "warnings": warnings,
        "changed_blocks": changed,
        "requested_sections": list(sections),
    }


SENTENCE_RE = re.compile(r"(?<=[。！？.!?])\s+")


def _sentences(text: str) -> List[str]:
    value = str(text or "").strip()
    if not value:
        return []
    return [item.strip() for item in SENTENCE_RE.split(value) if item.strip()]


def _sentence_ledger(
    document: DraftDocument, metrics: Sequence[MetricResult]
) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for section in document.sections:
        protected = _section_is_protected(section.heading)
        for block_index, block in enumerate(section.blocks):
            if block.kind not in ("paragraph", "bullet"):
                continue
            for sentence_index, sentence in enumerate(_sentences(block.text)):
                citations = extract_citations(sentence)
                numbers = protected_numbers(sentence)
                refs = _figure_refs(sentence)
                metric_refs: List[str] = []
                for token in numbers:
                    try:
                        number = float(token.replace("%", ""))
                    except ValueError:
                        continue
                    for metric in metrics:
                        if metric.value is None:
                            continue
                        tolerance = max(1e-9, abs(metric.value) * 0.001)
                        if abs(number - metric.value) <= tolerance:
                            metric_refs.append(metric.name)
                if citations or refs:
                    status = "cited"
                elif metric_refs:
                    status = "metric_backed"
                elif numbers:
                    status = "numeric_unreferenced"
                else:
                    status = "no_explicit_ref"
                entries.append(
                    {
                        "section": section.heading,
                        "block_index": block_index,
                        "sentence_index": sentence_index,
                        "protected_section": protected,
                        "citations": citations,
                        "figure_table_refs": refs,
                        "numbers": numbers,
                        "metric_refs": sorted(set(metric_refs)),
                        "status": status,
                        "sentence": sentence[:500],
                    }
                )
    summary = {
        "sentences": len(entries),
        "cited": sum(1 for item in entries if item["status"] == "cited"),
        "metric_backed": sum(1 for item in entries if item["status"] == "metric_backed"),
        "metric_linked": sum(1 for item in entries if item["metric_refs"]),
        "numeric_unreferenced": sum(1 for item in entries if item["status"] == "numeric_unreferenced"),
        "no_explicit_ref": sum(1 for item in entries if item["status"] == "no_explicit_ref"),
        "protected_numeric_unreferenced": sum(
            1 for item in entries
            if item["protected_section"] and item["status"] == "numeric_unreferenced"
        ),
    }
    return {
        "schema_version": "revision-sentence-ledger-0.1",
        "entries": entries,
        "summary": summary,
        "boundary": (
            "sentence ledger records explicit citations, figure/table refs and data-metric matches; "
            "it does not prove semantic entailment"
        ),
    }


def _metric_context(metrics: Sequence[MetricResult], document: DraftDocument) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for section in document.sections:
        for block in section.blocks:
            if block.kind not in ("paragraph", "bullet", "caption"):
                continue
            for token in protected_numbers(block.text):
                try:
                    number = float(token.replace("%", ""))
                except ValueError:
                    continue
                for metric in metrics:
                    if metric.value is None:
                        continue
                    tolerance = max(1e-9, abs(metric.value) * 0.001)
                    if abs(number - metric.value) <= tolerance:
                        matches.append(
                            {
                                "section": section.heading,
                                "number": token,
                                "metric": metric.name,
                                "formatted": metric.formatted,
                                "exact": token == metric.formatted,
                            }
                        )
    return matches


def _audit(
    document: DraftDocument,
    venue: Dict[str, Any],
    metrics: Sequence[MetricResult],
    metric_replacements: Sequence[Dict[str, Any]],
    figures: Dict[str, Any],
    rewrite: Dict[str, Any],
    writer_mode: str,
    export: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    blockers = list(rewrite.get("blockers") or [])
    warnings = list(document.warnings) + list(rewrite.get("warnings") or [])
    for metric in metrics:
        if metric.error:
            blockers.append("metric %s: %s" % (metric.name, metric.error))
    if writer_mode == "copy":
        warnings.append("no model profile supplied; manuscript text is unchanged (copy mode)")
    missing_sections = missing_required_sections(
        [section.heading for section in document.sections], venue
    )
    if missing_sections:
        warnings.append(
            "venue profile is missing suggested sections: "
            + "; ".join("/".join(group) for group in missing_sections)
        )
    if not figures.get("figures"):
        warnings.append("no data-backed figure was generated")
    else:
        referenced = " ".join(
            block.text for section in document.sections for block in section.blocks
            if block.kind in ("paragraph", "bullet", "caption")
        )
        for item in figures.get("figures") or []:
            if str(item.get("figure_id")) not in referenced and "图" not in referenced:
                warnings.append("generated figure is not referenced in the manuscript: " + str(item.get("figure_id")))
    sentence_ledger = _sentence_ledger(document, metrics)
    if sentence_ledger["summary"]["protected_numeric_unreferenced"]:
        warnings.append(
            "%d numeric sentence(s) in method/result/discussion sections have no citation, "
            "figure/table ref or computed metric" % sentence_ledger["summary"]["protected_numeric_unreferenced"]
        )
    if export:
        warnings.extend(export.get("warnings") or [])
    export_files = (export or {}).get("files") or {}
    format_ready = bool(
        export_files.get("markdown")
        and (export_files.get("docx") or export_files.get("latex"))
    )
    if writer_mode == "model" and not (rewrite.get("changed_blocks") or 0):
        warnings.append("model mode produced no accepted rewritten block; text remains original")
    status = "blocked" if blockers else (
        "copy_only" if writer_mode == "copy" or not (rewrite.get("changed_blocks") or 0)
        else "review_ready"
    )
    return {
        "schema_version": REVISION_AUDIT_SCHEMA,
        "status": status,
        "submission_ready": False,
        "review_ready": status == "review_ready",
        "format_ready": format_ready,
        "writer_mode": writer_mode,
        "template_status": venue.get("template_status"),
        "template_disclaimer": venue.get("disclaimer"),
        "missing_suggested_sections": missing_sections,
        "metrics": [metric.to_dict() for metric in metrics],
        "metric_matches": _metric_context(metrics, document),
        "sentence_ledger_summary": sentence_ledger["summary"],
        "metric_replacements": list(metric_replacements),
        "figures": figures.get("figures") or [],
        "rewrite": rewrite,
        "blockers": blockers,
        "warnings": warnings,
        "boundary": BOUNDARY,
        "created_at": _now(),
    }


def _summary_markdown(
    document: DraftDocument,
    audit: Dict[str, Any],
    export: Optional[Dict[str, Any]],
) -> str:
    lines = [
        "# 已有手稿修订摘要",
        "",
        "- 标题：%s" % document.title,
        "- 状态：`%s`" % audit["status"],
        "- 写作模式：`%s`" % audit["writer_mode"],
        "- submission_ready：`false`（本模块不替代投稿决定）",
        "- 模板：%s（%s）" % (
            audit.get("template_status"),
            (audit.get("template_disclaimer") or "").strip(),
        ),
        "",
        "## 数据指标",
        "",
    ]
    if audit.get("metrics"):
        for metric in audit["metrics"]:
            lines.append(
                "- `%s` = `%s` (%s, %d rows)%s"
                % (
                    metric.get("name"), metric.get("formatted"), metric.get("op"),
                    metric.get("count", 0),
                    "  ERROR: " + metric["error"] if metric.get("error") else "",
                )
            )
    else:
        lines.append("- 未提供 metric spec")
    lines += ["", "## 新图", ""]
    if audit.get("figures"):
        for figure in audit["figures"]:
            lines.append("- `%s` → `%s`" % (figure.get("figure_id"), figure.get("png")))
    else:
        lines.append("- 未生成新图")
    ledger_summary = audit.get("sentence_ledger_summary") or {}
    if ledger_summary:
        lines += ["", "## 逐句引用/数字账本", ""]
        lines.append(
            "- %d 句：%d 引用/图表，%d 数据指标，%d 有数字但无显式依据，%d 无显式依据"
            % (
                ledger_summary.get("sentences", 0),
                ledger_summary.get("cited", 0),
                ledger_summary.get("metric_linked", 0),
                ledger_summary.get("numeric_unreferenced", 0),
                ledger_summary.get("no_explicit_ref", 0),
            )
        )
    lines += ["", "## 改写", ""]
    rewrite = audit.get("rewrite") or {}
    lines.append("- 接受段落：%d" % int(rewrite.get("changed_blocks") or 0))
    lines.append("- 回退/拒绝段落：%d" % sum(
        1 for item in rewrite.get("records") or [] if item.get("status") == "rejected"
    ))
    lines += ["", "## 阻断项", ""]
    if audit.get("blockers"):
        lines += ["- " + item for item in audit["blockers"]]
    else:
        lines.append("- 无")
    lines += ["", "## 警告", ""]
    if audit.get("warnings"):
        lines += ["- " + item for item in audit["warnings"][:30]]
    else:
        lines.append("- 无")
    if export:
        lines += ["", "## 导出文件", ""]
        for key, value in sorted((export.get("files") or {}).items()):
            lines.append("- %s: `%s`" % (key, value))
        if export.get("warnings"):
            lines += ["", "导出警告："] + ["- " + item for item in export["warnings"]]
    lines += [
        "",
        "## 下一步",
        "",
        "1. 人工检查被拒绝/回退的段落和所有 blockers。",
        "2. 按目标期刊官网最新模板复核 DOCX/LaTeX 的版式、字体、图表尺寸和参考文献。",
        "3. 作者信息、基金、伦理声明和投稿信仍需人工填写。",
        "4. 该包不是同行评审，也不是期刊录用保证。",
        "",
    ]
    return "\n".join(lines)


def run_revision(
    draft_path: Path,
    output_dir: Path,
    data_paths: Optional[Sequence[Path]] = None,
    metrics_path: Optional[Path] = None,
    figures_path: Optional[Path] = None,
    venue: str = "zh_core_journal",
    profile_id: str = "",
    store_path: Optional[str] = None,
    model: Any = None,
    sections: Optional[Sequence[str]] = None,
    formats: Sequence[str] = ("md", "tex", "docx", "pdf"),
    goal: str = "",
    review_comments: Optional[Sequence[str]] = None,
    plan: Optional[Dict[str, Any]] = None,
    auto_plan: bool = False,
) -> Dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        venue_profile = get_venue_profile(venue)
        document = read_draft(Path(draft_path), assets_dir=output / "assets")
        tables = load_data_tables(list(data_paths or []))
        metric_specs = load_metric_specs(metrics_path)
        metrics = compute_metrics(tables, metric_specs)
        metric_replacements = apply_metric_replacements(document, metrics, metric_specs)
        figure_specs = load_figure_specs(figures_path)
        figures = generate_figures(figure_specs, tables, output)
        _insert_figures(document, figures)
    except (RevisionIOError, ValueError) as exc:
        raise RevisionError(str(exc))

    writer_mode = "copy"
    rewrite: Dict[str, Any] = {
        "records": [], "blockers": [], "warnings": [],
        "changed_blocks": 0, "requested_sections": list(sections or []),
    }
    plan_files: Dict[str, str] = {}
    if auto_plan and (profile_id or model is not None):
        from .revision_plan import build_revision_plan, write_revision_plan

        planner_model = model or _gateway_model(profile_id, store_path)
        plan = build_revision_plan(
            Path(draft_path),
            planner_model,
            sections=list(sections or []),
            goal=goal,
            review_comments=review_comments,
        )
        plan_files = write_revision_plan(plan, output)
    if profile_id or model is not None:
        writer = model or _gateway_model(profile_id, store_path)
        writer_mode = "model"
        rewrite = _rewrite_document(
            document, writer, list(sections or []), venue_profile, metrics, goal, review_comments, plan
        )

    plan = {
        "schema_version": REVISION_SCHEMA,
        "created_at": _now(),
        "draft": str(Path(draft_path)),
        "draft_sha256": document.source_sha256,
        "title": document.title,
        "language": document.language,
        "venue": profile_summary(venue_profile),
        "sections": [
            {
                "heading": section.heading,
                "level": section.level,
                "blocks": len(section.blocks),
                "protected": _section_is_protected(section.heading),
                "rewrite": not _skip_section(section.heading),
            }
            for section in document.sections
        ],
        "data_files": [str(path) for path in (data_paths or [])],
        "metric_specs": metric_specs,
        "metrics": [metric.to_dict() for metric in metrics],
        "metric_replacements": metric_replacements,
        "figure_specs": [
            {key: value for key, value in spec.items() if key != "spec"}
            for spec in figure_specs
        ],
        "figures": figures.get("figures") or [],
        "writer_mode": writer_mode,
        "profile_id": profile_id,
        "plan": plan or None,
        "plan_files": plan_files,
        "boundary": BOUNDARY,
    }
    write_json_atomic(output / "revision-plan.json", plan)
    write_json_atomic(output / "revision-diff.json", {
        "schema_version": "revision-diff-0.1",
        "records": rewrite.get("records") or [],
        "boundary": "diff is a review aid; rejected blocks are not applied",
    })
    write_json_atomic(output / "data-profile.json", {
        "schema_version": "revision-data-profile-0.1",
        "tables": profile_tables(tables),
        "boundary": "data profile is descriptive, not a claim",
    })
    write_json_atomic(output / "metric-results.json", {
        "schema_version": "revision-metric-results-0.1",
        "metrics": [metric.to_dict() for metric in metrics],
        "replacements": metric_replacements,
        "boundary": "metrics are recomputed only from user-provided tables and specs",
    })
    write_json_atomic(output / "figure-manifest.json", figures)
    sentence_ledger = _sentence_ledger(document, metrics)
    write_json_atomic(output / "sentence-ledger.json", sentence_ledger)

    export = None
    try:
        export = export_document(document, output / "export", venue=venue, formats=formats)
    except Exception as exc:
        export = {"files": {}, "warnings": ["export failed: %s" % type(exc).__name__]}

    audit = _audit(
        document=document,
        venue=venue_profile,
        metrics=metrics,
        metric_replacements=metric_replacements,
        figures=figures,
        rewrite=rewrite,
        writer_mode=writer_mode,
        export=export,
    )
    write_json_atomic(output / "revision-audit.json", audit)
    revised_json = {
        "schema_version": REVISION_SCHEMA,
        "document": document.to_dict(),
        "audit_status": audit["status"],
        "boundary": BOUNDARY,
    }
    write_json_atomic(output / "revised-manuscript.json", revised_json)
    _write_text(output / "revised-manuscript.md", render_markdown(document))
    if export and (export.get("files") or {}).get("markdown"):
        # Keep the root copy portable and identical to the export Markdown.
        export_markdown = Path(export["files"]["markdown"])
        _write_text(output / "revised-manuscript.md", export_markdown.read_text(encoding="utf-8"))
        export_images = export_markdown.parent / "images"
        if export_images.is_dir():
            shutil.copytree(
                str(export_images),
                str(output / "images"),
                dirs_exist_ok=True,
            )
    _write_text(output / "revision-summary.md", _summary_markdown(document, audit, export))
    return {
        "schema_version": REVISION_SCHEMA,
        "status": audit["status"],
        "title": document.title,
        "output_dir": str(output),
        "draft": str(Path(draft_path)),
        "venue": profile_summary(venue_profile),
        "writer_mode": writer_mode,
        "audit": audit,
        "export": export,
        "files": {
            "plan": str(output / "revision-plan.json"),
            "revised_markdown": str(output / "revised-manuscript.md"),
            "revised_json": str(output / "revised-manuscript.json"),
            "audit": str(output / "revision-audit.json"),
            "diff": str(output / "revision-diff.json"),
            "metrics": str(output / "metric-results.json"),
            "sentence_ledger": str(output / "sentence-ledger.json"),
            "figures": str(output / "figure-manifest.json"),
            "summary": str(output / "revision-summary.md"),
            "export": (export or {}).get("files") or {},
        },
        "boundary": BOUNDARY,
    }


def inspect_revision(
    draft_path: Path,
    output_dir: Path,
    data_paths: Optional[Sequence[Path]] = None,
    metrics_path: Optional[Path] = None,
    figures_path: Optional[Path] = None,
    venue: str = "zh_core_journal",
) -> Dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    try:
        venue_profile = get_venue_profile(venue)
        document = read_draft(Path(draft_path), assets_dir=output / "assets")
        tables = load_data_tables(list(data_paths or []))
        metric_specs = load_metric_specs(metrics_path)
        metrics = compute_metrics(tables, metric_specs)
        figures = generate_figures(load_figure_specs(figures_path), tables, output)
    except (RevisionIOError, ValueError) as exc:
        raise RevisionError(str(exc))
    return {
        "schema_version": REVISION_SCHEMA,
        "status": "inspected",
        "draft": str(Path(draft_path)),
        "title": document.title,
        "language": document.language,
        "venue": profile_summary(venue_profile),
        "sections": [
            {
                "heading": section.heading,
                "level": section.level,
                "blocks": [
                    {"kind": block.kind, "chars": len(block.text)}
                    for block in section.blocks
                ],
                "protected": _section_is_protected(section.heading),
                "rewrite": not _skip_section(section.heading),
            }
            for section in document.sections
        ],
        "data_profile": profile_tables(tables),
        "metrics": [metric.to_dict() for metric in metrics],
        "figures": figures.get("figures") or [],
        "boundary": BOUNDARY,
    }

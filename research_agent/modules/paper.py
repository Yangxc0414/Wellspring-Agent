"""S8–S12 paper scaffold: evidence-bound draft + slots, never result claims."""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..journal_skill_audit import journal_style_brief

from ..contracts import (
    DraftSection,
    ExperimentDesign,
    IdeaCard,
    LiteratureBrief,
    PaperContract,
    PaperSlot,
    Span,
    WritingProfile,
    seed_count,
)
from ..specs import ModuleSpec


class PaperError(RuntimeError):
    pass


@dataclass
class PaperRequest:
    topic: str
    language: str = "zh"
    venue_type: str = "zh_core_journal"
    evidence_refs: List[str] = field(default_factory=list)
    figure_refs: List[str] = field(default_factory=list)
    claim_refs: List[str] = field(default_factory=list)
    result_figure_refs: List[str] = field(default_factory=list)
    protocol_refs: List[str] = field(default_factory=list)
    bibliography_refs: List[str] = field(default_factory=list)
    spans: List[Span] = field(default_factory=list)
    literature_brief: Optional[LiteratureBrief] = None
    synthesis: Optional[Dict[str, Any]] = None
    idea_candidates: List[IdeaCard] = field(default_factory=list)
    design: Optional[ExperimentDesign] = None
    run_summary: Optional[Dict[str, Any]] = None
    claim_statements: List[str] = field(default_factory=list)
    claim_assertions: List[Dict[str, Any]] = field(default_factory=list)
    study_design: Optional[Dict[str, Any]] = None
    study_design_audit: Optional[Dict[str, Any]] = None
    fixture_mode: bool = True


SectionWriter = Callable[[Dict[str, Any]], Optional[Dict[str, str]]]

PROFILES = {
    "zh_core_journal": WritingProfile(
        language="zh", venue_type="zh_core_journal", citation_style="GB/T 7714-2015",
        sections=["摘要", "引言", "相关工作", "方法", "实验设计", "结果", "讨论", "结论"],
    ),
    "en_conference": WritingProfile(
        language="en", venue_type="en_conference", citation_style="venue-specific",
        sections=["Abstract", "Introduction", "Related Work", "Method", "Experimental Setup", "Results", "Discussion", "Conclusion"],
    ),
    "en_journal": WritingProfile(
        language="en", venue_type="en_journal", citation_style="venue-specific",
        sections=["Abstract", "Introduction", "Related Work", "Method", "Results", "Discussion", "Limitations", "Conclusion"],
    ),
    "zh_thesis": WritingProfile(
        language="zh", venue_type="zh_thesis", citation_style="学校模板 / GB/T 7714",
        sections=["摘要", "绪论", "相关工作", "方法", "实验", "讨论", "结论", "参考文献"],
    ),
    "software_journal": WritingProfile(
        language="zh", venue_type="software_journal", citation_style="GB/T 7714-2015",
        sections=["摘要", "引言", "相关工作", "方法", "实验", "讨论", "威胁有效性", "结论"],
    ),
    "computer_journal": WritingProfile(
        language="zh", venue_type="computer_journal", citation_style="GB/T 7714-2015",
        sections=["摘要", "引言", "相关工作", "方法", "实验", "结果", "讨论", "结论"],
    ),
}

WRITER_SECTIONS = ("abstract", "introduction", "related_work", "discussion", "conclusion")
CITATION_RE = re.compile(r"\[([A-Za-z0-9_.:-]+)\]")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _section_kind(label: str) -> str:
    lowered = label.lower()
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


def _clean_text(text: str, limit: int = 180) -> str:
    cleaned = " ".join(str(text).split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit] + "…"


def _display_value(value: str, language: str) -> str:
    if language != "en":
        return value
    return {
        "待人工补全": "needs human input",
        "待补": "pending",
        "无": "none",
    }.get(value, value)


def _display_stopping_rule(value: str, language: str) -> str:
    if language == "en" and "预注册" in value:
        return (
            "Frozen by a human after pre-registration; the primary metric, sample size, "
            "and stopping conditions must not be modified post hoc."
        )
    return value


def _first_ref(brief: Optional[LiteratureBrief], spans: List[Span], source_id: str) -> str:
    for span in spans:
        if span.source_id == source_id:
            return span.span_id
    return source_id


def _display_ref(span: Optional[Span], fallback: str) -> str:
    if span is None:
        return fallback
    return span.span_id + ((" · p.%d" % span.page) if span.page else "")


def _first_span(spans: List[Span], source_id: str) -> Optional[Span]:
    for span in spans:
        if span.source_id == source_id:
            return span
    return None


def _synthesis_theme_lines(request: PaperRequest, zh: bool) -> str:
    matrix = request.synthesis if isinstance(request.synthesis, dict) else {}
    themes = [
        item for item in (matrix.get("themes") or [])
        if isinstance(item, dict)
        and int(item.get("source_count") or 0) >= 2
        and all(str(stance.get("evidence") or "") for stance in (item.get("stances") or []))
    ]
    if not themes:
        return ""
    known_spans = {span.span_id for span in request.spans}
    lines = (
        ["跨来源主题（本 run 全文 span 的词法共现投影，非语义综合；每主题至少 2 篇来源）："]
        if zh else
        ["Cross-source themes (lexical co-occurrence over this run's full-text spans, not semantic synthesis; each theme covers at least 2 sources):"]
    )
    for theme in themes[:5]:
        evidence_refs = []
        for stance in theme.get("stances") or []:
            span_id = str(stance.get("evidence") or "")
            if span_id in known_spans and span_id not in evidence_refs:
                evidence_refs.append(span_id)
        if len(evidence_refs) < 2:
            continue
        label = str(theme.get("name") or "").strip()
        count = int(theme.get("source_count") or 0)
        lines.append(
            "- %s：%d 篇来源共同提及 %s"
            % (label, count, " ".join("[%s]" % ref for ref in evidence_refs[:4]))
            if zh else
            "- %s: co-mentioned by %d sources %s"
            % (label, count, " ".join("[%s]" % ref for ref in evidence_refs[:4]))
        )
    return "\n".join(lines) if len(lines) > 1 else ""


def _source_lines(
    request: PaperRequest,
    language: str,
) -> Tuple[List[str], List[str]]:
    brief = request.literature_brief
    if brief is None or not brief.source_briefs:
        return [], []
    lines: List[str] = []
    refs: List[str] = []
    for source in brief.source_briefs[:8]:
        span = _first_span(request.spans, source.source_id)
        ref = span.span_id if span else _first_ref(brief, request.spans, source.source_id)
        display_ref = _display_ref(span, ref)
        refs.append(ref)
        if language == "zh":
            if source.full_text:
                lines.append(
                    "- 《%s》（%s，%s）：%s [%s]"
                    % (source.title, source.year or "n.d.", source.venue, source.excerpt, display_ref)
                )
            else:
                lines.append(
                    "- 《%s》（%s）：%s（摘要线索；未生成 span，不作为证据）"
                    % (source.title, source.year or "n.d.", source.excerpt)
                )
        else:
            if source.full_text:
                lines.append(
                    "- %s (%s, %s): %s [%s]"
                    % (source.title, source.year or "n.d.", source.venue, source.excerpt, display_ref)
                )
            else:
                lines.append(
                    "- %s (%s): %s (abstract-only clue; no span, not evidence)"
                    % (source.title, source.year or "n.d.", source.excerpt)
                )
    return lines, refs


def _gap_lines(request: PaperRequest, language: str) -> List[str]:
    brief = request.literature_brief
    gaps: List[str] = []
    if brief is not None:
        gaps.extend(brief.gaps)
    if request.design is not None:
        for warning in request.design.warnings:
            if warning.lower().startswith(("missing", "fewer than 3 seeds", "no negative/positive control")):
                gaps.append(warning)
    gaps.extend("novelty_unverified" for _ in [0] if request.idea_candidates)
    seen = set()
    unique = []
    for gap in gaps:
        if gap not in seen:
            seen.add(gap)
            unique.append(gap)
    if not unique:
        return []
    if language == "zh":
        return ["- %s" % gap for gap in unique[:8]]
    return ["- %s" % gap for gap in unique[:8]]


def _study_design_text(study: Dict[str, Any], audit: Optional[Dict[str, Any]], zh: bool) -> str:
    """Render the pre-registered study design; the run design is only a protocol validation."""
    def text(value: Any) -> str:
        return " ".join(str(value or "").split())

    level = str(((audit or {}).get("ccfa") or {}).get("level") or "not audited")
    status = str((audit or {}).get("status") or "not audited")
    lines = [
        ("研究设计（预注册；CCF-A 披露检查：%s / %s）" % (status, level))
        if zh else
        ("Study design (pre-registered; CCF-A disclosure audit: %s / %s)" % (status, level)),
        "",
        ("问题：%s" if zh else "Question: %s") % text(study.get("question")),
        ("假设：%s" if zh else "Hypothesis: %s") % text(study.get("hypothesis")),
    ]
    claims = [item for item in (study.get("claims") or []) if isinstance(item, dict)]
    for index, claim in enumerate(claims, start=1):
        # Parentheses, not square brackets: the manuscript builder treats [token] as a citation
        # and would rewrite the claim type as an unresolved reference.
        lines.append(
            ("主张 %d（%s）：%s；证据：%s" if zh else "Claim %d (%s): %s; evidence: %s")
            % (index, text(claim.get("type")), text(claim.get("claim")), text(claim.get("evidence")))
        )
    datasets = [item for item in (study.get("datasets") or []) if isinstance(item, dict)]
    for index, dataset in enumerate(datasets, start=1):
        lines.append(
            ("数据 %d：%s（%s，%s）；切分：%s；泄漏检查：%s；许可：%s" if zh
             else "Dataset %d: %s (%s, %s); splits: %s; leakage: %s; license: %s")
            % (
                index,
                text(dataset.get("name")),
                text(dataset.get("role")),
                text(dataset.get("data_status")),
                text(dataset.get("splits")),
                text(dataset.get("leakage_checks")),
                text(dataset.get("license")),
            )
        )
    baselines = [item for item in (study.get("baselines") or []) if isinstance(item, dict)]
    for index, baseline in enumerate(baselines, start=1):
        lines.append(
            ("基线 %d：%s（%s；调参：%s；算力：%s；匹配：%s）" if zh
             else "Baseline %d: %s (%s; tuning: %s; compute: %s; matched: %s)")
            % (
                index,
                text(baseline.get("name")),
                text(baseline.get("implementation")),
                text(baseline.get("tuning")),
                text(baseline.get("compute")),
                "yes" if baseline.get("compute_matched") else "no",
            )
        )
    ablations = [item for item in (study.get("ablations") or []) if isinstance(item, dict)]
    for index, ablation in enumerate(ablations, start=1):
        lines.append(
            ("消融 %d：%s（机制：%s；单一变量：%s）" if zh
             else "Ablation %d: %s (mechanism: %s; single change: %s)")
            % (
                index,
                text(ablation.get("name")),
                text(ablation.get("mechanism")),
                "yes" if ablation.get("single_change") else "no",
            )
        )
    robustness = [item for item in (study.get("robustness") or []) if isinstance(item, dict)]
    if robustness:
        lines.append(
            ("稳健性：" if zh else "Robustness: ")
            + "；".join(
                "%s: %s" % (text(item.get("axis")), text(item.get("plan")))
                for item in robustness
            )
        )
    compute = study.get("compute") if isinstance(study.get("compute"), dict) else {}
    if compute:
        lines.append(
            ("计算：硬件 %s；训练/老化时间 %s；推理/测量成本 %s；公平性 %s" if zh
             else "Compute: hardware %s; training/ageing time %s; inference/measurement cost %s; fairness %s")
            % (
                text(compute.get("hardware")),
                text(compute.get("training_time")),
                text(compute.get("inference_cost")),
                text(compute.get("fairness")),
            )
        )
    stats = study.get("statistics") if isinstance(study.get("statistics"), dict) else {}
    if stats:
        power = stats.get("power_analysis") if isinstance(stats.get("power_analysis"), dict) else {}
        lines.append(
            ("统计：seeds %s；效应量 %s；区间 %s；多重比较 %s；缺失数据 %s；功效 %s" if zh
             else "Statistics: seeds %s; effect %s; CI %s; multiplicity %s; missing data %s; power %s")
            % (
                text(stats.get("seeds")),
                text(stats.get("effect_size")),
                text(stats.get("confidence_interval")),
                text(stats.get("multiplicity")),
                text(stats.get("missing_data")),
                "%s / sd %s / alpha %s / power %s / n %s"
                % (
                    text(power.get("effect_size")),
                    text(power.get("sd")),
                    text(power.get("alpha")),
                    text(power.get("power")),
                    text(power.get("n_per_arm")),
                )
                if power else "not declared",
            )
        )
    for key, label in (
        ("negative_results", "负结果计划" if zh else "Negative results"),
        ("limitations", "局限" if zh else "Limitations"),
    ):
        if text(study.get(key)):
            lines.append(("%s：%s" if zh else "%s: %s") % (label, text(study.get(key))))
    return "\n\n".join(lines)


def _deterministic_draft(
    request: PaperRequest,
    profile: WritingProfile,
) -> List[DraftSection]:
    zh = profile.language == "zh"
    source_lines, source_refs = _source_lines(request, profile.language)
    gap_lines = _gap_lines(request, profile.language)
    brief = request.literature_brief
    span_count = len(request.spans)
    source_count = len(brief.source_briefs) if brief else 0
    full_text_count = (
        sum(1 for item in brief.source_briefs if item.full_text) if brief else 0
    )
    fixture_prefix = (
        "【演示数据】以下来源为 fixture，仅用于流程验证，不得作为科学证据。\n\n"
        if request.fixture_mode and zh else
        "[FIXTURE DATA] Sources below are synthetic and must not be cited as evidence.\n\n"
        if request.fixture_mode else ""
    )
    design = request.design
    run_summary = request.run_summary or {}
    run_status = str(run_summary.get("status") or "")
    has_setup_section = any(_section_kind(label) == "setup" for label in profile.sections)
    draft: List[DraftSection] = []

    for label in profile.sections:
        kind = _section_kind(label)
        if kind == "references":
            continue
        text = ""
        status = "draft"
        refs: List[str] = []
        if kind == "abstract":
            if zh:
                text = (
                    "目的：围绕「%s」评估可复核的研究证据与当前结论边界。"
                    "方法：检索并读取 %d 篇来源（其中 %d 篇有全文），定位 %d 条句级 span，"
                    "仅将可定位证据与人工签署的 claim 纳入论证。"
                    % (request.topic, source_count, full_text_count, span_count)
                )
                if request.claim_refs:
                    text += (
                        "结果：结果部分仅引用已由作者签署的 claim：%s；本工作稿不复核其数值。"
                        % "、".join(request.claim_refs)
                    )
                else:
                    text += "结果：尚无已签 claim，因此不报告指标数值，也不形成效果性结论。"
                text += (
                    "结论：本稿给出当前证据边界、覆盖缺口与后续实验/写作槽位；"
                    "结论性表述需在 claim 签署后补全，未验证假设与覆盖缺口在讨论部分列出。"
                )
            else:
                text = (
                    "This draft examines %s through locatable evidence. "
                    "It reads %d sources (%d with full text) and keeps %d sentence-level spans; "
                    "all conclusions are limited to those spans and any human-signed claims."
                    % (request.topic, source_count, full_text_count, span_count)
                )
                if request.claim_refs:
                    text += " The results section cites only signed claims: %s; this draft does not re-verify their values." % ", ".join(request.claim_refs)
                else:
                    text += " No claim is signed, so no result numbers or efficacy conclusion are reported."
            refs = source_refs[:3]
            status = "draft_evidence" if source_refs else "pending_evidence"
        elif kind == "introduction":
            abstract_only = (
                sum(1 for item in brief.source_briefs if not item.full_text) if brief else 0
            )
            if zh:
                text = "研究问题：%s\n\n" % request.topic
                if brief is not None:
                    text += (
                        "本次读取 %d 篇来源（全文 %d / 摘要-only %d），保留 %d 条可定位 span。\n\n"
                        % (source_count, full_text_count, abstract_only, span_count)
                    )
                text += (
                    "本稿先固定证据边界：摘要-only 来源只作线索，不能被升级为证据；"
                    "实验设计与结果槽在人工门禁通过前保持待定。"
                )
                if gap_lines:
                    text += "\n\n当前识别到的覆盖缺口：\n" + "\n".join(gap_lines[:4])
            else:
                text = "Research question: %s\n\n" % request.topic
                if brief is not None:
                    text += (
                        "This run reads %d sources (%d full text, %d abstract-only) and keeps %d "
                        "locatable spans.\n\n"
                        % (source_count, full_text_count, abstract_only, span_count)
                    )
                text += (
                    "The draft fixes its evidence boundary first: abstract-only records remain clues, "
                    "and design/result slots stay pending until the human gates are passed."
                )
                if gap_lines:
                    text += "\n\nCurrent coverage gaps:\n" + "\n".join(gap_lines[:4])
            refs = source_refs[:4]
            status = "draft_evidence" if source_refs else "pending_evidence"
        elif kind == "related_work":
            if source_lines:
                header = (
                    "以下来源仅按检索与全文读取结果排列，不代表新颖性判断。\n\n"
                    if zh else
                    "Sources are ordered by retrieval and full-text reading, not by novelty.\n\n"
                )
                text = header + "\n".join(source_lines)
                theme_lines = _synthesis_theme_lines(request, zh)
                if theme_lines:
                    text = text + "\n\n" + theme_lines
                status = "draft_evidence"
            else:
                text = "尚无可用全文来源；相关工作槽保持待补。" if zh else "No full-text source is available; related work remains pending."
                status = "pending_evidence"
            refs = source_refs
        elif kind == "method":
            refs = list(request.protocol_refs)
            if design is None:
                text = "实验设计尚未达到可冻结条件；方法槽保持待补。" if zh else "The design is not ready to freeze; the method slot remains pending."
                status = "pending_evidence"
            elif has_setup_section:
                if zh:
                    text = (
                        "方法围绕 S2–S3 的候选假设展开，并在预注册约束下与 baseline、主指标和对照一起冻结。"
                        "具体参数、seeds 与停止规则见“实验设计”一节；本稿不在此处引入未给出的指标结果。"
                    )
                else:
                    text = (
                        "The method operationalizes the S2–S3 candidate under pre-registration constraints, "
                        "together with the baseline, primary metric, and controls. Concrete parameters, seeds, "
                        "and stopping rules appear in the Experimental Setup section; no unprovided metric result is introduced here."
                    )
                status = "draft_pending_g2" if design.status != "ready_for_g2" else "bound_protocol"
            else:
                if zh:
                    text = (
                        "研究假设（草案）：%s\n\n对照：%s\n\n主指标：%s\n\n控制：%s\n\n"
                        "seeds：%d；预算：%s\n\n停止规则：%s"
                        % (
                            design.hypothesis,
                            _display_value(design.baseline, profile.language),
                            _display_value(design.primary_metric, profile.language),
                            "、".join(design.controls) or "待补",
                            seed_count(design.seeds),
                            _display_value(design.budget or "待补", profile.language),
                            _display_stopping_rule(design.stopping_rule, profile.language),
                        )
                    )
                    if design.status != "ready_for_g2":
                        text += "\n\n注意：该设计仍缺预注册字段，G2 尚未通过，以上仅是方法草案。"
                else:
                    text = (
                        "Hypothesis (draft): %s\n\nBaseline: %s\n\nPrimary metric: %s\n\nControls: %s\n\n"
                        "Seeds: %d; budget: %s\n\nStopping rule: %s"
                        % (
                            design.hypothesis,
                            _display_value(design.baseline, profile.language),
                            _display_value(design.primary_metric, profile.language),
                            ", ".join(design.controls) or "pending",
                            seed_count(design.seeds),
                            _display_value(design.budget or "pending", profile.language),
                            _display_stopping_rule(design.stopping_rule, profile.language),
                        )
                    )
                    if design.status != "ready_for_g2":
                        text += "\n\nThe design still lacks pre-registration fields; G2 is not passed and the text above is a method draft only."
                status = "bound_protocol" if design.status == "ready_for_g2" else "draft_pending_g2"
        elif kind == "setup":
            refs = list(request.protocol_refs)
            if design is not None:
                if zh:
                    text = (
                        "研究假设（草案）：%s\n\n对照：%s\n\n主指标：%s\n\n控制：%s\n\n"
                        "seeds：%d；预算：%s\n\n停止规则：%s"
                        % (
                            design.hypothesis,
                            _display_value(design.baseline, profile.language),
                            _display_value(design.primary_metric, profile.language),
                            "、".join(design.controls) or "待补",
                            seed_count(design.seeds),
                            _display_value(design.budget or "待补", profile.language),
                            _display_stopping_rule(design.stopping_rule, profile.language),
                        )
                    )
                    if design.status != "ready_for_g2":
                        text += "\n\n注意：该设计仍缺预注册字段，G2 尚未通过，以上仅是设计草案。"
                else:
                    text = (
                        "Hypothesis (draft): %s\n\nBaseline: %s\n\nPrimary metric: %s\n\nControls: %s\n\n"
                        "Seeds: %d; budget: %s\n\nStopping rule: %s"
                        % (
                            design.hypothesis,
                            _display_value(design.baseline, profile.language),
                            _display_value(design.primary_metric, profile.language),
                            ", ".join(design.controls) or "pending",
                            seed_count(design.seeds),
                            _display_value(design.budget or "pending", profile.language),
                            _display_stopping_rule(design.stopping_rule, profile.language),
                        )
                    )
                    if design.status != "ready_for_g2":
                        text += "\n\nThe design still lacks pre-registration fields; G2 is not passed and the text above is a design draft only."
                status = "bound_protocol" if design.status == "ready_for_g2" else "draft_pending_g2"
            else:
                text = "实验设计尚未达到可冻结条件；该槽位保持待补。" if zh else "The design is not ready to freeze; this slot remains pending."
                status = "pending_evidence"
        elif kind == "results":
            if request.claim_statements:
                assertion_lines = []
                for item in request.claim_assertions:
                    if str(item.get("status") or "") != "pass":
                        continue
                    observed = item.get("observed")
                    expected = item.get("value", item.get("expected"))
                    assertion_lines.append(
                        "- %s %s %s (observed=%s, tolerance=%s)"
                        % (
                            item.get("metric") or "metric",
                            item.get("comparator") or ">=",
                            expected,
                            round(observed, 6) if isinstance(observed, (int, float)) else observed,
                            item.get("tolerance", 0),
                        )
                    )
                if zh:
                    text = (
                        "结果仅引用已由作者签署的 claim：\n\n"
                        + "\n".join("- %s" % item for item in request.claim_statements)
                    )
                    if assertion_lines:
                        text += "\n\n已验证数值（来自 metrics + 人签 claim）：\n" + "\n".join(assertion_lines)
                    text += "\n\n本工作稿不重新计算 EA 数值；引用前需在 Closure 中复核 claim/EA/图 manifest 的哈希绑定。"
                else:
                    text = (
                        "Results cite only author-signed claims:\n\n"
                        + "\n".join("- %s" % item for item in request.claim_statements)
                    )
                    if assertion_lines:
                        text += "\n\nVerified values (metrics + signed claim):\n" + "\n".join(assertion_lines)
                    text += "\n\nThis draft does not recompute EA values; Closure must re-check claim/EA/figure hashes before export."
                refs = list(request.claim_refs)
                status = "bound_claim"
            elif request.claim_refs:
                text = (
                    "结果槽已引用 claim ID（%s），但未提供人签陈述；按边界不写入任何数值。"
                    % "、".join(request.claim_refs) if zh else
                    "The result slot references claim IDs (%s) but no signed statement was supplied; no numbers are written."
                    % ", ".join(request.claim_refs)
                )
                refs = list(request.claim_refs)
                status = "bound_claim"
            elif run_status == "completed":
                text = (
                    "已完成本地 RunCapsule（%s），但在 claim 人签前不把任何指标数字写入正文；结果槽保持 pending_evidence。"
                    % (run_summary.get("run_id") or "run")
                    if zh else
                    "A local RunCapsule (%s) completed, but no metric is written before a claim is signed; the result slot stays pending_evidence."
                    % (run_summary.get("run_id") or "run")
                )
                status = "pending_evidence"
            else:
                text = "尚无 EA/人签 claim；结果槽保持 pending_evidence，不写数字。" if zh else "No EA or signed claim exists; the result slot stays pending_evidence with no numbers."
                status = "pending_evidence"
        elif kind == "discussion":
            if zh:
                text = (
                    "当前证据支持的是候选假设与实验设计，而不是效果性结论。"
                    "novelty 尚未核验，覆盖不足与来源限制必须与结果一起报告。"
                )
                if gap_lines:
                    text += "\n\n需要保留的缺口：\n" + "\n".join(gap_lines)
                if request.idea_candidates:
                    text += "\n\n候选否证条件：" + "；".join(
                        "%s：%s" % (card.idea_id, card.falsification)
                        for card in request.idea_candidates[:3]
                    )
            else:
                text = (
                    "The current evidence supports candidate hypotheses and a design, not an efficacy conclusion. "
                    "Novelty is unverified, and coverage/source limitations must be reported with any results."
                )
                if gap_lines:
                    text += "\n\nGaps to preserve:\n" + "\n".join(gap_lines)
                if request.idea_candidates:
                    text += "\n\nFalsification conditions: " + "; ".join(
                        "%s: %s" % (card.idea_id, card.falsification)
                        for card in request.idea_candidates[:3]
                    )
            refs = source_refs[:2]
            status = "draft_evidence" if refs else "draft"
        elif kind == "limitation":
            if zh:
                text = "局限：来源覆盖、全文可得性与人工签署状态都可能限制结论；未签 claim 前不得把结果外推。"
                if gap_lines:
                    text += "\n\n" + "\n".join(gap_lines)
            else:
                text = "Limitations: source coverage, full-text availability, and unsigned claims bound the conclusions; do not extrapolate before a claim is signed."
                if gap_lines:
                    text += "\n\n" + "\n".join(gap_lines)
            status = "draft"
        elif kind == "conclusion":
            if request.claim_statements:
                text = (
                    "在已签 claim 的范围内，本文给出可审计的结果；超出该范围的推断保持未验证。"
                    if zh else
                    "Within the signed claim scope, this draft reports auditable results; inferences beyond that scope remain unverified."
                )
            else:
                text = (
                    "由于结果槽尚未绑定人签 claim，本文只给出研究设计、证据覆盖与待验证假设，不给出效果性结论。"
                    if zh else
                    "Because the result slot has no signed claim, this draft reports only design, evidence coverage, and hypotheses; it makes no efficacy conclusion."
                )
            status = "bound_claim" if request.claim_statements else "pending_evidence"
            refs = list(request.claim_refs)
        else:
            continue
        if request.fixture_mode and kind == "related_work":
            text = fixture_prefix + text
        draft.append(DraftSection(section=label, text=text.strip(), status=status, evidence_refs=refs))
    return draft


def _allowed_numbers(request: PaperRequest) -> set:
    parts: List[str] = [request.topic]
    if request.literature_brief is not None:
        parts.append(request.literature_brief.summary)
        for item in request.literature_brief.source_briefs:
            parts.append("%s %s %s" % (item.year or "", item.title, item.excerpt))
    for span in request.spans[:200]:
        parts.append(span.text)
    if request.design is not None:
        parts.append(
            "%s %s %s %s %s"
            % (
                request.design.seeds,
                request.design.primary_metric,
                request.design.budget,
                request.design.stopping_rule,
                " ".join(request.design.controls),
            )
        )
    for statement in request.claim_statements:
        parts.append(statement)
    return set(NUMBER_RE.findall(" ".join(parts)))


def _validate_writer_sections(
    request: PaperRequest,
    raw: Dict[str, str],
    allowed_refs: set,
) -> Tuple[Dict[str, str], List[str]]:
    accepted: Dict[str, str] = {}
    rejected: List[str] = []
    allowed_numbers = _allowed_numbers(request)
    for key, value in raw.items():
        normalized = str(key).strip().lower().replace(" ", "_").replace("-", "_")
        if normalized not in WRITER_SECTIONS:
            rejected.append("%s:not_writer_section" % key)
            continue
        text = str(value or "").strip()
        if len(text) < 80 or len(text) > 4000:
            rejected.append("%s:length" % key)
            continue
        if text.startswith("#") or "\n## " in text:
            rejected.append("%s:structure" % key)
            continue
        citations = CITATION_RE.findall(text)
        if any(citation not in allowed_refs for citation in citations):
            rejected.append("%s:unknown_citation" % key)
            continue
        if normalized in ("introduction", "related_work") and not citations:
            rejected.append("%s:missing_citation" % key)
            continue
        # Span ids carry digits (ARXIV-2609.19526-S01-03), so citations are removed before the
        # number guard runs: otherwise every grounded section is rejected as an invented result.
        prose = CITATION_RE.sub(" ", text)
        unknown_numbers = [
            number for number in NUMBER_RE.findall(prose)
            if number not in allowed_numbers
        ]
        if unknown_numbers:
            rejected.append("%s:ungrounded_number" % key)
            continue
        accepted[normalized] = text
    return accepted, rejected


# How many spans the writer is shown; the citable set is exactly what is shown, so this also caps
# what a model citation may point at.
MAX_WRITER_EVIDENCE_SPANS = 40


def citable_refs(request: PaperRequest, language: str) -> set:
    """The only refs a model writer may cite: what its prompt actually presented.

    Span-level grounding is the point of the writer contract, so a ref to a span that exists in the
    pack but was never shown is an ungrounded citation even though it resolves. The source-card half
    of the rule ("span 或来源卡") is kept, but likewise limited to the cards listed in the payload.
    """
    _, shown_source_refs = _source_lines(request, language)
    return {
        span.span_id for span in request.spans[:MAX_WRITER_EVIDENCE_SPANS]
    } | set(shown_source_refs)


def _writer_payload(
    request: PaperRequest,
    profile: WritingProfile,
    draft: List[DraftSection],
) -> Dict[str, Any]:
    source_lines, _ = _source_lines(request, profile.language)
    sections = []
    for item in draft:
        kind = _section_kind(item.section)
        if kind in WRITER_SECTIONS:
            sections.append({"key": kind, "label": item.section})
    return {
        "topic": request.topic,
        "language": profile.language,
        "venue_type": profile.venue_type,
        "sections": sections,
        "allowed_evidence": [
            {"ref": span.span_id, "source": span.source_id, "section": span.section, "text": _clean_text(span.text, 220)}
            for span in request.spans[:MAX_WRITER_EVIDENCE_SPANS]
        ],
        "source_notes": source_lines,
        "journal_style": journal_style_brief(profile.venue_type),
        "coverage_gaps": _gap_lines(request, profile.language),
        "claims": list(request.claim_statements),
        "rules": [
            "Only write the sections listed in sections; keys must be the given key values.",
            "Do not invent evidence, citations, numbers, or claims.",
            "Every citation must be an existing span ref in square brackets, e.g. [FX-001-S01-01].",
            "Do not write result numbers; results remain outside the model writer.",
            "For a Chinese abstract, use the 目的/方法/结果/结论 structure without inventing numbers.",
            "Avoid unsupported 首次/突破/显著/最优 and boilerplate 值得注意的是/综上所述.",
            "Introduction and related work need at least one allowed citation per paragraph.",
            "Return strict JSON object: {key: prose}.",
        ],
        "allowed_refs": sorted(citable_refs(request, profile.language)),
    }


def render_paper_markdown(paper: Any) -> str:
    is_dict = isinstance(paper, dict)
    title = paper.get("title", "") if is_dict else paper.title
    profile = paper.get("profile", {}) if is_dict else paper.profile
    if is_dict:
        venue = profile.get("venue_type", "")
        citation = profile.get("citation_style", "")
    else:
        venue = profile.venue_type
        citation = profile.citation_style
    writer_mode = paper.get("writer_mode", "deterministic") if is_dict else paper.writer_mode
    status = paper.get("status", "") if is_dict else paper.status
    draft = paper.get("draft", []) if is_dict else paper.draft
    slots = paper.get("slots", []) if is_dict else paper.slots
    warnings = paper.get("warnings", []) if is_dict else paper.warnings
    lines = ["# %s" % title, ""]
    lines.append("> venue=%s · citation=%s · writer=%s · status=%s" % (
        venue, citation, writer_mode, status,
    ))
    lines.append("")
    for section in draft:
        if is_dict:
            label = section.get("section", "")
            text = section.get("text", "")
        else:
            label = section.section
            text = section.text
        lines.append("## %s" % label)
        lines.append("")
        lines.append(text)
        lines.append("")
    profile_language = profile.get("language", "zh") if is_dict else profile.language
    lines.append("## Slot status" if profile_language == "en" else "## 槽位状态")
    lines.append("")
    for slot in slots:
        if is_dict:
            lines.append(
                "- `%s` · %s · %s"
                % (slot.get("slot_id", ""), slot.get("status", ""), slot.get("required_evidence", ""))
            )
        else:
            lines.append("- `%s` · %s · %s" % (slot.slot_id, slot.status, slot.required_evidence))
    if warnings:
        lines.append("")
        lines.append("## Boundaries and warnings" if profile_language == "en" else "## 边界与警告")
        lines.append("")
        for warning in warnings:
            lines.append("- %s" % warning)
    return "\n".join(lines).rstrip() + "\n"


class PaperAgent:
    module_id = "paper"

    def __init__(self, spec: ModuleSpec, section_writer: Optional[SectionWriter] = None):
        if spec.id != self.module_id:
            raise PaperError("spec id must be 'paper'")
        self.spec = spec
        self.section_writer = section_writer

    def run(self, request: PaperRequest) -> PaperContract:
        if self.spec.status in ("revoked", "deprecated"):
            raise PaperError("module spec status is %s; refusing to run" % self.spec.status)
        if not request.topic.strip():
            raise PaperError("topic is required")
        profile = PROFILES.get(request.venue_type)
        if profile is None:
            raise PaperError("unknown venue_type: " + request.venue_type)
        if request.language not in ("zh", "en"):
            raise PaperError("language must be zh or en")
        if profile.language != request.language:
            raise PaperError(
                "language/venue mismatch: %s expects %s, got %s"
                % (request.venue_type, profile.language, request.language)
            )
        slots = [
            PaperSlot("method.protocol", "方法", "G2 Protocol / DesignCard / TaskSpec"),
            PaperSlot("result.primary", "结果", "EA + supported Claim + MetricRecord"),
            PaperSlot("result.figure", "结果", "FigureManifest + Figure data / run data"),
            PaperSlot("limitation", "讨论", "EvidenceCard scope / validity threats"),
            PaperSlot("citation.related", "相关工作", "verified bibliography (DOI/Crossref)"),
        ]
        warnings = [
            "draft is evidence-bound; no result claims or result numbers are generated",
            "WritingProfile=%s; citation_style=%s" % (profile.venue_type, profile.citation_style),
            "schematic figure is not a result figure; do not bind it to result.figure without data",
        ]
        if not request.evidence_refs:
            warnings.append("no evidence_refs supplied; result slots cannot be filled")
        if request.claim_refs:
            for slot in slots:
                if slot.slot_id == "result.primary":
                    slot.status = "bound_claim"
            warnings.append(
                "result.primary references human-signed claim IDs; writer does not re-verify EA/scope"
            )
            warnings.append("result.primary=bound_claim; other slots pending; export/Closure blocked")
        else:
            warnings.append("all result slots are pending_evidence; export/Closure remains blocked")
        if request.protocol_refs:
            for slot in slots:
                if slot.slot_id == "method.protocol":
                    slot.status = "bound_protocol"
                if slot.slot_id == "limitation":
                    slot.status = "bound_scope"
            warnings.append("protocol/limitation reference human-signed ProtocolCard; writer does not re-verify")
        if request.bibliography_refs:
            for slot in slots:
                if slot.slot_id == "citation.related":
                    slot.status = "bound_bibliography"
            warnings.append("citation.related references frozen DataCite metadata; not peer review")
        if request.result_figure_refs:
            for slot in slots:
                if slot.slot_id == "result.figure":
                    slot.status = "bound_figure"
            warnings.append("result.figure references data-backed FigureManifest; writer does not re-verify data")
        if request.figure_refs:
            warnings.append("figure_refs are schematic; not bound to result.figure")

        draft = _deterministic_draft(request, profile)
        if request.study_design:
            # The study design is the scientific design; the local S5 run design stays a
            # protocol-validation arm and must not be rendered as the study's setup.
            study_text = _study_design_text(
                request.study_design, request.study_design_audit, profile.language == "zh"
            )
            audit_status = str((request.study_design_audit or {}).get("status") or "")
            for item in draft:
                if _section_kind(item.section) == "setup":
                    item.text = study_text
                    item.status = (
                        "bound_protocol" if audit_status == "ready_for_g2" else "draft_pending_g2"
                    )
            warnings.append(
                "study design supplied; the local run remains a protocol-validation arm"
            )
        if request.run_summary:
            # The S5 run is a local protocol validation, not the study's scientific design.
            # Without this label a reader sees an unrelated dataset's metric presented as the
            # paper's design and result.
            zh = profile.language == "zh"
            setup_prefix = (
                "本地协议验证设计（本 run 实际执行的设计；不是本研究的科学设计，"
                "研究设计仍需领域模型或人工给出）。\n\n"
                if zh else
                "Local protocol-validation design (the design this run executed; not the "
                "study's scientific design, which still needs a domain model or a human).\n\n"
            )
            results_prefix = (
                "以下 claim 来自本地协议验证 run，只说明本地协议的可复现性，"
                "不是本研究的科学结论。\n\n"
                if zh else
                "The claims below come from the local protocol-validation run; they speak to "
                "local reproducibility, not to the study's scientific question.\n\n"
            )
            for item in draft:
                kind = _section_kind(item.section)
                if kind == "setup" and not request.study_design:
                    item.text = setup_prefix + item.text
                elif kind == "results":
                    item.text = results_prefix + item.text
        writer_mode = "deterministic"
        if self.section_writer is not None:
            allowed_refs = citable_refs(request, profile.language)
            try:
                raw = self.section_writer(_writer_payload(request, profile, draft))
            except Exception as exc:  # model failure must never break the draft
                from ..models import ModelRequiredError

                if isinstance(exc, ModelRequiredError):
                    raise
                raw = None
                warnings.append("section writer failed (%s); deterministic draft kept" % type(exc).__name__)
            if isinstance(raw, dict):
                accepted, rejected = _validate_writer_sections(request, raw, allowed_refs)
                if accepted:
                    by_kind = {_section_kind(item.section): item for item in draft}
                    for key, text in accepted.items():
                        item = by_kind.get(key)
                        if item is not None:
                            item.text = text
                            item.status = "model_draft"
                    writer_mode = "model"
                    warnings.append(
                        "section writer produced %d section(s); results/method remained deterministic"
                        % len(accepted)
                    )
                if rejected:
                    warnings.append("section writer rejected: " + ", ".join(sorted(rejected)[:6]))
                if not accepted:
                    writer_mode = "model_rejected"
            elif raw is not None:
                warnings.append("section writer returned non-object; deterministic draft kept")

        if request.fixture_mode:
            warnings.append("fixture sources are synthetic; draft is a workflow demo, not citable evidence")

        return PaperContract(
            title=(
                "Working draft: %s" % request.topic.strip()
                if profile.language == "en"
                else "工作稿：%s" % request.topic.strip()
            ),
            profile=profile,
            sections=list(profile.sections),
            slots=slots,
            claims=list(request.claim_refs),
            status="needs_evidence",
            warnings=warnings,
            draft=draft,
            writer_mode=writer_mode,
        )

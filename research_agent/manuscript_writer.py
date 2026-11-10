"""Generate a first Chinese review/position or empirical manuscript.

The writer receives only the compact writing pack and innovation review. For an
experiment pack (article_type=reproduction) it may report only signed-claim and
verified per-method result numbers; for a review pack it stays qualitative. Its
output is immediately checked by the deterministic manuscript audit. If the
audit blocks the draft, the writer gets one repair chance with the blockers.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .journal_skill_audit import journal_style_brief
from .writing_audit import audit_manuscript
from .writing_pack import (
    LENGTH_TARGETS,
    build_writing_pack,
    ensure_pack_marker,
    load_writing_pack,
)

MAX_PROMPT_CHARS = 36000


class ManuscriptWriterError(ValueError):
    pass


def _clean(value: Any, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit else text


def default_writer_model() -> Any:
    """Gateway binding first: a keyless host_agent profile needs no external API key."""
    from .adapters.research_models import default_model_for

    model, note = default_model_for("paper", purpose="S8 review/position draft")
    if model is None:
        raise ManuscriptWriterError(note)
    return model


def _offline_draft(pack: Dict[str, Any]) -> str:
    """Deterministic test-only draft from a signed writing pack."""
    references = [
        str(item.get("ref_id"))
        for item in ((pack.get("literature") or {}).get("references") or [])
        if isinstance(item, dict) and item.get("ref_id")
    ]
    refs = references or ["REF-01"]
    first, second, third = (refs * 3)[:3]
    first_cite = "[%s]" % first
    second_cite = "[%s]" % second
    third_cite = "[%s]" % third
    contract = pack.get("writing_contract") or {}
    package = pack.get("experiment_package") or {}
    figure = package.get("figure") or {}
    method_figure = package.get("method_figure") or {}
    table = package.get("results_table") or ""
    allowed = [str(item) for item in (contract.get("allowed_result_numbers") or [])]
    result_value = allowed[0] if allowed else ""
    result = (
        "已签 claim 报告的主指标观测值为 %s；该数字来自签名 claim 的 allowed numbers，"
        "正文不重新计算或外推。 %s"
        % (result_value, "图 1 给出结果图。" if figure else "")
    )
    if not result_value:
        result = "已签 claim 的具体数值只在 claim assertions 中；正文不复述未核验数字。"
    method = "本文使用统一协议、固定数据划分和多个随机种子进行比较。 %s" % third_cite
    if method_figure:
        method += " 图 2 给出方法示意图。"
    if table:
        result += " 表 1 给出逐方法汇总。"
    title = str(
        (pack.get("task") or {}).get("goal")
        or (pack.get("experiment_design") or {}).get("hypothesis")
        or "实证研究"
    )
    abstract = (
        "目的：在可审计协议下比较基线方法与候选方法。"
        "方法：使用写作包中的全文来源、选中 span、预注册设计和已签实验 claim。"
        "结果：仅报告签名 claim 允许的数值，并保留引用与 artifact 边界。"
        "结论：该工作稿用于本地证据链验证，不替代同行评审，也不声称可投稿。"
    )
    reference_lines = "\n".join(
        "%d. %s" % (index + 1, ref) for index, ref in enumerate(refs)
    )
    return (
        "# %s\n\n"
        "## 摘要\n\n%s\n\n"
        "## 引言\n\n本文研究可复现的实证评估问题 %s。\n\n"
        "## 相关工作\n\n已有研究覆盖了相关评估方法与证据边界 %s。\n\n"
        "## 方法\n\n%s\n\n"
        "## 实验\n\n实验使用固定数据划分、多个随机种子，并由本地审批后执行 %s。\n\n"
        "## 结果\n\n%s %s\n\n"
        "## 讨论\n\n结果仍需在更多数据集和独立环境中复核 %s。\n\n"
        "## 结论\n\n本文给出一个可审计的实证工作稿；结论只覆盖当前 pack 与 claim 的 scope %s。\n\n"
        "## 参考文献\n\n%s\n"
    ) % (
        title, abstract, first_cite, second_cite, method, first_cite,
        result, second_cite, third_cite, first_cite, reference_lines,
    )

def _experiment_context(pack: Dict[str, Any]) -> List[str]:
    design = pack.get("experiment_design") or {}
    package = pack.get("experiment_package") or {}
    if not design and not package:
        return []
    spec = package.get("spec") or {}
    package_design = spec.get("design") or {}
    data = spec.get("data") or {}
    capsule = (pack.get("run") or {}).get("capsule") or {}
    signed = (pack.get("claim") or {}).get("signed_claim") or {}
    contract = pack.get("writing_contract") or {}
    lines = ["实验设计:"]
    fields = [
        ("idea_id", design.get("idea_id") or spec.get("idea_id")),
        ("hypothesis", design.get("hypothesis") or spec.get("hypothesis")),
        ("dataset", data.get("path") or capsule.get("dataset_id")),
        ("target", data.get("target")),
        ("features", data.get("features")),
        (
            "methods",
            package_design.get("methods")
            or ([capsule.get("model")] if capsule.get("model") else []),
        ),
        (
            "metric",
            design.get("primary_metric")
            or package_design.get("metric")
            or capsule.get("metric_name"),
        ),
        (
            "seeds",
            design.get("seeds") or package_design.get("seeds") or capsule.get("seeds"),
        ),
        ("cv_folds", package_design.get("cv_folds") or (package.get("evidence") or {}).get("cv_folds")),
        ("test_size", package_design.get("test_size")),
        (
            "ridge_alpha",
            design.get("ridge_alpha")
            or (package.get("evidence") or {}).get("ridge_alpha"),
        ),
        ("controls", design.get("controls") or package_design.get("controls")),
        ("stopping_rule", package_design.get("stopping_rule")),
    ]
    for label, value in fields:
        if value in (None, "", []):
            continue
        rendered = (
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (list, dict))
            else _clean(value, 800)
        )
        lines.append("- %s: %s" % (label, rendered))
    if signed:
        lines.append("已人签实验证据（只能使用以下结果数字）:")
        lines.append("- claim: " + _clean(signed.get("statement"), 1200))
        for assertion in signed.get("assertions") or []:
            lines.append(
                "- assertion: " + json.dumps(assertion, ensure_ascii=False)[:600]
            )
        for method, item in (package.get("metrics_summary") or {}).items():
            lines.append(
                "- %s %s: mean=%.4f std=%.4f n=%s"
                % (
                    method,
                    item.get("metric"),
                    float(item.get("mean") or 0.0),
                    float(item.get("std") or 0.0),
                    item.get("n"),
                )
            )
        lines.append(
            "- allowed_result_numbers: "
            + ", ".join(str(value) for value in contract.get("allowed_result_numbers") or [])
        )
        lines.append(
            "- allowed_design_numbers: "
            + ", ".join(str(value) for value in contract.get("allowed_design_numbers") or [])
        )
        for name, item in (package.get("comparison") or {}).items():
            lines.append(
                "- paired comparison %s: mean_diff=%.4f CI95=[%.4f, %.4f] wins=%s/%s"
                "（normal-approx CI；不得声称显著性）"
                % (
                    name,
                    float(item.get("mean_diff") or 0.0),
                    float(item.get("ci95_low") or 0.0),
                    float(item.get("ci95_high") or 0.0),
                    item.get("wins"),
                    item.get("n"),
                )
            )
        if package.get("results_table"):
            lines.append("结果表（表 1，来自 verified metrics）:")
            lines.append("- 文件: " + str(package.get("results_table")))
            lines.append("- 在“结果”节引用表 1，按表报告 mean/std/CI；不得新增数字。")
    else:
        lines.append(
            "实验 claim 未签核：只能写设计与方法，不得报告任何结果数值、均值或标准差。"
        )
    figure = package.get("figure") or {}
    if figure and signed:
        lines.append("结果图（数据图，不是示意图）:")
        lines.append("- 图号: 图 %s" % figure.get("figure_number", 1))
        lines.append("- 图注: " + _clean(figure.get("caption"), 1200))
        lines.append("- PNG: " + str(figure.get("png") or ""))
        lines.append(
            "- 在“结果”节引用“图 1”，按图注描述均值与标准差；不得编造图中不存在的趋势、显著性或不存在的子图。"
        )
    elif figure:
        lines.append("结果图存在但 claim 未签核：不得引用为研究结果。")
    method_figure = package.get("method_figure") or {}
    if method_figure:
        lines.append("方法示意图（AstraDraw，schematic=true，不是实验结果）:")
        lines.append("- 图号: 图 %s" % method_figure.get("figure_number", 2))
        lines.append("- 图注: " + _clean(method_figure.get("caption"), 1200))
        lines.append("- SVG: " + str(method_figure.get("svg") or ""))
        lines.append(
            "- 在“方法”节引用图 2 解释机制；不得把示意图写成实验结果、数据趋势或显著性。"
        )
    return lines


def _evidence_context(pack: Dict[str, Any], innovation: Dict[str, Any]) -> str:
    lines = [
        "研究主题: %s" % _clean((pack.get("task") or {}).get("goal")),
        "语料统计: %s" % json.dumps((pack.get("literature") or {}).get("corpus") or {}, ensure_ascii=False),
        "",
    ]
    experiment_lines = _experiment_context(pack)
    if experiment_lines:
        lines.extend(experiment_lines)
        lines.append("")
    lines.append("来源卡:")
    for ref in ((pack.get("literature") or {}).get("references") or [])[:20]:
        lines.append(
            "[%s] %s. %s. %s, %s. %s"
            % (
                ref.get("ref_id"),
                _clean(ref.get("title")),
                ", ".join((ref.get("authors") or [])[:3]),
                _clean(ref.get("venue")),
                ref.get("year"),
                _clean(ref.get("url")),
            )
        )
        if ref.get("abstract"):
            lines.append("  摘要: " + _clean(ref.get("abstract"), 600))
    lines.append("")
    lines.append("引用-证据对照（每个 [REF] 只能支持其 span 能直接蕴含的句子）:")
    selected = (pack.get("literature") or {}).get("selected_spans") or {}
    span_by_id = {
        str(span.get("span_id")): span
        for spans in selected.values()
        for span in (spans or [])
        if isinstance(span, dict) and span.get("span_id")
    }
    evidence_map = pack.get("evidence_map") or {}
    for ref in ((pack.get("literature") or {}).get("references") or [])[:20]:
        ref_id = str(ref.get("ref_id") or "")
        if not ref_id:
            continue
        span_ids = [str(value) for value in evidence_map.get(ref_id) or [] if str(value)]
        lines.append("[%s] %s" % (ref_id, _clean(ref.get("title"), 180)))
        if not span_ids:
            lines.append("  - 无 selected span：不得用于具体事实或结论引用")
            continue
        for span_id in span_ids[:2]:
            span = span_by_id.get(span_id)
            if span:
                lines.append("  - %s: %s" % (span_id, _clean(span.get("text"), 360)))
    lines.append("")
    claim_plan = pack.get("claim_plan") or {}
    if claim_plan.get("claims"):
        lines.append("Claim plan（每句只选一个 claim/REF；只改写 quote 直接陈述的内容）:")
        for claim in (claim_plan.get("claims") or [])[:24]:
            lines.append(
                "- %s %s/%s: %s"
                % (
                    claim.get("claim_id"),
                    claim.get("ref_id"),
                    claim.get("span_id"),
                    _clean(claim.get("quote"), 300),
                )
            )
        if claim_plan.get("unusable_refs"):
            lines.append(
                "- 无可用 span 的 REF（不得用于具体事实）: "
                + ", ".join(claim_plan.get("unusable_refs") or [])
            )
        lines.append("")
    synthesis = (pack.get("literature") or {}).get("synthesis") or {}
    if synthesis.get("themes"):
        lines.append("跨来源综合矩阵（每个主题至少两篇来源）:")
        for theme in synthesis.get("themes") or []:
            lines.append(
                "- %s %s | sources=%s | confidence=%s"
                % (
                    theme.get("theme_id"),
                    theme.get("name"),
                    ", ".join(
                        str(item.get("ref_id")) for item in theme.get("stances") or []
                    ),
                    theme.get("confidence"),
                )
            )
            lines.append("  summary: " + _clean(theme.get("summary"), 500))
            if theme.get("tension"):
                lines.append("  tension: " + _clean(theme.get("tension"), 300))
    lines.append("")
    lines.append("已识别缺口:")
    for gap in innovation.get("gaps") or []:
        lines.append(
            "- %s %s | %s | evidence=%s"
            % (
                gap.get("gap_id"),
                gap.get("description"),
                gap.get("why_unresolved"),
                ", ".join(gap.get("evidence_refs") or []),
            )
        )
    lines.append("")
    lines.append("候选创新点:")
    for idea in innovation.get("final_ideas") or innovation.get("selected_ideas") or []:
        plan = idea.get("experiment_plan") or {}
        lines.append(
            "- %s %s | mechanism=%s | falsification=%s | evidence=%s | 可执行实验计划: profile=%s dataset=%s metric=%s"
            % (
                idea.get("idea_id"),
                idea.get("title"),
                idea.get("mechanism"),
                idea.get("falsification"),
                ", ".join(idea.get("evidence_refs") or []),
                plan.get("profile") or "未绑定",
                plan.get("dataset") or "?",
                plan.get("metric") or "?",
            )
        )
    independence = innovation.get("independence") or {}
    if independence:
        lines.append("")
        if independence.get("admission_eligible"):
            lines.append(
                "评审独立性: %d 次批评调用由 %d 个不同模型供给回答（providers=%s；models=%s；提案模型未兼任审稿），"
                "面板可称结构化独立评审；可以写明各角色的供给，但仍不得声称审稿意见彼此独立、"
                "不得把它当新颖性证明，也不得写成 G1/G2 已通过。kind=%s"
                % (
                    int(independence.get("critic_calls") or 0),
                    int(independence.get("distinct_supplies") or 0),
                    ", ".join(independence.get("distinct_providers") or []),
                    ", ".join(independence.get("distinct_model_ids") or []),
                    independence.get("kind") or "?",
                )
            )
        else:
            lines.append(
                "评审独立性: 本轮 %d 次批评调用不构成独立评审（%s）。写作时不得把三方角色写成三位独立审稿人，"
                "也不得用该分数支撑「已通过评审」；只能在讨论节作为流程信号说明，并在局限中给出解除条件"
                "（为每个角色绑定不同 provider+model，且提案模型不兼任审稿）。"
                % (
                    int(independence.get("critic_calls") or 0),
                    "; ".join(independence.get("reasons") or ["same model supply"]),
                )
            )
    return "\n".join(lines)[:MAX_PROMPT_CHARS]


def _normalise_refs(text: str) -> str:
    return re.sub(r"(?<!\[)\b(REF-[0-9]{2,})\b(?!\])", r"[\1]", text)


def _writer_prompt(pack: Dict[str, Any], innovation: Dict[str, Any], blockers: Optional[List[str]] = None):
    ref_ids = [
        str(ref.get("ref_id"))
        for ref in ((pack.get("literature") or {}).get("references") or [])
    ]
    article_type = str((pack.get("writing_contract") or {}).get("article_type") or "review")
    system = (
        "你是严谨的中文核刊作者，专长是自我改进科研智能体与证据审计。你只能使用给定的"
        "来源卡、证据句、语料统计、实验证据和创新评审结果。不得编造论文、引用、实验结果或数字。"
        "输出完整 Markdown 稿件。"
    )
    repair = ""
    if blockers:
        repair = (
            "\n上一稿被确定性审计阻断，必须在本次修复：\n- "
            + "\n- ".join(blockers)
            + "\n修复结果数值类阻断时，只能使用 writing contract 的 allowed_result_numbers 与 "
            "allowed_design_numbers；删除其他所有数字，不得为了迁就数字改写实验设计。\n"
        )
    if article_type == "reproduction":
        requirements = """请基于证据包写一篇中文实证研究论文，目标 7000-10000 个汉字。

结构必须包含：标题、摘要、引言、相关工作、方法、实验、结果、讨论、结论、参考文献。
写作要求：
1. 只能引用这些 REF: %s；不得出现列表外的引用。
1b. 每个 [REF-xx] 只能支持“引用-证据对照”中该 REF 的 span 能直接蕴含的句子；只能部分支持时必须弱化或拆句，禁止把多个 REF 的支持拼成一句。
1c. 每句最多保留一个 [REF-xx]；需要综合多个来源时拆成多个句子，每句只引用一个来源。不要在一句里用多个 REF 拼结论。
1d. 优先从 Claim plan 选择主张；每个句子只对应一个 claim/REF，只改写该 claim 的 quote 直接陈述的内容，不得扩成普遍结论。
2. 这是实证论文，不是综述：围绕一个可证伪假设，写清数据集、target、features、方法、baseline、主指标、seeds、test split/CV folds 与 stopping rule。
3. 结果段只报告写作契约 allowed_result_numbers 中的数字，且必须与已人签 claim 和 experiment evidence 对应；按方法报告 mean/std，明确 primary method 与 baseline 的差异；若有 paired comparison，可报告 mean_diff 与 CI95，但必须注明 normal-approx、无显著性检验。可提及 allowed_design_numbers 中的已验证设计常量（seeds/test split/rows），但不得把设计常量包装成结果。不得编造显著性、SOTA、置信区间或未实际运行的实验。
3b. 若证据包有结果表，必须在“结果”节引用表 1，并按表报告 mean/std/CI；不得新增表外数字。
4. 若实验 claim 未签核，只能写设计与方法，不得报告任何结果数值、均值或标准差。
5. 相关工作必须做跨来源综合：每个主题至少比较两篇不同来源，明确写出跨来源一致点与张力；禁止逐篇摘要式罗列。
6. 方法示意图只能用于解释机制，放在“方法”节引用图 2，不得放进“结果”节或当作实验证据。
7. 创新评审中的候选方向只能写在“讨论”或“未来工作”，不得包装成已经完成的实验结果。
8. 明确局限：单一数据集/本地 split、seed 数量有限、未做显著性检验、预印本未独立核验、审计不是语义蕴含证明。
9. 参考文献列表用 [REF-xx] 开头，逐条列出标题、作者、venue、年份、URL。
10. 不要在正文留下 TODO、待补或占位符。

证据包：
%s
%s""" % (", ".join(ref_ids), _evidence_context(pack, innovation), repair)
        if not ((pack.get("experiment_package") or {}).get("method_figure")):
            requirements = requirements.replace(
                "6. 方法示意图只能用于解释机制，放在“方法”节引用图 2，不得放进“结果”节或当作实验证据。\n",
                "",
            )
    else:
        _zh_low, _zh_high = LENGTH_TARGETS["zh"]
        requirements = f"""请基于证据包写一篇中文综述/立场论文，目标 {_zh_low}-{_zh_high} 个汉字。

结构必须包含：标题、摘要、引言、相关工作、方法、实验、结果、讨论、结论、参考文献。
写作要求：
1. 只能引用这些 REF: %s；不得出现列表外的引用。
1b. 每个 [REF-xx] 只能支持“引用-证据对照”中该 REF 的 span 能直接蕴含的句子；只能部分支持时必须弱化或拆句，禁止把多个 REF 的支持拼成一句。
1c. 每句最多保留一个 [REF-xx]；需要综合多个来源时拆成多个句子，每句只引用一个来源。不要在一句里用多个 REF 拼结论。
1d. 优先从 Claim plan 选择主张；每个句子只对应一个 claim/REF，只改写该 claim 的 quote 直接陈述的内容，不得扩成普遍结论。
2. 这是综述/立场论文，不得伪造新实验或新结果；实验部分写“语料与证据审计设计”，结果部分做定性综合，不放实验数值。
3. 语料统计（来源数、venue/year 分布）可以写在方法/实验，但不得写成模型性能结果。
4. 必须把创新评审中的 3 个候选方向写进“讨论”或“研究议程”，每个都给出可证伪预测和本地小规模实验计划。
5. 相关工作/方法必须做跨来源综合：每个主题至少比较两篇不同来源，明确写出跨来源一致点与张力；禁止逐篇摘要式罗列。
6. 正文至少引用 8 个不同 REF（若证据包不足 8 个则全部引用），不得依赖单一来源。
7. 明确局限：预印本/venue comment 未独立核验、语料有界、审计不是语义蕴含证明。
8. 参考文献列表用 [REF-xx] 开头，逐条列出标题、作者、venue、年份、URL。
9. 不要在正文留下 TODO、待补或占位符。

证据包：
%s
%s""" % (", ".join(ref_ids), _evidence_context(pack, innovation), repair)
    brief = journal_style_brief(str(pack.get("venue") or ""))
    if brief:
        requirements = (
            "目标期刊规范（来自外部 Skill 投影，优先遵循但不伪造结果）:\n"
            + brief
            + "\n\n"
            + requirements
        )
    return [{"role": "system", "content": system}, {"role": "user", "content": requirements}]


def generate_manuscript(
    project: Path,
    run_id: str,
    output_path: Path,
    *,
    model: Any = None,
    innovation: Optional[Dict[str, Any]] = None,
    repair_attempts: int = 1,
    offline_draft: bool = False,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    pack = load_writing_pack(project, run_id) or build_writing_pack(
        project, run_id, language="zh", venue="zh_core_journal",
        max_sources=16, max_spans_per_source=3,
    )
    if offline_draft:
        text = ensure_pack_marker(_offline_draft(pack), pack)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        audit = audit_manuscript(output, pack=pack)
        return {
            "status": "generated" if audit.get("status") != "blocked" else "blocked",
            "draft": str(output),
            "audit": audit,
            "repair_attempts": 0,
            "pack": pack,
            "innovation": innovation or {},
            "writer_mode": "deterministic_offline_test_only",
            "boundary": (
                "Deterministic offline test draft. It uses only pack refs and allowed "
                "numbers, is audited deterministically, and is not a model-quality result."
            ),
        }
    model = model or default_writer_model()
    if innovation is None:
        innovation_path = project / "runs" / run_id / "innovation-review.json"
        if not innovation_path.is_file():
            raise ManuscriptWriterError("innovation review is required before writing")
        innovation = json.loads(innovation_path.read_text(encoding="utf-8"))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    text = str(model.complete(_writer_prompt(pack, innovation), json_mode=False) or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    text = ensure_pack_marker(_normalise_refs(text), pack)
    output.write_text(text, encoding="utf-8")
    audit = audit_manuscript(output, pack=pack)
    attempts = 0
    while audit.get("status") == "blocked" and attempts < repair_attempts:
        attempts += 1
        repaired = str(
            model.complete(
                _writer_prompt(pack, innovation, audit.get("blockers") or []),
                json_mode=False,
            )
            or ""
        ).strip()
        if repaired.startswith("```"):
            repaired = re.sub(r"^```(?:markdown|md)?\s*", "", repaired)
            repaired = re.sub(r"\s*```$", "", repaired)
        if repaired:
            repaired = ensure_pack_marker(_normalise_refs(repaired), pack)
            output.write_text(repaired, encoding="utf-8")
            audit = audit_manuscript(output, pack=pack)
            text = repaired
    return {
        "status": "generated" if audit.get("status") != "blocked" else "blocked",
        "draft": str(output),
        "audit": audit,
        "repair_attempts": attempts,
        "pack": pack,
        "innovation": innovation,
        "boundary": (
            "Model-generated review/position draft. It is checked for citation/number/structure "
            "boundaries but is not peer reviewed, not submission-ready and does not create a claim."
        ),
    }

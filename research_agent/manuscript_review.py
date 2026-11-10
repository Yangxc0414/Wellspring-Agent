"""Review a manuscript with a strict rubric, revise it, and re-review.

The loop is deliberately conservative: a candidate revision is accepted only
if the deterministic manuscript audit does not get worse, citations remain
known, and the length stays within the configured range. Model prose can
improve, but it cannot invent citations, result numbers or sections.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project import run_dir
from .storage import write_json_atomic
from .writing_audit import audit_manuscript
from .ab_review import ABReviewError, run_ab_review
from .writing_pack import build_writing_pack, ensure_pack_marker, load_writing_pack

MANUSCRIPT_REVIEW_SCHEMA = "manuscript-review-0.1"
RUBRIC = ("evidence", "contribution", "method", "clarity", "venue_fit")
CITATION_RE = re.compile(r"\[(REF-[0-9]{2,}|[0-9]{1,3})\]")
BARE_REF_RE = re.compile(r"(?<!\[)REF-[0-9]{2,}(?!\])")
MAX_REVIEW_CONTEXT = 40000


class ManuscriptReviewError(ValueError):
    pass


def _clean(value: Any, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit else text


def _parse_json(text: str) -> Any:
    value = str(text or "").strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*", "", value)
        value = re.sub(r"\s*```$", "", value)
    try:
        return json.loads(value)
    except ValueError:
        start = value.find("{")
        end = value.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(value[start : end + 1])
            except ValueError:
                pass
    raise ManuscriptReviewError("model did not return valid JSON")


def review_model() -> Any:
    """Prefer the gateway binding for the paper stage; a host_agent profile needs no key."""
    from .adapters.research_models import default_model_for

    port, _note = default_model_for("paper", purpose="S8-S12 manuscript review")
    if port is not None:
        return port
    return default_review_model()


def default_review_model() -> Any:
    from .adapters.deepseek_model import DeepSeekModel, ModelConfigError

    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise ManuscriptReviewError(
            "manuscript review requires DEEPSEEK_API_KEY or an injected model port"
        )
    try:
        return DeepSeekModel(
            api_key=key,
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=240,
            max_tokens=8192,
        )
    except ModelConfigError as exc:
        raise ManuscriptReviewError(str(exc)) from exc


def _pack_context(pack: Dict[str, Any], limit: int = 12000) -> str:
    lines = ["研究目标: %s" % _clean((pack.get("task") or {}).get("goal"))]
    lines.append("来源:")
    for ref in ((pack.get("literature") or {}).get("references") or [])[:20]:
        lines.append(
            "- [%s] %s (%s, %s)"
            % (ref.get("ref_id"), ref.get("title"), ref.get("year"), ref.get("venue"))
        )
        if ref.get("abstract"):
            lines.append("  " + _clean(ref.get("abstract"), 500))
    lines.append("证据句:")
    for source_id, spans in ((pack.get("literature") or {}).get("selected_spans") or {}).items():
        for span in spans[:2]:
            lines.append("- " + _clean(span.get("text"), 420))
    contract = pack.get("writing_contract") or {}
    lines.append(
        "写作契约: article_type=%s; claim=%s; allowed_result_numbers=%s; allowed_design_numbers=%s"
        % (
            contract.get("article_type"),
            (pack.get("claim") or {}).get("status"),
            contract.get("allowed_result_numbers"),
            contract.get("allowed_design_numbers"),
        )
    )
    package = pack.get("experiment_package") or {}
    if package:
        evidence = package.get("evidence") or {}
        claim = package.get("claim") or {}
        lines.append(
            "实验包: id=%s; evidence=%s; claim=%s"
            % (
                package.get("experiment_id"),
                evidence.get("status"),
                claim.get("status") or "missing",
            )
        )
        if str(claim.get("status") or "") in ("supported", "approved"):
            lines.append("已人签 claim: " + _clean(claim.get("statement"), 900))
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
        else:
            lines.append("实验 claim 未签核：评审不得要求或接受结果数值。")
        figure = package.get("figure") or {}
        if figure and str(claim.get("status") or "") in ("supported", "approved"):
            lines.append(
                "结果图: 图 %s | %s"
                % (figure.get("figure_number", 1), _clean(figure.get("caption"), 900))
            )
    return "\n".join(lines)[:limit]


def _support_context(support: Optional[Dict[str, Any]]) -> str:
    if not support:
        return ""
    lines = [
        "语义支持账本: status=%s; counts=%s; unresolved_refs=%s"
        % (
            support.get("status"),
            json.dumps(support.get("counts") or {}, ensure_ascii=False),
            support.get("unresolved_refs"),
        )
    ]
    for item in support.get("items") or []:
        if item.get("status") == "supported" and not item.get("unresolved_refs"):
            continue
        lines.append(
            "- %s [%s] %s: %s | %s"
            % (
                item.get("id"),
                item.get("status"),
                ",".join(item.get("refs") or []),
                _clean(item.get("sentence"), 240),
                _clean(item.get("rationale"), 300),
            )
        )
    return "\n".join(lines[:10])


def _review_prompt(
    pack: Dict[str, Any],
    draft: str,
    round_index: int,
    support: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    system = (
        "你是严格的顶会/中文核刊领域主席。你要检查稿件的证据一致性、贡献、方法、"
        "结构与表达，但不得要求作者编造实验结果。只能依据给定的来源卡、证据句和稿件"
        "本身判断。输出必须是合法 JSON。"
    )
    article_type = str((pack.get("writing_contract") or {}).get("article_type") or "review")
    if article_type == "reproduction":
        article_note = (
            "这是实证论文：检查结果数字是否全部来自 allowed_result_numbers 且与已签 claim "
            "和 experiment evidence 对应；检查数据集、target/features、test split、seeds、"
            "baseline、主指标与停止规则是否写清；若证据包有结果图，检查正文是否引用图 1、"
            "图注是否与图和证据一致；不得要求作者补做未运行的实验或编造显著性。"
        )
    else:
        article_note = (
            "若是综述/立场论文，contribution 指新的 taxonomy、综合框架或研究议程，"
            "而不是实验数值。"
        )
    user = """第 %d 轮评审。请按 1-10 分评估，并给出可执行的 must_fix。%s

结构约束：必须保留摘要、引言、相关工作、方法、实验、结果、讨论、结论、参考文献；
“实验”节可以写证据审计设计，不得要求删除或改名。证据包列出的 REF 均视为可核验。

评分维度: evidence, contribution, method, clarity, venue_fit。

语义支持账本:
%s

证据包:
%s

稿件:
%s

只输出 JSON:
{"scores":{"evidence":1,"contribution":1,"method":1,"clarity":1,"venue_fit":1},"overall":1,"strengths":[""],"weaknesses":[""],"must_fix":[""],"section_actions":[{"heading":"","action":""}],"decision":"accept|revise|reject"}
""" % (
        round_index,
        article_note,
        _support_context(support) or "not requested",
        _pack_context(pack),
        draft[:MAX_REVIEW_CONTEXT],
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _normalise_review(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ManuscriptReviewError("review must be an object")
    raw_scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    scores = {}
    for key in RUBRIC:
        try:
            value = float(raw_scores.get(key))
        except (TypeError, ValueError):
            value = 0.0
        scores[key] = max(1.0, min(10.0, value)) if value else 1.0
    overall = sum(scores.values()) / len(scores)
    return {
        "scores": scores,
        "overall": round(overall, 3),
        "strengths": [_clean(item, 400) for item in payload.get("strengths") or []][:8],
        "weaknesses": [_clean(item, 400) for item in payload.get("weaknesses") or []][:8],
        "must_fix": [_clean(item, 400) for item in payload.get("must_fix") or []][:12],
        "section_actions": [
            {
                "heading": _clean(item.get("heading"), 120),
                "action": _clean(item.get("action"), 500),
            }
            for item in payload.get("section_actions") or []
            if isinstance(item, dict)
        ][:12],
        "decision": _clean(payload.get("decision"), 20).lower() or "revise",
    }


SECTION_RE = re.compile(r"(?m)^(##\s+.+)$")


def _normalise_heading(value: str) -> str:
    text = re.sub(r"^#+\s*", "", str(value or "")).strip().lower()
    text = re.sub(r"^[0-9]+(?:\.[0-9]+)*[.、\s]*", "", text)
    return re.sub(r"\s+", "", text)


def _split_markdown_sections(text: str) -> tuple:
    parts = re.split(r"(?m)(?=^##\s+)", text or "")
    preamble = parts[0] if parts and not parts[0].lstrip().startswith("##") else ""
    sections = []
    for part in parts[1:]:
        lines = part.splitlines()
        if not lines:
            continue
        heading = lines[0].strip()
        body = "\n".join(lines[1:]).strip("\n")
        sections.append(
            {
                "heading": heading,
                "title": re.sub(r"^##\s*", "", heading).strip(),
                "body": body,
            }
        )
    return preamble, sections


def _join_markdown_sections(preamble: str, sections: List[Dict[str, str]]) -> str:
    chunks = []
    if preamble.strip():
        chunks.append(preamble.strip("\n"))
    for section in sections:
        chunks.append(("%s\n\n%s" % (section["heading"], section["body"])).strip())
    return "\n\n".join(chunks) + "\n"


def _section_matches(candidate: str, title: str) -> bool:
    left = _normalise_heading(candidate)
    right = _normalise_heading(title)
    return bool(left and right and (left in right or right in left))


def _target_sections(review: Dict[str, Any], support: Optional[Dict[str, Any]], sections: List[Dict[str, str]]) -> List[Dict[str, str]]:
    headings = [
        str(item.get("heading") or "")
        for item in review.get("section_actions") or []
        if isinstance(item, dict)
    ]
    if support:
        headings += [
            str(item.get("section") or "")
            for item in support.get("items") or []
            if item.get("status") in ("insufficient", "contradicted")
            or item.get("unresolved_refs")
        ]
    targets = []
    for section in sections:
        if any(_section_matches(value, section["title"]) for value in headings if value):
            targets.append(section)
    return targets


def _clean_section_output(raw: Any, original: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:markdown|md)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    if text.startswith("##"):
        text = "\n".join(text.splitlines()[1:]).strip()
    ratio = len(text) / max(1, len(original))
    if not text or ratio < 0.4 or ratio > 1.8:
        return original
    return text


def _section_revision(
    pack: Dict[str, Any],
    current_text: str,
    review: Dict[str, Any],
    support: Optional[Dict[str, Any]],
    model: Any,
    round_index: int,
) -> tuple:
    preamble, sections = _split_markdown_sections(current_text)
    targets = _target_sections(review, support, sections)
    if not targets:
        return None, []
    revised_sections = []
    for section in targets[:3]:
        section_support = None
        if support:
            section_support = {
                **support,
                "items": [
                    item for item in support.get("items") or []
                    if _section_matches(str(item.get("section") or ""), section["title"])
                ],
            }
        prompt = _section_revise_prompt(
            pack,
            section["title"],
            section["body"],
            review,
            section_support,
            round_index,
        )
        raw = model.complete(prompt, json_mode=False)
        revised = _clean_section_output(raw, section["body"])
        if revised != section["body"]:
            revised_sections.append(section["title"])
        section["body"] = revised
    return _join_markdown_sections(preamble, sections), revised_sections


def _span_text_map(pack: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    selected = (pack.get("literature") or {}).get("selected_spans") or {}
    mapping: Dict[str, Dict[str, str]] = {}
    for source_id, spans in selected.items():
        for span in spans or []:
            if not isinstance(span, dict):
                continue
            span_id = str(span.get("span_id") or "")
            if span_id:
                mapping[span_id] = {
                    "source_id": str(source_id),
                    "text": str(span.get("text") or ""),
                }
    return mapping


def _normalised_numbers(text: str) -> List[float]:
    values = []
    for token in re.findall(r"(?<![A-Za-z0-9])[-+]?[0-9]+(?:\.[0-9]+)?%?(?![A-Za-z0-9])", text or ""):
        try:
            values.append(float(token.replace("%", "")))
        except ValueError:
            continue
    return values


def _support_patch_revision(
    pack: Dict[str, Any],
    current_text: str,
    support: Optional[Dict[str, Any]],
    model: Any,
    round_index: int,
) -> tuple:
    if not support:
        return None, []
    bad_items = [
        item
        for item in support.get("items") or []
        if item.get("status") in ("partial", "insufficient", "contradicted")
        or item.get("unresolved_refs")
    ]
    if not bad_items:
        return None, []
    preamble, sections = _split_markdown_sections(current_text)
    span_by_id = _span_text_map(pack)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in bad_items:
        grouped.setdefault(str(item.get("section") or ""), []).append(item)
    revised_sections: List[str] = []
    for section in sections:
        items = []
        for heading, values in grouped.items():
            if _section_matches(heading, section["title"]):
                items.extend(values)
        if not items:
            continue
        prompt = _support_patch_prompt(
            pack,
            section["title"],
            section["body"],
            items,
            span_by_id,
            round_index,
        )
        raw = model.complete(prompt, json_mode=True)
        payload = _parse_json(raw)
        replacements = payload.get("replacements") if isinstance(payload, dict) else None
        if not isinstance(replacements, list):
            continue
        body = section["body"]
        applied = 0
        for replacement in replacements[:12]:
            if not isinstance(replacement, dict):
                continue
            find = str(replacement.get("find") or "")
            rewrite = str(replacement.get("rewrite") or "").strip()
            if not find or not rewrite or find not in body:
                continue
            old_refs = set(re.findall(r"\[(REF-[0-9]{2,})\]", find))
            new_refs = set(re.findall(r"\[(REF-[0-9]{2,})\]", rewrite))
            if not new_refs.issubset(old_refs):
                continue
            refs_per_sentence = [
                set(re.findall(r"\[(REF-[0-9]{2,})\]", sentence))
                for sentence in re.split(r"(?<=[。！？])|(?<=[.!?])\s+", rewrite)
                if sentence.strip()
            ]
            if any(len(values) > 1 for values in refs_per_sentence):
                continue
            old_numbers = _normalised_numbers(find)
            new_numbers = _normalised_numbers(rewrite)
            if any(
                not any(abs(value - old) <= 1e-9 for old in old_numbers)
                for value in new_numbers
            ):
                continue
            ratio = len(rewrite) / max(1, len(find))
            if ratio < 0.35 or ratio > 2.2:
                continue
            body = body.replace(find, rewrite, 1)
            applied += 1
        if applied:
            section["body"] = body
            revised_sections.append(section["title"])
    if not revised_sections:
        return None, []
    return _join_markdown_sections(preamble, sections), revised_sections


def _support_patch_prompt(
    pack: Dict[str, Any],
    title: str,
    body: str,
    items: List[Dict[str, Any]],
    span_by_id: Dict[str, Dict[str, str]],
    round_index: int,
) -> List[Dict[str, str]]:
    system = (
        "你是证据约束的学术编辑。只改写给定的问题句，不改变其它文本。"
        "不得新增引用、数字或事实；只能使用原句已有的 [REF-xx]。"
        "每个改写句最多保留一个最能直接支持它的 REF；若原句合并了多个来源，拆成多句。"
        "删除“所有/普遍/必然/总是”等全称词和证据未覆盖的额外条件。"
        "只返回合法 JSON：{\"replacements\":[{\"find\":\"原句\",\"rewrite\":\"改写后句子\"}]}。"
    )
    issue_lines = []
    for item in items[:8]:
        issue_lines.append(
            "- %s [%s] %s"
            % (
                item.get("id"),
                item.get("status"),
                _clean(item.get("sentence"), 320),
            )
        )
        issue_lines.append("  rationale: " + _clean(item.get("rationale"), 320))
        for span_id in (item.get("evidence_refs") or [])[:3]:
            span = span_by_id.get(str(span_id))
            if span:
                issue_lines.append(
                    "  evidence %s: %s" % (span_id, _clean(span.get("text"), 360))
                )
    user = """第 %d 轮支持修复：章节 %s

问题句与证据:
%s

当前章节正文:
%s

要求：
1. 只改写列出的问题句；find 必须逐字来自当前章节。
2. 只能使用原句已有 REF；不得新增引用、数字、事实或新章节。
3. 若 rationale 指出全称/范围/额外条件不被支持，删除全称词和额外条件，只保留证据直接陈述的内容。
4. 若原句含多个 REF，拆成多个句子；每个句子只能出现 0 或 1 个 REF，且只保留最能直接支持该句的那个；含两个及以上 REF 的句子会被拒绝。
5. 优先使用 evidence span 的原词；不确定时写成“在该研究的设置下/该研究报告显示”，不要扩写成普遍结论。
6. 证据不足时删除该断言或改成研究问题/计划；没有可安全改写时返回 {"replacements":[]}。
7. 不返回标题、代码块或其它文本。
""" % (round_index, title, "\n".join(issue_lines), body[:12000])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _section_revise_prompt(
    pack: Dict[str, Any],
    title: str,
    body: str,
    review: Dict[str, Any],
    support: Optional[Dict[str, Any]],
    round_index: int,
) -> List[Dict[str, str]]:
    system = (
        "你是资深学术作者。只修订给定章节，返回章节正文，不要标题、不要代码块。"
        "必须保留原有引用、数字、事实与章节范围；不得新增引用或数字。"
    )
    issues = "\n".join("- " + str(item) for item in review.get("must_fix") or [])
    user = """第 %d 轮章节修订：%s

本节必须修复:
%s

语义支持问题:
%s

证据上下文:
%s

当前章节正文:
%s

要求：只返回修订后的章节正文；不得返回标题或其它章节；长度控制在原文 60%%-140%%；无法确定时保留原文。
""" % (
        round_index,
        title,
        issues or "按审稿意见改进论证与表达",
        _support_context(support) or "无",
        _pack_context(pack)[:8000],
        body[:12000],
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _revise_prompt(
    pack: Dict[str, Any],
    draft: str,
    review: Dict[str, Any],
    round_index: int,
    support: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    contract = pack.get("writing_contract") or {}
    allowed = contract.get("allowed_result_numbers") or []
    system = (
        "你是资深学术作者。根据审稿意见改进稿件，但必须遵守证据契约：不得新增"
        "不存在于证据包的引用，不得编造结果或数字，不得删除必需章节。未签核 Claim "
        "时结果段不得出现结果数值。输出只包含完整 Markdown 稿件，不要代码块。"
    )
    article_type = str(contract.get("article_type") or "review")
    if article_type == "reproduction":
        article_note = (
            "这是实证论文：保留结果节中与已签 claim 对应的可追溯结果数字，"
            "不得删除全部结果数字，不得新增未授权数字或显著性声明。"
        )
    else:
        article_note = "如果是综述/立场论文，不得伪造实验；实验部分写证据审计或研究议程。"
    user = """第 %d 轮修订。请实质改进稿件，而不是只改措辞。

硬约束：
- 保留并正确使用 [REF-xx]；只能引用证据包中已有的 REF。
- 不得新增结果数字；allowed_result_numbers=%s。
- 保留章节：摘要、引言、相关工作、方法、实验、结果、讨论、结论、参考文献。
- %s
- 语义支持必须修复（insufficient/contradicted/unresolved 引用句必须删除、降级或换成有 span 支持的表述；不得只改措辞）:
%s
- 长度控制在原文的 70%%-150%%。

审稿意见:
%s

证据包:
%s

原稿:
%s
""" % (
        round_index,
        json.dumps(allowed, ensure_ascii=False),
        article_note,
        _support_context(support) or "not requested",
        json.dumps(review, ensure_ascii=False, indent=2)[:12000],
        _pack_context(pack),
        draft[:MAX_REVIEW_CONTEXT],
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _citations(text: str) -> set:
    return set(CITATION_RE.findall(text or "")) | set(BARE_REF_RE.findall(text or ""))


def _audit_candidate(path: Path, pack: Dict[str, Any]) -> Dict[str, Any]:
    return audit_manuscript(path, pack=pack)


def _number_values(values: Any) -> List[float]:
    parsed = []
    for value in values or []:
        try:
            parsed.append(float(str(value).replace("%", "")))
        except (TypeError, ValueError):
            continue
    return parsed


def _accept_candidate(
    original_text: str,
    candidate_text: str,
    baseline_audit: Dict[str, Any],
    candidate_audit: Dict[str, Any],
) -> tuple:
    if not candidate_text.strip():
        return False, "empty revision"
    length_ratio = len(candidate_text) / max(1, len(original_text))
    if not 0.6 <= length_ratio <= 1.8:
        return False, "length ratio %.2f outside 0.6..1.8" % length_ratio
    if candidate_audit.get("status") == "blocked" and baseline_audit.get("status") != "blocked":
        return False, "revision introduces audit blockers: %s" % "; ".join(
            candidate_audit.get("blockers") or []
        )
    if len(candidate_audit.get("blockers") or []) > len(baseline_audit.get("blockers") or []):
        return False, "revision increases blockers"
    if (
        int(baseline_audit.get("result_number_count") or 0) > 0
        and int(candidate_audit.get("result_number_count") or 0) == 0
    ):
        return False, "revision drops all reported result numbers"
    baseline_numbers = _number_values(baseline_audit.get("result_numbers") or [])
    candidate_numbers = _number_values(candidate_audit.get("result_numbers") or [])
    missing = [
        value for value in baseline_numbers
        if not any(abs(value - other) <= 0.01 for other in candidate_numbers)
    ]
    if missing:
        return False, "revision changes or drops reported result numbers: %s" % ", ".join(
            "%g" % value for value in missing[:6]
        )
    return True, "accepted"


def run_manuscript_review(
    project: Path,
    run_id: str,
    draft_path: Path,
    *,
    rounds: int = 3,
    threshold: float = 8.0,
    model: Any = None,
    output_dir: Optional[Path] = None,
    support_judge: Any = None,
    strict_support: bool = False,
    judge_model_id: str = "",
    support_votes: int = 1,
    revision_mode: str = "full",
    ab_reviewer: Any = None,
    ab_sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    target = run_dir(project, run_id)
    if not target.is_dir():
        raise ManuscriptReviewError("run does not exist: " + run_id)
    draft_path = Path(draft_path)
    if not draft_path.is_file():
        raise ManuscriptReviewError("draft does not exist: " + str(draft_path))
    if model is None:
        raise ManuscriptReviewError("a model port is required for manuscript review")
    rounds = max(1, min(int(rounds), 5))
    threshold = max(0.0, min(float(threshold), 10.0))
    pack = load_writing_pack(project, run_id) or build_writing_pack(
        project, run_id, language="zh", venue="zh_core_journal",
        max_sources=16, max_spans_per_source=3,
    )
    if not str((pack.get("task") or {}).get("goal") or "").strip():
        try:
            demo = json.loads((target / "demo.json").read_text(encoding="utf-8"))
            topic = str(demo.get("topic") or "") if isinstance(demo, dict) else ""
        except (OSError, ValueError):
            topic = ""
        if topic:
            # The reviewer used to receive "研究目标:" with nothing after it.
            pack.setdefault("task", {})["goal"] = topic
    destination = Path(output_dir) if output_dir else target / "manuscript-review"
    destination.mkdir(parents=True, exist_ok=True)
    candidates = destination / "candidates"
    candidates.mkdir(exist_ok=True)
    current_text = draft_path.read_text(encoding="utf-8")

    def run_support(path: Path) -> Optional[Dict[str, Any]]:
        if support_judge is None:
            return None
        from .support_audit import audit_pack_support

        return audit_pack_support(
            path,
            pack,
            judge=support_judge,
            strict=strict_support,
            judge_model_id=judge_model_id,
            judge_votes=support_votes,
            cache_dir=destination / "support-cache",
        )

    baseline_audit = _audit_candidate(draft_path, pack)
    baseline_support = run_support(draft_path)
    iterations: List[Dict[str, Any]] = []
    accepted_rounds = 0
    best_text = current_text
    best_audit = baseline_audit
    best_support = baseline_support
    best_overall = 0.0
    current_path = draft_path
    previous_score: Optional[float] = None
    for round_index in range(1, rounds + 1):
        current_audit = _audit_candidate(current_path, pack)
        current_support = run_support(current_path)
        review_raw = model.complete(
            _review_prompt(pack, current_text, round_index, current_support),
            json_mode=True,
        )
        review = _normalise_review(_parse_json(review_raw))
        iterations.append(
            {
                "round": round_index,
                "stage": "review",
                "review": review,
                "audit": current_audit,
                "support": (
                    {
                        "status": current_support.get("status"),
                        "counts": current_support.get("counts"),
                        "unresolved_refs": current_support.get("unresolved_refs"),
                    }
                    if current_support
                    else None
                ),
                "candidate": str(current_path),
                "accepted": True,
            }
        )
        if review["overall"] > best_overall:
            best_overall = review["overall"]
            best_text = current_text
            best_audit = current_audit
            best_support = current_support
        if review["overall"] >= threshold:
            break
        if previous_score is not None and review["overall"] <= previous_score:
            break
        previous_score = review["overall"]
        if round_index >= rounds:
            break
        revised_sections = []
        candidate_text = ""
        mode = str(revision_mode or "full").lower()
        if mode == "support":
            candidate_text, revised_sections = _support_patch_revision(
                pack,
                current_text,
                current_support,
                model,
                round_index,
            )
        elif mode in ("section", "auto"):
            candidate_text, revised_sections = _section_revision(
                pack,
                current_text,
                review,
                current_support,
                model,
                round_index,
            )
        if mode == "support" and not candidate_text:
            break
        if not candidate_text:
            revision_raw = model.complete(
                _revise_prompt(pack, current_text, review, round_index, current_support),
                json_mode=False,
            )
            candidate_text = str(revision_raw or "").strip()
            if candidate_text.startswith("```"):
                candidate_text = re.sub(r"^```(?:markdown|md)?\s*", "", candidate_text)
                candidate_text = re.sub(r"\s*```$", "", candidate_text)
        candidate_path = candidates / ("round-%02d.md" % round_index)
        candidate_path.write_text(candidate_text, encoding="utf-8")
        candidate_audit = _audit_candidate(candidate_path, pack)
        candidate_support = run_support(candidate_path)
        accepted, reason = _accept_candidate(
            current_text, candidate_text, current_audit, candidate_audit
        )
        if accepted and candidate_support is not None and current_support is not None:
            current_bad = int(current_support.get("unresolved_refs") or 0) + sum(
                int((current_support.get("counts") or {}).get(key) or 0)
                for key in ("contradicted", "insufficient")
            )
            candidate_bad = int(candidate_support.get("unresolved_refs") or 0) + sum(
                int((candidate_support.get("counts") or {}).get(key) or 0)
                for key in ("contradicted", "insufficient")
            )
            if candidate_bad > current_bad:
                accepted, reason = False, "revision worsens semantic support"
            elif strict_support and candidate_bad > 0:
                accepted, reason = (
                    False,
                    "semantic support still has contradicted/unresolved/insufficient items",
                )
            else:
                current_supported = int(
                    (current_support.get("counts") or {}).get("supported") or 0
                )
                candidate_supported = int(
                    (candidate_support.get("counts") or {}).get("supported") or 0
                )
                tolerance = max(1, int(current_supported * 0.1))
                if candidate_supported < current_supported - tolerance:
                    accepted, reason = (
                        False,
                        "revision reduces supported citations: %d -> %d"
                        % (current_supported, candidate_supported),
                    )
                elif mode == "support":
                    current_partial = int(
                        (current_support.get("counts") or {}).get("partial") or 0
                    )
                    candidate_partial = int(
                        (candidate_support.get("counts") or {}).get("partial") or 0
                    )
                    if (
                        candidate_partial >= current_partial
                        and candidate_supported <= current_supported
                    ):
                        accepted, reason = (
                            False,
                            "support patch did not improve support",
                        )
        ab_summary = None
        if accepted and ab_reviewer is not None:
            try:
                ab_result = run_ab_review(
                    current_path,
                    candidate_path,
                    ab_reviewer,
                    sections=ab_sections or [],
                    rounds=1,
                )
                ab_summary = {
                    "overall_winner": ab_result.get("overall_winner"),
                    "original_overall": ab_result.get("original_overall"),
                    "revised_overall": ab_result.get("revised_overall"),
                }
                if ab_result.get("overall_winner") == "original":
                    accepted, reason = False, "blind A/B prefers the original"
            except ABReviewError as exc:
                accepted, reason = False, "A/B review failed: " + str(exc)
        iterations.append(
            {
                "round": round_index,
                "stage": "revision",
                "candidate": str(candidate_path),
                "revision_mode": (
                    "support" if mode == "support" else ("section" if revised_sections else "full")
                ),
                "revised_sections": revised_sections,
                "ab_review": ab_summary,
                "accepted": accepted,
                "reason": reason,
                "audit": candidate_audit,
                "support": (
                    {
                        "status": candidate_support.get("status"),
                        "counts": candidate_support.get("counts"),
                        "unresolved_refs": candidate_support.get("unresolved_refs"),
                    }
                    if candidate_support
                    else None
                ),
                "length_ratio": round(len(candidate_text) / max(1, len(current_text)), 3),
            }
        )
        if accepted:
            accepted_rounds += 1
            current_text = candidate_text
            current_path = candidate_path
        else:
            break
    final_path = destination / "final.md"
    best_text = ensure_pack_marker(best_text, pack)
    final_path.write_text(best_text, encoding="utf-8")
    final_support = run_support(final_path)
    write_json_atomic(destination / "final-audit.json", best_audit)
    if final_support is not None:
        write_json_atomic(destination / "support-ledger.json", final_support)
    with open(str(destination / "manuscript-review-iterations.jsonl"), "w", encoding="utf-8", newline="\n") as handle:
        for item in iterations:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    review_scores = [
        item["review"]["overall"] for item in iterations if item.get("stage") == "review"
    ]
    result = {
        "schema_version": MANUSCRIPT_REVIEW_SCHEMA,
        "run_id": run_id,
        "source_draft": str(draft_path),
        "final_draft": str(final_path),
        "model": getattr(model, "model_id", type(model).__name__),
        "rounds_requested": rounds,
        "rounds_completed": len(review_scores),
        "accepted_revisions": accepted_rounds,
        "threshold": threshold,
        "baseline_audit": baseline_audit,
        "final_audit": best_audit,
        "score_progression": review_scores,
        "best_score": round(best_overall, 3),
        "improved": bool(review_scores and best_overall > review_scores[0]),
        "status": (
            "reviewed"
            if best_overall >= threshold
            and (
                final_support is None
                or not strict_support
                or (
                    int(final_support.get("unresolved_refs") or 0) == 0
                    and int((final_support.get("counts") or {}).get("contradicted") or 0) == 0
                    and int((final_support.get("counts") or {}).get("insufficient") or 0) == 0
                )
            )
            else "needs_more_work"
        ),
        "support": final_support,
        "submission_ready": False,
        "iterations": iterations,
        "boundary": (
            "Model-assisted review/revision over a bounded evidence pack. "
            "Not peer review, not semantic entailment proof, not submission approval; "
            "no Claim/EA/gate/signature is created."
        ),
    }
    write_json_atomic(destination / "manuscript-review.json", result)
    lines = [
        "# Manuscript Review",
        "",
        "- source: `%s`" % draft_path,
        "- final: `%s`" % final_path,
        "- model: `%s`" % result["model"],
        "- rounds: %d" % result["rounds_completed"],
        "- accepted revisions: %d" % accepted_rounds,
        "- baseline audit: `%s`" % (baseline_audit.get("status")),
        "- final audit: `%s`" % (best_audit.get("status")),
        "- best score: %.2f" % best_overall,
        "- submission_ready: false",
        "",
        "## Scores",
        "",
    ]
    for index, score in enumerate(review_scores, 1):
        lines.append("- round %d: %.2f" % (index, score))
    lines += ["", "## Remaining blockers", ""]
    for item in best_audit.get("blockers") or []:
        lines.append("- " + item)
    lines += ["", result["boundary"], ""]
    (destination / "manuscript-review.md").write_text("\n".join(lines), encoding="utf-8")
    return result

"""LLM 辅助 span 分级：在机械切割之后，用宿主模型对每个 span 做信息类型分类。

设计原则（71-§4.4 延伸）：
- 发现（哪些句子是候选）= 机械规则，确定性
- 分级（每个候选是什么信息类型）= LLM 分类，对同一文本分类一致
- 绑定（哪些 span 进证据链）= 机械规则（evidence_role ∈ evidence_types），确定性
- LLM 不判断真假——只分类信息类型（可机械验证：quantitative_result 含数字等）

分类对错可独立验证 → 打破 LLM 设计 LLM 守卫的循环风险。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .storage import write_json_atomic

SPAN_GRADES_SCHEMA = "span-grades-0.1"

EVIDENCE_ROLES = (
    "quantitative_result",
    "causal_claim",
    "negative_result",
    "methodology",
    "limitation",
    "background",
)

_ROLE_CHECKS: Dict[str, Dict[str, Any]] = {
    "quantitative_result": {
        "hint_keywords": ("accuracy", "score", "rate", "p <",
                          "improve", "increase", "decrease", "significant",
                          "precision", "recall", "F1", "r2"),
        "hint_keywords_cn": ("准确率", "提升", "下降", "显著", "优于", "召回"),
    },
    "causal_claim": {
        "hint_keywords": ("leads to", "causes", "results in", "because",
                          "due to", "enables", "enhances"),
        "hint_keywords_cn": ("导致", "因为", "使得", "从而"),
    },
    "negative_result": {
        "hint_keywords": ("no significant", "failed to", "did not improve",
                          "worse than", "no improvement", "contrary to"),
        "hint_keywords_cn": ("未显著", "失败", "低于", "无改善", "相反"),
    },
    "methodology": {
        "hint_keywords": ("we use", "we train", "we evaluate", "we propose",
                          "method", "architecture", "protocol",
                          "fine-tune", "algorithm", "regression"),
        "hint_keywords_cn": ("使用", "训练", "评估", "提出", "架构", "回归"),
    },
    "limitation": {
        "hint_keywords": ("limitation", "however", "caveat", "future work",
                          "does not generalize", "only evaluated"),
        "hint_keywords_cn": ("局限", "然而", "仅", "未来", "不适用", "限制"),
    },
}

_BOUNDARY = (
    "LLM classifies information type (not truth); mechanical baseline provides "
    "an independent check; agreement rate is the pre-registered quality metric"
)


def _mechanical_hint(text: str) -> str:
    """规则基线：不依赖 LLM 的机械分类。无法匹配时返回 background（兜底）。"""
    lower = text.lower()
    if re.search(r"\d+\.\d+|\d+%|p\s*[<=]\s*0\.\d+", text):
        return "quantitative_result"
    for role in EVIDENCE_ROLES:
        spec = _ROLE_CHECKS.get(role)
        if not spec:
            continue
        for kw in spec.get("hint_keywords", ()):
            if kw in lower:
                return role
        for kw in spec.get("hint_keywords_cn", ()):
            if kw in text:
                return role
    return "background"


def build_grading_prompt(spans: List[Dict[str, Any]]) -> str:
    spans_json = json.dumps(
        [{"span_id": s.get("span_id", ""), "text": str(s.get("text") or "")[:400]}
         for s in spans],
        ensure_ascii=False, indent=2,
    )
    return _GRADING_PROMPT_TEMPLATE.format(spans_json=spans_json)


def parse_grading_response(raw: str, span_ids: List[str]) -> Dict[str, str]:
    """Parse LLM grading response into {span_id: evidence_role}.

    Only span_ids in the provided list are accepted (unknown ids ignored).
    """
    try:
        payload = json.loads(raw)
    except ValueError:
        start = raw.find("[")
        end = raw.rfind("]")
        if start >= 0 and end > start:
            try:
                payload = json.loads(raw[start:end + 1])
            except ValueError:
                return {}
        else:
            return {}
    if not isinstance(payload, list):
        return {}
    known = set(span_ids)
    grades: Dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("span_id") or "")
        role = str(item.get("evidence_role") or "")
        if sid in known and role in EVIDENCE_ROLES:
            grades[sid] = role
    return grades


def grade_spans(
    spans: List[Dict[str, Any]],
    *,
    model_port: Any,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Grade spans via the host model (host_agent face) + mechanical baseline."""
    if not spans:
        return {
            "schema_version": SPAN_GRADES_SCHEMA,
            "grades": {},
            "mechanical_baseline": {},
            "agreement_rate": None,
            "boundary": "no spans to grade",
        }
    prompt = build_grading_prompt(spans)
    messages = [{"role": "user", "content": prompt}]
    try:
        response = model_port.complete(messages, json_mode=True)
    except Exception as exc:
        return {
            "schema_version": SPAN_GRADES_SCHEMA,
            "grades": {},
            "error": str(exc)[:200],
            "boundary": "grading failed; no grades written",
        }

    span_ids = [str(s.get("span_id") or "") for s in spans]
    llm_grades = parse_grading_response(response, span_ids)

    mechanical: Dict[str, str] = {}
    grades: Dict[str, str] = {}
    for span in spans:
        sid = str(span.get("span_id") or "")
        text = str(span.get("text") or "")
        baseline = _mechanical_hint(text)
        mechanical[sid] = baseline
        grades[sid] = llm_grades.get(sid) or baseline

    both = [sid for sid in mechanical if sid in llm_grades]
    agree = sum(1 for sid in both if grades[sid] == mechanical[sid])
    agreement_rate = round(agree / len(both), 4) if both else None

    role_dist: Dict[str, int] = {}
    for g in grades.values():
        role_dist[g] = role_dist.get(g, 0) + 1

    return {
        "schema_version": SPAN_GRADES_SCHEMA,
        "grades": grades,
        "mechanical_baseline": mechanical,
        "agreement_rate": agreement_rate,
        "role_distribution": role_dist,
        "boundary": _BOUNDARY,
    }


def save_grades(path: Path, result: Dict[str, Any]) -> Dict[str, Any]:
    target = Path(path)
    if target.parent and not target.parent.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(str(target), result)
    return {"path": str(target), "graded": len(result.get("grades") or {})}


_GRADING_PROMPT_TEMPLATE = """对以下每条文本片段进行信息类型分类。只输出一个 JSON 数组，每个元素对应一条输入。

分类标准（严格按此分类，不要创造新类别）：
- quantitative_result: 包含具体数值、统计量或定量比较
- causal_claim: 声称因果效应（"X 导致 Y"、"X improves Y"）
- negative_result: 报告未达预期或否证性的结果
- methodology: 描述实验方法、协议、模型架构或数据处理步骤
- limitation: 描述研究的局限性或适用范围限制
- background: 背景叙述（不满足以上任何一类）

如果 span 同时满足多类，选最具体的（quantitative_result > causal_claim > negative_result > methodology > limitation > background）。

待分类的文本片段：
{spans_json}

输出格式：
[{{"span_id": "...", "evidence_role": "..."}}, ...]
"""

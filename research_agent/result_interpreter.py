"""Result interpretation connector: LLM generates a preliminary reading of
experimental results for the human reviewer at S5b.

设计定位（71-§4.2 延伸）：模块间的"语义兼容性连接器"——不是判定（门禁仍是人），
而是让判定者拿到更可理解的输入。LLM 解读不是 claim/gate/signature——它是
阅读辅助，人签不签仍由人决定。

边界：LLM 解读不写入 RunCapsule/EA/claim/closure——它只是旁路产物
（interpretation.json），供 S5b 阅读参考，不影响任何门禁语义。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import write_json_atomic

INTERPRETATION_SCHEMA = "result-interpretation-0.1"

_BOUNDARY = (
    "LLM-generated preliminary interpretation: reading aid for the human reviewer "
    "at S5b, NOT a claim, gate, signature or evidence artifact; the human makes "
    "the final decision; interpretation.json is a side artifact that does not "
    "enter RunCapsule, EA or closure"
)

_PROMPT_TEMPLATE = """你是一个严谨的科研结果解读助手。根据以下实验结果提供初步解读。

实验设计：
- 研究问题：{question}
- 主指标：{metric_name}
- 数据集：{dataset_id}
- Seeds：{seeds}
- 基线：{baseline}

实验结果：
{results_json}

请提供以下解读（输出 JSON）：
{{
  "metrics_reading": "逐 seed 指标的含义（哪些 seed 表现好/差，波动范围）",
  "notable_patterns": "值得注意的模式（一致性/异常值/趋势）",
  "potential_concerns": "潜在担忧（方差过大/样本不足/某个 seed 异常低）",
  "recommended_next_action": "建议下一步（签署/补 seeds/调整设计）",
  "confidence_note": "解读的置信度说明（哪些是数据直接支撑的，哪些是推断）"
}}

规则：
- 只解读给定的数字，不编造未给出的信息
- 如果 seeds 数量不足以得出统计结论，如实说明
- 不做因果推断（相关不等于因果）
- 不建议签署或不签署——那是人的决定
"""


def build_interpretation_prompt(capsule: Dict[str, Any], design: Dict[str, Any]) -> str:
    """Build the interpretation prompt from RunCapsule and experiment design."""
    metric_name = str(capsule.get("metric_name") or "unknown")
    metrics_by_seed = capsule.get("metrics_by_seed") or []
    seeds = capsule.get("seeds") or []
    dataset_id = str(capsule.get("dataset_id") or "unknown")
    return _PROMPT_TEMPLATE.format(
        question=str(design.get("question") or design.get("hypothesis") or "not provided")[:200],
        metric_name=metric_name,
        dataset_id=dataset_id,
        seeds=str(seeds),
        baseline=str(design.get("baseline") or "not provided")[:100],
        results_json=json.dumps(metrics_by_seed, ensure_ascii=False, indent=2),
    )


def _parse_interpretation(raw: str) -> Dict[str, str]:
    """Parse the LLM interpretation response into a structured dict."""
    try:
        payload = json.loads(raw)
    except ValueError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(raw[start:end + 1])
            except ValueError:
                return {}
        else:
            return {}
    if not isinstance(payload, dict):
        return {}
    keys = ("metrics_reading", "notable_patterns", "potential_concerns",
            "recommended_next_action", "confidence_note")
    return {key: str(payload.get(key) or "")[:500] for key in keys if payload.get(key)}


def interpret_results(
    run_dir: Path,
    *,
    model_port: Any,
) -> Dict[str, Any]:
    """Generate a preliminary interpretation of experimental results.

    Reads RunCapsule metrics + experiment design from the run dir, sends them
    to the host model for interpretation, and writes interpretation.json.
    The interpretation is a side artifact — it does not enter RunCapsule, EA
    or closure, and does not affect any gate semantics.
    """
    run = Path(run_dir).resolve()
    capsule = _read(run / "run" / "run-capsule.json")
    design = _read(run / "experiment.json") or _read(run / "design" / "experiment.json") or {}

    if not capsule:
        return {
            "schema_version": INTERPRETATION_SCHEMA,
            "status": "missing_capsule",
            "interpretation": {},
            "boundary": _BOUNDARY,
        }

    metric_name = str(capsule.get("metric_name") or "unknown")
    metrics_by_seed = capsule.get("metrics_by_seed") or []
    prompt = build_interpretation_prompt(capsule, design)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = model_port.complete(messages, json_mode=True)
    except Exception as exc:
        return {
            "schema_version": INTERPRETATION_SCHEMA,
            "status": "interpretation_failed",
            "error": str(exc)[:200],
            "boundary": _BOUNDARY,
        }

    parsed = _parse_interpretation(response)
    if not parsed:
        return {
            "schema_version": INTERPRETATION_SCHEMA,
            "status": "interpretation_unparseable",
            "interpretation": {},
            "boundary": _BOUNDARY,
        }

    result = {
        "schema_version": INTERPRETATION_SCHEMA,
        "status": "interpreted",
        "interpretation": parsed,
        "metric_name": metric_name,
        "metrics_by_seed": metrics_by_seed,
        "boundary": _BOUNDARY,
    }

    out = run / "interpretation.json"
    write_json_atomic(str(out), result)
    return result


def _read(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_interpretation(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Load a previously written interpretation.json."""
    path = Path(run_dir) / "interpretation.json"
    return _read(path)

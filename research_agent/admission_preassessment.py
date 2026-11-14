"""Admission pre-assessment: LLM prepares the full evidence chain for the human
reviewer at S5b, covering semantic consistency and evidence quality.

设计定位（71-§4.2 延伸）：LLM 是准备者（Preparer），不是决定者（Decider）。
在全自动和半自动模式下运行方式完全相同——它只增加信息，不改变门禁语义。
全自动模式下预评估结果作为 autopilot 策略执行的输入；半自动模式下作为
人工门的决策辅助展示。

边界：预评估不是 Claim/EA/gate/signature/evidence artifact——它是旁路产物
（admission-preassessment.json），不影响任何门禁语义，只在人工签署前提供
语义层面的阅读辅助。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import write_json_atomic

PREASSESSMENT_SCHEMA = "admission-preassessment-0.1"

_BOUNDARY = (
    "LLM-generated pre-assessment of the full evidence chain: reading aid for "
    "the human reviewer, NOT a claim, gate, signature or evidence artifact. "
    "The human makes the final decision. In full-auto mode the autopilot reads "
    "this alongside the raw metrics; in semi-auto mode it is shown to the human. "
    "admission-preassessment.json is a side artifact that does not enter "
    "RunCapsule, EA, closure or lineage."
)

_PROMPT_TEMPLATE = """你是一个严谨的科研证据链预评估助手。以下是一次完整研究运行的证据链产物，
请评估其语义一致性、证据质量和需要人工关注的重点。

实验设计：
- 研究问题：{question}
- 主指标：{metric_name}
- 数据集：{dataset_id}
- Seeds：{seeds}

RunCapsule 逐 seed 指标：
{metrics_json}

Claim 断言：
{assertions_json}

Idea 摘要：
{idea_summary}

请提供以下预评估（输出 JSON）：
{{
  "evidence_support": "strong / moderate / weak — 证据是否充分支撑 claim 断言",
  "semantic_consistency": "consistent / partial / inconsistent — idea 的问题与 experiment 设计与 run 结果是否语义一致",
  "gaps": ["发现的信息缺口（如：某指标未在设计中预注册）"],
  "focus_areas": ["建议人工评审重点关注的地方"],
  "reading_guide": "帮助评审快速理解结果的导读（一段话）"
}}

规则：
- 只解读给定的数据，不编造未给出的信息
- seeds 数量不足以得出统计结论时如实说明
- 不建议签署或不签署——那是人的决定
- 如果发现设计与结果之间的语义不一致，必须明确指出
"""


def _read(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _extract_idea_summary(idea: Optional[Dict[str, Any]]) -> str:
    if not idea:
        return "not available"
    candidates = idea.get("candidates") or []
    lines = []
    for c in candidates[:5]:
        if isinstance(c, dict):
            lines.append(
                f"  {c.get('idea_id', '?')}: {str(c.get('title', ''))[:100]} "
                f"| falsification: {str(c.get('falsification', ''))[:80]}"
            )
    return "\n".join(lines) if lines else "no candidates"


def _extract_assertions(claim: Optional[Dict[str, Any]]) -> str:
    assertions = claim.get("assertions") or []
    if not assertions:
        return "no assertions"
    lines = []
    for a in assertions:
        if isinstance(a, dict):
            lines.append(
                f"  {a.get('metric', '?')} {a.get('comparator', '?')} {a.get('value', '?')} "
                f"(observed={a.get('observed', '?')}, status={a.get('status', '?')})"
            )
    return "\n".join(lines)


def build_preassessment_prompt(
    capsule: Dict[str, Any],
    ea: Dict[str, Any],
    claim: Dict[str, Any],
    idea: Dict[str, Any],
    experiment: Dict[str, Any],
) -> str:
    return _PROMPT_TEMPLATE.format(
        question=str(experiment.get("question") or experiment.get("hypothesis") or "not provided")[:200],
        metric_name=str(capsule.get("metric_name") or "unknown"),
        dataset_id=str(capsule.get("dataset_id") or "unknown"),
        seeds=str(capsule.get("seeds") or "unknown"),
        metrics_json=json.dumps(capsule.get("metrics_by_seed") or [], ensure_ascii=False, indent=2),
        assertions_json=_extract_assertions(claim),
        idea_summary=_extract_idea_summary(idea),
    )


def _parse_preassessment(raw: str) -> Dict[str, Any]:
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
    keys = ("evidence_support", "semantic_consistency", "gaps",
            "focus_areas", "reading_guide")
    return {key: payload.get(key) for key in keys if payload.get(key) is not None}


def preassess_admission(
    run_dir: Path,
    *,
    model_port: Any,
) -> Dict[str, Any]:
    """Pre-assess the full evidence chain for the human reviewer at S5b.

    Runs in both full-auto and semi-auto modes — the LLM prepares information,
    the human (or autopilot policy) makes the decision.
    """
    run = Path(run_dir).resolve()

    capsule = _read(run / "run" / "run-capsule.json")
    if not capsule:
        return {
            "schema_version": PREASSESSMENT_SCHEMA,
            "status": "missing_capsule",
            "preassessment": {},
            "boundary": _BOUNDARY,
        }

    ea = _read(run / "run" / "ea.json") or {}
    claim = _read(run / "claim" / "claim.json")
    idea = _read(run / "idea.json")
    experiment = _read(run / "experiment.json") or _read(run / "design" / "experiment.json") or {}

    claim_status = str((claim or {}).get("status") or "absent")
    if claim_status not in ("supported", "approved"):
        return {
            "schema_version": PREASSESSMENT_SCHEMA,
            "status": "no_signed_claim",
            "preassessment": {},
            "boundary": "pre-assessment requires a signed claim; claim status: " + claim_status,
        }

    prompt = build_preassessment_prompt(capsule, ea, claim, idea, experiment)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = model_port.complete(messages, json_mode=True)
    except Exception as exc:
        return {
            "schema_version": PREASSESSMENT_SCHEMA,
            "status": "preassessment_failed",
            "error": str(exc)[:200],
            "boundary": _BOUNDARY,
        }

    parsed = _parse_preassessment(response)
    if not parsed:
        return {
            "schema_version": PREASSESSMENT_SCHEMA,
            "status": "preassessment_unparseable",
            "preassessment": {},
            "boundary": _BOUNDARY,
        }

    out = run / "admission-preassessment.json"
    result = {
        "schema_version": PREASSESSMENT_SCHEMA,
        "status": "preassessed",
        "run_id": run.name,
        "claim_id": str((claim or {}).get("claim_id") or ""),
        "claim_status": claim_status,
        "preassessment": parsed,
        "boundary": _BOUNDARY,
    }
    write_json_atomic(str(out), result)
    return result


def load_preassessment(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Load a previously written admission pre-assessment."""
    path = Path(run_dir) / "admission-preassessment.json"
    return _read(path)

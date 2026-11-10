"""Evidence-grounded innovation proposals with multi-role review iterations.

This module turns a completed S1 run into a bounded innovation review:
proposal -> novelty/evidence/feasibility critics -> revision -> re-review.
It never signs a claim or runs an experiment. Model output is treated as
untrusted until every evidence reference and required field is validated.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .executable import plan_prompt_block, validate_plan
from .guideline_memory import block_for as guideline_block_for
from .independence import evaluate_panel, supply_of
from .project import run_dir
from .storage import write_json_atomic
from .writing_pack import build_writing_pack, load_writing_pack

INNOVATION_SCHEMA = "innovation-review-0.2"
REVIEW_ROLES = ("novelty", "evidence", "feasibility")
REQUIRED_IDEA_FIELDS = (
    "title",
    "problem",
    "mechanism",
    "novelty_claim",
    "falsification",
)
REQUIRED_PLAN_FIELDS = ("profile", "dataset", "baseline", "metric", "stopping_rule")
MAX_CONTEXT_CHARS = 24000


class InnovationReviewError(ValueError):
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
    raise InnovationReviewError("model did not return valid JSON")


def _complete_json(model: Any, messages: List[Dict[str, str]]) -> Any:
    raw = str(model.complete(messages, json_mode=True) or "")
    try:
        return _parse_json(raw)
    except InnovationReviewError:
        repair = list(messages) + [
            {
                "role": "user",
                "content": (
                    "上一次输出不是合法 JSON。请只返回一个合法 JSON 对象，不要 Markdown 代码块、"
                    "不要解释。上一次输出开头：\n" + raw[:6000]
                ),
            }
        ]
        raw2 = str(model.complete(repair, json_mode=True) or "")
        try:
            return _parse_json(raw2)
        except InnovationReviewError as exc:
            raise InnovationReviewError(
                "model did not return valid JSON after repair; raw=%s" % raw2[:2000]
            ) from exc


def plan_levels_block() -> str:
    """Registered levels for every declared factor, so a plan cannot invent a vocabulary.

    Measured on a host-answered ideation run: the prompt named the controls but never their levels,
    and the model proposed archive "on", archive_window "top2" and parent_selection
    "diversity_biased" - all refused later by the runner. Rendered from the same registry the
    pre-flight validates against, so the prompt and the check cannot drift apart.
    """
    from .search_lab import MAX_DESIGN_CELLS, SEARCH_FACTORS

    lines = [
        "\n可声明因子及其合法水平（水平名不在表内会被执行侧直接拒绝；未声明的因子取首水平）："
    ]
    for factor in sorted(SEARCH_FACTORS):
        spec = SEARCH_FACTORS[factor] or {}
        kind = str(spec.get("kind") or "")
        levels = spec.get("levels") or []
        if kind == "boolean":
            shown = "on | off"
        elif kind == "number":
            shown = "任意数值（示意：%s）" % ", ".join(str(value) for value in levels)
        else:
            shown = " | ".join(str(value) for value in levels)
        lines.append("- %s: %s" % (factor, shown))
    lines.append("- 设计格子数上限 %d（各因子水平数相乘，未声明因子按 1 计）" % MAX_DESIGN_CELLS)
    return "\n".join(lines) + "\n"


def _default_model(project: Any = "", run_id: str = "") -> Any:
    """Gateway binding first: a keyless host_agent profile needs no external API key.

    The run is passed down as the turn binding so that a recorded prompt can be attributed to the
    package it produced; without it the ledger keeps the prompt text but no way to say which run
    asked for it, and a submission bundle cannot release its own prompts.
    """
    from .adapters.research_models import default_model_for

    binding = {}
    if project:
        binding["project_dir"] = str(project)
    if run_id:
        binding["run_id"] = str(run_id)
    model, note = default_model_for(
        "idea", purpose="S2-S3 gap and innovation review", binding=binding or None
    )
    if model is None:
        raise InnovationReviewError(note)
    return model


def _pack_context(pack: Dict[str, Any], max_chars: int = MAX_CONTEXT_CHARS) -> str:
    lines = [
        "研究主题: %s" % _clean(pack.get("task", {}).get("goal") or "未提供"),
        "运行: %s" % pack.get("run_id"),
        "来源数量: %d" % len((pack.get("literature") or {}).get("references") or []),
        "",
        "来源卡与证据:",
    ]
    spans_by_source = (pack.get("literature") or {}).get("selected_spans") or {}
    for ref in (pack.get("literature") or {}).get("references") or []:
        ref_id = str(ref.get("ref_id"))
        lines.append(
            "\n[%s] %s (%s, %s)" % (ref_id, ref.get("title"), ref.get("year"), ref.get("venue"))
        )
        if ref.get("abstract"):
            lines.append("摘要: " + _clean(ref.get("abstract"), 700))
        for span in spans_by_source.get(str(ref.get("source_id")), [])[:3]:
            lines.append("证据句: " + _clean(span.get("text"), 500))
    synthesis = (pack.get("literature") or {}).get("synthesis") or {}
    if synthesis.get("themes"):
        lines += ["", "跨来源综合主题:"]
        for theme in synthesis.get("themes") or []:
            refs = ", ".join(
                str(item.get("ref_id")) for item in theme.get("stances") or []
            )
            lines.append(
                "- %s %s | refs=%s | confidence=%s"
                % (theme.get("theme_id"), theme.get("name"), refs, theme.get("confidence"))
            )
            lines.append("  一致: " + _clean(theme.get("agreement"), 300))
            lines.append("  张力: " + _clean(theme.get("tension"), 300))
    lines += ["", "覆盖缺口:"]
    for gap in (pack.get("literature") or {}).get("gaps") or []:
        if isinstance(gap, dict):
            lines.append("- %s: %s" % (gap.get("code"), gap.get("message")))
        else:
            lines.append("- " + str(gap))
    text = "\n".join(lines)
    return text[:max_chars]


def _idea_id(index: int) -> str:
    return "IDEA-%02d" % index


def _ref_tokens(value: Any) -> List[str]:
    tokens: List[str] = []
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = re.split(r"[,;，；\s]+", value)
    else:
        raw = []
    for item in raw:
        text = str(item or "").strip().strip("[](){}<>").upper()
        match = re.search(r"REF[-_ ]?([0-9]+)", text)
        if match:
            text = "REF-%02d" % int(match.group(1))
        if text and text not in tokens:
            tokens.append(text)
    return tokens


def _normalise_gaps(
    payload: Any,
    ref_ids: set,
    ref_sources: Dict[str, str],
    warnings: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    raw = payload.get("gaps") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raise InnovationReviewError("model output must contain a gaps array")
    gaps: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, item in enumerate(raw[:8], 1):
        if not isinstance(item, dict):
            continue
        refs = _ref_tokens(item.get("evidence_refs"))
        valid_refs = [ref for ref in refs if ref in ref_ids]
        gap = {
            "gap_id": "GAP-%02d" % index,
            "description": _clean(item.get("description"), 600),
            "why_unresolved": _clean(item.get("why_unresolved"), 600),
            "observable": _clean(item.get("observable"), 400),
            "evidence_refs": valid_refs,
        }
        problem = ""
        distinct_sources = {ref_sources.get(ref) for ref in valid_refs if ref_sources.get(ref)}
        if not gap["description"] or not gap["why_unresolved"] or not gap["observable"]:
            problem = "%s missing description/why_unresolved/observable" % gap["gap_id"]
        elif len(valid_refs) < 2 or len(distinct_sources) < 2:
            problem = (
                "%s needs >=2 refs from >=2 distinct papers; got %d refs / %d sources"
                % (gap["gap_id"], len(valid_refs), len(distinct_sources))
            )
        if problem:
            errors.append(problem)
            continue
        gaps.append(gap)
    if warnings is not None:
        warnings.extend(errors)
    if len(gaps) < 2:
        raise InnovationReviewError(
            "at least 2 evidence-grounded gaps are required; " + "; ".join(errors[:8])
        )
    return gaps


def _normalise_design(value: Any) -> Dict[str, List[Any]]:
    if not isinstance(value, dict):
        return {}
    design: Dict[str, List[Any]] = {}
    for name, levels in value.items():
        if isinstance(levels, list) and levels:
            # Keep JSON scalars (true/false/0.02) as-is: the runner compares levels against
            # its registry, and "True" is not the boolean level it accepts.
            design[str(name)] = list(levels)
    return design


def _normalise_ideas(
    payload: Any,
    ref_ids: set,
    ref_sources: Dict[str, str],
    warnings: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    raw = payload.get("ideas") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raise InnovationReviewError("model output must contain an ideas array")
    ideas: List[Dict[str, Any]] = []
    errors: List[str] = []
    for index, item in enumerate(raw[:8], 1):
        if not isinstance(item, dict):
            errors.append("idea %d is not an object" % index)
            continue
        idea = {
            "idea_id": _idea_id(index),
            "title": _clean(item.get("title"), 200),
            "problem": _clean(item.get("problem"), 600),
            "mechanism": _clean(item.get("mechanism"), 900),
            "novelty_claim": _clean(item.get("novelty_claim"), 700),
            "falsification": _clean(item.get("falsification"), 500),
            "experiment_plan": {},
            "evidence_refs": [],
            "risks": [_clean(risk, 300) for risk in (item.get("risks") or []) if _clean(risk)][:5],
            "revision_notes": [],
        }
        plan = item.get("experiment_plan") if isinstance(item.get("experiment_plan"), dict) else {}
        idea["experiment_plan"] = {
            key: _clean(plan.get(key), 300) for key in REQUIRED_PLAN_FIELDS
        }
        raw_design = plan.get("design")
        if isinstance(raw_design, dict) and raw_design:
            # The runner reads factor levels from this dict; a plan that names factors only in
            # prose would otherwise execute the default memory x gate design.
            idea["experiment_plan"]["design"] = _normalise_design(raw_design)
        executable = validate_plan(idea["experiment_plan"])
        # validate_plan checks profile, dataset and metric but never looks at the declared design,
        # so plans whose levels or cell count the runner will refuse passed pre-flight and burned a
        # round before failing (measured: archive ["off","on"], archive_window ["all","top2"], a
        # 16-cell design). normalize_design is the runner's own rule, so this adds no second
        # vocabulary: the same coercion that accepts "on"/"off" for a boolean factor still applies.
        plan = idea["experiment_plan"] or {}
        try:
            from .search_lab import normalize_design

            cleaned = normalize_design(
                plan.get("design") or None, float(plan.get("min_delta") or 0.005)
            )
            cells = 1
            for values in cleaned.values():
                cells *= len(values)
            executable = dict(executable, cells=cells)
        except ValueError as exc:
            executable = dict(
                executable,
                ok=False,
                reasons=list(executable.get("reasons") or []) + [str(exc)],
            )
        idea["executable"] = executable
        refs = _ref_tokens(item.get("evidence_refs"))
        unknown = [ref for ref in refs if ref not in ref_ids]
        idea["evidence_refs"] = [ref for ref in refs if ref in ref_ids]
        missing = [key for key in REQUIRED_IDEA_FIELDS if not idea[key]]
        missing_plan = [key for key in REQUIRED_PLAN_FIELDS if not idea["experiment_plan"][key]]
        problems = []
        if unknown:
            problems.append("unknown evidence refs: " + ", ".join(unknown))
        if len(idea["evidence_refs"]) < 2:
            problems.append("needs at least 2 valid evidence refs")
        distinct_sources = {
            ref_sources.get(ref) for ref in idea["evidence_refs"] if ref_sources.get(ref)
        }
        if len(distinct_sources) < 2:
            problems.append("needs evidence from at least 2 distinct papers")
        if missing:
            problems.append("missing fields: " + ", ".join(missing))
        if missing_plan:
            problems.append("missing experiment plan fields: " + ", ".join(missing_plan))
        if not executable.get("ok"):
            problems.append("not executable here: " + "; ".join(executable.get("reasons") or []))
        if problems:
            errors.append("%s %s" % (idea["idea_id"], "; ".join(problems)))
            continue
        ideas.append(idea)
    if warnings is not None:
        warnings.extend(errors)
    if len(ideas) < 3:
        raise InnovationReviewError(
            "at least 3 valid ideas are required; " + "; ".join(errors[:8])
        )
    return ideas


def _parse_reviews(payload: Any, idea_ids: Sequence[str], role: str) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise InnovationReviewError("review output must be an object")
    raw = payload.get("scores")
    if not isinstance(raw, list):
        raise InnovationReviewError("review output must contain scores")
    scores: Dict[str, Dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        idea_id = str(item.get("idea_id") or "")
        if idea_id not in idea_ids:
            continue
        try:
            score = float(item.get("score"))
        except (TypeError, ValueError):
            continue
        scores[idea_id] = {
            "score": max(1.0, min(10.0, score)),
            "strengths": [_clean(value, 300) for value in item.get("strengths") or []][:5],
            "weaknesses": [_clean(value, 300) for value in item.get("weaknesses") or []][:5],
            "must_fix": [_clean(value, 300) for value in item.get("must_fix") or []][:5],
        }
    missing = [idea_id for idea_id in idea_ids if idea_id not in scores]
    if missing:
        raise InnovationReviewError(
            "%s reviewer omitted ideas: %s" % (role, ", ".join(missing))
        )
    return {"role": role, "scores": scores, "overall": _clean(payload.get("overall"), 1200)}


def _propose(
    pack: Dict[str, Any],
    model: Any,
    max_ideas: int,
    seed_direction: str = "",
    ref_sources: Optional[Dict[str, str]] = None,
    guidance: str = "",
    language: str = "zh",
) -> tuple:
    ref_ids = {
        str(ref.get("ref_id"))
        for ref in (pack.get("literature") or {}).get("references") or []
    }
    context = _pack_context(pack)
    ref_sources = ref_sources or {}
    system = (
        "你是严谨的科研创新评审主席。你只能使用给定的来源卡与证据句，不得编造论文、"
        "数据集、结果或引用。每个创新点必须可证伪、可在本地实验中检验，并明确说明"
        "与已有工作的差异。输出必须是合法 JSON。"
    )
    direction = (
        "\n研究主方向（必须围绕它形成统一机制，允许批判性修正）：%s\n"
        % _clean(seed_direction, 1200)
    ) if seed_direction else ""
    # The prompt stays Chinese because it is an instruction, not an artifact; the language of the
    # *returned fields* is a request parameter. Rule 8 used to be hard-coded to Chinese, which made
    # 0 of 11 idea artifacts readable by an English venue rubric (measured: covered=0, degraded).
    language_rule = (
        "Write every field you return — each gap's description/why_unresolved/observable and each "
        "idea's title, problem, mechanism, novelty_claim, falsification, risks and "
        "experiment_plan strings — in English."
        if str(language).strip().lower() == "en"
        else "使用中文。"
    )
    user = """先阅读下列顶会文献证据，识别 3-6 个真正未解决的缺口，再基于缺口提出 %d 个候选创新点。%s

要求：
1. 每个缺口和每个创新点都必须引用至少 2 个 REF，且这 2 个 REF 必须来自两篇不同论文；不能引用不存在的 REF。
2. evidence_refs 必须是数组，元素写成 REF-01 这样的独立字符串；不要写 "REF-01, REF-02" 这种逗号字符串。
3. 不能声称已经取得实验结果；实验计划只写设计。
4. 说明问题、机制、与已有工作的差异、可证伪预测、数据集/基线/指标/停止规则、风险。
5. 优先选择证据中反复出现但尚未被统一解决的缺口，不要做泛泛的“结合 A+B”。
6. 禁止“在 benchmark A 上加入 B”的拼接式想法；每个想法必须提出新的可测量对象、协议或控制机制。
7. 每个想法写出它挑战的两个最近来源的共同假设，以及打破该假设后应观察到什么。
8. %s
9. 实验计划的 profile 必须从下列**本运行时真正能执行**的档位中选择，dataset 与 metric 必须是该档位列出的值；不在档位内的计划会被直接拒绝，不要写无法在本系统执行的实验。若计划要检验注册因子，必须在 experiment_plan.design 中声明 {因子: [水平...]}；runner 不会从 stopping_rule 推断因子，缺 design 而文本又提到注册因子会被拒绝。
%s

%s
输出 JSON:
{"gaps":[{"description":"","why_unresolved":"","observable":"","evidence_refs":["REF-01"]}],
 "ideas":[{"title":"","problem":"","mechanism":"","novelty_claim":"","falsification":"","experiment_plan":{"profile":"","dataset":"","baseline":"","metric":"","stopping_rule":"","design":{}},"evidence_refs":["REF-01","REF-02"],"risks":[""]}]}

可用来源与证据：
%s""" % (max_ideas, direction, language_rule, plan_prompt_block() + plan_levels_block(), guidance or "", context)
    raw = model.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        json_mode=True,
    )
    warnings: List[str] = []
    try:
        payload = _parse_json(raw)
        return (
            _normalise_gaps(payload, ref_ids, ref_sources, warnings),
            _normalise_ideas(payload, ref_ids, ref_sources, warnings),
            warnings,
        )
    except InnovationReviewError as first_error:
        repair = (
            "上一次输出未通过字段校验：%s。请修复并只返回合法 JSON；不得新增不存在的 REF。\n\n"
            "上一次输出：\n%s\n\n可用来源：\n%s"
            % (first_error, raw[:12000], context[:16000])
        )
        raw2 = model.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": repair}],
            json_mode=True,
        )
        try:
            payload2 = _parse_json(raw2)
            return (
                _normalise_gaps(payload2, ref_ids, ref_sources, warnings),
                _normalise_ideas(payload2, ref_ids, ref_sources, warnings),
                warnings,
            )
        except InnovationReviewError as second_error:
            raise InnovationReviewError(
                "%s | first_error=%s | raw=%s"
                % (second_error, first_error, raw2[:2000])
            ) from second_error


PRIOR_ART_LIMIT = 6
PRIOR_ART_OVERLAP = 0.25

PRIOR_ART_BOUNDARY = (
    "reviewer-side retrieval: the critic searched for prior art with each idea's own mechanism "
    "wording after generation, so these hits are not the generator's chosen evidence set; lexical "
    "overlap is a pointer for the critic and never a proof of non-novelty, and hits already present "
    "in the generator's set are marked so independence is not assumed"
)

PRIOR_ART_SCOPE = (
    "already_in_generator_set is decided against the writing pack's cited sources only; the S2 "
    "prior-art search recorded on the IdeaCard as prior_art_refs (span ids, not carried into the "
    "critic payload) is not part of that comparison, so independent_sources is an upper bound and "
    "a hit the generator saw and dismissed may still be counted here"
)


def _ascii_tokens(text: Any) -> set:
    return set(
        token
        for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", str(text or "").lower())
        if len(token) > 2
    )


def _prior_art_check(
    ideas: List[Dict[str, Any]],
    retriever: Any,
    generator_source_ids: set,
    limit: int = PRIOR_ART_LIMIT,
) -> Dict[str, Any]:
    """What a reviewer finds when it looks for refuting prior art on its own.

    The novelty critic otherwise scores ideas against the very sources the generator selected,
    which makes the evidence set self-chosen; this retrieval is driven by the idea text and is
    reported separately, with generator overlap made visible instead of presumed away.
    """
    if retriever is None:
        return {
            "available": False,
            "reason": (
                "no reviewer-side retriever: novelty was judged only against the generator's "
                "own evidence set"
            ),
            "boundary": PRIOR_ART_BOUNDARY,
        }
    rows: List[Dict[str, Any]] = []
    lines: List[str] = []
    for idea in ideas:
        query = " ".join(
            [
                str(idea.get("title") or ""),
                str(idea.get("mechanism") or ""),
                str(idea.get("novelty_claim") or ""),
            ]
        )
        tokens = _ascii_tokens(query)
        try:
            hits = list(retriever.search(query[:400], int(limit)) or [])
        except Exception as exc:
            return {
                "available": False,
                "reason": "reviewer-side retrieval failed: %s" % exc,
                "boundary": PRIOR_ART_BOUNDARY,
            }
        for hit in hits:
            source_id = str(getattr(hit, "source_id", "") or "")
            text = " ".join(
                [str(getattr(hit, "title", "") or ""), str(getattr(hit, "abstract", "") or "")]
            )
            overlap = len(_ascii_tokens(text) & tokens) / float(max(1, len(tokens)))
            row = {
                "idea_id": idea.get("idea_id"),
                "source_id": source_id,
                "title": str(getattr(hit, "title", "") or "")[:180],
                "overlap": round(overlap, 4),
                "also_in_generator_set": source_id in generator_source_ids,
                "fixture": bool(getattr(hit, "fixture", True)),
            }
            rows.append(row)
            lines.append(
                "- %s [%s] | %s | overlap=%.3f | 已在生成方集合=%s | fixture=%s"
                % (
                    row["idea_id"],
                    row["source_id"],
                    row["title"],
                    row["overlap"],
                    row["also_in_generator_set"],
                    row["fixture"],
                )
            )
    return {
        "available": bool(rows),
        "queries": len(ideas),
        "sources": len(rows),
        "independent_sources": sum(1 for row in rows if not row["also_in_generator_set"]),
        "with_overlap": sum(1 for row in rows if row["overlap"] >= PRIOR_ART_OVERLAP),
        "independent_sources_are_upper_bound": True,
        "independence_scope": PRIOR_ART_SCOPE,
        "hits": rows,
        "text": "\n".join(lines),
        "reviewer_retrieved": True,
        "boundary": PRIOR_ART_BOUNDARY,
    }


def _review(
    role: str,
    ideas: List[Dict[str, Any]],
    context: str,
    model: Any,
    round_index: int,
    prior_art: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    role_prompts = {
        "novelty": (
            "你是 novelty 审稿人。逐个判断想法相对给定顶会语料是否真的不同；"
            "如果只是已有工作的措辞重排，或可以概括为“在 benchmark A 上加入 B”，"
            "给 4 分或更低。必须指出最接近的已有方向、它们共享的假设以及重叠点。"
        ),
        "evidence": (
            "你是 evidence 审稿人。逐个检查 evidence_refs 是否真的支持该机制，并检查是否来自至少两篇不同论文；"
            "只引用同一篇论文、把单篇结论当领域共识、或把摘要当结论都要扣分。"
        ),
        "feasibility": (
            "你是 feasibility 审稿人。逐个检查数据集、基线、指标、停止规则是否可在本地"
            "小规模实验中执行；不可测量、没有基线或没有否证条件的想法给低分。"
        ),
    }
    idea_payload = [
        {
            "idea_id": idea["idea_id"],
            "title": idea["title"],
            "problem": idea["problem"],
            "mechanism": idea["mechanism"],
            "novelty_claim": idea["novelty_claim"],
            "falsification": idea["falsification"],
            "experiment_plan": idea["experiment_plan"],
            "executability_check": idea.get("executable") or {},
            "evidence_refs": idea["evidence_refs"],
        }
        for idea in ideas
    ]
    system = role_prompts[role] + " 输出必须是合法 JSON，不得编造来源或结果。"
    if role == "feasibility":
        # Without the registry this critic scores plans it cannot see the limits of, and it
        # rates an unexecutable plan highly as long as it merely sounds measurable.
        system += (
            "\n本运行时可执行的实验档位如下，评分必须以它为准；"
            "计划的 profile/dataset/metric 不在档位内即为不可执行，最多给 3 分：\n"
            + plan_prompt_block()
            + plan_levels_block()
            + "\n每个想法已带 executability_check（代码层校验结果）；"
            "它与你的判断冲突时以代码层为准，并在 must_fix 中指出应改绑哪个档位。"
        )
    user = """第 %d 轮评审。请按 1-10 分评估每个想法，并给出 strengths/weaknesses/must_fix。

候选想法：
%s

来源与证据：
%s

输出 JSON:
{"scores":[{"idea_id":"IDEA-01","score":1,"strengths":[""],"weaknesses":[""],"must_fix":[""]}],"overall":""}
""" % (
        round_index,
        json.dumps(idea_payload, ensure_ascii=False, indent=2),
        context[:14000],
    )
    if role == "novelty" and (prior_art or {}).get("available"):
        user += (
            "\n\n评审方独立检索到的可能反证来源（与生成方证据集分离，overlap 只是指针不是结论）：\n%s\n"
            "逐条判定：若某来源已做过该想法声称的机制，必须在 weaknesses/must_fix 里点名该来源并说明"
            "共享假设与重叠点；若未做过，也必须显式写出为何不同。无视这些命中仍给高分，视为无效评审。\n"
            % str((prior_art or {}).get("text") or "")[:6000]
        )
    payload = _complete_json(
        model,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    review = _parse_reviews(payload, [idea["idea_id"] for idea in ideas], role)
    # Attribute the scores to the supply that produced them; a panel that cannot say who scored
    # what is not auditable after the fact.
    review["supply"] = supply_of(model)
    if role == "novelty":
        # Whether the critic had independent prior art to attack is part of the verdict's meaning,
        # so it travels with the review instead of living only in the caller.
        review["prior_art"] = (
            {key: value for key, value in (prior_art or {}).items() if key not in ("text", "hits")}
            if (prior_art or {}).get("available")
            else {
                "available": False,
                "reason": (
                    "no reviewer-side retriever: novelty was judged only against the generator's "
                    "own evidence set"
                ),
            }
        )
    return review


def _aggregate(
    ideas: List[Dict[str, Any]], reviews: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    rows = []
    for idea in ideas:
        per_role = {
            review["role"]: review["scores"][idea["idea_id"]] for review in reviews
        }
        average = sum(item["score"] for item in per_role.values()) / max(1, len(per_role))
        rows.append(
            {
                "idea_id": idea["idea_id"],
                "title": idea["title"],
                "average_score": round(average, 3),
                "scores": {role: per_role[role]["score"] for role in per_role},
                "must_fix": sorted(
                    {
                        fix
                        for item in per_role.values()
                        for fix in item.get("must_fix") or []
                    }
                ),
            }
        )
    return sorted(rows, key=lambda row: (-row["average_score"], row["idea_id"]))


def _revise(
    ideas: List[Dict[str, Any]],
    reviews: Sequence[Dict[str, Any]],
    context: str,
    model: Any,
    ref_sources: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    ref_ids = set()
    for match in re.finditer(r"\[(REF-[0-9]{2,})\]", context):
        ref_ids.add(match.group(1))
    system = (
        "你是创新点作者。根据三位审稿人的 must_fix 修订想法。只能保留原有 REF 证据，"
        "不得新增来源，不得声称已有实验结果，不得降低可证伪性。输出合法 JSON。"
    )
    user = """请修订以下想法，保留 idea_id，返回完整 ideas 数组。

规则：
- 如果 novelty 分数低于 7，允许替换机制和标题，不要只做措辞润色。
- 任何替换必须继续使用至少 2 个已有 REF，并明确说明为什么不是“A+B”拼接。
- 不得新增来源，不得声称已有实验结果，不得降低可证伪性。

原想法：
%s

审稿意见：
%s

可用来源与证据：
%s

输出 JSON 结构与原想法相同；每个想法增加 revision_notes 数组说明改了什么。
""" % (
        json.dumps(ideas, ensure_ascii=False, indent=2)[:14000],
        json.dumps(reviews, ensure_ascii=False, indent=2)[:10000],
        context[:14000],
    )
    payload = _complete_json(
        model,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    revised = _normalise_ideas(payload, ref_ids, ref_sources or {})
    for index, idea in enumerate(revised, 1):
        idea["idea_id"] = _idea_id(index)
    return revised


def _independence(
    models_by_role: Dict[str, Any],
    proposer: Any,
    roles: List[str],
    rounds_completed: int,
    answered_by: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Say plainly whether the critics were actually independent, and what would change that.

    The three roles are three prompts, not three reviewers, when one model answers them all.
    Measured earlier: the same host both proposed these ideas and scored them, and moving the
    threshold alone flipped the verdict from needs_more_work to reviewed.
    """
    if answered_by is None:
        answered_by = {}
        for role in roles:
            probe = getattr(models_by_role.get(role), "answered_by", None)
            if callable(probe):
                answered_by[role] = list(probe() or [])
    return evaluate_panel(
        list(roles),
        dict(models_by_role),
        proposer=proposer,
        rounds=rounds_completed,
        answered_by=answered_by,
    )


def run_innovation_review(
    project: Path,
    run_id: str,
    *,
    topic: str = "",
    direction: str = "",
    rounds: int = 2,
    max_ideas: int = 5,
    threshold: float = 8.0,
    model: Any = None,
    critic_models: Optional[Dict[str, Any]] = None,
    output_dir: Optional[Path] = None,
    use_guidance: bool = True,
    propose_only: bool = False,
    prior_art_corpus: Optional[Path] = None,
    prior_art_limit: int = PRIOR_ART_LIMIT,
    language: str = "zh",
) -> Dict[str, Any]:
    language = str(language or "zh").strip().lower()
    if language not in ("zh", "en"):
        raise InnovationReviewError(
            "innovation review language must be zh or en; the idea fields are written in the "
            "requested language, so an unvalidated value would silently produce artifacts no "
            "venue rubric can read: %r" % language
        )
    project = Path(project).resolve()
    target = run_dir(project, run_id)
    if not target.is_dir():
        raise InnovationReviewError("run does not exist: " + run_id)
    model = model or _default_model(project, run_id)
    assigned = dict(critic_models or {})
    unknown_roles = sorted(set(assigned) - set(REVIEW_ROLES))
    if unknown_roles:
        raise InnovationReviewError(
            "unknown critic role(s): %s; expected %s"
            % (", ".join(unknown_roles), ", ".join(REVIEW_ROLES))
        )
    models_by_role = {role: (assigned.get(role) or model) for role in REVIEW_ROLES}
    pack = load_writing_pack(project, run_id) or build_writing_pack(
        project,
        run_id,
        language=language,
        venue="en_conference",
        max_sources=16,
        max_spans_per_source=3,
    )
    if not topic:
        try:
            demo = json.loads((target / "demo.json").read_text(encoding="utf-8"))
            topic = str(demo.get("topic") or "") if isinstance(demo, dict) else ""
        except (OSError, ValueError):
            topic = ""
    if topic:
        task = pack.setdefault("task", {})
        if isinstance(task, dict) and not task.get("goal"):
            # The pipeline demo carries the topic; a pack with task.goal=null made every
            # innovation prompt say "研究主题: 未提供".
            task["goal"] = topic
    references = (pack.get("literature") or {}).get("references") or []
    if len(references) < 3:
        raise InnovationReviewError("at least 3 references are required for innovation review")
    if not any(((pack.get("literature") or {}).get("selected_spans") or {}).values()):
        raise InnovationReviewError("no selected full-text spans; innovation review needs evidence")
    rounds = max(1, min(int(rounds), 5))
    max_ideas = max(3, min(int(max_ideas), 8))
    threshold = max(0.0, min(float(threshold), 10.0))
    context = _pack_context(pack)
    ref_sources = {
        str(ref.get("ref_id")): str(ref.get("source_id"))
        for ref in references
        if ref.get("ref_id") and ref.get("source_id")
    }
    gaps, ideas, validation_warnings = _propose(
        pack,
        model,
        max_ideas,
        direction,
        ref_sources,
        guidance=guideline_block_for(project) if use_guidance else "",
        language=language,
    )
    prior_art: Optional[Dict[str, Any]] = None
    if prior_art_corpus:
        from .adapters.real_corpus_retriever import RealCorpusRetriever, RealCorpusError

        try:
            retriever = RealCorpusRetriever(Path(prior_art_corpus))
        except (OSError, ValueError, RealCorpusError) as exc:
            raise InnovationReviewError(
                "reviewer-side prior-art corpus is unusable: %s; it must be a real CC-BY corpus "
                "marked corpus_kind=real with full text (a fixture corpus cannot refute novelty, "
                "it can only echo the generator)" % exc
            )
        prior_art = _prior_art_check(
            ideas,
            retriever,
            {str(ref.get("source_id")) for ref in references if ref.get("source_id")},
            limit=prior_art_limit,
        )
    if propose_only:
        # The A/B question is "did the guideline block change the ideas", which is answerable
        # without spending a model call on every critic role.
        write_json_atomic(
            (Path(output_dir) if output_dir else target) / "proposal.json",
            {
                "schema_version": INNOVATION_SCHEMA,
                "status": "proposed_only",
                "run_id": run_id,
                "topic": str(topic or ""),
                "guidance_chars": len(guideline_block_for(project)) if use_guidance else 0,
                "gaps": gaps,
                "selected_ideas": ideas,
                "validation_warnings": validation_warnings,
                "boundary": (
                    "generation-only output: no critic panel ran, nothing here is a verdict, and "
                    "it never reaches a claim, a gate or an exported number"
                ),
            },
        )
        return {
            "schema_version": INNOVATION_SCHEMA,
            "status": "proposed_only",
            "rounds": 0,
            "ideas": len(ideas),
            "gaps": len(gaps),
            "guidance_chars": len(guideline_block_for(project)) if use_guidance else 0,
            "proposal_file": str((Path(output_dir) if output_dir else target) / "proposal.json"),
            "next": "score the two arms with `memory ab record --arm with|without --ideas-file <proposal.json>`",
        }
    iterations = []
    best_rows: List[Dict[str, Any]] = []
    for round_index in range(1, rounds + 1):
        reviews = [
            _review(role, ideas, context, models_by_role[role], round_index, prior_art=prior_art)
            for role in REVIEW_ROLES
        ]
        rows = _aggregate(ideas, reviews)
        best_rows = rows
        iterations.append(
            {
                "round": round_index,
                "ideas": ideas,
                "reviews": reviews,
                "ranking": rows,
                "overall": round(
                    sum(row["average_score"] for row in rows) / max(1, len(rows)), 3
                ),
            }
        )
        if round_index < rounds and all(row["average_score"] >= threshold for row in rows):
            break
        if round_index < rounds:
            ideas = _revise(ideas, reviews, context, model, ref_sources)

    top = best_rows[:3]
    selected_ids = {row["idea_id"] for row in top}
    selected = [idea for idea in ideas if idea["idea_id"] in selected_ids]
    status = "reviewed" if top and top[0]["average_score"] >= threshold else "needs_more_work"
    result = {
        "schema_version": INNOVATION_SCHEMA,
        "run_id": run_id,
        "topic": topic or _clean(pack.get("task", {}).get("goal")),
        "direction": _clean(direction, 1200),
        "rounds_requested": rounds,
        "rounds_completed": len(iterations),
        "model": getattr(model, "model_id", type(model).__name__),
        "independence": _independence(
            models_by_role, model, list(REVIEW_ROLES), len(iterations)
        ),
        "status": status,
        "threshold": threshold,
        "evidence_refs": [ref.get("ref_id") for ref in references],
        "evidence_source_count": len(ref_sources),
        "gaps": gaps,
        "validation_warnings": validation_warnings,
        "final_ideas": ideas,
        "selected_ideas": selected,
        "ranking": top,
        "iterations": [
            {
                "round": item["round"],
                "overall": item["overall"],
                "ranking": item["ranking"],
                "reviews": item["reviews"],
            }
            for item in iterations
        ],
        "boundary": (
            "Innovation review is a model-assisted design critique over a bounded local corpus. "
            "It is not novelty proof, peer review, an experiment result or a claim. "
            "No Claim/EA/gate/signature is created; human review remains required."
        ),
    }
    destination = Path(output_dir) if output_dir else target
    destination.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination / "innovation-review.json", result)
    with open(str(destination / "innovation-iterations.jsonl"), "w", encoding="utf-8", newline="\n") as handle:
        for item in iterations:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    lines = [
        "# Innovation Review",
        "",
        "- run: `%s`" % run_id,
        "- topic: %s" % result["topic"],
        "- model: `%s`" % result["model"],
        "- rounds: %d" % result["rounds_completed"],
        "- status: **%s**" % result["status"],
        "",
        "## Score progression",
        "",
    ]
    if validation_warnings:
        lines.append("- dropped invalid ideas: " + "; ".join(validation_warnings[:8]))
        lines.append("")
    for item in iterations:
        lines.append("- round %d: overall %.2f" % (item["round"], item["overall"]))
    lines += ["", "## Identified gaps", ""]
    for gap in gaps:
        lines.append(
            "- %s %s (evidence: %s)"
            % (gap["gap_id"], gap["description"], ", ".join(gap["evidence_refs"]))
        )
    lines += ["", "## Selected ideas", ""]
    for row in top:
        idea = next(item for item in ideas if item["idea_id"] == row["idea_id"])
        lines += [
            "### %s %s (%.2f)" % (idea["idea_id"], idea["title"], row["average_score"]),
            "",
            "- problem: %s" % idea["problem"],
            "- mechanism: %s" % idea["mechanism"],
            "- novelty: %s" % idea["novelty_claim"],
            "- falsification: %s" % idea["falsification"],
            "- evidence: %s" % ", ".join(idea["evidence_refs"]),
            "- plan: %s" % json.dumps(idea["experiment_plan"], ensure_ascii=False),
            "- must_fix: %s" % "; ".join(row["must_fix"]),
            "",
        ]
    lines += [
        "## Boundary",
        "",
        result["boundary"],
        "",
    ]
    (destination / "innovation-report.md").write_text("\n".join(lines), encoding="utf-8")
    return result

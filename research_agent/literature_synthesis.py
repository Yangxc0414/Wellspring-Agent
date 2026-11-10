"""Multi-source literature synthesis.

Turns a completed S1 run into a theme-by-source matrix with explicit
agreement, tension and evidence spans. The model proposes themes; the
deterministic layer validates source coverage and attaches spans. Every theme
must cover at least two distinct papers, and unused papers are reported rather
than silently dropped.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .project import run_dir
from .storage import write_json_atomic
from .writing_pack import build_writing_pack, load_writing_pack

SYNTHESIS_SCHEMA = "literature-synthesis-0.1"
STANCES = ("supports", "qualifies", "contradicts", "mixed")
MAX_CONTEXT_CHARS = 24000


class SynthesisError(ValueError):
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
    raise SynthesisError("model did not return valid JSON")


def default_synthesis_model() -> Any:
    from .adapters.deepseek_model import DeepSeekModel, ModelConfigError

    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SynthesisError(
            "literature synthesis requires DEEPSEEK_API_KEY or an injected model port"
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
        raise SynthesisError(str(exc)) from exc


def _source_map(pack: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    records = {}
    for index, ref in enumerate((pack.get("literature") or {}).get("references") or [], 1):
        source_id = str(ref.get("source_id") or "")
        if not source_id:
            continue
        records[source_id] = {
            "alias": "S%d" % index,
            "ref_id": ref.get("ref_id"),
            "title": _clean(ref.get("title"), 220),
            "venue": _clean(ref.get("venue"), 100),
            "year": ref.get("year"),
            "abstract": _clean(ref.get("abstract"), 650),
            "spans": (pack.get("literature") or {}).get("selected_spans", {}).get(source_id, [])[:3],
        }
    return records


def _context(sources: Dict[str, Dict[str, Any]]) -> str:
    lines = []
    for source_id, item in sources.items():
        lines.append(
            "\n[%s | %s] %s (%s, %s)"
            % (source_id, item["ref_id"], item["title"], item["venue"], item["year"])
        )
        if item["abstract"]:
            lines.append("摘要: " + item["abstract"])
        for span in item["spans"]:
            lines.append("- 证据(%s): %s" % (span.get("span_id") or "span", _clean(span.get("text"), 450)))
    return "\n".join(lines)[:MAX_CONTEXT_CHARS]


def _prompt(sources: Dict[str, Dict[str, Any]], max_themes: int) -> List[Dict[str, str]]:
    system = (
        "你是严谨的文献综合评审主席。你只能使用给定的来源卡与证据句，不能编造论文、"
        "数据集、结果或引用。你的任务不是逐篇摘要，而是跨来源综合。输出必须是合法 JSON。"
    )
    user = """阅读下列多篇顶会文献证据，生成 4–%d 个跨来源主题。

要求：
1. 每个主题必须综合至少 2 篇不同来源；source_ids 写内部 S 标识。
2. 标注每篇来源在该主题中的 stance：supports / qualifies / contradicts / mixed。
3. 写出跨来源的一致点（agreement）、张力或未解决冲突（tension）、以及结论强度（confidence）。
4. 不得把单篇论文的结论写成领域共识；证据不足时必须降低 confidence。
5. 未使用的来源放入 unused_sources，并给出原因；不要静默丢弃。
6. 不得新增来源、证据或数值。

输出 JSON:
{"themes":[{"name":"","summary":"","source_ids":["S1","S2"],"stances":[{"source_id":"S1","stance":"supports"}],"agreement":"","tension":"","confidence":"high|medium|low"}],
 "unused_sources":[{"source_id":"S1","reason":""}]}

来源与证据：
%s""" % (max_themes, _context(sources))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _source_aliases(sources: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    aliases = {}
    for source_id, item in sources.items():
        for value in (source_id, item.get("ref_id"), item.get("alias")):
            if value:
                aliases[str(value).strip().upper()] = source_id
    return aliases


def _resolve_source(value: Any, aliases: Dict[str, str]) -> str:
    return aliases.get(str(value or "").strip().upper(), "")


def _validate(
    payload: Any,
    sources: Dict[str, Dict[str, Any]],
    max_themes: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    raw = payload.get("themes") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raise SynthesisError("model output must contain a themes array")
    warnings: List[str] = []
    themes: List[Dict[str, Any]] = []
    used = set()
    aliases = _source_aliases(sources)
    for index, item in enumerate(raw[:max_themes + 2], 1):
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"), 160)
        summary = _clean(item.get("summary"), 900)
        source_ids = []
        for raw_source in item.get("source_ids") or []:
            source_id = _resolve_source(raw_source, aliases)
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)
        if not name or not summary or len(source_ids) < 2:
            warnings.append("theme %d dropped: needs name/summary and >=2 distinct sources" % index)
            continue
        stances = []
        stance_map = {}
        for stance in item.get("stances") or []:
            if not isinstance(stance, dict):
                continue
            source_id = _resolve_source(stance.get("source_id"), aliases)
            label = str(stance.get("stance") or "mixed").lower()
            if source_id in source_ids and label in STANCES:
                stance_map[source_id] = label
        for source_id in source_ids:
            evidence = [
                {"span_id": span.get("span_id"), "text": _clean(span.get("text"), 420)}
                for span in sources[source_id]["spans"][:2]
            ]
            stances.append(
                {
                    "source_id": source_id,
                    "ref_id": sources[source_id]["ref_id"],
                    "stance": stance_map.get(source_id, "mixed"),
                    "evidence": evidence,
                }
            )
            used.add(source_id)
        themes.append(
            {
                "theme_id": "TH-%02d" % (len(themes) + 1),
                "name": name,
                "summary": summary,
                "source_count": len(source_ids),
                "stances": stances,
                "agreement": _clean(item.get("agreement"), 700),
                "tension": _clean(item.get("tension"), 700),
                "confidence": str(item.get("confidence") or "low").lower()
                if str(item.get("confidence") or "low").lower() in ("high", "medium", "low")
                else "low",
            }
        )
    if len(themes) < 3:
        raise SynthesisError(
            "at least 3 valid cross-source themes are required; " + "; ".join(warnings[:6])
        )
    unused = [
        {
            "source_id": source_id,
            "ref_id": item["ref_id"],
            "title": item["title"],
            "reason": "not used by any validated theme",
        }
        for source_id, item in sources.items()
        if source_id not in used
    ]
    if unused:
        warnings.append("%d sources were not used by any theme" % len(unused))
    return themes, unused, warnings


def synthesize_literature(
    project: Path,
    run_id: str,
    *,
    max_themes: int = 7,
    model: Any = None,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    target = run_dir(project, run_id)
    if not target.is_dir():
        raise SynthesisError("run does not exist: " + run_id)
    model = model or default_synthesis_model()
    pack = load_writing_pack(project, run_id) or build_writing_pack(
        project, run_id, language="zh", venue="zh_core_journal",
        max_sources=20, max_spans_per_source=3,
    )
    sources = _source_map(pack)
    if len(sources) < 2:
        raise SynthesisError("at least 2 full-text sources are required for synthesis")
    max_themes = max(3, min(int(max_themes), 10))
    prompt = _prompt(sources, max_themes)
    raw = str(model.complete(prompt, json_mode=True) or "")
    warnings: List[str] = []
    try:
        themes, unused, warnings = _validate(_parse_json(raw), sources, max_themes)
    except SynthesisError as first_error:
        if len(sources) <= 4:
            raise
        repair = prompt + [
            {
                "role": "user",
                "content": (
                    "上一次输出未通过校验：%s。请只返回合法 JSON；每个主题至少引用 2 个不同来源，"
                    "不得编造来源。上一次输出开头：\n%s" % (first_error, raw[:6000])
                ),
            }
        ]
        raw2 = str(model.complete(repair, json_mode=True) or "")
        try:
            themes, unused, warnings = _validate(_parse_json(raw2), sources, max_themes)
        except SynthesisError as second_error:
            raise SynthesisError(
                "synthesis failed after repair: %s; raw=%s" % (second_error, raw2[:2000])
            ) from second_error
    result = {
        "schema_version": SYNTHESIS_SCHEMA,
        "run_id": run_id,
        "model": getattr(model, "model_id", type(model).__name__),
        "source_count": len(sources),
        "theme_count": len(themes),
        "themes": themes,
        "unused_sources": unused,
        "warnings": warnings,
        "boundary": (
            "Cross-source synthesis over a bounded full-text corpus. Themes are model-assisted "
            "and validated for source coverage, but stance labels are not semantic entailment "
            "proof. No Claim/EA/gate/signature is created; human review remains required."
        ),
    }
    destination = Path(output_dir) if output_dir else target
    destination.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination / "synthesis-matrix.json", result)
    lines = [
        "# Literature Synthesis Matrix",
        "",
        "- run: `%s`" % run_id,
        "- sources: %d" % len(sources),
        "- themes: %d" % len(themes),
        "- model: `%s`" % result["model"],
        "",
    ]
    for theme in themes:
        lines += [
            "## %s %s (confidence=%s)" % (theme["theme_id"], theme["name"], theme["confidence"]),
            "",
            theme["summary"],
            "",
            "- agreement: %s" % (theme["agreement"] or "-"),
            "- tension: %s" % (theme["tension"] or "-"),
            "",
        ]
        for stance in theme["stances"]:
            lines.append(
                "- `%s` %s: %s" % (stance["ref_id"], stance["source_id"], stance["stance"])
            )
        lines.append("")
    if unused:
        lines += ["## Unused sources", ""]
        for item in unused:
            lines.append("- `%s` %s" % (item["ref_id"], item["title"]))
        lines.append("")
    lines += [result["boundary"], ""]
    (destination / "synthesis-matrix.md").write_text("\n".join(lines), encoding="utf-8")
    return result


STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "can", "may", "will", "would", "could",
    "into", "than", "then", "them", "they", "their", "there", "these", "those",
    "which", "while", "where", "when", "what", "who", "how", "why", "all",
    "any", "each", "more", "most", "some", "such", "only", "also", "both",
    "between", "because", "been", "being", "does", "did", "done", "its", "it",
    "our", "we", "you", "your", "his", "her", "she", "he", "who", "whose",
}


def synthesize_sources_deterministic(
    sources: List[Dict[str, Any]],
    *,
    max_themes: int = 5,
    min_sources_per_theme: int = 2,
) -> Dict[str, Any]:
    """Lexical cross-source theme builder for the deterministic pipeline path.

    Clusters full-text sources by shared salient terms over their spans. Every
    theme must cover at least ``min_sources_per_theme`` distinct sources and
    cites span ids as evidence. This is co-occurrence projection, not semantic
    synthesis; the model-driven matrix remains the quality path.
    """
    source_map: Dict[str, Dict[str, Any]] = {}
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        if not source_id or not source.get("full_text"):
            continue
        spans = [
            {"span_id": str(item.get("span_id") or ""), "text": str(item.get("text") or "")}
            for item in (source.get("spans") or [])
            if str(item.get("span_id") or "") and str(item.get("text") or "")
        ]
        if not spans:
            continue
        source_map[source_id] = {
            "ref_id": str(source.get("ref_id") or source_id),
            "title": _clean(source.get("title"), 160),
            "spans": spans,
        }
    term_sources: Dict[str, Dict[str, List[Dict[str, str]]]] = {}
    for source_id, item in source_map.items():
        for span in item["spans"]:
            for term in _salient_terms(span["text"]):
                term_sources.setdefault(term, {}).setdefault(source_id, []).append(span)
    ranked: List[Tuple[int, int, str]] = []
    for term, by_source in term_sources.items():
        if len(by_source) < min_sources_per_theme:
            continue
        ranked.append((len(by_source), sum(len(v) for v in by_source.values()), term))
    ranked.sort(reverse=True)
    themes: List[Dict[str, Any]] = []
    used: set = set()
    seen_terms: set = set()
    for _, _, term in ranked:
        if len(themes) >= max_themes:
            break
        lowered = " %s " % term.lower()
        if any(lowered in " %s " % seen for seen in seen_terms):
            continue
        seen_terms.add(term)
        by_source = term_sources[term]
        stances = []
        for source_id in sorted(by_source):
            span = sorted(by_source[source_id], key=lambda item: len(item["text"]))[-1]
            stances.append(
                {
                    "source_id": source_id,
                    "ref_id": source_map[source_id]["ref_id"],
                    "stance": "mixed",
                    "evidence": span["span_id"],
                }
            )
            used.add(source_id)
        themes.append(
            {
                "theme_id": "TH-%02d" % (len(themes) + 1),
                "name": term,
                "summary": "%d full-text sources jointly discuss the term; span-level co-occurrence only." % len(by_source),
                "source_count": len(by_source),
                "stances": stances,
                "agreement": "",
                "tension": "",
                "confidence": "low",
            }
        )
    unused = [
        {
            "source_id": source_id,
            "ref_id": item["ref_id"],
            "title": item["title"],
            "reason": "not covered by any lexical theme",
        }
        for source_id, item in source_map.items()
        if source_id not in used
    ]
    excluded = [
        str(source.get("source_id") or "").strip()
        for source in sources
        if str(source.get("source_id") or "").strip()
        and (not source.get("full_text") or not (source.get("spans") or []))
    ]
    warnings = []
    if excluded:
        warnings.append(
            "%d source(s) without full-text spans were excluded from lexical synthesis: %s"
            % (len(excluded), ", ".join(excluded))
        )
    return {
        "schema_version": "literature-synthesis-deterministic-0.1",
        "model": "deterministic-lexical-v0",
        "status": "synthesized" if themes else "no_cross_source_theme",
        "source_count": len(source_map),
        "theme_count": len(themes),
        "themes": themes,
        "unused_sources": unused,
        "warnings": warnings,
        "excluded_sources": excluded,
        "boundary": (
            "Deterministic lexical co-occurrence over full-text spans of this run; themes are not "
            "semantic synthesis and stances are all 'mixed'. No Claim/EA/gate is created."
        ),
    }


def _salient_terms(text: str, limit: int = 12) -> List[str]:
    lowered = _clean(text).lower()
    terms: List[str] = []
    for token in re.findall(r"[a-z][a-z0-9_-]{2,}", lowered):
        if token in STOPWORDS or token.isdigit():
            continue
        terms.append(token)
    for bigram in re.findall(r"[\u4e00-\u9fff]{2}", lowered):
        terms.append(bigram)
    seen: List[str] = []
    for term in terms:
        if term not in seen:
            seen.append(term)
    return seen[:limit]

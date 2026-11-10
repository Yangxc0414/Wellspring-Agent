"""Compact evidence-and-writing pack for a Qoder-written Chinese manuscript.

This is a read-only projection of one run. It is intentionally smaller than the
raw artifacts: selected spans, real references, run capsule/EA, claim status,
and an explicit writing contract. It never signs a claim or invents a result.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project import ProjectError, run_dir
from .storage import read_json

WRITING_PACK_SCHEMA = "writing-pack-0.1"
PACK_MARKER_RE = re.compile(
    r"<!--\s*writing-pack:\s*(WP-[0-9a-f]+)\s+sha256=([0-9a-f]{64})\s*-->"
)


def pack_identity(pack: Dict[str, Any]) -> tuple:
    payload = {
        key: value
        for key, value in pack.items()
        if key not in ("pack_id", "pack_sha256", "token_estimate", "created_at")
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return "WP-" + digest[:12], digest


def pack_marker(pack: Dict[str, Any]) -> str:
    pack_id = str(pack.get("pack_id") or "")
    digest = str(pack.get("pack_sha256") or "")
    if not pack_id or not digest:
        return ""
    return "<!-- writing-pack: %s sha256=%s -->" % (pack_id, digest)


def ensure_pack_marker(text: str, pack: Dict[str, Any]) -> str:
    marker = pack_marker(pack)
    if not marker:
        return text
    cleaned = PACK_MARKER_RE.sub("", text or "").lstrip("\n")
    return marker + "\n\n" + cleaned


def _norm_title(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").lower())


def numeric_reference_map(text: str, references: List[Dict[str, Any]]) -> Dict[int, str]:
    """Map [n] to a pack reference by matching the draft's reference-list titles.

    Index order is not the pack order: the generated manuscript numbers references by first
    citation, so [1] can be REF-03. Matching titles is the only safe mapping.
    """
    titles = [
        (str(item.get("ref_id") or ""), _norm_title(item.get("title")))
        for item in references
        if isinstance(item, dict) and item.get("ref_id") and item.get("title")
    ]
    mapping: Dict[int, str] = {}
    for match in re.finditer(r"^\s*\[(\d{1,3})\]\s*(.+)$", text or "", re.MULTILINE):
        index = int(match.group(1))
        line = _norm_title(match.group(2))
        candidates = [
            (len(title), ref_id)
            for ref_id, title in titles
            if title and title in line
        ]
        if candidates:
            mapping[index] = max(candidates)[1]
    return mapping


def bind_text_to_pack(text: str, pack: Dict[str, Any]) -> Dict[str, Any]:
    marker = pack_marker(pack)
    if not marker:
        raise ValueError("writing pack has no marker")
    existing = PACK_MARKER_RE.findall(text or "")
    current = (
        str(pack.get("pack_id") or ""),
        str(pack.get("pack_sha256") or ""),
    )
    if existing:
        if current in existing:
            raise ValueError("draft is already bound to this writing pack")
        raise ValueError("draft is already bound to a different writing pack")
    refs = sorted(set(re.findall(r"\[(REF-\d{1,4})\]", text or "")))
    # The generated manuscript renders references numerically ([1], [2]); the support audit
    # already maps those indexes to REF ids, so binding must not reject them.
    numbered = sorted(
        {
            int(token)
            for token in re.findall(r"(?<![\d,])\[(\d{1,3})\](?![\d,])", text or "")
        }
    )
    if not refs and not numbered:
        raise ValueError("draft has no [REF-xx] or [n] citations to audit")
    literature = (
        pack.get("literature") if isinstance(pack.get("literature"), dict) else {}
    )
    reference_rows = [
        item
        for item in literature.get("references") or []
        if isinstance(item, dict) and item.get("ref_id")
    ]
    pack_refs = {str(item.get("ref_id")) for item in reference_rows}
    if not pack_refs:
        pack_refs = {str(key) for key in (pack.get("evidence_map") or {})}
    numbered_map = numeric_reference_map(text or "", reference_rows)
    unmapped = [index for index in numbered if index not in numbered_map]
    if unmapped:
        raise ValueError(
            "numeric citations are not in the draft's reference list: "
            + ", ".join("[%d]" % index for index in unmapped)
        )
    mapped_numbered = [numbered_map[index] for index in numbered]
    resolved = [ref for ref in refs if ref in pack_refs] + mapped_numbered
    unresolved = [ref for ref in refs if ref not in pack_refs]
    if not resolved:
        raise ValueError("none of the draft citations exist in the writing pack")
    return {
        "text": ensure_pack_marker(text, pack),
        "marker": marker,
        "refs": refs,
        "numbered_refs": numbered,
        "resolved_refs": resolved,
        "unresolved_refs": unresolved,
    }


SECTION_NAMES = ["摘要", "引言", "相关工作", "方法", "实验", "结果", "讨论", "结论", "参考文献"]

# The writer prompt and the audit must read one number, otherwise the length instruction is
# decorative: drafts were accepted far below the stated target because nothing checked it.
LENGTH_TARGETS = {
    "zh": (6000, 8500),
    "en": (4000, 6000),
}
SKIP_TEXT = (
    "springer nature", "latex template", "copyright", "all rights reserved",
    "arxiv:", "license", "creative commons", "university", "laboratory",
    "corresponding author", "email", "figure ", "fig. ", "table ",
    "proceedings", "under review", "preprint", "authorized licensed use",
    "作者简介", "基金项目", "收稿日期", "通信作者", "引用格式",
    "acknowledg", "fellowship", "funding", "conflict of interest",
)
POSITIVE_TEXT = (
    "we propose", "we present", "we introduce", "we show", "we argue",
    "we find", "we evaluate", "this paper", "this work", "our approach",
    "our method", "results suggest", "experiments", "we demonstrate",
    "we study", "we investigate", "our contributions", "in this survey",
    "本文", "本研究", "我们", "实验表明", "结果表明",
)
INSTRUCTION_RE = re.compile(
    r"^(instruction|question|answer|thought|solution|input|output|prompt|response)\s*[:：]",
    re.I,
)
CODE_MARKERS = ("```", "def ", "class ", "import ", "print(", "printf(", "return ", "```python")
TOY_RE = re.compile(
    r"\b(natalia|sold clips|how many .{0,24}(?:left|remain)|calculate\s+[\d\[]|what is\s+\d)",
    re.I,
)
URL_IN_TEXT_RE = re.compile(r"(?:https?://|www\.|\bdoi:\s*10\.)")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]+")
QUERY_STOPWORDS = frozenset(
    "about after also among another because been before being between both could "
    "does doing done during each from have having here into itself more most "
    "other over same should some such than that their them then there these "
    "they this those through under until using very were what when where which "
    "while with within without would your self".split()
)


def _query_terms(question: str) -> set:
    terms = set()
    for word in WORD_RE.findall(str(question or "").lower()):
        if len(word) < 4 or word in QUERY_STOPWORDS:
            continue
        if len(word) >= 5 and word.endswith("s"):
            word = word[:-1]
        terms.add(word)
    return terms


def _span_problem(text: str) -> str:
    lowered = text.lower()
    stripped = text.strip()
    if any(marker in lowered for marker in SKIP_TEXT):
        return "boilerplate"
    if INSTRUCTION_RE.match(stripped):
        return "instruction_example"
    if any(marker in lowered for marker in CODE_MARKERS):
        return "code"
    if TOY_RE.search(stripped):
        return "toy_example"
    if stripped.endswith(("?", "？")):
        return "question"
    if URL_IN_TEXT_RE.search(stripped):
        return "url_or_doi"
    cjk_count = len(CJK_RE.findall(stripped))
    if cjk_count >= 8:
        # A 20-character Chinese disclaimer ("该数值仅用于测试流程，不是真实实验结果。")
        # is a complete sentence; 24 dropped the very span that supports a boundary claim.
        return "" if len(stripped) >= 16 else "short"
    words = WORD_RE.findall(stripped)
    if len(words) < 8:
        return "short"
    if sum(char.isdigit() for char in stripped) / max(1, len(stripped)) > 0.12:
        return "numeric_table"
    symbols = sum(
        1 for char in stripped
        if not char.isalnum() and not char.isspace() and char not in ",.;:'\"()[]-–—/%"
    )
    if symbols / max(1, len(stripped)) > 0.12:
        return "symbol_heavy"
    return ""


def _span_score(text: str, page: Any, section: str = "") -> int:
    lowered = text.lower()
    score = 0
    if page == 1:
        score += 1
    if any(marker in lowered for marker in POSITIVE_TEXT):
        score += 5
    if any(marker in section.lower() for marker in ("abstract", "introduction", "method", "result", "conclusion")):
        score += 2
    if 100 <= len(text) <= 480:
        score += 2
    if text[:1].isupper() or CJK_RE.match(text[:1]):
        score += 2
    if re.match(r"^(we|our|this|these|the results|in this|however|moreover)", text, re.I):
        score += 2
    if text.endswith((".", "。", "!", "！")):
        score += 1
    return score


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _text(value: Any, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit else text


def _load(path: Path) -> Any:
    try:
        return read_json(path)
    except Exception:
        return None


def _normal_title(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _arxiv_metadata(project: Path) -> Dict[str, Dict[str, Any]]:
    by_title = {}
    for name in ("arxiv-sources.json", "conference-corpus.json"):
        payload = _load(project / "inputs" / name)
        if not isinstance(payload, dict):
            continue
        for item in payload.get("downloaded") or []:
            if isinstance(item, dict) and item.get("title"):
                by_title[_normal_title(item.get("title"))] = item
    return by_title


def _effective_length(text: str) -> int:
    """CJK chars carry more information per character; a 30-char Chinese span is not short."""
    return len(text) + len(re.findall(r"[\u4e00-\u9fff]", text))


def _selected_spans(
    literature: Dict[str, Any], max_spans_per_source: int, question: str = ""
) -> Dict[str, List[Dict[str, Any]]]:
    query_terms = _query_terms(question)
    selected: Dict[str, List[Dict[str, Any]]] = {}
    for span in literature.get("spans") or []:
        if not isinstance(span, dict):
            continue
        source_id = str(span.get("source_id") or "")
        text = _text(span.get("text"))
        # 36 effective chars ≈ an 18-character Chinese sentence; a shorter disclaimer
        # ("该数值仅用于测试流程，不是真实实验结果。") is still evidence and must not vanish.
        if not source_id or _effective_length(text) < 36:
            continue
        problem = _span_problem(text)
        if problem:
            continue
        selected.setdefault(source_id, [])
        selected[source_id].append(
            {
                "span_id": span.get("span_id"),
                "section": span.get("section"),
                "page": span.get("page"),
                "text": text[:500],
                "score": _span_score(text, span.get("page"), str(span.get("section") or "")),
                "topic_hits": 0,
            }
        )
    every = [item for items in selected.values() for item in items]
    rare_terms = set()
    term_df = {}
    if query_terms and every:
        # A question word that appears in most spans ("agent") does not identify evidence;
        # a rare one ("archive") does. Each rare term gets one coverage slot so a pack cannot
        # silently pick three fluent contribution sentences that never mention the topic.
        ceiling = max(1, int(len(every) * 0.2))
        for term in query_terms:
            hits = sum(1 for item in every if term in item["text"].lower())
            term_df[term] = hits
            if hits <= ceiling:
                rare_terms.add(term)
        if rare_terms:
            for item in every:
                lowered = item["text"].lower()
                item["topic_hits"] = sum(1 for term in rare_terms if term in lowered)
    for source_id, items in selected.items():
        ranked = sorted(items, key=lambda item: (-item["score"], str(item["span_id"])))
        coverage: List[Dict[str, Any]] = []
        for term in sorted(rare_terms, key=lambda value: (term_df.get(value, 0), value)):
            candidates = [
                item for item in items if term in item["text"].lower() and item["score"] >= 4
            ]
            if candidates:
                coverage.append(
                    max(candidates, key=lambda item: (item["score"], str(item["span_id"])))
                )
        ordered = coverage + ranked
        chosen: List[Dict[str, Any]] = []
        seen = set()
        for item in ordered:
            signature = re.sub(r"\W+", "", item["text"].lower())[:120]
            if signature in seen:
                continue
            seen.add(signature)
            if item["score"] >= 4 or not chosen:
                chosen.append(item)
            if len(chosen) >= max_spans_per_source:
                break
        selected[source_id] = chosen
    return selected


def load_writing_pack(project: Path, run_id: str) -> Optional[Dict[str, Any]]:
    try:
        path = run_dir(Path(project).resolve(), run_id) / "writing-pack.json"
    except ProjectError:
        return None
    payload = _load(path)
    if isinstance(payload, dict) and payload.get("schema_version") == WRITING_PACK_SCHEMA:
        return payload
    return None


def _metric_summary(evidence: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    metric = str(evidence.get("primary_metric") or "")
    values: Dict[str, List[float]] = {}
    for row in (evidence.get("metrics") or {}).get("by_seed") or []:
        if not isinstance(row, dict):
            continue
        method = str(row.get("method") or "")
        value = (row.get("metrics") or {}).get(metric)
        if method and isinstance(value, (int, float)) and not isinstance(value, bool):
            values.setdefault(method, []).append(float(value))
    summary: Dict[str, Dict[str, Any]] = {}
    for method, sequence in values.items():
        mean = sum(sequence) / len(sequence)
        variance = sum((value - mean) ** 2 for value in sequence) / len(sequence)
        summary[method] = {
            "metric": metric,
            "n": len(sequence),
            "mean": round(mean, 6),
            "std": round(variance ** 0.5, 6),
        }
    return summary


def _experiment_pack(project: Path, experiment_id: str) -> Dict[str, Any]:
    root = Path(project).resolve() / "experiments" / str(experiment_id).strip()
    spec = _load(root / "experiment-spec.json") or {}
    evidence = _load(root / "experiment-evidence.json") or {}
    claim = _load(root / "claim.json") or {}
    if not isinstance(spec, dict) or not spec:
        raise ProjectError("experiment spec does not exist: " + str(root))
    if not isinstance(evidence, dict) or not evidence:
        raise ProjectError("experiment evidence is missing; run experiment ingest first: " + str(root))
    design = spec.get("design") or {}
    methods = list(design.get("methods") or [])
    primary_method = evidence.get("primary_method") or (methods[-1] if methods else "")
    primary_metric = evidence.get("primary_metric") or design.get("metric") or ""
    evidence_path = root / "experiment-evidence.json"
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    claim_status = str(claim.get("status") or "")
    claim_hash = str(claim.get("evidence_sha256") or "")
    claim_hash_ok = bool(claim_hash) and claim_hash == evidence_sha256
    claim_reason_ok = bool(str(claim.get("human_reason") or "").strip())
    evidence_verified = evidence.get("status") == "verified"
    signed = claim_status in ("supported", "approved") and evidence_verified and claim_hash_ok and claim_reason_ok
    claim_error = ""
    if claim_status in ("supported", "approved") and not signed:
        reasons = []
        if not evidence_verified:
            reasons.append("experiment evidence status is not verified")
        if not claim_hash_ok:
            reasons.append("claim evidence_sha256 does not match the current experiment-evidence.json")
        if not claim_reason_ok:
            reasons.append("claim has no human_reason")
        claim_error = "; ".join(reasons)
    ea = {
        "artifact_id": "EE-" + evidence_sha256[:12],
        "kind": "experiment_evidence",
        "path": str(evidence_path),
        "sha256": evidence_sha256,
        "scope": evidence.get("scope") or {},
        "source": "experiment_runner",
        "status": evidence.get("status") or "",
        "hash_bound": signed,
        "immutable": False,
        "bound_claim_id": str(claim.get("claim_id") or "") if signed else "",
    }
    figure = {}
    figure_error = ""
    run_id = str(spec.get("run_id") or "")
    if run_id:
        from .experiment_figures import result_figure_manifest_path, verify_result_figure

        figure_path = result_figure_manifest_path(project, experiment_id)
        if figure_path.is_file():
            verified = verify_result_figure(figure_path, project=project)
            loaded = _load(figure_path)
            if verified.get("status") == "clean" and loaded.get("kind") == "data_result_plot":
                figure = {**loaded, "manifest": str(figure_path)}
            else:
                figure_error = "; ".join(verified.get("errors") or ["not a data result plot"])
    method_figure = {}
    method_figure_error = ""
    if run_id:
        pointer = project / "runs" / run_id / "figures" / "method-figure.json"
        info = _load(pointer) if pointer.is_file() else {}
        manifest_path = Path(str(info.get("manifest") or ""))
        if info and manifest_path.is_file():
            manifest = _load(manifest_path)
            svg = Path(str((manifest.get("files") or {}).get("svg") or ""))
            svg_ok = (
                svg.is_file()
                and hashlib.sha256(svg.read_bytes()).hexdigest()
                == str(manifest.get("svg_sha256") or "")
            )
            if (
                manifest.get("kind") == "astradraw_scene"
                and manifest.get("schematic") is True
                and svg_ok
            ):
                method_figure = {
                    **info,
                    "manifest": str(manifest_path),
                    "svg_sha256": manifest.get("svg_sha256"),
                    "schematic": True,
                    "kind": "astradraw_scene",
                    "renderer": "astradraw",
                }
            else:
                method_figure_error = "method schematic manifest is stale or not an AstraDraw schematic"
        elif info:
            method_figure_error = "method schematic manifest does not exist"
    return {
        "capsule": {
            "run_id": "EXP-" + str(experiment_id),
            "dataset_id": (spec.get("data") or {}).get("path"),
            "model": primary_method,
            "metric_name": primary_metric,
            "seeds": list(design.get("seeds") or []),
            "cv_folds": evidence.get("cv_folds"),
            "mean": evidence.get("mean"),
            "std": evidence.get("std"),
            "status": evidence.get("status"),
            "metrics_by_seed": (evidence.get("receipt") or {}).get("metrics") or [],
        },
        "ea": ea,
        "evidence_sha256": evidence_sha256,
        "claim_error": claim_error,
        "metrics": (evidence.get("metrics") or {}).get("by_seed") or [],
        "figure": {},
        "claim": {
            "status": (
                "signed" if signed
                else "invalidated" if claim_error
                else "draft_needs_human" if evidence_verified
                else "missing"
            ),
            "signed_claim": claim if signed else None,
            "draft": None if signed else evidence,
            "error": claim_error,
        },
        "experiment": {
            "experiment_id": experiment_id,
            "spec_path": str(root / "experiment-spec.json"),
            "evidence_path": str(evidence_path),
            "evidence_sha256": evidence_sha256,
            "claim_path": str(root / "claim.json") if claim else "",
            "claim_error": claim_error,
            "spec": spec,
            "evidence": evidence,
            "claim": claim or None,
            "metrics_summary": _metric_summary(evidence),
            "comparison": evidence.get("comparison") or {},
            "data_audit": evidence.get("data_audit") or {},
            "results_table": evidence.get("results_table") or "",
            "results_table_sha256": evidence.get("results_table_sha256") or "",
            "ridge_alpha": evidence.get("ridge_alpha"),
            "figure": figure or None,
            "figure_error": figure_error,
            "method_figure": method_figure or None,
            "method_figure_error": method_figure_error,
        },
    }


def _signed_claim(run_path: Path) -> Optional[Dict[str, Any]]:
    for name in ("claim/claim.json", "claim.json"):
        value = _load(run_path / name)
        if isinstance(value, dict) and value.get("status") in ("supported", "approved"):
            return value
    return None


def _run_evidence(run_path: Path) -> Dict[str, Any]:
    capsule = _load(run_path / "run" / "run-capsule.json") or {}
    ea = _load(run_path / "run" / "ea.json") or {}
    metrics = _load(run_path / "run" / "metrics.json") or []
    figure = _load(run_path / "run" / "result-figure.manifest.json") or {}
    claim_draft = _load(run_path / "run" / "claim-draft.json") or {}
    signed = _signed_claim(run_path) or {}
    return {
        "capsule": {
            "run_id": capsule.get("run_id"),
            "dataset_id": capsule.get("dataset_id"),
            "model": capsule.get("model"),
            "metric_name": capsule.get("metric_name"),
            "seeds": capsule.get("seeds") or [],
            "mean": capsule.get("mean"),
            "std": capsule.get("std"),
            "status": capsule.get("status"),
            "metrics_by_seed": capsule.get("metrics_by_seed") or [],
        },
        "ea": {
            "artifact_id": ea.get("artifact_id"),
            "scope": ea.get("scope"),
            "sha256": ea.get("sha256"),
            "immutable": ea.get("immutable"),
        },
        "metrics": metrics if isinstance(metrics, list) else [],
        "figure": {
            "figure_id": figure.get("figure_id"),
            "svg": str(run_path / "run" / "result-figure.svg"),
            "manifest": str(run_path / "run" / "result-figure.manifest.json"),
            "schematic": bool(figure.get("schematic", False)),
        }
        if figure else {},
        "claim": {
            "status": "signed" if signed else ("draft_needs_human" if claim_draft else "missing"),
            "signed_claim": signed or None,
            "draft": claim_draft or None,
        },
    }


RUNNABLE_DATASETS = ("iris", "breast_cancer", "chemlab")


def _reproduction_map(run_path: Path, claim_status: str = "") -> Dict[str, Any]:
    """Rebuild the claim -> exact command -> hashed artifacts mapping a reviewer needs.

    The capsule stores parameters and hashes but no invocation, so the command is
    reconstructed from the recorded parameters; a rebuilt command is a claim that the run is
    reproducible, not a verified re-run, and it is withheld when the parameters do not name a
    runnable surface.
    """
    capsule = _load(run_path / "run" / "run-capsule.json") or {}
    signed = _signed_claim(run_path) or {}
    dataset = str(capsule.get("dataset_id") or "")
    seeds = capsule.get("seeds") or []
    # the capsule stores a qualified id such as "sklearn:iris:150x4"; the runnable name is the
    # longest known dataset contained in it
    runnable = max(
        (name for name in RUNNABLE_DATASETS if name in dataset.lower()), key=len, default=""
    )
    caveats: List[str] = []
    command = ""
    if not capsule:
        caveats.append(
            "no run capsule: the stage never executed, so there is nothing to reproduce"
        )
    elif not runnable:
        caveats.append(
            "dataset %s is not on the run execute surface, so no command is offered"
            % (dataset or "unknown")
        )
    elif not seeds:
        caveats.append(
            "the capsule records no seeds; a command without a seed list is not a reproduction"
        )
    else:
        parts = [
            "python -m research_agent run execute",
            "--dataset %s" % runnable,
            "--seeds %d" % len(seeds),
        ]
        if capsule.get("protocol_id"):
            parts.append("--protocol-id %s" % capsule["protocol_id"])
        if capsule.get("test_size") is not None:
            parts.append("--test-size %s" % capsule["test_size"])
        parts.append("--output-dir <fresh-dir>")
        command = " ".join(parts)
    artifacts: List[Dict[str, str]] = []
    stored = capsule.get("artifacts")
    if isinstance(stored, dict):
        artifacts = [{"name": str(k), "path": str(v)} for k, v in sorted(stored.items())]
    elif isinstance(stored, list):
        for item in stored:
            if isinstance(item, dict):
                artifacts.append(
                    {
                        "name": str(item.get("name") or item.get("id") or ""),
                        "path": str(item.get("path") or ""),
                    }
                )
    if artifacts:
        caveats.append(
            "artifact entries are names and project-relative paths; the capsule hashes cover "
            "dataset/code/protocol only, so verify bytes with lineage verify"
        )
    return {
        "schema_version": "reproduction-map-0.1",
        # never vaguer than the pack's own claim field: draft and missing stay distinct
        "claim_status": claim_status or ("signed" if signed else "missing"),
        "claim_statement": str(signed.get("statement") or ""),
        "command": command,
        "inputs": {
            "dataset_id": dataset,
            "runnable_dataset": runnable,
            "dataset_sha256": str(capsule.get("dataset_sha256") or ""),
            "code_sha256": str(capsule.get("code_sha256") or ""),
            "protocol_sha256": str(capsule.get("protocol_sha256") or ""),
            "seeds": len(seeds),
            "metric_name": str(capsule.get("metric_name") or ""),
        },
        "artifacts": artifacts,
        "caveats": caveats,
        "boundary": (
            "the command is rebuilt from the parameters the capsule recorded, and the hashes "
            "are chain-of-custody values rather than a correctness proof: nothing here re-ran "
            "the experiment"
        ),
    }


def _build_claim_plan(
    references: List[Dict[str, Any]],
    evidence_refs: Dict[str, List[str]],
    selected_spans: Dict[str, List[Dict[str, Any]]],
    limit: int = 24,
) -> Dict[str, Any]:
    span_by_id = {
        str(span.get("span_id")): span
        for values in selected_spans.values()
        for span in (values or [])
        if isinstance(span, dict) and span.get("span_id")
    }
    claims: List[Dict[str, Any]] = []
    seen = set()
    used_refs = set()
    for ref in references:
        ref_id = str(ref.get("ref_id") or "")
        for span_id in (evidence_refs.get(ref_id) or [])[:2]:
            span = span_by_id.get(str(span_id))
            if not span:
                continue
            quote = _text(span.get("text"), 420)
            key = (ref_id, quote[:120])
            if len(quote) < 20 or key in seen:
                continue
            seen.add(key)
            used_refs.add(ref_id)
            claims.append(
                {
                    "claim_id": "CP-%02d" % (len(claims) + 1),
                    "ref_id": ref_id,
                    "span_id": str(span_id),
                    "section_hint": _text(span.get("section"), 80),
                    "quote": quote,
                    "rule": (
                        "只改写 quote 直接陈述的内容；一个句子只用一个 REF；"
                        "不得添加全称、额外条件或新数字"
                    ),
                }
            )
            if len(claims) >= limit:
                break
        if len(claims) >= limit:
            break
    return {
        "schema_version": "claim-plan-0.1",
        "claims": claims,
        "unusable_refs": [
            str(ref.get("ref_id")) for ref in references
            if str(ref.get("ref_id") or "") not in used_refs
        ],
        "boundary": (
            "Claim plan maps candidate claims to one selected span each. "
            "It is a writing aid, not evidence, a Claim or a semantic-entailment proof."
        ),
    }


def build_writing_pack(
    project: Path,
    run_id: str,
    language: str = "zh",
    venue: str = "zh_core_journal",
    max_sources: int = 8,
    max_spans_per_source: int = 3,
    experiment_id: str = "",
) -> Dict[str, Any]:
    target_venue = venue
    project = Path(project).resolve()
    try:
        run_path = run_dir(project, run_id)
    except ProjectError:
        raise
    if not run_path.is_dir():
        raise ProjectError("run does not exist: " + run_id)
    task = _load(run_path / "task.json") or {}
    literature_ledger = _load(run_path / "literature-ledger.json") or {}
    literature = _load(run_path / "literature.json") or {}
    idea = _load(run_path / "idea.json") or {}
    idea_review = _load(run_path / "idea-review.json") or {}
    design = _load(run_path / "experiment.json") or {}
    design_audit = _load(run_path / "design-audit.json") or {}
    synthesis = _load(run_path / "synthesis-matrix.json") or {}
    arxiv = _arxiv_metadata(project)
    query_plan = literature.get("query_plan") if isinstance(literature.get("query_plan"), dict) else {}
    question = _text(
        query_plan.get("question")
        or (task.get("goal") if isinstance(task, dict) else "")
    )
    spans = _selected_spans(literature, max_spans_per_source, question)
    sources = []
    references = []
    evidence_refs: Dict[str, List[str]] = {}
    for index, source in enumerate((literature_ledger.get("sources") or [])[: max(1, max_sources)], 1):
        if not isinstance(source, dict):
            continue
        title = _text(source.get("title"), 300)
        meta = arxiv.get(_normal_title(title), {})
        ref_id = "REF-%02d" % index
        url = _text(meta.get("url") or source.get("url"))
        if not url.startswith("http"):
            url = ""
        authors = list(meta.get("authors") or [])
        venue = _text(source.get("venue") or "arXiv", 200)
        venue_year = re.search(r"\b(19|20)[0-9]{2}\b", venue)
        reference = {
            "ref_id": ref_id,
            "source_id": source.get("source_id"),
            "title": title,
            "authors": authors,
            "year": int(venue_year.group(0)) if venue_year else (source.get("year") or meta.get("year")),
            "venue": venue,
            "doi": source.get("doi") or meta.get("doi") or "",
            "arxiv_id": meta.get("arxiv_id") or "",
            "url": url,
            "abstract": _text(meta.get("abstract"), 900),
            "license": source.get("license") or "",
            "full_text": bool(source.get("full_text")),
            "span_count": source.get("span_count") or 0,
            "source_type": source.get("source_type") or "unknown",
            "peer_reviewed": source.get("peer_reviewed") or "unknown",
            "fixture": bool(source.get("fixture")),
        }
        sources.append(reference)
        references.append(reference)
        evidence_refs[ref_id] = [
            item["span_id"] for item in spans.get(str(source.get("source_id")), []) if item.get("span_id")
        ]
    candidates = []
    for item in (idea.get("candidates") or [])[:3]:
        if isinstance(item, dict):
            candidates.append(
                {
                    "idea_id": item.get("idea_id"),
                    "title": _text(item.get("title"), 240),
                    "hypothesis": _text(item.get("hypothesis"), 800),
                    "falsification": _text(item.get("falsification"), 500),
                    "evidence_refs": list(item.get("evidence_refs") or []),
                }
            )
    warnings: List[str] = []
    run_evidence = _experiment_pack(project, experiment_id) if experiment_id else _run_evidence(run_path)
    if experiment_id:
        spec_run = str(((run_evidence.get("experiment") or {}).get("spec") or {}).get("run_id") or "")
        if spec_run and spec_run != run_id:
            warnings.append("experiment %s belongs to run %s, not %s" % (experiment_id, spec_run, run_id))
    venue_counts: Dict[str, int] = {}
    year_counts: Dict[str, int] = {}
    for ref in references:
        venue = str(ref.get("venue") or "unknown")
        year = str(ref.get("year") or "unknown")
        venue_counts[venue] = venue_counts.get(venue, 0) + 1
        year_counts[year] = year_counts.get(year, 0) + 1
    corpus_summary = {
        "source_count": len(references),
        "full_text_count": sum(1 for ref in references if ref.get("full_text")),
        "venue_counts": dict(sorted(venue_counts.items())),
        "year_counts": dict(sorted(year_counts.items())),
        "peer_reviewed_unknown": sum(
            1 for ref in references if ref.get("peer_reviewed") == "unknown"
        ),
    }
    conference_manifest = _load(project / "inputs" / "conference-corpus.json") or {}
    retrieved = conference_manifest.get("downloaded_count")
    if retrieved is None and isinstance(conference_manifest.get("downloaded"), list):
        retrieved = len(conference_manifest.get("downloaded") or [])
    if retrieved is not None:
        corpus_summary["retrieved_corpus_count"] = int(retrieved)
    experiment_package = run_evidence.get("experiment") or {}
    package_spec = experiment_package.get("spec") or {}
    package_design = package_spec.get("design") or {}
    design_constants = set()
    for value in (
        (package_spec.get("data") or {}).get("rows"),
        len((package_spec.get("data") or {}).get("features") or []),
        package_design.get("test_size"),
        design.get("seeds") if isinstance(design.get("seeds"), int) else None,
    ):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            design_constants.add(str(value))
    seeds = package_design.get("seeds") or run_evidence["capsule"].get("seeds") or []
    if isinstance(seeds, list):
        for seed in seeds:
            if isinstance(seed, (int, float)) and not isinstance(seed, bool):
                design_constants.add(str(seed))
    signed = run_evidence["claim"].get("signed_claim") or {}
    allowed_numbers = set()
    if signed:
        for assertion in signed.get("assertions") or []:
            # The draft prints the asserted value and rounds the observed value to 4/6 decimals;
            # allowing only the raw float made the draft's own rendering untraceable.
            for key in ("value", "observed", "tolerance"):
                value = assertion.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    allowed_numbers.add(str(value))
                    allowed_numbers.add("%.4f" % value)
                    allowed_numbers.add("%.6f" % value)
        for value in (run_evidence["capsule"].get("mean"), run_evidence["capsule"].get("std")):
            if isinstance(value, (int, float)):
                allowed_numbers.add("%.4f" % value)
        for item in (experiment_package.get("metrics_summary") or {}).values():
            for key in ("mean", "std"):
                value = item.get(key)
                if isinstance(value, (int, float)):
                    allowed_numbers.add("%.4f" % value)
        for item in (experiment_package.get("comparison") or {}).values():
            for key in ("mean_diff", "ci95_low", "ci95_high"):
                value = item.get(key)
                if isinstance(value, (int, float)):
                    allowed_numbers.add("%.4f" % value)
    if not synthesis and len(references) >= 5:
        warnings.append("multi-source synthesis matrix is missing; the writer may summarize papers one by one")
    if run_evidence.get("claim_error"):
        warnings.append("experiment claim is invalidated: " + str(run_evidence["claim_error"]))
    elif not signed:
        warnings.append("claim is not signed; do not report result numbers as findings")
    if run_evidence.get("figure_error"):
        warnings.append("experiment result figure is stale: " + run_evidence["figure_error"])
    if run_evidence.get("method_figure_error"):
        warnings.append("method schematic is stale: " + run_evidence["method_figure_error"])
    data_audit = (run_evidence.get("experiment") or {}).get("data_audit") or {}
    if data_audit.get("status") == "warn":
        warnings.append(
            "experiment data audit has warnings: " + "; ".join(data_audit.get("warnings") or [])[:600]
        )
    if not references:
        warnings.append("no references were extracted from the literature ledger")
    elif len(references) < 3:
        warnings.append("fewer than 3 references; treat the review as a scoped brief, not a field survey")
    if references and not any(spans.values()):
        warnings.append("no readable full-text spans were selected; reference cards alone cannot support specific claims")
    missing_span_sources = [
        ref["ref_id"] for ref in references if not evidence_refs.get(ref["ref_id"])
    ]
    if missing_span_sources:
        warnings.append(
            "sources without selected spans: " + ", ".join(missing_span_sources[:8])
        )
    if any(not ref["url"] for ref in references) and language == "zh":
        warnings.append("some references have no public URL; resolve before journal submission")
    if design_audit.get("status") in ("incomplete", "blocked"):
        warnings.append("S4 design audit is %s; G2 requires human completion" % design_audit.get("status"))
    if task.get("stopped_at"):
        warnings.append("run stopped at %s; human gate remains" % task.get("stopped_at"))
    claim_plan = _build_claim_plan(references, evidence_refs, spans)
    writing_contract = {
        "language": language,
        "venue": target_venue,
        "article_type": "reproduction" if run_evidence.get("capsule", {}).get("run_id") else "review",
        "citation_style": "GB/T 7714 working reference; use [REF-01] in draft and map to numeric refs at export",
        "section_plan": list(SECTION_NAMES),
        "length_target": {
            "unit": "chinese_characters" if language == "zh" else "words",
            "min": LENGTH_TARGETS.get(language, LENGTH_TARGETS["zh"])[0],
            "max": LENGTH_TARGETS.get(language, LENGTH_TARGETS["zh"])[1],
            "enforced_by": "writing audit length.<unit> check",
        },
        "reference_ids": [ref["ref_id"] for ref in references],
        "result_policy": (
            "signed claim required before reporting result numbers"
            if not signed else
            "only use numbers in allowed_result_numbers"
        ),
        "allowed_result_numbers": sorted(allowed_numbers),
        "allowed_design_numbers": sorted(design_constants),
        "rules": [
            "Only cite reference_ids in this pack; never invent citations or DOIs.",
            "Do not report result numbers unless claim.status == signed.",
            "Literature claims must point to selected spans or reference cards.",
            "Prefer claim_plan claims: one REF per sentence; do not merge multiple REFs into one universal claim.",
            "Do not use fixture data or write 待补/TODO in the final draft.",
            "Use a review/related-work section grounded in the extracted sources.",
            "Corpus metadata in literature.corpus may be described in method/experiment; keep result claims qualitative unless a claim is signed.",
        ],
    }
    if not signed:
        writing_contract["allowed_result_numbers"] = []
        writing_contract["allowed_design_numbers"] = []
    pack = {
        "schema_version": WRITING_PACK_SCHEMA,
        "created_at": _now(),
        "run_id": run_id,
        "project_dir": str(project),
        "language": language,
        "venue": target_venue,
        "task": {
            "route": task.get("route"),
            "status": task.get("status"),
            "stopped_at": task.get("stopped_at"),
            "goal": task.get("goal"),
        },
        "literature": {
            "sources": sources,
            "references": references,
            "corpus": corpus_summary,
            "coverage": literature_ledger.get("coverage") or {},
            "gaps": (literature_ledger.get("coverage") or {}).get("gaps") or [],
            "source_briefs": (literature.get("brief") or {}).get("source_briefs") or [],
            "synthesis": synthesis or None,
            "selected_spans": spans,
        },
        "evidence_map": evidence_refs,
        "claim_plan": claim_plan,
        "ideas": candidates,
        "idea_review_status": idea_review.get("status"),
        "experiment_design": {
            "status": design.get("status"),
            "idea_id": design.get("idea_id") or (run_evidence.get("experiment") or {}).get("spec", {}).get("idea_id"),
            "hypothesis": design.get("hypothesis"),
            "baseline": design.get("baseline"),
            "primary_metric": design.get("primary_metric"),
            "controls": design.get("controls") or [],
            "seeds": design.get("seeds"),
            "budget": design.get("budget"),
            "design_audit": design_audit.get("status"),
            "design_blockers": design_audit.get("blockers") or [],
        },
        "run": run_evidence,
        "claim": run_evidence["claim"],
        "reproduction_map": _reproduction_map(
            run_path, str((run_evidence["claim"] or {}).get("status") or "")
        ),
        "experiment_package": run_evidence.get("experiment") or None,
        "writing_contract": writing_contract,
        "warnings": warnings,
        "boundary": (
            "Writing pack is a read-only evidence projection. Qoder may write prose, "
            "but must not invent references, result numbers, claims or gates."
        ),
    }
    pack_id, digest = pack_identity(pack)
    pack["pack_id"] = pack_id
    pack["pack_sha256"] = digest
    pack["token_estimate"] = max(1, len(json.dumps(pack, ensure_ascii=False)) // 4)
    return pack


def render_writing_pack(pack: Dict[str, Any]) -> str:
    lines = [
        "# Writing Pack",
        "",
        "- pack: `%s` (sha256 `%s`)" % (pack.get("pack_id"), str(pack.get("pack_sha256") or "")[:16]),
        "- run: `%s`" % pack.get("run_id"),
        "- route: `%s`; status: `%s`; stopped_at: `%s`"
        % (
            (pack.get("task") or {}).get("route"),
            (pack.get("task") or {}).get("status"),
            (pack.get("task") or {}).get("stopped_at") or "-",
        ),
        "- claim: `%s`" % (pack.get("claim") or {}).get("status"),
        "",
        "## References",
        "",
    ]
    for ref in (pack.get("literature") or {}).get("references") or []:
        lines.append(
            "- `%s` %s (%s, %s) %s"
            % (ref.get("ref_id"), ref.get("title"), ref.get("year"), ref.get("venue"), ref.get("url"))
        )
    lines += ["", "## Claim plan", ""]
    for claim in (pack.get("claim_plan") or {}).get("claims") or []:
        lines.append(
            "- `%s` `%s`/`%s`: %s"
            % (claim.get("claim_id"), claim.get("ref_id"), claim.get("span_id"), claim.get("quote"))
        )
    unusable = (pack.get("claim_plan") or {}).get("unusable_refs") or []
    if unusable:
        lines.append("- unusable REFs (no selected span): " + ", ".join(unusable))
    lines += ["", "## Ideas", ""]
    for idea in pack.get("ideas") or []:
        lines.append("- `%s` %s" % (idea.get("idea_id"), idea.get("title")))
    lines += ["", "## Run", ""]
    capsule = (pack.get("run") or {}).get("capsule") or {}
    lines.append(
        "- dataset: `%s`; metric: `%s`; seeds: `%s`; mean: `%s`; std: `%s`"
        % (
            capsule.get("dataset_id"), capsule.get("metric_name"), capsule.get("seeds"),
            capsule.get("mean"), capsule.get("std"),
        )
    )
    repro = pack.get("reproduction_map") or {}
    lines += ["", "## Reproduction map (claim -> command -> artifacts)", ""]
    lines.append("- claim status: `%s`" % repro.get("claim_status"))
    if repro.get("command"):
        lines.append("- re-run: `%s`" % repro["command"])
    else:
        lines.append("- re-run: not offered (%s)" % "; ".join(repro.get("caveats") or ["—"]))
    inputs = repro.get("inputs") or {}
    lines.append(
        "- inputs: dataset `%s` code `%s` protocol `%s`"
        % (
            str(inputs.get("dataset_sha256") or "")[:12],
            str(inputs.get("code_sha256") or "")[:12],
            str(inputs.get("protocol_sha256") or "")[:12],
        )
    )
    for artifact in repro.get("artifacts") or []:
        lines.append("- artifact `%s`: `%s`" % (artifact.get("name"), artifact.get("path")))
    lines.append("- " + repro.get("boundary", ""))
    lines += ["", "## Warnings", ""]
    for warning in pack.get("warnings") or []:
        lines.append("- " + warning)
    return "\n".join(lines) + "\n"

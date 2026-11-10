"""Summarize artifact packages for the UI and task reports.

These summaries describe what exists and what is still missing. They are not
evidence themselves and never upgrade a draft or a claim into a verified one.
"""

from typing import Any, Dict, List, Optional

from .contracts import seed_count


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _package(
    package_id: str,
    stage: str,
    label: str,
    status: str,
    detail: str,
    boundary: str,
    refs: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "id": package_id,
        "stage": stage,
        "label": label,
        "status": status,
        "detail": detail,
        "boundary": boundary,
        "refs": [str(item) for item in (refs or []) if str(item).strip()],
    }


def summarize_evidence_packages(
    modules: Dict[str, Any],
    gates: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    modules = modules or {}
    gates = gates or []
    literature = modules.get("literature") or {}
    idea = modules.get("idea") or {}
    design = modules.get("experiment") or {}
    protocol = modules.get("protocol") or {}
    run = modules.get("run") or {}
    paper = modules.get("paper") or {}
    figure = modules.get("figure") or {}

    hits = _list(literature.get("hits"))
    spans = _list(literature.get("spans"))
    coverage = literature.get("coverage") or {}
    brief = literature.get("brief") or {}
    gaps = _list(coverage.get("gaps")) + _list(brief.get("gaps"))
    full_text = sum(1 for hit in hits if isinstance(hit, dict) and hit.get("full_text") is True)
    saturation = _text(brief.get("saturation")) or "unknown"
    if not hits and not spans:
        literature_status = "missing"
    elif not spans:
        literature_status = "partial"
    elif saturation == "saturated":
        literature_status = "ready"
    else:
        literature_status = "partial"
    fixture_boundary = (
        "fixture 语料只用于流程验证，不可作为真实证据。"
        if literature.get("fixture_mode")
        else "摘要-only 只能作为线索；没有全文不生成 span。"
    )

    candidates = _list(idea.get("candidates"))
    idea_status = "needs_human" if candidates else "missing"

    design_status = _text(design.get("status"))
    if design_status in ("ready_for_g2", "needs_human"):
        design_package_status = "needs_human"
    else:
        design_package_status = "missing"

    protocol_frozen = _text(protocol.get("status")) == "frozen"
    capsule = run.get("capsule") or {}
    run_status = _text(capsule.get("status"))
    run_package_status = (
        "ready" if run_status == "completed" else "blocked" if run_status == "failed" else "missing"
    )
    run_detail = (
        "%s · dataset=%s · %s seeds · metric=%s"
        % (
            _text(capsule.get("run_id")) or "no run",
            _text(capsule.get("dataset_id")) or "—",
            len(_list(capsule.get("seeds"))),
            _text(capsule.get("metric_name")) or "—",
        )
        if capsule
        else "尚未执行 S5；无可复现 RunCapsule。"
    )

    evidence = run.get("evidence") or {}
    evidence_id = _text(evidence.get("artifact_id"))
    ea_status = "ready" if evidence_id else "missing"

    claim_refs = _list(paper.get("claims"))
    claim_draft = run.get("claim_draft_record") or {}
    if claim_refs:
        claim_status = "ready"
        claim_detail = "%d 个 claim 引用已绑定；closure 仍需验证签名与 scope。" % len(claim_refs)
        claim_refs_out = [str(item) for item in claim_refs]
    elif _text(claim_draft.get("statement")):
        claim_status = "needs_signature"
        claim_detail = "只有未签 claim draft；结果段必须继续 pending。"
        claim_refs_out = [_text(claim_draft.get("scope")) or "S5/claim-draft"]
    else:
        claim_status = "missing"
        claim_detail = "没有 claim draft，也没有已签 claim。"
        claim_refs_out = []

    result_figure = run.get("result_figure") or {}
    if result_figure:
        figure_status = "ready"
        figure_detail = "数据图 manifest 已绑定为 result.figure。"
        figure_refs = [_text(result_figure.get("figure_id"))]
    elif figure.get("figure_id"):
        figure_status = "partial"
        figure_detail = "只有示意图（schematic）；不能当结果图。"
        figure_refs = [_text(figure.get("figure_id"))]
    else:
        figure_status = "missing"
        figure_detail = "没有图或图 manifest。"
        figure_refs = []

    slots = _list(paper.get("slots"))
    primary_slot = next(
        (slot for slot in slots if isinstance(slot, dict) and slot.get("id") == "result.primary"),
        {},
    )
    if _text(primary_slot.get("status")) == "bound_claim":
        paper_status = "ready"
        paper_detail = "result.primary 已绑定 claim；closure 未运行。"
    elif paper:
        paper_status = "needs_human"
        paper_detail = "%d sections / %d slots；结果槽不会先于人签 claim 填数。" % (
            len(_list(paper.get("draft"))), len(slots)
        )
    else:
        paper_status = "missing"
        paper_detail = "尚未生成论文契约或工作稿。"

    g5 = next(
        (gate for gate in gates if isinstance(gate, dict) and gate.get("gate") == "G5"),
        {},
    )
    g5_status = _text(g5.get("status"))
    closure_status = (
        "ready" if g5_status == "pass"
        else "blocked" if g5_status == "blocked"
        else "needs_human" if g5_status in ("needs_human", "pending")
        else "not_run"
    )

    return [
        _package(
            "literature", "S1", "文献证据包", literature_status,
            "%d hits · %d full-text · %d spans · %d gaps"
            % (len(hits), full_text, len(spans), len(gaps)),
            fixture_boundary,
            [_text((span or {}).get("span_id")) for span in spans[:6] if isinstance(span, dict)],
        ),
        _package(
            "idea", "S2–S3", "假设候选包", idea_status,
            "%d 个候选；每个候选必须有否证条件和可解析 span。" % len(candidates),
            "候选不是 claim；G1 未通过前不能当结论。",
            [_text(item.get("idea_id")) for item in candidates[:6] if isinstance(item, dict)],
        ),
        _package(
            "design", "S4", "实验设计包", design_package_status,
            "%s · baseline=%s · metric=%s · %d seeds"
            % (
                design_status or "missing",
                _text(design.get("baseline")) or "—",
                _text(design.get("primary_metric")) or "—",
                seed_count(design.get("seeds") or 0),
            ),
            "设计草稿不等于 G2；没有冻结协议时不得把它当预注册。",
            [_text(design.get("design_id"))],
        ),
        _package(
            "protocol", "S4/G2", "预注册协议包", "ready" if protocol_frozen else "missing",
            (
                "protocol=%s · design_sha=%s"
                % (
                    _text(protocol.get("protocol_id")) or "—",
                    _text(protocol.get("design_sha256"))[:12] or "—",
                )
                if protocol_frozen
                else "没有 frozen ProtocolCard；G2 未通过。"
            ),
            "协议必须与当前 design hash 绑定；不能复用旧协议。",
            [_text(protocol.get("protocol_id"))],
        ),
        _package(
            "run", "S5a", "运行胶囊包", run_package_status, run_detail,
            "本地协议验证不等于真实实验；RunCapsule 只证明本次执行的输入与结果。",
            [_text((run.get("paths") or {}).get("capsule"))],
        ),
        _package(
            "ea", "S5a", "证据工件包", ea_status,
            "EA=%s" % (evidence_id or "—"),
            "EA 已封存也不等于 claim 已签；结果表达仍须人签。",
            [evidence_id],
        ),
        _package(
            "claim", "S5b", "Claim 包", claim_status, claim_detail,
            "runtime 永不签署 claim；只展示 draft 或已提交引用。",
            claim_refs_out,
        ),
        _package(
            "figure", "S6", "图表包", figure_status, figure_detail,
            "示意图不能绑定为 result.figure；数据图必须有 manifest 与 EA 引用。",
            figure_refs,
        ),
        _package(
            "paper", "S8–S12", "论文槽位包", paper_status, paper_detail,
            "结果槽必须等待已签 claim；不能从 fixture 或示意图推断结果。",
            [_text(paper.get("profile", {}).get("venue_type"))] if isinstance(paper.get("profile"), dict) else [],
        ),
        _package(
            "closure", "S13–S16", "闭包/导出包", closure_status,
            _text(g5.get("reason")) or "closure 尚未运行。",
            "runtime 只读展示；签名、closure 与导出验证必须离线完成。",
        ),
    ]

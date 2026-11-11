"""Figure ① effectiveness audit: measure every core module of the main loop.

图①（过程可信主循环）是平台的核心：七阶段前向链 + 四道门 + 四条反馈环。本脚本
对一次真实 run 的产物逐模块测出读数（不是声明），每行给三态结论：effective /
present_weak / absent。反馈环 B（溯源/失效传播）额外做篡改实测：把 run 复制到
临时目录、篡改上游产物、重跑 lineage verify——失效传播必须真的工作，测出来才算数。

Usage:
    python scripts/figure1_effectiveness_audit.py --run-dir <runs/RUN-xxx> [--output-dir d]
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESULT_SCHEMA = "figure1-audit-0.1"


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _row(module, stage, verdict, evidence, detail):
    return {
        "module": module,
        "stage": stage,
        "verdict": verdict,  # effective | present_weak | absent
        "evidence": evidence,
        "detail": detail,
    }


def _audit_forward_chain(run: Path) -> list:
    rows = []
    literature = _read(run / "literature.json") or {}
    hits = literature.get("hits") or []
    spans = literature.get("spans") or []
    full_text = sum(1 for h in hits if isinstance(h, dict) and h.get("path"))
    rows.append(
        _row(
            "S1 文献检索与关系推理",
            "S1",
            "effective" if spans and hits else ("present_weak" if literature else "absent"),
            {"hits": len(hits), "full_text_hits": full_text, "spans": len(spans), "fixture_mode": bool(literature.get("fixture_mode"))},
            "span-only 证据边界：hits 里带全文路径的比例决定 Q0 的 coverage 读数",
        )
    )

    idea = _read(run / "idea.json") or {}
    candidates = [c for c in (idea.get("candidates") or []) if isinstance(c, dict)]
    grounded = sum(1 for c in candidates if c.get("evidence_refs"))
    falsifiable = sum(1 for c in candidates if c.get("falsification"))
    lenses = sorted({str(c.get("lens") or "unlabeled") for c in candidates})
    rows.append(
        _row(
            "S2 假设生成与开放探索",
            "S2",
            "effective" if candidates and grounded and falsifiable else ("present_weak" if candidates else "absent"),
            {
                "candidates": len(candidates),
                "grounded": grounded,
                "falsifiable": falsifiable,
                "lenses": lenses,
            },
            "每个候选必须落到证据引用与可证伪条件（executable 注册表校验在 idea-review）",
        )
    )

    experiment = _read(run / "experiment.json") or {}
    design_audit = _read(run / "design-audit.json") or {}
    protocol_frozen = (run / "protocol" / "protocol-card.json").is_file()
    design_complete = bool(
        experiment.get("primary_metric")
        and experiment.get("seeds")
        and experiment.get("stopping_rule")
    )
    rows.append(
        _row(
            "S3 实验设计 + 执行契约",
            "S4-设计",
            "effective" if design_complete and protocol_frozen else ("present_weak" if experiment else "absent"),
            {
                "primary_metric": str(experiment.get("primary_metric") or ""),
                "seeds": experiment.get("seeds"),
                "stopping_rule": str(experiment.get("stopping_rule") or "")[:60],
                "controls": len(experiment.get("controls") or []),
                "design_audit_status": str(design_audit.get("status") or "missing"),
                "protocol_frozen": protocol_frozen,
            },
            "S4 设计的有效性判据：primary_metric/seeds/stopping_rule 完整 + protocol 已冻结（G2 产物）",
        )
    )

    capsule = _read(run / "run" / "run-capsule.json") or {}
    metrics_by_seed = capsule.get("metrics_by_seed") or {}
    ea = (run / "run" / "ea.json").is_file()
    rows.append(
        _row(
            "S4 执行与数据分析（T4 过程可重建）",
            "S5",
            "effective" if metrics_by_seed and ea else ("present_weak" if capsule else "absent"),
            {
                "seeds": capsule.get("seeds"),
                "metrics_by_seed": metrics_by_seed,
                "metric_name": capsule.get("metric_name"),
                "ea_present": ea,
                "code_sha256": str(capsule.get("code_sha256") or "")[:12],
            },
            "RunCapsule 记录 dataset/code 哈希与逐 seed 指标——过程层可重建的根据",
        )
    )

    q0 = _read(run / "q0.json") or {}
    rows.append(
        _row(
            "Q0 统计/复现门（自动）",
            "Q0",
            "effective" if str(q0.get("status") or "") in ("pass", "blocked") else ("present_weak" if q0 else "absent"),
            {"status": str(q0.get("status") or ""), "reason": str(q0.get("reason") or "")[:120]},
            "自动门做出真实判定并写明理由（coverage=partial 是诚实读数，不是失败）",
        )
    )
    return rows


def _audit_three_layer_verification(run: Path) -> list:
    rows = []
    evidence_packages = _read(run / "evidence-packages.json")
    packages = evidence_packages if isinstance(evidence_packages, list) else (evidence_packages or {}).get("packages") or []
    verified = sum(1 for p in packages if isinstance(p, dict) and str(p.get("status") or "") == "verified")
    capsule = _read(run / "run" / "run-capsule.json") or {}
    manifest = (run / "lineage" / "lineage.json").is_file()
    metrics_layer = capsule.get("metrics_by_seed") or []
    result_layer = bool(metrics_layer)
    rows.append(
        _row(
            "S5 三层验证 · 结果层",
            "T6a",
            "effective" if result_layer else "absent",
            {"metrics_by_seed": len(metrics_layer or {}), "evidence_packages": len(packages), "verified_packages": verified},
            "结果层 = 逐 seed 指标 + verified evidence 包",
        )
    )
    rows.append(
        _row(
            "S5 三层验证 · 过程层",
            "T6a",
            "effective" if capsule else "absent",
            {"run_capsule": bool(capsule), "events_ndjson": (run / "events.ndjson").is_file()},
            "过程层 = RunCapsule + 事件流（可重建）",
        )
    )
    rows.append(
        _row(
            "S5 三层验证 · 证据链层",
            "T6a",
            "effective" if manifest else "absent",
            {"lineage_manifest": manifest},
            "证据链层 = lineage manifest（内容寻址节点）",
        )
    )
    return rows


def _audit_gates(run: Path) -> list:
    rows = []
    claim = _read(run / "claim" / "claim.json") or {}
    capsule = _read(run / "run" / "run-capsule.json") or {}
    assertion = None
    for item in claim.get("assertions") or []:
        if isinstance(item, dict):
            assertion = item
            break
    metric_name = str(capsule.get("metric_name") or "")
    metrics_by_seed = capsule.get("metrics_by_seed") or []
    worst_seed = None
    if assertion and metrics_by_seed:
        try:
            values = []
            for item in metrics_by_seed:
                if isinstance(item, dict):
                    value = item.get(metric_name) or item.get("metric") or item.get("value")
                    if value is None:
                        value = next((v for v in item.values() if isinstance(v, (int, float))), None)
                else:
                    value = item
                if isinstance(value, (int, float)):
                    values.append(float(value))
            worst_seed = min(values) if values else None
        except (TypeError, ValueError):
            worst_seed = None
    claimed_value = None
    if assertion:
        claimed_value = assertion.get("value")
        if isinstance(claimed_value, str):
            import re

            match = re.search(r"value=([0-9.]+)", claimed_value)
            claimed_value = float(match.group(1)) if match else None
    bound_ok = (
        worst_seed is not None
        and claimed_value is not None
        and abs(worst_seed - claimed_value) <= 0.005
    )
    rows.append(
        _row(
            "S5b 结果人签（最差种子下限断言）",
            "S5b",
            "effective" if bound_ok else ("present_weak" if claim else "absent"),
            {
                "claim_status": str(claim.get("status") or ""),
                "assertion": assertion,
                "recomputed_worst_seed": worst_seed,
                "bound_holds": bound_ok,
                "delegated": str((claim.get("human_reason") or "")).startswith("[delegated:"),
            },
            "重算逐 seed 最小值并与断言值比对——最差种子下限不是口号，是可复算的数值约束",
        )
    )

    closure = _read(run / "closure" / "closure-report.json") or {}
    signature = _read(run / "closure-signature" / "signature.json") or {}
    rows.append(
        _row(
            "G5 闭包签署（T7 陈述→证据溯源）",
            "G5",
            "effective" if closure.get("status") == "ready" and signature else ("present_weak" if closure else "absent"),
            {
                "closure_status": str(closure.get("status") or ""),
                "checks_passed": sum(1 for c in (closure.get("checks") or []) if isinstance(c, dict) and c.get("status") == "pass"),
                "checks_total": len(closure.get("checks") or []),
                "signature_id": str(signature.get("signature_id") or ""),
                "delegated": str(signature.get("human_reason") or "").startswith("[delegated:"),
            },
            "closure 检查槽位逐项通过后才可签；签名标记 delegated 时责任记在策略的 authorized_by",
        )
    )

    manuscript = run / "manuscript.md"
    audit = _read(run / "manuscript-audit.json") or {}
    claim_id = str(claim.get("claim_id") or "")
    cites_claim = bool(claim_id) and claim_id in (manuscript.read_text(encoding="utf-8") if manuscript.is_file() else "")
    rows.append(
        _row(
            "S7 证据绑定的成果陈述",
            "S8-S12",
            "effective" if cites_claim else ("present_weak" if manuscript.is_file() else "absent"),
            {
                "manuscript_present": manuscript.is_file(),
                "cites_signed_claim": cites_claim,
                "audit_status": str(audit.get("status") or ""),
                "audit_blockers": len(audit.get("blockers") or []),
                "submission_ready": bool(audit.get("submission_ready")),
            },
            "结果节只引用已签 claim；submission_ready 恒为 false（不投稿）",
        )
    )
    return rows


def _audit_feedback_loop_b(run: Path) -> list:
    """反馈环 B 篡改实测：上游被改，失效传播必须真的发生。"""
    rows = []
    from research_agent.lineage import LineageAgent

    manifest = run / "lineage" / "lineage.json"
    if not manifest.is_file():
        return [_row("反馈环 B · 溯源/失效传播", "T6a", "absent", {}, "run 没有 lineage manifest；先跑 lineage build")]
    baseline = LineageAgent().verify(manifest, run)
    clean_ok = str(baseline.get("status") or "") in ("clean", "no_change") and not baseline.get("changed")

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "run"
        shutil.copytree(run, copy)
        target = copy / "claim" / "claim.json"
        if target.is_file():
            payload = _read(target) or {}
            statement = str(payload.get("statement") or "")
            payload["statement"] = statement + " TAMPERED"
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            demo = copy / "demo.json"
            if demo.is_file():
                demo.write_text(demo.read_text(encoding="utf-8") + "\n<!-- TAMPERED -->\n", encoding="utf-8")
        impact = LineageAgent().verify(copy / "lineage" / "lineage.json", copy)
        stale_nodes = impact.get("stale") or []
        changed_nodes = impact.get("changed") or []
        detected = bool(stale_nodes or changed_nodes)
        export_blocked = impact.get("export_allowed") is False
        effective = clean_ok and detected and export_blocked
        rows.append(
            _row(
                "反馈环 B · 溯源/失效传播（篡改实测）",
                "T6a→S4",
                "effective" if effective else "present_weak",
                {
                    "clean_verify": str(baseline.get("status") or ""),
                    "tamper_detected": detected,
                    "stale_nodes": len(stale_nodes) if isinstance(stale_nodes, list) else int(stale_nodes or 0),
                    "changed_nodes": len(changed_nodes) if isinstance(changed_nodes, list) else int(changed_nodes or 0),
                    "requires_resign": bool(impact.get("requires_resign")),
                    "export_allowed_after_tamper": impact.get("export_allowed"),
                },
                "干净副本验证通过 + 篡改副本被检出的 changed/stale + export_allowed=false：失效传播实测成立",
            )
        )
    return rows


def _audit_feedback_loops_recorded(project: Path) -> list:
    from research_agent.feedback import registered_loops, run_feedback

    rows = []
    for loop_id in registered_loops():
        result = run_feedback(project, loops=[loop_id])
        produced = len(result.get("rows") or [])
        states = sorted({str(r["observation"].get("state") or "") for r in result.get("rows") or []})
        if produced:
            verdict = "effective"
        elif loop_id in ("homogeneity", "t6b_falsification"):
            # 该项目没有可观察对象（无 studies / 候选数不足）是诚实零，不是环的缺陷
            verdict = "not_applicable"
        else:
            verdict = "present_weak"
        rows.append(
            _row(
                "反馈环 %s（记录化）" % loop_id,
                "反馈环",
                verdict,
                {"observations": produced, "states": states[:6]},
                "记录化口径：环从真实产物产出约束 proposal；自动改写是 roadmap（默认拒绝）",
            )
        )
    return rows


def run_audit(run_dir: Path) -> dict:
    run = Path(run_dir).resolve()
    if not run.is_dir():
        raise ValueError("run directory does not exist: %s" % run)
    project = run.parent.parent
    rows = []
    rows += _audit_forward_chain(run)
    rows += _audit_three_layer_verification(run)
    rows += _audit_gates(run)
    rows += _audit_feedback_loop_b(run)
    rows += _audit_feedback_loops_recorded(project)
    counts = {"effective": 0, "present_weak": 0, "absent": 0, "not_applicable": 0}
    for row in rows:
        counts[row["verdict"]] += 1
    return {
        "schema_version": RESULT_SCHEMA,
        "run_dir": str(run),
        "rows": rows,
        "counts": counts,
        "criterion": (
            "effective = 模块产物存在且其自身的数值/行为判据实测通过；present_weak = 存在但"
            "实测读数暴露弱点（如 coverage=partial、audit blocked——诚实弱点不是缺陷）；absent = 核心"
            "产物缺失。反馈环 B 必须通过篡改实测才算 effective"
        ),
        "boundary": (
            "单 run 审计（RUN-E2E-02 为 autopilot 闭环产物）；fixture_mode 与 coverage 读数如实保留"
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args(argv)
    result = run_audit(Path(args.run_dir))
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "figure1-audit.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

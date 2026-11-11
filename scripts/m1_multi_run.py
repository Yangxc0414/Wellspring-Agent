"""M1 第二半的多 run 统计测量（73- 号设计文档 §2.3）——脚本已就绪，按指示暂不执行。

对多个项目的 runs 逐个计算：baseline（raw loop-capsule.json 建议）vs wired
（research_next_actions 现行为）。预注册判据：凡 baseline 含 stale 重签建议的 run，
wired 后必须翻转（flip）；flip_rate 必须 = 1.0，出现未翻转 run 即 verdict=
not_supported 如实记录。

Usage（后续执行）:
    python scripts/m1_multi_run.py --projects runtime_data/e2e-closed-loop \
        runtime_data/autopilot-e2e --output-dir runtime_data/m1-multi
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RESULT_SCHEMA = "m1-multi-run-0.1"


def _audit_run(project: Path, run_id: str) -> dict:
    from research_agent.mcp_server import _next_actions

    target = project / "runs" / run_id
    capsule_path = target / "loop-capsule.json"
    raw_advice: list = []
    if capsule_path.is_file():
        try:
            payload = json.loads(capsule_path.read_text(encoding="utf-8"))
            raw_advice = [
                str(a.get("command") or "")
                for a in (payload.get("next_actions") or [])
                if isinstance(a, dict)
            ]
        except (OSError, ValueError):
            raw_advice = []
    wired = _next_actions(project, run_id)
    wired_texts = [str(a.get("command") or a.get("cli") or "") for a in wired]
    stale_in_baseline = any("closure sign" in text for text in raw_advice)
    stale_in_wired = any("closure sign" in text for text in wired_texts)
    verdict_actions = [str(a.get("action") or "") for a in wired if a.get("kind") == "verdict_action"]
    return {
        "project": str(project),
        "run_id": run_id,
        "stale_in_baseline": stale_in_baseline,
        "stale_in_wired": stale_in_wired,
        "flipped": stale_in_baseline and not stale_in_wired,
        "verdict_actions": verdict_actions,
    }


def run(projects: list, limit: int = 50) -> dict:
    per_run = []
    for project in projects:
        root = Path(project).resolve()
        runs_dir = root / "runs"
        if not runs_dir.is_dir():
            continue
        for run_path in sorted(runs_dir.glob("RUN-*"))[:limit]:
            if not run_path.is_dir():
                continue
            try:
                per_run.append(_audit_run(root, run_path.name))
            except (OSError, ValueError) as exc:
                per_run.append({"project": str(root), "run_id": run_path.name, "error": str(exc)})
    stale_runs = [row for row in per_run if row.get("stale_in_baseline")]
    flipped = [row for row in stale_runs if row.get("flipped")]
    flip_rate = round(len(flipped) / len(stale_runs), 4) if stale_runs else None
    coverage = round(
        sum(1 for row in per_run if row.get("verdict_actions")) / len(per_run), 4
    ) if per_run else 0.0
    supported = flip_rate == 1.0 and len(stale_runs) > 0
    return {
        "schema_version": RESULT_SCHEMA,
        "projects": [str(Path(p).resolve()) for p in projects],
        "runs_scanned": len(per_run),
        "runs_with_stale_baseline": len(stale_runs),
        "flipped": len(flipped),
        "flip_rate": flip_rate,
        "verdict_action_coverage": coverage,
        "criterion": "flip_rate 必须 = 1.0（凡 baseline 有 stale 重签建议的 run 都必须翻转）；出现未翻转即 verdict=not_supported 如实记录",
        "verdict": "supported" if supported else ("not_supported" if stale_runs else "no_stale_runs"),
        "per_run": per_run,
        "boundary": (
            "多 run 统计测量：对真实消费者 research_next_actions 的 baseline/wired 对照；"
            "无 stale baseline 的 run 不进入 flip 分母（它们本来就没有错误建议可翻）"
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects", nargs="+", required=True)
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    result = run(args.projects, limit=args.limit)
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "result.json").write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

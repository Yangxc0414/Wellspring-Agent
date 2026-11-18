"""Generate the demo's "last real ESE run" panel from a pipeline run directory.

The static site previously had no surface for real runs: every claim about execution lived
in prose or design docs. This script turns a run's demo.json into (a) a shipped JSON
summary and (b) an HTML block between markers in site/index.html, so the panel is
generated, not hand-edited, and can be refreshed when a new run lands.
"""

import argparse
import html
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

START = "<!-- ESE-RUN-PANEL:START -->"
END = "<!-- ESE-RUN-PANEL:END -->"
SUMMARY_SCHEMA = "ese-run-panel-0.1"


def _read_json(path):
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def downstream_summary(project_run_dir, review_dir):
    """Optional S8 tail: manuscript review rounds and the final audit."""
    out = {}
    review = _read_json(Path(review_dir) / "manuscript-review.json")
    if review:
        accepted = None
        for iteration in review.get("iterations") or []:
            if isinstance(iteration, dict) and "accepted" in iteration:
                accepted = bool(iteration.get("accepted"))
        out["manuscript_review"] = {
            "status": str(review.get("status") or ""),
            "rounds_completed": review.get("rounds_completed"),
            "accepted": accepted,
        }
    audit = _read_json(Path(review_dir) / "final-audit.json") or _read_json(Path(project_run_dir) / "manuscript-audit.json")
    if audit:
        out["final_audit"] = {
            "status": str(audit.get("status") or ""),
            "citation_count": audit.get("citation_count"),
            "han_character_count": audit.get("han_character_count"),
            "submission_ready": bool(audit.get("submission_ready")),
        }
    return out


def build_summary(run_dir, project_run_dir="", review_dir=""):
    run = Path(run_dir)
    demo_path = run / "demo.json"
    if not demo_path.is_file():
        raise SystemExit("demo.json not found in " + str(run))
    demo = json.loads(demo_path.read_text(encoding="utf-8"))
    stages = []
    for key in ("literature", "synthesis", "idea", "experiment", "figure", "paper"):
        value = (demo.get("modules") or {}).get(key)
        if not isinstance(value, dict):
            continue
        stages.append({
            "stage": key,
            "status": str(value.get("status") or ""),
            "warnings": len(value.get("warnings") or []),
        })
    gates = []
    for gate in demo.get("gates") or []:
        gates.append({
            "gate": str(gate.get("gate") or ""),
            "status": str(gate.get("status") or ""),
            "reason": str(gate.get("reason") or ""),
        })
    return {
        "schema": SUMMARY_SCHEMA,
        "run_id": str(demo.get("run_id") or run.name),
        "fixture_mode": bool(demo.get("fixture_mode")),
        "status": str(demo.get("status") or ""),
        "stages": stages,
        "gates": gates,
        "ese_method": demo.get("ese_method") or {},
        "downstream": downstream_summary(project_run_dir, review_dir) if project_run_dir or review_dir else {},
        "boundary": (
            "static mirror of one real local run; gates need a human, no Claim/EA/signature is "
            "created by this panel"
        ),
    }


def render_panel(summary):
    rows = []
    for stage in summary["stages"]:
        warn = "" if not stage["warnings"] else " · %d warning(s)" % stage["warnings"]
        rows.append('<div class="sm-row"><span class="sm-key">{0}</span><p>{1}{2}</p></div>'.format(
            html.escape(stage["stage"]), html.escape(stage["status"]), html.escape(warn)))
    gate_bits = " · ".join(
        "{0}={1}".format(html.escape(gate["gate"]), html.escape(gate["status"]))
        for gate in summary["gates"]
    )
    downstream = summary.get("downstream") or {}
    if downstream.get("manuscript_review"):
        review = downstream["manuscript_review"]
        rows.append('<div class="sm-row"><span class="sm-key">manuscript-review</span><p>{0} · rounds={1} · accepted={2}</p></div>'.format(
            html.escape(str(review.get("status"))), html.escape(str(review.get("rounds_completed"))),
            html.escape(str(review.get("accepted")))))
    if downstream.get("final_audit"):
        audit = downstream["final_audit"]
        rows.append('<div class="sm-row"><span class="sm-key">final-audit</span><p>{0} · citations={1} · han={2} · submission_ready={3}</p></div>'.format(
            html.escape(str(audit.get("status"))), html.escape(str(audit.get("citation_count"))),
            html.escape(str(audit.get("han_character_count"))), html.escape(str(audit.get("submission_ready")))))
    rows.append('<div class="sm-row"><span class="sm-key">gates</span><p>{0}</p></div>'.format(gate_bits))
    return (
        '<div class="strategy-map" id="ese-run">\n'
        '  <h4>最近一次真实 ESE 全链运行 · {0}</h4>\n'
        '  <p class="sm-lede">本地真实 API 执行（非 fixture）；门按设计停住。面板由 scripts/build_ese_run_panel.py 从 demo.json 生成，不是手写。</p>\n'
        '  <div class="sm-rows">\n    {1}\n  </div>\n'
        '  <p class="fineprint">{2}</p>\n'
        '</div>'
    ).format(html.escape(summary["run_id"]), "\n    ".join(rows), html.escape(summary["boundary"]))


def inject(page_path, block):
    page = Path(page_path)
    text = page.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit("markers not found in " + str(page))
    start = text.index(START) + len(START)
    end = text.index(END)
    page.write_text(text[:start] + "\n" + block + "\n" + text[end:], encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="build the demo ESE run panel from a run dir")
    parser.add_argument("--run-dir", default="runtime_data/ese-fullrun-20261118")
    parser.add_argument("--page", default="site/index.html")
    parser.add_argument("--json-out", default="site/data/ese-run-summary.json")
    parser.add_argument("--project-run-dir", default="runtime_data/ese-fullrun-project/runs/RUN-ESE-01")
    parser.add_argument("--review-dir", default="runtime_data/ese-fullrun-project/manuscript-review")
    parser.add_argument("--no-inject", action="store_true")
    args = parser.parse_args(argv)
    summary = build_summary(args.run_dir, args.project_run_dir, args.review_dir)
    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.no_inject:
        inject(args.page, render_panel(summary))
    print("run panel: " + str(json_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

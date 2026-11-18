"""Generate demo/index.html from a real run: inputs -> stage outputs -> audit.

The old demo page was a 500 KB simulated console that looked like a workbench but was not
the workbench. This script replaces it with a small, generated walkthrough of one real run:
what went in, what each stage produced, what the gates said, and what is still missing.

Run it after a real pipeline run; the generated page is committed and copied to site/demo by
scripts/build-site.mjs.
"""

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read(path):
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _pipeline_run(run_dir):
    base = Path(run_dir)
    demo = _read(base / "demo.json")
    literature = _read(base / "literature.json")
    ideas = _read(base / "idea.json")
    design = _read(base / "experiment.json")
    paper = _read(base / "paper.json")
    return demo, literature, ideas, design, paper


def _project_tail(project_run_dir, review_dir):
    review = _read(Path(review_dir) / "manuscript-review.json")
    audit = _read(Path(review_dir) / "final-audit.json") or _read(Path(project_run_dir) / "manuscript-audit.json")
    return review, audit


def build(run_dir, project_run_dir, review_dir):
    demo, literature, ideas, design, paper = _pipeline_run(run_dir)
    review, audit = _project_tail(project_run_dir, review_dir)
    modules = demo.get("modules") or {}
    stages = []
    for key, label in (
        ("literature", "S1 文献 / 全证据"),
        ("synthesis", "S1b 跨来源综合"),
        ("idea", "S2-S3 假设"),
        ("experiment", "S4 设计与协议"),
        ("figure", "S6 图"),
        ("paper", "S8-S12 稿件"),
    ):
        value = modules.get(key) or {}
        stages.append({
            "key": key,
            "label": label,
            "status": str(value.get("status") or "not_run"),
            "warnings": len(value.get("warnings") or []),
        })
    gates = demo.get("gates") or []
    candidates = (ideas.get("candidates") or [])[:8]
    sources = literature.get("hits") or []
    spans = literature.get("spans") or []
    audit = audit or {}
    review = review or {}
    accepted = None
    for iteration in review.get("iterations") or []:
        if isinstance(iteration, dict) and "accepted" in iteration:
            accepted = bool(iteration.get("accepted"))
    return {
        "run_id": str(demo.get("run_id") or Path(run_dir).name),
        "question": str(demo.get("topic") or ""),
        "fixture_mode": bool(demo.get("fixture_mode")),
        "stages": stages,
        "gates": gates,
        "sources": len(sources),
        "spans": len(spans),
        "candidates": [
            {
                "title": str(item.get("title") or ""),
                "lens": str(item.get("lens") or ""),
                "refs": len(item.get("evidence_refs") or []),
            }
            for item in candidates
        ],
        "design": {
            "status": str(design.get("status") or ""),
            "metric": str(design.get("primary_metric") or ""),
            "warnings": len(design.get("warnings") or []),
        },
        "paper": {
            "status": str(paper.get("status") or ""),
            "writer_mode": str(paper.get("writer_mode") or ""),
            "sections": len(paper.get("sections") or []),
        },
        "review": {
            "status": str(review.get("status") or "not_run"),
            "rounds": review.get("rounds_completed"),
            "accepted": accepted,
        },
        "audit": {
            "status": str(audit.get("status") or "not_run"),
            "citations": audit.get("citation_count"),
            "han": audit.get("han_character_count"),
            "submission_ready": audit.get("submission_ready"),
        },
    }


def render(data):
    rows = "".join(
        '<tr><td>{0}</td><td>{1}</td><td>{2}</td></tr>'.format(
            html.escape(item["label"]), html.escape(item["status"]), item["warnings"]
        )
        for item in data["stages"]
    )
    gate_text = " · ".join("{0}={1}".format(html.escape(g.get("gate", "")), html.escape(g.get("status", ""))) for g in data["gates"])
    candidate_rows = "".join(
        '<tr><td>{0}</td><td>{1}</td><td>{2}</td></tr>'.format(
            html.escape(item["title"]), html.escape(item["lens"]), item["refs"]
        )
        for item in data["candidates"]
    )
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>研究运行回放 · 输入 → 输出（真实运行）</title>
<meta name="description" content="一次真实 ESE 运行的输入与阶段产物：文献、候选、设计、稿件、评审与审计；不是工作台，不含 SIM 控制台。" />
<link rel="stylesheet" href="../assets/demo-legibility.css" />
<style>
body{{margin:0;padding:32px;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.7;color:#1f2937;background:#f8fafc}}
main{{max-width:980px;margin:0 auto;background:#fff;border:1px solid #e5e9f0;border-radius:14px;padding:28px}}
h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:16px;margin:26px 0 8px;color:#111827}}
.meta{{color:#5b6472;font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}}
td,th{{border-bottom:1px solid #e5e9f0;padding:6px 8px;text-align:left;vertical-align:top}}
th{{color:#5b6472;font-weight:600}}
.badge{{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;background:#eef2ff;color:#2563eb;margin-right:6px}}
.boundary{{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:10px 14px;font-size:13px}}
a{{color:#2563eb}}
</style>
</head>
<body>
<main data-dl-page="demo" data-demo-run="{run_id}">
  <span class="badge">REAL RUN · 非 SIM</span><span class="badge">只读</span>
  <h1>研究运行回放：输入 → 产物</h1>
  <p class="meta">run: {run_id} · fixture_mode: {fixture_mode} · 真实工作台在 <a href="../app/">/app/</a>，本页是这份运行的只读回放。</p>

  <h2>1. 输入</h2>
  <p>研究问题：{question}</p>
  <p>文献语料：{sources} 篇全文来源、{spans} 个 span（pdf 解析，摘要不进入证据）。</p>

  <h2>2. 阶段 → 产物</h2>
  <table><thead><tr><th>阶段</th><th>状态</th><th>warning 数</th></tr></thead><tbody>{rows}</tbody></table>
  <p>门禁：{gate_text}</p>

  <h2>3. S2-S3 候选（前 {candidate_count} 条）</h2>
  <table><thead><tr><th>候选</th><th>lens</th><th>证据引用数</th></tr></thead><tbody>{candidate_rows}</tbody></table>

  <h2>4. S4 设计</h2>
  <p>状态：{design_status} · primary_metric：{design_metric} · warnings：{design_warnings}</p>

  <h2>5. S8-S12 输出</h2>
  <p>稿件：{paper_status} · writer_mode：{paper_writer} · sections：{paper_sections}</p>
  <p>手稿评审：{review_status} · rounds：{review_rounds} · accepted：{review_accepted}</p>
  <p>成稿审计：{audit_status} · citations：{audit_citations} · 汉字：{audit_han} · submission_ready：{audit_submission}</p>

  <h2>6. 边界</h2>
  <p class="boundary">本页回放一次本地真实运行（模型调用经本地网关）。门禁 G1/G2/G3/G5 仍待人签；没有 Claim/EA/签名；accepted 不等于通过，ready_for_human_review 不等于可投稿。工作台只保留一个入口：<a href="../app/">/app/</a>（构建产物），真实执行需本地 runtime。</p>
  <p><a href="../">← 返回首页</a> · <a href="../index.html#ese-run">最近一次真实运行面板</a> · <a href="run/">完整来龙去脉（逐阶段产物与门禁）→</a> · <a href="frontier/">24 篇前沿语料 / 6 候选版本 →</a> · 设计记录：design/111、design/117</p>
</main>
<script src="../assets/demo-legibility.js"></script>
</body>
</html>
""".format(
        run_id=html.escape(data["run_id"]),
        fixture_mode=str(data["fixture_mode"]).lower(),
        question=html.escape(data["question"]),
        sources=data["sources"],
        spans=data["spans"],
        rows=rows,
        gate_text=gate_text,
        candidate_count=len(data["candidates"]),
        candidate_rows=candidate_rows,
        design_status=html.escape(data["design"]["status"]),
        design_metric=html.escape(data["design"]["metric"][:180]),
        design_warnings=data["design"]["warnings"],
        paper_status=html.escape(data["paper"]["status"]),
        paper_writer=html.escape(data["paper"]["writer_mode"]),
        paper_sections=data["paper"]["sections"],
        review_status=html.escape(data["review"]["status"]),
        review_rounds=html.escape(str(data["review"]["rounds"])),
        review_accepted=html.escape(str(data["review"]["accepted"])),
        audit_status=html.escape(data["audit"]["status"]),
        audit_citations=html.escape(str(data["audit"]["citations"])),
        audit_han=html.escape(str(data["audit"]["han"])),
        audit_submission=html.escape(str(data["audit"]["submission_ready"])),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="generate demo/index.html from a real run")
    parser.add_argument("--run-dir", default="runtime_data/ese-fullrun-20261118")
    parser.add_argument("--project-run-dir", default="runtime_data/ese-fullrun-project/runs/RUN-ESE-01")
    parser.add_argument("--review-dir", default="runtime_data/ese-fullrun-project/manuscript-review")
    parser.add_argument("--out", default="demo/index.html")
    args = parser.parse_args(argv)
    data = build(args.run_dir, args.project_run_dir, args.review_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print("demo page: {0} (run {1}, {2} candidates, {3} sources)".format(
        out, data["run_id"], len(data["candidates"]), data["sources"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

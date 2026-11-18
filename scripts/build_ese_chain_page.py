"""Generate demo/run/index.html: end-to-end provenance of one real ESE run.

The replay page answers "what went in and what came out"; this page answers "where did each
artifact come from, which command produced it, what did it feed next, and where did the chain
stop". It reads one pipeline run plus its project tail (writing pack, innovation review,
manuscript review, final audit) and writes a static page. Local paths and hashes are labelled
as local artifacts; nothing here is a claim or a gate decision.
"""

import argparse
import hashlib
import html
import json
from pathlib import Path


def _read(path):
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha(path):
    target = Path(path)
    if not target.is_file():
        return ""
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _size(path):
    target = Path(path)
    return target.stat().st_size if target.is_file() else 0


def _pre(text, limit=900):
    text = str(text or "").strip()
    if not text:
        return "(empty)"
    if len(text) > limit:
        text = text[:limit] + " ..."
    return html.escape(text)


def _kv_rows(pairs):
    rows = []
    for key, value in pairs:
        rows.append("<tr><td>{0}</td><td>{1}</td></tr>".format(html.escape(str(key)), _pre(value, 400)))
    return "".join(rows)


def _artifact_rows(items):
    rows = []
    for name, path in items:
        target = Path(path)
        if not target.is_file():
            rows.append("<tr><td>{0}</td><td><code>{1}</code></td><td>-</td><td>-</td></tr>".format(
                html.escape(name), html.escape(str(path))))
            continue
        rows.append("<tr><td>{0}</td><td><code>{1}</code></td><td>{2}</td><td><code>{3}</code></td></tr>".format(
            html.escape(name), html.escape(str(path)), "{0:.1f} KB".format(_size(target) / 1024.0),
            _sha(target)[:12]))
    return "".join(rows)


def build(run_dir, project_dir, run_id, review_dir):
    run = Path(run_dir)
    project = Path(project_dir)
    review = Path(review_dir)
    demo = _read(run / "demo.json")
    literature = _read(run / "literature.json")
    synthesis = _read(run / "synthesis-matrix.json")
    ideas = _read(run / "idea.json")
    design = _read(run / "experiment.json")
    figure = _read(run / "figure.manifest.json")
    paper = _read(run / "paper.json")
    q0 = _read(run / "q0.json")
    writing = _read(project / "writing-pack.json")
    innovation = _read(project / "runs" / run_id / "innovation-review.json")
    manuscript = _read(project / "runs" / run_id / "manuscript.json")
    review_doc = _read(review / "manuscript-review.json")
    audit = _read(review / "final-audit.json")
    modules = demo.get("modules") or {}
    gates = demo.get("gates") or []
    hits = literature.get("hits") or []
    plan = literature.get("query_plan") or {}
    candidates = (ideas.get("candidates") or [])[:8]
    themes = (synthesis.get("themes") or [])[:6]
    draft = (paper.get("draft") or [])[:3]
    final_ideas = (innovation.get("final_ideas") or [])[:4]
    progression = review_doc.get("score_progression") or []
    accepted = None
    for iteration in review_doc.get("iterations") or []:
        if isinstance(iteration, dict) and "accepted" in iteration:
            accepted = bool(iteration.get("accepted"))
    artifacts = [
        ("literature", run / "literature.json"),
        ("synthesis", run / "synthesis-matrix.json"),
        ("ideas", run / "idea.json"),
        ("design", run / "experiment.json"),
        ("figure", run / "figure.manifest.json"),
        ("paper", run / "paper.json"),
        ("q0", run / "q0.json"),
        ("writing-pack", project / "writing-pack.json"),
        ("innovation-review", project / "runs" / run_id / "innovation-review.json"),
        ("manuscript", project / "runs" / run_id / "manuscript.json"),
        ("manuscript-review", review / "manuscript-review.json"),
        ("final-audit", review / "final-audit.json"),
    ]
    return {
        "run_id": str(demo.get("run_id") or run.name),
        "question": str((plan.get("question") or demo.get("topic") or "")),
        "fixture_mode": bool(demo.get("fixture_mode")),
        "models": demo.get("model_notes") or {},
        "modules": modules,
        "gates": gates,
        "ese_method": demo.get("ese_method") or {},
        "sources": [
            {"title": str(hit.get("title") or ""), "year": hit.get("year"),
             "venue": str(hit.get("venue") or ""), "full_text": bool(hit.get("full_text"))}
            for hit in hits[:10]
        ],
        "source_count": len(hits),
        "span_count": len(literature.get("spans") or []),
        "coverage": literature.get("coverage") or {},
        "themes": [{"name": str(item.get("name") or ""),
                     "sources": len(item.get("source_ids") or [])} for item in themes],
        "candidates": [
            {"title": str(item.get("title") or ""),
             "lens": str(item.get("lens") or ""),
             "hypothesis": str(item.get("hypothesis") or ""),
             "falsification": str(item.get("falsification") or ""),
             "refs": list(item.get("evidence_refs") or [])[:4]}
            for item in candidates
        ],
        "design": {
            "status": str(design.get("status") or ""),
            "hypothesis": str(design.get("hypothesis") or ""),
            "baseline": str(design.get("baseline") or ""),
            "metric": str(design.get("primary_metric") or ""),
            "controls": list(design.get("controls") or []),
            "budget": str(design.get("budget") or ""),
            "warnings": list(design.get("warnings") or []),
        },
        "figure": figure,
        "paper": {
            "status": str(paper.get("status") or ""),
            "writer_mode": str(paper.get("writer_mode") or ""),
            "sections": list(paper.get("sections") or []),
            "draft": [{"section": str(item.get("section") or ""),
                        "text": str(item.get("text") or "")} for item in draft],
        },
        "writing": writing,
        "innovation": {
            "status": str(innovation.get("status") or "not_run"),
            "rounds": innovation.get("rounds_completed"),
            "gaps": len(innovation.get("gaps") or []),
            "ideas": [
                {"title": str(item.get("title") or ""),
                 "falsification": str(item.get("falsification") or ""),
                 "problem": str(item.get("problem") or "")}
                for item in final_ideas
            ],
        },
        "manuscript": {
            "title": str(manuscript.get("title") or ""),
            "draft_sha": str(manuscript.get("draft_sha256") or ""),
        },
        "review": {
            "status": str(review_doc.get("status") or "not_run"),
            "rounds": review_doc.get("rounds_completed"),
            "accepted": accepted,
            "scores": progression,
            "accepted_revisions": review_doc.get("accepted_revisions"),
        },
        "audit": {
            "status": str(audit.get("status") or "not_run"),
            "submission_ready": bool(audit.get("submission_ready")),
            "citations": audit.get("citation_count"),
            "han": audit.get("han_character_count"),
            "claim_status": str(audit.get("claim_status") or ""),
        },
        "q0_status": str(q0.get("status") or ""),
        "artifacts": artifacts,
    }


def render(data):
    def status(name):
        value = data["modules"].get(name) or {}
        if not isinstance(value, dict):
            return str(value)
        warns = len(value.get("warnings") or [])
        return "{0}{1}".format(html.escape(str(value.get("status") or "not_run")),
                               "" if not warns else " (%d warning)" % warns)

    gates = " · ".join("{0}={1}".format(html.escape(str(g.get("gate"))), html.escape(str(g.get("status"))))
                       for g in data["gates"])
    method = data["ese_method"]
    method_missing = ", ".join(method.get("missing") or []) or "(none)"
    stage_rows = [
        ("S1 文献证据", "研究问题", "QueryPlan → 检索 → 全文解析 → span/coverage",
         "literature.json / q0.json", status("literature")),
        ("S1b 跨来源综合", "span + 来源元数据", "主题×来源矩阵", "synthesis-matrix.json", status("synthesis")),
        ("S2–S3 假设", "span + 缺口", "候选帧（falsification/lens/refs）", "idea.json", status("idea")),
        ("S4 设计+方法检查", "候选 + 方法卡", "设计草稿 + repository-mining 缺口", "experiment.json / ese-method.json", status("experiment")),
        ("S6 图", "设计/契约", "schematic SVG + manifest", "figure.manifest.json", status("figure")),
        ("S8–S12 稿件", "证据 + 设计", "非结果章节 + 结果槽 pending", "paper.json / paper.md", status("paper")),
        ("写作包", "run 产物", "证据包 + 写作契约", "writing-pack.json", "ok"),
        ("创新评审", "写作包 + 证据", "缺口→候选→三评审→修订", "innovation-review.json", data["innovation"]["status"]),
        ("中文初稿", "写作包 + 创新评审", "立场性综述初稿", "drafts/review.md", "generated" if data["manuscript"]["title"] else "not_run"),
        ("手稿评审", "初稿 + 证据包", "rubric 评审→修订→复评", "manuscript-review.json", data["review"]["status"]),
        ("成稿审计", "评审后初稿", "引用/数值/结构/claim 审计", "final-audit.json", data["audit"]["status"]),
    ]
    rows = "".join(
        "<tr><td>{0}</td><td>{1}</td><td>{2}</td><td><code>{3}</code></td><td>{4}</td></tr>".format(
            html.escape(a), html.escape(b), html.escape(c), html.escape(d), html.escape(e))
        for a, b, c, d, e in stage_rows
    )
    sources = "".join(
        "<li>{0} <span class='meta'>({1}, {2}{3})</span></li>".format(
            html.escape(item["title"]), html.escape(str(item["year"])), html.escape(item["venue"]),
            "" if item["full_text"] else ", no full text")
        for item in data["sources"]
    )
    themes = " · ".join("{0} ({1} sources)".format(html.escape(item["name"]), item["sources"])
                        for item in data["themes"]) or "(none)"
    candidates = "".join(
        "<div class='card'><b>{0}</b><p class='meta'>lens: {1} · refs: {2}</p>"
        "<p><b>hypothesis</b>: {3}</p><p><b>falsification</b>: {4}</p></div>".format(
            html.escape(item["title"]), html.escape(item["lens"]),
            html.escape(", ".join(item["refs"])),
            _pre(item["hypothesis"], 380), _pre(item["falsification"], 300))
        for item in data["candidates"]
    ) or "<p>(no candidates)</p>"
    design = data["design"]
    design_rows = _kv_rows([
        ("status", design["status"]), ("hypothesis", design["hypothesis"]),
        ("baseline", design["baseline"]), ("primary_metric", design["metric"]),
        ("controls", "; ".join(design["controls"])), ("budget", design["budget"]),
        ("warnings", " | ".join(design["warnings"])),
        ("ese-method missing", method_missing),
    ])
    figure_rows = _kv_rows([(key, value) for key, value in sorted(data["figure"].items())][:8])
    paper = data["paper"]
    drafts = "".join(
        "<div class='card'><b>{0}</b><pre>{1}</pre></div>".format(
            html.escape(item["section"]), _pre(item["text"], 700))
        for item in paper["draft"]
    ) or "<p>(no model draft)</p>"
    ideas = "".join(
        "<div class='card'><b>{0}</b><p class='meta'>problem: {1}</p><p>falsification: {2}</p></div>".format(
            html.escape(item["title"]), _pre(item["problem"], 240), _pre(item["falsification"], 300))
        for item in data["innovation"]["ideas"]
    ) or "<p>(no final ideas)</p>"
    review = data["review"]
    audit = data["audit"]
    artifact_rows = _artifact_rows(data["artifacts"])
    models = "".join("<li>{0}: {1}</li>".format(html.escape(k), html.escape(str(v)))
                     for k, v in sorted(data["models"].items())) or "<li>(no model notes)</li>"
    coverage = data["coverage"]
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>真实 ESE 全链运行的来龙去脉</title>
<meta name="description" content="一次真实 ESE 运行的完整血缘：输入、每阶段命令与产物、门禁、创新评审、手稿评审与成稿审计；本页由产物生成。" />
<link rel="stylesheet" href="../../assets/demo-legibility.css" />
<style>
body{{margin:0;padding:30px;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.65;color:#1f2937;background:#f8fafc}}
main{{max-width:1120px;margin:0 auto;background:#fff;border:1px solid #e5e9f0;border-radius:14px;padding:26px}}
h1{{font-size:23px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin:8px 0}}
td,th{{border-bottom:1px solid #e5e9f0;padding:6px 8px;text-align:left;vertical-align:top}}
th{{color:#5b6472;font-weight:600}}
.meta{{color:#5b6472;font-size:12px}} .badge{{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;background:#eef2ff;color:#2563eb;margin-right:6px}}
.card{{border:1px solid #e5e9f0;border-radius:10px;padding:10px 12px;margin:8px 0;background:#fbfcfe}}
pre{{white-space:pre-wrap;word-break:break-word;font-size:12px;background:#f1f5f9;padding:8px;border-radius:8px;margin:6px 0}}
.flow{{font-size:12px;background:#f1f5f9;padding:10px;border-radius:8px;white-space:pre-wrap}}
.boundary{{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:10px 14px;font-size:13px}}
a{{color:#2563eb}} code{{font-size:11.5px}}
</style></head>
<body><main data-dl-page="demo" data-demo-chain="{run_id}">
<span class="badge">REAL RUN · 非 SIM</span><span class="badge">只读血缘页</span>
<h1>真实 ESE 全链运行的来龙去脉</h1>
<p class="meta">run: {run_id} · fixture_mode: {fixture} · 本页由 scripts/build_ese_chain_page.py 从真实产物生成；路径与短哈希是本机产物指纹。</p>
<p><b>研究问题</b>：{question}</p>
<p class="meta">模型供给：</p><ul class="meta">{models}</ul>

<h2>1. 一图看清链路</h2>
<div class="flow">问题 / QueryPlan
  → 检索与全文解析（{source_count} sources）
  → span + coverage（{span_count} spans，Q0 {q0}）
  → S1b 跨来源综合（{theme_count} themes）
  → S2–S3 候选（{candidate_count} 条）
  → S4 设计 + repository-mining 方法缺口
  → S6 schematic 图
  → S8–S12 稿件（writer_mode={writer_mode}，结果槽 pending）
  → 写作包 → 创新评审（{inn_status}）
  → 中文初稿 → 手稿评审（{review_status}）→ 成稿审计（{audit_status}）
  → 门禁：{gates}；没有 Claim/EA/签名</div>

<h2>2. 每阶段：输入 → 动作 → 产物</h2>
<table><thead><tr><th>阶段</th><th>输入</th><th>动作</th><th>输出</th><th>状态</th></tr></thead><tbody>{stage_rows}</tbody></table>

<h2>3. 输入与覆盖</h2>
<p class="meta">coverage: {coverage} · Q0: {q0}</p>
<ul>{sources}</ul>

<h2>4. 综合与候选</h2>
<p><b>主题</b>：{themes}</p>
{candidates}

<h2>5. S4 设计与方法缺口（repository-mining）</h2>
<table><tbody>{design_rows}</tbody></table>
<p class="meta">方法检查是 advisory：缺 {method_missing}；它不改变设计状态或门禁。</p>

<h2>6. 图与稿件</h2>
<table><tbody>{figure_rows}</tbody></table>
<p>paper: {paper_status} · writer_mode: {writer_mode} · sections: {paper_sections}</p>
{drafts}

<h2>7. 创新评审</h2>
<p>状态：{inn_status} · rounds：{inn_rounds} · gaps：{inn_gaps}</p>
{ideas}

<h2>8. 初稿、评审与审计</h2>
<p>初稿：{manuscript_title}</p>
<p>评审：{review_status} · rounds：{review_rounds} · accepted：{review_accepted} · scores：{review_scores} · revisions：{review_revs}</p>
<p>审计：{audit_status} · citations：{audit_citations} · 汉字：{audit_han} · claim_status：{claim_status} · submission_ready：{submission_ready}</p>

<h2>9. 产物清单（本机指纹）</h2>
<table><thead><tr><th>名字</th><th>路径</th><th>大小</th><th>sha256(12)</th></tr></thead>
<tbody>{artifact_rows}</tbody></table>

<h2>10. 门禁与签名边界</h2>
<p>{gates}</p>
<div class="boundary">本页只回放一次真实运行：G1/G2/G3/S5b/G5 仍待人签；没有 Claim/EA/签名；创新评审与手稿评审是模型辅助的过程信号，不是同行评审；accepted 不等于通过，ready_for_human_review 不等于可投稿。产物路径来自本机 runtime_data，不入发布包。</div>
<p><a href="../">← 回放摘要</a> · <a href="../../">首页</a> · <a href="../run/">主版本来龙去脉</a> · <a href="../run-frontier/">24 篇版本来龙去脉</a> · <a href="../frontier/">24 篇前沿语料回放</a> · 设计记录：design/111、design/122、design/123</p>
</main>
<script src="../../assets/demo-legibility.js"></script>
</body></html>""".format(
        run_id=html.escape(data["run_id"]),
        fixture=str(data["fixture_mode"]).lower(),
        question=html.escape(data["question"]),
        models=models,
        source_count=data["source_count"],
        span_count=data["span_count"],
        q0=html.escape(data["q0_status"]),
        theme_count=len(data["themes"]),
        candidate_count=len(data["candidates"]),
        writer_mode=html.escape(paper["writer_mode"]),
        inn_status=html.escape(data["innovation"]["status"]),
        review_status=html.escape(review["status"]),
        audit_status=html.escape(audit["status"]),
        gates=html.escape(gates),
        stage_rows=rows,
        coverage=_pre(coverage, 260),
        sources=sources,
        themes=themes,
        candidates=candidates,
        design_rows=design_rows,
        method_missing=html.escape(method_missing),
        figure_rows=figure_rows,
        paper_status=html.escape(paper["status"]),
        paper_sections=html.escape(str(len(paper["sections"]))),
        drafts=drafts,
        inn_rounds=html.escape(str(data["innovation"]["rounds"])),
        inn_gaps=data["innovation"]["gaps"],
        ideas=ideas,
        manuscript_title=html.escape(data["manuscript"]["title"] or "(not found)"),
        review_rounds=html.escape(str(review["rounds"])),
        review_accepted=html.escape(str(review["accepted"])),
        review_scores=html.escape(str(review["scores"])),
        review_revs=html.escape(str(review["accepted_revisions"])),
        audit_citations=html.escape(str(audit["citations"])),
        audit_han=html.escape(str(audit["han"])),
        claim_status=html.escape(audit["claim_status"]),
        submission_ready=html.escape(str(audit["submission_ready"])),
        artifact_rows=artifact_rows,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="generate the ESE chain provenance page")
    parser.add_argument("--run-dir", default="runtime_data/ese-fullrun-20261118")
    parser.add_argument("--project-dir", default="runtime_data/ese-fullrun-project")
    parser.add_argument("--run-id", default="RUN-ESE-01")
    parser.add_argument("--review-dir", default="runtime_data/ese-fullrun-project/manuscript-review")
    parser.add_argument("--out", default="demo/run/index.html")
    args = parser.parse_args(argv)
    data = build(args.run_dir, args.project_dir, args.run_id, args.review_dir)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print("chain page: {0} (run {1}, {2} sources, {3} candidates)".format(
        out, data["run_id"], data["source_count"], len(data["candidates"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

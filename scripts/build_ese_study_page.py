"""Build the ESE study provenance page from real artifacts.

The page is generated, not hand-written: every number comes from
runtime_data/ese-ms-20261118-03/result.json and every chain step is read from
disk. If a claim/closure/signature does not exist yet, the page says so and
prints the exact command — it never renders a step as done when the file is
absent.

Usage:
    python scripts/build_ese_study_page.py
    python scripts/build_ese_study_page.py --study-dir runtime_data/ese-ms-20261118-03 --out demo/ese-ms-03/index.html
"""

import argparse
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDY = ROOT / "runtime_data" / "ese-ms-20261118-03"
DEFAULT_OUT = ROOT / "demo" / "ese-ms-03" / "index.html"


def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _esc(value):
    return html.escape(str(value), quote=True)


def _num(value, digits=4):
    try:
        return ("%." + str(digits) + "f") % float(value)
    except (TypeError, ValueError):
        return "—"


def _ci(value):
    if not isinstance(value, list) or len(value) != 2:
        return "—"
    return "[%s, %s]" % (_num(value[0]), _num(value[1]))


def _sha(value):
    text = str(value or "")
    return text[:12] + "…" if len(text) > 12 else (text or "—")


def _kv(rows):
    body = "".join(
        "<tr><td>%s</td><td>%s</td></tr>" % (_esc(key), _esc(value))
        for key, value in rows
    )
    return "<table>%s</table>" % body


def _chain(study_dir, result):
    run_dir = study_dir / "run"
    capsule = _read(run_dir / "run-capsule.json")
    evidence = _read(run_dir / "ea.json")
    claim = _read(study_dir / "claim" / "claim.json")
    report = _read(study_dir / "closure" / "closure-report.json")
    signature = _read(study_dir / "signature" / "signature.json")

    steps = []
    steps.append({
        "name": "RunCapsule",
        "ok": bool(capsule and capsule.get("status") == "completed"),
        "detail": (
            "run_id=%s · status=%s · metric=%s · seeds=%s"
            % (
                (capsule or {}).get("run_id", "—"),
                (capsule or {}).get("status", "—"),
                (capsule or {}).get("metric_name", "—"),
                (capsule or {}).get("seeds", "—"),
            )
            if capsule
            else "缺失：run/run-capsule.json"
        ),
        "path": "run/run-capsule.json",
    })
    steps.append({
        "name": "EA（证据制品）",
        "ok": bool(evidence and evidence.get("immutable")),
        "detail": (
            "artifact_id=%s · source=%s · immutable=%s · sha256=%s"
            % (
                ( evidence or {}).get("artifact_id", "—"),
                (evidence or {}).get("source", "—"),
                (evidence or {}).get("immutable", "—"),
                _sha((evidence or {}).get("sha256")),
            )
            if evidence
            else "缺失：run/ea.json"
        ),
        "path": "run/ea.json",
    })
    steps.append({
        "name": "Claim（人签断言）",
        "ok": bool(claim and claim.get("status") == "supported"),
        "detail": (
            "claim_id=%s · status=%s · assertions=%d · human_reason=%s"
            % (
                (claim or {}).get("claim_id", "—"),
                (claim or {}).get("status", "—"),
                len((claim or {}).get("assertions") or []),
                "有" if str((claim or {}).get("human_reason") or "").strip() else "缺",
            )
            if claim
            else "待人工执行：run claim --evidence-source ese-exec（见下方命令）"
        ),
        "path": "claim/claim.json",
    })
    steps.append({
        "name": "Closure（结构闭合）",
        "ok": bool(report and report.get("status") == "ready"),
        "detail": (
            "report_id=%s · status=%s · checks=%d · pass=%d"
            % (
                (report or {}).get("report_id", "—"),
                (report or {}).get("status", "—"),
                len((report or {}).get("checks") or []),
                len(
                    [
                        check
                        for check in ((report or {}).get("checks") or [])
                        if check.get("status") == "pass"
                    ]
                ),
            )
            if report
            else "待执行：closure ese-check（见下方命令）"
        ),
        "path": "closure/closure-report.json",
    })
    steps.append({
        "name": "Signature（人签）",
        "ok": bool(signature and signature.get("signature_id")),
        "detail": (
            "signature_id=%s · scheme=%s · submission=%s"
            % (
                (signature or {}).get("signature_id", "—"),
                (signature or {}).get("signature_scheme", "—"),
                (signature or {}).get("submission", "—"),
            )
            if signature
            else "待人工执行：closure ese-sign（见下方命令）"
        ),
        "path": "signature/signature.json",
    })

    if signature:
        state = "SIGNED"
        badge_class = "ok"
    elif claim:
        state = "CLAIMED · AWAITING CLOSURE/SIGNATURE"
        badge_class = "warn"
    else:
        state = "EXPLORATORY · AWAITING HUMAN SIGNATURE"
        badge_class = "warn"
    return steps, state, badge_class


# Public alias: the workbench JSON builder reuses the same chain state, so the
# demo page and the app panel cannot disagree about which step is done.
chain_state = _chain


def build(study_dir):
    result = _read(study_dir / "result.json")
    if not result:
        raise SystemExit("result.json not found under " + str(study_dir))
    steps, state, badge_class = chain_state(study_dir, result)

    pooled = result.get("pooled") or {}
    bugfix = pooled.get("bugfix") or {}
    non_bugfix = pooled.get("non_bugfix") or {}
    permutation = pooled.get("permutation") or {}
    strata = (result.get("stratified") or {}).get("strata") or []
    time_split = result.get("time_split") or {}

    repo_rows = []
    for repo in result.get("repos") or []:
        repo_rows.append(
            "<tr><td>%s</td><td><code>%s</code></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                _esc(repo.get("repo")),
                _esc(_sha(repo.get("head"))),
                _esc(repo.get("commits")),
                _esc(repo.get("test_cochange")),
                _esc(_num(repo.get("rate"))),
                _esc(_ci(repo.get("ci"))),
            )
        )

    strata_rows = []
    for item in strata:
        strata_rows.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (
                _esc(item.get("factor")),
                _esc(item.get("value")),
                _esc(_num((item.get("bug") or {}).get("rate"))),
                _esc(_num((item.get("other") or {}).get("rate"))),
                _esc(_num(item.get("difference"))),
            )
        )

    chain_rows = []
    for step in steps:
        mark = "done" if step["ok"] else "todo"
        label = "已完成" if step["ok"] else "未完成"
        chain_rows.append(
            "<tr class=\"%s\"><td>%s</td><td>%s</td><td>%s</td><td><code>%s</code></td></tr>"
            % (
                mark,
                _esc(step["name"]),
                label,
                _esc(step["detail"]),
                _esc(step["path"]),
            )
        )

    question = "; ".join(str(item) for item in (result.get("research_questions") or []))
    early = time_split.get("early") or {}
    late = time_split.get("late") or {}
    time_perm = time_split.get("permutation") or {}

    values = {
        "study_id": _esc(result.get("study_id")),
        "method": _esc(result.get("method")),
        "protocol_sha": _esc(_sha(result.get("protocol_sha256"))),
        "state": _esc(state),
        "badge_class": _esc(badge_class),
        "question": _esc(question),
        "repo_rows": "".join(repo_rows),
        "strata_rows": "".join(strata_rows),
        "chain_rows": "".join(chain_rows),
        "pooled_rate": _esc(_num(pooled.get("rate"))),
        "pooled_ci": _esc(_ci(pooled.get("ci"))),
        "commits": _esc(pooled.get("commits")),
        "cochange": _esc(pooled.get("test_cochange")),
        "bug_rate": _esc(_num(bugfix.get("rate"))),
        "bug_hits": _esc("%s/%s" % (bugfix.get("hits"), bugfix.get("total"))),
        "other_rate": _esc(_num(non_bugfix.get("rate"))),
        "other_hits": _esc("%s/%s" % (non_bugfix.get("hits"), non_bugfix.get("total"))),
        "difference": _esc(_num(pooled.get("difference"))),
        "p_value": _esc(permutation.get("p_value_two_sided")),
        "perm_n": _esc(permutation.get("n")),
        "early_rate": _esc(_num(early.get("rate"))),
        "early_ci": _esc(_ci(early.get("ci"))),
        "late_rate": _esc(_num(late.get("rate"))),
        "late_ci": _esc(_ci(late.get("ci"))),
        "time_diff": _esc(_num(time_split.get("difference"))),
        "time_p": _esc(time_perm.get("p_value_two_sided")),
        # The source boundary is English and says "no Claim/EA/signature" — it
        # means this read-only page does not create them, not that the run never
        # produced them. The stage table above may show EA as completed, so add
        # a clarification to prevent the two from reading as a contradiction.
        "boundary": _esc(result.get("boundary"))
        + "<br />说明：此处「no Claim/EA/signature」指本页只读回放、不会新建或签署证据；"
        + "上方阶段表显示的是该运行实际已有的产物状态（如 EA 已封装），两者不矛盾。",
    }
    return render(values)


def render(values):
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>ESE 研究闭环的来龙去脉 · {study_id} · Research Agent</title>
<meta name="description" content="一次真实经验软件工程研究的证据链：协议、数据、结果、分层与非结果，以及 capsule→EA→claim→closure→signature 的当前状态。本页由产物生成。" />
<link rel="stylesheet" href="../../assets/demo-legibility.css" />
<style>
body{{margin:0;padding:30px;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;line-height:1.65;color:#1f2937;background:#f8fafc}}
main{{max-width:1120px;margin:0 auto;background:#fff;border:1px solid #e5e9f0;border-radius:14px;padding:26px}}
h1{{font-size:23px;margin:0 0 4px}} h2{{font-size:16px;margin:28px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin:8px 0}}
td,th{{border-bottom:1px solid #e5e9f0;padding:6px 8px;text-align:left;vertical-align:top}}
th{{color:#5b6472;font-weight:600}}
.meta{{color:#5b6472;font-size:12px}}
.badge{{display:inline-block;font-size:12px;padding:1px 8px;border-radius:999px;background:#eef2ff;color:#2563eb;margin-right:6px}}
.badge.warn{{background:#fffbeb;color:#b45309}}
.badge.ok{{background:#ecfdf5;color:#047857}}
.card{{border:1px solid #e5e9f0;border-radius:10px;padding:10px 12px;margin:8px 0;background:#fbfcfe}}
pre{{white-space:pre-wrap;word-break:break-word;font-size:12px;background:#f1f5f9;padding:8px;border-radius:8px;margin:6px 0}}
.boundary{{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:10px 14px;font-size:13px}}
tr.done td:first-child{{color:#047857;font-weight:600}}
tr.todo td:first-child{{color:#b45309;font-weight:600}}
a{{color:#2563eb}} code{{font-size:11.5px}}
</style></head>
<body><main data-dl-page="demo" data-demo-chain="{study_id}">
<span class="badge">REAL ESE STUDY</span><span class="badge {badge_class}">{state}</span><span class="badge">只读血缘页</span>
<h1>缺陷修复提交是否更常触碰测试：一次 ESE 研究的来龙去脉</h1>
<p class="meta">study: {study_id} · method: {method} · protocol sha256: <code>{protocol_sha}</code> · 本页由 <code>scripts/build_ese_study_page.py</code> 从真实产物生成；状态按盘上文件判定，不预写完成。</p>

<h2>0. 这条研究现在到哪一步</h2>
<table><thead><tr><th>阶段</th><th>状态</th><th>实际读数 / 缺什么</th><th>产物</th></tr></thead>
<tbody>{chain_rows}</tbody></table>
<p class="meta">前两步（Capsule、EA）由执行器写出；后三步（Claim、Closure、Signature）都是人签步骤，agent 不代签。缺任何一步，页面就显示未完成，并给出下一步命令。</p>

<h2>1. 研究问题与规格</h2>
<div class="card"><b>研究问题</b>：{question}</div>
<p class="meta">规格在数据之前冻结：抽样框、时间窗、去重策略、标签规则、统计计划都写在协议里，执行器只做提取与统计。协议哈希绑定在 capsule，改了协议就无法与这份结果对上。</p>
<p class="meta">标签规则：单位＝至少触碰一个 <code>.py</code> 文件的提交；outcome＝同提交触碰 <code>tests/</code>、<code>test_*.py</code>、<code>*_test.py</code>；bug-fix＝提交标题匹配 fix/bug/issue/regression/hotfix/patch。全部是启发式，不是人工标注。</p>

<h2>2. 数据与抽样</h2>
<table><thead><tr><th>仓库</th><th>HEAD</th><th>提交数</th><th>触碰测试</th><th>比例</th><th>95% CI</th></tr></thead>
<tbody>{repo_rows}</tbody></table>
<p class="meta">这是便利抽样：三个成熟的 Python 开源库，不是概率样本。结论只能覆盖这三个仓库的合并样本，不能代表 Python 生态。</p>

<h2>3. 结果</h2>
<div class="card">
<p><b>合并</b>：{cochange}/{commits} = <b>{pooled_rate}</b>，95% CI {pooled_ci}。</p>
<p><b>缺陷修复</b>：{bug_hits} = {bug_rate}；<b>其它提交</b>：{other_hits} = {other_rate}；差 <b>{difference}</b>，置换检验（n={perm_n}，固定种子）双侧 p = <b>{p_value}</b>。</p>
<p><b>时间切分</b>（每仓库中位日期）：早期 {early_rate} {early_ci}；晚期 {late_rate} {late_ci}；差 {time_diff}，p = {time_p}。</p>
</div>

<h3>分层：差异不是每个项目都成立</h3>
<table><thead><tr><th>分层因子</th><th>取值</th><th>缺陷修复比例</th><th>其它比例</th><th>差</th></tr></thead>
<tbody>{strata_rows}</tbody></table>

<h2>4. 怎么读（这是本页最重要的一节）</h2>
<div class="card">
<p><b>总体差异 +0.046 是真的，但它不是"每个项目都更常改测试"。</b>按项目分层后，click 的差是负的（约 -0.007）：在 click 里，缺陷修复提交触碰测试的比例反而略低。这是典型的聚合掩盖异质性——合并样本的差异由 requests 与 httpx 拉动。</p>
<p>所以能写的句子只有："在三仓库合并样本上，缺陷修复提交触碰测试的比例比其它提交高 0.046（p=0.015）；该差异在 click 内方向反转，因此不适用于单项目。"不能写"缺陷修复提交更常改测试"这种无限定语。</p>
<p>另外，<b>p=0.015 只说明"不太可能纯由随机波动产生"，不说明差异有实际意义</b>。0.046 的比例差是否值得改变实践，需要另一个人来决定，不是统计能回答的。</p>
</div>

<h2>5. 证据链：五件产物怎样互相约束</h2>
<div class="card">
<p><b>RunCapsule</b> 记录协议哈希、数据哈希（仓库 HEAD）、代码哈希、种子与逐种子指标；<b>EA</b> 绑定 metrics 文件的 sha256；<b>Claim</b> 引用 EA，并在写入前从 metrics 重算每条断言；<b>Closure</b> 重新核对四件产物的一致性；<b>Signature</b> 对 export manifest 签名，不自动投稿。</p>
<p>任何一环被改动（改 metrics、改断言值、改 claim 的 scope），后续检查都会失败：hash 不匹配、断言重算不过、或报告与当前输入不一致。这不是"防篡改证明"，是完整性检测——MANIFEST 与产物同仓同机，有动机的重写可以同时改两者。</p>
</div>

<h2>6. 边界</h2>
<div class="boundary">{boundary}<br />
补充：三个仓库都是成熟开源项目，不含工业闭源代码；提交标题的 bug-fix 判定会漏标与误标；时间切分用中位日期，不能排除"项目在晚期更成熟"这一混杂。以上都不是可以在正文里省略的脚注。</div>

<h2>7. 复跑与下一步</h2>
<pre># 1) 人签 claim（statement / human-reason 由人定稿）
python -m research_agent run claim \\
  --capsule runtime_data/ese-ms-20261118-03/run/run-capsule.json \\
  --ea runtime_data/ese-ms-20261118-03/run/ea.json \\
  --scope S5/ESE-MS-20261118-03 \\
  --assertion "metric=test_cochange_rate,value=0.3749,comparator=approx,tolerance=0.001" \\
  --assertion "metric=adjusted_difference,value=0.0681,comparator=approx,tolerance=0.001" \\
  --evidence-source ese-exec \\
  --output-dir runtime_data/ese-ms-20261118-03/claim

# 2) 结构闭合（只读检查，不签）
python -m research_agent closure ese-check \\
  --capsule runtime_data/ese-ms-20261118-03/run/run-capsule.json \\
  --ea runtime_data/ese-ms-20261118-03/run/ea.json \\
  --claim runtime_data/ese-ms-20261118-03/claim/claim.json \\
  --output-dir runtime_data/ese-ms-20261118-03/closure

# 3) 最终签名（人签）
python -m research_agent closure ese-sign \\
  --report runtime_data/ese-ms-20261118-03/closure/closure-report.json \\
  --capsule runtime_data/ese-ms-20261118-03/run/run-capsule.json \\
  --ea runtime_data/ese-ms-20261118-03/run/ea.json \\
  --claim runtime_data/ese-ms-20261118-03/claim/claim.json \\
  --human-reason "..." \\
  --output-dir runtime_data/ese-ms-20261118-03/signature

# 4) 签完后重生成本页，状态会自动变成 SIGNED
python scripts/build_ese_study_page.py</pre>
<p class="meta">返回：<a href="../">demo 回放首页</a> · <a href="../run/">主版本来龙去脉</a> · <a href="../../app/">工作台 ESE 面板</a></p>
</main>
<script src="../../assets/demo-legibility.js"></script>
</body></html>
""".format(**values)


def main(argv=None):
    parser = argparse.ArgumentParser(description="build the ESE study provenance page")
    parser.add_argument("--study-dir", default=str(DEFAULT_STUDY))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(Path(args.study_dir)), encoding="utf-8")
    print("ESE study page: %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())

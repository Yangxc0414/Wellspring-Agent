// Six acts; the hero promises a "90 秒演示", so each act gets 15s (6*15=90). The previous 6.2s
// made the whole auto-run ~37s, contradicting the button copy and rushing dense acts.
const ACT_MS = 15000;
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const MODULES = {
  literature: { label: "文献调研", kind: "literature" },
  idea: { label: "假设收敛", kind: "idea" },
  experiment: { label: "实验设计", kind: "experiment" },
  figure: { label: "科研绘图", kind: "figure" },
  paper: { label: "论文契约", kind: "paper" },
  grant: { label: "基金申报", kind: "grant" }
};
const ORDER = ["literature", "idea", "experiment", "figure", "paper", "grant"];
const ACTS = [
  {
    key: "spec", name: "契约", sub: "SPEC / MODULE", title: "先写契约，再写代码。",
    noteTitle: "最小的可演进单元",
    noteBody: "每个子智能体都有 SPEC.md。改行为先改契约，再用 CLI 做最小更新；正文与未涉及字段保持不动。",
    noteFact: "6", noteFactLabel: "MODULE SPECS", tags: ["SPEC", "minimal diff", "changelog"]
  },
  {
    key: "evidence", name: "证据", sub: "SPAN / COVERAGE", title: "证据不是聊天记录。",
    noteTitle: "摘要不是证据",
    noteBody: "检索、全文、句级 span、覆盖回执分开记录；没有全文就不能生成 span，更不能创建 Claim。",
    noteFact: "0", noteFactLabel: "claims from S1", tags: ["QueryPlan", "Span", "CoverageReceipt"]
  },
  {
    key: "figure", name: "图", sub: "SVG / PROVENANCE", title: "图也要有 provenance。",
    noteTitle: "先审计，再交付",
    noteBody: "AstraDraw 负责 scene→SVG；我们审计 XML、ID、文本、外部引用和 aria，并把哈希写进 manifest。",
    noteFact: "PASS", noteFactLabel: "SVG AUDIT", tags: ["scene hash", "svg hash", "no external"]
  },
  {
    key: "paper", name: "稿件", sub: "SLOT / GATE", title: "写作可以并行，结果不能抢跑。",
    noteTitle: "结果槽保持 pending",
    noteBody: "论文和基金只产骨架。没有 EA/Claim，结果槽不填；G5 导出保持 blocked，示意图不能绑成结果图。",
    noteFact: "5", noteFactLabel: "PENDING SLOTS", tags: ["PaperContract", "G3", "G5 blocked"]
  },
  {
    key: "boundary", name: "边界", sub: "CLAIM / NEXT", title: "不宣称“通用 AI 科学家”。",
    noteTitle: "把不能说的说清楚",
    noteBody: "当前是 fixture、无 API、无真实 run/EA 的纵切。我们展示的是工程差异与可检验假设，不是论文效果。",
    noteFact: "0", noteFactLabel: "API CALLS", tags: ["fixture", "H1–H4", "next: OpenAlex / EA"]
  },
  {
    key: "validity", name: "度量", sub: "RAW / AUC", title: "一个稳健的交互，也可能只是度量的产物。",
    noteTitle: "0/4 不是“无效应”",
    noteBody: "64 种子扩样（97–160）：raw 交互 4/4 判定；AUC 交互 0/4，且 breast/iris/wine 的 AUC 上界低于 raw 效应量级。digits 96 种子合并后只是 borderline（AUC 上界 0.1378 vs raw 0.1403）。结论是效应量依赖度量，不是无效应。",
    noteFact: "4/4", noteFactLabel: "RAW · 0/4 AUC", tags: ["pre-registered", "MDE80", "metric validity"]
  },
  {
    key: "feedback", name: "判定", sub: "FEEDBACK / ACTION", title: "反馈被写下，不等于被用上。",
    noteTitle: "7.5% 走完闭环，25 次拿的是随机反馈",
    noteBody: "PerturbTrace 把闭环拆成反馈→状态→行动→结果逐段打分：576 次转换只有 43 次（7.5%）走完全程，其中 25 次拿的还是随机反馈，真实反馈也没稳定赢过随机。判定消费（策略②）要验证的正是：行动是否按证据质量变。",
    noteFact: "7.5%", noteFactLabel: "FULL FEEDBACK LOOP", tags: ["PerturbTrace", "Q2", "M1"]
  }
];
const CHECK_LABELS = {
  root: "root svg", size: "width / height / viewBox", ids_unique: "unique ids",
  text_count: "text nodes", role_img: "role=img", labelled: "aria-labelledby",
  has_title: "title", has_desc: "desc", aria_targets: "aria targets"
};

let state = {
  data: null,
  specs: [],
  act: 0,
  playing: false,
  elapsed: 0,
  startedAt: 0,
  raf: null,
  autoTimer: null,
  presenting: false
};

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const available = () => ORDER.filter((id) => id !== "grant" || state.data?.modules?.grant);
const statusOf = (id) => state.data?.modules?.[id]?.status || "not_run";
const specOf = (id) => state.specs.find((spec) => spec.id === id);
const moduleMeta = (id) => MODULES[id] || { label: id, kind: id };

function renderRail() {
  $("act-rail").innerHTML = ACTS.map((act, index) => `<button type="button" class="act-btn ${state.act === index ? "is-on" : ""} ${index < state.act ? "is-done" : ""}" data-act="${index}" aria-current="${state.act === index ? "step" : "false"}">
    <span class="act-no">0${index + 1}</span>
    <span><b class="act-name">${esc(act.name)}</b><span class="act-sub">${esc(act.sub)}</span></span>
    <span class="act-mark" aria-hidden="true"></span>
  </button>`).join("");
  // on the horizontal mobile rail the active act can sit off-screen; keep it in view
  const on = $("act-rail").querySelector(".act-btn.is-on");
  if (on) on.scrollIntoView({ block: "nearest", inline: "nearest", behavior: REDUCED ? "auto" : "smooth" });
}

function noteFor(index) {
  const act = ACTS[index];
  // 右侧数字必须与左侧画布同源：槽位 pending 数从 paper.slots 现算，避免硬编码 5 与 4 打架。
  let fact = act.noteFact;
  let label = act.noteFactLabel;
  const slots = state.data?.modules?.paper?.slots;
  if (act.key === "paper" && Array.isArray(slots)) {
    fact = String(slots.filter((slot) => slot.status === "pending_evidence").length);
    label = "PENDING SLOTS";
  }
  return `<span class="note-kicker">WHY IT MATTERS</span><b class="note-title">${esc(act.noteTitle)}</b><p class="note-body">${esc(act.noteBody)}</p>
    <div class="note-tags">${act.tags.map((tag) => `<span class="note-tag">${esc(tag)}</span>`).join("")}</div>
    <div class="note-fact"><b>${esc(fact)}</b><span>${esc(label)}</span></div>`;
}

function specAct() {
  const ids = available();
  return `<div class="act-head"><p class="eyebrow">ACT 01 / SPEC</p><h2>${esc(ACTS[0].title)}</h2><p>六模块同构：输入、输出、门禁、不变量、实现边界都写在 Markdown 里；代码读取版本，CLI 只改指定字段。</p></div>
    <div class="act-metrics"><span><b>${ids.length}</b> 模块 SPEC</span><span><b>version + changelog</b> 变更留痕</span><span><b>1</b> 次只改一个模块</span><span><b>tests first</b> 契约先行</span></div>
    <div class="spec-grid">${ids.map((id) => `<article class="spec-card" data-kind="${moduleMeta(id).kind}"><b>${esc(moduleMeta(id).label)}</b><small>${esc(specOf(id)?.stage || "")} · v${esc(specOf(id)?.version || state.data.spec_versions?.[id] || "—")}</small><em>${esc(statusOf(id))}</em></article>`).join("")}</div>
    <div class="spec-console"><span class="prompt">$</span> python -m research_agent spec update figure \\
  --version 0.1.1 --status pilot \\
  --changelog "最小改进：增加 SVG 审计"
<span class="prompt">→</span> body preserved · changelog appended · no cross-module edit</div>
    <div class="spec-points"><span>SPEC = single source</span><span>最小的 diff</span><span>version / changelog</span><span>tests first</span></div>
    <p class="source-note">数据来源：<code>data/specs.json</code>（由 <code>workspace export</code> 从 modules/*/SPEC.md 派生）· 版本与状态为当前检出值</p>`;
}

function evidenceAct() {
  const lit = state.data.modules.literature || {};
  const coverage = lit.coverage || {};
  const spans = (lit.spans || []).slice(0, 3);
  return `<div class="act-head"><p class="eyebrow">ACT 02 / EVIDENCE</p><h2>${esc(ACTS[1].title)}</h2><p>检索计划、来源命中、全文读取、句级 span 和覆盖缺口分开记录。摘要-only 只能作为线索，不能成为证据。</p></div>
    <div class="metric-row">
      <div class="metric"><b data-count="${coverage.sources_found ?? 0}">0</b><span>SOURCES FOUND</span><em>${coverage.sources_read ?? 0} full texts read</em></div>
      <div class="metric"><b data-count="${coverage.spans_extracted ?? 0}">0</b><span>SPANS EXTRACTED</span><em>sentence-level anchors</em></div>
      <div class="metric"><b data-count="${(coverage.gaps || []).length}">0</b><span>COVERAGE GAPS</span><em>reported, not hidden</em></div>
    </div>
    <div class="flow-line"><span class="flow-step">QueryPlan</span><span class="flow-arrow">→</span><span class="flow-step">SourceHit</span><span class="flow-arrow">→</span><span class="flow-step">full text</span><span class="flow-arrow">→</span><span class="flow-step">Span</span><span class="flow-arrow">→</span><span class="flow-step">CoverageReceipt</span></div>
    <div class="span-stack">${spans.map((span) => `<div class="span-item"><code>${esc(span.span_id)} · ${esc(span.section)}</code>${esc(span.text)}</div>`).join("") || `<div class="span-item">没有 span。先补全文。</div>`}</div>
    <div class="gap-line">${(coverage.gaps || []).map((gap) => `<span class="gap-chip">${esc(gap.code)}</span>`).join("") || `<span class="gap-chip">no gap reported</span>`}</div>
    <p class="source-note">数据来源：<code>data/demo.json · modules.literature.coverage</code>（fixture run；不是真实检索结果）</p>`;
}

function figureAct() {
  const figure = state.data.modules.figure || {};
  const audit = figure.audit || {};
  const checks = Object.entries(audit.checks || {}).filter(([, value]) => typeof value === "boolean");
  const pass = checks.filter(([, value]) => value).length;
  const scene = (figure.manifest?.scene_sha256 || "").slice(0, 18);
  const svg = (figure.manifest?.svg_sha256 || "").slice(0, 18);
  const refs = (figure.manifest?.evidence_refs || []).length;
  const groups = [
    { name: "结构", keys: ["root", "size", "ids_unique"] },
    { name: "可访问", keys: ["role_img", "labelled", "has_title", "has_desc"] },
    { name: "安全 / 文本", keys: ["text_count", "aria_targets"] }
  ];
  const rowsOf = (group) => group.keys.map((key) => {
    const value = audit.checks?.[key];
    const mark = value === true ? "✓" : value === false ? "×" : String(value ?? "—");
    return `${CHECK_LABELS[key] || key} ${mark}`;
  }).join(" · ");
  return `<div class="act-head"><p class="eyebrow">ACT 03 / SVG PROVENANCE</p><h2>${esc(ACTS[2].title)}</h2><p>scene 由 FigureAgent 生成，AstraDraw 渲染成 SVG；交付前必须通过可访问性、安全与文本检查。scene / svg / audit / manifest 四件一起交付。</p></div>
    <div class="act-metrics"><span><b>${pass}/${checks.length}</b> audit pass</span><span><b>${refs}</b> evidence refs</span><span><b>0</b> external refs</span><span><b>SCHEMATIC</b> 非结果图</span></div>
    <div class="provenance-strip">
      <div class="pv-step"><span>01 · SCENE</span><b>FigureScene</b><em>结构化节点 / 连线</em></div>
      <i class="provenance-arrow">→</i>
      <div class="pv-step"><span>02 · RENDER</span><b>figure.svg</b><em>AstraDraw</em></div>
      <i class="provenance-arrow">→</i>
      <div class="pv-step"><span>03 · AUDIT</span><b>${pass}/${checks.length} pass</b><em>XML · aria · 文本</em></div>
      <i class="provenance-arrow">→</i>
      <div class="pv-step"><span>04 · MANIFEST</span><b>hash bound</b><em>scene ${esc(scene.slice(0, 12))}…</em></div>
    </div>
    <figure class="figure-stage" title="点击放大">
      <img src="data/figure.svg" alt="研究运行时模块关系示意图；示意图，不是实验结果" />
      <figcaption><span>SCHEMATIC · 不是实验结果 · SVG ${esc(svg.slice(0, 12))}…</span><b>点击放大 ↗</b></figcaption>
    </figure>
    <div class="audit-matrix">${groups.map((group) => `<div class="audit-group"><b>${esc(group.name)} <i>${group.keys.length}</i></b><span>${esc(rowsOf(group))}</span></div>`).join("")}</div>
    <p class="source-note">数据来源：<code>modules.figure.audit</code> / <code>figure.manifest.json</code>；图为 schematic，不是实验结果</p>`;
}

function paperAct() {
  const paper = state.data.modules.paper || {};
  const grant = state.data.modules.grant;
  const g5 = (state.data.gates || []).find((gate) => gate.gate === "G5") || {};
  const slots = paper.slots || [];
  const pending = slots.filter((slot) => slot.status === "pending_evidence").length;
  const boundSlots = slots.filter((slot) => slot.status !== "pending_evidence");
  // paper.json 的 warnings 明确写着「schematic 不能绑成结果图」。所以 bound_figure 不能渲染成
  // 绿色的「已完成」；它绑定的是示意图，换成数据图之前 G5 仍然关着。
  const schematic = state.data.modules.figure?.manifest?.schematic !== false;
  const boundLabel = boundSlots.length
    ? `${boundSlots.length} 绑定 ${schematic ? "schematic" : "数据图"}`
    : "0 绑定";
  return `<div class="act-head"><p class="eyebrow">ACT 04 / SLOTS + GATES</p><h2>${esc(ACTS[3].title)}</h2><p>方法 / 结构可以先写，结果槽必须等 EA；示意图不能冒充结果图。</p></div>
    <div class="gate-banner"><span>G5 EXPORT · ${esc(g5.status || "blocked")}</span><b>${esc(g5.reason || "no EA/Closure")}</b><small>三件套少一件就 fail-closed；result.figure 绑的是 schematic，换数据图前 G5 仍关着。</small></div>
    <div class="slot-hero"><b>${pending}</b><span>PENDING SLOTS</span><em>没有 EA 就不填数字 · ${pending} 待证据 / ${boundLabel}</em></div>
    <div class="slot-stack">${slots.map((slot) => {
      const isBound = slot.status === "bound_figure";
      const cls = isBound ? (schematic ? "is-schematic" : "is-bound") : "";
      const stateText = isBound && schematic ? "bound · schematic" : slot.status;
      return `<div class="slot-card ${cls}"><span class="slot-id">${esc(slot.slot_id)}</span><span class="slot-sec">${esc(slot.section)}</span><span class="slot-req">${esc(slot.required_evidence)}</span><span class="slot-state">${esc(stateText)}</span></div>`;
    }).join("")}</div>
    <div class="track-grid">
      <div class="track-card"><span class="mono">PAPER TRACK</span><b>${esc(paper.profile?.venue_type || "论文契约")}</b><small>${esc(paper.profile?.citation_style || "GB/T 7714")} · ${(paper.sections || []).length} sections · 0 claims</small></div>
      <div class="track-card"><span class="mono">GRANT TRACK</span><b>${grant ? esc(grant.scheme.toUpperCase()) : "未生成"}</b><small>${grant ? `${(grant.modules || []).length} modules · ${(grant.compliance || []).length} compliance checks` : "用 --grant nsfc 生成基金骨架"}</small></div>
    </div>
    <p class="source-note">数据来源：<code>modules.paper.slots</code> / <code>modules.grant</code>；槽状态为 scaffold，不含任何结果数字</p>`;
}

function boundaryAct() {
  const specCount = state.specs.length || 6;
  const tests = state.stats && state.stats.ok && Number.isFinite(state.stats.tests_run) ? state.stats.tests_run : "—";
  return `<div class="act-head"><p class="eyebrow">ACT 05 / BOUNDARY</p><h2>${esc(ACTS[4].title)}</h2><p>这一页不把 fixture 说成实验，也不把“架构更清楚”说成“科研效果更好”。能证明的和不能证明的分开写。</p></div>
    <div class="act-metrics"><span><b>0</b> API calls</span><span><b>0</b> 外部效果数字</span><span><b>${specCount}</b> SPEC</span><span><b>${esc(tests)}</b> 自动测试</span></div>
    <div class="boundary-grid">
      <div class="boundary-card"><b>不是通用 AI 科学家</b><p>机器负责检索、草稿、图、核验；科学决策、实验安全、署名与责任在人。</p></div>
      <div class="boundary-card"><b>不是效果论文</b><p>当前没有真实检索、run/EA、用户研究；不引用任何外部效果数字。</p></div>
      <div class="boundary-card"><b>可检验的工程差异</b><p>${specCount} 个 SPEC、${state.stats && state.stats.ok && Number.isFinite(state.stats.tests_run) ? state.stats.tests_run : "—"} 个自动测试、SVG audit、结果槽阻断；这些都能在代码里找到。</p></div>
      <div class="boundary-card"><b>下一轮</b><p>OpenAlex adapter → EA/Run 账本 → 真实模板 → 5–8 人可用性测试。</p></div>
    </div>
    <div class="advantage-list">
      <div class="advantage-row"><b>SPEC</b><span>模块先有契约，改一个模块不必理解全部代码</span><em>implemented</em></div>
      <div class="advantage-row"><b>ARTIFACT</b><span>模块交换 artifact，不共享聊天上下文</span><em>implemented</em></div>
      <div class="advantage-row"><b>SVG</b><span>scene / svg / manifest / audit 一体</span><em>implemented</em></div>
      <div class="advantage-row"><b>BOUNDARY</b><span>结果槽 pending，G5 导出阻断</span><em>implemented</em></div>
      <div class="advantage-row"><b>RSI</b><span>StepLedger / policy / lease / MetaTracker；真实 evaluator 未接</span><em>control plane</em></div>
    </div>`;
}

function validityAct() {
  return `<div class="act-head"><p class="eyebrow">ACT 06 / METRIC VALIDITY</p><h2>${esc(ACTS[5].title)}</h2><p>64 种子预注册扩样（97–160）：raw 交互 4/4 判定；headroom-normalized AUC 交互 0/4。breast/iris/wine 的 AUC 上界低于 raw 效应量级，digits 96 种子合并后只是 borderline（0.1378 vs 0.1403）——效应量依赖度量，不是“无效应”。</p></div>
    <div class="metric-row">
      <div class="metric"><b>4/4</b><span>RAW INTERACTION</span><em>consistent negative</em></div>
      <div class="metric"><b>0/4</b><span>NORMALIZED AUC</span><em>undecided, not equivalence</em></div>
      <div class="metric"><b>0.153–0.217</b><span>MDE80</span><em>raw 0.140–0.407; digits borderline</em></div>
    </div>
    <div class="boundary-grid">
      <div class="boundary-card"><b>能证明</b><p>raw 交互在 1–32、33–64、65–96、97–160 四个不相交种子集上复制，4/4。</p></div>
      <div class="boundary-card"><b>不能证明</b><p>不是搜索效率或记忆×档案机制；AUC 交互未判定，breast/iris/wine 的上界低于 raw 效应量级，digits 只是 borderline。</p></div>
      <div class="boundary-card"><b>论文贡献</b><p>从“archive 组合发现”改成“效应量依赖度量 + 可审计流程”；CCF-A 审计仍为 evidence_ready。</p></div>
      <div class="boundary-card"><b>Qoder / MCP</b><p><code>research_venue_audit</code> 只读检查，<code>research_grant_template</code> 只写空白骨架；签名/提交仍只在人。</p></div>
    </div>
    <div class="advantage-list">
      <div class="advantage-row"><b>METRIC</b><span><code>study saturation</code> 复现 raw/AUC/MDE；64 种子扩样</span><em>implemented</em></div>
      <div class="advantage-row"><b>VENUE</b><span>中文期刊：摘要/关键词/章节/GB/T 7714/基金/创新/数据</span><em>MCP tool</em></div>
      <div class="advantage-row"><b>GRANT</b><span>NSFC/NSSFC 模块、创新点、活页匿名、AI 声明</span><em>MCP tool</em></div>
      <div class="advantage-row"><b>BIBLIO</b><span>DataCite 快照：2 篇引用 verified；原始响应 SHA-256 与仓库快照一致</span><em>verified</em></div>
    </div>
    <div class="misevolution">
      <b>自进化的副作用 · 准入与外部监督要挡的就是这些</b>
      <div class="advantage-row"><b>GOODHART</b><span>DGM：删掉幻觉检测依赖的日志函数，基准满分却没解决问题——指标变成目标就不再是好指标；准入要有「退化检测」</span><em>documented</em></div>
      <div class="advantage-row"><b>COST</b><span>DGM 80 轮 ≈ $22k / 两周，且主要在固定基准子集上评估；没有准入判据的自进化烧的就是这种预算</span><em>documented</em></div>
      <div class="advantage-row"><b>NEG-TRANSFER</b><span>MCMA：细粒度记忆跨任务 −3.13%、高层抽象 +1.04%——按抽象层级 × 适用域联合准入（策略③），不照单全存</span><em>measured</em></div>
    </div>
    <p class="source-note">数据来源：64 种子预注册扩样（97–160），见仓库 59- / 60- 文档；失效模式读数来自 1110 策略论证 §03（DGM / MCMA 原文已核对）。本页数字为研究快照，结论更新时需同步</p>`;
}

function feedbackAct() {
  return `<div class="act-head"><p class="eyebrow">ACT 07 / FEEDBACK → ACTION</p><h2>${esc(ACTS[6].title)}</h2><p>策略② · 判定消费：门禁、验证、失效的判定要进下一步行动，不能只躺在报告里。Q2（第一个诊断实验）同一任务给五类反馈，看行动是否按证据质量变。</p></div>
    <div class="metric-row">
      <div class="metric"><b>7.5%</b><span>完整反馈闭环</span><em>PerturbTrace · 43 / 576 次转换</em></div>
      <div class="metric"><b>25 / 43</b><span>拿的是随机反馈</span><em>闭环完整 ≠ 反馈被消费</em></div>
      <div class="metric"><b>5 类</b><span>对照反馈</span><em>真实 / 打乱 / 过时 / 含噪 / 矛盾</em></div>
    </div>
    <div class="fb-table">
      <div class="fb-row fb-head"><span>反馈类型</span><span>应有的行动（平台机制对应）</span><span>不消费的后果</span></div>
      <div class="fb-row"><span class="fb-kind is-real">真实</span><span>行动按证据收敛：改查询预算、缩 gap<span class="fb-mech">→ guidance 队列在阶段边界生效</span></span><span>无——唯一该改变行动的一类</span></div>
      <div class="fb-row"><span class="fb-kind is-shuffled">打乱</span><span>相关性检查拦下，不进流水线<span class="fb-mech">→ 两级过滤快层（程序门）</span></span><span>照单全收，拿噪声改动作</span></div>
      <div class="fb-row"><span class="fb-kind is-stale">过时</span><span>stale 判定拦截，先复验再行动<span class="fb-mech">→ 失效传播点名受影响结论</span></span><span>拿过期结论推进，产出作废稿件</span></div>
      <div class="fb-row"><span class="fb-kind is-noisy">含噪</span><span>降权，先测一轮再准入<span class="fb-mech">→ 学习证据准入：先测后用</span></span><span>噪声进下一轮，方向被带偏</span></div>
      <div class="fb-row"><span class="fb-kind is-conflict">矛盾</span><span>触发信念修订：改 / 保留不确定 / 再激活<span class="fb-mech">→ 策略④ · 交接协议记「谁提—谁评—谁消费—谁复验」</span></span><span>择优采信一边，另一边被丢弃</span></div>
    </div>
    <div class="gate-proof">
      <div class="gate-banner"><span>Q2 · 可失败的验收</span><b>反馈敏感性与真实信息价值一致 → 切口不成立</b><small>M1 的证伪条件：随机反馈与真实反馈若不改变行动差异，「让判定改变行动」不成立，回炉重述。</small></div>
      <div class="tamper-note"><b>平台侧对应物</b>guidance 队列、gate_stops、lineage 失效传播、交接协议字段——机制在，五类对照实验未跑；本幕为设计投影，非实验结果。</div>
    </div>
    <p class="source-note">读数来源：PerturbTrace（1110 策略论证 §01/§05 已核对原文）；五类对照的行动映射为本平台设计，SIM 标注 · 无真实 run</p>`;
}

const RENDERERS = [specAct, evidenceAct, figureAct, paperAct, boundaryAct, validityAct, feedbackAct];

function animateCounts(root) {
  root.querySelectorAll("[data-count]").forEach((el) => {
    const target = Number(el.dataset.count);
    if (!Number.isFinite(target) || REDUCED) { el.textContent = String(target || 0); return; }
    const start = performance.now();
    const run = (now) => {
      const p = Math.min(1, (now - start) / 520);
      el.textContent = String(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) requestAnimationFrame(run);
    };
    requestAnimationFrame(run);
  });
}

function renderAct(index, animate = true) {
  state.act = Math.max(0, Math.min(ACTS.length - 1, index));
  const act = ACTS[state.act];
  $("stage-act-label").textContent = `0${state.act + 1} / 06`;
  $("stage-title").textContent = act.title;
  const canvas = $("act-canvas");
  if (!state.data) {
    canvas.innerHTML = `<div class="act-head"><p class="eyebrow">FIXTURE NOT LOADED</p><h2>先运行 fixture pipeline。</h2><p>从项目根目录运行 <code>python -m research_agent pipeline run ...</code>，再启动静态服务器。当前页面不会调用 API。</p></div>`;
  } else {
    canvas.innerHTML = RENDERERS[state.act]();
    if (animate) {
      canvas.classList.remove("is-enter");
      void canvas.offsetWidth;
      canvas.classList.add("is-enter");
    }
    animateCounts(canvas);
  }
  $("act-note").innerHTML = noteFor(state.act);
  renderRail();
  setProgress(0);
  setSource();
}

function setSource() {
  $("stage-source").textContent = state.data?.fixture_mode ? "FIXTURE / NO API" : "STATIC DEMO";
}

// 全景状态条：直接读 demo.json 的 gates，避免页面写死「停在哪一步」。
function fillPanorama() {
  const el = $("pano-status");
  if (!el) return;
  if (!state.data) {
    el.textContent = "fixture 未载入：先启动静态服务器或运行 pipeline。";
    return;
  }
  const gates = state.data.gates || [];
  const g = (id) => (gates.find((gate) => gate.gate === id) || {}).status || "—";
  el.innerHTML = `<b>${esc(state.data.run_id)}</b><span>status ${esc(state.data.status)}</span><span>G1 ${esc(g("G1"))}</span><span>G2 ${esc(g("G2"))}</span><span>S5 ${esc(g("S5"))}</span><span>G5 ${esc(g("G5"))}</span>`;
}

function setProgress(value) {
  $("progress-fill").style.width = `${Math.max(0, Math.min(1, value)) * 100}%`;
}

function pauseAuto() {
  if (state.playing) state.elapsed += performance.now() - state.startedAt;
  state.playing = false;
  cancelAnimationFrame(state.raf);
  clearTimeout(state.autoTimer);
  state.raf = null;
  state.autoTimer = null;
  const btn = $("play-btn");
  btn.textContent = "播放";
  btn.setAttribute("aria-pressed", "false");
}

function tick(now) {
  if (!state.playing) return;
  const elapsed = state.elapsed + (now - state.startedAt);
  const p = Math.min(1, elapsed / ACT_MS);
  setProgress(p);
  if (p >= 1) {
    if (state.act < ACTS.length - 1) {
      state.elapsed = 0;
      state.startedAt = now;
      renderAct(state.act + 1, false);
      state.raf = requestAnimationFrame(tick);
    } else {
      pauseAuto();
      setProgress(1);
      $("play-btn").textContent = "重播";
    }
    return;
  }
  state.raf = requestAnimationFrame(tick);
}

function startAuto() {
  if (state.playing) return;
  if (state.act === ACTS.length - 1 && state.elapsed >= ACT_MS) {
    state.elapsed = 0;
    renderAct(0, false);
    state.elapsed = 0;
  }
  state.playing = true;
  state.startedAt = performance.now();
  const btn = $("play-btn");
  btn.textContent = "暂停";
  btn.setAttribute("aria-pressed", "true");
  state.raf = requestAnimationFrame(tick);
}

function toggleAuto() {
  if (state.playing) pauseAuto();
  else startAuto();
}

function go(delta) {
  pauseAuto();
  state.elapsed = 0;
  renderAct((state.act + delta + ACTS.length) % ACTS.length, true);
}

function selectAct(index) {
  pauseAuto();
  state.elapsed = 0;
  renderAct(index, true);
}

function setPresentation(on) {
  state.presenting = on;
  document.body.classList.toggle("is-present", on);
  $("present-btn").textContent = on ? "退出演示" : "演示模式";
  $("present-inline").textContent = on ? "退出" : "全屏";
  if (on) {
    $("stage").scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "start" });
    startAuto();
  } else {
    pauseAuto();
  }
}

function openDemo() {
  $("stage").scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "start" });
  selectAct(0);
  startAuto();
}

document.addEventListener("click", (event) => {
  const act = event.target.closest("[data-act]");
  if (act) selectAct(Number(act.dataset.act));
});

// 图放大：示意图在 700px 画布里会被压小，点开看细节。仍是同一张 fixture SVG，不引入新数据。
document.addEventListener("click", (event) => {
  const stage = event.target.closest(".figure-stage");
  if (!stage) return;
  const img = stage.querySelector("img");
  if (!img) return;
  const box = document.createElement("div");
  box.className = "figure-lightbox";
  box.innerHTML = `<button type="button" aria-label="关闭放大">×</button><img src="${esc(img.getAttribute("src"))}" alt="${esc(img.getAttribute("alt"))}">`;
  const close = () => { box.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (keyEvent) => { if (keyEvent.key === "Escape") close(); };
  box.addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  document.body.appendChild(box);
});
$("start-btn").addEventListener("click", openDemo);
$("play-btn").addEventListener("click", toggleAuto);
$("prev-btn").addEventListener("click", () => go(-1));
$("next-btn").addEventListener("click", () => go(1));
$("present-btn").addEventListener("click", () => setPresentation(!state.presenting));
$("present-inline").addEventListener("click", () => setPresentation(!state.presenting));

document.addEventListener("keydown", (event) => {
  if (event.target.closest("input, textarea, select")) return;
  if (event.key === "ArrowRight") { event.preventDefault(); go(1); }
  else if (event.key === "ArrowLeft") { event.preventDefault(); go(-1); }
  else if (event.key === " ") { if (event.target.closest("button,a")) return; event.preventDefault(); toggleAuto(); }
  else if (event.key === "Escape" && state.presenting) { event.preventDefault(); setPresentation(false); }
  else if (event.key.toLowerCase() === "p") { event.preventDefault(); setPresentation(!state.presenting); }
});

// Reading a dense act must not be interrupted by the auto-advance: pause while the pointer rests
// on the stage, resume when it leaves. Presentation mode is exempt (auto-advance is its purpose).
let hoverPaused = false;
$("stage").addEventListener("pointerenter", () => {
  if (state.playing && !state.presenting) { hoverPaused = true; pauseAuto(); }
});
$("stage").addEventListener("pointerleave", () => {
  if (hoverPaused) { hoverPaused = false; if (!state.presenting) startAuto(); }
});

function fillFacts() {
  const specs = (state.data ? available().length : 0) || 6;
  const set = (id, value) => { const el = $(id); if (el) el.textContent = String(value); };
  set("fact-specs", specs);
  set("proof-spec-foot", `${specs} SPEC · 版本化`);
  const tests = state.stats && state.stats.ok && Number.isFinite(state.stats.tests_run) ? state.stats.tests_run : "—";
  set("fact-tests", tests);
  const testEl = $("fact-tests");
  if (testEl && state.stats) testEl.title = `recorded verdict @ ${state.stats.source_fingerprint || "unknown"} · ${state.stats.finished_at || ""}`;
  ACTS[0].noteFact = String(specs);
}

// The hero board's connector curves used fixed viewBox coordinates while the nodes are placed in
// percentages, so at most widths the lines visibly missed the boxes. Recompute endpoints from the
// laid-out node centres so every curve actually terminates at the node it names.
function layoutBoard() {
  const board = document.querySelector(".board");
  const svg = document.querySelector(".board-lines");
  if (!board || !svg) return;
  const w = board.clientWidth, h = board.clientHeight;
  if (!w || !h) return;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  const bb = board.getBoundingClientRect();
  const center = (sel) => {
    const el = board.querySelector(sel);
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.left - bb.left + r.width / 2, y: r.top - bb.top + r.height / 2 };
  };
  const core = center(".board-core");
  const ends = [center(".n1"), center(".n2"), center(".n4"), center(".n5"), center(".n6"), center(".n3")];
  const paths = svg.querySelectorAll("path");
  const curve = (a, b) => `M ${a.x} ${a.y} C ${(a.x + b.x) / 2} ${a.y}, ${(a.x + b.x) / 2} ${b.y}, ${b.x} ${b.y}`;
  const pairs = [[ends[0], core], [ends[1], core], [core, ends[2]], [core, ends[3]], [core, ends[4]], [ends[5], core]];
  pairs.forEach(([a, b], i) => { if (paths[i] && a && b) paths[i].setAttribute("d", curve(a, b)); });
}
window.addEventListener("resize", layoutBoard);

async function load() {
  try {
    const [demo, specs, stats] = await Promise.all([
      fetch("data/demo.json", { cache: "no-store" }),
      fetch("data/specs.json", { cache: "no-store" }),
      fetch("data/stats.json", { cache: "no-store" }).catch(() => null)
    ]);
    if (!demo.ok) throw new Error("demo.json " + demo.status);
    state.data = await demo.json();
    state.specs = specs.ok ? await specs.json() : [];
    state.stats = stats && stats.ok ? await stats.json() : null;
    fillFacts();
    fillPanorama();
    renderAct(0, false);
    layoutBoard();
  } catch (error) {
    renderAct(0, false);
    fillPanorama();
    $("stage-source").textContent = "FIXTURE MISSING";
    $("stage-title").textContent = "静态数据未载入";
    $("act-note").innerHTML = `<span class="note-kicker">STATIC DEMO</span><b class="note-title">从仓库根目录启动静态服务器</b><p class="note-body">为了在 GitHub Pages 或本地正确读取 data/demo.json，不要直接双击文件；运行 <code>python -m http.server</code> 或部署到 Pages。</p>`;
  }
}

layoutBoard();
load();

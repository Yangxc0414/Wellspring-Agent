const MODULE_META = {
  literature: { label: "文献调研", stage: "S1", kind: "literature", desc: "检索、阅读、句级 span 与覆盖回执；不创建 Claim。调研模型 GLM-5.3-Flash（静态登记，未接 API）。" },
  idea: { label: "假设收敛", stage: "S2–S3", kind: "idea", desc: "把 span 变成带否证条件的候选，交人做 G1。" },
  experiment: { label: "实验设计", stage: "S4", kind: "experiment", desc: "产出预注册草稿；不执行 run、不产生结果。" },
  run: { label: "复现执行", stage: "S5", kind: "run", desc: "本地协议 run：RunCapsule + EA；Claim 必须由人签。" },
  figure: { label: "科研绘图", stage: "S6", kind: "figure", desc: "AstraDraw scene → 可审计 SVG；示意图，不是数据图。" },
  paper: { label: "论文契约", stage: "S8–S12", kind: "paper", desc: "语言/venue 路由、章节与结果槽；结果槽保持 pending。" },
  grant: { label: "基金申报", stage: "S8–S12", kind: "grant", desc: "NSFC/NSSFC 骨架与合规清单；不写科学观点/预算数字。" }
};
const ORDER = ["literature", "idea", "experiment", "run", "figure", "paper", "grant"];
const STATUS_TEXT = {
  ok: "ok · spans ready",
  candidates_need_human: "needs human · G1",
  ready_for_g2: "ready · G2",
  completed: "capsule · EA ready",
  schematic_ready: "schematic · audited",
  needs_evidence: "pending evidence",
  draft_needs_human: "draft · human",
  not_run: "not generated"
};

const state = {
  data: null,
  lastFocus: null,
  specs: [],
  models: [],
  rsi: null,
  innovations: [],
  innovationReport: null,
  gateway: null,
  gatewayLive: false,
  tasks: [],
  taskId: null,
  taskDir: "",
  selected: "literature",
  tab: "overview",
  mode: "paper",
  replayTimer: null,
  paletteItems: [],
  paletteIndex: 0
};

const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const statusOf = (id) => state.data?.modules?.[id]?.status || "not_run";
const specOf = (id) => state.specs.find((spec) => spec.id === id);
const modelOf = (id) => state.models.find((binding) => binding.module === id);
const available = () => ORDER.filter((id) => (id === "grant" || id === "run") ? !!state.data?.modules?.[id] : true);
const moduleStatusClass = (status) => status === "ok" || status === "ready_for_g2" || status === "schematic_ready" || status === "completed" ? "ok" : (status === "not_run" ? "" : "warn");
const fmtNum = (value) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return Math.abs(num) >= 100 || Number.isInteger(num) ? String(num) : String(Math.round(num * 1000) / 1000);
};

function currentScope(data = state.data) {
  const dataset = String(data?.modules?.run?.capsule?.dataset_id || "");
  if (dataset.startsWith("chemlab:morgan:376train")) return "S5/confirm/chemlab_holdout";
  if (dataset.startsWith("chemlab:morgan:")) return "S5/demo/chemlab";
  if (dataset.startsWith("sklearn:breast_cancer:")) return "S5/demo/breast_cancer";
  if (dataset.startsWith("sklearn:iris:")) return "S5/demo/iris";
  return "";
}

function evidenceArms(data = state.data) {
  const lit = data?.modules?.literature || {};
  const run = data?.modules?.run;
  const paper = data?.modules?.paper || {};
  const coverage = lit.coverage || {};
  const sourceScope = coverage.source_scope || lit.query_plan?.source_scope || [];
  const s1Mode = sourceScope.includes("real") ? "REAL TEXT" : (data?.fixture_mode ? "FIXTURE" : "REAL");
  const s1Bad = coverage.spans_extracted === 0;
  const runEvidence = run?.evidence || {};
  const runMode = run ? (runEvidence.source === "run" ? "REAL LOCAL RUN" : "REUSED RECORD") : "NOT RUN";
  const runValue = run ? `${fmtNum(run.capsule?.mean ?? "—")} ${String(run.capsule?.metric_name || "metric").toUpperCase()}` : "—";
  const pendingSlots = (paper.slots || []).filter((slot) => slot.status === "pending_evidence").length;
  const paperValue = paper.slots?.length ? `${paper.slots.length - pendingSlots}/${paper.slots.length} bound` : "—";
  const claimBound = (paper.claims || []).length > 0;
  const claimDraft = Boolean(run?.claim_draft);
  return {
    mixed: Boolean(data?.fixture_mode && run && runEvidence.source === "run"),
    s1: {
      mode: s1Mode,
      value: `${coverage.sources_found ?? 0} hit · ${coverage.spans_extracted ?? 0} span`,
      detail: s1Bad
        ? "无全文 span；摘要不能当证据，不能支撑 claim"
        : `${coverage.sources_read ?? 0} full text read · ${(coverage.gaps || []).length} gaps`,
      state: s1Bad ? "bad" : "ok",
      stateText: s1Bad ? "NO EVIDENCE" : "SPANS READY"
    },
    s5: {
      mode: runMode,
      value: run ? `${runValue} · ${run.capsule?.seeds?.length ?? "?"} seeds` : "—",
      detail: run
        ? `EA ${runEvidence.artifact_id || "—"} · ${claimBound ? "claim bound" : claimDraft ? "claim draft unsigned" : "no claim"}`
        : "本次任务没有执行 S5",
      state: run ? (claimBound ? "ok" : "warn") : "",
      stateText: run ? (claimBound ? "CLAIM BOUND" : "EA ONLY") : "NOT RUN"
    },
    paper: {
      mode: "PAPER CONTRACT",
      value: paperValue,
      detail: claimBound
        ? "result.primary 已绑定人签 claim"
        : pendingSlots
          ? `${pendingSlots} 个槽位仍待证据；导出保持关闭`
          : "槽位已绑定；仍需 Closure/export gate",
      state: claimBound && pendingSlots === 0 ? "ok" : "warn",
      stateText: claimBound ? "BOUND" : "PENDING"
    }
  };
}

function rsiScopeInfo() {
  const episodes = state.rsi?.ledger?.episodes || [];
  const leases = state.rsi?.ledger?.leases || [];
  const scopes = [...new Set([
    ...episodes.map((episode) => episode.candidate?.scope).filter(Boolean),
    ...leases.map((lease) => lease.scope).filter(Boolean)
  ])];
  const taskScope = currentScope();
  return {
    scopes,
    taskScope,
    matches: Boolean(taskScope && scopes.includes(taskScope)),
    ledger: state.rsi?.source?.ledger || "—"
  };
}

function leaseStatus(lease) {
  if (lease.status !== "active") return lease.status;
  const created = new Date(lease.created_at);
  if (Number.isNaN(created.getTime())) return "active";
  const expires = new Date(created.getTime() + Number(lease.ttl_days || 0) * 86400000);
  return expires.getTime() < Date.now() ? "expired" : "active";
}

function setStatus(message) {
  const el = $("status-msg");
  if (el) el.textContent = message;
}

/* ---- theme ---- */
function applyTheme(theme, announce = false) {
  document.documentElement.dataset.theme = theme;
  const ico = $("theme-ico");
  if (ico) ico.textContent = theme === "dark" ? "☀️" : "🌙";
  try { localStorage.setItem("ra-theme", theme); } catch (storageError) { /* private mode */ }
  if (announce) consoleEcho(theme === "dark" ? "已切换深色主题" : "已切换浅色主题");
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("ra-theme"); } catch (storageError) { /* private mode */ }
  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));
}

/* ---- command console ---- */
const VIEWS = ["overview", "evidence", "paper", "trace", "evolution", "innovation"];
const VIEW_ALIASES = { overview: "overview", evidence: "evidence", paper: "paper", trace: "trace", evolution: "evolution", innovation: "innovation", 自进化: "evolution", 创新: "innovation", 创新逻辑: "innovation", 证据: "evidence", 总览: "overview", 稿件: "paper", 运行: "trace" };
const CONSOLE_HELP = [
  { cmd: "/task <n|关键字>", desc: "切换任务，如 /task 2 或 /task chem" },
  { cmd: "/tasks", desc: "列出全部任务" },
  { cmd: "/module <名称>", desc: "选中模块，如 /module run 或 /module 文献" },
  { cmd: "/view <名称|1-6>", desc: "切换视图：overview evidence paper trace evolution innovation" },
  { cmd: "/replay", desc: "回放当前任务运行" },
  { cmd: "/model", desc: "打开模型网关面板（OpenAI / Anthropic / GLM / 兼容端点）" },
  { cmd: "/theme", desc: "切换浅色/深色主题" },
  { cmd: "/help", desc: "显示本帮助" }
];
const consoleState = { history: [], cursor: -1 };

function consoleEcho(message, isError = false) {
  const echo = $("console-echo");
  if (!echo) return;
  echo.textContent = message;
  echo.classList.toggle("err", isError);
}

function findTask(arg) {
  if (!state.tasks.length) return null;
  if (/^\d+$/.test(arg)) {
    const index = Number(arg) - 1;
    return state.tasks[index] || null;
  }
  const key = arg.toLowerCase();
  return state.tasks.find((task) => task.id.toLowerCase() === key)
    || state.tasks.find((task) => (task.topic || "").toLowerCase().includes(key) || task.id.toLowerCase().includes(key))
    || null;
}

function findModule(arg) {
  const key = arg.toLowerCase();
  return available().find((id) => id === key
    || MODULE_META[id].label === arg
    || MODULE_META[id].label.includes(arg)
    || id.includes(key)) || null;
}

function runConsoleCommand(raw) {
  const value = raw.trim();
  if (!value) return;
  consoleState.history.push(value);
  consoleState.cursor = consoleState.history.length;
  const [word, ...rest] = value.split(/\s+/);
  const arg = rest.join(" ");
  const command = word.toLowerCase().replace(/^\//, "");
  switch (command) {
    case "help":
      consoleEcho("指令：" + CONSOLE_HELP.map((item) => item.cmd).join(" · "));
      setStatus("HELP · " + CONSOLE_HELP.length + " commands");
      break;
    case "tasks":
      consoleEcho(state.tasks.map((task, index) => `${index + 1}.${task.topic || task.id}${task.id === state.taskId ? "（当前）" : ""}`).join(" · ") || "没有任务数据");
      break;
    case "task": {
      if (!arg) { consoleEcho("用法：/task <n|关键字>", true); break; }
      const task = findTask(arg);
      if (!task) { consoleEcho("未匹配到任务：" + arg, true); break; }
      switchTask(task);
      consoleEcho("已切换任务 → " + (task.topic || task.id));
      break;
    }
    case "module": case "m": {
      if (!arg) { consoleEcho("用法：/module <名称>", true); break; }
      const id = findModule(arg);
      if (!id) { consoleEcho("未匹配到模块：" + arg, true); break; }
      selectModule(id, false);
      consoleEcho("已选中模块 → " + MODULE_META[id].label + "（" + MODULE_META[id].stage + "）");
      break;
    }
    case "view": case "v": {
      const target = VIEW_ALIASES[arg] || (/^[1-6]$/.test(arg) ? VIEWS[Number(arg) - 1] : arg);
      if (!VIEWS.includes(target)) {
        consoleEcho("未知视图：" + arg + "（" + VIEWS.join(" ") + " 或 1-6）", true);
        break;
      }
      switchTab(target);
      consoleEcho("已切换视图 → " + target);
      break;
    }
    case "replay":
      replay();
      consoleEcho("回放当前任务运行 · SIM");
      break;
    case "model": case "models": case "gateway":
      openGateway();
      consoleEcho(state.models.map((binding) => `${binding.module}→${binding.model}`).join(" · ") || "模型网关面板已打开");
      break;
    case "theme":
      applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
      break;
    default:
      consoleEcho("未知指令：" + word + " · 输入 /help 查看", true);
  }
}

function consoleComplete() {
  const input = $("console-input");
  const value = input.value.trim();
  if (!value) return;
  const match = CONSOLE_HELP.find((item) => item.cmd.split(" ")[0].startsWith(value.startsWith("/") ? value : "/" + value));
  if (match) {
    const head = match.cmd.split(" ")[0];
    if (head.length > value.length) {
      input.value = head + " ";
      consoleEcho("补全 → " + match.cmd + " · " + match.desc);
    }
  }
}

function initConsole() {
  const input = $("console-input");
  if (!input) return;
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runConsoleCommand(input.value);
      input.value = "";
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      if (consoleState.cursor > 0) {
        consoleState.cursor -= 1;
        input.value = consoleState.history[consoleState.cursor] || "";
      }
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      if (consoleState.cursor < consoleState.history.length - 1) {
        consoleState.cursor += 1;
        input.value = consoleState.history[consoleState.cursor] || "";
      } else {
        consoleState.cursor = consoleState.history.length;
        input.value = "";
      }
    } else if (event.key === "Tab") {
      event.preventDefault();
      consoleComplete();
    } else if (event.key === "Escape") {
      input.value = "";
      input.blur();
    }
    event.stopPropagation();
  });
  const help = $("console-help");
  if (help) help.addEventListener("click", () => runConsoleCommand("/help"));
}

function renderHeader() {
  const d = state.data;
  const index = state.tasks.findIndex((task) => task.id === state.taskId);
  const current = state.tasks[index];
  $("run-id").textContent = (current ? `TASK ${String(index + 1).padStart(2, "0")}/${String(state.tasks.length).padStart(2, "0")} · ` : "") + (d.run_id || "—");
  $("run-topic").textContent = d.topic || "未命名运行";
  $("topic").textContent = d.topic || "从证据到可签署草稿";
  const paperProfile = d.modules.paper?.profile || {};
  $("subtitle").textContent = "文献、假设、设计、图、稿件与基金共享同一套 spec/artifact/gate；结果性内容等待 EA。";
  const eyebrow = $("head-eyebrow");
  if (eyebrow) eyebrow.textContent = `RUN SURFACE · ${(current?.venue || paperProfile.venue_type || "—").toUpperCase()} · ${(current?.language || paperProfile.language || "—").toUpperCase()}`;
  $("status-badge").textContent = d.status || "needs_human";
  const arms = evidenceArms(d);
  const modeBadge = $("mode-badge");
  modeBadge.textContent = arms.mixed ? "MIXED ARMS" : (current ? (current.fixture_mode ? "FIXTURE" : "REAL-TEXT · CC-BY") : (d.fixture_mode ? "FIXTURE" : "REAL-TEXT"));
  modeBadge.classList.toggle("mixed", arms.mixed);
  modeBadge.title = arms.mixed
    ? "S1 文献臂为 fixture，S5 执行臂为真实本地 run；两组指标不能合并为一个结果。"
    : "";
  const gates = d.gates || [];
  const blocked = gates.filter((gate) => gate.status === "blocked" || gate.status === "needs_human").length;
  $("gate-summary").textContent = `${gates.length} gates · ${blocked} need attention`;
  $("rail-state").textContent = d.fixture_mode ? "FIXTURE" : "LIVE";
  $("spec-count").textContent = String(Object.keys(d.spec_versions || {}).length);
  $("status-versions").textContent = "specs " + Object.entries(d.spec_versions || {}).map(([key, value]) => `${key}@${value}`).join(" · ");
  $("canvas-note").textContent = `${available().length} modules · j / k · 1–6`;
}

function currentTask() {
  return state.tasks.find((task) => task.id === state.taskId) || null;
}

function renderTasks() {
  const section = $("task-section");
  const list = $("task-list");
  if (!section || !list) return;
  if (!state.tasks.length) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  $("task-count").textContent = `${state.tasks.length} 条`;
  list.innerHTML = state.tasks.map((task, index) => `
    <button type="button" class="task-btn ${state.taskId === task.id ? "is-on" : ""}" data-task="${esc(task.id)}" ${state.taskId === task.id ? 'aria-current="true"' : ""}>
      <span class="task-index">${String(index + 1).padStart(2, "0")}</span>
      <span class="task-main">
        <b class="task-topic">${esc(task.topic || task.id)}</b>
        <small class="task-meta">${esc(task.venue)} · ${esc(task.language)}${task.has_run ? " · S5 run" : ""}${task.has_grant ? " · grant" : ""} · ${esc((task.created_at || "").slice(0, 8) || "—")}</small>
      </span>
      <span class="task-flag ${task.fixture_mode ? "" : "real"}">${task.fixture_mode ? "FIX" : "REAL"}</span>
    </button>`).join("");
  const name = $("rail-task-name");
  const current = currentTask();
  if (name) name.textContent = current ? (current.topic || current.id) : "—";
}

function renderRail() {
  const list = $("stage-list");
  list.innerHTML = available().map((id, index) => {
    const meta = MODULE_META[id];
    const status = statusOf(id);
    return `<button type="button" class="stage-btn ${state.selected === id ? "is-on" : ""}" data-module="${id}" data-status="${esc(status)}" ${state.selected === id ? 'aria-current="step"' : ''}>
      <span class="stage-dot" aria-hidden="true"></span>
      <span class="stage-main"><span class="stage-index">${String(index + 1).padStart(2, "0")}</span><b class="stage-name">${esc(meta.label)}</b><small class="stage-meta">${esc(meta.stage)} · ${esc(STATUS_TEXT[status] || status)}</small></span>
      <span class="mono">${esc(specOf(id)?.version || state.data.spec_versions?.[id] || "—")}</span>
    </button>`;
  }).join("");
}

function renderPipeline() {
  const strip = $("pipeline-strip");
  strip.innerHTML = available().map((id) => {
    const meta = MODULE_META[id];
    const status = statusOf(id);
    return `<button type="button" class="pipe-card ${state.selected === id ? "is-on" : ""}" data-kind="${meta.kind}" data-module="${id}" data-status="${esc(status)}">
      <span class="pipe-stage">${esc(meta.stage)}</span>
      <b class="pipe-name">${esc(meta.label)}</b>
      <span class="pipe-status">${esc(STATUS_TEXT[status] || status)}</span>
    </button>`;
  }).join("");
}

function renderModelBar() {
  const bar = $("model-bar");
  if (!bar) return;
  if (!state.models.length) {
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  bar.innerHTML = `
    <div class="card-head">
      <div><span class="eyebrow">MODEL BINDING · STATIC / NO API</span><b class="card-title">模型绑定（静态设计）</b></div>
      <span class="badge quiet">未接入 API</span>
    </div>
    <div class="model-chips">
      ${state.models.map((binding) => binding.module === "literature"
        ? `<button type="button" class="model-chip is-glm" data-module="literature" title="${esc(binding.status)}">
             <b>调研智能体 ${esc(binding.module)}</b><span>${esc(binding.model)}</span><em>${esc(binding.status)}</em>
           </button>`
        : `<span class="model-chip"><b>${esc(MODULE_META[binding.module]?.label || binding.module)}</b><span>${esc(binding.model)}</span><em>${esc(binding.status)}</em></span>`).join("")}
    </div>
    <p class="model-note">静态设计：不发起任何模型调用；接入前必须先在对应 SPEC.md 登记 adapter、权限、限流与错误处理。当前实现见各模块 chips 的 fallback。</p>`;
}

function renderArms() {
  const ledger = $("arm-ledger");
  if (!ledger) return;
  const arms = evidenceArms();
  const cards = [
    ["s1", "S1 · EVIDENCE", arms.s1],
    ["s5", "S5 · EXECUTION", arms.s5],
    ["paper", "S8 · CONTRACT", arms.paper]
  ];
  ledger.hidden = false;
  ledger.innerHTML = `
    <div class="arm-head">
      <span class="eyebrow">EVIDENCE ARMS · 先看臂，再看数</span>
      <span class="badge ${arms.mixed ? "mixed" : "quiet"}">${arms.mixed ? "MIXED · 不可合并" : "SINGLE-ARM"}</span>
    </div>
    <div class="arm-grid">
      ${cards.map(([key, label, arm]) => `
        <article class="arm-card ${arm.state === "" ? "is-missing" : ""}" data-arm="${key}">
          <div class="arm-top"><b>${label}</b><span class="arm-state ${arm.state}">${esc(arm.stateText)}</span></div>
          <span class="arm-value">${esc(arm.value)}</span>
          <span class="arm-detail">${esc(arm.mode)} · ${esc(arm.detail)}</span>
        </article>`).join("")}
    </div>
    <p class="arm-note">${arms.mixed
      ? "<b>不要把两臂读成一个结果：</b>S1 的 hit/span 与 S5 的 R²/accuracy 来自不同证据臂；S5 的 EA 只覆盖本地协议 run，claim 未签前不能进入结果槽。"
      : "每个数字都带有来源臂；只有同一 run_id、同一 scope 的 claim/EA/图才可合并解读。"}</p>`;
}

function renderOverview() {
  const d = state.data;
  const lit = d.modules.literature || {};
  const idea = d.modules.idea || {};
  const exp = d.modules.experiment || {};
  const fig = d.modules.figure || {};
  const run = d.modules.run;
  const hasClaim = (d.modules.paper?.claims || []).length > 0;
  $("figure-title").textContent = "模块关系图 · SVG";
  const figureBase = state.taskDir ? state.taskDir + "/figure.svg" : (d.figure_uri || "data/figure.svg");
  $("figure-img").src = figureBase + "?v=" + encodeURIComponent(fig.manifest?.svg_sha256 || d.run_id || "");
  $("figure-img").alt = (fig.manifest?.title || "研究流水线") + "；示意图，不是实验数据图";
  $("figure-caption").textContent = "AstraDraw scene → SVG；示意图，不是实验数据图。审计：" + (fig.audit?.ok ? "PASS" : "FAIL");
  $("figure-hash").textContent = (fig.manifest?.svg_sha256 || "").slice(0, 22) + "…";
  const coverage = lit.coverage || {};
  renderArms();
  const rsi = state.rsi?.report;
  const rsiContext = rsiScopeInfo();
  const stats = [
    { value: coverage.sources_found ?? "—", label: "SOURCES FOUND", note: `${coverage.sources_read ?? 0} full texts read` },
    { value: coverage.spans_extracted ?? "—", label: "SPANS EXTRACTED", note: `${(idea.candidates || []).length} idea candidates` },
    { value: run ? fmtNum(run.capsule?.mean ?? "—") : (coverage.gaps || []).length, label: run ? "S5 MEAN · EA SEALED" : "COVERAGE GAPS", note: run ? `${run.capsule?.metric_name || "metric"} · ${run.capsule?.seeds?.length ?? "?"} seeds · ${hasClaim ? "claim bound" : "claim 未签"}` : (exp.status === "ready_for_g2" ? "design ready for G2" : "design needs human") },
    ...(rsi ? [{ value: rsi.episodes, label: "RSI EPISODES", note: `${rsi.approved} 准入 · ${rsi.rejected} 拒绝 · ${rsiContext.matches ? "同任务台账" : "跨任务台账"}`, action: "evolution" }] : [])
  ];
  $("stat-grid").innerHTML = stats.map((stat) => stat.action
    ? `<button type="button" class="stat is-link" data-tab="evolution"><b>${esc(stat.value)}</b><span>${esc(stat.label)}</span><em>${esc(stat.note)} · 查看自进化 →</em></button>`
    : `<div class="stat"><b>${esc(stat.value)}</b><span>${esc(stat.label)}</span><em>${esc(stat.note)}</em></div>`).join("");
  renderModelBar();
}

function renderEvidence() {
  const d = state.data;
  const lit = d.modules.literature || {};
  const idea = d.modules.idea || {};
  const exp = d.modules.experiment || {};
  const fig = d.modules.figure || {};
  const run = d.modules.run;
  const coverage = lit.coverage || {};
  const spans = (lit.spans || []).slice(0, 4);
  const glm = modelOf("literature");
  $("evidence-grid").innerHTML = `
    <section class="data-card">
      <span class="eyebrow">S1 / LITERATURE</span><h3>检索与覆盖</h3>
      <dl class="kv">
        <dt>QUESTION</dt><dd>${esc(lit.query_plan?.question || "—")}</dd>
        <dt>SUBQUERIES</dt><dd>${(lit.query_plan?.subqueries || []).map((q) => `<span class="chip">${esc(q)}</span>`).join(" ")}</dd>
        <dt>MODEL</dt><dd>${glm ? `<span class="chip glm">${esc(glm.model)}</span> ${esc(glm.status)} · 用于 ${esc((glm.used_for || [])[0] || "检索规划")}` : "—"}</dd>
        <dt>COVERAGE</dt><dd>${coverage.sources_found ?? 0} hits · ${coverage.sources_read ?? 0} read · ${coverage.spans_extracted ?? 0} spans</dd>
        <dt>GAPS</dt><dd>${(coverage.gaps || []).map((gap) => `<span class="chip warn">${esc(gap.code)}</span>`).join(" ") || "none"}</dd>
      </dl>
      <ul class="span-list">${spans.map((span) => `<li><code>${esc(span.span_id)}</code> · ${esc(span.section)}<br>${esc(span.text)}</li>`).join("") || "<li>没有 span。</li>"}</ul>
    </section>
    <section class="data-card">
      <span class="eyebrow">S2–S3 / IDEA</span><h3>候选方向</h3>
      <ul class="candidate-list">${(idea.candidates || []).map((card) => `<li><b>${esc(card.title)}</b><span>${esc(card.falsification)}</span></li>`).join("") || "<li>没有候选；需要先补 span。</li>"}</ul>
    </section>
    <section class="data-card">
      <span class="eyebrow">S4 / EXPERIMENT</span><h3>预注册草稿</h3>
      <dl class="kv">
        <dt>STATUS</dt><dd><span class="chip ${moduleStatusClass(exp.status)}">${esc(exp.status)}</span></dd>
        <dt>HYPOTHESIS</dt><dd>${esc(exp.hypothesis || "—")}</dd>
        <dt>BASELINE</dt><dd>${esc(exp.baseline || "—")}</dd>
        <dt>METRIC</dt><dd>${esc(exp.primary_metric || "—")}</dd>
        <dt>SEEDS</dt><dd>${esc(exp.seeds ?? "—")}</dd>
        <dt>STOP</dt><dd>${esc(exp.stopping_rule || "—")}</dd>
      </dl>
    </section>
    ${run ? renderRunCard(run) : ""}
    <section class="data-card">
      <span class="eyebrow">S6 / SVG AUDIT</span><h3>图与 provenance</h3>
      <dl class="kv">
        <dt>FIGURE</dt><dd>${esc(fig.figure_id || "—")}</dd>
        <dt>AUDIT</dt><dd><span class="chip ${fig.audit?.ok ? "ok" : "bad"}">${fig.audit?.ok ? "PASS" : "FAIL"}</span></dd>
        <dt>CHECKS</dt><dd>${Object.entries(fig.audit?.checks || {}).map(([key, value]) => `<span class="chip">${esc(key)}=${esc(value)}</span>`).join(" ")}</dd>
        <dt>SCENE</dt><dd class="mono">${esc((fig.manifest?.scene_sha256 || "").slice(0, 24))}…</dd>
        <dt>SVG</dt><dd class="mono">${esc((fig.manifest?.svg_sha256 || "").slice(0, 24))}…</dd>
      </dl>
    </section>`;
}

function renderRunCard(run) {
  const capsule = run.capsule || {};
  const ea = run.evidence || {};
  const rf = run.result_figure || {};
  const paperClaims = state.data?.modules?.paper?.claims || [];
  const claimBound = paperClaims.length > 0;
  const runOk = (run.status || capsule.status) === "completed";
  const metricKey = capsule.metric_name || "metric";
  const seedRows = (capsule.metrics_by_seed || []).map((row) => `<span class="chip">${esc(row.seed)} → ${esc(fmtNum(row[metricKey] ?? row.metric ?? "?"))}</span>`).join(" ");
  return `
    <section class="data-card">
      <span class="eyebrow">S5 / RUN · LOCAL PROTOCOL</span><h3>复现执行（本地数据集）</h3>
      <dl class="kv">
        <dt>RUN</dt><dd class="mono">${esc(capsule.run_id || "—")}</dd>
        <dt>STATUS</dt><dd><span class="chip ${runOk ? "ok" : "bad"}">${esc(run.status || capsule.status)}</span></dd>
        <dt>DATASET</dt><dd>${esc(capsule.dataset_id || "—")} · test_size ${esc(capsule.test_size ?? "—")}</dd>
        <dt>SEEDS</dt><dd>${seedRows || "—"}</dd>
        <dt>RESULT</dt><dd>${esc(capsule.metric_name || "—")} mean <b>${esc(fmtNum(capsule.mean ?? "—"))}</b> ± ${esc(fmtNum(capsule.std ?? "—"))} · 协议验证，不是论文证据</dd>
        <dt>EA</dt><dd class="mono">${esc(ea.artifact_id || "—")} · sha ${esc((ea.sha256 || "").slice(0, 16))}…</dd>
        <dt>CLAIM</dt><dd>${claimBound
          ? '<span class="chip ok">bound_claim</span> 结果槽已绑定人签 claim'
          : run.claim_draft
            ? '<span class="chip warn">draft_needs_human</span> 人签后才可绑定 paper 结果槽'
            : '<span class="chip">not created</span> 本次 run 没有 claim 草稿'}</dd>
      </dl>
      ${rf.figure_id ? `
      <div class="run-figure">
        <div class="card-head"><div><span class="eyebrow">RESULT FIGURE · BOUND TO EA</span></div><span class="badge quiet">RUN DATA</span></div>
        <div class="figure-frame"><img src="${state.taskDir || "data"}/run/result-figure.svg?v=${encodeURIComponent(rf.figure_id)}" alt="S5 结果图，绑定 EA" loading="lazy" /></div>
        <div class="figure-foot"><span>结果图绑定 run capsule 与 EA；与模块关系示意图不同源。</span><span class="mono">${esc(rf.figure_id)}</span></div>
      </div>` : ""}
    </section>`;
}

function renderPaper() {
  const d = state.data;
  const paper = d.modules.paper || {};
  const grant = d.modules.grant;
  $("paper-grid").innerHTML = `
    <section class="data-card wide">
      <span class="eyebrow">S8–S12 / PAPER CONTRACT</span><h3>${esc(paper.title || "论文契约")}</h3>
      <dl class="kv">
        <dt>PROFILE</dt><dd>${esc(paper.profile?.venue_type || "—")} · ${esc(paper.profile?.language || "—")} · ${esc(paper.profile?.citation_style || "—")}</dd>
        <dt>STATUS</dt><dd><span class="chip warn">${esc(paper.status || "—")}</span></dd>
        <dt>SECTIONS</dt><dd class="chips">${(paper.sections || []).map((section) => `<span class="chip">${esc(section)}</span>`).join("")}</dd>
        <dt>CLAIMS</dt><dd>${(paper.claims || []).length} · ${(paper.claims || []).length ? "已绑定 claim ID" : "结果槽未填"}</dd>
      </dl>
      <ul class="slot-list">${(paper.slots || []).map((slot) => `<li class="slot-row"><div><b>${esc(slot.slot_id)}</b><span>${esc(slot.section)} · requires ${esc(slot.required_evidence)}</span></div><span class="slot-status">${esc(slot.status)}</span></li>`).join("")}</ul>
    </section>
    <section class="data-card wide">
      <span class="eyebrow">S8–S12 / GRANT TRACK</span><h3>${grant ? esc(grant.title) : "本次运行未生成基金轨"}</h3>
      ${grant ? `<dl class="kv"><dt>SCHEME</dt><dd>${esc(grant.scheme)}</dd><dt>MODULES</dt><dd class="chips">${(grant.modules || []).map((m) => `<span class="chip">${esc(m)}</span>`).join("")}</dd><dt>COMPLIANCE</dt><dd class="chips">${(grant.compliance || []).map((c) => `<span class="chip warn">${esc(c)}</span>`).join("")}</dd></dl>` : `<div class="empty">用 <code>--grant nsfc</code> 运行 pipeline 可生成基金骨架。</div>`}
    </section>
    <section class="data-card wide">
      <span class="eyebrow">WRITING SAFETY</span><h3>为什么结果槽是 pending</h3>
      <ul class="warning-list">${(paper.warnings || []).map((warning) => `<li>${esc(warning)}</li>`).join("")}</ul>
    </section>`;
}

function renderTrace() {
  const d = state.data;
  $("trace-grid").innerHTML = `
    <section class="trace-card">
      <span class="eyebrow">GATES</span><h3>门禁状态</h3>
      <div class="gate-list">${(d.gates || []).map((gate) => `<div class="gate-row"><b>${esc(gate.gate)}</b><span>${esc(gate.reason)}</span><em>${esc(gate.status)}</em></div>`).join("")}</div>
    </section>
    <section class="trace-card">
      <span class="eyebrow">WARNINGS</span><h3>边界与缺口</h3>
      <ul class="warning-list">${(d.warnings || []).map((warning) => `<li>${esc(warning)}</li>`).join("")}</ul>
    </section>
    <section class="trace-card">
      <span class="eyebrow">SPEC VERSIONS</span><h3>模块规格</h3>
      <div class="version-grid">${Object.entries(d.spec_versions || {}).map(([key, value]) => `<span><b>${esc(MODULE_META[key]?.label || key)}</b><code>${esc(value)}</code></span>`).join("")}</div>
    </section>
    <section class="trace-card">
      <span class="eyebrow">SOURCE</span><h3>运行来源</h3>
      <dl class="kv"><dt>RUN</dt><dd class="mono">${esc(d.run_id)}</dd><dt>MODE</dt><dd>${esc(d.source || "fixture")}</dd><dt>FIGURE</dt><dd>${esc(d.figure_uri)}</dd></dl>
    </section>`;
}

const LOOP_STEPS = [
  { key: "observe", title: "观察", actor: "AGENT", desc: "研究运行产出可证伪观测：成本、覆盖、缺口" },
  { key: "propose", title: "提案 + dry-run", actor: "AGENT", desc: "候选只改 skill / process / prompt / knowledge，必须带 dry-run 凭据" },
  { key: "public", title: "Public 预筛", actor: "GOVERNOR", desc: "按 public 指标排序，最多 2 个 finalist 依次过门" },
  { key: "gates", title: "Hidden / OOD / 回归", actor: "GOVERNOR", desc: "hidden 不参与排序；near-OOD 与 regression 防过拟合与遗忘" },
  { key: "admit", title: "人签准入", actor: "HUMAN", desc: "public + hidden 双过、dry-run、理由、scope，缺一不可" },
  { key: "lease", title: "Lease 发放", actor: "GOVERNOR", desc: "绑定 scope 与 TTL；不同预算的 active lease 冲突即 fail-closed" },
  { key: "consume", title: "研究运行消费", actor: "AGENT", desc: "run execute --use-lease / pipeline --use-lease；scope 不匹配拒绝执行" },
  { key: "confirm", title: "Sealed 复核", actor: "HUMAN", desc: "held-out 复核只做审计，不回流准入；回归交人处理" },
  { key: "archive", title: "归档 / 负结果", actor: "GOVERNOR", desc: "lineage 与拒绝理由永久保留；无新证据不得重试" }
];

const ACTOR_CLASS = { AGENT: "agent", GOVERNOR: "governor", HUMAN: "human" };
const DECISION_META = {
  approved: { label: "APPROVED · 人签准入", cls: "ok" },
  rejected: { label: "REJECTED · 负结果保留", cls: "bad" },
  pending_human: { label: "PENDING · 等待人签", cls: "warn" }
};
const EVAL_LABEL = { public_eval: "PUBLIC", hidden_eval: "HIDDEN", near_ood_eval: "NEAR-OOD", regression_eval: "REGRESSION" };

function renderEvolution() {
  const badge = $("evo-source-badge");
  const stepper = $("loop-stepper");
  const kpi = $("evo-kpi");
  const grid = $("evo-grid");
  if (!badge || !stepper || !kpi || !grid) return;
  if (!state.rsi) {
    badge.textContent = "NO DATA";
    stepper.innerHTML = "";
    kpi.innerHTML = "";
    grid.innerHTML = `<section class="data-card wide"><span class="eyebrow">RSI / GOVERNED LOOP</span><h3>暂无自进化台账快照</h3><div class="empty">未找到 <code>data/rsi.json</code>。用本地 RSI 控制面生成台账后导出：<br><code>python scripts/export-rsi-view.py --ledger research_agent/web/data/rsi-chemlab-v2/ledger.json --output research_agent/web/data/rsi.json</code><br>只读导出，不修改台账；浏览器端不提供 approve/claim/sign。</div></section>`;
    return;
  }
  const ledger = state.rsi.ledger || {};
  const report = state.rsi.report || {};
  const episodes = [...(ledger.episodes || [])].reverse();
  const leases = ledger.leases || [];
  const confirmations = report.confirmations?.records || [];
  const context = rsiScopeInfo();
  badge.textContent = report.simulation ? "FIXTURE / SIMULATION" : "STATIC SNAPSHOT · LOCAL EVAL";
  badge.title = `${context.ledger} · ${context.scopes.join(" / ") || "no scope"}`;

  const dryCount = (ledger.episodes || []).filter((e) => (e.dry_run_ref || "").trim()).length;
  const publicPassed = (ledger.episodes || []).filter((e) => e.public_eval?.status === "passed").length;
  const gated = (ledger.episodes || []).filter((e) => e.hidden_eval?.status === "passed" && e.near_ood_eval?.status === "passed" && e.regression_eval?.status === "passed").length;
  const confirmed = report.confirmations?.confirmed ?? 0;
  const regressed = report.confirmations?.regressed ?? 0;
  const stepStatus = {
    observe: `${report.episodes ?? 0} episodes`,
    propose: `${dryCount}/${report.episodes ?? 0} 带 dry-run`,
    public: `${publicPassed} public passed`,
    gates: gated ? `${gated} 过全部三道门` : "none",
    admit: `${report.approved ?? 0} 人签准入`,
    lease: `${report.active_leases ?? 0} active · ${report.expired_leases ?? 0} expired · ${report.revoked_leases ?? 0} revoked`,
    consume: confirmed || regressed ? "lease 已被消费（存在复核）" : "尚未消费",
    confirm: `${confirmed} confirmed · ${regressed} regressed`,
    archive: `${report.rejected ?? 0} 拒绝项保留`
  };
  stepper.innerHTML = LOOP_STEPS.map((step, index) => `
    <div class="loop-step ${stepStatus[step.key] && stepStatus[step.key] !== "none" && !/^(0|尚未)/.test(stepStatus[step.key]) ? "is-done" : ""} ${step.actor === "HUMAN" ? "is-human" : ""}">
      <div class="loop-top"><span class="loop-index">${String(index + 1).padStart(2, "0")}</span><span class="actor-chip ${ACTOR_CLASS[step.actor]}">${step.actor}</span></div>
      <b class="loop-title">${esc(step.title)}</b>
      <p class="loop-desc">${esc(step.desc)}</p>
      <span class="loop-state mono">${esc(stepStatus[step.key] || "—")}</span>
    </div>`).join("");
  const legend = $("loop-legend");
  if (legend) {
    legend.innerHTML = `
      <span><i class="swatch done"></i>有证据已完成</span>
      <span><i class="swatch human"></i>人工门（人签准入 / sealed 复核）</span>
      <span><i class="swatch todo"></i>尚无数据</span>
      <span class="loop-back">↻ 复核与归档结果回流为下一轮 Observation；负结果保留，无新证据不得重试</span>`;
  }

  const tracking = report.tracking || {};
  const capabilityClaims = (report.capability_claims || []).length;
  kpi.innerHTML = [
    { value: report.episodes ?? 0, label: "EPISODES", note: context.matches ? "本任务同 scope 的提案（含负结果）" : "跨任务台账；不是本任务证据" },
    { value: report.approved ?? 0, label: "APPROVED", note: "人签准入并发 lease" },
    { value: report.rejected ?? 0, label: "REJECTED", note: "负结果保留，不得无证据重试" },
    { value: report.active_leases ?? 0, label: "ACTIVE LEASES", note: `${report.expired_leases ?? 0} expired · ${report.revoked_leases ?? 0} revoked` },
    { value: `${confirmed}`, label: "SEALED 复核", note: "只审计，不回流准入" },
    { value: capabilityClaims, label: "CAPABILITY CLAIMS", note: capabilityClaims ? "存在可主张项；逐条核对" : "0 · harness-only 不产生能力主张" }
  ].map((stat) => `<div class="stat"><b>${esc(stat.value)}</b><span>${esc(stat.label)}</span><em>${esc(stat.note)}</em></div>`).join("");

  const episodeCards = episodes.map((episode) => {
    const candidate = episode.candidate || {};
    const decision = DECISION_META[episode.decision] || { label: episode.decision, cls: "warn" };
    const evals = Object.keys(EVAL_LABEL).map((key) => {
      const ev = episode[key];
      if (!ev) {
        if (key === "hidden_eval" && episode.decision !== "approved") return `<span class="chip">HIDDEN 未读 · 未准入</span>`;
        return "";
      }
      const metrics = ev.metrics || {};
      const mean = metrics.mean_r2 ?? metrics.mean_score ?? metrics.recall;
      const parts = [];
      if (mean != null) parts.push(`mean ${fmtNum(mean)}`);
      if ("cost" in metrics) parts.push(`cost ${fmtNum(metrics.cost)}`);
      return `<span class="chip ${ev.status === "passed" ? "ok" : "bad"}" title="${esc(ev.artifact_ref || "")}">${EVAL_LABEL[key]} ${esc(ev.status)}${parts.length ? " · " + esc(parts.join(" · ")) : ""}</span>`;
    }).join("");
    const predicted = candidate.predicted_metrics || {};
    const actuals = episode.actuals || {};
    const shared = Object.keys(predicted).filter((key) => key in actuals);
    const evidenceItems = ["public_eval", "hidden_eval", "near_ood_eval", "regression_eval"]
      .map((key) => episode[key]).filter(Boolean);
    const claimEligible = evidenceItems.length > 0
      && !episode.simulation
      && evidenceItems.every((item) => item.claim_eligible === true);
    const calibrationRows = shared.length ? shared.map((key) => {
      const error = Number(actuals[key]) - Number(predicted[key]);
      const sameDir = (predicted[key] > 0) === (actuals[key] > 0) && !(predicted[key] === 0 && actuals[key] !== 0);
      return `<tr><td class="mono">${esc(key)}</td><td class="mono">${esc(fmtNum(predicted[key]))}</td><td class="mono">${esc(fmtNum(actuals[key]))}</td><td class="mono ${sameDir ? "ok-text" : "bad-text"}">${error >= 0 ? "+" : ""}${esc(fmtNum(error))}</td><td class="mono ${sameDir ? "ok-text" : "bad-text"}">${sameDir ? "同向" : "反向"}</td></tr>`;
    }).join("") : "";
    return `
    <article class="ep-card is-${episode.decision}">
      <header class="ep-head">
        <div class="ep-title">
          <span class="dec-badge ${decision.cls}">${esc(decision.label)}</span>
          <b>${esc(candidate.candidate_id || episode.episode_id)}</b>
          <span class="chip">${esc(candidate.kind || "?")}</span>
          <span class="mono ep-target">${esc(candidate.target || "")}</span>
        </div>
        <span class="mono ep-date">${esc((episode.created_at || "").slice(0, 10))}</span>
      </header>
      <dl class="kv">
        <dt>PATCH</dt><dd class="mono">${esc(candidate.patch || "—")}</dd>
        <dt>WHY</dt><dd>${esc(candidate.rationale || "—")}</dd>
        <dt>PREDICT</dt><dd>${esc(candidate.predicted_effect || "—")}${Object.keys(predicted).length ? " · " + Object.entries(predicted).map(([k, v]) => `${esc(k)}=${esc(fmtNum(v))}`).join(" · ") : ""}</dd>
        ${evals ? `<dt>EVALS</dt><dd class="chips">${evals}</dd>` : ""}
        ${episode.dry_run_ref ? `<dt>DRY-RUN</dt><dd class="mono">${esc(episode.dry_run_ref)}</dd>` : `<dt>DRY-RUN</dt><dd><span class="chip bad">缺失 · 不可准入</span></dd>`}
        ${episode.decision === "approved" ? `<dt>HUMAN</dt><dd>${esc(episode.reason || "—")}</dd>` : ""}
        ${episode.decision === "rejected" ? `<dt>REJECT REASON</dt><dd>${esc(episode.reason || "—")}</dd>` : ""}
        ${episode.lease_id ? `<dt>LEASE</dt><dd class="mono">${esc(episode.lease_id)}</dd>` : ""}
      </dl>
      ${calibrationRows ? `<table class="cal-table"><thead><tr><th>指标</th><th>预测</th><th>实际</th><th>误差</th><th>方向</th></tr></thead><tbody>${calibrationRows}</tbody></table>` : ""}
      <footer class="ep-foot">
        <span class="chip ${episode.simulation ? "warn" : ""}">${episode.simulation ? "simulation" : "simulation=false"}</span>
        <span class="chip ${claimEligible ? "ok" : "warn"}">claim_eligible=${claimEligible}</span>
        <span class="mono">${esc(episode.episode_id)}</span>
      </footer>
    </article>`;
  }).join("") || `<div class="empty">还没有 episode；先记录一个可证伪的改进候选。</div>`;

  const leaseRows = leases.map((lease) => {
    const effective = leaseStatus(lease);
    return `
    <div class="lease-row ${effective}">
      <b class="mono">${esc(lease.lease_id)}</b>
      <span class="mono">${esc(lease.scope)}</span>
      <span>TTL ${esc(lease.ttl_days)}d · ${esc(effective)}</span>
      <span class="mono">${esc((lease.created_at || "").slice(0, 10))}</span>
    </div>`;
  }).join("") || `<div class="empty">没有 lease。</div>`;

  const confRows = confirmations.map((conf) => `
    <div class="conf-item">
      <div class="conf-head">
        <span class="dec-badge ${conf.status === "confirmed" ? "ok" : conf.status === "regressed" ? "bad" : "warn"}">${esc(conf.status?.toUpperCase())}</span>
        <span class="mono">${esc(conf.episode_id || "")}</span>
        <span class="chip">sealed · used_for_admission=false</span>
      </div>
      <div class="chips">${Object.entries(conf.delta || {}).map(([key, value]) => `<span class="chip ${value >= 0 ? "ok" : "warn"}">${esc(key)} ${value >= 0 ? "+" : ""}${esc(fmtNum(value))}</span>`).join("")}</div>
      <span class="mono conf-hash">${esc((conf.artifact_sha256 || "").slice(0, 24))}… · ${esc(conf.scope || "")}</span>
    </div>`).join("") || `<div class="empty">没有 sealed 复核记录。</div>`;

  const trackingMetrics = Object.entries(tracking.metrics || {}).map(([key, value]) => `
    <div class="version-grid"><span><b>${esc(key)}</b><code>n=${esc(value.n)} · MAE ${esc(fmtNum(value.mae))}</code></span><span><b>bias</b><code>${esc(fmtNum(value.bias))} · 同向 ${esc(Math.round((value.direction_agreement || 0) * 100))}%</code></span></div>`).join("");

  grid.innerHTML = `
    <section class="data-card wide">
      <div class="evo-context ${context.matches ? "" : "is-cross"}">
        <span><b>LEDGER</b> ${esc(context.ledger)}</span>
        <span><b>SCOPE</b> ${esc(context.scopes.join(" · ") || "未记录")}</span>
        <span><b>THIS TASK</b> ${esc(context.taskScope || "无 S5 run")}</span>
        <span><b>MATCH</b> ${context.matches ? "同任务" : "跨任务"}</span>
      </div>
      <p class="arm-note">${context.matches
        ? "该台账与当前任务的 S5 scope 一致；episode/lease 可对照本任务解读，但仍不得把 harness 指标写成科学结论。"
        : "该台账不是当前任务的证据：以下 episode、lease 与校准只能作为跨任务示例；不要把它读成本任务的自进化结果。"}</p>
    </section>
    <section class="data-card wide">
      <div class="card-head"><div><span class="eyebrow">EPISODE LEDGER</span><b class="card-title">改进候选时间线</b></div><span class="badge quiet">${esc(state.rsi.source?.command || "")}</span></div>
      <div class="ep-timeline">${episodeCards}</div>
    </section>
    <section class="data-card">
      <span class="eyebrow">LEASE / SEALED 复核</span><h3>租约与租约后审计</h3>
      ${leaseRows}
      <h4 class="sub-head">sealed confirmations</h4>
      ${confRows}
    </section>
    <section class="data-card">
      <span class="eyebrow">GUARDRAILS</span><h3>护栏 · 为什么不能自己改自己</h3>
      <dl class="kv">
        <dt>IMMUTABLE</dt><dd class="chips">${["claim", "evidence", "gate", "rubric", "export", "signature", "authorship"].map((surface) => `<span class="chip bad">${esc(surface)}</span>`).join("")}</dd>
        <dt>RULES</dt><dd><ul class="list">
          <li>无 dry-run 不准入；无 public+hidden 不准入；无人签不 active。</li>
          <li>lease scope 必须与执行器匹配；到期即失效；冲突 fail-closed。</li>
          <li>sealed 复核不回流准入；regressed 交人处理。</li>
          <li>同一 target+patch 不得重复 propose；负结果永久保留。</li>
          <li>预测-实际写入 ledger；数值校准只描述过程，不当能力证据。</li>
        </ul></dd>
        <dt>CLAIMS</dt><dd><span class="chip ${capabilityClaims ? "bad" : "warn"}">capability_claims = ${capabilityClaims}</span> ${capabilityClaims
          ? "存在可主张项；逐条核对 hidden/near-OOD/regression 与 scope，不得直接写成能力提升。"
          : "本台账没有可主张能力项；harness-only 证据按边界不生成能力主张。"}</dd>
      </dl>
      ${(report.warnings || []).length ? `<h4 class="sub-head">meta-tracker warnings</h4><ul class="warning-list">${report.warnings.map((warning) => `<li>${esc(warning)}</li>`).join("")}</ul>` : ""}
    </section>
    <section class="data-card">
      <span class="eyebrow">CALIBRATION</span><h3>预测校准（过程，非能力）</h3>
      <dl class="kv">
        <dt>STATUS</dt><dd><span class="chip ${tracking.status === "tracked" ? "ok" : "warn"}">${esc(tracking.status || "no_actuals")}</span> coverage ${esc(Math.round((tracking.coverage || 0) * 100))}%</dd>
        <dt>NEXT</dt><dd><ul class="list">${(report.next_questions || []).map((question) => `<li>${esc(question)}</li>`).join("")}</ul></dd>
      </dl>
      ${trackingMetrics || `<div class="empty">没有可比对的数值预测。</div>`}
    </section>`;
}

const INNOV_STATUS_META = {
  implemented: { label: "IMPLEMENTED · 已实现", cls: "ok" },
  "minimal-implemented": { label: "MINIMAL · 最小落地", cls: "warn" },
  design: { label: "DESIGN · 设计阶段", cls: "warn" }
};
const INNOV_PILLARS = [
  { key: "skeleton", title: "证据闭合（骨架）", desc: "定义「什么能被留下」：span-only → 结果槽 pending → 人签 Claim → 导出硬门" },
  { key: "engine", title: "Lease-Gated RSI（动力）", desc: "定义「什么能被改进」：dry-run → public/hidden → 人签准入 → Lease → sealed 复核" },
  { key: "runtime", title: "证据运行时（底座）", desc: "保证「没人能绕过」：Spec-Driven 模块 + artifact/gate 中介 + 真实性三态 + fail-closed" }
];

function innovationCheckState(pillarId, label) {
  const rows = (state.innovationReport?.results || []).filter((row) => row.pillar === pillarId && row.label === label);
  if (!rows.length) return null;
  return rows.every((row) => row.ok);
}

function renderInnovation() {
  const badge = $("innov-verify-badge");
  const flow = $("innov-flow");
  const grid = $("innov-grid");
  if (!badge || !flow || !grid) return;
  if (!state.innovations.length) {
    badge.textContent = "NO DATA";
    flow.innerHTML = "";
    grid.innerHTML = `<section class="data-card wide"><span class="eyebrow">INNOVATION LEDGER</span><h3>暂无创新账本数据</h3><div class="empty">未找到 <code>data/innovations.json</code>。创新主张映射由 27- 对账文档维护，运行 <code>python scripts/verify-innovation-claims.py</code> 生成校验报告。</div></section>`;
    return;
  }
  const report = state.innovationReport;
  if (report) {
    badge.textContent = `${report.passed}/${report.total} CHECKS ${report.failed ? "FAILED" : "PASS"}`;
    badge.className = "badge " + (report.failed ? "" : "quiet pass");
  } else {
    badge.textContent = "未验证 · 运行 verify 脚本";
    badge.className = "badge quiet";
  }
  flow.innerHTML = INNOV_PILLARS.map((pillar, index) => `
    <div class="loop-step is-done ${index === 1 ? "is-human" : ""}">
      <div class="loop-top"><span class="loop-index">${String(index + 1).padStart(2, "0")}</span><span class="actor-chip ${index === 1 ? "human" : index === 0 ? "governor" : "agent"}">${["SKELETON", "ENGINE", "RUNTIME"][index]}</span></div>
      <b class="loop-title">${esc(pillar.title)}</b>
      <p class="loop-desc">${esc(pillar.desc)}</p>
    </div>`).join("") + `
    <div class="loop-step">
      <div class="loop-top"><span class="loop-index">04</span><span class="actor-chip human">NEXT</span></div>
      <b class="loop-title">证据运营（RWMT）</b>
      <p class="loop-desc">绑定是入场券；传播—处置—修复—签署才是产品（设计阶段）</p>
    </div>`;

  grid.innerHTML = state.innovations.map((pillar) => {
    const statusMeta = INNOV_STATUS_META[pillar.status] || { label: pillar.status, cls: "warn" };
    const checks = (pillar.checks || []).map((check) => {
      const state1 = innovationCheckState(pillar.id, check.label);
      return `<span class="chip ${state1 === null ? "" : state1 ? "ok" : "bad"}" title="${esc(check.path)}">${state1 === null ? "?" : state1 ? "✓" : "✗"} ${esc(check.label)}</span>`;
    }).join("");
    return `
    <section class="data-card">
      <span class="eyebrow">${esc((pillar.docs || []).map((doc) => doc + "-").join(" "))}设计文档</span>
      <h3>${esc(pillar.title)}</h3>
      <p class="innov-claim">${esc(pillar.claim)}</p>
      <div class="innov-status"><span class="dec-badge ${statusMeta.cls}">${esc(statusMeta.label)}</span><span class="chip">${esc(pillar.status_label || pillar.status)}</span></div>
      <dl class="kv">
        <dt>MECH</dt><dd><ul class="list">${(pillar.mechanisms || []).map((mechanism) => `<li>${esc(mechanism)}</li>`).join("")}</ul></dd>
        <dt>CHECKS</dt><dd class="chips">${checks || "—"}</dd>
        <dt>EVIDENCE</dt><dd>${esc(pillar.live_evidence || "—")}</dd>
        <dt>CONTRAST</dt><dd>${esc(pillar.contrast || "—")}</dd>
      </dl>
    </section>`;
  }).join("");
}

function renderInspector() {
  const id = state.selected;
  const meta = MODULE_META[id];
  const spec = specOf(id);
  const module = state.data.modules[id];
  $("inspector-module").textContent = id.toUpperCase();
  if (!meta) {
    $("inspector-body").innerHTML = `<div class="empty">选择一个模块。</div>`;
    return;
  }
  const status = statusOf(id);
  const outputs = spec?.outputs || [];
  const invariants = spec?.invariants || [];
  const inputs = spec?.inputs || [];
  const binding = modelOf(id);
  const artifact = summarizeArtifact(id, module);
  $("inspector-body").innerHTML = `
    <h2>${esc(meta.label)}</h2>
    <div class="sub">${esc(meta.desc)}</div>
    <div class="spec-block"><h4>STATE</h4><p><span class="chip ${moduleStatusClass(status)}">${esc(status)}</span> ${spec ? `· spec ${esc(spec.version)}` : ""}</p></div>
    ${binding ? `<div class="spec-block"><h4>MODEL</h4><p><span class="chip glm">${esc(binding.model)}</span> ${esc(binding.status)}</p>${list(binding.used_for || [])}<p class="model-note-inside">约束：${esc((binding.constraints || []).join("；"))}</p></div>` : ""}
    <div class="spec-block"><h4>ARTIFACT</h4><p>${esc(artifact)}</p></div>
    <div class="spec-block"><h4>INPUTS</h4>${list(inputs)}</div>
    <div class="spec-block"><h4>OUTPUTS</h4>${list(outputs)}</div>
    <div class="spec-block"><h4>INVARIANTS</h4>${list(invariants)}</div>
    <div class="spec-block"><h4>NEXT ACTION</h4><p>${esc(nextAction(id, status))}</p></div>`;
}

function list(items) {
  return items.length ? `<ul class="list">${items.map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : `<p>—</p>`;
}

function summarizeArtifact(id, module) {
  if (!module) return "尚未生成。";
  if (id === "literature") return `${(module.hits || []).length} hits · ${(module.spans || []).length} spans · ${(module.coverage?.gaps || []).length} gaps`;
  if (id === "idea") return `${(module.candidates || []).length} candidate frames · no claim`;
  if (id === "experiment") return `${module.status} · ${module.seeds} seeds · metric ${module.primary_metric || "待补"}`;
  if (id === "run") return `${module.capsule?.run_id || "—"} · ${module.capsule?.metric_name} ${fmtNum(module.capsule?.mean ?? "—")}±${fmtNum(module.capsule?.std ?? "—")} · EA ${module.evidence?.artifact_id || "—"} · claim 未签`;
  if (id === "figure") return `${module.figure_id} · audit ${module.audit?.ok ? "PASS" : "FAIL"} · ${module.manifest?.style || ""}`;
  if (id === "paper") return `${(module.sections || []).length} sections · ${(module.slots || []).length} pending slots · 0 claims`;
  if (id === "grant") return `${(module.modules || []).length} modules · ${(module.compliance || []).length} compliance checks`;
  return "—";
}

function nextAction(id, status) {
  if (id === "literature") return "抽查 span 与 coverage；通过 Q0 后才进入 claim 准入。";
  if (id === "idea") return "由人补全机制/指标并做 G1；不要自动选短名单。";
  if (id === "experiment") return "冻结 protocol/TaskSpec 并签 G2；本模块不执行 run。";
  if (id === "run") return "人签 claim（run claim --capsule … --ea …）后才能绑定 paper 结果槽；未签前结果槽保持 pending。";
  if (id === "figure") return "确认示意图语义；结果图必须重新绑定 run data，不能复用示意图。";
  if (id === "paper") return "等 EA/Claim 到达后填结果槽；schematic figure 不能当结果图。";
  if (id === "grant") return "按当年官方模板核对页限/匿名/AI 声明；科学观点由申请人提供。";
  return "查看 SPEC.md 与 gate。";
}

function renderTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    const on = tab.dataset.tab === state.tab;
    tab.classList.toggle("is-on", on);
    tab.setAttribute("aria-selected", String(on));
  });
  VIEWS.forEach((name) => {
    const panel = $("panel-" + name);
    if (panel) {
      panel.classList.toggle("is-on", state.tab === name);
      panel.hidden = state.tab !== name;
    }
  });
}

function renderAll() {
  renderTasks();
  renderHeader();
  renderRail();
  renderPipeline();
  renderOverview();
  renderEvidence();
  renderPaper();
  renderTrace();
  renderEvolution();
  renderInnovation();
  renderInspector();
  renderTabs();
}

function selectModule(id, announce = true, tab = "overview") {
  if (!available().includes(id)) return;
  clearTimeout(state.replayTimer);
  state.replayTimer = null;
  state.selected = id;
  state.tab = tab;
  if (announce) setStatus("INSPECT · " + MODULE_META[id].label);
  renderAll();
}

function switchTab(name) {
  state.tab = name;
  setStatus("VIEW · " + name.toUpperCase());
  renderTabs();
}

function switchMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode").forEach((button) => {
    const on = button.dataset.mode === mode;
    button.classList.toggle("is-on", on);
    button.setAttribute("aria-pressed", String(on));
  });
  if (mode === "grant") {
    if (state.data.modules.grant) selectModule("grant", true, "paper");
    else {
      switchTab("paper");
      setStatus("本次运行未生成基金轨");
    }
  } else {
    selectModule("paper", true, "paper");
  }
}

function replay() {
  clearTimeout(state.replayTimer);
  switchTab("overview");
  const ids = available();
  let index = 0;
  setStatus("SIM REPLAY · fixture");
  const step = () => {
    if (index >= ids.length) {
      setStatus("REPLAY DONE · no data mutated");
      state.replayTimer = null;
      return;
    }
    state.selected = ids[index];
    renderAll();
    setStatus("SIM REPLAY · " + MODULE_META[ids[index]].label);
    index += 1;
    state.replayTimer = setTimeout(step, 460);
  };
  step();
}

function paletteItems(query) {
  const q = query.trim().toLowerCase();
  const items = state.tasks.map((task) => ({
    id: "task:" + task.id,
    type: "task",
    title: task.topic || task.id,
    meta: `TASK · ${task.venue} · ${task.fixture_mode ? "fixture" : "real-text"}${state.taskId === task.id ? " · 当前" : ""}`
  }));
  const modules = available().map((id) => ({
    id: "module:" + id,
    type: "module",
    module: id,
    title: MODULE_META[id].label,
    meta: `${MODULE_META[id].stage} · ${statusOf(id)}`
  }));
  const actions = [
    { id: "action:replay", type: "action", title: "回放运行", meta: "SIM" },
    { id: "action:overview", type: "tab", title: "打开总览", meta: "VIEW" },
    { id: "action:evidence", type: "tab", title: "打开证据", meta: "VIEW" },
    { id: "action:paper", type: "tab", title: "打开稿件/基金", meta: "VIEW" },
    { id: "action:trace", type: "tab", title: "打开运行记录", meta: "VIEW" },
    { id: "action:evolution", type: "tab", title: "打开自进化", meta: "VIEW · RSI" },
    { id: "action:innovation", type: "tab", title: "打开创新逻辑", meta: "VIEW · LEDGER" },
    { id: "action:gateway", type: "action", title: "打开模型网关", meta: "MODELS" }
  ];
  return [...items, ...modules, ...actions].filter((item) => !q || (item.title + " " + item.meta).toLowerCase().includes(q));
}

function renderPalette(query = "") {
  state.paletteItems = paletteItems(query);
  if (state.paletteIndex >= state.paletteItems.length) state.paletteIndex = Math.max(0, state.paletteItems.length - 1);
  $("palette-list").innerHTML = state.paletteItems.map((item, index) => `<button type="button" class="palette-item ${index === state.paletteIndex ? "is-on" : ""}" data-index="${index}"><b>${esc(item.title)}</b><span>${esc(item.meta)}</span></button>`).join("") || `<div class="empty">没有匹配项</div>`;
}

function openPalette() {
  state.lastFocus = document.activeElement;
  $("app").inert = true;
  $("palette").hidden = false;
  $("palette-input").value = "";
  state.paletteIndex = 0;
  renderPalette("");
  setTimeout(() => $("palette-input").focus(), 0);
}

function closePalette() {
  $("palette").hidden = true;
  $("app").inert = false;
  if (state.lastFocus && state.lastFocus !== document.body && typeof state.lastFocus.focus === "function") state.lastFocus.focus();
  else $("palette-btn").focus();
}

/* ---- model gateway panel ---- */
function renderGateway() {
  const body = $("gateway-body");
  const badge = $("gateway-live-badge");
  if (!body) return;
  const snap = state.gateway;
  if (!snap) {
    badge.textContent = "NO DATA";
    badge.className = "badge";
    body.innerHTML = `<div class="empty">未找到 data/gateway.json。运行 <code>python scripts/export-gateway-snapshot.py</code> 生成离线快照，或启动本地 runtime（python -m research_agent.runtime）后点击「探测实时状态」。</div>`;
    return;
  }
  badge.textContent = state.gatewayLive ? "LIVE · 本地 RUNTIME" : "STATIC · 离线快照";
  badge.className = "badge quiet" + (state.gatewayLive ? " pass" : "");
  const providers = (snap.providers || []).map((provider) => `
    <div class="gw-provider">
      <div class="gw-provider-head"><b>${esc(provider.label || provider.provider_id)}</b><span class="gw-kind">${esc(provider.kind)}</span></div>
      <span class="gw-key ${provider.configured ? "ok" : "miss"}"><i></i>${provider.configured ? `key 已配置（${esc(provider.key_source || "env")} · ${esc(provider.masked_key || "****")}）` : `未设置 key · export ${esc(provider.api_key_env)}=sk-…`}</span>
      <p class="gw-meta">${esc(provider.base_url || "(default)")}</p>
      ${(provider.models || []).length ? `<div class="gw-models">${provider.models.map((model) => `<span class="chip">${esc(model)}</span>`).join("")}</div>` : ""}
    </div>`).join("");
  const profiles = snap.profiles || [];
  const bindings = snap.bindings || {};
  const wired = snap.wired || {};
  const bindingRows = Object.keys(bindings).map((moduleId) => {
    const profileId = bindings[moduleId];
    const profile = profiles.find((item) => item.profile_id === profileId) || {};
    const wiring = wired[moduleId] || {};
    const thinking = profile.thinking || {};
    const thinkingText = thinking.mode === "off" ? "off"
      : thinking.mode === "budget" ? `budget(${thinking.budget_tokens})`
      : `effort(${thinking.effort})`;
    return `<div class="gw-binding-row">
      <b>${esc(moduleId)}</b>
      <div>
        <span class="chip glm">${esc(profileId)}</span> ${esc(profile.model || "")} · ${esc(profile.provider_id || "")} · thinking ${esc(thinkingText)}
        <span class="gw-binding-note">${wiring.wired ? esc(wiring.consumer || "") : esc(wiring.note || "未接入：当前为规则模板")}${wiring.wired && wiring.note ? " · " + esc(wiring.note) : ""}</span>
      </div>
    </div>`;
  }).join("");
  body.innerHTML = `
    <div>
      <span class="gateway-section-title">Providers · 接入任意 OpenAI / Anthropic / 兼容端点</span>
      <div class="gw-provider-grid">${providers}</div>
    </div>
    <div>
      <span class="gateway-section-title">模块绑定 · 谁用哪个模型</span>
      <div>${bindingRows || '<div class="empty">暂无绑定</div>'}</div>
    </div>
    <div>
      <span class="gateway-section-title">思考模式 · 三种语义</span>
      <div class="gw-thinking">
        <div class="gw-card"><b>off</b><br>直接采样（temperature 0.2）；默认。</div>
        <div class="gw-card"><b>effort</b><br>OpenAI/Azure → reasoning_effort（minimal→max）；Anthropic 映射为 1024–16384 token 预算。</div>
        <div class="gw-card"><b>budget</b><br>Anthropic → thinking.budget_tokens（1024–32000）；OpenAI 不支持（用 effort）；兼容端点经 extra_body 透传。</div>
      </div>
    </div>
    <div>
      <span class="gateway-section-title">安全边界</span>
      <div class="gw-card"><b>keys_persisted=false</b> · 密钥只进环境变量或 runtime 内存；配置落盘时自动扫描并拒绝 secret 字段；错误信息自动脱敏；本地 runtime 默认只绑 127.0.0.1。</div>
    </div>`;
}

function openGateway() {
  const dialog = $("gateway-dialog");
  if (!dialog) return;
  dialog.hidden = false;
  renderGateway();
  probeGateway(false);
}

function closeGateway() {
  const dialog = $("gateway-dialog");
  if (dialog) dialog.hidden = true;
}

async function probeGateway(announce = true) {
  const note = $("gateway-probe-note");
  const input = $("gateway-runtime-url");
  if (!note || !input) return;
  const base = (input.value || "").trim().replace(/\/$/, "");
  note.textContent = "探测中 · " + base;
  try {
    const response = await fetch(base + "/api/models", { cache: "no-store" });
    if (!response.ok) throw new Error(response.status);
    state.gateway = await response.json();
    state.gatewayLive = true;
    note.textContent = "已连接 · " + base;
  } catch (error) {
    state.gatewayLive = false;
    note.textContent = "未连接 · 使用离线快照（" + error.message + "）";
    if (announce) consoleEcho("runtime 未连接，展示离线快照", true);
  }
  renderGateway();
}

function initGateway() {
  const button = $("gateway-btn");
  if (button) button.addEventListener("click", openGateway);
  const probeButton = $("gateway-probe-btn");
  if (probeButton) probeButton.addEventListener("click", () => probeGateway());
  const dialog = $("gateway-dialog");
  if (dialog) dialog.addEventListener("click", (event) => {
    if (event.target.closest("[data-close-gateway]")) closeGateway();
  });
}

function runPaletteItem(index) {
  const item = state.paletteItems[index];
  if (!item) return;
  closePalette();
  if (item.type === "task") {
    const task = state.tasks.find((entry) => entry.id === item.id.split(":")[1]);
    switchTask(task);
  } else if (item.type === "module") selectModule(item.module, true, "overview");
  else if (item.type === "tab") switchTab(item.id.split(":")[1]);
  else if (item.id === "action:replay") replay();
  else if (item.id === "action:gateway") openGateway();
}

async function loadTask(task) {
  clearTimeout(state.replayTimer);
  state.replayTimer = null;
  const previous = state.taskId;
  state.taskId = task.id;
  state.taskDir = task.dir;
  try {
    setStatus("LOADING · " + (task.topic || task.id).slice(0, 32));
    const demo = await fetchJson(task.dir + "/demo.json");
    const specs = await fetchJson(task.dir + "/specs.json").catch(() => []);
    state.data = demo;
    state.specs = specs;
    state.selected = available().includes("literature") ? "literature" : available()[0];
    try { localStorage.setItem("ra-task", task.id); } catch (storageError) { /* private mode */ }
    renderAll();
    setStatus("TASK · " + (task.topic || task.id));
  } catch (error) {
    if (previous) state.taskId = previous;
    setStatus("TASK LOAD FAILED · " + error.message);
  }
}

function switchTask(task) {
  if (!task || task.id === state.taskId) return;
  loadTask(task);
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(path + " " + response.status);
  return response.json();
}

async function load() {
  try {
    const [demoResponse, specsResponse, modelsResponse, rsiResponse, tasksResponse, innovationsResponse, innovationReportResponse, gatewayResponse] = await Promise.allSettled([
      fetchJson("data/demo.json"),
      fetchJson("data/specs.json"),
      fetchJson("data/models.json"),
      fetchJson("data/rsi.json"),
      fetchJson("data/tasks.json"),
      fetchJson("data/innovations.json"),
      fetchJson("data/innovations-report.json"),
      fetchJson("data/gateway.json")
    ]);
    state.models = modelsResponse.status === "fulfilled" ? (modelsResponse.value.bindings || []) : [];
    state.rsi = rsiResponse.status === "fulfilled" ? rsiResponse.value : null;
    state.tasks = tasksResponse.status === "fulfilled" ? (tasksResponse.value.tasks || []) : [];
    state.innovations = innovationsResponse.status === "fulfilled" ? (innovationsResponse.value.pillars || []) : [];
    state.innovationReport = innovationReportResponse.status === "fulfilled" ? innovationReportResponse.value : null;
    state.gateway = gatewayResponse.status === "fulfilled" ? gatewayResponse.value : null;
    if (state.tasks.length) {
      let remembered = null;
      try { remembered = localStorage.getItem("ra-task"); } catch (storageError) { /* private mode */ }
      const pick = state.tasks.find((task) => task.id === remembered) || state.tasks[0];
      await loadTask(pick);
      return;
    }
    if (demoResponse.status !== "fulfilled") throw demoResponse.reason;
    state.data = demoResponse.value;
    state.specs = specsResponse.status === "fulfilled" ? specsResponse.value : [];
    state.taskDir = "";
    state.taskId = null;
    state.selected = available().includes("literature") ? "literature" : available()[0];
    renderAll();
    setStatus("READY · fixture loaded");
  } catch (error) {
    $("subtitle").textContent = "无法载入 fixture。请从项目根目录运行 python -m research_agent web，而不是直接打开 file://。";
    setStatus("LOAD FAILED · " + error.message);
    $("inspector-body").innerHTML = `<div class="empty">没有数据。运行 <code>python -m research_agent pipeline run --topic "..."</code> 后启动 <code>python -m research_agent web</code>。</div>`;
  }
}

document.addEventListener("click", (event) => {
  const taskButton = event.target.closest("[data-task]");
  if (taskButton) {
    const task = state.tasks.find((entry) => entry.id === taskButton.dataset.task);
    switchTask(task);
  }
  const stage = event.target.closest("[data-module]");
  if (stage) selectModule(stage.dataset.module, true, "overview");
  const tab = event.target.closest("[data-tab]");
  if (tab) switchTab(tab.dataset.tab);
  const paletteItem = event.target.closest("[data-index]");
  if (paletteItem) runPaletteItem(Number(paletteItem.dataset.index));
  if (event.target.closest("[data-close-palette]")) closePalette();
});
document.querySelectorAll(".mode").forEach((button) => button.addEventListener("click", () => switchMode(button.dataset.mode)));
$("replay-btn").addEventListener("click", replay);
$("palette-btn").addEventListener("click", openPalette);
$("palette-input").addEventListener("input", (event) => {
  state.paletteIndex = 0;
  renderPalette(event.target.value);
});
$("palette-input").addEventListener("keydown", (event) => {
  if (event.key === "ArrowDown") {
    event.preventDefault();
    state.paletteIndex = Math.min(state.paletteIndex + 1, state.paletteItems.length - 1);
    renderPalette($("palette-input").value);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    state.paletteIndex = Math.max(0, state.paletteIndex - 1);
    renderPalette($("palette-input").value);
  } else if (event.key === "Enter") {
    event.preventDefault();
    runPaletteItem(state.paletteIndex);
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") { closePalette(); closeGateway(); return; }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    if (!event.target.closest("input")) { event.preventDefault(); openPalette(); }
    return;
  }
  if (event.key === "/" && !event.target.closest("input, textarea, select")) {
    event.preventDefault();
    const input = $("console-input");
    if (input) input.focus();
    return;
  }
  if (event.target.closest("input, textarea, select")) return;
  if (event.key.toLowerCase() === "j" || event.key.toLowerCase() === "k") {
    const ids = available();
    const at = Math.max(0, ids.indexOf(state.selected));
    const next = event.key.toLowerCase() === "j" ? Math.min(ids.length - 1, at + 1) : Math.max(0, at - 1);
    selectModule(ids[next]);
  } else if (event.key.toLowerCase() === "r") {
    replay();
  } else if (/^[1-6]$/.test(event.key)) {
    switchTab(VIEWS[Number(event.key) - 1]);
  }
});

initTheme();
initConsole();
initGateway();
const themeButton = $("theme-btn");
if (themeButton) themeButton.addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
load();

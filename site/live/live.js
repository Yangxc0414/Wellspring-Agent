"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const STAGE_LABELS = {
  literature: ["检索与阅读", "LITERATURE"],
  idea: ["假设收敛", "IDEA"],
  experiment: ["设计冻结", "DESIGN"],
  run: ["复现执行", "RUN"],
  figure: ["科研绘图", "FIGURE"],
  paper: ["写作与槽位", "PAPER"],
  grant: ["基金骨架", "GRANT"],
};
const DEFAULT_STAGES = Object.keys(STAGE_LABELS);
const state = {
  api: "http://127.0.0.1:8787",
  online: false,
  health: null,
  jobId: "",
  job: null,
  lastSeq: 0,
  source: null,
  pollTimer: null,
  finished: false,
  stages: DEFAULT_STAGES.slice(),
};

const refs = {
  api: $("#api-base"),
  connect: $("#connect-btn"),
  chip: $("#conn-chip"),
  healthVersion: $("#health-version"),
  factStatus: $("#fact-status"),
  factQueue: $("#fact-queue"),
  factRsi: $("#fact-rsi"),
  healthAlert: $("#health-alert"),
  form: $("#run-form"),
  runBtn: $("#run-btn"),
  topic: $("#topic"),
  language: $("#language"),
  venue: $("#venue"),
  maxSources: $("#max-sources"),
  grant: $("#grant"),
  runDataset: $("#run-dataset"),
  runSeeds: $("#run-seeds"),
  realCorpus: $("#real-corpus"),
  runTitle: $("#run-title"),
  runSubtitle: $("#run-subtitle"),
  runState: $("#run-state"),
  jobId: $("#job-id"),
  stageRail: $("#stage-rail"),
  eventLog: $("#event-log"),
  eventCount: $("#event-count"),
  resultPanel: $("#result-panel"),
  resultStatus: $("#result-status"),
  resultGrid: $("#result-grid"),
  armNote: $("#arm-note"),
  warningList: $("#warning-list"),
  gateList: $("#gate-list"),
  artifactList: $("#artifact-list"),
  artifactCount: $("#artifact-count"),
  previewName: $("#preview-name"),
  previewBody: $("#preview-body"),
  rsiLedger: $("#rsi-ledger"),
  rsiRefresh: $("#rsi-refresh"),
  rsiTiles: $("#rsi-tiles"),
  confirmList: $("#confirm-list"),
  rsiWarnings: $("#rsi-warnings"),
  traceForm: $("#trace-form"),
  traceScope: $("#trace-scope"),
  traceCapsule: $("#trace-capsule"),
  traceConfirmation: $("#trace-confirmation"),
  traceResult: $("#trace-result"),
};

function apiUrl(path) {
  return state.api.replace(/\/+$/, "") + path;
}

function normalizeApi(value) {
  const trimmed = (value || "").trim().replace(/\/+$/, "");
  return trimmed || "http://127.0.0.1:8787";
}

async function jsonFetch(path, options = {}, timeout = 8000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(apiUrl(path), {
      cache: "no-store",
      ...options,
      signal: controller.signal,
    });
    const text = await response.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      data = {};
    }
    if (!response.ok) {
      throw new Error(data.detail || response.statusText || "HTTP " + response.status);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时；runtime 是否已启动？");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

function setChip(text, status) {
  refs.chip.dataset.state = status;
  refs.chip.innerHTML = "<i></i>";
  refs.chip.appendChild(document.createTextNode(text));
}

function setAlert(text) {
  refs.healthAlert.hidden = !text;
  refs.healthAlert.textContent = text || "";
}

function setRunState(status) {
  const labels = {
    idle: "IDLE",
    queued: "QUEUED",
    running: "RUNNING",
    completed: "COMPLETED",
    failed: "FAILED",
  };
  refs.runState.dataset.state = status;
  refs.runState.textContent = labels[status] || String(status || "IDLE").toUpperCase();
}

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function fmtMetric(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return Math.abs(num) >= 10 ? num.toFixed(2) : num.toFixed(3);
}

function textNode(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  return node;
}

function stageNode(stage, status) {
  const node = document.createElement("div");
  node.className = "stage-node";
  node.dataset.stage = stage;
  node.dataset.state = status || "pending";
  const label = STAGE_LABELS[stage] || [stage, stage.toUpperCase()];
  node.appendChild(textNode("b", "", label[0]));
  node.appendChild(textNode("small", "", label[1]));
  return node;
}

function renderStageRail(stages) {
  state.stages = stages && stages.length ? stages.slice() : DEFAULT_STAGES.slice();
  clearNode(refs.stageRail);
  state.stages.forEach((stage) => refs.stageRail.appendChild(stageNode(stage, "pending")));
}

function setStage(stage, status) {
  const node = refs.stageRail.querySelector('.stage-node[data-stage="' + stage + '"]');
  if (node) node.dataset.state = status;
}

function addEvent(event) {
  if (event.seq && event.seq <= state.lastSeq) return;
  if (event.seq) state.lastSeq = Number(event.seq);
  if (event.type === "run_start" && event.data && Array.isArray(event.data.stages)) {
    renderStageRail(event.data.stages);
  }
  if (event.stage) {
    if (event.type === "stage_start") setStage(event.stage, "running");
    if (event.type === "stage_end") setStage(event.stage, "done");
    if (event.type === "stage_skip") setStage(event.stage, "skipped");
    if (event.type === "error") setStage(event.stage, "error");
  }
  if (event.type === "done" || (event.type === "error" && event.seq && state.jobId)) {
    finishRun();
  }
  if (event.type === "run_complete" && event.data) {
    renderResult(event.data);
  }

  const empty = refs.eventLog.querySelector(".empty-line");
  if (empty) empty.remove();
  const row = document.createElement("div");
  row.className = "ev";
  row.dataset.type = event.type || "info";
  const when = event.ts ? String(event.ts).slice(11, 19) : "--:--:--";
  row.appendChild(textNode("time", "", when));
  row.appendChild(textNode("span", "ev-type", event.type || "info"));
  const message = [event.stage ? "[" + event.stage + "]" : "", event.message || ""]
    .filter(Boolean)
    .join(" ");
  row.appendChild(textNode("span", "ev-msg", message));
  refs.eventLog.appendChild(row);
  while (refs.eventLog.children.length > 600) refs.eventLog.removeChild(refs.eventLog.firstChild);
  const count = refs.eventLog.querySelectorAll(".ev").length;
  refs.eventCount.textContent = count + " events";
  refs.eventLog.scrollTop = refs.eventLog.scrollHeight;
}

function renderHealth(health) {
  refs.healthVersion.textContent = "v" + (health.version || "—");
  refs.factStatus.textContent = "LOCAL OK";
  refs.factQueue.textContent = (health.queue ? health.queue.pending : 0) + " / " + (health.queue ? health.queue.max_pending : "—");
  refs.factRsi.textContent = health.rsi_read_only ? "READ ONLY" : "—";
  const mixed = window.location.protocol === "https:" && state.api.startsWith("http:");
  setAlert(
    mixed
      ? "当前页面是 HTTPS，而 runtime 是 HTTP；浏览器会因 mixed content 拦截请求。请本地打开站点，或把 runtime 放到 HTTPS 后面。"
      : ""
  );
}

function renderOffline(message) {
  refs.healthVersion.textContent = "—";
  refs.factStatus.textContent = "OFFLINE";
  refs.factQueue.textContent = "—";
  refs.factRsi.textContent = "READ ONLY";
  setAlert(
    "未连接到本地 runtime：" + message +
    "。启动：python -m research_agent.runtime；站点：python -m http.server 8000 --directory site"
  );
  setRunState("idle");
  refs.runBtn.disabled = true;
}

async function connect() {
  state.api = normalizeApi(refs.api.value);
  refs.api.value = state.api;
  try { localStorage.setItem("researchAgentRuntime", state.api); } catch (_) {}
  setChip("CHECKING", "checking");
  refs.runBtn.disabled = true;
  try {
    const health = await jsonFetch("/api/health", {}, 5000);
    state.online = true;
    state.health = health;
    setChip("LIVE LOCAL", "ok");
    renderHealth(health);
    refs.runBtn.disabled = false;
    await loadLedgers();
  } catch (error) {
    state.online = false;
    setChip("OFFLINE", "bad");
    renderOffline(error.message);
  }
}

function readPayload() {
  return {
    topic: refs.topic.value.trim(),
    language: refs.language.value,
    venue_type: refs.venue.value,
    grant_scheme: refs.grant.value,
    max_sources: Number(refs.maxSources.value || 6),
    real_corpus: refs.realCorpus.checked,
    run_dataset: refs.runDataset.value,
    run_seeds: Number(refs.runSeeds.value || 3),
    figure_style: "modern",
  };
}

function resetRunUI() {
  if (state.source) state.source.close();
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.source = null;
  state.pollTimer = null;
  state.lastSeq = 0;
  state.finished = false;
  state.job = null;
  state.jobId = "";
  refs.eventCount.textContent = "0 events";
  clearNode(refs.eventLog);
  refs.eventLog.appendChild(textNode("p", "empty-line", "运行已提交，等待真实事件…"));
  renderStageRail(DEFAULT_STAGES);
  refs.resultPanel.hidden = true;
  clearNode(refs.resultGrid);
  if (refs.armNote) {
    refs.armNote.hidden = true;
    refs.armNote.textContent = "";
  }
  clearNode(refs.warningList);
  clearNode(refs.gateList);
  refs.artifactCount.textContent = "0 files";
  clearNode(refs.artifactList);
  refs.artifactList.appendChild(textNode("p", "empty-line", "运行完成后可查看真实产物。"));
  refs.previewName.textContent = "NO FILE";
  clearNode(refs.previewBody);
  refs.previewBody.appendChild(textNode("p", "empty-line", "点击产物文件进行只读预览。"));
}

async function startRun(event) {
  event.preventDefault();
  if (!state.online) {
    setAlert("先连接本地 runtime。");
    return;
  }
  const payload = readPayload();
  if (payload.topic.length < 2) {
    setAlert("研究主题至少 2 个字符。");
    return;
  }
  resetRunUI();
  setRunState("queued");
  refs.runTitle.textContent = payload.topic;
  refs.runSubtitle.textContent = "请求已提交；阶段、事件与产物均来自本地执行。";
  refs.jobId.textContent = "submitting…";
  try {
    const job = await jsonFetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.jobId = job.job_id;
    refs.jobId.textContent = job.job_id;
    connectStream(job.job_id);
  } catch (error) {
    setRunState("failed");
    addEvent({ seq: 0, ts: new Date().toISOString(), type: "error", stage: null, message: error.message });
  }
}

function connectStream(jobId) {
  if (state.source) state.source.close();
  let source;
  try {
    source = new EventSource(apiUrl("/api/runs/" + encodeURIComponent(jobId) + "/events/stream?after=0"));
  } catch (_) {
    startPolling(jobId);
    return;
  }
  state.source = source;
  source.onmessage = (message) => {
    try {
      addEvent(JSON.parse(message.data));
    } catch (_) {}
  };
  source.onerror = () => {
    if (state.jobId !== jobId || state.finished) return;
    source.close();
    state.source = null;
    startPolling(jobId);
  };
}

function startPolling(jobId) {
  if (state.pollTimer) return;
  addEvent({ seq: 0, ts: new Date().toISOString(), type: "info", stage: null, message: "SSE unavailable; falling back to polling" });
  state.pollTimer = setInterval(async () => {
    if (state.jobId !== jobId || state.finished) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      return;
    }
    try {
      const data = await jsonFetch("/api/runs/" + encodeURIComponent(jobId) + "/events?after=" + state.lastSeq);
      (data.events || []).forEach(addEvent);
      const job = await jsonFetch("/api/runs/" + encodeURIComponent(jobId));
      setRunState(job.status);
      if (["completed", "failed"].includes(job.status) && !state.finished) {
        finishRun(job);
      }
    } catch (error) {
      addEvent({ seq: 0, ts: new Date().toISOString(), type: "error", stage: null, message: error.message });
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }, 700);
}

async function finishRun(knownJob) {
  if (state.finished) return;
  state.finished = true;
  if (state.source) state.source.close();
  state.source = null;
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
  try {
    const job = knownJob || await jsonFetch("/api/runs/" + encodeURIComponent(state.jobId));
    state.job = job;
    setRunState(job.status);
    if (job.error) {
      addEvent({ seq: 0, ts: new Date().toISOString(), type: "error", stage: null, message: job.error });
    }
    if (job.result) {
      renderResult(job.result);
      const demoPath = job.result.artifacts && job.result.artifacts.demo;
      if (demoPath) {
        try {
          const detail = await fetch(artifactUrl(job.job_id, demoPath), { cache: "no-store" });
          if (detail.ok) renderResult(job.result, await detail.json());
        } catch (_) {
          // Summary fields remain visible; the detail fetch only enriches arm provenance.
        }
      }
    }
    await loadArtifacts(job.job_id);
  } catch (error) {
    addEvent({ seq: 0, ts: new Date().toISOString(), type: "error", stage: null, message: error.message });
  }
}

function renderResult(result, detail) {
  refs.resultPanel.hidden = false;
  refs.resultStatus.textContent = String(result.status || "—").toUpperCase();
  clearNode(refs.resultGrid);
  const modules = detail?.modules || result.modules || {};
  const lit = modules.literature && typeof modules.literature === "object" ? modules.literature : {};
  const run = modules.run && typeof modules.run === "object" ? modules.run : null;
  const coverage = lit.coverage || {};
  const sourceScope = coverage.source_scope || [];
  const s1Mode = sourceScope.includes("real") ? "REAL TEXT" : "FIXTURE";
  const runMode = run ? (run.evidence?.source === "run" ? "REAL LOCAL RUN" : "REUSED RECORD") : "NOT RUN";
  const mixed = Boolean(result.fixture_mode && run && run.evidence?.source === "run");
  const claims = (modules.paper?.claims || []).length;
  const facts = [
    ["RUN ID", result.run_id || "—"],
    ["MODE", mixed ? "MIXED ARMS" : (result.fixture_mode ? "FIXTURE" : "REAL TEXT")],
    ["STATUS", result.status || "—"],
    ["S1 ARM", `${s1Mode} · ${coverage.sources_found ?? 0} hit / ${coverage.spans_extracted ?? 0} span`],
    ["S5 ARM", run ? `${runMode} · ${run.capsule?.metric_name || "metric"} ${fmtMetric(run.capsule?.mean)}` : "NOT RUN"],
    ["CLAIM", claims ? `${claims} bound` : run?.claim_draft ? "draft unsigned" : "none"],
    ["MODULES", result.modules ? Object.keys(result.modules).length : "—"],
    ["WARNINGS", result.warnings ? result.warnings.length : 0],
  ];
  facts.forEach(([key, value]) => {
    const cell = document.createElement("div");
    cell.appendChild(textNode("dt", "", key));
    cell.appendChild(textNode("dd", "", String(value)));
    refs.resultGrid.appendChild(cell);
  });
  if (refs.armNote) {
    refs.armNote.hidden = !mixed;
    refs.armNote.textContent = mixed
      ? "MIXED ARMS：S1 的 hit/span 与 S5 的指标来自不同证据臂；不要把它们读成同一次研究结果。S5 的 EA 只覆盖本地协议 run，claim 未签前结果槽保持 pending。"
      : "";
  }
  clearNode(refs.warningList);
  (result.warnings || []).slice(0, 20).forEach((warning) => {
    refs.warningList.appendChild(textNode("p", "", warning));
  });
  clearNode(refs.gateList);
  (result.gates || []).forEach((gate) => {
    const chip = document.createElement("span");
    chip.dataset.status = gate.status || "";
    chip.textContent = gate.gate + " · " + gate.status;
    chip.title = gate.reason || "";
    refs.gateList.appendChild(chip);
  });
}

function artifactUrl(jobId, path) {
  return apiUrl(
    "/api/runs/" + encodeURIComponent(jobId) + "/artifacts/" +
    path.split("/").map(encodeURIComponent).join("/")
  );
}

async function loadArtifacts(jobId) {
  try {
    const data = await jsonFetch("/api/runs/" + encodeURIComponent(jobId) + "/artifacts");
    const items = data.artifacts || [];
    refs.artifactCount.textContent = items.length + " files";
    clearNode(refs.artifactList);
    if (!items.length) {
      refs.artifactList.appendChild(textNode("p", "empty-line", "没有产物。"));
      return;
    }
    items.forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "artifact-item";
      button.appendChild(textNode("span", "", item.path));
      button.appendChild(textNode("span", "", item.kind + " · " + item.size + " B"));
      button.addEventListener("click", () => previewArtifact(jobId, item));
      refs.artifactList.appendChild(button);
    });
    const preferred = items.find((item) => item.path === "demo.json") || items.find((item) => item.kind === "figure") || items[0];
    if (preferred) previewArtifact(jobId, preferred);
  } catch (error) {
    refs.artifactList.appendChild(textNode("p", "empty-line", error.message));
  }
}

async function previewArtifact(jobId, item) {
  refs.previewName.textContent = item.path.toUpperCase();
  clearNode(refs.previewBody);
  const url = artifactUrl(jobId, item.path);
  const download = document.createElement("a");
  download.href = url;
  download.target = "_blank";
  download.rel = "noopener";
  download.textContent = "在新标签打开 ↗";
  if (item.path.endsWith(".svg")) {
    const image = document.createElement("img");
    image.alt = item.path;
    image.src = url;
    refs.previewBody.appendChild(image);
    refs.previewBody.appendChild(download);
    return;
  }
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error("HTTP " + response.status);
    const text = await response.text();
    let rendered = text;
    if (item.path.endsWith(".json")) {
      try { rendered = JSON.stringify(JSON.parse(text), null, 2); } catch (_) {}
    }
    const pre = textNode("pre", "", rendered.slice(0, 30000));
    refs.previewBody.appendChild(pre);
    refs.previewBody.appendChild(download);
  } catch (error) {
    refs.previewBody.appendChild(textNode("p", "empty-line", error.message));
  }
}

function option(value, label) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

async function loadLedgers() {
  try {
    const data = await jsonFetch("/api/rsi/ledgers");
    const ledgers = data.ledgers || [];
    clearNode(refs.rsiLedger);
    if (!ledgers.length) {
      refs.rsiLedger.appendChild(option("", "没有可用账本"));
      return;
    }
    ledgers.forEach((item) => {
      refs.rsiLedger.appendChild(option(item.path, item.path + " · " + item.episodes + " ep"));
    });
    const preferred = (state.health && state.health.default_rsi_ledger) || ledgers[0].path;
    const match = ledgers.find((item) => item.path === preferred) || ledgers[0];
    refs.rsiLedger.value = match.path;
    await loadRsiStatus(match.path);
  } catch (error) {
    clearNode(refs.rsiLedger);
    refs.rsiLedger.appendChild(option("", error.message));
  }
}

async function loadRsiStatus(path) {
  if (!path) return;
  try {
    const status = await jsonFetch("/api/rsi/status?ledger=" + encodeURIComponent(path));
    const confirmations = status.confirmations || {};
    const tiles = refs.rsiTiles.querySelectorAll("b");
    tiles[0].textContent = status.episodes ?? "—";
    tiles[1].textContent = status.active_leases ?? "—";
    tiles[2].textContent = confirmations.confirmed ?? "—";
    tiles[3].textContent = (status.capability_claims || []).length;
    clearNode(refs.confirmList);
    (confirmations.records || []).slice(-4).forEach((record) => {
      const row = document.createElement("div");
      row.appendChild(textNode("b", "", record.status));
      const delta = record.delta || {};
      const bits = [record.split, delta.cost !== undefined ? "Δcost " + delta.cost : "", record.passed ? "passed" : ""].filter(Boolean);
      row.appendChild(textNode("span", "", bits.join(" · ")));
      refs.confirmList.appendChild(row);
    });
    clearNode(refs.rsiWarnings);
    (status.warnings || []).slice(0, 6).forEach((warning) => {
      refs.rsiWarnings.appendChild(textNode("p", "", warning));
    });
    if (path.indexOf("rsi-chemlab-v2") >= 0) {
      const base = path.replace(/ledger\.json$/, "");
      refs.traceCapsule.value = base + "leased-run/run-capsule.json";
      refs.traceConfirmation.value = base + "confirm/s5-confirmation.json";
    }
  } catch (error) {
    refs.rsiTiles.querySelectorAll("b").forEach((node) => { node.textContent = "—"; });
    clearNode(refs.confirmList);
    clearNode(refs.rsiWarnings);
    refs.rsiWarnings.appendChild(textNode("p", "", error.message));
  }
}

async function runTrace(event) {
  event.preventDefault();
  const ledger = refs.rsiLedger.value;
  const scope = refs.traceScope.value.trim();
  const capsule = refs.traceCapsule.value.trim();
  const confirmation = refs.traceConfirmation.value.trim();
  if (!ledger || !scope || !capsule) {
    refs.traceResult.textContent = "ledger / scope / capsule 都是必填。";
    return;
  }
  const params = new URLSearchParams({ ledger, scope, capsule });
  if (confirmation) params.set("confirmation", confirmation);
  try {
    const result = await jsonFetch("/api/rsi/trace?" + params.toString());
    clearNode(refs.traceResult);
    const head = document.createElement("div");
    head.appendChild(textNode("b", "", result.status || (result.ok ? "traceable" : "incomplete")));
    head.appendChild(document.createTextNode(" · " + (result.run ? result.run.run_id : "no run")));
    refs.traceResult.appendChild(head);
    const checks = document.createElement("div");
    checks.className = "trace-checks";
    Object.entries(result.checks || {}).forEach(([key, ok]) => {
      const chip = document.createElement("span");
      chip.dataset.ok = ok ? "true" : "false";
      chip.textContent = key;
      checks.appendChild(chip);
    });
    refs.traceResult.appendChild(checks);
    (result.warnings || []).forEach((warning) => {
      refs.traceResult.appendChild(textNode("p", "empty-line", warning));
    });
  } catch (error) {
    refs.traceResult.textContent = error.message;
  }
}

function applyPreset(name) {
  if (name === "en") {
    refs.topic.value = "How do self-improving coding agents use archives?";
    refs.language.value = "en";
    refs.venue.value = "en_conference";
    refs.realCorpus.checked = true;
    refs.maxSources.value = "3";
    refs.runDataset.value = "";
  } else {
    refs.topic.value = "钙钛矿太阳能电池的界面钝化与长期稳定性";
    refs.language.value = "zh";
    refs.venue.value = "zh_core_journal";
    refs.realCorpus.checked = false;
    refs.maxSources.value = "4";
    refs.runDataset.value = "";
  }
}

function init() {
  let saved = "";
  try { saved = localStorage.getItem("researchAgentRuntime") || ""; } catch (_) {}
  state.api = normalizeApi(saved || refs.api.value);
  refs.api.value = state.api;
  refs.connect.addEventListener("click", connect);
  refs.form.addEventListener("submit", startRun);
  refs.rsiRefresh.addEventListener("click", () => loadLedgers());
  refs.rsiLedger.addEventListener("change", () => loadRsiStatus(refs.rsiLedger.value));
  refs.traceForm.addEventListener("submit", runTrace);
  document.querySelectorAll("[data-preset]").forEach((button) => {
    button.addEventListener("click", () => applyPreset(button.dataset.preset));
  });
  renderStageRail(DEFAULT_STAGES);
  connect();
}

init();

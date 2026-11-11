"use strict";

const STORAGE_KEY = "researchAgent.workspace.v1";
const STATE_VERSION = 6;
const AUTO_MS = 900;
const APP_VERSION = "0.1.0";
const BUILD_DATE = "2026-10-24";
const DEFAULT_PREFERENCES = { autoExpandRunning: true, autoScroll: true, reduceMotion: false };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const MODE_META = {
  research: { label: "调研模式", kicker: "RESEARCH / S1–S3", hint: "先证据后假设", placeholder: "问一个研究问题，或让我扩展检索……" },
  experiment: { label: "实验模式", kicker: "EXPERIMENT / S4–S5", hint: "先冻结协议，再运行", placeholder: "描述要验证的假设，或输入 /run 运行协议……" },
  auto: { label: "全自动模式", kicker: "GOVERNED AUTO / S1–META", hint: "跑到人工门再决定", placeholder: "输入 /start 启动，或 /pause /step 控制……" }
};
const STAGES = [
  ["S1", "文献检索", "retrieval.query"],
  ["S2–S3", "假设收敛", "idea.frame"],
  ["S4", "设计冻结", "design.freeze"],
  ["S5", "复现执行", "run.work"],
  ["S5b", "证据判定", "judge.verify"],
  ["S6", "结果图", "figure.render"],
  ["S8–S12", "写作槽位", "paper.bind"],
  ["S13–S16", "闭包检查", "closure.check"],
  ["META", "自进化提案", "rsi.propose"]
];
const AUTO_STAGES = [
  { name: "S1 文献检索", cmd: "retrieval.query", output: "3 sources / 12 spans · 1 abstract-only gap", stage: 0 },
  { name: "S2–S3 假设收敛", cmd: "idea.frame", output: "2 candidates · G1 signed (SIM)", stage: 1 },
  { name: "S4 设计冻结", cmd: "design.freeze", output: "G2 ready · protocol frozen", stage: 2 },
  { name: "S5a 复现执行", cmd: "run.work", output: "RUN-014 · 3 seeds · R² 0.164 vs baseline −0.048", stage: 3 },
  { name: "S5b 证据判定", cmd: "judge.verify", output: "EA sealed · claim 未签", stage: 4, gate: "claim" },
  { name: "S6 结果图", cmd: "figure.render", output: "SVG + manifest · bound to EA", stage: 5 },
  { name: "S8–S12 写作槽位", cmd: "paper.bind", output: "result.primary pending_evidence", stage: 6 },
  { name: "S13–S16 闭包检查", cmd: "closure.check", output: "9/11 · citation.related pending", stage: 7 },
  { name: "META 自进化提案", cmd: "rsi.propose", output: "candidate · S1 budget 6 → 3", stage: 8 }
];
const SUGGESTIONS = {
  research: ["扩展检索", "把 gap 变成假设", "查看证据链"],
  experiment: ["冻结协议", "运行 2 seeds", "查看 EA"],
  auto: ["启动全自动", "单步", "暂停"]
};
const MODEL_PROFILES = [
  {
    id: "gpt-5",
    name: "GPT-5 · reasoning",
    short: "GPT-5",
    provider: "OpenAI",
    contextWindow: 400000,
    maxOutput: 16384,
    kind: "effort",
    defaultStop: "medium",
    stops: [
      { value: "minimal", label: "minimal", detail: "reasoning_effort=minimal" },
      { value: "low", label: "low", detail: "reasoning_effort=low" },
      { value: "medium", label: "medium", detail: "reasoning_effort=medium" },
      { value: "high", label: "high", detail: "reasoning_effort=high" }
    ],
    note: "示例能力：上下文 400k / 输出 16k；思考档位来自模型配置，不是所有 OpenAI 模型都支持。"
  },
  {
    id: "claude-sonnet",
    name: "Claude Sonnet · extended thinking",
    short: "Claude",
    provider: "Anthropic",
    contextWindow: 200000,
    maxOutput: 16384,
    kind: "budget",
    defaultStop: 4096,
    stops: [
      { value: 1024, label: "1k", detail: "thinking.budget_tokens=1024" },
      { value: 2048, label: "2k", detail: "thinking.budget_tokens=2048" },
      { value: 4096, label: "4k", detail: "thinking.budget_tokens=4096" },
      { value: 8192, label: "8k", detail: "thinking.budget_tokens=8192" },
      { value: 16384, label: "16k", detail: "thinking.budget_tokens=16384" }
    ],
    note: "示例能力：上下文 200k / 输出 16k；思考档位是 budget token，不是文本长度。"
  },
  {
    id: "qwen-local",
    name: "Qwen 2.5 · local",
    short: "Qwen",
    provider: "Local / frozen",
    contextWindow: 32768,
    maxOutput: 2048,
    kind: "unsupported",
    defaultStop: null,
    stops: [],
    note: "示例能力：本地冻结模型；未声明可调思考强度，滑块不可用。"
  }
];

const PLUGIN_PRESETS = {
  github: {
    name: "GitHub MCP",
    transport: "streamable-http",
    url: "https://api.githubcopilot.com/mcp/",
    auth: "oauth",
    readonly: true,
    toolsets: "repos,issues,pull_requests",
    note: "官方远程 MCP；Streamable HTTP + OAuth；只读优先。静态预览不会真实连接。"
  },
  custom: {
    name: "Custom MCP",
    transport: "streamable-http",
    url: "",
    auth: "env",
    readonly: true,
    toolsets: "tools",
    note: "自定义 Streamable HTTP MCP；token 只从 runtime 环境读取。"
  },
  local: {
    name: "Local MCP (registered only)",
    transport: "stdio",
    url: "",
    auth: "none",
    readonly: true,
    toolsets: "tools",
    note: "仅登记配置，不执行本地命令；避免浏览器触发任意进程。"
  }
};

const WORKSPACES = [
  { id: "materials", name: "材料实验室", note: "钙钛矿 / 稳定性" },
  { id: "agent", name: "Agent 研究", note: "自改进 / archive" },
  { id: "thesis", name: "毕业设计", note: "写作 / 证据" }
];

function seedGithubPlugin() {
  return {
    id: "github",
    name: "GitHub MCP",
    preset: "github",
    transport: "streamable-http",
    url: "https://api.githubcopilot.com/mcp/",
    auth: "oauth",
    readonly: true,
    toolsets: ["repos", "issues", "pull_requests"],
    status: "ready",
    note: "SIM · 未真实连接；OAuth/token 由 runtime 保管",
    installedAt: "2026-10-24"
  };
}

function defaultModelState() {
  return {
    profileId: "gpt-5",
    contextLimit: 128000,
    maxReply: 8192,
    thinkingStop: "medium",
    compression: "auto",
    threshold: 0.7,
    keepRecent: 6,
    summaryTokens: 512
  };
}

function modelProfile(project) {
  const settings = project.model || defaultModelState();
  return MODEL_PROFILES.find((profile) => profile.id === settings.profileId) || MODEL_PROFILES[0];
}

function modelSettings(project) {
  if (!project.model) project.model = defaultModelState();
  return project.model;
}

function formatTokens(value) {
  const number = Number(value || 0);
  if (number >= 1000000) return (number / 1000000).toFixed(number % 1000000 ? 1 : 0) + "m";
  if (number >= 1000) return Math.round(number / 1000) + "k";
  return String(number);
}

function thinkingStop(project) {
  const profile = modelProfile(project);
  if (profile.kind === "unsupported") return null;
  const settings = modelSettings(project);
  return profile.stops.find((stop) => String(stop.value) === String(settings.thinkingStop)) || profile.stops[0];
}

function thinkingLabel(project) {
  const stop = thinkingStop(project);
  return stop ? stop.label : "off";
}

let state = null;
let activeContext = "run";
let autoTimer = null;
let modelDraft = null;
let uidCounter = 0;
let paletteItems = [];
let paletteIndex = 0;

function uid(prefix = "id") {
  uidCounter += 1;
  return prefix + "-" + String(Date.now()).slice(-6) + String(uidCounter).padStart(2, "0");
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function now() {
  return new Date().toISOString().slice(11, 19);
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (_) { /* private mode */ }
}

function currentProject() {
  return state.projects.find((project) => project.id === state.selectedProjectId) || state.projects[0];
}

function card(type, data, actions = []) {
  return { type, data, actions };
}

function message(role, text, cardData = null, extra = {}) {
  return { id: uid("msg"), role, at: now(), text, card: cardData, ...extra };
}

function system(text) {
  return message("system", text);
}

function agent(text, cardData = null) {
  return message("agent", text, cardData);
}

function user(text) {
  return message("user", text);
}

function defaultGates() {
  return [
    { id: "Q0", status: "pending", reason: "coverage / claim admission 未运行" },
    { id: "G1", status: "needs_human", reason: "候选假设需要人工收敛" },
    { id: "G2", status: "not_started", reason: "设计 + 协议尚未冻结" },
    { id: "S5", status: "not_started", reason: "尚未执行 run" },
    { id: "G5", status: "blocked", reason: "没有 EA / Claim / Closure" }
  ];
}

function planCard() {
  return card("plan", {
    queries: ["界面钝化 湿热稳定性", "perovskite passivation damp heat", "passivation layer defect density"],
    scope: "2020–2026 · 中英双语 · 只读公开摘要/全文",
    budget: "6 sources · span-only",
    note: "摘要-only 只作 SourceHit；没有全文不生成 span，也不进入 claim。"
  }, [
    { label: "开始检索", action: "run-research" },
    { label: "调整问题", action: "focus-composer", quiet: true }
  ]);
}

function sourcesCard() {
  return card("sources", {
    items: [
      { title: "Huang et al. · 2024 · Joule", meta: "full text · 6 spans", status: "ok" },
      { title: "Wang et al. · 2023 · ACS Energy Lett.", meta: "full text · 4 spans", status: "ok" },
      { title: "Chen et al. · 2025 · Adv. Mater.", meta: "full text · 2 spans", status: "ok" },
      { title: "Liu et al. · 2022 · Sol. RRL", meta: "abstract only · 0 span", status: "warn" }
    ],
    note: "12 个可定位 span；1 条摘要-only 来源只能作为线索。"
  }, [
    { label: "查看 gap", action: "show-evidence" },
    { label: "扩展检索", action: "run-research", quiet: true }
  ]);
}

function ideaCard() {
  return card("idea", {
    gap: "湿热循环后的定量对照缺失：现有来源只报告初始 PCE 与 T80，没有钝化层/未钝化层的配对比较。",
    candidates: [
      { id: "H1", text: "双分子钝化层降低界面缺陷密度，从而延长湿热条件下的 T80。" },
      { id: "H2", text: "钝化层的疏水性（而非缺陷密度）是湿热稳定性的主因。" }
    ],
    note: "候选不是 claim；需要 G1 人工收敛，再进入 S4 设计。"
  }, [
    { label: "送入实验设计", action: "design-experiment" },
    { label: "先看证据链", action: "show-evidence", quiet: true }
  ]);
}

function protocolCard() {
  return card("protocol", {
    hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
    baseline: "未钝化对照",
    metric: "T80（小时）· 初始 PCE",
    seeds: 3,
    controls: ["未钝化", "单分子钝化"],
    status: "G2 needs_human"
  }, [
    { label: "冻结协议", action: "freeze-protocol" },
    { label: "运行 3 seeds", action: "run-experiment" },
    { label: "查看证据链", action: "show-evidence", quiet: true }
  ]);
}

function runCard(run = {}) {
  return card("run", {
    id: run.id || "RUN-014",
    dataset: run.dataset || "perovskite / 本地 fixture",
    seeds: run.seeds || 3,
    metric: run.metric || "T80 (h)",
    mean: run.mean || 412,
    baseline: run.baseline || 286,
    status: run.status || "EA sealed · claim unsigned",
    ea: run.ea || "EA-7c41"
  }, [
    { label: "查看 EA", action: "show-evidence" },
    { label: "签 claim（需人工）", action: "sign-claim-gate", quiet: true }
  ]);
}

function gateCard(gate = "claim", extra = {}) {
  const isClaim = gate === "claim";
  return card("gate", {
    gate: isClaim ? "S5 · CLAIM" : gate,
    title: isClaim ? "人工门：claim 尚未签署" : "人工门",
    reason: isClaim
      ? "EA 已封存，但 claim 必须由作者/PI 签核；系统不会自动生成结论。"
      : "该门需要人工判断。",
    status: "needs_human"
  }, [
    { label: isClaim ? "模拟签核" : "处理人工门", action: isClaim ? "sign-gate" : "show-run" },
    { label: "保持 pending", action: "dismiss-gate", quiet: true }
  ]);
}

function autoStartCard() {
  return card("auto-start", {
    title: "受治理全自动",
    note: "系统会连续执行 S1→S5→S6→S8→S13，并在 claim 人工门暂停；不会自动签署，也不会绕过 gate。"
  }, [
    { label: "启动全自动", action: "start-auto" },
    { label: "先看运行上下文", action: "show-run", quiet: true }
  ]);
}

function evolutionCard(project) {
  const candidate = project.evolution.candidate;
  if (!candidate) return null;
  const status = candidate.status || "pending";
  const actions = status === "pending"
    ? [
        { label: "批准候选", action: "approve-candidate" },
        { label: "拒绝并保留负结果", action: "reject-candidate", quiet: true }
      ]
    : status === "active"
      ? [{ label: "撤销租约", action: "rollback-harness", quiet: true }]
      : [];
  return card("evolution", {
    id: candidate.id,
    target: candidate.target,
    patch: candidate.patch,
    rationale: candidate.rationale,
    predicted: candidate.predicted,
    ev: candidate.ev,
    lease: candidate.lease,
    status
  }, actions);
}

function seedProject() {
  return {
    id: "perovskite",
    name: "钙钛矿界面钝化",
    goal: "验证界面钝化对湿热稳定性的影响，并留下可追溯的证据链。",
    domain: "材料科学",
    mode: "research",
    status: "active",
    createdAt: "2026-10-24",
    updatedAt: "2026-10-24T08:32:00",
    workspaceId: "materials",
    stage: 1,
    completedStages: [0],
    skippedStages: [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelState(),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 12, total: 40 },
    gates: [
      { id: "Q0", status: "pass", reason: "12 spans / 2 gaps recorded" },
      { id: "G1", status: "needs_human", reason: "2 个候选假设等待收敛" },
      { id: "G2", status: "not_started", reason: "尚未冻结设计" },
      { id: "S5", status: "not_started", reason: "尚未执行 run" },
      { id: "G5", status: "blocked", reason: "没有 Claim / Closure" }
    ],
    evidence: [
      { id: "GAP-001", type: "gap", status: "open", text: "湿热循环后的配对定量对照缺失。", scope: "S1/perovskite", refs: ["SPAN-021"], note: "4 篇来源中只有 2 篇报告 T80。" },
      { id: "CAND-H1", type: "hypothesis", status: "candidate", text: "双分子钝化层降低界面缺陷密度 → 延长 T80。", scope: "S2/perovskite", refs: ["SPAN-014", "SPAN-021"] },
      { id: "CAND-H2", type: "hypothesis", status: "candidate", text: "疏水性而非缺陷密度是湿热稳定性的主因。", scope: "S2/perovskite", refs: ["SPAN-009"] }
    ],
    protocol: null,
    protocolFrozen: false,
    run: null,
    evolution: { status: "idle", candidate: null, lease: null, history: [] },
    auto: { running: false, paused: false, index: 0, gate: "", cycle: 0, gateApproved: false },
    done: { research: true, experiment: false, auto: false },
    intro: {},
    messages: [
      system("STATIC WORKSPACE · 示例状态；不调用模型、不执行真实实验、不产生真实 claim。"),
      agent("项目已接入。我会先把问题拆成可检索的子问题，再决定是否值得进入实验。", planCard()),
      user("先调研界面钝化与长期稳定性的证据，重点看湿热稳定性。"),
      agent("检索完成。3 条来源有全文，1 条只有摘要；12 个可定位 span，2 个 coverage gap。", sourcesCard()),
      agent("最重要的 gap 是：缺少湿热循环后的配对定量对照。它足以支撑一个可否证的假设，但还不足以支撑 claim。", ideaCard())
    ]
  };
}

function seedArchives() {
  return {
    id: "archives",
    name: "自改进 agent 的 archive 使用",
    goal: "理解自改进 coding agent 如何选择、保留与复用 archive 中的历史版本。",
    domain: "机器学习",
    mode: "research",
    status: "active",
    createdAt: "2026-10-24",
    updatedAt: "2026-10-24T08:20:00",
    workspaceId: "agent",
    stage: 0,
    completedStages: [],
    skippedStages: [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelState(),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 4, total: 30 },
    gates: defaultGates(),
    evidence: [],
    protocol: null,
    protocolFrozen: false,
    run: null,
    evolution: { status: "idle", candidate: null, lease: null, history: [] },
    auto: { running: false, paused: false, index: 0, gate: "", cycle: 0, gateApproved: false },
    done: { research: false, experiment: false, auto: false },
    intro: {},
    messages: [
      system("STATIC WORKSPACE · 示例状态；不调用模型、不执行真实实验。"),
      user("自改进 agent 到底怎么使用 archive？我想先做一轮文献调研。"),
      agent("可以。我会先区分三种“archive”：代码版本 archive、轨迹/反思 archive、评测结果 archive；再判断哪些机制有可核验证据。", card("plan", {
        queries: ["self-improving agent archive", "Darwin Gödel Machine stepping stones", "agent memory reuse lineage"],
        scope: "2024–2026 · arXiv / 会议",
        budget: "6 sources · span-only",
        note: "先宽后深；摘要-only 来源不生成 span。"
      }, [
        { label: "开始检索", action: "run-research" },
        { label: "切换研究问题", action: "focus-composer", quiet: true }
      ]))
    ]
  };
}

function createProject({ name, goal, domain, mode, workspaceId }) {
  const project = {
    id: uid("project"),
    name: name.trim(),
    goal: goal.trim(),
    domain: domain || "其他",
    mode: mode || "research",
    status: "active",
    createdAt: new Date().toISOString().slice(0, 10),
    updatedAt: new Date().toISOString().slice(0, 16),
    workspaceId: workspaceId || state.activeWorkspaceId || "materials",
    stage: mode === "experiment" ? 2 : 0,
    completedStages: [],
    skippedStages: mode === "experiment" ? [0, 1] : [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelState(),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 0, total: 30 },
    gates: defaultGates(),
    evidence: [],
    protocol: null,
    protocolFrozen: false,
    run: null,
    evolution: { status: "idle", candidate: null, lease: null, history: [] },
    auto: { running: false, paused: false, index: 0, gate: "", cycle: 0, gateApproved: false },
    done: { research: false, experiment: false, auto: false },
    intro: {},
    messages: [
      system("STATIC WORKSPACE · 新项目；示例状态，不调用模型、不执行真实实验。"),
      agent(`项目已创建：${name.trim()}。我会先明确问题边界，再选择调研、实验或受治理全自动。`)
    ]
  };
  if (mode === "research") {
    project.messages.push(agent("先给你一个检索计划；确认后再进入 span 与 gap。", planCard()));
  } else if (mode === "experiment") {
    project.protocol = {
      hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
      baseline: "未钝化对照",
      metric: "T80（小时）· 初始 PCE",
      seeds: 3
    };
    project.messages.push(agent("先登记一个可冻结的协议。S1/S2 尚未运行，G1 仍需人工收敛；结果槽会保持 pending，直到 EA 与人签 claim。", protocolCard()));
    project.gates[2] = { id: "G2", status: "needs_human", reason: "协议等待人工冻结" };
  } else {
    project.messages.push(agent("全自动会跑到人工门。你可以随时暂停、单步或停止。", autoStartCard()));
  }
  return project;
}

function seedThesisProject(id, name, goal, updatedAt) {
  const project = seedArchives();
  project.id = id;
  project.name = name;
  project.goal = goal;
  project.domain = "写作 / 证据";
  project.workspaceId = "thesis";
  project.updatedAt = updatedAt;
  project.stage = 0;
  project.messages = [
    system("STATIC WORKSPACE · 示例任务；不调用模型、不执行真实实验。"),
    agent(`任务已创建：${name}。这是一个毕业设计工作区里的静态示例；可以从调研开始，也可以直接设计实验。`),
    agent("先明确证据边界，再决定是否进入实验。", card("plan", {
      queries: ["证据闭合 writing agent", "claim span provenance", "中文核刊 结构"],
      scope: "2022–2026 · 中文/英文",
      budget: "4 sources · span-only",
      note: "摘要-only 只作线索；没有全文不生成 span。"
    }, [{ label: "开始检索", action: "run-research" }]))
  ];
  return project;
}

function seedState() {
  return {
    version: STATE_VERSION,
    selectedProjectId: "perovskite",
    activeWorkspaceId: "materials",
    preferences: { ...DEFAULT_PREFERENCES },
    ui: { groups: { running: false, recent: true } },
    plugins: [seedGithubPlugin()],
    projects: [seedProject(), seedArchives(),
      seedThesisProject("evidence-writing", "证据驱动科研写作系统", "把 claim 与 span 的绑定做成可审计的写作工作流。", "2026-10-23T16:40:00"),
      seedThesisProject("proposal-review", "项目命题设计与反思", "收敛毕设命题、边界与验证顺序。", "2026-10-23T15:20:00")]
  };
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return seedState();
    const parsed = JSON.parse(raw);
    if (parsed.version !== STATE_VERSION || !Array.isArray(parsed.projects) || !parsed.projects.length) return seedState();
    parsed.preferences = { ...DEFAULT_PREFERENCES, ...(parsed.preferences || {}) };
    parsed.ui = { groups: { running: false, recent: true }, ...(parsed.ui || {}) };
    parsed.ui.groups = { running: false, recent: true, ...(parsed.ui.groups || {}) };
    if (!Array.isArray(parsed.plugins)) parsed.plugins = [seedGithubPlugin()];
    if (!parsed.activeWorkspaceId) parsed.activeWorkspaceId = "materials";
    parsed.projects.forEach((project) => {
      if (!project.workspaceId) project.workspaceId = "materials";
      if (!project.updatedAt) project.updatedAt = project.createdAt || "2026-10-24";
    });
    return parsed;
  } catch (_) {
    return seedState();
  }
}

function saveAndRender() {
  save();
  renderAll();
}

/* ---------- rendering ---------- */

function renderAll() {
  const project = currentProject();
  if (!project) return;
  renderProjectSelect();
  renderProjects();
  renderHeader();
  renderThread();
  renderWorkspaces();
  renderContext();
  renderSuggestions();
  renderComposerMode();
  renderModelChip();
  renderPluginChip();
  applyPreferences();
  syncVersion();
}

function renderProjectSelect() {
  const select = $("#project-select");
  select.innerHTML = state.projects.map((project) =>
    `<option value="${esc(project.id)}" ${project.id === state.selectedProjectId ? "selected" : ""}>${esc(project.name)}</option>`
  ).join("");
}

function renderWorkspaces() {
  const host = $("#workspace-list");
  host.innerHTML = WORKSPACES.map((workspace) => {
    const tasks = state.projects.filter((project) => project.workspaceId === workspace.id)
      .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")));
    const active = workspace.id === state.activeWorkspaceId;
    const taskRows = tasks.map((project) => `
      <button type="button" class="ag-workspace-task ${project.id === state.selectedProjectId ? "is-on" : ""}" data-workspace-task="${esc(project.id)}">
        <span class="ag-project-dot" aria-hidden="true"></span><span>${esc(project.name)}</span>
      </button>`).join("") || '<div class="ag-workspace-empty">还没有任务</div>';
    return `<details class="ag-workspace-group ${active ? "is-on" : ""}" data-workspace-group="${esc(workspace.id)}" open>
      <summary>
        <span class="ag-folder-icon" aria-hidden="true"><svg viewBox="0 0 16 16" fill="none"><path d="M1.7 3.2h4.3l1.1 1.4h7.2v8.2H1.7V3.2Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><path d="M1.7 5.4h12.6" stroke="currentColor" stroke-width="1.2"/></svg></span>
        <span class="ag-workspace-name">${esc(workspace.name)}</span><b>${tasks.length}</b><span class="ag-triangle" aria-hidden="true"></span>
      </summary>
      <div class="ag-workspace-tasks">${taskRows}</div>
    </details>`;
  }).join("");
  $$("[data-workspace-task]").forEach((button) => button.addEventListener("click", () => selectProject(button.dataset.workspaceTask)));
  if ($("#workspace-count")) $("#workspace-count").textContent = `${WORKSPACES.length} 个`;
}

function renderProjects() {
  const list = $("#project-list");
  const query = ($("#task-search")?.value || "").trim().toLowerCase();
  const tasks = state.projects
    .filter((project) => !query || [project.name, project.goal, project.domain, project.workspaceId].join(" ").toLowerCase().includes(query))
    .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")))
    .slice(0, query ? 50 : 6);
  if ($("#task-count")) $("#task-count").textContent = String(tasks.length);
  if ($("#recent-tasks-group")) $("#recent-tasks-group").open = true;
  list.innerHTML = tasks.map((project) => {
    const active = project.id === state.selectedProjectId ? " is-on" : "";
    const workspace = WORKSPACES.find((item) => item.id === project.workspaceId);
    const status = project.auto?.running ? "running" : project.auto?.gate ? "human gate" : project.status;
    const time = String(project.updatedAt || "").slice(5, 16).replace("T", " ");
    return `<button type="button" class="ag-project${active}" data-project="${esc(project.id)}" data-status="${esc(project.status)}">
      <span class="ag-project-dot"></span>
      <span><b>${esc(project.name)}</b><small>${esc(workspace?.name || "工作区")} · ${esc(status)} · ${esc(time)}</small></span>
    </button>`;
  }).join("") || `<div class="ag-project-empty">${query ? "没有匹配的任务" : "还没有最近任务"}</div>`;
  $$(".ag-project").forEach((button) => {
    button.addEventListener("click", () => selectProject(button.dataset.project));
  });
}

function renderHeader() {
  const project = currentProject();
  const meta = MODE_META[project.mode];
  const gates = project.gates.filter((gate) => gate.status !== "pass" && gate.status !== "not_started");
  const workspace = WORKSPACES.find((item) => item.id === project.workspaceId);
  $("#thread-kicker").textContent = `${workspace?.name || "Workspace"} / ${meta.kicker} · ${project.domain}`;
  $("#thread-title").textContent = project.name;
  $("#thread-goal").textContent = project.goal;
  const gaps = (project.evidence || []).filter((item) => item.type === "gap").length;
  const candidates = (project.evidence || []).filter((item) => item.type === "hypothesis").length;
  const claims = (project.evidence || []).filter((item) => item.type === "claim").length;
  $("#thread-brief").textContent = `${(project.evidence || []).length} objects · ${gaps} gaps · ${candidates} hypotheses · ${claims} claims · ${project.run ? "EA " + project.run.id : "no EA"}`;
  const chips = [
    `<span class="ag-chip live">${esc(meta.label)}</span>`,
    `<span class="ag-chip">STAGE ${project.stage + 1}/9</span>`,
    gates.length ? `<span class="ag-chip warn">${gates.length} gate${gates.length > 1 ? "s" : ""}</span>` : `<span class="ag-chip ok">gates clear</span>`,
    `<span class="ag-chip">${esc(project.harness.version)} · budget ${project.harness.budget}</span>`,
    project.auto.running ? `<span class="ag-chip live">${project.auto.paused ? "AUTO PAUSED" : "AUTO RUNNING"}</span>` : "",
    project.auto.paused && project.auto.gate ? `<span class="ag-chip bad">HUMAN GATE</span>` : "",
    (project.guidance || []).some((item) => item.status === "queued") ? `<span class="ag-chip warn">GUIDANCE ${(project.guidance || []).filter((item) => item.status === "queued").length}</span>` : ""
  ].filter(Boolean);
  $("#thread-meta").innerHTML = chips.join("");
  $$(".ag-mode").forEach((button) => {
    button.classList.toggle("is-on", button.dataset.mode === project.mode);
    button.setAttribute("aria-pressed", button.dataset.mode === project.mode ? "true" : "false");
  });
}

function renderThread() {
  const project = currentProject();
  const thread = $("#ag-thread");
  const stick = state.preferences.autoScroll && thread.scrollHeight - thread.scrollTop - thread.clientHeight < 120;
  thread.innerHTML = project.messages.map(renderMessage).join("");
  if (stick) requestAnimationFrame(() => { thread.scrollTop = thread.scrollHeight; });
}

function renderMessage(item) {
  if (item.role === "system") {
    return `<div class="ag-system"><b>${esc(item.at)}</b> · ${esc(item.text)}</div>`;
  }
  const isUser = item.role === "user";
  return `
    <div class="ag-msg ${isUser ? "user" : "agent"}">
      <div class="ag-avatar">${isUser ? "YOU" : "RA"}</div>
      <div class="ag-msg-body">
        <div class="ag-msg-head"><b>${isUser ? "你" : "Research Agent"}</b><span>${esc(item.at)}</span></div>
        <div class="ag-bubble">
          ${item.text ? `<p>${formatText(item.text)}</p>` : ""}
          ${item.card ? renderCard(item.card) : ""}
        </div>
      </div>
    </div>`;
}

function formatText(text) {
  let safe = esc(text);
  safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");
  safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return safe;
}

function renderActions(actions) {
  if (!actions || !actions.length) return "";
  return `<div class="ag-card-actions">${actions.map((action) =>
    `<button type="button" class="ag-action ${action.quiet ? "quiet" : ""} ${action.bad ? "bad" : ""}" data-action="${esc(action.action)}" ${action.arg ? `data-arg="${esc(action.arg)}"` : ""}>${esc(action.label)}</button>`
  ).join("")}</div>`;
}

function renderCard(cardData) {
  const live = currentProject();
  let data = { ...(cardData.data || {}) };
  let actions = cardData.actions || [];
  const liveClaim = live.evidence.find((item) => item.type === "claim" && item.status === "supported");
  if (cardData.type === "protocol" && live.protocolFrozen) {
    data.status = "G2 frozen · SIM";
    data.note = liveClaim
      ? "Claim 已签（SIM）；result.primary 可绑定这次 run，但 closure 仍可能因引用槽 blocked。"
      : "结果槽仍为 pending：没有 EA 与人签 claim，不会生成结果数字。";
    actions = actions.filter((action) => action.action !== "freeze-protocol");
  }
  if (cardData.type === "run" && liveClaim) {
    data.status = "EA sealed · claim signed (SIM)";
    data.claimSigned = true;
    actions = actions.filter((action) => action.action !== "sign-claim-gate");
  }
  if (cardData.type === "gate" && liveClaim) {
    data.status = "signed";
    data.title = "Claim 已签（SIM）";
    data.reason = "人工门已完成；claim 只覆盖这一次 run。";
    data.note = "这是历史人工门，不是可以重复点击的动作。";
    actions = [];
  }
  if (cardData.type === "evolution") {
    const current = live.evolution.candidate;
    if (current && current.id === data.id) {
      data = { ...data, ...current };
      actions = current.status === "pending"
        ? [{ label: "批准候选", action: "approve-candidate" }, { label: "拒绝并保留负结果", action: "reject-candidate", quiet: true }]
        : current.status === "active"
          ? [{ label: "撤销租约", action: "rollback-harness", quiet: true }]
          : [];
    }
  }
  const head = (label, right = "") => `<div class="ag-card-head"><b>${esc(label)}</b><span>${esc(right)}</span></div>`;
  if (cardData.type === "plan") {
    return `<section class="ag-card">${head("QUERY PLAN", "6 SOURCES")}
      <div class="ag-card-body"><ul class="ag-list">${(data.queries || []).map((query) => `<li>${esc(query)}</li>`).join("")}</ul>
      <p><b>scope</b> ${esc(data.scope)} · <b>budget</b> ${esc(data.budget)}</p><p>${esc(data.note)}</p></div>
      ${renderActions(actions)}</section>`;
  }
  if (cardData.type === "sources") {
    return `<section class="ag-card">${head("SOURCES / SPANS", "4 HITS")}
      <div class="ag-card-body"><ul class="ag-list">${(data.items || []).map((item) => `
        <li><span class="ag-source-row"><b>${esc(item.title)}</b><span>${esc(item.meta)} <span class="ag-badge ${item.status === "ok" ? "ok" : "warn"}">${item.status === "ok" ? "FULL" : "ABSTRACT"}</span></span></span></li>`).join("")}</ul>
      <p>${esc(data.note)}</p></div>${renderActions(actions)}</section>`;
  }
  if (cardData.type === "idea") {
    return `<section class="ag-card">${head("GAP → HYPOTHESES", "G1 NEEDS HUMAN")}
      <div class="ag-card-body"><p><b>gap</b> ${esc(data.gap)}</p>
      <ul class="ag-list">${(data.candidates || []).map((candidate) => `<li><b>${esc(candidate.id)} · candidate</b>${esc(candidate.text)}</li>`).join("")}</ul>
      <p class="ag-inline-note">${esc(data.note)}</p></div>${renderActions(actions)}</section>`;
  }
  if (cardData.type === "protocol") {
    return `<section class="ag-card">${head("PROTOCOL DRAFT", data.status)}
      <div class="ag-card-body"><dl class="ag-kv">
        <dt>HYPOTHESIS</dt><dd>${esc(data.hypothesis)}</dd>
        <dt>BASELINE</dt><dd>${esc(data.baseline)}</dd>
        <dt>METRIC</dt><dd>${esc(data.metric)}</dd>
        <dt>SEEDS</dt><dd>${esc(data.seeds)}</dd>
        <dt>CONTROLS</dt><dd>${esc((data.controls || []).join(" · "))}</dd>
      </dl><p class="ag-inline-note">${esc(data.note || "结果槽仍为 pending：没有 EA 与人签 claim，不会生成结果数字。")}</p></div>
      ${renderActions(actions)}</section>`;
  }
  if (cardData.type === "run") {
    return `<section class="ag-card">${head("RUN RESULT", data.status)}
      <div class="ag-card-body"><dl class="ag-kv">
        <dt>RUN</dt><dd>${esc(data.id)}</dd>
        <dt>DATASET</dt><dd>${esc(data.dataset)} · ${esc(data.seeds)} seeds</dd>
        <dt>RESULT</dt><dd><b>${esc(data.metric)} ${esc(data.mean)}</b> · baseline ${esc(data.baseline)}</dd>
        <dt>EA</dt><dd>${esc(data.ea)} · sealed</dd>
        <dt>CLAIM</dt><dd>${data.claimSigned ? '<span class="ag-badge ok">signed</span> 只覆盖这次 run' : '<span class="ag-badge warn">unsigned</span> 人工签核后才可绑定 paper'}</dd>
      </dl></div>${renderActions(actions)}</section>`;
  }
  if (cardData.type === "gate") {
    return `<section class="ag-card">${head(data.gate, data.status)}
      <div class="ag-card-body"><p><b>${esc(data.title)}</b></p><p>${esc(data.reason)}</p>
      <p class="ag-inline-note">${esc(data.note || "这是人工门，不是系统失败。全自动会在这里暂停。")}</p></div>
      ${renderActions(actions)}</section>`;
  }
  if (cardData.type === "stage") {
    return `<section class="ag-card">${head("AUTO STEP", data.cmd)}
      <div class="ag-card-body"><p><b>${esc(data.name)}</b> · ${esc(data.output)}</p>
      <div class="ag-progress"><i style="width:${Math.max(4, Math.min(100, ((data.stage || 0) + 1) / 9 * 100))}%"></i></div>
      <p class="ag-inline-note">${esc(data.note || "SIM 自动推进；无真实 run。")}</p></div></section>`;
  }
  if (cardData.type === "evolution") {
    const statusLabel = data.status === "active" ? "LEASE ACTIVE" : data.status === "rejected" ? "REJECTED · NEGATIVE KEPT" : "PENDING HUMAN";
    return `<section class="ag-card">${head("SELF-EVOLUTION CANDIDATE", statusLabel)}
      <div class="ag-card-body">
        <p><b>${esc(data.id)}</b> · ${esc(data.target)}</p>
        <p><b>patch</b> ${esc(data.patch)}</p>
        <p>${esc(data.rationale)}</p>
        <p class="ag-inline-note"><b>predicted</b> ${esc(data.predicted)} · <b>lease</b> ${esc(data.lease || "未发放")}</p>
        <div class="ag-evidence-meta">${(data.ev || []).map((item) => `<span class="ag-badge ${item.ok ? "ok" : "warn"}">${esc(item.label)} ${esc(item.value)}</span>`).join("")}</div>
      </div>${renderActions(actions)}</section>`;
  }
  if (cardData.type === "tool-call") {
    return `<section class="ag-card">${head("MCP TOOL CALL", "APPROVAL REQUIRED")}
      <div class="ag-card-body"><p><b>${esc(data.plugin)}</b> · ${esc(data.tool)}</p>
      <p class="mono" style="font-size:8px">${esc(data.args)}</p>
      <p class="ag-inline-note">工具结果不可信；不会自动进入 claim/EA/evidence。需要逐次批准。</p></div>
      ${renderActions(actions)}</section>`;
  }
  if (cardData.type === "tool-result") {
    return `<section class="ag-card">${head("MCP RESULT", "UNTRUSTED")}
      <div class="ag-card-body"><p><b>${esc(data.tool)}</b> · ${(data.items || []).length} results</p>
      <ul class="ag-list">${(data.items || []).map((item) => `<li>${esc(item)}</li>`).join("")}</ul>
      <p class="ag-inline-note">外部工具结果只作线索；需要人工核对，不能直接生成 claim。</p></div></section>`;
  }
  if (cardData.type === "guidance") {
    return `<section class="ag-card">${head("USER GUIDANCE", data.status || "queued")}
      <div class="ag-card-body"><p>${esc(data.text)}</p>
      <p class="ag-inline-note">scope ${esc(data.scope || "next_checkpoint")} · 只改执行策略，不改 claim/EA/gate。</p></div></section>`;
  }
  if (cardData.type === "auto-start") {
    return `<section class="ag-card">${head("GOVERNED AUTO", "READY")}
      <div class="ag-card-body"><p><b>${esc(data.title)}</b></p><p>${esc(data.note)}</p></div>
      ${renderActions(actions)}</section>`;
  }
  if (cardData.type === "summary") {
    return `<section class="ag-card">${head("CLOSURE SUMMARY", "STATIC")}
      <div class="ag-card-body"><p><b>${esc(data.title)}</b></p><dl class="ag-kv">${(data.rows || []).map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`).join("")}</dl></div>
      ${renderActions(actions)}</section>`;
  }
  return "";
}

function profileById(id) {
  return MODEL_PROFILES.find((profile) => profile.id === id) || MODEL_PROFILES[0];
}

function renderModelChip() {
  const project = currentProject();
  const profile = modelProfile(project);
  const settings = modelSettings(project);
  $("#model-name").textContent = profile.short;
  $("#model-thinking").textContent = `${formatTokens(settings.contextLimit)} · ${thinkingLabel(project)}`;
  $("#model-btn").title = `${profile.name} · ${formatTokens(settings.contextLimit)} ctx · ${thinkingLabel(project)} · compression ${settings.compression}`;
}

function openModelDialog() {
  const project = currentProject();
  modelDraft = { ...modelSettings(project) };
  renderModelDialog();
  const dialog = $("#model-dialog");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}

function closeModelDialog() {
  const dialog = $("#model-dialog");
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
  modelDraft = null;
}

function renderModelDialog() {
  if (!modelDraft) return;
  const profile = profileById(modelDraft.profileId);
  if (modelDraft.contextLimit > profile.contextWindow) modelDraft.contextLimit = profile.contextWindow;
  if (modelDraft.maxReply > profile.maxOutput) modelDraft.maxReply = profile.maxOutput;
  $("#model-profile-list").innerHTML = MODEL_PROFILES.map((item) => `
    <button type="button" class="ag-model-option ${item.id === profile.id ? "is-on" : ""}" data-model-profile="${esc(item.id)}">
      <b>${esc(item.short)}</b><span>${esc(item.provider)} · ${esc(formatTokens(item.contextWindow))} ctx</span><em>${item.kind === "unsupported" ? "thinking off" : "thinking " + esc(item.kind)}</em>
    </button>`).join("");
  $$("[data-model-profile]").forEach((button) => button.addEventListener("click", () => {
    const next = profileById(button.dataset.modelProfile);
    modelDraft.profileId = next.id;
    modelDraft.contextLimit = Math.min(128000, next.contextWindow);
    modelDraft.maxReply = Math.min(8192, next.maxOutput);
    modelDraft.thinkingStop = next.defaultStop;
    renderModelDialog();
  }));
  $("#model-capability").innerHTML = [
    `<span>ctx <b>${esc(formatTokens(profile.contextWindow))}</b></span>`,
    `<span>out <b>${esc(formatTokens(profile.maxOutput))}</b></span>`,
    `<span>thinking <b>${profile.kind === "unsupported" ? "未声明" : esc(profile.kind)}</b></span>`,
    `<span>${esc(profile.provider)}</span>`
  ].join("");
  const contextSlider = $("#ms-context");
  contextSlider.min = "8192";
  contextSlider.max = String(profile.contextWindow);
  contextSlider.step = "8192";
  contextSlider.value = String(modelDraft.contextLimit);
  $("#ms-context-limit").textContent = `模型上限 ${formatTokens(profile.contextWindow)}`;
  $("#ms-context-value").textContent = formatTokens(modelDraft.contextLimit);
  const replySlider = $("#ms-reply");
  replySlider.min = "256";
  replySlider.max = String(profile.maxOutput);
  replySlider.step = "256";
  replySlider.value = String(modelDraft.maxReply);
  $("#ms-reply-limit").textContent = `模型上限 ${formatTokens(profile.maxOutput)} · 实际发送时不超过`;
  $("#ms-reply-value").textContent = formatTokens(modelDraft.maxReply);
  const thinking = $("#ms-thinking");
  const stops = profile.stops || [];
  const selectedIndex = Math.max(0, stops.findIndex((stop) => String(stop.value) === String(modelDraft.thinkingStop)));
  thinking.min = "0";
  thinking.max = String(Math.max(0, stops.length - 1));
  thinking.step = "1";
  thinking.value = String(selectedIndex);
  thinking.disabled = !stops.length;
  $("#ms-thinking-labels").innerHTML = stops.length
    ? stops.map((stop, index) => `<span class="${index === selectedIndex ? "is-on" : ""}">${esc(stop.label)}</span>`).join("")
    : "<span>未声明可调思考强度</span>";
  $("#ms-thinking-value").textContent = stops.length ? stops[selectedIndex].label : "off";
  $("#ms-thinking-note").textContent = stops.length
    ? `${profile.note} 当前映射：${stops[selectedIndex].detail}`
    : `${profile.note} 思考强度滑块不可用；不会伪造档位。`;
  $$("[data-compression]").forEach((button) => button.classList.toggle("is-on", button.dataset.compression === modelDraft.compression));
  $("#ms-compression-value").textContent = modelDraft.compression;
  $("#ms-threshold").value = String(Math.round(modelDraft.threshold * 100));
  $("#ms-threshold-value").textContent = Math.round(modelDraft.threshold * 100) + "%";
  $("#ms-keep").value = String(modelDraft.keepRecent);
  $("#ms-summary").value = String(modelDraft.summaryTokens);
  updateModelPreview();
}

function updateModelPreview() {
  if (!modelDraft) return;
  const profile = profileById(modelDraft.profileId);
  const stops = profile.stops || [];
  const index = Math.max(0, stops.findIndex((stop) => String(stop.value) === String(modelDraft.thinkingStop)));
  const stop = stops[index];
  $("#ms-context-value").textContent = formatTokens(modelDraft.contextLimit);
  $("#ms-reply-value").textContent = formatTokens(modelDraft.maxReply);
  $("#ms-thinking-value").textContent = stop ? stop.label : "off";
  $("#ms-thinking-labels").innerHTML = stops.length
    ? stops.map((item, i) => `<span class="${i === index ? "is-on" : ""}">${esc(item.label)}</span>`).join("")
    : "<span>未声明可调思考强度</span>";
  $("#ms-thinking-note").textContent = stop
    ? `${profile.note} 当前映射：${stop.detail}`
    : `${profile.note} 思考强度滑块不可用；不会伪造档位。`;
  $("#ms-compression-value").textContent = modelDraft.compression;
  $("#ms-threshold-value").textContent = Math.round(modelDraft.threshold * 100) + "%";
  $("#ms-compression-note").textContent = modelDraft.compression === "off"
    ? "压缩关闭：历史会一直保留到模型上下文上限；超出时请求应失败，而不是静默截断。"
    : `约在 ${formatTokens(Math.round(modelDraft.contextLimit * modelDraft.threshold / 1000) * 1000)} tokens 时压缩历史；保留最近 ${modelDraft.keepRecent} 轮 + ${modelDraft.summaryTokens} tokens 摘要。`;
  $("#ms-preview").innerHTML = [
    `MODEL <b>${esc(profile.name)}</b> · context <b>${esc(formatTokens(modelDraft.contextLimit))}</b> / ${esc(formatTokens(profile.contextWindow))} · reply <b>${esc(formatTokens(modelDraft.maxReply))}</b>`,
    `thinking <b>${esc(stop ? stop.label : "off")}</b> (${esc(stop ? stop.detail : "model 未声明")}) · compression <b>${esc(modelDraft.compression)}</b>${modelDraft.compression === "off" ? "" : ` @ ${Math.round(modelDraft.threshold * 100)}%`}`,
    `能力值来自示例配置；真实接入时以 Provider/Profile 或模型文档为准。`
  ].join("<br>");
}

function saveModelSettings(event) {
  event.preventDefault();
  if (!modelDraft) return;
  const project = currentProject();
  const profile = profileById(modelDraft.profileId);
  project.model = {
    ...modelDraft,
    contextLimit: Math.max(8192, Math.min(modelDraft.contextLimit, profile.contextWindow)),
    maxReply: Math.max(256, Math.min(modelDraft.maxReply, profile.maxOutput))
  };
  project.messages.push(system(
    `MODEL CONFIG · ${profile.name} · ctx ${formatTokens(project.model.contextLimit)} · reply ${formatTokens(project.model.maxReply)} · thinking ${thinkingLabel(project)} · compression ${project.model.compression}`
  ));
  closeModelDialog();
  saveAndRender();
  scrollThread();
  toast("模型设置已应用（静态）");
}

function applyPreferences() {
  document.body.classList.toggle("ag-reduce-motion", Boolean(state.preferences.reduceMotion));
}

function syncVersion() {
  const label = `v${APP_VERSION} · static`;
  if ($("#app-version")) $("#app-version").textContent = label;
  if ($("#side-version")) $("#side-version").textContent = `workspace v${APP_VERSION} · seed ${BUILD_DATE}`;
}

function syncTools() {
  $("#pref-auto-expand").checked = state.preferences.autoExpandRunning;
  $("#pref-auto-scroll").checked = state.preferences.autoScroll;
  $("#pref-reduce-motion").checked = state.preferences.reduceMotion;
}

function openTools() {
  $("#tools-panel").hidden = false;
  $("#tools-btn").setAttribute("aria-expanded", "true");
  syncTools();
}

function closeTools() {
  $("#tools-panel").hidden = true;
  $("#tools-btn").setAttribute("aria-expanded", "false");
}

function setPreference(key, value) {
  state.preferences[key] = value;
  save();
  applyPreferences();
  renderAll();
  toast("偏好已保存");
}

function enabledPlugins(project) {
  return (state.plugins || []).filter((plugin) => (project.plugins || []).includes(plugin.id));
}

function renderPluginChip() {
  const project = currentProject();
  $("#plugin-count").textContent = String((project.plugins || []).length);
  $("#plugin-btn").title = `插件 / MCP · ${enabledPlugins(project).map((item) => item.name).join(", ") || "未启用"}`;
}

function openPlugins() {
  closeTools();
  $("#plugin-drawer").hidden = false;
  renderPlugins();
}

function closePlugins() {
  $("#plugin-drawer").hidden = true;
}

function renderPlugins() {
  const project = currentProject();
  const list = $("#plugin-list");
  const plugins = state.plugins || [];
  list.innerHTML = plugins.map((plugin) => {
    const enabled = (project.plugins || []).includes(plugin.id);
    return `<div class="ag-plugin-card">
      <div class="ag-plugin-card-head"><b>${esc(plugin.name)}</b><span class="ag-badge ${plugin.status === "ready" ? "ok" : "warn"}">${plugin.status === "ready" ? "SIM READY" : esc(plugin.status.toUpperCase())}</span></div>
      <div class="ag-plugin-meta">${esc(plugin.transport)} · ${esc(plugin.auth)} · ${plugin.readonly ? "READ ONLY" : "WRITE"}</div>
      <div class="ag-plugin-toolsets">${(plugin.toolsets || []).map((tool) => `<span>${esc(tool)}</span>`).join("")}</div>
      <div class="ag-plugin-card-foot"><span>${esc(plugin.note || "")}</span><label class="ag-switch-inline"><input type="checkbox" data-plugin-toggle="${esc(plugin.id)}" ${enabled ? "checked" : ""}/> 本对话启用</label></div>
    </div>`;
  }).join("") || '<div class="ag-context-empty">还没有 MCP server。添加一个或使用 GitHub 预设。</div>';
  $$("[data-plugin-toggle]").forEach((input) => input.addEventListener("change", () => {
    togglePlugin(input.dataset.pluginToggle, input.checked);
  }));
  renderPluginCalls(project);
}

function togglePlugin(pluginId, enabled) {
  const project = currentProject();
  const set = new Set(project.plugins || []);
  if (enabled) set.add(pluginId); else set.delete(pluginId);
  project.plugins = Array.from(set);
  project.messages.push(system(`PLUGIN ${enabled ? "ENABLED" : "DISABLED"} · ${pluginId} · this conversation`));
  saveAndRender();
  renderPlugins();
  toast(enabled ? "插件已在本对话启用" : "插件已停用");
}

function renderPluginCalls(project) {
  const host = $("#plugin-calls");
  const calls = (project.toolCalls || []).slice().reverse();
  host.innerHTML = calls.length ? calls.map((call) => `
    <div class="ag-plugin-call">
      <b>${esc(call.tool)}</b><span class="ag-badge ${call.status === "approved" ? "ok" : call.status === "denied" ? "bad" : "warn"}">${esc(call.status)}</span>
      <p>${esc(call.args)}</p>
    </div>`).join("") : '<div class="ag-context-empty">本对话还没有工具调用。输入 “用 GitHub MCP 查一下 issue” 试试。</div>';
}

function syncPluginForm() {
  const preset = PLUGIN_PRESETS[$("#plugin-preset").value] || PLUGIN_PRESETS.custom;
  $("#plugin-name").value = preset.name;
  $("#plugin-url").value = preset.url;
  $("#plugin-auth").value = preset.auth;
  $("#plugin-toolsets").value = preset.toolsets;
  $("#plugin-readonly").checked = preset.readonly;
}

function addPlugin(event) {
  event.preventDefault();
  const presetId = $("#plugin-preset").value;
  const name = $("#plugin-name").value.trim();
  const url = $("#plugin-url").value.trim();
  if (!name) return toast("插件名称不能为空");
  if (presetId !== "local" && !url) return toast("MCP endpoint 不能为空");
  const id = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || uid("mcp");
  const plugin = {
    id,
    name,
    preset: presetId,
    transport: PLUGIN_PRESETS[presetId]?.transport || "streamable-http",
    url,
    auth: $("#plugin-auth").value,
    readonly: $("#plugin-readonly").checked,
    toolsets: $("#plugin-toolsets").value.split(",").map((item) => item.trim()).filter(Boolean),
    status: "ready",
    note: presetId === "github" ? "SIM · GitHub 官方远程 MCP；OAuth 由 runtime 保管" : "SIM · 静态登记；未真实连接",
    installedAt: now()
  };
  state.plugins = (state.plugins || []).filter((item) => item.id !== id).concat(plugin);
  const project = currentProject();
  project.plugins = Array.from(new Set([...(project.plugins || []), id]));
  project.messages.push(system(`MCP REGISTERED (SIM) · ${name} · ${url || "stdio registered only"}`));
  saveAndRender();
  renderPlugins();
  toast("MCP server 已登记并启用（SIM）");
}

function proposeGithubCall(text) {
  const project = currentProject();
  if (!(project.plugins || []).includes("github")) {
    project.messages.push(agent("GitHub MCP 还没有在本对话启用。先打开 PLUGINS 启用它；我不会在未授权时调用外部工具。", card("summary", {
      title: "PLUGIN NOT ENABLED",
      rows: [["plugin", "GitHub MCP"], ["state", "disabled"], ["next", "PLUGINS → 启用"]]
    }, [{ label: "打开插件", action: "open-plugins" }])));
    saveAndRender();
    return;
  }
  const call = {
    id: uid("TOOL"),
    plugin: "github",
    tool: "list_issues",
    args: text.includes("pull") || text.includes("PR") ? "pull_requests · query=research-agent" : "issues · query=research-agent",
    status: "pending",
    at: now()
  };
  project.toolCalls = project.toolCalls || [];
  project.toolCalls.push(call);
  project.messages.push(agent(
    "GitHub MCP 提议调用一个只读工具。工具输出是不可信外部内容，必须先批准一次；它不会直接变成 claim 或证据。",
    card("tool-call", call, [
      { label: "允许一次", action: "approve-tool", arg: call.id },
      { label: "拒绝", action: "deny-tool", arg: call.id, quiet: true }
    ])
  ));
  saveAndRender();
  scrollThread();
}

function approveToolCall(id) {
  const project = currentProject();
  const call = (project.toolCalls || []).find((item) => item.id === id);
  if (!call || call.status !== "pending") return;
  call.status = "approved";
  call.approvedAt = now();
  project.messages.push(system(`TOOL APPROVED (SIM) · ${call.id} · ${call.tool}`));
  project.messages.push(agent("工具返回了 3 条只读结果（SIM）。它们是外部内容，不是 claim；需要人工核对后才能进入证据链。", card("tool-result", {
    tool: "list_issues",
    items: [
      "research-agent#12 · evidence ledger schema",
      "research-agent#18 · runtime guidance checkpoint",
      "research-agent#21 · MCP plugin approval"
    ]
  })));
  saveAndRender();
  renderPlugins();
  scrollThread();
  toast("已允许一次工具调用（SIM）");
}

function denyToolCall(id) {
  const project = currentProject();
  const call = (project.toolCalls || []).find((item) => item.id === id);
  if (!call || call.status !== "pending") return;
  call.status = "denied";
  project.messages.push(system(`TOOL DENIED · ${call.id} · ${call.tool}`));
  saveAndRender();
  renderPlugins();
  scrollThread();
  toast("已拒绝工具调用");
}

function renderSideStatus() {
  const project = currentProject();
  const attention = project.gates.filter((gate) => gate.status === "needs_human" || gate.status === "blocked").length;
  $("#side-status").innerHTML = [
    ["阶段", `S${project.stage + 1} / 9`],
    ["模式", MODE_META[project.mode].label],
    ["gates", `${attention} need attention`],
    ["guidance", `${(project.guidance || []).filter((item) => item.status === "queued").length} queued`],
    ["plugins", `${(project.plugins || []).length} enabled`],
    ["harness", `${project.harness.version} · budget ${project.harness.budget}`],
    ["预算", `${project.budget.used} / ${project.budget.total} runs`],
    ["自动", project.auto.running ? (project.auto.paused ? "paused" : "running") : project.auto.gate ? "human gate" : "idle"]
  ].map(([key, value]) => `<div class="ag-side-stat"><span>${esc(key)}</span><b>${esc(value)}</b></div>`).join("");
}

function suggestionsFor(project) {
  if (project.auto.gate) return ["模拟签核", "插入指导", "查看证据"];
  if (project.auto.running) return ["插入指导", project.auto.paused ? "继续" : "暂停", "单步", "停止"];
  const candidate = project.evolution.candidate;
  if (candidate?.status === "pending") return ["批准候选", "拒绝并保留负结果", "查看证据"];
  if (candidate?.status === "active") return ["再跑一轮", "撤销租约", "查看证据"];
  return SUGGESTIONS[project.mode] || [];
}

function renderSuggestions() {
  const project = currentProject();
  const suggestions = suggestionsFor(project);
  $("#suggestions").innerHTML = suggestions.map((text) =>
    `<button type="button" class="ag-suggestion" data-suggestion="${esc(text)}">${esc(text)}</button>`
  ).join("");
  $$(".ag-suggestion").forEach((button) => button.addEventListener("click", () => handleSuggestion(button.dataset.suggestion)));
}

function renderComposerMode() {
  const project = currentProject();
  const mode = project.mode;
  if (project.auto.running) {
    $("#composer-mode").textContent = project.auto.paused
      ? "全自动已暂停 · 输入指导，或 /resume /step"
      : "全自动运行中 · 输入指导会在下一阶段应用";
    $("#composer-input").placeholder = project.auto.paused
      ? "输入指导，或 /resume 继续 /step 单步……"
      : "输入指导（如：优先看 archive 复用），或 /pause /step……";
    return;
  }
  $("#composer-mode").textContent = `${MODE_META[mode].label} · ${MODE_META[mode].hint}`;
  $("#composer-input").placeholder = MODE_META[mode].placeholder;
}

/* ---------- context panel ---------- */

function renderContext() {
  const project = currentProject();
  $$(".ag-ctx-tab").forEach((tab) => {
    const active = tab.dataset.context === activeContext;
    tab.classList.toggle("is-on", active);
    tab.setAttribute("aria-selected", active ? "true" : "false");
  });
  $("#context-count").textContent = activeContext === "run" ? `S${project.stage + 1}/9` : activeContext === "evidence" ? `${project.evidence.length} objects` : `${project.evolution.history.length} records`;
  const body = $("#context-body");
  if (activeContext === "run") body.innerHTML = renderRunContext(project);
  else if (activeContext === "evidence") body.innerHTML = renderEvidenceContext(project);
  else body.innerHTML = renderEvolutionContext(project);
  $("#context-foot").innerHTML = `<b>下一步</b> ${esc(nextStep(project))}`;
  bindContextActions();
}

function renderRunContext(project) {
  const stage = STAGES[Math.min(project.stage, STAGES.length - 1)];
  const progress = Math.max(0, Math.min(100, ((project.stage + 1) / STAGES.length) * 100));
  const completed = new Set(project.completedStages || []);
  const skipped = new Set(project.skippedStages || []);
  const stageRows = STAGES.map((item, index) => {
    const done = completed.has(index);
    const isCurrent = index === project.stage;
    const stateClass = done ? "is-done" : isCurrent ? "is-current" : skipped.has(index) ? "is-skipped" : "";
    const status = done ? "done" : isCurrent ? "current" : skipped.has(index) ? "skipped" : "pending";
    const open = isCurrent && state.preferences.autoExpandRunning;
    return `<details class="ag-stage ${stateClass}" ${open ? "open" : ""}>
      <summary><span class="ag-triangle" aria-hidden="true"></span><span class="ag-stage-index">${String(index + 1).padStart(2, "0")}</span><b>${esc(item[1])}</b><span>${esc(status)}</span></summary>
      <div class="ag-stage-detail"><span>cmd <b>${esc(item[2])}</b></span><span>${esc(status)} · ${esc(project.auto.running ? (project.auto.paused ? "paused" : "auto") : "manual")}</span></div>
    </details>`;
  }).join("");
  const gates = project.gates.map((gate) => `
    <div class="ag-gate"><b>${esc(gate.id)}</b><span>${esc(gate.reason)}</span><em>${esc(gate.status)}</em></div>`).join("");
  return `
    <section class="ag-panel"><div class="ag-panel-head"><b>CURRENT RUN</b><span>${esc(stage[0])}</span></div>
      <div class="ag-panel-body"><div class="ag-progress"><i style="width:${progress}%"></i></div>
      <p style="margin:6px 0 0;font-size:9px;color:var(--muted)"><b>${esc(stage[1])}</b> · ${esc(stage[2])}</p>
      <p style="margin:4px 0 0;font-size:8px;color:var(--faint)">${project.auto.running ? "自动运行中" : project.auto.paused ? "已暂停 / 等待人工" : "手动推进"}</p></div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>STAGES</b><span>9 STEPS</span></div><div class="ag-panel-body"><div class="ag-stage-list">${stageRows}</div></div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>OBJECT CHAIN</b><span>ARTIFACT</span></div><div class="ag-panel-body"><div class="ag-chain">
      <span>QueryPlan</span><i>→</i><span>Span</span><i>→</i><span>Design</span><i>→</i><span>RunCapsule</span><i>→</i><span>EA</span><i>→</i><span>Claim</span><i>→</i><span>Closure</span>
    </div><p class="ag-inline-note">claim/EA 必须绑定同一 run；closure 结构闭合不等于同行评审。</p></div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>GATES</b><span>HUMAN / RULE</span></div><div class="ag-panel-body">${gates}</div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>GUIDANCE</b><span>${(project.guidance || []).filter((item) => item.status === "queued").length} QUEUED</span></div>
      <div class="ag-panel-body">${(project.guidance || []).length ? (project.guidance || []).slice().reverse().map((item) => `
        <div class="ag-guidance-item ${esc(item.status)}">
          <b>${esc(item.id)} · ${esc(item.kind || "note")}</b>
          <p>${esc(item.text)}</p>
          <span>${esc(item.status)}${item.appliedAt ? " · " + esc(item.appliedAt) : ""}</span>
          ${item.status === "queued" ? `<div class="ag-evo-actions"><button type="button" class="ag-action" data-action="apply-guidance" data-arg="${esc(item.id)}">立即应用</button><button type="button" class="ag-action quiet" data-action="dismiss-guidance" data-arg="${esc(item.id)}">丢弃</button></div>` : ""}
        </div>`).join("") : '<div class="ag-context-empty">运行中直接在输入框说话，会把指导排到下一阶段；不会改 claim/EA/gate。</div>'}
      </div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>BUDGET</b><span>SIM</span></div><div class="ag-panel-body">
      <div class="ag-evo-row"><span>used / total</span><b>${project.budget.used} / ${project.budget.total}</b></div>
      <div class="ag-evo-row"><span>harness</span><b>${esc(project.harness.version)} · budget ${project.harness.budget}</b></div>
      <div class="ag-evo-row"><span>API calls</span><b>0 · static</b></div>
    </div></section>`;
}

function renderEvidenceContext(project) {
  const claims = project.evidence.filter((item) => item.type === "claim");
  const others = project.evidence.filter((item) => item.type !== "claim");
  const cards = project.evidence.map((item) => `
    <div class="ag-evidence-card">
      <b>${esc(item.id)} <span class="ag-badge ${item.status === "supported" ? "ok" : item.status === "open" ? "warn" : ""}">${esc(item.status)}</span></b>
      <p>${esc(item.text)}</p>
      <div class="ag-evidence-meta"><span class="ag-badge">${esc(item.type)}</span><span class="ag-badge">${esc(item.scope || "—")}</span>${(item.refs || []).map((ref) => `<span class="ag-badge">${esc(ref)}</span>`).join("")}</div>
      ${item.note ? `<p class="ag-inline-note">${esc(item.note)}</p>` : ""}
    </div>`).join("");
  return `
    <section class="ag-panel"><div class="ag-panel-head"><b>EVIDENCE OBJECTS</b><span>${project.evidence.length} TOTAL</span></div>
      <div class="ag-panel-body">${cards || '<div class="ag-context-empty">还没有证据对象。先跑一轮检索或实验。</div>'}</div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>CLAIM / CLOSURE</b><span>${claims.length ? "PARTIAL" : "NO CLAIM"}</span></div>
      <div class="ag-panel-body"><div class="ag-evo-row"><span>claims</span><b>${claims.length} · ${claims.filter((item) => item.status === "supported").length} signed</b></div>
      <div class="ag-evo-row"><span>closure</span><b>${project.evidence.some((item) => item.type === "claim") ? "blocked · citation pending" : "blocked · no claim"}</b></div>
      <div class="ag-evo-row"><span>result slot</span><b>pending_evidence</b></div>
      <p class="ag-inline-note">只有同一 run 的 claim/EA 才能填结果槽；结构闭合不等于语义正确。</p></div></section>`;
}

function renderEvolutionContext(project) {
  const evo = project.evolution;
  const candidate = evo.candidate;
  const history = evo.history.slice(-4).reverse().map((item) =>
    `<div class="ag-evo-row"><span>${esc(item.at)} · ${esc(item.version)}</span><b>${esc(item.status)}</b></div>`).join("");
  const candidateBlock = candidate ? `
    <div class="ag-evo-candidate"><b>${esc(candidate.id)} · ${esc(candidate.status)}</b>
      <p>${esc(candidate.target)} · ${esc(candidate.patch)}</p>
      <p>${esc(candidate.rationale)}</p>
      <div class="ag-evidence-meta">${(candidate.ev || []).map((item) => `<span class="ag-badge ${item.ok ? "ok" : "warn"}">${esc(item.label)} ${esc(item.value)}</span>`).join("")}</div>
      <div class="ag-evo-actions">
        ${candidate.status === "pending" ? `<button type="button" class="ag-action" data-action="approve-candidate">批准</button><button type="button" class="ag-action quiet" data-action="reject-candidate">拒绝</button>` : ""}
        ${candidate.status === "active" ? `<button type="button" class="ag-action bad" data-action="rollback-harness">撤销租约</button>` : ""}
      </div>
    </div>` : '<div class="ag-context-empty">还没有改进候选。跑完一轮全自动后，会在人工门前出现。</div>';
  return `
    <section class="ag-panel"><div class="ag-panel-head"><b>HARNESS</b><span>${esc(project.harness.version)}</span></div>
      <div class="ag-panel-body"><div class="ag-evo-status">
        <div class="ag-evo-row"><span>active</span><b>${esc(project.harness.label)}</b></div>
        <div class="ag-evo-row"><span>retrieval budget</span><b>${project.harness.budget} sources</b></div>
        <div class="ag-evo-row"><span>lease</span><b>${evo.lease ? esc(evo.lease.id) : "none"}</b></div>
        <div class="ag-evo-row"><span>TTL</span><b>${evo.lease ? esc(evo.lease.ttl) : "—"}</b></div>
      </div></div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>PROCESS FEEDBACK</b><span>PF-S1</span></div>
      <div class="ag-panel-body"><p style="margin:0;font-size:8.5px;line-height:1.55;color:var(--muted)">上一轮 broad-first 用 4 篇全文换 12 个 span；候选改为 budget 3 + 先深读 top-2，预计 span 不降、成本下降。过程协议只改同阶段跑法，不改研究问题/claim/gate。</p>
      <div class="ag-evo-row" style="margin-top:5px"><span>status</span><b>${candidate ? esc(candidate.status) : "no update"}</b></div></div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>CANDIDATE</b><span>EV1–EV4</span></div>
      <div class="ag-panel-body">${candidateBlock}</div></section>
    <section class="ag-panel"><div class="ag-panel-head"><b>LINEAGE</b><span>KEEP NEGATIVE</span></div>
      <div class="ag-panel-body">${history || '<div class="ag-context-empty">没有历史租约；拒绝的候选也会保留。</div>'}</div></section>
    <p class="ag-inline-note">这不是 autonomous RSI：候选由系统提议、人签准入；lease 有 scope/TTL，撤销只回退该阶段。</p>`;
}

function nextStep(project) {
  if (project.auto.gate) return "处理人工门：claim 需要人签，系统不会自动继续。";
  if (project.auto.running) return project.auto.paused ? "已暂停；可继续或单步。" : "自动运行中；可随时暂停。";
  if (project.evolution.candidate?.status === "pending") return "审批自进化候选，或保留负结果。";
  if (project.evolution.candidate?.status === "active") return "候选已发放租约；可再跑一轮验证，或撤销回滚。";
  if (project.mode === "research") return "把 gap 变成假设，或扩展检索。";
  if (project.mode === "experiment") return project.protocolFrozen ? "运行协议并查看 EA。" : "冻结协议，运行 seeds。";
  return "启动受治理全自动，跑到人工门再决定。";
}

function bindContextActions() {
  $$("[data-action]", $("#context-body")).forEach((button) => {
    button.addEventListener("click", () => runAction(button.dataset.action, button.dataset.arg));
  });
}

/* ---------- actions ---------- */

function selectProject(id) {
  const mobileSide = document.querySelector(".ag-side");
  if (mobileSide) mobileSide.classList.remove("is-mobile-open");
  if (id === state.selectedProjectId) return;
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  state.projects.forEach((project) => {
    if (project.auto.running) {
      project.auto.running = false;
      project.auto.paused = true;
    }
  });
  state.selectedProjectId = id;
  state.activeWorkspaceId = state.projects.find((project) => project.id === id)?.workspaceId || state.activeWorkspaceId;
  $(".ag-side").classList.remove("is-mobile-open");
  activeContext = "run";
  saveAndRender();
}

function setMode(mode) {
  const project = currentProject();
  if (project.mode === mode) return;
  project.mode = mode;
  if (mode === "experiment" && !project.protocol) {
    project.protocol = { hypothesis: "待从 gap 收敛", baseline: "待补", metric: "待补", seeds: 3 };
    project.messages.push(agent("切到实验模式。先登记一个可冻结的协议；结果槽保持 pending，直到 EA 与人签 claim。", protocolCard()));
    project.stage = Math.max(project.stage, 2);
    project.gates[2] = { id: "G2", status: "needs_human", reason: "协议等待人工冻结" };
  }
  if (mode === "auto" && project.intro.auto !== true) {
    project.intro.auto = true;
    project.messages.push(agent("全自动会连续执行，但会在人工门暂停；不会自动签 claim，也不会绕过 gate。", autoStartCard()));
  }
  saveAndRender();
  focusComposer();
}

function markStage(project, index, skipped = false) {
  if (skipped) {
    project.skippedStages = Array.from(new Set([...(project.skippedStages || []), index]));
  } else {
    project.completedStages = Array.from(new Set([...(project.completedStages || []), index]));
    project.skippedStages = (project.skippedStages || []).filter((item) => item !== index);
  }
}

function runResearch() {
  const project = currentProject();
  if (project.mode !== "research") project.mode = "research";
  project.done.research = true;
  project.stage = Math.max(project.stage, 1);
  markStage(project, 0);
  project.budget.used = Math.min(project.budget.total, project.budget.used + 4);
  project.gates[0] = { id: "Q0", status: "pass", reason: "coverage receipt recorded · 12 spans" };
  project.gates[1] = { id: "G1", status: "needs_human", reason: "2 个候选假设等待收敛" };
  project.status = "active";
  project.messages.push(user("重新跑一轮检索，先宽后深。"));
  project.messages.push(agent("检索完成。3 条全文 + 1 条摘要；span 数没有下降，gap 仍集中在湿热循环对照。", sourcesCard()));
  saveAndRender();
  scrollThread();
}

function designExperiment() {
  const project = currentProject();
  project.mode = "experiment";
  project.done.experiment = true;
  project.stage = Math.max(project.stage, 2);
  if (!(project.completedStages || []).includes(0)) markStage(project, 0, true);
  markStage(project, 1);
  project.protocol = {
    hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
    baseline: "未钝化对照",
    metric: "T80（小时）· 初始 PCE",
    seeds: 3
  };
  project.protocolFrozen = false;
  project.gates[2] = { id: "G2", status: "needs_human", reason: "协议等待人工冻结" };
  project.messages.push(user("把 H1 送入实验设计。"));
  project.messages.push(agent("设计草稿已生成。先冻结协议，再运行；运行完成后会产出 RunCapsule 与 EA，但 claim 仍要人签。", protocolCard()));
  saveAndRender();
  scrollThread();
  focusComposer();
}

function freezeProtocol() {
  const project = currentProject();
  if (!project.protocol) return designExperiment();
  project.protocolFrozen = true;
  project.stage = Math.max(project.stage, 2);
  markStage(project, 2);
  project.gates[2] = { id: "G2", status: "pass", reason: "protocol frozen · human sign (SIM)" };
  project.messages.push(system("G2 人签（SIM）· protocol frozen · 结果槽仍 pending"));
  project.messages.push(agent("协议已冻结。现在可以运行 3 seeds；EA 会绑定这次 run。"));
  saveAndRender();
  toast("G2 已冻结（SIM）");
}

function runExperiment() {
  const project = currentProject();
  if (!project.protocol) return designExperiment();
  if (!project.protocolFrozen) {
    project.messages.push(agent("先处理 G2：协议还没有冻结。冻结后才能运行；这是为了确保结果不是事后改参数。", gateCard("G2")));
    saveAndRender();
    scrollThread();
    return;
  }
  project.mode = "experiment";
  project.stage = 4;
  markStage(project, 3);
  markStage(project, 4);
  project.budget.used = Math.min(project.budget.total, project.budget.used + 6);
  project.run = { id: "RUN-014", mean: 412, baseline: 286, seeds: 3 };
  project.gates[3] = { id: "S5", status: "needs_human", reason: "EA sealed · claim unsigned" };
  project.gates[4] = { id: "G5", status: "blocked", reason: "Claim / Closure 未完成" };
  project.status = "blocked";
  project.evidence = project.evidence.filter((item) => item.type !== "claim" && item.type !== "EA");
  project.evidence.push({ id: "EA-7c41", type: "EA", status: "sealed", text: "T80 mean 412h vs baseline 286h; 3 seeds.", scope: "S5/demo/perovskite", refs: ["RUN-014"], note: "EA 绑定 metrics 哈希，不可原地修改。" });
  project.messages.push(user("运行协议，3 seeds。"));
  project.messages.push(system("run.work · RUN-014 · queued → completed (SIM)"));
  project.messages.push(agent("RUN-014 完成：T80 412h vs 对照 286h；EA 已封存。claim 仍未签，所以结果槽不能填。", runCard(project.run)));
  saveAndRender();
  scrollThread();
}

function signGate() {
  const project = currentProject();
  if (!project.run) return runExperiment();
  project.evidence = project.evidence.filter((item) => item.type !== "claim");
  project.evidence.push({ id: "CLM-9a2c", type: "claim", status: "supported", text: "双分子钝化层在该协议下延长 T80，且初始 PCE 不劣化。", scope: "S5/demo/perovskite", refs: ["EA-7c41", "RUN-014"], note: "SIM 人签；真实系统需 CLI/人工签署。" });
  project.gates[3] = { id: "S5", status: "pass", reason: "claim signed (SIM) · EA linked" };
  project.gates[4] = { id: "G5", status: "blocked", reason: "closure: citation.related pending" };
  project.status = "blocked";
  project.messages.push(system("HUMAN SIGN (SIM) · CLM-9a2c · scope S5/demo/perovskite"));
  project.messages.push(agent("Claim 已签（SIM）。它只覆盖这一次 run；closure 仍因引用槽未完成而 blocked。", card("summary", {
    title: "Closure 9/11",
    rows: [["Claim", "CLM-9a2c · supported"], ["EA", "EA-7c41 · sealed"], ["Closure", "blocked · citation.related"], ["Export", "closed"]]
  }, [{ label: "查看证据", action: "show-evidence", quiet: true }])));
  saveAndRender();
  scrollThread();
}

function startAuto() {
  const project = currentProject();
  if (project.auto.running) return toast("全自动已在运行。");
  if (project.auto.gate) return toast("先处理人工门，不能跳过。");
  if (project.evolution.candidate?.status === "pending") return toast("先审批自进化候选，再开始下一轮。");
  project.mode = "auto";
  project.auto = { running: true, paused: false, index: 0, gate: "", cycle: (project.auto.cycle || 0) + 1, gateApproved: false };
  project.status = "active";
  project.messages.push(system(`AUTO STARTED · cycle ${project.auto.cycle} · ${project.harness.version} · budget ${project.harness.budget} (SIM)`));
  project.messages.push(agent("全自动开始。我会逐阶段推进，遇到人工门会停下来；你随时可以暂停或单步。"));
  saveAndRender();
  scrollThread();
  scheduleAuto();
}

function scheduleAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = setInterval(() => autoStep(false), AUTO_MS);
}

function applyPendingGuidance(project) {
  const item = (project.guidance || []).find((entry) => entry.status === "queued");
  if (!item) return null;
  item.status = "applied";
  item.appliedAt = now();
  project.messages.push(system(`GUIDANCE APPLIED · ${item.id} · ${item.text}`));
  return item;
}

function autoStep(manual) {
  const project = currentProject();
  if (!project.auto.running) {
    if (manual) startAuto();
    return;
  }
  if (project.auto.gate) {
    if (manual) toast("先处理人工门；系统不会自动跳过。");
    return;
  }
  if (project.auto.paused && !manual) return;
  if (project.auto.index >= AUTO_STAGES.length) return finishAuto();
  if (project.auto.paused && manual) project.auto.paused = false;
  const item = AUTO_STAGES[project.auto.index];
  if (item.gate && !project.auto.gateApproved) {
    project.auto.paused = true;
    project.auto.gate = item.gate;
    project.stage = item.stage;
    project.status = "blocked";
    project.messages.push(agent(`到达人工门：${item.output}。系统不会自动签署；请选择“模拟签核”或保持 pending。`, gateCard("claim")));
    saveAndRender();
    scrollThread();
    toast("已暂停在人工门");
    return;
  }
  const appliedGuidance = applyPendingGuidance(project);
  const carriedGuidance = project.auto.guidanceNote || "";
  project.auto.guidanceNote = "";
  const guidanceText = appliedGuidance ? appliedGuidance.text : carriedGuidance;
  const output = guidanceText ? `${item.output} · 已按指导：${guidanceText}` : item.output;
  project.stage = item.stage;
  if (!item.gate) markStage(project, item.stage);
  project.budget.used = Math.min(project.budget.total, project.budget.used + 2);
  if (item.stage === 2) {
    project.protocol = {
      hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
      baseline: "未钝化对照",
      metric: "T80（小时）· 初始 PCE",
      seeds: 3
    };
    project.protocolFrozen = true;
    project.gates[2] = { id: "G2", status: "pass", reason: "protocol frozen (SIM)" };
  }
  if (item.stage === 3) {
    project.run = { id: "RUN-014", mean: 412, baseline: 286, seeds: 3 };
    project.evidence = project.evidence.filter((evidence) => evidence.type !== "EA");
    project.evidence.push({ id: "EA-7c41", type: "EA", status: "sealed", text: "T80 mean 412h vs baseline 286h; 3 seeds.", scope: "S5/demo/perovskite", refs: ["RUN-014"], note: "EA 绑定 metrics 哈希，不可原地修改。" });
    project.gates[3] = { id: "S5", status: "needs_human", reason: "EA sealed · claim unsigned" };
  }
  project.messages.push(agent(output, card("stage", { ...item, output, note: `${project.harness.version} · ${manual ? "单步" : "自动"} · SIM${guidanceText ? " · guided" : ""}` })));
  project.auto.index += 1;
  if (project.auto.index >= AUTO_STAGES.length) {
    finishAuto();
  } else {
    saveAndRender();
    scrollThread();
  }
}

function finishAuto() {
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  const project = currentProject();
  project.auto.running = false;
  project.auto.paused = false;
  project.auto.gate = "";
  project.stage = 8;
  [0, 1, 2, 3, 4, 5, 6, 7, 8].forEach((index) => markStage(project, index));
  project.status = "blocked";
  const candidate = makeCandidate(project);
  project.evolution.candidate = candidate;
  project.evolution.status = "pending";
  project.messages.push(agent("循环结束。自进化提案已生成；它不是 claim，必须通过 EV1–EV4 与人签租约才会在下一轮加载。", evolutionCard(project)));
  activeContext = "evolution";
  saveAndRender();
  scrollThread();
  toast("自进化候选等待审批");
}

function makeCandidate(project) {
  const cycle = project.auto.cycle || 1;
  const isSecond = project.harness.version !== "v1";
  const candidate = isSecond ? {
    id: `CAND-PF-${String(cycle).padStart(2, "0")}`,
    target: "process.literature.read_order",
    patch: "broad-first  →  deep-read top-2 → broad",
    rationale: "上一轮 span yield 12/4 sources；先深读高相关来源可减少无效阅读。",
    predicted: "span yield +2; retrieval cost +1",
    lease: "S1/perovskite · TTL 30d",
    ev: [{ label: "EV1", value: "reason", ok: true }, { label: "EV2", value: "held-out", ok: true }, { label: "EV3", value: "transfer?", ok: false }, { label: "EV4", value: "pending", ok: false }]
  } : {
    id: `CAND-S1-${String(cycle).padStart(2, "0")}`,
    target: "literature.retrieval.budget",
    patch: "budget 6 → 3 sources",
    rationale: "上一轮 4 篇全文中只有 2 篇贡献了有效 span；降低成本而不降覆盖。",
    predicted: "cost −40%; recall non-inferior",
    lease: "S1/perovskite · TTL 30d",
    ev: [{ label: "EV1", value: "reason", ok: true }, { label: "EV2", value: "scope", ok: true }, { label: "EV3", value: "near-OOD", ok: true }, { label: "EV4", value: "cost −40%", ok: true }]
  };
  return { ...candidate, status: "pending", created: now() };
}

function signAutoGate() {
  const project = currentProject();
  if (!project.auto.running) return signGate();
  if (project.auto.gate !== "claim") return toast("当前没有 claim 人工门。");
  signGate();
  project.auto.gateApproved = true;
  project.auto.gate = "";
  project.auto.paused = false;
  project.auto.index = Math.max(project.auto.index + 1, 0);
  markStage(project, 4);
  project.messages.push(system("HUMAN GATE CLEARED (SIM) · 自动继续后续阶段"));
  saveAndRender();
  scheduleAuto();
  toast("人工门已清（SIM）");
}

function pauseAuto(silent = false) {
  const project = currentProject();
  if (!project.auto.running) return;
  project.auto.paused = true;
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  if (!silent) {
    project.messages.push(system("AUTO PAUSED · 可继续或单步"));
    saveAndRender();
    toast("已暂停");
  }
}

function resumeAuto() {
  const project = currentProject();
  if (!project.auto.running) return startAuto();
  if (project.auto.gate) return toast("先处理人工门。");
  project.auto.paused = false;
  project.messages.push(system("AUTO RESUMED"));
  saveAndRender();
  scheduleAuto();
  toast("继续运行");
}

function stepAuto() {
  const project = currentProject();
  if (!project.auto.running) {
    startAuto();
    return;
  }
  if (project.auto.gate) return toast("先处理人工门；系统不会自动跳过。");
  if (project.auto.paused) project.auto.paused = false;
  autoStep(true);
  toast("已单步推进");
}

function stopAuto() {
  const project = currentProject();
  if (!project.auto.running) return;
  project.auto.running = false;
  project.auto.paused = true;
  project.auto.gate = "";
  if (autoTimer) clearInterval(autoTimer);
  autoTimer = null;
  project.messages.push(system("AUTO STOPPED · 未完成阶段保持阻塞；不会写 claim"));
  saveAndRender();
  toast("已停止");
}

function approveCandidate() {
  const project = currentProject();
  const candidate = project.evolution.candidate;
  if (!candidate || candidate.status !== "pending") return;
  candidate.status = "active";
  project.harness = {
    version: project.harness.version === "v1" ? "v2" : "v3",
    budget: project.harness.version === "v1" ? 3 : 4,
    label: candidate.target
  };
  project.evolution.status = "active";
  project.status = "active";
  project.evolution.lease = { id: "LEASE-" + uid("x").slice(-6), ttl: "30d", scope: "S1/perovskite" };
  project.evolution.history.push({ at: now(), version: project.harness.version, status: "active" });
  project.messages.push(system("LEASE ISSUED (SIM) · " + project.evolution.lease.id));
  project.messages.push(agent(`候选已准入（SIM）。下一轮会加载 ${project.harness.version}：${candidate.patch}。租约到期或撤销后只回退该阶段。`));
  saveAndRender();
  scrollThread();
  toast("候选已批准（SIM）");
}

function rejectCandidate() {
  const project = currentProject();
  const candidate = project.evolution.candidate;
  if (!candidate || candidate.status !== "pending") return;
  candidate.status = "rejected";
  project.evolution.status = "rejected";
  project.evolution.lease = null;
  project.evolution.history.push({ at: now(), version: project.harness.version, status: "rejected" });
  project.messages.push(system("CANDIDATE REJECTED · negative result kept"));
  project.messages.push(agent("候选被拒绝，负结果保留；不会重试同一条没有新证据的提案。"));
  saveAndRender();
  scrollThread();
  toast("已拒绝，负结果保留");
}

function rollbackHarness() {
  const project = currentProject();
  if (!project.evolution.lease) return toast("没有 active lease。");
  const old = project.harness.version;
  project.harness = { version: "v1", budget: 6, label: "incumbent · broad-first" };
  project.evolution.status = "revoked";
  if (project.evolution.candidate) project.evolution.candidate.status = "revoked";
  project.evolution.history.push({ at: now(), version: "v1", status: "revoked" });
  project.evolution.lease = null;
  project.messages.push(system(`LEASE REVOKED · ${old} → v1 · dependent artifacts require review`));
  project.messages.push(agent("租约已撤销（SIM）。回滚不等于修复：依赖该 harness 的产物需要重新复核。"));
  saveAndRender();
  scrollThread();
  toast("已回滚到 v1");
}

function dismissGate() {
  const project = currentProject();
  project.messages.push(system("人工门保持 pending · 导出仍 blocked"));
  saveAndRender();
  toast("保持 pending");
}

function showContext(tab) {
  activeContext = tab;
  const context = $(".ag-context");
  if (context) context.classList.add("is-open");
  renderContext();
  if (window.innerWidth > 960) context?.classList.remove("is-open");
}

function handleSuggestion(text) {
  if (text === "扩展检索") return runResearch();
  if (text === "把 gap 变成假设") return designExperiment();
  if (text === "查看证据链" || text === "查看 EA" || text === "查看证据") return showContext("evidence");
  if (text === "冻结协议") return freezeProtocol();
  if (text === "运行 2 seeds") return runExperiment();
  if (text === "插入指导") { focusComposer(); return toast("直接输入指导；会在下一阶段应用，不改 claim/EA/gate。"); }
  if (text === "启动全自动" || text === "启动受治理全自动" || text === "再跑一轮") return startAuto();
  if (text === "单步") return stepAuto();
  if (text === "暂停") return pauseAuto();
  if (text === "继续") return resumeAuto();
  if (text === "停止") return stopAuto();
  if (text === "模拟签核") return currentProject().auto.running ? signAutoGate() : signGate();
  if (text === "保持 pending") return dismissGate();
  if (text === "批准候选") return approveCandidate();
  if (text === "拒绝并保留负结果") return rejectCandidate();
  if (text === "撤销租约") return rollbackHarness();
  $("#composer-input").value = text;
  focusComposer();
}

function sendMessage() {
  const input = $("#composer-input");
  const text = input.value.trim();
  if (!text) return;
  if (text.startsWith("/")) {
    input.value = "";
    runCommand(text);
    return;
  }
  input.value = "";
  const project = currentProject();
  project.messages.push(user(text));
  saveAndRender();
  scrollThread();
  respondTo(text);
}

function queueGuidance(text, kind = "note") {
  const project = currentProject();
  const item = {
    id: uid("GUIDE"),
    text: text.trim(),
    kind,
    scope: "next_checkpoint",
    status: "queued",
    at: now()
  };
  project.guidance = project.guidance || [];
  project.guidance.push(item);
  project.messages.push(agent(
    `收到指导（${item.id}）。它会在下一个检查点应用；只改执行策略，不改 claim/EA/gate。`,
    card("guidance", item)
  ));
  saveAndRender();
  toast("指导已入队，等待下一检查点");
}

function applyGuidanceById(id) {
  const project = currentProject();
  const item = (project.guidance || []).find((entry) => entry.id === id);
  if (!item || item.status !== "queued") return;
  item.status = "applied";
  item.appliedAt = now();
  project.auto.guidanceNote = item.text;
  project.messages.push(system(`GUIDANCE APPLIED · ${item.id} · ${item.text}`));
  saveAndRender();
  toast("指导已应用；下一阶段会显示生效说明");
}

function dismissGuidanceById(id) {
  const project = currentProject();
  const item = (project.guidance || []).find((entry) => entry.id === id);
  if (!item || item.status !== "queued") return;
  item.status = "dismissed";
  project.messages.push(system(`GUIDANCE DISMISSED · ${item.id}`));
  saveAndRender();
  toast("指导已丢弃");
}

function guidanceStatusReply() {
  const project = currentProject();
  const queued = (project.guidance || []).filter((item) => item.status === "queued").length;
  const stage = STAGES[Math.min(project.stage, STAGES.length - 1)];
  project.messages.push(agent(
    `当前 S${project.stage + 1}/9 · ${stage[1]} · ${project.auto.running ? (project.auto.paused ? "已暂停" : "运行中") : "未运行"} · ${queued} 条待应用指导。`,
    card("summary", {
      title: "RUN STATUS",
      rows: [
        ["stage", `S${project.stage + 1} · ${stage[1]}`],
        ["state", project.auto.running ? (project.auto.paused ? "paused" : "running") : "idle"],
        ["guidance", `${queued} queued`],
        ["gate", project.auto.gate || "none"]
      ]
    })
  ));
  saveAndRender();
}

function respondTo(text) {
  const project = currentProject();
  const lower = text.toLowerCase();
  const projectMode = project.mode;
  if (/(github|mcp)/i.test(text) && /(issue|pull|pr|repo|仓库|问题|查)/i.test(text)) {
    return proposeGithubCall(text);
  }
  if (projectMode === "auto") {
    if (/启动|开始|start|run/.test(lower)) return startAuto();
    if (/暂停|pause|停一下/.test(lower)) return pauseAuto();
    if (/继续|恢复|resume/.test(lower)) return resumeAuto();
    if (/单步|step|下一步/.test(lower)) return stepAuto();
    if (/签核|签署|approve|sign/.test(lower)) {
      if (project.auto.gate) return signAutoGate();
      return toast("当前没有 claim 人工门。");
    }
    if (/进展|状态|到哪|为什么|卡在|status|where/.test(lower)) return guidanceStatusReply();
    if (project.auto.running || project.auto.gate) {
      const kind = /优先|只看|只保留|不要|重点|补充|换|限定|focus|only|prioritize|exclude/.test(lower) ? "constraint" : "note";
      return queueGuidance(text, kind);
    }
  }
  if (projectMode === "experiment") {
    if (/运行|run|执行|seeds/.test(lower)) return runExperiment();
    if (/冻结|freeze|协议/.test(lower)) return freezeProtocol();
    if (/claim|签/.test(lower)) return signGate();
  }
  if (projectMode === "research" && /检索|文献|调研|source|span/i.test(lower)) {
    return runResearch();
  }
  const reply = projectMode === "research"
    ? "我先把问题收敛成可检索的子问题。你可以让我“扩展检索”、把 gap 变成假设，或切到实验模式。当前我不会生成 claim；文献句只认可定位 span。"
    : projectMode === "experiment"
      ? "实验模式只处理已冻结的协议。你可以“冻结协议”或“运行 2 seeds”；结果槽会保持 pending，直到 EA 与人签 claim。"
      : "全自动会在人工门停下。输入“启动全自动”开始，或用“暂停/单步”控制；候选通过 EV1–EV4 与人签租约才会进入下一轮。";
  project.messages.push(agent(reply));
  saveAndRender();
  scrollThread();
}

function runCommand(command) {
  const [name, ...rest] = command.trim().split(/\s+/);
  const arg = rest.join(" ");
  const commandMap = {
    "/research": () => setMode("research"),
    "/experiment": () => setMode("experiment"),
    "/auto": () => setMode("auto"),
    "/start": () => startAuto(),
    "/pause": () => pauseAuto(),
    "/resume": () => resumeAuto(),
    "/step": () => stepAuto(),
    "/stop": () => stopAuto(),
    "/evidence": () => showContext("evidence"),
    "/evolution": () => showContext("evolution"),
    "/run": () => runExperiment(),
    "/freeze": () => freezeProtocol(),
    "/sign": () => signGate(),
    "/approve": () => approveCandidate(),
    "/reject": () => rejectCandidate(),
    "/rollback": () => rollbackHarness(),
    "/model": () => openModelDialog(),
    "/tools": () => openTools(),
    "/plugins": () => openPlugins(),
    "/github": () => proposeGithubCall("GitHub issues research-agent"),
    "/new": () => openNewProject(),
    "/export": () => exportState(),
    "/reset": () => resetState(),
    "/help": () => {
      var list = document.getElementById("dl-command-list");
      if (list) {
        list.open = true;
        if (list.scrollIntoView) list.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      toast("已展开「可用指令」清单：每条都有中文说明，输入 / 加指令名即可调用");
    },
    "/task": () => {
      if (arg) { $("#composer-input").value = arg; sendMessage(); }
    }
  };
  const run = commandMap[name.toLowerCase()];
  if (run) { run(); return; }
  toast("未知指令：" + name + "。输入 /help 查看。");
}

function focusComposer() {
  const input = $("#composer-input");
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}

function scrollThread() {
  if (!state.preferences.autoScroll) return;
  const thread = $("#ag-thread");
  requestAnimationFrame(() => { thread.scrollTop = thread.scrollHeight; });
}

function openNewProject() {
  const select = $("#np-workspace");
  if (select) {
    select.innerHTML = WORKSPACES.map((workspace) => `<option value="${esc(workspace.id)}">${esc(workspace.name)} · ${esc(workspace.note)}</option>`).join("");
    select.value = state.activeWorkspaceId || "materials";
  }
  const dialog = $("#new-project-dialog");
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  setTimeout(() => $("#np-name").focus(), 30);
}

function closeNewProject() {
  const dialog = $("#new-project-dialog");
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

function createFromDialog(event) {
  event.preventDefault();
  const name = $("#np-name").value.trim();
  const goal = $("#np-goal").value.trim();
  if (!name || !goal) return toast("项目名与研究目标必填。");
  const project = createProject({
    name,
    goal,
    domain: $("#np-domain").value,
    mode: $("#np-mode").value,
    workspaceId: $("#np-workspace").value
  });
  state.projects.unshift(project);
  state.selectedProjectId = project.id;
  state.activeWorkspaceId = project.workspaceId;
  closeNewProject();
  $("#new-project-form").reset();
  activeContext = "run";
  saveAndRender();
  toast("任务已创建（本地静态状态）");
}

function exportState() {
  const payload = JSON.stringify(state, null, 2);
  const blob = new Blob([payload], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "research-agent-workspace.json";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  toast("已导出本地状态 JSON");
}

function resetState() {
  if (!window.confirm("重置所有本地项目与会话？此操作只影响浏览器 localStorage，不会影响仓库。")) return;
  try { localStorage.removeItem(STORAGE_KEY); } catch (_) {}
  if (autoTimer) clearInterval(autoTimer);
  state = seedState();
  activeContext = "run";
  saveAndRender();
  toast("已重置到示例项目");
}

function toast(text) {
  const node = $("#toast");
  node.textContent = text;
  node.classList.add("is-on");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("is-on"), 2200);
}

/* ---------- command palette ---------- */

function paletteData() {
  return [
    { label: "新建对话", meta: "CONVERSATION", action: "new-project" },
    { label: "设置与工具", meta: "VERSION / PERSONALIZATION", action: "tools" },
    { label: "插件与 MCP", meta: "GITHUB / TOOLS", action: "plugins" },
    { label: "模型设置", meta: "CTX / THINKING / COMPRESSION", action: "model-settings" },
    { label: "调研模式", meta: "/research", action: "mode-research" },
    { label: "实验模式", meta: "/experiment", action: "mode-experiment" },
    { label: "全自动模式", meta: "/auto", action: "mode-auto" },
    { label: "启动全自动", meta: "/start", action: "start-auto" },
    { label: "暂停 / 继续", meta: "SPACE", action: "toggle-auto" },
    { label: "单步推进", meta: "/step", action: "step-auto" },
    { label: "查看证据", meta: "/evidence", action: "show-evidence" },
    { label: "查看自进化", meta: "/evolution", action: "show-evolution" },
    { label: "批准候选", meta: "/approve", action: "approve-candidate" },
    { label: "回滚 harness", meta: "/rollback", action: "rollback-harness" },
    { label: "导出状态", meta: "/export", action: "export-state" },
    { label: "重置示例", meta: "/reset", action: "reset-state" }
  ];
}

function openPalette() {
  $("#palette").hidden = false;
  paletteIndex = 0;
  $("#palette-input").value = "";
  paletteItems = paletteData();
  renderPalette();
  $("#palette-input").focus();
}

function closePalette() {
  $("#palette").hidden = true;
}

function renderPalette() {
  const query = $("#palette-input").value.trim().toLowerCase();
  paletteItems = paletteData().filter((item) => !query || (item.label + " " + item.meta).toLowerCase().includes(query));
  if (paletteIndex >= paletteItems.length) paletteIndex = Math.max(0, paletteItems.length - 1);
  $("#palette-list").innerHTML = paletteItems.length
    ? paletteItems.map((item, index) => `<button type="button" class="ag-palette-item ${index === paletteIndex ? "is-on" : ""}" data-palette-index="${index}"><b>${esc(item.label)}</b><span>${esc(item.meta)}</span></button>`).join("")
    : '<div class="ag-context-empty">没有匹配动作。</div>';
  $$("[data-palette-index]").forEach((button) => button.addEventListener("click", () => runPaletteItem(Number(button.dataset.paletteIndex))));
}

function runPaletteItem(index) {
  const item = paletteItems[index];
  if (!item) return;
  closePalette();
  const map = {
    "new-project": openNewProject,
    "tools": openTools,
    "plugins": openPlugins,
    "model-settings": openModelDialog,
    "mode-research": () => setMode("research"),
    "mode-experiment": () => setMode("experiment"),
    "mode-auto": () => setMode("auto"),
    "start-auto": startAuto,
    "toggle-auto": () => currentProject().auto.running ? (currentProject().auto.paused ? resumeAuto() : pauseAuto()) : startAuto(),
    "step-auto": stepAuto,
    "show-evidence": () => showContext("evidence"),
    "show-evolution": () => showContext("evolution"),
    "approve-candidate": approveCandidate,
    "rollback-harness": rollbackHarness,
    "export-state": exportState,
    "reset-state": resetState
  };
  (map[item.action] || (() => {}))();
}

/* ---------- bindings ---------- */

function bind() {
  $("#project-select").addEventListener("change", (event) => selectProject(event.target.value));
  $$(".ag-mode").forEach((button) => button.addEventListener("click", () => setMode(button.dataset.mode)));
  $$(".ag-quick").forEach((button) => button.addEventListener("click", () => {
    const mode = button.dataset.quick;
    if (mode === "auto") { setMode("auto"); startAuto(); return; }
    setMode(mode);
  }));
  $$(".ag-ctx-tab").forEach((button) => button.addEventListener("click", () => showContext(button.dataset.context)));
  $("#send-btn").addEventListener("click", sendMessage);
  $("#composer-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  });
  $("#ag-thread").addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    runAction(button.dataset.action, button.dataset.arg);
  });
  $("#context-body").addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    runAction(button.dataset.action, button.dataset.arg);
  });
  $("#new-project-btn").addEventListener("click", openNewProject);
  $("#close-dialog").addEventListener("click", closeNewProject);
  $("#cancel-dialog").addEventListener("click", closeNewProject);
  $("#new-project-form").addEventListener("submit", createFromDialog);
  $("#export-btn").addEventListener("click", exportState);
  $("#new-task-btn").addEventListener("click", openNewProject);
  $("#tasks-btn").addEventListener("click", () => $(".ag-side").classList.toggle("is-mobile-open"));
  $("#task-search").addEventListener("input", renderProjects);
  $$("[data-utility]").forEach((button) => button.addEventListener("click", () => {
    if (button.dataset.utility === "site") window.open("../", "_blank", "noopener");
    else if (button.dataset.utility === "auto") setMode("auto");
    else if (button.dataset.utility === "plugins") openPlugins();
    else openTools();
  }));
  $("#tools-btn").addEventListener("click", () => $("#tools-panel").hidden ? openTools() : closeTools());
  $("#tools-close").addEventListener("click", closeTools);
  $("#tools-model").addEventListener("click", () => { closeTools(); openModelDialog(); });
  $("#tools-plugins").addEventListener("click", () => { closeTools(); openPlugins(); });
  $("#tools-export").addEventListener("click", () => { closeTools(); exportState(); });
  $("#plugin-btn").addEventListener("click", () => $("#plugin-drawer").hidden ? openPlugins() : closePlugins());
  $("#plugin-close").addEventListener("click", closePlugins);
  $("#plugin-preset").addEventListener("change", syncPluginForm);
  $("#plugin-form").addEventListener("submit", addPlugin);
  $("#plugin-test").addEventListener("click", () => {
    toast("仅说明：这里只展示端点登记示例，不会发起真实连接；真实连接需本地 runtime + OAuth/token");
  });
  $("#tools-reset").addEventListener("click", () => { closeTools(); resetState(); });
  $("#pref-auto-expand").addEventListener("change", (event) => setPreference("autoExpandRunning", event.target.checked));
  $("#pref-auto-scroll").addEventListener("change", (event) => setPreference("autoScroll", event.target.checked));
  $("#pref-reduce-motion").addEventListener("change", (event) => setPreference("reduceMotion", event.target.checked));
  document.addEventListener("click", (event) => {
    if (!$("#tools-panel").hidden) {
      if (!event.target.closest("#tools-panel") && !event.target.closest("#tools-btn") && !event.target.closest("#palette")) closeTools();
    }
    if (!$("#plugin-drawer").hidden) {
      if (!event.target.closest("#plugin-drawer") && !event.target.closest("#plugin-btn") && !event.target.closest("#tools-plugins")) closePlugins();
    }
    if ($(".ag-side").classList.contains("is-mobile-open")) {
      if (!event.target.closest(".ag-side") && !event.target.closest("#tasks-btn")) $(".ag-side").classList.remove("is-mobile-open");
    }
  });
  $("#model-btn").addEventListener("click", openModelDialog);
  $("#model-close").addEventListener("click", closeModelDialog);
  $("#model-cancel").addEventListener("click", closeModelDialog);
  $("#model-form").addEventListener("submit", saveModelSettings);
  $("#ms-context").addEventListener("input", (event) => {
    if (!modelDraft) return;
    modelDraft.contextLimit = Number(event.target.value);
    updateModelPreview();
  });
  $("#ms-reply").addEventListener("input", (event) => {
    if (!modelDraft) return;
    modelDraft.maxReply = Number(event.target.value);
    updateModelPreview();
  });
  $("#ms-thinking").addEventListener("input", (event) => {
    if (!modelDraft) return;
    const profile = profileById(modelDraft.profileId);
    const stop = (profile.stops || [])[Number(event.target.value)];
    if (stop) modelDraft.thinkingStop = stop.value;
    updateModelPreview();
  });
  $("#ms-threshold").addEventListener("input", (event) => {
    if (!modelDraft) return;
    modelDraft.threshold = Number(event.target.value) / 100;
    updateModelPreview();
  });
  $("#ms-keep").addEventListener("input", (event) => {
    if (!modelDraft) return;
    modelDraft.keepRecent = Math.max(2, Math.min(20, Number(event.target.value) || 2));
    updateModelPreview();
  });
  $("#ms-summary").addEventListener("input", (event) => {
    if (!modelDraft) return;
    modelDraft.summaryTokens = Math.max(256, Math.min(4096, Number(event.target.value) || 256));
    updateModelPreview();
  });
  $$("[data-compression]").forEach((button) => button.addEventListener("click", () => {
    if (!modelDraft) return;
    modelDraft.compression = button.dataset.compression;
    if (modelDraft.compression === "off") modelDraft.threshold = 1;
    else if (modelDraft.compression === "aggressive") modelDraft.threshold = 0.55;
    else if (modelDraft.threshold >= 1) modelDraft.threshold = 0.7;
    renderModelDialog();
  }));
  $("#palette-btn").addEventListener("click", openPalette);
  $("#palette-input").addEventListener("input", () => { paletteIndex = 0; renderPalette(); });
  $("#palette-input").addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") { event.preventDefault(); paletteIndex = Math.min(paletteIndex + 1, paletteItems.length - 1); renderPalette(); }
    if (event.key === "ArrowUp") { event.preventDefault(); paletteIndex = Math.max(0, paletteIndex - 1); renderPalette(); }
    if (event.key === "Enter") { event.preventDefault(); runPaletteItem(paletteIndex); }
    if (event.key === "Escape") closePalette();
  });
  $$("[data-close-palette]").forEach((node) => node.addEventListener("click", closePalette));
  $("#context-toggle").addEventListener("click", () => {
    const context = $(".ag-context");
    context.classList.toggle("is-open");
  });
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openPalette();
      return;
    }
    if (event.key === "Escape") {
      closePalette();
      $(".ag-context").classList.remove("is-open");
      return;
    }
    if (event.key === "/" && !event.target.closest("input, textarea, select")) {
      event.preventDefault();
      focusComposer();
      return;
    }
    if (event.key === " " && !event.target.closest("input, textarea, select") && currentProject().auto.running) {
      event.preventDefault();
      currentProject().auto.paused ? resumeAuto() : pauseAuto();
    }
  });
}

function runAction(action, arg) {
  const project = currentProject();
  switch (action) {
    case "run-research": return runResearch();
    case "design-experiment": return designExperiment();
    case "freeze-protocol": return freezeProtocol();
    case "run-experiment": return runExperiment();
    case "sign-claim-gate": return signGate();
    case "sign-gate": return project.auto.running || project.auto.gate ? signAutoGate() : signGate();
    case "dismiss-gate": return dismissGate();
    case "start-auto": return startAuto();
    case "pause-auto": return pauseAuto();
    case "resume-auto": return resumeAuto();
    case "step-auto": return stepAuto();
    case "stop-auto": return stopAuto();
    case "approve-candidate": return approveCandidate();
    case "reject-candidate": return rejectCandidate();
    case "rollback-harness": return rollbackHarness();
    case "show-evidence": return showContext("evidence");
    case "show-evolution": return showContext("evolution");
    case "open-plugins": return openPlugins();
    case "approve-tool": return approveToolCall(arg);
    case "deny-tool": return denyToolCall(arg);
    case "apply-guidance": return applyGuidanceById(arg);
    case "dismiss-guidance": return dismissGuidanceById(arg);
    case "show-run": return showContext("run");
    case "focus-composer": return focusComposer();
    case "toggle-auto": return project.auto.running ? (project.auto.paused ? resumeAuto() : pauseAuto()) : startAuto();
    default: return toast("该动作在静态预览中不可用，不会改动数据；可用动作见页面底部「可用指令」清单。");
  }
}

function init() {
  state = loadState();
  bind();
  renderAll();
  if (currentProject().auto.running) {
    // A persisted "running" state is not resumed silently; make it paused and explicit.
    currentProject().auto.running = false;
    currentProject().auto.paused = true;
    save();
    renderAll();
  }
}

init();

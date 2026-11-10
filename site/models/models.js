"use strict";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const MODULES = [
  ["literature", "文献调研", "S1"],
  ["idea", "假设收敛", "S2–S3"],
  ["experiment", "实验设计", "S4"],
  ["paper", "论文契约", "S8–S12"],
  ["rsi", "RSI 提案器", "META"],
];
const KIND_LABEL = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  openai_compatible: "OpenAI 兼容",
  azure_openai: "Azure OpenAI",
};
const DEFAULT_BASE = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  openai_compatible: "http://127.0.0.1:11434/v1",
  azure_openai: "https://<resource>.openai.azure.com/openai/deployments/<deployment>",
};
const state = {
  api: "http://127.0.0.1:8787",
  online: false,
  snapshot: null,
  selectedProvider: "",
  selectedProfile: "",
  creatingProvider: false,
  creatingProfile: false,
};

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function apiUrl(path) {
  return state.api.replace(/\/+$/, "") + path;
}

async function jsonFetch(path, options = {}, timeout = 12000) {
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
    try { data = text ? JSON.parse(text) : {}; } catch (_) { data = {}; }
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || response.statusText);
      throw new Error(detail || "HTTP " + response.status);
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
  const chip = $("#conn-chip");
  chip.dataset.state = status;
  chip.innerHTML = "<i></i>" + esc(text);
}

function banner(text, ok = false) {
  const node = $("#banner");
  node.hidden = !text;
  node.textContent = text || "";
  node.classList.toggle("ok", ok);
}

function providerStatus(provider) {
  if (!provider.configured) return { text: "NO KEY", cls: "bad" };
  return { text: "READY", cls: "ok" };
}

function kindLabel(kind) {
  return KIND_LABEL[kind] || kind;
}

function selectedProvider() {
  return (state.snapshot?.providers || []).find((item) => item.provider_id === state.selectedProvider) || null;
}

function selectedProfile() {
  return (state.snapshot?.profiles || []).find((item) => item.profile_id === state.selectedProfile) || null;
}

async function connect() {
  state.api = ($("#api-base").value || state.api).trim().replace(/\/+$/, "") || "http://127.0.0.1:8787";
  $("#api-base").value = state.api;
  try { localStorage.setItem("researchAgentModelApi", state.api); } catch (_) {}
  setChip("CHECKING", "checking");
  banner("");
  try {
    const health = await jsonFetch("/api/health", {}, 5000);
    if (!health.model_gateway) throw new Error("runtime 没有 model gateway");
    state.online = true;
    setChip("LIVE LOCAL", "ok");
    await loadSnapshot();
    await loadCalls();
  } catch (error) {
    state.online = false;
    setChip("OFFLINE", "bad");
    banner("未连接到本地 runtime：" + error.message + "。启动：python -m research_agent.runtime");
  }
}

async function loadSnapshot() {
  const snapshot = await jsonFetch("/api/models");
  state.snapshot = snapshot;
  const providers = snapshot.providers || [];
  const profiles = snapshot.profiles || [];
  if (!providers.some((item) => item.provider_id === state.selectedProvider)) {
    state.selectedProvider = providers[0]?.provider_id || "";
  }
  if (!profiles.some((item) => item.profile_id === state.selectedProfile)) {
    state.selectedProfile = profiles[0]?.profile_id || "";
  }
  renderAll();
  if (snapshot.store_warning) banner(snapshot.store_warning);
}

function renderAll() {
  renderProviders();
  renderProfileProviderOptions(state.selectedProvider);
  updateThinkingUI();
  renderProfiles();
  renderProbeProfiles();
  renderBindings();
  $("#provider-count").textContent = `${(state.snapshot?.providers || []).length} providers`;
  $("#profile-count").textContent = `${(state.snapshot?.profiles || []).length} profiles`;
  $("#binding-count").textContent = `${Object.keys(state.snapshot?.bindings || {}).length} bound`;
}

function renderProviders() {
  const list = $("#provider-list");
  const providers = state.snapshot?.providers || [];
  if (!providers.length) {
    list.innerHTML = '<p class="mg-empty">没有 provider。</p>';
    return;
  }
  list.innerHTML = providers.map((provider) => {
    const status = providerStatus(provider);
    const active = provider.provider_id === state.selectedProvider ? " is-on" : "";
    return `
      <button type="button" class="provider-item${active}" data-provider="${esc(provider.provider_id)}">
        <span class="provider-main"><b>${esc(provider.label || provider.provider_id)}</b><span class="provider-tag ${status.cls}">${status.text}</span></span>
        <span class="provider-meta">${esc(provider.provider_id)} · ${esc(kindLabel(provider.kind))} · ${esc(provider.base_url)}</span>
        <span class="provider-detail"><span>${(provider.models || []).length} models</span><span>${esc(provider.key_source || "missing")}</span><span>${esc(provider.masked_key || "")}</span></span>
      </button>`;
  }).join("");
  $$(".provider-item").forEach((node) => node.addEventListener("click", () => {
    state.selectedProvider = node.dataset.provider;
    state.creatingProvider = false;
    const provider = selectedProvider();
    if (provider) fillProviderForm(provider);
    renderProviders();
    renderProfileProviderOptions(provider?.provider_id || "");
    renderModelDatalist(provider?.provider_id || "");
  }));
  const provider = selectedProvider();
  if (provider && !state.creatingProvider && !$("#p-id").value) fillProviderForm(provider);
}

function fillProviderForm(provider) {
  $("#p-id").value = provider.provider_id;
  $("#p-id").disabled = true;
  $("#p-kind").value = provider.kind;
  $("#p-label").value = provider.label || "";
  $("#p-base").value = provider.base_url || "";
  $("#p-env").value = provider.api_key_env || "";
  $("#p-version").value = provider.api_version || "";
  $("#p-private").checked = Boolean(provider.allow_private_network);
  $("#p-models").value = (provider.models || []).join("\n");
  $("#p-key").value = "";
  $("#provider-hint").textContent = provider.configured
    ? `已配置 · ${provider.key_source} · ${provider.masked_key || ""} · 留空保持`
    : "未配置 · 填 key 或设置环境变量";
  $("#p-base").placeholder = DEFAULT_BASE[provider.kind] || "";
}

function resetProviderForm() {
  state.selectedProvider = "";
  state.creatingProvider = true;
  $("#p-id").disabled = false;
  $("#p-id").value = "";
  $("#p-kind").value = "openai";
  $("#p-label").value = "";
  $("#p-base").value = DEFAULT_BASE.openai;
  $("#p-env").value = "OPENAI_API_KEY";
  $("#p-version").value = "";
  $("#p-private").checked = false;
  $("#p-models").value = "";
  $("#p-key").value = "";
  $("#provider-hint").textContent = "新建 provider；key 留空则之后用环境变量";
  renderProviders();
}

function renderProfileProviderOptions(preferredProvider = "") {
  const select = $("#f-provider");
  const current = preferredProvider || select.value || selectedProfile()?.provider_id || "";
  select.innerHTML = (state.snapshot?.providers || []).map((provider) =>
    `<option value="${esc(provider.provider_id)}">${esc(provider.label || provider.provider_id)} · ${esc(kindLabel(provider.kind))}</option>`
  ).join("");
  if (current) select.value = current;
  renderModelDatalist(select.value);
}

function renderModelDatalist(providerId) {
  const provider = (state.snapshot?.providers || []).find((item) => item.provider_id === providerId);
  $("#model-options").innerHTML = (provider?.models || []).map((model) => `<option value="${esc(model)}"></option>`).join("");
}

function renderProfiles() {
  const list = $("#profile-list");
  const profiles = state.snapshot?.profiles || [];
  if (!profiles.length) {
    list.innerHTML = '<p class="mg-empty">暂无模型档案。先在右侧选择 provider 与 model。</p>';
    return;
  }
  list.innerHTML = profiles.map((profile) => {
    const provider = (state.snapshot?.providers || []).find((item) => item.provider_id === profile.provider_id);
    const active = profile.profile_id === state.selectedProfile ? " is-on" : "";
    const thinking = profile.thinking?.mode === "budget"
      ? `budget ${profile.thinking.budget_tokens || "?"}`
      : profile.thinking?.mode === "effort" ? `effort ${profile.thinking.effort}` : "off";
    return `
      <button type="button" class="profile-item${active}" data-profile="${esc(profile.profile_id)}">
        <span class="profile-main"><b>${esc(profile.label || profile.profile_id)}</b><span class="profile-tag ${provider?.configured ? "ok" : "bad"}">${provider?.configured ? "KEY READY" : "NO KEY"}</span></span>
        <span class="profile-meta">${esc(profile.profile_id)} · ${esc(profile.provider_id)} / ${esc(profile.model)}</span>
        <span class="profile-meta">${esc(thinking)} · ctx ${esc(profile.context_window ?? "—")} · out ${esc(profile.max_output_tokens ?? "—")} · max ${esc(profile.max_tokens)} · ${profile.json_mode ? "JSON" : "text"}</span>
      </button>`;
  }).join("");
  $$(".profile-item").forEach((node) => node.addEventListener("click", () => {
    state.selectedProfile = node.dataset.profile;
    state.creatingProfile = false;
    const profile = selectedProfile();
    if (profile) {
      fillProfileForm(profile);
      const provider = (state.snapshot?.providers || []).find((item) => item.provider_id === profile.provider_id);
      if (provider) {
        state.selectedProvider = provider.provider_id;
        fillProviderForm(provider);
      }
    }
    renderProviders();
    renderProfiles();
    renderProbeProfiles();
  }));
  const profile = selectedProfile();
  if (profile && !state.creatingProfile && !$("#f-id").value) fillProfileForm(profile);
}

function fillProfileForm(profile) {
  $("#f-id").value = profile.profile_id;
  $("#f-id").disabled = true;
  renderProfileProviderOptions();
  $("#f-provider").value = profile.provider_id;
  $("#f-model").value = profile.model;
  $("#f-label").value = profile.label || "";
  $("#f-thinking").value = profile.thinking?.mode || "off";
  $("#f-effort").value = profile.thinking?.effort || "medium";
  $("#f-budget").value = profile.thinking?.budget_tokens || "";
  $("#f-max").value = profile.max_tokens;
  $("#f-context").value = profile.context_window ?? 128000;
  $("#f-output").value = profile.max_output_tokens ?? 16384;
  $("#f-thinking-supported").checked = profile.thinking_supported !== false;
  $("#f-temperature").value = profile.temperature ?? "";
  $("#f-topp").value = profile.top_p ?? "";
  $("#f-json").checked = Boolean(profile.json_mode);
  $("#f-extra").value = Object.keys(profile.extra_body || {}).length ? JSON.stringify(profile.extra_body, null, 2) : "";
  updateThinkingUI();
  renderModelDatalist(profile.provider_id);
}

function resetProfileForm() {
  state.selectedProfile = "";
  state.creatingProfile = true;
  $("#f-id").disabled = false;
  $("#f-id").value = "";
  $("#f-model").value = "";
  $("#f-label").value = "";
  $("#f-thinking").value = "off";
  $("#f-effort").value = "medium";
  $("#f-budget").value = "";
  $("#f-max").value = "2048";
  $("#f-context").value = "128000";
  $("#f-output").value = "16384";
  $("#f-thinking-supported").checked = true;
  $("#f-temperature").value = "0.2";
  $("#f-topp").value = "";
  $("#f-json").checked = false;
  $("#f-extra").value = "";
  renderProfileProviderOptions();
  updateThinkingUI();
}

function updateThinkingUI() {
  const supported = $("#f-thinking-supported")?.checked !== false;
  const mode = $("#f-thinking").value;
  const providerId = $("#f-provider").value;
  const provider = (state.snapshot?.providers || []).find((item) => item.provider_id === providerId);
  const kind = provider?.kind || "openai";
  const budgetOption = $('#f-thinking option[value="budget"]');
  const budgetAllowed = supported && (kind === "anthropic" || kind === "openai_compatible");
  budgetOption.disabled = !budgetAllowed;
  $("#f-thinking").disabled = !supported;
  if (!supported) $("#f-thinking").value = "off";
  if (!budgetAllowed && mode === "budget") $("#f-thinking").value = "effort";
  $("#budget-field").hidden = $("#f-thinking").value !== "budget";
  $("#f-effort").disabled = !supported || $("#f-thinking").value === "off";
  $("#thinking-note").textContent = kind === "anthropic"
    ? "Anthropic：effort 会映射为 budget_tokens（low 1024 / medium 4096 / high 8192）；启用 thinking 时不发送 temperature/top_p。"
    : kind === "openai" || kind === "azure_openai"
      ? "OpenAI：使用 reasoning_effort；budget 模式不适用。启用 thinking 时省略 temperature/top_p，并使用 max_completion_tokens。"
      : "OpenAI 兼容：effort 会透传 reasoning_effort；budget 模式必须在 extra_body 中显式提供 enable_thinking/thinking_budget 等字段。";
  renderModelDatalist(providerId);
}

function renderProbeProfiles() {
  const select = $("#probe-profile");
  const profiles = state.snapshot?.profiles || [];
  const current = select.value || state.selectedProfile;
  select.innerHTML = profiles.map((profile) =>
    `<option value="${esc(profile.profile_id)}">${esc(profile.label || profile.profile_id)} · ${esc(profile.provider_id)}/${esc(profile.model)}</option>`
  ).join("");
  if (current && profiles.some((profile) => profile.profile_id === current)) select.value = current;
}

function renderBindings() {
  const list = $("#binding-list");
  const profiles = state.snapshot?.profiles || [];
  const bindings = state.snapshot?.bindings || {};
  const wired = state.snapshot?.wired || {};
  list.innerHTML = MODULES.map(([module, label, stage]) => {
    const current = bindings[module] || "";
    const info = wired[module] || { wired: false };
    return `
      <div class="binding-row" data-module="${esc(module)}">
        <div class="binding-name"><b>${esc(label)}</b><span>${esc(stage)} · ${esc(module)}</span></div>
        <select data-bind="${esc(module)}">
          <option value="">不绑定</option>
          ${profiles.map((profile) => `<option value="${esc(profile.profile_id)}" ${profile.profile_id === current ? "selected" : ""}>${esc(profile.label || profile.profile_id)} · ${esc(profile.model)}</option>`).join("")}
        </select>
        <span class="binding-state ${info.wired ? "wired" : "pending"}">${info.wired ? "WIRED" : "CONFIG ONLY"}</span>
      </div>`;
  }).join("");
  $$("[data-bind]").forEach((select) => select.addEventListener("change", () => {
    saveBinding(select.dataset.bind, select.value);
  }));
}

async function saveBinding(module, profileId) {
  try {
    const snapshot = await jsonFetch("/api/models/bindings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ module, profile_id: profileId }),
    });
    state.snapshot = snapshot;
    renderAll();
    banner(`${module} 已绑定到 ${profileId || "无"}。WIRED 模块才会被真实消费者读取。`, true);
  } catch (error) {
    banner("绑定失败：" + error.message);
  }
}

async function saveProvider(event) {
  event.preventDefault();
  const payload = {
    provider_id: $("#p-id").value.trim(),
    kind: $("#p-kind").value,
    label: $("#p-label").value.trim(),
    base_url: $("#p-base").value.trim(),
    api_key_env: $("#p-env").value.trim(),
    api_version: $("#p-version").value.trim(),
    allow_private_network: $("#p-private").checked,
    models: $("#p-models").value.split(/\n+/).map((item) => item.trim()).filter(Boolean),
  };
  const key = $("#p-key").value.trim();
  if (key) payload.api_key = key;
  try {
    const snapshot = await jsonFetch("/api/models/providers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.snapshot = snapshot;
    state.selectedProvider = payload.provider_id;
    state.creatingProvider = false;
    $("#p-key").value = "";
    fillProviderForm(selectedProvider());
    renderProfileProviderOptions(payload.provider_id);
    renderAll();
    banner("Provider 已保存；API key 只在 runtime 内存中（若填写）。", true);
  } catch (error) {
    banner("Provider 保存失败：" + error.message);
  }
}

async function refreshModels() {
  const provider = selectedProvider();
  if (!provider) return banner("先选择一个 provider。");
  try {
    const result = await jsonFetch(`/api/models/providers/${encodeURIComponent(provider.provider_id)}/refresh`, { method: "POST" });
    state.snapshot = result.snapshot;
    renderAll();
    fillProviderForm(selectedProvider());
    banner(`已刷新 ${result.models.length} 个模型；模型列表来自 provider 的 /models。`, true);
  } catch (error) {
    banner("刷新失败：" + error.message);
  }
}

async function clearKey() {
  const provider = selectedProvider();
  if (!provider) return banner("先选择一个 provider。");
  try {
    const snapshot = await jsonFetch(`/api/models/providers/${encodeURIComponent(provider.provider_id)}/key`, { method: "DELETE" });
    state.snapshot = snapshot;
    renderAll();
    fillProviderForm(selectedProvider());
    banner("已清除该 provider 的 session key；环境变量 key 不会被删除。", true);
  } catch (error) {
    banner("清除失败：" + error.message);
  }
}

async function saveProfile(event) {
  event.preventDefault();
  let extraBody = {};
  const rawExtra = $("#f-extra").value.trim();
  if (rawExtra) {
    try {
      extraBody = JSON.parse(rawExtra);
      if (!extraBody || Array.isArray(extraBody) || typeof extraBody !== "object") throw new Error("必须是 JSON 对象");
    } catch (error) {
      return banner("extra_body 不是合法 JSON 对象：" + error.message);
    }
  }
  const mode = $("#f-thinking").value;
  const budget = $("#f-budget").value.trim();
  const thinking = { mode, effort: $("#f-effort").value };
  if (mode === "budget") thinking.budget_tokens = Number(budget || 0);
  const payload = {
    profile_id: $("#f-id").value.trim(),
    provider_id: $("#f-provider").value,
    model: $("#f-model").value.trim(),
    label: $("#f-label").value.trim(),
    thinking,
    max_tokens: Number($("#f-max").value || 2048),
    context_window: Number($("#f-context").value || 128000),
    max_output_tokens: Number($("#f-output").value || 16384),
    thinking_supported: $("#f-thinking-supported").checked,
    temperature: $("#f-temperature").value === "" ? null : Number($("#f-temperature").value),
    top_p: $("#f-topp").value === "" ? null : Number($("#f-topp").value),
    json_mode: $("#f-json").checked,
    extra_body: extraBody,
  };
  try {
    const snapshot = await jsonFetch("/api/models/profiles", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.snapshot = snapshot;
    state.selectedProfile = payload.profile_id;
    state.creatingProfile = false;
    renderAll();
    fillProfileForm(selectedProfile());
    banner("模型档案已保存。绑定到 WIRED 模块后才会进入真实调用。", true);
  } catch (error) {
    banner("档案保存失败：" + error.message);
  }
}

async function runProbe(event) {
  event.preventDefault();
  const profileId = $("#probe-profile").value;
  const prompt = $("#probe-prompt").value.trim();
  if (!profileId) return banner("先创建并选择一个模型档案。");
  if (!prompt) return banner("Prompt 不能为空。");
  $("#probe-status").textContent = "RUNNING";
  $("#probe-output").hidden = true;
  $("#probe-meta").hidden = true;
  const max = $("#probe-max").value.trim();
  try {
    const result = await jsonFetch("/api/models/probe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        profile_id: profileId,
        prompt,
        system: $("#probe-system").value.trim(),
        max_tokens: max ? Number(max) : null,
      }),
    });
    const response = result.response;
    $("#probe-status").textContent = "OK";
    $("#probe-meta").hidden = false;
    $("#probe-meta").innerHTML = [
      `provider ${response.provider_id}`,
      `model ${response.model}`,
      `thinking ${JSON.stringify(response.thinking_applied || {})}`,
      `latency ${response.latency_ms} ms`,
      `usage ${JSON.stringify(response.usage || {})}`,
      `json_mode ${response.json_mode_applied ? "on" : "off"}`,
      response.request_id ? `request ${response.request_id}` : "",
    ].filter(Boolean).map((item) => `<span>${esc(item)}</span>`).join("");
    $("#probe-output").hidden = false;
    $("#probe-output").textContent = response.text;
    await loadCalls();
  } catch (error) {
    $("#probe-status").textContent = "FAILED";
    banner("探测失败：" + error.message);
    await loadCalls();
  }
}

async function loadCalls() {
  try {
    const data = await jsonFetch("/api/models/calls");
    const rows = data.calls || [];
    const table = $("#call-table");
    if (!rows.length) {
      table.innerHTML = '<p class="mg-empty">还没有调用。</p>';
      return;
    }
    table.innerHTML = rows.map((call) => `
      <div class="call-row">
        <span>${esc(call.at ? call.at.slice(11, 19) : "—")}</span>
        <b>${esc(call.profile_id || "—")} · ${esc(call.model || "—")}</b>
        <span class="${call.ok ? "ok" : "bad"}">${call.ok ? "OK" : "FAIL"}</span>
        <span>${esc(call.latency_ms || 0)} ms</span>
        <span>${esc(call.usage?.total_tokens || call.usage?.output_tokens || 0)} tok</span>
      </div>`).join("");
  } catch (_) { /* offline; keep the previous table */ }
}

$("#connect-btn").addEventListener("click", connect);
$("#api-base").addEventListener("keydown", (event) => { if (event.key === "Enter") connect(); });
$("#new-provider").addEventListener("click", resetProviderForm);
$("#provider-form").addEventListener("submit", saveProvider);
$("#refresh-models").addEventListener("click", refreshModels);
$("#clear-key").addEventListener("click", clearKey);
$("#profile-form").addEventListener("submit", saveProfile);
$("#reset-profile").addEventListener("click", resetProfileForm);
$("#probe-form").addEventListener("submit", runProbe);
$("#refresh-calls").addEventListener("click", loadCalls);
$("#p-kind").addEventListener("change", () => {
  $("#p-base").placeholder = DEFAULT_BASE[$("#p-kind").value] || "";
  if (!$("#p-base").value || Object.values(DEFAULT_BASE).includes($("#p-base").value)) {
    $("#p-base").value = DEFAULT_BASE[$("#p-kind").value] || "";
  }
  if ($("#p-kind").value === "anthropic") $("#p-env").value = "ANTHROPIC_API_KEY";
  if ($("#p-kind").value === "openai") $("#p-env").value = "OPENAI_API_KEY";
  if ($("#p-kind").value === "azure_openai") $("#p-env").value = "AZURE_OPENAI_API_KEY";
});
$("#f-provider").addEventListener("change", updateThinkingUI);
$("#f-thinking").addEventListener("change", updateThinkingUI);
$("#f-thinking-supported").addEventListener("change", updateThinkingUI);

try {
  const saved = localStorage.getItem("researchAgentModelApi");
  if (saved) state.api = saved;
} catch (_) {}
$("#api-base").value = state.api;
connect();

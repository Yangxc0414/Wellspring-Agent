import { useEffect, useMemo, useState } from "react";
import { apiFormatLabel, syncProfileToRuntime, syncProviderToRuntime } from "../../adapters/modelRuntime";
import { matchModelPreset } from "../../domain/modelCatalog";
import type { ModelPreset } from "../../domain/modelCatalog";
import type { ModelProfile } from "../../domain/types";
import { useAllModelProfiles, useModelRegistryStore } from "../../state/modelStore";
import type { ModelProviderEntry } from "../../state/modelStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { Icon } from "../Icon";

type ProviderDraft = Omit<ModelProviderEntry, "builtin">;

const NEW_PROVIDER = "__new__";
const INPUT_TYPES: Array<{ id: string; label: string }> = [
  { id: "text", label: "文本" },
  { id: "image", label: "图片" },
  { id: "video", label: "视频" },
  { id: "pdf", label: "PDF" },
  { id: "audio", label: "音频" }
];
const CAPABILITIES: Array<{ id: string; label: string }> = [
  { id: "structured_output", label: "结构化输出" },
  { id: "web_search", label: "原生联网搜索" },
  { id: "system_messages", label: "系统消息" },
  { id: "function_calling", label: "函数调用" }
];

function emptyDraft(): ProviderDraft {
  return {
    id: "",
    name: "新供应商",
    apiFormat: "openai_chat",
    baseUrl: "",
    apiKeyEnv: "CUSTOM_MODEL_API_KEY"
  };
}

function toDraft(provider: ModelProviderEntry): ProviderDraft {
  return {
    id: provider.id,
    name: provider.name,
    apiFormat: provider.apiFormat,
    baseUrl: provider.baseUrl,
    apiKeyEnv: provider.apiKeyEnv
  };
}

export function ModelProviderManager() {
  const providers = useModelRegistryStore((state) => state.providers);
  const addProvider = useModelRegistryStore((state) => state.addProvider);
  const updateProvider = useModelRegistryStore((state) => state.updateProvider);
  const addProfile = useModelRegistryStore((state) => state.addProfile);
  const removeProfile = useModelRegistryStore((state) => state.removeProfile);
  const allProfiles = useAllModelProfiles();
  const actions = useWorkspaceStore((state) => state.actions);

  const [selectedId, setSelectedId] = useState(providers[0]?.id ?? "");
  const selected = providers.find((item) => item.id === selectedId) ?? null;
  const [draft, setDraft] = useState<ProviderDraft>(() => (selected ? toDraft(selected) : emptyDraft()));
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState("");
  const [addOpen, setAddOpen] = useState(false);
  const [modelDraft, setModelDraft] = useState(() => ({
    modelId: "",
    label: "",
    contextWindow: "128000",
    maxOutput: "16384",
    kind: "effort" as ModelProfile["kind"],
    levels: "low, medium, high",
    inputTypes: ["text"] as string[],
    capabilities: ["system_messages"] as string[],
    reasoningParam: "reasoning_effort",
    sourceUrl: ""
  }));
  const [matched, setMatched] = useState<ModelPreset | null>(null);

  useEffect(() => {
    if (!selected) return;
    setDraft(toDraft(selected));
    setApiKey("");
  }, [selectedId]);

  useEffect(() => {
    if (!addOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setAddOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [addOpen]);

  const providerProfiles = useMemo(
    () => allProfiles.filter((profile) => profile.providerId === selectedId),
    [allProfiles, selectedId]
  );

  const choosePreset = (value: string) => {
    const preset = matchModelPreset(value);
    setMatched(preset);
    if (!preset) return;
    setModelDraft((current) => ({
      ...current,
      modelId: value,
      label: preset.label,
      contextWindow: String(preset.contextWindow),
      maxOutput: String(preset.maxOutput),
      kind: preset.kind,
      levels: preset.stops.map((stop) => String(stop.value)).join(", "),
      inputTypes: [...preset.inputTypes],
      capabilities: [...preset.capabilities],
      reasoningParam: preset.reasoningParam,
      sourceUrl: preset.sourceUrl
    }));
  };

  const saveProvider = async () => {
    if (!draft.name.trim() || !draft.baseUrl.trim()) {
      actions.notify("供应商名称与 Base URL 不能为空");
      return;
    }
    setBusy("provider");
    try {
      let id = selectedId;
      if (selectedId === NEW_PROVIDER) {
        id = addProvider(draft);
        setSelectedId(id);
      } else if (selected && !selected.builtin) {
        updateProvider(selected.id, draft);
      }
      try {
        await syncProviderToRuntime(
          { ...draft, id, builtin: false },
          providerProfiles.map((profile) => profile.modelId ?? profile.name),
          apiKey
        );
        actions.notify(apiKey ? "供应商已保存并写入本地 runtime（密钥仅会话内存）" : "供应商已保存并写入本地 runtime");
      } catch {
        actions.notify("供应商已保存到本地；runtime 离线或未接受该配置");
      }
      setApiKey("");
    } finally {
      setBusy("");
    }
  };

  const saveModel = async () => {
    if (!selected || !modelDraft.modelId.trim()) {
      actions.notify("请先选择供应商并填写模型 ID");
      return;
    }
    const levels = modelDraft.levels.split(",").map((item) => item.trim()).filter(Boolean);
    const stops = modelDraft.kind === "unsupported"
      ? []
      : levels.map((value) => modelDraft.kind === "budget"
        ? { value: Number(value), label: `${Math.round(Number(value) / 1024)}k`, detail: `thinking budget ${value}` }
        : { value, label: value, detail: `reasoning_effort=${value}` });
    if (modelDraft.kind === "budget" && stops.some((stop) => !Number.isFinite(Number(stop.value)) || Number(stop.value) < 1024)) {
      actions.notify("budget 等级必须是 ≥1024 的数字，用逗号分隔");
      return;
    }
    const baseId = `${selected.id}-${modelDraft.modelId}`.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 36);
    const existing = allProfiles.some((profile) => profile.id === baseId);
    const profile: ModelProfile = {
      id: existing ? `${baseId}-${Date.now().toString(36)}` : baseId,
      name: modelDraft.label.trim() || modelDraft.modelId.trim(),
      short: (modelDraft.label.trim() || modelDraft.modelId.trim()).slice(0, 18),
      provider: selected.name,
      providerId: selected.id,
      modelId: modelDraft.modelId.trim(),
      contextWindow: Math.max(8192, Number(modelDraft.contextWindow) || 128000),
      maxOutput: Math.max(256, Number(modelDraft.maxOutput) || 16384),
      kind: modelDraft.kind,
      defaultStop: stops.length ? stops[stops.length - 1].value : null,
      stops,
      note: matched?.note ?? "自定义模型；参数来自用户填写，服务商能力可能不同。",
      apiFormat: selected.apiFormat,
      baseUrl: selected.baseUrl,
      apiKeyEnv: selected.apiKeyEnv,
      inputTypes: [...modelDraft.inputTypes],
      capabilities: [...modelDraft.capabilities],
      reasoningParam: modelDraft.reasoningParam,
      sourceUrl: modelDraft.sourceUrl || undefined,
      custom: true
    };
    addProfile(profile);
    setBusy("model");
    try {
      await syncProviderToRuntime(selected, providerProfiles.map((item) => item.modelId ?? item.name).concat(profile.modelId ?? profile.name), apiKey);
      await syncProfileToRuntime(profile);
      actions.notify(`${profile.name} 已加入模型列表并写入本地 runtime`);
    } catch {
      actions.notify(`${profile.name} 已加入本地模型列表；runtime 离线或未接受该配置`);
    } finally {
      setBusy("");
    }
    setAddOpen(false);
  };

  const providerModels = (providerId: string) =>
    allProfiles.filter((profile) => profile.providerId === providerId);

  const toggleModelValue = (key: "inputTypes" | "capabilities", value: string) => {
    setModelDraft((current) => ({
      ...current,
      [key]: current[key].includes(value)
        ? current[key].filter((item) => item !== value)
        : [...current[key], value]
    }));
  };

  return (
    <>
      <section className="settings-card model-provider-card">
        <div className="settings-card-head">
          <div>
            <h2>模型供应商</h2>
            <p>管理 Base URL、API 格式与模型目录；输入模型 ID 会自动匹配上下文/输出/推理参数。</p>
          </div>
          <button type="button" className="settings-btn primary" onClick={() => { setSelectedId(NEW_PROVIDER); setDraft(emptyDraft()); }}>
            <Icon name="plus" size={12} />添加供应商
          </button>
        </div>
        <div className="model-provider-grid">
          <div className="provider-list">
            {providers.map((provider) => {
              const count = providerModels(provider.id).length;
              return (
                <button
                  key={provider.id}
                  type="button"
                  className={`provider-row${provider.id === selectedId ? " is-on" : ""}`}
                  onClick={() => setSelectedId(provider.id)}
                >
                  <span className={`provider-dot${count ? " is-ready" : ""}`} />
                  <span><b>{provider.name}</b><small>{apiFormatLabel(provider.apiFormat)} · {count} models</small></span>
                  {provider.builtin && <em>BUILT-IN</em>}
                </button>
              );
            })}
          </div>

          <div className="provider-editor">
            <div className="provider-editor-head">
              <b>{selectedId === NEW_PROVIDER ? "新供应商" : selected?.name ?? "模型供应商"}</b>
              <span>{selectedId === NEW_PROVIDER ? "UNSAVED" : selected?.builtin ? "READ-ONLY BASE" : "CUSTOM"}</span>
            </div>
            <label className="field"><span>名称</span>
              <input value={draft.name} disabled={Boolean(selected?.builtin)} onChange={(event) => setDraft({ ...draft, name: event.target.value })} />
            </label>
            <label className="field"><span>Base URL</span>
              <input value={draft.baseUrl} disabled={Boolean(selected?.builtin)} spellCheck={false} placeholder="https://api.example.com/v1" onChange={(event) => setDraft({ ...draft, baseUrl: event.target.value })} />
            </label>
            <div className="two-fields">
              <label className="field"><span>API 格式</span>
                <select value={draft.apiFormat} disabled={Boolean(selected?.builtin)} onChange={(event) => setDraft({ ...draft, apiFormat: event.target.value as ProviderDraft["apiFormat"] })}>
                  <option value="openai_chat">OpenAI Chat Completions</option>
                  <option value="openai_responses">Responses（仅登记）</option>
                  <option value="anthropic_messages">Anthropic Messages</option>
                  <option value="openai_compatible">OpenAI-compatible Chat</option>
                </select>
              </label>
              <label className="field"><span>API Key 环境变量</span>
                <input value={draft.apiKeyEnv} onChange={(event) => setDraft({ ...draft, apiKeyEnv: event.target.value })} spellCheck={false} />
              </label>
            </div>
            <label className="field"><span>API Key（仅本次会话 / runtime 内存）</span>
              <input type="password" value={apiKey} placeholder={draft.apiKeyEnv} onChange={(event) => setApiKey(event.target.value)} autoComplete="off" />
            </label>
            <p className="settings-note">密钥不会写入 localStorage 或工作区导出；只有连接本地 runtime 时才会发送到会话内存。Responses 格式目前仅登记，runtime 网关仍走 Chat Completions。</p>
            <div className="settings-actions">
              {selectedId !== NEW_PROVIDER && !selected?.builtin && (
                <button type="button" className="settings-btn primary" onClick={() => void saveProvider()} disabled={busy === "provider"}>
                  {busy === "provider" ? "保存中…" : "保存供应商"}
                </button>
              )}
              {selectedId === NEW_PROVIDER && (
                <button type="button" className="settings-btn primary" onClick={() => void saveProvider()} disabled={busy === "provider"}>
                  {busy === "provider" ? "保存中…" : "创建供应商"}
                </button>
              )}
              {selected && (
                <button type="button" className="settings-btn" onClick={() => setAddOpen(true)}>
                  <Icon name="plus" size={12} />添加模型
                </button>
              )}
            </div>

            <div className="provider-models">
              <div className="section-title"><span>模型列表</span><em>{providerProfiles.length}</em></div>
              {providerProfiles.length ? providerProfiles.map((profile) => (
                <div className="provider-model-row" key={profile.id}>
                  <span className="provider-model-mark"><Icon name="cpu" size={12} /></span>
                  <div>
                    <b>{profile.name}</b>
                    <small>{profile.modelId} · {Math.round(profile.contextWindow / 1000)}k ctx · {Math.round(profile.maxOutput / 1000)}k out</small>
                  </div>
                  <span className="settings-state" data-state={profile.kind === "unsupported" ? "draft" : "active"}>{profile.kind}</span>
                  {profile.custom && (
                    <button type="button" className="icon-button" onClick={() => removeProfile(profile.id)} aria-label={`删除 ${profile.name}`}>
                      <Icon name="trash" size={11} />
                    </button>
                  )}
                </div>
              )) : <p className="settings-empty">该供应商还没有模型；添加一个后会出现在 Composer 模型选择器。</p>}
            </div>
          </div>
        </div>
      </section>

      {addOpen && selected && (
        <div className="modal-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAddOpen(false); }}>
          <section className="modal model-add-modal" role="dialog" aria-modal="true" aria-label="添加模型">
            <header className="modal-head">
              <div><span className="eyebrow">MODEL / REGISTRY</span><h2>添加模型</h2></div>
              <button type="button" className="icon-button" onClick={() => setAddOpen(false)} aria-label="关闭添加模型"><Icon name="close" size={14} /></button>
            </header>
            <p className="modal-lede">输入模型 ID 会自动匹配已知参数；所有字段都可继续编辑。匹配不代表供应商端点已验证。</p>
            <label className="field"><span>模型 ID</span>
              <input autoFocus value={modelDraft.modelId} spellCheck={false} placeholder="例如 glm-5.3-flash" onChange={(event) => choosePreset(event.target.value)} />
            </label>
            {matched && (
              <div className="model-match-note">
                <Icon name="spark" size={12} />
                <span>已匹配 {matched.label} · {Math.round(matched.contextWindow / 1000)}k ctx / {Math.round(matched.maxOutput / 1000)}k out · <a href={matched.sourceUrl} target="_blank" rel="noopener noreferrer">规格来源</a></span>
              </div>
            )}
            <div className="two-fields">
              <label className="field"><span>显示名称</span>
                <input value={modelDraft.label} onChange={(event) => setModelDraft({ ...modelDraft, label: event.target.value })} /></label>
              <label className="field"><span>供应商</span>
                <input value={selected.name} readOnly /></label>
            </div>
            <div className="two-fields">
              <label className="field"><span>上下文窗口</span>
                <input type="number" value={modelDraft.contextWindow} onChange={(event) => setModelDraft({ ...modelDraft, contextWindow: event.target.value })} /></label>
              <label className="field"><span>最大输出 Token</span>
                <input type="number" value={modelDraft.maxOutput} onChange={(event) => setModelDraft({ ...modelDraft, maxOutput: event.target.value })} /></label>
            </div>
            <label className="field"><span>输入类型</span>
              <span className="check-row">
                {INPUT_TYPES.map((item) => (
                  <button key={item.id} type="button" className={`check-pill${modelDraft.inputTypes.includes(item.id) ? " is-on" : ""}`} onClick={() => toggleModelValue("inputTypes", item.id)}>
                    {modelDraft.inputTypes.includes(item.id) ? "✓ " : ""}{item.label}
                  </button>
                ))}
              </span>
            </label>
            <label className="field"><span>模型能力</span>
              <span className="check-row">
                {CAPABILITIES.map((item) => (
                  <button key={item.id} type="button" className={`check-pill${modelDraft.capabilities.includes(item.id) ? " is-on" : ""}`} onClick={() => toggleModelValue("capabilities", item.id)}>
                    {modelDraft.capabilities.includes(item.id) ? "✓ " : ""}{item.label}
                  </button>
                ))}
              </span>
            </label>
            <div className="two-fields">
              <label className="field"><span>推理模式</span>
                <select value={modelDraft.kind} onChange={(event) => setModelDraft({ ...modelDraft, kind: event.target.value as ModelProfile["kind"] })}>
                  <option value="effort">effort（reasoning_effort）</option>
                  <option value="budget">budget（thinking budget）</option>
                  <option value="unsupported">不支持 / off</option>
                </select>
              </label>
              <label className="field"><span>推理参数映射</span>
                <input value={modelDraft.reasoningParam} onChange={(event) => setModelDraft({ ...modelDraft, reasoningParam: event.target.value })} /></label>
            </div>
            <label className="field"><span>推理等级（从低到高，逗号分隔）</span>
              <input value={modelDraft.levels} onChange={(event) => setModelDraft({ ...modelDraft, levels: event.target.value })} placeholder="low, medium, high" />
            </label>
            <footer className="modal-foot">
              <span className="form-note">参数只用于本地预算与请求映射；不会自动验证模型端点。</span>
              <button type="button" className="text-button" onClick={() => setAddOpen(false)}>取消</button>
              <button type="button" className="solid-button" onClick={() => void saveModel()} disabled={busy === "model"}>
                {busy === "model" ? "保存中…" : "保存模型"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </>
  );
}

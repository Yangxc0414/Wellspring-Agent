import { create } from "zustand";
import { MODEL_PROFILES, setCustomModelProfiles } from "../domain/catalog";
import type { ModelProfile } from "../domain/types";
import type { ApiFormat } from "../domain/modelCatalog";

export interface ModelProviderEntry {
  id: string;
  name: string;
  apiFormat: ApiFormat;
  baseUrl: string;
  apiKeyEnv: string;
  builtin?: boolean;
  sourceUrl?: string;
}

interface ModelRegistryState {
  providers: ModelProviderEntry[];
  customProfiles: ModelProfile[];
  addProvider: (provider: Omit<ModelProviderEntry, "builtin">) => string;
  updateProvider: (id: string, patch: Partial<ModelProviderEntry>) => void;
  addProfile: (profile: ModelProfile) => void;
  removeProfile: (id: string) => void;
}

const STORAGE_KEY = "researchAgent.models.v1";

const BUILTIN_PROVIDERS: ModelProviderEntry[] = [
  { id: "openai", name: "OpenAI", apiFormat: "openai_chat", baseUrl: "https://api.openai.com/v1", apiKeyEnv: "OPENAI_API_KEY", builtin: true },
  { id: "anthropic", name: "Anthropic", apiFormat: "anthropic_messages", baseUrl: "https://api.anthropic.com/v1", apiKeyEnv: "ANTHROPIC_API_KEY", builtin: true },
  { id: "zhipu", name: "智谱 Z.ai", apiFormat: "openai_chat", baseUrl: "https://open.bigmodel.cn/api/paas/v4", apiKeyEnv: "ZHIPU_API_KEY", builtin: true },
  { id: "google", name: "Google Gemini", apiFormat: "openai_compatible", baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai", apiKeyEnv: "GEMINI_API_KEY", builtin: true },
  { id: "deepseek", name: "DeepSeek", apiFormat: "openai_compatible", baseUrl: "https://api.deepseek.com/v1", apiKeyEnv: "DEEPSEEK_API_KEY", builtin: true },
  { id: "alibaba", name: "阿里云百炼", apiFormat: "openai_compatible", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKeyEnv: "DASHSCOPE_API_KEY", builtin: true },
  { id: "local-openai", name: "本地 OpenAI 兼容网关", apiFormat: "openai_compatible", baseUrl: "http://127.0.0.1:11434/v1", apiKeyEnv: "LOCAL_LLM_API_KEY", builtin: true }
];

function loadSaved(): { providers: ModelProviderEntry[]; customProfiles: ModelProfile[] } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { providers: [], customProfiles: [] };
    const data = JSON.parse(raw) as { providers?: ModelProviderEntry[]; customProfiles?: ModelProfile[] };
    const custom = Array.isArray(data.providers) ? data.providers.filter((item) => item && !item.builtin) : [];
    const profiles = Array.isArray(data.customProfiles) ? data.customProfiles.filter((item) => item && item.id && item.contextWindow) : [];
    return { providers: custom, customProfiles: profiles };
  } catch {
    return { providers: [], customProfiles: [] };
  }
}

function save(
  providers: ModelProviderEntry[],
  customProfiles: ModelProfile[]
): void {
  const custom = providers.filter((item) => !item.builtin);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ providers: custom, customProfiles }));
  } catch {
    /* storage can be unavailable in private mode */
  }
}

function slug(value: string): string {
  const cleaned = value.trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
  return cleaned || "provider-" + Date.now().toString(36);
}

const saved = loadSaved();
const initialProviders = [...BUILTIN_PROVIDERS, ...saved.providers];
setCustomModelProfiles(saved.customProfiles);

export const useModelRegistryStore = create<ModelRegistryState>((set, get) => ({
  providers: initialProviders,
  customProfiles: saved.customProfiles,
  addProvider: (provider) => {
    const id = slug(provider.id || provider.name);
    const next = get().providers.filter((item) => item.id !== id);
    const entry: ModelProviderEntry = { ...provider, id, builtin: false };
    const providers = [...next, entry];
    set({ providers });
    save(providers, get().customProfiles);
    return id;
  },
  updateProvider: (id, patch) => {
    const providers = get().providers.map((item) =>
      item.id === id && !item.builtin ? { ...item, ...patch, id } : item
    );
    set({ providers });
    save(providers, get().customProfiles);
  },
  addProfile: (profile) => {
    const current = get().customProfiles.filter(
      (item) => item.id !== profile.id && !(item.providerId === profile.providerId && item.name === profile.name)
    );
    const customProfiles = [...current, profile];
    set({ customProfiles });
    setCustomModelProfiles(customProfiles);
    save(get().providers, customProfiles);
  },
  removeProfile: (id) => {
    const customProfiles = get().customProfiles.filter((item) => item.id !== id);
    set({ customProfiles });
    setCustomModelProfiles(customProfiles);
    save(get().providers, customProfiles);
  }
}));

export function useAllModelProfiles(): ModelProfile[] {
  const custom = useModelRegistryStore((state) => state.customProfiles);
  return [...MODEL_PROFILES, ...custom];
}

export { BUILTIN_PROVIDERS };

import type { ModelProfile } from "../domain/types";
import type { ApiFormat } from "../domain/modelCatalog";
import type { ModelProviderEntry } from "../state/modelStore";

import { authHeaders, describeAuthRefusal } from "./runtimeAuth";

const runtimeBase = (import.meta.env.VITE_RUNTIME_URL ?? "").replace(/\/$/, "");

export interface RuntimeModelProvider {
  provider_id: string;
  label: string;
  kind: string;
  base_url: string;
  api_key_env: string;
  models: string[];
  configured: boolean;
  key_source: string;
  masked_key: string;
}

export interface RuntimeModelProfile {
  profile_id: string;
  provider_id: string;
  model: string;
  label: string;
  context_window: number;
  max_output_tokens: number;
}

export interface RuntimeModelReadiness {
  required_modules: string[];
  modules: Record<string, {
    wired: boolean;
    bound_profile: string;
    provider: string;
    key_configured: boolean;
    consumer: string;
  }>;
  production_ready: boolean;
  blocking: string[];
  warnings: string[];
  boundary: string;
}

export interface RuntimeModelSnapshot {
  providers: RuntimeModelProvider[];
  profiles: RuntimeModelProfile[];
  bindings: Record<string, string>;
  wired: Record<string, { wired: boolean; consumer?: string; note?: string }>;
  readiness: RuntimeModelReadiness;
}

function kindFor(provider: ModelProviderEntry): string {
  if (provider.apiFormat === "anthropic_messages") return "anthropic";
  if (provider.apiFormat === "openai_responses") {
    throw new Error("runtime 网关尚未接入 Responses API；请先使用 Chat Completions");
  }
  if (provider.id === "openai") return "openai";
  return "openai_compatible";
}

async function request(path: string, body: Record<string, unknown>): Promise<Record<string, unknown>> {
  return requestJson("POST", path, body);
}

async function requestJson(
  method: "POST" | "DELETE",
  path: string,
  body?: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 3200);
  try {
    const response = await fetch(runtimeBase + path, {
      method,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", Accept: "application/json", ...authHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      const refusal = describeAuthRefusal(response.status, detail);
      throw new Error(refusal || `${response.status} ${detail.slice(0, 160)}`.trim());
    }
    return (await response.json()) as Record<string, unknown>;
  } finally {
    window.clearTimeout(timer);
  }
}

async function getJson(path: string): Promise<Record<string, unknown>> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(runtimeBase + path, {
      signal: controller.signal,
      headers: { Accept: "application/json", ...authHeaders() }
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      const refusal = describeAuthRefusal(response.status, detail);
      throw new Error(refusal || `${response.status} ${detail.slice(0, 160)}`.trim());
    }
    return (await response.json()) as Record<string, unknown>;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function loadRuntimeModelSnapshot(): Promise<RuntimeModelSnapshot> {
  return (await getJson("/api/models")) as unknown as RuntimeModelSnapshot;
}

export async function bindRuntimeModule(module: string, profileId: string): Promise<RuntimeModelSnapshot> {
  return (await request("/api/models/bindings", { module, profile_id: profileId })) as unknown as RuntimeModelSnapshot;
}

export async function setRuntimeProviderKey(
  providerId: string,
  apiKey: string
): Promise<RuntimeModelSnapshot> {
  return (await request(
    `/api/models/providers/${encodeURIComponent(providerId)}/key`,
    { api_key: apiKey }
  )) as unknown as RuntimeModelSnapshot;
}

export async function clearRuntimeProviderKey(providerId: string): Promise<RuntimeModelSnapshot> {
  return (await requestJson(
    "DELETE",
    `/api/models/providers/${encodeURIComponent(providerId)}/key`
  )) as unknown as RuntimeModelSnapshot;
}

export async function syncProviderToRuntime(
  provider: ModelProviderEntry,
  models: string[],
  apiKey: string
): Promise<void> {
  const payload: Record<string, unknown> = {
    provider_id: provider.id,
    kind: kindFor(provider),
    label: provider.name,
    base_url: provider.baseUrl,
    api_key_env: provider.apiKeyEnv,
    models
  };
  if (apiKey.trim()) payload.api_key = apiKey.trim();
  await request("/api/models/providers", payload);
}

export async function syncProfileToRuntime(profile: ModelProfile): Promise<void> {
  const budget = profile.kind === "budget" ? Number(profile.defaultStop ?? 4096) : 0;
  const thinking = profile.kind === "effort"
    ? { mode: "effort", effort: String(profile.defaultStop ?? "medium"), budget_tokens: null }
    : profile.kind === "budget"
      ? { mode: "budget", effort: "medium", budget_tokens: budget }
      : { mode: "off", effort: "medium", budget_tokens: null };
  const extraBody: Record<string, unknown> = {};
  if (profile.providerId === "zhipu") extraBody.clear_thinking = true;
  if (profile.providerId === "alibaba") extraBody.enable_thinking = profile.kind !== "unsupported";
  if (profile.kind === "budget" && profile.providerId !== "anthropic" && profile.providerId !== "zhipu") {
    throw new Error("runtime 网关需要供应商特定的 thinking extra_body；该预算模型只保存在本地");
  }
  await request("/api/models/profiles", {
    profile_id: profile.id.replace(/\./g, "-"),
    provider_id: profile.providerId ?? profile.provider,
    model: profile.modelId ?? profile.name,
    label: profile.name,
    thinking,
    max_tokens: Math.min(profile.maxOutput, Math.max(8192, budget + 1024)),
    context_window: profile.contextWindow,
    max_output_tokens: profile.maxOutput,
    thinking_supported: profile.kind !== "unsupported",
    json_mode: Boolean(profile.capabilities?.includes("structured_output")),
    extra_body: extraBody
  });
}

export function apiFormatLabel(format: ApiFormat): string {
  if (format === "anthropic_messages") return "Anthropic Messages";
  if (format === "openai_responses") return "Responses（仅登记）";
  if (format === "openai_compatible") return "OpenAI-compatible Chat";
  return "OpenAI Chat Completions";
}

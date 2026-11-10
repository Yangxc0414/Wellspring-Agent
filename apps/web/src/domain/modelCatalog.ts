import type { ModelProfile, ModelStop } from "./types";

export type ApiFormat = "openai_chat" | "openai_responses" | "anthropic_messages" | "openai_compatible";

export interface ModelPreset {
  id: string;
  label: string;
  short: string;
  provider: string;
  providerId: string;
  modelId: string;
  apiFormat: ApiFormat;
  baseUrl: string;
  apiKeyEnv: string;
  contextWindow: number;
  maxOutput: number;
  kind: "effort" | "budget" | "unsupported";
  defaultStop: string | number | null;
  stops: ModelStop[];
  inputTypes: string[];
  capabilities: string[];
  reasoningParam: string;
  note: string;
  sourceUrl: string;
  aliases: string[];
}

export const MODEL_PRESETS: ModelPreset[] = [
  {
    id: "glm-5.3-flash",
    label: "GLM-5.3-Flash",
    short: "GLM-5.3",
    provider: "智谱 Z.ai",
    providerId: "zhipu",
    modelId: "glm-5.3-flash",
    apiFormat: "openai_chat",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    apiKeyEnv: "ZHIPU_API_KEY",
    contextWindow: 1048576,
    maxOutput: 131072,
    kind: "effort",
    defaultStop: "max",
    stops: [
      { value: "low", label: "low", detail: "reasoning_effort=low" },
      { value: "high", label: "high", detail: "reasoning_effort=high" },
      { value: "max", label: "max", detail: "reasoning_effort=max（默认）" }
    ],
    inputTypes: ["text", "image", "video", "pdf"],
    capabilities: ["structured_output", "system_messages", "function_calling"],
    reasoningParam: "reasoning_effort",
    note: "1M 上下文 / 128K–131K 输出，原生多模态；不同托管商的 JSON/工具面可能不同。",
    sourceUrl: "https://modelscope.cn/models/ZhipuAI/GLM-5.3-Flash/summary",
    aliases: ["glm-5.3-flash", "glm-5.3-flashx", "zhipu/glm-5.3-flash", "z-ai/glm-5.3-flash"]
  },
  {
    id: "gpt-5",
    label: "GPT-5",
    short: "GPT-5",
    provider: "OpenAI",
    providerId: "openai",
    modelId: "gpt-5",
    apiFormat: "openai_chat",
    baseUrl: "https://api.openai.com/v1",
    apiKeyEnv: "OPENAI_API_KEY",
    contextWindow: 400000,
    maxOutput: 128000,
    kind: "effort",
    defaultStop: "medium",
    stops: [
      { value: "minimal", label: "minimal", detail: "reasoning_effort=minimal" },
      { value: "low", label: "low", detail: "reasoning_effort=low" },
      { value: "medium", label: "medium", detail: "reasoning_effort=medium" },
      { value: "high", label: "high", detail: "reasoning_effort=high" }
    ],
    inputTypes: ["text", "image", "pdf"],
    capabilities: ["structured_output", "system_messages", "function_calling"],
    reasoningParam: "reasoning_effort",
    note: "400K 上下文 / 128K 输出；思考档位由 reasoning_effort 控制。",
    sourceUrl: "https://openai.com/gpt-5/",
    aliases: ["gpt-5", "openai/gpt-5", "gpt5"]
  },
  {
    id: "gpt-5-mini",
    label: "GPT-5 mini",
    short: "GPT-5 mini",
    provider: "OpenAI",
    providerId: "openai",
    modelId: "gpt-5-mini",
    apiFormat: "openai_chat",
    baseUrl: "https://api.openai.com/v1",
    apiKeyEnv: "OPENAI_API_KEY",
    contextWindow: 400000,
    maxOutput: 128000,
    kind: "effort",
    defaultStop: "medium",
    stops: [
      { value: "minimal", label: "minimal", detail: "reasoning_effort=minimal" },
      { value: "low", label: "low", detail: "reasoning_effort=low" },
      { value: "medium", label: "medium", detail: "reasoning_effort=medium" },
      { value: "high", label: "high", detail: "reasoning_effort=high" }
    ],
    inputTypes: ["text", "image", "pdf"],
    capabilities: ["structured_output", "system_messages", "function_calling"],
    reasoningParam: "reasoning_effort",
    note: "400K 上下文 / 128K 输出；适合高频低成本调用。",
    sourceUrl: "https://openai.com/gpt-5/",
    aliases: ["gpt-5-mini", "openai/gpt-5-mini"]
  },
  {
    id: "claude-sonnet-5.5",
    label: "Claude Sonnet 5.5",
    short: "Sonnet 5.5",
    provider: "Anthropic",
    providerId: "anthropic",
    modelId: "claude-sonnet-5-5",
    apiFormat: "anthropic_messages",
    baseUrl: "https://api.anthropic.com/v1",
    apiKeyEnv: "ANTHROPIC_API_KEY",
    contextWindow: 1000000,
    maxOutput: 128000,
    kind: "budget",
    defaultStop: 8192,
    stops: [
      { value: 1024, label: "1k", detail: "thinking.budget_tokens=1024" },
      { value: 4096, label: "4k", detail: "thinking.budget_tokens=4096" },
      { value: 8192, label: "8k", detail: "thinking.budget_tokens=8192" },
      { value: 16384, label: "16k", detail: "thinking.budget_tokens=16384" },
      { value: 32000, label: "32k", detail: "thinking.budget_tokens=32000" }
    ],
    inputTypes: ["text", "image", "pdf"],
    capabilities: ["structured_output", "system_messages", "function_calling"],
    reasoningParam: "thinking.budget_tokens",
    note: "1M 上下文 / 128K 输出；Anthropic 使用 thinking budget，必须小于最大回复。",
    sourceUrl: "https://platform.claude.com/docs/en/models/sonnet-5-5/overview",
    aliases: ["claude-sonnet-5.5", "claude-sonnet-5-5", "claude-5-5-sonnet", "anthropic/claude-sonnet-5.5"]
  },
  {
    id: "gemini-2.5-pro",
    label: "Gemini 2.5 Pro",
    short: "Gemini 2.5",
    provider: "Google",
    providerId: "google",
    modelId: "gemini-2.5-pro",
    apiFormat: "openai_compatible",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    apiKeyEnv: "GEMINI_API_KEY",
    contextWindow: 1048576,
    maxOutput: 65536,
    kind: "budget",
    defaultStop: 8192,
    stops: [
      { value: 1024, label: "1k", detail: "thinking budget 1024" },
      { value: 4096, label: "4k", detail: "thinking budget 4096" },
      { value: 8192, label: "8k", detail: "thinking budget 8192" },
      { value: 24576, label: "24k", detail: "thinking budget 24576" }
    ],
    inputTypes: ["text", "image", "video", "pdf", "audio"],
    capabilities: ["structured_output", "system_messages", "function_calling", "web_search"],
    reasoningParam: "thinking budget",
    note: "1,048,576 上下文 / 65,536 输出；多模态输入，思考预算由供应商端点解释。",
    sourceUrl: "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-pro",
    aliases: ["gemini-2.5-pro", "google/gemini-2.5-pro", "gemini-25-pro"]
  },
  {
    id: "deepseek-v3.2",
    label: "DeepSeek V3.2",
    short: "DeepSeek 3.2",
    provider: "DeepSeek",
    providerId: "deepseek",
    modelId: "deepseek-v3.2",
    apiFormat: "openai_compatible",
    baseUrl: "https://api.deepseek.com/v1",
    apiKeyEnv: "DEEPSEEK_API_KEY",
    contextWindow: 128000,
    maxOutput: 32000,
    kind: "budget",
    defaultStop: 4096,
    stops: [
      { value: 1024, label: "1k", detail: "thinking budget 1024" },
      { value: 4096, label: "4k", detail: "thinking budget 4096" },
      { value: 8192, label: "8k", detail: "thinking budget 8192" },
      { value: 32000, label: "32k", detail: "thinking budget 32000" }
    ],
    inputTypes: ["text"],
    capabilities: ["structured_output", "system_messages", "function_calling"],
    reasoningParam: "thinking budget",
    note: "128K 上下文 / 32K 输出；OpenAI 兼容接口，思考输出计入输出预算。",
    sourceUrl: "https://cloud.tencent.com/document/product/1772/115963",
    aliases: ["deepseek-v3.2", "deepseek/deepseek-v3.2", "deepseek-chat"]
  },
  {
    id: "qwen3.7-max",
    label: "Qwen3.7 Max",
    short: "Qwen3.7 Max",
    provider: "阿里云百炼",
    providerId: "alibaba",
    modelId: "qwen3.7-max",
    apiFormat: "openai_compatible",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    apiKeyEnv: "DASHSCOPE_API_KEY",
    contextWindow: 1000000,
    maxOutput: 131072,
    kind: "budget",
    defaultStop: 8192,
    stops: [
      { value: 1024, label: "1k", detail: "thinking budget 1024" },
      { value: 8192, label: "8k", detail: "thinking budget 8192" },
      { value: 16384, label: "16k", detail: "thinking budget 16384" },
      { value: 32768, label: "32k", detail: "thinking budget 32768" }
    ],
    inputTypes: ["text", "image", "video", "pdf"],
    capabilities: ["structured_output", "system_messages", "function_calling", "web_search"],
    reasoningParam: "thinking budget",
    note: "1M 上下文 / 131K 输出；支持结构化输出、联网搜索与多模态输入。",
    sourceUrl: "https://help.aliyun.com/zh/model-studio/qwen3-7-max",
    aliases: ["qwen3.7-max", "qwen3-max", "qwen/qwen3.7-max", "qwen3.7-max-latest"]
  }
];

function normalizeModelId(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^[a-z0-9-]+\//, "")
    .replace(/[_\s]+/g, "-");
}

export function matchModelPreset(value: string): ModelPreset | null {
  const needle = normalizeModelId(value);
  if (!needle) return null;
  for (const preset of MODEL_PRESETS) {
    if (normalizeModelId(preset.modelId) === needle) return preset;
    if (preset.aliases.some((alias) => normalizeModelId(alias) === needle)) return preset;
  }
  for (const preset of MODEL_PRESETS) {
    if (preset.aliases.some((alias) => needle.includes(normalizeModelId(alias)))) return preset;
  }
  return null;
}

export function presetToProfile(preset: ModelPreset, providerId = preset.providerId): ModelProfile {
  return {
    id: preset.id,
    name: preset.label,
    short: preset.short,
    provider: preset.provider,
    contextWindow: preset.contextWindow,
    maxOutput: preset.maxOutput,
    kind: preset.kind,
    defaultStop: preset.defaultStop,
    stops: preset.stops.map((stop) => ({ ...stop })),
    note: preset.note,
    providerId,
    modelId: preset.modelId,
    apiFormat: preset.apiFormat,
    baseUrl: preset.baseUrl,
    apiKeyEnv: preset.apiKeyEnv,
    inputTypes: [...preset.inputTypes],
    capabilities: [...preset.capabilities],
    reasoningParam: preset.reasoningParam,
    sourceUrl: preset.sourceUrl,
    custom: true
  };
}

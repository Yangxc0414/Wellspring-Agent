import { DEFAULT_SHORTCUTS } from "./shortcuts";
import type { AccessMode, AutoStage, Mode, ModelProfile, ModelSettings, Plugin, Preferences, Skill } from "./types";

export const APP_VERSION = "0.2.0";
export const BUILD_DATE = "2026-10-24";
export const STORAGE_VERSION = 1;
export const STORAGE_KEY = "researchAgent.web.v1";
export const AUTO_TICK_MS = 1100;

export const MODE_META: Record<Mode, { label: string; kicker: string; hint: string; placeholder: string }> = {
  research: {
    label: "调研",
    kicker: "RESEARCH / S1–S3",
    hint: "先证据后假设",
    placeholder: "问一个研究问题，或让我扩展检索……"
  },
  experiment: {
    label: "实验",
    kicker: "EXPERIMENT / S4–S5",
    hint: "先冻结协议，再运行",
    placeholder: "描述要验证的假设，或输入 /run 运行已冻结协议……"
  },
  writing: {
    label: "写作",
    kicker: "WRITING / S8–S12",
    hint: "先槽位，后正文",
    placeholder: "把已签 claim 绑定到写作槽位，或检查证据边界……"
  },
  auto: {
    label: "全自动",
    kicker: "GOVERNED AUTO / S1–META",
    hint: "跑到人工门再决定",
    placeholder: "输入 /start 启动，或用 /pause /step 控制……"
  }
};

export const AUTO_STAGE_CATALOG: AutoStage[] = [
  { id: "S1", label: "文献检索", cmd: "retrieval.query", output: "3 sources / 12 spans · 1 abstract-only gap", status: "pending" },
  { id: "S2–S3", label: "假设收敛", cmd: "idea.frame", output: "2 candidates · G1 演示推进，真实收敛需 CLI", status: "pending" },
  { id: "S4", label: "设计冻结", cmd: "design.freeze", output: "G2 待人工冻结 · 协议草案已生成", status: "pending" },
  { id: "S5a", label: "复现执行", cmd: "run.work", output: "RUN-014 · 3 seeds · R² 0.164 vs baseline −0.048", status: "pending" },
  { id: "S5b", label: "证据判定", cmd: "judge.verify", output: "EA sealed · claim 等待人工签署", status: "pending", gate: true },
  { id: "S6", label: "结果图", cmd: "figure.render", output: "SVG + manifest · bound to EA", status: "pending" },
  { id: "S8–S12", label: "写作槽位", cmd: "paper.bind", output: "result.primary pending_evidence", status: "pending" },
  { id: "S13–S16", label: "闭包检查", cmd: "closure.check", output: "closure 9/11 · citation.related pending", status: "pending" },
  { id: "META", label: "自进化提案", cmd: "rsi.propose", output: "candidate · S1 budget 6 → 3", status: "pending" }
];

export const SUGGESTIONS: Record<Mode, string[]> = {
  research: ["扩展检索", "把 gap 变成假设", "查看证据链"],
  experiment: ["冻结协议", "运行 3 seeds", "查看 EA"],
  writing: ["生成写作槽位", "检查证据边界", "查看证据链"],
  auto: ["启动全自动", "单步", "暂停"]
};

export const MODE_ORDER: Mode[] = ["research", "experiment", "writing", "auto"];

export const ACCESS_META: Record<
  AccessMode,
  { label: string; short: string; hint: string; description: string; tone: "teal" | "amber" | "coral" }
> = {
  read_only: {
    label: "只读",
    short: "READ",
    hint: "查看与检索，不执行",
    description: "允许检索、查看证据与写作预览；禁止设计/冻结协议、运行实验、签署 claim、批准工具、准入候选或启动全自动。",
    tone: "teal"
  },
  ask: {
    label: "每次询问",
    short: "ASK",
    hint: "高权限动作逐次确认",
    description: "运行实验、批准工具、准入候选与启动全自动前都会弹出确认；claim 签名仍由人工门控制。",
    tone: "amber"
  },
  full: {
    label: "完全访问",
    short: "FULL",
    hint: "不再逐次确认，仍有人工门",
    description: "高权限动作直接执行；claim、EA、closure、导出与签名的人工门不会被绕过。",
    tone: "coral"
  }
};

export const ACCESS_ORDER: AccessMode[] = ["read_only", "ask", "full"];

export const BUILTIN_SKILLS: Skill[] = [
  {
    id: "literature-brief",
    name: "文献速览",
    description: "审计来源广度、全文覆盖、span 与 gap，并给出覆盖总结。",
    instructions: "覆盖 core/survey/method/evaluation/limitation/recent 六面向；低于来源/全文/span 目标时显式提示补检索。",
    tools: ["literature.query", "span.locate", "coverage.receipt"],
    activation: "auto",
    source: "builtin",
    version: "1.1.0"
  },
  {
    id: "hypothesis-triage",
    name: "假设收敛",
    description: "检查候选的证据支持、否证条件、跨来源与否证前缺口。",
    instructions: "多个候选并排；优先支持引用 ≥2 条证据、跨来源、lens 多样的候选；novelty 未核验前不收敛。",
    tools: ["idea.cluster", "evidence.inspect", "gate.check"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  },
  {
    id: "protocol-review",
    name: "协议体检",
    description: "检查假设、baseline、主指标、对照与 seeds 是否可冻结。",
    instructions: "对当前协议逐项检查假设、baseline、主指标、对照与 seeds；冻结后不得改写主指标。",
    tools: ["protocol.inspect", "gate.check"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  },
  {
    id: "evidence-audit",
    name: "证据边界审计",
    description: "检查 claim 是否越过来源、EA 与人工门。",
    instructions: "检查 span→claim→EA→gate 的边界；未签 claim 不得进入写作与导出。",
    tools: ["evidence.inspect", "claim.inspect", "gate.check"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  },
  {
    id: "paper-slots",
    name: "写作槽位草拟",
    description: "按已签 claim 与冻结协议生成六个写作槽位。",
    instructions: "只绑定已签 claim、冻结协议与 figure manifest；没有证据的槽位保持 locked。",
    tools: ["paper.bind", "claim.inspect"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  },
  {
    id: "rsi-preflight",
    name: "自进化预检",
    description: "检查候选是否只改策略层、是否具备租约与回滚路径。",
    instructions: "核对候选目标、dry-run、public/hidden、regression、人工准入与租约；不可写面保持只读。",
    tools: ["rsi.inspect", "lease.check", "gate.check"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  },
  {
    id: "research-scout",
    name: "研究构思",
    description: "先查领域与方法两条文献线，再区分大胆方案与稳妥方案。",
    instructions: "先检查科学领域与 AI/ML 方法的相关工作，再提出 Tier-1 激进方案与 Tier-2 稳妥方案；明确回答它是否回应了任务结构。",
    tools: ["literature.query", "gap.inspect", "idea.frame"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  },
  {
    id: "experiment-manager",
    name: "实验管理",
    description: "预算、短程验证、失败分诊与独立目录。",
    instructions: "先做 1–2 个 epoch / 小样本 smoke run；核对数据加载、设备使用与预算；失败按实现错误、环境设置、方案不适配分诊。",
    tools: ["run.plan", "budget.check", "failure.triage"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  },
  {
    id: "exploration-check",
    name: "探索巡检",
    description: "检查是否退回超参数、验证选择是否过多、探索是否收窄。",
    instructions: "逐小时检查是否仍在探索有意义的方案；统计工程/领域干预比例与验证选择次数；发现收窄时重新规划。",
    tools: ["trace.inspect", "budget.check", "strategy.audit"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  },
  {
    id: "eval-integrity",
    name: "评估隔离",
    description: "检查 held-out 访问、规则哈希、复现基线与过程审计。",
    instructions: "核对测试集只在最终评估中被访问一次、评价规则未改写、比较使用复现基线，并保留审计轨迹。",
    tools: ["eval.inspect", "audit.trace", "baseline.check"],
    activation: "auto",
    source: "builtin",
    version: "1.0.0"
  }
];

export function builtinSkills(): Skill[] {
  return BUILTIN_SKILLS.map((skill) => ({ ...skill, tools: [...skill.tools] }));
}

export const DOMAINS = ["材料科学", "机器学习", "生物医学", "社会科学", "其他"];

export const DEFAULT_PREFERENCES: Preferences = {
  autoExpandRunning: true,
  autoScroll: true,
  reduceMotion: false,
  fontScale: 1,
  shortcuts: { ...DEFAULT_SHORTCUTS }
};

export const FONT_SCALE_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0.9, label: "小" },
  { value: 1, label: "标准" },
  { value: 1.1, label: "大" },
  { value: 1.2, label: "特大" }
];

export const MODEL_PROFILES: ModelProfile[] = [
  {
    id: "gpt-5",
    name: "GPT-5 · reasoning",
    short: "GPT-5",
    provider: "OpenAI",
    providerId: "openai",
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
    note: "示例能力：上下文 400k / 输出 16k；档位来自模型配置，并非所有 OpenAI 模型都支持 reasoning。"
  },
  {
    id: "claude-sonnet",
    name: "Claude Sonnet · extended thinking",
    short: "Claude",
    provider: "Anthropic",
    providerId: "anthropic",
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
    note: "示例能力：上下文 200k / 输出 16k；思考档位是 budget tokens，不是回复文本长度。"
  },
  {
    id: "qwen-local",
    name: "Qwen 2.5 · local",
    short: "Qwen",
    provider: "Local / frozen",
    providerId: "local-openai",
    contextWindow: 32768,
    maxOutput: 2048,
    kind: "unsupported",
    defaultStop: null,
    stops: [],
    note: "示例能力：本地冻结模型；未声明可调思考强度，滑块保持不可用。"
  }
];

export const PLUGIN_PRESETS: Record<Plugin["preset"], Omit<Plugin, "id" | "status" | "note"> & { note: string }> = {
  github: {
    name: "GitHub MCP",
    preset: "github",
    transport: "streamable-http",
    url: "https://api.githubcopilot.com/mcp/",
    auth: "oauth",
    readonly: true,
    toolsets: ["repos", "issues", "pull_requests"],
    note: "官方远程 MCP；Streamable HTTP + OAuth；只读优先。静态预览不会真实连接。"
  },
  custom: {
    name: "Custom MCP",
    preset: "custom",
    transport: "streamable-http",
    url: "",
    auth: "env",
    readonly: true,
    toolsets: ["tools"],
    note: "自定义 Streamable HTTP MCP；token 只从 runtime 环境读取。"
  },
  local: {
    name: "Local MCP (registered only)",
    preset: "local",
    transport: "stdio",
    url: "",
    auth: "none",
    readonly: true,
    toolsets: ["tools"],
    note: "仅登记配置，不执行本地命令；避免浏览器触发任意进程。"
  }
};

export function defaultModelSettings(): ModelSettings {
  return {
    profileId: "gpt-5",
    contextLimit: 128000,
    maxReply: 8192,
    thinkingStop: "medium",
    compression: "auto",
    threshold: 70,
    keepRecent: 6,
    summaryTokens: 512
  };
}

let CUSTOM_MODEL_PROFILES: ModelProfile[] = [];

export function setCustomModelProfiles(profiles: ModelProfile[]): void {
  CUSTOM_MODEL_PROFILES = [...profiles];
}

export function allModelProfiles(): ModelProfile[] {
  return [...MODEL_PROFILES, ...CUSTOM_MODEL_PROFILES];
}

export function modelSettingsForProfile(profileId: string): ModelSettings {
  const profiles = allModelProfiles();
  const profile = profiles.find((item) => item.id === profileId) ?? profiles[0];
  return clampModel({
    ...defaultModelSettings(),
    profileId: profile.id,
    contextLimit: Math.min(128000, profile.contextWindow),
    maxReply: Math.min(8192, profile.maxOutput),
    thinkingStop: profile.kind === "unsupported" ? null : profile.defaultStop
  });
}

export function seedGithubPlugin(): Plugin {
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
    note: "演示数据 · 未真实连接；OAuth/token 由 runtime 保管"
  };
}

export function modelProfile(settings: ModelSettings): ModelProfile {
  const profiles = allModelProfiles();
  return profiles.find((profile) => profile.id === settings.profileId) ?? profiles[0];
}

export function activeThinkingStop(settings: ModelSettings): ModelProfile["stops"][number] | null {
  const profile = modelProfile(settings);
  if (profile.kind === "unsupported" || settings.thinkingStop === null) return null;
  return profile.stops.find((stop) => String(stop.value) === String(settings.thinkingStop)) ?? null;
}

export function thinkingLabel(settings: ModelSettings): string {
  return activeThinkingStop(settings)?.label ?? "off";
}

export function formatTokens(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(value % 1000000 ? 1 : 0)}m`;
  if (value >= 1000) return `${Math.round(value / 1000)}k`;
  return String(value);
}

export function formatUsageTokens(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}m`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`;
  return String(Math.round(value));
}

export function compressionNote(settings: ModelSettings): string {
  if (settings.compression === "off") return "不压缩历史；上下文超过上限时请求会失败，而不是静默截断。";
  const at = formatTokens(Math.round(settings.contextLimit * (settings.threshold / 100)));
  return `约在 ${at} tokens 时压缩历史；保留最近 ${settings.keepRecent} 轮与一份 ${settings.summaryTokens} token 摘要。`;
}

export function clampModel(settings: ModelSettings): ModelSettings {
  const profile = modelProfile(settings);
  const maxReply = Math.min(Math.max(settings.maxReply, 256), profile.maxOutput);
  const contextLimit = Math.min(Math.max(settings.contextLimit, 8192), profile.contextWindow);
  const reply = Math.min(maxReply, contextLimit);
  let thinkingStop = profile.kind === "unsupported" ? null : settings.thinkingStop;
  if (profile.kind === "budget" && typeof thinkingStop === "number" && thinkingStop >= reply) {
    const allowed = profile.stops.filter((stop) => Number(stop.value) < reply);
    thinkingStop = allowed.length ? allowed[allowed.length - 1].value : null;
  }
  return {
    ...settings,
    contextLimit,
    maxReply: reply,
    thinkingStop
  };
}

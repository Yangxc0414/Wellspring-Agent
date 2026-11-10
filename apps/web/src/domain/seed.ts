import { AUTO_STAGE_CATALOG, DEFAULT_PREFERENCES, builtinSkills, clampModel, defaultModelSettings, modelSettingsForProfile, seedGithubPlugin } from "./catalog";
import type {
  AccessMode,
  AutoStage,
  Card,
  ContextAttachment,
  EvaluationState,
  EvidenceItem,
  EvolutionCandidate,
  Gate,
  Message,
  Mode,
  PersistedWorkspace,
  ResearchTask,
  TokenUsage,
  Workspace
} from "./types";
import { formatBytes, isoDate, isoDateOffset, isoNow, uid } from "./utils";

export const WORKSPACES: Workspace[] = [
  { id: "materials", name: "材料实验室", note: "钙钛矿 / 稳定性" },
  { id: "agent", name: "Agent 研究", note: "自改进 / archive" },
  { id: "thesis", name: "毕业设计", note: "写作 / 证据" }
];

function system(text: string, at = "08:31:40"): Message {
  return { id: uid("msg"), role: "system", at, text };
}

function agent(text: string, card?: Card, at = "08:32:02"): Message {
  return { id: uid("msg"), role: "agent", at, text, card };
}

function user(text: string, at = "08:32:10"): Message {
  return { id: uid("msg"), role: "user", at, text };
}

function freshStages(): AutoStage[] {
  return AUTO_STAGE_CATALOG.map((stage) => ({ ...stage, status: "pending" }));
}

type UsageInput = Record<string, [prompt: number, completion: number, requests: number]>;

function seedUsage(days: Array<{ offset: number; models: UsageInput }>): Pick<ResearchTask, "usage" | "usageDays"> {
  const usageDays: Record<string, Record<string, TokenUsage>> = {};
  const usage: Record<string, TokenUsage> = {};
  for (const day of days) {
    const key = isoDateOffset(day.offset);
    const bucket = usageDays[key] ?? {};
    for (const [profileId, [prompt, completion, requests]] of Object.entries(day.models)) {
      const total = usage[profileId] ?? { prompt: 0, completion: 0, requests: 0 };
      usage[profileId] = {
        prompt: total.prompt + prompt,
        completion: total.completion + completion,
        requests: total.requests + requests
      };
      const dayUsage = bucket[profileId] ?? { prompt: 0, completion: 0, requests: 0 };
      bucket[profileId] = {
        prompt: dayUsage.prompt + prompt,
        completion: dayUsage.completion + completion,
        requests: dayUsage.requests + requests
      };
    }
    usageDays[key] = bucket;
  }
  return { usage, usageDays };
}

function defaultGates(): Gate[] {
  return [
    { id: "Q0", status: "pending", reason: "coverage / claim admission 未运行" },
    { id: "G1", status: "needs_human", reason: "候选假设需要人工收敛" },
    { id: "G2", status: "not_started", reason: "设计 + 协议尚未冻结" },
    { id: "S5", status: "not_started", reason: "尚未执行 run" },
    { id: "G5", status: "blocked", reason: "没有 EA / Claim / Closure" }
  ];
}

export function emptyEvaluation(): EvaluationState {
  return {
    baselinePaper: null,
    baselineReproduced: null,
    hiddenAccessCount: 0,
    validationSelections: 0,
    evalRuleHash: "—",
    audit: "pending",
    trainCost: null,
    inferenceCost: null,
    interventions: []
  };
}

function demoEvaluation(): EvaluationState {
  return {
    baselinePaper: 300,
    baselineReproduced: 286,
    hiddenAccessCount: 0,
    validationSelections: 6,
    evalRuleHash: "sha256:7c41e2",
    audit: "pending",
    trainCost: 2.4,
    inferenceCost: 1,
    interventions: [
      {
        id: "INT-01",
        label: "baseline reproduction",
        kind: "engineering",
        note: "固定训练/验证/测试划分；以复现基线 286h 作为比较起点",
        at: "2026-10-24T08:04:00"
      },
      {
        id: "INT-02",
        label: "hydration-aware split",
        kind: "domain",
        note: "按湿热循环批次分组，避免同批样品跨训练/验证泄漏",
        at: "2026-10-24T08:12:00"
      },
      {
        id: "INT-03",
        label: "passivation mechanism",
        kind: "domain",
        note: "双分子钝化层 / 界面缺陷密度作为机制假设，而非仅调参",
        at: "2026-10-24T08:20:00"
      },
      {
        id: "INT-04",
        label: "seed budget",
        kind: "engineering",
        note: "3 seeds；没有扩大集成，控制训练与推理成本",
        at: "2026-10-24T08:28:00"
      }
    ]
  };
}

export function planCard(queries: string[], scope: string, budget: string, note: string): Card {
  return { type: "plan", queries, scope, budget, note };
}

function sourcesCard(): Card {
  return {
    type: "sources",
    items: [
      { title: "Huang et al. · 2024 · Joule", meta: "full text · 6 spans", status: "ok" },
      { title: "Wang et al. · 2023 · ACS Energy Lett.", meta: "full text · 4 spans", status: "ok" },
      { title: "Chen et al. · 2025 · Adv. Mater.", meta: "full text · 2 spans", status: "ok" },
      { title: "Liu et al. · 2022 · Sol. RRL", meta: "abstract only · 0 span", status: "warn" }
    ],
    note: "12 个可定位 span；1 条摘要-only 来源只能作为线索。"
  };
}

function ideaCard(): Card {
  return {
    type: "idea",
    gap: "湿热循环后的定量对照缺失：现有来源只报告初始 PCE 与 T80，没有钝化层/未钝化层的配对比较。",
    candidates: [
      { id: "H1", text: "双分子钝化层降低界面缺陷密度，从而延长湿热条件下的 T80。" },
      { id: "H2", text: "钝化层的疏水性（而非缺陷密度）是湿热稳定性的主因。" }
    ],
    note: "候选不是 claim；需要 G1 人工收敛，再进入 S4 设计。"
  };
}

function protocolCard(): Card {
  return {
    type: "protocol",
    hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
    baseline: "未钝化对照",
    metric: "T80（小时）· 初始 PCE",
    seeds: 3,
    controls: ["未钝化", "单分子钝化"],
    status: "G2 needs_human"
  };
}

export function writingCard(options: {
  claimSigned?: boolean;
  protocolFrozen?: boolean;
} = {}): Card {
  const { claimSigned = false, protocolFrozen = false } = options;
  return {
    type: "writing",
    slots: [
      {
        id: "S8.methods",
        label: "Methods · 协议与 seeds",
        status: protocolFrozen ? "bound" : "pending",
        note: protocolFrozen ? "绑定已冻结协议；主指标不可改写" : "需要 G2 协议冻结"
      },
      {
        id: "S9.results",
        label: "Results · 主结果",
        status: claimSigned ? "bound" : "locked",
        note: claimSigned ? "绑定已签 claim 与 EA" : "没有已签 claim；数值不得先填"
      },
      {
        id: "S10.figure",
        label: "Figure · 主图",
        status: claimSigned ? "bound" : "locked",
        note: claimSigned ? "绑定 EA-7c41 / figure manifest" : "先有 EA 才能绑定图"
      },
      {
        id: "S11.abstract",
        label: "Abstract · 结论",
        status: claimSigned ? "bound" : "locked",
        note: claimSigned ? "只陈述已签 claim 的范围" : "claim 未签，摘要保持 locked"
      },
      {
        id: "S12.related",
        label: "Related · 引用",
        status: "pending",
        note: "2 条 citation.related 待补；closure 仍会拦住导出"
      },
      {
        id: "S12.limitations",
        label: "Limitations · 作者声明",
        status: "pending",
        note: "必须由作者写，不能由 agent 代填"
      }
    ],
    note: "槽位只接受已签 claim / EA / closure 引用；正文不会先于证据填数。"
  };
}

export function makeCandidate(): EvolutionCandidate {
  return {
    id: "CAND-RSI-014",
    target: "literature.query_planner",
    patch: "broad retrieval 前追加 review 子查询；预算从 6 调为 3。",
    rationale: "transfer 任务 coverage 偏薄，gap 数连续两轮为 0。",
    predicted: "多 1 篇全文、多 1 个可定位 span；不改变 claim 边界。",
    evidence: "public 3/3 · hidden 2/2 · regression 0 · near-OOD 待复核",
    lease: "未授予",
    status: "pending"
  };
}

const PROTOCOL = {
  hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
  baseline: "未钝化对照",
  metric: "T80（小时）· 初始 PCE",
  seeds: 3,
  controls: ["未钝化", "单分子钝化"]
};

const EVIDENCE: EvidenceItem[] = [
  {
    id: "GAP-001",
    kind: "gap",
    status: "open",
    text: "湿热循环后的配对定量对照缺失。",
    scope: "S1/perovskite",
    refs: ["SPAN-021"],
    note: "4 篇来源中只有 2 篇报告 T80。"
  },
  {
    id: "CAND-H1",
    kind: "hypothesis",
    status: "candidate",
    text: "双分子钝化层降低界面缺陷密度 → 延长 T80。",
    scope: "S2/perovskite",
    refs: ["SPAN-014", "SPAN-021"]
  },
  {
    id: "CAND-H2",
    kind: "hypothesis",
    status: "candidate",
    text: "疏水性而非缺陷密度是湿热稳定性的主因。",
    scope: "S2/perovskite",
    refs: ["SPAN-009"]
  }
];

function seedPerovskite(): ResearchTask {
  return {
    id: "perovskite",
    name: "钙钛矿界面钝化",
    goal: "验证界面钝化对湿热稳定性的影响，并留下可追溯的证据链。",
    domain: "材料科学",
    mode: "research",
    access: "ask",
    status: "active",
    workspaceId: "materials",
    createdAt: "2026-10-24",
    updatedAt: "2026-10-24T08:32:00",
    stage: 1,
    completedStages: [0],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelSettings(),
    ...seedUsage([
      { offset: -28, models: { "gpt-5": [3200, 480, 1] } },
      { offset: -21, models: { "gpt-5": [4100, 680, 1] } },
      { offset: -18, models: { "claude-sonnet": [4200, 540, 1] } },
      { offset: -14, models: { "gpt-5": [5300, 820, 1] } },
      { offset: -10, models: { "qwen-local": [2100, 460, 1] } },
      { offset: -7, models: { "gpt-5": [5000, 900, 1] } },
      { offset: -4, models: { "claude-sonnet": [5400, 700, 1] } },
      { offset: 0, models: { "gpt-5": [7200, 1380, 1] } }
    ]),
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
    coverage: { sources: 4, spans: 12, gaps: 2, abstractOnly: 1 },
    evidence: EVIDENCE.map((item) => ({ ...item, refs: [...item.refs] })),
    protocol: null,
    protocolFrozen: false,
    run: null,
    evaluation: demoEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: freshStages().map((stage, index) => (index === 0 ? { ...stage, status: "done" } : stage)),
    messages: [
      system("STATIC WORKSPACE · 示例状态；不调用模型、不执行真实实验、不产生真实 claim。"),
      agent("项目已接入。我会先把问题拆成可检索的子问题，再决定是否值得进入实验。", planCard(
        ["界面钝化 湿热稳定性", "perovskite passivation damp heat", "passivation layer defect density"],
        "2020–2026 · 中英双语 · 只读公开摘要/全文",
        "6 sources · span-only",
        "摘要-only 只作 SourceHit；没有全文不生成 span，也不进入 claim。"
      )),
      user("先调研界面钝化与长期稳定性的证据，重点看湿热稳定性。"),
      agent(
        "**检索完成** · 4 sources\n\n- 3 条全文，1 条摘要-only\n- 12 个可定位 span\n- 2 个 coverage gap\n\n> 摘要-only 只作线索，不进入 claim。",
        sourcesCard()
      ),
      agent(
        "### 关键 gap\n湿热循环后的配对定量对照缺失。\n\n- 足以支撑一个可否证的假设\n- 还不够支撑 claim\n\n> 候选不是 claim；需要 G1 人工收敛。",
        ideaCard()
      )
    ]
  };
}

function seedArchives(): ResearchTask {
  return {
    id: "archives",
    name: "自改进 agent 的 archive 使用",
    goal: "理解自改进 coding agent 如何选择、保留与复用 archive 中的历史版本。",
    domain: "机器学习",
    mode: "research",
    access: "ask",
    status: "active",
    workspaceId: "agent",
    createdAt: "2026-10-24",
    updatedAt: "2026-10-24T08:20:00",
    stage: 0,
    completedStages: [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelSettings(),
    ...seedUsage([
      { offset: -5, models: { "gpt-5": [3700, 560, 1] } },
      { offset: -1, models: { "gpt-5": [3700, 560, 1] } }
    ]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 4, total: 30 },
    gates: defaultGates(),
    coverage: { sources: 0, spans: 0, gaps: 0, abstractOnly: 0 },
    evidence: [],
    protocol: null,
    protocolFrozen: false,
    run: null,
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: freshStages(),
    messages: [
      system("STATIC WORKSPACE · 示例状态；不调用模型、不执行真实实验。"),
      user("自改进 agent 到底怎么使用 archive？我想先做一轮文献调研。"),
      agent(
        "我会先区分三类 archive，再判断哪些机制有可核验证据：\n\n- 代码版本 archive\n- 轨迹 / 反思 archive\n- 评测结果 archive\n\n> 先形成 span，再谈复用机制。",
        planCard(
          ["self-improving agent archive", "Darwin Gödel Machine stepping stones", "agent memory reuse lineage"],
          "2024–2026 · arXiv / 会议",
          "6 sources · span-only",
          "先宽后深；摘要-only 来源不生成 span。"
        )
      )
    ]
  };
}

function seedThesisTask(
  id: string,
  name: string,
  goal: string,
  updatedAt: string,
  mode: Mode = "research"
): ResearchTask {
  return {
    id,
    name,
    goal,
    domain: "写作 / 证据",
    mode,
    access: "ask",
    status: "active",
    workspaceId: "thesis",
    createdAt: "2026-10-23",
    updatedAt,
    stage: mode === "writing" ? 6 : 0,
    completedStages: [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelSettings(),
    ...seedUsage([]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 0, total: 30 },
    gates: defaultGates(),
    coverage: { sources: 0, spans: 0, gaps: 0, abstractOnly: 0 },
    evidence: [],
    protocol: null,
    protocolFrozen: false,
    run: null,
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: freshStages(),
    messages: [
      system("STATIC WORKSPACE · 示例任务；不调用模型、不执行真实实验。"),
      agent(
        mode === "writing"
          ? `任务已创建：${name}。写作从槽位开始；没有已签 claim 之前，结果与摘要槽位保持 locked。`
          : `任务已创建：${name}。这是毕业设计工作区里的静态示例；可以从调研开始，也可以直接设计实验。`
      ),
      mode === "writing"
        ? agent(
            "先把已签 claim、冻结协议与图 manifest 绑定到槽位；正文不得先于证据填数。",
            writingCard()
          )
        : agent(
            "先明确证据边界，再决定是否进入实验。",
            planCard(
              ["证据闭合 writing agent", "claim span provenance", "中文核刊 结构"],
              "2022–2026 · 中文/英文",
              "4 sources · span-only",
              "摘要-only 只作线索；没有全文不生成 span。"
            )
          )
    ]
  };
}

export function createSeedWorkspace(): PersistedWorkspace {
  return {
    version: 1,
    selectedTaskId: "perovskite",
    activeWorkspaceId: "materials",
    preferences: { ...DEFAULT_PREFERENCES, shortcuts: { ...DEFAULT_PREFERENCES.shortcuts } },
    workspaces: WORKSPACES,
    plugins: [seedGithubPlugin()],
    skills: builtinSkills(),
    memory: [],
    archivedTaskIds: [],
    tasks: [
      seedPerovskite(),
      seedArchives(),
      seedThesisTask("evidence-writing", "证据驱动科研写作系统", "把 claim 与 span 的绑定做成可审计的写作工作流。", "2026-10-23T16:40:00", "writing"),
      seedThesisTask("proposal-review", "项目命题设计与反思", "收敛毕设命题、边界与验证顺序。", "2026-10-23T15:20:00")
    ]
  };
}

export function createTask(input: {
  name: string;
  goal: string;
  domain: string;
  mode: Mode;
  workspaceId: string;
  access?: AccessMode;
  profileId?: string;
  thinkingStop?: string | number | null;
}): ResearchTask {
  const mode = input.mode;
  const messages: Message[] = [
    system("STATIC WORKSPACE · 新任务；示例状态，不调用模型、不执行真实实验。"),
    agent(`任务已创建：${input.name}。我会先明确问题边界，再选择调研、实验或受治理全自动。`)
  ];
  if (mode === "research") {
    messages.push(
      agent(
        "先给你一个检索计划；确认后再进入 span 与 gap。",
        planCard(
          ["研究问题 关键词", "英文对应检索式", "review / survey 入口"],
          "近五年 · 中英双语 · 公开摘要/全文",
          "4 sources · span-only",
          "摘要-only 只作线索；没有全文不生成 span。"
        )
      )
    );
  } else if (mode === "experiment") {
    messages.push(
      agent(
        "本任务从实验设计开始：S1/S2 已标为 skipped，G1 仍未收敛；结果槽保持 pending，直到 EA 与人签 claim。",
        protocolCard()
      )
    );
  } else if (mode === "writing") {
    messages.push(
      agent(
        "写作从槽位开始：没有已签 claim，结果与摘要槽位保持 locked；可以先去补齐证据，或检查已有边界。",
        writingCard()
      )
    );
  } else {
    messages.push(
      agent("全自动会从 S1 跑到人工门。你可以随时暂停、单步或停止；claim 不会被自动签署。")
    );
  }

  return {
    id: uid("task"),
    name: input.name.trim(),
    goal: input.goal.trim(),
    domain: input.domain,
    mode,
    access: input.access ?? "ask",
    status: "active",
    workspaceId: input.workspaceId,
    createdAt: isoDate(),
    updatedAt: isoNow(),
    stage: mode === "experiment" ? 2 : mode === "writing" ? 6 : 0,
    completedStages: [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: clampModel({
      ...modelSettingsForProfile(input.profileId ?? "glm-5.3-flash"),
      ...(input.thinkingStop !== undefined ? { thinkingStop: input.thinkingStop } : {})
    }),
    ...seedUsage([]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 0, total: 30 },
    gates: mode === "experiment"
      ? [
          { id: "Q0", status: "pending", reason: "尚未运行检索" },
          { id: "G1", status: "needs_human", reason: "尚未收敛假设" },
          { id: "G2", status: "needs_human", reason: "协议等待人工冻结" },
          { id: "S5", status: "not_started", reason: "尚未执行 run" },
          { id: "G5", status: "blocked", reason: "没有 Claim / Closure" }
        ]
      : defaultGates(),
    coverage: { sources: 0, spans: 0, gaps: 0, abstractOnly: 0 },
    evidence: [],
    protocol: mode === "experiment" ? { ...PROTOCOL, controls: [...PROTOCOL.controls] } : null,
    protocolFrozen: false,
    run: null,
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: mode === "experiment"
      ? freshStages().map((stage, index) => (index < 2 ? { ...stage, status: "skipped" as const } : stage))
      : freshStages(),
    messages
  };
}

export function createConversationTask(input: {
  text: string;
  workspaceId: string;
  access: AccessMode;
  profileId?: string;
  thinkingStop?: string | number | null;
  attachments?: ContextAttachment[];
}): ResearchTask {
  const text = input.text.trim();
  const clean = text.replace(/[#*>`]/g, "").replace(/\s+/g, " ");
  const topic = clean.slice(0, 22) || "研究问题";
  const base = createTask({
    name: clean.slice(0, 26) || "新会话",
    goal: text.slice(0, 220),
    domain: "其他",
    mode: "research",
    workspaceId: input.workspaceId,
    access: input.access,
    profileId: input.profileId,
    thinkingStop: input.thinkingStop
  });
  const attachments = input.attachments ?? [];
  const contextNote = attachments.length
    ? system(
        "已附加上下文（仅元数据，不进入证据链）：" +
          attachments
            .map((item) =>
              `${item.kind === "folder" ? "文件夹" : "文件"} ${item.name}（${item.files} 个文件，${formatBytes(item.bytes)}${item.source === "workspace" ? "，工作区登记" : ""}）`
            )
            .join("；")
      )
    : null;
  return {
    ...base,
    messages: [
      system("STATIC WORKSPACE · 新会话；示例状态，不调用模型、不执行真实实验。"),
      user(text),
      ...(contextNote ? [contextNote] : []),
      agent(
        "已收到问题。先把它拆成可检索的子问题：\n\n- 明确研究对象与时间范围\n- 生成中英检索式\n- 先登记 span，再判断 gap\n\n> 摘要-only 不生成 span，也不进入 claim。",
        planCard(
          [topic, `${topic} review`, "英文对应检索式"],
          "近五年 · 中英双语 · 公开摘要/全文",
          "4 sources · span-only",
          "摘要-only 只作线索；没有全文不生成 span。"
        )
      )
    ]
  };
}
